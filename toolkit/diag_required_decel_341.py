#!/usr/bin/env python3
"""
diag_required_decel_341.py (341차 신규, 사용자 지적으로 정정판)
================================================================
목적: WIP 340차가 남긴 가설(직선구간 route flapping의 원인이 required_decel_mss
가 임계값 근처에서 진동해 ACTIVE 신규 진입게이트를 넘었다/못넘었다 하는 것)을
code-level로 확정/기각한다.

**정정 경위(중요)**: 이 스크립트의 1차 버전은 `src`가 route->1프레임
이탈->route로 돌아오는 상관관계만 보고 이를 "신규 진입게이트
(v_ego<=target_eff) 실패"로 귀속했다. 사용자가 "ACTIVE 유지 중 릴리즈
조건(v_ego_kph<=apex_speed*RELEASE_MARGIN_RATIO)에 해당하는 것 아니냐"고
지적해, route_active 상태를 실제로 프레임별 추적하는 이 버전으로
재작성했다. **핵심 결과(정정됨)**: 그룹13(t=1076~1085) 릴리즈 이벤트
7건 전부, 전체 로그 기준 flapping성 릴리즈(2초 이내 재진입) 54건 중
33건(61.1%)이 신규 진입게이트가 아니라 **ACTIVE 릴리즈 조건
speed_reached**에서 발동했다. 상세는 FINDINGS.md/WIP.md 341차 참고.

기존 toolkit/sim_route_273_active_gate_relax_sensitivity.py의
ContinuityApprox/confidence_from_streak/게이트 산식(carrot_man.py
stage4 거리게이트+confidence blend 재구현)을 그대로 import해서
재사용한다(§21 -- 새 게이트 재구성 로직을 중복 작성하지 않음). 이
스크립트는 route_active 상태전이를 직접 추적해 release 순간 어느 조건
(apex_reset=streak==1 / speed_reached=v_ego_kph<=apexSpeed*RELEASE_MARGIN_RATIO
/ dist_reached=apexDist<=RELEASE_DIST_M / no_apex=후보 소실 /
entry_gate_fail=신규진입 실패)이 발동했는지 분류해 출력한다(§27 --
게이트 산식 자체는 변경하지 않고 관측/분류만 추가).

사용:
    # 구간 프레임별 상세 로그
    python3 diag_required_decel_341.py <csv> <t0> <t1> [--decel-rate=1.00]

    # 전체 로그 release reason 통계(구간 지정 없이 --summary)
    python3 diag_required_decel_341.py <csv> --summary [--decel-rate=1.00]
        [--flap-window=2.0]   # 이 시간(초) 이내 재진입만 'flapping'으로 카운트
"""
import csv
import sys

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


def simulate_with_reason(rows, decel_rate, tau, ctrl_end, continuity_tol):
    """route_active 상태전이를 프레임별로 추적하며 release/entry reason을 함께 낸다.
    반환: list of dict(t, route_active, reason, apex_idx, apex_dist, apex_speed,
                        v_ego_kph, req_decel, eff_apex_speed, streak)
    reason은 '이 프레임에서 상태가 바뀌었을 때만' 채워진다(release 원인 또는
    신규진입 성공/실패 사유).
    """
    cont = ContinuityApprox(continuity_tol)
    route_active = False
    prev_t = None
    out = []
    for row in rows:
        t = row["t"]
        dt = (t - prev_t) if prev_t is not None else 0.05
        prev_t = t
        dt = max(0.001, min(dt, 0.5))

        apex_idx, apex_dist, apex_speed = row["apex_idx"], row["apex_dist"], row["apex_speed"]
        v_ego_ms = row["v_ego_ms"]
        v_ego_kph = v_ego_ms * 3.6
        streak = cont.step(dt, v_ego_ms, apex_idx, apex_dist, row["candidates"])

        was_active = route_active
        reason = None
        req_decel = None
        eff_apex_speed = None

        if apex_idx is None or apex_idx < 0 or apex_speed is None or apex_dist is None:
            route_active = False
            if was_active:
                reason = "no_apex"
        else:
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
                    reason = ("apex_reset" if apex_reset else
                              "speed_reached" if speed_reached else "dist_reached")
                else:
                    if eff_dist > 0 and v_ego_ms > target_ms:
                        req_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            else:
                if v_ego_ms <= target_ms:
                    pass
                elif eff_dist <= 0:
                    pass
                else:
                    req_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                    if req_decel >= decel_rate:
                        route_active = True

        out.append({
            "t": t, "route_active": route_active, "was_active": was_active,
            "reason": reason, "apex_idx": apex_idx, "apex_dist": apex_dist,
            "apex_speed": apex_speed, "v_ego_kph": v_ego_kph,
            "req_decel": req_decel, "eff_apex_speed": eff_apex_speed, "streak": streak,
        })
    return out


def run_window(csv_path, t0, t1, decel_rate, tau, ctrl_end, continuity_tol):
    rows = load_rows(csv_path)
    src_map = load_src(csv_path)
    sim = simulate_with_reason(rows, decel_rate, tau, ctrl_end, continuity_tol)

    print(f"{'t':>9} {'src':>6} {'idx':>4} {'apexD':>7} {'apexS':>6} "
          f"{'streak':>6} {'req_decel':>9} {'active':>6} {'reason':>14}")
    for s in sim:
        if t0 <= s["t"] <= t1:
            src_actual = src_map.get(s["t"], "?")
            print(f"{s['t']:9.2f} {src_actual:>6} "
                  f"{(s['apex_idx'] if s['apex_idx'] is not None else -1):4d} "
                  f"{(s['apex_dist'] if s['apex_dist'] is not None else float('nan')):7.1f} "
                  f"{(s['apex_speed'] if s['apex_speed'] is not None else float('nan')):6.1f} "
                  f"{s['streak']:6d} "
                  f"{(s['req_decel'] if s['req_decel'] is not None else float('nan')):9.3f} "
                  f"{str(s['route_active']):>6} {str(s['reason']):>14}")


def run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window):
    from collections import Counter
    rows = load_rows(csv_path)
    sim = simulate_with_reason(rows, decel_rate, tau, ctrl_end, continuity_tol)

    releases = [(i, s) for i, s in enumerate(sim) if s["was_active"] and not s["route_active"]]
    print(f"[전체] route_active True->False 릴리즈 이벤트: {len(releases)}건")
    print("  reason 분포:", dict(Counter(s["reason"] for _, s in releases)))

    flap = []
    for i, s in releases:
        t0 = s["t"]
        reentered = False
        for j in range(i + 1, len(sim)):
            if sim[j]["t"] - t0 > flap_window:
                break
            if sim[j]["route_active"]:
                reentered = True
                break
        if reentered:
            flap.append(s)
    print(f"\n[{flap_window}s 이내 재진입=flapping] {len(flap)}건")
    print("  reason 분포:", dict(Counter(s["reason"] for s in flap)))


def main():
    csv_path = sys.argv[1]
    decel_rate = DECEL_RATE_DEFAULT
    tau = CONFIDENCE_TAU_DEFAULT
    ctrl_end = CTRL_END_DEFAULT
    continuity_tol = CONTINUITY_TOL_DEFAULT
    flap_window = 2.0
    summary_mode = "--summary" in sys.argv[2:]

    rest = [a for a in sys.argv[2:] if a != "--summary"]
    for a in rest:
        if a.startswith("--decel-rate="):
            decel_rate = float(a.split("=", 1)[1])
        elif a.startswith("--tau="):
            tau = float(a.split("=", 1)[1])
        elif a.startswith("--ctrl-end="):
            ctrl_end = float(a.split("=", 1)[1])
        elif a.startswith("--continuity-tol="):
            continuity_tol = float(a.split("=", 1)[1])
        elif a.startswith("--flap-window="):
            flap_window = float(a.split("=", 1)[1])

    if summary_mode:
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window)
    else:
        t0 = float(rest[0])
        t1 = float(rest[1])
        run_window(csv_path, t0, t1, decel_rate, tau, ctrl_end, continuity_tol)


if __name__ == "__main__":
    main()
