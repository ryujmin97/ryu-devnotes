#!/usr/bin/env python3
"""
sim_route_260_confidence_signals.py (260차 신규)

목적: 259차가 확정한 "apex 후보 선정을 최근접(clusters[0])에서 confidence
기반으로 재설계"하는 방향(WIP.md 259차)을 위해, Master가 제시한 4개
confidence 신호 중 코드 변경 없이 기존 CSV(+naviPaths)만으로 계측 가능한
3개(persistence/curvature consistency/speed-drop strength)를 프레임 단위로
실측한다. GPS positional reliability(4번째 신호)는 horizontalAccuracy가
extract_log.py CSV에 없어 이번 스크립트에서는 계측 불가(별도 extract_log.py
확장 필요, 아래 미완료 참고).

재사용: sim_route_234_spatial_apex_continuity.py의 build_speeds_distances/
gate_candidates/gate_base_kph/find_clusters를 그대로 재사용(§21). 다른 점은
1) curvature 배열도 함께 반환(merged[1]), 2) 단일 locked apex가 아니라
"현재 프레임에 존재하는 모든 클러스터"를 동시에 추적하는 멀티트랙 continuity
매처(MultiTrackContinuity)를 신규 작성한 것.

**스테이지 구성 (259차 WIP 기준)**: 247/248/249/250/251차 실측으로
severity gate(stage1)는 완전 삭제 확정(WIP 259차 "ROUTE_SEVERITY_GATE_RATIO ...
확인 삭제됨"). 따라서 이 스크립트는 항상 stage0(road_limit_speed 필터)
후보를 그대로 stage2(spatial cluster) 입력으로 사용한다(= 기존 스크립트의
--skip-gate와 동일 경로) -- 현재 실제 배포 코드 구조를 그대로 반영.

멀티트랙 매칭 로직: 기존 ContinuityState(단일 locked apex)와 동일한
예측거리 매칭(및 CONTINUITY_MATCH_TOLERANCE_M=15.0, MISS_TOLERANCE=3프레임)을
"현재 살아있는 모든 트랙"에 대해 그리디로 확장 적용. 트랙별로 매 매칭
프레임마다 다음을 누적한다:
  - streak: 지금까지 연속 매칭된 프레임 수(hold 프레임 포함하지 않음,
    실제 클러스터가 존재해 매칭된 프레임만 카운트 -- Master의
    "cluster persistence" 정의와 일치)
  - curv_signs: 매칭 시점 대표점(cluster[0]) curvature의 부호 히스토리
  - speed_drops: (v_ego_kph - candidate_speed)/v_ego_kph 히스토리
    (클수록 "현재 속도 대비 강한 감속을 요구하는 후보")

프레임 단위 신호값(그 시점까지의 track 누적 기준, look-ahead 없음 -- 실제
런타임에서 그 프레임에 알 수 있는 값만 사용):
  persistence_signal      = 그 프레임까지의 track.streak
  curvature_consistency   = 그 프레임까지 track 내 최빈 부호 비율
  speed_drop_strength     = 그 프레임의 speed_drop 값 자체(누적 아님,
                             순간값 -- "감속 심각도"는 시점별로 봐야 의미
                             있음, Master 정의)

사용:
    python3 sim_route_260_confidence_signals.py <route.csv> \
        --window 2190 2225 --label tunnel \
        --window 2108 2112 --label ic_gore \
        --window 2116 2122.2 --label s_curve
    (인자 없이 실행하면 251차가 확정한 터널/IC gore/S커브 3구간 기본 실행)
"""
import argparse
import csv
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

MACRO_SAMPLE = 4
FINE_SAMPLE = 1
FLOOR_THRESHOLD = 0.001  # 157차 패치(ROUTE_CURVE_NEGLIGIBLE_THRESHOLD), 현재 HEAD와 동일
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
CONTINUITY_MATCH_TOLERANCE_M = 15.0
MISS_TOLERANCE_FRAMES = 3

DEFAULT_WINDOWS = [
    (2190.0, 2225.0, "tunnel"),
    (2108.0, 2112.0, "ic_gore"),
    (2116.0, 2122.2, "s_curve"),
]


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_dist_curv_speed(navi_paths_str):
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < FINE_SAMPLE * 2 + 1:
        return [], [], []
    merged = recompute_route_curvature_speed(
        points, distances, sample=MACRO_SAMPLE, sample_fine=FINE_SAMPLE,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD,
    )
    if not merged:
        return [], [], []
    return [m[0] for m in merged], [m[1] for m in merged], [m[2] for m in merged]


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
    __slots__ = ("last_dist", "last_speed", "streak", "miss_frames",
                 "curv_signs", "start_t", "id")
    _next_id = 1

    def __init__(self, dist, speed, curv_sign, t):
        self.last_dist = dist
        self.last_speed = speed
        self.streak = 1
        self.miss_frames = 0
        self.curv_signs = [curv_sign]
        self.start_t = t
        self.id = Track._next_id
        Track._next_id += 1

    def majority_sign_ratio(self):
        if not self.curv_signs:
            return 0.0
        pos = sum(1 for s in self.curv_signs if s > 0)
        neg = sum(1 for s in self.curv_signs if s < 0)
        dom = max(pos, neg)
        return dom / len(self.curv_signs)


class MultiTrackContinuity:
    """모든 raw cluster를 동시에 추적하는 멀티트랙 확장판.
    (기존 ContinuityState는 locked apex 1개만 추적)"""

    def __init__(self):
        self.tracks = []  # list[Track]

    def step(self, clusters, dists, curvs, speeds, v_ego_ms, dt, t):
        """반환: list of (cluster, track, is_new) -- 이번 프레임에 매칭/신규
        생성된 (cluster, track) 쌍. hold 프레임(클러스터 없이 예측만 유지)은
        신호 계측에 포함하지 않는다(실측 클러스터가 있을 때만 신호 정의)."""
        results = []
        used_track_ids = set()
        used_cluster_ids = set()

        # 1) 기존 트랙들의 예측 위치 계산 후 그리디 최근접 매칭
        candidates = []  # (err, track, cluster_i)
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
            track.last_speed = speeds[idx]
            track.streak += 1
            track.miss_frames = 0
            sign = 1 if curvs[idx] > 0 else (-1 if curvs[idx] < 0 else 0)
            track.curv_signs.append(sign)
            results.append((clusters[ci], track, False))

        # 2) 매칭 안 된 기존 트랙: miss_frames 증가, 초과 시 폐기
        alive = []
        for track in self.tracks:
            if id(track) in used_track_ids:
                alive.append(track)
                continue
            track.miss_frames += 1
            if track.miss_frames < MISS_TOLERANCE_FRAMES:
                alive.append(track)  # hold 상태로 유지(신호 계측 대상 아님)

        # 3) 매칭 안 된 신규 클러스터: 새 트랙 생성
        for ci, c in enumerate(clusters):
            if ci in used_cluster_ids:
                continue
            idx = c[0]
            sign = 1 if curvs[idx] > 0 else (-1 if curvs[idx] < 0 else 0)
            track = Track(dists[idx], speeds[idx], sign, t)
            alive.append(track)
            results.append((c, track, True))

        self.tracks = alive
        return results


def replay(rows):
    mtc = MultiTrackContinuity()
    frame_signals = []  # per (frame, cluster) 신호 레코드
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

        dists, curvs, speeds = build_dist_curv_speed(row.get("naviPaths", ""))
        if not speeds:
            continue

        gate_base = gate_base_kph(row, v_ego_kph)
        c0 = gate_candidates(speeds, gate_base)
        clusters = find_clusters(c0, dists, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        if not clusters:
            continue

        matched = mtc.step(clusters, dists, curvs, speeds, v_ego_ms, dt, t)
        for cluster, track, is_new in matched:
            idx = cluster[0]
            speed_drop = (v_ego_kph - speeds[idx]) / v_ego_kph if v_ego_kph > 0 else 0.0
            frame_signals.append({
                "t": t,
                "track_id": track.id,
                "is_new": is_new,
                "dist": dists[idx],
                "persistence": track.streak,
                "curv_consistency": track.majority_sign_ratio(),
                "speed_drop": speed_drop,
            })
    return frame_signals


def summarize_window(frame_signals, lo, hi, label):
    w = [r for r in frame_signals if lo <= r["t"] <= hi]
    n_tracks = len(set(r["track_id"] for r in w))
    print(f"\n=== {label} (t={lo}~{hi}, {len(w)} (frame,cluster) 레코드, "
          f"고유 track {n_tracks}개) ===")
    if not w:
        print("  (매칭된 클러스터 없음)")
        return
    persistences = [r["persistence"] for r in w]
    consistencies = [r["curv_consistency"] for r in w]
    drops = [r["speed_drop"] for r in w]

    def stats(name, arr):
        arr_sorted = sorted(arr)
        n = len(arr_sorted)
        mean = sum(arr_sorted) / n
        p50 = arr_sorted[n // 2]
        print(f"  {name}: mean={mean:.3f} median={p50:.3f} "
              f"min={arr_sorted[0]:.3f} max={arr_sorted[-1]:.3f}")

    stats("persistence(streak, frames)", persistences)
    stats("curvature_consistency(0~1)", consistencies)
    stats("speed_drop_strength(0~1)", drops)

    # streak==1(방금 생성된 트랙, 신뢰도 최저 -- "new" 상태) 비율
    new_ratio = sum(1 for r in w if r["persistence"] == 1) / len(w)
    print(f"  streak==1(신규 트랙) 비율: {new_ratio*100:.1f}% "
          f"(현재 코드의 clusters[0] 최근접 즉시선택이 이 비율만큼 "
          f"검증되지 않은 후보를 그대로 채택한다는 뜻)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--window", type=float, nargs=2, action="append", default=None)
    ap.add_argument("--label", action="append", default=None)
    ap.add_argument("--tolerance", type=float, default=None,
                     help="266차: CONTINUITY_MATCH_TOLERANCE_M(기본 15.0, "
                          "260차 원본값)을 오버라이드. 프로덕션 값(10.0)으로 "
                          "재실행해 265차가 발견한 15.0/10.0 불일치를 재검증할 "
                          "때 사용. 미지정 시 기존 260차와 100% 동일 동작.")
    args = ap.parse_args()

    if args.tolerance is not None:
        global CONTINUITY_MATCH_TOLERANCE_M
        CONTINUITY_MATCH_TOLERANCE_M = args.tolerance
    print(f"CONTINUITY_MATCH_TOLERANCE_M = {CONTINUITY_MATCH_TOLERANCE_M}")

    rows = load_csv(args.csv_path)
    if not rows:
        print("no rows", file=sys.stderr)
        sys.exit(1)

    frame_signals = replay(rows)
    print(f"=== 전체 {len(rows)}행 처리, (frame,cluster) 매칭 레코드 "
          f"{len(frame_signals)}건, 고유 track "
          f"{len(set(r['track_id'] for r in frame_signals))}개 ===")

    if args.window:
        labels = args.label or [f"win{i}" for i in range(len(args.window))]
        for (lo, hi), label in zip(args.window, labels):
            summarize_window(frame_signals, lo, hi, label)
    else:
        for lo, hi, label in DEFAULT_WINDOWS:
            summarize_window(frame_signals, lo, hi, label)


if __name__ == "__main__":
    main()
