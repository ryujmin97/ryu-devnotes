#!/usr/bin/env python3
"""
160차 신규 - "route 감속을 과속카메라 감속 로직과 완전히 동일하게" (사용자
설계, 곡선_가감속_코딩.txt + 곡선_개념도.pdf) 시뮬레이션 검증.

사용자 설계 요약:
  1. route 감속의 목적 = Vturn(비전) 감속으로는 부족한 사전감속.
  2. apex(최대곡률지점) 목표속도를 "과속카메라 제한속도"처럼 취급하고,
     carrot_serv.calculate_current_speed(left_dist, safe_speed_kph,
     safe_time, safe_decel_rate) 물리공식을 그대로 재사용해 서서히
     감속 -> apex 도달 시 원복.
  3. apex 선택 기준은 157차와 동일("가장 급한 지점" = lookahead 내
     목표속도 최저점). 순차(1차->2차) state는 도입하지 않음 -- 매 프레임
     무상태 재계산이라 apex 통과 후 다음 프레임에 윈도우가 전진하며
     자동으로 다음 apex가 선택됨(157차와 동일 원리).
  4. 157차의 "필요감속률이 accel_limit 초과 시 vturn_decel_rate까지
     동적 부스트"하는 분기는 폐기 -- 카메라 로직엔 그런 부스트가 없고
     고정 decel_rate(autoNaviSpeedDecelRate)만 사용.

carrot_serv.calculate_current_speed()와 100% 동일한 수식을 아래
camera_calculate_current_speed()로 그대로 복제(카피 아님 -- 동일
파라미터 이름/순서/분기 유지해 수치 동일성이 육안으로 검증되게 함).

기존 자산 재사용(먼저 찾는다 원칙): simulate_road/RampLimiterState 등
도로 샘플러·다중프레임 접근 시뮬레이터는 sim_route_apex_redesign.py를
그대로 import해서 쓴다 -- 새로 안 만듦.

사용:
    python3 sim_route_camera_style_decel.py --unit-tests
"""
import sys

sys.path.insert(0, ".")
from sim_route_apex_redesign import (
    DISTANCE_INTERVAL,
    carrot_navi_route_apex,
    winding_road_curvature_fn,
    straight_road_curvature_fn,
    single_sharp_curve_curvature_fn,
    sample_curvature_road,
    sample_near_stop,
)
from sim_route_boundary_ramp_limiter import RampLimiterState


# ---------------------------------------------------------------------------
# carrot_serv.py::calculate_current_speed()를 그대로 복제 (과속카메라와
# 수식/분기 100% 동일 -- left_dist/safe_speed_kph/safe_time/safe_decel_rate
# 네 인자 이름과 순서까지 프로덕션 함수 시그니처와 맞춤).
# ---------------------------------------------------------------------------
def camera_calculate_current_speed(left_dist, safe_speed_kph, safe_time, safe_decel_rate):
    safe_speed = safe_speed_kph / 3.6
    safe_dist = safe_speed * safe_time
    decel_dist = left_dist - safe_dist

    if decel_dist <= 0:
        return safe_speed_kph

    temp = safe_speed ** 2 + 2 * safe_decel_rate * decel_dist
    if temp < 0:
        speed_mps = safe_speed
    else:
        speed_mps = temp ** 0.5
    return max(safe_speed_kph, min(250, speed_mps * 3.6))


# ---------------------------------------------------------------------------
# 재설계: route apex에 카메라 감속 공식 그대로 적용 (160차, 사용자 설계)
# ---------------------------------------------------------------------------
def carrot_navi_route_camera_style(speeds, distances, safe_time, decel_rate_mss):
    """apex 선택은 157차와 동일(가장 급한 지점=목표속도 최저점). v_ego는
    카메라 공식과 마찬가지로 아예 사용하지 않는다(거리만으로 결정).
    accel_limit_kmh는 더 이상 동적으로 변하지 않으므로(부스트 폐기) 고정값."""
    if not speeds:
        return 300.0, decel_rate_mss * 3.6
    apex_idx = min(range(len(speeds)), key=lambda k: speeds[k])
    apex_dist = distances[apex_idx]
    apex_speed = speeds[apex_idx]
    out_speed = camera_calculate_current_speed(apex_dist, apex_speed, safe_time, decel_rate_mss)
    return min(out_speed, 300.0), decel_rate_mss * 3.6


def simulate_road_camera(sampler, road_len_m, v_ego_kph_start, safe_time, decel_rate_mss,
                          dt=0.05, max_steps=6000):
    """sim_route_apex_redesign.simulate_road()와 동일 방법론(완벽추종 가정,
    132차 램프리미터 포함)이나 algo가 camera-style 하나뿐이라 분기 없이 직접 구현."""
    v_ego_kph = v_ego_kph_start
    pos = 0.0
    t = 0.0
    limiter = RampLimiterState()
    trace = []
    steps = 0
    min_v = v_ego_kph
    max_step_kmh = 0.0
    prev_unrounded = None  # 프레임간 낙차 판정은 표시용 반올림(trace) 값이 아니라
                            # 반올림 전 실제 값끼리 비교해야 함 -- round(...,1) 두 값을
                            # 서로 비교하면 최대 0.1kph의 반올림 오차가 섞여 잘못된
                            # "위반" 판정이 나올 수 있음(160차 최초 작성 시 실제로 겪은 버그).
    while pos < road_len_m and steps < max_steps:
        speeds, distances = sampler(pos)
        raw_out, accel_limit_kmh = carrot_navi_route_camera_style(speeds, distances, safe_time, decel_rate_mss)
        out_speed = limiter.apply(raw_out, accel_limit_kmh, dt)
        if prev_unrounded is not None:
            max_step_kmh = max(max_step_kmh, abs(out_speed - prev_unrounded))
        prev_unrounded = out_speed
        v_ego_kph = out_speed
        min_v = min(min_v, v_ego_kph)
        pos += (v_ego_kph / 3.6) * dt
        t += dt
        steps += 1
        trace.append((round(t, 2), round(pos, 1), round(v_ego_kph, 1)))
    return v_ego_kph, min_v, t, trace, max_step_kmh


# ---------------------------------------------------------------------------
# 연속 S자 커브(1차/2차 곡선이 가깝게 붙은 경우) -- 곡선_개념도.pdf의 "②
# 연속되는 곡선" 케이스. 톱니 진동(1차 통과 즉시 원복 -> 바로 2차 재감속)
# 발생 여부를 프레임간 낙차(max_step_kmh)로 확인한다.
# ---------------------------------------------------------------------------
def double_curve_curvature_fn(apex1_m=200.0, apex2_m=260.0, curv1=0.011, curv2=0.017, width_m=15.0):
    """절대좌표 apex1_m/apex2_m 부근에서만 각각 curv1/curv2, 그 외 직선.
    두 apex 간격(기본 60m)은 149/152차 근정지 사례보다 넉넉하지만
    S자 연속곡선치고는 좁은 축(사용자 그림의 "②" 케이스를 과장해서
    재현 -- 간격을 더 좁힐수록 톱니 진동 여부가 더 잘 드러남)."""
    def fn(abs_d):
        if abs(abs_d - apex1_m) < width_m / 2:
            return curv1
        if abs(abs_d - apex2_m) < width_m / 2:
            return curv2
        return 0.0003
    return fn


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

    SAFE_TIME = 2.2       # autoNaviSpeedCtrlEnd 대표값(카메라 기본과 동일 가정)
    DECEL_RATE = 0.7      # autoNaviSpeedDecelRate 대표값(157차 시나리오와 동일)

    # 1) 156차류 연속 굽이길: 157차(apex, floor=0.001)와 동일 곡률/속도로
    #    실행해 "실제로 감속하는가"는 유지되는지 확인.
    curv_fn = winding_road_curvature_fn()
    sampler_apex = lambda pos: sample_curvature_road(curv_fn, pos, 600.0, 110.0, 0.001)
    _, min_v_apex157, _, _ = __import__("sim_route_apex_redesign").simulate_road(
        sampler_apex, 600.0, 68.0, 0.7, "apex")
    _, min_v_cam, _, _, _ = simulate_road_camera(sampler_apex, 600.0, 68.0, SAFE_TIME, DECEL_RATE)
    check("156차류 winding road: camera-style도 실제 커브속도까지 감속",
          min_v_cam < 65.0, f"min_v_cam={min_v_cam:.1f}")
    check("156차류 winding road: 157차 대비 최소속도 과도한 이탈 없음(±15kph 이내)",
          abs(min_v_cam - min_v_apex157) < 15.0,
          f"apex157={min_v_apex157:.1f}, camera={min_v_cam:.1f}")

    # 2) 직선(노이즈만): raw out_speed가 road_limit(110)보다 높아야 함(오탐 없음).
    straight_fn = straight_road_curvature_fn()
    speeds_s, dist_s = sample_curvature_road(straight_fn, 0.0, 600.0, 110.0, 0.001)
    raw_s, _ = carrot_navi_route_camera_style(speeds_s, dist_s, SAFE_TIME, DECEL_RATE)
    check("직선도로: camera-style 회귀 없음(제약 없음 유지)", raw_s > 150.0, f"{raw_s:.1f}")

    # 3) 147차류 단일 급커브: apex 재설계와 동일하게 정상 감속해야 함.
    sharp_fn = single_sharp_curve_curvature_fn(apex_dist_m=300.0)
    sampler_c = lambda pos: sample_curvature_road(sharp_fn, pos, 400.0, 110.0, 0.001)
    _, min_v_cam_c, _, _, _ = simulate_road_camera(sampler_c, 400.0, 90.0, SAFE_TIME, DECEL_RATE)
    check("147차류 단일커브: camera-style도 정상 감속", min_v_cam_c < 60.0, f"{min_v_cam_c:.1f}")

    # 4) 152/153차 근정지 코너: safe_time 버퍼가 추가돼도 목표속도 근접
    #    도달해야 함(버퍼 때문에 오히려 못 미치거나 초과하면 문제).
    sampler_ns = lambda pos: sample_near_stop(pos, 280.0, target_kph=10.7)
    final_v_cam, _, _, _, _ = simulate_road_camera(sampler_ns, 280.0, 90.0, SAFE_TIME, DECEL_RATE)
    check("152/153차 근정지 재현: camera-style도 목표속도 근접 도달(초과 없음)",
          final_v_cam < 10.7 + 1.0, f"final_v={final_v_cam:.1f} (target=10.7)")

    # 5) [신규, 사용자 설계 핵심 검증] 연속 S자 커브(1차/2차 곡선이 60m
    #    간격으로 붙어있음, 2차가 더 급함) -- "1차 apex 통과 즉시 원복 후
    #    바로 2차 재감속"이 톱니 진동(짧은 시간 내 큰 낙차 반복)을
    #    유발하는지 프레임간 최대낙차(max_step_kmh)로 확인.
    #    132차 램프리미터가 정상 작동하면 이론 상한(accel_limit_kmh*dt)을
    #    넘지 않아야 한다 -- 넘으면 램프리미터가 깨진 것(회귀).
    dbl_fn = double_curve_curvature_fn()
    sampler_dbl = lambda pos: sample_curvature_road(dbl_fn, pos, 400.0, 110.0, 0.001)
    final_v_dbl, min_v_dbl, _, trace_dbl, max_step_dbl = simulate_road_camera(
        sampler_dbl, 400.0, 80.0, SAFE_TIME, DECEL_RATE, dt=0.05)
    theoretical_max_step = DECEL_RATE * 3.6 * 0.05  # accel_limit_kmh * dt
    check("연속 S자커브: 2차(더 급한 커브)까지 실제로 감속함",
          min_v_dbl < 55.0, f"min_v_dbl={min_v_dbl:.1f}")
    check("연속 S자커브: 프레임간 최대낙차가 132차 램프리미터 이론상한 이내(톱니 진동 없음)",
          max_step_dbl <= theoretical_max_step + 1e-6,
          f"max_step={max_step_dbl:.4f}, 이론상한={theoretical_max_step:.4f}")
    # 1차 apex(200m) 부근에서 "확 풀렸다가"가 실제로 일어나는지 참고 출력
    near_apex1 = [row for row in trace_dbl if 190.0 <= row[1] <= 230.0]
    if len(near_apex1) >= 2:
        deltas = [abs(near_apex1[i+1][2] - near_apex1[i][2]) for i in range(len(near_apex1)-1)]
        print(f"  (참고) 1차 apex(200m) 통과 구간 프레임간 낙차: max={max(deltas):.3f}kph, "
              f"구간속도범위={min(r[2] for r in near_apex1):.1f}~{max(r[2] for r in near_apex1):.1f}kph")

    print(f"\n{passed} PASS / {failed} FAIL")
    return failed == 0


if __name__ == "__main__":
    if "--unit-tests" in sys.argv:
        ok = _run_unit_tests()
        sys.exit(0 if ok else 1)
    print(__doc__)
