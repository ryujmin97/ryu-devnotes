#!/usr/bin/env python3
"""
104차/130차: LeadBlend BIG_JUMP '즉시 스냅' 경로에 신뢰도 게이트를
추가한 패치(radard.py LeadBlend.update())의 로직 단위 합성 검증.

배경: 104차 실차 로그(route 0000034f--ed879bbde8 seg10/11, t=684.3~
688.97) 분석에서, 3.5초간 안정적으로 레이더 락온되던 근접 리드가
조향각 증가(커브 진입)로 락을 잃고 vision-only 저신뢰(prob≈0.24)로
전환되는 순간, 실제로는 근접(qcamera 대조 30~40m) 물체인데도 vision
단독 추정이 84~89m로 튀며 기존 BIG_JUMP(>15m, 안전방향) 즉시-스냅
경로를 타고 블렌딩 없이 그대로 반영됨을 확인(FINDINGS.md 104차
Finding A). radard.py를 이 컨테이너에서 직접 import할 수 없어(capnp/
cereal 의존성), LeadBlend 클래스 로직을 patched/unpatched 두 버전으로
문자 그대로 복제해 비교한다.

검증 항목:
  A) 104차 실측 근사 재현 -- patched가 즉시 스냅을 하지 않고
     LEAD_BLEND_SAFE_DIST_TIME(0.35s) 시정수로 점진 전환하는지, 첫
     프레임에서 unpatched 대비 급격한 dRel 점프가 줄었는지 확인.
  B) 고신뢰 vision(modelProb>=GATE) far jump -- 회귀 없음(patched ==
     unpatched, 즉시 스냅 유지) 확인.
  C) 레이더 교차검증(radar=True) far jump -- 회귀 없음 확인.
  D) closer_jump(위험 방향, 8m 이상 더 가까워짐) -- 게이트와 무관하게
     기존 danger-passthrough 그대로 즉시 반영되는지 확인(반응지연 없음).
  E) 정상 추종 중(점프 없음) -- unpatched/patched 완전 동일(diff=0) 확인.

사용: python3 sim_lead_blend_far_jump_gate.py
"""
import copy

DT = 0.05  # 20Hz, DT_MDL

# radard.py 기존 상수 (그대로 복사, L38~66 부근)
LEAD_BLEND_TTC_DANGER = 2.5
LEAD_BLEND_DANGER_HOLD = 0.3
LEAD_BLEND_SAFE_DIST_TIME = 0.35
LEAD_BLEND_CLOSER_JUMP_DIST = 8.0
LEAD_BLEND_BIG_JUMP_DIST = 15.0
# 104차/130차 신규
LEAD_BLEND_BIG_JUMP_PROB_GATE = 0.70


def _ttc(dRel, vRel):
  if vRel >= -0.1:
    return 1e3
  return max(dRel, 0.0) / max(-vRel, 0.1)


class LeadBlendSim:
  """radard.py LeadBlend 클래스를 patched 여부에 따라 재현.
  patched=False: 원본(BIG_JUMP는 신뢰도 무관하게 항상 즉시 스냅)
  patched=True : 104차/130차 수정(BIG_JUMP는 radar 또는 고신뢰 vision일
                 때만 즉시 스냅, 아니면 일반 블렌딩 경로로)
  """

  def __init__(self, patched: bool):
    self.patched = patched
    self.prev = None
    self.miss_cnt = 0
    self.danger_hold_cnt = 0

  def _is_dangerous(self, raw):
    ttc = _ttc(raw['dRel'], raw['vRel'])
    closing = raw['vRel'] < -0.1
    worsening = (self.prev is not None and self.prev.get('status') and
                 raw['vRel'] < self.prev.get('vRel', 0.0) - 0.3)
    closer_jump = (self.prev is not None and self.prev.get('status') and
                   (self.prev.get('dRel', 0.0) - raw['dRel']) > LEAD_BLEND_CLOSER_JUMP_DIST)
    return closer_jump or (ttc < LEAD_BLEND_TTC_DANGER and (closing or worsening))

  def update(self, raw: dict, dt: float) -> dict:
    if not raw.get('status'):
      self.prev, self.miss_cnt, self.danger_hold_cnt = None, 0, 0
      return raw

    self.miss_cnt = 0

    if self.prev is None or not self.prev.get('status'):
      self.prev = dict(raw)
      return raw

    dangerous = self._is_dangerous(raw)
    if dangerous:
      self.danger_hold_cnt = int(LEAD_BLEND_DANGER_HOLD / max(dt, 1e-3))

    if dangerous or self.danger_hold_cnt > 0:
      self.danger_hold_cnt = max(0, self.danger_hold_cnt - 1)
      self.prev = dict(raw)
      return raw

    is_big_jump = abs(raw['dRel'] - self.prev.get('dRel', raw['dRel'])) > LEAD_BLEND_BIG_JUMP_DIST
    if self.patched:
      is_trusted = raw.get('radar', False) or raw.get('modelProb', 0.0) >= LEAD_BLEND_BIG_JUMP_PROB_GATE
      snap = is_big_jump and is_trusted
    else:
      snap = is_big_jump

    if snap:
      self.prev = dict(raw)
      return raw

    alpha = max(0.0, min(1.0, dt / LEAD_BLEND_SAFE_DIST_TIME))
    blended = dict(raw)
    for k in ('dRel', 'vRel', 'vLead', 'aLead', 'aLeadK'):
      if k in raw and k in self.prev:
        blended[k] = self.prev[k] + (raw[k] - self.prev[k]) * alpha
    self.prev = dict(blended)
    return blended


def mk(dRel, vRel, status=True, radar=False, modelProb=0.5):
  return {'status': status, 'dRel': dRel, 'vRel': vRel, 'vLead': 0.0,
          'aLead': 0.0, 'aLeadK': 0.0, 'dPath': 0.0, 'radar': radar,
          'modelProb': modelProb}


def scenario_A_104cha_reproduction():
  """A) 104차 실측 근사: 레이더 락온 근접(35m) 안정 추종 3.5초 ->
  락 유실 + vision-only 저신뢰(prob=0.24)로 dRel이 89m로 튐(54m
  jump). patched가 첫 프레임에 그대로 스냅하지 않아야 한다."""
  sim_unpatched = LeadBlendSim(patched=False)
  sim_patched = LeadBlendSim(patched=True)

  # 3.5초(70프레임) 안정 레이더 추종(35m, vRel 약간의 접근)
  for i in range(70):
    raw = mk(dRel=35.0 - i * 0.02, vRel=-0.4, radar=True, modelProb=0.9)
    r_u = sim_unpatched.update(raw, DT)
    r_p = sim_patched.update(raw, DT)

  # 락 유실 -> vision-only 저신뢰 far jump (89m, prob=0.24) 최초 프레임
  raw_fallback = mk(dRel=89.0, vRel=0.0, radar=False, modelProb=0.24)
  r_u1 = sim_unpatched.update(raw_fallback, DT)
  r_p1 = sim_patched.update(raw_fallback, DT)

  jump_unpatched = abs(r_u1['dRel'] - 33.6)
  jump_patched = abs(r_p1['dRel'] - 33.6)

  print("=== A) 104차 실측 근사 재현 ===")
  print(f"  unpatched 첫 프레임 dRel = {r_u1['dRel']:.2f}m (즉시 89m 스냅 -> jump={jump_unpatched:.1f}m)")
  print(f"  patched   첫 프레임 dRel = {r_p1['dRel']:.2f}m (블렌딩 시작 -> jump={jump_patched:.1f}m)")

  ok = (jump_unpatched > 40.0) and (jump_patched < jump_unpatched * 0.5)
  print(f"  결과: {'PASS' if ok else 'FAIL'} (patched가 unpatched 대비 첫 프레임 점프 절반 미만)")

  # 저신뢰 상태가 지속되면(prob 계속 0.24) 몇 프레임 후 수렴하는지도 참고 기록
  r_p = r_p1
  for i in range(1, 10):
    raw_fallback = mk(dRel=89.0, vRel=0.0, radar=False, modelProb=0.24)
    r_p = sim_patched.update(raw_fallback, DT)
  print(f"  (참고) patched 10프레임(0.5s) 후 dRel = {r_p['dRel']:.2f}m -- "
        f"완전 차단이 아니라 시정수(0.35s)로 점진 수렴함을 확인용")
  return ok


def scenario_B_high_confidence_vision_regression():
  """B) 고신뢰 vision(modelProb=0.85) far jump -- 회귀 없음(즉시 스냅
  유지) 확인."""
  sim_unpatched = LeadBlendSim(patched=False)
  sim_patched = LeadBlendSim(patched=True)
  raw0 = mk(dRel=35.0, vRel=-0.2, radar=False, modelProb=0.85)
  sim_unpatched.update(raw0, DT)
  sim_patched.update(raw0, DT)

  raw1 = mk(dRel=70.0, vRel=0.0, radar=False, modelProb=0.85)  # 35m jump, 고신뢰
  r_u = sim_unpatched.update(raw1, DT)
  r_p = sim_patched.update(raw1, DT)

  ok = abs(r_u['dRel'] - r_p['dRel']) < 1e-6 and r_p['dRel'] == 70.0
  print("\n=== B) 고신뢰 vision far jump 회귀 검증 ===")
  print(f"  unpatched dRel={r_u['dRel']:.2f}m, patched dRel={r_p['dRel']:.2f}m")
  print(f"  결과: {'PASS' if ok else 'FAIL'} (동일하게 즉시 스냅되어야 함)")
  return ok


def scenario_C_radar_confirmed_regression():
  """C) 레이더 교차검증(radar=True) far jump -- modelProb 낮아도(0.1)
  radar=True면 회귀 없이 즉시 스냅되어야 함."""
  sim_unpatched = LeadBlendSim(patched=False)
  sim_patched = LeadBlendSim(patched=True)
  raw0 = mk(dRel=20.0, vRel=-0.3, radar=True, modelProb=0.1)
  sim_unpatched.update(raw0, DT)
  sim_patched.update(raw0, DT)

  raw1 = mk(dRel=50.0, vRel=0.0, radar=True, modelProb=0.1)  # 30m jump, radar=True
  r_u = sim_unpatched.update(raw1, DT)
  r_p = sim_patched.update(raw1, DT)

  ok = abs(r_u['dRel'] - r_p['dRel']) < 1e-6 and r_p['dRel'] == 50.0
  print("\n=== C) 레이더 교차검증 far jump 회귀 검증 ===")
  print(f"  unpatched dRel={r_u['dRel']:.2f}m, patched dRel={r_p['dRel']:.2f}m")
  print(f"  결과: {'PASS' if ok else 'FAIL'} (radar=True면 modelProb 낮아도 즉시 스냅)")
  return ok


def scenario_D_closer_jump_unaffected():
  """D) closer_jump(위험 방향, 예: SCC 근접구간 오래된 원거리값 -> 실제
  근접값) -- 저신뢰 vision이어도 danger-passthrough 그대로 즉시 반영,
  반응지연 생기면 안 됨."""
  sim_patched = LeadBlendSim(patched=True)
  raw0 = mk(dRel=60.0, vRel=-0.2, radar=True, modelProb=0.9)
  sim_patched.update(raw0, DT)

  raw1 = mk(dRel=40.0, vRel=-0.5, radar=False, modelProb=0.2)  # 20m 더 가까워짐, 저신뢰
  r_p = sim_patched.update(raw1, DT)

  ok = r_p['dRel'] == 40.0
  print("\n=== D) closer_jump(위험방향) 반응지연 없음 검증 ===")
  print(f"  patched dRel={r_p['dRel']:.2f}m (raw={raw1['dRel']}m)")
  print(f"  결과: {'PASS' if ok else 'FAIL'} (저신뢰여도 danger-passthrough로 즉시 반영)")
  return ok


def scenario_E_normal_tracking_no_regression():
  """E) 정상 추종 중(점프 없음, 완만한 접근) -- patched/unpatched 완전
  동일해야 함(diff=0)."""
  sim_unpatched = LeadBlendSim(patched=False)
  sim_patched = LeadBlendSim(patched=True)
  max_diff = 0.0
  dRel = 45.0
  for i in range(200):
    dRel -= 0.05  # 완만한 접근, jump 없음
    raw = mk(dRel=dRel, vRel=-1.0, radar=False, modelProb=0.55)
    r_u = sim_unpatched.update(raw, DT)
    r_p = sim_patched.update(raw, DT)
    max_diff = max(max_diff, abs(r_u['dRel'] - r_p['dRel']))

  ok = max_diff < 1e-9
  print("\n=== E) 정상 추종(점프 없음) 회귀 검증 ===")
  print(f"  200프레임(10s) 중 최대 diff = {max_diff:.2e}")
  print(f"  결과: {'PASS' if ok else 'FAIL'} (완전 동일해야 함)")
  return ok


if __name__ == '__main__':
  results = [
    scenario_A_104cha_reproduction(),
    scenario_B_high_confidence_vision_regression(),
    scenario_C_radar_confirmed_regression(),
    scenario_D_closer_jump_unaffected(),
    scenario_E_normal_tracking_no_regression(),
  ]
  print("\n=== 종합 ===")
  print(f"  {sum(results)}/{len(results)} PASS")
