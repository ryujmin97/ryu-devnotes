#!/usr/bin/env python3
"""
363차 신규 -- 362차/362차 계속2가 설계한 "고립 fine curvature spike 억제
게이트"(크기-비율 게이트, RATIO 파라미터)를 실제 R≈20~35m급 급커브
corpus(0000039a--7b602ffb85 seg12, 2026-09-04, IC 램프)의 naviPaths
원본 좌표에 재적용해, 게이트가 진짜 급커브까지 억제하지 않는지 검증한다.

배경: 362차 계속2는 RATIO=0.3/0.5 둘 다 362차 오탐 corpus(고속도로
완만한 커브)에서 신고된 27개 오탐을 100% 억제한다고 확인했지만, 정작
"실제 급커브에서도 정상 검출을 유지하는가"(147/148차 원본 R≈27m
corpus로 검증 예정이었던 항목)는 원본 데이터 부재로 미실시였다. 이
스크립트는 그 미검증 항목을 이번에 새로 확보된 대체 corpus로 채운다.

핵심 함수(route_curvature_macro_fine)와 게이트 삽입 위치는 ryu HEAD
(bd21c7e)/WIP.md 362차 계속2에 기록된 설계를 verbatim 포팅했다(§27,
로직 재구현 없음) -- 게이트 자체는 아직 ryu 코드에 반영되지 않았으므로
production 코드에서 직접 import할 수 없어 이 방식이 유일한 검증 경로.

사용:
    python3 sim_route_363_gate_sharp_curve_regression.py <extract_log.py --with-navi-paths 출력 CSV> \\
        [--times 2024.5,2026.0,2028.0,2028.56,2030.0,2032.0] \\
        [--ratios 0.3,0.5] [--sharp-threshold-r 50]

CSV는 naviPaths 컬럼이 채워져 있어야 한다(--with-navi-paths 필수).
--times를 생략하면 naviPaths가 있는 모든 행을 훑어 NO-GATE 기준으로
R<sharp-threshold-r(기본 50m)인 급커브가 존재하는 프레임을 자동 선별한다.

출력: 프레임별로 NO-GATE/각 RATIO 적용 시 R<sharp-threshold-r인 지점들의
생존 여부를 나란히 보여주고, 마지막에 "가장 급한 지점(global min R)이
게이트 후에도 살아남은 프레임 비율" 요약 통계를 낸다.

363차가 이 스크립트로 실제 확인한 것: 0000039a seg12(t=2024.5~2032,
IC 램프, R≈20~35m 6프레임 샘플)에서 RATIO=0.5는 6개 중 3개 프레임에서
급커브 후보를 전부 걸러냄(0건 생존), RATIO=0.3도 6개 중 다수 프레임에서
가장 급한 지점(R≈20~24m)을 탈락시키고 더 완만한 인접 지점(R≈28~33m)만
남김. WIP.md/FINDINGS.md 363차 참고.
"""
import argparse
import csv
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
        return 0
    return cross_product / (len_v1 * len_v2 * len_v1)


def route_curvature_macro_fine_gated(resampled_points, distance_interval, sample,
                                      sample_fine, distance_offset,
                                      map_turn_speed_factor, road_limit_speed,
                                      ratio=None):
    """ryu/selfdrive/carrot/carrot_man.py::route_curvature_macro_fine()
    (bd21c7e 기준) verbatim 포팅 + WIP.md 362차 계속2 확정 설계(크기-비율
    게이트, fine 채택 직전에 좌우 인접 fine window 중 1개 이상이
    `|curv| >= ratio * 중심점|curv|`를 만족해야 함, OR조건, 탈락 시
    continue로 macro 유지) 삽입. ratio=None이면 게이트 비활성(기존
    동작과 byte-identical).
    """
    curvatures = []
    distances = []
    fine_triggered = []
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

    macro_speeds_arr = np.interp(macro_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
    macro_speeds_arr = macro_speeds_arr * map_turn_speed_factor
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
            fine_curvatures = []
            fine_abs_curv = []
            for i in range(n_fine):
                p1 = resampled_points[i]
                p2 = resampled_points[i + sample_fine]
                p3 = resampled_points[i + sample_fine * 2]
                f_curvature = calculate_curvature(p1, p2, p3)
                fine_curvatures.append(f_curvature)
                fine_abs_curv.append(abs(f_curvature))
            fine_speeds_arr = np.interp(fine_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
            fine_speeds_arr = fine_speeds_arr * map_turn_speed_factor
            for j in range(n_fine):
                f_curv = fine_curvatures[j]
                f_speed = fine_speeds_arr[j]
                if fine_abs_curv[j] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                    f_speed = max(f_speed, road_limit_speed)

                if ratio is not None:
                    left_supported = j > 0 and fine_abs_curv[j - 1] >= ratio * fine_abs_curv[j]
                    right_supported = (j + 1 < n_fine and
                                        fine_abs_curv[j + 1] >= ratio * fine_abs_curv[j])
                    if not (left_supported or right_supported):
                        continue  # macro 결과(speeds[j]) 유지, fine 미채택

                if f_speed < speeds[j]:
                    speeds[j] = f_speed
                    curvatures[j] = f_curv
                    fine_triggered[j] = True
    return curvatures, distances, speeds, fine_triggered


def parse_navipaths(s):
    pts = []
    for tok in s.split(';'):
        if not tok:
            continue
        x, y, _d = tok.split(',')
        pts.append((float(x), float(y)))
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", help="extract_log.py --with-navi-paths 출력 CSV")
    ap.add_argument("--times", default=None,
                     help="콤마구분 목표 시각(t). 생략 시 자동 스캔")
    ap.add_argument("--ratios", default="0.3,0.5",
                     help="콤마구분 RATIO 후보 목록 (기본 0.3,0.5)")
    ap.add_argument("--sharp-threshold-r", type=float, default=50.0,
                     help="이 반경(m) 미만을 '급커브'로 간주 (기본 50m)")
    ap.add_argument("--sample", type=int, default=4)
    ap.add_argument("--sample-fine", type=int, default=1)
    ap.add_argument("--distance-interval", type=float, default=10.0)
    args = ap.parse_args()

    ratios = [float(x) for x in args.ratios.split(",") if x]

    with open(args.csv_path) as fh:
        rows = list(csv.DictReader(fh))

    def to_float(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    if args.times:
        target_rows = []
        for tt in (float(x) for x in args.times.split(",") if x):
            best = min(rows, key=lambda r: abs(to_float(r['t']) - tt)
                       if to_float(r['t']) is not None else 1e9)
            target_rows.append(best)
    else:
        # naviPaths가 있고 NO-GATE 기준 급커브(R<threshold)가 존재하는 행만 자동 선별
        target_rows = []
        for row in rows:
            if not row.get('naviPaths'):
                continue
            pts = parse_navipaths(row['naviPaths'])
            curv, dist, speed, fine = route_curvature_macro_fine_gated(
                pts, args.distance_interval, args.sample, args.sample_fine,
                0.0, 1.0, 110.0, ratio=None)
            if any(f and abs(c) > 1.0 / args.sharp_threshold_r for c, f in zip(curv, fine)):
                target_rows.append(row)

    if not target_rows:
        print("급커브(NO-GATE 기준) 후보 프레임을 찾지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    survived_global_min = {r: 0 for r in ratios}
    total = 0

    for row in target_rows:
        if not row.get('naviPaths'):
            continue
        pts = parse_navipaths(row['naviPaths'])
        ve = to_float(row.get('vEgo'))
        ve_kmh = ve * 3.6 if ve is not None else float('nan')
        print(f"--- t={row['t'][:9]} seg={row['seg'][-2:]} vEgo={ve_kmh:.1f}km/h ---")

        curv0, dist0, speed0, fine0 = route_curvature_macro_fine_gated(
            pts, args.distance_interval, args.sample, args.sample_fine,
            0.0, 1.0, 110.0, ratio=None)
        sharp0 = [(d, c) for d, c, f in zip(dist0, curv0, fine0)
                  if f and abs(c) > 1.0 / args.sharp_threshold_r]
        if not sharp0:
            continue
        gmin_d, gmin_c = min(sharp0, key=lambda x: 1.0 / abs(x[1]))
        print(f"  NO-GATE : " + ", ".join(
            f"d={d:.0f}(R={1/abs(c):.1f}m)" for d, c in sharp0))
        total += 1

        for ratio in ratios:
            curv, dist, speed, fine = route_curvature_macro_fine_gated(
                pts, args.distance_interval, args.sample, args.sample_fine,
                0.0, 1.0, 110.0, ratio=ratio)
            sharp = [(d, c) for d, c, f in zip(dist, curv, fine)
                     if f and abs(c) > 1.0 / args.sharp_threshold_r]
            sharp_str = (", ".join(f"d={d:.0f}(R={1/abs(c):.1f}m)" for d, c in sharp)
                         if sharp else "(전부 걸러짐)")
            # global-min 지점(가장 급한 지점)이 이 ratio에서도 동일 dist로 살아남았는가
            gmin_survived = any(abs(d - gmin_d) < 1e-6 for d, _c in sharp)
            if gmin_survived:
                survived_global_min[ratio] += 1
            tag = "생존" if gmin_survived else "탈락"
            print(f"  RATIO={ratio}: {sharp_str}  [최급지점 {tag}]")

    print(f"\n=== 요약: 급커브 후보 프레임 {total}개 중 '가장 급한 지점'이 생존한 비율 ===")
    for ratio in ratios:
        n = survived_global_min[ratio]
        pct = (100.0 * n / total) if total else 0.0
        print(f"  RATIO={ratio}: {n}/{total} ({pct:.0f}%)")


if __name__ == "__main__":
    main()
