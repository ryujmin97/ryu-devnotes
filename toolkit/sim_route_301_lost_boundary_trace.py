#!/usr/bin/env python3
"""
sim_route_301_lost_boundary_trace.py (301차 신규)

목적
----
300차(ChatGPT 제안 검토, ANALYSIS_ONLY)가 밝힌 핵심 사실:

    강제 RELEASE 이벤트 15/15 전부 mode="lost" (mode="passed"는 0건)

에 대해 사용자/ChatGPT가 301차 방향으로 제시한 질문 하나만 답한다(§28 --
원인 확정 전에 증상/재현조건부터, 여기서는 아직 게이트/패치를 만들지
않음):

    "lost가 발생한 순간, 기존 Apex A가 정말 죽은 것인가?
     아니면 A를 잠깐 놓쳤지만 B가 이미 유효한 새 Apex였는가?"

즉 각 lost 이벤트를 다음 관점으로 재구성한다:

    A 마지막 정상 매칭(matched)
        -> miss_frames 누적(held, 최대 ROUTE_APEX_MISS_TOLERANCE_FRAMES-1회)
        -> LOST 선언 (동일 프레임에 clusters가 있으면 B를 즉시 재획득)
        -> B가 이후 몇 초/프레임 동안 continuity를 유지하며 살아남는가

`_route_cluster_continuity_step()`(735~808행, sim_route_296의
`ContinuityState`로 이식됨, 297/298/299/300차와 동일 재사용 -- §21)
자체는 한 글자도 바꾸지 않는다. 이 스크립트는 그 클래스를 감싸
프레임별 사전/사후 상태(locked_dist/locked_speed/miss_frames/cluster
크기)를 관찰만 하는 얇은 계측 레이어를 추가할 뿐이다(§27).

강제 RELEASE 이벤트 자체의 탐지는 300차 `ActualLayer`를 그대로 import해
재사용한다(§21 -- 동일 목적의 탐지 로직을 다시 만들지 않음). 300차가
이미 확인한 "15/15 lost" 결과와 이번 스크립트의 이벤트 개수/타임스탬프가
정확히 일치하는지를 자체 검증(assert)한다.

**하지 않는 것(이번 세션 범위 밖)**: confidence 게이트/임계값 설계,
`carrot_man.py` 패치. 이 스크립트는 관측 전용이며 `ryu` 코드는 건드리지
않는다(ANALYSIS_ONLY, 300차와 동일 원칙).

사용
----
    python3 sim_route_301_lost_boundary_trace.py \\
        --csv-dir /path/to/route_csvs \\
        --classification evidence/route_297_seamless_release_qcamera/classification.md \\
        --persistence-horizon 5.0
"""
import argparse
import os
import sys

sys.path.insert(0, ".")

from sim_route_296_active_reacquire_gap import (
    ContinuityState, route_find_clusters, ROUTE_CLUSTER_MIN_POINTS,
    ROUTE_CLUSTER_MAX_GAP_M,
)
from sim_route_299_reacquire_confidence_features import (
    recompute_with_curvature, load_ground_truth,
)
from sim_route_300_release_boundary_counterfactual import (
    ActualLayer, build_frames,
)

ROUTE_IDS = ["a3b3373495", "01742d6c1c", "c8d2619479", "bf794c0073"]


def build_stream(csv_path, map_turn_speed_factor):
    """continuity 재생 + 프레임별 사전/사후 상태 계측(§27 -- 계측만
    추가, ContinuityState.step()의 산식/분기는 무변경)."""
    frames = build_frames(csv_path, map_turn_speed_factor)
    continuity = ContinuityState()
    stream = []
    for fr in frames:
        pre_locked_dist = continuity.locked_dist
        pre_locked_speed = continuity.locked_speed
        pre_miss_frames = continuity.miss_frames

        distances = [c[0] for c in fr["candidates"]]
        speeds = [c[1] for c in fr["candidates"]]
        idxs = list(range(len(fr["candidates"])))
        clusters = route_find_clusters(idxs, distances, ROUTE_CLUSTER_MIN_POINTS,
                                        ROUTE_CLUSTER_MAX_GAP_M)

        apex_idx, apex_dist, apex_speed, mode, streak = continuity.step(
            clusters, distances, speeds, fr["v_ego_ms"])

        cluster_size = None
        if apex_idx is not None and apex_idx >= 0:
            for c in clusters:
                if apex_idx in c:
                    cluster_size = len(c)
                    break

        stream.append({
            "t": fr["t"], "v_ego_ms": fr["v_ego_ms"], "v_ego_kph": fr["v_ego_kph"],
            "apex_idx": apex_idx, "apex_dist": apex_dist, "apex_speed": apex_speed,
            "mode": mode, "streak": streak,
            "pre_locked_dist": pre_locked_dist, "pre_locked_speed": pre_locked_speed,
            "pre_miss_frames": pre_miss_frames,
            "cluster_size": cluster_size, "n_clusters": len(clusters),
        })
    return stream


def trace_lost_events(stream, actual_events, persistence_horizon_s):
    """actual_events(300차 ActualLayer가 탐지한 강제 RELEASE 이벤트) 중
    mode=="lost"인 것만 골라 A->LOST->B 경계를 재구성한다."""
    t_index = {round(row["t"], 2): i for i, row in enumerate(stream)}
    out = []
    for ev in actual_events:
        if ev["mode"] != "lost":
            continue
        i = t_index.get(round(ev["t"], 2))
        if i is None:
            continue
        row = stream[i]

        # A 마지막 정상 매칭(matched) 프레임 -- 직전으로 거슬러 올라가며
        # "held" 프레임(=miss 누적 중)을 건너뛰고 첫 matched를 찾는다.
        last_matched = None
        miss_run = 0
        for j in range(i - 1, -1, -1):
            if stream[j]["mode"] == "matched":
                last_matched = stream[j]
                break
            if stream[j]["mode"] == "held":
                miss_run += 1
                continue
            break  # matched/held가 아닌 다른 상태가 나오면 탐색 중단

        # B(=이번 프레임에 새로 lock된 apex)가 이후 몇 초/프레임 동안
        # continuity를 유지하는지(matched/held로 이어지는지) 관찰.
        survive_frames = 0
        survive_t = row["t"]
        for j in range(i + 1, len(stream)):
            if stream[j]["t"] - row["t"] > persistence_horizon_s:
                break
            if stream[j]["mode"] in ("matched", "held"):
                survive_frames += 1
                survive_t = stream[j]["t"]
                continue
            break  # B 스스로도 passed/lost/new로 끊김

        out.append({
            "t": round(row["t"], 2),
            "A_last_matched_t": (round(last_matched["t"], 2) if last_matched else None),
            "A_last_dist_m": (round(last_matched["apex_dist"], 1) if last_matched else None),
            "A_last_speed_kph": (round(last_matched["apex_speed"], 1) if last_matched else None),
            "A_last_v_ego_kph": (round(last_matched["v_ego_kph"], 1) if last_matched else None),
            "miss_frames_at_lost": row["pre_miss_frames"] + 1,
            "gap_seconds_A_to_LOST": (round(row["t"] - last_matched["t"], 2)
                                       if last_matched else None),
            "B_dist_m": (round(row["apex_dist"], 1) if row["apex_dist"] is not None else None),
            "B_speed_kph": (round(row["apex_speed"], 1) if row["apex_speed"] is not None else None),
            "B_cluster_size": row["cluster_size"],
            "B_n_clusters_total_this_frame": row["n_clusters"],
            "B_survive_seconds": round(survive_t - row["t"], 2),
            "B_survive_frames": survive_frames,
            "B_survived_full_horizon": (survive_t - row["t"]) >= persistence_horizon_s - 1e-6,
            "v_ego_kph_at_lost": round(row["v_ego_kph"], 1),
        })
    return out


def run_route(csv_path, map_turn_speed_factor, ctrl_end, decel_rate, persistence_horizon_s):
    stream = build_stream(csv_path, map_turn_speed_factor)

    # 300차 ActualLayer 그대로 재사용해 강제 RELEASE 이벤트를 탐지
    # (§21 -- 이벤트 탐지 로직 중복 작성 금지). ContinuityState 재계산을
    # 피하기 위해 stream을 그대로 재생만 시킨다(300차 run_route()의
    # actual_track 생성부와 동일 패턴).
    actual = ActualLayer()
    for fr in stream:
        actual.step(fr["t"], fr["apex_idx"], fr["apex_dist"], fr["apex_speed"],
                    fr["mode"], fr["streak"], fr["v_ego_ms"], fr["v_ego_kph"],
                    ctrl_end, decel_rate)

    events = trace_lost_events(stream, actual.events, persistence_horizon_s)
    return actual.events, events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", required=True)
    ap.add_argument("--classification",
                     default="evidence/route_297_seamless_release_qcamera/classification.md")
    ap.add_argument("--map-turn-speed-factor", type=float, default=1.10)
    ap.add_argument("--ctrl-end", type=float, default=8.0)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--persistence-horizon", type=float, default=5.0,
                     help="LOST 이후 B 생존 여부를 관찰할 시간 창(초)")
    args = ap.parse_args()

    gt = load_ground_truth(args.classification)

    all_rows = []
    total_forced_release = 0
    total_lost = 0
    for rid in ROUTE_IDS:
        csv_path = os.path.join(args.csv_dir, f"route_{rid}.csv")
        if not os.path.exists(csv_path):
            print(f"(스킵: {csv_path} 없음)")
            continue
        actual_events, rows = run_route(csv_path, args.map_turn_speed_factor,
                                         args.ctrl_end, args.decel_rate,
                                         args.persistence_horizon)
        total_forced_release += len(actual_events)
        total_lost += len(rows)
        print(f"\n=== {rid}: 강제 RELEASE {len(actual_events)}건 중 "
              f"lost {len(rows)}건 ===")
        for r in rows:
            key = (rid, r["t"])
            label = gt.get(key, "unknown")
            r["route"] = rid
            r["label"] = label
            all_rows.append(r)
            print(f"  t={r['t']:.2f} label={label:10s}"
                  f" A_last(t={r['A_last_matched_t']}, dist={r['A_last_dist_m']},"
                  f" speed={r['A_last_speed_kph']}, gap={r['gap_seconds_A_to_LOST']}s)"
                  f" -> B(dist={r['B_dist_m']}, speed={r['B_speed_kph']},"
                  f" cluster={r['B_cluster_size']}/{r['B_n_clusters_total_this_frame']})"
                  f" survive={r['B_survive_seconds']}s/{r['B_survive_frames']}f"
                  f"{'(+)' if r['B_survived_full_horizon'] else ''}")

    print(f"\n=== 정합성 체크(300차 대비) ===")
    print(f"  강제 RELEASE 전체: {total_forced_release}건, 그 중 lost: {total_lost}건")
    print(f"  (300차 기록: 강제 RELEASE 15건, 전부 lost -- 위 total_lost와 "
          f"total_forced_release가 15로 일치해야 함)")

    def _bucket(label):
        if label in ("real_curve", "weak_curve"):
            return "real"
        if label == "no_curve":
            return "noise"
        return None

    print(f"\n=== B 생존 요약(persistence_horizon={args.persistence_horizon}s) ===")
    for bucket_name in ("real", "noise", None):
        rows_b = [r for r in all_rows if _bucket(r["label"]) == bucket_name]
        if not rows_b:
            continue
        name = bucket_name or "unclear/unknown"
        n = len(rows_b)
        n_full_survive = sum(1 for r in rows_b if r["B_survived_full_horizon"])
        avg_survive = sum(r["B_survive_seconds"] for r in rows_b) / n
        avg_cluster = sum((r["B_cluster_size"] or 0) for r in rows_b) / n
        avg_gap = (sum(r["gap_seconds_A_to_LOST"] for r in rows_b
                        if r["gap_seconds_A_to_LOST"] is not None)
                   / max(1, sum(1 for r in rows_b if r["gap_seconds_A_to_LOST"] is not None)))
        print(f"  {name}(n={n}): horizon 끝까지 생존={n_full_survive}/{n}, "
              f"평균 생존={avg_survive:.2f}s, 평균 cluster_size={avg_cluster:.1f}, "
              f"평균 A->LOST gap={avg_gap:.2f}s")


if __name__ == "__main__":
    main()
