#!/usr/bin/env python3
"""227차: carrot_serv.py::update_navi()의 route_speed 상한 클램프
(225차 B, `min(v_ego_kph, max(route_speed, autoCurveSpeedLowerLimit))`)가
ACTIVE 추적 분기와 226차 ACTIVE 진입 게이트 ceiling 분기를 구분하지 않고
무차별 적용되어, vEgo<=apex_speed 구간에서 route_speed가 매 프레임 vEgo
그 자체로 고정 -> desired_speed(=min(route,...))도 vEgo로 고정 -> 가속
명령이 원천 봉쇄되는 회귀를 재현/검증한다.

carrot_man.py::carrot_navi_route() ACTIVE 상태기계(223/226차) +
carrot_serv.py::update_navi() route_speed 클램프(225차B/227차)를
1:1 재구현(OLD=225차B 그대로/NEW=227차 route_active 분기)해 두 버전을
동일 시나리오로 비교한다. 실제 소스 파일과의 대조는 README/WIP.md 참고.

실행: python3 sim_route_227_ceiling_clamp_scope.py
"""

DT = 0.05  # ROUTE_SPEED_LOOP_DT
AUTO_CURVE_LOWER = 30.0
ROUTE_APEX_REACHED_DIST_M = 10.0
DECEL_RATE = 1.5   # autoNaviSpeedDecelRate 가정값 (comfort cap, m/s^2)
ACCEL_RATE = 1.0   # 시뮬레이션용 단순 가속 모델(m/s^2) -- 실제 MPC 아님,
                    # "desired==vEgo 고착이면 가속이 전혀 없다"만 보이면 충분.


class RouteSim:
    """carrot_man.py::carrot_navi_route() ACTIVE 상태기계 핵심 재구현."""

    def __init__(self, apex_speed, apex_dist):
        self.apex_speed = apex_speed
        self.apex_dist = apex_dist
        self.route_active = False

    def step(self, v_ego_kph):
        v_ego_ms = v_ego_kph / 3.6
        if self.route_active and self.apex_dist <= ROUTE_APEX_REACHED_DIST_M:
            self.route_active = False
            return None
        elif not self.route_active and v_ego_kph <= self.apex_speed:
            # [226차] ceiling 유지, route_active는 False 그대로
            return self.apex_speed
        else:
            self.route_active = True
            target_ms = self.apex_speed / 3.6
            eff_dist = max(0.0, self.apex_dist - target_ms * 1.0)
            if v_ego_ms <= target_ms or eff_dist <= 0:
                out_ms = v_ego_ms
            else:
                required = (v_ego_ms**2 - target_ms**2) / (2.0 * eff_dist)
                applied = min(max(required, 0.0), DECEL_RATE)
                out_ms = max(target_ms, v_ego_ms - applied * DT)
            return out_ms * 3.6


def clamp_route_speed(route_out, v_ego_kph, route_active, mode):
    """carrot_serv.py::update_navi() route_speed 후처리.
    mode='OLD'(225차B, 무조건 vEgo 클램프) / 'NEW'(227차, route_active일 때만)."""
    if route_out is None:
        return None
    if mode == "OLD":
        return min(v_ego_kph, max(route_out, AUTO_CURVE_LOWER))
    else:
        if route_active:
            return min(v_ego_kph, max(route_out, AUTO_CURVE_LOWER))
        else:
            return max(route_out, AUTO_CURVE_LOWER)


def arbitrate(route_speed, v_cruise, road_limit):
    sources = [v_cruise, road_limit]
    if route_speed is not None:
        sources.append(route_speed)
    return min(sources)


def run_multiframe(mode, v_ego0, apex_speed, apex_dist, v_cruise, road_limit,
                    frames=400):
    sim = RouteSim(apex_speed, apex_dist)
    v_ego = v_ego0
    max_v = v_ego0
    for _ in range(frames):
        route_out = sim.step(v_ego)
        route_speed = clamp_route_speed(route_out, v_ego, sim.route_active, mode)
        desired = arbitrate(route_speed, v_cruise, road_limit)
        if desired > v_ego:
            v_ego = min(desired, v_ego + ACCEL_RATE * DT * 3.6)
        elif desired < v_ego:
            v_ego = max(desired, v_ego - DECEL_RATE * DT * 3.6)
        max_v = max(max_v, v_ego)
    return v_ego, max_v


results = []

def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


# CASE1: vEgo=60/apex=80/vCruise=100, 먼 apex(600m) -- 226차 WIP가 단일
# 프레임만 확인했던 시나리오를 다중 프레임(400 frame = 20s)으로 확장.
# OLD: route_speed가 매 프레임 min(vEgo,80)=vEgo로 고정 -> desired=vEgo
# 고정 -> 가속 0(회귀). NEW: route_active=False 구간에서 클램프 생략 ->
# route_speed=80 유지 -> desired=min(80,100,road)=80 -> 60에서 80까지
# 정상 가속 후 80에서 정지(ceiling 정상 작동).
final_old, max_old = run_multiframe("OLD", 60.0, 80.0, 600.0, 100.0, 130.0)
final_new, max_new = run_multiframe("NEW", 60.0, 80.0, 600.0, 100.0, 130.0)
check("CASE1-OLD-freeze-regression-reproduced",
      abs(final_old - 60.0) < 0.1,
      f"OLD final={final_old:.2f} (60 고착 재현 기대)")
check("CASE1-NEW-reaches-ceiling",
      abs(final_new - 80.0) < 0.5,
      f"NEW final={final_new:.2f} (80 ceiling까지 정상 가속 기대)")
check("CASE1-NEW-does-not-exceed-ceiling",
      max_new <= 80.0 + 0.5,
      f"NEW max={max_new:.2f}")

# CASE2: 정상 감속(vEgo=100 > apex=80, ACTIVE 추적 분기) -- OLD/NEW 완전
# 동일해야 함(route_active=True 구간은 두 모드 모두 동일 클램프 적용).
sim_old = RouteSim(80.0, 200.0)
sim_new = RouteSim(80.0, 200.0)
v_old = v_new = 100.0
diverged = False
for _ in range(200):
    ro = sim_old.step(v_old)
    rn = sim_new.step(v_new)
    rso = clamp_route_speed(ro, v_old, sim_old.route_active, "OLD")
    rsn = clamp_route_speed(rn, v_new, sim_new.route_active, "NEW")
    do = arbitrate(rso, 130.0, 130.0)
    dn = arbitrate(rsn, 130.0, 130.0)
    if abs(do - dn) > 0.01:
        diverged = True
    v_old = v_old + (min(do, v_old+ACCEL_RATE*DT*3.6) - v_old) if do > v_old else max(do, v_old-DECEL_RATE*DT*3.6)
    v_new = v_new + (min(dn, v_new+ACCEL_RATE*DT*3.6) - v_new) if dn > v_new else max(dn, v_new-DECEL_RATE*DT*3.6)
check("CASE2-normal-decel-no-regression", not diverged,
      f"OLD final={v_old:.2f} NEW final={v_new:.2f}")

# CASE3: Stop&Go -- vEgo=0, apex=45, 근접(eff_dist<=0 유발). ACTIVE
# 추적(inert) 분기 -- route_active=True이므로 두 모드 동일해야 하며,
# 224차 ceiling-fix 의도대로 vEgo=0을 그대로 통과(45로 밀어올리지 않음).
sim3 = RouteSim(45.0, 50.0)  # apex_dist=50m(>10, RELEASE 미유발), v_ego_ms<=target_ms로 inert 진입
sim3.route_active = True  # 이미 ACTIVE 추적 중이라고 가정(정지 직전 진입)
route_out3 = sim3.step(0.0)
rs3_old = clamp_route_speed(route_out3, 0.0, sim3.route_active, "OLD")
rs3_new = clamp_route_speed(route_out3, 0.0, sim3.route_active, "NEW")
check("CASE3-stop-inert-no-forced-accel",
      rs3_old == rs3_new and rs3_old <= AUTO_CURVE_LOWER + 0.1,
      f"route_out={route_out3:.2f} clamped={rs3_old:.2f} (ACTIVE 추적 분기라 OLD/NEW 동일 클램프 적용, vEgo=0을 30으로 밀어올리지 않음 -- 224/225차 의도 유지)")

# CASE4: apex 도달 -> RELEASE(out_speed=None) -- 두 모드 모두 None 그대로
# (클램프 로직이 route_speed is not None 가드 밖이므로 영향 없음).
sim4 = RouteSim(80.0, 5.0)
sim4.route_active = True
route_out4 = sim4.step(90.0)  # apex_dist=5<=10 -> RELEASE
check("CASE4-release-still-none", route_out4 is None, f"route_out={route_out4}")

# CASE5: NEW 모드 -- vEgo가 apex_speed보다 이미 높은 상태로 curve 구간에
# 진입하면(하강길 등, 226차 ceiling 분기가 관여하지 않는 정상 케이스)
# 즉시 ACTIVE 추적으로 들어가 apex_speed까지 정상 감속하는지 확인 --
# ceiling 분기(vEgo<=apex_speed) 신설이 이 기존 감속 경로를 건드리지
# 않았음을 재확인.
sim5 = RouteSim(80.0, 200.0)
v5 = 100.0
transitioned = False
for _ in range(1200):
    ro = sim5.step(v5)
    rs = clamp_route_speed(ro, v5, sim5.route_active, "NEW")
    d = arbitrate(rs, 130.0, 130.0)
    v5 = min(d, v5 + ACCEL_RATE*DT*3.6) if d > v5 else max(d, v5 - DECEL_RATE*DT*3.6)
    if sim5.route_active:
        transitioned = True
check("CASE5-active-tracking-unaffected-when-starting-above-apex",
      transitioned and abs(v5 - 80.0) < 0.5,
      f"transitioned={transitioned} final v5={v5:.2f}")

print()
passed = sum(1 for _, c, _ in results if c)
print(f"TOTAL: {passed}/{len(results)} PASS")
