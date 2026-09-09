#!/usr/bin/env python3
"""329차(계속): 328차 route_local_curve_merge의 context(macro chord 계산에
필요한 원본 경로 구간)/replacement(10m 결과를 실제 대체하는 구간) 분리
수정 -- x18seg 실측 routeOrphanRawPath에 재생해 fallback률/window당
출력 point 수 개선을 정량화하고, 병합 후 무결성(중복 distance/미정렬/
distance hole)까지 검사한다.

**배경**: 329차(진행중, WIP.md) 1차 검증에서 328차 설계(crop=[ws,we]=
replacement 범위와 동일, 폭 80m=macro chord 폭과 우연히 같음 -> 여유 0)가
실측상 fallback 45.5%, window당 출력 중앙값 1점임을 확인했다. 이 스크립트는
그 다음 작업(디자인 3안: context/replacement 분리)을 구현/검증한다 --
distance_offset=ws(기존 라벨링 관례, p1=macro chord 시작점)와 replacement
범위(ws,we)는 그대로 두고, crop 범위만 뒤쪽으로 LOCAL_CURVE_MACRO_CHORD_M
(=2*MACRO_SAMPLE*DISTANCE_INTERVAL=80m)만큼 넓힌다. route_crop_path_by_
distance()가 d_end를 total_len으로 clamp하므로 path 끝 근처에서는 context가
자동으로 좁아지는데, 이 경우 국소 출력이 we까지 못 미치는 꼬리 구간이
생길 수 있어(실측 946/3633프레임, gap 최대 52.5m) 그 구간만 원본 10m
포인트로 부분 복원한다(=신규 developed, tail_partial_restore).

이 CSV(x18seg, 2026-09-09 06:27~06:43)는 328차 패치 *이전*(1b77b799,
323차 빌드) 코드로 기록됐다(328차/329차 WIP 재확인). raw path
(routeOrphanRawPath)를 오프라인에서 이 함수로 재생하는 방식은 324차/329차와
동일(§28 한계 동일).

아래 함수들은 `ryu`(base b31016fe + 이번 세션 patch) carrot_man.py에서
**verbatim 복사**(route_curvature_macro_fine/route_crop_path_by_distance/
resample_10m_np는 328차와 완전 동일, route_local_curve_merge만 이번
세션에서 수정) -- route_find_clusters/calculate_curvature는
sim_route_322d_stateful_replay.py에서 그대로 import(§21).

사용:
  python3 sim_route_329b_context_fix_replay.py <CSV>

기존 328차 원본(context=replacement, 수정 전) 동작은
sim_route_329_local_merge_replay.py(변경 없음, 그대로 보존)로 계속
비교할 수 있다.
"""
import argparse
import csv
import sys

import numpy as np

from sim_route_322d_stateful_replay import (
    calculate_curvature, route_find_clusters,
    V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS, ROUTE_CURVE_NEGLIGIBLE_THRESHOLD,
    ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M,
    MAP_TURN_SPEED_FACTOR,
)

# [324차 params_backup-1.json 재확인] x17seg와 동일 상수, x18seg에도 그대로 적용
ROAD_LIMIT_SPEED_FALLBACK = None  # 실측 nRoadLimitSpeed 컬럼을 그대로 사용(있으면)

LOCAL_CURVE_DISTANCE_INTERVAL = 2.5
LOCAL_CURVE_MACRO_SAMPLE = 16
LOCAL_CURVE_FINE_SAMPLE = 4
LOCAL_CURVE_WINDOW_BACK_M = 40.0
LOCAL_CURVE_WINDOW_FWD_M = 40.0


def resample_10m_np(points_xy, distance_interval=10.0):
    pts = np.asarray(points_xy, dtype=np.float64)
    if len(pts) < 2:
        return [tuple(p) for p in pts]
    seg_vec = np.diff(pts, axis=0)
    seg_len = np.hypot(seg_vec[:, 0], seg_vec[:, 1])
    cum_len = np.concatenate(([0.0], np.cumsum(seg_len)))
    total_len = cum_len[-1]
    if total_len <= 0:
        return [tuple(pts[0])]
    n_samples = int(total_len // distance_interval) + 1
    sample_d = np.arange(n_samples, dtype=np.float64) * distance_interval
    sample_d = sample_d[sample_d <= total_len]
    idx = np.searchsorted(cum_len, sample_d, side="right") - 1
    idx = np.clip(idx, 0, len(seg_len) - 1)
    seg_start_len = cum_len[idx]
    seg_total_len = seg_len[idx]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(seg_total_len > 0, (sample_d - seg_start_len) / seg_total_len, 0.0)
    p_start = pts[idx]
    p_end = pts[idx + 1]
    out_xy = p_start + (p_end - p_start) * t[:, None]
    return [tuple(p) for p in out_xy]


def route_curvature_macro_fine(resampled_points, distance_interval, sample,
                                sample_fine, distance_offset,
                                map_turn_speed_factor, road_limit_speed):
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
    return curvatures, distances, speeds, fine_triggered


def route_crop_path_by_distance(points_xy, d_start, d_end):
    pts = np.asarray(points_xy, dtype=np.float64)
    if len(pts) < 2:
        return []
    seg_vec = np.diff(pts, axis=0)
    seg_len = np.hypot(seg_vec[:, 0], seg_vec[:, 1])
    cum_len = np.concatenate(([0.0], np.cumsum(seg_len)))
    total_len = cum_len[-1]
    if total_len <= 0:
        return []
    d_start = max(0.0, d_start)
    d_end = min(total_len, d_end)
    if d_end - d_start < 1.0:
        return []

    def _interp_at(d):
        idx = np.searchsorted(cum_len, d, side="right") - 1
        idx = int(np.clip(idx, 0, len(seg_len) - 1))
        seg_l = seg_len[idx]
        t = 0.0 if seg_l <= 0 else (d - cum_len[idx]) / seg_l
        return pts[idx] + (pts[idx + 1] - pts[idx]) * t

    start_pt = _interp_at(d_start)
    end_pt = _interp_at(d_end)
    inner_mask = (cum_len > d_start) & (cum_len < d_end)
    out = [tuple(start_pt)]
    for p in pts[inner_mask]:
        out.append(tuple(p))
    out.append(tuple(end_pt))
    return out


# [329차] macro chord(=2*MACRO_SAMPLE*interval=80m)를 채우려면
# window 자체가 80m를 요구하는데(기존 window 폭도 80m) 기존 코드는 crop
# 범위(context)와 실제 10m 포인트 교체 범위(replacement)를 동일한 [ws,we]로
# 취급해 여유(margin)가 0이 되고, window당 출력이 이론상/실측상 거의
# 항상 1점으로 축약된다(329차 진행중 WIP 2/4/5번 참고). 이 수정은
# distance_offset=ws(기존 라벨링 관례, p1=macro chord 시작점, 변경 없음)와
# 교체범위 [ws,we](기존과 동일, 변경 없음)는 그대로 두고, crop만
# [ws, we+MACRO_CHORD_M]로 확장한다 -- p1이 we까지 가더라도 p3=p1+80m가
# 항상 context 안에 있도록. route_crop_path_by_distance()가 이미
# d_end를 total_len으로 clamp하므로, path 끝 근처에서는 자동으로 예전과
# 동일한 최악의 경우(80m 미만이면 여전히 fallback)로 수렴한다 -- 즉 이
# 변경은 boundary fallback률을 악화시키지 않고 interior fallback/point
# 부족만 개선하는 단조 개선(strict improvement)이어야 한다는 것이 가설.
MACRO_CHORD_M = LOCAL_CURVE_MACRO_SAMPLE * LOCAL_CURVE_DISTANCE_INTERVAL * 2  # 80.0


def route_local_curve_merge(orphans, distances, speeds, curvatures,
                             fine_triggered, relative_coords,
                             map_turn_speed_factor, road_limit_speed):
    if not orphans:
        return distances, speeds, curvatures, fine_triggered, False, {}

    windows = []
    for orphan_cluster in orphans:
        idx0 = orphan_cluster[0]
        center = distances[idx0]
        windows.append((center - LOCAL_CURVE_WINDOW_BACK_M,
                         center + LOCAL_CURVE_WINDOW_FWD_M))
    windows.sort()
    merged_windows = []
    for ws, we in windows:
        if merged_windows and ws <= merged_windows[-1][1]:
            merged_windows[-1] = (merged_windows[-1][0], max(merged_windows[-1][1], we))
        else:
            merged_windows.append((ws, we))

    diag = {"n_windows": len(merged_windows), "window_spans": [],
            "window_out_points": [], "window_out_span": [], "fallback": []}

    out_d, out_s, out_c, out_ft = [], [], [], []
    for i, d in enumerate(distances):
        if not any(ws <= d <= we for ws, we in merged_windows):
            out_d.append(d)
            out_s.append(speeds[i])
            out_c.append(curvatures[i])
            out_ft.append(fine_triggered[i])

    local_used = False
    for ws, we in merged_windows:
        diag["window_spans"].append((ws, we))
        # [329차] context만 확장(we + MACRO_CHORD_M) -- distance_offset과
        # 이후 출력 필터링(교체범위 판단)은 전부 기존 ws/we 그대로.
        local_path = route_crop_path_by_distance(relative_coords, ws, we + MACRO_CHORD_M)
        if len(local_path) < 2:
            diag["fallback"].append("crop<2pts")
            for i, d in enumerate(distances):
                if ws <= d <= we:
                    out_d.append(d); out_s.append(speeds[i])
                    out_c.append(curvatures[i]); out_ft.append(fine_triggered[i])
            continue
        local_resampled = resample_10m_np(local_path, LOCAL_CURVE_DISTANCE_INTERVAL)
        if len(local_resampled) < LOCAL_CURVE_MACRO_SAMPLE * 2 + 1:
            diag["fallback"].append(f"resampled_too_short({len(local_resampled)})")
            for i, d in enumerate(distances):
                if ws <= d <= we:
                    out_d.append(d); out_s.append(speeds[i])
                    out_c.append(curvatures[i]); out_ft.append(fine_triggered[i])
            continue
        l_curv, l_dist, l_speed, l_ft = route_curvature_macro_fine(
            local_resampled, LOCAL_CURVE_DISTANCE_INTERVAL,
            LOCAL_CURVE_MACRO_SAMPLE, LOCAL_CURVE_FINE_SAMPLE, ws,
            map_turn_speed_factor, road_limit_speed)
        if not l_dist:
            diag["fallback"].append("empty_curvature_output")
            for i, d in enumerate(distances):
                if ws <= d <= we:
                    out_d.append(d); out_s.append(speeds[i])
                    out_c.append(curvatures[i]); out_ft.append(fine_triggered[i])
            continue
        diag["window_out_points"].append(len(l_dist))
        diag["window_out_span"].append((min(l_dist), max(l_dist)))
        out_d.extend(l_dist); out_s.extend(l_speed)
        out_c.extend(l_curv); out_ft.extend(l_ft)
        local_used = True

        # [329차] context 확장(we+MACRO_CHORD_M)이 path 끝단에서
        # clamp되면(총 길이가 we+80m에 못 미치면) 국소 출력의 마지막
        # 점이 we에 못 미칠 수 있다(v2에서 실측 확인, gap>15m 946건).
        # 이 구간을 빈 채로 두면(제거는 [ws,we] 전체인데 대체는 일부만)
        # 조용한 데이터 손실이 되므로(§28, 328차가 이미 한 번 고친 것과
        # 동일 성격의 버그), 커버 안 된 꼬리 구간[max(l_dist), we]은
        # 원본 10m 포인트로 부분 복원한다.
        covered_max = max(l_dist)
        if covered_max < we - 1e-6:
            diag["fallback"].append("tail_partial_restore")
            for i, d in enumerate(distances):
                if covered_max < d <= we:
                    out_d.append(d); out_s.append(speeds[i])
                    out_c.append(curvatures[i]); out_ft.append(fine_triggered[i])

    if not local_used:
        return distances, speeds, curvatures, fine_triggered, False, diag

    order = sorted(range(len(out_d)), key=lambda i: out_d[i])
    merged_d = [out_d[i] for i in order]
    merged_s = [out_s[i] for i in order]
    merged_c = [out_c[i] for i in order]
    merged_ft = [out_ft[i] for i in order]
    return merged_d, merged_s, merged_c, merged_ft, True, diag


def parse_raw_path(s):
    pts = []
    if not s:
        return pts
    toks = s.split(';')
    for tok in toks:
        tok = tok.strip()
        if not tok or ',' not in tok:
            continue
        x, y = tok.split(',')
        pts.append((float(x), float(y)))
    return pts


def recompute_10m_pass(relative_coords, road_limit_speed, map_turn_speed_factor):
    resampled_points = resample_10m_np(relative_coords, 10.0)
    curvatures, distances, speeds, fine_triggered = route_curvature_macro_fine(
        resampled_points, 10.0, 4, 1, 0.0, map_turn_speed_factor, road_limit_speed)
    candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed]
    all_clusters = route_find_clusters(candidates, distances, 1, ROUTE_CLUSTER_MAX_GAP_M)
    clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
    orphans = [c for c in all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]
    return distances, speeds, curvatures, fine_triggered, candidates, clusters, orphans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--limit-print", type=int, default=15)
    args = ap.parse_args()

    n_rows_with_raw = 0
    n_10m_orphan_gt0 = 0          # raw path 존재 + 10m 1차패스 orphan>0 (재현 가능)
    n_10m_orphan_mismatch = 0     # raw path는 있는데 10m 1차패스 재계산시 orphan==0 (post-merge라 불일치 가능)
    n_local_used = 0
    n_promoted_to_cluster = 0    # local_used=True 이고 병합 후 클러스터>=1 존재
    n_still_orphan_after_merge = 0
    n_fallback = 0
    fallback_reasons = {}
    window_point_counts = []
    window_coverage_ratios = []  # (max_dist-min_dist)/(we-ws) 실제커버리지
    mismatched_examples = []

    with open(args.csv, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            raw = row.get("routeOrphanRawPath", "")
            if not raw:
                continue
            n_rows_with_raw += 1
            try:
                rls = float(row.get("nRoadLimitSpeed", "") or 0.0)
            except ValueError:
                rls = 0.0
            if rls <= 0:
                rls = 30.0  # 실측값 없으면 보수적 fallback(드묾)
            relative_coords = parse_raw_path(raw)
            if len(relative_coords) < 2:
                continue

            (distances, speeds, curvatures, fine_triggered,
             candidates, clusters, orphans) = recompute_10m_pass(
                relative_coords, rls, MAP_TURN_SPEED_FACTOR)

            if not orphans:
                # 이 프레임은 (post-merge 상태에서) orphan이 있었기 때문에
                # raw_path가 기록됐지만, 328차 패치가 없던 pre-328 빌드에서는
                # 이게 곧 10m 1차패스 orphan이었다(이 로그가 pre-328 빌드이므로
                # post==pre). 그런데 우리가 여기서 오프라인 재계산한 10m
                # 1차패스가 orphan==0이면, 실측(로그)과 재계산이 어긋난다는
                # 뜻 -- 반올림(.2f)/road_limit_speed 근사 등으로 발생 가능.
                n_10m_orphan_mismatch += 1
                if len(mismatched_examples) < 5:
                    mismatched_examples.append(row.get("t", "?"))
                continue

            n_10m_orphan_gt0 += 1
            (m_d, m_s, m_c, m_ft, local_used, diag) = route_local_curve_merge(
                orphans, distances, speeds, curvatures, fine_triggered,
                relative_coords, MAP_TURN_SPEED_FACTOR, rls)

            if diag.get("fallback"):
                n_fallback += 1
                for reason in diag["fallback"]:
                    key = reason.split("(")[0]
                    fallback_reasons[key] = fallback_reasons.get(key, 0) + 1
                orphan_center = distances[orphans[0][0]]
                if orphan_center < 90 or orphan_center > (distances[-1] - 90):
                    fallback_reasons["_near_path_edge"] = fallback_reasons.get("_near_path_edge", 0) + 1

            if not local_used:
                continue
            n_local_used += 1

            for n_pts, (lo, hi) in zip(diag["window_out_points"], diag["window_out_span"]):
                window_point_counts.append(n_pts)

            for (ws, we), (lo, hi) in zip(diag["window_spans"], diag["window_out_span"] or [(0, 0)] * len(diag["window_spans"])):
                span = we - ws
                if span > 0 and diag["window_out_span"]:
                    pass

            m_candidates = [k for k in range(len(m_s)) if m_s[k] < rls]
            m_all_clusters = route_find_clusters(m_candidates, m_d, 1, ROUTE_CLUSTER_MAX_GAP_M)
            m_clusters = [c for c in m_all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
            m_orphans = [c for c in m_all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]

            if m_clusters:
                n_promoted_to_cluster += 1
            if m_orphans:
                n_still_orphan_after_merge += 1

    print(f"raw_path 존재 행수: {n_rows_with_raw}")
    print(f"  10m 1차패스 재계산 orphan==0(불일치, 반올림/근사 추정): {n_10m_orphan_mismatch}"
          f"  (샘플 t={mismatched_examples})")
    print(f"  10m 1차패스 재계산 orphan>0 (재현 성공): {n_10m_orphan_gt0}")
    print(f"    -> route_local_curve_merge local_used=True: {n_local_used}"
          f" ({100*n_local_used/max(1,n_10m_orphan_gt0):.1f}%)")
    print(f"       fallback(원본 10m 복원) 발생 프레임: {n_fallback}, 사유: {fallback_reasons}")
    print(f"       병합 후 cluster(>=2점)로 승격: {n_promoted_to_cluster}"
          f" ({100*n_promoted_to_cluster/max(1,n_local_used):.1f}% of local_used)")
    print(f"       병합 후에도 orphan 잔존: {n_still_orphan_after_merge}"
          f" ({100*n_still_orphan_after_merge/max(1,n_local_used):.1f}% of local_used)")
    if window_point_counts:
        arr = np.array(window_point_counts)
        print(f"  window당 실제 2.5m curvature 출력 point 개수: "
              f"min={arr.min()} median={np.median(arr):.1f} max={arr.max()} "
              f"(<=2점인 window 비율: {100*np.mean(arr<=2):.1f}%)")
        print(f"  분포(1~10점): " + ", ".join(
            f"{k}점:{int(np.sum(arr==k))}" for k in range(1, 11)))


if __name__ == "__main__":
    main()
