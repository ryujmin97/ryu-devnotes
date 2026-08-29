#!/usr/bin/env python3
"""
118차 설계 제안(빨간 박스 우회 경로에서도 적용되는 차선이탈 강제해제 게이트)
로직 단위 합성 시뮬레이션.

radard.py 기존 _is_cutout()(L657~662, CUTOUT_DPATH_THRESH=2.0m,
CUTOUT_VREL_GATE=-0.5)와 동일 철학을 그대로 재사용한 신규 게이트를
재현. 아직 radard.py에 실제 코드로 반영되지 않았으므로(118차: "아직
미구현, 사용자 확인 필요") 여기서는 118차 WIP.md에 기록된 제안 로직을
문자 그대로 옮겨 파라미터(THRESH, CONFIRM_S)를 바꿔가며 검증.

목적(119차, 사용자 제안 파라미터 검증):
  기존 CUTOUT_DPATH_THRESH=2.0m 그대로 재사용 vs 사용자가 제안한
  1.75m(더 좁힘) 사이의 트레이드오프를, (a) 정상 커브 dPath 노이즈
  (±0.3~0.9m, 118차 기록) 오탐 여부와 (b) route1 t=5915~5932 실측
  이벤트 근사 재현에서의 조기해제 효과 두 축으로 정량 비교.

주의: route1.csv 원본이 이 세션에 캐시/업로드돼 있지 않아 실측
프레임 단위 replay는 불가. 시나리오 2는 118차 WIP.md에 문서화된
요약 수치(t=5915 dPath~0.2m -> t=5931.02 dPath=-1.97m -> t=5932.53
자연해제, -1.98~-1.99 부근에서 정체)만으로 만든 "근사" 프로파일이며,
정밀 검증은 아니다(README/CHANGELOG에도 이 한계를 명시).
"""
import collections

DT = 0.05  # 20Hz, DT_MDL

# radard.py L42~43 기존 상수 (그대로 복사)
CUTOUT_DPATH_THRESH = 2.0
CUTOUT_VREL_GATE = -0.5


class LaneDepartureGateSim:
  """118차 WIP.md 제안 로직을 최대한 그대로 재현.
  status=True 이고 |dPath|>thresh 이고 vRel>vrel_gate(강접근 아님)인
  프레임이 confirm_s 이상 연속되면 강제로 status=False 전환.
  """

  def __init__(self, thresh, confirm_s, vrel_gate=CUTOUT_VREL_GATE):
    self.thresh = thresh
    self.confirm_s = confirm_s
    self.vrel_gate = vrel_gate
    self.cnt = 0.0
    self.forced_off_at = None

  def step(self, t, dPath, vRel, status_in):
    if self.forced_off_at is not None:
      return False  # 이미 해제됨
    if status_in and abs(dPath) > self.thresh and vRel > self.vrel_gate:
      self.cnt += DT
      if self.cnt >= self.confirm_s:
        self.forced_off_at = t
        return True
    else:
      self.cnt = 0.0
    return False


def run_normal_curve_noise(thresh, confirm_s, n_trials=200, seed=0):
  """시나리오1: 정상 차로 유지 중 커브 dPath 노이즈(±0.3~0.9m, 118차
  기록 실측 범위) -- confirm_s 이상 연속 초과가 없어야 함(오탐 방지).
  준정현파(커브 진입/이탈 형태) + 소음으로 근사."""
  import math
  import random
  random.seed(seed)
  false_positive_runs = 0
  for trial in range(n_trials):
    sim = LaneDepartureGateSim(thresh, confirm_s)
    triggered = False
    amp = random.uniform(0.3, 0.9)  # 118차 기록 실측 스윙 범위
    period = random.uniform(2.0, 5.0)  # 커브 통과 시간대 근사
    for i in range(400):  # 20초
      t = i * DT
      dPath = amp * math.sin(2 * math.pi * t / period) + random.uniform(-0.15, 0.15)
      vRel = random.uniform(-0.3, 0.3)  # 강접근 아님(느슨히 추종 중)
      if sim.step(t, dPath, vRel, True):
        triggered = True
        break
    if triggered:
      false_positive_runs += 1
  fp_rate = false_positive_runs / n_trials
  return fp_rate


def run_real_event_approx(thresh, confirm_s):
  """시나리오2: route1 t=5915.03~5932.53 이벤트 근사 재현(118차 기록
  수치 기반, 선형 근사 -- 정밀 replay 아님).
  t=0(=원본 t=5915.03) dPath=0.2m -> t=15.99(=t=5931.02) dPath=-1.97m
  (구간 내 완만가속 성장으로 근사: 뒤로 갈수록 변화율 커짐) ->
  이후 t=5932.53까지 -1.98~-1.99 정체 -> 자연해제.
  vRel은 118차에 기록 없음 -- 저속 launch 근접 상황 가정, 강접근
  아님(vRel=0 근사, 보수적으로 게이트 항상 통과하게 둠)."""
  t_release_natural = 5932.53 - 5915.03  # =17.50
  t_thresh_2p0_actual = 5931.02 - 5915.03  # =15.99, 실측 기록값

  sim = LaneDepartureGateSim(thresh, confirm_s)
  n = int(t_release_natural / DT) + 1
  forced_t = None
  for i in range(n):
    t = i * DT
    if t <= t_thresh_2p0_actual:
      # 0.2 -> 1.97 완만 가속 성장(제곱근형 근사: 초반 느리고 후반 가팔라짐)
      frac = t / t_thresh_2p0_actual
      dPath = -(0.2 + (1.97 - 0.2) * (frac ** 1.6))
    else:
      dPath = -1.985  # 정체 구간 근사
    vRel = 0.0
    if sim.step(t, dPath, vRel, True):
      forced_t = t
      break
  saved_s = None
  if forced_t is not None:
    saved_s = t_release_natural - forced_t
  return forced_t, saved_s, t_release_natural


def run_single_frame_spike(thresh, confirm_s):
  """시나리오3: 단일 프레임 노이즈 스파이크(threshold 살짝 초과 후
  즉시 복귀) -- confirm_s 디바운스로 트리거되면 안 됨."""
  sim = LaneDepartureGateSim(thresh, confirm_s)
  seq = [(0.0, 0.3), (0.05, thresh + 0.05), (0.10, 0.35), (0.15, 0.3)]
  triggered = False
  for t, dPath in seq:
    if sim.step(t, dPath, 0.0, True):
      triggered = True
  return triggered


def run_strong_closing_override(thresh, confirm_s):
  """시나리오4: dPath는 threshold 초과했지만 강하게 접근 중(vRel <
  vrel_gate)인 경우 -- danger override 철학과 일치하게 트리거되면
  안 됨(끼어들기 등 실제 위험 상황에서 락 풀리는 부작용 방지)."""
  sim = LaneDepartureGateSim(thresh, confirm_s)
  triggered = False
  for i in range(40):  # 2초간 지속
    t = i * DT
    if sim.step(t, thresh + 0.5, -1.0, True):  # vRel=-1.0 < -0.5, 강접근
      triggered = True
  return triggered


def main():
  print("=" * 78)
  print("119차: 118차 제안 LANE_DEPARTURE 게이트 파라미터 검증")
  print("       (기존 2.0m 재사용 vs 사용자 제안 1.75m, confirm_s=0.5 고정)")
  print("=" * 78)

  configs = [
    ("2.00m / 0.5s (118차 기본안)", 2.00, 0.5),
    ("1.75m / 0.5s (사용자 제안)", 1.75, 0.5),
    ("2.30m / 0.5s (118차 '보수적' 대안)", 2.30, 0.5),
  ]

  print("\n[시나리오1] 정상 커브 dPath 노이즈(±0.3~0.9m, 200회 시행) 오탐율")
  for name, thresh, confirm_s in configs:
    fp_rate = run_normal_curve_noise(thresh, confirm_s)
    flag = "  <-- 오탐 위험" if fp_rate > 0.02 else ""
    print(f"  {name:32s}: false_positive_rate = {fp_rate*100:5.1f}% ({int(fp_rate*200)}/200){flag}")

  print("\n[시나리오2] route1 t=5915~5932 실측 이벤트 근사(선형 아님, 참고용)")
  print(f"  (자연해제까지 원래 {5932.53-5915.03:.2f}s 걸림, 실측 t=5931.02에 dPath=-1.97 최초도달)")
  for name, thresh, confirm_s in configs:
    forced_t, saved_s, natural = run_real_event_approx(thresh, confirm_s)
    if forced_t is None:
      print(f"  {name:32s}: 트리거 안 됨(자연해제까지 대기)")
    else:
      print(f"  {name:32s}: t={forced_t:5.2f}s 에 강제해제 -> 자연해제 대비 {saved_s:4.2f}s 단축")

  print("\n[시나리오3] 단일 프레임 노이즈 스파이크 (confirm_s 디바운스 확인)")
  for name, thresh, confirm_s in configs:
    triggered = run_single_frame_spike(thresh, confirm_s)
    status = "FAIL(오탐)" if triggered else "PASS(오탐없음)"
    print(f"  {name:32s}: {status}")

  print("\n[시나리오4] 강접근(vRel<-0.5) 중 dPath 초과 -- danger override 우선 확인")
  for name, thresh, confirm_s in configs:
    triggered = run_strong_closing_override(thresh, confirm_s)
    status = "FAIL(부적절 해제)" if triggered else "PASS(게이트 정상 차단)"
    print(f"  {name:32s}: {status}")

  print("\n" + "=" * 78)
  print("결론 요약은 CHANGELOG/WIP 기록 참고")
  print("=" * 78)


if __name__ == "__main__":
  main()
