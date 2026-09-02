#!/usr/bin/env python3
"""
199차(설계 A v2 FAIL2 부분 해결) -- v2 위에 "불연속 감지 게이트"만 추가한다.

[전제, v2에서 그대로 가져옴] raw out_speed(목표속도)는 절대 건드리지 않는다.
197차와 100% 동일한 camera-style 공식 그대로. 이 파일이 바꾸는 것은 오직
비대칭 램프리미터의 하강 상한(accel_limit_kmh)을 vEgo 기반으로 부스트할지
말지의 "게이트" 뿐이다.

[FAIL2 재확인, 198차 v2에서 발견] `carrot_navi_route_197cha()`의 apex 선택
(candidates[0] = "road_limit 미만인 가장 가까운 곡률 샘플")은 연속되는
굽이길(winding road)에서 거의 항상 `apex_dist == DISTANCE_INTERVAL`
(=10.0m, lookahead 상대배열의 첫 샘플)로 구조적으로 고정된다 -- 실측
확인(이 파일 작성 중 재확인): `winding_road_curvature_fn()` 전체 600m
구간에서 apex_dist 값의 집합은 정확히 `{10.0}` 하나뿐이었다. 즉
`apex_dist`는 "브레이크를 걸어야 할 진짜 정점까지의 거리"가 아니라 그냥
"다음 곡률 샘플이 얼마나 가까운가"에 불과하며, 이 값만으로는 "뒤늦게
발견된 진짜 급커브"와 "정상적으로 굽이길을 통과하며 매 프레임 갱신되는
다음 샘플"을 구분할 수 없다(198차 결론 그대로, 미해결로 남겨짐).

[v3, 부분 해결책] apex_dist 대신 **apex_speed의 프레임간 변화량**을 구분
기준으로 쓴다. 근거(이 파일 작성 중 실측):
  - 연속 굽이길에서 apex_speed는 곡률이 sinusoidal로 서서히 변하므로
    프레임당(20Hz, 심지어 0.5m 간격 fine sweep으로도) 최대 ~1.4~2.6km/h
    수준으로만 완만하게 변한다(실측값, 아래 THRESH 설정 근거).
  - 반대로 "뒤늦게 발견된 급커브"(예: lookahead/폴리라인 갱신 지연으로
    이전 프레임까지 무제약(300)이었다가 갑자기 낮은 target이 채워지는
    경우, 또는 candidates[0]가 훨씬 급한 다른 지점으로 즉시 대체되는
    경우)는 정의상 apex_speed가 한 프레임 만에 큰 폭(수십 km/h)으로
    떨어진다.
  - 따라서 "직전 프레임 대비 apex_speed가 THRESH(km/h) 이상 떨어졌는가"를
    불연속 감지 트리거로 쓰고, 감지된 순간의 apex_speed를 "무장된 목표"로
    저장해 그 목표가 유지되는 동안(=apex_speed가 무장값 근방을 유지하는
    동안)만 부스트를 켠 채로 둔다. 일반 굽이길처럼 apex_speed가 계속
    완만하게만 바뀌면 트리거 자체가 없어 부스트가 켜지지 않고, v3는
    197차와 diff-0가 된다(핵심 불변식, 아래 유닛테스트 5 참고).

[THRESH 산정] winding road 실측 최대 프레임당 delta가 20Hz 샘플링
기준으로도 fine sweep(0.5m 간격) 기준으로도 1.4~2.6km/h를 넘지 않았으므로,
안전마진을 크게 두어 15.0km/h로 설정한다(기존 코드베이스의 유사 불연속
감지 상수 `DREL_DISCONTINUITY_DROP_THRESH`와 동일 크기 단위 관례를 참고했을
뿐, 그 상수 자체를 재사용하는 것은 아님 -- 대상 물리량이 다름(그쪽은
레이더 lead 거리(m), 이쪽은 목표속도(km/h))).

[여전히 남는 한계 -- "부분" 해결인 이유, 반드시 기록]
apex_speed가 "한 프레임에 크게" 떨어지는 경우만 잡는다. 만약 어떤 실제
도로에서 급커브가 여러 프레임에 걸쳐 THRESH 미만씩 점진적으로(계단식이
아니라 매 프레임 조금씩) 나타나는 경우-- 즉 누적으로는 크지만 프레임당
delta는 항상 THRESH 미만인 경우 -- 이 게이트는 뚫리지 않고 여전히
197차와 동일하게(부스트 없이) 동작한다. 이는 apex 절대위치를 프레임 간
추적하는 완전한 재설계(158/159차가 시도했다 실측 악화로 폐기된 전례가
있는 방향, 195차/198차 기록 참고) 없이는 원천적으로 닫을 수 없는 구멍이며,
이번 v3는 "한 프레임 급락형" 불연속만 부분적으로 해결한다.

사용:
    python3 sim_route_vego_required_decel_v3.py --unit-tests
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
from sim_route_vego_required_decel_v2 import (
    calculate_route_required_decel,
    carrot_navi_route_197cha,
    carrot_navi_route_197cha_full,
)

# [v3 신규 상수] apex_speed 프레임간 하락폭이 이 값(km/h) 이상이면
# "불연속(=뒤늦게 발견된 급커브)"로 간주한다. winding road 실측 최대
# delta(~2.6km/h, fine sweep 기준 ~1.4km/h)의 약 6~10배 안전마진.
ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH = 15.0


class ApexDiscontinuityState:
    """apex_speed의 프레임간 이력을 들고 있다가, "불연속 급락"이 감지된
    동안에만 vEgo 기반 램프 부스트를 무장(armed)시킨다. RampLimiterState와
    별개의 독립 상태(같은 인스턴스 생명주기 동안 함께 생성/유지)."""

    def __init__(self, thresh_kph=ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH):
        self.thresh_kph = thresh_kph
        self.prev_apex_speed = None
        self.armed = False
        self.armed_apex_speed = None

    def update(self, apex_speed):
        """apex_speed=None(경로 비활성/무제약)이면 상태 전부 리셋하고
        False 반환. 그 외에는 이번 프레임 부스트 무장 여부를 반환."""
        if apex_speed is None:
            self.prev_apex_speed = None
            self.armed = False
            self.armed_apex_speed = None
            return False

        if self.prev_apex_speed is None:
            # 최초 관측(또는 방금 비활성에서 복귀) -- 직전 값이 없어
            # "불연속인지" 판단할 기준 자체가 없다. 안전한 기본값은
            # 197차와 diff-0(=미무장)이다. 실제로 이 프레임이 late-discovery
            # 최초 프레임이더라도, 그 다음 프레임부터는 prev_apex_speed가
            # 채워져 정상적으로 델타 비교가 시작된다(1프레임=0.05s 지연,
            # 무시 가능한 수준).
            self.prev_apex_speed = apex_speed
            return self.armed

        delta = self.prev_apex_speed - apex_speed  # 양수 = 더 급해짐(속도↓)
        if delta > self.thresh_kph:
            self.armed = True
            self.armed_apex_speed = apex_speed
        elif self.armed:
            # 이미 무장된 상태 -- 대상 지점이 크게 달라지면(도달해서
            # 다음 지점으로 넘어갔거나, 더 완만한 지점으로 대체됨) 해제.
            if abs(apex_speed - self.armed_apex_speed) > self.thresh_kph:
                self.armed = False
                self.armed_apex_speed = None
        # else: 무장 안 된 상태에서 delta<=thresh -- 계속 미무장 유지
        # (연속 굽이길의 정상적인 완만한 변화, 197차와 diff-0 유지)

        self.prev_apex_speed = apex_speed
        return self.armed


def carrot_navi_route_v3(speeds, distances, v_ego_kph, base_decel_mss,
                          max_decel_mss, safe_time, disc_state,
                          road_limit_speed=200.0):
    """198차 v2 + 199차 불연속 게이트. raw out_speed는 197차와 100% 동일.
    accel_limit_kmh(램프용)는 disc_state가 "무장"된 프레임에서만 a_req
    기반으로 동적화되고, 그 외에는 base_decel_mss 그대로(diff-0)."""
    apex_dist, apex_speed = carrot_navi_route_197cha(speeds, distances, road_limit_speed)
    armed = disc_state.update(apex_speed)

    if apex_dist is None:
        return 300.0, base_decel_mss * 3.6, 0.0, armed
    out_speed = camera_calculate_current_speed(apex_dist, apex_speed, safe_time, base_decel_mss)
    out_speed = min(out_speed, 300.0)

    if not armed:
        return out_speed, base_decel_mss * 3.6, 0.0, armed

    required_decel = calculate_route_required_decel(v_ego_kph, apex_dist, apex_speed)
    if required_decel <= base_decel_mss:
        ramp_decel = base_decel_mss
    else:
        ramp_decel = min(required_decel, max_decel_mss)
    return out_speed, ramp_decel * 3.6, required_decel, armed


def simulate_road(sampler, road_len_m, v_ego_kph_start, base_decel_mss,
                   max_decel_mss, safe_time, algo, dt=0.05, max_steps=6000):
    v_ego_kph = v_ego_kph_start
    pos = 0.0
    t = 0.0
    limiter = RampLimiterState(asymmetric_up=True)
    disc_state = ApexDiscontinuityState()
    trace = []
    steps = 0
    while pos < road_len_m and steps < max_steps:
        speeds, distances = sampler(pos)
        if algo == "v3":
            raw_out, accel_limit_kmh, req_decel, armed = carrot_navi_route_v3(
                speeds, distances, v_ego_kph, base_decel_mss, max_decel_mss, safe_time, disc_state)
        else:
            raw_out, accel_limit_kmh = carrot_navi_route_197cha_full(
                speeds, distances, base_decel_mss, safe_time)
            req_decel = 0.0
            armed = False
        out_speed = limiter.apply(raw_out, accel_limit_kmh, dt)
        if raw_out >= 299.999:
            # v2와 동일한 단순화(센티널 처리) -- 위 sim_route_vego_required_decel_v2.py 주석 참고.
            out_speed = v_ego_kph
        v_ego_kph = out_speed
        pos += (v_ego_kph / 3.6) * dt
        t += dt
        steps += 1
        trace.append((round(t, 2), round(pos, 1), round(v_ego_kph, 1), round(raw_out, 1),
                      round(req_decel, 2), armed))
    return v_ego_kph, t, trace


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

    # 1) [v2에서 그대로 승계] raw out_speed는 v3와 197차가 항상 완전히
    #    동일해야 함(핵심 불변식, 게이트 유무와 무관).
    disc = ApexDiscontinuityState()
    speeds_short, distances_short = [30.0], [60.0]
    out_v3, lim_v3, req, armed = carrot_navi_route_v3(speeds_short, distances_short, 90.0, BASE, MAXD, SAFE_TIME, disc)
    out_197, lim_197 = carrot_navi_route_197cha_full(speeds_short, distances_short, BASE, SAFE_TIME)
    check("[핵심 불변식] raw out_speed는 v3와 197차가 항상 동일",
          abs(out_v3 - out_197) < 1e-9, f"v3={out_v3:.3f}, 197cha={out_197:.3f}")
    check("최초 관측(prev_apex_speed 없음)은 미무장이 기본값 -- 이 단일콜에서는 부스트 없음",
          not armed and abs(lim_v3 - lim_197) < 1e-9,
          f"armed={armed}, lim_v3={lim_v3:.2f}, lim_197={lim_197:.2f}")

    # 2) 같은 지점을 반복 관측하면(delta=0) 여전히 미무장 -- 진짜 불연속이
    #    없으면 절대 부스트가 켜지지 않아야 함.
    disc2 = ApexDiscontinuityState()
    for _ in range(5):
        _, lim_repeat, _, armed_repeat = carrot_navi_route_v3(speeds_short, distances_short, 90.0, BASE, MAXD, SAFE_TIME, disc2)
    check("동일 apex_speed 반복 관측(delta=0)은 계속 미무장",
          not armed_repeat and abs(lim_repeat - BASE * 3.6) < 1e-9)

    # 3) [핵심, 실제 위험 시나리오 -- v2와 동일 취지, 상태 시딩 방식만 변경]
    #    "완만한 1차 커브(apex_speed≈45)를 지나던 중 candidates[0]가 훨씬
    #    급한 2차 지점(target=15)으로 즉시 대체"되는 진짜 불연속을 재현한다.
    #    v2는 RampLimiterState.prev_out만 시딩했지만, v3는 불연속 감지용
    #    ApexDiscontinuityState.prev_apex_speed도 "직전 관측값"으로 함께
    #    시딩해야 이 프레임에서 델타(45->15=30 > THRESH)가 정상적으로
    #    계산된다(이게 v3가 v2 대비 늘어난 유일한 시딩 요구사항).
    def simulate_seeded(algo, seed_prev_out_kph, seed_prev_apex_kph, v_ego_start_kph,
                         apex_dist0, target_kph, steps_before_arrival=None):
        limiter = RampLimiterState(asymmetric_up=True)
        limiter.prev_out = seed_prev_out_kph
        disc_state = ApexDiscontinuityState()
        disc_state.prev_apex_speed = seed_prev_apex_kph
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
            if algo == "v3":
                raw_out, accel_limit_kmh, req, armed = carrot_navi_route_v3(
                    speeds, distances, v_ego_kph, BASE, MAXD, SAFE_TIME, disc_state)
            else:
                raw_out = camera_calculate_current_speed(remaining, target_kph, SAFE_TIME, BASE)
                accel_limit_kmh = BASE * 3.6
            out_speed = limiter.apply(raw_out, accel_limit_kmh, dt)
            v_ego_kph = out_speed
            pos += (v_ego_kph / 3.6) * dt
            trace.append((round(pos, 1), round(v_ego_kph, 1)))
        return v_ego_kph, trace

    end_v_197_seed, _ = simulate_seeded("197", 92.0, None, 92.0, 30.0, 15.0)
    end_v_v3_seed, _ = simulate_seeded("v3", 92.0, 45.0, 92.0, 30.0, 15.0)
    check("[핵심] 불연속(45->15) 시딩 시 v3가 197차보다 apex 도달 시 실제vEgo를 target에 더 가깝게 만듦(오버슈트 감소)",
          end_v_v3_seed < end_v_197_seed - 3.0,
          f"197cha 도달속도={end_v_197_seed:.1f}kph, v3 도달속도={end_v_v3_seed:.1f}kph, target=15.0")

    # 3b) 동일 시나리오인데 직전 apex_speed를 target과 가깝게(45 대신 20,
    #     delta=5<THRESH) 시딩하면 -- 즉 "원래도 이미 급한 지점을 보고
    #     있었을 뿐 새로 나타난 게 아님" -- 무장되지 않아야 하고, 결과가
    #     197차와 동일해야 함(오탐 없음 확인).
    end_v_v3_noconn, _ = simulate_seeded("v3", 92.0, 20.0, 92.0, 30.0, 15.0)
    check("직전 apex_speed가 target과 가까움(delta<THRESH)이면 무장 안 됨 -- 197차와 동일",
          abs(end_v_v3_noconn - end_v_197_seed) < 0.5,
          f"v3(no-disc)={end_v_v3_noconn:.1f}, 197cha={end_v_197_seed:.1f}")

    # 4) 안전 클램프: 무장된 시나리오에서 프레임당 낙차가 MAXD 이론상한을
    #    넘지 않는지(저크 없음, v2와 동일 원칙 승계, 반올림 오차 허용).
    limiter = RampLimiterState(asymmetric_up=True)
    limiter.prev_out = 92.0
    disc_state = ApexDiscontinuityState()
    disc_state.prev_apex_speed = 45.0
    v_ego_kph = 92.0
    pos = 0.0
    dt = 0.05
    max_step_seen = 0.0
    prev_v = 92.0
    for _ in range(400):
        remaining = 30.0 - pos
        if remaining <= 0:
            break
        raw_out, accel_limit_kmh, req, armed = carrot_navi_route_v3(
            [15.0], [remaining], v_ego_kph, BASE, MAXD, SAFE_TIME, disc_state)
        out_speed = limiter.apply(raw_out, accel_limit_kmh, dt)
        v_ego_kph = out_speed
        pos += (v_ego_kph / 3.6) * dt
        max_step_seen = max(max_step_seen, prev_v - v_ego_kph)
        prev_v = v_ego_kph
    theoretical_max = MAXD * 3.6 * dt
    check("[안전] 무장 시나리오(v3)에서 프레임당 낙차가 MAXD 이론상한 초과 없음",
          max_step_seen <= theoretical_max + 0.1,
          f"max_step_seen={max_step_seen:.3f}, theoretical_max={theoretical_max:.3f}")

    # 5) [FAIL2 재검증, 이번 v3의 핵심 목표] 156차 winding road(연속 굽이길,
    #    일반 주행) 전체 궤적이 197차와 diff-0이어야 함 -- apex_speed가
    #    완만하게만 바뀌므로 불연속 게이트가 한 번도 무장되지 않아야 함.
    curv_fn = winding_road_curvature_fn()
    sampler = lambda pos: sample_curvature_road(curv_fn, pos, 600.0, 110.0, 0.001)
    _, _, trace_wind_197 = simulate_road(sampler, 600.0, 68.0, BASE, MAXD, SAFE_TIME, "197")
    _, _, trace_wind_v3 = simulate_road(sampler, 600.0, 68.0, BASE, MAXD, SAFE_TIME, "v3")
    max_diff = max(abs(a[2] - b[2]) for a, b in zip(trace_wind_197, trace_wind_v3))
    any_armed = any(row[5] for row in trace_wind_v3)
    check("[FAIL2 부분해결 검증] 156차 winding road 전체 궤적 diff-0(<=0.1kph), 불연속 게이트 한 번도 무장 안 됨",
          max_diff <= 0.1 and not any_armed,
          f"max_diff={max_diff:.4f}kph, any_armed={any_armed}")

    # 6) [v2에서 승계] 여유있는 상황 -- diff-0
    disc6 = ApexDiscontinuityState()
    speeds_ample = [30.0] * 5
    distances_ample = list(range(60, 360, 60))
    out_a, lim_a, req_a, armed_a = carrot_navi_route_v3(speeds_ample, distances_ample, 50.0, BASE, MAXD, SAFE_TIME, disc6)
    out_a197, lim_a197 = carrot_navi_route_197cha_full(speeds_ample, distances_ample, BASE, SAFE_TIME)
    check("여유있는 거리에서는 v3가 197차와 완전히 동일(diff-0)",
          abs(out_a - out_a197) < 1e-9 and abs(lim_a - lim_a197) < 1e-9)

    # 7) [FAIL2 부분해결 실증] winding road 진행 중, 어느 한 프레임에서만
    #    "진짜 급커브가 갑자기 나타난 것"을 인위적으로 주입(candidates[0]가
    #    가리키는 다음 샘플의 speed를 그 프레임에서만 크게 낮춤)하면, v3는
    #    그 프레임부터 정확히 무장되어야 한다(연속 굽이길의 배경 잡음과
    #    실제 이벤트를 구분하는 것이 이번 v3의 목적이므로 이 실증이 핵심).
    disc7 = ApexDiscontinuityState()
    pos7 = 0.0
    armed_seen_at = None
    for step in range(60):
        speeds, distances = sampler(pos7)
        if step == 30:
            # 급커브 late-discovery 주입: 가장 가까운 샘플의 speed를
            # road_limit 미만인 채로 크게 낮춤(예: 20km/h) -- candidates[0]가
            # 여전히 이 샘플을 가리키므로 apex_dist는 그대로 10m지만
            # apex_speed만 인위적으로 급락.
            speeds = list(speeds)
            speeds[0] = 20.0
        apex_dist, apex_speed = carrot_navi_route_197cha(speeds, distances)
        armed = disc7.update(apex_speed)
        if armed and armed_seen_at is None:
            armed_seen_at = step
        pos7 += 1.0
    check("[FAIL2 부분해결 실증] 급커브 주입 프레임(step=30)에서 즉시 무장 감지",
          armed_seen_at == 30, f"armed_seen_at={armed_seen_at}")

    print(f"\n{passed} PASS / {failed} FAIL")
    return failed == 0


if __name__ == "__main__":
    if "--unit-tests" in sys.argv:
        ok = _run_unit_tests()
        sys.exit(0 if ok else 1)
    print(__doc__)
