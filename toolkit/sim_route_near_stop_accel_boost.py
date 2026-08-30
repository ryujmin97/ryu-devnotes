#!/usr/bin/env python3
"""
150차 신규 - carrot_man.py::carrot_navi_route()의 "역방향 accel-limited DP"
(target_speed 배열 -> out_speed 스케줄) 핵심 로직을 독립 재현하고, 150차
패치(근정지급 코너 한정 accel_limit 부스트: ROUTE_NEAR_STOP_TARGET_KPH,
ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS)를 켰을 때/껐을 때(=패치 전/후)를 비교한다.

기존 toolkit의 replay_route_ramp_limiter_direct.py / sim_route_boundary_ramp_limiter.py
는 132차 프레임간 스무딩(out_speed 사후 클램프)만 재현하고, 이 배열->스케줄
변환 DP 자체는 재현하지 않는다(README 확인, 149차/150차 시점 기준 없음) --
그래서 신규 작성함.

용도 1: 합성 시나리오로 패치 로직 자체를 단위검증(패치 미적용 시 기존 동작과
        diff=0, 근정지급 아닌 일반 커브는 패치 켜져 있어도 diff=0, 근정지급
        코너에서만 필요시 부스트 발동 & 상한 클램프 확인).
용도 2: --with-navi-paths로 뽑은 실측 CSV(naviPaths/desiredSpeed 컬럼 필요)에
        기록된 실제 naviPaths+vEgo를 그대로 넣어, "이 프레임에서 실제로
        route가 계산했을 out_speed"를 패치 전/후로 재현 -- 실측
        desiredSpeed(당시 선택된 src의 값, cam/vturn 등)와 비교해 패치 적용 시
        route가 arbitration(min())에서 이 값보다 낮아져 선택됐을지 근사 판정.
        **주의**: cam/vturn 자체의 값은 패치와 무관하게 실측 그대로 두므로
        "route가 이겼을지"는 근사(다른 소스가 패치로 인해 간접적으로
        달라지는 2차 효과는 반영 안 됨).

사용:
    python3 sim_route_near_stop_accel_boost.py --unit-tests
    python3 sim_route_near_stop_accel_boost.py <route.csv> --accel 0.70
"""
import argparse
import sys

sys.path.insert(0, ".")
from analysis_helpers import load_csv, parse_navi_paths, recompute_route_curvature_speed
from sim_route_boundary_ramp_limiter import RampLimiterState

# carrot_man.py와 동일 상수 (150차 패치)
ROUTE_ENTRY_MARGIN_KPH = 25.0
VTURN_SAFE_TIME = 2.0
DISTANCE_INTERVAL = 10.0
ROUTE_NEAR_STOP_TARGET_KPH = 15.0
ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS = 1.2


def carrot_navi_route_dp(speeds, distances, v_ego_kph, accel_limit_mss,
                          route_entry_margin_kph=ROUTE_ENTRY_MARGIN_KPH,
                          vturn_safe_time=VTURN_SAFE_TIME,
                          apply_near_stop_boost=False,
                          near_stop_target_kph=ROUTE_NEAR_STOP_TARGET_KPH,
                          boost_max_mss=ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS):
    """carrot_man.py carrot_navi_route() L595-655(150차 패치 포함)의
    "역방향 accel-limited DP" 핵심 로직을 독립 함수로 재현. speeds/distances는
    같은 길이의 리스트(가까운 순=index 0). apply_near_stop_boost=False면
    150차 패치 이전(기존) 동작과 100% 동일 -- 회귀 없음 확인용.

    반환: (out_speeds, accel_limit_kmh) -- accel_limit_kmh는 이번 사이클에
    실제로 쓰인 값(부스트 적용 시 boost_max_mss까지 상향된 값)을 그대로
    반환한다. production(carrot_man.py L723)의 132차 프레임간 램프리미터가
    바로 이 지역변수 accel_limit_kmh를 그대로 재사용하므로(부스트와
    램프리미터가 같은 값을 공유), 호출부(simulate_approach)에서 램프리미터를
    정확히 재현하려면 이 값이 필요하다.
    """
    if not speeds:
        return [], 0.0

    accel_limit = accel_limit_mss
    if apply_near_stop_boost and speeds:
        min_idx = min(range(len(speeds)), key=lambda k: speeds[k])
        if speeds[min_idx] <= near_stop_target_kph and distances[min_idx] > 0:
            v_ego_ms = v_ego_kph / 3.6
            target_ms = speeds[min_idx] / 3.6
            required_accel_mss = max(0.0, (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * distances[min_idx]))
            accel_limit = min(max(accel_limit, required_accel_mss), boost_max_mss)
    accel_limit_kmh = accel_limit * 3.6

    out_speeds = [0.0] * len(speeds)
    out_speeds[-1] = speeds[-1]

    time_wait = 0.0
    route_prev_state = None
    for i in range(len(speeds) - 2, -1, -1):
        target_speed = speeds[i]
        next_out_speed = out_speeds[i + 1]

        if target_speed < next_out_speed:
            margin_target_speed = max(0.0, target_speed - route_entry_margin_kph)
            time_delay = max(0.0, (v_ego_kph - margin_target_speed) / accel_limit_kmh) if accel_limit_kmh > 0 else 0.0
            time_wait = -time_delay
            route_prev_state = "decel"
        elif target_speed > next_out_speed and route_prev_state == "decel":
            time_wait += vturn_safe_time
            route_prev_state = "accel"

        time_interval = DISTANCE_INTERVAL / (next_out_speed / 3.6) if next_out_speed > 0 else 0.0
        time_apply = min(time_interval, max(0.0, time_interval + time_wait))
        max_allowed_speed = next_out_speed + (accel_limit_kmh * time_apply)
        adjusted_speed = min(target_speed, max_allowed_speed)
        time_wait += min(2.0, time_interval)
        out_speeds[i] = adjusted_speed

    return out_speeds, accel_limit_kmh


def carrot_navi_route_dp_forced_decel(speeds, distances, v_ego_kph, accel_limit_mss,
                                       route_entry_margin_kph=ROUTE_ENTRY_MARGIN_KPH,
                                       vturn_safe_time=VTURN_SAFE_TIME,
                                       apply_forced_decel=False,
                                       near_stop_target_kph=ROUTE_NEAR_STOP_TARGET_KPH,
                                       max_forced_accel_mss=ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS):
    """152차 옵션1 -- 151차(accel_limit을 부스트해 같은 역방향 DP 재귀에 넣는 방식)의
    실패 원인은 그 재귀의 time_wait/margin 메커니즘이 "accel_limit이 크면 나중에
    더 세게 감속 가능"이라 판단해 현재 시점 감속 권고를 오히려 늦추는 것이었다
    (FINDINGS.md 151차). 이 함수는 그 재귀 자체를 우회한다:

    1. 먼저 기존 DP(`carrot_navi_route_dp`, apply_near_stop_boost=False, 즉 base
       accel_limit)를 그대로 돌려 out_speeds/accel_limit_kmh를 얻는다 -- "감속
       시작 시점" 판단 로직은 전혀 건드리지 않음(151차가 확인한 부작용의 근원을
       원천 차단).
    2. 근정지급 target(<=near_stop_target_kph) 지점(min_idx)을 찾아 "지금 이
       순간부터 등가속도로 감속하면 코너에서 정확히 target에 도달"하는 필요
       감속률(required_accel_mss, 149차/151차와 동일 공식)을 계산한다.
    3. 이 required_accel_mss가 base accel_limit_mss보다 큰(=현재 설정으로는
       물리적으로 못 따라가는) 경우에만, min_idx까지의 각 지점 i에 대해
       "target에서 required_accel_mss로 역산한 등가속도 감속 곡선"을 직접
       계산(sqrt(v^2) 공식, 재귀/time_wait 전혀 개입 안 함)해 out_speeds[i]를
       그 값과 min()으로 덮어쓴다. 이러면 감속 스케줄이 재귀의 "지연 후 급감속"
       왜곡 없이 처음부터 물리적으로 필요한 만큼만 매끄럽게 하강한다.
    4. 132차 프레임간 램프리미터가 이 새 스케줄을 따라잡을 수 있도록,
       accel_limit_kmh도 required_accel_mss 기준으로 상향해 반환한다.

    required_accel_mss가 이미 base accel_limit_mss 이하면(=일반 커브, 굳이
    부스트가 필요 없는 경우) 아무 것도 덮어쓰지 않고 base 결과를 그대로
    반환한다(151차 시나리오 A/B와 동일한 회귀 없음 보장).
    """
    out_speeds, accel_limit_kmh = carrot_navi_route_dp(
        speeds, distances, v_ego_kph, accel_limit_mss,
        route_entry_margin_kph=route_entry_margin_kph,
        vturn_safe_time=vturn_safe_time,
        apply_near_stop_boost=False)

    if not apply_forced_decel or not speeds:
        return out_speeds, accel_limit_kmh

    min_idx = min(range(len(speeds)), key=lambda k: speeds[k])
    if speeds[min_idx] > near_stop_target_kph or distances[min_idx] <= 0:
        return out_speeds, accel_limit_kmh

    v_ego_ms = v_ego_kph / 3.6
    target_ms = speeds[min_idx] / 3.6
    required_accel_mss = max(0.0, (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * distances[min_idx]))

    if required_accel_mss <= accel_limit_mss:
        # 기존 accel_limit으로 이미 물리적으로 충분 -- 덮어쓸 필요 없음(회귀 방지)
        return out_speeds, accel_limit_kmh

    # [152차 옵션1] 감지가 너무 늦어(거리 부족) required_accel_mss가 비현실적으로
    # 커질 수 있음(급브레이크 급의 편의/안전 문제) -- max_forced_accel_mss로 상한
    # 클램프(기본값은 151차와 동일하게 vturn_decel_rate 재사용 1.2 m/s^2). 클램프된
    # 경우 물리적으로 target까지 완전히 못 따라갈 수 있으나(잔여 overshoot),
    # 151차 boost처럼 "감속 시작 자체를 늦추는" 역효과는 구조적으로 없음 --
    # 이 함수는 항상 지금 이 순간부터 즉시 감속 곡선을 강제하기 때문.
    applied_accel_mss = required_accel_mss
    if max_forced_accel_mss is not None:
        applied_accel_mss = min(required_accel_mss, max_forced_accel_mss)

    for i in range(min_idx + 1):
        dist_to_corner = max(0.0, distances[min_idx] - distances[i])
        forced_ms_sq = target_ms ** 2 + 2.0 * applied_accel_mss * dist_to_corner
        forced_kph = (forced_ms_sq ** 0.5) * 3.6 if forced_ms_sq > 0 else speeds[min_idx]
        out_speeds[i] = min(out_speeds[i], forced_kph)

    accel_limit_kmh_forced = max(accel_limit_kmh, applied_accel_mss * 3.6)
    return out_speeds, accel_limit_kmh_forced


def simulate_approach(target_speed_kph, corner_dist_m, v_ego_kph_start, accel_limit_mss,
                       apply_near_stop_boost, dt=0.05, near_stop_target_kph=ROUTE_NEAR_STOP_TARGET_KPH,
                       boost_max_mss=ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS, max_steps=20000,
                       apply_forced_decel=False):
    """단일 정지선/코너(target_speed_kph, 최초 corner_dist_m 지점)에 접근하는
    상황을 20Hz(dt)로 다중 프레임 시뮬레이션한다.

    **150차 계속 수정**: 최초 버전은 매 프레임 2점짜리 배열([far=200kph,
    near=target_speed_kph], 간격 고정 10m)만 만들어 넘겼는데, 이는
    carrot_navi_route()의 실제 구조(10m 간격으로 lookahead 전체(수백m)를
    덮는 배열 -- DP가 `time_wait += min(2.0, time_interval)`로 "감속 시작
    지점"부터 "지금"까지 매 10m 스텝마다 시간 예산을 누적)와 다르다.
    2점 배열은 이 누적 과정 자체가 없어, corner_dist_m이 클수록(=아직
    감속 시작 안 해도 되는 먼 거리) DP가 실제보다 훨씬 적은 시간 예산만
    본 것처럼 오판 -- accel_limit을 올려도(부스트) 효과가 왜곡되어 나타남
    (실측: 패치 후 도달속도가 오히려 더 나쁘게 나왔던 최초 FAIL의 원인).

    이번 버전은 매 프레임 corner_dist_m 스케일에 맞춰 10m 간격 전체
    배열(가까운 순=index 0, 마지막 index만 target_speed_kph, 그 전은
    전부 200kph 무제한 -- 단일 코너 시나리오이므로 다른 곡률 제약 없음)을
    새로 구성해 넘긴다. 이러면 실제 carrot_navi_route()가 매 사이클
    lookahead 전체를 다시 계산하는 것과 동일한 방식이 된다.

    매 프레임 out_speeds[0](배열의 가장 가까운 점, ~20m 앞 기준)을
    "이번 프레임에 차가 실제로 낼 속도"로 그대로 채택(=완벽한 추종 가정,
    차량 동역학 지연 없음 -- 스케줄러 로직 자체의 최종 도달 성능만 보기
    위한 단순화)해 다음 프레임의 v_ego/남은거리를 갱신한다. corner_dist_m
    이하로 도달하면 종료.

    반환: (final_speed_kph, elapsed_s, trace) -- trace는 (t, dist, v_ego,
    raw_out_speed, ramp_limited_out_speed) 리스트(최대 max_steps로 안전장치).
    """
    v_ego_kph = v_ego_kph_start
    dist = corner_dist_m
    t = 0.0
    trace = []
    steps = 0
    # [150차 계속, 핵심 수정] production(carrot_man.py L723)은 이 함수가
    # 매 사이클 새로 계산한 raw out_speed를 그대로 차량에 반영하지 않고,
    # 132차 프레임간 램프리미터(RampLimiterState, 이번 사이클
    # accel_limit_kmh*ROUTE_SPEED_LOOP_DT로 프레임당 변화폭 클램프)를 한 번
    # 더 거친다. 최초 버전은 이 리미터 없이 raw out_speeds[0]을 곧바로
    # v_ego로 채택(텔레포트)해, 매 프레임 전체 배열을 다시 계산하는 이
    # DP가 사실상 "지금 이 순간 순간이동으로 도달 가능한 속도"를 매번
    # 되돌려주는 바람에 accel_limit(부스트 여부 무관)이 실제로 전혀
    # 강제되지 않고 항상 정확히 target에 도달하는 것처럼 보이는
    # 오류(패치 후가 오히려 나쁘게 나온 최초 FAIL의 근본 원인)가 있었음.
    # 램프리미터는 이미 devnotes toolkit에 있는 sim_route_boundary_ramp_limiter.py
    # 의 RampLimiterState를 그대로 재사용(README "먼저 찾는다" 원칙).
    limiter = RampLimiterState()
    while dist > 0 and steps < max_steps:
        # 10m 간격 전체 배열 재구성 (production carrot_navi_route()와 동일 패턴:
        # distance는 10.0에서 시작해 매 포인트마다 += distance_interval).
        n_points = max(1, round(dist / DISTANCE_INTERVAL))
        distances = [DISTANCE_INTERVAL * (i + 1) for i in range(n_points)]
        # 마지막 포인트만 실제 남은 거리(dist)로 스냅 -- 격자 반올림 오차 방지
        distances[-1] = dist
        speeds = [200.0] * (n_points - 1) + [target_speed_kph]
        if apply_forced_decel:
            out_speeds, accel_limit_kmh = carrot_navi_route_dp_forced_decel(
                speeds, distances, v_ego_kph, accel_limit_mss,
                apply_forced_decel=True,
                near_stop_target_kph=near_stop_target_kph,
                max_forced_accel_mss=boost_max_mss)
        else:
            out_speeds, accel_limit_kmh = carrot_navi_route_dp(
                speeds, distances, v_ego_kph, accel_limit_mss,
                apply_near_stop_boost=apply_near_stop_boost,
                near_stop_target_kph=near_stop_target_kph,
                boost_max_mss=boost_max_mss)
        raw_out_speed = out_speeds[0]
        # production과 동일하게 이번 사이클의 accel_limit_kmh(부스트 반영값)로
        # 램프리미터 프레임당 상한을 적용
        out_speed = limiter.apply(raw_out_speed, accel_limit_kmh, dt)
        trace.append((round(t, 2), round(dist, 1), round(v_ego_kph, 1),
                      round(raw_out_speed, 1), round(out_speed, 1)))
        v_ego_kph = out_speed
        dist -= (v_ego_kph / 3.6) * dt
        t += dt
        steps += 1
    return v_ego_kph, t, trace


def _run_unit_tests():
    passed = failed = 0

    def check(name, cond):
        nonlocal passed, failed
        status = "PASS" if cond else "FAIL"
        if cond:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {name}")

    print("=== 시나리오 A: 일반 커브(target=40kph, 근정지급 아님) - 패치 on/off diff=0 ===")
    speeds = [40.0] * 20 + [200.0] * 10
    distances = [DISTANCE_INTERVAL * (i + 2) for i in range(len(speeds))]
    out_before, _ = carrot_navi_route_dp(speeds, distances, v_ego_kph=90.0, accel_limit_mss=0.70,
                                          apply_near_stop_boost=False)
    out_after, _ = carrot_navi_route_dp(speeds, distances, v_ego_kph=90.0, accel_limit_mss=0.70,
                                         apply_near_stop_boost=True)
    diff = max(abs(a - b) for a, b in zip(out_before, out_after))
    check(f"일반 커브 diff=0 (실제 diff={diff:.6f})", diff < 1e-9)

    print("=== 시나리오 B: near_stop_target_kph 임계값 초과(target=20kph) - 부스트 미발동 ===")
    n = 28
    distances_n = [DISTANCE_INTERVAL * (i + 1) for i in range(n)]
    speeds_d = [90.0] * (n - 1) + [20.0]
    out_before_d, _ = carrot_navi_route_dp(speeds_d, distances_n, v_ego_kph=90.0, accel_limit_mss=0.70,
                                            apply_near_stop_boost=False)
    out_after_d, _ = carrot_navi_route_dp(speeds_d, distances_n, v_ego_kph=90.0, accel_limit_mss=0.70,
                                           apply_near_stop_boost=True)
    diff_d = max(abs(a - b) for a, b in zip(out_before_d, out_after_d))
    check(f"target=20kph(임계값 15 초과)는 부스트 미발동, diff=0 (실제 diff={diff_d:.6f})", diff_d < 1e-9)

    print("=== 시나리오 C: 149차 근사 접근(v_ego=90kph, target=10.7kph, 280m) 다중프레임 시뮬레이션 ===")
    final_before, t_before, trace_before = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=280.0, v_ego_kph_start=90.0,
        accel_limit_mss=0.70, apply_near_stop_boost=False)
    final_after, t_after, trace_after = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=280.0, v_ego_kph_start=90.0,
        accel_limit_mss=0.70, apply_near_stop_boost=True)
    print(f"    패치 전: 도달 시 속도={final_before:.1f}kph (경과 {t_before:.1f}s), "
          f"초과분(target 10.7 대비)={final_before-10.7:.1f}kph")
    print(f"    패치 후: 도달 시 속도={final_after:.1f}kph (경과 {t_after:.1f}s), "
          f"초과분(target 10.7 대비)={final_after-10.7:.1f}kph")
    check("패치 후 도달 시 속도가 패치 전보다 낮음(target에 더 근접)",
          final_after < final_before - 5.0)
    check("패치 후에도 여전히 target보다는 높음(상한 1.2 m/s^2로는 완전 해결은 못함, 설계대로)",
          final_after > 10.7)

    print("=== 시나리오 D: 149차 실측값 그대로(v_ego=109.6kph, target=10.7kph, 감지~arrive 19.2s 근사) ===")
    # 149차/150차 실측: t_detect~t_arrive 19.2s 동안 실제 이동거리를 등속 근사(과대추정 방지 위해
    # 초기속도 109.6kph 그대로 19.2s 유지 시 이동거리로 corner_dist 설정 -- 상한선 근사)
    approx_dist = 109.6 / 3.6 * 19.2
    final_before2, t_before2, _ = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=approx_dist, v_ego_kph_start=109.6,
        accel_limit_mss=0.70, apply_near_stop_boost=False)
    final_after2, t_after2, _ = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=approx_dist, v_ego_kph_start=109.6,
        accel_limit_mss=0.70, apply_near_stop_boost=True)
    print(f"    근사 거리={approx_dist:.0f}m")
    print(f"    패치 전: 도달 시 속도={final_before2:.1f}kph (초과분={final_before2-10.7:.1f}kph)")
    print(f"    패치 후: 도달 시 속도={final_after2:.1f}kph (초과분={final_after2-10.7:.1f}kph)")
    check("실측 근사 조건에서도 패치 후 개선", final_after2 < final_before2 - 5.0)

    print("=== 시나리오 E(152차 옵션1): 일반 커브 회귀 없음 (forced_decel on, 필요감속률<=base라 미발동) ===")
    speeds_e = [40.0] * 20 + [200.0] * 10
    distances_e = [DISTANCE_INTERVAL * (i + 2) for i in range(len(speeds_e))]
    out_base_e, _ = carrot_navi_route_dp(speeds_e, distances_e, v_ego_kph=90.0, accel_limit_mss=0.70,
                                          apply_near_stop_boost=False)
    out_forced_e, _ = carrot_navi_route_dp_forced_decel(speeds_e, distances_e, v_ego_kph=90.0,
                                                          accel_limit_mss=0.70, apply_forced_decel=True)
    diff_e = max(abs(a - b) for a, b in zip(out_base_e, out_forced_e))
    check(f"target=40kph(near_stop_target_kph=15 미만 아님)는 옵션1도 미발동, diff=0 (실제 diff={diff_e:.6f})",
          diff_e < 1e-9)

    print("=== 시나리오 F(152차 옵션1): 149차 근사조건(v_ego=90kph, target=10.7kph, 280m) 다중프레임, "
          "151차 boost와 비교 ===")
    final_boost, t_boost, _ = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=280.0, v_ego_kph_start=90.0,
        accel_limit_mss=0.70, apply_near_stop_boost=True)
    final_forced, t_forced, trace_forced = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=280.0, v_ego_kph_start=90.0,
        accel_limit_mss=0.70, apply_near_stop_boost=False, apply_forced_decel=True)
    print(f"    패치 전(base)      : 도달 시 속도={final_before:.1f}kph (초과분={final_before-10.7:.1f}kph, {t_before:.1f}s)")
    print(f"    151차 boost(NEGATIVE): 도달 시 속도={final_boost:.1f}kph (초과분={final_boost-10.7:.1f}kph, {t_boost:.1f}s)")
    print(f"    152차 옵션1(forced) : 도달 시 속도={final_forced:.1f}kph (초과분={final_forced-10.7:.1f}kph, {t_forced:.1f}s)")
    check("옵션1이 151차 boost보다 나음(초과분 더 작음)", final_forced < final_boost)
    check("옵션1이 base(패치 전)보다 나쁘지 않음(초과분이 base 이하)", final_forced <= final_before + 0.5)

    print("=== 시나리오 G(152차 옵션1): 149차 실측값 그대로(v_ego=109.6kph, ~585m), 151차 boost와 비교 ===")
    final_boost2, t_boost2, _ = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=approx_dist, v_ego_kph_start=109.6,
        accel_limit_mss=0.70, apply_near_stop_boost=True)
    final_forced2, t_forced2, _ = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=approx_dist, v_ego_kph_start=109.6,
        accel_limit_mss=0.70, apply_near_stop_boost=False, apply_forced_decel=True)
    print(f"    패치 전(base)        : 초과분={final_before2-10.7:.1f}kph")
    print(f"    151차 boost(NEGATIVE): 초과분={final_boost2-10.7:.1f}kph")
    print(f"    152차 옵션1(forced) : 초과분={final_forced2-10.7:.1f}kph")
    check("옵션1이 151차 boost보다 나음(실측 근사조건)", final_forced2 < final_boost2)
    check("옵션1이 base보다 나쁘지 않음(실측 근사조건)", final_forced2 <= final_before2 + 0.5)

    print("=== 시나리오 H(152차 옵션1): 극단적 늦은 감지(50m, required_accel>클램프 상한) -- "
          "클램프 적용 시 잔여 overshoot는 남지만 역효과(151차 boost처럼 악화)는 없어야 함 ===")
    final_before_h, _, _ = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=50.0, v_ego_kph_start=90.0,
        accel_limit_mss=0.70, apply_near_stop_boost=False)
    final_boost_h, _, _ = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=50.0, v_ego_kph_start=90.0,
        accel_limit_mss=0.70, apply_near_stop_boost=True)
    final_forced_h, _, _ = simulate_approach(
        target_speed_kph=10.7, corner_dist_m=50.0, v_ego_kph_start=90.0,
        accel_limit_mss=0.70, apply_near_stop_boost=False, apply_forced_decel=True)
    print(f"    패치 전(base)        : 초과분={final_before_h-10.7:.1f}kph")
    print(f"    151차 boost(NEGATIVE): 초과분={final_boost_h-10.7:.1f}kph")
    print(f"    152차 옵션1(forced, 클램프 1.2 m/s^2 적용) : 초과분={final_forced_h-10.7:.1f}kph")
    check("극단적 늦은 감지에서도 옵션1이 base보다 나쁘지 않음(역효과 없음)",
          final_forced_h <= final_before_h + 0.5)
    check("극단적 늦은 감지에서도 옵션1이 151차 boost보다 나쁘지 않음",
          final_forced_h <= final_boost_h + 0.5)

    print(f"\n합계: {passed} PASS / {failed} FAIL")
    return failed == 0


def _run_on_csv(csv_path, accel):
    rows = load_csv(csv_path)
    print(f"loaded {len(rows)} rows from {csv_path}")
    n_checked = n_naq = n_would_flip = 0
    for r in rows:
        naq = r.get("naviPaths", "")
        if not naq:
            continue
        n_naq += 1
        points, distances = parse_navi_paths(naq)
        recomputed = recompute_route_curvature_speed(points, distances, sample=4, sample_fine=1)
        if not recomputed:
            continue
        distances_r = [d for d, c, s in recomputed]
        speeds_r = [s for d, c, s in recomputed]
        try:
            v_ego_kph = float(r.get("vEgo")) * 3.6
            recorded_desired = float(r.get("desiredSpeed"))
            recorded_src = r.get("src", "")
        except (TypeError, ValueError):
            continue
        n_checked += 1
        out_before, _ = carrot_navi_route_dp(speeds_r, distances_r, v_ego_kph, accel,
                                              apply_near_stop_boost=False)
        out_after, _ = carrot_navi_route_dp(speeds_r, distances_r, v_ego_kph, accel,
                                             apply_near_stop_boost=True)
        if not out_before or not out_after:
            continue
        before0, after0 = out_before[0], out_after[0]
        if recorded_src != "route" and after0 < recorded_desired - 0.5 and before0 >= recorded_desired - 0.5:
            n_would_flip += 1
            print(f"  t={r.get('t')}: recorded_src={recorded_src} recorded_desired={recorded_desired:.1f} "
                  f"| route_before={before0:.1f} route_after={after0:.1f} "
                  f"-> 패치 적용 시 route가 이 프레임에서 min()으로 선택됐을 가능성")
    print(f"\nnaviPaths 있는 행: {n_naq}, DP 계산 성공: {n_checked}, "
          f"패치로 arbitration 결과가 바뀌었을 것으로 추정되는 프레임: {n_would_flip}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", help="--with-navi-paths로 뽑은 route.csv")
    ap.add_argument("--accel", type=float, default=0.70, help="AutoNaviSpeedDecelRate(m/s^2), 기본 0.70")
    ap.add_argument("--unit-tests", action="store_true")
    args = ap.parse_args()

    if args.unit_tests or not args.csv:
        ok = _run_unit_tests()
        sys.exit(0 if ok else 1)
    else:
        _run_on_csv(args.csv, args.accel)
