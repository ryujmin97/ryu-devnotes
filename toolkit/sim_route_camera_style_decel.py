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


def carrot_navi_route_camera_style_nearest(speeds, distances, safe_time, decel_rate_mss,
                                            road_limit_speed=200.0):
    """179차 신규 -- apex 선택기준을 "가장 급한 지점"(전역 min(speeds))에서
    "가장 가까운 지점"(감속필요 최근접, speeds[k] < road_limit_speed인 최소
    index)으로 변경. carrot_man.py 179차 패치와 동일 로직(distances가 항상
    오름차순이라는 production 불변식 그대로 사용). road_limit_speed는
    실측 nRoadLimitSpeed를 CSV가 기록하지 않아 recompute_route_curvature_speed()
    와 동일한 200.0 기본 가정을 그대로 재사용(내부 floor 로직과 정합성
    유지 -- floor가 리셋하는 기준값과 apex 게이트 기준값이 같아야 "감속
    필요 없는 직선"과 "실제 커브"가 일관되게 구분됨)."""
    if not speeds:
        return 300.0, decel_rate_mss * 3.6
    apex_idx = next((k for k in range(len(speeds)) if speeds[k] < road_limit_speed), None)
    if apex_idx is None:
        apex_idx = min(range(len(speeds)), key=lambda k: speeds[k])
    apex_dist = distances[apex_idx]
    apex_speed = speeds[apex_idx]
    out_speed = camera_calculate_current_speed(apex_dist, apex_speed, safe_time, decel_rate_mss)
    return min(out_speed, 300.0), decel_rate_mss * 3.6


def carrot_navi_route_camera_style_nearest_severity_gated(speeds, distances, safe_time, decel_rate_mss,
                                                            road_limit_speed=200.0, min_severity_ratio=0.5):
    """179차 후속(사용자 제안, 미채택 -- 아래 유닛테스트 참고) -- nearest
    게이트에 "목표속도가 도로제한속도 대비 일정 비율(min_severity_ratio)
    이상 낮을 때만 유효 apex 후보로 인정"하는 최소 심각도 기준을 추가한
    버전. speeds[k] < road_limit_speed * min_severity_ratio 인 첫 지점을
    선택 -- 그런 지점이 없으면(모두 완만) 폴백으로 기존 nearest 방식
    (speeds[k] < road_limit_speed)으로 재탐색, 그마저 없으면 전역
    min(speeds)로 폴백(3단 폴백, 179차 기존 2단에서 1단 추가).

    [사전 경고, 179차 후속 유닛테스트로 확정] 이 게이트는 설계 의도와
    반대로 작동할 수 있다 -- lookup 테이블(V_CURVE_LOOKUP_BP/VALS)이
    "낮은 curvature 구간에서 기울기가 매우 가파른" 비선형 형태라, floor
    (0.001) 바로 위 미세잡음(curv~0.01~0.02)이 실제 완만한 커브(curv=0.01)
    보다 오히려 목표속도가 더 낮게(=비율 기준 "더 심각하게") 나오는
    경우가 실측에서 이미 확인됐음(179차 검증1, curv1=0.010의 target=54.0
    vs 잡음 curv~0.015의 target=45.0 -- 잡음이 더 "심각"). 즉 min_severity_
    ratio를 아무리 조정해도 curve1을 통과시키는 동시에 그보다 ratio가
    낮은(더 심각해 보이는) 잡음을 걸러내는 단일 임계값은 존재하지 않을
    수 있다 -- 아래 유닛테스트가 이를 직접 재현/확정한다."""
    if not speeds:
        return 300.0, decel_rate_mss * 3.6
    strict_threshold = road_limit_speed * min_severity_ratio
    apex_idx = next((k for k in range(len(speeds)) if speeds[k] < strict_threshold), None)
    if apex_idx is None:
        apex_idx = next((k for k in range(len(speeds)) if speeds[k] < road_limit_speed), None)
    if apex_idx is None:
        apex_idx = min(range(len(speeds)), key=lambda k: speeds[k])
    apex_dist = distances[apex_idx]
    apex_speed = speeds[apex_idx]
    out_speed = camera_calculate_current_speed(apex_dist, apex_speed, safe_time, decel_rate_mss)
    return min(out_speed, 300.0), decel_rate_mss * 3.6


def carrot_navi_route_camera_style_nearest_relative_gated(speeds, distances, safe_time, decel_rate_mss,
                                                            road_limit_speed=200.0, relative_severity_ratio=0.85):
    """179차 후속, 대안1(상대적 심각도 비교) -- 도로제한속도 대비 절대
    비율(위 severity_gated, 폐기됨) 대신, "같은 lookahead 윈도우 내
    가장 급한 지점(sharpest) 대비 후보 지점의 심각도 비율"을 게이트
    기준으로 사용. severity(k) := road_limit_speed - speeds[k] (클수록
    급커브)로 정의하면, 이 지표는 road_limit_speed 절대값에 덜 민감하고
    같은 윈도우 안에서의 상대적 위험도만 비교하므로 폐기된 접근의 핵심
    결함(잡음이 절대비율상 더 "심각"해 보이는 문제)을 피할 수 있다.

    apex 후보(=speeds[k] < road_limit_speed인 지점들) 중 severity(k) >=
    relative_severity_ratio * sharpest_severity(윈도우 내 최댓값)를
    만족하는 가장 가까운 지점을 선택. 그런 지점이 없으면(모든 후보가
    sharpest 대비 상대적으로 완만) 기존 nearest(게이트 없음, 가장 가까운
    후보)로 폴백 -- "게이트 때문에 아예 반응 안 함"이 되는 것보다는
    안전 쪽으로 폴백.

    [유닛테스트로 확정] relative_severity_ratio=0.80~0.95 구간에서
    검증2(curve1, 상대severity=0.962)는 유지, 검증1(noise, 상대severity=
    0.795)은 차단 -- 두 조건을 동시에 만족하는 워킹 구간이 실제로 존재함
    (폐기된 절대비율 접근과 달리 POSITIVE). 기본값 0.85는 그 구간의
    중간값으로 마진을 둔 선택."""
    if not speeds:
        return 300.0, decel_rate_mss * 3.6
    candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed]
    if not candidates:
        apex_idx = min(range(len(speeds)), key=lambda k: speeds[k])
    else:
        sharpest_severity = road_limit_speed - min(speeds[k] for k in candidates)
        gated = [k for k in candidates
                 if sharpest_severity > 0 and (road_limit_speed - speeds[k]) >= relative_severity_ratio * sharpest_severity]
        apex_idx = gated[0] if gated else candidates[0]
    apex_dist = distances[apex_idx]
    apex_speed = speeds[apex_idx]
    out_speed = camera_calculate_current_speed(apex_dist, apex_speed, safe_time, decel_rate_mss)
    return min(out_speed, 300.0), decel_rate_mss * 3.6


def carrot_navi_route_camera_style_nearest_persistence_gated(speeds, distances, safe_time, decel_rate_mss,
                                                               road_limit_speed=200.0, min_persist_points=2):
    """179차 후속, 대안2(연속성/지속성 기준) -- 잡음은 대개 fine-sample
    1개 지점에서만 threshold를 넘고, 진짜 커브는 인접 지점에서도 유지될
    것이라는 가설. 후보 지점 k가 "인접한 min_persist_points개 연속
    지점(k, k+1, ..., 또는 k-1, k)이 모두 road_limit_speed 미만"을
    만족해야 apex로 인정, 아니면 다음 후보로 넘어간다. 만족하는 지점이
    하나도 없으면 기존 nearest(게이트 없음)로 폴백.

    [유닛테스트로 확정, NEGATIVE] 검증2의 curve1(width=20m)도 실제로는
    fine-sample merge 특성상 단일 10m 지점에서만 threshold를 넘는 것으로
    확인됨(대상 시나리오에서 curve2는 2개 연속지점에서 넘지만 curve1은
    1개뿐) -- 즉 "진짜 커브=항상 연속, 잡음=항상 단일"이라는 가설의
    전제 자체가 이 시나리오에서 성립하지 않는다. min_persist_points=2를
    적용하면 curve1도 noise와 마찬가지로 걸러져 검증2가 깨진다."""
    if not speeds:
        return 300.0, decel_rate_mss * 3.6
    candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed]
    apex_idx = None
    for k in candidates:
        window = range(k, min(k + min_persist_points, len(speeds)))
        if len(list(window)) == min_persist_points and all(speeds[j] < road_limit_speed for j in window):
            apex_idx = k
            break
    if apex_idx is None:
        apex_idx = candidates[0] if candidates else min(range(len(speeds)), key=lambda k: speeds[k])
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


def noise_then_real_curve_curvature_fn(noise_m=10.0, real_m=80.0, noise_curv=0.015, real_curv=0.09,
                                        noise_width_m=8.0, real_width_m=20.0):
    """179차 후속 -- 179차 검증1(실측 route 00000374, t=753.5~759.3) 지오메트리를
    합성 재현: 가까운 곳(10m)에 floor 바로 위 미세잡음(curv=0.015, 실측
    -0.001~-0.02 범위 대표값), 더 먼 곳(80m)에 실제 급커브(curv=0.09, 실측
    -0.08~-0.10 범위 대표값). 그 외 구간은 직선."""
    def fn(abs_d):
        if abs(abs_d - noise_m) < noise_width_m / 2:
            return noise_curv
        if abs(abs_d - real_m) < real_width_m / 2:
            return real_curv
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

    # 6) [179차, 사용자 가설 검증] "2차가 1차보다 아주 조금이라도 더 급하면
    #    apex가 처음부터 2차로 고정되어 1차는 사실상 무시됨"(160차 자체
    #    기록에 이미 있던 현상, 당시엔 "2차까지는 정상 감속하니 문제 아님"
    #    으로 넘어감) -- 1차 자신의 곡률에 맞는 감속이 실제로 되는지는
    #    검증한 적이 없었음. sharpest는 1차 진입 직전에도 1차 고유
    #    안전속도보다 훨씬 높은 값을 낼 것이고, nearest는 1차 진입 직전
    #    1차 고유 안전속도에 정확히 도달해야 한다.
    from sim_route_apex_redesign import V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS, _interp
    dbl2_fn = double_curve_curvature_fn(apex1_m=120.0, apex2_m=260.0, curv1=0.010, curv2=0.011, width_m=20.0)
    sampler_dbl2 = lambda pos: sample_curvature_road(dbl2_fn, pos, 400.0, 110.0, 0.001)
    speeds_at_apex1, dist_at_apex1 = sampler_dbl2(119.0)  # apex1 진입 1m 직전
    sharp_at_apex1, _ = carrot_navi_route_camera_style(speeds_at_apex1, dist_at_apex1, SAFE_TIME, DECEL_RATE)
    near_at_apex1, _ = carrot_navi_route_camera_style_nearest(speeds_at_apex1, dist_at_apex1, SAFE_TIME, DECEL_RATE)
    curve1_own_target = _interp(0.010, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
    check("[179차] 연속커브(2차가 살짝 더 급함): sharpest는 1차 진입 직전에도 1차 고유속도보다 과속 상태(=1차 사실상 무시, 160차 기존 특성 재확인)",
          sharp_at_apex1 > curve1_own_target + 5.0,
          f"sharpest={sharp_at_apex1:.1f}, 1차고유속도={curve1_own_target:.1f}")
    check("[179차] 연속커브(2차가 살짝 더 급함): nearest는 1차 진입 직전 1차 고유속도에 정확히 도달(±1kph)",
          abs(near_at_apex1 - curve1_own_target) < 1.0,
          f"nearest={near_at_apex1:.1f}, 1차고유속도={curve1_own_target:.1f}")
    # 1차 통과 후(윈도우에서 사라진 뒤) 2차 접근 시 두 모드가 완전히
    # 수렴하는지(=nearest가 2차 대응력을 전혀 희생하지 않는지) 확인.
    speeds_post1, dist_post1 = sampler_dbl2(200.0)
    sharp_post1, _ = carrot_navi_route_camera_style(speeds_post1, dist_post1, SAFE_TIME, DECEL_RATE)
    near_post1, _ = carrot_navi_route_camera_style_nearest(speeds_post1, dist_post1, SAFE_TIME, DECEL_RATE)
    check("[179차] 1차 통과 후 2차 접근 시 sharpest/nearest 완전 수렴(2차 대응력 희생 없음)",
          abs(sharp_post1 - near_post1) < 0.01,
          f"sharpest={sharp_post1:.2f}, nearest={near_post1:.2f}")

    # 7) [179차 후속, 사용자 제안 "최소 심각도 게이트" 검증] 검증2(연속
    #    S자커브, curve1=0.010)와 검증1(근접잡음 vs 원거리 실제커브)을
    #    동일 게이트 함수로 동시에 만족시키는 min_severity_ratio가
    #    존재하는지 직접 탐색.
    from sim_route_apex_redesign import V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS, _interp

    # 7a) 검증2 재현 (road_limit=110 가정, sim 시나리오와 동일)
    dbl2_fn = double_curve_curvature_fn(apex1_m=120.0, apex2_m=260.0, curv1=0.010, curv2=0.011, width_m=20.0)
    sampler_dbl2 = lambda pos: sample_curvature_road(dbl2_fn, pos, 400.0, 110.0, 0.001)
    speeds_v2, dist_v2 = sampler_dbl2(119.0)
    curve1_own_target = _interp(0.010, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)

    # 7b) 검증1 재현 (road_limit=200 가정, 179차 검증1의 오프라인 재계산 관례와 동일)
    noise_fn = noise_then_real_curve_curvature_fn()
    sampler_noise = lambda pos: sample_curvature_road(noise_fn, pos, 400.0, 200.0, 0.001)
    speeds_v1, dist_v1 = sampler_noise(0.0)

    # 두 시나리오의 road_limit이 달라(110 vs 200) ratio 자체도 시나리오별로
    # 계산해 표로 남긴다 -- 단일 ratio가 "curve1은 통과, noise는 차단"을
    # 동시에 만족하려면 ratio_needed_for_curve1 >= ratio_needed_to_block_noise
    # 여야 하는데, 아래에서 이게 성립하지 않음을 직접 확인한다.
    ratio_curve1 = curve1_own_target / 110.0
    noise_idx_v1 = next((k for k in range(len(speeds_v1)) if speeds_v1[k] < 200.0), None)
    noise_speed = speeds_v1[noise_idx_v1] if noise_idx_v1 is not None else None
    ratio_noise = noise_speed / 200.0 if noise_speed is not None else None
    print(f"  (참고) curve1 ratio(target/road_limit)={ratio_curve1:.3f}, "
          f"noise ratio(target/road_limit)={ratio_noise:.3f} (noise가 더 낮으면 게이트로 분리 불가)")

    # 7c) 게이트 함수로 각 시나리오에서 실제 apex가 어디로 잡히는지 여러
    #     ratio에 대해 스캔 -- curve1을 살리면서 noise를 죽이는 ratio가
    #     하나라도 있는지 전수 확인.
    def apex_dist_with_ratio(speeds, distances, ratio, road_limit):
        out_speed = None
        strict_threshold = road_limit * ratio
        idx = next((k for k in range(len(speeds)) if speeds[k] < strict_threshold), None)
        if idx is None:
            idx = next((k for k in range(len(speeds)) if speeds[k] < road_limit), None)
        if idx is None:
            idx = min(range(len(speeds)), key=lambda k: speeds[k])
        return distances[idx]

    real_curve_dist_expected = 80.0  # noise_then_real_curve_curvature_fn의 real_m
    curve1_dist_expected = 120.0     # double_curve_curvature_fn(apex1_m=120)의 근접 지점(첫 샘플=119m 시점)

    found_working_ratio = None
    for ratio_pct in range(5, 100, 5):
        ratio = ratio_pct / 100.0
        d_v2 = apex_dist_with_ratio(speeds_v2, dist_v2, ratio, 110.0)
        d_v1 = apex_dist_with_ratio(speeds_v1, dist_v1, ratio, 200.0)
        curve1_ok = abs(d_v2 - curve1_dist_expected) < 15.0   # 검증2: 여전히 1차(가까운) 지점을 apex로 선택
        noise_blocked = abs(d_v1 - real_curve_dist_expected) < 15.0  # 검증1: 잡음이 아닌 원거리 실제커브를 apex로 선택
        if curve1_ok and noise_blocked:
            found_working_ratio = ratio
            break

    check("[179차 후속] 검증2(curve1 유지)와 검증1(noise 차단)을 동시에 만족하는 "
          "min_severity_ratio가 존재하지 않음(단일 비율 게이트로는 두 케이스 분리 불가 -- "
          "noise가 curve1보다 ratio 기준 더 '심각'해서, curve1을 살리는 ratio는 항상 noise도 같이 살림)",
          found_working_ratio is None,
          f"found_working_ratio={found_working_ratio}" if found_working_ratio is not None else "(전 구간 탐색, 없음 확인됨)")

    # 게이트 함수 자체(carrot_navi_route_camera_style_nearest_severity_gated)로도
    # 동일하게 재확인 -- ratio=0.5(검증2의 curve1 ratio=0.491보다 살짝 높게 설정,
    # 즉 "curve1은 통과시키려는 의도"로 고른 값)에서 검증1의 apex가 여전히
    # noise(10m)로 고정되는지 직접 함수 호출로 검증.
    gated_out_v1, _ = carrot_navi_route_camera_style_nearest_severity_gated(
        speeds_v1, dist_v1, SAFE_TIME, DECEL_RATE, road_limit_speed=200.0, min_severity_ratio=0.5)
    sharpest_out_v1, _ = carrot_navi_route_camera_style(speeds_v1, dist_v1, SAFE_TIME, DECEL_RATE)
    check("[179차 후속] ratio=0.5(curve1 기준 설정) 게이트를 검증1에 적용해도 여전히 "
          "noise 지점을 apex로 선택(=게이트가 목적을 달성 못 함, sharpest보다 여전히 높은/불안전한 값)",
          gated_out_v1 > sharpest_out_v1 + 5.0,
          f"gated={gated_out_v1:.1f}, sharpest(기존, 원거리 실제커브 타겟)={sharpest_out_v1:.1f}")

    # 8) [179차 후속, 대안1(상대적 심각도 비교) 실함수 검증, POSITIVE 확정]
    #    검증2(연속 S자, curve1=0.010)와 검증1(근접잡음 vs 원거리 실제커브)에
    #    실제 게이트 함수(carrot_navi_route_camera_style_nearest_relative_gated,
    #    기본값 relative_severity_ratio=0.85)를 그대로 호출해 두 조건을 동시에
    #    만족하는지 확인(위 7번은 거리 인덱스만 보는 약식 스캔이었고, 이번엔
    #    실제 프로덕션 시그니처와 동일한 함수 호출 + out_speed 비교로 확정).
    gated_v2_out, _ = carrot_navi_route_camera_style_nearest_relative_gated(
        speeds_v2, dist_v2, SAFE_TIME, DECEL_RATE, road_limit_speed=110.0)
    nearest_v2_out, _ = carrot_navi_route_camera_style_nearest(
        speeds_v2, dist_v2, SAFE_TIME, DECEL_RATE, road_limit_speed=110.0)
    check("[179차 후속 대안1] 검증2(curve1): relative_gated(0.85)가 게이트 없는 "
          "nearest와 동일한 apex(1차)를 선택 -- curve1 대응력 유지됨",
          abs(gated_v2_out - nearest_v2_out) < 0.5,
          f"gated={gated_v2_out:.2f}, nearest(게이트없음)={nearest_v2_out:.2f}")

    gated_v1_out, _ = carrot_navi_route_camera_style_nearest_relative_gated(
        speeds_v1, dist_v1, SAFE_TIME, DECEL_RATE, road_limit_speed=200.0)
    nearest_v1_out, _ = carrot_navi_route_camera_style_nearest(
        speeds_v1, dist_v1, SAFE_TIME, DECEL_RATE, road_limit_speed=200.0)
    sharpest_v1_out, _ = carrot_navi_route_camera_style(speeds_v1, dist_v1, SAFE_TIME, DECEL_RATE)
    check("[179차 후속 대안1] 검증1(잡음 vs 원거리 실제커브): relative_gated(0.85)가 "
          "잡음(10m)을 차단하고 sharpest(원거리 실제커브 타겟)와 정확히 일치하는 값을 냄 "
          "-- 게이트 없는 nearest(잡음에 고정)와 뚜렷이 구분됨",
          abs(gated_v1_out - sharpest_v1_out) < 0.5 and gated_v1_out < nearest_v1_out - 5.0,
          f"gated={gated_v1_out:.1f}, nearest(게이트없음)={nearest_v1_out:.1f}, "
          f"sharpest(기준)={sharpest_v1_out:.1f}")

    # 9) [179차 후속, 대안2(연속성/지속성 기준) 실함수 검증, NEGATIVE 확정]
    #    min_persist_points=2를 검증2(curve1)에 적용하면 curve1(단일 지점만
    #    threshold 통과)이 걸러지고 더 먼 curve2(2개 연속 통과)로 apex가
    #    이동해버려 -- 원래 목적(1차 자신의 곡률에 맞는 감속)이 깨지는지 확인.
    persist_v2_out, _ = carrot_navi_route_camera_style_nearest_persistence_gated(
        speeds_v2, dist_v2, SAFE_TIME, DECEL_RATE, road_limit_speed=110.0, min_persist_points=2)
    check("[179차 후속 대안2] 검증2(curve1): persistence_gated(min=2)를 적용하면 "
          "1차 고유속도(nearest 기준값)에서 벗어남 -- 1차 대응력 상실 확인(NEGATIVE)",
          abs(persist_v2_out - nearest_v2_out) > 1.0,
          f"persistence_gated={persist_v2_out:.2f}, nearest(게이트없음, 기준)={nearest_v2_out:.2f}")

    print(f"\n{passed} PASS / {failed} FAIL")
    return failed == 0


if __name__ == "__main__":
    if "--unit-tests" in sys.argv:
        ok = _run_unit_tests()
        sys.exit(0 if ok else 1)
    print(__doc__)
