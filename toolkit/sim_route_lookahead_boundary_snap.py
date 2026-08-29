#!/usr/bin/env python3
"""
131차: 129차(교차로 접근 route 사전감속 "계단형 고정" 실측) 재현 시도.

배경: 129차는 원인을 91차 ROUTE_ENTRY_MARGIN_KPH의 time_delay 계산
방식(margin_kph 차감)으로 가설했으나, 130차/131차에서 이어서
`sim_route_step_drop_repro.py`(desiredCurvature 시간적분 재구성 기반)로
동일 시각(t=2182.70~2182.75)을 20Hz 슬라이딩 재현했을 때 최대
프레임간 낙차가 1.46~1.84kph에 그쳐, 실측 Δ-25kph 단일프레임 급락을
전혀 재현하지 못함(NEGATIVE 결과) -- margin_kph 가설만으로는 급락의
"계단" 형태(연속감속이 아니라 20Hz 1프레임 내 완결)를 설명 못 함.

이 스크립트가 검증하는 새 가설(Hypothesis C, 코드 정독 기반):
`carrot_man.py::carrot_navi_route()`는 매 20Hz 사이클마다
`route_lookahead_m = compute_route_lookahead_distance(v_ego, accel)`으로
정해지는 "고정 거리 윈도우"를 현재 GPS 위치 기준으로 매번 새로 잘라
`get_path_after_distance()`로 뽑고, 그 윈도우 끝점(가장 먼 점)의
curvature 기반 speed가 역방향 DP의 초기 anchor(`out_speeds[-1] =
speeds[-1]`)로 쓰인다. 또한 curvature는 3점(sample*10m=40m 간격)
방식이라 윈도우 끝에서 40m 폭만큼은애초에 계산 자체가 안 된다(배열
길이 = len(resampled_points) - sample*2). 즉 "윈도우 밖에 있던 급커브
지점"은 그 지점이 윈도우 안으로 들어오기 전까지는 speeds[] 배열에
전혀 존재하지 않다가, 차량이 다가가며 윈도우가 그 지점을 포함하는
순간 **단 한 프레임 만에** 급커브의 낮은 speed가 배열에 나타나고,
역방향 DP가 그 프레임에서 즉시 전체 배열을 재계산 -- margin_kph
로직이 허용하는 한 그 낮은 값이 근접 지점(out_speeds[0])까지 즉시
전파될 수 있다. 이는 "서서히 다가가며 감속 스케줄이 당겨지는" 것과는
질적으로 다른, "윈도우 경계를 넘는 순간의 이산적 정보 출현"이 원인인
불연속이다.

방법: 실제 운영 코드의 순수함수(haversine/closest_point_on_segment/
get_path_after_distance/compute_route_lookahead_distance/
gps_to_relative_xy/resample_10m_np/calculate_curvature)를 carrot_man.py
(커밋 1cc2bf3, 130차 반영 이후 HEAD)에서 그대로 복제하고, 역방향 DP도
carrot_navi_route() 본문과 동일하게 복제한다(ROUTE_ENTRY_MARGIN_KPH
등 상수 포함). 실제 navi 폴리라인은 로그에 없으므로(131차 확인,
navRoute capnp 채널 count=0, navInstructionCarrot에는 좌표 없음 --
maneuverDistance/speedLimit 등 요약 정보만 존재) **합성 GPS 폴리라인**
(직선 도로 뒤에 급커브)을 만들어 차량을 등속으로 접근시키며 20Hz로
carrot_navi_route()를 반복 호출, out_speed(t) 시계열의 프레임간 낙차를
관찰한다.

사용:
  python3 sim_route_lookahead_boundary_snap.py \
      --v-ego-kph 74 --curve-radius-m 25 --accel 0.70 \
      --straight-before-curve-m 700
"""
import argparse
import math

import numpy as np

# ---- carrot_man.py 순수함수 그대로 복제 (커밋 1cc2bf3, 130차 이후 HEAD) ----
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265.,
                     1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_ENTRY_MARGIN_KPH = 25.0


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def closest_point_on_segment(p1, p2, current_position):
    x1, y1 = p1
    x2, y2 = p2
    px, py = current_position
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return p1
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0, min(1, t))
    return (x1 + t * dx, y1 + t * dy)


def get_path_after_distance(start_index, coordinates, current_position, distance_m):
    total_distance = 0
    path_after_distance = []
    closest_index = -1
    closest_point = None
    min_distance = float('inf')
    start_index = max(0, start_index - 2)
    for i in range(start_index, len(coordinates) - 1):
        p1 = coordinates[i]
        p2 = coordinates[i + 1]
        candidate_point = closest_point_on_segment(p1, p2, current_position)
        distance = haversine(current_position[0], current_position[1], candidate_point[0], candidate_point[1])
        if distance < min_distance:
            min_distance = distance
            closest_point = candidate_point
            closest_index = i
        elif distance > min_distance and min_distance < 10:
            break
    start_index = closest_index
    if closest_index != -1:
        path_after_distance.append(closest_point)
        path_after_distance.append(coordinates[closest_index + 1])
        total_distance = haversine(closest_point[0], closest_point[1], coordinates[closest_index + 1][0],
                                    coordinates[closest_index + 1][1])
        for i in range(closest_index + 1, len(coordinates) - 1):
            coord1 = coordinates[i]
            coord2 = coordinates[i + 1]
            segment_distance = haversine(coord1[0], coord1[1], coord2[0], coord2[1])
            if total_distance + segment_distance >= distance_m and segment_distance > 0:
                remaining_distance = distance_m - total_distance
                ratio = remaining_distance / segment_distance
                interpolated_lon = coord1[0] + ratio * (coord2[0] - coord1[0])
                interpolated_lat = coord1[1] + ratio * (coord2[1] - coord1[1])
                path_after_distance.append((interpolated_lon, interpolated_lat))
                break
            total_distance += segment_distance
            path_after_distance.append(coord2)
    return path_after_distance, start_index, closest_point


def compute_route_lookahead_distance(v_ego_kph, accel_limit_mss, min_m=300.0, max_m=600.0,
                                      assumed_target_kph=30.0):
    if accel_limit_mss is None or accel_limit_mss <= 0:
        return min_m
    v_ego_ms = max(0.0, v_ego_kph) / 3.6
    v_target_ms = assumed_target_kph / 3.6
    needed_m = max(0.0, (v_ego_ms ** 2 - v_target_ms ** 2) / (2.0 * accel_limit_mss))
    return float(min(max_m, max(min_m, needed_m)))


def gps_to_relative_xy(gps_path, reference_point, heading_deg):
    ref_lon, ref_lat = reference_point
    relative_coordinates = []
    heading_rad = math.radians(heading_deg)
    for lon, lat in gps_path:
        x = (lon - ref_lon) * 40008000 * math.cos(math.radians(ref_lat)) / 360
        y = (lat - ref_lat) * 40008000 / 360
        x_rot = x * math.cos(heading_rad) - y * math.sin(heading_rad)
        y_rot = x * math.sin(heading_rad) + y * math.cos(heading_rad)
        relative_coordinates.append((y_rot, x_rot))
    return relative_coordinates


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
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


def carrot_navi_route_core(navi_points, navi_points_start_index, current_position, heading_deg,
                            v_ego_kph, accel_limit, road_limit_speed_kph=300.0):
    """carrot_navi_route() 본문 그대로 복제 (messaging/캐시 등 IO 부분 제외한 순수 로직)."""
    distance_interval = 10.0
    out_speed = 300
    route_lookahead_m = compute_route_lookahead_distance(v_ego_kph, accel_limit)
    path, navi_points_start_index, start_point = get_path_after_distance(
        navi_points_start_index, navi_points, current_position, route_lookahead_m)
    speeds = []
    distances = []
    if path:
        relative_coords = gps_to_relative_xy(path, start_point, heading_deg)
        resampled_points = resample_10m_np(relative_coords, distance_interval)
        sample = 4
        distance = 10.0
        if len(resampled_points) >= sample * 2 + 1:
            for i in range(len(resampled_points) - sample * 2):
                distance += distance_interval
                p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
                curvature = calculate_curvature(p1, p2, p3)
                speed = np.interp(abs(curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
                if abs(curvature) < 0.02:
                    speed = max(speed, road_limit_speed_kph)
                speeds.append(speed)
                distances.append(distance)
            accel_limit_kmh = accel_limit * 3.6
            out_speeds = [0] * len(speeds)
            out_speeds[-1] = speeds[-1]
            time_wait = 0
            route_prev_state = None
            for i in range(len(speeds) - 2, -1, -1):
                target_speed = speeds[i]
                next_out_speed = out_speeds[i + 1]
                if target_speed < next_out_speed:
                    margin_target_speed = max(0.0, target_speed - ROUTE_ENTRY_MARGIN_KPH)
                    time_delay = max(0, ((v_ego_kph - margin_target_speed) / accel_limit_kmh))
                    time_wait = -time_delay
                    route_prev_state = 'decel'
                elif target_speed > next_out_speed and route_prev_state == 'decel':
                    time_wait += 2.0  # vturn_safe_time 근사(실측 상수, 82차)
                    route_prev_state = 'accel'
                time_interval = distance_interval / (next_out_speed / 3.6) if next_out_speed > 0 else 0
                time_apply = min(time_interval, max(0, time_interval + time_wait))
                max_allowed_speed = next_out_speed + (accel_limit_kmh * time_apply)
                adjusted_speed = min(target_speed, max_allowed_speed)
                time_wait += min(2.0, time_interval)
                out_speeds[i] = adjusted_speed
            out_speed = out_speeds[0]
    return out_speed, navi_points_start_index, len(speeds), (distances[-1] if distances else 0.0)


def build_synthetic_route(straight_before_m, curve_radius_m, curve_arc_deg=90.0,
                           straight_after_m=300.0, point_spacing_m=5.0):
    """직선 -> 반경 curve_radius_m 원호(curve_arc_deg도 회전) -> 직선. 위경도 근사(적도 부근 단순 평면가정)."""
    lon0, lat0 = 129.0756, 35.1796  # 부산 근방 임의 원점
    m_per_deg_lon = 40008000 * math.cos(math.radians(lat0)) / 360.0
    m_per_deg_lat = 40008000 / 360.0

    pts_xy = [(0.0, 0.0)]
    d = 0.0
    while d < straight_before_m:
        d += point_spacing_m
        pts_xy.append((0.0, min(d, straight_before_m)))
    # 원호: 진행방향 +y에서 좌회전, 중심은 (-R, straight_before_m)
    R = curve_radius_m
    cx, cy = -R, straight_before_m
    arc_len = R * math.radians(curve_arc_deg)
    n_arc = max(2, int(arc_len // point_spacing_m))
    for k in range(1, n_arc + 1):
        theta = math.radians(curve_arc_deg) * k / n_arc
        x = cx + R * math.sin(theta)
        y = cy + R * (1 - math.cos(theta))
        pts_xy.append((x, y))
    # 원호 끝점에서의 진행방향으로 직선 연장
    theta_end = math.radians(curve_arc_deg)
    end_heading = theta_end  # y축 기준 회전각
    ex, ey = pts_xy[-1]
    dirx, diry = math.sin(end_heading), math.cos(end_heading)
    d = 0.0
    while d < straight_after_m:
        d += point_spacing_m
        pts_xy.append((ex + dirx * d, ey + diry * d))

    coords = []
    for x, y in pts_xy:
        lon = lon0 + x / m_per_deg_lon
        lat = lat0 + y / m_per_deg_lat
        coords.append((lon, lat))
    return coords, lon0, lat0, m_per_deg_lon, m_per_deg_lat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--v-ego-kph', type=float, default=74.0, help='129차 실측 근접값(t=2182.7 vEgo=73.9)')
    ap.add_argument('--curve-radius-m', type=float, default=25.0, help='급커브 반경(작을수록 목표속도 낮음)')
    ap.add_argument('--curve-arc-deg', type=float, default=90.0)
    ap.add_argument('--accel', type=float, default=0.70, help='AutoNaviSpeedDecelRate 실측 기본값(83차)')
    ap.add_argument('--straight-before-curve-m', type=float, default=700.0,
                     help='시작 위치~커브 진입까지 직선거리(커브가 초기엔 lookahead 밖에 있도록 충분히 길게)')
    ap.add_argument('--dt', type=float, default=0.05, help='20Hz')
    args = ap.parse_args()

    coords, lon0, lat0, m_per_deg_lon, m_per_deg_lat = build_synthetic_route(
        args.straight_before_curve_m, args.curve_radius_m, args.curve_arc_deg)

    v_ego_ms = args.v_ego_kph / 3.6
    # 시작 위치: 커브 진입점 기준, 현재 lookahead(최대600m)+여유 200m 뒤에서 출발
    lookahead0 = compute_route_lookahead_distance(args.v_ego_kph, args.accel)
    start_offset_m = min(args.straight_before_curve_m - 5.0, lookahead0 + 250.0)
    ego_y = max(0.0, args.straight_before_curve_m - start_offset_m)

    navi_points_start_index = 0
    prev_out = None
    max_drop = 0.0
    max_drop_t = None
    t = 0.0
    print(f"=== 합성 route 경계진입 스냅 검증 (v_ego={args.v_ego_kph}kph, "
          f"curve_R={args.curve_radius_m}m, accel={args.accel}, dt={args.dt}s) ===")
    print(f"route_lookahead(v={args.v_ego_kph}kph) = {lookahead0:.1f}m, 출발지점: 커브진입 {ego_y:.0f}m 앞 "
          f"(직선구간 총 {args.straight_before_curve_m:.0f}m)")
    print(f"{'t':>7} {'ego_y(m)':>9} {'dist_to_curve':>14} {'out_speed':>10} {'n_speeds':>9} {'d(out)':>8}")

    rows = []
    while ego_y < args.straight_before_curve_m + 50:
        lon = lon0
        lat = lat0 + ego_y / m_per_deg_lat
        current_position = (lon, lat)
        out_speed, navi_points_start_index, n_speeds, far_dist = carrot_navi_route_core(
            coords, navi_points_start_index, current_position, heading_deg=0.0,
            v_ego_kph=args.v_ego_kph, accel_limit=args.accel)
        dist_to_curve = args.straight_before_curve_m - ego_y
        drop_str = ""
        if prev_out is not None:
            d = out_speed - prev_out
            drop_str = f"{d:+.2f}"
            if -d > max_drop:
                max_drop = -d
                max_drop_t = t
        rows.append((t, ego_y, dist_to_curve, out_speed, n_speeds))
        if abs(dist_to_curve) < 400 or (prev_out is not None and abs(out_speed - prev_out) > 3.0):
            print(f"{t:7.2f} {ego_y:9.1f} {dist_to_curve:14.1f} {out_speed:10.1f} {n_speeds:9d} {drop_str:>8}")
        prev_out = out_speed
        ego_y += v_ego_ms * args.dt
        t += args.dt

    print(f"\n최대 프레임간(1/20s) out_speed 낙차: {max_drop:.2f}kph @ t={max_drop_t}")
    print("(참고) 129차 실측 desiredSpeed 단일프레임 낙차: Δ-25.0 (t=2182.70->2182.75), Δ-24.0 (t=2206.81->2206.85)")
    if max_drop > 10.0:
        print("=> Hypothesis C(lookahead 경계진입 시 speeds[] 배열에 급커브가 이산적으로 "
              "'출현'하며 역방향DP가 그 프레임에 즉시 전체 재계산) 재현 SUCCESS (실측과 동일 규모/형태)")
    else:
        print("=> Hypothesis C 재현 실패 또는 규모 부족 -- 파라미터(curve_radius/straight_before 등) 조정 필요")


if __name__ == '__main__':
    main()
