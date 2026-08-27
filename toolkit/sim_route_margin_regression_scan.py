"""
93차: 91차(ROUTE_ENTRY_MARGIN_KPH=25.0) 패치를 국도 연속곡선 실주행 로그
(route 0000032d--c0e3054c4a, seg13~19, 91차 패치 이전 baseline)에 대해
전체 구간 스윕으로 회귀검증.

방법: sim_route_curvature_sample.py의 reconstruct_path/resample_10m/
compute_curvatures_speeds/backward_dp를 그대로 재사용하되, backward_dp에
91차의 ROUTE_ENTRY_MARGIN_KPH 로직(감속전환 시점 time_delay 계산에만
target_speed - margin_kph 사용)을 추가한 patched 버전을 병행 실행.

route margin=0(baseline, 91차 이전) vs margin=25(91차 패치)를 로그 전체에
3초 간격으로 스냅샷을 찍어 비교:
  1. 직선 구간(향후 lookahead 내 최대곡률이 사실상 0)에서 margin=25가
     margin=0 대비 불필요한 조기감속(오탐)을 유발하는지
  2. 커브 구간에서 margin=25가 margin=0보다 유의미하게 일찍(더 높은
     out_speed_now, 즉 아직 안 조여진 상태가 아니라 이미 조여지기 시작한
     상태) 개입하면서도, 최종 min target_speed 자체는 동일한지(설계
     의도: 스케줄만 당김, 목표값 자체는 불변)
"""
import argparse
import math
import sys

import numpy as np

sys.path.append("/home/claude/devnotes/toolkit")
from analysis_helpers import load_csv  # noqa: E402
from sim_route_curvature_sample import (  # noqa: E402
    reconstruct_path, resample_10m, compute_curvatures_speeds,
)


def backward_dp_margin(speeds, distances, v_ego_kph, accel_limit, distance_interval=10.0,
                        vturn_safe_time=2.0, margin_kph=0.0):
    """82차(원복측 대칭버퍼) + 91차(ROUTE_ENTRY_MARGIN_KPH) 로직 그대로 복제."""
    accel_limit_kmh = accel_limit * 3.6
    out_speeds = [0.0] * len(speeds)
    if not speeds:
        return out_speeds
    out_speeds[-1] = speeds[-1]
    time_wait = 0.0
    route_prev_state = None
    for i in range(len(speeds) - 2, -1, -1):
        target_speed = speeds[i]
        next_out_speed = out_speeds[i + 1]
        if target_speed < next_out_speed:
            # 91차: time_delay 계산에만 margin 차감 (최종 target_speed 자체는 불변)
            entry_target_for_delay = target_speed - margin_kph
            time_delay = max(0.0, (v_ego_kph - entry_target_for_delay) / accel_limit_kmh)
            time_wait = -time_delay
            route_prev_state = 'decel'
        elif target_speed > next_out_speed and route_prev_state == 'decel':
            time_wait += vturn_safe_time
            route_prev_state = 'accel'
        time_interval = distance_interval / (next_out_speed / 3.6) if next_out_speed > 0 else 0
        time_apply = min(time_interval, max(0.0, time_interval + time_wait))
        max_allowed_speed = next_out_speed + (accel_limit_kmh * time_apply)
        adjusted_speed = min(target_speed, max_allowed_speed)
        time_wait += min(2.0, time_interval)
        out_speeds[i] = adjusted_speed
    return out_speeds


def run_snapshot_margin(rows, t0, lookahead_s=45.0, accel_limit=0.70, sample=4):
    """t0 시점부터 lookahead_s초 구간을 재구성해 margin=0/25 비교."""
    pts = reconstruct_path(rows, t_start=t0, t_end=t0 + lookahead_s)
    if len(pts) < 20:
        return None
    xy = [(p['x'], p['y']) for p in pts]
    v_ego_kph = pts[0]['vEgo'] * 3.6
    try:
        resampled = resample_10m(xy)
    except Exception:
        return None
    curvatures, speeds, distances = compute_curvatures_speeds(resampled, sample)
    if not speeds:
        return None
    out0 = backward_dp_margin(speeds, distances, v_ego_kph, accel_limit, margin_kph=0.0)
    out25 = backward_dp_margin(speeds, distances, v_ego_kph, accel_limit, margin_kph=25.0)
    return {
        't0': t0,
        'v_ego_kph': v_ego_kph,
        'out_speed_now_m0': out0[0],
        'out_speed_now_m25': out25[0],
        'min_speed_m0': min(out0),
        'min_speed_m25': min(out25),
        'max_curvature': max(abs(c) for c in curvatures) if curvatures else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path')
    ap.add_argument('--step', type=float, default=3.0)
    ap.add_argument('--lookahead', type=float, default=45.0)
    ap.add_argument('--accel', type=float, default=0.70)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    t_min = min(float(r['t']) for r in rows)
    t_max = max(float(r['t']) for r in rows)

    results = []
    t0 = t_min
    while t0 < t_max - args.lookahead:
        res = run_snapshot_margin(rows, t0, lookahead_s=args.lookahead, accel_limit=args.accel)
        if res:
            results.append(res)
        t0 += args.step

    print(f"총 스냅샷 {len(results)}건 (t={t_min:.1f}~{t_max:.1f}, step={args.step}s, lookahead={args.lookahead}s)")

    # 1) 직선 오탐 체크: 향후 lookahead 구간 전체가 사실상 직선(max_curvature 작음)인데
    #    margin=25가 margin=0보다 3km/h+ 낮은 out_speed_now를 내는 경우
    STRAIGHT_CURV_THRESH = 1.0 / 800.0  # V_CURVE_LOOKUP_BP 최저 구간(300kph 대응) 미만이면 사실상 무곡률
    false_positive = [r for r in results
                       if r['max_curvature'] < STRAIGHT_CURV_THRESH
                       and (r['out_speed_now_m0'] - r['out_speed_now_m25']) > 3.0]
    print(f"\n[1] 직선구간(향후 lookahead 전체 무곡률) 오탐 후보: {len(false_positive)}건")
    for r in false_positive[:10]:
        print(f"  t={r['t0']:.2f} vEgo={r['v_ego_kph']:.1f}kph "
              f"out_m0={r['out_speed_now_m0']:.1f} out_m25={r['out_speed_now_m25']:.1f} "
              f"maxcurv={r['max_curvature']:.5f}")

    # 2) 조기개입 확인: margin=25가 margin=0보다 out_speed_now를 유의미하게 낮춰(=먼저 감속
    #    스케줄 반영) 조이는 스냅샷 수, 그리고 최종 min_speed(정점 목표값)는 거의 동일한지
    advanced = [r for r in results if (r['out_speed_now_m0'] - r['out_speed_now_m25']) > 1.0]
    print(f"\n[2] margin=25가 margin=0보다 조기개입(더 낮은 out_speed_now)한 스냅샷: {len(advanced)}건 / 전체 {len(results)}건")
    if advanced:
        min_diffs = [abs(r['min_speed_m0'] - r['min_speed_m25']) for r in advanced]
        print(f"    이 구간들의 min_speed(정점 목표값) 차이: 평균 {np.mean(min_diffs):.2f}kph, "
              f"최대 {np.max(min_diffs):.2f}kph (설계 의도: 0에 가까워야 함 - 목표값 자체는 불변)")
        max_advance = max(advanced, key=lambda r: r['out_speed_now_m0'] - r['out_speed_now_m25'])
        print(f"    최대 조기개입 사례: t={max_advance['t0']:.2f} "
              f"out_m0={max_advance['out_speed_now_m0']:.1f} -> out_m25={max_advance['out_speed_now_m25']:.1f} "
              f"(min_m0={max_advance['min_speed_m0']:.1f}, min_m25={max_advance['min_speed_m25']:.1f})")

    # 3) 반대방향(margin=25가 margin=0보다 오히려 더 높게=늦게 나오는 경우) - 로직상 있으면 안 됨(버그 신호)
    reversed_cases = [r for r in results if (r['out_speed_now_m25'] - r['out_speed_now_m0']) > 1.0]
    print(f"\n[3] margin=25가 오히려 margin=0보다 더 높은(개입이 늦은) 역전 사례: {len(reversed_cases)}건 (0건이어야 정상)")
    for r in reversed_cases[:5]:
        print(f"  t={r['t0']:.2f} out_m0={r['out_speed_now_m0']:.1f} out_m25={r['out_speed_now_m25']:.1f}")


if __name__ == '__main__':
    main()
