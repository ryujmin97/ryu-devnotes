#!/usr/bin/env python3
"""
134차: long_mpc.py의 _discontinuity_jerk_boost_timer/_discontinuity_trigger_source
"arm" 지점(discontinuity/discontinuity_lc/handoff/low_speed_strong_decel,
4곳)이 서로를 덮어쓸 때의 우선순위/기간을 검증하는 로직단위 시뮬레이션.

배경: 112차가 low_speed_strong_decel arm에 "이미 부스트 진행 중이면
덮어쓰지 않음"(timer<=0.0 가드)을 넣었는데, 반대 방향(plain 'discontinuity'
가 이미 진행 중인 더 긴 hold를 덮어써 단축시키는 경우)은 보호가 없었음
(134차 정적 리뷰 발견). 아래 arm() 함수는 long_mpc.py 패치 후 코드를
리터럴 이식한 것 -- 실제 파일과 분기 구조가 달라지면 이 스크립트도 함께
갱신 필요.

의존성: 없음(표준 라이브러리만).
"""

RADAR_HANDOFF_JERK_BOOST_S = 4.0
DISCONTINUITY_JERK_COST_BOOST_S = 1.0


class BoostArmState:
    """long_mpc.py의 관련 인스턴스 필드만 최소 재현."""

    def __init__(self):
        self.timer = 0.0
        self.source = None
        self.handoff_release_value = None
        self.lc_danger_confirm_timer = 0.0

    def tick(self, dt=0.05):
        self.timer = max(0.0, self.timer - dt)

    # --- 134차 패치 후 arm 지점 (long_mpc.py L1085-1108 리터럴 이식) ---
    def arm_discontinuity_or_lc(self, lane_change_active):
        if lane_change_active:
            self.timer = RADAR_HANDOFF_JERK_BOOST_S
            self.source = 'discontinuity_lc'
            self.handoff_release_value = None
            self.lc_danger_confirm_timer = 0.0
        elif self.timer <= 0.0 or self.source == 'discontinuity':
            self.timer = DISCONTINUITY_JERK_COST_BOOST_S
            self.source = 'discontinuity'
            self.handoff_release_value = None
            self.lc_danger_confirm_timer = 0.0
        # else: 더 긴 hold 소스 보존, 아무것도 안 건드림

    # --- handoff/low_speed_strong_decel: 기존 그대로(무조건 덮어씀 or
    # 자기 자신만 가드) ---
    def arm_handoff(self):
        self.timer = RADAR_HANDOFF_JERK_BOOST_S
        self.source = 'handoff'
        self.handoff_release_value = None

    def arm_low_speed_strong_decel(self):
        if self.timer <= 0.0:
            self.timer = RADAR_HANDOFF_JERK_BOOST_S
            self.source = 'low_speed_strong_decel'
            self.handoff_release_value = None


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    return cond


def scenario_1_no_active_boost_arms_normally():
    s = BoostArmState()
    s.arm_discontinuity_or_lc(lane_change_active=False)
    return check(
        "S1: 무boost 상태 -> plain discontinuity 1.0s 정상 arm",
        s.source == 'discontinuity' and abs(s.timer - 1.0) < 1e-9,
    )


def scenario_2_low_speed_active_not_downgraded_by_plain_discontinuity():
    s = BoostArmState()
    s.arm_low_speed_strong_decel()
    s.tick(dt=1.0)  # 3.0s 남음
    remaining_before = s.timer
    s.arm_discontinuity_or_lc(lane_change_active=False)
    ok = (
        s.source == 'low_speed_strong_decel'
        and abs(s.timer - remaining_before) < 1e-9
    )
    return check(
        "S2(134차 수정 검증): low_speed_strong_decel(4.0s, 3.0s 남음) 진행 중"
        " plain discontinuity 트리거 -> 덮어쓰지 않고 보존",
        ok,
    )


def scenario_3_discontinuity_lc_not_downgraded_by_plain_discontinuity():
    s = BoostArmState()
    s.arm_discontinuity_or_lc(lane_change_active=True)
    s.tick(dt=0.5)
    s.lc_danger_confirm_timer = 0.15  # 진행 중이던 confirm 누적치(가상)
    remaining_before = s.timer
    confirm_before = s.lc_danger_confirm_timer
    s.arm_discontinuity_or_lc(lane_change_active=False)
    ok = (
        s.source == 'discontinuity_lc'
        and abs(s.timer - remaining_before) < 1e-9
        and abs(s.lc_danger_confirm_timer - confirm_before) < 1e-9
    )
    return check(
        "S3(134차 수정 검증): discontinuity_lc 진행 중(confirm 누적치 포함)"
        " plain discontinuity 트리거 -> hold/confirm 모두 보존",
        ok,
    )


def scenario_4_handoff_not_downgraded_by_plain_discontinuity():
    s = BoostArmState()
    s.arm_handoff()
    s.tick(dt=2.0)
    remaining_before = s.timer
    s.arm_discontinuity_or_lc(lane_change_active=False)
    ok = s.source == 'handoff' and abs(s.timer - remaining_before) < 1e-9
    return check(
        "S4(134차 수정 검증): handoff(4.0s, 2.0s 남음) 진행 중"
        " plain discontinuity 트리거 -> 덮어쓰지 않고 보존",
        ok,
    )


def scenario_5_same_source_retrigger_still_refreshes():
    s = BoostArmState()
    s.arm_discontinuity_or_lc(lane_change_active=False)
    s.tick(dt=0.8)  # 0.2s 남음
    s.arm_discontinuity_or_lc(lane_change_active=False)  # 같은 소스 재트리거
    return check(
        "S5(회귀 없음): 같은 'discontinuity' 소스 재트리거는 기존처럼"
        " 1.0s로 리프레시",
        s.source == 'discontinuity' and abs(s.timer - 1.0) < 1e-9,
    )


def scenario_6_expired_boost_arms_normally_even_if_source_stale():
    s = BoostArmState()
    s.arm_handoff()
    s.tick(dt=10.0)  # 완전 소진(timer<=0), source 필드는 'handoff'로 남아있음
    s.arm_discontinuity_or_lc(lane_change_active=False)
    return check(
        "S6: 이전 소스가 이미 소진(timer<=0)된 상태 -> stale source 태그와"
        " 무관하게 정상 arm",
        s.source == 'discontinuity' and abs(s.timer - 1.0) < 1e-9,
    )


def scenario_7_lc_trigger_always_overwrites_with_same_duration():
    # discontinuity_lc/handoff/low_speed_strong_decel은 서로 전부 4.0s라
    # 덮어써도 기간 단축이 없음 -- 기존처럼 무조건 덮어쓰는 게 안전.
    s = BoostArmState()
    s.arm_low_speed_strong_decel()
    s.tick(dt=3.5)  # 0.5s 남음
    s.arm_discontinuity_or_lc(lane_change_active=True)  # 새 LC discontinuity
    return check(
        "S7(설계 유지 확인): low_speed_strong_decel(0.5s 남음) 도중 새"
        " discontinuity_lc 발생 -> 동일 4.0s로 정상 재시작(단축 아님)",
        s.source == 'discontinuity_lc' and abs(s.timer - 4.0) < 1e-9,
    )


if __name__ == '__main__':
    results = [
        scenario_1_no_active_boost_arms_normally(),
        scenario_2_low_speed_active_not_downgraded_by_plain_discontinuity(),
        scenario_3_discontinuity_lc_not_downgraded_by_plain_discontinuity(),
        scenario_4_handoff_not_downgraded_by_plain_discontinuity(),
        scenario_5_same_source_retrigger_still_refreshes(),
        scenario_6_expired_boost_arms_normally_even_if_source_stale(),
        scenario_7_lc_trigger_always_overwrites_with_same_duration(),
    ]
    n_pass = sum(results)
    print(f"\n{n_pass}/{len(results)} PASS")
    raise SystemExit(0 if n_pass == len(results) else 1)
