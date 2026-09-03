"""224차 -- carrot_serv.py::update_navi() autoCurveSpeedLowerLimit 바닥값이
route_speed를 vEgo 위로 재상승시키는 버그 수정 검증 합성 시뮬레이션.

배경("224차 Route 로직 수정 지침" §5 + carrot_man.py 224차 ceiling-fix):
  carrot_man.py::carrot_navi_route()의 224차 ceiling-fix(§2/§4)로
  route_speed(out_speed)는 항상 v_ego_kph 이하로 보장된다(정지 중이면
  route_speed=0, target 이하로 감속 중인 vEgo면 route_speed=vEgo 그대로
  통과/inert).

  그런데 carrot_serv.py::update_navi()는 이 값을 넘겨받은 뒤
      route_speed = max(route_speed, self.autoCurveSpeedLowerLimit)
  (구코드, autoCurveSpeedLowerLimit 기본값 30 -- common/params_keys.h,
  UI 범위 30~200 -- settings.cc) 를 무조건 적용한다. route_speed가 정지
  중(0) 또는 저속(<30kph)이면 이 한 줄이 30(또는 사용자 설정값)으로 다시
  밀어올려, carrot_man.py가 막 제거한 "route가 vEgo보다 높은 값을 명령"
  버그를 carrot_serv.py 쪽에서 재현시킨다.

  수정: route_speed = min(v_ego_kph, max(route_speed, autoCurveSpeedLowerLimit))
  바닥값 자체의 보호 목적(곡률 계산 노이즈로 target이 비정상적으로 낮게
  나오는 것 방지)은 유지하되, v_ego_kph를 넘지 않도록 다시 상한을 씌운다.

  이 스크립트는 carrot_man.py 224차 ceiling-fix(RouteSimNEW, 기존
  sim_route_224_ceiling_fix.py와 동일 재구현)의 출력을 입력으로 받아
  OLD(구 바닥로직) vs NEW(수정 바닥로직)의 carrot_serv.py 단계를 대조한다.

실행: python3 sim_route_224_serv_floor_fix.py
기대 결과: 모든 CASE PASS, 마지막 줄 "ALL 224CHA SERV-FLOOR-FIX CASES PASSED".
**실차 검증: 미실시.**
"""

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0
AUTO_CURVE_SPEED_LOWER_LIMIT_DEFAULT = 30.0  # common/params_keys.h 기본값


class RouteSimNEW:
    """carrot_man.py 224차 ceiling-fix (sim_route_224_ceiling_fix.py::RouteSimNEW
    와 동일 재구현) -- route_speed(out_speed)는 항상 v_ego 이하."""

    def __init__(self, decel_cap=1.0, ctrl_end=0.0):
        self.route_active = False
        self.route_release_time = None
        self.decel_cap = decel_cap
        self.ctrl_end = ctrl_end
        self.t = 0.0

    def step(self, mode, v_ego_kph, apex_dist, apex_speed_kph, candidates_empty=False):
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
        if v_ego_ms <= target_ms:
            out_ms = v_ego_ms
        else:
            eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end)
            if eff_dist <= 0:
                required = 0.0
            else:
                required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            applied = min(max(required, 0.0), self.decel_cap)
            out_ms = max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
        return out_ms * 3.6


def serv_floor_old(route_speed, v_ego_kph, lower_limit=AUTO_CURVE_SPEED_LOWER_LIMIT_DEFAULT):
    """carrot_serv.py 구코드: route_speed = max(route_speed, lower_limit)."""
    return max(route_speed, lower_limit)


def serv_floor_new(route_speed, v_ego_kph, lower_limit=AUTO_CURVE_SPEED_LOWER_LIMIT_DEFAULT):
    """carrot_serv.py 224차 수정: min(v_ego_kph, max(route_speed, lower_limit))."""
    return min(v_ego_kph, max(route_speed, lower_limit))


results = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append(cond)
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


def run(name, fn):
    print(f"--- {name} ---")
    fn()
    print()


# ---------------------------------------------------------------------------
# CASE 1 (224차 실차로그 재현 -- 정지 중) -- carrot_man.py는 vEgo=0을 그대로
# 통과(route_speed=0)시키지만, OLD 바닥로직이 이를 30kph로 재상승시켜
# "정지 중 route가 30kph를 명령"하는, carrot_man.py 수정이 막 없앤 바로
# 그 버그를 재현한다. NEW는 v_ego=0을 상한으로 다시 씌워 0을 유지해야 한다.
# ---------------------------------------------------------------------------
def case1_stopped_floor_reintroduces_bug():
    sim = RouteSimNEW(decel_cap=2.0)
    sim.step(3, 90.0, 300.0, 80.0)  # ACTIVE 진입
    for _ in range(20):
        route_speed = sim.step(3, 0.0, 40.0, 80.0)  # 정지 유지, apex 도달 전
    check("case1: carrot_man.py 224cha fix already outputs 0 while stopped",
          route_speed is not None and abs(route_speed - 0.0) < 1e-6,
          f"route_speed={route_speed}")
    old_final = serv_floor_old(route_speed, 0.0)
    new_final = serv_floor_new(route_speed, 0.0)
    check("case1/OLD: floor reintroduces the bug (out==30, vEgo==0)",
          abs(old_final - 30.0) < 1e-6 and old_final > 0.0,
          f"old_final={old_final}")
    check("case1/NEW: floor capped at vEgo, out==0 (no phantom accel)",
          abs(new_final - 0.0) < 1e-6,
          f"new_final={new_final}")


# ---------------------------------------------------------------------------
# CASE 2 (저속 주행, 정지 아님) -- v_ego=15kph(< lower_limit=30), route가
# target=10kph 이하로 inert 통과 중이라고 가정(route_speed=15, vEgo와 동일).
# OLD는 30으로 밀어올려 vEgo(15)를 초과. NEW는 vEgo(15)로 캡.
# ---------------------------------------------------------------------------
def case2_low_speed_not_stopped():
    sim = RouteSimNEW(decel_cap=2.0)
    sim.step(3, 90.0, 300.0, 80.0)
    route_speed = sim.step(3, 15.0, 40.0, 10.0)  # target(10) < vEgo(15) -> 정상 감속경로
    old_final = serv_floor_old(route_speed, 15.0)
    new_final = serv_floor_new(route_speed, 15.0)
    check("case2/OLD: floor pushes output above vEgo(15) -> 30",
          old_final > 15.0, f"old_final={old_final}")
    check("case2/NEW: output capped at vEgo(15), never exceeds it",
          new_final <= 15.0 + 1e-9, f"new_final={new_final}")


# ---------------------------------------------------------------------------
# CASE 3 (바닥값의 원래 보호 기능은 유지) -- route_speed가 정상 감속 경로로
# vEgo보다 낮지만 lower_limit보다도 낮게(예: 곡률 노이즈로 target=5kph 근접)
# 나오는 상황에서, vEgo가 충분히 높으면(예: 50kph) 바닥값이 여전히
# route_speed를 30까지 끌어올려야 한다(§27 -- 바닥값 자체의 기존 보호
# 목적은 손대지 않음, "v_ego 이하로만" 상한을 추가한 것뿐).
# ---------------------------------------------------------------------------
def case3_floor_still_protects_when_room_available():
    route_speed = 5.0  # 가정: 정상 감속 경로 중 노이즈로 target 근접, 5kph
    v_ego_kph = 50.0
    old_final = serv_floor_old(route_speed, v_ego_kph)
    new_final = serv_floor_new(route_speed, v_ego_kph)
    check("case3: floor still raises route_speed to 30 when vEgo(50) has room",
          abs(new_final - 30.0) < 1e-6 and new_final == old_final,
          f"old_final={old_final}, new_final={new_final}")


# ---------------------------------------------------------------------------
# REGRESSION -- 정상 고속 감속 경로(vEgo>target>lower_limit)에서는
# 바닥값이 애초에 무관(= max()에서 route_speed가 이미 더 큼) -- OLD==NEW.
# ---------------------------------------------------------------------------
def regression_normal_decel_floor_irrelevant():
    sim = RouteSimNEW(decel_cap=2.0)
    sim.step(3, 90.0, 300.0, 80.0)
    route_speed = sim.step(3, 85.0, 200.0, 80.0)  # vEgo>target, 정상 감속 램프 중
    v_ego_kph = 85.0
    old_final = serv_floor_old(route_speed, v_ego_kph)
    new_final = serv_floor_new(route_speed, v_ego_kph)
    check("regression: normal decel (route_speed>>floor, <vEgo) OLD==NEW unaffected",
          abs(old_final - new_final) < 1e-9 and new_final <= v_ego_kph + 1e-9,
          f"old_final={old_final}, new_final={new_final}")


if __name__ == "__main__":
    run("CASE1 stopped -- floor reintroduces 224cha-fixed bug (OLD) vs capped (NEW)",
        case1_stopped_floor_reintroduces_bug)
    run("CASE2 low speed, not stopped -- OLD exceeds vEgo, NEW capped",
        case2_low_speed_not_stopped)
    run("CASE3 floor still protects target when vEgo has room (no regression)",
        case3_floor_still_protects_when_room_available)
    run("REGRESSION normal decel path, floor irrelevant, OLD==NEW",
        regression_normal_decel_floor_irrelevant)

    if all(results):
        print("ALL 224CHA SERV-FLOOR-FIX CASES PASSED")
    else:
        print(f"FAILED: {results.count(False)}/{len(results)} checks failed")
        raise SystemExit(1)
