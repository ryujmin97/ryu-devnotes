#!/usr/bin/env python3
"""
sim_route_302_ab_gps_correlation.py (302차 신규)

목적
----
301차가 밝힌 15건의 A->LOST->B 경계 중, 시간적으로 연쇄된 3쌍
(#1->#2, #4->#5, #9->#10, 전부 a3b3373495)에 대해 "이전 이벤트의 B와
다음 이벤트의 A가 실제로 같은 물리적 커브인가"를 실측 GPS로 판정한다
(298차부터 이월된 미해결 항목).

방법(§27 -- 계측만 추가, 기존 산식 재사용)
----------------------------------------
1. carrotMan `naviPaths`의 각 포인트는 차량 로컬(ego) 프레임의 (x, y)
   직교좌표 + 누적 arclength d로 기록된다(`parse_navi_paths`,
   analysis_helpers.py 2335행, §21 재사용). apex 후보의 거리값(D)은
   301차 스크립트가 그대로 리포트한 A_last_dist_m/B_dist_m이며, 이
   값들은 naviPaths d 배열의 값(10m 간격)과 정확히 일치하므로
   `points[argmin(|distances-D|)]`로 해당 apex의 로컬 (x,y)를 그대로
   복원할 수 있다 -- 별도 재계산(§27 위반) 없이 원본 스트림에서 인덱스만
   찾는다.
2. 그 로컬 (x,y)를 절대 GPS로 옮기려면 그 순간 차량의 절대 위치+헤딩이
   필요하다. **carrotMan 자체 추정 위치/헤딩(`xPosLat/xPosLon/xPosAngle`)은
   이번 판정에 쓰지 않는다** -- 162차가 이미 회전 중 dead-reckoning으로
   헤딩이 최대 11초 고정되는 문제를 확인했기 때문(사용자 지시 반영).
   대신 `extract_gps.py`로 뽑은 실측 `gpsLocation`(1Hz, latitude/
   longitude/bearingDeg)에서 해당 프레임 t에 가장 가까운 1개 fix를
   찾아 그 lat/lon을 원점, bearingDeg를 회전각으로 쓴다.
3. 로컬 (x=전방, y=좌측 ISO 관례) -> 지역 ENU 변환:
       East  = x*sin(theta) - y*cos(theta)
       North = x*cos(theta) + y*sin(theta)
   (theta = bearingDeg, 진북 기준 시계방향). 위경도 변환은 평면근사
   (111,320 m/deg 위도, 경도는 cos(lat) 보정) -- 대상 거리가 최대
   ~300m 수준이라 이 근사의 오차는 <1m 수준으로 무시 가능.
4. A/B 절대좌표 간 haversine(compare_navpos_vs_gps.py 재사용, §21)으로
   직선거리를 계산하고, 판정표(SAME_CURVE/NEXT_CURVE/DIFFERENT/
   GPS_UNCERTAIN)를 적용한다.

한계(§28, 반드시 인지)
----------------------
- bearingDeg는 실측이지만 1Hz라 최대 0.5초 갭이 있을 수 있고, 급커브
  진입 구간에서는 course-over-ground 자체가 순간 회전각과 다를 수
  있다(요레이트 지연). horizontalAccuracy와 함께 판정 근거로 병기한다.
- naviPaths 로컬 (x,y)는 그 시점 HD맵 곡률 기반 경로이므로, 회전만
  적용하면 곡선 형태 자체는 보존된다(단일 회전은 형태를 왜곡하지
  않음) -- 다만 원점(gpsLocation)과 실제 카메라/네비 위치 사이 수 m
  오프셋(안테나 위치 등)은 보정하지 않는다.
- 이 스크립트는 판정만 하며 `carrot_man.py`는 건드리지 않는다
  (ANALYSIS_ONLY, §29).

사용
----
    python3 sim_route_302_ab_gps_correlation.py \\
        --csv-dir /home/claude/csvdir --gps-dir /home/claude \\
        --classification ../evidence/route_297_seamless_release_qcamera/classification.md
"""
import argparse
import csv
import math
import os
import sys

sys.path.insert(0, ".")

from analysis_helpers import parse_navi_paths
from sim_route_301_lost_boundary_trace import run_route, ROUTE_IDS
from sim_route_299_reacquire_confidence_features import load_ground_truth

# 연쇄 판정 임계값(§27 -- 최소 변경, 임의 조정 금지 없이 문서화된 기준만 사용)
SAME_CURVE_M = 15.0     # 이 이내면 사실상 같은 지점(GPS 오차 범위 포함)
NEXT_CURVE_M = 80.0     # 이 이내면 "바로 다음 커브"로 볼 수 있는 근접 거리
# 80m 초과는 DIFFERENT. horizontalAccuracy 평균이 임계값을 넘으면
# GPS_UNCERTAIN으로 강등(판정 신뢰 불가).
ACCURACY_UNCERTAIN_M = 15.0


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def load_gps(path):
    rows = []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                rows.append({
                    "t": float(row["t"]),
                    "lat": float(row["latitude"]),
                    "lon": float(row["longitude"]),
                    "bearing": float(row["bearingDeg"]),
                    "acc": float(row["horizontalAccuracy"]) if row["horizontalAccuracy"] else None,
                })
            except (ValueError, KeyError):
                continue
    rows.sort(key=lambda r: r["t"])
    return rows


def nearest_gps(gps_rows, t):
    if not gps_rows:
        return None
    best = min(gps_rows, key=lambda r: abs(r["t"] - t))
    return best, abs(best["t"] - t)


def project_local_to_gps(gps_fix, x, y):
    """로컬 ego(x=forward, y=left, ISO) -> 절대 lat/lon (평면 근사)."""
    theta = math.radians(gps_fix["bearing"])
    east = x * math.sin(theta) - y * math.cos(theta)
    north = x * math.cos(theta) + y * math.sin(theta)
    lat = gps_fix["lat"] + (north / 111320.0)
    lon = gps_fix["lon"] + (east / (111320.0 * math.cos(math.radians(gps_fix["lat"])) + 1e-9))
    return lat, lon


def find_local_xy(navi_paths_str, target_dist):
    points, distances = parse_navi_paths(navi_paths_str)
    if not points:
        return None
    best_i = min(range(len(distances)), key=lambda i: abs(distances[i] - target_dist))
    if abs(distances[best_i] - target_dist) > 15.0:
        return None  # 원본 포인트 목록에 해당 거리 근방이 없음(비정상)
    return points[best_i]


def load_navi_row_at_t(csv_path, target_t):
    """target_t와 가장 가까운(naviPaths 존재) row 하나를 돌려준다."""
    best_row, best_dt = None, None
    with open(csv_path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if not row.get("naviPaths"):
                continue
            try:
                t = float(row["t"])
            except (TypeError, ValueError):
                continue
            dt = abs(t - target_t)
            if best_dt is None or dt < best_dt:
                best_dt, best_row = dt, row
    return best_row


def classify(dist_m, acc_avg_m):
    if acc_avg_m is not None and acc_avg_m > ACCURACY_UNCERTAIN_M:
        return "GPS_UNCERTAIN"
    if dist_m <= SAME_CURVE_M:
        return "SAME_CURVE"
    if dist_m <= NEXT_CURVE_M:
        return "NEXT_CURVE"
    return "DIFFERENT"


def resolve_point(csv_path, gps_rows, t, dist_m):
    """이벤트의 (t, apex_dist)를 절대 GPS 좌표로 변환. 실패 시 None."""
    row = load_navi_row_at_t(csv_path, t)
    if row is None or dist_m is None:
        return None
    xy = find_local_xy(row["naviPaths"], dist_m)
    if xy is None:
        return None
    fix, dt_gps = nearest_gps(gps_rows, t)
    if fix is None:
        return None
    lat, lon = project_local_to_gps(fix, xy[0], xy[1])
    return {
        "lat": lat, "lon": lon, "gps_dt": round(dt_gps, 2),
        "gps_acc_m": fix["acc"], "gps_bearing": fix["bearing"],
        "local_xy": xy,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", required=True)
    ap.add_argument("--gps-dir", required=True, help="extract_gps.py 출력 CSV(gps_<route>.csv)가 있는 폴더")
    ap.add_argument("--classification",
                     default="../evidence/route_297_seamless_release_qcamera/classification.md")
    ap.add_argument("--map-turn-speed-factor", type=float, default=1.10)
    ap.add_argument("--ctrl-end", type=float, default=8.0)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--persistence-horizon", type=float, default=5.0)
    args = ap.parse_args()

    gt = load_ground_truth(args.classification)

    all_events = []  # (idx, route, label, event_dict)
    idx = 0
    for rid in ROUTE_IDS:
        csv_path = os.path.join(args.csv_dir, f"route_{rid}.csv")
        if not os.path.exists(csv_path):
            continue
        _actual, rows = run_route(csv_path, args.map_turn_speed_factor,
                                   args.ctrl_end, args.decel_rate,
                                   args.persistence_horizon)
        for r in rows:
            idx += 1
            label = gt.get((rid, r["t"]), "unknown")
            all_events.append((idx, rid, csv_path, label, r))

    print(f"=== 302차: 15건 이벤트에 A/B 절대 GPS 부여 ===\n")
    resolved = {}
    for idx, rid, csv_path, label, r in all_events:
        gps_rows = load_gps(os.path.join(args.gps_dir, f"gps_{rid}.csv"))
        a_pt = resolve_point(csv_path, gps_rows, r["A_last_matched_t"], r["A_last_dist_m"]) \
            if r["A_last_matched_t"] is not None else None
        b_pt = resolve_point(csv_path, gps_rows, r["t"], r["B_dist_m"])
        resolved[idx] = {"route": rid, "label": label, "row": r, "A": a_pt, "B": b_pt}
        a_str = f"({a_pt['lat']:.6f},{a_pt['lon']:.6f}, acc={a_pt['gps_acc_m']}m, gps_dt={a_pt['gps_dt']}s)" if a_pt else "N/A"
        b_str = f"({b_pt['lat']:.6f},{b_pt['lon']:.6f}, acc={b_pt['gps_acc_m']}m, gps_dt={b_pt['gps_dt']}s)" if b_pt else "N/A"
        print(f"#{idx:<2d} {rid:12s} t={r['t']:9.2f} label={label:10s} A={a_str}  B={b_str}")

    print(f"\n=== 연쇄 쌍 판정: 이전 이벤트 B -> 다음 이벤트 A ===\n")
    # 같은 route 내에서 시간상 인접한(gap이 작은) 쌍만 자동 후보로 잡는다.
    by_route = {}
    for idx, rid, csv_path, label, r in all_events:
        by_route.setdefault(rid, []).append(idx)

    pair_results = []
    for rid, idxs in by_route.items():
        idxs.sort(key=lambda i: resolved[i]["row"]["t"])
        for a_i, b_i in zip(idxs, idxs[1:]):
            prev = resolved[a_i]
            nxt = resolved[b_i]
            # 연쇄 여부는 "이전 이벤트의 B가 잡힌 시각(LOST t)" ->
            # "다음 이벤트의 A_last_matched_t"(=다음 이벤트가 벌어지기
            # 전, 그 A를 마지막으로 정상 추적하던 시각) 사이 간격으로
            # 판단해야 한다. 두 이벤트 자신의 LOST 시각끼리 비교하면
            # (예: #2 자체 LOST=325.61) 실제 연쇄 시점(319.32)을
            # 놓친다 -- 버그 수정, 초기 구현의 착오.
            nxt_a_t = nxt["row"]["A_last_matched_t"]
            if nxt_a_t is None:
                continue
            gap = nxt_a_t - prev["row"]["t"]
            if gap < 0 or gap > 10.0:
                continue  # 너무 멀리 떨어진 이벤트는 애초에 연쇄 후보가 아님
            if prev["B"] is None or nxt["A"] is None:
                verdict = "GPS_UNCERTAIN"
                dist_m = None
                acc_avg = None
            else:
                dist_m = haversine(prev["B"]["lon"], prev["B"]["lat"],
                                    nxt["A"]["lon"], nxt["A"]["lat"])
                accs = [x for x in (prev["B"]["gps_acc_m"], nxt["A"]["gps_acc_m"]) if x is not None]
                acc_avg = sum(accs) / len(accs) if accs else None
                verdict = classify(dist_m, acc_avg)
            pair_results.append((a_i, b_i, gap, dist_m, acc_avg, verdict))
            dist_str = f"{dist_m:.1f}m" if dist_m is not None else "N/A"
            acc_str = f"{acc_avg:.1f}m" if acc_avg is not None else "N/A"
            print(f"  #{a_i}.B -> #{b_i}.A  gap={gap:.2f}s  dist={dist_str}  "
                  f"gps_acc_avg={acc_str}  => {verdict}")

    return resolved, pair_results


if __name__ == "__main__":
    main()
