"""
replay_route_apex_vs_baseline.py (158차, 신규)

목적: extract_log.py --with-navi-paths로 뽑은 "패치 적용 이전" 실측
로그를 프레임(20Hz) 단위로 재생해, 157차 apex 재설계 알고리즘
(carrot_navi_route_apex, sim_route_apex_redesign.py)이 그 실제 상황에서
어떻게 반응했을지 오프라인으로 계산하고, CSV에 이미 기록된
liveRouteSpeed(149차 -- 패치 적용 전 실제 production이 낸 route_speed,
역방향DP+132차 램프까지 통과한 실측 ground truth)와 나란히 비교한다.

148차 replay_route_full_pipeline.py가 신뢰불가(오차 98.7kph, 미기록
nRoadLimitSpeed를 가정치로 대체해야 했음)였던 것과 달리, 이 스크립트는
"패치 전 실제로 어떻게 나왔는지"를 재현이 아니라 실측값(liveRouteSpeed)
그대로 사용하므로 그 문제가 없다. 대신 "패치를 실측 발행 안 했던 이
프레임에서, 대신 발행했다면 어떻게 나왔을까"만 apex 알고리즘으로 오프라인
계산한다.

주의: apex 알고리즘의 floor_threshold=0.001 분기가 곡률이 진짜 작은
프레임에서 road_limit_speed를 참조하지만(analysis_helpers.
recompute_route_curvature_speed의 road_limit_speed 인자, 기본 200.0
가정치), 이 분기는 그 프레임의 apex 자체가 사실상 무의미(거의 직선)할
때만 영향을 주므로 148차가 겪은 문제와 달리 결과 해석에 미치는 영향이
제한적이다 -- 그래도 절대값보다는 "패치 전 무반응 구간에서 패치 후
반응하는가", "직선/근정지 구간에서 회귀가 없는가"라는 상대적/구조적
판정에 우선 쓸 것.

입력: extract_log.py --with-navi-paths로 뽑은 CSV (naviPaths, vEgo, t,
liveRouteSpeed 컬럼 필수)
출력: stdout 표 (구간별 실측 liveRouteSpeed vs apex 오프라인 계산값) +
      --json 지정 시 프레임별 전체 결과 JSON 덤프

의존성: analysis_helpers.py(load_csv, parse_navi_paths,
recompute_route_curvature_speed(floor_threshold 인자, 158차 추가)),
sim_route_apex_redesign.py(carrot_navi_route_apex),
sim_route_boundary_ramp_limiter.py(RampLimiterState)

사용:
  python3 replay_route_apex_vs_baseline.py <route.csv> \
      [--accel 0.70] [--start-t T0] [--end-t T1] [--json out.json]

  --start-t/--end-t 없으면 전체 구간을 재생하되, "정체(고정값) 구간"을
  자동 탐지해 요약에서 강조한다.
"""
import argparse
import json
import sys

from analysis_helpers import load_csv, parse_navi_paths, recompute_route_curvature_speed
from sim_route_apex_redesign import carrot_navi_route_apex
from sim_route_boundary_ramp_limiter import RampLimiterState

ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001  # 157차 패치값
MAX_ACCEL_MSS = 1.2  # vturn_decel_rate, 153차/157차와 동일


def find_stuck_segments(rows, field="liveRouteSpeed", min_len_s=5.0, tol=0.05):
    """liveRouteSpeed가 min_len_s 이상 거의 고정(tol 이내)되는 구간을
    찾는다. 156차/158차가 말한 "route= N초+ 고정" 패턴 자동 탐지용."""
    segs = []
    if not rows:
        return segs
    start = 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or abs(float(rows[i][field]) - float(rows[start][field])) > tol:
            length = float(rows[i - 1]["t"]) - float(rows[start]["t"])
            if length >= min_len_s:
                segs.append((start, i - 1, length, float(rows[start][field])))
            start = i
    return segs


def replay(rows, accel_limit_mss):
    """프레임별로 apex 알고리즘을 오프라인 재생. 반환: 프레임별 dict 리스트
    (t, v_ego_kph, src, live_route_speed(실측, 패치전), apex_out_speed
    (157차 알고리즘 오프라인 계산, 132차 램프 통과 후), apex_dist,
    apex_curvature)."""
    ramp = RampLimiterState()
    out = []
    prev_t = None
    for row in rows:
        t = float(row["t"])
        v_ego_kph = float(row["vEgo"]) * 3.6
        dt = (t - prev_t) if prev_t is not None else 0.05
        # 프레임 drop 등으로 비정상적으로 큰 dt가 나오면 램프 상한 계산이
        # 왜곡되므로(지침: "Frame intervals are not uniform") 클램프.
        dt = max(0.001, min(dt, 0.5))
        prev_t = t

        points, distances = parse_navi_paths(row.get("naviPaths", ""))
        if len(points) < 9:  # sample_fine=1 기준 최소 3점 필요(len>=1*2+1)
            out.append({
                "t": t, "v_ego_kph": v_ego_kph, "src": row.get("src", ""),
                "live_route_speed": float(row["liveRouteSpeed"]),
                "apex_out_speed": None, "apex_dist": None, "apex_curvature": None,
            })
            ramp.prev_out = None
            continue

        merged = recompute_route_curvature_speed(
            points, distances, sample=4, sample_fine=1,
            floor_threshold=ROUTE_CURVE_NEGLIGIBLE_THRESHOLD,
        )
        if not merged:
            out.append({
                "t": t, "v_ego_kph": v_ego_kph, "src": row.get("src", ""),
                "live_route_speed": float(row["liveRouteSpeed"]),
                "apex_out_speed": None, "apex_dist": None, "apex_curvature": None,
            })
            ramp.prev_out = None
            continue

        distances_only = [m[0] for m in merged]
        speeds_only = [m[2] for m in merged]
        raw_out, accel_limit_kmh = carrot_navi_route_apex(
            speeds_only, distances_only, v_ego_kph, accel_limit_mss,
            max_accel_mss=MAX_ACCEL_MSS,
        )
        smoothed = ramp.apply(raw_out, accel_limit_kmh, dt)

        apex_idx = min(range(len(speeds_only)), key=lambda k: speeds_only[k])
        out.append({
            "t": t, "v_ego_kph": v_ego_kph, "src": row.get("src", ""),
            "live_route_speed": float(row["liveRouteSpeed"]),
            "apex_out_speed": smoothed,
            "apex_dist": distances_only[apex_idx],
            "apex_curvature": merged[apex_idx][1],
        })
    return out


def summarize_stuck_segment(result, start_idx, end_idx, live_value):
    window = result[start_idx:end_idx + 1]
    apex_vals = [r["apex_out_speed"] for r in window if r["apex_out_speed"] is not None]
    if not apex_vals:
        return f"  (apex 계산 불가 -- naviPaths 부족 프레임)"
    lines = []
    lines.append(f"  실측(패치전, liveRouteSpeed) 고정값: {live_value:.1f} km/h, "
                 f"{window[-1]['t']-window[0]['t']:.1f}s 지속")
    lines.append(f"  apex 오프라인 재계산(패치후 예상): min={min(apex_vals):.1f}, "
                 f"max={max(apex_vals):.1f}, 시작={apex_vals[0]:.1f}, 끝={apex_vals[-1]:.1f} km/h")
    min_curv = min((r["apex_curvature"] for r in window if r["apex_curvature"] is not None), default=None)
    if min_curv is not None:
        lines.append(f"  구간 내 최대곡률(apex 지점 기준 최소): {min_curv:.4f}")
    responded = min(apex_vals) < live_value - 3.0
    lines.append(f"  판정: {'반응함(패치가 이 구간에서 실제로 낮은 값을 냈을 것)' if responded else '반응 미미(패치 후에도 유사하게 무반응 -- 추가 조사 필요)'}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--accel", type=float, default=0.70, help="AutoNaviSpeedDecelRate 실측값 (기본 0.70)")
    ap.add_argument("--start-t", type=float, default=None)
    ap.add_argument("--end-t", type=float, default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    if args.start_t is not None:
        rows = [r for r in rows if float(r["t"]) >= args.start_t]
    if args.end_t is not None:
        rows = [r for r in rows if float(r["t"]) <= args.end_t]
    if not rows:
        print("no rows in range", file=sys.stderr)
        sys.exit(1)

    result = replay(rows, args.accel)

    stuck = find_stuck_segments(rows, "liveRouteSpeed", min_len_s=5.0, tol=0.05)
    print(f"=== 총 {len(rows)} rows, t={rows[0]['t']}~{rows[-1]['t']} ===")
    print(f"=== liveRouteSpeed 5초+ 고정 구간: {len(stuck)}건 ===\n")
    for (s, e, length, val) in stuck:
        print(f"[{rows[s]['t']} ~ {rows[e]['t']}] ({length:.1f}s, value={val})")
        print(summarize_stuck_segment(result, s, e, val))
        print()

    # 전체 회귀 체크: apex_out_speed가 liveRouteSpeed보다 큰 폭으로 갑자기
    # 낮아지는(단일프레임 급락) 케이스가 있는지도 같이 스캔(132차 램프가
    # 실제로 걸리고 있는지 재확인).
    max_frame_drop = 0.0
    for i in range(1, len(result)):
        a, b = result[i - 1]["apex_out_speed"], result[i]["apex_out_speed"]
        if a is not None and b is not None:
            max_frame_drop = max(max_frame_drop, a - b)
    print(f"=== apex 오프라인 계산 결과의 프레임간 최대 낙차: {max_frame_drop:.2f} km/h ===")
    print(f"    (accel={args.accel} m/s^2 기준 이론 상한 = {args.accel*3.6*0.05:.2f} km/h/frame @ dt=0.05s)")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=1)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
