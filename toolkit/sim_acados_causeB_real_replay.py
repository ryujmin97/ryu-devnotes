#!/usr/bin/env python3
"""
176차 계속: 174/172차와 동일 route(`00000372--6310bba9b8--5,6`)의 실측 raw
로그(사용자 재업로드, 176차)를 acados 실솔버에 프레임 단위로 그대로 주입하는
정밀 재현. `sim_acados_causeB_signflip.py`(합성 시나리오, 176차 1차)의 후속 --
그 스크립트가 "정성적으로 A_CHANGE_COST 크기가 부호전환 속도에 영향을 준다"를
확인했다면, 이 스크립트는 "그 정성적 결론이 이번 route의 실제 프레임에서도
그대로 성립하는가"를 확인.

**방식(open-loop, 매 프레임 실측 상태로 리셋)**: 폐루프 적분(이전 스크립트)과
달리, 매 프레임 `mpc.set_cur_state(real_vEgo, real_aEgo)`로 실측 상태 그대로
주입 후 `update()` 1회 호출 -> `a_solution[1]`(다음 프레임 명령가속도 예측치)을
실측 다음 프레임 aEgo와 비교. 이렇게 하면 "실제 그 순간 그 상태에서 solver가
정말로 이렇게 반응이 느렸는가"를 실측과 1:1로 대조할 수 있음(폐루프처럼
시뮬레이션 자체 오차가 누적되지 않음). 내부 타이머 상태(discontinuity 부스트,
lead acquisition ramp 등)는 매 프레임 update() 호출 순서를 따라 정상적으로
전진(연속 호출이므로 정확).

리드 데이터는 leadStatus/leadDRel/leadVRel/leadVLead/leadALeadK/leadRadar/
leadModelProb를 CSV에서 그대로 사용. leadJLead/aLeadTau는 CSV 미포함(추출
컬럼에 없음) -- jLead=0.0(전 프레임 유사값 없어 보수적으로 무시), aLeadTau는
long_mpc.py가 import하는 radard.py의 `_LEAD_ACCEL_TAU` 기본값 사용.

두 조건(baseline A_CHANGE_COST=200 / 완화 20)을 동일 실측 시퀀스에 각각
독립 실행해 비교.

**사용**:
```
bash devnotes/toolkit/build_acados_long_mpc.sh   # 컨테이너 리셋마다 필요
export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
export PYTHONPATH=/home/claude/ryu
python3 devnotes/toolkit/sim_acados_causeB_real_replay.py <csv_path> [--t-start 829.0] [--t-end 832.6]
```
"""
import sys, csv, argparse
exec(open('/home/claude/devnotes/toolkit/acados_stub_prelude.py').read())

import numpy as np
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc, N, A_CHANGE_COST
from openpilot.selfdrive.controls.radard import _LEAD_ACCEL_TAU

KPH_TO_MS = 1.0 / 3.6

# 176차 계속: 실제 carrot.v_cruise로 어느 컬럼이 더 적합한지 두 후보를 비교
# 가능하게 전역 스위치로 뺌(기본은 liveRouteSpeed, --v-cruise-col로 변경 가능)
V_CRUISE_COL = 'liveRouteSpeed'


class FakeLead:
    def __init__(self, status=False, dRel=0.0, vRel=0.0, vLead=0.0, aLeadK=0.0,
                 radar=False, modelProb=0.0):
        self.status = status
        self.dRel = dRel
        self.vRel = vRel
        self.vLead = vLead
        self.aLeadK = aLeadK
        self.aLeadTau = _LEAD_ACCEL_TAU
        self.jLead = 0.0  # CSV 미추출 -- 보수적으로 0 (174차 정적분석: leadStatus=False
                           # 구간이 핵심이라 이 값의 영향은 제한적)
        self.radar = radar
        self.modelProb = modelProb


class FakeRadarState:
    def __init__(self, lead_one, lead_two=None):
        self.leadOne = lead_one
        self.leadTwo = lead_two if lead_two is not None else FakeLead()


class FakeCarrot:
    def __init__(self, mode='acc'):
        self.j_lead_factor = 0.0
        self.comfort_brake = 2.5
        self.stop_distance = 6.0
        self.v_cruise = 0.0
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


def load_rows(csv_path, t_start, t_end):
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if t_start <= float(r['t']) <= t_end]
    return rows


def run_replay(rows, a_change_cost_override, label, log=True):
    mpc = LongitudinalMpc(mode='acc')
    mpc.a_change_cost = a_change_cost_override
    mpc.set_weights()
    mpc.set_accel_limits(-2.0, 1.5)

    carrot = FakeCarrot(mode='acc')
    zeros = np.zeros(N + 1)

    out = []
    reset_state = True
    for i, r in enumerate(rows):
        t = float(r['t'])
        v_ego = float(r['vEgo'])
        a_ego = float(r['aEgo'])
        lead_status = r['leadStatus'] == 'True'
        lead = FakeLead(
            status=lead_status,
            dRel=float(r['leadDRel']) if r['leadDRel'] else 0.0,
            vRel=float(r['leadVRel']) if r['leadVRel'] else 0.0,
            vLead=float(r['leadVLead']) if r['leadVLead'] else 0.0,
            aLeadK=float(r['leadALeadK']) if r['leadALeadK'] else 0.0,
            radar=r['leadRadar'] == 'True',
            modelProb=float(r['leadModelProb']) if r['leadModelProb'] else 0.0,
        )
        radarstate = FakeRadarState(lead)

        v_cruise = float(r[V_CRUISE_COL]) * KPH_TO_MS
        carrot.v_cruise = v_cruise

        mpc.set_cur_state(v_ego, a_ego)  # 실측 상태로 매 프레임 강제 리셋(open-loop)
        x = zeros.copy(); v = zeros.copy(); a = zeros.copy(); j = zeros.copy()
        mpc.update(carrot, reset_state, radarstate, v_cruise, x, v, a, j)
        reset_state = False

        a_pred_next = float(mpc.a_solution[1])
        actual_next_a = float(rows[i + 1]['aEgo']) if i + 1 < len(rows) else None

        out.append(dict(t=t, v_ego_kph=v_ego / KPH_TO_MS, live_route_kph=v_cruise / KPH_TO_MS,
                         a_ego_actual=a_ego, a_pred_next=a_pred_next,
                         a_actual_next=actual_next_a, lead_status=lead_status))

    if log:
        print(f"\n=== {label} (A_CHANGE_COST={a_change_cost_override}) ===")
        print(f"{'t':>8} {'vEgo':>7} {'route':>7} {'aEgo(actual)':>13} "
              f"{'a_pred_next':>12} {'a_actual_next':>13} {'lead':>5}")
        for o in out[::2]:
            an = f"{o['a_actual_next']:.3f}" if o['a_actual_next'] is not None else "N/A"
            print(f"{o['t']:8.2f} {o['v_ego_kph']:7.2f} {o['live_route_kph']:7.2f} "
                  f"{o['a_ego_actual']:13.3f} {o['a_pred_next']:12.3f} {an:>13} "
                  f"{'Y' if o['lead_status'] else 'N':>5}")

    return out


def run_closedloop_real_target(rows, a_change_cost_override, label, log=True):
    """오픈루프(위 run_replay)는 매 프레임 실측 상태로 리셋하므로 "누적 지연"
    효과가 지워진다(1프레임짜리 국소 반응만 봄). 이 함수는 실측 t=rows[0]의
    초기상태(v_ego,a_ego)에서 출발해 이후로는 ego 상태를 실측이 아니라
    solver 자신의 a_solution[1]로 적분 전진시키면서, target(liveRouteSpeed)과
    leadOne 트랙 데이터는 실측 시퀀스를 그대로 따라간다(exogenous input로 취급,
    ego 위치가 실측과 달라져도 리드 dRel/vRel은 실측값 그대로 사용 -- 근사).
    실측 실제 vEgo/aEgo 궤적과 나란히 비교해 "그때 다른 A_CHANGE_COST였다면
    얼마나 더 빨리 감속했을까"를 실측 target 궤적 기준으로 정량화."""
    mpc = LongitudinalMpc(mode='acc')
    mpc.a_change_cost = a_change_cost_override
    mpc.set_weights()
    mpc.set_accel_limits(-2.0, 1.5)

    carrot = FakeCarrot(mode='acc')
    zeros = np.zeros(N + 1)

    v_ego = float(rows[0]['vEgo'])
    a_ego = float(rows[0]['aEgo'])
    mpc.set_cur_state(v_ego, a_ego)

    out = []
    reset_state = True
    for i, r in enumerate(rows):
        t = float(r['t'])
        lead_status = r['leadStatus'] == 'True'
        lead = FakeLead(
            status=lead_status,
            dRel=float(r['leadDRel']) if r['leadDRel'] else 0.0,
            vRel=float(r['leadVRel']) if r['leadVRel'] else 0.0,
            vLead=float(r['leadVLead']) if r['leadVLead'] else 0.0,
            aLeadK=float(r['leadALeadK']) if r['leadALeadK'] else 0.0,
            radar=r['leadRadar'] == 'True',
            modelProb=float(r['leadModelProb']) if r['leadModelProb'] else 0.0,
        )
        radarstate = FakeRadarState(lead)
        v_cruise = float(r[V_CRUISE_COL]) * KPH_TO_MS
        carrot.v_cruise = v_cruise

        x = zeros.copy(); v = zeros.copy(); a = zeros.copy(); j = zeros.copy()
        mpc.update(carrot, reset_state, radarstate, v_cruise, x, v, a, j)
        reset_state = False

        a_cmd = float(mpc.a_solution[1])
        out.append(dict(t=t, v_ego_kph=v_ego / KPH_TO_MS, live_route_kph=v_cruise / KPH_TO_MS,
                         a_ego_sim=a_ego, a_ego_actual=float(r['aEgo']),
                         v_ego_actual_kph=float(r['vEgo']) / KPH_TO_MS, lead_status=lead_status))

        # 다음 상태로 solver 자신의 명령가속도를 적분 전진 (폐루프, 실측 dt 사용)
        if i + 1 < len(rows):
            dt_real = float(rows[i + 1]['t']) - t
        else:
            dt_real = DT_MDL
        a_ego = a_cmd
        v_ego = max(0.0, v_ego + a_ego * dt_real)
        mpc.set_cur_state(v_ego, a_ego)

    if log:
        print(f"\n=== 폐루프(실측target추종, 실측초기상태) {label} (A_CHANGE_COST={a_change_cost_override}) ===")
        print(f"{'t':>8} {'vEgo_sim':>9} {'vEgo_actual':>11} {'route':>7} {'aEgo_sim':>9} {'aEgo_actual':>11} {'lead':>5}")
        for o in out[::2]:
            print(f"{o['t']:8.2f} {o['v_ego_kph']:9.2f} {o['v_ego_actual_kph']:11.2f} "
                  f"{o['live_route_kph']:7.2f} {o['a_ego_sim']:9.3f} {o['a_ego_actual']:11.3f} "
                  f"{'Y' if o['lead_status'] else 'N':>5}")

    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path')
    ap.add_argument('--t-start', type=float, default=829.0)
    ap.add_argument('--t-end', type=float, default=832.6)
    ap.add_argument('--mode', choices=['openloop', 'closedloop', 'both'], default='both')
    ap.add_argument('--v-cruise-col', choices=['liveRouteSpeed', 'desiredSpeed'], default='liveRouteSpeed')
    args = ap.parse_args()

    V_CRUISE_COL = args.v_cruise_col

    rows = load_rows(args.csv_path, args.t_start, args.t_end)
    print(f"로드된 프레임: {len(rows)} (t={args.t_start}~{args.t_end})")

    if args.mode in ('openloop', 'both'):
        out_base = run_replay(rows, A_CHANGE_COST, "baseline(현재 코드)")
        out_relaxed = run_replay(rows, 20.0, "완화(A_CHANGE_COST=20)")

        print("\n=== [오픈루프] solver 예측(a_pred_next) vs 실측(a_actual_next) — baseline ===")
        diffs = [(o['a_pred_next'] - o['a_actual_next']) for o in out_base if o['a_actual_next'] is not None]
        print(f"평균 오차(pred-actual): {np.mean(diffs):+.4f} m/s^2, "
              f"RMSE: {np.sqrt(np.mean(np.square(diffs))):.4f}")

        print("\n=== [오픈루프] baseline vs 완화 조건 간 a_pred_next 차이(같은 실측 프레임 기준) ===")
        delta = [(ob['a_pred_next'] - orl['a_pred_next']) for ob, orl in zip(out_base, out_relaxed)]
        print(f"평균 차이: {np.mean(delta):+.4f} m/s^2 (1프레임짜리 국소 반응만 봄 -- 누적 지연 미반영)")

    if args.mode in ('closedloop', 'both'):
        cl_base = run_closedloop_real_target(rows, A_CHANGE_COST, "baseline")
        cl_relaxed = run_closedloop_real_target(rows, 20.0, "완화(20)")

        def find_sign_flip(out):
            for o in out:
                if o['a_ego_sim'] < 0.0:
                    return o['t']
            return None

        flip_base = find_sign_flip(cl_base)
        flip_relaxed = find_sign_flip(cl_relaxed)

        def gap_kph_at(out, t_target):
            best = min(out, key=lambda o: abs(o['t'] - t_target))
            return best['v_ego_kph'] - best['live_route_kph']

        print("\n=== [폐루프] 요약 ===")
        print(f"baseline(200) 부호전환: {flip_base}")
        print(f"완화(20)      부호전환: {flip_relaxed}")
        t_end = rows[-1]['t']
        print(f"t={float(t_end):.2f}s(구간끝) gap: baseline={gap_kph_at(cl_base, float(t_end)):.2f}kph, "
              f"완화={gap_kph_at(cl_relaxed, float(t_end)):.2f}kph, "
              f"실측={float(rows[-1]['vEgo'])/KPH_TO_MS - float(rows[-1]['liveRouteSpeed']):.2f}kph")
