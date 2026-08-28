#!/usr/bin/env python3
"""
112차 계속: LOW_SPEED_STRONG_DECEL threshold 강화(-1.8->-2.5) +
discontinuity_jerk_boost 신규 소스 'low_speed_strong_decel' 실측 replay
검증. sim_low_speed_decel.py(합성 시나리오)와 달리 extract_log.py로
뽑은 실제 CSV(vEgo/leadALeadK/leadVLead/leadDRel 등, 노이즈 포함)를
그대로 흘려서 검증한다.

목적:
  1. 구threshold(-1.8) 기준으로는 라우트1에서 저속게이트가 실제로
     발동했는지(FINDINGS.md 112차가 t=1938.97 근방으로 특정한 지점과
     일치하는지) 실측 데이터로 재확인.
  2. 신threshold(-2.5) 적용 시 라우트 전체에서 저속게이트가 단 한 번도
     발동하지 않는지(오탐 완전 해소) 확인.
  3. discontinuity_jerk_boost가 신threshold 기준으로는 아예 arm되지
     않는다는 뜻이므로, 이 라우트만으로는 jerk_boost 신규 소스 자체의
     동작(hold/release)은 검증 불가 -- 별도로 threshold를 낮춰(-1.8
     그대로 두고) 같은 실측 데이터에 jerk_boost 로직만 태워 arm/release
     궤적이 합성검증(G)과 같은 패턴을 보이는지 교차검증한다(실측 노이즈
     환경에서 플리커링/재트리거 이상 없는지가 핵심 -- 합성 시나리오는
     이상적 신호라 실측에서만 드러나는 문제가 있을 수 있음).

사용:
    python3 replay_low_speed_strong_decel.py /home/claude/work/route1.csv
"""
import sys
import csv


LOW_SPEED_STRONG_DECEL_V_EGO_GATE = 30.0 / 3.6
RADAR_HANDOFF_JERK_BOOST_S = 4.0
RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE = 100.0
DISCONTINUITY_JERK_COST_BOOST = 500.0
BASE_A_CHANGE_COST = 100.0  # 실측 j_lead 기반 base가 아니라 리포트용 임의 상수(sim과 동일 관례)
LEAD_ACQ_TTC_DANGER = 2.5


def _b(v):
    return v in ('True', '1', 'true')


# --- 정상경로(margin/ttc/rise-rate) 재현 -- 오버라이드의 "실제 한계효용"을
# 확인하기 위해 필요(아래 compare_weight_trajectory 참고) ---
MARGIN_ACCEL_GATE_FULL = 1.5
MARGIN_ACCEL_GATE_NONE = 1.0
LEAD_ACCEL_TTC_GATE_FULL = 12.0
LEAD_ACCEL_TTC_GATE_NONE = 6.0
LEAD_ACCEL_WEIGHT_RISE_RATE = 1.0  # 1/s
COMFORT_BRAKE = 2.5
STOP_DISTANCE = 6.0
T_FOLLOW_STANDARD = 1.45  # get_T_FOLLOW(standard), long_mpc.py 실제 값


def margin_accel_weight(dRel, desired_distance):
    if desired_distance <= 1.0:
        return 1.0
    ratio = dRel / desired_distance
    return float(max(0.0, min(1.0, (MARGIN_ACCEL_GATE_FULL - ratio) / (MARGIN_ACCEL_GATE_FULL - MARGIN_ACCEL_GATE_NONE))))


def ttc_accel_weight(dRel, v_ego, v_lead):
    closing = v_ego - v_lead
    if closing <= 0.1:
        return 0.0
    ttc = dRel / closing
    return float(max(0.0, min(1.0, (LEAD_ACCEL_TTC_GATE_FULL - ttc) / (LEAD_ACCEL_TTC_GATE_FULL - LEAD_ACCEL_TTC_GATE_NONE))))


def approx_desired_distance(v_ego, v_lead):
    """get_safe_obstacle_distance()-get_stopped_equivalence_factor()
    (long_mpc.py 61~70줄) 근사 재현 -- personality=standard 고정 가정
    (CSV에 personality 컬럼 없음, 대부분 세션이 standard로 주행)."""
    safe = (v_ego ** 2) / (2 * COMFORT_BRAKE) + T_FOLLOW_STANDARD * v_ego + STOP_DISTANCE
    stopped_eq = (v_lead ** 2) / (2 * COMFORT_BRAKE)
    return safe - stopped_eq


def compare_weight_trajectory(csv_path, t_start, t_end, new_thresh, old_thresh):
    """112차 계속: threshold 강화가 실제로 '얼마나' 다른지 정량화.
    오버라이드 자체를 끈 baseline(정상 ttc/margin/rise-rate 경로만)과
    구/신 threshold를 나란히 비교 -- 오버라이드가 baseline 대비 얼마나
    일찍/강하게 w=1.0을 강제하는지가 핵심(오탐이냐 아니냐의 이분법보다
    "얼마나 앞당겨지는가"가 실제 체감 급감속의 크기를 결정함)."""
    rows = load_rows(csv_path)
    window = [r for r in rows if t_start <= float(r['t']) <= t_end]

    def run(threshold):
        prev_w = 1.0
        out = []
        for r in window:
            v_ego = float(r['vEgo']); v_lead = float(r['leadVLead'])
            dRel = float(r['leadDRel']); a_lead = float(r['leadALeadK'])
            dd = approx_desired_distance(v_ego, v_lead)
            dist_w = margin_accel_weight(dRel, dd)
            ttc_w = ttc_accel_weight(dRel, v_ego, v_lead)
            w = min(dist_w, ttc_w)
            closing = v_ego - v_lead
            ttc_now = dRel / closing if closing > 0.1 else float('inf')
            override = (threshold is not None) and (v_ego <= LOW_SPEED_STRONG_DECEL_V_EGO_GATE) and (a_lead <= threshold)
            danger = (ttc_now <= LEAD_ACQ_TTC_DANGER) or override
            if danger:
                w = 1.0
            elif w > prev_w:
                w = min(w, prev_w + LEAD_ACCEL_WEIGHT_RISE_RATE * 0.05)
            prev_w = w
            out.append(dict(t=float(r['t']), w=w, weighted_a_lead=w * a_lead, override=override))
        return out

    base = run(None)     # 오버라이드 완전 비활성(정상 경로만) -- "이상적 비교군"
    old = run(old_thresh)
    new = run(new_thresh)

    print(f"--- weighted a_lead 비교 (t={t_start}~{t_end}) ---")
    print(f"{'t':>9} {'aLeadK':>7} {'w_base':>7} {'w_old':>7} {'w_new':>7} "
          f"{'wA_base':>8} {'wA_old':>8} {'wA_new':>8}")
    for i, r in enumerate(window):
        aL = float(r['leadALeadK'])
        print(f"{base[i]['t']:9.3f} {aL:7.2f} {base[i]['w']:7.3f} {old[i]['w']:7.3f} {new[i]['w']:7.3f} "
              f"{base[i]['weighted_a_lead']:8.3f} {old[i]['weighted_a_lead']:8.3f} {new[i]['weighted_a_lead']:8.3f}")

    # baseline이 w>=0.99(사실상 완전수렴)에 처음 도달하는 시각 -- "오버라이드 없이도
    # 결국 도달했을 시점" 기준점.
    base_converge_t = next((o['t'] for o in base if o['w'] >= 0.99), None)
    old_override_t = next((o['t'] for o in old if o['override']), None)
    new_override_t = next((o['t'] for o in new if o['override']), None)
    old_override_end_t = next((o['t'] for o in reversed(old) if o['override']), None)
    new_override_end_t = next((o['t'] for o in reversed(new) if o['override']), None)

    print()
    print("=== 해석 ===")
    print(f"  baseline(오버라이드 없음)이 자연 수렴(w>=0.99)하는 시각: {base_converge_t}")
    print(f"  구threshold 오버라이드 구간: {old_override_t} ~ {old_override_end_t}"
          f" ({(old_override_end_t - old_override_t) if old_override_t else 'N/A':.3f}s 조기/과잉 구간)" if old_override_t else "  구threshold: 미발동")
    print(f"  신threshold 오버라이드 구간: {new_override_t} ~ {new_override_end_t}"
          f" ({(new_override_end_t - new_override_t):.3f}s 조기/과잉 구간)" if new_override_t else "  신threshold: 미발동")
    if base_converge_t and old_override_t:
        print(f"  구threshold가 baseline 자연수렴보다 앞당기는 시간: {base_converge_t - old_override_t:.3f}s")
    if base_converge_t and new_override_t:
        print(f"  신threshold가 baseline 자연수렴보다 앞당기는 시간: {base_converge_t - new_override_t:.3f}s")
    return dict(base=base, old=old, new=new)


def load_rows(csv_path):
    with open(csv_path, newline='') as f:
        rows = list(csv.DictReader(f))
    clean = [r for r in rows if r.get('vEgo') not in ('', None)]
    clean.sort(key=lambda r: float(r['t']))
    return clean


class LowSpeedStrongDecelReplay:
    """long_mpc.py process_lead() 내 low_speed_strong_lead_decel 판정 +
    discontinuity_jerk_boost 'low_speed_strong_decel' 소스 arm/release를
    실측 row 스트림으로 재현. TTC danger override도 함께 반영해 실제
    lead0_danger_now과 동일한 조합으로 판정한다(합성 스크립트의 격리
    검증과 달리, 실측에서는 TTC danger와 겹치는 프레임이 있을 수 있어
    이를 구분해서 로그로 남긴다)."""

    def __init__(self, a_lead_thresh):
        self.a_lead_thresh = a_lead_thresh
        self.timer = 0.0
        self.trigger_source = None
        self.handoff_release_value = None
        self.prev_low_speed_strong_lead_decel = False
        self.lead0_danger_active = False

    def step(self, dt, v_ego, dRel, v_lead, a_lead, lead_status):
        self.timer = max(0.0, self.timer - dt)

        if not lead_status:
            # 리드 소실 -- process_lead()의 else 분기와 동일하게 안전측 리셋
            self.lead0_danger_active = False
            self.prev_low_speed_strong_lead_decel = False
            return self._apply_cost(low_speed_strong_lead_decel=False, ttc_danger=False)

        closing = v_ego - v_lead
        ttc_now = dRel / closing if closing > 0.1 else float('inf')
        ttc_danger = ttc_now <= LEAD_ACQ_TTC_DANGER

        low_speed_strong_lead_decel = (
            v_ego <= LOW_SPEED_STRONG_DECEL_V_EGO_GATE
            and a_lead <= self.a_lead_thresh
        )
        lead0_danger_now = ttc_danger or low_speed_strong_lead_decel
        self.lead0_danger_active = lead0_danger_now

        if (low_speed_strong_lead_decel and not self.prev_low_speed_strong_lead_decel
                and self.timer <= 0.0):
            self.timer = RADAR_HANDOFF_JERK_BOOST_S
            self.trigger_source = 'low_speed_strong_decel'
            self.handoff_release_value = None
        self.prev_low_speed_strong_lead_decel = low_speed_strong_lead_decel

        return self._apply_cost(low_speed_strong_lead_decel, ttc_danger, ttc_now=ttc_now)

    def _apply_cost(self, low_speed_strong_lead_decel, ttc_danger, ttc_now=float('inf')):
        is_handoff_source = self.trigger_source in ('handoff', 'discontinuity_lc', 'low_speed_strong_decel')
        boost_gate_ok = (self.timer > 0.0) and not self.lead0_danger_active

        if is_handoff_source:
            force_revert = self.lead0_danger_active
            if boost_gate_ok:
                a_change_cost = DISCONTINUITY_JERK_COST_BOOST
                self.handoff_release_value = DISCONTINUITY_JERK_COST_BOOST
            elif force_revert:
                a_change_cost = BASE_A_CHANGE_COST
                self.handoff_release_value = None
            elif self.handoff_release_value is not None:
                self.handoff_release_value = max(
                    BASE_A_CHANGE_COST, self.handoff_release_value - RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE * 0.05)
                a_change_cost = self.handoff_release_value
                if self.handoff_release_value <= BASE_A_CHANGE_COST + 1e-6:
                    self.handoff_release_value = None
            else:
                a_change_cost = BASE_A_CHANGE_COST
        else:
            a_change_cost = BASE_A_CHANGE_COST

        return dict(
            low_speed_strong_lead_decel=low_speed_strong_lead_decel,
            ttc_danger=ttc_danger,
            ttc_now=ttc_now,
            timer=self.timer,
            trigger_source=self.trigger_source,
            a_change_cost=a_change_cost,
            boost_active=(a_change_cost > BASE_A_CHANGE_COST + 1e-6),
        )


def _iter_frames(rows):
    prev_t = None
    for r in rows:
        t = float(r['t'])
        dt = (t - prev_t) if prev_t is not None else 0.05
        prev_t = t
        lead_status = _b(r['leadStatus'])
        dRel = float(r['leadDRel']) if r.get('leadDRel') not in ('', None) else 0.0
        v_lead = float(r['leadVLead']) if r.get('leadVLead') not in ('', None) else 0.0
        a_lead = float(r['leadALeadK']) if r.get('leadALeadK') not in ('', None) else 0.0
        v_ego = float(r['vEgo'])
        aEgo = float(r['aEgo']) if r.get('aEgo') not in ('', None) else None
        yield t, dt, v_ego, dRel, v_lead, a_lead, lead_status, aEgo


def run_threshold_scan(csv_path, thresh, label):
    rows = load_rows(csv_path)
    rep = LowSpeedStrongDecelReplay(a_lead_thresh=thresh)
    triggers = []
    for t, dt, v_ego, dRel, v_lead, a_lead, lead_status, aEgo in _iter_frames(rows):
        res = rep.step(dt, v_ego, dRel, v_lead, a_lead, lead_status)
        if res['low_speed_strong_lead_decel']:
            triggers.append(dict(t=t, v_ego_kmh=v_ego * 3.6, a_lead=a_lead, aEgo=aEgo,
                                  ttc_now=res['ttc_now'], ttc_danger=res['ttc_danger']))
    print(f"--- threshold={thresh} ({label}) ---")
    print(f"  저속게이트 발동 프레임 수: {len(triggers)}")
    if triggers:
        t0 = triggers[0]
        print(f"  최초 발동: t={t0['t']:.3f} v_ego={t0['v_ego_kmh']:.1f}km/h "
              f"a_lead={t0['a_lead']:.2f} aEgo(실측)={t0['aEgo']}  "
              f"ttc_danger_동시발동={t0['ttc_danger']}")
        # 연속 구간 클러스터링(gap>0.5s면 별도 에피소드)
        episodes = []
        cur = [triggers[0]]
        for tr in triggers[1:]:
            if tr['t'] - cur[-1]['t'] > 0.5:
                episodes.append(cur)
                cur = [tr]
            else:
                cur.append(tr)
        episodes.append(cur)
        print(f"  에피소드(클러스터, gap>0.5s 분리) 수: {len(episodes)}")
        for i, ep in enumerate(episodes):
            aEgos = [e['aEgo'] for e in ep if e['aEgo'] is not None]
            print(f"    ep{i+1}: t={ep[0]['t']:.3f}~{ep[-1]['t']:.3f} "
                  f"({len(ep)}프레임, 실측 min aEgo={min(aEgos) if aEgos else 'N/A'})")
    return triggers


def run_jerk_boost_flicker_check(csv_path, thresh):
    """실측 노이즈 환경에서 jerk_boost 'low_speed_strong_decel' 소스가
    비정상적으로 재트리거(짧은 간격 내 arm이 여러 번 발생, 플리커링)되는지
    확인. sim(합성)에서는 이상적 신호라 안 드러날 수 있는 문제."""
    rows = load_rows(csv_path)
    rep = LowSpeedStrongDecelReplay(a_lead_thresh=thresh)
    arm_events = []
    prev_source = None
    prev_timer = 0.0
    for t, dt, v_ego, dRel, v_lead, a_lead, lead_status, aEgo in _iter_frames(rows):
        res = rep.step(dt, v_ego, dRel, v_lead, a_lead, lead_status)
        # arm 감지: timer가 이전 프레임보다 커졌고(재시작) source가 우리 소스인 경우
        if res['trigger_source'] == 'low_speed_strong_decel' and res['timer'] > prev_timer + 1e-6:
            arm_events.append(t)
        prev_timer = res['timer']
    print(f"--- jerk_boost arm 이벤트(threshold={thresh}) ---")
    print(f"  총 arm 횟수: {len(arm_events)}")
    if len(arm_events) >= 2:
        gaps = [arm_events[i] - arm_events[i-1] for i in range(1, len(arm_events))]
        min_gap = min(gaps)
        flicker = min_gap < RADAR_HANDOFF_JERK_BOOST_S  # hold 시간(4.0s) 내 재arm이면 사실 정상(연속이벤트) -- 참고용 로그
        print(f"  arm 간 최소 간격: {min_gap:.2f}s (참고 -- {RADAR_HANDOFF_JERK_BOOST_S}s hold 안이면 동일 이벤트의 자연스런 연장일 수 있음)")
    for t in arm_events:
        print(f"    arm t={t:.3f}")
    return arm_events


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("사용법: python3 replay_low_speed_strong_decel.py <route.csv>")
        sys.exit(1)
    csv_path = sys.argv[1]

    print("=== 1) 구threshold(-1.8) 실측 재현 -- 기존 분석(t=1938.97) 재확인 ===")
    old_triggers = run_threshold_scan(csv_path, -1.8, "구(패치 전)")

    print()
    print("=== 2) 신threshold(-2.5) 실측 검증 -- 오탐 해소 확인 ===")
    new_triggers = run_threshold_scan(csv_path, -2.5, "신(패치 후)")

    print()
    print("=== 3) jerk_boost 신규소스 실측 플리커링 점검(구threshold로 arm 유도) ===")
    run_jerk_boost_flicker_check(csv_path, -1.8)

    print()
    print("=== 4) weighted a_lead 궤적 비교 (오버라이드의 실제 한계효용) ===")
    if old_triggers:
        t0 = old_triggers[0]['t']
        t1 = old_triggers[-1]['t']
        compare_weight_trajectory(csv_path, t0 - 0.5, t1 + 1.0, new_thresh=-2.5, old_thresh=-1.8)
    else:
        print("  구threshold 발동 없음 -- 비교 구간 특정 불가, 건너뜀")

    print()
    print("=== 요약 ===")
    print(f"  구threshold 발동 프레임: {len(old_triggers)}건")
    print(f"  신threshold 발동 프레임: {len(new_triggers)}건")
    ok = len(old_triggers) > 0 and len(new_triggers) == 0
    print(f"  판정: {'PASS (오탐 해소 확인)' if ok else 'FAIL (예상과 다름 -- 수동 확인 필요)'}")
    sys.exit(0 if ok else 1)
