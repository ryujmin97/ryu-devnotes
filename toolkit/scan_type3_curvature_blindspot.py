#!/usr/bin/env python3
"""
187차: 152차가 확정한 "유형3"(naviPaths 원본 폴리라인 좌표 자체에 급회전
형상이 담겨있지 않은 경우 -- chord 샘플 간격 문제가 아니므로 fine 샘플로
줄여도 못 잡는 유형)을 blinker에 의존하지 않고 자동 탐지하는 CLI.

배경: 152차는 required_decel_gap_scan()(blinker 필수)이 이 유형을
원천적으로 탐지 못함을 확인했다("blinker가 아예 없어서 이 함수로 탐지
불가"). 187차가 실차로 재현한 우회전 교차로 사례(seg14/seg15,
t=1370.06)도 blinker 없이 발생했다. 이 스크립트는 blinker 대신
steeringAngleDeg(실제로 곧 급조향이 일어났는가)를 ground truth로 삼아
"naviPaths는 직선처럼 보이는데 실제로는 곧 급조향이 일어난" 구간을
찾는다.

로직 상세는 analysis_helpers.py::type3_curvature_blindspot_scan()
docstring 참고.

사용:
    python3 scan_type3_curvature_blindspot.py <route.csv> \\
        [--lookahead 6.0] [--steering-thresh 60.0] \\
        [--min-recomputed-speed 150.0] [--min-duration 0.3] \\
        [--merge-gap 1.0]

route.csv는 extract_log.py --with-navi-paths 로 뽑은 CSV여야 한다
(naviPaths 컬럼 필수 -- 없으면 이벤트 0건으로 조용히 종료).

의존성: analysis_helpers.load_csv, type3_curvature_blindspot_scan
"""
import argparse
import sys

from analysis_helpers import load_csv, type3_curvature_blindspot_scan


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", help="extract_log.py --with-navi-paths 로 뽑은 route CSV")
    ap.add_argument("--lookahead", type=float, default=6.0,
                     help="이 시점 이후 몇 초 안에 급조향이 오는지 확인할 창(기본 6.0초)")
    ap.add_argument("--steering-thresh", type=float, default=60.0,
                     help="'급조향'으로 간주할 steeringAngleDeg 절대값 임계치(기본 60.0deg)")
    ap.add_argument("--min-recomputed-speed", type=float, default=150.0,
                     help="이 값 이상이면 폴리라인이 '사실상 직선'으로 간주(기본 150.0km/h)")
    ap.add_argument("--min-duration", type=float, default=0.3,
                     help="급조향 상태가 최소 이만큼 지속돼야 인정(기본 0.3초, 노이즈 배제)")
    ap.add_argument("--merge-gap", type=float, default=1.0,
                     help="이 간격(초) 이내로 붙은 이벤트는 하나로 병합(기본 1.0초)")
    ap.add_argument("--near-field-guard", type=float, default=50.0,
                     help="이 거리(m) 미만은 앵커전환 노이즈로 보고 '직선 판정'에서 제외(기본 50.0m)")
    ap.add_argument("--far-check-max", type=float, default=250.0,
                     help="'직선 판정' 중앙값 계산에 포함할 최대 거리(m, 기본 250.0m)")
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    if not rows:
        print("CSV가 비어있습니다.", file=sys.stderr)
        sys.exit(1)
    if "naviPaths" not in rows[0]:
        print("경고: 이 CSV에 naviPaths 컬럼이 없습니다. "
              "extract_log.py --with-navi-paths 로 재추출하세요. "
              "이대로면 이벤트 0건이 반환됩니다.", file=sys.stderr)

    events = type3_curvature_blindspot_scan(
        rows,
        lookahead_s=args.lookahead,
        steering_thresh_deg=args.steering_thresh,
        min_recomputed_speed_kph=args.min_recomputed_speed,
        min_duration_s=args.min_duration,
        merge_gap_s=args.merge_gap,
        near_field_guard_m=args.near_field_guard,
        far_check_max_m=args.far_check_max,
    )

    if not events:
        print(f"유형3 후보 이벤트 0건 (rows={len(rows)}, "
              f"lookahead={args.lookahead}s, steering_thresh={args.steering_thresh}deg, "
              f"min_recomputed_speed={args.min_recomputed_speed}km/h)")
        return

    print(f"유형3 후보 이벤트 {len(events)}건 (rows={len(rows)}):\n")
    header = f"{'start_t':>10} {'end_t':>10} {'dur_s':>6} {'med_recomp_kph':>15} {'steer_peak_deg':>15} {'steer_peak_t':>12}"
    print(header)
    print("-" * len(header))
    for ev in events:
        dur = ev["end_t"] - ev["start_t"]
        print(f"{ev['start_t']:>10.2f} {ev['end_t']:>10.2f} {dur:>6.2f} "
              f"{ev['recomputed_median_speed_kph']:>15.1f} {ev['steering_peak_deg']:>15.1f} "
              f"{ev['steering_peak_t'] if ev['steering_peak_t'] is not None else float('nan'):>12.2f}")


if __name__ == "__main__":
    main()
