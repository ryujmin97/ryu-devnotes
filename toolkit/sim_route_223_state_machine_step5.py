"""223차 STEP5 -- Route 감속 로직 전면 재설계(무상태 감속식 + route_active
상태기계) 합성 시뮬레이션.

설계 문서: design/223cha_design_instructions.md (원본 지시)
           design/223cha_step2_decel_formula.md (신규 감속식)
           design/223cha_step3_arbitration.md (arbitration 확인)

carrot_man.py::carrot_navi_route() 내 실제 구현 로직을 순수 함수(RouteSim)로
재구현해(상태는 인스턴스 dict-like 필드로 관리) design doc §20의 CASE 1~14
중 코드 레벨로 검증 가능한 항목을 합성 시나리오로 확인한다.

**주의 -- 이것은 실제 carrot_man.py를 import해서 도는 테스트가 아니라
독립 재구현이다.** openpilot 런타임 의존성(cereal, messaging 등) 없이
로직만 빠르게 검증하기 위한 목적 -- 기존 sim_route_* 스크립트들과 동일한
패턴(README 참고). 실제 코드와의 diff는 STEP6(사용자 diff 검토)에서
별도 확인 필요. **실차 검증: 미실시.**

실행: python3 sim_route_223_state_machine_step5.py
기대 결과: 모든 CASE가 PASS 출력, 마지막 줄에 "ALL STEP5 SIM CASES PASSED".
"""
import math

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0


class RouteSim:
    def __init__(self, decel_cap=1.0, safe_time=0.0):
        self.route_active = False
        self.route_release_time = None
        self.decel_cap = decel_cap
        self.safe_time = safe_time
        self.t = 0.0

    def step(self, mode, v_ego_kph, apex_dist, apex_speed_kph, candidates_empty=False):
        """한 프레임(20Hz) 시뮬레이션. apex_dist/apex_speed_kph는 candidates[0] 가정."""
        self.t += ROUTE_SPEED_LOOP_DT
        route_enabled = mode in (2, 3)
        if not route_enabled:
            self.route_active = False
            self.route_release_time = None
            return None
        if self.route_release_time is not None:
            if (self.t - self.route_release_time) < ROUTE_RELEASE_HOLD_S:
                return None
            self.route_release_time = None
        if candidates_empty:
            if self.route_active:
                self.route_active = False
                self.route_release_time = self.t
            return None

        v_ego_ms = v_ego_kph / 3.6
        if self.route_active and apex_dist <= ROUTE_APEX_REACHED_DIST_M:
            self.route_active = False
            self.route_release_time = self.t
            return None
        if not self.route_active and v_ego_kph <= apex_speed_kph:
            return None

        self.route_active = True
        target_ms = apex_speed_kph / 3.6
        eff_dist = max(0.0, apex_dist - target_ms * self.safe_time)
        if v_ego_ms <= target_ms or eff_dist <= 0:
            required = 0.0
        else:
            required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
        applied = min(max(required, 0.0), self.decel_cap)
        out_ms = max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
        return out_ms * 3.6


def run(name, fn):
    print(f"--- {name} ---")
    fn()
    print()


def test_mode01_off():
    sim = RouteSim()
    for mode in (0, 1):
        out = sim.step(mode, 80, 100, 40)
        assert out is None, f"mode{mode} should be OFF, got {out}"
    print("CASE1/2 PASS: mode 0/1 -> route always None")


def test_no_accel():
    sim = RouteSim()
    out = sim.step(2, 40, 100, 50)  # vEgo < target
    assert out is None, f"expected None (no accel), got {out}"
    print("CASE6/9 PASS: vEgo<target -> route OFF, never accel")


def test_decel_and_monotonic_vs_vego():
    sim = RouteSim(decel_cap=1.0)
    outs = []
    v = 80.0
    for i in range(200):
        apex_dist = max(0.0, 300 - i * 2.0)  # closing distance
        out = sim.step(2, v, apex_dist, 40)
        outs.append(out)
        if out is not None:
            assert out <= v + 1e-6, f"out {out} > vEgo {v} at frame {i}"
    active_outs = [o for o in outs if o is not None]
    assert len(active_outs) > 0
    print(f"CASE7 PASS: {len(active_outs)} active frames, out<=vEgo held for all, "
          f"first={active_outs[0]:.1f} last={active_outs[-1]:.1f} target=40")


def test_apex_release_and_hold():
    sim = RouteSim(decel_cap=2.0)
    v = 80.0
    reached = False
    release_frame = None
    for i in range(400):
        apex_dist = max(0.0, 200 - i * 1.0)
        out = sim.step(2, v, apex_dist, 40)
        if sim.route_active:
            v = out
        if not sim.route_active and sim.route_release_time is not None and release_frame is None:
            release_frame = i
        if apex_dist <= ROUTE_APEX_REACHED_DIST_M and not reached:
            reached = True
    assert release_frame is not None, "should have released after reaching apex"
    print(f"CASE8/9 PASS: released at frame {release_frame} (t={release_frame*0.05:.2f}s)")

    out_during_hold2 = sim.step(2, 80, 50, 20, candidates_empty=False)
    assert out_during_hold2 is None, f"expected hold to block re-activation, got {out_during_hold2}"
    print("CASE11 PASS: new sharper curve during 2s hold does not re-engage route")


def test_hold_expiry_then_research():
    sim = RouteSim(decel_cap=2.0)
    sim.route_active = False
    sim.route_release_time = 0.0
    sim.t = 2.1
    out = sim.step(2, 80, 100, 40)
    assert sim.route_active is True and out is not None
    print(f"CASE10 PASS: after hold expiry, new curve search re-engages -> out={out:.1f}")


def test_mode_switch_reset_midtrack():
    sim = RouteSim(decel_cap=1.0)
    sim.step(2, 80, 100, 40)
    assert sim.route_active is True
    out = sim.step(1, 80, 100, 40)  # switch to mode 1 mid-track
    assert out is None and sim.route_active is False and sim.route_release_time is None
    print("CASE12 PASS: mode 2->1 mid-ACTIVE resets immediately, no hold carried")


def test_stop_restart_curve_no_overshoot_above_vego():
    # 222cha found liveRouteSpeed > vEgo during stop->restart. New formula structurally
    # forbids out > vEgo (since out = max(target, vEgo - applied*dt) <= vEgo always).
    sim = RouteSim(decel_cap=1.0)
    violations = 0
    v = 1.5
    for i in range(100):
        v = min(60.0, v + 0.5)  # restarting acceleration
        apex_dist = 150.0
        out = sim.step(2, v, apex_dist, 40)
        if out is not None and out > v + 1e-9:
            violations += 1
    assert violations == 0
    print("CASE14 PASS: 0 frames with out_speed>vEgo during stop->restart (222cha bug structurally closed)")


if __name__ == "__main__":
    run("mode0/1 off", test_mode01_off)
    run("no-accel gate", test_no_accel)
    run("decel <= vEgo monotonic-safe", test_decel_and_monotonic_vs_vego)
    run("apex release + 2s hold", test_apex_release_and_hold)
    run("hold expiry -> re-search", test_hold_expiry_then_research)
    run("mode switch mid-active reset", test_mode_switch_reset_midtrack)
    run("stop->restart no vEgo overshoot", test_stop_restart_curve_no_overshoot_above_vego)
    print("ALL STEP5 SIM CASES PASSED")
