#!/usr/bin/env python3
"""
sim_route_303_ab_continuity_features.py (303차 신규)

목적
----
302차가 GPS로 확정한 3쌍의 SAME_CURVE 연쇄(#4.B->#5.A(6.8m),
#7.B->#8.A(9.5m), #9.B->#10.A(0.0m), 전부 a3b3373495)에 대해,
"같은 물리적 커브였다"를 넘어 "이 B를 A의 연속 track으로 승계해도
되는가"를 판단하기 위한 연속성 feature를 정량화한다(302차 다음 작업
2번, 사용자 제시 303차 방향 STEP1/STEP2).

방법(§27 -- 계측만 추가, 기존 산식/이벤트탐지 재사용)
----------------------------------------------------
1. 301차 `build_stream()`/`run_route()`(ContinuityState.step 무변경,
   §21)로 15건 이벤트와 전체 프레임 스트림을 그대로 재생.
2. 302차 `resolve_point()`/`load_gps()`/`project_local_to_gps()`/
   `haversine()`(§21)로 각 이벤트의 A_last/B에 절대 GPS+bearing 부여.
3. 이번 세션 신규 계측(§27):
   - 체인 쌍(prev.B -> next.A) 구간 전체를 프레임 단위로 dense하게
     나열(mode/apex_dist/apex_speed/candidate 개수/cluster_size/
     miss_frames) -- 301차는 이벤트별 요약값만 냈고 중간 matched 구간
     프레임별 흐름은 보지 않았음.
   - Δdistance/Δspeed/Δtime은 301차 이벤트 필드에서 바로 계산.
   - ΔGPS_bearing은 302차가 구했던 GPS fix의 bearingDeg 차이(원형
     wraparound 처리)로 신규 계산.
   - candidate 개수(그 프레임 fr["candidates"] 원본 길이, 클러스터링
     이전 raw point 수)는 300차 build_frames가 이미 만들어내는 값을
     그대로 노출만 함(§27 -- 재계산 아님).

**하지 않는 것(§33/§29)**: LOST 재정의/seamless switch 코드 설계(STEP3
이후, 다음 세션 논의), counterfactual 3방식 비교(STEP5, 이 세션은
"조건을 데이터로 찾는" 단계까지만 -- 사용자가 제시한 303차 방향 문서
결론과 동일), `carrot_man.py` 변경 없음(ANALYSIS_ONLY).

사용
----
    python3 sim_route_303_ab_continuity_features.py \\
        --csv-dir /home/claude/csvdir --gps-dir /home/claude
"""
import argparse
import math
import os
import sys

sys.path.insert(0, ".")

from sim_route_301_lost_boundary_trace import run_route, build_stream, ROUTE_IDS
from sim_route_302_ab_gps_correlation import (
    load_gps, resolve_point, haversine, classify,
    SAME_CURVE_M, NEXT_CURVE_M, ACCURACY_UNCERTAIN_M,
)
from sim_route_299_reacquire_confidence_features import load_ground_truth
from sim_route_300_release_boundary_counterfactual import build_frames


def build_ncand_by_t(csv_path, map_turn_speed_factor):
    """build_stream()이 노출하지 않는 "raw candidate 개수"(클러스터링
    이전, road_limit 미만 후보 총점 수)를 300차 build_frames()에서 t
    기준으로 재조회(§27 -- 새 계산이 아니라 이미 존재하는 fr["candidates"]
    길이를 t로 join만 함). build_stream()과 build_frames()는 동일한
    naviPaths 파싱 순서를 그대로 타므로 t가 1:1 대응된다."""
    frames = build_frames(csv_path, map_turn_speed_factor)
    return {round(fr["t"], 2): len(fr["candidates"]) for fr in frames}

# 302차가 확정한 3쌍(전부 a3b3373495, event index는 이 스크립트에서
# (route, t)로 재식별 -- 302차의 전역 idx(1~15)는 실행 순서에 의존하는
# 값이라 그대로 하드코딩하지 않고 매 실행마다 재계산한다).
CHAIN_PAIR_LABELS = {
    (578.36, 585.36): "#4->#5",
    (1001.06, 1006.76): "#7->#8",
    (1225.81, 1228.31): "#9->#10",
}
# 참고용(보류 건, STEP6): #1->#2 (319.06 -> 325.61, NEXT_CURVE 20.0m)


def bearing_delta(b1, b2):
    """두 bearingDeg(0~360, 진북 기준) 사이 최소 각도차(0~180)."""
    if b1 is None or b2 is None:
        return None
    d = abs(b1 - b2) % 360.0
    return min(d, 360.0 - d)


def frame_window(stream, t_start, t_end, pad_frames=2):
    """t_start~t_end(둘 다 포함) 구간의 스트림 프레임을 앞뒤로 pad_frames개
    여유를 두고 반환. dense 출력을 위한 순수 슬라이싱(§27 -- 재계산 없음)."""
    idxs = [i for i, fr in enumerate(stream) if t_start - 1e-6 <= fr["t"] <= t_end + 1e-6]
    if not idxs:
        return []
    lo = max(0, idxs[0] - pad_frames)
    hi = min(len(stream) - 1, idxs[-1] + pad_frames)
    return stream[lo:hi + 1]


def annotate_mode_boundary(fr, t_start, t_end):
    tags = []
    if abs(fr["t"] - t_start) < 1e-6:
        tags.append("<=prev.B(reacquire)")
    if abs(fr["t"] - t_end) < 1e-6:
        tags.append("<=next.LOST(reacquire frame)")
    return " ".join(tags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", required=True)
    ap.add_argument("--gps-dir", required=True)
    ap.add_argument("--classification",
                     default="../evidence/route_297_seamless_release_qcamera/classification.md")
    ap.add_argument("--map-turn-speed-factor", type=float, default=1.10)
    ap.add_argument("--ctrl-end", type=float, default=8.0)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--persistence-horizon", type=float, default=5.0)
    args = ap.parse_args()

    gt = load_ground_truth(args.classification)

    # route별 이벤트/스트림을 한 번씩만 계산해 재사용(§27)
    per_route = {}
    for rid in ROUTE_IDS:
        csv_path = os.path.join(args.csv_dir, f"route_{rid}.csv")
        if not os.path.exists(csv_path):
            continue
        stream = build_stream(csv_path, args.map_turn_speed_factor)
        _actual, rows = run_route(csv_path, args.map_turn_speed_factor,
                                   args.ctrl_end, args.decel_rate,
                                   args.persistence_horizon)
        ncand_by_t = build_ncand_by_t(csv_path, args.map_turn_speed_factor)
        per_route[rid] = {"csv_path": csv_path, "stream": stream, "rows": rows,
                           "ncand_by_t": ncand_by_t}

    events_by_t = {}  # (rid, t) -> row(301차 이벤트 dict)
    for rid, d in per_route.items():
        for r in d["rows"]:
            events_by_t[(rid, r["t"])] = r

    print("=" * 78)
    print("303차 STEP1/STEP2: A->LOST->B 연쇄 3쌍 프레임 상세 추적 + 연속성 feature")
    print("=" * 78)

    feature_rows = []
    for (t_prev, t_next), label in CHAIN_PAIR_LABELS.items():
        rid = "a3b3373495"  # 302차 확인: 4쌍 전부 이 route 내부
        d = per_route[rid]
        ev_prev = events_by_t.get((rid, t_prev))
        ev_next = events_by_t.get((rid, t_next))
        if ev_prev is None or ev_next is None:
            print(f"\n[{label}] 이벤트 매칭 실패(t_prev={t_prev}, t_next={t_next}) -- 스킵")
            continue

        gps_rows = load_gps(os.path.join(args.gps_dir, f"gps_{rid}.csv"))
        prevB = resolve_point(d["csv_path"], gps_rows, ev_prev["t"], ev_prev["B_dist_m"])
        nextA = resolve_point(d["csv_path"], gps_rows, ev_next["A_last_matched_t"],
                               ev_next["A_last_dist_m"])

        gap_s = ev_next["A_last_matched_t"] - ev_prev["t"]
        d_dist = (ev_next["A_last_dist_m"] - ev_prev["B_dist_m"]
                  if ev_next["A_last_dist_m"] is not None and ev_prev["B_dist_m"] is not None else None)
        d_speed = (ev_next["A_last_speed_kph"] - ev_prev["B_speed_kph"]
                   if ev_next["A_last_speed_kph"] is not None and ev_prev["B_speed_kph"] is not None else None)
        gps_dist_m = None
        gps_verdict = "GPS_UNCERTAIN"
        d_bearing = None
        if prevB and nextA:
            gps_dist_m = haversine(prevB["lon"], prevB["lat"], nextA["lon"], nextA["lat"])
            accs = [x for x in (prevB["gps_acc_m"], nextA["gps_acc_m"]) if x is not None]
            acc_avg = sum(accs) / len(accs) if accs else None
            gps_verdict = classify(gps_dist_m, acc_avg)
            d_bearing = bearing_delta(prevB["gps_bearing"], nextA["gps_bearing"])

        print(f"\n--- {label} (prev.B t={t_prev} -> next.A_last t={ev_next['A_last_matched_t']}, "
              f"next.LOST t={t_next}) ---")
        print(f"  Δtime(prev.B -> next.A_last)   = {gap_s:.2f}s")
        print(f"  Δdistance(apex, m)             = {d_dist:+.1f}m"
              f"  (prev.B={ev_prev['B_dist_m']}m, next.A_last={ev_next['A_last_dist_m']}m)")
        print(f"  Δspeed(apex, kph)               = {d_speed:+.1f}kph"
              f"  (prev.B={ev_prev['B_speed_kph']}, next.A_last={ev_next['A_last_speed_kph']})")
        print(f"  ΔGPS_position(haversine)        = {gps_dist_m:.1f}m => {gps_verdict}"
              if gps_dist_m is not None else "  ΔGPS_position                   = N/A(GPS_UNCERTAIN)")
        print(f"  ΔGPS_bearing(deg, wraparound)    = {d_bearing:.1f}deg" if d_bearing is not None else
              "  ΔGPS_bearing                     = N/A")
        print(f"  prev.B_cluster_size/candidates   = {ev_prev['B_cluster_size']}/"
              f"{ev_prev['B_n_clusters_total_this_frame']} clusters")
        print(f"  next.miss_frames_at_lost         = {ev_next['miss_frames_at_lost']}")
        print(f"  prev.B_survive_seconds(원 지표)  = {ev_prev['B_survive_seconds']}s"
              f"/{ev_prev['B_survive_frames']}f"
              f"{'(+full_horizon)' if ev_prev['B_survived_full_horizon'] else '(중도 이탈)'}")

        # 프레임 단위 dense 추적: prev의 B 재획득 프레임 ~ next의 LOST
        # 재획득 프레임까지, 그 사이 "matched로 이어졌는가/중간에 몇 번
        # 더 미스가 있었는가"를 원 스트림에서 직접 나열(§27).
        win = frame_window(d["stream"], t_prev, t_next, pad_frames=1)
        print(f"  [프레임 단위 흐름, {len(win)}프레임]")
        print(f"  {'t':>9s} {'mode':>7s} {'apex_dist':>9s} {'apex_speed':>10s} "
              f"{'n_cand':>6s} {'n_clus':>6s} {'clus_sz':>7s} {'miss':>4s}  tag")
        ncand_by_t = d["ncand_by_t"]
        for fr in win:
            tag = annotate_mode_boundary(fr, t_prev, t_next)
            n_cand = ncand_by_t.get(round(fr["t"], 2), -1)
            print(f"  {fr['t']:9.2f} {fr['mode']:>7s} "
                  f"{('%.1f' % fr['apex_dist']) if fr['apex_dist'] is not None else '-':>9s} "
                  f"{('%.1f' % fr['apex_speed']) if fr['apex_speed'] is not None else '-':>10s} "
                  f"{n_cand:6d} {fr['n_clusters']:6d} "
                  f"{(fr['cluster_size'] if fr['cluster_size'] is not None else '-'):>7} "
                  f"{fr['pre_miss_frames']:4d}  {tag}")

        feature_rows.append({
            "pair": label, "route": rid,
            "gap_s": round(gap_s, 2), "d_dist_m": d_dist, "d_speed_kph": d_speed,
            "gps_dist_m": round(gps_dist_m, 1) if gps_dist_m is not None else None,
            "gps_verdict": gps_verdict,
            "d_bearing_deg": round(d_bearing, 1) if d_bearing is not None else None,
            "prev_B_cluster_size": ev_prev["B_cluster_size"],
            "next_miss_frames_at_lost": ev_next["miss_frames_at_lost"],
            "prev_B_survive_s": ev_prev["B_survive_seconds"],
            "prev_B_survived_full_horizon": ev_prev["B_survived_full_horizon"],
        })

    print("\n" + "=" * 78)
    print("STEP2 요약표: 3쌍 연속성 feature 비교")
    print("=" * 78)
    hdr = f"{'pair':8s} {'gap_s':>6s} {'d_dist':>7s} {'d_speed':>8s} {'gps_m':>6s} {'verdict':>12s} {'d_bear':>7s} {'clus_sz':>7s} {'miss':>5s} {'B_surv_s':>9s}"
    print(hdr)
    for r in feature_rows:
        print(f"{r['pair']:8s} {r['gap_s']:6.2f} "
              f"{(r['d_dist_m'] if r['d_dist_m'] is not None else float('nan')):7.1f} "
              f"{(r['d_speed_kph'] if r['d_speed_kph'] is not None else float('nan')):8.1f} "
              f"{(r['gps_dist_m'] if r['gps_dist_m'] is not None else float('nan')):6.1f} "
              f"{r['gps_verdict']:>12s} "
              f"{(r['d_bearing_deg'] if r['d_bearing_deg'] is not None else float('nan')):7.1f} "
              f"{str(r['prev_B_cluster_size']):>7s} {r['next_miss_frames_at_lost']:5d} "
              f"{r['prev_B_survive_s']:9.2f}")

    return feature_rows


if __name__ == "__main__":
    main()
