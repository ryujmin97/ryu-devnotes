#!/usr/bin/env python3
"""
94차(방안 D) 로직 단위 시뮬레이션 -- discontinuity 트리거 시
_vision_dRel_rate/_vision_dRel_rate_window/_vision_dRel_prev도 함께
리셋하는 패치의 회귀검증.

배경(63차 계속, r1-14 사각지대): 방안C(discontinuity 트리거 시
_lead_acq_timer=0)만으로는 frac_rate/frac_ttc를 못 막는다 -- 이 둘은
_lead_acq_timer와 무관하게 self._vision_dRel_rate를 직접 읽기 때문.
radar가 discontinuity 급락 이후에도 한동안 락온을 못 하는 경우(r1-14류),
급락 자체가 이미 _vision_dRel_rate(저역통과 필터)를 크게 오염시켜놓은
상태라 frac_rate가 트리거 이후에도 한동안 DANGER급으로 유지된다.

이 스크립트는 long_mpc.py의 실제 코드(클램프+중앙값+저역통과 필터,
discontinuity 트리거, frac_rate 정규화)를 그대로 복사해 재현 --
`sim_frac_rate.py`(28차)/`sim_drel_discontinuity.py`(63차)와 각각
겹치는 부분이 있으나, "방안D 리셋이 frac_rate에 실제로 어떤 영향을
주는지"를 함께 보는 스크립트가 그동안 없었음.

시나리오:
 1. r1-14류 재현(cutin 급락 후 radar 락온 지연): UNPATCHED는 트리거
    이후에도 frac_rate가 한동안 1.0(DANGER) 유지, PATCHED는 트리거
    프레임에서 즉시 0으로 리셋되고 이후 완만한 접근이면 다시 서서히만
    상승.
 2. 정상 완만 접근(discontinuity 없음): PATCHED/UNPATCHED 완전 동일
    (회귀 없음) -- 방안D는 discontinuity 트리거 조건 자체를 안 건드림.
 3. r1-3류(radar 즉시 락온): 락온 프레임 자체가 이미 rate/window를
    무조건 리셋하므로(기존 코드), 방안D 유무와 무관하게 락온 이후
    frac_rate가 같아야 함 -- 방안D가 이 기존 검증된 조합을 깨지 않는지
    확인.
 4. danger override 독립성 재확인(정적 확인, 코드 구조상 process_lead의
    ttc_now는 _vision_dRel_rate와 별개 변수라 이 리셋과 무관).
"""
import collections
import numpy as np

DT = 0.05  # 20Hz
DREL_DISCONTINUITY_DROP_THRESH = 15.0
DREL_DISCONTINUITY_WINDOW_N = 5
VISION_CLOSING_RATE_TAU = 1.0
VISION_CLOSING_RATE_MEDIAN_WINDOW = 3
VISION_CLOSING_RATE_MAX_PLAUSIBLE = 30.0
VISION_CLOSING_RATE_GATE_CAUTION = -2.2
VISION_CLOSING_RATE_GATE_DANGER = -5.0


class DiscontinuityFracRateSim:
  """long_mpc.py의 discontinuity 트리거 + vision_dRel_rate 필터 +
  frac_rate 정규화 부분을 그대로 재현. patched=True면 94차(방안D) 적용."""

  def __init__(self, patched):
    self.dt = DT
    self.patched = patched
    self._lead_acq_timer = 0.0
    self._dRel_raw_history = collections.deque(maxlen=DREL_DISCONTINUITY_WINDOW_N)
    self._vision_dRel_prev = None
    self._vision_dRel_rate = 0.0
    self._vision_dRel_rate_window = collections.deque(maxlen=VISION_CLOSING_RATE_MEDIAN_WINDOW)
    self.triggered_frames = []
    self.trace = []  # (frame, dRel, rate, frac_rate, triggered_this_frame)

  def frac_rate(self):
    # long_mpc.py 실제 정규화 그대로(음수 rate만 의미, GATE_CAUTION~GATE_DANGER 사이 선형)
    if self._vision_dRel_rate >= VISION_CLOSING_RATE_GATE_CAUTION:
      return 0.0
    f = ((VISION_CLOSING_RATE_GATE_CAUTION - self._vision_dRel_rate) /
         (VISION_CLOSING_RATE_GATE_CAUTION - VISION_CLOSING_RATE_GATE_DANGER))
    return float(np.clip(f, 0.0, 1.0))

  def step(self, frame_idx, dRel_now, v_ego=20.0, lead_one_status_now=True, radar_locked=False):
    triggered_this_frame = False
    if lead_one_status_now and not radar_locked:
      self._dRel_raw_history.append(dRel_now)
      if (len(self._dRel_raw_history) == self._dRel_raw_history.maxlen and
          (self._dRel_raw_history[-1] - self._dRel_raw_history[0]) < -DREL_DISCONTINUITY_DROP_THRESH):
        self._lead_acq_timer = 0.0
        self.triggered_frames.append(frame_idx)
        triggered_this_frame = True
        if self.patched:
          # 94차(방안D)
          self._vision_dRel_rate = 0.0
          self._vision_dRel_rate_window.clear()
          self._vision_dRel_prev = None
      else:
        self._lead_acq_timer += self.dt

      if self._vision_dRel_prev is not None:
        raw_rate = (dRel_now - self._vision_dRel_prev) / max(self.dt, 1e-3)
        raw_rate_clamped = max(raw_rate, -VISION_CLOSING_RATE_MAX_PLAUSIBLE)
        self._vision_dRel_rate_window.append(raw_rate_clamped)
        rate_for_filter = float(np.median(self._vision_dRel_rate_window))
        alpha = float(np.clip(self.dt / VISION_CLOSING_RATE_TAU, 0.0, 1.0))
        self._vision_dRel_rate = self._vision_dRel_rate * (1. - alpha) + rate_for_filter * alpha
      self._vision_dRel_prev = dRel_now
    elif lead_one_status_now and radar_locked:
      self._dRel_raw_history.clear()
      self._vision_dRel_prev = None
      self._vision_dRel_rate = 0.0
      self._vision_dRel_rate_window.clear()

    self.trace.append((frame_idx, dRel_now, self._vision_dRel_rate, self.frac_rate(), triggered_this_frame))
    return triggered_this_frame


def run_pair(name, dRel_seq, radar_lock_frame=None, print_trace=False):
  """UNPATCHED/PATCHED 두 버전을 같은 dRel 시퀀스로 재생, frac_rate 비교."""
  results = {}
  for patched in (False, True):
    sim = DiscontinuityFracRateSim(patched=patched)
    for i, d in enumerate(dRel_seq):
      radar_locked = radar_lock_frame is not None and i >= radar_lock_frame
      sim.step(i, d, radar_locked=radar_locked)
    results[patched] = sim

  unpatched, patched = results[False], results[True]
  trig_frame = unpatched.triggered_frames[0] if unpatched.triggered_frames else None

  if print_trace:
    print(f"  --- {name} trace (frame, dRel, rate, frac_rate) ---")
    for i in range(len(dRel_seq)):
      u = unpatched.trace[i]
      p = patched.trace[i]
      marker = " <== trigger" if u[4] else ""
      print(f"  f{i:2d} dRel={u[1]:6.1f} | UNPATCHED rate={u[2]:7.2f} frac={u[3]:.3f} | "
            f"PATCHED rate={p[2]:7.2f} frac={p[3]:.3f}{marker}")

  return unpatched, patched, trig_frame


def scenario_1_r1_14_style():
  """cutin 급락 후 radar 락온이 한참(급감속 종료 이후) 뒤에야 발생 --
  UNPATCHED는 트리거 이후에도 frac_rate가 DANGER급으로 남아야 하고,
  PATCHED는 트리거 프레임에서 즉시 0으로 떨어져야 함."""
  # 완만 접근 몇 프레임 -> 급락(discontinuity, 65->24m류) -> 급락 이후
  # 완만한 접근으로 안정화(트리거 이후 rate 자체는 크지 않음) -- radar는
  # 락온 안 함(None, r1-14류: 락온이 이 윈도우 밖에서 늦게 발생)
  seq = [80.0, 78.0, 76.0, 74.0, 72.0,   # 완만 접근(문턱 안 넘음)
         70.0, 65.0, 55.0, 40.0, 24.0,   # 급락(discontinuity, 5프레임 -46m)
         23.5, 23.0, 22.5, 22.0, 21.5]   # 트리거 이후 완만한 접근(rate 작음)
  unpatched, patched, trig = run_pair("1. r1-14류(radar 락온 지연)", seq, radar_lock_frame=None, print_trace=True)
  assert trig is not None, "이 시나리오는 discontinuity가 트리거돼야 함"

  # 트리거 프레임 자체의 frac_rate: UNPATCHED는 급락 rate가 그대로
  # DANGER급(오히려 이 프레임에 raw_rate가 가장 크게 튐), PATCHED는 0.
  frac_at_trigger_unpatched = unpatched.trace[trig][3]
  frac_at_trigger_patched = patched.trace[trig][3]

  # 트리거 직후 몇 프레임 동안(완만한 접근만 있는데도) UNPATCHED가 여전히
  # 높은 frac_rate를 유지하는지(저역통과 필터 잔류 오염) 확인.
  frac_2_after_unpatched = unpatched.trace[trig + 2][3]
  frac_2_after_patched = patched.trace[trig + 2][3]

  ok = (frac_at_trigger_patched == 0.0 and
        frac_at_trigger_unpatched > frac_at_trigger_patched and
        frac_2_after_unpatched > frac_2_after_patched)
  status = "PASS" if ok else "FAIL"
  print(f"  [{status}] trigger_frame={trig} | frac@trigger UNPATCHED={frac_at_trigger_unpatched:.3f} "
        f"PATCHED={frac_at_trigger_patched:.3f} | frac@trigger+2 UNPATCHED={frac_2_after_unpatched:.3f} "
        f"PATCHED={frac_2_after_patched:.3f}")
  return ok


def scenario_2_normal_approach_no_regression():
  """discontinuity가 전혀 없는 완만한 접근 -- PATCHED/UNPATCHED 완전 동일해야 함."""
  seq = [90.0 - 1.5 * i for i in range(20)]  # 1.5m/frame 일정한 완만 접근(30m/s 상한 안 넘음)
  unpatched, patched, trig = run_pair("2. 정상 완만 접근(discontinuity 없음)", seq, radar_lock_frame=None)
  assert trig is None, "이 시나리오는 discontinuity가 트리거되면 안 됨"
  diffs = [abs(u[2] - p[2]) for u, p in zip(unpatched.trace, patched.trace)]
  ok = max(diffs) < 1e-9
  status = "PASS" if ok else "FAIL"
  print(f"  [{status}] max|rate_diff|={max(diffs):.6f} (0이어야 회귀 없음)")
  return ok


def scenario_3_r1_3_style_radar_locks_immediately():
  """cutin 급락 직후(다음 프레임) radar가 바로 락온 -- 기존 코드가 락온
  프레임에서 이미 rate/window/prev를 전부 무조건 리셋하므로, 방안D 유무와
  무관하게 락온 이후 상태는 완전히 같아야 함(기존 검증된 조합 회귀 없음)."""
  seq = [80.0, 78.0, 76.0, 74.0, 72.0,
         70.0, 65.0, 55.0, 40.0, 24.0]   # 트리거는 f9에서 발생
  # radar가 트리거 바로 다음 프레임(f10)에 락온된다고 가정
  radar_lock_frame = 10
  seq = seq + [23.0, 22.0, 21.0]  # 락온 이후 몇 프레임 더
  unpatched, patched, trig = run_pair("3. r1-3류(radar 즉시 락온)", seq, radar_lock_frame=radar_lock_frame, print_trace=True)
  assert trig is not None

  # 락온 이후(f10 이상) rate/frac_rate는 두 버전 모두 0/0이어야 함(기존
  # 코드의 무조건 리셋 경로가 이미 처리 -- 방안D와 무관).
  diffs_after_lock = [abs(u[2] - p[2]) for u, p in zip(unpatched.trace[radar_lock_frame:],
                                                        patched.trace[radar_lock_frame:])]
  all_zero_after_lock = all(u[2] == 0.0 and p[2] == 0.0
                             for u, p in zip(unpatched.trace[radar_lock_frame:],
                                             patched.trace[radar_lock_frame:]))
  ok = max(diffs_after_lock) < 1e-9 and all_zero_after_lock
  status = "PASS" if ok else "FAIL"
  print(f"  [{status}] 락온 이후 max|rate_diff|={max(diffs_after_lock):.6f}, "
        f"양쪽 다 rate=0 유지={all_zero_after_lock}")
  return ok


def scenario_4_danger_override_independence():
  print("  [INFO] 4. danger override 독립성: process_lead()의 ttc_now는 "
        "radarstate.leadOne.dRel/vRel 기반으로 매 프레임 직접 계산되며, "
        "self._vision_dRel_rate/window와는 코드상 완전히 분리된 변수 -- "
        "방안D의 리셋과 무관하게 항상 즉시 반응(정적 확인, FINDINGS.md "
        "'안전 백스톱 확인' 항목과 동일 근거).")
  return True


def main():
  print("=== 94차(방안 D) discontinuity 트리거 시 vision_dRel_rate 동반 리셋 검증 ===\n")
  results = [
      scenario_1_r1_14_style(),
      scenario_2_normal_approach_no_regression(),
      scenario_3_r1_3_style_radar_locks_immediately(),
      scenario_4_danger_override_independence(),
  ]
  print()
  n_pass = sum(results)
  print(f"=== {n_pass}/{len(results)} PASS ===")
  return n_pass == len(results)


if __name__ == "__main__":
  import sys
  sys.exit(0 if main() else 1)
