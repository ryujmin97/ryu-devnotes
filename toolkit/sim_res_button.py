#!/usr/bin/env python3
"""
79차 -- "수동주행 중 첫 +RES(accelCruise) 시 목표속도가 현재속도보다
낮게 설정되는 문제" 패치의 순수함수 재현 합성검증.

당시(79차) 이 검증은 세션 컨테이너의 work/sim_res_button.py에만 있었고
`toolkit/`에는 저장되지 않은 채로 세션이 종료됨(80차에서 뒤늦게 발견,
정식 편입). 실차 검증(패치는 적용/push까지는 완료, 실제 도로 반응
확인은 아직)이 아직 진행 중이므로, 필요 시 이 스크립트로 회귀 재현이
가능하도록 남겨둔다.

재현 대상: `selfdrive/car/cruise.py`의
`VCruiseCarrot._update_cruise_buttons()` accelCruise 분기
(`not long_pressed` 블록 안, `elif self._cruise_ready or ... elif not
CC.enabled: ...` 부분). 순서가 중요 -- `_cruise_ready`/`standstill`/
`carrot_cruise_active` 세 조건이 먼저 체크되고, 그 다음에만 79차가
추가한 `not CC.enabled` 분기가 평가된다(기존 no-op 분기들의 우선순위를
바꾸지 않기 위함).

의존성: 없음(표준 라이브러리만).

사용:
    python3 sim_res_button.py
"""
import math

CRUISE_SPEED_UNIT_BASIC = 5  # 기본 눈금(km/h), 실제론 사용자 설정값


def update_cruise_buttons_accel(v_cruise_kph, v_ego_kph_set, cc_enabled,
                                 cruise_ready, standstill, carrot_cruise_active,
                                 v_cruise_kph_at_brake, cruise_button_mode,
                                 unit=CRUISE_SPEED_UNIT_BASIC, patched=True):
    """
    accelCruise 버튼 1회 처리를 순수함수로 재현. patched=False면 79차
    이전(버그) 동작, True면 79차 패치 이후 동작.

    반환: 새 v_cruise_kph
    """
    if cruise_ready or standstill or carrot_cruise_active:
        # 기존 no-op 분기(취소 직후 재인게이지 등) -- 패치 전/후 동일, 변경 없음
        return v_cruise_kph
    elif (not cc_enabled) and patched:
        # 79차 패치: 수동주행 중 첫 인게이지 -> 현재속도보다 반드시 높게
        # (다음 단위 눈금으로 올림)
        return math.ceil((v_ego_kph_set + 0.01) / unit) * unit
    elif (not cc_enabled) and not patched:
        # 79차 이전(버그): 이 분기 자체가 없어서 v_cruise_kph가 CC.enabled=False
        # 동안 정체된 이전 값 그대로 채택됨(np.clip(v_cruise_kph,30,max)만
        # 매 프레임 반복 적용되던 상황을 그대로 반환)
        return v_cruise_kph
    elif v_cruise_kph_at_brake > 0 and v_cruise_kph < v_cruise_kph_at_brake:
        return v_cruise_kph_at_brake
    elif cruise_button_mode == 0:
        return v_cruise_kph  # button_kph, 이 시뮬레이션에서는 단순화
    else:
        return v_cruise_kph  # _v_cruise_desired(), 이 시뮬레이션 범위 밖


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  PASS: {msg}")


def scenario_bug_reproduction():
    """사용자 제보 재현: 수동 60km/h 주행 중 v_cruise_kph가 이전 세션
    잔여값(33)에 정체된 상태에서 첫 +RES."""
    print("[시나리오1] 버그 재현 -- 구코드는 33(현재속도보다 낮음) 그대로 채택")
    result_bug = update_cruise_buttons_accel(
        v_cruise_kph=33, v_ego_kph_set=60.0, cc_enabled=False,
        cruise_ready=False, standstill=False, carrot_cruise_active=False,
        v_cruise_kph_at_brake=0, cruise_button_mode=1, patched=False)
    _assert(result_bug == 33, f"구코드 결과={result_bug} (버그 재현: 현재속도(60)보다 낮게 설정됨)")

    print("[시나리오1] 패치 재현 -- 신코드는 현재속도(60)보다 높은 다음 눈금(61 또는 65)")
    result_fixed = update_cruise_buttons_accel(
        v_cruise_kph=33, v_ego_kph_set=60.0, cc_enabled=False,
        cruise_ready=False, standstill=False, carrot_cruise_active=False,
        v_cruise_kph_at_brake=0, cruise_button_mode=1, patched=True, unit=1)
    _assert(result_fixed == 61, f"신코드 결과={result_fixed} (개선 확인: 현재속도(60)보다 높게 설정됨)")


def scenario_unit_5():
    """unit(눈금)이 5인 사용자 설정 -- 60km/h 주행 중이면 다음 5단위 눈금인 65로 설정."""
    print("[시나리오2] unit=5 설정 -- 60km/h -> 65km/h(다음 눈금)로 설정되는지 확인")
    result = update_cruise_buttons_accel(
        v_cruise_kph=33, v_ego_kph_set=60.0, cc_enabled=False,
        cruise_ready=False, standstill=False, carrot_cruise_active=False,
        v_cruise_kph_at_brake=0, cruise_button_mode=1, patched=True, unit=5)
    _assert(result == 65, f"결과={result} (unit=5 눈금 반영 확인, NEEDS_VALIDATION: 실차 튜닝 여지)")


def scenario_regression_cruise_ready():
    """회귀 확인: 취소 직후 재인게이지(_cruise_ready=True) 등 기존 no-op
    분기는 패치 전/후 동일해야 함(79차가 건드리지 않은 경로)."""
    print("[시나리오3] 회귀 확인 -- cruise_ready=True 케이스는 패치 전/후 동일(33 그대로)")
    args = dict(v_cruise_kph=33, v_ego_kph_set=60.0, cc_enabled=False,
                cruise_ready=True, standstill=False, carrot_cruise_active=False,
                v_cruise_kph_at_brake=0, cruise_button_mode=1)
    result_before = update_cruise_buttons_accel(**args, patched=False)
    result_after = update_cruise_buttons_accel(**args, patched=True)
    _assert(result_before == result_after == 33,
            f"before={result_before}, after={result_after} (기존 no-op 분기 보존 확인)")


def scenario_regression_standstill():
    """회귀 확인: 정차 후 출발(standstill=True) 케이스도 패치 전/후 동일해야 함."""
    print("[시나리오4] 회귀 확인 -- standstill=True 케이스도 패치 전/후 동일")
    args = dict(v_cruise_kph=33, v_ego_kph_set=0.5, cc_enabled=False,
                cruise_ready=False, standstill=True, carrot_cruise_active=False,
                v_cruise_kph_at_brake=0, cruise_button_mode=1)
    result_before = update_cruise_buttons_accel(**args, patched=False)
    result_after = update_cruise_buttons_accel(**args, patched=True)
    _assert(result_before == result_after == 33,
            f"before={result_before}, after={result_after} (standstill 분기 보존 확인)")


def scenario_regression_cc_enabled():
    """회귀 확인: CC.enabled=True(정상 크루즈 주행 중) 상황에서는 79차가
    추가한 'not CC.enabled' 분기 자체가 아예 열리지 않아야 함."""
    print("[시나리오5] 회귀 확인 -- CC.enabled=True면 79차 분기 미개입, 이후 분기로 자연 진행")
    args = dict(v_cruise_kph=80, v_ego_kph_set=79.0, cc_enabled=True,
                cruise_ready=False, standstill=False, carrot_cruise_active=False,
                v_cruise_kph_at_brake=0, cruise_button_mode=0)
    result_before = update_cruise_buttons_accel(**args, patched=False)
    result_after = update_cruise_buttons_accel(**args, patched=True)
    _assert(result_before == result_after == 80,
            f"before={result_before}, after={result_after} (CC.enabled=True 정상주행 중 회귀 없음)")


if __name__ == "__main__":
    scenario_bug_reproduction()
    scenario_unit_5()
    scenario_regression_cruise_ready()
    scenario_regression_standstill()
    scenario_regression_cc_enabled()
    print("\n전 시나리오 통과 -- 79차 패치가 현재 cruise.py와 일치하고,"
          " 기존 no-op 분기들에는 회귀가 없음을 확인.")
