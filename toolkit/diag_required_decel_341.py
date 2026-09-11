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

    # [370차 신규] L1807 히스테리시스(B3=hold=4프레임) 오프라인 검증
    python3 diag_required_decel_341.py <csv> --hold-frames=4 [--decel-rate=1.00]
        # L1807(v_ego<=target, INERT 분기) raw 조건과 N프레임 디바운스 적용 후
        # 1프레임성 토글 건수를 비교 출력(§21 -- 게이트 산식 자체는 무변경,
        # 관측/디바운스 레이어만 추가). 369차 corpus(`22ebbb245d`)에서
        # hold=4 -> raw 218건 전량(100%) 제거 확인(FINDINGS.md 370차 참고).
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


def apply_hold(raw_series, hold_frames):
    """B3 설계안(370차 논의, L1807 유지시간 히스테리시스) 오프라인 검증용.
    raw_series: 매 프레임 bool (None=True 취급/미평가=None).
    hold_frames: 값이 바뀌려면 새 값이 이만큼 연속으로 관측돼야 실제 전환.
    hold_frames<=1이면 raw_series 그대로(디바운스 없음=현재 코드 상태).
    반환: (held_series, pending_run_len) -- None 값은 그대로 통과(평가 대상 아님).
    """
    if hold_frames <= 1:
        return list(raw_series)
    held = []
    stable = None
    pending_val = None
    pending_len = 0
    for raw in raw_series:
        if raw is None:
            held.append(stable)
            continue
        if stable is None:
            stable = raw
            held.append(stable)
            continue
        if raw == stable:
            pending_val, pending_len = None, 0
            held.append(stable)
        else:
            if raw == pending_val:
                pending_len += 1
            else:
                pending_val, pending_len = raw, 1
            if pending_len >= hold_frames:
                stable = pending_val
                pending_val, pending_len = None, 0
            held.append(stable)
    return held


def count_single_frame_flips(series):
    """앞뒤 프레임과 다르고 지속시간이 정확히 1프레임인 전환(그 유명한
    "route->1프레임 이탈->route" 패턴)만 센다. None은 평가 제외."""
    n = len(series)
    count = 0
    i = 0
    while i < n:
        if series[i] is None:
            i += 1
            continue
        j = i
        while j < n and series[j] == series[i]:
            j += 1
        run_len = j - i
        if run_len == 1 and i > 0 and j < n and series[i - 1] is not None and series[j] is not None \
                and series[i - 1] == series[j] and series[i - 1] != series[i]:
            count += 1
        i = j
    return count


def simulate_with_reason(rows, decel_rate, tau, ctrl_end, continuity_tol, hold_frames=1):
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
    raw_inert = []  # L1807 raw bool per frame (True=v_ego<=target/None분기, None=미평가)
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
        raw_val = None  # [370차 B3 검증] L1807(비활성 분기 v_ego<=target) 원 조건, 이 분기 평가시에만 채움

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
                raw_val = (v_ego_ms <= target_ms)  # L1807 그 자체
                if raw_val:
                    pass
                elif eff_dist <= 0:
                    pass
                else:
                    req_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                    if req_decel >= decel_rate:
                        route_active = True

        raw_inert.append(raw_val)
        out.append({
            "t": t, "route_active": route_active, "was_active": was_active,
            "reason": reason, "apex_idx": apex_idx, "apex_dist": apex_dist,
            "apex_speed": apex_speed, "v_ego_kph": v_ego_kph,
            "req_decel": req_decel, "eff_apex_speed": eff_apex_speed, "streak": streak,
        })

    held_inert = apply_hold(raw_inert, hold_frames)
    for o, raw, held in zip(out, raw_inert, held_inert):
        o["l1807_raw"] = raw          # True=out_speed None(route 배제), False=out_speed=v_ego_kph(route 포함), None=미평가
        o["l1807_held"] = held        # hold_frames 적용 후 동일 의미
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


def run_hold_compare(csv_path, decel_rate, tau, ctrl_end, continuity_tol, hold_frames):
    """[370차, B3 검증] L1807에 hold_frames 프레임 디바운스를 적용했을 때
    'route 배제(None)/포함(v_ego_kph)' 상태의 1프레임성 토글(=368/369차가
    실측 src 컬럼에서 135건 드롭아웃/116건 블립으로 센 것과 동일 패턴)이
    몇 건에서 몇 건으로 주는지 raw(hold=1, 현재 코드와 동일) vs
    hold=hold_frames로 비교한다. 실제 src 컬럼과의 교차 대조도 참고용으로 낸다.
    주의: L1807 판정만 격리 재현한 것으로, carrot_serv.py의 다른 소스와의
    arbitration(min 선택)까지 재현한 것은 아니다(오프라인 근사, §29 실차검증 아님).
    """
    rows = load_rows(csv_path)
    src_map = load_src(csv_path)
    sim = simulate_with_reason(rows, decel_rate, tau, ctrl_end, continuity_tol, hold_frames=1)
    sim_held = simulate_with_reason(rows, decel_rate, tau, ctrl_end, continuity_tol, hold_frames=hold_frames)

    raw_series = [s["l1807_raw"] for s in sim]
    held_series = [s["l1807_held"] for s in sim_held]

    n_evaluated = sum(1 for v in raw_series if v is not None)
    raw_flips = count_single_frame_flips(raw_series)
    held_flips = count_single_frame_flips(held_series)

    print(f"[L1807 격리 재현, hold=1(현재코드) vs hold={hold_frames}]")
    print(f"  평가 대상 프레임(비활성+유효apex): {n_evaluated} / 전체 {len(raw_series)}")
    print(f"  1프레임 토글(raw, hold=1={'현재 코드와 동일'}): {raw_flips}건")
    print(f"  1프레임 토글(held, hold={hold_frames}): {held_flips}건")
    print(f"  감소: {raw_flips - held_flips}건 ({(raw_flips - held_flips) / raw_flips * 100:.1f}% 감소)" if raw_flips else "  raw_flips=0")

    # 참고: 실측 src 컬럼 기준 route/비route 1프레임 토글과 교차비교
    src_series = []
    for r, s in zip(rows, sim):
        is_route = (src_map.get(r["t"], "?") == "route")
        src_series.append(is_route if s["l1807_raw"] is not None else None)
    src_flips = count_single_frame_flips(src_series)
    print(f"\n  참고: 실측 src(route/비route) 1프레임 토글 (368/369차 135+116=251건 기준): {src_flips}건 "
          f"(단, arbitration 등 L1807 외 요인도 섞여 있어 완전 일치는 기대하지 않음)")


def main():
    csv_path = sys.argv[1]
    decel_rate = DECEL_RATE_DEFAULT
    tau = CONFIDENCE_TAU_DEFAULT
    ctrl_end = CTRL_END_DEFAULT
    continuity_tol = CONTINUITY_TOL_DEFAULT
    flap_window = 2.0
    hold_frames = 1
    summary_mode = "--summary" in sys.argv[2:]
    hold_mode = any(a.startswith("--hold-frames=") for a in sys.argv[2:])

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
        elif a.startswith("--hold-frames="):
            hold_frames = int(a.split("=", 1)[1])

    if hold_mode:
        run_hold_compare(csv_path, decel_rate, tau, ctrl_end, continuity_tol, hold_frames)
    elif summary_mode:
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window)
    else:
        t0 = float(rest[0])
        t1 = float(rest[1])
        run_window(csv_path, t0, t1, decel_rate, tau, ctrl_end, continuity_tol)


if __name__ == "__main__":
    main()
