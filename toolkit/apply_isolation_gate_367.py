#!/usr/bin/env python3
"""
[367차 신규] 365차 ISOLATION 게이트(isolation_score, th=0.885~0.92)를
367차가 확보한 22개 FP / 4개 TP "물리적 이벤트"(dedup_physical_events_367.py
산출)에 직접 적용해 억제율/생존율을 재평가한다.

배경 (§28 순서 -- 증상->재현조건->원인->검증):
- 367차 v2 스캔은 요약 CSV(route,t,R,apexSpeed,vTurnSpeed,apexDist,
  n_frames_in_cluster)만 남기고 naviPaths는 버렸다 -- 365차 isolation_score()는
  naviPaths 원시좌표가 있어야 계산 가능하므로, extract_log.py --with-navi-paths로
  해당 11개 route를 재추출한 뒤 (route,t) 매칭으로 naviPaths를 다시 찾아온다.
- 365차 collect_false_positive_scores()/collect_true_positive_scores()는
  routeApexMode=='new' & routeApexFineTriggered=='True' (362차형) 또는
  routeApexSpeed<=45kph 대리필터(363차형) 기준으로 후보를 스스로 고르는데,
  367차 22/4건은 이미 완성된 후보 목록(v2 재계산 + 8초 클러스터링)이라
  이 필터들을 그대로 쓰지 않고, isolation_score(pts, j) 계산 함수만
  365차 스크립트에서 verbatim import해 재사용한다(§27 최소변경 -- 새
  isolation_score 로직 작성 안 함).

한계 (§28 -- 성급한 결론 금지):
1. 22/4건 자체가 이미 이중 근사(v2 재계산 dedup + 8초 클러스터링) 위에
   있음(367차 WIP 기록 참고) -- 이 스크립트가 추가하는 근사는 없지만
   원본 한계는 그대로 유지됨.
2. 클러스터 대표 프레임(R 최소)의 t/apexDist로 naviPaths를 찾으므로,
   클러스터 내 다른 프레임의 isolation_score는 보지 않음(대표 1프레임만).
3. t 매칭은 정확히 같은 프레임을 다시 찾는 것(재계산 소스가 같은
   추출이므로 소수점 단위로 일치해야 함) -- 매칭 실패 시 명시적으로 보고.

입력: 367차 FP/TP dedup CSV(route,t,R,apexSpeed,vTurnSpeed,apexDist,
n_frames_in_cluster) + extract_log.py --with-navi-paths로 뽑은
route별 전체 CSV(naviPaths 포함).

사용:
    python3 apply_isolation_gate_367.py \
        --fp-csv fp_candidates_367_v2_clean_dedup.csv \
        --tp-csv tp_candidates_367_v2_dedup.csv \
        --route-csv-dir /home/claude/work \
        [--thresholds 0.80,0.85,0.885,0.90,0.905,0.92,0.95,0.98] \
        [--t-tolerance 0.05]
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 365차 스크립트를 모듈로 import (isolation_score/parse_navipaths verbatim 재사용, §27)
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "sim_route_365", "/home/claude/ryu-devnotes/toolkit/sim_route_365_heading_isolation_gate.py")
sim_route_365 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim_route_365)
isolation_score = sim_route_365.isolation_score
parse_navipaths = sim_route_365.parse_navipaths


def load_candidates(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def build_route_index(route_csv_path):
    """route별 전체 CSV를 route,t 매칭용으로 메모리에 로드."""
    with open(route_csv_path, newline='') as f:
        rows = list(csv.DictReader(f))
    return rows


def find_matching_row(rows, t_target, tol):
    best = None
    best_diff = None
    for r in rows:
        if not r.get('t'):
            continue
        diff = abs(float(r['t']) - t_target)
        if diff <= tol and (best_diff is None or diff < best_diff):
            best = r
            best_diff = diff
    return best, best_diff


def compute_scores(candidates, route_csv_dir, tol):
    results = []
    route_cache = {}
    for c in candidates:
        route = c['route'].replace('.csv', '')
        t_target = float(c['t'])
        if route not in route_cache:
            csv_path = os.path.join(route_csv_dir, f"{route}_full.csv")
            if not os.path.exists(csv_path):
                print(f"[경고] {route}_full.csv 없음 -- 건너뜀", file=sys.stderr)
                route_cache[route] = []
            else:
                route_cache[route] = build_route_index(csv_path)
        rows = route_cache[route]
        if not rows:
            results.append({**c, 'route': route, 'match': False, 'score': None, 'reason': 'route_csv_missing'})
            continue
        row, diff = find_matching_row(rows, t_target, tol)
        if row is None:
            results.append({**c, 'route': route, 'match': False, 'score': None, 'reason': f't_no_match(tol={tol})'})
            continue
        navi = row.get('naviPaths', '')
        if len(navi) < 20:
            results.append({**c, 'route': route, 'match': True, 'score': None, 'reason': 'naviPaths_empty', 't_diff': diff})
            continue
        try:
            apex_dist = float(row['routeApexDist'])
        except (KeyError, ValueError):
            results.append({**c, 'route': route, 'match': True, 'score': None, 'reason': 'apexDist_parse_fail', 't_diff': diff})
            continue
        pts = parse_navipaths(navi)
        j = round(apex_dist / 10.0)
        score = isolation_score(pts, j)
        results.append({**c, 'route': route, 'match': True, 'score': score,
                         'reason': None if score is not None else 'window_edge(j-1<0 or j+2>=len)',
                         't_diff': diff, 'apexDist_matched': apex_dist})
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fp-csv', required=True)
    ap.add_argument('--tp-csv', required=True)
    ap.add_argument('--route-csv-dir', required=True)
    ap.add_argument('--thresholds', type=str, default='0.80,0.85,0.885,0.90,0.905,0.92,0.95,0.98')
    ap.add_argument('--t-tolerance', type=float, default=0.05)
    args = ap.parse_args()

    fp_candidates = load_candidates(args.fp_csv)
    tp_candidates = load_candidates(args.tp_csv)

    print(f"FP 후보: {len(fp_candidates)}건 / TP 후보: {len(tp_candidates)}건")
    print()

    fp_results = compute_scores(fp_candidates, args.route_csv_dir, args.t_tolerance)
    tp_results = compute_scores(tp_candidates, args.route_csv_dir, args.t_tolerance)

    print("=== FP (22건) isolation_score 상세 ===")
    for r in fp_results:
        score_str = f"{r['score']:.3f}" if r['score'] is not None else f"N/A({r.get('reason')})"
        print(f"  {r['route']:>12} t={float(r['t']):>10.3f} R={float(r['R']):>8.1f} "
              f"n_cluster={r['n_frames_in_cluster']:>3} iso={score_str}")
    print()
    print("=== TP (4건) isolation_score 상세 ===")
    for r in tp_results:
        score_str = f"{r['score']:.3f}" if r['score'] is not None else f"N/A({r.get('reason')})"
        print(f"  {r['route']:>12} t={float(r['t']):>10.3f} R={float(r['R']):>8.1f} "
              f"n_cluster={r['n_frames_in_cluster']:>3} iso={score_str}")
    print()

    fp_vals = [r['score'] for r in fp_results if r['score'] is not None]
    tp_vals = [r['score'] for r in tp_results if r['score'] is not None]
    fp_na = len(fp_results) - len(fp_vals)
    tp_na = len(tp_results) - len(tp_vals)
    print(f"매칭/계산 성공: FP {len(fp_vals)}/{len(fp_results)}건 (N/A {fp_na}건), "
          f"TP {len(tp_vals)}/{len(tp_results)}건 (N/A {tp_na}건)")
    print()

    if fp_vals:
        print(f"FP isolation_score: min={min(fp_vals):.3f} "
              f"median={sorted(fp_vals)[len(fp_vals)//2]:.3f} max={max(fp_vals):.3f}")
    if tp_vals:
        print(f"TP isolation_score: min={min(tp_vals):.3f} "
              f"median={sorted(tp_vals)[len(tp_vals)//2]:.3f} max={max(tp_vals):.3f}")
    print()

    thresholds = [float(x) for x in args.thresholds.split(',')]
    print(f"{'threshold':>10} {'FP 억제율':>12} {'TP 생존율':>12}")
    for th in thresholds:
        supp = sum(1 for v in fp_vals if v >= th) / len(fp_vals) if fp_vals else float('nan')
        surv = sum(1 for v in tp_vals if v < th) / len(tp_vals) if tp_vals else float('nan')
        print(f"{th:>10.3f} {supp*100:>11.1f}% {surv*100:>11.1f}%")


if __name__ == '__main__':
    main()
