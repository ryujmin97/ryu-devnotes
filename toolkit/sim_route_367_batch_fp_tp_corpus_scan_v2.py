#!/usr/bin/env python3
"""
[367차 예정] sim_route_367_batch_fp_tp_corpus_scan_v2.py -- 366차 "다음
작업 1"(오탐/정탐 corpus 다변화)용. v1과 차이: 업로드된 11개 신규 route가
모두 2026-09-01~09-03 녹화분으로, routeApexMode/routeApexFineTriggered
계측(310차, 2026-09-08 추가)보다 이전 빌드라 해당 필드가 항상 빈 값임을
확인(§28 -- 원인 추적 후 확정). 이 필드에 의존하지 않고 naviPaths(194차,
2026-09-02부터 존재 -- 이 11개 route 전부 포함)만으로 자체 재계산한다.

방법(§27, 기존 함수 verbatim 재사용):
1. `route_curvature_macro_fine_gated()`(363차 포팅본)를 각 행의 naviPaths
   전체에 그대로 실행해 fine_triggered 배열을 자체 계산(device 필드 대신).
2. apex 지점 j=round(routeApexDist/10)에서 fine_triggered[j]가 True인
   행만 후보로 채택 -- "device가 fine으로 새 apex를 잡았다"의 근사.
3. 중복 제거(dedup, §29 -- 근사 로직임을 명시): routeApexMode='new'
   전이(이전 프레임과 다른 새 apex 시작)를 대신할 상태가 없으므로,
   route별로 시간순 정렬 후 apexDist가 "감소 추적 중"(이전 값보다 작거나
   비슷)이면 같은 이벤트의 연속 관측으로 보고 skip, apexDist가 이전보다
   `--new-event-jump-m`(기본 15m) 이상 커지면 새 이벤트 시작으로 보고
   그 프레임만 채택한다. 이는 device의 정확한 상태기계 재현이 아니라
   근사 휴리스틱이다 -- 결과 corpus는 362차 corpus(실제 device
  'new'+fineTriggered 필드로 확정된 수동 검증 corpus)와 반드시 구분해서
  다뤄야 한다.
4. TP(정탐) 후보: 실제 R < tp-r-max(기본 30m).
   FP(오탐) 후보: 실제 R >= fp-r-min(기본 50m) AND vTurnSpeed(비전 기반,
   route와 독립) - routeApexSpeed >= gap-kph(기본 30kph, 362차 수동 확인
   사례의 관측 격차를 일반화).

한계(§29 필수 명시): 이 스크립트로 확보한 FP/TP corpus는 "자체 재계산 +
근사 dedup 휴리스틱" 기반이지 device의 실제 상태기계 출력이 아니다.
362/363차 corpus(수동 확인 또는 device 필드 확정)와 섞어 결론 낼 때는
반드시 이 한계를 함께 표기한다.

사용:
    python3 sim_route_367_batch_fp_tp_corpus_scan_v2.py <corpus_dir_glob...> \\
        [--gap-kph 30.0] [--fp-r-min 50.0] [--tp-r-max 30.0]
        [--new-event-jump-m 15.0]
        [--out-fp fp.csv] [--out-tp tp.csv]
"""
import argparse
import csv
import glob
import math
import sys

import numpy as np

V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265.,
                     1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001


def calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


def route_curvature_macro_fine_gated(resampled_points, distance_interval, sample,
                                      sample_fine, distance_offset,
                                      map_turn_speed_factor, road_limit_speed):
    """363차 sim_route_363_gate_sharp_curve_regression.py verbatim(§27),
    ratio=None 고정(게이트 없음, ryu 기본 동작과 byte-identical)."""
    curvatures, distances, fine_triggered = [], [], []
    if len(resampled_points) < sample * 2 + 1:
        return curvatures, distances, [], fine_triggered
    distance = distance_offset - distance_interval
    macro_abs_curv = []
    for i in range(len(resampled_points) - sample * 2):
        distance += distance_interval
        p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
        curvature = calculate_curvature(p1, p2, p3)
        curvatures.append(curvature)
        macro_abs_curv.append(abs(curvature))
        distances.append(distance)
    macro_speeds_arr = np.interp(macro_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS) * map_turn_speed_factor
    speeds = []
    for i in range(len(curvatures)):
        speed = macro_speeds_arr[i]
        if macro_abs_curv[i] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
            speed = max(speed, road_limit_speed)
        speeds.append(speed)
    fine_triggered = [False] * len(speeds)
    if sample_fine and sample_fine < sample and len(resampled_points) >= sample_fine * 2 + 1:
        n_fine = min(len(distances), len(resampled_points) - sample_fine * 2)
        if n_fine > 0:
            fine_curvatures, fine_abs_curv = [], []
            for i in range(n_fine):
                p1, p2, p3 = resampled_points[i], resampled_points[i + sample_fine], resampled_points[i + sample_fine * 2]
                f_curvature = calculate_curvature(p1, p2, p3)
                fine_curvatures.append(f_curvature)
                fine_abs_curv.append(abs(f_curvature))
            fine_speeds_arr = np.interp(fine_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS) * map_turn_speed_factor
            for j in range(n_fine):
                f_curv, f_speed = fine_curvatures[j], fine_speeds_arr[j]
                if fine_abs_curv[j] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                    f_speed = max(f_speed, road_limit_speed)
                if f_speed < speeds[j]:
                    speeds[j] = f_speed
                    curvatures[j] = f_curv
                    fine_triggered[j] = True
    return curvatures, distances, speeds, fine_triggered


def parse_navipaths(s):
    pts = []
    for chunk in s.strip().rstrip(';').split(';'):
        if not chunk:
            continue
        x, y, d = chunk.split(',')
        pts.append((float(x), float(y), float(d)))
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_paths", nargs='+')
    ap.add_argument("--gap-kph", type=float, default=30.0)
    ap.add_argument("--fp-r-min", type=float, default=50.0)
    ap.add_argument("--tp-r-max", type=float, default=30.0)
    ap.add_argument("--new-event-jump-m", type=float, default=15.0)
    ap.add_argument("--out-fp", default=None)
    ap.add_argument("--out-tp", default=None)
    args = ap.parse_args()

    paths = []
    for p in args.csv_paths:
        paths.extend(sorted(glob.glob(p)))
    if not paths:
        print("입력 CSV를 찾지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    fp_rows, tp_rows = [], []
    per_route_stats = []

    for path in paths:
        route = path.split('/')[-1]
        with open(path, newline='') as f:
            rows = list(csv.DictReader(f))

        def to_float(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        rows.sort(key=lambda r: to_float(r.get('t')) or 0.0)

        n_total = len(rows)
        n_navi = 0
        n_fine_self = 0
        n_new_event = 0
        n_tp = n_fp = 0
        prev_dist = None

        for r in rows:
            navi = r.get('naviPaths', '')
            d = to_float(r.get('routeApexDist'))
            spd = to_float(r.get('routeApexSpeed'))
            vturn = to_float(r.get('vTurnSpeed'))
            if len(navi) < 20 or d is None or spd is None:
                prev_dist = None
                continue
            n_navi += 1

            # dedup: apexDist가 이전보다 new-event-jump-m 이상 커지면 새 이벤트
            is_new_event = (prev_dist is None) or (d > prev_dist + args.new_event_jump_m)
            prev_dist = d
            if not is_new_event:
                continue
            n_new_event += 1

            pts_full = parse_navipaths(navi)
            pts_xy = [(x, y) for x, y, _dd in pts_full]
            curv, dist_arr, speed_arr, fine = route_curvature_macro_fine_gated(
                pts_xy, 10.0, 4, 1, 0.0, 1.0, 110.0)
            j = round(d / 10.0)
            if j < 0 or j >= len(fine) or not fine[j]:
                continue
            n_fine_self += 1
            c = curv[j]
            R = float('inf') if abs(c) < 1e-9 else 1.0 / abs(c)

            rec = dict(route=route, t=r.get('t'), R=R, apexSpeed=spd,
                       vTurnSpeed=vturn if vturn is not None else float('nan'),
                       apexDist=d)
            if R < args.tp_r_max:
                tp_rows.append(rec)
                n_tp += 1
            elif R >= args.fp_r_min and vturn is not None and (vturn - spd) >= args.gap_kph:
                fp_rows.append(rec)
                n_fp += 1

        per_route_stats.append((route, n_total, n_navi, n_new_event, n_fine_self, n_tp, n_fp))

    print(f"{'route':<50} {'총행':>7} {'naviOK':>7} {'새이벤트':>8} {'자체fine':>8} {'TP':>5} {'FP':>5}")
    for route, n_total, n_navi, n_new_event, n_fine_self, n_tp, n_fp in per_route_stats:
        print(f"{route:<50} {n_total:>7} {n_navi:>7} {n_new_event:>8} {n_fine_self:>8} {n_tp:>5} {n_fp:>5}")

    print(f"\n=== 합계 ===")
    print(f"TP(정탐, 실제 R<{args.tp_r_max}m) 후보: {len(tp_rows)}건")
    print(f"FP(오탐, 실제 R>={args.fp_r_min}m 이고 vTurnSpeed-apexSpeed>={args.gap_kph}kph) 후보: {len(fp_rows)}건")

    if args.out_tp:
        with open(args.out_tp, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['route', 't', 'R', 'apexSpeed', 'vTurnSpeed', 'apexDist'])
            w.writeheader()
            w.writerows(tp_rows)
        print(f"TP 후보 -> {args.out_tp}")
    if args.out_fp:
        with open(args.out_fp, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['route', 't', 'R', 'apexSpeed', 'vTurnSpeed', 'apexDist'])
            w.writeheader()
            w.writerows(fp_rows)
        print(f"FP 후보 -> {args.out_fp}")


if __name__ == "__main__":
    main()
