#!/usr/bin/env python3
"""
73차 — 72차 계속2/3/4에서 확정된 "boost 윈도우(1.0s)가 실제 급감속
지속시간(4~5.5초)에 비해 구조적으로 부족" 가설을, data_routes.py로
불러온 실측 route1(ea5bcc0566)/route2(a5b1ce4e42)에 대해 boost
지속시간 후보(2.0/2.5/3.0s) + release-rate 완만화안을 정량 비교한다.

long_mpc.py의 discontinuity 트리거(dRel 급락/레이더 락온 vRel 불연속,
L884~938) + a_change_cost 부스트 적용부(L1120~1134) 로직을 최대한
그대로 복제. acados MPC 자체(floor_cap 이후 실제 j_ego/a_ego 산출)는
재현하지 않음 -- 대신 "실제 관측된 위험구간(aEgo<=-1.5 지속)" 동안
후보별 a_change_cost가 얼마나 오래 유의미하게 부스트 상태(>=300)를
유지하는지를 커버리지(coverage)로 비교한다. 이 방법은
replay_drel_discontinuity_real.py(63차)와 동일한 "로직 레벨 재생"
원칙을 따름 -- frac/danger 계산까지 그대로 복제해 boost 게이트 조건
(danger 미발동 + frac<=0)도 실측대로 반영.

한계: base_a_change_cost의 j_lead는 CSV에 없는 값이라
leadALeadK(a_lead)의 프레임간 미분으로 근사(NEEDS_VALIDATION).
"""
import sys
import os
import collections
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_routes import load_route  # noqa: E402

# --- long_mpc.py 실제 상수 ---
LEAD_ACQ_TTC_DANGER = 2.5
LEAD_ACQ_TTC_CAUTION = 6.0
LEAD_ACQ_RAMP_TIME = 5.0
LEAD_ACQ_MIN_V_EGO = 3.0
LEAD_ACQ_CONFIRM_TIME = 0.2
LEAD_ACQ_LOSS_GRACE_TIME = 0.5

VISION_CLOSING_RATE_TAU = 1.0
VISION_CLOSING_RATE_MIN_TIME = 0.5
VISION_CLOSING_RATE_MAX_PLAUSIBLE = 30.0
VISION_CLOSING_RATE_MEDIAN_WINDOW = 3
VISION_CLOSING_RATE_GATE_CAUTION = -2.2
VISION_CLOSING_RATE_GATE_DANGER = -5.0

DREL_DISCONTINUITY_DROP_THRESH = 15.0
DREL_DISCONTINUITY_WINDOW_N = 5
RADAR_HANDOFF_VREL_JUMP_THRESH = 3.0

A_CHANGE_COST = 200.0
DISCONTINUITY_JERK_COST_BOOST = 500.0

# 위험(danger) 판정 근사 -- process_lead()의 _lead0_danger_active를 완전히
# 재현하려면 저속강한감속 게이트까지 필요하나, boost 게이트 조건 자체는
# ttc_now<=DANGER 시 즉시 우회이므로 이 근사로 충분(과거 세션과 동일 원칙).


class BoostReplay:
  def __init__(self, boost_s, release_rate=None, split_gate=False):
    """
    boost_s: 트리거 시 부스트 유지시간(현재 원본=1.0s)
    release_rate: None이면 현재처럼 하드컷(윈도우 종료 즉시 base로 복귀).
                   숫자(cost/s)면 윈도우 종료 후 500에서 base까지
                   이 속도로 선형 감쇠(release-rate 완만화안).
    split_gate: True면 73차 계속 결정대로 트리거 소스별로 게이트를
                분리 -- 레이더 핸드오프(방안I) 트리거는 danger_active
                단독 게이트(frac 무관), dRel discontinuity(방안C/G)
                트리거는 기존 게이트(danger_active 무관 + frac<=0.0)
                그대로 유지. False면 원본과 동일(소스 무관 공통 게이트).
    """
    self.boost_s = boost_s
    self.release_rate = release_rate
    self.split_gate = split_gate
    self._timer = 0.0
    self._release_value = None  # release-rate 모드에서 현재 감쇠 중인 값
    self._trigger_source = None  # 'discontinuity' | 'handoff' | None

    self._lead_present_run_timer = 0.0
    self._lead_absent_timer = 0.0
    self._lead_acq_ramp_started = False
    self._lead_acq_timer = 0.0
    self._vision_dRel_prev = None
    self._vision_dRel_rate = 0.0
    self._vision_dRel_rate_window = collections.deque(maxlen=VISION_CLOSING_RATE_MEDIAN_WINDOW)
    self._dRel_raw_history = collections.deque(maxlen=DREL_DISCONTINUITY_WINDOW_N)
    self._prev_lead_radar = False
    self._prev_lead_vRel = None
    self._prev_a_lead = None

  def step(self, dt, lead_status, dRel, vRel, a_lead, radar_locked, v_ego, cruise_enabled):
    dt = max(dt, 1e-3)
    self._timer = max(0.0, self._timer - dt)
    lead_one_status_now = bool(lead_status)

    # --- ramp bookkeeping ---
    if lead_one_status_now:
      self._lead_absent_timer = 0.0
      self._lead_present_run_timer += dt
      if not self._lead_acq_ramp_started:
        if self._lead_present_run_timer >= LEAD_ACQ_CONFIRM_TIME:
          self._lead_acq_ramp_started = True
          self._lead_acq_timer = 0.0
      else:
        self._lead_acq_timer += dt
    else:
      self._lead_absent_timer += dt
      if self._lead_absent_timer > LEAD_ACQ_LOSS_GRACE_TIME:
        self._lead_present_run_timer = 0.0
        self._lead_acq_ramp_started = False
        self._lead_acq_timer = 0.0
        self._vision_dRel_prev = None
        self._vision_dRel_rate = 0.0
        self._vision_dRel_rate_window.clear()
        self._dRel_raw_history.clear()

    triggered = False
    if lead_one_status_now and not radar_locked:
      dRel_now = float(dRel)
      self._dRel_raw_history.append(dRel_now)
      if (len(self._dRel_raw_history) == self._dRel_raw_history.maxlen and
          (self._dRel_raw_history[-1] - self._dRel_raw_history[0]) < -DREL_DISCONTINUITY_DROP_THRESH):
        self._lead_acq_timer = 0.0
        self._timer = self.boost_s
        self._release_value = None
        self._trigger_source = 'discontinuity'
        triggered = True

      if self._vision_dRel_prev is not None:
        raw_rate = (dRel_now - self._vision_dRel_prev) / dt
        raw_rate_clamped = max(raw_rate, -VISION_CLOSING_RATE_MAX_PLAUSIBLE)
        self._vision_dRel_rate_window.append(raw_rate_clamped)
        rate_for_filter = float(np.median(self._vision_dRel_rate_window))
        alpha = float(np.clip(dt / VISION_CLOSING_RATE_TAU, 0.0, 1.0))
        self._vision_dRel_rate = self._vision_dRel_rate * (1. - alpha) + rate_for_filter * alpha
      self._vision_dRel_prev = dRel_now
      self._prev_lead_radar = False
    elif lead_one_status_now and radar_locked:
      if (not self._prev_lead_radar) and self._prev_lead_vRel is not None:
        vRel_now = float(vRel)
        if (vRel_now - self._prev_lead_vRel) < -RADAR_HANDOFF_VREL_JUMP_THRESH:
          self._timer = self.boost_s
          self._release_value = None
          self._trigger_source = 'handoff'
          triggered = True
      self._vision_dRel_prev = None
      self._vision_dRel_rate = 0.0
      self._vision_dRel_rate_window.clear()
      self._dRel_raw_history.clear()
      self._prev_lead_radar = True
    elif self._lead_absent_timer > LEAD_ACQ_LOSS_GRACE_TIME:
      self._vision_dRel_prev = None
      self._vision_dRel_rate = 0.0
      self._vision_dRel_rate_window.clear()
      self._dRel_raw_history.clear()
      self._prev_lead_radar = False

    self._prev_lead_vRel = float(vRel) if lead_one_status_now else None

    # --- frac(TTC danger 근사) ---
    frac_time = frac_ttc = frac_rate = 0.0
    ttc_now = 999.0
    if cruise_enabled and lead_one_status_now and v_ego >= LEAD_ACQ_MIN_V_EGO and self._lead_acq_ramp_started:
      if self._lead_acq_timer <= LEAD_ACQ_RAMP_TIME:
        frac_time = float(np.clip(self._lead_acq_timer / LEAD_ACQ_RAMP_TIME, 0.0, 1.0))
      lead_v_rel = vRel
      if lead_v_rel < -0.1:
        ttc_now = dRel / max(-lead_v_rel, 0.1)
      frac_ttc = float(np.clip((LEAD_ACQ_TTC_CAUTION - ttc_now) / (LEAD_ACQ_TTC_CAUTION - LEAD_ACQ_TTC_DANGER), 0.0, 1.0))
      if (not radar_locked) and self._lead_acq_timer >= VISION_CLOSING_RATE_MIN_TIME:
        if self._vision_dRel_rate < -0.1:
          ttc_dRel = dRel / max(-self._vision_dRel_rate, 0.1)
          ttc_now = min(ttc_now, ttc_dRel)
        frac_rate = float(np.clip(
          (VISION_CLOSING_RATE_GATE_CAUTION - self._vision_dRel_rate) /
          (VISION_CLOSING_RATE_GATE_CAUTION - VISION_CLOSING_RATE_GATE_DANGER), 0.0, 1.0))
    frac = max(frac_time, frac_ttc, frac_rate)
    danger_active = ttc_now <= LEAD_ACQ_TTC_DANGER

    # --- j_lead 근사(leadALeadK 프레임간 미분) + base_a_change_cost ---
    if self._prev_a_lead is not None:
      j_lead = (a_lead - self._prev_a_lead) / dt
    else:
      j_lead = 0.0
    self._prev_a_lead = a_lead
    if lead_one_status_now:
      base_cost = float(np.interp(abs(j_lead), [0.3, 2.0], [A_CHANGE_COST, 20.0]))
    else:
      base_cost = A_CHANGE_COST

    boost_gate_ok = (self._timer > 0.0) and (not danger_active) and (frac <= 0.0)
    if self.split_gate and self._timer > 0.0 and self._trigger_source == 'handoff':
      # 73차 계속: 방안I(레이더 핸드오프) 트리거는 danger_active 단독
      # 게이트 -- frac(찰나성 노이즈용 floor)는 이 트리거 소스에는
      # 애초에 설계 의도상 무관하다고 판단(FINDINGS.md 73차 참고).
      boost_gate_ok = (self._timer > 0.0) and (not danger_active)

    if self.release_rate is None:
      a_change_cost = DISCONTINUITY_JERK_COST_BOOST if boost_gate_ok else base_cost
    else:
      # release-rate 완만화안: boost 윈도우 종료 순간 base로 즉시 떨어지는
      # 대신, release_rate(cost/s)로 500 -> base까지 선형 감쇠.
      if boost_gate_ok:
        a_change_cost = DISCONTINUITY_JERK_COST_BOOST
        self._release_value = DISCONTINUITY_JERK_COST_BOOST
      elif danger_active or frac > 0.0:
        # 위험 감지 시엔 완만화안도 즉시 base로 복귀(원본 설계 원칙 유지).
        a_change_cost = base_cost
        self._release_value = None
      elif self._release_value is not None:
        self._release_value = max(base_cost, self._release_value - release_rate * dt)
        a_change_cost = self._release_value
        if self._release_value <= base_cost + 1e-6:
          self._release_value = None
      else:
        a_change_cost = base_cost

    return dict(triggered=triggered, a_change_cost=a_change_cost, danger_active=danger_active, frac=frac,
                timer=self._timer, timer_active=self._timer > 0.0)


def run_candidates(rows, t_lo, t_hi, candidates):
  """candidates: list of (label, boost_s, release_rate, split_gate) """
  sub = [r for r in rows if t_lo <= float(r['t']) <= t_hi]
  sub.sort(key=lambda r: float(r['t']))

  replayers = {label: BoostReplay(boost_s, release_rate, split_gate)
               for label, boost_s, release_rate, split_gate in candidates}
  series = {label: [] for label, *_ in candidates}
  ts, aEgos = [], []
  prev_t = None
  for r in sub:
    t = float(r['t'])
    dt = (t - prev_t) if prev_t is not None else 0.05
    prev_t = t
    lead_status = r['leadStatus'] in ('True', '1', 'true')
    dRel = float(r['leadDRel']) if r['leadDRel'] not in ('', None) else 0.0
    vRel = float(r['leadVRel']) if r['leadVRel'] not in ('', None) else 0.0
    a_lead = float(r['leadALeadK']) if r.get('leadALeadK') not in ('', None) else 0.0
    radar_locked = r['leadRadar'] in ('True', '1', 'true')
    v_ego = float(r['vEgo'])
    cruise_enabled = r['cruiseEnabled'] in ('True', '1', 'true')
    aEgo = float(r['aEgo'])

    ts.append(t)
    aEgos.append(aEgo)
    for label, boost_s, release_rate, split_gate in candidates:
      res = replayers[label].step(dt, lead_status, dRel, vRel, a_lead, radar_locked, v_ego, cruise_enabled)
      series[label].append(res)
  return ts, aEgos, series


def summarize_event(name, ts, aEgos, series, candidates, risk_thresh=-1.5, max_gap_s=0.5):
  print(f"\n===== {name} =====")
  # 위험구간: 트리거 이후 첫 aEgo<=risk_thresh 시작부터, 이후 aEgo가
  # risk_thresh를 초과한 상태가 max_gap_s 이상 연속되기 전까지의 마지막
  # 시점까지(짧은 회복 blip은 "위험 종료"로 치지 않음 -- WIP.md 72차
  # 계속3의 "5.55초 지속" 판정과 동일 원칙).
  trig_idx = None
  for label, boost_s, release_rate, split_gate in candidates:
    for i, res in enumerate(series[label]):
      if res['triggered']:
        trig_idx = i if trig_idx is None else min(trig_idx, i)
  if trig_idx is None:
    print("트리거 프레임을 못 찾음 -- t_lo/t_hi 범위 재확인 필요")
    return

  risk_start = None
  risk_end = None
  above_since = None  # risk_thresh 초과 상태가 시작된 시각(회복 후보)
  for i in range(trig_idx, len(ts)):
    if aEgos[i] <= risk_thresh:
      if risk_start is None:
        risk_start = i
      risk_end = i
      above_since = None
    else:
      if risk_start is not None:
        if above_since is None:
          above_since = ts[i]
        elif ts[i] - above_since >= max_gap_s:
          break
  if risk_start is None:
    print(f"트리거(t={ts[trig_idx]:.3f}) 이후 aEgo<={risk_thresh} 구간 없음")
    return

  risk_t0, risk_t1 = ts[risk_start], ts[risk_end]
  risk_dur = risk_t1 - risk_t0
  print(f"트리거 t={ts[trig_idx]:.3f} / 관측 위험구간(aEgo<={risk_thresh}) "
        f"t={risk_t0:.3f}~{risk_t1:.3f} ({risk_dur:.2f}s)")

  print(f"{'후보':<26}{'boost_s':>8}{'release':>10}{'timer활성(s)':>14}{'실부스트(s)':>12}{'게이트차단(s)':>14}{'커버율':>8}")
  for label, boost_s, release_rate, split_gate in candidates:
    res_list = series[label]
    timer_on = 0.0
    boosted = 0.0
    prev_t = None
    for i in range(risk_start, risk_end + 1):
      t = ts[i]
      dt = (t - prev_t) if prev_t is not None else 0.05
      prev_t = t
      if res_list[i]['timer_active']:
        timer_on += dt
      if res_list[i]['a_change_cost'] >= 300.0:
        boosted += dt
    gate_blocked = max(0.0, timer_on - boosted)
    coverage_pct = 100.0 * boosted / risk_dur if risk_dur > 0 else 0.0
    rel_str = f"{release_rate:.0f}/s" if release_rate else "-"
    print(f"{label:<26}{boost_s:>8.2f}{rel_str:>10}{timer_on:>14.2f}{boosted:>12.2f}{gate_blocked:>14.2f}{coverage_pct:>7.1f}%")
  # danger override 회귀 체크: split_gate 후보들의 danger_active 프레임 수가
  # split_gate=False(원본과 동일 로직)와 다르면 즉시 표시 -- danger 계산은
  # boost 게이트와 독립이라 원칙상 항상 동일해야 함(회귀 없음 확인용).
  base_label = candidates[0][0]
  base_danger = sum(1 for r in series[base_label] if r['danger_active'])
  for label, boost_s, release_rate, split_gate in candidates:
    d = sum(1 for r in series[label] if r['danger_active'])
    if d != base_danger:
      print(f"  [경고] {label}: danger_active 프레임 수({d})가 baseline({base_danger})과 다름!")
  print("(\"게이트차단\": boost 타이머는 활성(timer>0)인데 danger_active 또는 frac>0.0\n"
        " 조건에 걸려 실제로는 base_a_change_cost로 강등된 시간.)")


if __name__ == "__main__":
  devnotes_dir = "/home/claude/devnotes"
  rows1, meta1 = load_route(devnotes_dir, "ea5bcc0566")
  rows2, meta2 = load_route(devnotes_dir, "a5b1ce4e42")
  print(f"route1(ea5bcc0566): {meta1['n_rows']}행 / route2(a5b1ce4e42): {meta2['n_rows']}행")

  candidates = [
    ("baseline(1.0s hard)", 1.0, None, False),
    ("2.0s hard", 2.0, None, False),
    ("3.0s hard", 3.0, None, False),
    ("1.0s+split_gate(안I전용)", 1.0, None, True),
    ("2.0s+split_gate(안I전용)", 2.0, None, True),
    ("3.0s+split_gate(안I전용)", 3.0, None, True),
  ]

  # route1 seg10, 72차 계속2 기준 레이더 락온 엣지 t=690.0027
  ts1, ae1, s1 = run_candidates(rows1, 685.0, 705.0, candidates)
  summarize_event("route1 seg10 (레이더 락온 vRel 불연속, t~690.0)", ts1, ae1, s1, candidates)

  # route2 seg1(--1), 72차 계속3 기준 t=1378.85 레이더 락온
  ts2, ae2, s2 = run_candidates(rows2, 1375.0, 1385.0, candidates)
  summarize_event("route2 seg1 (레이더 락온 vRel 불연속, t~1378.85)", ts2, ae2, s2, candidates)
