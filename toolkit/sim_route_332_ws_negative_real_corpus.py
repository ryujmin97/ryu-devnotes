#!/usr/bin/env python3
"""332차 STEP3: x18seg 실측 corpus(routeOrphanRawPath, base 823943a6)로
331차 STEP1/STEP2가 예측한 "ws<0 -> apex_dist 음수/시프트" 전파 경로가
실제 주행 데이터에서도 발생하는지 확인한다.

331차 WIP "다음 작업" 1번(STEP3)에 대한 응답. sim_route_329_local_merge_replay.py
(routeOrphanRawPath 재생 골격)와 sim_route_331_ws_negative_downstream.py
(route_local_curve_merge/route_find_clusters/continuity_new_entry/
active_gate_downstream, verbatim base 823943a6)를 그대로 재사용해 조립만
한다(§21, 새 로직 재구현 없음).

핵심 질문:
  1. 이 CSV의 3645개 orphan(raw_path 존재) 프레임 중 실제로 ws<0인
     프레임이 몇 건인가(=orphan cluster 중심이 ego로부터 40m 이내)?
  2. 그 프레임들에서 offline route_local_curve_merge 재생 결과 apex_dist가
     실제로 음수/비정상 시프트로 나오는가?
  3. 실측 텔레메트리(routeApexDist, routeApexMode)가 이미 로깅한 값과
     offline 재생값이 (mode=='new' 구간에서) 서로 일치하는가 -- 일치하면
     offline 재생 자체의 신뢰도가 검증되고, 이 corpus에서 실제로
     routeApexDist<0가 관측되지 않은 이유(WIP 331차 STEP3 착수 전 사전
     grep에서 0건 확인됨)를 offline 쪽에서 설명할 수 있는지 확인.

사용:
  python3 sim_route_332_ws_negative_real_corpus.py <CSV>
"""
import argparse
import csv
import sys

import numpy as np

from sim_route_331_ws_negative_downstream import (
    resample_10m_np, route_curvature_macro_fine, route_crop_path_by_distance,
    route_local_curve_merge, route_find_clusters, continuity_new_entry,
    active_gate_downstream,
    ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M,
    LOCAL_CURVE_WINDOW_BACK_M, LOCAL_CURVE_WINDOW_FWD_M,
)

MAP_TURN_SPEED_FACTOR = 1.10  # params_backup-1.json AutoCurveSpeedFactor=80 아님,
# MapTurnSpeedFactor=110(%) -- 324/329차와 동일하게 1.10 사용(§26, x17/x18seg 공통 상수)


def parse_raw_path(s):
    pts = []
    if not s:
        return pts
    for tok in s.split(';'):
        tok = tok.strip()
        if not tok or ',' not in tok:
            continue
        x, y = tok.split(',')
        pts.append((float(x), float(y)))
    return pts


def recompute_10m_pass(relative_coords, road_limit_speed):
    resampled = resample_10m_np(relative_coords, 10.0)
    curv, dist, speed, ft = route_curvature_macro_fine(
        resampled, 10.0, 4, 1, 0.0, MAP_TURN_SPEED_FACTOR, road_limit_speed)
    candidates = [k for k in range(len(speed)) if speed[k] < road_limit_speed]
    all_clusters = route_find_clusters(candidates, dist, 1, ROUTE_CLUSTER_MAX_GAP_M)
    clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
    orphans = [c for c in all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]
    return dist, speed, curv, ft, candidates, clusters, orphans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--limit-print", type=int, default=20)
    args = ap.parse_args()

    n_raw = 0
    n_10m_orphan_mismatch = 0
    n_10m_orphan_gt0 = 0
    n_ws_negative = 0
    n_ws_nonneg = 0
    ws_values_neg = []
    apex_dist_offline_at_ws_neg = []
    new_mode_compare = []  # (t, telemetry_apex_dist, offline_apex_dist, ws)
    active_gate_examples = []

    with open(args.csv, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            raw = row.get("routeOrphanRawPath", "")
            if not raw:
                continue
            n_raw += 1
            try:
                rls = float(row.get("nRoadLimitSpeed", "") or 0.0)
            except ValueError:
                rls = 0.0
            if rls <= 0:
                rls = 30.0
            relative_coords = parse_raw_path(raw)
            if len(relative_coords) < 2:
                continue

            dist, speed, curv, ft, candidates, clusters, orphans = recompute_10m_pass(
                relative_coords, rls)

            if not orphans:
                n_10m_orphan_mismatch += 1
                continue
            n_10m_orphan_gt0 += 1

            idx0 = orphans[0][0]
            ws = dist[idx0] - LOCAL_CURVE_WINDOW_BACK_M
            we = dist[idx0] + LOCAL_CURVE_WINDOW_FWD_M

            if ws < 0:
                n_ws_negative += 1
                ws_values_neg.append(ws)
            else:
                n_ws_nonneg += 1
                continue  # ws>=0 프레임은 이번 조사 범위 밖(331차가 이미 구조적으로 안전 확인)

            merged_d, merged_s, merged_c, merged_ft, local_used = route_local_curve_merge(
                orphans, dist, speed, curv, ft, relative_coords,
                map_turn_speed_factor=MAP_TURN_SPEED_FACTOR, road_limit_speed=rls,
                patch_ws_clamp=False)

            if not local_used:
                continue

            m_candidates = [k for k in range(len(merged_s)) if merged_s[k] < rls]
            m_all_clusters = route_find_clusters(m_candidates, merged_d, 1, ROUTE_CLUSTER_MAX_GAP_M)
            m_clusters = [c for c in m_all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
            apex_idx, apex_dist, apex_speed = continuity_new_entry(m_clusters, merged_d, merged_s)

            if apex_dist is not None:
                apex_dist_offline_at_ws_neg.append((row.get("t", "?"), ws, apex_dist, apex_speed,
                                                     row.get("routeApexMode", ""),
                                                     row.get("routeApexDist", "")))
                if row.get("routeApexMode", "") == "new":
                    try:
                        tel_apex = float(row.get("routeApexDist", "") or "nan")
                    except ValueError:
                        tel_apex = float("nan")
                    n_clusters_total = len(m_clusters)
                    cluster_dists = [merged_d[c[0]] for c in m_clusters[:5]]
                    new_mode_compare.append((row.get("t", "?"), tel_apex, apex_dist, ws,
                                              n_clusters_total, cluster_dists))

                if len(active_gate_examples) < args.limit_print:
                    v_ego_kph = 100.0
                    try:
                        v_ego_kph = float(row.get("vEgo", "") or 0.0) * 3.6
                        if v_ego_kph <= 0:
                            v_ego_kph = 100.0
                    except ValueError:
                        pass
                    v_ego_ms = v_ego_kph / 3.6
                    gate_active = active_gate_downstream(
                        apex_dist, apex_speed, v_ego_kph, v_ego_ms, 8.0, 0.90, True)
                    gate_inert = active_gate_downstream(
                        apex_dist, apex_speed, v_ego_kph, v_ego_ms, 8.0, 0.90, False)
                    active_gate_examples.append(
                        (row.get("t", "?"), ws, apex_dist, apex_speed,
                         gate_active["outcome"], gate_inert["outcome"]))

    print(f"=== 332차 STEP3: x18seg 실측 corpus ws<0 실제 발생/영향 확인 ===")
    print(f"raw_path 존재 행수: {n_raw}")
    print(f"  10m 1차패스 재계산 orphan==0(불일치): {n_10m_orphan_mismatch}")
    print(f"  10m 1차패스 재계산 orphan>0: {n_10m_orphan_gt0}")
    print(f"    ws>=0 (구조적으로 안전, 331차 확인분): {n_ws_nonneg}")
    print(f"    ws<0 (이번 조사 대상): {n_ws_negative}")
    if ws_values_neg:
        arr = np.array(ws_values_neg)
        print(f"      ws 분포: min={arr.min():.2f} median={np.median(arr):.2f} max={arr.max():.2f}")
    print(f"\n  ws<0 프레임 중 offline apex 산출 성공: {len(apex_dist_offline_at_ws_neg)}건")
    if apex_dist_offline_at_ws_neg:
        neg_apex = [x for x in apex_dist_offline_at_ws_neg if x[2] < 0]
        print(f"    -> offline apex_dist<0로 산출된 건수: {len(neg_apex)}"
              f" / {len(apex_dist_offline_at_ws_neg)}")
        print(f"    -> offline apex_dist==ws로 정확히 일치(라벨 그대로 노출)한 건수: "
              f"{sum(1 for x in apex_dist_offline_at_ws_neg if abs(x[2]-x[1])<1e-6)}")
        print(f"\n  샘플(t, ws, offline_apex_dist, offline_apex_speed, tel_mode, tel_apex_dist):")
        for x in apex_dist_offline_at_ws_neg[:args.limit_print]:
            print(f"    {x}")

    print(f"\n  routeApexMode=='new' 실측 vs offline 비교 (동일 프레임, "
          f"continuity_new_entry가 실제 stateful 'new' 진입과 같은 조건인지 검증):")
    print(f"    'new' 모드이면서 이번 회차 ws<0 후보에 걸린 행수: {len(new_mode_compare)}")
    for x in new_mode_compare[:args.limit_print]:
        t, tel, off, ws, n_cl, cl_dists = x
        diff = (off - tel) if (tel == tel and off is not None) else float("nan")
        print(f"    t={t} 실측apex={tel} offline_apex={off:.2f} ws={ws:.2f} diff={diff} "
              f"n_clusters={n_cl} cluster_dists(가까운순5개)={cl_dists}")

    print(f"\n  offline apex_dist<0 샘플(negative apex 실제 사례, 최대 {args.limit_print}건):")
    neg_samples = [x for x in apex_dist_offline_at_ws_neg if x[2] < 0][:args.limit_print]
    for x in neg_samples:
        print(f"    {x}")

    print(f"\n  ACTIVE/INERT 게이트 영향 샘플(ws<0 프레임, v_ego는 실측 vEgo 사용):")
    for x in active_gate_examples:
        t, ws, ad, asp, out_active, out_inert = x
        print(f"    t={t} ws={ws:.2f} apex_dist={ad:.2f} apex_speed={asp:.1f} "
              f"-> [ACTIVE중]{out_active} / [INERT]{out_inert}")


if __name__ == "__main__":
    main()
