#!/usr/bin/env python3
"""331차: sim_route_330_boundary_synthetic.py 확장 -- ws<0 라벨이
candidates/clusters/apex(_route_cluster_continuity_step 'new' 진입)/
ACTIVE-INERT 게이트(1655~1776행)까지 실제로 어떤 값을 만드는지 A(현재
823943a6, distance_offset=ws)와 B(가상 패치, distance_offset=max(0,ws))
두 경로로 A/B 비교한다. 지선생 331차 제안(WIP.md 330차 "다음 작업" 1번,
"수정 전에 실제 제어경로 영향부터 증명")에 대한 응답.

포함된 3개 실행 모드:
  --self-test              : 330차 원본 5개 경계조건 검증(변경 없음, 회귀 방지용)
  --downstream             : 330차 3번 케이스(orphan center 5~39m, 전구간
                              곡률 사인곡선)를 그대로 확장 -- apex_idx가 항상
                              재계산 window 좌단(=ws 그 자체)으로 나옴을
                              확인(candidates가 window 전체에 걸쳐 존재하는
                              synthetic 특성상 자연스러운 결과). 결과: apex_dist
                              == ws(A) / == max(0,ws)=0(B)가 그대로 검증됨 --
                              이 값이 eff_dist=max(0,apex_dist-...) 클램프와
                              dist_reached(<=20m) 판정에 직접 들어가는 것도
                              동일 스크립트로 확인.
  --downstream-localized    : [미완성, 참고용] 국소 curve(window 내부 임의
                              위치에 진짜 진입점)로 위 결과를 재현하려는
                              1차 시도 -- 이번 세션 파라미터(sigma=3,
                              wavelength=30)는 10m macro sample 간격(40m)
                              대비 파장이 짧아 aliasing으로 실제 도로와
                              무관한 급격한 curvature가 나옴(§28 미검증
                              상태로 결론 내리지 않음). 다음 세션 과제로
                              이월 -- 파라미터 재설계 또는 실측 x18seg
                              corpus 대체 권장(STEP3).

route_local_curve_merge()/route_curvature_macro_fine()/
route_crop_path_by_distance()/resample_10m_np()/calculate_curvature()/
route_find_clusters()는 carrot_man.py(base 823943a6)에서 verbatim
추출(§27, 로직 무변경). route_local_curve_merge()에만 이번 세션
patch_ws_clamp 파라미터를 추가했다(기본 False=현재 프로덕션과 동일
동작, True일 때만 A/B 비교용 가상 패치 경로 -- 이 파일 밖 production
코드는 무변경).

사용: python3 sim_route_331_ws_negative_downstream.py [--self-test|--downstream|--downstream-localized]
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
                             map_turn_speed_factor, road_limit_speed,
                             patch_ws_clamp=False):
    # patch_ws_clamp=True: 331차 STEP2 A/B 비교용 가상 패치 -- 지선생
    # 331차 제안대로 "0으로 고치는 게 정답"이라 단정하지 않고, 비교
    # 대상 중 하나로만 사용(§27 -- 이 스크립트 밖 production 코드는
    # 무변경, 검증 전용).
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
        _distance_offset = max(0.0, ws) if patch_ws_clamp else ws
        l_curv, l_dist, l_speed, l_ft = route_curvature_macro_fine(
            local_resampled, LOCAL_CURVE_DISTANCE_INTERVAL,
            LOCAL_CURVE_MACRO_SAMPLE, LOCAL_CURVE_FINE_SAMPLE, _distance_offset,
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


ROUTE_RELEASE_DIST_M = 20.0


def continuity_new_entry(clusters, distances, speeds):
    """_route_cluster_continuity_step()의 'new' 진입(신규/최초 lock)
    분기만 verbatim 재현 -- 이번 331차 STEP2는 세션 상태(held/matched)가
    아니라 '이번 프레임 처음 이 apex가 잡혔을 때 apex_dist가 무엇인가'만
    확인하면 되므로 stateful 전체 이식 대신 이 분기만으로 충분(§27,
    범위 최소화)."""
    if not clusters:
        return -1, None, None
    idx = clusters[0][0]
    return idx, distances[idx], speeds[idx]


def active_gate_downstream(apex_dist, apex_speed, v_ego_kph, v_ego_ms,
                            auto_navi_speed_ctrl_end, auto_navi_speed_decel_rate,
                            route_active):
    """1655~1776행(ACTIVE/INERT 게이트)을 apex_confidence=1.0(단순화, streak
    영향 배제 -- 이번 STEP2 목적은 confidence blend가 아니라 apex_dist
    부호 자체의 영향)으로 verbatim 재현."""
    target_ms = apex_speed / 3.6
    eff_dist = max(0.0, apex_dist - target_ms * auto_navi_speed_ctrl_end)
    result = {"apex_dist": apex_dist, "eff_dist": eff_dist, "target_ms": target_ms}
    if route_active:
        speed_reached = v_ego_kph <= apex_speed * 1.05
        dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
        result["speed_reached"] = speed_reached
        result["dist_reached"] = dist_reached
        if speed_reached or dist_reached:
            result["outcome"] = "RELEASE"
        else:
            result["outcome"] = "ACTIVE_decel_continue"
    else:
        if v_ego_ms <= target_ms:
            result["outcome"] = "INERT_hold(target_already_met)"
        elif eff_dist <= 0:
            result["outcome"] = "INERT_hold(eff_dist<=0_224cha_pass_through)"
        else:
            required_decel_mss = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            result["required_decel_mss"] = required_decel_mss
            if required_decel_mss >= auto_navi_speed_decel_rate:
                result["outcome"] = "ACTIVE_ENTER"
            else:
                result["outcome"] = "INERT_hold(gate_not_met)"
    return result


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


def make_localized_curve_path(curve_center=30.0, curve_sigma=12.0, amp=25.0,
                               wavelength=60.0, total_len_m=600.0, step_m=1.0):
    """330차 self_test의 전구간 사인곡선과 달리, curve_center 주변에만
    곡률이 몰린 국소 커브(가우시안 envelope) + 나머지는 거의 직선.
    목적: apex_idx=0이 'window 시작점'이 아니라 '실제 커브 진입점'이
    되도록 만들어 ws<0 라벨 시프트의 실제 크기를 분리 관찰하기 위함
    (330차/STEP2 1차 실행에서 사인곡선 전구간 곡률 때문에 apex가 항상
    window 좌단으로 나와 ws<0의 순수 크기(=|ws|)만 그대로 노출됐음 --
    실제 도로에서는 커브 진입점이 window 내부 임의 위치에 있으므로 이
    쪽이 더 현실적)."""
    n = int(total_len_m / step_m) + 1
    xs = np.arange(n) * step_m
    envelope = np.exp(-0.5 * ((xs - curve_center) / curve_sigma) ** 2)
    ys = amp * np.sin(2 * math.pi * xs / wavelength) * envelope
    return list(zip(xs.tolist(), ys.tolist()))


def run_downstream_comparison(orphan_center, road_limit_speed=110.0,
                               v_ego_kph=100.0,
                               auto_navi_speed_ctrl_end=8.0,
                               auto_navi_speed_decel_rate=0.90,
                               route_active_test=True):
    """331차 STEP2 -- ws<0 라벨이 candidates/clusters/apex/ACTIVE 게이트에
    실제로 어떤 값을 만드는지 A(현재 823943a6, distance_offset=ws)와
    B(가상 패치, distance_offset=max(0,ws)) 두 경로로 나란히 계산."""
    path = make_synthetic_path(total_len_m=600.0)
    dist, speed, curv, ft = build_10m_pass(path)
    idx0 = int(np.argmin(np.abs(np.asarray(dist) - orphan_center)))
    orphans = [[idx0]]
    v_ego_ms = v_ego_kph / 3.6

    print(f"\n=== downstream 비교: orphan_center={orphan_center}m, "
          f"road_limit_speed={road_limit_speed}, v_ego={v_ego_kph}kph ===")
    for label, patch in (("A(현재,823943a6)", False), ("B(가상패치,max(0,ws))", True)):
        merged_d, merged_s, merged_c, merged_ft, local_used = route_local_curve_merge(
            orphans, dist, speed, curv, ft, path,
            map_turn_speed_factor=1.0, road_limit_speed=road_limit_speed,
            patch_ws_clamp=patch)
        candidates = [k for k in range(len(merged_s)) if merged_s[k] < road_limit_speed]
        all_clusters = route_find_clusters(candidates, merged_d, 1, ROUTE_CLUSTER_MAX_GAP_M)
        clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
        orphans_out = [c for c in all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]
        apex_idx, apex_dist, apex_speed = continuity_new_entry(clusters, merged_d, merged_s)
        print(f"  [{label}] local_used={local_used} candidates={len(candidates)} "
              f"clusters={len(clusters)} orphans={len(orphans_out)} "
              f"apex_idx={apex_idx} apex_dist={apex_dist} apex_speed={apex_speed}")
        if apex_dist is None:
            print("      -> apex 없음(직선), 게이트 비교 불가")
            continue
        for ra in ([True, False] if route_active_test is None else [route_active_test]):
            gate = active_gate_downstream(
                apex_dist, apex_speed, v_ego_kph, v_ego_ms,
                auto_navi_speed_ctrl_end, auto_navi_speed_decel_rate, ra)
            state = "ACTIVE중" if ra else "INERT(미진입)"
            print(f"      [{state}] eff_dist={gate['eff_dist']:.2f} -> outcome={gate['outcome']}"
                  + (f" (dist_reached={gate.get('dist_reached')}, speed_reached={gate.get('speed_reached')})"
                     if ra else
                     (f" (required_decel={gate.get('required_decel_mss'):.3f})" if 'required_decel_mss' in gate else "")))


def run_localized_case(curve_center, road_limit_speed=110.0, v_ego_kph=100.0,
                        auto_navi_speed_ctrl_end=8.0,
                        auto_navi_speed_decel_rate=0.90,
                        curve_sigma=3.0, amp=40.0, wavelength=30.0):
    """국소 커브(curve_center 실제 진입점)를 ego에서 가까운 거리에
    배치해 ws<0가 유발되는 실제 상황을 재현하고, apex_dist가 실제
    커브 위치(진짜 물리적 거리)와 얼마나 어긋나는지 A/B로 비교."""
    path = make_localized_curve_path(curve_center=curve_center, curve_sigma=curve_sigma,
                                      amp=amp, wavelength=wavelength)
    dist, speed, curv, ft = build_10m_pass(path)
    # 10m 1차 패스에서 실제로 road_limit_speed 미만인(=감속 필요) 첫
    # 지점을 찾는다 -- 이것이 "실제 물리적 커브 진입 거리"의 10m-grid
    # 근사치(ground truth 역할).
    cand10 = [k for k in range(len(speed)) if speed[k] < road_limit_speed]
    if not cand10:
        print(f"[curve_center={curve_center}] 10m pass에서 candidate 없음(곡률 임계 미달) -- SKIP")
        return
    true_entry_dist = dist[cand10[0]]
    all_c10 = route_find_clusters(cand10, dist, 1, ROUTE_CLUSTER_MAX_GAP_M)
    orph10 = [c for c in all_c10 if len(c) < ROUTE_CLUSTER_MIN_POINTS]
    if not orph10:
        print(f"[curve_center={curve_center}] orphan 없음(min_points>=2 정상 충족) -- SKIP "
              f"(true_entry_dist={true_entry_dist:.1f}m)")
        return
    orphan_idx0 = orph10[0][0]
    ws_expected = dist[orphan_idx0] - LOCAL_CURVE_WINDOW_BACK_M
    print(f"\n=== 국소커브 curve_center={curve_center}m -- 10m orphan @ {dist[orphan_idx0]:.1f}m "
          f"(ws={ws_expected:.1f}m), true_entry_dist(10m grid)={true_entry_dist:.1f}m ===")
    orphans = [[orphan_idx0]]
    v_ego_ms = v_ego_kph / 3.6
    for label, patch in (("A(현재,823943a6)", False), ("B(가상패치,max(0,ws))", True)):
        merged_d, merged_s, merged_c, merged_ft, local_used = route_local_curve_merge(
            orphans, dist, speed, curv, ft, path,
            map_turn_speed_factor=1.0, road_limit_speed=road_limit_speed,
            patch_ws_clamp=patch)
        candidates = [k for k in range(len(merged_s)) if merged_s[k] < road_limit_speed]
        all_clusters = route_find_clusters(candidates, merged_d, 1, ROUTE_CLUSTER_MAX_GAP_M)
        clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
        apex_idx, apex_dist, apex_speed = continuity_new_entry(clusters, merged_d, merged_s)
        if apex_dist is None:
            print(f"  [{label}] apex 없음 -- SKIP")
            continue
        label_error = apex_dist - true_entry_dist
        print(f"  [{label}] apex_dist={apex_dist:.2f}m (실제 대비 오차 {label_error:+.2f}m) "
              f"apex_speed={apex_speed:.1f}")
        for ra in (True, False):
            gate = active_gate_downstream(
                apex_dist, apex_speed, v_ego_kph, v_ego_ms,
                auto_navi_speed_ctrl_end, auto_navi_speed_decel_rate, ra)
            state = "ACTIVE중" if ra else "INERT"
            extra = f"required_decel={gate.get('required_decel_mss'):.3f}" if 'required_decel_mss' in gate else \
                    f"dist_reached={gate.get('dist_reached')}"
            print(f"      [{state}] eff_dist={gate['eff_dist']:.2f} -> {gate['outcome']} ({extra})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true",
                     help="5개 경계조건 합성 시나리오 실행 (인자 없이 실행해도 동일)")
    ap.add_argument("--downstream", action="store_true",
                     help="331차 STEP2: ws<0 라벨의 candidates/cluster/apex/ACTIVE 게이트 영향 A/B 비교")
    ap.add_argument("--downstream-localized", action="store_true",
                     help="331차 STEP2 개선판: 국소 커브(실제 진입점 명확)로 apex_dist 오차 A/B 비교")
    args = ap.parse_args()
    if args.downstream_localized:
        for cc in (10.0, 20.0, 30.0, 40.0, 50.0, 60.0):
            run_localized_case(cc)
    elif args.downstream:
        # orphan center를 15m(330차 원 케이스)부터 39m(ws<0 경계 부근)까지
        # 스윕 -- ws<0가 실제로 어느 근접거리 범위에서 발생하고 그 영향이
        # 어떻게 달라지는지 확인.
        for center in (5.0, 15.0, 25.0, 35.0, 39.0):
            run_downstream_comparison(center, route_active_test=True)
            run_downstream_comparison(center, route_active_test=False)
    else:
        self_test()


if __name__ == "__main__":
    main()
