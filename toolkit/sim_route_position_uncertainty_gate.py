#!/usr/bin/env python3
"""
162차, 방향2(보수적 완화) 사전검증: carrot_man.py::carrot_navi_route()의
132차 램프리미터에 추가한 "위치불확실성 게이트"를 순수함수로 복제해 검증한다.

배경(FINDINGS.md 162차): route aeeed9e4a5 seg3 실측에서 앱/폰 GPS 위치갱신이
약 11초간 끊기며 carrot_serv.py::_update_gps()의 estimate_position() 데드
레커닝이 옛 헤딩(296.0deg 고정)으로 계속 직진 외삽 -> 실제 급우회전
(steer 최대 -121.9deg) 중인데 carrot_navi_route()의 curvature 계산이
"직선"으로 오판해 route_speed가 300(무제한) 쪽으로 완화되며 상승. 실측
liveRouteSpeed가 t=6378~6395(약17초) 동안 92->149kph로 매끄럽게 상승한
패턴이 132차 램프리미터가 이미 어느 정도 완만화하고 있었음을 보여준다
(급락/급등이 아니라 accel_limit_kmh 기울기로 상승).

패치(carrot_man.py, 162차): 램프리미터의 "완화(상승)" 방향 상한(hi)을,
carrot_serv.py가 계산하는 position_dt_since_fix(마지막 실제 GPS/앱 위치
fix 이후 데드레커닝 경과시간)가 ROUTE_POSITION_UNCERTAIN_DT_S(3.0s)를
넘는 프레임에서는 이전 값(prev_out)으로 고정한다. 하강(lo) 방향은 그대로
둬 실제 감속 필요는 계속 반영한다.

한계(정직하게 기록): carrotMan cereal 메시지가 position_dt_since_fix를
발행하지 않아 실측 CSV로 이 게이트 자체의 프레임별 dt 값을 직접 재생할
수는 없다(carrot_serv.py 내부 상태). 이 스크립트는 대신:
  1. 실측에서 관측된 것과 동일한 규모(경과시간 ~11초, accel_limit_kmh
     ~3.3, 300으로 즉시 열리려는 raw 신호)의 합성 시나리오로 게이트가
     설계대로 동작하는지 확인(재현 검증).
  2. dt가 항상 임계값 미만인 "정상" 시나리오에서 패치 전/후 출력이
     완전히 동일함을 확인(회귀 없음 검증).
  3. 불확실 구간 중에도 raw_out_speed가 실제로 더 낮아지는 경우(진짜
     커브가 늦게라도 감지된 경우)엔 게이트가 하강을 막지 않음을 확인.
다음 세션에서 carrotMan에 이 필드를 발행하도록 확장하면 실측 재생 검증도
가능해진다(향후 과제로 기록).

사용:
    python3 sim_route_position_uncertainty_gate.py --unit-tests
"""
import argparse
import sys


class RampLimiterState:
    """132차 원본(위치불확실성 게이트 없음) -- 회귀 비교 기준선."""

    def __init__(self):
        self.prev_out = None

    def apply(self, raw_out_speed, accel_limit_kmh, dt):
        if self.prev_out is None:
            out = raw_out_speed
        else:
            max_step = accel_limit_kmh * dt
            lo = self.prev_out - max_step
            hi = self.prev_out + max_step
            out = min(max(raw_out_speed, lo), hi)
        self.prev_out = out
        return out


class GatedRampLimiterState:
    """162차 패치와 정확히 동일한 로직(carrot_man.py carrot_navi_route()
    내 램프리미터 블록의 순수함수 복제)."""

    def __init__(self, uncertain_thresh_s=3.0):
        self.prev_out = None
        self.uncertain_thresh_s = uncertain_thresh_s

    def apply(self, raw_out_speed, accel_limit_kmh, dt, position_dt_since_fix):
        if self.prev_out is None:
            out = raw_out_speed
        else:
            max_step = accel_limit_kmh * dt
            lo = self.prev_out - max_step
            hi = self.prev_out + max_step
            if position_dt_since_fix > self.uncertain_thresh_s:
                hi = self.prev_out
            out = min(max(raw_out_speed, lo), hi)
        self.prev_out = out
        return out


def test_regression_dt_always_low():
    """dt(위치불확실성)가 항상 임계값 미만이면 패치 전/후 출력이 완전히
    동일해야 한다 (정상 주행 중 회귀 없음)."""
    accel_limit_kmh = 3.3
    dt = 0.05
    # 임의의 오르내림이 섞인 raw 시퀀스 (직선/커브/근정지 등 혼합 근사)
    raw_seq = [120, 118, 100, 80, 60, 45, 40, 42, 55, 70, 90, 110, 130, 150,
               160, 158, 140, 120, 110, 108, 300, 300, 250, 200, 150, 100]

    baseline = RampLimiterState()
    gated = GatedRampLimiterState()
    max_diff = 0.0
    for raw in raw_seq:
        b = baseline.apply(raw, accel_limit_kmh, dt)
        g = gated.apply(raw, accel_limit_kmh, dt, position_dt_since_fix=0.5)
        max_diff = max(max_diff, abs(b - g))
    ok = max_diff < 1e-9
    print(f"[regression_dt_always_low] max_diff={max_diff:.6f} -> {'PASS' if ok else 'FAIL'}")
    return ok


def test_reproduction_real_event_scale():
    """실측 규모(약 11초 위치불확실, accel_limit_kmh~3.3, raw가 즉시
    300으로 열리려는 상황)를 합성 재현. 패치 전(baseline)은 실측처럼
    매끄럽게 상승(92->149 근사 재현), 패치 후(gated)는 불확실 구간 동안
    동결돼야 한다."""
    accel_limit_kmh = 3.3
    dt = 0.05  # 20Hz
    n_uncertain_frames = int(11.0 / dt)  # 약 11초 = 220 프레임
    start_speed = 92.0

    baseline = RampLimiterState()
    gated = GatedRampLimiterState()
    baseline.prev_out = start_speed
    gated.prev_out = start_speed

    baseline_trace = [start_speed]
    gated_trace = [start_speed]
    for i in range(n_uncertain_frames):
        # 불확실 구간 내내 raw는 "커브 없음"(300, 즉시 완화 시도)
        pdt = 0.05 + i * dt  # dt(=경과시간)가 프레임마다 선형으로 증가(재fix 없음)
        b = baseline.apply(300.0, accel_limit_kmh, dt)
        g = gated.apply(300.0, accel_limit_kmh, dt, position_dt_since_fix=pdt)
        baseline_trace.append(b)
        gated_trace.append(g)

    baseline_end = baseline_trace[-1]
    gated_end = gated_trace[-1]

    # 게이트 임계값(3.0s) 이후부턴 gated가 완전히 동결돼야 한다.
    idx_thresh = int(3.0 / dt)
    gated_after_thresh = gated_trace[idx_thresh:]
    frozen = all(abs(v - gated_after_thresh[0]) < 1e-9 for v in gated_after_thresh)

    # baseline은 accel_limit_kmh*dt*n_frames 만큼 상승했어야 함(실측 92->149,
    # 17초/약3.35kph/s와 동일 규모인지 근사 확인)
    expected_baseline_end = min(300.0, start_speed + accel_limit_kmh * dt * n_uncertain_frames)
    baseline_ok = abs(baseline_end - expected_baseline_end) < 1e-6

    ok = frozen and baseline_ok and (gated_end < baseline_end - 10.0)
    print(
        f"[reproduction_real_event_scale] baseline_end={baseline_end:.1f} "
        f"(실측 92->149 규모와 비교), gated_end={gated_end:.1f} "
        f"(3.0s 이후 완전동결={frozen}) -> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def test_decrease_still_allowed_during_uncertainty():
    """불확실 구간 중이라도 raw_out_speed가 더 낮아지면(=진짜 커브가
    늦게라도 감지됨) 게이트가 하강을 막지 않아야 한다(안전 방향은 항상
    즉시 반영)."""
    accel_limit_kmh = 3.3
    dt = 0.05
    gated = GatedRampLimiterState()
    gated.prev_out = 120.0

    # 불확실(pdt=5.0 > 3.0) 상태에서 raw가 큰 폭으로 낮아짐(급커브 감지)
    out = gated.apply(40.0, accel_limit_kmh, dt, position_dt_since_fix=5.0)
    max_step = accel_limit_kmh * dt
    expected = max(40.0, 120.0 - max_step)  # lo 방향은 게이트 영향 없음
    ok = abs(out - expected) < 1e-9
    print(
        f"[decrease_still_allowed] out={out:.3f} expected={expected:.3f} "
        f"-> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def run_unit_tests():
    results = [
        test_regression_dt_always_low(),
        test_reproduction_real_event_scale(),
        test_decrease_still_allowed_during_uncertainty(),
    ]
    n_pass = sum(results)
    print(f"\n{n_pass}/{len(results)} PASS")
    return n_pass == len(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit-tests", action="store_true")
    args = ap.parse_args()
    if args.unit_tests:
        ok = run_unit_tests()
        sys.exit(0 if ok else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
