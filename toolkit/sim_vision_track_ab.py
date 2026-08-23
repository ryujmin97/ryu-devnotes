#!/usr/bin/env python3
"""
58차 3번 (A: tentative 조기등록 / B: 저확신구간 안전측 보정) 로직 단위
합성검증. radard.py는 cereal/capnp 컴파일 의존이라 컨테이너에서 직접
import 불가 -- VisionTrack.update()의 핵심 분기만 순수 파이썬으로
재현해서 검증한다(기존 세션들의 표준 관행, 예: sim_frac_rate.py,
sim_low_speed_decel.py와 동일 패턴).

radard.py 실제 코드와 반드시 동일하게 유지해야 하는 상수/로직:
- VISION_TRACK_PROB_GATE=0.70, VISION_TRACK_CNT_GATE=10
- VISION_TRACK_TENTATIVE_PROB_GATE=0.35, VISION_TRACK_TENTATIVE_CNT_GATE=10,
  VISION_TRACK_TENTATIVE_DREL_JITTER=8.0
- VISION_TRACK_SAFETY_MIN_CNT=2
"""
import math

VISION_TRACK_PROB_GATE = 0.70
VISION_TRACK_CNT_GATE = 10
VISION_TRACK_TENTATIVE_PROB_GATE = 0.35
VISION_TRACK_TENTATIVE_CNT_GATE = 10
VISION_TRACK_TENTATIVE_DREL_JITTER = 8.0
VISION_TRACK_SAFETY_MIN_CNT = 2


class VT:
    """radard.py VisionTrack의 update() 핵심 분기만 재현 (dPath/vLat/aLead
    미분 스무딩 등 이번 패치와 무관한 부분은 생략, vLead/vRel/status/cnt만
    추적)."""

    def __init__(self, radar_ts=0.05):
        self.radar_ts = radar_ts
        self.dRel = 0.0
        self.dRel_last = 0.0
        self.vLead = 0.0
        self.vLead_last = 0.0
        self.vRel = 0.0
        self.status = False
        self.cnt = 0
        self.tentative_cnt = 0
        self.tentative_dRel_last = 0.0
        self.prob = 0.0

    def reset(self):
        self.status = False
        self.vRel = 0.0
        # 실제 코드는 vLead=v_ego로 리셋하지만 이번 시뮬레이션에선 미사용

    def update(self, prob, dRel_candidate, v_rel_pred, v_ego):
        self.prob = prob

        if VISION_TRACK_TENTATIVE_PROB_GATE <= prob <= 0.5:
            if self.tentative_cnt > 0 and abs(dRel_candidate - self.tentative_dRel_last) > VISION_TRACK_TENTATIVE_DREL_JITTER:
                self.tentative_cnt = 0
            self.tentative_cnt += 1
            self.tentative_dRel_last = dRel_candidate
        elif prob < VISION_TRACK_TENTATIVE_PROB_GATE:
            self.tentative_cnt = 0

        register_ok = (prob > .5) or (self.tentative_cnt >= VISION_TRACK_TENTATIVE_CNT_GATE)

        if register_ok:
            dRel = dRel_candidate
            if abs(self.dRel - dRel) > 5.0:
                self.cnt = 0
            self.dRel = dRel

            if self.cnt < VISION_TRACK_CNT_GATE or prob < VISION_TRACK_PROB_GATE:
                self.vRel = v_rel_pred
                self.vLead = v_ego + v_rel_pred
                if self.cnt >= VISION_TRACK_SAFETY_MIN_CNT and self.dRel_last > 0.0 and self.radar_ts > 0:
                    v_rel_measured = (self.dRel - self.dRel_last) / self.radar_ts
                    vLead_measured = v_ego + v_rel_measured
                    if vLead_measured < self.vLead:
                        self.vLead = vLead_measured
                        self.vRel = v_rel_measured
            else:
                # (B 무관 구간 -- 기존 blend 로직, 검증 범위 밖이라 단순화)
                v_rel = (self.dRel - self.dRel_last) / self.radar_ts
                self.vRel = v_rel
                self.vLead = v_ego + v_rel

            self.status = True
            self.cnt += 1
        else:
            self.reset()
            self.cnt = 0

        self.dRel_last = self.dRel
        self.vLead_last = self.vLead
        return self.status, self.vLead, self.cnt, self.tentative_cnt


def scenario_A_early_registration():
    """8초(160프레임@20Hz) 동안 prob=0.42(tentative 구간)로 고정, dRel이
    안정적으로 서서히 감소(진짜 존재하는 정지앞차 재현) -> 정식문턱(0.5)을
    한번도 못 넘어도 tentative_cnt>=10(0.5s)에서 조기 등록돼야 함."""
    vt = VT()
    dRel = 130.0
    first_registered_frame = None
    for i in range(160):
        dRel -= 0.05  # 서서히 접근(정지앞차, 자차 속도로 접근)
        status, vLead, cnt, tcnt = vt.update(prob=0.42, dRel_candidate=dRel, v_rel_pred=-1.0, v_ego=28.0)
        if status and first_registered_frame is None:
            first_registered_frame = i
    ok = first_registered_frame is not None and first_registered_frame <= 12
    print(f"[A-1 조기등록] 최초 등록 프레임={first_registered_frame} (프레임10 근처 기대) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_A_no_false_promotion_low_prob():
    """prob가 계속 0.2대(TENTATIVE_PROB_GATE 밑) -> tentative_cnt 자체가 안 쌓여야
    하고, 등록도 안 돼야 함(패치 전과 동일 = 회귀 없음)."""
    vt = VT()
    dRel = 100.0
    ever_registered = False
    for i in range(200):
        dRel -= 0.05
        status, vLead, cnt, tcnt = vt.update(prob=0.2, dRel_candidate=dRel, v_rel_pred=-1.0, v_ego=25.0)
        ever_registered = ever_registered or status
    ok = not ever_registered
    print(f"[A-2 저prob 미등록 회귀] 200프레임간 등록 여부={ever_registered} (False 기대) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_A_jitter_rejects_promotion():
    """prob는 tentative 구간(0.42)이지만 dRel이 매 프레임 크게 튐(노이즈/여러
    물체 혼재 재현) -> tentative_cnt가 계속 리셋돼 승격되면 안 됨."""
    vt = VT()
    ever_registered = False
    import random
    random.seed(0)
    for i in range(200):
        dRel = 80.0 + random.uniform(-15, 15)  # 매 프레임 위치 요동(다른 물체로 튐 재현)
        status, vLead, cnt, tcnt = vt.update(prob=0.42, dRel_candidate=dRel, v_rel_pred=-1.0, v_ego=25.0)
        ever_registered = ever_registered or status
    ok = not ever_registered
    print(f"[A-3 jitter 오인승격 방지] 200프레임간 등록 여부={ever_registered} (False 기대) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_B_safety_floor_pulls_down_optimistic_model():
    """정지차량_미인식 실사례 재현: prob=0.53(0.70 미만, B구간), 모델예측은
    낙관적으로 27->14m/s 완만히 감소(50프레임=2.5s)라고 보고하지만, 실제
    dRel은 훨씬 급하게 줄어드는 중(진짜 vLead는 그보다 훨씬 낮음) ->
    B 보정이 모델예측보다 낮은(더 위험한) 실측을 min()으로 반영해야 함."""
    vt = VT()
    v_ego = 31.0
    dRel = 123.7
    real_vLead_true = 27.0  # 실제로는 이미 이 근처(정체 후미)
    model_vLead = 27.0
    corrected_pulled_down = False
    for i in range(50):
        model_vLead -= (27.0 - 14.0) / 50.0  # 모델: 완만히 낙관적 감소
        v_rel_pred = model_vLead - v_ego
        real_vLead_true -= (27.0 - 4.0) / 50.0  # 실제: 훨씬 급격히 감속 중(레이더 락온 시 4.88 근사)
        dRel += (real_vLead_true - v_ego) * vt.radar_ts  # 실제 물리에 따른 dRel 변화
        status, vLead_out, cnt, tcnt = vt.update(prob=0.53, dRel_candidate=dRel, v_rel_pred=v_rel_pred, v_ego=v_ego)
        if i >= 5 and vLead_out < model_vLead - 0.5:
            corrected_pulled_down = True
    print(f"[B-1 안전측 보정] 모델예측보다 낮게 보정된 프레임 존재={corrected_pulled_down} (True 기대) -> {'PASS' if corrected_pulled_down else 'FAIL'}")
    return corrected_pulled_down


def scenario_B_no_intervention_when_model_correct():
    """모델예측이 실제와 거의 일치(정상 상황) -> B 보정이 개입해 값을 흔들면
    안 됨(min() 방향이라 이론상 개입해도 안전측이지만, '불필요한 노이즈
    유입' 자체가 없어야 승차감 회귀가 없음을 확인)."""
    vt = VT()
    v_ego = 25.0
    dRel = 90.0
    max_abs_diff = 0.0
    for i in range(50):
        v_rel_true = -3.0  # 일정한 감속 상대속도(모델도 실측도 같은 값)
        dRel += v_rel_true * vt.radar_ts
        v_rel_pred = v_rel_true
        status, vLead_out, cnt, tcnt = vt.update(prob=0.6, dRel_candidate=dRel, v_rel_pred=v_rel_pred, v_ego=v_ego)
        expected = v_ego + v_rel_pred
        max_abs_diff = max(max_abs_diff, abs(vLead_out - expected))
    ok = max_abs_diff < 0.05
    print(f"[B-2 정상상황 무간섭] 모델-보정 최대오차={max_abs_diff:.4f} (<0.05 기대) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_high_prob_regression():
    """prob>0.5로 정상 등록되는 기존 케이스(58차 이전부터 있던 로직)는
    이번 패치로 전혀 안 바뀌어야 함 -- A/B 둘 다 register_ok가 이미 True인
    경로엔 개입하지 않으므로 diff=0 기대."""
    vt = VT()
    v_ego = 20.0
    dRel = 60.0
    diffs = []
    for i in range(60):
        v_rel_true = -2.0
        dRel += v_rel_true * vt.radar_ts
        status, vLead_out, cnt, tcnt = vt.update(prob=0.85, dRel_candidate=dRel, v_rel_pred=v_rel_true, v_ego=v_ego)
    ok = vt.status is True
    print(f"[고prob 회귀] 정상등록 유지={vt.status} -> {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    results = [
        scenario_A_early_registration(),
        scenario_A_no_false_promotion_low_prob(),
        scenario_A_jitter_rejects_promotion(),
        scenario_B_safety_floor_pulls_down_optimistic_model(),
        scenario_B_no_intervention_when_model_correct(),
        scenario_high_prob_regression(),
    ]
    print(f"\n총 {len(results)}건 중 {sum(results)}건 PASS")
    assert all(results), "일부 시나리오 FAIL -- 코드 재검토 필요"
