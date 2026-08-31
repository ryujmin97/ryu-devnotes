#!/usr/bin/env python3
"""
replay_route_camera_style_vs_baseline.py (161차, 신규)

목적: extract_log.py --with-navi-paths로 뽑은 실측 로그를 20Hz 프레임
단위로 재생해, 160차 camera-style route 감속 알고리즘
(sim_route_camera_style_decel.carrot_navi_route_camera_style)이 그 실제
상황에서 어떻게 반응했을지 오프라인으로 계산하고, CSV에 이미 기록된
liveRouteSpeed(149차 -- 실제 production이 낸 값, 역방향DP+132차 램프까지
통과한 실측 ground truth)와 나란히 비교한다.

158차 replay_route_apex_vs_baseline.py와 구조가 거의 동일하다(그 스크립트를
그대로 복사해 apex 알고리즘 호출부만 157차->160차로 교체) -- 코드 중복을
최소화하기 위해 find_stuck_segments/summarize 로직은 그 파일에서 import해서
재사용하고, replay()만 새로 정의한다.

주의: carrot_navi_route_camera_style()은 v_ego_kph를 아예 안 쓴다(거리만으로
계산하는 카메라 공식 특성) -- 157차용 replay와 달리 v_ego_kph 인자를 안 넘김.
accel_limit_kmh(램프리미터용)도 더 이상 동적이 아니라 decel_rate_mss*3.6
고정값을 매 프레임 반환.

입력: extract_log.py --with-navi-paths로 뽑은 CSV (naviPaths, vEgo, t,
liveRouteSpeed 컬럼 필수)
출력: stdout 표 (구간별 실측 liveRouteSpeed vs camera-style 오프라인
계산값) + --json 지정 시 프레임별 전체 결과 JSON 덤프

의존성: analysis_helpers.py(load_csv, parse_navi_paths,
recompute_route_curvature_speed), sim_route_camera_style_decel.py
(carrot_navi_route_camera_style), sim_route_boundary_ramp_limiter.py
(RampLimiterState), replay_route_apex_vs_baseline.py(find_stuck_segments 재사용)

사용:
  python3 replay_route_camera_style_vs_baseline.py <route.csv> \
      [--safe-time 2.2] [--decel 0.70] [--start-t T0] [--end-t T1] [--json out.json]
"""
import argparse
import json
import sys

from analysis_helpers import load_csv, parse_navi_paths, recompute_route_curvature_speed
from sim_route_camera_style_decel import carrot_navi_route_camera_style
from sim_route_boundary_ramp_limiter import RampLimiterState
from replay_route_apex_vs_baseline import find_stuck_segments

ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001  # 157차/160차 공통값


def replay(rows, safe_time, decel_rate_mss):
    """프레임별로 160차 camera-style 알고리즘을 오프라인 재생. 반환:
    프레임별 dict 리스트 (t, v_ego_kph, src, live_route_speed(실측),
    cam_out_speed(160차 알고리즘 오프라인 계산, 132차 램프 통과 후),
    cam_apex_dist, cam_apex_curvature)."""
    ramp = RampLimiterState()
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
            out.append({
                "t": t, "v_ego_kph": v_ego_kph, "src": row.get("src", ""),
                "live_route_speed": float(row["liveRouteSpeed"]),
                "cam_out_speed": None, "cam_apex_dist": None, "cam_apex_curvature": None,
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
                "cam_out_speed": None, "cam_apex_dist": None, "cam_apex_curvature": None,
            })
            ramp.prev_out = None
            continue

        distances_only = [m[0] for m in merged]
        speeds_only = [m[2] for m in merged]
        raw_out, accel_limit_kmh = carrot_navi_route_camera_style(
            speeds_only, distances_only, safe_time, decel_rate_mss,
        )
        smoothed = ramp.apply(raw_out, accel_limit_kmh, dt)

        apex_idx = min(range(len(speeds_only)), key=lambda k: speeds_only[k])
        out.append({
            "t": t, "v_ego_kph": v_ego_kph, "src": row.get("src", ""),
            "live_route_speed": float(row["liveRouteSpeed"]),
            "cam_out_speed": smoothed,
            "cam_apex_dist": distances_only[apex_idx],
            "cam_apex_curvature": merged[apex_idx][1],
        })
    return out


def summarize_stuck_segment(result, start_idx, end_idx, live_value):
    window = result[start_idx:end_idx + 1]
    cam_vals = [r["cam_out_speed"] for r in window if r["cam_out_speed"] is not None]
    if not cam_vals:
        return "  (camera-style 계산 불가 -- naviPaths 부족 프레임)"
    lines = []
    lines.append(f"  실측(liveRouteSpeed) 고정값: {live_value:.1f} km/h, "
                 f"{window[-1]['t']-window[0]['t']:.1f}s 지속")
    lines.append(f"  160차 camera-style 오프라인 재계산: min={min(cam_vals):.1f}, "
                 f"max={max(cam_vals):.1f}, 시작={cam_vals[0]:.1f}, 끝={cam_vals[-1]:.1f} km/h")
    min_curv = min((r["cam_apex_curvature"] for r in window if r["cam_apex_curvature"] is not None), default=None)
    if min_curv is not None:
        lines.append(f"  구간 내 최대곡률(apex 지점 기준 최소): {min_curv:.4f}")
    responded = min(cam_vals) < live_value - 3.0
    lines.append(f"  판정: {'반응함(160차가 이 구간에서 실제로 낮은 값을 냈을 것)' if responded else '반응 미미(160차도 유사하게 무반응 -- 추가 조사 필요)'}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--safe-time", type=float, default=2.2, help="autoNaviSpeedCtrlEnd 대표값 (기본 2.2)")
    ap.add_argument("--decel", type=float, default=0.70, help="AutoNaviSpeedDecelRate 실측값 (기본 0.70)")
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

    result = replay(rows, args.safe_time, args.decel)

    stuck = find_stuck_segments(rows, "liveRouteSpeed", min_len_s=5.0, tol=0.05)
    print(f"=== 총 {len(rows)} rows, t={rows[0]['t']}~{rows[-1]['t']} ===")
    print(f"=== liveRouteSpeed 5초+ 고정 구간: {len(stuck)}건 ===\n")
    for (s, e, length, val) in stuck:
        print(f"[{rows[s]['t']} ~ {rows[e]['t']}] ({length:.1f}s, value={val})")
        print(summarize_stuck_segment(result, s, e, val))
        print()

    max_frame_drop = 0.0
    for i in range(1, len(result)):
        a, b = result[i - 1]["cam_out_speed"], result[i]["cam_out_speed"]
        if a is not None and b is not None:
            max_frame_drop = max(max_frame_drop, a - b)
    print(f"=== camera-style 오프라인 계산 결과의 프레임간 최대 낙차: {max_frame_drop:.2f} km/h ===")
    print(f"    (decel={args.decel} m/s^2 기준 이론 상한 = {args.decel*3.6*0.05:.2f} km/h/frame @ dt=0.05s)")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=1)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
