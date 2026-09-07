#!/usr/bin/env python3
"""
sim_route_307_provisional_singleton_telemetry.py (307차 신규)

목적: 306차가 코드+합성 재현으로 확정한 가설("route_find_clusters()의
min_points=2 게이트가 고립된 1포인트 좁은 커브를 노이즈로 오인해 제거할
수 있다")을 실차 로그가 없는 상태에서 production 코드를 바로 바꾸지
않고, 다음 실차 로그에서 검증 가능하도록 추가한 관측 전용 계측
(carrot_man.py/carrot_serv.py/custom.capnp @58~@69, 307차 patch)의
정확성을 배포 전에 확인한다.

**§21/22 기존 도구 재사용**: route_find_clusters()/ContinuityState는
296차/306차가 이미 이식해둔 것을 상수 정의만 그대로 재사용(재구현 아님,
상수값은 296차 스크립트와 대조해 동일함을 유지).

**검증 대상 2가지(둘 다 patch에 실제로 들어간 로직 그대로 재현)**:
1. orphan 도출 방식의 등가성 -- carrot_man.py는 이제
   `route_find_clusters(candidates, distances, 1, MAX_GAP_M)`로 전체
   클러스터를 한 번 얻은 뒤 호출부에서 `len(c) >= MIN_POINTS`로
   clusters/orphans를 나눈다. 이 방식이 기존 한 줄 호출
   (`route_find_clusters(candidates, distances, MIN_POINTS, MAX_GAP_M)`)과
   `clusters` 결과가 100% 동일한지 확인 -- 다르면 §27 최소변경 위반
   (기존 apex 선택 동작이 바뀌는 회귀).
2. `_route_provisional_singleton_step()` shadow tracker -- (a) 물리적으로
   실재하는 고립된 좁은 커브에 접근하며 매 프레임 거리가 vEgo*dt만큼
   줄어드는 시나리오에서 streak가 정상적으로 증가해 PROVISIONAL_
   PROMOTE_STREAK(3) 이상에서 promoted=True가 되는지, (b) 위치가 일관되지
   않는 단발성 노이즈(매 프레임 랜덤 위치)에서는 streak가 계속 1로
   리셋되어 promoted=True가 되지 않는지, (c) 이 tracker의 반환값이 실제
   apex_idx/apex_dist/apex_speed/apex_mode(메인 clusters 기반 상태머신)
   와 완전히 독립적으로 동작하는지(§10/§27 -- 제어 미사용 원칙).

**한계**: 이 스크립트는 patch 로직 자체의 정확성/등가성만 검증한다.
PROVISIONAL_PROMOTE_STREAK=3이 실제 도로 데이터에 적합한 값인지는
여전히 NEEDS_VALIDATION -- 실차 로그 확보 후 재조정 필요.
"""

import sys

# ---- carrot_man.py 상수 그대로 이식 (HEAD 8d481ec=305차 + 307차 patch
# 적용 기준으로 이번 세션에 직접 대조 완료) ----
ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
CONTINUITY_MATCH_TOLERANCE_M = 20.0
PROVISIONAL_PROMOTE_STREAK = 3


def route_find_clusters(idxs, distances, min_points, max_gap_m):
    # carrot_man.py route_find_clusters() 그대로.
    if not idxs:
        return []
    clusters = []
    cur = [idxs[0]]
    for i in idxs[1:]:
        if distances[i] - distances[cur[-1]] <= max_gap_m:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_points]


def derive_clusters_and_orphans(candidates, distances):
    # carrot_man.py 307차 patch가 실제로 하는 것 그대로: min_points=1로
    # 한 번 호출해 전체 분할을 얻고, 호출부에서 min_points>=2 필터를
    # 적용해 clusters/orphans를 나눈다.
    all_clusters = route_find_clusters(candidates, distances, 1, ROUTE_CLUSTER_MAX_GAP_M)
    clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
    orphans = [c for c in all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]
    return clusters, orphans


class ProvisionalSingletonTracker:
    """carrot_man.py::_route_provisional_singleton_step() 이식. 인스턴스
    상태만 다르고 분기/반환값은 patch와 동일하게 유지한다."""

    def __init__(self):
        self.locked_dist = None
        self.locked_speed = None
        self.streak = 0

    def step(self, orphans, distances, speeds, v_ego_ms):
        dt = ROUTE_SPEED_LOOP_DT
        predicted = (self.locked_dist - v_ego_ms * dt) if self.locked_dist is not None else None

        matched = None
        if predicted is not None and predicted > 0 and orphans:
            best = None
            best_err = None
            for c in orphans:
                idx = c[0]
                err = abs(distances[idx] - predicted)
                if best_err is None or err < best_err:
                    best, best_err = idx, err
            if best_err is not None and best_err <= CONTINUITY_MATCH_TOLERANCE_M:
                matched = (best, best_err)

        if matched is not None:
            idx, err = matched
            self.locked_dist = distances[idx]
            self.locked_speed = speeds[idx]
            self.streak += 1
            promoted = self.streak >= PROVISIONAL_PROMOTE_STREAK
            return True, self.locked_dist, self.locked_speed, self.streak, err, promoted

        self.locked_dist = None
        self.locked_speed = None
        self.streak = 0
        if orphans:
            idx = orphans[0][0]
            self.locked_dist = distances[idx]
            self.locked_speed = speeds[idx]
            self.streak = 1
            return True, distances[idx], speeds[idx], 1, 0.0, (1 >= PROVISIONAL_PROMOTE_STREAK)
        return False, 0.0, 0.0, 0, 0.0, False


def run_tests():
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    # ---- 검증1: orphan 도출 등가성 (여러 랜덤/수기 시나리오) ----
    scenarios = [
        # (candidates(=idxs, 오름차순), distances 딕셔너리형 인덱스->거리)
        ([0], {0: 10.0}),                              # 완전 고립 단일
        ([0, 1], {0: 10.0, 1: 15.0}),                  # gap<=40 -> 클러스터(2)
        ([0, 1, 2], {0: 10.0, 1: 60.0, 2: 65.0}),      # 0 고립 + (1,2) 클러스터
        ([0, 1, 2, 3], {0: 10.0, 1: 55.0, 2: 100.0, 3: 145.0}),  # 전부 고립(gap>40)
        ([], {}),                                       # 후보 없음
        ([0], {0: 5.0}),
    ]
    for i, (idxs, dist_map) in enumerate(scenarios):
        distances = [0.0] * (max(idxs) + 1 if idxs else 0)
        for k, v in dist_map.items():
            distances[k] = v
        baseline_clusters = route_find_clusters(idxs, distances, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        new_clusters, orphans = derive_clusters_and_orphans(idxs, distances)
        check(f"orphan_equiv_scenario{i}", new_clusters == baseline_clusters,
              f"baseline={baseline_clusters} new={new_clusters} orphans={orphans}")

    # orphan 내용 자체도 기대와 일치하는지(시나리오2: idx0만 고립)
    idxs, dist_map = scenarios[2]
    distances = [0.0] * (max(idxs) + 1)
    for k, v in dist_map.items():
        distances[k] = v
    _, orphans = derive_clusters_and_orphans(idxs, distances)
    check("orphan_content_scenario2", orphans == [[0]], f"orphans={orphans}")

    # ---- 검증2a: 실재 고립 커브 접근 시나리오 -- streak 증가 + 승격 ----
    tracker = ProvisionalSingletonTracker()
    v_ego_ms = 15.0  # 54km/h
    dt = ROUTE_SPEED_LOOP_DT
    dist = 100.0
    speed_kph = 25.0
    streak_history = []
    promoted_history = []
    for frame in range(6):
        # 물리적으로 실재하는 지점 -- 매 프레임 vEgo*dt만큼 자연 감소.
        dist -= v_ego_ms * dt
        orphans = [[0]]
        distances = [dist]
        speeds = [speed_kph]
        active, d, s, streak, err, promoted = tracker.step(orphans, distances, speeds, v_ego_ms)
        streak_history.append(streak)
        promoted_history.append(promoted)
    check("real_curve_streak_monotonic_increase",
          streak_history == sorted(streak_history) and streak_history[-1] >= streak_history[0],
          f"streak_history={streak_history}")
    check("real_curve_eventually_promoted",
          any(promoted_history),
          f"promoted_history={promoted_history}, streak_history={streak_history}")
    check("real_curve_promoted_at_streak_threshold",
          promoted_history[PROVISIONAL_PROMOTE_STREAK - 1] is True,
          f"promoted_history={promoted_history}")

    # ---- 검증2b: 단발성 노이즈(매 프레임 위치 무관) -- streak 계속 1, 승격 안 됨 ----
    tracker2 = ProvisionalSingletonTracker()
    noise_positions = [40.0, 120.0, 8.0, 95.0, 30.0, 200.0]
    streak_history2 = []
    for pos in noise_positions:
        orphans = [[0]]
        distances = [pos]
        speeds = [30.0]
        active, d, s, streak, err, promoted = tracker2.step(orphans, distances, speeds, v_ego_ms)
        streak_history2.append((streak, promoted))
    check("noise_never_promoted",
          all(not p for _, p in streak_history2),
          f"streak_history2={streak_history2}")
    check("noise_streak_stays_at_1",
          all(s == 1 for s, _ in streak_history2),
          f"streak_history2={streak_history2}")

    # ---- 검증2c: 고립 후보가 아예 없는 프레임 -- active=False, 상태 리셋 ----
    tracker3 = ProvisionalSingletonTracker()
    tracker3.step([[0]], [50.0], [20.0], v_ego_ms)  # 먼저 하나 시작
    active, d, s, streak, err, promoted = tracker3.step([], [], [], v_ego_ms)
    check("no_orphan_frame_inactive", active is False and streak == 0,
          f"active={active} streak={streak}")

    # ---- 검증3: shadow tracker가 실제 apex 상태(mp>=2 clusters)와 완전
    # 독립적으로 계산됨을 시나리오로 재확인(같은 프레임에서 clusters도
    # 있고 orphan도 있는 경우, tracker는 clusters를 전혀 참조하지 않음) ----
    idxs_mixed = [0, 1, 2, 3]
    dist_mixed = [30.0, 90.0, 95.0, 200.0]  # 0=고립, (1,2)=클러스터, 3=고립
    clusters_mixed, orphans_mixed = derive_clusters_and_orphans(idxs_mixed, dist_mixed)
    check("mixed_scenario_clusters_correct", clusters_mixed == [[1, 2]],
          f"clusters={clusters_mixed}")
    check("mixed_scenario_orphans_correct", orphans_mixed == [[0], [3]],
          f"orphans={orphans_mixed}")

    return results


def main():
    results = run_tests()
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_total = len(results)
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        line = f"[{status}] {name}"
        if not ok:
            line += f"  ({detail})"
        print(line)
    print(f"\n{n_pass}/{n_total} PASS")
    if n_pass != n_total:
        sys.exit(1)


if __name__ == "__main__":
    main()
