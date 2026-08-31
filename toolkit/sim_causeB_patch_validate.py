#!/usr/bin/env python3
"""
177차: 176차가 검증한 원인B 가설(리드없는 cruise 모드에서 A_CHANGE_COST=200
고정이 route 감속 스케줄 추종을 구조적으로 지연시킨다)에 대한 실제 패치
(long_mpc.py 내 `route_decel_rate` 기반 a_change_cost 완화 게이트, L1348~1367
부근)를 검증한다.

`sim_acados_causeB_signflip.py`(176차 1차)와 달리, 이 스크립트는
`mpc.a_change_cost`를 외부에서 강제로 override하지 않는다 -- 패치가 이미
update() 내부에서 매 사이클 self.a_change_cost를 자체 계산하므로, override는
그 즉시 다음 update() 호출에서 덮어써져 무의미하다. 대신:
  - **패치 ON(기본, 현재 코드 그대로)**: 아무것도 건드리지 않고 그대로 실행
  - **패치 OFF(비교군)**: 모듈 상수 `CRUISE_DECEL_RATE_RELAX_LOW/HIGH`를
    실행 중(import 후) 비현실적으로 큰 값으로 monkeypatch -- route_decel_rate가
    항상 LOW 미만이 되어 interp가 절대 완화 구간에 들어가지 않음(=기존
    A_CHANGE_COST=200 고정 동작과 동일). 프로덕션 코드에는 이런 토글을
    추가하지 않는다(글로벌 kill-switch 금지 원칙, WIP.md 176차 계속 참고) --
    monkeypatch는 이 검증 스크립트 안에서만 유효.

시나리오는 `sim_acados_causeB_signflip.py`(176차 1차)와 동일한 174차 요약
특성(vEgo 57.5kph 시작, target 57.9->48.1kph 3초 램프, leadStatus=False)을
그대로 재사용 -- route `6310bba9b8` raw zip이 이번 세션엔 캐싱돼 있지 않아
실측 프레임 재주입은 불가(176차 계속이 이미 실측으로 재검증 완료했으므로
이 스크립트는 "패치가 그 검증된 방향대로 실제로 동작하는가"만 합성
시나리오로 재확인하는 목적).

**사용**:
```
bash devnotes/toolkit/build_acados_long_mpc.sh
export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
export PYTHONPATH=/home/claude/ryu
python3 devnotes/toolkit/sim_causeB_patch_validate.py
```
"""
import sys
exec(open('/home/claude/devnotes/toolkit/acados_stub_prelude.py').read())

import numpy as np
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib import long_mpc
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc, N, A_CHANGE_COST

KPH_TO_MS = 1.0 / 3.6


class FakeLead:
    def __init__(self):
        self.status = False
        self.radar = False
        self.dRel = 0.0
        self.vRel = 0.0
        self.vLead = 0.0
        self.aLeadK = 0.0
        self.aLeadTau = 0.0
        self.jLead = 0.0
        self.modelProb = 0.0


class FakeRadarState:
    def __init__(self):
        self.leadOne = FakeLead()
        self.leadTwo = FakeLead()


class FakeCarrot:
    def __init__(self, v_cruise_ms, mode='acc'):
        self.j_lead_factor = 0.0
        self.comfort_brake = 2.5
        self.stop_distance = 6.0
        self.v_cruise = v_cruise_ms
        self.stop_dist = 1000.0
        self.mode = mode
        self.autoNaviSpeedDecelRate = 1.5
        self.trafficStopDistanceAdjust = 2.5
        self._t_follow_last = 1.2

    def get_T_FOLLOW(self, personality=0, v_ego=0.0, a_ego=0.0):
        return 1.2

    def dynamic_t_follow(self, t_follow, lead, desired_follow_distance, prev_a):
        return t_follow

    def apply_t_follow(self, t_follow, adjust_t_follow=0.0):
        if t_follow > self._t_follow_last:
            t_follow = min(t_follow, self._t_follow_last + 0.1 * DT_MDL)
        self._t_follow_last = float(t_follow)
        return float(t_follow + adjust_t_follow)


def run_scenario(label, duration_s=4.0, log=True):
    mpc = LongitudinalMpc(mode='acc')
    mpc.set_accel_limits(-2.0, 1.5)

    v_ego = 57.5 * KPH_TO_MS
    a_ego = 0.5
    x_ego = 0.0

    v_target_start = 57.9 * KPH_TO_MS
    v_target_end = 48.1 * KPH_TO_MS
    ramp_dur = 3.0

    radarstate = FakeRadarState()

    dt = DT_MDL
    n_steps = int(duration_s / dt)
    zeros = np.zeros(N + 1)

    rows = []
    mpc.set_cur_state(v_ego, a_ego)
    reset_state = True
    for i in range(n_steps):
        t = i * dt
        frac = min(1.0, t / ramp_dur)
        v_cruise = v_target_start + (v_target_end - v_target_start) * frac

        carrot = FakeCarrot(v_cruise_ms=v_cruise, mode='acc')
        x = zeros.copy(); v = zeros.copy(); a = zeros.copy(); j = zeros.copy()

        # 실제 longitudinal_planner.py 호출 순서(220행 set_weights -> 225행
        # update)와 동일: set_weights()가 "직전 사이클 update()가 계산한"
        # self.a_change_cost를 solver 비용행렬에 반영(1사이클 지연은 기존
        # 리드 기반 interp와 동일한 기존 설계) -- 그 다음 update()가 이번
        # 사이클용 self.a_change_cost를 새로 계산해 다음 사이클에 넘긴다.
        mpc.set_weights(a_change_cost_starting=long_mpc.A_CHANGE_COST_STARTING)
        mpc.update(carrot, reset_state, radarstate, v_cruise, x, v, a, j)
        reset_state = False

        a_cmd = float(mpc.a_solution[1])

        rows.append(dict(t=t, v_ego_kph=v_ego / KPH_TO_MS, v_cruise_kph=v_cruise / KPH_TO_MS,
                          a_ego=a_ego, a_cmd=a_cmd, gap_kph=(v_ego - v_cruise) / KPH_TO_MS,
                          a_change_cost=mpc.a_change_cost, route_decel_rate=mpc.route_decel_rate))

        a_ego = a_cmd
        v_ego = max(0.0, v_ego + a_ego * dt)
        x_ego += v_ego * dt
        mpc.set_cur_state(v_ego, a_ego)

    sign_flip_t = None
    for r in rows:
        if r['a_ego'] < 0.0:
            sign_flip_t = r['t']
            break

    if log:
        print(f"\n=== {label} ===")
        print(f"{'t':>5} {'v_ego':>7} {'v_cruise':>9} {'a_ego':>7} {'a_cmd':>7} "
              f"{'gap(kph)':>9} {'a_chg_cost':>10} {'route_rate':>10}")
        for r in rows[::2]:
            print(f"{r['t']:5.2f} {r['v_ego_kph']:7.2f} {r['v_cruise_kph']:9.2f} "
                  f"{r['a_ego']:7.3f} {r['a_cmd']:7.3f} {r['gap_kph']:9.2f} "
                  f"{r['a_change_cost']:10.1f} {r['route_decel_rate']:10.3f}")
        print(f"-> 가속(+)->감속(-) 부호전환 시각: "
              f"{sign_flip_t if sign_flip_t is not None else 'N/A(전 구간 미전환)'}s")

    return rows, sign_flip_t


def gap_at(rows, t_target):
    best = min(rows, key=lambda r: abs(r['t'] - t_target))
    return best['gap_kph']


if __name__ == '__main__':
    print("### 패치 ON (현재 코드, route_decel_rate 게이트 활성) ###")
    rows_on, flip_on = run_scenario("패치 ON")

    print("\n### 패치 OFF (비교군 -- CRUISE_DECEL_RATE_RELAX_* monkeypatch로 완화 무력화) ###")
    orig_low = long_mpc.CRUISE_DECEL_RATE_RELAX_LOW
    orig_high = long_mpc.CRUISE_DECEL_RATE_RELAX_HIGH
    long_mpc.CRUISE_DECEL_RATE_RELAX_LOW = 1e6
    long_mpc.CRUISE_DECEL_RATE_RELAX_HIGH = 1e6 + 1.0
    try:
        rows_off, flip_off = run_scenario("패치 OFF(=기존 200 고정과 동일)")
    finally:
        long_mpc.CRUISE_DECEL_RATE_RELAX_LOW = orig_low
        long_mpc.CRUISE_DECEL_RATE_RELAX_HIGH = orig_high

    print("\n=== 비교 요약 ===")
    print(f"패치 ON  부호전환: {flip_on}s")
    print(f"패치 OFF 부호전환: {flip_off}s")
    if flip_on is not None and flip_off is not None:
        print(f"차이: {flip_off - flip_on:.2f}s (양수면 패치가 그만큼 더 빨리 감속 전환)")

    print(f"\nt=3.0s gap(패치 ON) ={gap_at(rows_on, 3.0):.2f}kph "
          f"(174차 실측 t=832.45 gap≈+4.35kph)")
    print(f"t=3.0s gap(패치 OFF)={gap_at(rows_off, 3.0):.2f}kph")
