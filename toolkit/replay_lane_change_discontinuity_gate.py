#!/usr/bin/env python3
"""
75차 — 73차의 split_gate(handoff 트리거 전용 frac 무관 게이트)를,
차선변경(blinker 활성 + LANE_CHANGE_VLEAD_CORRECTION_HOLD_S hold) 중에
한정해 discontinuity 트리거(방안C/G)에도 적용하는 방향(b)을 정량 검증.

replay_boost_duration.py의 BoostReplay 로직을 그대로 재사용하되,
lane_change_gate=True 옵션을 추가해 step()에 leftBlinker/rightBlinker를
받는다. long_mpc.py 실제 패치(is_lane_change_discontinuity)와 동일 조건:
  discontinuity 트리거 + (blinker 활성 또는 hold 타이머>0) 이면
  handoff와 동일하게 danger_active만으로 게이트(frac 무관).
LANE_CHANGE_VLEAD_CORRECTION_HOLD_S 자체는 v_lead 보정용 타이머와
별개 인스턴스로 이 스크립트 안에서 재현한다(long_mpc.py와 동일 원칙).
"""
import sys
import os
import collections
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_routes import load_route  # noqa: E402
from replay_boost_duration import (  # noqa: E402
    LEAD_ACQ_TTC_DANGER, LEAD_ACQ_TTC_CAUTION, LEAD_ACQ_RAMP_TIME,
    LEAD_ACQ_MIN_V_EGO, LEAD_ACQ_CONFIRM_TIME, LEAD_ACQ_LOSS_GRACE_TIME,
    VISION_CLOSING_RATE_TAU, VISION_CLOSING_RATE_MIN_TIME,
    VISION_CLOSING_RATE_MAX_PLAUSIBLE, VISION_CLOSING_RATE_MEDIAN_WINDOW,
    VISION_CLOSING_RATE_GATE_CAUTION, VISION_CLOSING_RATE_GATE_DANGER,
    DREL_DISCONTINUITY_DROP_THRESH, DREL_DISCONTINUITY_WINDOW_N,
    RADAR_HANDOFF_VREL_JUMP_THRESH, A_CHANGE_COST, DISCONTINUITY_JERK_COST_BOOST,
)

LANE_CHANGE_VLEAD_CORRECTION_HOLD_S = 1.0  # long_mpc.py 실제 값


class LaneChangeGateReplay:
  """BoostReplay(discontinuity_jerk_boost_timer=1.0s hard, split_gate 없음)
  + lane_change 조건부 frac 무관 게이트를 추가한 버전."""

  def __init__(self, lane_change_gate):
    self.lane_change_gate = lane_change_gate
    self._timer = 0.0
    self._trigger_source = None
    self._lane_change_hold_timer = 0.0

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

  def step(self, dt, lead_status, dRel, vRel, a_lead, radar_locked, v_ego, cruise_enabled,
            blinker_active):
    dt = max(dt, 1e-3)
    self._timer = max(0.0, self._timer - dt)
    if blinker_active:
      self._lane_change_hold_timer = LANE_CHANGE_VLEAD_CORRECTION_HOLD_S
    else:
      self._lane_change_hold_timer = max(0.0, self._lane_change_hold_timer - dt)
    lane_change_active_now = blinker_active or self._lane_change_hold_timer > 0.0

    lead_one_status_now = bool(lead_status)

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
        self._timer = 1.0  # DISCONTINUITY_JERK_COST_BOOST_S
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
          self._timer = 4.0  # RADAR_HANDOFF_JERK_BOOST_S
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

    if self._prev_a_lead is not None:
      j_lead = (a_lead - self._prev_a_lead) / dt
    else:
      j_lead = 0.0
    self._prev_a_lead = a_lead
    if lead_one_status_now:
      base_cost = float(np.interp(abs(j_lead), [0.3, 2.0], [A_CHANGE_COST, 20.0]))
    else:
      base_cost = A_CHANGE_COST

    is_handoff = (self._trigger_source == 'handoff')
    is_lane_change_discontinuity = (
      self.lane_change_gate and
      self._trigger_source == 'discontinuity' and
      lane_change_active_now
    )
    boost_gate_ok = (self._timer > 0.0) and (not danger_active)
    if not is_handoff and not is_lane_change_discontinuity:
      boost_gate_ok = boost_gate_ok and (frac <= 0.0)

    a_change_cost = DISCONTINUITY_JERK_COST_BOOST if boost_gate_ok else base_cost

    return dict(triggered=triggered, a_change_cost=a_change_cost, danger_active=danger_active,
                frac=frac, timer_active=self._timer > 0.0, trigger_source=self._trigger_source,
                lane_change_active=lane_change_active_now)


def run(rows, t_lo, t_hi, lane_change_gate):
  sub = [r for r in rows if t_lo <= float(r['t']) <= t_hi]
  sub.sort(key=lambda r: float(r['t']))
  rep = LaneChangeGateReplay(lane_change_gate)
  ts, aEgos, results = [], [], []
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
    blinker = (r.get('leftBlinker') in ('True', '1', 'true') or
               r.get('rightBlinker') in ('True', '1', 'true'))
    ts.append(t)
    aEgos.append(aEgo)
    results.append(rep.step(dt, lead_status, dRel, vRel, a_lead, radar_locked, v_ego,
                             cruise_enabled, blinker))
  return ts, aEgos, results


def summarize(name, t_lo, t_hi, ts_base, aEgos, res_base, res_patched, risk_thresh=-1.5, max_gap_s=0.5):
  print(f"\n===== {name} (t={t_lo}~{t_hi}) =====")
  triggered_idxs = [i for i, r in enumerate(res_patched) if r['triggered']]
  if not triggered_idxs:
    print("  트리거 없음 -- 범위 재확인 필요")
    return
  # 위험구간: aEgo<=risk_thresh 구간(짧은 회복 blip은 종료로 안 침 --
  # replay_boost_duration.py summarize_event()와 동일 원칙, max_gap_s=0.5s)
  trig_idx = triggered_idxs[0]
  risk_start = risk_end = None
  above_since = None
  for i in range(trig_idx, len(ts_base)):
    if aEgos[i] <= risk_thresh:
      if risk_start is None:
        risk_start = i
      risk_end = i
      above_since = None
    else:
      if risk_start is not None:
        if above_since is None:
          above_since = ts_base[i]
        elif ts_base[i] - above_since >= max_gap_s:
          break
  if risk_start is None:
    print(f"  트리거(t={ts_base[trig_idx]:.3f}) 이후 aEgo<={risk_thresh} 구간 없음")
    return
  risk_dur = ts_base[risk_end] - ts_base[risk_start]
  print(f"  트리거 t={ts_base[trig_idx]:.3f} (source={res_patched[trig_idx]['trigger_source']}, "
        f"lane_change_active={res_patched[trig_idx]['lane_change_active']})")
  print(f"  위험구간 t={ts_base[risk_start]:.3f}~{ts_base[risk_end]:.3f} ({risk_dur:.2f}s)")

  for label, res in [("UNPATCHED(기존 frac 게이트)", res_base), ("PATCHED(차선변경 한정 완화)", res_patched)]:
    boosted = 0.0
    prev_t = None
    for i in range(risk_start, risk_end + 1):
      t = ts_base[i]
      dt = (t - prev_t) if prev_t is not None else 0.05
      prev_t = t
      if res[i]['a_change_cost'] >= 300.0:
        boosted += dt
    cov = 100.0 * boosted / risk_dur if risk_dur > 0 else 0.0
    print(f"  {label:<28} boost적용 {boosted:.2f}s / {risk_dur:.2f}s ({cov:.1f}%)")

  base_danger = sum(1 for r in res_base if r['danger_active'])
  patched_danger = sum(1 for r in res_patched if r['danger_active'])
  if base_danger != patched_danger:
    print(f"  [경고] danger_active 프레임 수 불일치: base={base_danger} patched={patched_danger}")
  else:
    print(f"  danger_active 프레임 수 회귀 없음(base=patched={base_danger})")


if __name__ == "__main__":
  devnotes_dir = "/home/claude/devnotes"
  rows1, meta1 = load_route(devnotes_dir, "ea5bcc0566")
  rows2, meta2 = load_route(devnotes_dir, "a5b1ce4e42")
  print(f"route1(ea5bcc0566): {meta1['n_rows']}행 / route2(a5b1ce4e42): {meta2['n_rows']}행")

  # 75차 대상 구간: route2 t=1469~1472 / t=1541~1545 (discontinuity+차선변경 사각지대)
  for t_lo, t_hi in [(1460.0, 1480.0), (1535.0, 1550.0)]:
    ts_b, aEgos_b, res_b = run(rows2, t_lo, t_hi, lane_change_gate=False)
    ts_p, aEgos_p, res_p = run(rows2, t_lo, t_hi, lane_change_gate=True)
    summarize(f"route2 discontinuity+lane_change t={t_lo}~{t_hi}", t_lo, t_hi, ts_b, aEgos_b, res_b, res_p)

  # 회귀 체크: route1 전체 구간에서 discontinuity+non-lane-change 트리거들의
  # boost_gate_ok 시퀀스가 UNPATCHED/PATCHED 동일한지(비차선변경 상황은
  # 100% 그대로 유지되어야 함).
  print("\n===== 회귀 체크: route1 전체, PATCHED vs UNPATCHED a_change_cost diff =====")
  ts_b1, aEgos_b1, res_b1 = run(rows1, 0.0, 1e9, lane_change_gate=False)
  ts_p1, aEgos_p1, res_p1 = run(rows1, 0.0, 1e9, lane_change_gate=True)
  diffs = [i for i in range(len(res_b1)) if abs(res_b1[i]['a_change_cost'] - res_p1[i]['a_change_cost']) > 1e-6]
  print(f"  route1 전체 {len(res_b1)}프레임 중 diff 프레임: {len(diffs)}건")
  for i in diffs[:20]:
    print(f"    t={ts_b1[i]:.3f} base={res_b1[i]['a_change_cost']:.1f} patched={res_p1[i]['a_change_cost']:.1f} "
          f"source={res_p1[i]['trigger_source']} lane_change_active={res_p1[i]['lane_change_active']}")

  print("\n===== 회귀 체크: route2 전체, PATCHED vs UNPATCHED a_change_cost diff =====")
  ts_b2, aEgos_b2, res_b2 = run(rows2, 0.0, 1e9, lane_change_gate=False)
  ts_p2, aEgos_p2, res_p2 = run(rows2, 0.0, 1e9, lane_change_gate=True)
  diffs2 = [i for i in range(len(res_b2)) if abs(res_b2[i]['a_change_cost'] - res_p2[i]['a_change_cost']) > 1e-6]
  print(f"  route2 전체 {len(res_b2)}프레임 중 diff 프레임: {len(diffs2)}건")
  n_show = 0
  for i in diffs2:
    if n_show >= 20:
      print(f"    ... (총 {len(diffs2)}건 중 20건만 표시)")
      break
    print(f"    t={ts_b2[i]:.3f} base={res_b2[i]['a_change_cost']:.1f} patched={res_p2[i]['a_change_cost']:.1f} "
          f"source={res_p2[i]['trigger_source']} lane_change_active={res_p2[i]['lane_change_active']}")
    n_show += 1
