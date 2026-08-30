"""
replay_route_apex_hysteresis_ab.py (158차 계속, 신규)

목적: extract_log.py --with-navi-paths 실측 CSV를 프레임 재생하며 두
알고리즘을 나란히 오프라인 계산한다.
  A = 157차 carrot_navi_route_apex (매 프레임 무상태 전역탐색, 이미
      158차에서 이 CSV로 검증 완료 -- 3개 stuck 구간 전부 정상반응)
  B = 158차계속 carrot_navi_route_apex_hysteresis (target_curv 기억하는
      3상태: reset/engaged/disengaged)

각각 132차 RampLimiterState를 별도 인스턴스로 통과시켜 최종 out_speed를
낸다(두 알고리즘이 서로 다른 램프 상태를 오염시키지 않도록 완전히 독립).

비교 관점:
  1) liveRouteSpeed(실측, 패치전) 5초+ 고정 구간(158차가 찾은 그 3곳)에서
     A/B 둘 다 정상 반응하는가 -- 히스테리시스가 157차 대비 회귀가 없는지.
  2) "제약 해제"(out_speed>=road_limit 근접, 사실상 vturn에 위임) 상태로
     전환되는 빈도 -- A는 상태가 없어 매 프레임 재탐색이라 이 개념이
     없고(항상 그 프레임의 apex를 낸다), B는 명시적으로 세어 disengaged/
     reset 비율을 볼 수 있다. 사용자가 우려한 "톱니 진동"이 실제로
     B에서 A보다 심한지/약한지를 프레임간 낙차(절대값) 분포로 비교.
  3) 프레임간 out_speed 변화량(절대값) 최대/평균 -- 램프리미터가 상한을
     걸어주므로 이론적으로는 두 알고리즘 다 accel_limit*dt를 못 넘어야
     하지만, B가 disengaged<->engaged를 자주 오가며 "제약 있음<->없음"을
     반복하면(=램프리미터 관점에서 "제약 해제는 즉시 통과" 규칙 때문에)
     A보다 큰 낙차가 더 자주 나올 수 있음 -- 이게 이번 A/B의 핵심 가설.

사용:
  python3 replay_route_apex_hysteresis_ab.py <route.csv> [--accel 0.70]
"""
import argparse
import sys

from analysis_helpers import load_csv, parse_navi_paths, recompute_route_curvature_speed
from sim_route_apex_redesign import carrot_navi_route_apex
from sim_route_apex_hysteresis import carrot_navi_route_apex_hysteresis, ApexHysteresisState
from sim_route_boundary_ramp_limiter import RampLimiterState
from replay_route_apex_vs_baseline import find_stuck_segments

ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
MAX_ACCEL_MSS = 1.2


def replay_ab(rows, accel_limit_mss):
    ramp_a = RampLimiterState()
    ramp_b = RampLimiterState()
    hyst_state = ApexHysteresisState()
    out = []
    prev_t = None
    for row in rows:
        t = float(row["t"])
        v_ego_kph = float(row["vEgo"]) * 3.6
        dt = (t - prev_t) if prev_t is not None else 0.05
        dt = max(0.001, min(dt, 0.5))
        prev_t = t

        points, distances = parse_navi_paths(row.get("naviPaths", ""))
        if len(points) < 9:
            out.append({"t": t, "v_ego_kph": v_ego_kph,
                        "live_route_speed": float(row["liveRouteSpeed"]),
                        "a_out": None, "b_out": None, "b_mode": hyst_state.mode})
            ramp_a.prev_out = None
            ramp_b.prev_out = None
            continue

        merged = recompute_route_curvature_speed(
            points, distances, sample=4, sample_fine=1,
            floor_threshold=ROUTE_CURVE_NEGLIGIBLE_THRESHOLD,
        )
        if not merged:
            out.append({"t": t, "v_ego_kph": v_ego_kph,
                        "live_route_speed": float(row["liveRouteSpeed"]),
                        "a_out": None, "b_out": None, "b_mode": hyst_state.mode})
            ramp_a.prev_out = None
            ramp_b.prev_out = None
            continue

        distances_only = [m[0] for m in merged]
        speeds_only = [m[2] for m in merged]

        raw_a, accel_kmh_a = carrot_navi_route_apex(
            speeds_only, distances_only, v_ego_kph, accel_limit_mss,
            max_accel_mss=MAX_ACCEL_MSS)
        smoothed_a = ramp_a.apply(raw_a, accel_kmh_a, dt)

        raw_b, accel_kmh_b = carrot_navi_route_apex_hysteresis(
            hyst_state, merged, v_ego_kph, accel_limit_mss,
            max_accel_mss=MAX_ACCEL_MSS,
            negligible_curv=ROUTE_CURVE_NEGLIGIBLE_THRESHOLD)
        smoothed_b = ramp_b.apply(raw_b, accel_kmh_b, dt)

        out.append({
            "t": t, "v_ego_kph": v_ego_kph, "src": row.get("src", ""),
            "live_route_speed": float(row["liveRouteSpeed"]),
            "a_out": smoothed_a, "b_out": smoothed_b, "b_mode": hyst_state.mode,
        })
    return out


def frame_delta_stats(result, key):
    deltas = []
    for i in range(1, len(result)):
        a, b = result[i - 1][key], result[i][key]
        if a is not None and b is not None:
            deltas.append(abs(a - b))
    if not deltas:
        return 0.0, 0.0, 0
    return max(deltas), sum(deltas) / len(deltas), len(deltas)


def summarize_segment(result, s, e, live_value):
    window = result[s:e + 1]
    a_vals = [r["a_out"] for r in window if r["a_out"] is not None]
    b_vals = [r["b_out"] for r in window if r["b_out"] is not None]
    if not a_vals or not b_vals:
        return "  (계산 불가 -- naviPaths 부족 프레임)"
    modes = sorted(set(r["b_mode"] for r in window))
    lines = []
    lines.append(f"  실측(패치전) 고정: {live_value:.1f} km/h, {window[-1]['t']-window[0]['t']:.1f}s")
    lines.append(f"  A(157차 무상태): min={min(a_vals):.1f} max={max(a_vals):.1f} "
                 f"시작={a_vals[0]:.1f} 끝={a_vals[-1]:.1f}")
    lines.append(f"  B(히스테리시스): min={min(b_vals):.1f} max={max(b_vals):.1f} "
                 f"시작={b_vals[0]:.1f} 끝={b_vals[-1]:.1f} (구간내 mode: {modes})")
    a_resp = min(a_vals) < live_value - 3.0
    b_resp = min(b_vals) < live_value - 3.0
    lines.append(f"  판정: A={'반응' if a_resp else '무반응'} / B={'반응' if b_resp else '무반응'}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--accel", type=float, default=0.70)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    if not rows:
        print("no rows", file=sys.stderr)
        sys.exit(1)

    result = replay_ab(rows, args.accel)

    stuck = find_stuck_segments(rows, "liveRouteSpeed", min_len_s=5.0, tol=0.05)
    print(f"=== 총 {len(rows)} rows, t={rows[0]['t']}~{rows[-1]['t']} ===")
    print(f"=== liveRouteSpeed 5초+ 고정 구간: {len(stuck)}건 ===\n")
    for (s, e, length, val) in stuck:
        print(f"[{rows[s]['t']} ~ {rows[e]['t']}] ({length:.1f}s, value={val})")
        print(summarize_segment(result, s, e, val))
        print()

    max_a, mean_a, n_a = frame_delta_stats(result, "a_out")
    max_b, mean_b, n_b = frame_delta_stats(result, "b_out")
    theory_cap = args.accel * 3.6 * 0.05
    print(f"=== 프레임간 낙차(절대값) ===")
    print(f"  A(157차 무상태): max={max_a:.2f} mean={mean_a:.3f} km/h (n={n_a})")
    print(f"  B(히스테리시스): max={max_b:.2f} mean={mean_b:.3f} km/h (n={n_b})")
    print(f"  이론상한(accel={args.accel} m/s^2, dt=0.05s)={theory_cap:.2f} km/h/frame")

    # mode 전이 횟수(disengaged<->engaged<->reset) 카운트 -- 톱니 진동 빈도 프록시
    transitions = 0
    for i in range(1, len(result)):
        if result[i]["b_mode"] != result[i - 1]["b_mode"]:
            transitions += 1
    print(f"\n=== B(히스테리시스) mode 전이 횟수: {transitions}건 (총 {len(result)} 프레임) ===")

    # 오탐(회귀) 체크: stuck 구간 앞뒤 20초 이상 떨어진 구간에서
    # live>=95 & (a_out or b_out)<70 인 프레임(과잉감속 의심)
    stuck_ranges = [(float(rows[s]['t']) - 20, float(rows[e]['t']) + 20) for (s, e, _, _) in stuck]
    def in_buffer(t):
        return any(lo <= t <= hi for lo, hi in stuck_ranges)
    fp_a = fp_b = 0
    for r in result:
        if r["a_out"] is None or in_buffer(r["t"]):
            continue
        if r["live_route_speed"] >= 95.0:
            if r["a_out"] < 70.0:
                fp_a += 1
            if r["b_out"] < 70.0:
                fp_b += 1
    print(f"=== 오탐(회귀) 스캔(stuck 구간 ±20s 제외, live>=95 & out<70): A={fp_a}건 / B={fp_b}건 ===")


if __name__ == "__main__":
    main()
