#!/usr/bin/env python3
"""
270차/271차: A_CHANGE_COST route_decel_rate 완화 게이트(177차 도입)를, 269차가
새로 발굴한 실 no-lead 우회전 구간(0000039a--7b602ffb85 seg12-16,
t=2117.0~2127.0, src route->vturn->route 연속 감속, leadStatus=False 전구간)
으로 실측 A/B 재현한다.

176차 sim_acados_causeB_real_replay.py 대비 세 가지 수정:
  (1) V_CRUISE_COL: 이 구간은 route와 vturn이 번갈아 desiredSpeed를
      arbitrate하므로 liveRouteSpeed(route 전용)는 vturn 구간에서 실제
      바인딩 타겟과 어긋난다(실측 확인, WIP 270차). desiredSpeed(carrotMan
      최종 arbitrated target, 모든 소스 공통)를 사용.
  (2) set_weights()/update() 호출 순서: 177차 이후 longitudinal_planner.py가
      매 프레임 set_weights()->update() 순으로 호출하도록 바뀌었고(현재
      self.a_change_cost는 update() 내부에서 매 프레임 갱신됨), 176차
      스크립트는 이 구조 변경 이전(a_change_cost가 상수이던 시절)에
      작성돼 set_weights()를 루프 밖에서 1회만 호출한다 -- 이번 스크립트는
      실제 프로덕션과 동일하게 매 프레임 set_weights()->update() 순서로
      호출한다.
  (3) [271차 추가] 폐루프(closedloop, 자기 상태 적분) 방식은 176차가 이미
      문서화한 한계대로 FakeCarrot 근사(t_follow/jerk_factor 등 실측이
      아닌 상수)가 누적되며 절대치가 실측과 크게 벌어진다(270차 1차
      실행 결과: t=2126.8s에서 baseline sim 최종 vEgo 52.7kph vs 실측
      44.8kph -- 7.9kph 괴리, 상대비교만 가능). 이 한계를 보완하기 위해
      오픈루프(매 프레임 실측 vEgo/aEgo로 강제 리셋, 176차
      run_replay()와 동일 철학이나 (2)의 호출순서 수정 반영) 모드를
      추가한다 -- "그 순간 그 상태에서 solver가 실제로 이렇게 반응이
      느렸는가"를 시뮬레이션 자체 오차 누적 없이 프레임 단위로 직접
      대조 가능.

baseline: 매 프레임 set_weights() 호출 직전에 mpc.a_change_cost=200.0으로
강제 고정(177차 이전 동작 재현, "글로벌 kill-switch"가 아니라 이 study
스크립트 로컬 오버라이드일 뿐 -- production 코드 변경 없음).
patched(현재 코드): a_change_cost를 건드리지 않고 update()가 매 프레임
계산한 값을 다음 프레임 set_weights()가 그대로 읽게 둔다(실제 배포 동작).

사용:
    bash devnotes/toolkit/build_acados_long_mpc.sh
    export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
    export PYTHONPATH=/home/claude/ryu
    python3 sim_acados_causeB_270_real_replay.py <csv> --t-start 2117.0 --t-end 2127.0 [--mode openloop|closedloop|both]
"""
import sys, csv, argparse
exec(open('/home/claude/devnotes/toolkit/acados_stub_prelude.py').read())

import numpy as np
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc, N, A_CHANGE_COST
from openpilot.selfdrive.controls.radard import _LEAD_ACCEL_TAU

KPH_TO_MS = 1.0 / 3.6


class FakeLead:
    def __init__(self, status=False, dRel=0.0, vRel=0.0, vLead=0.0, aLeadK=0.0,
                 radar=False, modelProb=0.0):
        self.status = status
        self.dRel = dRel
        self.vRel = vRel
        self.vLead = vLead
        self.aLeadK = aLeadK
        self.aLeadTau = _LEAD_ACCEL_TAU
        self.jLead = 0.0
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
        self.jerk_factor_apply = 1.0
        self.aChangeCostStarting = 10.0
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


def _make_lead(r):
    return FakeLead(
        status=r['leadStatus'] == 'True',
        dRel=float(r['leadDRel']) if r['leadDRel'] else 0.0,
        vRel=float(r['leadVRel']) if r['leadVRel'] else 0.0,
        vLead=float(r['leadVLead']) if r['leadVLead'] else 0.0,
        aLeadK=float(r['leadALeadK']) if r['leadALeadK'] else 0.0,
        radar=r['leadRadar'] == 'True',
        modelProb=float(r['leadModelProb']) if r['leadModelProb'] else 0.0,
    )


def run_closedloop(rows, v_cruise_col, force_baseline, label, log=True):
    """force_baseline=True: 매 프레임 set_weights() 직전 a_change_cost를
    200으로 강제(177차 이전 재현). False: 프로덕션 그대로(update()가 매
    프레임 쓴 값을 다음 set_weights()가 읽음).
    [271차 주의] ego 상태를 solver 자신의 a_solution[1]로 적분 전진시키는
    폐루프 방식 -- FakeCarrot 근사(상수 t_follow/jerk_factor 등)가
    누적되어 절대치가 실측과 벌어질 수 있음(아래 open-loop과 병기해
    상대비교 용도로만 사용할 것)."""
    mpc = LongitudinalMpc(mode='acc')
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
        lead = _make_lead(r)
        radarstate = FakeRadarState(lead)
        v_cruise = float(r[v_cruise_col]) * KPH_TO_MS
        carrot.v_cruise = v_cruise

        if force_baseline:
            mpc.a_change_cost = A_CHANGE_COST  # 177차 이전 재현: 상수 200 고정

        # [270차 수정] 현재 프로덕션(longitudinal_planner.py L220/225)과
        # 동일하게 매 프레임 set_weights() -> update() 순서로 호출.
        mpc.set_weights(True, jerk_factor=carrot.jerk_factor_apply,
                         a_change_cost_starting=carrot.aChangeCostStarting)

        x = zeros.copy(); v = zeros.copy(); a = zeros.copy(); j = zeros.copy()
        mpc.update(carrot, reset_state, radarstate, v_cruise, x, v, a, j)
        reset_state = False

        a_cmd = float(mpc.a_solution[1])
        out.append(dict(t=t, v_ego_kph=v_ego / KPH_TO_MS, target_kph=v_cruise / KPH_TO_MS,
                         a_ego_sim=a_ego, a_ego_actual=float(r['aEgo']),
                         v_ego_actual_kph=float(r['vEgo']) / KPH_TO_MS,
                         a_change_cost=float(mpc.a_change_cost), lead_status=lead.status))

        if i + 1 < len(rows):
            dt_real = float(rows[i + 1]['t']) - t
        else:
            dt_real = DT_MDL
        a_ego = a_cmd
        v_ego = max(0.0, v_ego + a_ego * dt_real)
        mpc.set_cur_state(v_ego, a_ego)

    if log:
        print(f"\n=== [폐루프] {label} ===")
        print(f"{'t':>10} {'vEgo_sim':>9} {'vEgo_act':>9} {'target':>7} "
              f"{'aEgo_sim':>9} {'aEgo_act':>9} {'a_chg_cost':>11} {'lead':>5}")
        for o in out[::4]:
            print(f"{o['t']:10.3f} {o['v_ego_kph']:9.2f} {o['v_ego_actual_kph']:9.2f} "
                  f"{o['target_kph']:7.1f} {o['a_ego_sim']:9.3f} {o['a_ego_actual']:9.3f} "
                  f"{o['a_change_cost']:11.2f} {'Y' if o['lead_status'] else 'N':>5}")
    return out


def run_openloop(rows, v_cruise_col, force_baseline, label, log=True):
    """[271차 신규] 매 프레임 실측 vEgo/aEgo로 강제 리셋(mpc.set_cur_state) 후
    update() 1회 -> a_solution[1](다음 프레임 명령가속도 예측치)을 실측
    다음 프레임 aEgo와 직접 비교. 폐루프처럼 시뮬레이션 자체 오차가
    누적되지 않아 "그 순간 그 상태에서 solver가 실제로 얼마나 느리게
    반응했는가"를 절대치 기준으로 신뢰도 높게 볼 수 있음(176차
    run_replay()와 동일 철학, (2)의 set_weights/update 호출순서만 수정)."""
    mpc = LongitudinalMpc(mode='acc')
    mpc.set_accel_limits(-2.0, 1.5)

    carrot = FakeCarrot(mode='acc')
    zeros = np.zeros(N + 1)

    out = []
    reset_state = True
    for i, r in enumerate(rows):
        t = float(r['t'])
        v_ego = float(r['vEgo'])
        a_ego = float(r['aEgo'])
        lead = _make_lead(r)
        radarstate = FakeRadarState(lead)
        v_cruise = float(r[v_cruise_col]) * KPH_TO_MS
        carrot.v_cruise = v_cruise

        mpc.set_cur_state(v_ego, a_ego)  # 실측 상태로 매 프레임 강제 리셋(open-loop)

        if force_baseline:
            mpc.a_change_cost = A_CHANGE_COST

        mpc.set_weights(True, jerk_factor=carrot.jerk_factor_apply,
                         a_change_cost_starting=carrot.aChangeCostStarting)

        x = zeros.copy(); v = zeros.copy(); a = zeros.copy(); j = zeros.copy()
        mpc.update(carrot, reset_state, radarstate, v_cruise, x, v, a, j)
        reset_state = False

        a_pred_next = float(mpc.a_solution[1])
        actual_next_a = float(rows[i + 1]['aEgo']) if i + 1 < len(rows) else None

        out.append(dict(t=t, v_ego_kph=v_ego / KPH_TO_MS, target_kph=v_cruise / KPH_TO_MS,
                         a_ego_actual=a_ego, a_pred_next=a_pred_next,
                         a_actual_next=actual_next_a,
                         a_change_cost=float(mpc.a_change_cost), lead_status=lead.status))

    if log:
        print(f"\n=== [오픈루프] {label} ===")
        print(f"{'t':>10} {'vEgo':>7} {'target':>7} {'aEgo(actual)':>13} "
              f"{'a_pred_next':>12} {'a_actual_next':>13} {'a_chg_cost':>11} {'lead':>5}")
        for o in out[::4]:
            an = f"{o['a_actual_next']:.3f}" if o['a_actual_next'] is not None else "N/A"
            print(f"{o['t']:10.3f} {o['v_ego_kph']:7.2f} {o['target_kph']:7.1f} "
                  f"{o['a_ego_actual']:13.3f} {o['a_pred_next']:12.3f} {an:>13} "
                  f"{o['a_change_cost']:11.2f} {'Y' if o['lead_status'] else 'N':>5}")
    return out


def find_sign_flip(out, key='a_ego_sim', start_search_t=None):
    for o in out:
        if start_search_t is not None and o['t'] < start_search_t:
            continue
        if o[key] < 0.0:
            return o['t']
    return None


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path')
    ap.add_argument('--t-start', type=float, default=2117.0)
    ap.add_argument('--t-end', type=float, default=2127.0)
    ap.add_argument('--v-cruise-col', default='desiredSpeed')
    ap.add_argument('--mode', choices=['openloop', 'closedloop', 'both'], default='both')
    args = ap.parse_args()

    rows = load_rows(args.csv_path, args.t_start, args.t_end)
    print(f"로드된 프레임: {len(rows)} (t={args.t_start}~{args.t_end}), v_cruise_col={args.v_cruise_col}")
    print(f"leadStatus 전부 False? {all(r['leadStatus']=='False' for r in rows)}")

    if args.mode in ('openloop', 'both'):
        ol_base = run_openloop(rows, args.v_cruise_col, True, "baseline(A_CHANGE_COST=200 고정, 177차 이전 재현)")
        ol_patch = run_openloop(rows, args.v_cruise_col, False, "현재 프로덕션(route_decel_rate 완화 게이트 활성)")

        diffs_base = [(o['a_pred_next'] - o['a_actual_next']) for o in ol_base if o['a_actual_next'] is not None]
        diffs_patch = [(o['a_pred_next'] - o['a_actual_next']) for o in ol_patch if o['a_actual_next'] is not None]
        print("\n=== [오픈루프] solver 예측(a_pred_next) vs 실측(a_actual_next) 오차 ===")
        print(f"baseline(200고정): 평균오차={np.mean(diffs_base):+.4f} m/s^2, RMSE={np.sqrt(np.mean(np.square(diffs_base))):.4f}")
        print(f"현재프로덕션      : 평균오차={np.mean(diffs_patch):+.4f} m/s^2, RMSE={np.sqrt(np.mean(np.square(diffs_patch))):.4f}")

        delta = [(ob['a_pred_next'] - op['a_pred_next']) for ob, op in zip(ol_base, ol_patch)]
        n_diff_frames = sum(1 for d in delta if abs(d) > 1e-6)
        print(f"\nbaseline과 현재프로덕션 간 a_pred_next 차이(같은 실측 프레임 기준, 1프레임짜리 국소 반응):")
        print(f"평균 차이: {np.mean(delta):+.4f} m/s^2, 최대 |차이|: {max(abs(d) for d in delta):.4f} m/s^2, "
              f"차이 발생 프레임: {n_diff_frames}/{len(delta)}")

    if args.mode in ('closedloop', 'both'):
        cl_base = run_closedloop(rows, args.v_cruise_col, True, "baseline(A_CHANGE_COST=200 고정, 177차 이전 재현)")
        cl_patch = run_closedloop(rows, args.v_cruise_col, False, "현재 프로덕션(route_decel_rate 완화 게이트 활성)")

        flip_base = find_sign_flip(cl_base)
        flip_patch = find_sign_flip(cl_patch)

        print("\n=== [폐루프] 요약 (참고용 -- 아래 §271차 한계 노트 참고) ===")
        print(f"baseline(200 고정)     부호전환(a_ego_sim<0) 시각: {flip_base}")
        print(f"현재 프로덕션(완화게이트) 부호전환(a_ego_sim<0) 시각: {flip_patch}")
        actual_flip = None
        for r in rows:
            if float(r['aEgo']) < 0.0:
                actual_flip = float(r['t']); break
        print(f"실측 aEgo 부호전환 시각: {actual_flip}")

        t_end = float(rows[-1]['t'])

        def gap_at_end(out):
            return out[-1]['v_ego_kph'] - out[-1]['target_kph']

        print(f"\nt={t_end:.2f}s(구간끝) vEgo-target gap: "
              f"baseline={gap_at_end(cl_base):.2f}kph, 현재={gap_at_end(cl_patch):.2f}kph, "
              f"실측={float(rows[-1]['vEgo'])/KPH_TO_MS - float(rows[-1][args.v_cruise_col]):.2f}kph")

        print(f"\n실측 최종 vEgo: {float(rows[-1]['vEgo']):.2f}kph, "
              f"baseline sim 최종 vEgo: {cl_base[-1]['v_ego_kph']:.2f}kph, "
              f"현재 sim 최종 vEgo: {cl_patch[-1]['v_ego_kph']:.2f}kph")
        print("\n[271차 주의] 위 폐루프 절대치는 FakeCarrot 근사 누적오차로 실측과")
        print("크게 벌어질 수 있음(1절 참고) -- 오픈루프 결과를 1차 근거로 삼을 것.")
