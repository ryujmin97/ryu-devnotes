#!/usr/bin/env python3
"""
63차 — r1-3/r1-14 원본 rlog(재업로드분, route a2141d7786 seg3/seg14) CSV로
방안C(61차 계속) 실측 재생 검증.

long_mpc.py의 lead-acquisition ramp bookkeeping(L744~845) +
process_lead 진입 직전 vlead_correction_suppressed 계산(L859~877) +
frac_time/frac_ttc/frac_rate 계산(L907~961)을 실제 코드와 최대한
동일하게 복제. PATCHED(방안C 있음, 현재 origin 상태)와 UNPATCHED(방안C
제거, discontinuity 리셋 없음 -- 60차 계속2까지만 있던 상태)를 같은
실측 프레임 시퀀스에 나란히 돌려 결과를 비교한다.

주의: acados MPC 자체(floor_cap 적용 이후 실제 j_ego/a_ego 산출)는
재현하지 않음 -- frac(개입 강도 floor)과 vision_rate_for_lead0
(v_lead 직접보정 주입 여부)까지만 비교해도 "이 프레임에 방안C가
개입했는지/그 결과 v_lead 보정이 억제됐는지"는 정량적으로 판단 가능.
"""
import sys
import pandas as pd
import numpy as np
import collections

# --- 실제 long_mpc.py 상수(grep으로 확인한 값 그대로) ---
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

NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S = 1.5
LANE_CHANGE_VLEAD_CORRECTION_HOLD_S = 1.0

DREL_DISCONTINUITY_DROP_THRESH = 15.0
DREL_DISCONTINUITY_WINDOW_N = 5


class LongMpcReplay:
  def __init__(self, patched: bool):
    self.patched = patched
    self._lead_present_run_timer = 0.0
    self._lead_absent_timer = 0.0
    self._lead_acq_ramp_started = False
    self._lead_acq_timer = 0.0
    self._vision_dRel_prev = None
    self._vision_dRel_rate = 0.0
    self._vision_dRel_rate_window = collections.deque(maxlen=VISION_CLOSING_RATE_MEDIAN_WINDOW)
    self._dRel_raw_history = collections.deque(maxlen=DREL_DISCONTINUITY_WINDOW_N)
    self._lane_change_vlead_hold_timer = 0.0
    self.dt = 0.05  # overwritten per-step

  def step(self, dt, lead_status, dRel, vRel, radar_locked, blinker_active, v_ego, cruise_enabled):
    self.dt = max(dt, 1e-3)
    lead_one_status_now = bool(lead_status)

    # --- ramp bookkeeping (L754~780) ---
    if lead_one_status_now:
      self._lead_absent_timer = 0.0
      self._lead_present_run_timer += self.dt
      if not self._lead_acq_ramp_started:
        if self._lead_present_run_timer >= LEAD_ACQ_CONFIRM_TIME:
          self._lead_acq_ramp_started = True
          self._lead_acq_timer = 0.0
      else:
        self._lead_acq_timer += self.dt
    else:
      self._lead_absent_timer += self.dt
      if self._lead_absent_timer > LEAD_ACQ_LOSS_GRACE_TIME:
        self._lead_present_run_timer = 0.0
        self._lead_acq_ramp_started = False
        self._lead_acq_timer = 0.0
        self._vision_dRel_prev = None
        self._vision_dRel_rate = 0.0
        self._vision_dRel_rate_window.clear()
        self._dRel_raw_history.clear()

    # --- vision-only dRel bookkeeping + (patched only) discontinuity check (L801~844) ---
    discontinuity_triggered = False
    if lead_one_status_now and not radar_locked:
      dRel_now = float(dRel)
      if self.patched:
        self._dRel_raw_history.append(dRel_now)
        if (len(self._dRel_raw_history) == self._dRel_raw_history.maxlen and
            (self._dRel_raw_history[-1] - self._dRel_raw_history[0]) < -DREL_DISCONTINUITY_DROP_THRESH):
          self._lead_acq_timer = 0.0
          discontinuity_triggered = True

      if self._vision_dRel_prev is not None:
        raw_rate = (dRel_now - self._vision_dRel_prev) / self.dt
        raw_rate_clamped = max(raw_rate, -VISION_CLOSING_RATE_MAX_PLAUSIBLE)
        self._vision_dRel_rate_window.append(raw_rate_clamped)
        rate_for_filter = float(np.median(self._vision_dRel_rate_window))
        alpha = float(np.clip(self.dt / VISION_CLOSING_RATE_TAU, 0.0, 1.0))
        self._vision_dRel_rate = self._vision_dRel_rate * (1. - alpha) + rate_for_filter * alpha
      self._vision_dRel_prev = dRel_now
    elif lead_one_status_now and radar_locked:
      self._vision_dRel_prev = None
      self._vision_dRel_rate = 0.0
      self._vision_dRel_rate_window.clear()
      self._dRel_raw_history.clear()
    elif self._lead_absent_timer > LEAD_ACQ_LOSS_GRACE_TIME:
      self._vision_dRel_prev = None
      self._vision_dRel_rate = 0.0
      self._vision_dRel_rate_window.clear()
      self._dRel_raw_history.clear()

    # --- vlead_correction_suppressed / vision_rate_for_lead0 (L866~877) ---
    if blinker_active:
      self._lane_change_vlead_hold_timer = LANE_CHANGE_VLEAD_CORRECTION_HOLD_S
    else:
      self._lane_change_vlead_hold_timer = max(0.0, self._lane_change_vlead_hold_timer - self.dt)
    vlead_correction_suppressed = (
      self._lead_acq_timer < NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S or
      blinker_active or
      self._lane_change_vlead_hold_timer > 0.0
    )
    vision_rate_for_lead0 = (self._vision_dRel_rate
                              if self._lead_acq_timer >= VISION_CLOSING_RATE_MIN_TIME and not vlead_correction_suppressed
                              else None)

    # --- frac_time / frac_ttc / frac_rate (L907~961), mode='acc' 가정 (cruiseEnabled) ---
    frac_time = frac_ttc = frac_rate = 0.0
    ttc_now = 999.0
    if cruise_enabled and lead_one_status_now and v_ego >= LEAD_ACQ_MIN_V_EGO and self._lead_acq_ramp_started:
      if self._lead_acq_timer <= LEAD_ACQ_RAMP_TIME:
        frac_time = float(np.clip(self._lead_acq_timer / LEAD_ACQ_RAMP_TIME, 0.0, 1.0))
      else:
        frac_time = 0.0

      lead_v_rel = vRel
      if lead_v_rel < -0.1:
        ttc_now = dRel / max(-lead_v_rel, 0.1)
      else:
        ttc_now = 999.0

      if (not radar_locked) and self._lead_acq_timer >= VISION_CLOSING_RATE_MIN_TIME:
        if self._vision_dRel_rate < -0.1:
          ttc_dRel = dRel / max(-self._vision_dRel_rate, 0.1)
          ttc_now = min(ttc_now, ttc_dRel)

      frac_ttc = float(np.clip((LEAD_ACQ_TTC_CAUTION - ttc_now) / (LEAD_ACQ_TTC_CAUTION - LEAD_ACQ_TTC_DANGER), 0.0, 1.0))

      if (not radar_locked) and self._lead_acq_timer >= VISION_CLOSING_RATE_MIN_TIME:
        frac_rate = float(np.clip(
          (VISION_CLOSING_RATE_GATE_CAUTION - self._vision_dRel_rate) /
          (VISION_CLOSING_RATE_GATE_CAUTION - VISION_CLOSING_RATE_GATE_DANGER), 0.0, 1.0))

    frac = max(frac_time, frac_ttc, frac_rate)

    return dict(
      lead_acq_timer=self._lead_acq_timer,
      vision_dRel_rate=self._vision_dRel_rate,
      discontinuity_triggered=discontinuity_triggered,
      vlead_suppressed=vlead_correction_suppressed,
      vision_rate_for_lead0=vision_rate_for_lead0,
      frac_time=frac_time, frac_ttc=frac_ttc, frac_rate=frac_rate, frac=frac,
      ttc_now=ttc_now,
    )


def run_segment(csv_path, seg_suffix, t_lo=None, t_hi=None):
  df = pd.read_csv(csv_path)
  seg = df[df['seg'].str.endswith(seg_suffix)].reset_index(drop=True)
  if t_lo is not None:
    seg = seg[(seg['t'] >= t_lo) & (seg['t'] <= t_hi)].reset_index(drop=True)

  patched = LongMpcReplay(patched=True)
  unpatched = LongMpcReplay(patched=False)

  rows = []
  prev_t = None
  for i, row in seg.iterrows():
    t = row['t']
    dt = (t - prev_t) if prev_t is not None else 0.05
    prev_t = t
    lead_status = bool(row['leadStatus']) if not pd.isna(row['leadStatus']) else False
    dRel = row['leadDRel'] if not pd.isna(row.get('leadDRel', np.nan)) else 0.0
    vRel = row['leadVRel'] if not pd.isna(row.get('leadVRel', np.nan)) else 0.0
    radar_locked = bool(row['leadRadar']) if not pd.isna(row.get('leadRadar', np.nan)) else False
    blinker = bool(row.get('leftBlinker', False)) or bool(row.get('rightBlinker', False))
    v_ego = row['vEgo']
    cruise_enabled = bool(row['cruiseEnabled'])

    rp = patched.step(dt, lead_status, dRel, vRel, radar_locked, blinker, v_ego, cruise_enabled)
    ru = unpatched.step(dt, lead_status, dRel, vRel, radar_locked, blinker, v_ego, cruise_enabled)

    rows.append(dict(
      t=t, aEgo=row['aEgo'], dRel=dRel, vRel=vRel, radar=radar_locked,
      p_disc=rp['discontinuity_triggered'], p_timer=rp['lead_acq_timer'],
      p_rate=rp['vision_dRel_rate'], p_suppressed=rp['vlead_suppressed'],
      p_vr4lead0=rp['vision_rate_for_lead0'], p_frac=rp['frac'],
      p_frac_rate=rp['frac_rate'], p_frac_ttc=rp['frac_ttc'],
      u_timer=ru['lead_acq_timer'], u_rate=ru['vision_dRel_rate'],
      u_suppressed=ru['vlead_suppressed'], u_vr4lead0=ru['vision_rate_for_lead0'],
      u_frac=ru['frac'], u_frac_rate=ru['frac_rate'], u_frac_ttc=ru['frac_ttc'],
    ))
  return pd.DataFrame(rows)


def summarize(name, res):
  print(f"\n===== {name} =====")
  n_disc = res['p_disc'].sum()
  print(f"discontinuity 트리거 프레임 수: {n_disc}")
  if n_disc:
    print(res[res['p_disc']][['t', 'dRel']].to_string(index=False))

  # v_lead 직접보정이 실제로 주입된(None 아닌) 프레임 비교
  p_active = res['p_vr4lead0'].notna().sum()
  u_active = res['u_vr4lead0'].notna().sum()
  print(f"v_lead 직접보정 주입 프레임: PATCHED={p_active} / UNPATCHED={u_active} "
        f"(감소={u_active - p_active})")

  # frac(개입강도 floor) 최대값/평균 비교
  print(f"frac 최댓값: PATCHED={res['p_frac'].max():.3f} / UNPATCHED={res['u_frac'].max():.3f}")
  print(f"frac 평균값: PATCHED={res['p_frac'].mean():.3f} / UNPATCHED={res['u_frac'].mean():.3f}")

  # aEgo 최저치가 나온 시점 부근에서 두 버전의 frac/rate 비교
  idxmin = res['aEgo'].idxmin()
  lo = max(0, idxmin - 8)
  hi = min(len(res), idxmin + 3)
  print(f"\naEgo 최저치({res.loc[idxmin,'aEgo']:.3f}) 부근 (t={res.loc[idxmin,'t']:.3f}):")
  cols = ['t', 'dRel', 'aEgo', 'radar', 'p_disc', 'p_suppressed', 'p_frac', 'u_suppressed', 'u_frac']
  print(res.loc[lo:hi, cols].to_string(index=False))
  return res


if __name__ == "__main__":
  res3 = run_segment('/home/claude/work/route63/route1.csv', '--3', t_lo=256.0, t_hi=262.0)
  summarize("seg3 (r1-3, cutin 급감속)", res3)

  res14 = run_segment('/home/claude/work/route63/route1.csv', '--14', t_lo=916.0, t_hi=926.0)
  summarize("seg14 (r1-14, cutin 급감속_택시)", res14)
