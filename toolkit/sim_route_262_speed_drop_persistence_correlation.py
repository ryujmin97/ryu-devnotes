#!/usr/bin/env python3
"""
sim_route_262_speed_drop_persistence_correlation.py (262차 신규)

목적: 260차가 "corpus 한계로 미검증"이라 남긴 speed-drop strength 신호를,
사용자가 제안한 터널 외 corpus(dashcam_1788583013065.zip, 세그 25개 전체
route_ac/ad)로 재검증한다. 260차의 실패 원인은 신호 자체가 아니라 분석에
사용한 3개 좁은 window(tunnel/ic_gore/s_curve)가 전부 "이미 stage2를 통과한
실제 커브"만 포함해 노이즈 대조군이 없었던 것 -- WIP.md 261차 "다음 작업 1"
참고.

방법: sim_route_260_confidence_signals.py의 replay()를 그대로 재사용(§21,
동일 pass에서 persistence와 speed_drop이 이미 함께 기록되므로 --
261차가 지적한 "서로 다른 스크립트를 조인"하는 문제 자체가 애초에 없음).
narrow window로 자르지 않고 CSV 전체를 사용, 각 (frame,cluster) 레코드를
"그 track이 죽을 때까지 도달한 최종 streak"(persistence 최댓값) 구간으로
재버킷팅해 speed_drop_strength 분포를 비교한다. 260차/261차와 동일한 버킷
경계(streak=1 / 2-5 / 6-20 / 20+)를 사용해 직접 비교 가능하게 함.

주의: 프레임별 speed_drop은 track이 살아있는 동안 매 프레임 변하므로,
"이 track의 최종 streak"로 버킷팅한 뒤 그 track에 속한 모든 프레임의
speed_drop을 그 버킷에 넣는다(즉 streak=20+ 버킷에는 streak=1~19였던
시점의 speed_drop도 포함됨 -- persistence가 신호로서 최종 결과를 아직
모르는 시점에도 speed_drop이 이미 구분력이 있는지 보려는 의도. "그 track이
결국 얼마나 오래 살아남았는가"를 label로, "그 순간의 speed_drop"을 값으로
쓰는 방식).

**[262차 실측 중 발견, 중요]**: dashcam corpus(도심/정차 포함) 실행 중
`speed_drop=(v_ego_kph-candidate_speed)/v_ego_kph` 분모가 사실상 0에
가까운 vEgo(실측 최소 5e-45 kph -- 정지 상태에서 발생하는 부동소수점
잔차로 추정, 실제 물리적 저속이 아님)로 나뉘어 speed_drop이 -6e46 등
극단값으로 발산하는 사례 다수 확인(전체 15841건 중 vEgo<1kph 2675건,
16.9%). 261차의 magnitude_ratio 분모(FLOOR_THRESHOLD 근접 curvature)
발산과 동일한 성격의 아티팩트 -- 이 스크립트는 재현/진단 목적으로 원본
공식을 그대로 두고, `--min-vego-kph`로 하한 필터를 켤 수 있게만 확장했다
(기본값 0.0=필터 없음, 발산 재현용). 실제 confidence 공식에 반영할 하한
값 자체는 이번 세션에서 확정하지 않음(아래 다음 작업 참고).

사용:
    python3 sim_route_262_speed_drop_persistence_correlation.py \
        <route1.csv> [<route2.csv> ...] [--min-vego-kph 2.0]
"""
import argparse
import sys

sys.path.insert(0, ".")
from sim_route_260_confidence_signals import load_csv, replay as _replay_orig
from sim_route_260_confidence_signals import (
    build_dist_curv_speed, gate_base_kph, gate_candidates, find_clusters,
    MultiTrackContinuity, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M,
)


def replay(rows, min_vego_kph=0.0):
    """260차 replay()와 동일하나 min_vego_kph 초과 프레임만 신호 계측에
    포함(분모 발산 진단/필터용, 262차 확장). min_vego_kph=0.0이면 260차와
    100% 동일 동작(필터 없음)."""
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
            if v_ego_kph <= min_vego_kph:
                continue  # 262차 필터: track 자체는 계속 추적하되 신호 기록만 스킵
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

BUCKETS = [
    (1, 1, "streak=1"),
    (2, 5, "streak2-5"),
    (6, 20, "streak6-20"),
    (21, float("inf"), "streak20+"),
]


def bucket_label(final_streak):
    for lo, hi, label in BUCKETS:
        if lo <= final_streak <= hi:
            return label
    return "?"


def analyze(frame_signals, csv_label):
    if not frame_signals:
        print(f"\n=== {csv_label}: 매칭된 클러스터 없음 ===")
        return

    # track별 최종(최댓값) streak 계산 -- 그 track이 도달한 persistence 정점
    final_streak = {}
    for r in frame_signals:
        tid = r["track_id"]
        final_streak[tid] = max(final_streak.get(tid, 0), r["persistence"])

    n_tracks = len(final_streak)
    bucket_counts = {label: 0 for _, _, label in BUCKETS}
    for tid, fs in final_streak.items():
        bucket_counts[bucket_label(fs)] += 1

    print(f"\n=== {csv_label}: 전체 {len(frame_signals)}개 (frame,cluster) "
          f"레코드, 고유 track {n_tracks}개 ===")
    print(f"  track 최종 streak 분포: " +
          ", ".join(f"{label}={bucket_counts[label]}개"
                     f"({bucket_counts[label]/n_tracks*100:.1f}%)"
                     for _, _, label in BUCKETS))

    bucket_drops = {label: [] for _, _, label in BUCKETS}
    for r in frame_signals:
        tid = r["track_id"]
        label = bucket_label(final_streak[tid])
        bucket_drops[label].append(r["speed_drop"])

    print(f"  speed_drop_strength(0~1) -- track의 '최종 도달 streak' 구간별 "
          f"(그 구간에 속하는 모든 순간값 포함):")
    for _, _, label in BUCKETS:
        arr = sorted(bucket_drops[label])
        if not arr:
            print(f"    {label}: (표본 없음)")
            continue
        n = len(arr)
        mean = sum(arr) / n
        p50 = arr[n // 2]
        print(f"    {label}: n={n} mean={mean:.3f} median={p50:.3f} "
              f"min={arr[0]:.3f} max={arr[-1]:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_paths", nargs="+")
    ap.add_argument("--min-vego-kph", type=float, default=0.0,
                     help="이 값 이하 vEgo 프레임은 speed_drop 신호 기록에서 "
                          "제외(분모 발산 진단/필터, 기본 0.0=필터 없음)")
    args = ap.parse_args()

    all_signals = []
    for path in args.csv_paths:
        rows = load_csv(path)
        if not rows:
            print(f"no rows: {path}", file=sys.stderr)
            continue
        signals = replay(rows, min_vego_kph=args.min_vego_kph)
        analyze(signals, path)
        all_signals.extend(signals)

    if len(args.csv_paths) > 1:
        analyze(all_signals, "전체 합산")


if __name__ == "__main__":
    main()
