#!/usr/bin/env python3
"""333차: x18seg 전체 타임라인 stateful replay -- route_local_curve_merge를
production과 동일한 순서(1차 10m pass -> orphan>0이면 local merge -> 병합
결과로 candidates/clusters 재계산 -> _route_cluster_continuity_step)로 매
프레임 주입해, 'matched' 모드에서도 ws<0 라벨이 apex_dist에 유입되는지
전체 corpus 시간축으로 확인한다.

배경(332차 gap): 332차 sim_route_332_ws_negative_real_corpus.py는 매
orphan 프레임을 독립적으로(stateless, continuity_new_entry()로 "이번
프레임에 신규 진입했다면"만 가정) 검사했다. 그래서 실제로는 "기존에
locked된 apex가 이번 프레임의 근접(ws<0) 클러스터에 matched로 재확인되는"
경로는 전혀 검증되지 않았다 -- 332차 WIP 미확인사항 1번("다른 상황에서
근접 curve가 승격되고 실제 apex 값에 영향주는 사례")의 일부.

설계(§21 -- 재구현 없음, 기존 두 스크립트를 조립만):
  - sim_route_322d_stateful_replay.py: recompute_full()(naviPaths 10m
    1차 pass, production 100% 재현 검증됨), ContinuityState(=
    _route_cluster_continuity_step() 그대로 이식, streak 포함),
    route_find_clusters, 관련 상수를 그대로 import.
  - sim_route_331_ws_negative_downstream.py: route_local_curve_merge()
    (328차 국소 2.5m 재샘플, carrot_man.py 1568행 그대로 이식)를 그대로
    import.
  - sim_route_332_ws_negative_real_corpus.py: parse_raw_path()(routeOrphanRawPath
    파싱)를 그대로 import.

매 프레임 순서(carrot_man.py 1556~1580행과 동일, §27):
  1. naviPaths -> recompute_full() 1차 10m pass -> candidates/clusters/orphans/
     distances/speeds/fine_triggered.
  2. orphans가 있고 이번 프레임에 routeOrphanRawPath가 로깅되어 있으면(=
     production에서도 orphan_count>0 조건으로 동일하게 로깅됨, 323차) ->
     route_local_curve_merge() 호출.
  3. local_used=True면 병합된 distances/speeds로 candidates/clusters/orphans
     재계산(production과 동일 조건문).
  4. ContinuityState.step(clusters, distances, speeds, v_ego_ms) 호출 --
     이 state는 매 프레임 지속(reset 규칙도 322d와 동일하게 재현).

계측: 매 프레임 로컬 merge가 발생했다면 해당 프레임의 ws<0 윈도우
범위([ws, we])를 기록해두고, continuity.step()이 반환한 (idx, dist, mode)가
그 윈도우 범위 안에 들어오면(=이번 프레임 apex 채택값이 국소 재샘플/ws<0
라벨 구간에서 나온 값이면) mode별로 집계한다. 특히 mode=='matched'인
경우가 이번 회차의 핵심 질문(332차는 'new'만 봤음).

부가 신호(구조적으로 명확한 케이스): distances 배열의 10m 1차pass 원본
값은 항상 0 이상(recompute_full 첫 값이 distance=0에서 시작)이므로,
merged 배열에서 apex_dist(=distances[idx])가 음수로 나온다면 그 값은
100% ws<0 국소구간에서 유입된 것이다 -- mode 무관하게 전체 타임라인에서
apex_dist<0 발생 여부를 별도로 집계한다.

사용:
  python3 sim_route_333_ws_negative_matched_mode.py <CSV> [--limit-print N]

**주의(333차, 미해결) -- 이 스크립트의 출력을 findings로 사용하지 말 것**:
x18seg 첫 orphan 프레임(t=640.216, ws=0 경계값)을 실측과 대조한 결과,
1차 10m pass(candidate/cluster, stage0)까지는 실측과 완전 일치(candidateCount/
candidate0~2 거리 전부 일치)하지만, route_local_curve_merge() 적용 후
결과가 실측과 다르다(실측: routeClusterCount=2/routeOrphanSingletonCount=3
=병합 전과 동일=사실상 이 프레임에서 로컬 병합이 무변화였던 것으로 보임 /
이 스크립트 재현: 로컬 병합 후 클러스터 4개로 증가). 즉 route_local_curve_merge()
자체는 331/332차에서 이미 검증된 verbatim 함수를 그대로 썼음에도 이 조합
(naviPaths 기반 1차pass + routeOrphanRawPath 기반 로컬 재계산 + 전체
타임라인 stateful 연결)에서 실측과 어긋나는 지점이 있다 -- 원인 미확정.
따라서 이 스크립트가 출력하는 'matched 모드 ws<0 유입 351건'/'음수 apex_dist
416건' 수치는 재현 버그가 섞여 있을 가능성이 있어 **신뢰할 수 없다**.
다음 세션 최우선 작업: t=640.216 프레임에서 route_local_curve_merge() 내부
호출을 단계별로 실측과 대조해 정확히 어느 단계부터 갈라지는지 원인 확정
(§28 순서: 증상->재현조건->입력->상태->호출흐름->계산->조건/분기->출력->원인).
"""
import argparse
import csv
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim_route_322d_stateful_replay import (
    recompute_full, ContinuityState, route_find_clusters, parse_navi_paths,
    ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M, MAP_TURN_SPEED_FACTOR,
    ROUTE_SPEED_LOOP_DT,
)
from sim_route_331_ws_negative_downstream import (
    route_local_curve_merge, LOCAL_CURVE_WINDOW_BACK_M, LOCAL_CURVE_WINDOW_FWD_M,
    LOCAL_CURVE_MACRO_CHORD_M,
)
from sim_route_332_ws_negative_real_corpus import parse_raw_path


def compute_ws_windows(orphans, distances):
    """route_local_curve_merge() 내부의 windows 계산과 동일(계측 전용
    복제 -- 함수가 최종 배열만 반환하고 윈도우 범위 자체는 반환하지
    않아서, 태깅 목적으로만 그대로 재현. §27: 핵심 로직 자체는 여전히
    route_local_curve_merge()를 그대로 호출해 사용, 이 함수는 그 호출과
    별개로 "이번 프레임에 ws<0 윈도우가 있었는가"만 기록하는 부가
    계측이다."""
    windows = []
    for orphan_cluster in orphans:
        idx0 = orphan_cluster[0]
        center = distances[idx0]
        windows.append((center - LOCAL_CURVE_WINDOW_BACK_M,
                         center + LOCAL_CURVE_WINDOW_FWD_M))
    windows.sort()
    merged = []
    for ws, we in windows:
        if merged and ws <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], we))
        else:
            merged.append((ws, we))
    return merged


def in_any_window(value, windows, margin=LOCAL_CURVE_MACRO_CHORD_M):
    for ws, we in windows:
        if ws <= value <= we + margin:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--limit-print", type=int, default=20)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, newline="")))

    continuity = ContinuityState()

    n_frames = 0
    n_full_block = 0
    n_local_used_frames = 0
    n_ws_neg_frames = 0

    mode_counts = {"matched": 0, "held": 0, "new": 0, "passed": 0, "lost": 0, "none": 0}
    mode_in_ws_neg_window = {"matched": 0, "held": 0, "new": 0, "passed": 0, "lost": 0, "none": 0}
    matched_examples = []
    negative_apex_examples = []
    n_apex_dist_negative_any_mode = 0

    for row in rows:
        n_frames += 1
        t = row.get("t", "?")
        pts, _ = parse_navi_paths(row.get("naviPaths", ""))
        v_ego_ms = float(row["vEgo"]) if row.get("vEgo") else 0.0
        road_limit_speed = float(row["nRoadLimitSpeed"]) if row.get("nRoadLimitSpeed") else 300.0
        if road_limit_speed <= 0:
            road_limit_speed = 30.0

        full_block = len(pts) >= 9
        if not full_block:
            # [322d와 동일 재현] naviPaths 있으나 부족/완전공백 -- reset 규칙
            if pts:
                pass  # route_active였을 때만 리셋(이 스크립트는 route_active 미추적,
                      # continuity lock 자체는 322d 검증 결과 이 케이스가 x17/x18seg
                      # 모두에서 매우 드묾 -- 보수적으로 아무것도 하지 않고 다음
                      # full_block 프레임까지 lock 유지, 실제 route_active=False가
                      # 대다수인 구간이라 production과 사실상 동일)
            else:
                continuity.reset()
            continue

        n_full_block += 1
        candidates, clusters, orphans, distances, speeds, fine_triggered = recompute_full(
            pts, road_limit_speed, MAP_TURN_SPEED_FACTOR)

        ws_windows_this_frame = []
        raw_path_str = row.get("routeOrphanRawPath", "")
        if orphans and raw_path_str:
            relative_coords = parse_raw_path(raw_path_str)
            curvatures_dummy = [0.0] * len(distances)
            merged_d, merged_s, merged_c, merged_ft, local_used = route_local_curve_merge(
                orphans, distances, speeds, curvatures_dummy, fine_triggered,
                relative_coords, MAP_TURN_SPEED_FACTOR, road_limit_speed)
            if local_used:
                n_local_used_frames += 1
                windows = compute_ws_windows(orphans, distances)
                if any(ws < 0 for ws, we in windows):
                    n_ws_neg_frames += 1
                    ws_windows_this_frame = [(ws, we) for ws, we in windows if ws < 0]
                distances, speeds, fine_triggered = merged_d, merged_s, merged_ft
                candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed]
                all_clusters = route_find_clusters(candidates, distances, 1, ROUTE_CLUSTER_MAX_GAP_M)
                clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
                orphans = [c for c in all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]

        idx, apex_dist, apex_speed, apex_mode, streak = continuity.step(
            clusters, distances, speeds, v_ego_ms)

        mode_counts[apex_mode] = mode_counts.get(apex_mode, 0) + 1

        if apex_dist is not None and apex_dist < 0:
            n_apex_dist_negative_any_mode += 1
            if len(negative_apex_examples) < args.limit_print:
                negative_apex_examples.append((t, apex_mode, idx, apex_dist, apex_speed))

        if ws_windows_this_frame and apex_dist is not None and idx != -1:
            if in_any_window(apex_dist, ws_windows_this_frame):
                mode_in_ws_neg_window[apex_mode] = mode_in_ws_neg_window.get(apex_mode, 0) + 1
                if apex_mode == "matched" and len(matched_examples) < args.limit_print:
                    matched_examples.append((t, idx, apex_dist, apex_speed, ws_windows_this_frame))

    print("=== 333차: x18seg 전체 stateful replay -- ws<0 라벨의 'matched' 모드 유입 여부 ===")
    print(f"전체 프레임: {n_frames}, full_block(계산 실행): {n_full_block}")
    print(f"local_curve_merge 적용된 프레임: {n_local_used_frames}")
    print(f"  그 중 ws<0 윈도우 포함 프레임: {n_ws_neg_frames}")
    print()
    print("apex_mode별 발생 횟수(전체 타임라인):")
    for m, c in mode_counts.items():
        print(f"  {m}: {c}")
    print()
    print("apex_mode별 -- 이번 프레임 ws<0 윈도우 범위 안에서 apex 채택된 횟수:")
    for m, c in mode_in_ws_neg_window.items():
        print(f"  {m}: {c}")
    print()
    print(f"전체 타임라인 중 apex_dist<0로 채택된 프레임(mode 무관, 구조적으로 "
          f"ws<0 유입 확정 신호): {n_apex_dist_negative_any_mode}건")
    if negative_apex_examples:
        print("  샘플(t, mode, idx, apex_dist, apex_speed):")
        for x in negative_apex_examples:
            print(f"    {x}")
    print()
    print(f"'matched' 모드이면서 ws<0 윈도우 범위 안에서 apex 채택된 샘플"
          f"(t, idx, apex_dist, apex_speed, windows):")
    for x in matched_examples:
        print(f"    {x}")
    if not matched_examples:
        print("    (없음)")


if __name__ == "__main__":
    main()
