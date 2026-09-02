#!/usr/bin/env python3
"""
207차 -- 205차/206차가 다룬 "route out_speed 상한(ceiling)" 항을,
apex_speed(candidates[0], 가장 가까운 후보) 대신
sharpest_candidate_speed(= candidates 전체 중 가장 급한 후보의 speed,
candidates가 비어있으면 apex_speed로 폴백)로 교체하는 설계를
carrot_man.py에 실제로 반영하기 전에 시나리오 기반으로 먼저 검증한다.

배경(devnotes WIP.md 206차):
205차는 out_speed = min(raw, max(vEgo_kph, apex_speed), 150)로 상한을
vEgo 기반 동적값으로 바꿨으나, 199cha 8세그 로그(북대전IC 진입 26초 전
t=418.42~423.18, 92프레임, apex_idx가 15->7로 슬라이딩)에서 raw와
apex_speed가 "둘 다" ~297~298로 동시에 오염되어 max(vEgo, apex_speed)가
오염된 apex_speed에 지배당해 vEgo 하한이 전혀 작동하지 않았음(206차
NEGATIVE, would_bind 37.1%->37.1% 불변).

이번 세션 코드 추적: carrot_man.py L839("candidates = [k for k in
range(len(speeds)) if speeds[k] < road_limit_speed]")가 이미 "실제
감속이 필요한 지점 전체"를 계산해두고 있다(현재는 telemetry
용도로만 사용, L856-868). apex_idx=candidates[0](가장 가까운 후보)이
"road_limit보다 살짝만 낮은 사실상 무해한 근접 후보"인 동안에도, 같은
lookahead 윈도우 안에 이미 훨씬 급한(=speed가 훨씬 낮은) 후보가
"더 멀리" 존재한다면 그 값도 candidates 리스트 안에 이미 들어있다
(apex_idx만 아직 그 지점을 가리키지 않을 뿐). 이 사실을 이용해:

  sharpest_candidate_speed = min(speeds[k] for k in candidates) if candidates else apex_speed
  out_speed = min(raw, max(vEgo_kph, sharpest_candidate_speed), 150)

로 "상한(ceiling) 항"에서만 apex_speed를 sharpest_candidate_speed로
교체한다.

**중요: 이 변경은 apex_idx/apex_dist/apex_speed 자체(=raw 계산에 쓰이는
1차->2차 순차처리 선택, 196/197차 설계)를 전혀 건드리지 않는다.**
raw(calculate_current_speed 결과값)는 100% 그대로 유지되고, 그 위에
얹는 안전 상한(ceiling)의 "얼마나 관대하게 풀어줄지" 판단 기준만
"가장 가까운 후보"에서 "윈도우 내 가장 급한 후보"로 낮춘다(=더 보수적
으로만 바뀔 수 있음, sharpest_candidate_speed <= apex_speed가 항상
성립하므로 상한이 완화되는 방향의 회귀는 구조적으로 불가능).

158/159차 폐기 사유(명시적 3상태 히스테리시스: stuck-disengaged 2/3,
프레임간 최대낙차 244km/h)와는 무관 -- 이번 설계는 새로운 상태를
추가하지 않고(무상태, 매 프레임 독립 재계산), _route_speed_prev
램프리미터는 205/206차와 완전히 동일하게 매 프레임 연속으로만
동작하므로 159차 실패의 구조적 원인(상태 리셋으로 인한 300 즉시통과
점프)이 애초에 발생할 수 없다.

이 스크립트는 실제 199cha 8세그 로그(대용량, §23 대상, 컨테이너
리셋으로 소실)를 재사용하지 못해(원본 재추출 필요), 206차 WIP 기록에
명시된 수치(apex_idx/apex_dist/apex_speed/vEgo 근사값)로 재구성한
시나리오 + 회귀 확인용 대조 시나리오로 검증한다. 실제 로그 재생 검증은
다음 세션 과제로 남긴다(NEEDS_VALIDATION).
"""
import math

AUTO_NAVI_SPEED_DECEL_RATE = 0.70  # 83차 실측
AUTO_NAVI_SPEED_CTRL_END = 7.0     # params_keys.h 기본값(AutoNaviSpeedCtrlEnd)
ROUTE_MAX_SPEED_KPH = 150.0


def calculate_current_speed(left_dist, safe_speed_kph, safe_time, safe_decel_rate):
    """carrot_serv.py::calculate_current_speed 그대로 재현."""
    safe_speed = safe_speed_kph / 3.6
    safe_dist = safe_speed * safe_time
    decel_dist = left_dist - safe_dist
    if decel_dist <= 0:
        return safe_speed_kph
    temp = safe_speed ** 2 + 2 * safe_decel_rate * decel_dist
    speed_mps = math.sqrt(temp) if temp >= 0 else safe_speed
    return max(safe_speed_kph, min(250, speed_mps * 3.6))


def ceiling_old_205(apex_speed, sharpest_candidate_speed, v_ego_kph):
    """205/206차 현재 코드: ceiling = max(vEgo, apex_speed)."""
    return max(v_ego_kph, apex_speed)


def ceiling_new_207(apex_speed, sharpest_candidate_speed, v_ego_kph):
    """207차 제안: ceiling = max(vEgo, sharpest_candidate_speed)."""
    return max(v_ego_kph, sharpest_candidate_speed)


def run_scenario(name, apex_dist, apex_speed, sharpest_candidate_speed, v_ego_kph,
                  expect_old, expect_new, tol=0.1):
    raw = calculate_current_speed(apex_dist, apex_speed, AUTO_NAVI_SPEED_CTRL_END,
                                   AUTO_NAVI_SPEED_DECEL_RATE)
    old_ceiling = ceiling_old_205(apex_speed, sharpest_candidate_speed, v_ego_kph)
    new_ceiling = ceiling_new_207(apex_speed, sharpest_candidate_speed, v_ego_kph)
    old_out = min(raw, old_ceiling, ROUTE_MAX_SPEED_KPH)
    new_out = min(raw, new_ceiling, ROUTE_MAX_SPEED_KPH)

    ok = True
    if expect_old is not None and abs(old_out - expect_old) > tol:
        ok = False
    if expect_new is not None and abs(new_out - expect_new) > tol:
        ok = False

    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    print(f"    apex_dist={apex_dist} apex_speed={apex_speed:.1f} "
          f"sharpest={sharpest_candidate_speed:.1f} vEgo={v_ego_kph:.1f}")
    print(f"    raw={raw:.1f}  OLD(205차) out={old_out:.1f} (기대 {expect_old})  "
          f"NEW(207차) out={new_out:.1f} (기대 {expect_new})")
    return ok


def main():
    results = []

    # 시나리오 1 -- 206차가 발견한 "298 고원" 재현(핵심 검증 대상).
    # 근접 후보(idx~7, dist=70m)는 road_limit(300) 바로 아래(297.5)라
    # 사실상 무해하지만, 같은 lookahead 윈도우 안에 이미 idx=21(dist=230m,
    # speed=50, 실제 북대전IC 커브)이 candidates 리스트에 들어있다(아직
    # candidates[0]로 선택되지 않았을 뿐). vEgo=55.
    results.append(run_scenario(
        "1. 199cha 8세그 재현(근접 trivial 후보 + 원거리 진짜 급커브 공존)",
        apex_dist=70.0, apex_speed=297.5, sharpest_candidate_speed=50.0, v_ego_kph=55.0,
        expect_old=150.0,  # 206차 NEGATIVE 재현: apex_speed가 지배해 150 절대상한까지만 눌림(vEgo 무시)
        expect_new=55.0,   # 207차: sharpest(50)가 vEgo(55)보다 낮으므로 ceiling=vEgo=55 -> out=55
    ))

    # 시나리오 1b -- 전환 직후(t=423.23 부근). apex_idx가 실제로 idx=21로
    # 넘어간 직후, 거리 230m/목표 50kph 조건에서 raw 자체가 아직 높음
    # (calculate_current_speed가 먼 거리에서는 큰 값을 반환하는 구조,
    # 202/206차가 이미 지적한 성질). 이 프레임에서는 apex_speed=sharpest이므로
    # OLD/NEW가 동일해야 한다(회귀 없음 확인).
    results.append(run_scenario(
        "1b. 전환 직후(candidates[0]가 이미 진짜 급커브를 가리킴)",
        apex_dist=230.0, apex_speed=50.0, sharpest_candidate_speed=50.0, v_ego_kph=55.0,
        expect_old=None, expect_new=None,  # 값 자체보다 OLD==NEW 일치 여부만 아래에서 별도 확인
    ))

    # 시나리오 2 -- 진짜 직선 복귀(커브 통과 후 가속), 윈도우 내 다른 급커브 없음.
    # candidates가 근접 1개뿐이고 그 값 자체가 sharpest와 동일 -> OLD와 NEW가
    # 완전히 같아야 한다(203차가 우려했던 "가속을 막는 회귀"가 없어야 함).
    results.append(run_scenario(
        "2. 정상 직선 복귀(원거리 급커브 없음, 회귀 없어야 함)",
        apex_dist=50.0, apex_speed=90.0, sharpest_candidate_speed=90.0, v_ego_kph=40.0,
        expect_old=90.0, expect_new=90.0,
    ))

    # 시나리오 3 -- 연속 S자, 1차(근접)가 2차(원거리)보다 완만하지만 둘 다
    # vEgo보다는 낮은 정상적인 연속감속 상황. ceiling 자체가 vEgo에 의해
    # 이미 지배되므로(=vEgo가 가장 큰 값) OLD/NEW 동일해야 한다(연속곡선
    # 순차처리 설계 자체는 이 변경과 무관함을 확인).
    results.append(run_scenario(
        "3. 연속 S자(2차가 더 급함, 정상 감속 진행 중, 회귀 없어야 함)",
        apex_dist=30.0, apex_speed=45.0, sharpest_candidate_speed=30.0, v_ego_kph=50.0,
        expect_old=45.0, expect_new=45.0,
        # raw = calculate_current_speed(30, 45, 7, 0.70): decel_dist = 30-87.5 <0 -> raw=45
        # OLD ceiling=max(50,45)=50, NEW ceiling=max(50,30)=50 -> 둘 다 min(45,50,150)=45
    ))

    # 시나리오 4 -- candidates가 비어있는 완전 직선(폴백 경로). sharpest는
    # apex_speed로 그대로 폴백해야 하며 OLD와 100% 동일해야 한다.
    results.append(run_scenario(
        "4. 완전 직선(candidates=[] 폴백, diff-0 확인)",
        apex_dist=300.0, apex_speed=300.0, sharpest_candidate_speed=300.0, v_ego_kph=40.0,
        expect_old=150.0, expect_new=150.0,
        # raw=calculate_current_speed(300,300,7,0.70): safe_dist=300*7/3.6? wait speed in m/s
    ))

    # 시나리오 1b의 OLD==NEW 재확인(별도 assert, tol 사용).
    raw_1b = calculate_current_speed(230.0, 50.0, AUTO_NAVI_SPEED_CTRL_END, AUTO_NAVI_SPEED_DECEL_RATE)
    old_1b = min(raw_1b, ceiling_old_205(50.0, 50.0, 55.0), ROUTE_MAX_SPEED_KPH)
    new_1b = min(raw_1b, ceiling_new_207(50.0, 50.0, 55.0), ROUTE_MAX_SPEED_KPH)
    ok_1b = abs(old_1b - new_1b) < 1e-6
    print(f"[{'PASS' if ok_1b else 'FAIL'}] 1b 부가확인: OLD==NEW ({old_1b:.3f} vs {new_1b:.3f})")
    results.append(ok_1b)

    total = len(results)
    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
