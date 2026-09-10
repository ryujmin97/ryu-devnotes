#!/usr/bin/env python3
"""
sim_route_346_lost_freq_single_route.py (346차 신규)

목적
----
345차 "다음 작업" 2번 -- 기존 실측 corpus에서 `apex_mode == "lost" AND
apex_dist > 0` 패턴의 실제 발생 빈도를 확인한다. 301차
(`sim_route_301_lost_boundary_trace.py`)가 이미 이 정확한 목적으로
"lost 발생 -> route release -> B 재획득 -> 생존시간" 추적 도구를
만들어뒀지만, ROUTE_IDS가 route1~4(a3b3373495 등)로 하드코딩돼 있고
298차 qcamera classification.md 파일을 필수 인자로 요구해 다른 corpus
(이번 x20seg 등)에는 그대로 쓸 수 없었다.

이 스크립트는 301차의 `build_stream`/`trace_lost_events`/`run_route`를
전부 무변경 import(§21)하고, 다음 2가지만 추가한다:
1. `--csv`(단일 파일 경로)로 임의 corpus를 받을 수 있게 함(ROUTE_IDS
   루프 대신).
2. classification.md 없이도 동작하도록 라벨링을 생략(다른 corpus는
   298차 qcamera 정답 라벨이 없으므로 당연히 불가능 -- real/noise
   분류는 이 스크립트 범위 밖, 원본 301차가 route1~4 전용으로 하던
   부분).

추가로 이번 목적(전체 lost 빈도)에 맞춰 "강제 RELEASE로 이어진 lost"뿐
아니라 continuity 스트림 전체에서 mode=="lost"인 프레임 수(전체
빈도, route_active 여부 무관)도 별도로 집계한다 -- 301차는 강제
RELEASE 이벤트만 봤지만(활성 중 lost로 종료된 경우만), 345차가 확인하려는
"apex_dist>0인 lost"는 INERT 상태에서 발생하는 lost도 포함하는 게
맞다(continuity 자체는 route_active와 무관하게 항상 진행됨, 296/300차
확인 사항).

`apex_dist > 0`는 continuity 판정 로직(`_route_cluster_continuity_step`,
`ContinuityState`) 자체가 이미 보장한다 -- "lost"는 miss_frames 초과로만
선언되고, "passed"는 predicted<=0(물리적 통과)일 때만 선언되므로 lost로
분류된 프레임은 정의상 마지막 예측 위치가 아직 0을 넘지 않은(=apex_dist
아직 남은) 상태다. 따라서 이 스크립트는 (a) mode=="lost" 전체 프레임 수,
(b) 그 중 A의 마지막 apex_dist(lost 선언 시점 예측 거리, `pre_locked_dist`
사용)가 실제로 0보다 큰 비율을 함께 출력해 이 전제를 직접 확인한다.

사용
----
    python3 sim_route_346_lost_freq_single_route.py \\
        --csv /home/claude/work/x20seg_346cha.csv \\
        --map-turn-speed-factor 1.10 --ctrl-end 8.0 --decel-rate 0.70

**하지 않는 것**: qcamera 대조(라벨 없음), 코드 패치, 신뢰도 게이트
설계. ANALYSIS_ONLY, `ryu` 코드 무변경.
"""
import argparse
import sys

sys.path.insert(0, ".")

from sim_route_301_lost_boundary_trace import (
    build_stream, trace_lost_events, run_route,
)
from sim_route_300_release_boundary_counterfactual import ActualLayer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--map-turn-speed-factor", type=float, default=1.10)
    ap.add_argument("--ctrl-end", type=float, default=8.0)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--persistence-horizon", type=float, default=5.0)
    args = ap.parse_args()

    # --- (a) 전체 continuity 스트림에서 mode=="lost" 빈도 (route_active 무관) ---
    stream = build_stream(args.csv, args.map_turn_speed_factor)
    naviPaths_frames = len(stream)
    lost_frames = [row for row in stream if row["mode"] == "lost"]
    n_lost_total = len(lost_frames)
    n_lost_dist_gt0 = sum(
        1 for row in lost_frames
        if row["pre_locked_dist"] is not None and row["pre_locked_dist"] > 0.0
    )

    print(f"=== (a) 전체 continuity 스트림 (naviPaths 프레임 {naviPaths_frames}개) ===")
    print(f"  mode==\"lost\" 전체: {n_lost_total}건")
    if n_lost_total:
        print(f"  그 중 lost 선언 시점 pre_locked_dist>0 (아직 apex 미통과): "
              f"{n_lost_dist_gt0}/{n_lost_total} ({100*n_lost_dist_gt0/n_lost_total:.1f}%)")
    else:
        print("  (lost 이벤트 없음)")

    # --- (b) 301차 방식: 강제 RELEASE(route_active 중 발생)로 이어진 lost + B 재획득/생존 추적 ---
    actual = ActualLayer()
    for fr in stream:
        actual.step(fr["t"], fr["apex_idx"], fr["apex_dist"], fr["apex_speed"],
                    fr["mode"], fr["streak"], fr["v_ego_ms"], fr["v_ego_kph"],
                    args.ctrl_end, args.decel_rate)
    lost_boundary_events = trace_lost_events(stream, actual.events,
                                              args.persistence_horizon)

    print(f"\n=== (b) 강제 RELEASE(route_active 중 lost로 종료) 이벤트: "
          f"{len(actual.events)}건, 그 중 mode==lost: {len(lost_boundary_events)}건 ===")
    for r in lost_boundary_events:
        print(f"  t={r['t']:.2f} A_last(t={r['A_last_matched_t']}, "
              f"dist={r['A_last_dist_m']}, speed={r['A_last_speed_kph']}, "
              f"gap={r['gap_seconds_A_to_LOST']}s)"
              f" -> B(dist={r['B_dist_m']}, speed={r['B_speed_kph']},"
              f" cluster={r['B_cluster_size']}/{r['B_n_clusters_total_this_frame']})"
              f" survive={r['B_survive_seconds']}s/{r['B_survive_frames']}f"
              f"{'(+)' if r['B_survived_full_horizon'] else ''}")

    if lost_boundary_events:
        n_reacquired = sum(1 for r in lost_boundary_events if r["B_dist_m"] is not None)
        n_survive_gt0 = sum(1 for r in lost_boundary_events if r["B_survive_frames"] > 0)
        print(f"\n  요약: {len(lost_boundary_events)}건 중 같은 프레임 B 재획득 "
              f"{n_reacquired}건, 그 중 1프레임 이상 생존 {n_survive_gt0}건")
        print("  (\"lost -> release -> 짧은 시간 후 재활성\" 패턴 존재 여부의 직접 근거)")


if __name__ == "__main__":
    main()
