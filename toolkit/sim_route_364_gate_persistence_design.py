#!/usr/bin/env python3
"""
364차 신규 -- 363차가 "채택 불가"로 판정한 크기-비율(RATIO) 게이트를 대신할
"지속성 기반 게이트"(PERSIST) 설계안. 363차가 남긴 다음 작업(WIP.md 363차
"다음 작업" 1번: 게이트 재설계 방향 논의)에 대한 후속.

배경(FINDINGS.md 363차): RATIO 게이트는 "중심점 대비 바로 옆 1개 fine
윈도우의 상대적 낙폭"을 본다. 362차 오탐(완만한 직선 위 고립 spike)은
이웃이 거의 0이라 걸리지만, 실제 급커브(R≈20~35m)를 10m 간격 3점으로
근사하면 인접 윈도우끼리도 값이 크게 흔들려 같은 조건에 걸린다 -- 즉
"바로 옆 1점과의 비율"은 오탐/정탐을 가르는 신호가 아니었다.

이 스크립트가 시도하는 대안: route_curvature_macro_fine()의 fine 배열은
이미 distance_interval(기본 10m) 간격의 "공간적으로 연속된" 배열이다
(같은 프레임 내에서 차량 전방 경로를 따라 나열됨, 프레임 간 상태 불필요).
고립 spike는 이 배열에서 폭이 1점짜리 튀는 값이고, 실제 원호는 여러
연속 점이 함께 높은 값을 유지한다는 차이가 있다 -- 이를 "1개 이웃과의
비율"이 아니라 "중심점 기준 완화된 임계값(LOW_FRAC)을 만족하는 연속
구간의 길이(MIN_RUN점, 곧 MIN_RUN*distance_interval미터)"로 재정의한다.

RATIO 게이트와 동일하게 아직 ryu 코드에 없는 설계안이므로 verbatim
포팅(§27)으로 offline replay만 검증한다. route_curvature_macro_fine()
본문은 363차 스크립트(sim_route_363_gate_sharp_curve_regression.py)에서
그대로 재사용했다(§21, 동일 하네스 재작성 금지).

** 중요 -- 이 세션에서 실측하지 않았음 **
363차/362차 검증에 쓰인 corpus(0000039a--7b602ffb85 seg12-16,
d1cd25bdf1 등)는 §23 정책(대용량 CSV 미Git보관)에 따라 로컬/사용자
Drive에만 있고 이 세션 환경에는 없다. 아래 PERSIST 게이트는 설계 및
정적 구현만 완료된 상태이며, RATIO와 같은 자리에서 바로 비교
실행(--gate persist vs --gate ratio)할 수 있도록만 만들어졌다.
실측(오탐 corpus 억제율 + 급커브 corpus 생존율)은 사용자가 로컬에서
직접 돌리거나, corpus CSV를 업로드해주면 이어서 실행한다.

사용:
    python3 sim_route_364_gate_persistence_design.py <extract_log.py --with-navi-paths 출력 CSV> \\
        [--times ...] [--sharp-threshold-r 50] \\
        [--gate ratio|persist|both] \\
        [--ratios 0.3,0.5] \\
        [--low-fracs 0.15,0.25] [--min-runs 2,3,4]

--gate both: RATIO와 PERSIST 후보들을 한 표에 나란히 비교(363차 형식과
동일한 "가장 급한 지점 생존율" 요약 포함).
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


def _ratio_pass(j, fine_abs_curv, n_fine, ratio):
    """363차/362차 계속2 RATIO 게이트: 좌우 인접 1점 중 하나라도
    |curv| >= ratio * center|curv| 를 만족해야 채택(OR조건)."""
    left_supported = j > 0 and fine_abs_curv[j - 1] >= ratio * fine_abs_curv[j]
    right_supported = (j + 1 < n_fine and
                        fine_abs_curv[j + 1] >= ratio * fine_abs_curv[j])
    return left_supported or right_supported


def _persist_pass(j, fine_abs_curv, n_fine, low_frac, min_run):
    """364차 신규안: 중심점 기준 완화된 임계값(low_frac * center|curv|)을
    만족하는 연속 구간(중심점 포함, 좌우로 확장)의 길이가 min_run점
    이상이면 채택. 1점짜리 고립 spike는 폭이 1이라 대부분 걸리고, 실제
    원호는 인접 다수 점이 함께 낮아지지 않으므로 폭이 넓게 나올 것으로
    기대 -- 이 기대가 맞는지는 실측 전까지 가설이다.
    """
    center = fine_abs_curv[j]
    if center <= 0:
        return False
    thresh = low_frac * center
    left = j
    while left - 1 >= 0 and fine_abs_curv[left - 1] >= thresh:
        left -= 1
    right = j
    while right + 1 < n_fine and fine_abs_curv[right + 1] >= thresh:
        right += 1
    run_len = right - left + 1
    return run_len >= min_run


def route_curvature_macro_fine_gated(resampled_points, distance_interval, sample,
                                      sample_fine, distance_offset,
                                      map_turn_speed_factor, road_limit_speed,
                                      gate=None, ratio=None,
                                      low_frac=None, min_run=None):
    """ryu/selfdrive/carrot/carrot_man.py::route_curvature_macro_fine()
    (bd21c7e 기준) verbatim 포팅. gate=None이면 게이트 비활성(기존 동작과
    byte-identical). gate="ratio"면 363차 RATIO 게이트, gate="persist"면
    364차 지속성 게이트를 fine 채택 직전에 삽입한다.
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

                if gate == "ratio":
                    if not _ratio_pass(j, fine_abs_curv, n_fine, ratio):
                        continue
                elif gate == "persist":
                    if not _persist_pass(j, fine_abs_curv, n_fine, low_frac, min_run):
                        continue

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


def build_candidates(args):
    """--gate 옵션에 따라 (label, kwargs) 후보 목록을 만든다."""
    cands = []
    if args.gate in ("ratio", "both"):
        for r in (float(x) for x in args.ratios.split(",") if x):
            cands.append((f"RATIO={r}", dict(gate="ratio", ratio=r)))
    if args.gate in ("persist", "both"):
        low_fracs = [float(x) for x in args.low_fracs.split(",") if x]
        min_runs = [int(x) for x in args.min_runs.split(",") if x]
        for lf in low_fracs:
            for mr in min_runs:
                cands.append((f"PERSIST(low_frac={lf},min_run={mr})",
                               dict(gate="persist", low_frac=lf, min_run=mr)))
    return cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", help="extract_log.py --with-navi-paths 출력 CSV")
    ap.add_argument("--times", default=None,
                     help="콤마구분 목표 시각(t). 생략 시 자동 스캔")
    ap.add_argument("--gate", choices=["ratio", "persist", "both"], default="both")
    ap.add_argument("--ratios", default="0.3,0.5")
    ap.add_argument("--low-fracs", default="0.15,0.25")
    ap.add_argument("--min-runs", default="2,3,4")
    ap.add_argument("--sharp-threshold-r", type=float, default=50.0,
                     help="이 반경(m) 미만을 '급커브'로 간주 (기본 50m)")
    ap.add_argument("--sample", type=int, default=4)
    ap.add_argument("--sample-fine", type=int, default=1)
    ap.add_argument("--distance-interval", type=float, default=10.0)
    args = ap.parse_args()

    candidates = build_candidates(args)

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
        target_rows = []
        for row in rows:
            if not row.get('naviPaths'):
                continue
            pts = parse_navipaths(row['naviPaths'])
            curv, dist, speed, fine = route_curvature_macro_fine_gated(
                pts, args.distance_interval, args.sample, args.sample_fine,
                0.0, 1.0, 110.0, gate=None)
            if any(f and abs(c) > 1.0 / args.sharp_threshold_r for c, f in zip(curv, fine)):
                target_rows.append(row)

    if not target_rows:
        print("급커브(NO-GATE 기준) 후보 프레임을 찾지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    survived_global_min = {label: 0 for label, _ in candidates}
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
            0.0, 1.0, 110.0, gate=None)
        sharp0 = [(d, c) for d, c, f in zip(dist0, curv0, fine0)
                  if f and abs(c) > 1.0 / args.sharp_threshold_r]
        if not sharp0:
            continue
        gmin_d, gmin_c = min(sharp0, key=lambda x: 1.0 / abs(x[1]))
        print(f"  NO-GATE : " + ", ".join(
            f"d={d:.0f}(R={1/abs(c):.1f}m)" for d, c in sharp0))
        total += 1

        for label, kwargs in candidates:
            curv, dist, speed, fine = route_curvature_macro_fine_gated(
                pts, args.distance_interval, args.sample, args.sample_fine,
                0.0, 1.0, 110.0, **kwargs)
            sharp = [(d, c) for d, c, f in zip(dist, curv, fine)
                     if f and abs(c) > 1.0 / args.sharp_threshold_r]
            sharp_str = (", ".join(f"d={d:.0f}(R={1/abs(c):.1f}m)" for d, c in sharp)
                         if sharp else "(전부 걸러짐)")
            gmin_survived = any(abs(d - gmin_d) < 1e-6 for d, _c in sharp)
            if gmin_survived:
                survived_global_min[label] += 1
            tag = "생존" if gmin_survived else "탈락"
            print(f"  {label}: {sharp_str}  [최급지점 {tag}]")

    print(f"\n=== 요약: 급커브 후보 프레임 {total}개 중 '가장 급한 지점'이 생존한 비율 ===")
    for label, _ in candidates:
        n = survived_global_min[label]
        pct = (100.0 * n / total) if total else 0.0
        print(f"  {label}: {n}/{total} ({pct:.0f}%)")
    print("\n주의: 위 수치는 '급커브 corpus 생존율'만 나타낸다. 362차 오탐")
    print("corpus에서의 억제율은 별도로(같은 스크립트, 362차 corpus CSV로)")
    print("확인해야 PERSIST 후보의 최종 채택 여부를 판단할 수 있다.")


if __name__ == "__main__":
    main()
