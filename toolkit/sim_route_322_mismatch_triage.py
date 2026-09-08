#!/usr/bin/env python3
"""322-B: sim_route_322_single_frame_check.py가 찾은 mismatch 프레임들을
자동 분류한다.

분류 기준:
  A. Rounding-boundary: offline이 logged보다 candidate가 1개 많거나 적을 때,
     그 차이나는 후보(가장 마지막에 추가/제외된 후보)의 speed가
     road_limit_speed(nRoadLimitSpeed) 경계에서 ROUND_MARGIN_KPH 이내로 붙어
     있는 경우. naviPaths가 .2f(0.01m)로 반올림되어 로깅되므로, production의
     미반올림 좌표가 만든 진짜 curvature/speed와 offline이 반올림된 좌표로
     재계산한 curvature/speed가 이 폭 안에서 갈릴 수 있다.
  B. 그 외 전부(경계에서 먼 차이, count 차이가 2 이상, cluster/orphan 재배치가
     경계값 하나로 설명 안 되는 경우 등) -- 실제 reconstruction 차이 후보.

주의: 로그에는 .2f로 반올림된 naviPaths만 있고 production의 원본 미반올림
좌표는 없으므로, "진짜 경계값 근처였다"는 것을 좌표 자체로 직접 증명할 수는
없다 -- 대신 재계산된 speed가 threshold에 얼마나 가까운지로 간접 판정한다
(A 분류의 한계로 WIP에 명시할 것).
"""
import argparse
import csv

from sim_route_322_single_frame_check import (
    MAP_TURN_SPEED_FACTOR, ROUTE_CLUSTER_MAX_GAP_M, ROUTE_CLUSTER_MIN_POINTS,
    ROUTE_CURVE_NEGLIGIBLE_THRESHOLD, V_CRUVE_LOOKUP_VALS, V_CURVE_LOOKUP_BP,
    calculate_curvature, parse_navi_paths, route_find_clusters)
import numpy as np

ROUND_MARGIN_KPH = 0.5  # 경계 판정 폭(kph) -- speed가 road_limit_speed와 이 이내면 "경계 근접"


def recompute_full(resampled_points, resampled_distances, road_limit_speed,
                    map_turn_speed_factor=MAP_TURN_SPEED_FACTOR):
    """sim_route_322_single_frame_check.recompute()와 동일 로직이지만
    speeds/distances 전체 배열과 candidates 인덱스 리스트를 그대로 반환
    (경계값 근접 여부를 보려면 count/앞 3개만으로는 부족)."""
    sample = 4
    curvatures, distances, speeds = [], [], []

    if len(resampled_points) >= sample * 2 + 1:
        distance = -10.0
        macro_abs_curv = []
        for i in range(len(resampled_points) - sample * 2):
            distance += 10.0
            p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
            curvature = calculate_curvature(p1, p2, p3)
            curvatures.append(curvature)
            macro_abs_curv.append(abs(curvature))
            distances.append(distance)

        macro_speeds_arr = np.interp(macro_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS) * map_turn_speed_factor
        for i in range(len(curvatures)):
            speed = macro_speeds_arr[i]
            if macro_abs_curv[i] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                speed = max(speed, road_limit_speed)
            speeds.append(speed)

        sample_fine = 1
        if sample_fine < sample and len(resampled_points) >= sample_fine * 2 + 1:
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
                    f_speed = fine_speeds_arr[j]
                    if fine_abs_curv[j] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                        f_speed = max(f_speed, road_limit_speed)
                    if f_speed < speeds[j]:
                        speeds[j] = f_speed
                        curvatures[j] = fine_curvatures[j]

    candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed]
    all_clusters = route_find_clusters(candidates, distances, 1, ROUTE_CLUSTER_MAX_GAP_M)
    clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
    orphans = [c for c in all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]
    return speeds, distances, candidates, len(clusters), len(orphans)


def classify(row):
    pts, dists_raw = parse_navi_paths(row["naviPaths"])
    road_limit_speed = float(row["nRoadLimitSpeed"]) if row["nRoadLimitSpeed"] else 300.0
    speeds, distances, candidates, cluster_count, orphan_count = recompute_full(pts, dists_raw, road_limit_speed)

    logged_cand = int(row["routeCandidateCount"]) if row["routeCandidateCount"] else 0
    logged_cluster = int(row["routeClusterCount"]) if row["routeClusterCount"] else 0
    logged_orphan = int(row["routeOrphanSingletonCount"]) if row["routeOrphanSingletonCount"] else 0
    off_cand = len(candidates)

    diff = off_cand - logged_cand
    reason = "B_other"
    detail = ""

    if abs(diff) == 1:
        # 후보 전체 리스트 중 "가장 거리가 먼(=가장 최근에 lookahead에 들어온)"
        # 쪽이 갈렸을 가능성이 가장 크다 -- speeds[]는 index=distance 오름차순이므로
        # 마지막 후보들의 speed가 threshold에 얼마나 가까운지를 본다.
        if candidates:
            near_margin = min(abs(speeds[k] - road_limit_speed) for k in candidates
                               if abs(speeds[k] - road_limit_speed) <= 5.0) if any(
                abs(speeds[k] - road_limit_speed) <= 5.0 for k in candidates) else None
        else:
            near_margin = None
        # threshold 부근(비후보 쪽에서도) 점 전체를 훑어 가장 가까운 margin을 구함
        all_margins = [abs(s - road_limit_speed) for s in speeds]
        min_margin = min(all_margins) if all_margins else None
        if min_margin is not None and min_margin <= ROUND_MARGIN_KPH:
            reason = "A_rounding_boundary"
            detail = f"min|speed-road_limit|={min_margin:.4f}kph"
        else:
            reason = "B_other"
            detail = f"min|speed-road_limit|={min_margin:.4f}kph (>{ROUND_MARGIN_KPH})" if min_margin is not None else "no speeds"
    else:
        detail = f"cand diff={diff} (>1, count 자체가 크게 다름)"

    # [수정, 최초 초안 버그] 최초 초안은 "cluster_count/orphan_count가 로그와
    # 정확히 같아야만 A로 인정"했는데, 이는 틀린 전제였다 -- 경계에 있는
    # 후보 1개가 다른 후보들과 고립돼 있으면(singleton), 그 후보 자체가
    # orphan_count에 직접 반영되므로 candidate diff=1일 때 orphan_count도
    # 함께 ±1 움직이는 것이 오히려 정상이다. cluster_count가 바뀌는 경우도
    # 마찬가지(경계 후보가 인접 클러스터를 min_points=2로 밀어올리거나
    # 끌어내릴 수 있음). 따라서 cluster/orphan 일치 여부로 A/B를 가르지
    # 않고, "경계 후보 1개의 존재/부재만으로 후보 diff=1이 설명되는가"만
    # 본다(위 min_margin 판정). cluster/orphan 변화는 참고용으로만 기록.
    cluster_delta = cluster_count - logged_cluster
    orphan_delta = orphan_count - logged_orphan
    detail += f" | cluster_delta={cluster_delta} orphan_delta={orphan_delta}"

    return reason, detail, diff, off_cand, logged_cand, cluster_count, logged_cluster, orphan_count, logged_orphan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    args = ap.parse_args()

    counts = {"A_rounding_boundary": 0, "B_other": 0}
    b_examples = []

    with open(args.csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("naviPaths"):
                continue
            pts, _ = parse_navi_paths(row["naviPaths"])
            if not pts:
                continue
            road_limit_speed = float(row["nRoadLimitSpeed"]) if row["nRoadLimitSpeed"] else 300.0
            speeds, distances, candidates, cluster_count, orphan_count = recompute_full(pts, [], road_limit_speed)
            logged_cand = int(row["routeCandidateCount"]) if row["routeCandidateCount"] else 0
            logged_cluster = int(row["routeClusterCount"]) if row["routeClusterCount"] else 0
            logged_orphan = int(row["routeOrphanSingletonCount"]) if row["routeOrphanSingletonCount"] else 0
            if len(candidates) == logged_cand and cluster_count == logged_cluster and orphan_count == logged_orphan:
                continue  # match, skip

            reason, detail, diff, off_cand, lg_cand, off_cl, lg_cl, off_or, lg_or = classify(row)
            counts[reason] = counts.get(reason, 0) + 1
            if reason == "B_other":
                b_examples.append((row["t"], row["seg"], diff, off_cand, lg_cand, off_cl, lg_cl, off_or, lg_or, detail))

    total = sum(counts.values())
    print(f"총 mismatch: {total}")
    for k, v in counts.items():
        print(f"  {k}: {v} ({100*v/total:.1f}%)" if total else f"  {k}: {v}")

    print(f"\n--- B_other 상세({len(b_examples)}건) ---")
    for ex in b_examples:
        print("t=%s seg=%s cand(diff=%s off=%s logged=%s) cluster(off=%s logged=%s) orphan(off=%s logged=%s) | %s" % ex)


if __name__ == "__main__":
    main()
