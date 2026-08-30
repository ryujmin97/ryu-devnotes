#!/usr/bin/env python3
"""
157차 신규 - 사용자 제안 재설계("route는 다음 최대곡률(apex) 지점까지의
거리만으로 사전감속률을 결정하고, apex 통과 시 vturn에 넘긴 뒤 다음 apex를
다시 찾는다") 시뮬레이션 검증.

배경(FINDINGS.md 156차 -> 157차):
156차에서 확인한 "route= HUD 16초+ 고정" 현상을 다시 파고든 결과, 원인이
147차가 고친 "coarse chord가 급커브를 놓침"과는 별개로 **carrot_man.py
carrot_navi_route()의 `if abs(curvature) < 0.02: speed = max(speed,
nRoadLimitSpeed)` 플로어 로직 자체가 과도하게 넓은 범위를 덮는 것**임을
확인. V_CURVE_LOOKUP_BP/VALS 테이블을 그대로 보간하면 curvature=0.0091
(R=110m)은 이미 ~56km/h급 커브로 계산되는데, 0.02 임계값 미만이라는
이유만으로 그 값이 통째로 버려지고 nRoadLimitSpeed(도로 제한속도,
104~118 관측)로 다시 올려붙여진다. 즉 R 50m~800m 사이의 "완만하지만
실제로는 감속이 필요한" 연속 커브 전체가 이 플로어 하나로 무력화되고
있었다 -- 147차 fine-sample 패치는 "40m chord가 61m 급커브 1개를 평활화"
케이스만 고쳤을 뿐, 이 플로어 자체의 범위 문제는 그대로 남아있었음.

사용자 제안 재설계는 이 구조를 다음과 같이 단순화한다:
  1. lookahead 윈도우 내 모든 포인트의 curvature-speed를 계산(플로어는
     진짜 노이즈 수준(negligible_curv, 기본 0.001=R>1000m)에만 적용).
  2. 그 중 speed가 가장 낮은 지점(= 다음 apex)을 찾는다.
  3. apex까지의 거리 하나만으로 "지금부터 accel_limit(필요시 상한까지
     부스트)으로 감속하면 apex에서 정확히 apex_speed에 도달"하는 물리
     공식 하나로 route_speed를 계산한다(153차 근정지 강제감속 로직을
     "근정지급 한정"에서 "모든 apex"로 일반화한 형태 -- 153차 로직이
     이 설계의 특수 사례로 흡수됨).
  4. apex를 지나면(매 20Hz 재계산이라 상태 저장 불필요) 다음 프레임에는
     윈도우가 전진해 자동으로 다음 apex가 선택됨 -- 명시적 "리셋" 코드
     불필요(이미 매 프레임 무상태 재계산 구조).
  5. "apex 이후는 vturn에 넘김"도 기존 min() arbitration으로 이미 성립 --
     apex 근방/통과 후 route가 더 낮은 값을 낼 이유가 없으므로 자연히
     vturn이 이김. 별도 handoff 코드 불필요.

기존 역방향 DP(carrot_navi_route_dp, ROUTE_ENTRY_MARGIN_KPH/time_wait
스케줄링)를 이 5줄짜리 물리 공식 하나로 완전히 대체한다 -- "간단하게
생각해야 한다"는 사용자 요구를 그대로 코드 구조에 반영.

**주의**: ROUTE_ENTRY_MARGIN_KPH(91차, route가 vturn보다 먼저 개입하도록
당기는 마진)는 이번 v1 재설계에 포함하지 않음(단순화 우선, 실측 후
재도입 여부 판단 -- 아래 "알려진 단순화" 참고).

사용:
    python3 sim_route_apex_redesign.py --unit-tests
"""
import math
import sys

sys.path.insert(0, ".")
from sim_route_boundary_ramp_limiter import RampLimiterState

DISTANCE_INTERVAL = 10.0
ROUTE_SPEED_LOOP_DT = 0.05
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265.,
                     1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]


def _interp(x, bp, vals):
    if x <= bp[0]:
        return vals[0]
    if x >= bp[-1]:
        return vals[-1]
    for i in range(len(bp) - 1):
        if bp[i] <= x <= bp[i + 1]:
            t = (x - bp[i]) / (bp[i + 1] - bp[i])
            return vals[i] + t * (vals[i + 1] - vals[i])
    return vals[-1]


def curve_speed(curvature, road_limit_speed, floor_threshold):
    """공통 곡률->속도 변환. floor_threshold=0.02면 기존(baseline, 버그
    포함) 동작과 100% 동일, floor_threshold를 낮추면(예: 0.001) 그 버그
    범위를 줄인 재설계 동작."""
    speed = _interp(abs(curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
    if abs(curvature) < floor_threshold:
        speed = max(speed, road_limit_speed)
    return speed


# ---------------------------------------------------------------------------
# Baseline: 기존 프로덕션(carrot_man.py L608-698, 153차 근정지 강제감속 포함)
# 을 그대로 재현. floor_threshold=0.02(기존 버그 그대로) 고정.
# ---------------------------------------------------------------------------
ROUTE_ENTRY_MARGIN_KPH = 25.0
VTURN_SAFE_TIME = 2.0
ROUTE_NEAR_STOP_TARGET_KPH = 15.0


def carrot_navi_route_baseline(speeds, distances, v_ego_kph, accel_limit_mss,
                                vturn_decel_rate=1.2):
    if not speeds:
        return 300.0, accel_limit_mss * 3.6
    accel_limit_kmh = accel_limit_mss * 3.6
    out_speeds = [0.0] * len(speeds)
    out_speeds[-1] = speeds[-1]
    time_wait = 0.0
    route_prev_state = None
    for i in range(len(speeds) - 2, -1, -1):
        target_speed = speeds[i]
        next_out_speed = out_speeds[i + 1]
        if target_speed < next_out_speed:
            margin_target_speed = max(0.0, target_speed - ROUTE_ENTRY_MARGIN_KPH)
            time_delay = max(0.0, (v_ego_kph - margin_target_speed) / accel_limit_kmh) if accel_limit_kmh > 0 else 0.0
            time_wait = -time_delay
            route_prev_state = "decel"
        elif target_speed > next_out_speed and route_prev_state == "decel":
            time_wait += VTURN_SAFE_TIME
            route_prev_state = "accel"
        time_interval = DISTANCE_INTERVAL / (next_out_speed / 3.6) if next_out_speed > 0 else 0.0
        time_apply = min(time_interval, max(0.0, time_interval + time_wait))
        max_allowed_speed = next_out_speed + (accel_limit_kmh * time_apply)
        out_speeds[i] = min(target_speed, max_allowed_speed)
        time_wait += min(2.0, time_interval)

    # 153차 근정지 강제감속 후처리
    min_idx = min(range(len(speeds)), key=lambda k: speeds[k])
    if speeds[min_idx] <= ROUTE_NEAR_STOP_TARGET_KPH and distances[min_idx] > 0:
        v_ego_ms = v_ego_kph / 3.6
        target_ms = speeds[min_idx] / 3.6
        required_accel_mss = max(0.0, (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * distances[min_idx]))
        if required_accel_mss > accel_limit_mss:
            applied_accel_mss = min(required_accel_mss, vturn_decel_rate)
            for i in range(min_idx + 1):
                dist_to_corner = max(0.0, distances[min_idx] - distances[i])
                forced_ms_sq = target_ms ** 2 + 2.0 * applied_accel_mss * dist_to_corner
                forced_kph = (forced_ms_sq ** 0.5) * 3.6 if forced_ms_sq > 0 else speeds[min_idx]
                out_speeds[i] = min(out_speeds[i], forced_kph)
            accel_limit_kmh = max(accel_limit_kmh, applied_accel_mss * 3.6)

    return out_speeds[0], accel_limit_kmh


# ---------------------------------------------------------------------------
# 재설계: 단일 apex 거리기반 감속 (157차, 사용자 제안)
# ---------------------------------------------------------------------------
def carrot_navi_route_apex(speeds, distances, v_ego_kph, accel_limit_mss,
                            max_accel_mss=1.2):
    if not speeds:
        return 300.0, accel_limit_mss * 3.6
    apex_idx = min(range(len(speeds)), key=lambda k: speeds[k])
    apex_dist = distances[apex_idx]
    apex_speed = speeds[apex_idx]
    if apex_dist <= 0:
        return apex_speed, accel_limit_mss * 3.6
    v_ego_ms = v_ego_kph / 3.6
    target_ms = apex_speed / 3.6
    required_accel_mss = max(0.0, (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * apex_dist))
    applied_accel_mss = accel_limit_mss if required_accel_mss <= accel_limit_mss \
        else min(required_accel_mss, max_accel_mss)
    out_ms_sq = target_ms ** 2 + 2.0 * applied_accel_mss * apex_dist
    out_speed = (out_ms_sq ** 0.5) * 3.6 if out_ms_sq > 0 else apex_speed
    return min(out_speed, 300.0), applied_accel_mss * 3.6


# ---------------------------------------------------------------------------
# 도로 형상 생성기 -- 절대좌표(도로 시작점 기준) 곡률함수를 반환한다.
# simulate_road()가 매 프레임 "차량 현재 위치 ~ 도로 끝"까지를 이 함수로
# 샘플링해 상대거리 배열(distances)을 만든다(production의 "현재 위치부터
# lookahead_m까지" 구조와 동일).
# ---------------------------------------------------------------------------
def winding_road_curvature_fn(curv_lo=0.002, curv_hi=0.013, period_m=120.0):
    """156차 실측(curvature 0.002~0.013, 16.4초 지속)을 모사하는 연속
    완만한 굽이길. sinusoidal로 curv_lo~curv_hi 사이를 오간다(절대좌표 기준)."""
    def fn(abs_d):
        return curv_lo + (curv_hi - curv_lo) * 0.5 * (1 - math.cos(2 * math.pi * abs_d / period_m))
    return fn


def straight_road_curvature_fn(noise=0.0003):
    return lambda abs_d: noise


def single_sharp_curve_curvature_fn(apex_dist_m, curvature=0.0165):
    """147차 실측(R=61m 교차로 우회전) 재현. apex 지점만 급커브, 나머지는 직선."""
    def fn(abs_d):
        return curvature if abs(abs_d - apex_dist_m) < DISTANCE_INTERVAL / 2 else 0.0003
    return fn


def sample_curvature_road(curvature_fn, pos, road_len_m, road_limit_speed, floor_threshold):
    """현재 위치 pos부터 도로 끝(road_len_m)까지 10m 간격으로 샘플링해
    (speeds, distances) 반환. distances는 pos 기준 상대거리(10,20,...)."""
    n_points = max(1, round((road_len_m - pos) / DISTANCE_INTERVAL))
    distances = [DISTANCE_INTERVAL * (i + 1) for i in range(n_points)]
    speeds = [curve_speed(curvature_fn(pos + d), road_limit_speed, floor_threshold) for d in distances]
    return speeds, distances


def sample_near_stop(pos, corner_abs_m, target_kph=8.0):
    """152/153차 근정지급 코너(절대좌표 corner_abs_m). 마지막 지점만
    target, 나머지는 무제한."""
    remaining = corner_abs_m - pos
    if remaining <= 0:
        return [target_kph], [max(0.1, remaining + DISTANCE_INTERVAL)]
    n_points = max(1, round(remaining / DISTANCE_INTERVAL))
    distances = [DISTANCE_INTERVAL * (i + 1) for i in range(n_points)]
    distances[-1] = remaining
    speeds = [200.0] * (n_points - 1) + [target_kph]
    return speeds, distances


# ---------------------------------------------------------------------------
# 다중프레임 접근 시뮬레이션 (132차 램프리미터 포함, 완벽추종 가정 -
# sim_route_near_stop_accel_boost.py::simulate_approach와 동일 방법론)
# ---------------------------------------------------------------------------
def simulate_road(sampler, road_len_m, v_ego_kph_start, accel_limit_mss,
                   algo, max_accel_mss=1.2, dt=0.05, max_steps=6000):
    """sampler(pos) -> (speeds, distances), pos=현재까지 주행한 절대거리."""
    v_ego_kph = v_ego_kph_start
    pos = 0.0
    t = 0.0
    limiter = RampLimiterState()
    trace = []
    steps = 0
    min_v = v_ego_kph
    while pos < road_len_m and steps < max_steps:
        speeds, distances = sampler(pos)
        if algo == "baseline":
            raw_out, accel_limit_kmh = carrot_navi_route_baseline(
                speeds, distances, v_ego_kph, accel_limit_mss)
        else:
            raw_out, accel_limit_kmh = carrot_navi_route_apex(
                speeds, distances, v_ego_kph, accel_limit_mss, max_accel_mss)
        out_speed = limiter.apply(raw_out, accel_limit_kmh, dt)
        v_ego_kph = out_speed
        min_v = min(min_v, v_ego_kph)
        pos += (v_ego_kph / 3.6) * dt
        t += dt
        steps += 1
        trace.append((round(t, 2), round(pos, 1), round(v_ego_kph, 1)))
    return v_ego_kph, min_v, t, trace


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

    # 1) 156차 재현: 연속 굽이길, road_limit=110, v_ego=68kph(19m/s) 시작
    #    도로 총 600m 주행 -- baseline은 거의 감속 안 함(플로어 버그),
    #    apex 재설계는 최소속도 지점에서 실제 커브속도(~48~56kph대)까지
    #    사전감속해야 한다.
    curv_fn = winding_road_curvature_fn()
    sampler_base = lambda pos: sample_curvature_road(curv_fn, pos, 600.0, 110.0, 0.02)
    sampler_apex = lambda pos: sample_curvature_road(curv_fn, pos, 600.0, 110.0, 0.001)
    _, min_v_base, _, _ = simulate_road(sampler_base, 600.0, 68.0, 0.7, "baseline")
    _, min_v_apex, _, _ = simulate_road(sampler_apex, 600.0, 68.0, 0.7, "apex")
    check("156차 winding road: baseline은 전혀 반응 안 함(=최소속도가 출발속도 그대로, 플로어 버그 재현)",
          abs(min_v_base - 68.0) < 0.5, f"min_v_base={min_v_base:.1f}")
    check("156차 winding road: apex 재설계는 실제 커브속도까지 감속",
          min_v_apex < 65.0, f"min_v_apex={min_v_apex:.1f}")

    # 2) 직선(노이즈만): 두 알고리즘 모두 이 시점(pos=0, 정지 상태 기준)
    #    raw out_speed가 road_limit(110)보다 훨씬 높아야 함(=제약을 걸지
    #    않음, 오탐 없음). 회귀 없음 확인은 raw 단일계산으로 직접 검증.
    straight_fn = straight_road_curvature_fn()
    speeds_s_base, dist_s = sample_curvature_road(straight_fn, 0.0, 600.0, 110.0, 0.02)
    speeds_s_apex, _ = sample_curvature_road(straight_fn, 0.0, 600.0, 110.0, 0.001)
    raw_base_s, _ = carrot_navi_route_baseline(speeds_s_base, dist_s, 68.0, 0.7)
    raw_apex_s, _ = carrot_navi_route_apex(speeds_s_apex, dist_s, 68.0, 0.7)
    check("직선도로: baseline 회귀 없음(제약 없음 유지)", raw_base_s > 150.0, f"{raw_base_s:.1f}")
    check("직선도로: apex 재설계도 회귀 없음(오탐 없음)", raw_apex_s > 150.0, f"{raw_apex_s:.1f}")

    # 3) 147차류 단일 급커브(curvature=0.0165, apex 절대위치=300m, v_ego=90):
    #    이 curvature는 0.02 미만이라 baseline은 fine-sample 보정 없이는
    #    (이 축소 재현 테스트엔 fine-sample 자체를 넣지 않았음) **똑같이
    #    플로어 버그에 걸려 반응하지 않는다** -- 이는 회귀가 아니라 "coarse
    #    chord로 놓치는 정도가 아니라 플로어 임계값 자체가 근본 원인"이라는
    #    157차 발견을 한 번 더 보여주는 것. apex 재설계만 정상 감속하면 됨.
    sharp_fn = single_sharp_curve_curvature_fn(apex_dist_m=300.0)
    sampler_base_c = lambda pos: sample_curvature_road(sharp_fn, pos, 400.0, 110.0, 0.02)
    sampler_apex_c = lambda pos: sample_curvature_road(sharp_fn, pos, 400.0, 110.0, 0.001)
    _, min_v_base_c, _, _ = simulate_road(sampler_base_c, 400.0, 90.0, 0.7, "baseline")
    _, min_v_apex_c, _, _ = simulate_road(sampler_apex_c, 400.0, 90.0, 0.7, "apex")
    check("147차류 단일커브(0.02 미만, fine-sample 미적용 축소재현): baseline도 플로어 버그로 무반응(참고용, 회귀 아님)",
          abs(min_v_base_c - 90.0) < 0.5, f"{min_v_base_c:.1f}")
    check("147차류 단일커브: apex 재설계는 fine-sample 없이도 정상 감속(임계값 자체를 안 쓰므로 chord 문제에 안 걸림)",
          min_v_apex_c < 60.0, f"{min_v_apex_c:.1f}")

    # 4) 152/153차 근정지 코너(target=10.7kph, corner 절대위치=280m,
    #    v_ego=90kph 시작, 149차 근사조건과 동일 파라미터):
    #    apex 재설계는 153차 forced-decel과 동일한 일반화 로직이므로
    #    153차 실측(초과분 0.0kph)과 동등하거나 더 나은 결과가 나와야 함.
    sampler_ns = lambda pos: sample_near_stop(pos, 280.0, target_kph=10.7)
    final_v, _, _, _ = simulate_road(sampler_ns, 280.0, 90.0, 0.7, "apex")
    check("152/153차 근정지 재현: apex 재설계도 목표속도 근접 도달",
          final_v < 10.7 + 1.0, f"final_v={final_v:.1f} (target=10.7)")

    print(f"\n{passed} PASS / {failed} FAIL")
    return failed == 0


if __name__ == "__main__":
    if "--unit-tests" in sys.argv:
        ok = _run_unit_tests()
        sys.exit(0 if ok else 1)
    print(__doc__)
