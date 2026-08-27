#!/usr/bin/env python3
"""
58차 1번("카메라 인식 감속이 레이더 대비 약함 -> 레이더 인식 수준으로
강화") 로직 단위 합성검증.

이 패치는 두 파일에 걸쳐 있음:
1. radard.py VisionTrack.update() -- 실측 dRel미분(v_rel) 경로로
   전환하는 게이트를 VISION_TRACK_PROB_GATE(0.97->0.70)/
   VISION_TRACK_CNT_GATE(20->10)로 완화 (커밋 1f0d292).
2. long_mpc.py process_lead() -- vision-only lead에서 long_mpc가
   이미 계산해 오던 _vision_dRel_rate(실측 dRel미분)를 v_lead 자체에
   min() 안전클램프로 직접 반영 (커밋 e17e078).

58차 1번 세션 당시엔 work/test_visiontrack_gate.py(스크래치)로만
검증했고 toolkit에 편입되지 않아 컨테이너 리셋으로 소실됐음 -- 이번에
정식으로 toolkit에 편입해 재현 가능하게 만든다.

radard.py/long_mpc.py는 cereal/capnp 컴파일 의존이라 컨테이너에서
직접 import 불가 -- 핵심 분기만 순수 파이썬으로 재현해서 검증한다
(기존 세션들의 표준 관행, sim_vision_track_ab.py/sim_low_speed_decel.py
와 동일 패턴). 이번 패치 이전(구게이트/구로직)과 이후(신게이트/신로직)를
같은 시나리오로 나란히 돌려 "실제로 개선됐는지"를 직접 비교하는 것이
이 스크립트의 핵심 목적(sim_vision_track_ab.py는 A/B 각각의 신로직만
검증했을 뿐 58차1번의 before/after 비교는 다루지 않았음).

radard.py 실제 코드와 반드시 동일하게 유지해야 하는 상수:
- VISION_TRACK_PROB_GATE = 0.70 (구 0.97)
- VISION_TRACK_CNT_GATE  = 10   (구 20)
long_mpc.py:
- VISION_CLOSING_RATE_MIN_TIME = 0.5 (s)
"""
import math

# ---- 1) radard.py VisionTrack.update() 게이트 부분만 재현 ----
# (dPath/vLat/aLead 스무딩 등 이번 패치와 무관한 부분은 생략, cnt<GATE
# 또는 prob<GATE일 때 "모델예측만 쓰는지 vs 실측 dRel미분 blend로 넘어가는지"
# 분기만 재현)

NEW_PROB_GATE = 0.70
NEW_CNT_GATE = 10
OLD_PROB_GATE = 0.97
OLD_CNT_GATE = 20


def vision_track_branch(cnt, prob, prob_gate, cnt_gate):
    """True면 아직 모델예측(lead_v_rel_pred)만 쓰는 구간, False면 실측
    dRel미분 blend 구간으로 전환됨 (radard.py L501의 조건과 동일)."""
    return cnt < cnt_gate or prob < prob_gate


def first_blend_frame(prob, prob_gate, cnt_gate, max_frames=200):
    """매 프레임 cnt가 1씩 증가한다고 가정하고(register_ok가 계속 True인
    안정 추적 상황), 몇 프레임째에 blend 구간(실측 dRel미분 사용)으로
    전환되는지 반환. 전환이 아예 안 되면 None."""
    for cnt in range(max_frames):
        if not vision_track_branch(cnt, prob, prob_gate, cnt_gate):
            return cnt
    return None


def scenario_gate_relaxation_typical_prob():
    """56/57차 qcamera 대조로 확인된 실제 원거리 vision lead의 흔한 prob
    분포(0.70~0.85대)를 재현. 구게이트(0.97)는 이 prob 범위에선 cnt가
    아무리 쌓여도 절대 blend로 못 넘어가야 하고(=모델예측에 영원히
    갇힘, 58차1번이 지적한 근본원인), 신게이트(0.70)는 cnt=10(0.5s)
    근처에서 넘어가야 한다."""
    results = []
    for prob in (0.75, 0.80, 0.85):
        old_frame = first_blend_frame(prob, OLD_PROB_GATE, OLD_CNT_GATE)
        new_frame = first_blend_frame(prob, NEW_PROB_GATE, NEW_CNT_GATE)
        ok = (old_frame is None) and (new_frame == NEW_CNT_GATE)
        print(f"[게이트완화 prob={prob}] 구게이트 전환프레임={old_frame}(None 기대) / "
              f"신게이트 전환프레임={new_frame}({NEW_CNT_GATE} 기대) -> {'PASS' if ok else 'FAIL'}")
        results.append(ok)
    return all(results)


def scenario_gate_relaxation_high_prob_regression():
    """prob=0.98(구게이트 0.97도 넘는 고확신 케이스)는 구게이트에서도
    cnt=20(1.0s)에 전환됐어야 함 -- 신게이트에서는 cnt=10(0.5s)로 더
    빨라짐(둘 다 전환은 되지만 신게이트가 더 이름). 회귀(다르게 동작해선
    안 되는 부분)는 없고 오직 '더 빠른 전환'만 확인."""
    old_frame = first_blend_frame(0.98, OLD_PROB_GATE, OLD_CNT_GATE)
    new_frame = first_blend_frame(0.98, NEW_PROB_GATE, NEW_CNT_GATE)
    ok = (old_frame == OLD_CNT_GATE) and (new_frame == NEW_CNT_GATE) and (new_frame < old_frame)
    print(f"[고prob 회귀] 구게이트 전환프레임={old_frame}({OLD_CNT_GATE} 기대) / "
          f"신게이트 전환프레임={new_frame}({NEW_CNT_GATE} 기대, 더 빨라야 함) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_gate_relaxation_too_low_prob_no_change():
    """prob=0.5(신게이트 0.70도 못 넘는 저확신) -- 구게이트/신게이트 둘 다
    영원히 모델예측 구간에 머물러야 함(신게이트라고 무조건 다 풀리는 게
    아니라는 회귀 확인, 안전측 유지)."""
    old_frame = first_blend_frame(0.5, OLD_PROB_GATE, OLD_CNT_GATE)
    new_frame = first_blend_frame(0.5, NEW_PROB_GATE, NEW_CNT_GATE)
    ok = (old_frame is None) and (new_frame is None)
    print(f"[저prob 무변화] 구게이트={old_frame}(None 기대) / 신게이트={new_frame}(None 기대) -> {'PASS' if ok else 'FAIL'}")
    return ok


# ---- 2) long_mpc.py process_lead()의 v_lead 직접보정 부분만 재현 ----
# (launch bypass/dist_w/ttc_w 등 이번 패치와 무관한 부분은 생략,
# "vision_dRel_rate가 v_lead를 min()으로 안전측 보정하는지"만 재현)

VISION_CLOSING_RATE_MIN_TIME = 0.5


def apply_vision_v_lead_correction(lead_radar, lead_vLead, vision_dRel_rate, v_ego, lead_acq_timer):
    """long_mpc.py process_lead() L618-621 재현. vision_dRel_rate는
    process_lead 호출 전 이미 `_lead_acq_timer >= VISION_CLOSING_RATE_MIN_TIME`
    조건으로 None/값이 걸러져서 들어오므로(L798), 이 함수는 그 상위 게이트도
    함께 재현해 별도로 넘어온 raw 값에 대해서도 방어적으로 검증한다."""
    v_lead = lead_vLead
    effective_rate = vision_dRel_rate if lead_acq_timer >= VISION_CLOSING_RATE_MIN_TIME else None
    if (not lead_radar) and effective_rate is not None:
        measured_v_lead = v_ego + effective_rate
        if measured_v_lead < v_lead:
            v_lead = measured_v_lead
    return v_lead


def scenario_v_lead_pulled_down_when_model_optimistic():
    """58차1번 원 검증 수치 재현: 모델예측 v_lead=24.0m/s(낙관적)이지만
    실측 dRel미분 기반 vision_dRel_rate가 훨씬 급한 접근(v_ego=25.0,
    rate=-6.0 -> measured_v_lead=19.0)을 가리킬 때, v_lead가 24.0->19.0
    으로 안전측 보정돼야 함."""
    v_lead = apply_vision_v_lead_correction(
        lead_radar=False, lead_vLead=24.0, vision_dRel_rate=-6.0,
        v_ego=25.0, lead_acq_timer=1.2,
    )
    ok = abs(v_lead - 19.0) < 1e-6
    print(f"[v_lead 안전측 보정] 24.0->{v_lead} (19.0 기대) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_v_lead_no_weakening_when_model_pessimistic():
    """vision_dRel_rate가 모델예측보다 '덜 위험'(measured_v_lead가 더 큼)
    하게 나오는 경우 -- min() 방향이라 절대 반영되면 안 됨(완화 방향
    없음 원칙, 58차1번/58차3번 B와 동일한 안전 설계)."""
    v_lead = apply_vision_v_lead_correction(
        lead_radar=False, lead_vLead=15.0, vision_dRel_rate=2.0,
        v_ego=25.0, lead_acq_timer=1.2,
    )  # measured_v_lead = 25.0+2.0 = 27.0 > 15.0 -> 개입 안 함
    ok = abs(v_lead - 15.0) < 1e-6
    print(f"[완화방향 없음] 15.0->{v_lead} (15.0 유지 기대, min()이 더 큰 값 무시) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_v_lead_radar_lead_untouched():
    """레이더 락온 리드(lead.radar=True)는 vision_dRel_rate와 무관하게
    v_lead가 절대 바뀌면 안 됨(이 패치는 vision-only 상황 전용, radard.py
    가 이미 레이더 실측을 쓰는 리드에 개입하는 건 범위 밖 -- 회귀 방지
    핵심 확인)."""
    v_lead = apply_vision_v_lead_correction(
        lead_radar=True, lead_vLead=24.0, vision_dRel_rate=-6.0,
        v_ego=25.0, lead_acq_timer=1.2,
    )
    ok = abs(v_lead - 24.0) < 1e-6
    print(f"[레이더 리드 무간섭] 24.0->{v_lead} (24.0 유지 기대) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_v_lead_min_time_gate():
    """추적 시작 직후(lead_acq_timer < VISION_CLOSING_RATE_MIN_TIME=0.5s)엔
    vision_dRel_rate가 아직 신뢰 안 된 상태 -- 값이 넘어와도(방어적 케이스)
    적용되면 안 됨(신규 트랙 초반 노이즈 유입 방지)."""
    v_lead = apply_vision_v_lead_correction(
        lead_radar=False, lead_vLead=24.0, vision_dRel_rate=-6.0,
        v_ego=25.0, lead_acq_timer=0.2,
    )
    ok = abs(v_lead - 24.0) < 1e-6
    print(f"[MIN_TIME 게이트] 24.0->{v_lead} (24.0 유지 기대, 추적시간 부족) -> {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_v_lead_stopped_lead_case():
    """'정지차량_미인식' 계열 실사례 근사: v_ego=31.0, 모델기반 lead.vLead가
    아직 27.0(낙관적, 정체 후미를 놓침) 근처인데 vision_dRel_rate 실측은
    이미 -25.0m/s급 급접근(레이더 락온 직전 vLead 4.88 근사, FINDINGS.md
    58차3번 케이스 수치)을 가리키는 극단 상황도 정상적으로 크게
    끌어내려야 함(안전측 클램프에 상한이 없어야 함)."""
    v_lead = apply_vision_v_lead_correction(
        lead_radar=False, lead_vLead=27.0, vision_dRel_rate=-25.0,
        v_ego=31.0, lead_acq_timer=2.0,
    )  # measured_v_lead = 31.0-25.0 = 6.0
    ok = abs(v_lead - 6.0) < 1e-6
    print(f"[극단 실사례 근사] 27.0->{v_lead} (6.0 기대) -> {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    results = [
        scenario_gate_relaxation_typical_prob(),
        scenario_gate_relaxation_high_prob_regression(),
        scenario_gate_relaxation_too_low_prob_no_change(),
        scenario_v_lead_pulled_down_when_model_optimistic(),
        scenario_v_lead_no_weakening_when_model_pessimistic(),
        scenario_v_lead_radar_lead_untouched(),
        scenario_v_lead_min_time_gate(),
        scenario_v_lead_stopped_lead_case(),
    ]
    print(f"\n총 {len(results)}건 중 {sum(results)}건 PASS")
    assert all(results), "일부 시나리오 FAIL -- 코드 재검토 필요"
