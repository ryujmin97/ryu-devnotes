#!/usr/bin/env python3
"""
162차: carrotMan.xPosLat/xPosLon/xPosAngle (carrot_serv.py _update_gps()가
estimate_position()으로 데드레커닝한 ego 추정위치/헤딩, 20Hz)과
gpsLocation (차량 실측 GPS, 1Hz)을 시간 정렬해 거리(m) 이격을 계산한다.

배경: naviPaths/route 곡률이 특정 구간에서 이상하게 0(또는 목표 지점이 엉뚱한
방향)으로 나오면, carrot_navi_route()의 곡률/DP 계산 로직을 의심하기 전에
그 계산의 입력값(current_position/heading_deg) 자체가 실측 GPS/실제 진행
방향과 벌어져 있는지부터 이 스크립트로 배제해야 한다.

발견(162차): route aeeed9e4a5 seg3의 실제 급우회전 구간(t=6389~6393,
steer 최대 -121.9deg)에서 이 이격이 최대 ~28m까지 누적되고, xPosAngle이
회전 내내(약 11초) 296.0deg로 고정돼 있다가 회전 종료 직후 3.0deg로 한번에
점프하는 패턴을 확인. bearing_calculated가 CarrotNavi 앱의 ~1Hz nPosAngle을
그대로 쓰고, 그 사이는 직선 데드레커닝만 하기 때문
(carrot_serv.py::_update_gps()/estimate_position()).

사용:
  python3 compare_navpos_vs_gps.py <route_dir> [--repo /home/claude/ryu]
      [--t-start T] [--t-end T] [--out out.csv]

route_dir: 세그먼트 폴더들(각각 rlog.zst 포함)의 상위 폴더.
--t-start/--t-end 생략 시 전체 구간을 스캔.
--out 지정 시 CSV로 저장: t, seg, navLat, navLon, navAngle, gpsLat, gpsLon, dist_m

의존성: decode_rlog.py. extract_gps.py와 달리 gpsLocation을 자체 내장
추출하므로 별도 CSV 선추출이 필요 없다(route_dir만 주면 됨).

주의: gpsLocation이 1Hz라 매칭은 가장 가까운 t 기준(선형보간 아님) —
dist_m의 프레임간 개별 값보다 추세(지속 증가/유지)로 판단할 것.
"""
import argparse
import csv
import math
import os
import sys

from decode_rlog import iter_events


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _seg_dirs(route_dir):
    return sorted(
        d for d in os.listdir(route_dir)
        if os.path.isdir(os.path.join(route_dir, d))
        and os.path.exists(os.path.join(route_dir, d, "rlog.zst"))
    )


def extract_nav_and_gps(route_dir, repo_dir, t_start=None, t_end=None):
    nav_rows = []  # (t, seg, lat, lon, angle)
    gps_rows = []  # (t, seg, lat, lon)
    for seg in _seg_dirs(route_dir):
        rlog_path = os.path.join(route_dir, seg, "rlog.zst")
        n_nav, n_gps = 0, 0
        for evt in iter_events(rlog_path, repo_dir=repo_dir):
            which = evt.which()
            if which == "carrotMan":
                t = evt.logMonoTime / 1e9
                if (t_start is not None and t < t_start) or (t_end is not None and t > t_end):
                    continue
                cm = evt.carrotMan
                nav_rows.append((t, seg, cm.xPosLat, cm.xPosLon, cm.xPosAngle))
                n_nav += 1
            elif which in ("gpsLocation", "gpsLocationExternal"):
                t = evt.logMonoTime / 1e9
                if (t_start is not None and t < t_start) or (t_end is not None and t > t_end):
                    continue
                gps = getattr(evt, which)
                gps_rows.append((t, seg, gps.latitude, gps.longitude))
                n_gps += 1
        print(f"  {seg}: carrotMan={n_nav} gpsLocation={n_gps}", file=sys.stderr)
    return nav_rows, gps_rows


def nearest_gps(gps_rows_sorted, t):
    # gps_rows_sorted: list sorted by t. Simple linear-scan nearest match
    # is fine at these data sizes (1Hz, minutes-long routes).
    best = min(gps_rows_sorted, key=lambda g: abs(g[0] - t))
    return best


def compare(route_dir, repo_dir, t_start=None, t_end=None, out_csv=None):
    nav_rows, gps_rows = extract_nav_and_gps(route_dir, repo_dir, t_start, t_end)
    if not gps_rows:
        print("gpsLocation 이벤트 없음 -- 비교 불가", file=sys.stderr)
        return []
    gps_rows.sort()

    results = []  # (t, seg, navLat, navLon, navAngle, gpsLat, gpsLon, dist_m)
    for t, seg, lat, lon, angle in nav_rows:
        if lat == 0 or lon == 0:
            continue
        gt, gseg, glat, glon = nearest_gps(gps_rows, t)
        dist = haversine(lon, lat, glon, glat)
        results.append((t, seg, lat, lon, angle, glat, glon, dist))

    if not results:
        print("매칭된 carrotMan/gps 쌍 없음", file=sys.stderr)
        return []

    dists = [r[7] for r in results]
    print(
        f"\ndist_m 요약: min={min(dists):.1f} max={max(dists):.1f} "
        f"mean={sum(dists) / len(dists):.1f} (n={len(dists)})",
        file=sys.stderr,
    )
    print(
        "주의: dist_m이 시간에 따라 지속적으로 증가하는 구간은 "
        "estimate_position()의 직선 데드레커닝이 실제 회전을 못 따라가고 "
        "있다는 신호(162차 패턴). 순간적 튐(1개 프레임)은 gpsLocation 1Hz "
        "보간 오차일 수 있어 추세로만 판단할 것.",
        file=sys.stderr,
    )

    if out_csv:
        with open(out_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "seg", "navLat", "navLon", "navAngle", "gpsLat", "gpsLon", "dist_m"])
            for row in results:
                w.writerow(row)
        print(f"Wrote {len(results)} rows to {out_csv}", file=sys.stderr)

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_dir")
    ap.add_argument("--repo", default="/home/claude/ryu")
    ap.add_argument("--t-start", type=float, default=None)
    ap.add_argument("--t-end", type=float, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    compare(args.route_dir, args.repo, args.t_start, args.t_end, args.out)


if __name__ == "__main__":
    main()
