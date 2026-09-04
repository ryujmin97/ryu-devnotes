#!/usr/bin/env python3
"""
scan_route_vturn_handoff_ratio.py (240cha, 신규)

목적: "route→vturn handoff ratio" 실측 지시서(2026-09-05, 사용자 검증지시)
1~2번 -- 실차 로그에서 route가 실제로 vturn에게 커브 감속을 넘기는 시점의
apex_speed/vEgo 비율 분포를 계측한다.

**중요 -- 이 스크립트를 쓰기 전에 반드시 read**:
`check_device_build.py`로 이번 세션 업로드된 11개 로그 전부를 확인한 결과,
전부 223차(`ee1f5f8`, 무상태 감속식+route_active 상태기계, ROUTE_RELEASE_HOLD_S
신설) **이전** 빌드(179차 후속2 ~ 221차, 전부 dirty=True)에서 채록됨.
즉:
  - 2초 hold(`ROUTE_RELEASE_HOLD_S`)는 이 로그들 어디에도 존재하지 않는
    코드 경로다 -- 지시서 4/5번(hold 검증)은 이 로그로는 **원천적으로
    검증 불가**.
  - 234~237차가 논의한 severity gate(`ROUTE_SEVERITY_GATE_RATIO`)도
    이 로그들에는 없다 -- 즉 여기서 관측되는 "route->vturn 전환"은 gate로
    인한 인위적 조기소거가 섞이지 않은, 순수 물리적 전환(route가 자기
    apex에 도달하거나, 혹은 그 이전 다른 사유로 자연 릴리즈되는 시점)이다.
  - 이 스크립트는 naviPaths 재구성(현재/최신 곡률 로직, 버전 무관)과
    실측 vEgo/vTurnSpeed/src(control arbitration 실제 결과)를 대조하는
    구조라서 recompute 자체는 유효하지만, "src가 route에서 vturn으로
    바뀐 시점"의 물리적 의미가 234~239차가 논의해온 "severity gate로
    인한 자기소거/재게이트 리밋사이클"과는 **다른 현상**임을 반드시
    인지할 것 (FINDINGS.md 240차 CRITICAL 참고).

재사용: candidate 재구성은 sim_route_234_spatial_apex_continuity.py의
build_speeds_distances()/analysis_helpers.recompute_route_curvature_speed()
그대로 사용(§21, 신규 재구현 안 함). gate/cluster/continuity(stage1~3)는
이 스크립트의 목적(순수 handoff ratio 실측)과 무관하므로 적용하지 않고
stage0(현재 배포 코드 후보 필터, nRoadLimitSpeed 기준)만 사용한다.

정의:
  - "route episode": src=='route'가 N프레임(기본 3, ~150ms) 이상 연속된 구간.
  - "handoff": route episode 종료 직후 src=='vturn'으로 전환되고, 전환 후
    HANDOFF_CONFIRM_WINDOW_S(기본 2.0s) 이내에 실측 vTurnSpeed가 handoff
    시점의 recomputed apex_speed와 HANDOFF_CONFIRM_TOL_KPH(기본 15kph)
    이내로 수렴하는 경우만 "확인된 handoff"로 채택(239차 예비분석과 동일
    기준). 단순히 src 라벨 한 프레임만 보고 판단하지 않는다(지시서 원칙).
  - ratio = recomputed apex_speed(핸드오프 직전 마지막 route 프레임 기준) /
    그 시점 vEgo(kph).
  - apex_dist도 함께 기록 -- ratio가 낮아도 apex_dist가 이미 0에 가까우면
    "사전감속 후 이른 핸드오프"가 아니라 "apex 도달 후 정상 릴리즈"일 수
    있으므로 별도 표시(HANDOFF_NEAR_APEX_M, 기본 15m 이내면 near_apex=True).

사용:
    python3 scan_route_vturn_handoff_ratio.py <route1.csv> [<route2.csv> ...] \\
        [--confirm-window 2.0] [--confirm-tol 15.0] [--near-apex-m 15.0] \\
        [--min-episode-frames 3] [--json out.json]
"""
import argparse
import csv
import json
import statistics
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

MACRO_SAMPLE = 4
FINE_SAMPLE = 1
FLOOR_THRESHOLD = 0.001

HANDOFF_CONFIRM_WINDOW_S = 2.0
HANDOFF_CONFIRM_TOL_KPH = 15.0
HANDOFF_NEAR_APEX_M = 15.0
MIN_EPISODE_FRAMES = 3


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_speeds_distances(navi_paths_str):
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < FINE_SAMPLE * 2 + 1:
        return [], []
    merged = recompute_route_curvature_speed(
        points, distances, sample=MACRO_SAMPLE, sample_fine=FINE_SAMPLE,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD,
    )
    if not merged:
        return [], []
    return [m[0] for m in merged], [m[2] for m in merged]


def gate_base_kph(row):
    raw = row.get("nRoadLimitSpeed", "")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0 else 200.0


def nearest_candidate(dists, speeds, gate_kph):
    best = None
    for i in range(len(speeds)):
        if speeds[i] < gate_kph:
            if best is None or dists[i] < dists[best]:
                best = i
    return best


def safe_float(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def scan_file(path, args):
    rows = load_csv(path)
    frames = []
    for row in rows:
        t = safe_float(row.get("t"), 0.0)
        v_ego_ms = safe_float(row.get("vEgo"), 0.0) or 0.0
        v_ego_kph = v_ego_ms * 3.6
        dists, speeds = build_speeds_distances(row.get("naviPaths", ""))
        gate_kph = gate_base_kph(row)
        idx = nearest_candidate(dists, speeds, gate_kph) if speeds else None
        apex_speed = speeds[idx] if idx is not None else None
        apex_dist = dists[idx] if idx is not None else None
        frames.append({
            "t": t,
            "v_ego_kph": v_ego_kph,
            "apex_speed": apex_speed,
            "apex_dist": apex_dist,
            "vTurnSpeed": safe_float(row.get("vTurnSpeed")),
            "desiredSpeed": safe_float(row.get("desiredSpeed")),
            "src": row.get("src", ""),
        })

    # route episodes
    episodes = []
    cur = []
    for i, f in enumerate(frames):
        if f["src"] == "route":
            cur.append(i)
        else:
            if len(cur) >= args.min_episode_frames:
                episodes.append(cur)
            cur = []
    if len(cur) >= args.min_episode_frames:
        episodes.append(cur)

    handoffs = []
    for ep in episodes:
        last_idx = ep[-1]
        if last_idx + 1 >= len(frames):
            continue
        nxt = frames[last_idx + 1]
        if nxt["src"] != "vturn":
            continue  # route->vturn 직접 전환만 (route->cam/road/bump 등은 제외)
        last = frames[last_idx]
        if last["apex_speed"] is None or last["v_ego_kph"] <= 1.0:
            continue

        # confirm window 내 vTurnSpeed 수렴 확인
        t0 = nxt["t"]
        converged = False
        conv_t = None
        for f2 in frames[last_idx + 1:]:
            if f2["t"] - t0 > args.confirm_window:
                break
            if f2["src"] != "vturn":
                break
            if f2["vTurnSpeed"] is not None and abs(f2["vTurnSpeed"] - last["apex_speed"]) <= args.confirm_tol:
                converged = True
                conv_t = f2["t"]
                break

        ratio = last["apex_speed"] / max(last["v_ego_kph"], 1.0)
        handoffs.append({
            "file": path,
            "t_handoff": t0,
            "v_ego_kph": last["v_ego_kph"],
            "apex_speed": last["apex_speed"],
            "apex_dist": last["apex_dist"],
            "vTurnSpeed_at_handoff": nxt["vTurnSpeed"],
            "desiredSpeed_at_handoff": nxt["desiredSpeed"],
            "ratio": ratio,
            "confirmed": converged,
            "confirm_t": conv_t,
            "near_apex": (last["apex_dist"] is not None and last["apex_dist"] <= args.near_apex_m),
        })
    return handoffs


def percentile(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--confirm-window", type=float, default=HANDOFF_CONFIRM_WINDOW_S, dest="confirm_window")
    ap.add_argument("--confirm-tol", type=float, default=HANDOFF_CONFIRM_TOL_KPH, dest="confirm_tol")
    ap.add_argument("--near-apex-m", type=float, default=HANDOFF_NEAR_APEX_M, dest="near_apex_m")
    ap.add_argument("--min-episode-frames", type=int, default=MIN_EPISODE_FRAMES, dest="min_episode_frames")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    all_handoffs = []
    for path in args.csvs:
        hs = scan_file(path, args)
        all_handoffs.extend(hs)
        print(f"{path}: route episode {sum(1 for h in hs)}건 route->vturn 직접전환 감지 "
              f"(confirmed={sum(1 for h in hs if h['confirmed'])})")

    confirmed = [h for h in all_handoffs if h["confirmed"]]
    ratios_all = [h["ratio"] for h in all_handoffs]
    ratios_conf = [h["ratio"] for h in confirmed]
    ratios_conf_far = [h["ratio"] for h in confirmed if not h["near_apex"]]

    print(f"\n=== 전체 route->vturn 전환 후보: {len(all_handoffs)}건 ===")
    print(f"=== confirmed(2s내 vTurnSpeed 수렴): {len(confirmed)}건 ===")
    print(f"=== confirmed & near_apex=False(apex_dist>{args.near_apex_m}m, 순수 사전감속 핸드오프로 추정): {len(ratios_conf_far)}건 ===")

    def report(label, vals):
        if not vals:
            print(f"{label}: 표본 없음")
            return
        print(f"{label}: n={len(vals)} min={min(vals):.3f} median={statistics.median(vals):.3f} "
              f"mean={statistics.mean(vals):.3f} max={max(vals):.3f} "
              f"P10={percentile(vals,10):.3f} P25={percentile(vals,25):.3f} "
              f"P50={percentile(vals,50):.3f} P75={percentile(vals,75):.3f} P90={percentile(vals,90):.3f}")

    report("ratio(all candidates)", ratios_all)
    report("ratio(confirmed)", ratios_conf)
    report("ratio(confirmed, far-from-apex only)", ratios_conf_far)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(all_handoffs, f, indent=2, default=str)
        print(f"\nJSON dump: {args.json}")


if __name__ == "__main__":
    main()
