#!/usr/bin/env python3
"""
sim_route_261_ratio_threshold_tradeoff.py (261차 신규)

목적: 260차 계속2가 확인한 magnitude_ratio(macro/fine cross-scale)
신호의 실제 threshold 후보값을 사용자가 판단할 수 있도록, persistence
(streak)와 ratio를 "같은 pass에서 동시에" 계측해(260차 계속2는 두 스크립트를
따로 돌려 t/dist join, tolerance 5m로 근사 매칭했음 -- 이번엔 조인오차
자체를 없앰) streak 구간별 ratio 분포와, 후보 threshold별
"streak=1(미검증 신규 후보)이 그 threshold를 통과해버리는 비율"(오탐 위험)
vs "streak20+(이미 확실한 실제 커브)가 통과하는 비율"(recall)을 표로 낸다.

재사용: sim_route_260_confidence_signals.py의 MultiTrackContinuity/Track/
gate_candidates/find_clusters 그대로. 여기에 sim_route_260_gyesok2_...의
macro/fine 독립 계산(cross_scale_consistency)을 프레임 단위 신호에 추가.

사용:
    python3 sim_route_261_ratio_threshold_tradeoff.py <route.csv> [<route2.csv> ...] \
        --thresholds 0.45 0.5 0.55 0.6 0.65 0.7
"""
import argparse
import csv
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

MACRO_SAMPLE = 4
FINE_SAMPLE = 1
FLOOR_THRESHOLD = 0.001
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
CONTINUITY_MATCH_TOLERANCE_M = 15.0
MISS_TOLERANCE_FRAMES = 3


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_gating_fine_pure_macro(navi_paths_str):
    """gating/streak용 candidate는 실제 프로덕션과 동일한 merged(sample=4,
    sample_fine=1) 재구성을 쓴다(sim_route_260_confidence_signals.py와
    동일 -- streak 통계가 이 후보 집합 기준으로 이미 보고되어 있으므로
    비교 가능하게 맞춤). ratio 계산용 순수 fine/macro는 별도로 만든다
    (gyesok2 방식, merge 안 함)."""
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < 2 * 2 + 1:
        return None
    gating = recompute_route_curvature_speed(
        points, distances, sample=MACRO_SAMPLE, sample_fine=FINE_SAMPLE,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD)
    pure_fine = recompute_route_curvature_speed(
        points, distances, sample=FINE_SAMPLE, sample_fine=None,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD)
    pure_macro = recompute_route_curvature_speed(
        points, distances, sample=MACRO_SAMPLE, sample_fine=None,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD)
    if not gating or not pure_fine or not pure_macro:
        return None
    return gating, pure_fine, pure_macro


def nearest_point(arr, dist):
    return min(arr, key=lambda m: abs(m[0] - dist))


def ratio_at(dist, pure_fine, pure_macro):
    _, fine_curv, _ = nearest_point(pure_fine, dist)
    _, macro_curv, _ = nearest_point(pure_macro, dist)
    if abs(fine_curv) < FLOOR_THRESHOLD or abs(macro_curv) < FLOOR_THRESHOLD:
        return None
    raw = abs(macro_curv) / abs(fine_curv)
    return min(raw, 2.0), raw


def gate_base_kph(row, v_ego_kph):
    raw = row.get("nRoadLimitSpeed", "")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0 else v_ego_kph


def gate_candidates(speeds, threshold):
    return [k for k in range(len(speeds)) if speeds[k] <= threshold]


def find_clusters(idxs, dists, min_points, max_gap_m):
    if not idxs:
        return []
    clusters = []
    cur = [idxs[0]]
    for i in idxs[1:]:
        if dists[i] - dists[cur[-1]] <= max_gap_m:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_points]


class Track:
    __slots__ = ("last_dist", "streak", "miss_frames", "id")
    _next_id = 1

    def __init__(self, dist):
        self.last_dist = dist
        self.streak = 1
        self.miss_frames = 0
        self.id = Track._next_id
        Track._next_id += 1


class MultiTrackContinuity:
    def __init__(self):
        self.tracks = []

    def step(self, clusters, dists, v_ego_ms, dt):
        results = []
        used_track_ids, used_cluster_ids = set(), set()
        candidates = []
        for track in self.tracks:
            predicted = track.last_dist - v_ego_ms * dt
            if predicted <= 0:
                continue
            for ci, c in enumerate(clusters):
                idx = c[0]
                err = abs(dists[idx] - predicted)
                if err <= CONTINUITY_MATCH_TOLERANCE_M:
                    candidates.append((err, track, ci))
        candidates.sort(key=lambda x: x[0])
        for err, track, ci in candidates:
            if id(track) in used_track_ids or ci in used_cluster_ids:
                continue
            used_track_ids.add(id(track))
            used_cluster_ids.add(ci)
            idx = clusters[ci][0]
            track.last_dist = dists[idx]
            track.streak += 1
            track.miss_frames = 0
            results.append((clusters[ci], track, False))

        alive = []
        for track in self.tracks:
            if id(track) in used_track_ids:
                alive.append(track)
                continue
            track.miss_frames += 1
            if track.miss_frames < MISS_TOLERANCE_FRAMES:
                alive.append(track)

        for ci, c in enumerate(clusters):
            if ci in used_cluster_ids:
                continue
            idx = c[0]
            track = Track(dists[idx])
            alive.append(track)
            results.append((c, track, True))

        self.tracks = alive
        return results


def replay(rows):
    mtc = MultiTrackContinuity()
    frame_signals = []
    prev_t = None
    for row in rows:
        t = float(row["t"])
        dt = (t - prev_t) if prev_t is not None else 0.05
        dt = max(0.001, min(dt, 0.5))
        prev_t = t

        if not row.get("vEgo"):
            continue
        v_ego_ms = float(row["vEgo"])
        v_ego_kph = v_ego_ms * 3.6

        built = build_gating_fine_pure_macro(row.get("naviPaths", ""))
        if not built:
            continue
        gating, pure_fine, pure_macro = built
        gate_dists = [m[0] for m in gating]
        gate_speeds = [m[2] for m in gating]

        gate_base = gate_base_kph(row, v_ego_kph)
        c0 = gate_candidates(gate_speeds, gate_base)
        clusters = find_clusters(c0, gate_dists, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        if not clusters:
            continue

        matched = mtc.step(clusters, gate_dists, v_ego_ms, dt)
        for cluster, track, is_new in matched:
            idx = cluster[0]
            got = ratio_at(gate_dists[idx], pure_fine, pure_macro)
            if got is None:
                continue
            ratio, raw = got
            frame_signals.append({
                "t": t, "track_id": track.id, "streak": track.streak,
                "ratio": ratio, "raw": raw,
            })
    return frame_signals


def bucket(streak):
    if streak == 1:
        return "streak=1"
    if streak <= 5:
        return "streak2-5"
    if streak <= 20:
        return "streak6-20"
    return "streak20+"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_paths", nargs="+")
    ap.add_argument("--thresholds", type=float, nargs="+",
                     default=[0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70])
    args = ap.parse_args()

    all_signals = []
    for path in args.csv_paths:
        rows = load_csv(path)
        sig = replay(rows)
        print(f"{path}: {len(rows)}행 -> (frame,cluster,ratio판정가능) {len(sig)}건")
        all_signals.extend(sig)

    print(f"\n=== 합산 {len(all_signals)}건 ===\n")

    # 1) streak 구간별 ratio 분포
    buckets = {}
    raw_buckets = {}
    for r in all_signals:
        buckets.setdefault(bucket(r["streak"]), []).append(r["ratio"])
        raw_buckets.setdefault(bucket(r["streak"]), []).append(r["raw"])
    print("--- streak 구간별 magnitude_ratio 분포 ---")
    for name in ["streak=1", "streak2-5", "streak6-20", "streak20+"]:
        vals = sorted(buckets.get(name, []))
        if not vals:
            print(f"  {name}: (데이터 없음)")
            continue
        n = len(vals)
        mean = sum(vals) / n
        clamped_n = sum(1 for v in vals if v >= 2.0)
        print(f"  {name:12s} n={n:5d}  mean={mean:.3f}  median={vals[n//2]:.3f}  "
              f"min={vals[0]:.3f}  max={vals[-1]:.3f}  clamp@2.0={clamped_n}({100*clamped_n/n:.1f}%)")
    print("\n--- (참고) raw ratio(클램프 전) 분포 ---")
    for name in ["streak=1", "streak2-5", "streak6-20", "streak20+"]:
        rvals = sorted(raw_buckets.get(name, []))
        if not rvals:
            continue
        n = len(rvals)
        print(f"  {name:12s} n={n:5d}  mean={sum(rvals)/n:.3f}  median={rvals[n//2]:.3f}  "
              f"p90={rvals[int(n*0.9)]:.3f}  max={rvals[-1]:.3f}")

    # 2) threshold별 오탐/recall 트레이드오프
    #    "오탐 위험" = streak=1(방금 생성, 아직 검증 안 된 신규 후보) 중
    #    ratio>=threshold 로 "즉시 고신뢰"로 잘못 판정될 비율
    #    "recall" = streak20+(이미 확실한 실제 커브) 중 ratio>=threshold 통과 비율
    s1 = buckets.get("streak=1", [])
    s20 = buckets.get("streak20+", [])
    print(f"\n--- threshold 후보별 트레이드오프 (streak=1 n={len(s1)}, streak20+ n={len(s20)}) ---")
    print(f"  {'threshold':>10s} {'streak=1 오탐율':>16s} {'streak20+ recall':>18s}")
    for th in args.thresholds:
        fp = (sum(1 for v in s1 if v >= th) / len(s1)) if s1 else float('nan')
        rec = (sum(1 for v in s20 if v >= th) / len(s20)) if s20 else float('nan')
        print(f"  {th:>10.2f} {100*fp:>15.1f}% {100*rec:>17.1f}%")


if __name__ == "__main__":
    main()
