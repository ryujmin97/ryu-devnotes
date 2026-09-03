#!/usr/bin/env python3
"""228차 v2 실제 패치 diff 기준 엣지케이스 A~J 검증 (수정판).

1차 시도(sim_route_228_edge_cases_AJ.py)에서 B/C/D/E/F를 단일 프레임으로
구성했다가 route_active가 아직 False인 첫 프레임이라 226차 GATE_CEILING
분기나 RELEASE 분기로 먼저 빠지는 문제를 발견(228차 route_inert 분기는
route_active=True로 이미 추적 중일 때만 의미가 있음). 이 v2는 먼저 vEgo>target
조건으로 ACTIVE 진입 프레임을 한 번 통과시킨 뒤, 다음 프레임에서 각 케이스의
vEgo/eff_dist 조건을 적용하는 2-프레임 구성으로 수정했다.

실차 검증: 미실시. 합성 시나리오(단순 차량모델) 시뮬레이션만 수행.
"""

DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0
AUTO_CURVE_LOWER = 30.0
DECEL_RATE = 1.5
CTRL_END = 1.0
LOOKAHEAD_CAP_M = 600.0

results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


class PatchedRouteSim:
    def __init__(self, curves):
        self.curves = curves
        self.route_active = False
        self.route_inert = False
        self.route_release_time = None
        self.t = 0.0

    def _find_candidate(self, x):
        for apex_x, apex_speed in self.curves:
            if apex_x > x and (apex_x - x) <= LOOKAHEAD_CAP_M:
                return apex_x, apex_speed
        return None

    def step(self, x, v_ego_kph, route_enabled=True):
        self.t += DT
        v_ego_ms = v_ego_kph / 3.6

        if not route_enabled:
            self.route_active = False
            self.route_inert = False
            self.route_release_time = None
            return None, "MODE_OFF"

        if self.route_release_time is not None:
            if (self.t - self.route_release_time) < ROUTE_RELEASE_HOLD_S:
                return None, "HOLD"
            self.route_release_time = None

        cand = self._find_candidate(x)
        if cand is None:
            released = False
            if self.route_active:
                self.route_active = False
                self.route_inert = False
                self.route_release_time = self.t
                released = True
            return None, ("RELEASE_NO_CANDIDATE" if released else "NO_CANDIDATE_INACTIVE")

        apex_x, apex_speed = cand
        apex_dist = apex_x - x

        if self.route_active and apex_dist <= ROUTE_APEX_REACHED_DIST_M:
            self.route_active = False
            self.route_inert = False
            self.route_release_time = self.t
            return None, "RELEASE_APEX_REACHED"
        elif not self.route_active and v_ego_kph <= apex_speed:
            self.route_inert = False
            return apex_speed, "GATE_CEILING"
        else:
            self.route_active = True
            target_ms = apex_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * CTRL_END)
            if eff_dist <= 0:
                out_ms = v_ego_ms
                self.route_inert = False
                branch = "EFF_DIST_LE_0"
            elif v_ego_ms <= target_ms:
                out_ms = target_ms
                self.route_inert = True
                branch = "FAR_INERT"
            else:
                required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                applied = min(max(required, 0.0), DECEL_RATE)
                out_ms = max(target_ms, v_ego_ms - applied * DT)
                self.route_inert = False
                branch = "DECEL_FORMULA"
            return out_ms * 3.6, branch


def clamp_route_speed(route_out, v_ego_kph, route_active, route_inert):
    if route_out is None:
        return None
    if route_active and not route_inert:
        return min(v_ego_kph, max(route_out, AUTO_CURVE_LOWER))
    else:
        return max(route_out, AUTO_CURVE_LOWER)


def enter_active(curve_apex_x, curve_apex_speed, entry_v_kph=90.0):
    """vEgo>target, eff_dist>0인 진입 프레임을 통과시켜 route_active=True로
    만든 sim 인스턴스를 반환(x=0 시점)."""
    sim = PatchedRouteSim([(curve_apex_x, curve_apex_speed)])
    out, branch = sim.step(x=0.0, v_ego_kph=entry_v_kph)
    assert sim.route_active, f"진입 실패: branch={branch}"
    assert branch == "DECEL_FORMULA", f"진입 프레임이 예상과 다름: branch={branch}"
    return sim


# ============================================================
# A. vEgo > target, eff_dist > 0 -> DECEL_FORMULA, route_inert=False
# ============================================================
sim = enter_active(300.0, 50.0, entry_v_kph=90.0)
out = None
# 진입 프레임 자체가 이미 A 조건(vEgo=90>target=50, eff_dist>0)이므로 이 프레임 결과를 그대로 사용
out, branch = sim.step(x=0.0, v_ego_kph=90.0)  # 재확인용 재호출(같은 프레임 조건 반복)
route_speed = clamp_route_speed(out, 90.0, sim.route_active, sim.route_inert)
check("A-branch-is-decel-formula", branch == "DECEL_FORMULA", f"branch={branch}")
check("A-route-inert-false", sim.route_inert is False, f"route_inert={sim.route_inert}")
check("A-out-le-vego", out <= 90.0 + 1e-9, f"out={out:.3f}")
check("A-clamp-applies-vego-ceiling", abs(route_speed - min(90.0, max(out, AUTO_CURVE_LOWER))) < 1e-9,
      f"route_speed={route_speed:.3f}")

# ============================================================
# B. vEgo == target, eff_dist > 0 (이미 ACTIVE 추적 중) -> FAR_INERT, route_inert=True
# ============================================================
sim = enter_active(300.0, 50.0, entry_v_kph=90.0)
out, branch = sim.step(x=10.0, v_ego_kph=50.0)  # apex_dist=290, eff_dist>>0, v_ego_ms==target_ms
route_speed = clamp_route_speed(out, 50.0, sim.route_active, sim.route_inert)
check("B-active-already-true", sim.route_active is True, f"route_active={sim.route_active}")
check("B-branch-is-far-inert", branch == "FAR_INERT", f"branch={branch}")
check("B-route-inert-true", sim.route_inert is True, f"route_inert={sim.route_inert}")
check("B-out-equals-target", abs(out - 50.0) < 1e-6, f"out={out:.3f}")
check("B-clamp-skips-vego-ceiling", abs(route_speed - max(out, AUTO_CURVE_LOWER)) < 1e-9,
      f"route_speed={route_speed:.3f} (vEgo=50 상한 클램프 생략 확인)")

# ============================================================
# C. vEgo < target, eff_dist > 0 (이미 ACTIVE) -> FAR_INERT, route_inert=True
# ============================================================
sim = enter_active(300.0, 50.0, entry_v_kph=90.0)
out, branch = sim.step(x=10.0, v_ego_kph=20.0)  # apex_dist=290, v_ego_ms(5.56)<target_ms(13.89)
route_speed = clamp_route_speed(out, 20.0, sim.route_active, sim.route_inert)
check("C-branch-is-far-inert", branch == "FAR_INERT", f"branch={branch}")
check("C-route-inert-true", sim.route_inert is True, f"route_inert={sim.route_inert}")
check("C-out-equals-target-not-vego", abs(out - 50.0) < 1e-6,
      f"out={out:.3f} (v_ego=20이 아니라 target=50 ceiling 유지)")
check("C-clamp-not-dragged-to-vego", route_speed >= 20.0,
      f"route_speed={route_speed:.3f} (20으로 눌리지 않음)")

# ============================================================
# D. vEgo = 0, eff_dist > 0 (이미 ACTIVE, 고착 방지 핵심 케이스) -> FAR_INERT, route_inert=True
# ============================================================
sim = enter_active(300.0, 50.0, entry_v_kph=90.0)
out, branch = sim.step(x=10.0, v_ego_kph=0.0)  # apex_dist=290, v_ego=0
route_speed = clamp_route_speed(out, 0.0, sim.route_active, sim.route_inert)
check("D-branch-is-far-inert", branch == "FAR_INERT", f"branch={branch}")
check("D-route-inert-true", sim.route_inert is True, f"route_inert={sim.route_inert}")
check("D-out-equals-target-not-zero", abs(out - 50.0) < 1e-6,
      f"out={out:.3f} (v_ego=0인데도 ceiling=target=50 유지)")
check("D-clamp-not-locked-to-zero", route_speed > 0.0,
      f"route_speed={route_speed:.3f} (228차 고착 버그의 핵심 -- 0에 갇히지 않음)")

# ============================================================
# E. vEgo > target, eff_dist <= 0 -> EFF_DIST_LE_0, route_inert=False, out=v_ego(224차 유지)
# ============================================================
# apex_dist=8m(<10m RELEASE 임계보다 작지만, 첫 프레임엔 route_active=False라
# RELEASE 분기 대상이 아님). target=30kph -> target_ms*CTRL_END=8.33m > apex_dist=8m
# 이므로 eff_dist=max(0,8-8.33)=0 (<=0) 확정.
sim = PatchedRouteSim([(8.0, 30.0)])
out, branch = sim.step(x=0.0, v_ego_kph=60.0)
route_speed = clamp_route_speed(out, 60.0, sim.route_active, sim.route_inert)
check("E-branch-is-eff-dist-le-0", branch == "EFF_DIST_LE_0", f"branch={branch}")
check("E-route-inert-false", sim.route_inert is False, f"route_inert={sim.route_inert}")
check("E-out-equals-vego", abs(out - 60.0) < 1e-6, f"out={out:.3f} (224차 의도: vEgo 그대로 통과)")
check("E-clamp-applies-vego-ceiling", abs(route_speed - min(60.0, max(out, AUTO_CURVE_LOWER))) < 1e-9,
      f"route_speed={route_speed:.3f}")

# ============================================================
# F. vEgo = 0, eff_dist <= 0 -> EFF_DIST_LE_0, route_inert=False, floor 미노출(2차 버그 회귀 방지)
# ============================================================
# target=50kph -> target_ms*CTRL_END=13.89m > ROUTE_APEX_REACHED_DIST_M(10m)이므로
# apex_dist in (10, 13.89] 구간에서 "apex 미도달(RELEASE 아님) & eff_dist<=0"이 동시 성립
# (WIP.md 228차 재탐색 조건과 동일 원리: apex_dist>10 및 eff_dist<=0 동시 만족).
sim = PatchedRouteSim([(200.0, 50.0)])
out1, branch1 = sim.step(x=0.0, v_ego_kph=90.0)   # ACTIVE 진입(DECEL_FORMULA), apex_dist=200
out2, branch2 = sim.step(x=188.0, v_ego_kph=0.0)  # apex_dist=12(>10, RELEASE 아님), eff_dist=12-13.89<0->0
route_speed = clamp_route_speed(out2, 0.0, sim.route_active, sim.route_inert)
check("F-apex-not-yet-released", sim.route_active is True, f"route_active={sim.route_active}")
check("F-branch-is-eff-dist-le-0", branch2 == "EFF_DIST_LE_0", f"branch2={branch2}")
check("F-route-inert-false", sim.route_inert is False, f"route_inert={sim.route_inert}")
check("F-out-is-zero", abs(out2 - 0.0) < 1e-6, f"out2={out2:.3f}")
check("F-no-floor-regression", route_speed == 0.0,
      f"route_speed={route_speed:.3f} (floor 30으로 밀려 올라가면 회귀, 228차 2차 버그)")

# ============================================================
# G. apex 도달 후 release/2초 hold
# ============================================================
sim = PatchedRouteSim([(50.0, 40.0)])
out, branch = sim.step(x=0.0, v_ego_kph=60.0)
check("G-active-entered", sim.route_active is True, f"route_active={sim.route_active}")
out, branch = sim.step(x=42.0, v_ego_kph=40.0)  # apex_dist=8<=10
check("G-release-on-apex-reached", branch == "RELEASE_APEX_REACHED", f"branch={branch}")
check("G-active-false-after-release", sim.route_active is False, f"route_active={sim.route_active}")
check("G-inert-false-after-release", sim.route_inert is False, f"route_inert={sim.route_inert}")
check("G-release-time-set", sim.route_release_time is not None, f"release_time={sim.route_release_time}")
out, event = sim.step(x=42.5, v_ego_kph=40.0)
check("G-hold-returns-none", out is None and event == "HOLD", f"out={out}, event={event}")
for _ in range(int(2.0 / DT) + 1):
    out, event = sim.step(x=42.5, v_ego_kph=40.0)
check("G-hold-expires", sim.route_release_time is None, f"release_time={sim.route_release_time}")

# ============================================================
# H. Stop&Go 후 재출발 (far-inert 고착 방지 통합 확인, 물리모델 포함)
# ============================================================
sim = PatchedRouteSim([(500.0, 40.0)])
x, v = 0.0, 90.0
min_v_during_stop = 999.0
recovered = False
for i in range(2000):
    t = (i + 1) * DT
    if t < 10.0:
        v_cruise = 90.0
    elif t < 30.0:
        v_cruise = 0.0
    else:
        v_cruise = 90.0
    out, branch = sim.step(x=x, v_ego_kph=v)
    route_speed = clamp_route_speed(out, v, sim.route_active, sim.route_inert)
    desired = min(v_cruise, route_speed) if route_speed is not None else v_cruise
    if desired > v:
        v = min(desired, v + 1.0 * DT * 3.6)
    elif desired < v:
        v = max(desired, v - 2.5 * DT * 3.6)
    x += (v / 3.6) * DT
    if 10.0 <= t <= 30.0:
        min_v_during_stop = min(min_v_during_stop, v)
    if t > 32.0 and v > 25.0:
        recovered = True
check("H-vehicle-actually-stops", min_v_during_stop < 1.0, f"min_v={min_v_during_stop:.2f}")
check("H-recovers-after-cruise-restored", recovered, f"recovered={recovered}, final_v={v:.2f}")

# ============================================================
# I. mode 0/1 진입 (ACTIVE 추적 도중 route_enabled=False)
# ============================================================
sim = enter_active(300.0, 50.0, entry_v_kph=90.0)
check("I-active-before-mode-off", sim.route_active is True, f"route_active={sim.route_active}")
out, branch = sim.step(x=50.0, v_ego_kph=70.0, route_enabled=False)
check("I-mode-off-out-none", out is None and branch == "MODE_OFF", f"out={out}, branch={branch}")
check("I-active-reset", sim.route_active is False, f"route_active={sim.route_active}")
check("I-inert-reset", sim.route_inert is False, f"route_inert={sim.route_inert}")
check("I-release-time-cleared", sim.route_release_time is None, f"release_time={sim.route_release_time}")

# ============================================================
# J. candidate 소실 후 release (far-inert 상태에서 곡선이 사라지는 경우 포함)
# ============================================================
sim = enter_active(100.0, 20.0, entry_v_kph=30.0)  # 진입 즉시 far-inert 유도 위해 target에 근접한 속도로 진입
# 위 enter_active는 DECEL_FORMULA 진입을 강제하므로, 먼저 진입시킨 뒤 다음 프레임에서 far-inert로 전환
out, branch = sim.step(x=50.0, v_ego_kph=10.0)  # apex_dist=50, target_ms=5.56, v_ego_ms=2.78<=target_ms -> FAR_INERT
check("J-far-inert-before-loss", branch == "FAR_INERT" and sim.route_inert is True,
      f"branch={branch}, route_inert={sim.route_inert}")
out, event = sim.step(x=150.0, v_ego_kph=10.0)  # apex(100)를 지나침 -> candidate 없음
check("J-release-no-candidate", event == "RELEASE_NO_CANDIDATE", f"event={event}")
check("J-active-false-after-loss", sim.route_active is False, f"route_active={sim.route_active}")
check("J-inert-false-after-loss", sim.route_inert is False,
      f"route_inert={sim.route_inert} (far-inert 마킹이 RELEASE 시 함께 해제됨)")

print()
n_pass = sum(1 for _, c, _ in results if c)
print(f"TOTAL: {n_pass}/{len(results)} PASS")
