#!/usr/bin/env python3
"""
133차: 131차에서 인라인으로만 했던 gpsLocation(1Hz) capnp 채널 추출을
재사용 가능한 toolkit 스크립트로 정식화.

배경: navRoute/navInstructionCarrot 채널엔 실제 navi 폴리라인 좌표가 없음
(131차 확인, navRoute count=0). 하지만 차량 자체 GPS는 gpsLocation
채널(1Hz, GpsLocationData)에 별도로 기록되며, extract_log.py의 20Hz
FIELDNAMES에는 포함돼 있지 않다. 이 스크립트는 route_dir(세그먼트
폴더들)를 순회하며 gpsLocation 이벤트만 별도 CSV로 뽑는다.

사용:
  python3 extract_gps.py <route_dir> <out.csv> [--repo /home/claude/ryu]

CSV 컬럼: t, seg, latitude, longitude, altitude, speed, bearingDeg,
          horizontalAccuracy
t는 extract_log.py와 동일하게 logMonoTime 기준 절대 초 단위라
route.csv와 직접 join 가능하다 (join 시 1Hz vs 20Hz라 가장 가까운
t로 매칭 필요).
"""
import argparse
import csv
import os
import sys

from decode_rlog import iter_events

FIELDNAMES = ["t", "seg", "latitude", "longitude", "altitude", "speed",
              "bearingDeg", "horizontalAccuracy"]


def extract_route(route_dir, out_csv, repo_dir):
    seg_dirs = sorted(
        d for d in os.listdir(route_dir)
        if os.path.isdir(os.path.join(route_dir, d))
        and os.path.exists(os.path.join(route_dir, d, "rlog.zst"))
    )
    if not seg_dirs:
        print(f"no segment dirs with rlog.zst found under {route_dir}", file=sys.stderr)
        return 0

    total = 0
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for seg in seg_dirs:
            rlog_path = os.path.join(route_dir, seg, "rlog.zst")
            n = 0
            for evt in iter_events(rlog_path, repo_dir=repo_dir):
                which = evt.which()
                if which not in ("gpsLocation", "gpsLocationExternal"):
                    continue
                gps = getattr(evt, which)
                t = evt.logMonoTime / 1e9
                writer.writerow({
                    "t": t, "seg": seg,
                    "latitude": gps.latitude, "longitude": gps.longitude,
                    "altitude": gps.altitude, "speed": gps.speed,
                    "bearingDeg": gps.bearingDeg,
                    "horizontalAccuracy": gps.horizontalAccuracy,
                })
                n += 1
            print(f"  {seg}: {n} gps rows", file=sys.stderr)
            total += n
    print(f"Wrote {total} rows to {out_csv}", file=sys.stderr)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_dir")
    ap.add_argument("out_csv")
    ap.add_argument("--repo", default="/home/claude/ryu")
    args = ap.parse_args()
    extract_route(args.route_dir, args.out_csv, args.repo)


if __name__ == "__main__":
    main()
