"""
99차 발견 -> 100차 패치 사전검증: carrot_navi_route()의 Shapely
LineString.interpolate() 반복호출을 numpy 벡터화로 대체했을 때
기존 방식과 수치적으로 동일한 결과를 내는지 확인.

원본 방식 (carrot_man.py 435-444줄, sim_route_curvature_sample.py의
resample_10m()과 동일):
    line = LineString(points_xy)
    d = 0.0
    while d <= line.length:
        p = line.interpolate(d)
        out.append((p.x, p.y))
        d += distance_interval

신규 방식 (numpy 벡터화, 후보):
    resample_10m_np(points_xy, distance_interval)
"""
import math
import random

import numpy as np
from shapely.geometry import LineString


def resample_10m_shapely(points_xy, distance_interval=10.0):
    line = LineString(points_xy)
    out = []
    d = 0.0
    while d <= line.length:
        p = line.interpolate(d)
        out.append((p.x, p.y))
        d += distance_interval
    return out


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


def make_random_path(n_points, seed, jitter=1.0, step=40.0):
    rnd = random.Random(seed)
    x, y = 0.0, 0.0
    heading = 0.0
    pts = [(x, y)]
    for _ in range(n_points - 1):
        heading += rnd.uniform(-0.4, 0.4)  # 급커브 포함
        x += step * math.cos(heading) + rnd.uniform(-jitter, jitter)
        y += step * math.sin(heading) + rnd.uniform(-jitter, jitter)
        pts.append((x, y))
    return pts


def compare(points_xy, distance_interval, label):
    ref = resample_10m_shapely(points_xy, distance_interval)
    cand = resample_10m_np(points_xy, distance_interval)
    if len(ref) != len(cand):
        print(f"[FAIL] {label}: 길이 다름 ref={len(ref)} cand={len(cand)}")
        return False
    max_err = 0.0
    for (rx, ry), (cx, cy) in zip(ref, cand):
        err = math.hypot(rx - cx, ry - cy)
        max_err = max(max_err, err)
    ok = max_err < 1e-6
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}: n_ref={len(ref)} n_cand={len(cand)} max_err={max_err:.3e}")
    return ok


def main():
    all_ok = True

    # 1) 일반 랜덤 경로 (다양한 커브 곡률/길이)
    for seed in range(20):
        pts = make_random_path(n_points=random.Random(seed).randint(5, 40), seed=seed)
        all_ok &= compare(pts, 10.0, f"random_path seed={seed} n={len(pts)}")

    # 2) 89/90차 케이스와 동일한 짧은 램프 커브 스타일 (급격한 헤딩 변화)
    sharp = [(0, 0), (10, 2), (18, 8), (22, 18), (20, 28), (12, 34), (2, 33)]
    all_ok &= compare(sharp, 10.0, "sharp_ramp_curve")

    # 3) 직선 경로 (오탐/회귀 없는지 -- 곡률 0)
    straight = [(i * 15.0, 0.0) for i in range(10)]
    all_ok &= compare(straight, 10.0, "straight_line")

    # 4) 아주 짧은 경로 (점 2~3개, 경계조건)
    all_ok &= compare([(0, 0), (5, 0)], 10.0, "two_points_short")
    all_ok &= compare([(0, 0), (25, 0), (25, 25)], 10.0, "three_points_Lshape")

    # 5) 총 길이가 distance_interval의 정확한 배수인 경우 (경계값 d==length)
    exact_multiple = [(0, 0), (100.0, 0.0)]  # length=100, interval=10 -> d=100 포함 여부
    all_ok &= compare(exact_multiple, 10.0, "exact_multiple_boundary")

    # 6) route_lookahead_m 최대치(600m)에 가까운 긴 경로
    long_path = make_random_path(n_points=60, seed=999, step=10.0)
    all_ok &= compare(long_path, 10.0, "long_path_600m_scale")

    print()
    print("=== 전체 결과:", "ALL PASS" if all_ok else "일부 FAIL 존재", "===")


if __name__ == "__main__":
    main()
