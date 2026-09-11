#!/usr/bin/env python3
"""
[366차 신규] sim_route_366_tp_proxy_r_crossvalidation.py -- 365차
"미확인 사항 #2" 해소: 365차 collect_true_positive_scores()/
isolation_score()가 실제로 쓴 표본 정의(윈도우 조건 j-1>=0 and
j+2<len(pts), 365차 tp corpus=1233건과 정확히 일치 확인됨)를 그대로
재사용해, "실제 R<30m"(363차 원 기준, sim_route_363_gate_sharp_curve_
regression.py) 대비 365차 대리필터(routeApexSpeed<=45kph)의 정확도를
프레임 단위 혼동행렬로 낸다.

366차 실측 결과(corpus_363_seg12-16.csv, 5,999행 중 사용가능 3649건,
routeApexSpeed<=45kph 필터 통과 1233건 = 365차 기록과 일치):
- precision(대리필터 통과분 중 실제 R<30m 비율) = 92.2%(1137/1233)
- recall(실제 R<30m 중 대리필터가 포착한 비율) = 100%(1137/1137, 누락 없음)
- 오염(R>=30m인데 필터 통과) 96건(7.8%), R 분포 min=19.7m~max=67.1m
- 임계값 스윕: routeApexSpeed<=25kph로 좁히면 precision/recall 둘 다
  100%(1137/1137, 오염 0건) -- 363차 R<30m 기준과 완전히 일치하는 순수
  정탐 표본을 얻으려면 45kph보다 25kph 근방이 더 정확.
상세는 WIP.md/FINDINGS.md 366차 참고.

사용:
    python3 sim_route_366_tp_proxy_r_crossvalidation.py <corpus_363_seg12-16.csv> \\
        [--tp-speed-max 45.0] [--sharp-r 30.0]

한계: 이 스크립트 자체는 363차 corpus 1개 route에서만 검증됨(다른 route
급커브 corpus로 일반화 여부 미검증, 366차 "다음 작업" 참고).
"""
import argparse
import csv
import math


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--tp-speed-max", type=float, default=45.0)
    ap.add_argument("--sharp-r", type=float, default=30.0)
    args = ap.parse_args()

    with open(args.csv_path, newline='') as f:
        rows = list(csv.DictReader(f))

    recs = []  # (R, spd, t)
    for r in rows:
        navi = r.get('naviPaths', '')
        if len(navi) < 20:
            continue
        try:
            d = float(r['routeApexDist'])
            spd = float(r['routeApexSpeed'])
        except (KeyError, ValueError, TypeError):
            continue
        pts = parse_navipaths(navi)
        j = round(d / 10.0)
        # 365차 isolation_score()와 동일 윈도우 조건 (j-1>=0 and j+2<len(pts))
        if j - 1 < 0 or j + 2 >= len(pts):
            continue
        p1 = (pts[j][0], pts[j][1])
        p2 = (pts[j + 1][0], pts[j + 1][1])
        p3 = (pts[j + 2][0], pts[j + 2][1])
        c = calculate_curvature(p1, p2, p3)
        R = float('inf') if abs(c) < 1e-9 else 1.0 / abs(c)
        recs.append((R, spd, r.get('t')))

    print(f"365차와 동일 모집단(isolation 윈도우 조건 충족): {len(recs)}건")

    proxy_pass = [rec for rec in recs if 0 < rec[1] <= args.tp_speed_max]
    print(f"대리필터(routeApexSpeed<=({args.tp_speed_max})kph) 통과: {len(proxy_pass)}건 "
          f"(365차 실측 1233건과 {'일치' if len(proxy_pass) == 1233 else '불일치 -- 재확인 필요'})")

    tp = fp = fn = tn = 0
    for R, spd, t in recs:
        actual_sharp = R < args.sharp_r
        proxy_sharp = (0 < spd <= args.tp_speed_max)
        if actual_sharp and proxy_sharp:
            tp += 1
        elif (not actual_sharp) and proxy_sharp:
            fp += 1
        elif actual_sharp and not proxy_sharp:
            fn += 1
        else:
            tn += 1

    print(f"\n=== 혼동행렬 (실제 R<{args.sharp_r}m vs 대리필터 routeApexSpeed<={args.tp_speed_max}kph) ===")
    print(f"  TP(실제급커브&대리필터통과): {tp}   FP(실제완만&대리필터통과, 오염): {fp}")
    print(f"  FN(실제급커브&대리필터탈락, 누락): {fn}   TN(실제완만&대리필터탈락): {tn}")
    if proxy_pass:
        precision = tp / (tp + fp) if (tp + fp) else float('nan')
        print(f"\n  precision(대리필터 통과분 중 실제 R<{args.sharp_r}m 비율) = {precision*100:.1f}% ({tp}/{tp+fp})")
    sharp_total = tp + fn
    if sharp_total:
        recall = tp / sharp_total
        print(f"  recall(실제 R<{args.sharp_r}m 중 대리필터가 포착한 비율)   = {recall*100:.1f}% ({tp}/{sharp_total})")

    if proxy_pass:
        Rs = sorted(x[0] for x in proxy_pass if x[0] != float('inf'))
        def pct(p):
            idx = min(len(Rs) - 1, int(len(Rs) * p))
            return Rs[idx]
        print(f"\n365차 정탐 표본({len(proxy_pass)}건) 실제 R 분포: "
              f"min={Rs[0]:.1f}m median={pct(0.50):.1f}m p90={pct(0.90):.1f}m max={Rs[-1]:.1f}m")
        over_r = sum(1 for x in Rs if x >= args.sharp_r)
        print(f"  R>={args.sharp_r}m(363차 정의상 '정탐 아님')인 오염 표본: {over_r}/{len(Rs)} ({100*over_r/len(Rs):.1f}%)")

    print(f"\n=== 대리필터 임계값 스윕 (실제 R<{args.sharp_r}m 재현도, 365차와 동일 모집단) ===")
    print(f"{'speed_max':>10} {'precision':>10} {'recall':>10} {'n_pass':>8}")
    for smax in [15, 20, 25, 30, 35, 40, 45, 50, 60]:
        p_tp = p_fp = 0
        for R, spd, t in recs:
            if 0 < spd <= smax:
                if R < args.sharp_r:
                    p_tp += 1
                else:
                    p_fp += 1
        n_pass = p_tp + p_fp
        prec = p_tp / n_pass if n_pass else float('nan')
        rec_ = p_tp / sharp_total if sharp_total else float('nan')
        print(f"{smax:>10} {prec*100:>9.1f}% {rec_*100:>9.1f}% {n_pass:>8}")


if __name__ == "__main__":
    main()
