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

188차: v1의 median 단독 판정이 "far_window 안에 실제 짧은 커브가
있는데 앞뒤 긴 직선 때문에 median이 희석되는" 경우(seg14/15 신규 B,
t=1352.76~1361.91 -- 대시캠 확인 결과 일반 도로커브, naviPaths도 실제
곡률을 담고 있었음)를 오탐으로 잡는 것을 발견, 2단계 판정
type3_curvature_blindspot_scan_v2()를 추가. --v2 플래그로 전환(기본은
기존 v1 그대로 -- 회귀 없음). v2 상세 로직/파라미터는
analysis_helpers.py::type3_curvature_blindspot_scan_v2() docstring 참고.

route.csv는 extract_log.py --with-navi-paths 로 뽑은 CSV여야 한다
(naviPaths 컬럼 필수 -- 없으면 이벤트 0건으로 조용히 종료).

의존성: analysis_helpers.load_csv, type3_curvature_blindspot_scan,
type3_curvature_blindspot_scan_v2
"""
import argparse
import sys

from analysis_helpers import (
    load_csv,
    type3_curvature_blindspot_scan,
    type3_curvature_blindspot_scan_v2,
)


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
    ap.add_argument("--v2", action="store_true",
                     help="188차 2단계 판정(type3_curvature_blindspot_scan_v2) 사용 "
                          "-- far_window 안에 실제 커브가 끼어있는 오탐 후보를 별도로 걸러냄")
    ap.add_argument("--show-rejected", action="store_true",
                     help="--v2와 함께 사용 시 오탐으로 제외된 후보도 사유와 함께 출력")
    ap.add_argument("--low-cap-thresh", type=float, default=100.0,
                     help="[--v2] 이 값 미만이면 '실제 저속 커브 지점'으로 간주(기본 100.0km/h)")
    ap.add_argument("--low-cap-run-m", type=float, default=20.0,
                     help="[--v2] 저속 지점이 거리축으로 이 값(m) 이상 연속되면 오탐 처리(기본 20.0m)")
    ap.add_argument("--low-cap-ratio", type=float, default=0.15,
                     help="[--v2] 평가구간 내 저속 지점 비율이 이 값 이상이면 오탐 처리(기본 0.15)")
    ap.add_argument("--low-cap-eval-start", type=float, default=80.0,
                     help="[--v2] 이 거리(m) 미만은 near_field_guard 경계인접 노이즈로 보고 "
                          "저속판정 평가에서 제외(기본 80.0m)")
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    if not rows:
        print("CSV가 비어있습니다.", file=sys.stderr)
        sys.exit(1)
    if "naviPaths" not in rows[0]:
        print("경고: 이 CSV에 naviPaths 컬럼이 없습니다. "
              "extract_log.py --with-navi-paths 로 재추출하세요. "
              "이대로면 이벤트 0건이 반환됩니다.", file=sys.stderr)

    def _print_table(events, title):
        print(f"{title} {len(events)}건:\n")
        header = (f"{'start_t':>10} {'end_t':>10} {'dur_s':>6} {'med_recomp_kph':>15} "
                  f"{'steer_peak_deg':>15} {'steer_peak_t':>12}")
        print(header)
        print("-" * len(header))
        for ev in events:
            dur = ev["end_t"] - ev["start_t"]
            print(f"{ev['start_t']:>10.2f} {ev['end_t']:>10.2f} {dur:>6.2f} "
                  f"{ev['recomputed_median_speed_kph']:>15.1f} {ev['steering_peak_deg']:>15.1f} "
                  f"{ev['steering_peak_t'] if ev['steering_peak_t'] is not None else float('nan'):>12.2f}")
            if "reject_reason" in ev:
                print(f"           -> 제외사유: {', '.join(ev['reject_reason'])}")
        print()

    if args.v2:
        accepted, rejected = type3_curvature_blindspot_scan_v2(
            rows,
            lookahead_s=args.lookahead,
            steering_thresh_deg=args.steering_thresh,
            min_recomputed_speed_kph=args.min_recomputed_speed,
            min_duration_s=args.min_duration,
            merge_gap_s=args.merge_gap,
            near_field_guard_m=args.near_field_guard,
            far_check_max_m=args.far_check_max,
            low_cap_thresh_kph=args.low_cap_thresh,
            low_cap_run_m=args.low_cap_run_m,
            low_cap_ratio_thresh=args.low_cap_ratio,
            low_cap_eval_start_m=args.low_cap_eval_start,
            return_rejected=True,
        )
        if not accepted and not rejected:
            print(f"유형3 후보 이벤트 0건 (rows={len(rows)}, v2)")
            return
        print(f"rows={len(rows)}, v2(2단계 판정) 결과:\n")
        _print_table(accepted, "확정 유형3 후보(2단계 통과)")
        if args.show_rejected or rejected:
            _print_table(rejected, "오탐 제외(far_window 내 실제 커브 감지)")
        return

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

    _print_table(events, "유형3 후보 이벤트")


if __name__ == "__main__":
    main()
