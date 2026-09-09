#!/usr/bin/env python3
"""330차: route_local_curve_merge() (base 823943a6=329차 계속2, verbatim 추출)
경계조건 합성(synthetic) 검증 -- ChatGPT 329차 계속2 코드감사가 제안한 5개
카테고리(정상 mid-path / path 끝단(clamp) / ws<0 / orphan 다중 / window
겹침(merge))를 각각 폐루프로 실행해 출력 배열의 정합성(정렬/중복/gap/
ws<0 라벨링 불일치)을 확인한다.

이 스크립트는 실측 로그가 아닌 순수 합성 경로(사인곡선 polyline)를
사용한다 -- 목적은 "이 특정 도로에서 무엇이 일어나는가"가 아니라
"route_local_curve_merge()가 이 5개 경계조건 각각에서 구조적으로
올바른 배열을 만드는가"이다.

route_local_curve_merge()/route_curvature_macro_fine()/
route_crop_path_by_distance()/resample_10m_np()/calculate_curvature()/
route_find_clusters()는 carrot_man.py(base 823943a6)에서 verbatim
추출(§27, 로직 무변경 -- 위 함수들은 이 파일에서 재사용만 되고
곡률/속도 계산식은 원본과 완전히 동일하다).

사용: python3 sim_route_330_boundary_synthetic.py [--self-test]
(인자 없이 실행하면 --self-test와 동일)
"""
import argparse
import math

import numpy as np

# ---- carrot_man.py(base 823943a6=329차 계속2)에서 verbatim 추출 ----
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0

LOCAL_CURVE_DISTANCE_INTERVAL = 2.5
LOCAL_CURVE_MACRO_SAMPLE = 16
LOCAL_CURVE_FINE_SAMPLE = 4
LOCAL_CURVE_WINDOW_BACK_M = 40.0
LOCAL_CURVE_WINDOW_FWD_M = 40.0
LOCAL_CURVE_MACRO_CHORD_M = LOCAL_CURVE_MACRO_SAMPLE * LOCAL_CURVE_DISTANCE_INTERVAL * 2


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


def calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        curvature = 0
    else:
        curvature = cross_product / (len_v1 * len_v2 * len_v1)
    return curvature


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


def route_local_curve_merge(orphans, distances, speeds, curvatures,
                             fine_triggered, relative_coords,
                             map_turn_speed_factor, road_limit_speed):
    if not orphans:
        return distances, speeds, curvatures, fine_triggered, False
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

    out_d, out_s, out_c, out_ft = [], [], [], []
    for i, d in enumerate(distances):
        if not any(ws <= d <= we for ws, we in merged_windows):
            out_d.append(d)
            out_s.append(speeds[i])
            out_c.append(curvatures[i])
            out_ft.append(fine_triggered[i])

    local_used = False
    for ws, we in merged_windows:
        local_path = route_crop_path_by_distance(
            relative_coords, ws, we + LOCAL_CURVE_MACRO_CHORD_M)
        if len(local_path) < 2:
            for i, d in enumerate(distances):
                if ws <= d <= we:
                    out_d.append(d)
                    out_s.append(speeds[i])
                    out_c.append(curvatures[i])
                    out_ft.append(fine_triggered[i])
            continue
        local_resampled = resample_10m_np(local_path, LOCAL_CURVE_DISTANCE_INTERVAL)
        if len(local_resampled) < LOCAL_CURVE_MACRO_SAMPLE * 2 + 1:
            for i, d in enumerate(distances):
                if ws <= d <= we:
                    out_d.append(d)
                    out_s.append(speeds[i])
                    out_c.append(curvatures[i])
                    out_ft.append(fine_triggered[i])
            continue
        l_curv, l_dist, l_speed, l_ft = route_curvature_macro_fine(
            local_resampled, LOCAL_CURVE_DISTANCE_INTERVAL,
            LOCAL_CURVE_MACRO_SAMPLE, LOCAL_CURVE_FINE_SAMPLE, ws,
            map_turn_speed_factor, road_limit_speed)
        if not l_dist:
            for i, d in enumerate(distances):
                if ws <= d <= we:
                    out_d.append(d)
                    out_s.append(speeds[i])
                    out_c.append(curvatures[i])
                    out_ft.append(fine_triggered[i])
            continue
        out_d.extend(l_dist)
        out_s.extend(l_speed)
        out_c.extend(l_curv)
        out_ft.extend(l_ft)
        local_used = True

        covered_max = max(l_dist)
        if covered_max < we - 1e-6:
            for i, d in enumerate(distances):
                if covered_max < d <= we:
                    out_d.append(d)
                    out_s.append(speeds[i])
                    out_c.append(curvatures[i])
                    out_ft.append(fine_triggered[i])

    if not local_used:
        return distances, speeds, curvatures, fine_triggered, False

    order = sorted(range(len(out_d)), key=lambda i: out_d[i])
    merged_d = [out_d[i] for i in order]
    merged_s = [out_s[i] for i in order]
    merged_c = [out_c[i] for i in order]
    merged_ft = [out_ft[i] for i in order]
    return merged_d, merged_s, merged_c, merged_ft, True
# ---- verbatim 추출 끝 ----


def make_synthetic_path(total_len_m=600.0, amp=25.0, wavelength=140.0, step_m=1.0):
    """완만한 사인곡선 polyline(직선이 아닌, 곡률이 0이 아닌 합성 도로).
    실제 도로 형상과 무관 -- route_local_curve_merge()의 배열 정합성만
    검사하는 것이 목적이므로 임의 곡률로 충분하다."""
    n = int(total_len_m / step_m) + 1
    xs = np.arange(n) * step_m
    ys = amp * np.sin(2 * math.pi * xs / wavelength)
    return list(zip(xs.tolist(), ys.tolist()))


def build_10m_pass(relative_coords):
    resampled = resample_10m_np(relative_coords, 10.0)
    curv, dist, speed, ft = route_curvature_macro_fine(
        resampled, 10.0, sample=4, sample_fine=1, distance_offset=0.0,
        map_turn_speed_factor=1.0, road_limit_speed=110.0)
    return dist, speed, curv, ft


def check_integrity(label, out_d, we_hint=None):
    problems = []
    if len(out_d) < 2:
        problems.append("output too short (<2 points)")
        return problems
    arr = np.asarray(out_d, dtype=np.float64)
    diffs = np.diff(arr)
    n_dup = int(np.sum(np.abs(diffs) < 1e-6))
    n_unsorted = int(np.sum(diffs < -1e-6))
    max_gap = float(np.max(diffs)) if len(diffs) else 0.0
    n_gap_gt15 = int(np.sum(diffs > 15.0))
    n_negative = int(np.sum(arr < -1e-6))
    if n_dup:
        problems.append(f"duplicate distances: {n_dup}건")
    if n_unsorted:
        problems.append(f"unsorted (역행) 지점: {n_unsorted}건")
    if n_gap_gt15:
        problems.append(f"gap>15m: {n_gap_gt15}건 (max_gap={max_gap:.2f}m)")
    if n_negative:
        problems.append(f"음수 distance 라벨: {n_negative}건 (min={arr.min():.2f}m) -- ws<0 라벨링이 그대로 노출된 것")
    return problems


def run_case(name, relative_coords, orphan_center_distances, note=""):
    dist, speed, curv, ft = build_10m_pass(relative_coords)
    if not dist:
        print(f"[{name}] 10m pass 결과 없음 (path 너무 짧음) -- SKIP")
        return
    # orphan_center_distances에 가장 가까운 10m pass 인덱스를 orphan cluster로 지정
    orphans = []
    for c in orphan_center_distances:
        idx = int(np.argmin(np.abs(np.asarray(dist) - c)))
        orphans.append([idx])

    merged_d, merged_s, merged_c, merged_ft, local_used = route_local_curve_merge(
        orphans, dist, speed, curv, ft, relative_coords,
        map_turn_speed_factor=1.0, road_limit_speed=110.0)

    problems = check_integrity(name, merged_d)
    status = "PASS" if not problems else "ISSUE"
    print(f"[{name}] local_used={local_used} out_points={len(merged_d)} "
          f"d_range=[{merged_d[0]:.1f},{merged_d[-1]:.1f}] -> {status}")
    if note:
        print(f"    note: {note}")
    for p in problems:
        print(f"    - {p}")
    return problems


def self_test():
    print("=== 330차 route_local_curve_merge() 경계조건 합성 검증 ===")
    print("(base carrot_man.py 823943a6=329차 계속2, verbatim 추출)\n")

    all_problems = {}

    # 1) 정상 mid-path: orphan이 양쪽으로 충분한 여유(>200m)를 가진 위치
    path = make_synthetic_path(total_len_m=600.0)
    all_problems["1_normal_mid_path"] = run_case(
        "1_normal_mid_path", path, [300.0],
        note="path 길이 600m, orphan center=300m (양쪽 200m+ 여유)")

    # 2) path 끝단(clamp): orphan이 path 끝에서 15m 지점 -- we+MACRO_CHORD_M(=we+80)이
    #    total_len을 넘어 context가 clamp되고 tail_partial_restore가 발동해야 함
    path = make_synthetic_path(total_len_m=600.0)
    all_problems["2_path_end_clamp"] = run_case(
        "2_path_end_clamp", path, [585.0],
        note="orphan center=585m, path_len=600m -- we=625m > 600m, context clamp 필수 경로")

    # 3) ws<0: orphan이 path 시작점에서 15m 지점 -- ws=center-40 <0
    path = make_synthetic_path(total_len_m=600.0)
    all_problems["3_ws_negative"] = run_case(
        "3_ws_negative", path, [15.0],
        note="orphan center=15m -- ws=15-40=-25m<0, route_crop_path_by_distance()가 d_start를 0으로 clamp하지만 distance_offset=ws=-25는 그대로 curvature label에 쓰임")

    # 4) 다중 orphan(겹치지 않음): 두 orphan이 서로 멀리 떨어져 있어 window가 분리됨
    path = make_synthetic_path(total_len_m=600.0)
    all_problems["4_multi_orphan_separate"] = run_case(
        "4_multi_orphan_separate", path, [150.0, 400.0],
        note="orphan center=150m/400m -- window (110,190)/(360,440) 겹치지 않음")

    # 5) window 겹침(merge): 두 orphan이 가까이 있어 window가 병합됨
    path = make_synthetic_path(total_len_m=600.0)
    all_problems["5_overlapping_windows"] = run_case(
        "5_overlapping_windows", path, [280.0, 310.0],
        note="orphan center=280m/310m -- window (240,320)/(270,350) 겹침 -> (240,350) 단일 병합 window")

    print("\n=== 요약 ===")
    n_pass = sum(1 for v in all_problems.values() if not v)
    n_total = len(all_problems)
    for k, v in all_problems.items():
        print(f"  {k}: {'PASS' if not v else 'ISSUE(' + str(len(v)) + ')'}")
    print(f"\n{n_pass}/{n_total} PASS")
    return all_problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true",
                     help="5개 경계조건 합성 시나리오 실행 (인자 없이 실행해도 동일)")
    args = ap.parse_args()
    self_test()


if __name__ == "__main__":
    main()
