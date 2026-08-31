#!/usr/bin/env python3
"""
175차 계속(176차): acados 실솔버로 174차 원인B("A_CHANGE_COST=200이 리드없는
cruise 모드에서 가속->감속 부호전환을 구조적으로 지연시킨다") 재현검증.

[중요 제약] route `00000372--6310bba9b8--5,6` raw zip이 devnotes 캐시에
없어(172/174차 모두 재업로드였고 이번 세션엔 미제공) 실측 프레임별 원시값을
그대로 주입할 수 없음. 대신 FINDINGS.md 174차가 기록한 요약 특성(vEgo가
liveRouteSpeed와 ~57~58kph에서 교차, 이후 목표가 57.9->48.1kph로 ~3초간
0.75~0.95 m/s² 요구감속, leadStatus=False)을 그대로 재현한 **통제된 합성
시나리오**로 폐루프(closed-loop) 시뮬레이션함. 목적은 "이 비용함수 구조에서
가속->감속 부호전환이 구조적으로 느린가"라는 정성적 가설 검증이지 이번
특정 route의 프레임 단위 정량 재현이 아님 -- 결과 해석 시 이 점 명시 필요.

폐루프 방식: 매 사이클 mpc.update() 호출 -> a_solution[1](다음 스텝
명령가속도)을 실제 ego가 그대로 따른다고 가정하고 v_ego/x_ego를 적분
전진 -> 다음 사이클 set_cur_state()에 주입. 이는 실차의 롱컨트롤(가속페달/
브레이크 추종 지연)을 이상화(무지연)한 것이므로, 실측 대비 오히려 관대한
(더 빠르게 반응하는) 조건 -- 그럼에도 지연이 나타나면 가설이 강하게 뒷받침됨.

두 조건 비교:
  A) baseline: A_CHANGE_COST=200 (현재 코드 그대로)
  B) 완화: A_CHANGE_COST=20 (process_lead가 리드 저크 큰 경우 적용하는 최소값,
     174차 정적분석이 "리드 있으면 최대 20까지 완화"라고 지목한 값)
"""
import os, sys
sys.path.insert(0, '/home/claude/devnotes/toolkit')
exec(open('/home/claude/devnotes/toolkit/acados_stub_prelude.py').read())

import numpy as np
from openpilot.common.realtime import DT_MDL
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
    """174차/175차 제약: Params 의존 없이 update()가 요구하는 최소 인터페이스만
    구현. T_FOLLOW 자체는 이번 가설(A_CHANGE_COST 부호전환 지연)과 무관하므로
    표준(personality=standard) 근사 고정값으로 단순화함 -- 결과 해석 시
    참고."""
    def __init__(self, v_cruise_ms, mode='acc'):
        self.j_lead_factor = 0.0
        self.comfort_brake = 2.5
        self.stop_distance = 6.0
        self.v_cruise = v_cruise_ms
        self.stop_dist = 1000.0  # cruise_obstacle이 항상 최소가 되도록 충분히 크게
        self.mode = mode
        self.autoNaviSpeedDecelRate = 1.5
        self.trafficStopDistanceAdjust = 2.5
        self._t_follow_last = 1.2

    def get_T_FOLLOW(self, personality=0, v_ego=0.0, a_ego=0.0):
        return 1.2

    def dynamic_t_follow(self, t_follow, lead, desired_follow_distance, prev_a):
        return t_follow  # leadStatus=False 전구간 -> passthrough

    def apply_t_follow(self, t_follow, adjust_t_follow=0.0):
        if t_follow > self._t_follow_last:
            t_follow = min(t_follow, self._t_follow_last + 0.1 * DT_MDL)
        self._t_follow_last = float(t_follow)
        return float(t_follow + adjust_t_follow)


def run_scenario(a_change_cost_override, label, duration_s=4.0, log=True):
    mpc = LongitudinalMpc(mode='acc')
    mpc.a_change_cost = a_change_cost_override  # __init__/reset()이 기본 A_CHANGE_COST로
    mpc.set_weights()                            # 세팅했으므로 override 후 재적용
    mpc.set_accel_limits(-2.0, 1.5)              # A_CRUISE_MIN=-2.0(longitudinal_planner.py), max는 여유값

    v_ego = 57.5 * KPH_TO_MS      # 174차: vEgo가 liveRouteSpeed와 교차하는 시작점
    a_ego = 0.5                    # 174차 요약: 교차 직전 +0.3~+1.0 구간의 중간값
    x_ego = 0.0

    v_target_start = 57.9 * KPH_TO_MS
    v_target_end = 48.1 * KPH_TO_MS
    ramp_dur = 3.0  # 174차: ~3초 구간

    radarstate = FakeRadarState()  # leadStatus=False 고정 (174차 핵심구간 조건)

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

        mpc.update(carrot, reset_state, radarstate, v_cruise, x, v, a, j)
        reset_state = False

        a_cmd = float(mpc.a_solution[1])  # 다음 스텝 명령가속도(폐루프 적분에 사용)

        rows.append(dict(t=t, v_ego_kph=v_ego / KPH_TO_MS, v_cruise_kph=v_cruise / KPH_TO_MS,
                          a_ego=a_ego, a_cmd=a_cmd, gap_kph=(v_ego - v_cruise) / KPH_TO_MS))

        # 폐루프 전진(이상화, 지연 없음): 다음 상태로 명령가속도를 그대로 적용
        a_ego = a_cmd
        v_ego = max(0.0, v_ego + a_ego * dt)
        x_ego += v_ego * dt
        mpc.set_cur_state(v_ego, a_ego)

    # 부호전환 시각(a_ego가 처음으로 음수가 되는 시각) 산출
    sign_flip_t = None
    for r in rows:
        if r['a_ego'] < 0.0:
            sign_flip_t = r['t']
            break

    if log:
        print(f"\n=== {label} (A_CHANGE_COST={a_change_cost_override}) ===")
        print(f"{'t':>5} {'v_ego':>7} {'v_cruise':>9} {'a_ego':>7} {'a_cmd':>7} {'gap(kph)':>9}")
        for r in rows[::2]:  # 0.1s 간격 출력
            print(f"{r['t']:5.2f} {r['v_ego_kph']:7.2f} {r['v_cruise_kph']:9.2f} "
                  f"{r['a_ego']:7.3f} {r['a_cmd']:7.3f} {r['gap_kph']:9.2f}")
        print(f"-> 가속(+)->감속(-) 부호전환 시각: "
              f"{sign_flip_t if sign_flip_t is not None else 'N/A(전 구간 미전환)'}s")

    return rows, sign_flip_t


if __name__ == '__main__':
    rows_base, flip_base = run_scenario(A_CHANGE_COST, "baseline(현재 코드)")
    rows_relaxed, flip_relaxed = run_scenario(20.0, "완화(A_CHANGE_COST=20, 리드있음 최소완화값)")

    print("\n=== 비교 요약 ===")
    print(f"baseline(200)  부호전환: {flip_base}s")
    print(f"완화(20)       부호전환: {flip_relaxed}s")
    if flip_base is not None and flip_relaxed is not None:
        print(f"차이: {flip_base - flip_relaxed:.2f}s (양수면 baseline이 그만큼 더 느림)")

    # t=3.0s(=목표 하강 종료 시점) 시점 gap 비교 -- 174차 실측(0.17->3.75kph)과 대조
    def gap_at(rows, t_target):
        best = min(rows, key=lambda r: abs(r['t'] - t_target))
        return best['gap_kph']

    print(f"\nt=3.0s gap(baseline)={gap_at(rows_base, 3.0):.2f}kph  "
          f"(174차 실측 t=832.45 gap≈+4.35kph)")
    print(f"t=3.0s gap(relaxed) ={gap_at(rows_relaxed, 3.0):.2f}kph")
