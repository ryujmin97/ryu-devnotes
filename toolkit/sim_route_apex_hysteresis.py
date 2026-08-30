#!/usr/bin/env python3
"""
158차 계속 (신규) - 157차 apex 재설계(carrot_navi_route_apex, 매 프레임
무상태 전역탐색)에 대해 사용자가 제기한 우려("apex마다 명시적 리셋을
넣으면 연속 굽이길에서 매 apex 통과 시점마다 target이 톱니처럼
300<->커브속도로 진동하는 것 아닌가")를 검증하기 위해 설계한 3상태
히스테리시스 대안.

배경: 157차 carrot_navi_route_apex()는 매 프레임 lookahead 윈도우 전체를
무상태로 재탐색(min-speed 지점 = apex)한다. 사용자가 "route는 apex까지
사전감속만 담당하고, 정점(최대곡률) 통과 후에는 vturn(비전)에 완전히
넘긴 뒤 다음 apex를 다시 찾는 게 의도"라고 명시하자, 이 무상태 구조가
실제로 그 의도대로 동작하는지 실측(route156.csv, t=6226~6346 연속
굽이길)으로 확인했다. 결과: 고립된 단일 커브는 이미 사실상 "정점 통과
즉시 해제"와 동일하게 동작하지만, 156차류 연속 굽이길에서는 apex 하나
지나면 20~50m 뒤에 바로 다음 apex가 있어 "리셋"이라는 개념 자체가 안
맞고, 오히려 매 apex마다 강제 리셋을 넣으면 300<->커브속도 톱니 진동
위험이 있다는 결론(사용자 확인).

이에 사용자가 제시한 개선 방향: "먼저 계산했던 곡률보다 완만한 곡률이
연속되면 vturn에 맡기고, 더 급한 곡률이 나오면 route가 개입, 완전
리셋(직선 확인) 이후에만 다음 곡률 계산을 새로 시작"는 3상태 설계:

  1. RESET (target_curv 없음): 전방 윈도우 전체가 negligible_curv 미만
     (진짜 직선)이면 이 상태 유지, 제약 없음(300) 반환. 유의미한 곡률이
     하나라도 나타나면 즉시 ENGAGED로 전이하고 그 값을 target_curv로 삼음.
  2. ENGAGED (현재 target_curv를 추적/감속 중): 윈도우 내 curvature >=
     target_curv인 후보만 유효. 후보 중 가장 급한 값으로 target_curv를
     승격(에스컬레이션, 접근 중 더 급한 지점 발견 시 갱신) -- 아직
     ENGAGED 유지. target_curv 이상인 후보가 더 이상 없으면(=완만한
     지점만 남음, 즉 apex를 통과했거나 그 이상 급한 게 없음)
     DISENGAGED로 전이, 이번 프레임은 제약 없음(300) 반환.
  3. DISENGAGED (target_curv는 기억, vturn에 위임 중): 윈도우 내
     최대곡률이 target_curv보다 급해지면(=진짜 다음 급커브 재접근)
     즉시 ENGAGED로 재전이. target_curv 미만이지만 여전히 negligible
     이상(=완만한 커브가 남아있음)이면 계속 DISENGAGED 유지(무시,
     vturn에 맡김, target_curv는 그대로 보존). 윈도우 전체가 negligible
     미만(진짜 직선)이 되면 RESET으로 완전 전이(target_curv 삭제).

157차와의 차이는 "제약을 낼지 말지"뿐 -- 제약을 낼 때(ENGAGED)의 물리
공식(거리기반 accel_limit/vturn_decel_rate 부스트)은 157차
carrot_navi_route_apex와 동일하게 재사용.

사용:
    python3 sim_route_apex_hysteresis.py --unit-tests
"""
import sys
from dataclasses import dataclass

sys.path.insert(0, ".")
from sim_route_apex_redesign import curve_speed, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS

NEGLIGIBLE_CURV_DEFAULT = 0.001  # 157차 ROUTE_CURVE_NEGLIGIBLE_THRESHOLD와 동일


@dataclass
class ApexHysteresisState:
    mode: str = "reset"       # "reset" | "engaged" | "disengaged"
    target_curv: float = 0.0  # 현재 추적/기억 중인 곡률(절대값)


def carrot_navi_route_apex_hysteresis(state, merged, v_ego_kph, accel_limit_mss,
                                       max_accel_mss=1.2,
                                       negligible_curv=NEGLIGIBLE_CURV_DEFAULT):
    """merged: [(distance, curvature, speed), ...] (analysis_helpers.
    recompute_route_curvature_speed()와 동일 포맷, 거리 오름차순).
    state: ApexHysteresisState (프레임 간 유지되는 유일한 상태, in-place 갱신).
    반환: (out_speed_kph, accel_limit_kmh) -- 157차 carrot_navi_route_apex와
    동일 시그니처(램프리미터에 그대로 이어붙일 수 있게).
    """
    accel_limit_kmh = accel_limit_mss * 3.6
    if not merged:
        state.mode = "reset"
        state.target_curv = 0.0
        return 300.0, accel_limit_kmh

    curvs = [abs(m[1]) for m in merged]
    front_max_curv = max(curvs)
    front_max_idx = curvs.index(front_max_curv)

    apex_idx = None

    if state.mode == "reset":
        if front_max_curv < negligible_curv:
            return 300.0, accel_limit_kmh  # 계속 직선, 리셋 유지
        state.mode = "engaged"
        state.target_curv = front_max_curv
        apex_idx = front_max_idx

    elif state.mode == "engaged":
        candidates = [i for i, c in enumerate(curvs) if c >= state.target_curv - 1e-9]
        if not candidates:
            # target_curv급 이상은 윈도우에서 사라짐 -> 정점 통과/소실, 해제
            state.mode = "disengaged"
            return 300.0, accel_limit_kmh
        apex_idx = max(candidates, key=lambda i: curvs[i])
        if curvs[apex_idx] > state.target_curv:
            state.target_curv = curvs[apex_idx]  # 접근 중 더 급한 지점 발견 -> 승격

    else:  # disengaged
        if front_max_curv > state.target_curv + 1e-9:
            state.mode = "engaged"
            state.target_curv = front_max_curv
            apex_idx = front_max_idx
        elif front_max_curv < negligible_curv:
            state.mode = "reset"
            state.target_curv = 0.0
            return 300.0, accel_limit_kmh
        else:
            return 300.0, accel_limit_kmh  # 완만한 잔여 곡률, 계속 vturn에 위임

    dist = merged[apex_idx][0]
    speed = merged[apex_idx][2]
    if dist <= 0:
        return speed, accel_limit_kmh
    v_ego_ms = v_ego_kph / 3.6
    target_ms = speed / 3.6
    required_accel_mss = max(0.0, (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * dist))
    applied_accel_mss = accel_limit_mss if required_accel_mss <= accel_limit_mss \
        else min(required_accel_mss, max_accel_mss)
    out_ms_sq = target_ms ** 2 + 2.0 * applied_accel_mss * dist
    out_speed = (out_ms_sq ** 0.5) * 3.6 if out_ms_sq > 0 else speed
    return min(out_speed, 300.0), applied_accel_mss * 3.6


# ---------------------------------------------------------------------------
# 합성 헬퍼: (distance, curvature) 목록에서 curve_speed()로 speed까지 채운
# merged 프레임을 만든다. road_limit_speed/floor_threshold는 157차와 동일
# 기본값(200.0 / negligible_curv) 사용.
# ---------------------------------------------------------------------------
def make_frame(dist_curv_pairs, road_limit_speed=200.0, floor_threshold=NEGLIGIBLE_CURV_DEFAULT):
    return [(d, c, curve_speed(c, road_limit_speed, floor_threshold)) for d, c in dist_curv_pairs]


def _run_unit_tests():
    passed = failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"PASS: {name}")
        else:
            failed += 1
            print(f"FAIL: {name} {detail}")

    ACC = 0.70

    # 1) 고립된 단일 커브: apex(curv=0.0165, R~61m) 통과 후 창이 전진하며
    #    남은 구간이 전부 negligible(noise) -> engaged에서 candidates 없음
    #    -> disengaged로 즉시 해제(제약 300 반환), 다음 프레임에 완전 reset.
    st = ApexHysteresisState()
    # 접근 프레임: apex가 창 안(50m 앞)
    f1 = make_frame([(20, 0.0003), (50, 0.0165), (80, 0.0003)])
    out1, _ = carrot_navi_route_apex_hysteresis(st, f1, 90.0, ACC)
    engaged_after_f1 = (st.mode == "engaged" and abs(st.target_curv - 0.0165) < 1e-9)
    # 통과 프레임: apex가 창 뒤로 빠짐(창이 전진), 남은 건 전부 noise
    f2 = make_frame([(30, 0.0003), (60, 0.0004)])
    out2, _ = carrot_navi_route_apex_hysteresis(st, f2, 43.0, ACC)
    disengaged_after_f2 = (st.mode == "disengaged")
    # 다음 프레임: 여전히 noise만 -> 완전 reset, 제약 없음
    f3 = make_frame([(30, 0.0003), (60, 0.0003)])
    out3, _ = carrot_navi_route_apex_hysteresis(st, f3, 43.0, ACC)
    reset_after_f3 = (st.mode == "reset" and out3 > 150.0)
    check("test_isolated_curve_release_after_apex",
          engaged_after_f1 and out1 < 60.0 and disengaged_after_f2 and out2 > 150.0 and reset_after_f3,
          f"f1={out1:.1f}/{st.mode} f2={out2:.1f} f3={out3:.1f}")

    # 2) 급커브 통과 후 disengaged 상태에서, target_curv보다 완만한 커브가
    #    나타나도 무시(vturn에 계속 위임) -- 300 반환, target_curv 그대로.
    st2 = ApexHysteresisState(mode="disengaged", target_curv=0.0165)
    f_mild = make_frame([(40, 0.006), (90, 0.005)])  # 0.0165보다 완만
    out_mild, _ = carrot_navi_route_apex_hysteresis(st2, f_mild, 70.0, ACC)
    check("test_milder_curve_deferred_to_vturn",
          out_mild > 150.0 and st2.mode == "disengaged" and abs(st2.target_curv - 0.0165) < 1e-9,
          f"out={out_mild:.1f} mode={st2.mode} target={st2.target_curv}")

    # 3) disengaged 상태에서 target_curv보다 더 급한 커브가 새로 나타나면
    #    즉시 재개입(엔진engaged)해 감속값을 낸다.
    st3 = ApexHysteresisState(mode="disengaged", target_curv=0.0091)  # R~110m급 기억
    f_sharp = make_frame([(50, 0.020)])  # 훨씬 급함(R~50m급)
    out_sharp, _ = carrot_navi_route_apex_hysteresis(st3, f_sharp, 80.0, ACC)
    check("test_sharper_curve_reengages",
          st3.mode == "engaged" and abs(st3.target_curv - 0.020) < 1e-9 and out_sharp < 70.0,
          f"out={out_sharp:.1f} mode={st3.mode} target={st3.target_curv}")

    # 4) engaged 상태에서 접근 중(같은 커브의 정점에 더 가까운 지점이 창에
    #    새로 들어옴) 더 급한 지점이 나타나면 target_curv를 승격하되 engaged
    #    상태는 계속 유지(불필요한 disengage/reengage 사이클 없음).
    st4 = ApexHysteresisState(mode="engaged", target_curv=0.010)
    f_escalate = make_frame([(20, 0.010), (40, 0.0165)])  # 더 급한 지점이 뒤에 추가로 나타남
    out_esc, _ = carrot_navi_route_apex_hysteresis(st4, f_escalate, 60.0, ACC)
    check("test_engaged_escalation_mid_approach",
          st4.mode == "engaged" and abs(st4.target_curv - 0.0165) < 1e-9,
          f"mode={st4.mode} target={st4.target_curv} out={out_esc:.1f}")

    print(f"\n{passed} PASS / {failed} FAIL")
    return failed == 0


if __name__ == "__main__":
    if "--unit-tests" in sys.argv:
        ok = _run_unit_tests()
        sys.exit(0 if ok else 1)
    print(__doc__)
