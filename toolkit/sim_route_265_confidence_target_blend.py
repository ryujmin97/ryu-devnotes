#!/usr/bin/env python3
"""
sim_route_265_confidence_target_blend.py (265차 신규)

목적: 264차가 확정한 "confidence 스코어링 공식은 persistence(streak) 단독
기반"이라는 방향과, 이번 265차에서 사용자가 승인한 "연속 가중치(blend)"
소비 방식을 실제 프로덕션 코드 구조에 맞춰 구현/검증한다.

**아키텍처 확인 (carrot_man.py 실제 코드 대조, 265차)**:
1. 실제 `_route_cluster_continuity_step()`은 260차 분석 스크립트의
   MultiTrackContinuity(여러 후보 동시추적)와 달리 단일 lock만 추적한다
   (`new` 상태에서 clusters[0]을 즉시 lock). 따라서 confidence는 "여러
   후보 중 무엇을 기준으로 blend할지" 선택 문제가 아니라, 현재 lock
   하나의 streak만으로 정의된다 -- 원래 질문(3) "멀티트랙 중 선택 기준"은
   프로덕션 구조상 해당 없음으로 확인됨.
2. **불일치 발견**: `CONTINUITY_MATCH_TOLERANCE_M`이 프로덕션(carrot_man.py,
   258차 HEAD)은 10.0m인데, 260차 분석 스크립트(sim_route_260_confidence_
   signals.py)는 15.0m을 사용했다. 이 스크립트는 프로덕션 값(10.0)을
   그대로 쓴다 -- 260차 실측 결과(streak 분포 등)가 이 차이로 얼마나
   달라지는지는 별도 검증 필요(미해결 항목으로 남김).
3. **삽입 지점**: apex_speed는 `target_ms = apex_speed / 3.6` 단 한
   지점(INERT 게이트/ACTIVE STEP2 공통)에서만 소비된다. confidence blend는
   out_speed를 직접 조작하지 않고, 이 지점의 입력값만 다음과 같이
   대체한다:
       eff_apex_speed_kph = confidence*apex_speed + (1-confidence)*v_ego_kph
       target_ms = eff_apex_speed_kph / 3.6
   ACTIVE/INERT 상태기계(257차 확정 설계) 자체는 완전히 그대로 유지 --
   §27 최소변경 원칙에 부합. "이전 프레임 출력 의존 없음"(223차 무상태
   원칙)도 유지됨 -- blend 대상이 "이전 값"이 아니라 "현재 vEgo"라서
   cold start 문제 자체가 발생하지 않는다.

confidence 공식 (263/264차가 검증한 4개 신호 중 유일하게 채택된
persistence(streak) 단독, 260차 실측 버킷 streak=1/2-5/6-20/20+를
캘리브레이션 앵커로 사용한 포화 지수함수):
    confidence(streak) = 1 - exp(-(streak-1)/TAU)
    TAU=6.3 default -> confidence(1)=0(정확히 0, 신규 미검증 후보는
    개입 0), confidence(6)~=0.55, confidence(20)~=0.95

streak 정의는 260차와 동일: matched 프레임만 카운트(+1), held 프레임은
증가시키지 않고 유지, new/passed/lost 전이 시 1로 리셋.

**중요**: 아래는 프로덕션 carrot_navi_route()의 관련 분기를 최대한 충실히
이식한 것이나, 실차 코드 자체를 실행하는 것이 아니라 재구현(port)이다.
이 스크립트만으로 "검증 완료"라 부르지 않는다(§28/§29) -- 구조적
self-test(synthetic)까지가 265차의 범위였고, 실제 corpus(seg12-16/
dashcam) 재검증은 파일 재업로드 후 별도로 수행한다.

[268차 추가] corpus 모드 구현 완료(266차 다음 작업 1번). 260차
sim_route_260_confidence_signals.py의 CSV 로딩/게이트(nRoadLimitSpeed)/
클러스터링 로직을 §21에 따라 그대로 재사용했다. baseline과
confidence-blend 두 트래커를 완전히 독립적으로(서로 영향 없이) 같은
입력으로 재생해 윈도우 구간별 out_speed 차이 + 267차가 발견한 "지속
접근 중 순간 streak=1 리셋(flicker)" 후보 프레임 수를 출력한다.
아래 self-test(synthetic)만으로는 이 corpus 모드 자체의 정합성이
검증되지 않으므로, 실 corpus 재업로드 후 반드시 별도 실행/확인이
필요하다(§28 -- 아직 실측 미실시, 아래 함수 자체는 정적 분석/합성
CSV 자체검증만 완료).

사용법:
    # synthetic self-test만 실행(corpus 없이 구조 검증)
    python3 sim_route_265_confidence_target_blend.py --self-test

    # 실제 corpus로 baseline vs blended 비교(파일 있을 때)
    python3 sim_route_265_confidence_target_blend.py <route.csv> \
        --window 2116 2122.2 --label s_curve
"""
import argparse
import csv
import math
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

# ---- carrot_man.py 실제 상수 그대로(258차 HEAD 대조, 265차) ----
ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_ACTIVE_RELEASE_MARGIN_RATIO = 1.1
ROUTE_RELEASE_DIST_M = 20.0
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
ROUTE_APEX_MISS_TOLERANCE_FRAMES = 3
CONTINUITY_MATCH_TOLERANCE_M = 10.0  # [265차] 260차 스크립트는 15.0 사용 -- 불일치, 프로덕션값 채택

# [268차 신규] corpus 모드 전용 -- naviPaths -> (dist, curv, speed) 재계산
# 파라미터. 260차 스크립트와 동일값(§21 재사용, 동일 corpus 비교 목적상
# 반드시 일치해야 함).
MACRO_SAMPLE = 4
FINE_SAMPLE = 1
FLOOR_THRESHOLD = 0.001  # 157차 패치(ROUTE_CURVE_NEGLIGIBLE_THRESHOLD) 재현

# [268차 신규] 260/267차가 써온 known-good corpus(0000039a--7b602ffb85
# seg12-16)의 3구간 기본 윈도우 -- 260차 DEFAULT_WINDOWS와 동일(§21).
DEFAULT_WINDOWS = [
    (2190.0, 2225.0, "tunnel"),
    (2108.0, 2112.0, "ic_gore"),
    (2116.0, 2122.2, "s_curve"),
]

# PARAMS_REGISTRY 등록값(사용자 실측 기본값, FINDINGS.md 256차 인용)
AUTO_NAVI_SPEED_DECEL_RATE = 1.0      # m/s^2
AUTO_NAVI_SPEED_CTRL_END = 7.0        # s (219/220차부터 7->10 변경 논의 중, 아직 7)

# [265차 신규] confidence 공식 파라미터
CONFIDENCE_TAU_DEFAULT = 6.3


def confidence_from_streak(streak, tau=CONFIDENCE_TAU_DEFAULT):
    """streak>=1. streak=1에서 정확히 0.0(신규 미검증 후보는 개입 0),
    이후 포화 지수함수로 1.0에 근접."""
    if streak <= 1:
        return 0.0
    return 1.0 - math.exp(-(streak - 1) / tau)


class SingleLockContinuity:
    """carrot_man.py::_route_cluster_continuity_step() 이식(265차) --
    streak 카운터 추가(260차 정의: matched만 +1, held 유지, reset 시 1)."""

    def __init__(self):
        self.locked_dist = None
        self.locked_speed = None
        self.miss_frames = 0
        self.streak = 0  # 아직 lock 없음

    def step(self, clusters, distances, speeds, v_ego_ms):
        dt = ROUTE_SPEED_LOOP_DT
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
            self.streak += 1  # [265차] matched만 streak 증가
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
                    # held: streak 유지(증가도 리셋도 안 함), idx=-1
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
            self.streak = 1  # [265차] new/passed/lost 재탐색 시 1로 리셋
            return idx, distances[idx], speeds[idx], (reset_reason or "new"), self.streak

        self.streak = 0
        return -1, None, None, (reset_reason or "none"), self.streak


def route_step(tracker, clusters, distances, speeds, v_ego_ms, v_ego_kph,
                route_active_state, use_confidence, tau=CONFIDENCE_TAU_DEFAULT):
    """carrot_navi_route()의 INERT/ACTIVE 분기를 이식(265차). out_speed와
    갱신된 route_active를 반환. use_confidence=False면 264차 이전(현재
    프로덕션) 동작과 동일(confidence=1.0 고정) -- baseline.
    [268차] 반환값에 apex_mode를 5번째 원소로 추가(corpus 모드의 267차
    flicker 탐지에 필요 -- 이 프레임에서 tracker가 new/passed/lost로
    리셋됐는지 상위에서 알아야 함). 기존 4-tuple 소비 코드(self_test)도
    함께 수정."""
    apex_idx, apex_dist, apex_speed, apex_mode, streak = tracker.step(
        clusters, distances, speeds, v_ego_ms)

    if apex_mode == "none" or apex_speed is None:
        return None, False, streak, None, apex_mode

    confidence = confidence_from_streak(streak, tau) if use_confidence else 1.0
    eff_apex_speed = confidence * apex_speed + (1.0 - confidence) * v_ego_kph
    target_ms = eff_apex_speed / 3.6

    if route_active_state:
        apex_passed_or_lost = apex_mode in ("passed", "lost", "new")
        # [265차] release 판정(speed_reached)은 실제 apex_speed 기준 유지 --
        # confidence로 낮춘 eff_apex_speed를 release 기준에 쓰면 "약한
        # confidence일수록 더 쉽게 release"가 되어 목적(노이즈 억제)과
        # 무관한 부작용을 만들 수 있어 원 apex_speed를 그대로 사용한다.
        speed_reached = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
        dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
        if apex_passed_or_lost or speed_reached or dist_reached:
            return None, False, streak, confidence, apex_mode
        eff_dist = max(0.0, apex_dist - target_ms * AUTO_NAVI_SPEED_CTRL_END)
        if eff_dist <= 0 or v_ego_ms <= target_ms:
            out_speed_ms = v_ego_ms
        else:
            required_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            applied_decel = min(max(required_decel, 0.0), AUTO_NAVI_SPEED_DECEL_RATE)
            out_speed_ms = max(target_ms, v_ego_ms - applied_decel * ROUTE_SPEED_LOOP_DT)
        return out_speed_ms * 3.6, True, streak, confidence, apex_mode

    eff_dist = max(0.0, apex_dist - target_ms * AUTO_NAVI_SPEED_CTRL_END)
    if v_ego_ms <= target_ms:
        return None, False, streak, confidence, apex_mode
    if eff_dist <= 0:
        return v_ego_kph, False, streak, confidence, apex_mode
    required_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
    if required_decel >= AUTO_NAVI_SPEED_DECEL_RATE:
        applied_decel = min(max(required_decel, 0.0), AUTO_NAVI_SPEED_DECEL_RATE)
        out_speed_ms = max(target_ms, v_ego_ms - applied_decel * ROUTE_SPEED_LOOP_DT)
        return out_speed_ms * 3.6, True, streak, confidence, apex_mode
    return None, False, streak, confidence, apex_mode


def find_clusters(idxs, dists, min_points, max_gap_m):
    if not idxs:
        return []
    clusters, cur = [], [idxs[0]]
    for i in idxs[1:]:
        if dists[i] - dists[cur[-1]] <= max_gap_m:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_points]


# ============================================================
# Synthetic self-test (corpus 없이 구조 검증, 254차 선례 방식 계승)
# ============================================================

def run_scenario(frames, tau=CONFIDENCE_TAU_DEFAULT, label=""):
    """frames: list of (distances, speeds, v_ego_ms) per-frame synthetic
    입력. baseline(confidence 없음, 현재 프로덕션 동작)과 blended(265차
    제안) 각각 재생해 out_speed 시퀀스를 비교한다."""
    tracker_base = SingleLockContinuity()
    tracker_conf = SingleLockContinuity()
    active_base = False
    active_conf = False
    print(f"\n=== self-test: {label} ===")
    print(f"{'t':>4} {'vEgo_kph':>9} {'base_out':>9} {'conf_out':>9} "
          f"{'streak':>6} {'confidence':>10}")
    for i, (dists, speeds, v_ego_ms) in enumerate(frames):
        v_ego_kph = v_ego_ms * 3.6
        candidates = list(range(len(speeds)))
        clusters = find_clusters(candidates, dists, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)

        out_base, active_base, _, _, _ = route_step(
            tracker_base, clusters, dists, speeds, v_ego_ms, v_ego_kph,
            active_base, use_confidence=False)
        out_conf, active_conf, streak, conf, _ = route_step(
            tracker_conf, clusters, dists, speeds, v_ego_ms, v_ego_kph,
            active_conf, use_confidence=True, tau=tau)

        ob = f"{out_base:.1f}" if out_base is not None else "None"
        oc = f"{out_conf:.1f}" if out_conf is not None else "None"
        cf = f"{conf:.3f}" if conf is not None else "-"
        print(f"{i:>4} {v_ego_kph:>9.1f} {ob:>9} {oc:>9} {streak:>6} {cf:>10}")


def scenario_noise_spike():
    """한 프레임만 존재하다 사라지는 노이즈성 단발 후보(streak=1로 끝남).
    기대: baseline은 즉시 감속 개입(out_speed 하락), confidence 버전은
    streak=1이라 confidence=0 -> 개입 없음(out_speed=None 유지)."""
    frames = []
    v_ego_ms = 25.0  # 90kph 근방
    # 정상 주행 5프레임(후보 없음)
    for _ in range(5):
        frames.append(([], [], v_ego_ms))
    # 1프레임만 등장하는 급커브 후보(예: GPS jitter로 추정되는 순간 스파이크)
    frames.append(([40.0, 55.0], [30.0, 30.0], v_ego_ms))
    # 다시 정상 주행(후보 소실)
    for _ in range(10):
        frames.append(([], [], v_ego_ms))
    return frames


def scenario_genuine_curve():
    """지속적으로 존재하며 서서히 접근하는 실제 커브(streak가 계속
    증가). 기대: baseline과 confidence 버전 모두 결국 target(apex_speed)
    까지 감속하되, confidence 버전은 초반 몇 프레임만 개입이 지연되고
    이후 거의 동일하게 수렴."""
    frames = []
    v_ego_ms = 25.0
    dist = 200.0
    target_speed_kph = 30.0
    # 40프레임(2초) 동안 매 프레임 동일 후보가 v_ego*dt만큼 접근
    for _ in range(60):
        frames.append(([dist, dist + 15.0], [target_speed_kph, target_speed_kph], v_ego_ms))
        dist = max(0.0, dist - v_ego_ms * ROUTE_SPEED_LOOP_DT)
    return frames


def self_test(tau=CONFIDENCE_TAU_DEFAULT):
    print("confidence(streak) 표:")
    for s in [1, 2, 3, 5, 6, 10, 15, 20, 30]:
        print(f"  streak={s:>3}: confidence={confidence_from_streak(s, tau):.3f}")

    run_scenario(scenario_noise_spike(), tau, label="noise_spike(streak=1 단발 후보)")
    run_scenario(scenario_genuine_curve(), tau, label="genuine_curve(지속 접근 커브)")


# ============================================================
# [268차 신규] 실 corpus 재생 모드 -- 266차 다음 작업 1번 구현
# (extract_log.py --with-navi-paths CSV로 baseline vs confidence-blend
# A/B 재검증. 260차 sim_route_260_confidence_signals.py의 CSV 로딩/게이트/
# 클러스터링 로직을 §21에 따라 그대로 재사용한다.)
# ============================================================

def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_dist_speed(navi_paths_str):
    """260차 build_dist_curv_speed()와 동일 계산이나, 265차 route_step은
    curvature를 쓰지 않으므로(§27 최소변경 -- 필요한 두 배열만 반환)
    (distances, speeds)만 돌려준다."""
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
    clusters, cur = [], [idxs[0]]
    for i in idxs[1:]:
        if dists[i] - dists[cur[-1]] <= max_gap_m:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_points]


def replay_corpus(rows, tau=CONFIDENCE_TAU_DEFAULT):
    """실 corpus CSV를 baseline(use_confidence=False, 264차 이전/현재
    프로덕션과 동일)과 confidence-blend(266차 patch, use_confidence=True)
    두 개의 완전히 독립된 SingleLockContinuity 트래커로 동시 재생한다.
    두 트래커는 서로의 streak/lock 상태에 영향을 주지 않는다(같은
    입력을 각자 별도로 재현) -- look-ahead 없이 그 프레임까지의 정보만
    사용(258차/260차와 동일 원칙)."""
    tracker_base = SingleLockContinuity()
    tracker_conf = SingleLockContinuity()
    active_base = False
    active_conf = False
    records = []
    for row in rows:
        if not row.get("vEgo"):
            continue
        t = float(row["t"])
        v_ego_ms = float(row["vEgo"])
        v_ego_kph = v_ego_ms * 3.6

        dists, speeds = build_dist_speed(row.get("naviPaths", ""))
        if speeds:
            threshold = gate_base_kph(row, v_ego_kph)
            c0 = gate_candidates(speeds, threshold)
            clusters = find_clusters(c0, dists, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        else:
            clusters = []

        out_base, active_base, streak_b, conf_b, mode_b = route_step(
            tracker_base, clusters, dists, speeds, v_ego_ms, v_ego_kph,
            active_base, use_confidence=False)
        out_conf, active_conf, streak_c, conf_c, mode_c = route_step(
            tracker_conf, clusters, dists, speeds, v_ego_ms, v_ego_kph,
            active_conf, use_confidence=True, tau=tau)

        records.append({
            "t": t,
            "v_ego_kph": v_ego_kph,
            "out_base": out_base,
            "active_base": active_base,
            "out_conf": out_conf,
            "active_conf": active_conf,
            "streak": streak_c,
            "confidence": conf_c,
            "mode_conf": mode_c,
        })
    return records


def summarize_corpus_window(records, lo, hi, label):
    w = [r for r in records if lo <= r["t"] <= hi]
    print(f"\n=== corpus {label} (t={lo}~{hi}, {len(w)}프레임) ===")
    if not w:
        print("  (해당 구간 프레임 없음)")
        return

    # 1) baseline vs confidence-blend out_speed 차이(개입 강도 비교).
    #    개입 없음(out=None)인 프레임은 v_ego_kph(=개입 없음을 속도차 0으로
    #    표현)로 취급 -- "두 버전이 서로 다른 세기로 감속을 걸었는가"만 본다.
    diffs = []
    for r in w:
        if r["out_base"] is None and r["out_conf"] is None:
            continue
        ob = r["out_base"] if r["out_base"] is not None else r["v_ego_kph"]
        oc = r["out_conf"] if r["out_conf"] is not None else r["v_ego_kph"]
        diffs.append(oc - ob)
    if diffs:
        mean_diff = sum(diffs) / len(diffs)
        max_diff = max(diffs, key=abs)
        weaker = sum(1 for d in diffs if d > 0.5)
        print(f"  out_speed 차이(confidence-baseline, kph): "
              f"mean={mean_diff:+.2f} max_abs={max_diff:+.2f} (n={len(diffs)})")
        print(f"  confidence 버전이 baseline보다 0.5kph 이상 약하게 개입한 "
              f"프레임: {weaker}/{len(diffs)} ({weaker/len(diffs)*100:.1f}%)")
    else:
        print("  (양쪽 모두 개입 없음 -- 비교 대상 프레임 없음)")

    # 2) [267차 발견 항목] 지속 접근 중 순간 streak=1 리셋(flicker) 탐지:
    #    직전 프레임까지 streak>=2(=이미 어느 정도 신뢰가 쌓인 track)였는데
    #    이번 프레임에 confidence 트랙만 new/passed/lost로 streak=1 리셋되고,
    #    같은 프레임 baseline은 여전히 능동 개입 중(out_base is not None)인
    #    경우 -- baseline 기준으로는 감속이 계속 필요한 상황인데
    #    confidence=0으로 이 프레임만 개입이 순간 풀리는 사례.
    #    (§28 -- 이 지표는 "가능성 있는 후보"를 세는 것이며, 실제 체감
    #    가능한 flicker인지는 실차/영상 대조가 별도로 필요하다.)
    flicker_events = []
    prev_streak = None
    for r in w:
        if (r["mode_conf"] in ("new", "passed", "lost")
                and prev_streak is not None and prev_streak >= 2
                and r["out_base"] is not None):
            flicker_events.append(r["t"])
        prev_streak = r["streak"]
    preview = flicker_events[:5]
    suffix = "..." if len(flicker_events) > 5 else ""
    print(f"  [267차 flicker 후보] 직전 streak>=2 -> 이번 프레임 리셋 "
          f"(mode=new/passed/lost) 되면서 baseline은 여전히 개입 중인 "
          f"프레임: {len(flicker_events)}건"
          + (f" (t={preview}{suffix})" if flicker_events else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", nargs="?", default=None)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--tau", type=float, default=CONFIDENCE_TAU_DEFAULT)
    ap.add_argument("--window", type=float, nargs=2, action="append", default=None)
    ap.add_argument("--label", action="append", default=None)
    args = ap.parse_args()

    if args.self_test or not args.csv_path:
        self_test(args.tau)
        return

    rows = load_csv(args.csv_path)
    if not rows:
        print("no rows", file=sys.stderr)
        sys.exit(1)

    records = replay_corpus(rows, args.tau)
    print(f"=== 전체 {len(rows)}행 처리, 유효 프레임 {len(records)}건 "
          f"(tau={args.tau}) ===")

    if args.window:
        labels = args.label or [f"win{i}" for i in range(len(args.window))]
        for (lo, hi), label in zip(args.window, labels):
            summarize_corpus_window(records, lo, hi, label)
    else:
        for lo, hi, label in DEFAULT_WINDOWS:
            summarize_corpus_window(records, lo, hi, label)


if __name__ == "__main__":
    main()
