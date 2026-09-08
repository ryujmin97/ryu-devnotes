#!/usr/bin/env python3
"""322차 1단계: 단일 프레임 production vs offline 재현 대조.

핵심 전제(carrot_man.py 1134/1145/1152/1705행 확인):
  carrot_navi_route()는 resample_10m_np() 결과(resampled_points,
  resampled_distances)를 그대로 return하고, carrot_serv.py::update_navi()가
  그 값을 coords_str로 직렬화해 cereal carrotMan.naviPaths에 발행한다.
  즉 로그의 naviPaths는 gps_to_relative_xy/resample_10m_np까지 이미 끝난
  "production이 실제로 candidate 계산에 사용한 바로 그 배열"이다.
  따라서 이 단계에서는 get_path_after_distance/gps_to_relative_xy/
  resample_10m_np를 재현할 필요가 없다 -- naviPaths를 입력으로 candidate/
  cluster/orphan 계산 블록(carrot_man.py 1160~1372행)만 그대로 재구현해
  로그된 routeCandidate*/routeClusterCount/routeOrphanSingletonCount와
  대조한다. (apex_mode/Dist/Speed는 프레임간 상태를 갖는
  _route_cluster_continuity_step()에 의존하므로 이 단계 범위 밖 -- 별도
  전체구간 순차 재생이 필요, 322차 2단계 예정)
"""
import argparse
import csv
import math

import numpy as np

V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
ROUTE_CURVATURE_FINE_SAMPLE = 1
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
MAP_TURN_SPEED_FACTOR = 1.10  # [322차] x17seg 단일 프레임 캘리브레이션으로 확정 -- PARAMS_REGISTRY.md에 등록된
                               # 1.30(201/210차 실측)은 이 corpus 캡처 시점 실제값과 다름(1.0~1.3 스윕 중
                               # 1.10만 candidate0/1 speed=5.5(logged) 정확히 재현). Params는 실행 중
                               # 언제든 사용자가 바꿀 수 있는 값이므로 서로 다른 캡처가 다른 값을 가질 수 있음 --
                               # 이 상수는 x17seg corpus 전용, 다른 route CSV에 그대로 재사용 금지.


def calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0
    return cross_product / (len_v1 * len_v2 * len_v1)


def route_find_clusters(idxs, distances, min_points, max_gap_m):
    if not idxs:
        return []
    clusters = []
    cur = [idxs[0]]
    for i in idxs[1:]:
        if distances[i] - distances[cur[-1]] <= max_gap_m:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_points]


def parse_navi_paths(s):
    pts = []
    dists = []
    for tok in s.split(';'):
        tok = tok.strip()
        if not tok:
            continue
        x, y, d = tok.split(',')
        pts.append((float(x), float(y)))
        dists.append(float(d))
    return pts, dists


def recompute(resampled_points, resampled_distances, road_limit_speed, map_turn_speed_factor=MAP_TURN_SPEED_FACTOR):
    """carrot_man.py 1160~1372행(candidate/cluster/orphan 블록)을 그대로 재구현."""
    sample = 4
    curvatures = []
    distances = []
    speeds = []
    fine_triggered = []

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

        macro_speeds_arr = np.interp(macro_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
        macro_speeds_arr = macro_speeds_arr * map_turn_speed_factor
        for i in range(len(curvatures)):
            speed = macro_speeds_arr[i]
            if macro_abs_curv[i] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                speed = max(speed, road_limit_speed)
            speeds.append(speed)

        fine_triggered = [False] * len(speeds)
        sample_fine = ROUTE_CURVATURE_FINE_SAMPLE
        if sample_fine and sample_fine < sample and len(resampled_points) >= sample_fine * 2 + 1:
            n_fine = min(len(distances), len(resampled_points) - sample_fine * 2)
            if n_fine > 0:
                fine_curvatures = []
                fine_abs_curv = []
                for i in range(n_fine):
                    p1, p2, p3 = resampled_points[i], resampled_points[i + sample_fine], resampled_points[i + sample_fine * 2]
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
                    if f_speed < speeds[j]:
                        speeds[j] = f_speed
                        curvatures[j] = f_curv
                        fine_triggered[j] = True

    candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed]
    cand0 = (-1, 0.0, 0.0)
    cand1 = (-1, 0.0, 0.0)
    cand2 = (-1, 0.0, 0.0)
    if len(candidates) >= 1:
        c = candidates[0]; cand0 = (c, distances[c], speeds[c])
    if len(candidates) >= 2:
        c = candidates[1]; cand1 = (c, distances[c], speeds[c])
    if len(candidates) >= 3:
        c = candidates[2]; cand2 = (c, distances[c], speeds[c])

    all_clusters = route_find_clusters(candidates, distances, 1, ROUTE_CLUSTER_MAX_GAP_M)
    clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
    orphans = [c for c in all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]

    return {
        "candidate_count": len(candidates),
        "candidate0": cand0, "candidate1": cand1, "candidate2": cand2,
        "cluster_count": len(clusters),
        "orphan_count": len(orphans),
        "orphan0_dist": distances[orphans[0][0]] if orphans else 0.0,
        "orphan0_speed": speeds[orphans[0][0]] if orphans else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--t", type=float, help="특정 t(초) 프레임만 대조. 미지정시 전체 스캔")
    ap.add_argument("--limit", type=int, default=0, help="전체 스캔시 처음 N개 불일치만 출력(0=전부)")
    args = ap.parse_args()

    total = 0
    checked = 0
    mismatches = []

    with open(args.csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("naviPaths"):
                continue
            if args.t is not None and abs(float(row["t"]) - args.t) > 0.001:
                continue
            total += 1
            pts, dists = parse_navi_paths(row["naviPaths"])
            if not pts:
                continue
            road_limit_speed = float(row["nRoadLimitSpeed"]) if row["nRoadLimitSpeed"] else 300.0
            result = recompute(pts, dists, road_limit_speed)
            checked += 1

            logged_cand_count = int(row["routeCandidateCount"]) if row["routeCandidateCount"] else 0
            logged_cluster_count = int(row["routeClusterCount"]) if row["routeClusterCount"] else 0
            logged_orphan_count = int(row["routeOrphanSingletonCount"]) if row["routeOrphanSingletonCount"] else 0

            ok_cand = (result["candidate_count"] == logged_cand_count)
            ok_cluster = (result["cluster_count"] == logged_cluster_count)
            ok_orphan = (result["orphan_count"] == logged_orphan_count)

            if not (ok_cand and ok_cluster and ok_orphan):
                mismatches.append((row["t"], row["seg"], logged_cand_count, result["candidate_count"],
                                    logged_cluster_count, result["cluster_count"],
                                    logged_orphan_count, result["orphan_count"]))

            if args.t is not None:
                print(f"t={row['t']} seg={row['seg']}")
                print(f"  naviPaths points: {len(pts)}  road_limit_speed(nRoadLimitSpeed)={road_limit_speed}")
                print(f"  candidate_count  logged={logged_cand_count:4d}  offline={result['candidate_count']:4d}  {'OK' if ok_cand else 'MISMATCH'}")
                print(f"  cluster_count    logged={logged_cluster_count:4d}  offline={result['cluster_count']:4d}  {'OK' if ok_cluster else 'MISMATCH'}")
                print(f"  orphan_count     logged={logged_orphan_count:4d}  offline={result['orphan_count']:4d}  {'OK' if ok_orphan else 'MISMATCH'}")
                for i, name in enumerate(["candidate0", "candidate1", "candidate2"]):
                    logged = (int(row[f"route{name.capitalize()}Idx"]) if row[f"route{name.capitalize()}Idx"] else -1,
                              float(row[f"route{name.capitalize()}Dist"]) if row[f"route{name.capitalize()}Dist"] else 0.0,
                              float(row[f"route{name.capitalize()}Speed"]) if row[f"route{name.capitalize()}Speed"] else 0.0)
                    off = result[name]
                    print(f"  {name}: logged idx/dist/speed={logged}  offline={off}")

    print(f"\n--- scan summary: total_frames_with_naviPaths={total} checked={checked} mismatches={len(mismatches)} ---")
    lim = len(mismatches) if args.limit == 0 else args.limit
    for m in mismatches[:lim]:
        print("MISMATCH t=%s seg=%s cand(logged=%s,off=%s) cluster(logged=%s,off=%s) orphan(logged=%s,off=%s)" % m)


if __name__ == "__main__":
    main()
