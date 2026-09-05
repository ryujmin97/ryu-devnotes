#!/usr/bin/env python3
"""
scan_route_far_apex_accel_freeze.py (246차 신규)

목적: "route apex가 수백 미터 밖에 있는데도 desiredSpeed가 vEgo에 거의
고정돼(min() 승자=route) 실제로 가속이 억제되는" 패턴을 extract_log.py
CSV에서 자동 탐지한다. 사용자 실차 보고("거리가 멀리 남음에도 라우트가
10이하, 주행중에 차가 안나감")를 계기로, 246차에서 carrot_man.py
STEP2 감속식(223/224차)이 `out_speed_ms = max(target_ms, v_ego_ms -
applied_decel*dt)` 형태로 매 프레임 "현재 vEgo에서 살짝 뺀 값"을
ceiling으로 쓰기 때문에, apex가 아무리 멀어도(eff_dist가 커서
required_decel이 작아도) ceiling이 vEgo를 살짝 밑도는 값에 자기참조적으로
묶여 vCruise/cam이 원하는 자유가속(desiredSpeed 급등)을 막는다는 가설을
실측 로그로 확인하기 위해 작성.

탐지 조건 (연속 프레임 구간):
  1. src == 'route' (route가 arbitration 승자)
  2. routeApexDist > --far-dist-m (기본 150m, "멀다"의 기준)
  3. vCruise - vEgo_kph > --cruise-gap-kph (기본 15kph, "차가 더 낼 수
     있는 여유가 충분히 있다"는 조건 -- 이미 목표속도 근처면 애초에
     가속 억제를 논할 이유가 없음)
  4. |routeOutSpeed - vEgo_kph| < --ceiling-track-kph (기본 2kph,
     "ceiling이 현재 속도에 거의 달라붙어 있다"는 조건)
위 4개를 모두 만족하는 프레임이 --min-duration-s(기본 2.0초) 이상
연속되면 "freeze episode"로 보고한다.

사용:
    python3 scan_route_far_apex_accel_freeze.py route.csv \
        [--far-dist-m 150] [--cruise-gap-kph 15] \
        [--ceiling-track-kph 2.0] [--min-duration-s 2.0]

출력: episode별 시작/끝 시각, 지속시간, apex_dist 범위, vEgo 범위,
vCruise, 시작/끝 apex_speed. 종료 코드는 항상 0(순수 리포트 도구).
"""
import sys
import csv
import argparse


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            yield row


def to_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def scan(path, far_dist_m, cruise_gap_kph, ceiling_track_kph, min_duration_s):
    episodes = []
    cur = None

    def flush():
        nonlocal cur
        if cur is not None:
            dur = cur["t_end"] - cur["t_start"]
            if dur >= min_duration_s:
                episodes.append({**cur, "dur": dur})
        cur = None

    for row in load_rows(path):
        t = to_float(row.get("t"))
        v_ego = to_float(row.get("vEgo"))
        v_cruise = to_float(row.get("vCruise"))
        src = row.get("src")
        apex_dist = to_float(row.get("routeApexDist"))
        apex_speed = to_float(row.get("routeApexSpeed"))
        out_speed = to_float(row.get("routeOutSpeed"))
        if None in (t, v_ego, v_cruise, apex_dist, apex_speed, out_speed):
            flush()
            continue
        v_ego_kph = v_ego * 3.6
        cond = (
            src == "route"
            and apex_dist > far_dist_m
            and (v_cruise - v_ego_kph) > cruise_gap_kph
            and abs(out_speed - v_ego_kph) < ceiling_track_kph
        )
        if cond:
            if cur is None:
                cur = {
                    "t_start": t, "t_end": t,
                    "vEgo0": v_ego_kph, "vEgo1": v_ego_kph,
                    "apexDist0": apex_dist, "apexDist1": apex_dist,
                    "apexSpeed0": apex_speed, "apexSpeed1": apex_speed,
                    "vCruise": v_cruise,
                }
            else:
                cur["t_end"] = t
                cur["vEgo1"] = v_ego_kph
                cur["apexDist1"] = apex_dist
                cur["apexSpeed1"] = apex_speed
        else:
            flush()
    flush()
    return episodes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--far-dist-m", type=float, default=150.0)
    ap.add_argument("--cruise-gap-kph", type=float, default=15.0)
    ap.add_argument("--ceiling-track-kph", type=float, default=2.0)
    ap.add_argument("--min-duration-s", type=float, default=2.0)
    args = ap.parse_args()

    episodes = scan(
        args.csv_path, args.far_dist_m, args.cruise_gap_kph,
        args.ceiling_track_kph, args.min_duration_s,
    )
    print(f"episodes found: {len(episodes)}")
    for e in episodes:
        print(
            f"t={e['t_start']:.1f}-{e['t_end']:.1f} (dur={e['dur']:.2f}s)  "
            f"vEgo {e['vEgo0']:.1f}->{e['vEgo1']:.1f}kph  "
            f"vCruise={e['vCruise']:.0f}  "
            f"apexDist {e['apexDist0']:.0f}->{e['apexDist1']:.0f}m  "
            f"apexSpeed {e['apexSpeed0']:.1f}->{e['apexSpeed1']:.1f}kph"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
