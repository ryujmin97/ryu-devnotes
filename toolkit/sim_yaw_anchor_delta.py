#!/usr/bin/env python3
"""
165차/166차, 방향1(livePose 대신 carControl 헤딩보정) 앵커링/wrap 로직
자체의 정합성 검증.

배경(FINDINGS.md 165/166차): carrot_serv.py::_update_gps()가 매 fix마다
쓰는 헤딩(bearing_calculated, CarrotNavi 앱 nPosAngle 원값)이 앱 정체
동안 옛 값에 고정된 채 데드레커닝을 계속하는 것이 162차 근본원인(route가
급우회전을 "직선"으로 오판)이었다. 163차는 "완화 방향 억제"(방안2)로
안전영향만 차단했고, 165차는 "진짜 헤딩을 보정"하는 방안1을 설계했다:

    corrected_heading = wrap360(last_fix_heading + (cc_yaw_now - cc_yaw_at_fix))

여기서 cc_yaw_now/cc_yaw_at_fix는 이미 100Hz로 흐르는 carControl의
CC.orientationNED[2](절대 헤딩, rad) **두 시점 값의 직접 차분**이다
(적분이 아님 — controlsd.py가 이미 캘리브레이션 보정 완료해 발행 중이라
신규 SubMaster도 불필요). CC.angularVelocity[2](요레이트)는 실제 설계엔
안 쓰지만 아래 교차검증 테스트에서 대안 경로로 활용한다.
절대값을 그대로 대입하지 않고 "마지막 fix 시점 기준 델타만" 더하는 이유는
locationd.py의 오도메트리가 GPS 없는 순수 IMU+카메라 융합이라 장시간
드리프트 가능하기 때문 — 정상 구간(fix가 자주 옴)에서는 매 fix마다
델타누적이 0으로 리셋돼 기존 동작과 완전히 동일해야 한다.

166차가 실측(route aeeed9e4a5 seg0/seg3, ccYawDeg/ccYawRateZ 컬럼)으로
"CC.orientationNED가 나침반 관례(진북기준 시계방향 양수)"라는 부호 가정을
확인 완료(우회전 시 ccYawDeg 증가+ccYawRateZ 양수, 좌회전 시 반대 —
FINDINGS.md 166차 참고). 이 스크립트는 그 확인된 부호를 전제로 앵커링/wrap
수식 자체(리셋 시 드리프트 없음, wrap 경계 연속성, 정체 구간 재현)를
검증한다. 아직 ryu 코드 패치 없음 — 이 검증 통과 후 사용자 승인 시 패치.

한계: carrot_serv.py의 실제 "새 fix 도착" 감지(_update_gps() 내부
self.last_calculate_gps_time 변화)는 이 스크립트에 없다 — on_fix() 호출
시점을 테스트가 직접 지정하는 것으로 대체(그 감지 로직 자체는 165차 설계상
diff 10줄 내외로 간단해 별도 시뮬레이션 가치가 낮다고 판단).

사용:
    python3 sim_yaw_anchor_delta.py --unit-tests
"""
import argparse
import math
import sys


def wrap360(deg):
    return deg % 360.0


def shortest_diff_deg(a, b):
    """a-b를 -180~180 범위로 정규화(랩 경계 넘나드는 두 각도의 실제 최단 차이)."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return d


class BaselineFrozenHeadingState:
    """현재(패치 전) 동작 복제: _update_gps()가 마지막 fix(nPosAngle)를
    다음 fix가 올 때까지 그대로 고정해 쓴다 — 회전 정보를 전혀 반영 안 함."""

    def __init__(self):
        self.heading = None

    def on_fix(self, fix_heading_deg):
        self.heading = wrap360(fix_heading_deg)

    def on_tick(self, yaw_rate_rad_s, dt):
        return self.heading


class AnchoredHeadingStateDiff:
    """165차 실제 채택 설계(FINDINGS.md 165차 설계결정2/의사코드 그대로):
    마지막 fix 시점의 절대 CC.orientationNED[2] 값(cc_yaw_at_fix)을
    저장해뒀다가, Δyaw = 현재 orientationNED[2] - cc_yaw_at_fix(±180 wrap)
    를 fix 헤딩에 더한다. **적분이 아니라 두 절대값의 직접 차분** —
    angularVelocity를 아예 쓰지 않아 적분오차 누적 경로 자체가 없음."""

    def __init__(self):
        self.last_fix_heading = None  # bearing 기준점(nPosAngle 등)
        self.cc_yaw_at_fix_deg = None  # CC.orientationNED[2] 기준점(같은 시각)

    def on_fix(self, fix_heading_deg, cc_yaw_now_deg):
        self.last_fix_heading = wrap360(fix_heading_deg)
        self.cc_yaw_at_fix_deg = cc_yaw_now_deg  # wrap 안 함(차분 전용, 원값 유지)

    def on_tick(self, cc_yaw_now_deg):
        if self.last_fix_heading is None:
            return None
        dyaw = shortest_diff_deg(cc_yaw_now_deg, self.cc_yaw_at_fix_deg)
        return wrap360(self.last_fix_heading + dyaw)

    def current(self, cc_yaw_now_deg):
        return self.on_tick(cc_yaw_now_deg)


class AnchoredHeadingStateIntegrated:
    """165차 FINDINGS 미해결사항 2번: 실제 설계는 아니지만 \"orientationNED가
    두 프레임 사이 부드럽게 변하는지\" 교차검증용으로 언급된 대안 -
    angularVelocity[2](요레이트)를 적분해 델타를 만드는 방식. 위
    AnchoredHeadingStateDiff와 결과를 대조하는 용도로만 사용(적분이라
    이산화 오차가 누적되는 것이 정상 - Diff가 정답 기준선)."""

    def __init__(self):
        self.last_fix_heading = None
        self.accum_delta_deg = 0.0

    def on_fix(self, fix_heading_deg):
        self.last_fix_heading = wrap360(fix_heading_deg)
        self.accum_delta_deg = 0.0

    def on_tick(self, yaw_rate_rad_s, dt):
        # 166차 실측 확인: NED 관례, yaw_rate 양수 = 시계방향(우회전) =
        # bearing 증가. 부호 반전 불필요.
        self.accum_delta_deg += math.degrees(yaw_rate_rad_s) * dt
        if self.last_fix_heading is None:
            return None
        return wrap360(self.last_fix_heading + self.accum_delta_deg)

    def current(self):
        if self.last_fix_heading is None:
            return None
        return wrap360(self.last_fix_heading + self.accum_delta_deg)


# 166차 실측(route aeeed9e4a5 seg3, t=6370.973~6394.779, 4프레임당 1개
# 서브샘플, 120개): (t, ccYawDeg, ccYawRateZ). 162차가 기록한 "정체 11초,
# xPosAngle 296.0deg 고정 -> 3.0deg로 점프" 사건과 동일 구간(carControl
# 기준 실제 헤딩은 298.1 -> 4.2deg로 연속 회전).
REAL_FREEZE_WINDOW_SAMPLES = [
    (6370.973, 298.136, 0.003397), (6371.174, 298.1864, 0.010216),
    (6371.375, 298.2363, 0.005719), (6371.576, 298.2784, 0.004761),
    (6371.775, 298.317, 0.003957), (6371.974, 298.3534, 0.004371),
    (6372.173, 298.3807, 0.00461), (6372.375, 298.4156, 0.003738),
    (6372.573, 298.45, 0.004186), (6372.773, 298.4844, 0.003639),
    (6372.976, 298.5078, 0.001819), (6373.173, 298.5199, 0.000624),
    (6373.376, 298.5379, 0.001499), (6373.573, 298.5351, 0.001887),
    (6373.775, 298.546, -0.001141), (6373.973, 298.5184, -0.000795),
    (6374.176, 298.4985, -0.003527), (6374.373, 298.4447, -0.007406),
    (6374.575, 298.3374, -0.01074), (6374.776, 298.2441, -0.009074),
    (6374.973, 298.1366, -0.009807), (6375.175, 298.0416, -0.010045),
    (6375.376, 297.9773, -0.007218), (6375.573, 297.9319, -0.002369),
    (6375.773, 297.9423, 0.002281), (6375.973, 297.9912, 0.007371),
    (6376.177, 298.0771, 0.007265), (6376.373, 298.1554, 0.006603),
    (6376.573, 298.2472, 0.007007), (6376.777, 298.3367, 0.008148),
    (6376.973, 298.414, 0.006845), (6377.173, 298.486, 0.006769),
    (6377.373, 298.5212, 0.001228), (6377.574, 298.5162, -4.2e-05),
    (6377.776, 298.5193, -5.4e-05), (6377.974, 298.48, -0.003969),
    (6378.173, 298.4603, -0.002055), (6378.376, 298.4279, -0.004754),
    (6378.574, 298.3921, -0.001964), (6378.772, 298.3558, -0.00335),
    (6378.973, 298.3267, -0.001146), (6379.175, 298.3182, 0.002872),
    (6379.376, 298.3152, -0.000471), (6379.573, 298.3262, 0.001441),
    (6379.773, 298.3428, 0.001785), (6379.973, 298.37, 0.001758),
    (6380.177, 298.426, 0.003451), (6380.374, 298.4927, 0.005933),
    (6380.573, 298.5507, 0.005011), (6380.773, 298.5801, 0.001982),
    (6380.973, 298.606, 0.002424), (6381.173, 298.6356, 0.00219),
    (6381.373, 298.6611, 0.001786), (6381.573, 298.689, 0.004783),
    (6381.775, 298.7822, 0.009452), (6381.977, 298.8852, 0.006805),
    (6382.175, 298.9288, 0.002593), (6382.376, 298.9632, 0.004395),
    (6382.573, 298.9977, 0.003603), (6382.773, 299.0205, 0.001381),
    (6382.973, 298.996, -0.003514), (6383.176, 298.9391, -0.006453),
    (6383.373, 298.8651, -0.004217), (6383.573, 298.8457, 0.001567),
    (6383.777, 298.9254, 0.009733), (6383.973, 299.0224, 0.006472),
    (6384.174, 299.1412, 0.011894), (6384.373, 299.2591, 0.007874),
    (6384.578, 299.4228, 0.016935), (6384.773, 299.6876, 0.025642),
    (6384.977, 299.9571, 0.022574), (6385.173, 300.2177, 0.022289),
    (6385.377, 300.4604, 0.019214), (6385.576, 300.6211, 0.010333),
    (6385.775, 300.7021, 0.005502), (6385.977, 300.7465, 0.002351),
    (6386.175, 300.7471, -0.000828), (6386.373, 300.6808, -0.004519),
    (6386.574, 300.5823, -0.011762), (6386.785, 300.4202, -0.01648),
    (6386.979, 300.2652, -0.011399), (6387.174, 300.1406, -0.015263),
    (6387.373, 299.9595, -0.016419), (6387.574, 299.7683, -0.019545),
    (6387.774, 299.5416, -0.01772), (6387.973, 299.4026, -0.014596),
    (6388.173, 299.2477, -0.016116), (6388.376, 299.1301, -0.010127),
    (6388.575, 299.0504, -0.00817), (6388.776, 299.0227, -0.002535),
    (6388.973, 299.0213, 0.000387), (6389.174, 299.0768, 0.006543),
    (6389.378, 299.1611, 0.007385), (6389.577, 299.2729, 0.009495),
    (6389.773, 299.449, 0.019808), (6389.973, 299.8202, 0.033396),
    (6390.173, 300.3398, 0.051279), (6390.374, 301.1097, 0.075237),
    (6390.574, 302.2177, 0.110507), (6390.773, 303.8654, 0.154699),
    (6390.978, 305.8116, 0.18549), (6391.175, 308.2687, 0.235874),
    (6391.376, 311.4124, 0.277665), (6391.573, 314.7504, 0.321497),
    (6391.773, 318.7824, 0.347165), (6391.974, 322.9611, 0.343033),
    (6392.175, 326.6255, 0.338222), (6392.374, 330.5625, 0.346968),
    (6392.574, 334.5236, 0.348182), (6392.777, 338.4443, 0.342529),
    (6392.975, 342.6906, 0.357312), (6393.176, 346.6958, 0.350375),
    (6393.377, 350.8291, 0.341142), (6393.574, 354.391, 0.325176),
    (6393.774, 358.08, 0.296969), (6393.975, 0.9033, 0.211912),
    (6394.177, 2.6152, 0.124542), (6394.373, 3.887, 0.069436),
    (6394.574, 4.2713, 0.027175), (6394.779, 4.2422, -0.013681),
]


def test_reset_no_drift_over_many_fixes():
    """정상 구간(fix가 자주 옴) 회귀 검증: 매 fix 순간 corrected 출력이
    fix 값과 정확히 일치해야 하고(리셋), 여러 fix를 반복해도 잔여 오차가
    누적되지 않아야 한다(앵커링 코드 자체의 드리프트 버그 없음 확인).
    실제 설계(Diff 방식) 대상."""
    import random
    random.seed(42)
    anchored = AnchoredHeadingStateDiff()
    baseline = BaselineFrozenHeadingState()

    max_reset_mismatch = 0.0
    heading_true = 10.0  # fix 헤딩(bearing/nPosAngle)과 CC.orientationNED가
    cc_yaw_true = 10.0   # 정상 동작 중엔 항상 같은 참값을 공유한다고 가정
    for cycle in range(50):
        anchored.on_fix(heading_true, cc_yaw_true)
        baseline.on_fix(heading_true)
        mismatch = abs(shortest_diff_deg(anchored.current(cc_yaw_true), heading_true))
        max_reset_mismatch = max(max_reset_mismatch, mismatch)

        yaw_rate = random.uniform(-0.4, 0.4)  # rad/s
        dt = 0.05
        for _ in range(20):
            baseline.on_tick(yaw_rate, dt)
            heading_true = wrap360(heading_true + math.degrees(yaw_rate) * dt)
            cc_yaw_true = heading_true  # CC.orientationNED도 동일하게 회전 반영
            anchored.on_tick(cc_yaw_true)

    ok = max_reset_mismatch < 1e-9
    print(
        f"[reset_no_drift] 50 fix 사이클, 리셋 순간 최대 오차={max_reset_mismatch:.2e}deg "
        f"-> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def test_wrap_boundary_right_turn_synthetic():
    """합성: 350deg에서 시작해 +30deg/s로 13초간 우회전 지속 시
    359->0 경계를 넘어야 한다. wrap360 누적이 연속적인지(프레임간
    급점프 없음) + 최종값이 이론치와 일치하는지 확인. Diff 방식은
    orientationNED 자체가 이미 절대값이므로 여기선 그 절대값이 실제로
    360도 넘게(또는 음수로) 흘러가도(랩 안 된 raw) 정상 처리되는지도
    같이 확인한다(locationd 내부표현이 랩 여부 불명이라 양쪽 다 검증)."""
    dt = 0.05
    yaw_rate_deg_s = 30.0  # 시계방향(우회전)
    n = int(13.0 / dt)

    # Case A: CC.orientationNED가 랩 없이 계속 누적되는 raw 표현이라 가정
    anchored_raw = AnchoredHeadingStateDiff()
    cc_yaw_raw = 350.0
    anchored_raw.on_fix(350.0, cc_yaw_raw)
    prev = anchored_raw.current(cc_yaw_raw)
    max_jump = 0.0
    for _ in range(n):
        cc_yaw_raw += yaw_rate_deg_s * dt  # 랩 안 함(예: 740.0까지 그대로 증가)
        cur = anchored_raw.current(cc_yaw_raw)
        jump = abs(shortest_diff_deg(cur, prev))
        max_jump = max(max_jump, jump)
        prev = cur
    expected_final = wrap360(350.0 + 30.0 * 13.0)  # 20.0
    final_ok = abs(shortest_diff_deg(anchored_raw.current(cc_yaw_raw), expected_final)) < 1e-6
    continuity_ok = max_jump < 5.0
    ok = final_ok and continuity_ok
    print(
        f"[wrap_right_turn] final={anchored_raw.current(cc_yaw_raw):.4f} "
        f"expected={expected_final:.4f} max_frame_jump={max_jump:.4f}deg "
        f"(입력 orientationNED가 랩 없이 누적돼도 shortest_diff_deg로 정상 처리) "
        f"-> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def test_wrap_boundary_left_turn_synthetic():
    """합성: 10deg에서 시작해 -30deg/s로 13초간 좌회전 지속 시
    0->359 경계(반대 방향 wrap)를 넘어야 한다."""
    dt = 0.05
    yaw_rate_deg_s = -30.0
    n = int(13.0 / dt)

    anchored = AnchoredHeadingStateDiff()
    cc_yaw = 10.0
    anchored.on_fix(10.0, cc_yaw)
    prev = anchored.current(cc_yaw)
    max_jump = 0.0
    for _ in range(n):
        cc_yaw += yaw_rate_deg_s * dt  # 음수 방향으로 랩 없이 누적(-380까지)
        cur = anchored.current(cc_yaw)
        jump = abs(shortest_diff_deg(cur, prev))
        max_jump = max(max_jump, jump)
        prev = cur
    expected_final = wrap360(10.0 - 30.0 * 13.0)  # 340.0
    final_ok = abs(shortest_diff_deg(anchored.current(cc_yaw), expected_final)) < 1e-6
    continuity_ok = max_jump < 5.0
    ok = final_ok and continuity_ok
    print(
        f"[wrap_left_turn] final={anchored.current(cc_yaw):.4f} "
        f"expected={expected_final:.4f} max_frame_jump={max_jump:.4f}deg "
        f"-> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def test_real_freeze_event_reproduction():
    """166차 실측(REAL_FREEZE_WINDOW_SAMPLES, ccYawDeg=CC.orientationNED[2]
    나침반변환값): 162차가 발견한 정체 사건과 동일 구간에서, baseline
    (현재 동작, fix 고정)은 끝까지 시작값(298.1deg 근방)에 묶여 있어야
    하고, anchored(방안1, 실제 설계 = orientationNED 직접차분)는 사실상
    **오차 0에 가깝게 정확히** 실제 최종 헤딩(4.24deg 근방)과 일치해야
    한다 — 같은 필드(ccYawDeg)의 시작/끝 값을 그대로 빼는 연산이라 적분
    오차가 아예 없기 때문(설계 우위 확인)."""
    samples = REAL_FREEZE_WINDOW_SAMPLES
    t0, yaw0, _ = samples[0]

    anchored = AnchoredHeadingStateDiff()
    baseline = BaselineFrozenHeadingState()
    anchored.on_fix(yaw0, yaw0)  # 정체 시작 시점: bearing과 CC 둘 다 yaw0로 정렬
    baseline.on_fix(yaw0)

    t_end, yaw_end_true, _ = samples[-1]
    anchored_final = anchored.current(yaw_end_true)
    baseline_final = baseline.on_tick(0.0, 0.0)

    anchored_err = abs(shortest_diff_deg(anchored_final, yaw_end_true))
    baseline_err = abs(shortest_diff_deg(baseline_final, yaw_end_true))

    # Diff 방식은 시작/끝 절대값을 그대로 빼므로 부동소수 오차(<1e-6) 수준만
    # 나야 정상. baseline은 완전히 고정이라 실제 회전량만큼 크게 틀려야 함.
    anchored_ok = anchored_err < 1e-6
    baseline_wrong = baseline_err > 30.0
    ok = anchored_ok and baseline_wrong
    print(
        f"[real_freeze_reproduction] t={t0:.1f}~{t_end:.1f} "
        f"({t_end - t0:.1f}s), true_end={yaw_end_true:.2f}deg | "
        f"anchored(diff)={anchored_final:.4f}deg(err={anchored_err:.2e}) "
        f"baseline(frozen)={baseline_final:.2f}deg(err={baseline_err:.2f}) "
        f"-> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def test_diff_vs_integrated_cross_check():
    """165차 FINDINGS 미해결사항 2번: 실제 설계(Diff)와 교차검증용 대안
    (angularVelocity 적분)이 같은 실측 정체구간에서 서로 근접한 결과를
    내는지 확인 — 두 개의 독립 센서경로(orientationNED 절대값 vs
    angularVelocity 적분)가 자체정합적이면 locationd 추정기 신뢰도가
    높다는 방증. 완전 일치는 기대하지 않음(적분측만 이산화오차 있음)."""
    samples = REAL_FREEZE_WINDOW_SAMPLES
    t0, yaw0, _ = samples[0]

    diff_state = AnchoredHeadingStateDiff()
    integ_state = AnchoredHeadingStateIntegrated()
    diff_state.on_fix(yaw0, yaw0)
    integ_state.on_fix(yaw0)

    prev_t = t0
    for t, _yd, yaw_rate in samples[1:]:
        dt = t - prev_t
        integ_state.on_tick(yaw_rate, dt)
        prev_t = t

    t_end, yaw_end_true, _ = samples[-1]
    diff_final = diff_state.current(yaw_end_true)
    integ_final = integ_state.current()

    cross_diff = abs(shortest_diff_deg(diff_final, integ_final))
    # 24초 적분에 수 도 이내 이산화오차는 정상(둘 다 같은 물리량을 다른
    # 경로로 추정한 것이므로 자체정합성 확인 목적 - 과도한 괴리(>10deg)만
    # 이상신호로 취급)
    ok = cross_diff < 10.0
    print(
        f"[diff_vs_integrated_cross_check] diff(실제설계)={diff_final:.2f}deg "
        f"integrated(교차검증용)={integ_final:.2f}deg 괴리={cross_diff:.2f}deg "
        f"-> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def run_unit_tests():
    results = [
        test_reset_no_drift_over_many_fixes(),
        test_wrap_boundary_right_turn_synthetic(),
        test_wrap_boundary_left_turn_synthetic(),
        test_real_freeze_event_reproduction(),
        test_diff_vs_integrated_cross_check(),
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
