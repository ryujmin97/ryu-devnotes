#!/usr/bin/env python3
"""
[367차] dedup_physical_events_367.py -- v2 스캔이 생성한 TP/FP 후보 CSV에서
같은 물리적 커브가 apexDist 진동(§365차 '미확인 사항 #3' 계열, 격자
경계/노이즈로 인한 재트리거)으로 여러 프레임에 걸쳐 중복 채택된 것을
"물리적 이벤트" 단위로 묶어 재정제한다.

방법: route별로 시간순 정렬 후, 연속 후보 간 시간차가 --cluster-gap-s
(기본 8초) 이내면 같은 물리적 이벤트로 간주해 하나의 클러스터로 묶는다.
클러스터 대표값은 R이 가장 작은(가장 급한 커브로 판정된) 프레임을 채택한다.
이는 v2 스크립트의 dedup(§29 근사 휴리스틱)보다 한 단계 더 보수적인
재정제이며, 이 역시 실제 device 상태기계 출력이 아닌 근사임을 명시한다.
"""
import argparse
import csv


def cluster(rows, gap_s):
    rows = sorted(rows, key=lambda r: (r['route'], float(r['t'])))
    clusters = []
    cur = []
    for r in rows:
        if cur and (r['route'] != cur[-1]['route'] or float(r['t']) - float(cur[-1]['t']) > gap_s):
            clusters.append(cur)
            cur = []
        cur.append(r)
    if cur:
        clusters.append(cur)
    return clusters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--cluster-gap-s", type=float, default=8.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.csv_path, newline='') as f:
        rows = list(csv.DictReader(f))

    clusters = cluster(rows, args.cluster_gap_s)
    reps = [min(c, key=lambda r: float(r['R'])) for c in clusters]

    from collections import Counter
    print(f"입력 프레임 수: {len(rows)} -> 물리적 이벤트(클러스터) 수: {len(clusters)}")
    print("route별 클러스터 수:", Counter(r['route'] for r in reps))

    if args.out:
        with open(args.out, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['route', 't', 'R', 'apexSpeed', 'vTurnSpeed', 'apexDist', 'n_frames_in_cluster'])
            w.writeheader()
            for c, rep in zip(clusters, reps):
                d = dict(rep)
                d['n_frames_in_cluster'] = len(c)
                w.writerow(d)
        print(f"-> {args.out}")


if __name__ == "__main__":
    main()
