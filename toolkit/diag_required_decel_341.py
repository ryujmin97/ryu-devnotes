#!/usr/bin/env python3
"""
diag_required_decel_341.py (341차 신규)
========================================
목적: WIP 340차가 남긴 가설(직선구간 route flapping의 원인이 10m 그리드
apex_speed 요동 -> required_decel_mss가 임계값(decel_rate) 바로 근처에서
프레임마다 넘었다/안 넘었다 하는 것) 을 code-level로 직접 확정/기각한다.

기존 toolkit/sim_route_273_active_gate_relax_sensitivity.py의
ContinuityApprox/confidence_from_streak/simulate 로직(carrot_man.py
stage4 거리게이트+confidence blend 재구현, sanity check로 신뢰도 확인된
바 있음)을 그대로 import해서 재사용한다(§21 -- 새 게이트 재구성 로직을
중복 작성하지 않음). 이 스크립트는 simulate()의 내부 계산을 그대로
풀어서(§27 -- 산식 자체는 절대 변경하지 않고 관측값만 추가 노출)
required_decel_mss/eff_apex_speed/conf/streak/게이트 결과를 프레임별로
출력하고, 실측 src 컬럼과 시간 정렬해 대조한다.

사용:
    python3 diag_required_decel_341.py <csv> <t0> <t1> [--decel-rate=1.00]
"""
import csv
import sys
import os

sys.path.insert(0, "/home/claude/ryu-devnotes/toolkit")
from sim_route_273_active_gate_relax_sensitivity import (
    ContinuityApprox, confidence_from_streak, load_rows,
    CONFIDENCE_TAU_DEFAULT, CTRL_END_DEFAULT, DECEL_RATE_DEFAULT,
    CONTINUITY_TOL_DEFAULT, RELEASE_MARGIN_RATIO, RELEASE_DIST_M,
)


def load_src(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {float(r["t"]): r["src"] for r in rows}


def run(csv_path, t0, t1, decel_rate, tau, ctrl_end, continuity_tol):
    rows = load_rows(csv_path)
    src_map = load_src(csv_path)
    cont = ContinuityApprox(continuity_tol)
    route_active = False
    prev_t = None

    print(f"{'t':>9} {'src':>6} {'idx':>4} {'apexD':>7} {'apexS':>6} "
          f"{'streak':>6} {'conf':>5} {'eff_apxS':>8} {'eff_dist':>8} "
          f"{'req_decel':>9} {'gate':>4} {'sim_active':>10}")

    toggle_count = 0
    prev_active_out = None
    req_decel_series = []

    for row in rows:
        t = row["t"]
        dt = (t - prev_t) if prev_t is not None else 0.05
        prev_t = t
        dt = max(0.001, min(dt, 0.5))

        apex_idx, apex_dist, apex_speed = row["apex_idx"], row["apex_dist"], row["apex_speed"]
        v_ego_ms = row["v_ego_ms"]
        v_ego_kph = v_ego_ms * 3.6

        streak = cont.step(dt, v_ego_ms, apex_idx, apex_dist, row["candidates"])

        req_decel = None
        conf = None
        eff_apex_speed = None
        eff_dist = None
        gate_pass = None
        out_active = False

        if not (apex_idx is None or apex_idx < 0 or apex_speed is None or apex_dist is None):
            conf = confidence_from_streak(streak, tau)
            eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
            target_ms = eff_apex_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)

            if route_active:
                speed_reached = v_ego_kph <= apex_speed * RELEASE_MARGIN_RATIO
                dist_reached = apex_dist <= RELEASE_DIST_M
                apex_reset = streak == 1
                if apex_reset or speed_reached or dist_reached:
                    route_active = False
                else:
                    out_active = True
            else:
                if v_ego_ms <= target_ms:
                    pass
                elif eff_dist <= 0:
                    out_active = True  # ceiling only, but counts as "route touches output"
                else:
                    req_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                    gate_pass = req_decel >= decel_rate
                    if gate_pass:
                        route_active = True
                        out_active = True

            if route_active and req_decel is None and eff_dist > 0 and v_ego_ms > target_ms:
                req_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
        else:
            route_active = False

        if prev_active_out is not None and out_active != prev_active_out:
            toggle_count += 1
        prev_active_out = out_active

        if req_decel is not None:
            req_decel_series.append((t, req_decel))

        if t0 <= t <= t1:
            src_actual = src_map.get(t, "?")
            print(f"{t:9.2f} {src_actual:>6} {apex_idx if apex_idx is not None else -1:4d} "
                  f"{(apex_dist if apex_dist is not None else float('nan')):7.1f} "
                  f"{(apex_speed if apex_speed is not None else float('nan')):6.1f} "
                  f"{streak:6d} "
                  f"{(conf if conf is not None else float('nan')):5.2f} "
                  f"{(eff_apex_speed if eff_apex_speed is not None else float('nan')):8.1f} "
                  f"{(eff_dist if eff_dist is not None else float('nan')):8.1f} "
                  f"{(req_decel if req_decel is not None else float('nan')):9.3f} "
                  f"{str(gate_pass):>4} {str(out_active):>10}")

    print()
    print(f"=== 요약(t={t0}~{t1}, decel_rate={decel_rate}) ===")
    print(f"sim_active 토글 횟수(전체 구간): {toggle_count}")
    win = [(t, rd) for t, rd in req_decel_series if t0 <= t <= t1]
    if win:
        vals = [rd for _, rd in win]
        crossings = sum(1 for i in range(1, len(vals))
                         if (vals[i - 1] - decel_rate) * (vals[i] - decel_rate) < 0)
        print(f"윈도우 내 required_decel_mss 범위: {min(vals):.3f} ~ {max(vals):.3f} "
              f"(decel_rate={decel_rate} 기준 임계 교차 횟수: {crossings})")


def main():
    csv_path = sys.argv[1]
    t0 = float(sys.argv[2])
    t1 = float(sys.argv[3])
    decel_rate = DECEL_RATE_DEFAULT
    tau = CONFIDENCE_TAU_DEFAULT
    ctrl_end = CTRL_END_DEFAULT
    continuity_tol = CONTINUITY_TOL_DEFAULT
    for a in sys.argv[4:]:
        if a.startswith("--decel-rate="):
            decel_rate = float(a.split("=", 1)[1])
        elif a.startswith("--tau="):
            tau = float(a.split("=", 1)[1])
        elif a.startswith("--ctrl-end="):
            ctrl_end = float(a.split("=", 1)[1])
        elif a.startswith("--continuity-tol="):
            continuity_tol = float(a.split("=", 1)[1])
    run(csv_path, t0, t1, decel_rate, tau, ctrl_end, continuity_tol)


if __name__ == "__main__":
    main()
