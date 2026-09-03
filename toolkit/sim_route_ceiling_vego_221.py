#!/usr/bin/env python3
"""
221차 -- out_speed ceiling 기준항 vCruise(217차) -> vEgo(221차) 재교체 합성검증.

**실차로그 없음(§23, 대용량 CSV 미보관 정책 + 이번 세션에 재업로드도 안 됨)**.
사용자 설계문서("Route 감속 다음 설계 방향(2026-09 개정)") 1번이 직접 예시로 든
2개 시나리오 + 안전조건(2번) 재현을 위한 합성(synthetic) 시나리오만 수행한다.
실차 검증은 별도 과제로 이월(WIP.md 221차 미완료 항목 참고).

OLD (217차, 사용자 설계문서 구버전 2번 -- 150 고정 -> vCruise 기준):
    route_ceiling_kph = min(vCruise, 150.0) if vCruise > 0 else 150.0
NEW (221차, 이번 설계문서 1번 -- vCruise -> vEgo 기준):
    route_ceiling_kph = min(vEgo_kph, 150.0) if vEgo_kph > 0 else 150.0

out_speed = min(raw, max(vEgo_kph, sharpest_candidate_speed), ceiling)

raw/sharpest_candidate_speed는 apex_dist/apex_speed에 calculate_current_speed()를
적용한 값 -- 이 항 자체(196/179/207/214차 로직)는 221차가 건드리지 않으므로
OLD/NEW 양쪽에 동일 값을 넣어 ceiling 기준항 교체 효과만 분리한다.
"""
import math

ROUTE_MAX_SPEED_KPH = 150.0
AUTO_NAVI_SPEED_DECEL_RATE = 1.00  # [218차 디바이스 적용값] 0.70 -> 1.00 m/s²
AUTO_NAVI_SPEED_CTRL_END = 7.0     # 디바이스 현재값(참고용, 이번 검증은 apex_dist/apex_speed를 직접 지정하므로 이 값 자체는 raw 계산에만 영향)


def calculate_current_speed(left_dist, safe_speed_kph, safe_time, safe_decel_rate):
    safe_speed = safe_speed_kph / 3.6
    safe_dist = safe_speed * safe_time
    decel_dist = left_dist - safe_dist
    if decel_dist <= 0:
        return safe_speed_kph
    temp = safe_speed ** 2 + 2 * safe_decel_rate * decel_dist
    speed_mps = math.sqrt(temp) if temp >= 0 else safe_speed
    return max(safe_speed_kph, min(250, speed_mps * 3.6))


def ceiling_old_vcruise(v_ego_kph, v_cruise_kph, sharpest_candidate_speed):
    route_ceiling_kph = min(v_cruise_kph, ROUTE_MAX_SPEED_KPH) if v_cruise_kph > 0 else ROUTE_MAX_SPEED_KPH
    return max(v_ego_kph, sharpest_candidate_speed), route_ceiling_kph


def ceiling_new_vego(v_ego_kph, v_cruise_kph, sharpest_candidate_speed):
    route_ceiling_kph = min(v_ego_kph, ROUTE_MAX_SPEED_KPH) if v_ego_kph > 0 else ROUTE_MAX_SPEED_KPH
    return max(v_ego_kph, sharpest_candidate_speed), route_ceiling_kph


def run_scenario(name, apex_dist, apex_speed, v_ego_kph, v_cruise_kph, expect_note="", sharpest_candidate_speed=None):
    raw = calculate_current_speed(apex_dist, apex_speed, AUTO_NAVI_SPEED_CTRL_END, AUTO_NAVI_SPEED_DECEL_RATE)
    # candidates=[apex] 단일 후보가 기본(ceiling 기준항 교체 효과만 분리).
    # sharpest_candidate_speed를 명시하면 "vEgo보다는 빠르지만 vCruise보다는
    # 느린 먼 완만 후보가 하나 더 있는" 상황(mid항 = max(vEgo,sharpest)이
    # vEgo를 넘어서는 경우)을 재현할 수 있다 -- 이 경우에만 OLD/NEW ceiling
    # 기준항 차이가 실제로 out_speed에 반영된다(그렇지 않으면 mid항 자체가
    # 이미 vEgo로 눌러서 ceiling 차이가 가려짐, 시나리오2 참고).
    if sharpest_candidate_speed is None:
        sharpest_candidate_speed = apex_speed

    mid_old, ceil_old = ceiling_old_vcruise(v_ego_kph, v_cruise_kph, sharpest_candidate_speed)
    out_old = min(raw, mid_old, ceil_old)

    mid_new, ceil_new = ceiling_new_vego(v_ego_kph, v_cruise_kph, sharpest_candidate_speed)
    out_new = min(raw, mid_new, ceil_new)

    print(f"[{name}]")
    print(f"  입력: apex_dist={apex_dist}m apex_speed={apex_speed}kph vEgo={v_ego_kph}kph vCruise={v_cruise_kph}kph")
    print(f"  raw(물리계산, ceiling 이전)   = {raw:.2f} kph")
    print(f"  OLD(217차, vCruise ceiling)   = {out_old:.2f} kph  (ceiling={ceil_old:.2f})")
    print(f"  NEW(221차, vEgo ceiling)      = {out_new:.2f} kph  (ceiling={ceil_new:.2f})")
    print(f"  NEW <= vEgo ?                 = {out_new <= v_ego_kph + 1e-6}")
    if expect_note:
        print(f"  기대: {expect_note}")
    print()
    return out_old, out_new


def main():
    print("=" * 78)
    print("221차 vEgo ceiling A/B 합성검증 (실차 검증: 미실시)")
    print("=" * 78)
    print()

    # 시나리오 1 -- 사용자 설계문서 예시 1: vCruise=70, vEgo=70, 목표=40
    # (설정속도와 실제속도가 같은 정상 케이스 -- OLD/NEW가 같아야 함)
    o1, n1 = run_scenario(
        "시나리오1: vCruise=vEgo=70, 목표=40 (설계문서 예시1)",
        apex_dist=100.0, apex_speed=40.0, v_ego_kph=70.0, v_cruise_kph=70.0,
        expect_note="vCruise==vEgo이므로 OLD==NEW (회귀 없음 확인)",
    )
    assert abs(o1 - n1) < 1e-6, "시나리오1: vCruise==vEgo인데 OLD!=NEW -- 회귀"

    # 시나리오 2 -- 사용자 설계문서 예시 2 (핵심): vCruise=70, vEgo=50, 목표=40,
    # 그리고 lookahead 내에 "vEgo(50)보다는 빠르지만 vCruise(70)보다는 느린"
    # 먼 완만한 후보(65kph)가 하나 더 있는 경우(600m 확장 이후 흔해질 구성 --
    # 위 2번 lookahead 변경과 직결). mid항(max(vEgo,sharpest)=65)이 vEgo(50)를
    # 넘어서므로, 이 경우에만 ceiling 기준항(OLD=vCruise vs NEW=vEgo) 차이가
    # 실제로 out_speed에 반영된다 -- OLD는 65(=mid, ceiling=70이 안 걸림)까지
    # 허용해 "vEgo=50인데 65로 가속하라"는 신호가 되지만, NEW는 ceiling=50이
    # mid(65)보다 낮아 반드시 50으로 눌린다.
    o2, n2 = run_scenario(
        "시나리오2: vCruise=70, vEgo=50, 완만후보=65, 목표=40 (설계문서 예시2, 핵심)",
        apex_dist=250.0, apex_speed=40.0, v_ego_kph=50.0, v_cruise_kph=70.0,
        sharpest_candidate_speed=65.0,
        expect_note="OLD는 65까지 허용(vEgo=50보다 빠르게 가라는 신호, 위반) / NEW는 50으로 눌림(안전조건 성립)",
    )
    assert n2 <= 50.0 + 1e-6, f"시나리오2: NEW={n2}가 vEgo(50)를 초과함 -- 안전조건 위반"
    assert o2 > 50.0 + 1e-6, "시나리오2: OLD가 예상대로 vEgo를 넘지 않음 -- 시나리오 재설계 필요(대비 효과 없음)"

    # 시나리오 2b -- 단일 후보만 있는 단순 케이스(sharpest_candidate_speed
    # 별도 지정 없음)는 mid항(max(vEgo,apex_speed)=vEgo)이 이미 ceiling과
    # 무관하게 out_speed를 vEgo 근방으로 누르므로 OLD==NEW로 수렴한다는 것을
    # 확인하는 대조군(회귀 아님, ceiling 차이가 "항상" 드러나는 게 아니라
    # "mid항이 vEgo를 넘어서는 경우"에만 드러난다는 걸 명시적으로 기록).
    o2b, n2b = run_scenario(
        "시나리오2b: vCruise=70, vEgo=50, 단일 후보(=목표40) -- ceiling 차이 안 드러나는 대조군",
        apex_dist=250.0, apex_speed=40.0, v_ego_kph=50.0, v_cruise_kph=70.0,
        expect_note="mid항=max(vEgo,40)=vEgo(50)이 이미 지배 -> OLD==NEW==50 (ceiling 차이 무관, 정상)",
    )
    assert abs(o2b - n2b) < 1e-6

    # 시나리오 3 -- 안전조건: vEgo가 이미 목표보다 낮음(목표=40인데 vEgo=30) ->
    # route가 오히려 속도를 올리라고 요구하면 안 됨(무개입 == vEgo 그대로 출력)
    o3, n3 = run_scenario(
        "시나리오3: vEgo(30) < apex_speed(40) -- route 무개입 조건",
        apex_dist=250.0, apex_speed=40.0, v_ego_kph=30.0, v_cruise_kph=70.0,
        expect_note="NEW == vEgo(30) (route가 40으로 가속하라고 요구하지 않음)",
    )
    assert abs(n3 - 30.0) < 1e-6, f"시나리오3: NEW={n3} != vEgo(30) -- route가 가속을 요구함(안전조건 위반)"

    # 시나리오 4 -- 대조군: apex가 없는(직선) 상태와 동등한 큰 apex_speed,
    # vCruise가 매우 낮고 vEgo가 그보다 높은 비정상 조합(예: 크루즈 감속 중
    # 관성으로 vEgo가 아직 안 내려온 경우) -- ROUTE_MAX_SPEED_KPH(150) 폴백
    # 경계와 vEgo<=0 폴백 분기도 함께 확인.
    o4, n4 = run_scenario(
        "시나리오4: vEgo=0(정지/센서이상 폴백) 대조군",
        apex_dist=250.0, apex_speed=40.0, v_ego_kph=0.0, v_cruise_kph=70.0,
        expect_note="vEgo<=0 폴백 -> ceiling=150 그대로 (기존 150 고정과 동일)",
    )

    print("-" * 78)
    print("요약 (raw는 두 브랜치 공통이므로 생략, OLD/NEW만 비교)")
    print(f"{'시나리오':40s} {'OLD':>10s} {'NEW':>10s}")
    print(f"{'1(vCruise==vEgo)':40s} {o1:10.2f} {n1:10.2f}")
    print(f"{'2(완만후보65, 핵심 -- OLD/NEW 분기)':40s} {o2:10.2f} {n2:10.2f}")
    print(f"{'2b(단일후보, 대조군 -- 분기 없음)':40s} {o2b:10.2f} {n2b:10.2f}")
    print(f"{'3(vEgo<목표, 무개입)':40s} {o3:10.2f} {n3:10.2f}")
    print(f"{'4(vEgo=0 폴백)':40s} {o4:10.2f} {n4:10.2f}")
    print()
    print("ALL SCENARIOS PASS (assert 전부 통과, 합성검증 한정)")


if __name__ == "__main__":
    main()
