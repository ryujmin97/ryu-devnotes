#!/usr/bin/env python3
"""
198차 v2 (v1 설계 오류 발견 후 재설계).

[v1에서 발견된 설계 오류, 반드시 기록] 최초 설계(calculate_current_speed의
decel_rate 인자 자체를 a_req로 올려서 목표속도를 재계산)는 물리적으로
거꾸로였다. calculate_current_speed(left_dist, safe_speed, safe_time,
decel_rate)는 "지금 decel_rate로 감속을 시작하면 목표에 맞는, 지금 낼 수
있는 최대 허용속도"를 계산하는 함수라, decel_rate를 올리면(더 세게
브레이크를 밟을 각오라고 가정하면) 오히려 "지금은 더 빨리 가도 된다"는
더 높은 out_speed가 나온다(단일프레임 실측: v_ego=90kph/apex=60m/target=30
에서 base(1.2)=47.4kph인데 boosted(3.0)=65.3kph로 **더 높게** 나옴 --
거리부족 상황에서 목표를 오히려 완화해버리는 방향, 명백히 안전하지 않음).
게다가 이건 149/150차(ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS, PARAMS_REGISTRY.md
참고)가 이미 시도했다가 NEGATIVE로 배포 보류된 것과 정확히 같은 실수
패턴(DP decel_rate만 올리고 램프는 그대로 -- 149/150차는 그 반대 조합조차
악화됐다).

[v2 재설계] raw out_speed(=목표속도, calculate_current_speed 호출 자체)는
**전혀 건드리지 않는다** -- base_decel_rate 그대로, 197차와 100% 동일.
대신 vEgo 기반 a_req는 **132/173차 프레임간 램프리미터의 하강 속도
상한(accel_limit_kmh)에만** 반영한다:
  - a_req <= base_decel_rate: 램프도 기존과 동일(base rate) -- 변경 없음.
  - a_req >  base_decel_rate: "이미 comfortable 스케줄보다 뒤처진(실제
    vEgo가 목표보다 여유가 없는) 상황" -- 램프의 하강 상한을
    min(a_req, MAX_DECEL_MSS)로 올려서, 이미 올바르게 낮은 target을 향해
    실제 명령속도가 더 빨리 따라갈 수 있게 한다(target 자체는 안 바뀜).

이 구조는 149/150차와 반대 조합(target 고정, 램프만 조정)이라 "목표를
완화하는" 부작용이 구조적으로 불가능하고, 197차 대비 "여유있는 상황"에서는
완전히 diff-0(램프도 base rate 그대로)이다.

사용:
    python3 sim_route_vego_required_decel_v2.py --unit-tests
"""
import sys

sys.path.insert(0, ".")
from sim_route_apex_redesign import (
    DISTANCE_INTERVAL,
    winding_road_curvature_fn,
    sample_curvature_road,
)
from sim_route_boundary_ramp_limiter import RampLimiterState
from sim_route_camera_style_decel import camera_calculate_current_speed


def calculate_route_required_decel(v_ego_kph, apex_dist, target_speed_kph):
    """(변경 없음, v1과 동일) 현재 vEgo에서 apex_dist(m) 이내에
    target_speed_kph까지 도달하기 위해 "지금 이 순간" 필요한 감속도(m/s^2).
    이 값은 197차 raw out_speed 계산에는 쓰이지 않고, 아래 램프리미터
    하강 상한에만 쓰인다."""
    if apex_dist <= 0:
        return 0.0
    v_ego = max(0.0, v_ego_kph) / 3.6
    v_target = max(0.0, target_speed_kph) / 3.6
    if v_ego <= v_target:
        return 0.0
    return (v_ego ** 2 - v_target ** 2) / (2.0 * apex_dist)


def carrot_navi_route_197cha(speeds, distances, road_limit_speed=200.0):
    """197차(origin) apex 선택, vEgo/decel 인자와 무관한 순수 지점선택
    부분만 분리(v1의 static_decel_baseline과 동일 선택 로직)."""
    if not speeds:
        return None, None
    candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed]
    if not candidates:
        apex_idx = min(range(len(speeds)), key=lambda k: speeds[k])
    else:
        apex_idx = candidates[0]
    return distances[apex_idx], speeds[apex_idx]


def carrot_navi_route_v2(speeds, distances, v_ego_kph, base_decel_mss,
                          max_decel_mss, safe_time, road_limit_speed=200.0):
    """198차 v2: raw out_speed는 197차와 100% 동일 공식(base_decel_mss
    고정). 반환하는 accel_limit_kmh(램프용)만 a_req 기반으로 동적화."""
    apex_dist, apex_speed = carrot_navi_route_197cha(speeds, distances, road_limit_speed)
    if apex_dist is None:
        return 300.0, base_decel_mss * 3.6, 0.0
    out_speed = camera_calculate_current_speed(apex_dist, apex_speed, safe_time, base_decel_mss)
    out_speed = min(out_speed, 300.0)

    required_decel = calculate_route_required_decel(v_ego_kph, apex_dist, apex_speed)
    if required_decel <= base_decel_mss:
        ramp_decel = base_decel_mss
    else:
        ramp_decel = min(required_decel, max_decel_mss)
    return out_speed, ramp_decel * 3.6, required_decel


def carrot_navi_route_197cha_full(speeds, distances, base_decel_mss, safe_time,
                                   road_limit_speed=200.0):
    """197차(origin) 그대로 -- out_speed/accel_limit_kmh 둘 다 base_decel_mss
    고정. 비교 기준선."""
    apex_dist, apex_speed = carrot_navi_route_197cha(speeds, distances, road_limit_speed)
    if apex_dist is None:
        return 300.0, base_decel_mss * 3.6
    out_speed = camera_calculate_current_speed(apex_dist, apex_speed, safe_time, base_decel_mss)
    return min(out_speed, 300.0), base_decel_mss * 3.6


def simulate_road(sampler, road_len_m, v_ego_kph_start, base_decel_mss,
                   max_decel_mss, safe_time, algo, dt=0.05, max_steps=6000):
    v_ego_kph = v_ego_kph_start
    pos = 0.0
    t = 0.0
    limiter = RampLimiterState(asymmetric_up=True)
    trace = []
    steps = 0
    while pos < road_len_m and steps < max_steps:
        speeds, distances = sampler(pos)
        if algo == "v2":
            raw_out, accel_limit_kmh, req_decel = carrot_navi_route_v2(
                speeds, distances, v_ego_kph, base_decel_mss, max_decel_mss, safe_time)
        else:
            raw_out, accel_limit_kmh = carrot_navi_route_197cha_full(
                speeds, distances, base_decel_mss, safe_time)
            req_decel = 0.0
        out_speed = limiter.apply(raw_out, accel_limit_kmh, dt)
        if raw_out >= 299.999:
            # [시뮬레이션 단순화 주의] production에서는 route=300(제약없음)이
            # 다른 source와의 arbitration(min())에 들어갈 뿐 실제 vEgo를
            # 300으로 끌어올리지 않는다. 이 단순 모델은 route out_speed를
            # 곧 v_ego로 취급하므로, 센티널(제약없음)일 때는 현재 속도를
            # 그대로 유지한 것으로 간주한다(순수 route 단독 시나리오 검증
            # 목적 -- 다른 source/크루즈 로직은 이 스크립트 범위 밖).
            out_speed = v_ego_kph
        v_ego_kph = out_speed
        pos += (v_ego_kph / 3.6) * dt
        t += dt
        steps += 1
        trace.append((round(t, 2), round(pos, 1), round(v_ego_kph, 1), round(raw_out, 1), round(req_decel, 2)))
    return v_ego_kph, t, trace


def late_discovery_sampler(pos, apex_abs_m=90.0, target_kph=30.0, visible_from_m=55.0):
    """apex_abs_m - pos > visible_from_m인 동안은 커브가 lookahead/곡률
    계산에 아직 안 잡힌 것으로 가정(모두 무제한 200kph) -- 실제로는 GPS
    폴리라인 갱신 지연/lookahead 캡 등으로 발생 가능한 "뒤늦은 발견"을
    단순화해서 재현. visible_from_m 이내로 들어오면 그제서야 실제
    목표속도가 보인다."""
    remaining = apex_abs_m - pos
    if remaining <= 0:
        return [target_kph], [max(0.1, remaining + DISTANCE_INTERVAL)]
    if remaining > visible_from_m:
        # 아직 안 보임 -- carrot_navi_route()가 navi_points_active=False나
        # 곡률 데이터 없음일 때 반환하는 것과 동일하게 "제약 없음"(빈
        # 리스트 -> out_speed=300 센티널)으로 표현한다. 200kph 같은
        # 가짜 근접 target을 채우면 안 됨(아래에서 실제로 재현된 버그:
        # 그 값 자체를 apex로 오인해 out_speed가 300+ 로 폭주).
        return [], []
    n_points = max(1, round(remaining / DISTANCE_INTERVAL))
    distances = [DISTANCE_INTERVAL * (i + 1) for i in range(n_points)]
    distances[-1] = remaining
    speeds = [target_kph] * n_points
    return speeds, distances


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

    BASE = 1.2
    MAXD = 3.0
    SAFE_TIME = 2.0

    # 1) raw out_speed는 v2와 197차가 항상 완전히 동일해야 함(단일프레임,
    #    여유/거리부족 두 경우 모두) -- 이번 설계의 핵심 불변식.
    speeds_short, distances_short = [30.0], [60.0]
    out_v2, lim_v2, req = carrot_navi_route_v2(speeds_short, distances_short, 90.0, BASE, MAXD, SAFE_TIME)
    out_197, lim_197 = carrot_navi_route_197cha_full(speeds_short, distances_short, BASE, SAFE_TIME)
    check("[핵심 불변식] raw out_speed(목표속도)는 v2와 197차가 항상 동일(target 자체는 안 건드림)",
          abs(out_v2 - out_197) < 1e-9, f"v2={out_v2:.3f}, 197cha={out_197:.3f}")
    check("거리부족 상황에서 램프 하강상한(accel_limit_kmh)만 v2가 197차보다 커짐(더 빨리 따라감)",
          lim_v2 > lim_197 + 0.1, f"lim_v2={lim_v2:.2f}, lim_197={lim_197:.2f}, req_decel={req:.2f}mss")
    check("램프 하강상한도 MAXD를 넘지 않음",
          lim_v2 <= MAXD * 3.6 + 1e-6)

    # 2) 여유있는 상황 -- 램프도 diff-0
    speeds_ample = [30.0] * 5
    distances_ample = list(range(60, 360, 60))
    out_a, lim_a, req_a = carrot_navi_route_v2(speeds_ample, distances_ample, 50.0, BASE, MAXD, SAFE_TIME)
    out_a197, lim_a197 = carrot_navi_route_197cha_full(speeds_ample, distances_ample, BASE, SAFE_TIME)
    check("여유있는 거리(a_req<=base)에서는 v2가 197차와 완전히 동일(target+램프 둘 다, diff-0)",
          abs(out_a - out_a197) < 1e-9 and abs(lim_a - lim_a197) < 1e-9,
          f"out: {out_a:.3f} vs {out_a197:.3f}, lim: {lim_a:.3f} vs {lim_a197:.3f}")

    # 3) [핵심, 실제 위험 시나리오] "이미 앞 커브 때문에 감속 중이던(=
    #    RampLimiterState.prev_out이 None이 아닌, 132차 리셋 예외가 이미
    #    소진된) 상태에서 더 급한 커브가 candidates[0]로 갱신"되는 상황을
    #    직접 재현한다 -- late_discovery_sampler류("제약없음"에서 갑자기
    #    나타남)는 132차의 "제약없음->있음 전환 시 리미터 리셋" 규칙 덕에
    #    첫 프레임이 무제한 통과되어 버려 실제로는 오버슈트가 재현되지
    #    않았다(위 late-discovery는 회귀 없음 확인용으로만 남김). 아래는
    #    limiter.prev_out을 직접 시딩해 "이미 램프가 걸린 상태"에서 시작,
    #    197차(고정 base 램프)와 v2(동적 램프)의 다중프레임 따라잡기
    #    성능을 비교한다.
    def simulate_seeded(algo, seed_prev_kph, v_ego_start_kph, apex_dist0, target_kph,
                         steps_before_arrival=None):
        limiter = RampLimiterState(asymmetric_up=True)
        limiter.prev_out = seed_prev_kph
        v_ego_kph = v_ego_start_kph
        pos = 0.0
        dt = 0.05
        trace = []
        n = steps_before_arrival or 400
        for _ in range(n):
            remaining = apex_dist0 - pos
            if remaining <= 0:
                break
            speeds, distances = [target_kph], [remaining]
            if algo == "v2":
                req = calculate_route_required_decel(v_ego_kph, remaining, target_kph)
                ramp_decel = BASE if req <= BASE else min(req, MAXD)
                raw_out = camera_calculate_current_speed(remaining, target_kph, SAFE_TIME, BASE)
                accel_limit_kmh = ramp_decel * 3.6
            else:
                raw_out = camera_calculate_current_speed(remaining, target_kph, SAFE_TIME, BASE)
                accel_limit_kmh = BASE * 3.6
            out_speed = limiter.apply(raw_out, accel_limit_kmh, dt)
            v_ego_kph = out_speed
            pos += (v_ego_kph / 3.6) * dt
            trace.append((round(pos, 1), round(v_ego_kph, 1)))
        return v_ego_kph, trace

    # 이미 92kph로 램프가 걸려있던 중(예: 완만한 1차 커브를 지나던 중)
    # candidates[0]가 훨씬 급한 2차 지점(30m 앞, target=15kph)으로 갱신된
    # 상황. v_ego(=직전 프레임 out)=92kph에서 시작.
    end_v_197_seed, trace_197_seed = simulate_seeded("197", 92.0, 92.0, 30.0, 15.0)
    end_v_v2_seed, trace_v2_seed = simulate_seeded("v2", 92.0, 92.0, 30.0, 15.0)
    check("[핵심] 이미 램프가 걸린 상태(prev_out 시딩)에서 더 급한 지점 갱신 시, "
          "v2가 197차보다 apex 도달 시 실제vEgo를 target에 더 가깝게 만듦(오버슈트 감소)",
          end_v_v2_seed < end_v_197_seed - 3.0,
          f"197cha 도달속도={end_v_197_seed:.1f}kph, v2 도달속도={end_v_v2_seed:.1f}kph, target=15.0")

    # 4) 안전 클램프: 위 시딩 시나리오(prev_out이 이미 설정된, 132차 리셋
    #    예외가 개입하지 않는 순수 케이스)에서 프레임당 낙차가 MAXD 기준
    #    이론상한을 넘지 않는지 확인(저크 없음). late_discovery_sampler류는
    #    "제약없음->있음" 전환 첫 프레임이 132차 설계상 의도적으로
    #    무제한이라 이 체크에 안 씀(회귀 없음 확인 3번 참고).
    # [198차 v2 FAIL1 원인규명] trace가 round(v,1)로 반올림된 값이라, 인접
    # 프레임이 서로 반대 방향으로 반올림되면 실제 낙차(정확히 0.5400)가
    # 표시상 0.6으로 튈 수 있음(예: 91.460->91.5, 90.920->90.9). 안전
    # 검증은 반올림 오차 2배(±0.1)까지 허용해야 오탐이 없다. 실제 미반올림
    # 값은 전 구간 정확히 0.5400로 확인됨(디버그 스크립트로 재검증 완료) --
    # 이 항목은 순수 반올림 아티팩트였고 실제 램프리미터 안전성 위반은 없었음.
    max_step_seen = 0.0
    prev_v = 92.0
    for (_, v) in trace_v2_seed:
        max_step_seen = max(max_step_seen, prev_v - v)
        prev_v = v
    theoretical_max = MAXD * 3.6 * 0.05
    check("[안전] 시딩 시나리오(v2)에서 프레임당 낙차가 MAXD 이론상한 초과 없음(저크 없음)",
          max_step_seen <= theoretical_max + 0.1,
          f"max_step_seen={max_step_seen:.3f}, theoretical_max={theoretical_max:.3f} (반올림 허용오차 포함)")

    # 5) 156차 winding road(여유 있는 일반 주행) 전체 궤적 회귀 없음
    curv_fn = winding_road_curvature_fn()
    sampler = lambda pos: sample_curvature_road(curv_fn, pos, 600.0, 110.0, 0.001)
    _, _, trace_wind_197 = simulate_road(sampler, 600.0, 68.0, BASE, MAXD, SAFE_TIME, "197")
    _, _, trace_wind_v2 = simulate_road(sampler, 600.0, 68.0, BASE, MAXD, SAFE_TIME, "v2")
    max_diff = max(abs(a[2] - b[2]) for a, b in zip(trace_wind_197, trace_wind_v2))
    check("156차 winding road(일반 주행) 전체 궤적 diff-0(<=0.1kph) -- 회귀 없음",
          max_diff <= 0.1, f"max_diff={max_diff:.4f}kph")

    # 6) 근접 잡음(noise) 케이스에서도 v2가 base와 동일해야 함(v_ego가
    #    이미 target 근처거나 여유 있는 일반 상황이면 a_req가 자연히
    #    작아 램프도 그대로) -- 179차/196차 등 기존 apex 선택 로직에
    #    영향이 없음을 별도로 재확인.
    speeds_noise = [40.0, 40.0, 200.0, 200.0]
    distances_noise = [40.0, 50.0, 60.0, 70.0]
    out_n_v2, lim_n_v2, req_n = carrot_navi_route_v2(speeds_noise, distances_noise, 45.0, BASE, MAXD, SAFE_TIME)
    out_n_197, lim_n_197 = carrot_navi_route_197cha_full(speeds_noise, distances_noise, BASE, SAFE_TIME)
    check("근접 저속(45->40kph) 완만한 상황 -- a_req가 작아 v2도 197차와 diff-0",
          abs(out_n_v2 - out_n_197) < 1e-9 and abs(lim_n_v2 - lim_n_197) < 1e-9,
          f"req_decel={req_n:.3f}mss (base={BASE})")

    print(f"\n{passed} PASS / {failed} FAIL")
    return failed == 0


if __name__ == "__main__":
    if "--unit-tests" in sys.argv:
        ok = _run_unit_tests()
        sys.exit(0 if ok else 1)
    print(__doc__)
