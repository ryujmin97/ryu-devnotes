"""
90차: route 곡률 샘플링 chord 축소(sample 4->2/3) 방안(89차 대안1) 검증용
시뮬레이션.

배경: 89차에서 실측 확인된 문제 - carrot_navi_route()의 곡률 계산이
p1-p2-p3 3점을 sample*distance_interval(기본 4*10=40m) 간격으로 떼어
계산해, 반경이 작고 급격한 램프 커브에서 순간곡률을 평활화(과소평가)
할 가능성이 있음(가설, 코드 구조상 개연성만 확인, raw navi_points가
로그에 없어 직접검증 불가였음).

방법: 이 로그(89차/90차 원본과 동일 route bc4301a25d seg12)에 실제
기록된 desiredCurvature(모델이 그 순간 추종한 경로 곡률, 20Hz)를
시간에 대해 적분해 차량이 실제로 통과한 경로의 2D 지역좌표
(x,y,heading)를 재구성한다 -- 이는 "차량이 실제로 그 지점에 도달했을
때 보고한 곡률"이므로 도로의 실제 물리적 곡률 프로파일의 근사치로
쓸 수 있다(GPS 폴리라인 자체는 아니지만, calculate_curvature()가
회전/이동 불변량만 사용하므로 이 재구성 경로에 원본 코드의 곡률+속도
+역방향DP 로직을 그대로 적용해 sample=4(현재)/3/2(candidate)를
비교할 수 있음).

이 재구성 경로에 carrot_man.py의 calculate_curvature() +
V_CURVE_LOOKUP_BP/VALS + 역방향DP 로직을 그대로 복제해, 특정 시점
(스냅샷)에서 sample 값에 따라 산출되는 out_speed(현재 지점 목표속도)가
얼마나 달라지는지, 그리고 최소 목표속도(정점 근처)가 vturn 실측 최종
요구치(73km/h)에 얼마나 더 가까워지는지 비교한다.
"""
import argparse
import csv
import math
import sys

import numpy as np

sys.path.append("/home/claude/devnotes/toolkit")
from analysis_helpers import load_csv  # noqa: E402

try:
    from shapely.geometry import LineString
except ImportError:
    LineString = None

# carrot_man.py 원본과 동일 (2026-08-26 시점, c3-ms-curv HEAD cf32b5d)
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265.,
                     1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]


def calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


def reconstruct_path(rows, t_start=None, t_end=None):
    """desiredCurvature를 시간축으로 적분해 (t, x, y, vEgo) 배열 재구성."""
    sub = [r for r in rows if r.get('desiredCurvature', '') != '']
    if t_start is not None:
        sub = [r for r in sub if float(r['t']) >= t_start]
    if t_end is not None:
        sub = [r for r in sub if float(r['t']) <= t_end]
    sub.sort(key=lambda r: float(r['t']))

    theta = 0.0
    x, y = 0.0, 0.0
    pts = []
    prev_t = None
    prev_v = None
    for r in sub:
        t = float(r['t'])
        v = float(r['vEgo'])
        curv = float(r['desiredCurvature'])
        if prev_t is not None:
            dt = t - prev_t
            if 0 < dt < 0.5:
                ds = 0.5 * (prev_v + v) * dt
                theta += curv * ds
                x += math.cos(theta) * ds
                y += math.sin(theta) * ds
        pts.append({'t': t, 'x': x, 'y': y, 'vEgo': v})
        prev_t, prev_v = t, v
    return pts


def resample_10m(points_xy, distance_interval=10.0):
    if LineString is None:
        raise RuntimeError("shapely 필요 (pip install shapely)")
    line = LineString(points_xy)
    out = []
    d = 0.0
    while d <= line.length:
        p = line.interpolate(d)
        out.append((p.x, p.y))
        d += distance_interval
    return out


def compute_curvatures_speeds(resampled_points, sample, distance_interval=10.0):
    curvatures, speeds, distances = [], [], []
    distance = distance_interval
    if len(resampled_points) < sample * 2 + 1:
        return curvatures, speeds, distances
    for i in range(len(resampled_points) - sample * 2):
        distance += distance_interval
        p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
        curvature = calculate_curvature(p1, p2, p3)
        curvatures.append(curvature)
        speed = float(np.interp(abs(curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS))
        # nRoadLimitSpeed floor(직선 구간용)는 이번 비교 범위 밖 -- 생략
        speeds.append(speed)
        distances.append(distance)
    return curvatures, speeds, distances


def backward_dp(speeds, distances, v_ego_kph, accel_limit, distance_interval=10.0,
                 vturn_safe_time=0.0):
    """carrot_navi_route()의 역방향 DP 그대로 복제 (82차 수정판: 진입측은
    순수 물리 도달시간, 원복측만 vturn_safe_time 크레딧)."""
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
            time_delay = max(0.0, (v_ego_kph - target_speed) / accel_limit_kmh)
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


def run_snapshot(path_pts, snapshot_idx, v_ego_kph, accel_limit=0.70, vturn_safe_time=2.0):
    """snapshot_idx 이후의 재구성 경로로 route 계산 1회(sample 2/3/4 비교)."""
    xy_ahead = [(p['x'], p['y']) for p in path_pts[snapshot_idx:]]
    if len(xy_ahead) < 10:
        return None
    resampled = resample_10m(xy_ahead)
    result = {}
    for sample in (4, 3, 2):
        curvatures, speeds, distances = compute_curvatures_speeds(resampled, sample)
        if not speeds:
            result[sample] = None
            continue
        out_speeds = backward_dp(speeds, distances, v_ego_kph, accel_limit,
                                  vturn_safe_time=vturn_safe_time)
        result[sample] = {
            'out_speed_now': out_speeds[0],
            'min_target_speed': min(speeds),
            'min_target_speed_at_m': distances[speeds.index(min(speeds))],
            'n_points': len(speeds),
        }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv_path')
    ap.add_argument('--t-start', type=float, default=9190.0)
    ap.add_argument('--t-end', type=float, default=9235.0)
    ap.add_argument('--accel-limit', type=float, default=0.70,
                     help='m/s^2, 사용자 실제 AutoNaviSpeedDecelRate(83차 확인, 0.70)')
    ap.add_argument('--vturn-safe-time', type=float, default=2.0)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    path_pts = reconstruct_path(rows, args.t_start, args.t_end)
    print(f"재구성 경로 포인트 수: {len(path_pts)} (t={path_pts[0]['t']:.2f}~{path_pts[-1]['t']:.2f})")

    # 여러 스냅샷 시점에서 route 계산 재현 (실제 route가 개입하기 시작한
    # t=9211.27 이전부터, vturn에 넘어가는 t=9221.17까지)
    snapshot_times = [9200.0, 9203.0, 9205.0, 9208.0, 9211.0, 9214.0, 9217.0, 9220.0]
    print(f"{'t':>8} {'vEgo(kph)':>10} | "
          f"{'s=4 now':>8} {'s=4 min':>8} {'@m':>6} | "
          f"{'s=3 now':>8} {'s=3 min':>8} {'@m':>6} | "
          f"{'s=2 now':>8} {'s=2 min':>8} {'@m':>6}")
    for ts in snapshot_times:
        idx = min(range(len(path_pts)), key=lambda i: abs(path_pts[i]['t'] - ts))
        v_ego_kph = path_pts[idx]['vEgo'] * 3.6
        res = run_snapshot(path_pts, idx, v_ego_kph, accel_limit=args.accel_limit,
                            vturn_safe_time=args.vturn_safe_time)
        if res is None:
            print(f"{ts:8.2f} {v_ego_kph:10.1f} | (lookahead 부족, 스킵)")
            continue
        line = f"{ts:8.2f} {v_ego_kph:10.1f} |"
        for s in (4, 3, 2):
            r = res[s]
            if r is None:
                line += f" {'N/A':>8} {'N/A':>8} {'':>6} |"
            else:
                line += (f" {r['out_speed_now']:8.1f} {r['min_target_speed']:8.1f} "
                         f"{r['min_target_speed_at_m']:6.0f} |")
        print(line)

    print("\n참고: 실제 로그 실측값 -- route(src=route) desiredSpeed는 t=9211.27~9221.12")
    print("동안 155->121km/h까지만 하강(최저 121), vturn(src=vturn) 실제 요구치는")
    print("t=9221.17 이후 최저 71~73km/h까지 하강(t=9225~9229 부근). accel_limit=0.70,")
    print("vturn_safe_time=2.0(81차)은 사용자 실제 설정값.")


if __name__ == '__main__':
    main()
