#!/usr/bin/env python3
"""
359차: get_path_after_distance() 300m 캡 오버런(경로 반전) 버그 재현 + 수정 검증

배경 (WIP.md/FINDINGS.md 359차 참고):
  route 7bf8a00d14 seg7~10 (직선 고속도로) 에서 routeApexDist/routeApexSpeed가
  프레임마다 크게 요동(10<->95<->31<->89km/h)하고 routePathLen=3으로 고정되는
  증상 발견. naviPaths 원시좌표 분석 결과 dist=690m 지점에서 경로가 정확히
  반대방향으로 반전되어 dist=1050m까지 이어짐을 확인.

근본원인:
  carrot_man.py::get_path_after_distance() 가 closest_point ->
  coordinates[closest_index+1] 첫 세그먼트를 distance_m(호출부에서 300.0
  고정 캡) 체크 없이 무조건 추가한다. 직선 구간처럼 raw waypoint 간격이
  넓어(navd가 촘촘하지 않게 점을 줄 때) 첫 세그먼트 자체가 이미 300m를
  초과하면, 이어지는 루프의 remaining_distance(=distance_m-total_distance)가
  음수가 되고 ratio도 음수가 되어 보간점이 coord2 방향과 반대로
  외삽(extrapolation)된다.

이 스크립트는:
  1) OLD(버그) 버전과 NEW(수정) 버전의 get_path_after_distance()를 각각
     정의(NEW는 carrot_man.py 현재 코드를 verbatim 포팅, §27).
  2) 버그 재현 시나리오(690m sparse gap, 실측값과 근사) -- OLD는 반전,
     NEW는 정상 300m 캡을 assert.
  3) 회귀 방지 시나리오(정상 촘촘한 점, gap < 300m 다건) -- OLD/NEW 결과가
     바이트 단위로 동일함을 assert (§27 최소변경 원칙 검증).

실행: python3 sim_route_359_lookahead_overrun.py
"""
import math

ROUTE_LOOKAHEAD_M = 300.0  # carrot_man.py 호출부 고정 캡 (217차 이후)


# ---- carrot_man.py verbatim 포팅 (공통 helper, §27) ----
def haversine(lon1, lat1, lon2, lat2):
    R = 6371000  # Radius of Earth in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    distance = 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return distance


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

    closest_x = x1 + t * dx
    closest_y = y1 + t * dy

    return (closest_x, closest_y)


# ---- OLD (358차 이전, 버그) get_path_after_distance verbatim ----
def get_path_after_distance_OLD(start_index, coordinates, current_position, distance_m):
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


# ---- NEW (359차 수정, carrot_man.py 현재 코드 verbatim 포팅) ----
def get_path_after_distance_NEW(start_index, coordinates, current_position, distance_m):
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

        first_segment_distance = haversine(closest_point[0], closest_point[1], coordinates[closest_index + 1][0],
                                   coordinates[closest_index + 1][1])

        if first_segment_distance >= distance_m:
            ratio = distance_m / first_segment_distance if first_segment_distance > 0 else 0
            interpolated_lon = closest_point[0] + ratio * (coordinates[closest_index + 1][0] - closest_point[0])
            interpolated_lat = closest_point[1] + ratio * (coordinates[closest_index + 1][1] - closest_point[1])
            path_after_distance.append((interpolated_lon, interpolated_lat))
            total_distance = distance_m
        else:
            path_after_distance.append(coordinates[closest_index + 1])
            total_distance = first_segment_distance

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


def meters_to_deg_lon(m, lat_deg):
    return m / (111320.0 * math.cos(math.radians(lat_deg)))


def build_straight_sparse_route(lat0=37.5, lon0=127.0, gaps_m=(690, 360, 50, 50)):
    """직선(동쪽방향) 경로. 첫 gap(690m)이 차량 현재위치(coords[0]) 바로 다음
    점까지의 첫 세그먼트 거리가 됨 -- 실측(dist=690m 반전 시작, ~1050m까지
    이어짐) 재현 시나리오의 핵심(690+360=1050)."""
    coords = [(lon0, lat0)]
    lon = lon0
    for g in gaps_m:
        lon += meters_to_deg_lon(g, lat0)
        coords.append((lon, lat0))
    return coords


def build_straight_dense_route(lat0=37.5, lon0=127.0, n=40, gap_m=15):
    """정상(회귀 방지) 케이스: 촘촘한 점(간격 15m x 40개, 항상 300m 미만)."""
    coords = [(lon0, lat0)]
    lon = lon0
    for _ in range(n):
        lon += meters_to_deg_lon(gap_m, lat0)
        coords.append((lon, lat0))
    return coords


def path_total_span_m(path):
    """path_after_distance 리스트의 첫점->끝점 haversine 거리."""
    if len(path) < 2:
        return 0.0
    return haversine(path[0][0], path[0][1], path[-1][0], path[-1][1])


def max_dist_from_start(path):
    """path_after_distance 내 모든 점 중 시작점(path[0])으로부터 가장 먼
    haversine 거리. OLD 버그에서는 캡 없이 추가된 raw 점(예: 690m)이
    남아있어 distance_m(300m) 캡을 초과한다."""
    if len(path) < 2:
        return 0.0
    return max(haversine(path[0][0], path[0][1], p[0], p[1]) for p in path[1:])


def is_reversed(path, forward_lon_sign=1):
    """path_after_distance 내부에 진행방향(forward_lon_sign)과 반대로 가는
    세그먼트가 하나라도 있으면 반전으로 간주. 실제 버그는 캡 없이 추가된
    원거리점(예: 690m) 다음에 보간으로 캡된 근거리점(300m)이 이어지며
    경로가 국소적으로 뒤로 가는 현상이므로, 첫점-끝점만 비교하면 놓칠 수
    있다 -- 연속 세그먼트 단위로 검사한다."""
    for i in range(len(path) - 1):
        delta_lon = path[i + 1][0] - path[i][0]
        if (delta_lon * forward_lon_sign) < -1e-12:
            return True
    return False


def main():
    lat0 = 37.5
    current_position = (127.0, lat0)  # 시작점 바로 위(=start point)에 차량 위치

    print("=" * 70)
    print("시나리오 1: 버그 재현 (690m sparse gap, 직선 고속도로 실측 근사)")
    print("=" * 70)
    coords_bug = build_straight_sparse_route(lat0=lat0, lon0=127.0,
                                              gaps_m=(690, 360, 50, 50))
    old_path, old_idx, old_cp = get_path_after_distance_OLD(0, coords_bug, current_position, ROUTE_LOOKAHEAD_M)
    new_path, new_idx, new_cp = get_path_after_distance_NEW(0, coords_bug, current_position, ROUTE_LOOKAHEAD_M)

    old_span = path_total_span_m(old_path)
    new_span = path_total_span_m(new_path)
    old_maxdist = max_dist_from_start(old_path)
    new_maxdist = max_dist_from_start(new_path)
    old_rev = is_reversed(old_path)
    new_rev = is_reversed(new_path)

    print(f"OLD: {old_path}")
    print(f"OLD: path점수={len(old_path)} span={old_span:.1f}m max_dist={old_maxdist:.1f}m reversed={old_rev}")
    print(f"NEW: {new_path}")
    print(f"NEW: path점수={len(new_path)} span={new_span:.1f}m max_dist={new_maxdist:.1f}m reversed={new_rev}")

    # OLD: 캡 없이 추가된 raw 690m 점이 path 중간에 남아있고(캡 300m 초과),
    # 그 다음 보간으로 300m 지점으로 "되돌아가는" 반전이 재현되어야 함
    assert old_maxdist > ROUTE_LOOKAHEAD_M + 300, f"OLD 캡 초과가 예상보다 작음: {old_maxdist:.1f}m"
    assert old_rev, "OLD가 반전(경로 중 뒤로 가는 세그먼트)을 재현하지 못함"

    # NEW: 캡 초과 raw 점이 남지 않고, 반전도 없어야 하며, 최종 span/최대거리
    # 모두 300m 캡에 정확히(부동소수 오차 이내) 맞아야 함
    assert not new_rev, "NEW에서도 반전 발생 -- 수정 실패"
    assert new_maxdist <= ROUTE_LOOKAHEAD_M + 0.5, f"NEW가 300m 캡을 초과함: {new_maxdist:.1f}m"
    assert abs(new_span - ROUTE_LOOKAHEAD_M) < 0.5, f"NEW span이 300m 캡과 불일치: {new_span:.1f}m"
    print("PASS: OLD는 캡초과+반전 재현, NEW는 300m 캡 정상 동작(반전 없음)\n")

    print("=" * 70)
    print("시나리오 2: 회귀 방지 (정상 촘촘한 점, 모든 gap < 300m)")
    print("=" * 70)
    coords_normal = build_straight_dense_route(lat0=lat0, lon0=127.0, n=40, gap_m=15)
    old_path2, old_idx2, old_cp2 = get_path_after_distance_OLD(0, coords_normal, current_position, ROUTE_LOOKAHEAD_M)
    new_path2, new_idx2, new_cp2 = get_path_after_distance_NEW(0, coords_normal, current_position, ROUTE_LOOKAHEAD_M)

    print(f"OLD: path점수={len(old_path2)} span={path_total_span_m(old_path2):.2f}m")
    print(f"NEW: path점수={len(new_path2)} span={path_total_span_m(new_path2):.2f}m")

    assert old_idx2 == new_idx2, "closest_index 불일치"
    assert len(old_path2) == len(new_path2), "정상 케이스에서 path 길이 불일치 -- 회귀 발생"
    for a, b in zip(old_path2, new_path2):
        assert abs(a[0] - b[0]) < 1e-12 and abs(a[1] - b[1]) < 1e-12, "정상 케이스에서 좌표값 불일치 -- 회귀 발생"
    print("PASS: 정상(첫 세그먼트 < 300m) 케이스는 OLD/NEW 바이트 단위로 동일 -- 회귀 없음\n")

    print("=" * 70)
    print("전체 통과: 359차 수정이 버그 케이스를 고치면서 정상 케이스에 회귀 없음")
    print("=" * 70)


if __name__ == "__main__":
    main()
