#!/usr/bin/env python3
"""
[367차 예정] sim_route_367_batch_fp_tp_corpus_scan.py -- 366차 "다음 작업 1"
(오탐/정탐 corpus 다변화)을 위해 신규 11개 route(15만+ 행)를 자동 스캔해
ISOLATION 게이트용 오탐/정탐 후보를 대량 확보한다.

분류 기준(§27 -- 기존 방법론 재사용, 새 판별 로직 최소화):
- 공통 전제: routeApexMode=='new' and routeApexFineTriggered=='True'인
  프레임만 후보로 본다(365차 collect_false_positive_scores()와 동일한
  "fine이 새 apex를 트리거한 시점" 정의).
- 실제 R: 366차 crossval 스크립트와 동일하게 naviPaths에서
  calculate_curvature() verbatim 재계산(§27, apex j=round(dist/10)).
- TP(정탐) 후보: 실제 R < 30m (363차 원 기준 그대로).
- FP(오탐) 후보: 실제 R >= 50m **그리고** vTurnSpeed(비전 모델 기반 회전
  속도, route와 독립적인 신호) - routeApexSpeed >= gap_kph(기본 30kph).
  이는 362차가 수동으로 확인한 원 사례(vTurnSpeed 120~140 대비
  routeApexSpeed 70~80, 실제 R=88~92m)를 자동화 가능한 조건으로
  일반화한 것 -- vTurnSpeed는 실제 R 계산과 무관한 독립 신호라 R>=50m와
  함께 쓰면 "실제로 완만한데 route만 급감속을 낸" 경우를 골라낼 수 있음.

주의(§29 -- 미검증 시뮬레이션을 검증 결과로 보고 금지): 이 FP 자동분류는
362차처럼 개별 사례를 사람이 직접 채록/확인한 것이 아니라 gap 임계값
기반 자동 후보 선정이다. 362차 corpus(수동 확인 완료)와 섞어 쓰기 전에
반드시 "미확인" 꼬리표를 유지해야 한다.

사용:
    python3 sim_route_367_batch_fp_tp_corpus_scan.py <corpus_dir_glob...> \\
        [--gap-kph 30.0] [--fp-r-min 50.0] [--tp-r-max 30.0]
        [--out-fp fp_candidates.csv] [--out-tp tp_candidates.csv]
"""
import argparse
import csv
import glob
import math
import sys


def calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


def parse_navipaths(s):
    pts = []
    for chunk in s.strip().rstrip(';').split(';'):
        if not chunk:
            continue
        x, y, d = chunk.split(',')
        pts.append((float(x), float(y), float(d)))
    return pts


def actual_R_at_apex(pts, j):
    if j - 1 < 0 or j + 2 >= len(pts):
        return None
    p1 = (pts[j][0], pts[j][1])
    p2 = (pts[j + 1][0], pts[j + 1][1])
    p3 = (pts[j + 2][0], pts[j + 2][1])
    c = calculate_curvature(p1, p2, p3)
    return float('inf') if abs(c) < 1e-9 else 1.0 / abs(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_paths", nargs='+', help="corpus CSV 파일(들) 또는 glob 패턴")
    ap.add_argument("--gap-kph", type=float, default=30.0)
    ap.add_argument("--fp-r-min", type=float, default=50.0)
    ap.add_argument("--tp-r-max", type=float, default=30.0)
    ap.add_argument("--out-fp", default=None)
    ap.add_argument("--out-tp", default=None)
    args = ap.parse_args()

    paths = []
    for p in args.csv_paths:
        paths.extend(sorted(glob.glob(p)))
    if not paths:
        print("입력 CSV를 찾지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    fp_rows = []
    tp_rows = []
    per_route_stats = []

    for path in paths:
        route = path.split('/')[-1]
        n_total = 0
        n_navi = 0
        n_candidate = 0
        n_oob = 0
        n_fp = 0
        n_tp = 0
        with open(path, newline='') as f:
            for r in csv.DictReader(f):
                n_total += 1
                navi = r.get('naviPaths', '')
                if r.get('routeApexMode') != 'new' or r.get('routeApexFineTriggered') != 'True':
                    continue
                if len(navi) < 20:
                    continue
                n_navi += 1
                try:
                    d = float(r['routeApexDist'])
                    spd = float(r['routeApexSpeed'])
                    vturn = float(r.get('vTurnSpeed') or 'nan')
                except (KeyError, ValueError, TypeError):
                    continue
                pts = parse_navipaths(navi)
                j = round(d / 10.0)
                R = actual_R_at_apex(pts, j)
                if R is None:
                    n_oob += 1
                    continue
                n_candidate += 1
                rec = dict(route=route, t=r.get('t'), R=R, apexSpeed=spd,
                           vTurnSpeed=vturn, apexDist=d)
                if R < args.tp_r_max:
                    tp_rows.append(rec)
                    n_tp += 1
                elif (R >= args.fp_r_min and vturn == vturn  # not NaN
                        and (vturn - spd) >= args.gap_kph):
                    fp_rows.append(rec)
                    n_fp += 1
        per_route_stats.append((route, n_total, n_navi, n_candidate, n_tp, n_fp))

    print(f"{'route':<55} {'총행':>8} {'naviOK':>8} {'후보':>6} {'TP':>5} {'FP':>5}")
    for route, n_total, n_navi, n_candidate, n_tp, n_fp in per_route_stats:
        print(f"{route:<55} {n_total:>8} {n_navi:>8} {n_candidate:>6} {n_tp:>5} {n_fp:>5}")

    print(f"\n=== 합계 ===")
    print(f"TP(정탐, 실제 R<{args.tp_r_max}m) 후보: {len(tp_rows)}건")
    print(f"FP(오탐, 실제 R>={args.fp_r_min}m 이고 vTurnSpeed-apexSpeed>={args.gap_kph}kph) 후보: {len(fp_rows)}건")

    if args.out_tp and tp_rows:
        with open(args.out_tp, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['route', 't', 'R', 'apexSpeed', 'vTurnSpeed', 'apexDist'])
            w.writeheader()
            w.writerows(tp_rows)
        print(f"TP 후보 -> {args.out_tp}")
    if args.out_fp and fp_rows:
        with open(args.out_fp, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['route', 't', 'R', 'apexSpeed', 'vTurnSpeed', 'apexDist'])
            w.writeheader()
            w.writerows(fp_rows)
        print(f"FP 후보 -> {args.out_fp}")


if __name__ == "__main__":
    main()
