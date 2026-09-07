#!/usr/bin/env python3
"""
sim_route_296_active_reacquire_gap.py (296차 신규)

목적
----
295차까지의 세션(사용자 + ChatGPT 협업 세션)에서 나온 설계 논의를 실측
검증하기 위한 도구.

논의 요지: `carrot_navi_route()` 1217행

    apex_passed_or_lost = apex_mode in ("passed", "lost", "new")

는 continuity가 "passed"/"lost"로 판정하면서 **같은 프레임에 새 apex를
이미 재탐색(reacquire)한 경우**에도 무조건 RELEASE시킨다. 이때
`apex_idx`/`apex_dist`/`apex_speed`는 이미 새 apex(B)의 유효한 값인데도
그 데이터를 버리고 route_active=False로 떨어뜨린 뒤, 다음 프레임부터
INERT 게이트를 처음부터 다시 통과시켜야 한다.

**"new"는 이 상황에서 실제로 나오지 않는다는 점이 이번 세션 논의로
정정됨**(WIP.md/대화 기록 296차 참고) -- `_route_cluster_continuity_step()`
805행 `(reset_reason or "new")`는 reset_reason이 이미 "passed"/"lost"로
설정된 경우 그 값을 그대로 반환하므로, route_active=True인 도중에는
"passed"/"lost"만 나온다. "new"는 진입 시점에 locked apex 자체가 없었던
경우(=INERT 쪽)에만 나온다.

**왜 기존 289~293차 분류로는 이 현상의 빈도를 알 수 없는가**: 289차
계열 스크립트(`sim_route_289_margin_ab_real_log.py`,
`sim_route_292_continuity_root_cause.py`)는 raw `routeApexSpeed`가
0/NaN으로 찍히는 "cutoff 프레임"을 찾아서만 에피소드를 잡는다. 그런데
"passed/lost + 같은 프레임 재탐색 성공"은 apex_speed가 A의 값에서 B의
값으로 **끊김 없이(0/NaN 프레임 없이) 즉시 점프**하므로, 저 gap-탐지
방법론 자체가 이 케이스를 원천적으로 볼 수 없다. 즉 293차가 실측한
"lost_with_candidates_present 1/39(ep108)"는 이 현상과 무관한 별개
통계(진짜 데이터 공백 + 클러스터링 매칭 실패)이며, 이 스크립트가 찾는
현상의 실제 빈도에 대해 어떤 상한/하한도 주지 못한다.

이 스크립트가 하는 일
----------------------
`route_find_clusters()`(454~466행) + `_route_cluster_continuity_step()`
(735~808행) + `carrot_navi_route()`의 ACTIVE/INERT 상태기계(1174~1324행,
266차 confidence blend 포함)를 그대로 이식해 프레임 단위로 재생하면서,
**"route_active=True로 진입한 프레임에서 mode가 passed/lost이면서
apex_speed가 None이 아닌"** 이벤트("seamless forced release")를 직접
카운트한다.

각 이벤트에 대해 두 가지 보조 지표를 추가로 계산한다(§28 -- 추측 아닌
코드/게이트 동일 산식 재적용으로 판정):

- `immediate_reentry`: INERT 게이트(confidence blend 포함)를 그대로
  재적용했을 때 0프레임 지연으로 즉시 ACTIVE 재진입했을지 여부.
  **self-test로 실제 확인한 구조적 한계**: 재탐색 성공 시 streak가
  항상 1로 리셋되고(704행) `confidence_from_streak(1)=0.0`이라
  eff_apex_speed가 그 프레임엔 무조건 v_ego_kph 그대로 나온다 --
  즉 이 지표는 confidence blend 설계상 재탐색 직후에는 거의 항상
  False로 나오도록 구조화돼 있어(streak가 몇 프레임 쌓여야 gate에
  닿음), "0프레임 flicker가 실제로 있는가"의 답으로는 쓸모가 제한적임을
  self-test 단계에서 발견함 -- 다음 세션 실 corpus 분석 시 이 지표
  단독으로 "낭비 없음"을 결론 내리지 말 것.
- `new_apex_needs_decel`(위 한계 보완용 신규 지표): confidence blend와
  무관하게 `v_ego_ms > apex_speed/3.6`인지만 본다 -- "재탐색된 새
  apex가 애초에 감속 대상이긴 한가"를 순수 물리량으로 판정, 사용자/
  ChatGPT가 제안한 "감속 필요/불필요" 분기와 직접 대응된다.

입력 (실 corpus, 다음 세션 예정)
--------------------------------
extract_log.py --with-navi-paths로 뽑은 CSV + analysis_helpers.py::
recompute_route_curvature_speed()로 naviPaths 폴리라인에서 매 프레임
전체 후보 리스트(distance, speed_cap)를 복원해 사용한다 -- 273차가
top-3 candidate 텔레메트리만으로 continuity를 근사했던 것과 달리, 이
방식은 stage0(클러스터링 이전) 전체 후보를 그대로 재현할 수 있어
273차가 남긴 "top-3 근사 한계" 문제를 이 스크립트에서는 겪지 않는다
(단, 273차 자체의 baseline 재현 실패는 이 스크립트의 범위가 아니다 --
별개 이슈로 남겨둠).

이번 세션 상태: **corpus 없음 -- self-test(synthetic)만 실행**.
"합성 검증 PASS / 실차 미검증"(§29).

사용
----
    python3 sim_route_296_active_reacquire_gap.py --self-test

    (실 corpus 확보 후)
    python3 sim_route_296_active_reacquire_gap.py \\
        --frames-json frames.json  # [{t, v_ego_ms, v_ego_kph, road_limit_speed,
                                     #   candidates:[(dist,speed),...],
                                     #   ctrl_end, decel_rate}, ...]
"""
import argparse
import json
import math
import sys

# ---- carrot_man.py 상수 그대로 이식 (HEAD d2f47d1=290차, 296차 세션
# 확인 시점 기준 실제 소스값과 대조 완료) ----
ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_ACTIVE_RELEASE_MARGIN_RATIO = 1.05
ROUTE_RELEASE_DIST_M = 10.0
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
ROUTE_APEX_MISS_TOLERANCE_FRAMES = 6
CONTINUITY_MATCH_TOLERANCE_M = 20.0
CONFIDENCE_TAU = 6.3


def route_find_clusters(idxs, distances, min_points, max_gap_m):
    # carrot_man.py 454~466행 그대로.
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


def confidence_from_streak(streak, tau=CONFIDENCE_TAU):
    # carrot_man.py 249~254행 그대로.
    if streak <= 1:
        return 0.0
    return 1.0 - math.exp(-(streak - 1) / tau)


class ContinuityState:
    """carrot_man.py::_route_cluster_continuity_step()(735~808행) 이식.
    인스턴스 상태만 다르고 분기/반환값은 프로덕션과 동일하게 유지한다
    (§27 -- 게이트 산식 자체를 손대지 않는 것과 동일 원칙을 재현 코드에도
    적용: 이 클래스가 실제와 달라지면 아래에서 세는 이벤트 자체가
    무의미해지므로, 어떤 변형도 주석 없이 넣지 않는다).
    """

    def __init__(self):
        self.locked_dist = None
        self.locked_speed = None
        self.miss_frames = 0
        self.streak = 0

    def step(self, clusters, distances, speeds, v_ego_ms, dt=ROUTE_SPEED_LOOP_DT):
        predicted = (self.locked_dist - v_ego_ms * dt) if self.locked_dist is not None else None

        matched = None
        if predicted is not None and predicted > 0 and clusters:
            best, best_err = None, None
            for c in clusters:
                idx = c[0]
                err = abs(distances[idx] - predicted)
                if best_err is None or err < best_err:
                    best, best_err = idx, err
            if best_err is not None and best_err <= CONTINUITY_MATCH_TOLERANCE_M:
                matched = best

        if matched is not None:
            self.locked_dist = distances[matched]
            self.locked_speed = speeds[matched]
            self.miss_frames = 0
            self.streak += 1
            return matched, self.locked_dist, self.locked_speed, "matched", self.streak

        reset_reason = None
        if self.locked_dist is not None:
            if predicted is not None and predicted <= 0:
                reset_reason = "passed"
            else:
                self.miss_frames += 1
                if (self.miss_frames < ROUTE_APEX_MISS_TOLERANCE_FRAMES
                        and predicted is not None and predicted > 0):
                    self.locked_dist = predicted
                    return -1, predicted, self.locked_speed, "held", self.streak
                reset_reason = "lost"
            self.locked_dist = None
            self.locked_speed = None
            self.miss_frames = 0

        if clusters:
            idx = clusters[0][0]
            self.locked_dist = distances[idx]
            self.locked_speed = speeds[idx]
            self.miss_frames = 0
            self.streak = 1
            return idx, distances[idx], speeds[idx], (reset_reason or "new"), self.streak

        self.streak = 0
        return -1, None, None, (reset_reason or "none"), self.streak


class RouteStateMachine:
    """carrot_navi_route()의 ACTIVE/INERT/RELEASE 판정(1174~1324행,
    266차 confidence blend 포함)만 이식 -- vturn/road_limit_speed 필터
    이전 단계(navi 맵 곡률 추출, stage0 candidate 산출)는 호출자가
    이미 필터링한 candidates 리스트로 넘겨준다고 가정(§27, 이 스크립트의
    관심사는 stage2 이후이므로 stage0/1 재구현은 범위 밖).
    """

    def __init__(self):
        self.continuity = ContinuityState()
        self.route_active = False
        self.events = []  # seamless forced-release 이벤트 로그

    def _inert_gate(self, apex_speed, apex_dist, apex_streak, v_ego_ms, v_ego_kph,
                     ctrl_end, decel_rate):
        """INERT 게이트만 떼어내 재사용(강제 RELEASE 이벤트의
        immediate_reentry 판정에도 그대로 씀 -- carrot_navi_route()의
        else 분기, 1283~1324행과 동일 산식)."""
        conf = confidence_from_streak(apex_streak)
        eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
        target_ms = eff_apex_speed / 3.6
        eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)
        if v_ego_ms <= target_ms:
            return False, None
        if eff_dist <= 0:
            return False, None
        required_decel_mss = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
        return required_decel_mss >= decel_rate, required_decel_mss

    def step(self, t, candidates, v_ego_ms, v_ego_kph, ctrl_end, decel_rate):
        """candidates: [(dist, speed), ...] road_limit_speed 필터를 이미
        통과한 이번 프레임의 원시 후보 리스트(stage0 결과, clustering
        이전) -- production의 `candidates = [k for k in range(len(speeds))
        if speeds[k] < road_limit_speed]` 다음 단계에 해당."""
        distances = [c[0] for c in candidates]
        speeds = [c[1] for c in candidates]
        idxs = list(range(len(candidates)))
        clusters = route_find_clusters(idxs, distances, ROUTE_CLUSTER_MIN_POINTS,
                                        ROUTE_CLUSTER_MAX_GAP_M)

        was_active = self.route_active
        apex_idx, apex_dist, apex_speed, mode, streak = self.continuity.step(
            clusters, distances, speeds, v_ego_ms)

        # -- 이벤트 탐지: was_active=True인데 mode가 passed/lost이고
        # apex_speed가 있다(=같은 프레임 재탐색 성공) --
        if was_active and mode in ("passed", "lost") and apex_speed is not None:
            would_reenter, required_decel = self._inert_gate(
                apex_speed, apex_dist, streak, v_ego_ms, v_ego_kph, ctrl_end, decel_rate)
            # [296차 self-test 중 발견] streak는 재탐색 성공 시 항상 1로
            # 리셋되고(704행), confidence_from_streak(1)=0.0(249~254행)이라
            # eff_apex_speed=v_ego_kph 그대로 -> target_ms==v_ego_ms가 되어
            # `v_ego_ms<=target_ms`가 항상 참으로 나온다. 즉
            # `immediate_reentry`는 confidence blend 설계상 재탐색 직후
            # 프레임에는 구조적으로 거의 항상 False가 된다(streak가 쌓여야
            # gate에 도달) -- "0프레임 flicker"를 재는 지표로는 이 값
            # 하나만으로 불충분함을 self-test로 확인(아래 참고). 그래서
            # confidence blend와 무관하게 "이 새 apex가 애초에 감속
            # 대상이긴 한가"(conf=1.0 가정, streak 무관)를 별도로
            # 계산해 `new_apex_needs_decel`로 분리해서 담는다 -- 이게
            # 사용자/ChatGPT가 제안한 "감속 필요/불필요" 분기 판정에
            # 더 가깝다.
            new_apex_needs_decel = v_ego_ms > (apex_speed / 3.6)
            self.events.append({
                "t": t, "mode": mode, "new_apex_dist": apex_dist,
                "new_apex_speed": apex_speed, "immediate_reentry": would_reenter,
                "required_decel_mss": required_decel,
                "new_apex_needs_decel": new_apex_needs_decel,
            })

        if mode == "none" or apex_speed is None:
            if self.route_active:
                self.route_active = False
            out_speed = None
        else:
            if self.route_active:
                apex_passed_or_lost = mode in ("passed", "lost", "new")
                speed_reached = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
                dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
                if apex_passed_or_lost or speed_reached or dist_reached:
                    self.route_active = False
                    out_speed = None
                else:
                    conf = confidence_from_streak(streak)
                    eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
                    target_ms = eff_apex_speed / 3.6
                    eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)
                    if eff_dist <= 0 or v_ego_ms <= target_ms:
                        out_speed_ms = v_ego_ms
                    else:
                        required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                        applied = min(max(required, 0.0), decel_rate)
                        out_speed_ms = max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
                    out_speed = out_speed_ms * 3.6
            else:
                would_active, required_decel = self._inert_gate(
                    apex_speed, apex_dist, streak, v_ego_ms, v_ego_kph, ctrl_end, decel_rate)
                if v_ego_ms <= (confidence_from_streak(streak) * apex_speed
                                + (1.0 - confidence_from_streak(streak)) * v_ego_kph) / 3.6:
                    out_speed = None
                elif would_active:
                    self.route_active = True
                    conf = confidence_from_streak(streak)
                    eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
                    target_ms = eff_apex_speed / 3.6
                    applied = min(max(required_decel, 0.0), decel_rate)
                    out_speed_ms = max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
                    out_speed = out_speed_ms * 3.6
                else:
                    conf = confidence_from_streak(streak)
                    eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
                    target_ms = eff_apex_speed / 3.6
                    eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)
                    out_speed = v_ego_kph if eff_dist <= 0 else None
        return out_speed, mode, self.route_active


# ---------------------------------------------------------------------
# self-test (synthetic) -- 실 corpus 없이도 상태기계 자체의 정합성을
# 검증. §29 "합성 검증 PASS / 실차 미검증" 원칙에 따라 아래 결과만으로
# 실제 corpus에서의 빈도를 주장하지 않는다.
# ---------------------------------------------------------------------

def _run_frames(sm, frames):
    results = []
    for f in frames:
        out_speed, mode, active = sm.step(
            f["t"], f["candidates"], f["v_ego_ms"], f["v_ego_kph"],
            f.get("ctrl_end", 7.0), f.get("decel_rate", 0.70))
        results.append((f["t"], mode, active, out_speed))
    return results


def self_test():
    ok = True

    # 시나리오 1: matched 유지 -- apex가 예측 위치 근처에 계속 잡힘,
    # 이벤트 없어야 함.
    sm = RouteStateMachine()
    sm.route_active = True
    sm.continuity.locked_dist = 100.0
    sm.continuity.locked_speed = 40.0
    sm.continuity.streak = 5
    frames = []
    dist = 100.0
    for i in range(5):
        dist -= 20.0 * ROUTE_SPEED_LOOP_DT
        # ROUTE_CLUSTER_MIN_POINTS=2 -- 2개 후보로 클러스터 형성.
        frames.append({"t": i * 0.05, "candidates": [(dist, 40.0), (dist + 3.0, 40.0)],
                        "v_ego_ms": 20.0, "v_ego_kph": 72.0})
    results = _run_frames(sm, frames)
    modes = [r[1] for r in results]
    if len(sm.events) != 0:
        print("FAIL: 시나리오1(matched 유지)에서 이벤트가 발생함:", sm.events)
        ok = False
    elif not all(m == "matched" for m in modes):
        print(f"FAIL: 시나리오1에서 mode가 전부 matched가 아님: {modes}")
        ok = False
    else:
        print("PASS: 시나리오1(matched 유지) -- 이벤트 0건, mode 전부 matched 확인")

    # 시나리오 2: 진짜 passed, 재탐색 후보 없음 -- RELEASE는 발생하지만
    # apex_speed=None이므로 우리 이벤트 조건(apex_speed is not None)에는
    # 해당하지 않아야 함(§ "정상 완료" 케이스, 292차 분류의 case 1).
    sm = RouteStateMachine()
    sm.route_active = True
    sm.continuity.locked_dist = 1.0
    sm.continuity.locked_speed = 40.0
    sm.continuity.streak = 5
    frames = [{"t": 0.0, "candidates": [], "v_ego_ms": 15.0, "v_ego_kph": 54.0}]
    _run_frames(sm, frames)
    if len(sm.events) != 0:
        print("FAIL: 시나리오2(진짜 passed, 후보없음)에서 이벤트 발생:", sm.events)
        ok = False
    elif sm.route_active:
        print("FAIL: 시나리오2에서 route_active가 False로 안 떨어짐")
        ok = False
    else:
        print("PASS: 시나리오2(진짜 passed, 후보없음) -- 이벤트 0건, RELEASE 정상")

    # 시나리오 3 (핵심): "passed" + 같은 프레임 재탐색 성공 -- 이벤트가
    # 정확히 1건 잡혀야 하고, mode="passed"여야 하며, "new"가 아니어야
    # 한다(이번 세션 정정 사항의 핵심 회귀 테스트).
    sm = RouteStateMachine()
    sm.route_active = True
    sm.continuity.locked_dist = 0.3     # A: 다음 프레임 predicted<=0 확정
    sm.continuity.locked_speed = 40.0
    sm.continuity.streak = 5
    # ROUTE_CLUSTER_MIN_POINTS=2 -- 클러스터 형성에 후보 2개 필요(단일
    # 후보는 클러스터가 안 되어 "none"으로 새 버그를 만들 뻔함, 디버깅
    # 중 실제로 발견 -- 아래 회귀 방지 주석).
    frames = [{"t": 0.0, "candidates": [(80.0, 30.0), (85.0, 30.0)],  # B: 80m, 30kph
               "v_ego_ms": 15.0, "v_ego_kph": 54.0}]
    _run_frames(sm, frames)
    if len(sm.events) != 1:
        print(f"FAIL: 시나리오3(passed+재탐색)에서 이벤트 {len(sm.events)}건"
              f" (기대: 1건)")
        ok = False
    elif sm.events[0]["mode"] != "passed":
        print(f"FAIL: 시나리오3 이벤트 mode={sm.events[0]['mode']} (기대: passed)")
        ok = False
    elif sm.route_active:
        print("FAIL: 시나리오3에서 강제 RELEASE가 재현되지 않음"
              " (route_active가 여전히 True)")
        ok = False
    else:
        print(f"PASS: 시나리오3(passed+재탐색, 핵심 케이스) -- 이벤트 1건,"
              f" mode=passed(≠new) 확인, immediate_reentry="
              f"{sm.events[0]['immediate_reentry']}")

    # 시나리오 4: "lost" + 같은 프레임 재탐색 성공 (miss_frames 초과 경로).
    sm = RouteStateMachine()
    sm.route_active = True
    sm.continuity.locked_dist = 200.0
    sm.continuity.locked_speed = 40.0
    sm.continuity.miss_frames = ROUTE_APEX_MISS_TOLERANCE_FRAMES - 1
    sm.continuity.streak = 5
    frames = [{"t": 0.0, "candidates": [(90.0, 35.0), (95.0, 35.0)],
               "v_ego_ms": 15.0, "v_ego_kph": 54.0}]
    _run_frames(sm, frames)
    if len(sm.events) != 1 or sm.events[0]["mode"] != "lost":
        print(f"FAIL: 시나리오4(lost+재탐색) -- events={sm.events}")
        ok = False
    else:
        print("PASS: 시나리오4(lost+재탐색) -- 이벤트 1건, mode=lost 확인")

    # 시나리오 5: INERT 상태에서 "new"로 재진입 -- was_active=False이므로
    # 이벤트가 절대 잡히면 안 됨(이번 세션 핵심 주장: "new"는
    # route_active=True에서 못 나온다 -> was_active=False일 때만 나오고,
    # 그때는 이벤트 조건(was_active=True)에서 애초에 제외됨).
    sm = RouteStateMachine()
    sm.route_active = False
    frames = [{"t": 0.0, "candidates": [(150.0, 30.0), (155.0, 30.0)],
               "v_ego_ms": 10.0, "v_ego_kph": 36.0}]
    results = _run_frames(sm, frames)
    if results[0][1] != "new":
        print(f"FAIL: 시나리오5 setup 오류 -- mode={results[0][1]} (기대: new)")
        ok = False
    elif len(sm.events) != 0:
        print("FAIL: 시나리오5(INERT->new)에서 이벤트 발생(있으면 안 됨):",
              sm.events)
        ok = False
    else:
        print("PASS: 시나리오5(INERT->new) -- mode=new 확인, 이벤트 0건"
              " ('new'는 ACTIVE에서 안 나온다는 주장과 일치)")

    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--frames-json", default=None,
                     help="실 corpus에서 뽑은 프레임 리스트(JSON) -- 다음 세션용")
    args = ap.parse_args()

    if args.self_test or not args.frames_json:
        ok = self_test()
        print("\n=== self-test 결과:", "5/5 PASS" if ok else "FAIL 있음", "===")
        if not ok:
            sys.exit(1)
        if not args.frames_json:
            print("(--frames-json 없이 실행됨 -- 실 corpus 분석은 다음 세션)")
        return

    with open(args.frames_json) as f:
        frames = json.load(f)
    sm = RouteStateMachine()
    _run_frames(sm, frames)
    print(f"총 프레임: {len(frames)}, seamless forced-release 이벤트: {len(sm.events)}건")
    n_immediate = sum(1 for e in sm.events if e["immediate_reentry"])
    n_needs_decel = sum(1 for e in sm.events if e["new_apex_needs_decel"])
    print(f"  - immediate_reentry=True(confidence blend 무시하고 0프레임 재진입): {n_immediate}건")
    print(f"  - new_apex_needs_decel=True(재탐색된 apex가 실제로 v_ego>target,"
          f" 즉 감속 대상): {n_needs_decel}건 / {len(sm.events)}건")
    for e in sm.events:
        print(f"  t={e['t']:.2f} mode={e['mode']} new_dist={e['new_apex_dist']:.1f}"
              f" new_speed={e['new_apex_speed']:.1f} needs_decel="
              f"{e['new_apex_needs_decel']} immediate_reentry={e['immediate_reentry']}")


if __name__ == "__main__":
    main()
