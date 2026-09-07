#!/usr/bin/env python3
"""
sim_route_304_navipaths_gap_audit.py (304차 신규)

목적
----
303차가 a3b3373495 #4->#5 구간에서 발견한 "naviPaths 기반 프레임이
2초대로 점프하는" 신규 이슈(FINDINGS.md 303차)의 원인을 코드 레벨로
확정한다. 303차는 "build_frames()가 naviPaths 빈 값 또는
nRoadLimitSpeed<=0인 행을 건너뛰기 때문으로 추정"이라고만 적었다 --
이번 세션은 그 추정을 원본 CSV 실측으로 검증한다(§28 원칙:
추정 -> 실측 확정).

방법
----
원본 route CSV를 그대로(= build_frames() 필터링 이전) 순회하며 각 행을
naviPaths 유무 / nRoadLimitSpeed 값 / naviPointsActive / navdActive /
dtRouteInactive / routeSource 기준으로 분류해서 원인을 좁힌다. 300차
build_frames()의 두 skip 조건(navi 없음, road_limit<=0)을 그대로
재현해서 KEEP/DROP 판정도 함께 낸다(로직은 300차 원본과 100% 동일,
계측만 추가 -- §27).

사용법
------
    python3 sim_route_304_navipaths_gap_audit.py <route.csv> [--min-gap 1.0]

출력
----
1. naviPaths가 비어있는(N) 연속 구간(run)을 전부 나열 -- 시작/끝 시각,
   길이(초), 프레임 수.
2. --min-gap(기본 1.0초) 이상인 run에 대해서만 naviPointsActive/
   navdActive/dtRouteInactive/routeSource/평균 vEgo/추정 이동거리를
   함께 출력 -- 182차가 다룬 "navi_points_active 자체가 False로
   떨어지는" 유형과, naviPointsActive=True인 채로 naviPaths만 비는
   이번 유형을 구분하기 위함.
3. 요약: road_limit<=0 발생 횟수(0이어야 정상, 300차 두 번째 skip
   조건이 실제로는 이 route에서 한 번도 발동하지 않았음을 확인하는 용도).
"""
import argparse
import csv
import sys


def build_frames_reasons(csv_path):
    """300차 build_frames()와 100% 동일한 KEEP/DROP 판정을 각 행에
    부여해서 반환(§27 -- 로직 자체는 절대 변경하지 않고 계측만 추가).
    """
    rows = []
    road_limit_bad = 0
    with open(csv_path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                t = float(row["t"])
            except (ValueError, TypeError):
                continue
            navi = row.get("naviPaths", "")
            reason = "KEEP"
            if not navi:
                reason = "DROP:NAVI_EMPTY"
            else:
                try:
                    _v = float(row["vEgo"])
                    rl = float(row["nRoadLimitSpeed"])
                except (ValueError, TypeError):
                    reason = "DROP:PARSE_FLOAT_FAIL"
                    rl = None
                else:
                    if rl <= 0:
                        reason = "DROP:ROAD_LIMIT<=0"
                        road_limit_bad += 1
            row["_t"] = t
            row["_reason"] = reason
            rows.append(row)
    return rows, road_limit_bad


def find_navi_empty_runs(rows, min_gap):
    runs = []
    cur_start = None
    cur_rows = []
    for row in rows:
        state = "Y" if row.get("naviPaths", "") else "N"
        if state == "N":
            if cur_start is None:
                cur_start = row["_t"]
            cur_rows.append(row)
        else:
            if cur_start is not None:
                dur = cur_rows[-1]["_t"] - cur_start
                if dur >= min_gap:
                    runs.append((cur_start, cur_rows[-1]["_t"], dur, cur_rows))
                cur_start = None
                cur_rows = []
    if cur_start is not None:
        dur = cur_rows[-1]["_t"] - cur_start
        if dur >= min_gap:
            runs.append((cur_start, cur_rows[-1]["_t"], dur, cur_rows))
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--min-gap", type=float, default=1.0)
    args = ap.parse_args()

    rows, road_limit_bad = build_frames_reasons(args.csv_path)
    print(f"총 행수: {len(rows)}, nRoadLimitSpeed<=0 행수: {road_limit_bad}")
    print(f"(road_limit<=0 == 0 이면, 300차 build_frames()의 두 번째 skip "
          f"조건은 이 route에서 발동하지 않았다는 뜻)\n")

    runs = find_navi_empty_runs(rows, args.min_gap)
    print(f"naviPaths 빈 구간(>= {args.min_gap}s) 개수: {len(runs)}\n")

    for s, e, dur, run_rows in runs:
        vs = [float(r["vEgo"]) * 3.6 for r in run_rows]
        avg_v = sum(vs) / len(vs)
        est_dist = avg_v / 3.6 * dur
        npa_vals = {r.get("naviPointsActive") for r in run_rows}
        nda_vals = {r.get("navdActive") for r in run_rows}
        dri_vals = {r.get("dtRouteInactive") for r in run_rows}
        src_vals = {r.get("routeSource") for r in run_rows}
        print(f"t={s:9.3f} -> {e:9.3f}  dur={dur:5.2f}s  n={len(run_rows):4d}  "
              f"avg_vEgo={avg_v:5.1f}kph  est_dist={est_dist:5.1f}m")
        print(f"    naviPointsActive={npa_vals}  navdActive={nda_vals}  "
              f"dtRouteInactive={dri_vals}  routeSource={src_vals}")


if __name__ == "__main__":
    main()
