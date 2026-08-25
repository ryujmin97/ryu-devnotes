#!/usr/bin/env python3
"""
75차 — 73차의 split_gate(handoff 트리거 전용 frac 무관 게이트)를,
차선변경(blinker 활성 + LANE_CHANGE_VLEAD_CORRECTION_HOLD_S hold) 중에
한정해 discontinuity 트리거(방안C/G)에도 적용하는 방향(b)을 정량 검증.

76차(갱신) — 75차 검증 중 신규 발견된 한계(hard-hold 1.0s가 여전히 짧아
실제 aEgo 최저점을 놓침, WIP.md 75차 계속2 참고)에 대응해
`duration_mode` 옵션 추가:
  - 'gate_only'(75차 원안): 게이트만 frac 무관으로 완화, hard-hold는
    기존 DISCONTINUITY_JERK_COST_BOOST_S(1.0s) 그대로 즉시 base 복귀.
  - 'full'(76차): 게이트뿐 아니라 hard-hold 유지시간/release-rate도
    방안I(handoff)과 완전히 동일(4.0s+100/s)하게 맞춤 -- 실제
    long_mpc.py 패치의 'discontinuity_lc' 소스 태그와 동일 동작.

replay_boost_duration.py의 BoostReplay 로직을 그대로 재사용하되,
lane_change_gate=True 옵션을 추가해 step()에 leftBlinker/rightBlinker를
받는다. LANE_CHANGE_VLEAD_CORRECTION_HOLD_S 자체는 v_lead 보정용
타이머와 별개 인스턴스로 이 스크립트 안에서 재현한다(long_mpc.py와
동일 원칙).
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
DISCONTINUITY_JERK_COST_BOOST_S = 1.0      # long_mpc.py 실제 값(방안C/G 기본 hard-hold)
# 73차가 방안I(handoff) 전용으로 확정한 값(long_mpc.py RADAR_HANDOFF_JERK_
# BOOST_S/RATE) -- replay_boost_duration.py는 이 값들을 BoostReplay
# 생성자 인자로만 받고 모듈 상수로 노출하지 않으므로 여기서 실제 값 그대로 재정의.
RADAR_HANDOFF_JERK_BOOST_S = 4.0
RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE = 100.0


class LaneChangeGateReplay:
  """BoostReplay(discontinuity_jerk_boost_timer=1.0s hard, split_gate 없음)
  + lane_change 조건부 완화를 추가한 버전.

  duration_mode:
    'gate_only' -- 75차 원안, 게이트만 완화(hard-hold는 1.0s 그대로)
    'full'      -- 76차, hard-hold/release-rate까지 방안I과 완전 동일(4.0s+100/s)
  """

  def __init__(self, lane_change_gate, duration_mode='gate_only'):
    self.lane_change_gate = lane_change_gate
    assert duration_mode in ('gate_only', 'full')
    self.duration_mode = duration_mode
    self._timer = 0.0
    self._trigger_source = None
    self._lane_change_hold_timer = 0.0
    self._release_value = None  # 76차 'full' 모드에서 handoff류 release-rate 감쇠용

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
        # 76차: 'full' 모드 + 차선변경 중이면 hard-hold 자체를 방안I과
        # 동일(4.0s)하게 부여 -- long_mpc.py의 'discontinuity_lc' 소스와 동일.
        if self.lane_change_gate and self.duration_mode == 'full' and lane_change_active_now:
          self._timer = RADAR_HANDOFF_JERK_BOOST_S
          self._trigger_source = 'discontinuity_lc'
        else:
          self._timer = DISCONTINUITY_JERK_COST_BOOST_S
          self._trigger_source = 'discontinuity'
        self._release_value = None
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
          self._timer = RADAR_HANDOFF_JERK_BOOST_S
          self._trigger_source = 'handoff'
          self._release_value = None
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

    # 76차: 'discontinuity_lc'(full 모드)는 'handoff'와 완전히 동일한
    # frac-무관 게이트 + release-rate 감쇠 경로를 탄다. 'gate_only' 모드는
    # 소스 태그가 여전히 'discontinuity'이므로 lane_change_active_now로
    # 별도 판정(75차 원안, hard-cutoff만 적용, release 없음).
    is_handoff_style = self._trigger_source in ('handoff', 'discontinuity_lc')
    is_lane_change_discontinuity_gate_only = (
      self.lane_change_gate and self.duration_mode == 'gate_only' and
      self._trigger_source == 'discontinuity' and
      lane_change_active_now
    )
    frac_independent = is_handoff_style or is_lane_change_discontinuity_gate_only
    boost_gate_ok = (self._timer > 0.0) and (not danger_active)
    if not frac_independent:
      boost_gate_ok = boost_gate_ok and (frac <= 0.0)

    if is_handoff_style:
      # long_mpc.py is_handoff_source 분기와 동일: hard-hold 종료 후에도
      # release_rate로 base까지 완만히 감쇠(danger_active 뜨면 즉시 강제복귀).
      if boost_gate_ok:
        a_change_cost = DISCONTINUITY_JERK_COST_BOOST
        self._release_value = DISCONTINUITY_JERK_COST_BOOST
      elif danger_active:
        a_change_cost = base_cost
        self._release_value = None
      elif self._release_value is not None:
        self._release_value = max(base_cost, self._release_value - RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE * dt)
        a_change_cost = self._release_value
        if self._release_value <= base_cost + 1e-6:
          self._release_value = None
      else:
        a_change_cost = base_cost
    else:
      a_change_cost = DISCONTINUITY_JERK_COST_BOOST if boost_gate_ok else base_cost

    return dict(triggered=triggered, a_change_cost=a_change_cost, danger_active=danger_active,
                frac=frac, timer_active=self._timer > 0.0, trigger_source=self._trigger_source,
                lane_change_active=lane_change_active_now)


def run(rows, t_lo, t_hi, lane_change_gate, duration_mode='gate_only'):
  sub = [r for r in rows if t_lo <= float(r['t']) <= t_hi]
  sub.sort(key=lambda r: float(r['t']))
  rep = LaneChangeGateReplay(lane_change_gate, duration_mode=duration_mode)
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


def summarize(name, t_lo, t_hi, ts_base, aEgos, variants, risk_thresh=-1.5, max_gap_s=0.5):
  """variants: [(label, res_list), ...] -- 첫 번째가 트리거 탐지 기준(보통 가장
  넓게 커버하는 변형, 트리거 시점/소스 자체는 lane_change_gate 여부와 무관하게
  동일하므로 아무 변형이나 기준으로 써도 됨)."""
  print(f"\n===== {name} (t={t_lo}~{t_hi}) =====")
  ref_label, ref_res = variants[0]
  triggered_idxs = [i for i, r in enumerate(ref_res) if r['triggered']]
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
  print(f"  트리거 t={ts_base[trig_idx]:.3f} (source={ref_res[trig_idx]['trigger_source']}, "
        f"lane_change_active={ref_res[trig_idx]['lane_change_active']})")
  print(f"  위험구간 t={ts_base[risk_start]:.3f}~{ts_base[risk_end]:.3f} ({risk_dur:.2f}s)")

  for label, res in variants:
    boosted = 0.0
    prev_t = None
    for i in range(risk_start, risk_end + 1):
      t = ts_base[i]
      dt = (t - prev_t) if prev_t is not None else 0.05
      prev_t = t
      if res[i]['a_change_cost'] >= 300.0:
        boosted += dt
    cov = 100.0 * boosted / risk_dur if risk_dur > 0 else 0.0
    print(f"  {label:<32} boost적용 {boosted:.2f}s / {risk_dur:.2f}s ({cov:.1f}%)")

  base_danger = sum(1 for r in variants[0][1] if r['danger_active'])
  any_mismatch = False
  for label, res in variants[1:]:
    d = sum(1 for r in res if r['danger_active'])
    if d != base_danger:
      print(f"  [경고] danger_active 프레임 수 불일치: {variants[0][0]}={base_danger} {label}={d}")
      any_mismatch = True
  if not any_mismatch:
    print(f"  danger_active 프레임 수 회귀 없음(전 변형 동일={base_danger})")


if __name__ == "__main__":
  devnotes_dir = "/home/claude/devnotes"
  rows1, meta1 = load_route(devnotes_dir, "ea5bcc0566")
  rows2, meta2 = load_route(devnotes_dir, "a5b1ce4e42")
  print(f"route1(ea5bcc0566): {meta1['n_rows']}행 / route2(a5b1ce4e42): {meta2['n_rows']}행")

  # 75차/76차 대상 구간: route2 t=1469~1472 / t=1541~1545 (discontinuity+차선변경)
  # 3-way 비교: UNPATCHED(기존) / gate_only(75차, hard-hold 1.0s 그대로) /
  # full(76차, hard-hold 4.0s+release-rate 100/s까지 방안I과 동일)
  for t_lo, t_hi in [(1460.0, 1480.0), (1535.0, 1550.0)]:
    ts_u, aEgos_u, res_u = run(rows2, t_lo, t_hi, lane_change_gate=False)
    ts_g, aEgos_g, res_g = run(rows2, t_lo, t_hi, lane_change_gate=True, duration_mode='gate_only')
    ts_f, aEgos_f, res_f = run(rows2, t_lo, t_hi, lane_change_gate=True, duration_mode='full')
    summarize(f"route2 discontinuity+lane_change t={t_lo}~{t_hi}", t_lo, t_hi, ts_u, aEgos_u,
              [("UNPATCHED(기존 frac 게이트)", res_u),
               ("75차 gate_only(hard 1.0s)", res_g),
               ("76차 full(4.0s+100/s)", res_f)])

  # 76차 핵심 검증: route2 t=1470.75 이벤트는 aEgo<=-1.5 위험구간 자체가
  # 짧아(0.05s) risk_dur 기반 %커버율 지표가 무의미 -- 75차 계속2가 발견한
  # 진짜 문제는 "실제 aEgo 최저점(트리거 후 1.4~1.65초, t≈1472.30~1472.40)
  # 시점에 hard-hold(1.0s, t=1471.75 소진)가 이미 꺼져있었다"는 것이므로,
  # 그 시점의 a_change_cost 값 자체를 직접 대조한다.
  print("\n===== 76차 핵심 확인: route2 t=1470.75 트리거, 최저점(t≈1472.30~1472.40) 시점 a_change_cost =====")
  ts_g2, aEgos_g2, res_g2 = run(rows2, 1465.0, 1476.0, lane_change_gate=True, duration_mode='gate_only')
  ts_f2, aEgos_f2, res_f2 = run(rows2, 1465.0, 1476.0, lane_change_gate=True, duration_mode='full')
  for i, t in enumerate(ts_g2):
    if 1472.20 <= t <= 1472.45:
      print(f"  t={t:.3f} aEgo={aEgos_g2[i]:+.3f}  75차(gate_only)={res_g2[i]['a_change_cost']:6.1f}"
            f"  76차(full)={res_f2[i]['a_change_cost']:6.1f}")
  print("  -> 75차(gate_only)는 hard-hold(1.0s, t=1471.75) 소진으로 최저점에서 이미 base 근처로")
  print("     복귀해 무력화됨 -- WIP.md 75차 계속2가 발견한 한계 재확인.")
  print("     76차(full)는 hard-hold가 4.0s(t=1474.75까지)라 최저점 전체 구간에서")
  print("     500(부스트) 유지 -- 이번 패치로 이 한계가 해소됨.")

  # 회귀 체크: route1 전체 구간에서 discontinuity+non-lane-change 트리거들의
  # a_change_cost 시퀀스가 UNPATCHED/76차(full) 동일한지(비차선변경 상황은
  # 100% 그대로 유지되어야 함).
  print("\n===== 회귀 체크: route1 전체, 76차(full) vs UNPATCHED a_change_cost diff =====")
  ts_b1, aEgos_b1, res_b1 = run(rows1, 0.0, 1e9, lane_change_gate=False)
  ts_p1, aEgos_p1, res_p1 = run(rows1, 0.0, 1e9, lane_change_gate=True, duration_mode='full')
  diffs = [i for i in range(len(res_b1)) if abs(res_b1[i]['a_change_cost'] - res_p1[i]['a_change_cost']) > 1e-6]
  print(f"  route1 전체 {len(res_b1)}프레임 중 diff 프레임: {len(diffs)}건")
  for i in diffs[:20]:
    print(f"    t={ts_b1[i]:.3f} base={res_b1[i]['a_change_cost']:.1f} patched={res_p1[i]['a_change_cost']:.1f} "
          f"source={res_p1[i]['trigger_source']} lane_change_active={res_p1[i]['lane_change_active']}")

  print("\n===== 회귀 체크: route2 전체, 76차(full) vs UNPATCHED a_change_cost diff =====")
  ts_b2, aEgos_b2, res_b2 = run(rows2, 0.0, 1e9, lane_change_gate=False)
  ts_p2, aEgos_p2, res_p2 = run(rows2, 0.0, 1e9, lane_change_gate=True, duration_mode='full')
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

  # 76차 추가 확인: gate_only(75차) vs full(76차) diff -- full이 gate_only보다
  # boost 커버 시간이 실제로 늘어나는지(줄어들면 버그).
  print("\n===== 76차 확인: route1/route2 전체, full vs gate_only 비교(디버그) =====")
  for name, rows in [("route1", rows1), ("route2", rows2)]:
    ts_g, aEgos_g, res_g = run(rows, 0.0, 1e9, lane_change_gate=True, duration_mode='gate_only')
    ts_f, aEgos_f, res_f = run(rows, 0.0, 1e9, lane_change_gate=True, duration_mode='full')
    boosted_g = sum(1 for r in res_g if r['a_change_cost'] >= 300.0)
    boosted_f = sum(1 for r in res_f if r['a_change_cost'] >= 300.0)
    print(f"  {name}: gate_only boost프레임={boosted_g}  full boost프레임={boosted_f}  "
          f"(full >= gate_only 이어야 정상: {'OK' if boosted_f >= boosted_g else 'FAIL'})")
