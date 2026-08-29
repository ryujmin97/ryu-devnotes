#!/usr/bin/env python3
"""
114차: margin_accel_weight(dist_w)까지 포함한 완전 재현 + rise-rate saturation 재검증.

배경: 113차가 만들었던 replay_rise_rate_saturation.py는 ttc_accel_weight만
재현하고 margin_accel_weight(dist_w)는 desired_distance 계산에 필요한 carrot
상태(t_follow/comfort_brake/stop_distance)가 route CSV에 없어 근사하지
못했다(dist_w 자체를 아예 계산 안 하고 ttc_w 단독으로 saturation을 봄 --
과대평가 가능성). **그 스크립트 파일 자체가 컨테이너 리셋으로 유실되어
(FINDINGS.md/WIP.md 서술만 남고 toolkit/README.md·CHANGELOG.md에도 등록되지
않은 채 사라짐, 114차 세션 시작 시 확인) 이 스크립트가 그 대체 + 확장판이다.**

이번 스크립트는 long_mpc.py의 실제 desired_distance 체인
(get_safe_obstacle_distance/desired_follow_distance/carrot.get_T_FOLLOW)을
selfdrive/carrot/carrot_functions.py의 **기본 Params 값**을 그대로 대입해
재현한다:

  - personality = standard (가정, CSV에 기록 없음)
  - EnableSpeedTF = 0 (기본값, common/params_keys.h) -> 속도 스케일 스킵
  - DynamicTFollow = 0 (기본값) -> dynamic_t_follow()의 jLead 기반 보정 스킵
    (jLead 자체가 CSV에 없어 어차피 근사해야 했을 항 -- 기본값이 꺼져있어
    다행히 완전히 스킵 가능, 근사 오차 소스 하나가 사라짐)
  - MyDrivingMode = 3(Normal) (기본값) -> mySafeFactor = 1.0
  - TFollowGap1..4 = 1.10/1.20/1.40/1.60 (기본값) -> standard는 tf_base=1.20
  - TFollowDecelBoost = 0.10 (기본값) -> 강한 감속 중 t_follow에 최대 +0.025s
  - StopDistanceCarrot = 5.5m (기본값, 550/100)
  - comfort_brake = 2.4 (하드코드 기본값, self.comfortBrake)

**한계(사용자 확인 필요)**:
  1. 위 값들은 전부 "Params를 건드리지 않은 기본값" 가정 -- 사용자가 실제로
     TFollowGap 등을 커스텀했다면 desired_distance가 달라진다.
  2. comfort_brake는 특정 상황(carrot_functions.py L607 부근, 조건 미확인)에서
     *0.9로 조정되는 분기가 있으나 이번 재현에서는 반영 안 함(일상 추종
     상황에서는 해당 분기 진입 가능성 낮다고 판단, 미검증).
  3. stop_distance는 정지모델(actual_stop_distance, 교차로 정지선 등) 반영
     안 함 -- 순수 추종(car-following) 구간 한정 근사.
  4. t_follow의 decel-hold 상태(_tf_applied)는 매 세그먼트 시작 시 tf_target과
     동일하게 리셋(직전 세그먼트 상태 이어받지 않음) -- 세그먼트 초입 수 프레임만
     영향, 분석 구간(이벤트 발생 시점)은 세그먼트 중간이라 무관.
  5. dist_w 계산에 쓰이는 self.desired_distance는 실제로는 "1사이클(0.05s) 전"
     값이지만, 이 재현은 동일 프레임 값을 씀(long_mpc.py 주석상 staleness
     negligible이라 명시돼 있어 동일하게 무시).

margin_accel_weight/ttc_accel_weight/LOW_SPEED_STRONG_DECEL/danger override/
rise-rate 클램프 로직 자체는 long_mpc.py 리터럴 그대로 복사(코드-스크립트
drift 방지).

입력: extract_log.py CSV (leadDRel/leadVRel/leadVLead/leadALeadK/leadStatus/
leadRadar/vEgo/aEgo/t 컬럼 필요).

사용:
    python3 replay_margin_accel_weight_full.py <route.csv> [t_lo t_hi]
    # 또는:
    from replay_margin_accel_weight_full import run_window, scan_saturation_episodes
"""
import csv
import sys

# ---- long_mpc.py 상수 그대로 복사 ----
COMFORT_BRAKE = 2.4
STOP_DISTANCE = 5.5  # StopDistanceCarrot 기본값(550/100), long_mpc.py 자체 기본(6.0)이 아니라
                      # carrot_functions.py Params 기본값을 우선 사용
T_FOLLOW_STANDARD_BASE = 1.20  # TFollowGap2 기본값
T_FOLLOW_DECEL_BOOST = 0.10    # TFollowDecelBoost 기본값
T_FOLLOW_CLIP_MIN = 1.10       # min(TFollowGap1..4) 기본값
T_FOLLOW_CLIP_MAX = 1.60       # max(TFollowGap1..4) 기본값
DECEL_HOLD_A = -0.2

MARGIN_ACCEL_GATE_FULL = 1.5
MARGIN_ACCEL_GATE_NONE = 1.0

LEAD_ACCEL_TTC_GATE_FULL = 12.0
LEAD_ACCEL_TTC_GATE_NONE = 6.0

LEAD_ACCEL_WEIGHT_RISE_RATE = 1.0  # 1/s

LOW_SPEED_STRONG_DECEL_V_EGO_GATE = 30.0 / 3.6
LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH = -2.5

LEAD_ACQ_TTC_DANGER = 2.5  # danger override 임계값(long_mpc.py 기존 상수)

LAUNCH_BYPASS_STOP_V_EGO = 0.3
LAUNCH_BYPASS_EXIT_V_EGO = 5.0

DT = 0.05  # DT_MDL


def get_safe_obstacle_distance(v_ego, t_follow, comfort_brake, stop_distance):
    return (v_ego ** 2) / (2 * comfort_brake) + t_follow * v_ego + stop_distance


def get_stopped_equivalence_factor(v_lead):
    return (v_lead ** 2) / (2 * COMFORT_BRAKE)


def desired_follow_distance(v_ego, v_lead, comfort_brake, stop_distance, t_follow):
    return get_safe_obstacle_distance(v_ego, t_follow, comfort_brake, stop_distance) - get_stopped_equivalence_factor(v_lead)


def margin_accel_weight(dRel, desired_distance):
    if desired_distance <= 1.0:
        return 1.0
    ratio = dRel / desired_distance
    w = (MARGIN_ACCEL_GATE_FULL - ratio) / (MARGIN_ACCEL_GATE_FULL - MARGIN_ACCEL_GATE_NONE)
    return max(0.0, min(1.0, w))


def ttc_accel_weight(dRel, v_ego, v_lead):
    closing = v_ego - v_lead
    if closing <= 0.1:
        return 0.0
    ttc = dRel / closing
    w = (LEAD_ACCEL_TTC_GATE_FULL - ttc) / (LEAD_ACCEL_TTC_GATE_FULL - LEAD_ACCEL_TTC_GATE_NONE)
    return max(0.0, min(1.0, w))


class TFollowState:
    """carrot._apply_decel_hold_and_boost_t_follow()의 세션(세그먼트) 단위 상태."""

    def __init__(self):
        self.tf_applied = None

    def step(self, a_ego):
        tf_target = T_FOLLOW_STANDARD_BASE
        if self.tf_applied is None:
            self.tf_applied = tf_target
        if a_ego <= DECEL_HOLD_A and tf_target < self.tf_applied:
            tf_held = self.tf_applied
        else:
            tf_held = tf_target
        # decel_boost: interp(a_ego, [-2.5,-1.0,-0.2,0.0], [0.25,0.12,0.02,0.0]) * boost
        xs = [-2.5, -1.0, -0.2, 0.0]
        ys = [0.25, 0.12, 0.02, 0.0]
        if a_ego <= xs[0]:
            frac = ys[0]
        elif a_ego >= xs[-1]:
            frac = ys[-1]
        else:
            frac = 0.0
            for i in range(len(xs) - 1):
                if xs[i] <= a_ego <= xs[i + 1]:
                    t = (a_ego - xs[i]) / (xs[i + 1] - xs[i])
                    frac = ys[i] + (ys[i + 1] - ys[i]) * t
                    break
        decel_boost = frac
        tf_final = tf_held + decel_boost * T_FOLLOW_DECEL_BOOST
        tf_final = max(T_FOLLOW_CLIP_MIN, min(T_FOLLOW_CLIP_MAX, tf_final))
        # mySafeFactor=1.0 가정이라 곱해도 변화 없음
        self.tf_applied = tf_final
        return tf_final


def load_rows(csv_path):
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def run_window(rows, t_lo, t_hi, launch_bypass=True):
    """
    지정 시간범위(seg 경계 무시하고 t 컬럼 절대시간 기준)의 프레임을 순서대로
    재생해 dist_w/ttc_w/w_target/w_applied/danger 여부를 프레임별 리스트로 리턴.
    """
    tf_state = TFollowState()
    out = []
    w_prev = 1.0
    launch_active = False
    prev_t = None
    for r in rows:
        t = float(r["t"])
        if t < t_lo or t > t_hi:
            continue
        if r.get("leadStatus", "").strip() not in ("True", "1", "true"):
            continue
        v_ego = float(r["vEgo"])
        a_ego = float(r["aEgo"])
        dRel = float(r["leadDRel"])
        vRel = float(r["leadVRel"])
        v_lead = float(r["leadVLead"])
        a_lead = float(r["leadALeadK"]) if r.get("leadALeadK", "") not in ("", None) else 0.0

        dt = DT if prev_t is None else max(0.001, t - prev_t)
        prev_t = t

        if v_ego < LAUNCH_BYPASS_STOP_V_EGO:
            launch_active = True
        elif v_ego >= LAUNCH_BYPASS_EXIT_V_EGO:
            launch_active = False

        t_follow = tf_state.step(a_ego)
        desired_distance = desired_follow_distance(v_ego, v_lead, COMFORT_BRAKE, STOP_DISTANCE, t_follow)
        dist_w = margin_accel_weight(dRel, desired_distance)

        if launch_active and launch_bypass:
            ttc_w = 1.0
        else:
            ttc_w = ttc_accel_weight(dRel, v_ego, v_lead)

        w_target = min(dist_w, ttc_w)

        closing = v_ego - v_lead
        ttc_now = dRel / closing if closing > 0.1 else float("inf")
        low_speed_strong = (v_ego <= LOW_SPEED_STRONG_DECEL_V_EGO_GATE and a_lead <= LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH)
        danger_now = (ttc_now <= LEAD_ACQ_TTC_DANGER) or low_speed_strong

        if danger_now:
            w_applied = 1.0
        elif launch_active:
            w_applied = w_target
        elif w_target > w_prev:
            w_applied = min(w_target, w_prev + LEAD_ACCEL_WEIGHT_RISE_RATE * dt)
        else:
            w_applied = w_target
        w_prev = w_applied

        out.append({
            "t": t, "vEgo": v_ego, "aEgo": a_ego, "dRel": dRel, "vLead": v_lead,
            "aLeadK": a_lead, "t_follow": t_follow, "desired_distance": desired_distance,
            "dist_w": dist_w, "ttc_w": ttc_w, "w_target": w_target, "w_applied": w_applied,
            "danger_now": danger_now, "gap": max(0.0, w_target - w_applied),
        })
    return out


def longest_saturation_run(frames):
    """gap>0(w_applied이 w_target을 못 따라잡는 상태)이 연속된 최장 시간(s)."""
    best = 0.0
    cur = 0.0
    prev_t = None
    for f in frames:
        if prev_t is not None:
            dt = f["t"] - prev_t
        else:
            dt = DT
        if f["gap"] > 1e-6:
            cur += dt
            best = max(best, cur)
        else:
            cur = 0.0
        prev_t = f["t"]
    return best


def total_saturation_time(frames):
    total = 0.0
    prev_t = None
    for f in frames:
        dt = DT if prev_t is None else f["t"] - prev_t
        if f["gap"] > 1e-6:
            total += dt
        prev_t = f["t"]
    return total


def scan_route_saturation_episodes(rows, thresholds):
    """
    라우트 전체(윈도우 제한 없이)를 스캔해, 각 threshold(연속 saturation 초)마다
    그 threshold를 넘는 "에피소드"가 몇 번 발생하는지 센다 (오탐률 스윕용).
    라우트 전체를 한 번에 순차 재생(세그먼트 경계에서 tf_state/w_prev는
    이어짐 -- extract_log.py가 세그먼트 경계 상태를 carryover하므로 CSV 자체가
    연속적이라는 전제).
    """
    tf_state = TFollowState()
    w_prev = 1.0
    launch_active = False
    prev_t = None
    cur_run = 0.0
    episodes = []  # (start_t, duration)
    run_start_t = None
    for r in rows:
        if r.get("leadStatus", "").strip() not in ("True", "1", "true"):
            # 리드 없으면 rise-rate 상태 리셋(long_mpc.py와 동일)
            w_prev = 1.0
            if cur_run > 0:
                episodes.append((run_start_t, cur_run))
            cur_run = 0.0
            prev_t = None
            continue
        t = float(r["t"])
        v_ego = float(r["vEgo"])
        a_ego = float(r["aEgo"])
        dRel = float(r["leadDRel"])
        v_lead = float(r["leadVLead"])
        a_lead = float(r["leadALeadK"]) if r.get("leadALeadK", "") not in ("", None) else 0.0

        dt = DT if prev_t is None else max(0.001, t - prev_t)
        if dt > 1.0:  # 세그먼트 갭 등 비정상 점프는 새 구간으로 취급
            if cur_run > 0:
                episodes.append((run_start_t, cur_run))
            cur_run = 0.0
            w_prev = 1.0
        prev_t = t

        if v_ego < LAUNCH_BYPASS_STOP_V_EGO:
            launch_active = True
        elif v_ego >= LAUNCH_BYPASS_EXIT_V_EGO:
            launch_active = False

        t_follow = tf_state.step(a_ego)
        desired_distance = desired_follow_distance(v_ego, v_lead, COMFORT_BRAKE, STOP_DISTANCE, t_follow)
        dist_w = margin_accel_weight(dRel, desired_distance)
        ttc_w = 1.0 if launch_active else ttc_accel_weight(dRel, v_ego, v_lead)
        w_target = min(dist_w, ttc_w)

        closing = v_ego - v_lead
        ttc_now = dRel / closing if closing > 0.1 else float("inf")
        low_speed_strong = (v_ego <= LOW_SPEED_STRONG_DECEL_V_EGO_GATE and a_lead <= LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH)
        danger_now = (ttc_now <= LEAD_ACQ_TTC_DANGER) or low_speed_strong

        if danger_now:
            w_applied = 1.0
        elif launch_active:
            w_applied = w_target
        elif w_target > w_prev:
            w_applied = min(w_target, w_prev + LEAD_ACCEL_WEIGHT_RISE_RATE * dt)
        else:
            w_applied = w_target
        w_prev = w_applied

        gap = max(0.0, w_target - w_applied)
        if gap > 1e-6:
            if cur_run == 0.0:
                run_start_t = t
            cur_run += dt
        else:
            if cur_run > 0:
                episodes.append((run_start_t, cur_run))
            cur_run = 0.0
    if cur_run > 0:
        episodes.append((run_start_t, cur_run))

    result = {}
    for th in thresholds:
        count = sum(1 for (_, dur) in episodes if dur >= th)
        max_dur = max((dur for (_, dur) in episodes), default=0.0)
        result[th] = {"count": count, "n_episodes_total": len(episodes), "max_duration": max_dur}
    return result, episodes


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    rows = load_rows(path)
    if len(sys.argv) >= 4:
        t_lo, t_hi = float(sys.argv[2]), float(sys.argv[3])
        frames = run_window(rows, t_lo, t_hi)
        print(f"frames={len(frames)} longest_saturation={longest_saturation_run(frames):.3f}s "
              f"total_saturation={total_saturation_time(frames):.3f}s")
    else:
        thresholds = [0.3, 0.35, 0.4, 0.45, 0.5]
        res, episodes = scan_route_saturation_episodes(rows, thresholds)
        for th, d in res.items():
            print(f"th={th:.2f}s -> episodes>=th: {d['count']} / total_episodes: {d['n_episodes_total']} (max={d['max_duration']:.3f}s)")
