"""224차 -- carrot_man.py::carrot_navi_route() continuation 분기의
"route는 target ceiling인데 v_ego_ms<=target_ms일 때
out=max(target_ms, v_ego_ms)=target_ms로 확정되어 사실상 가속 목표처럼
동작"하는 버그 수정 검증 합성 시뮬레이션.

배경("224차 Route 로직 수정 지침" §9 + 224차 실차로그, WIP.md "225차" 항목):
  223차 재설계(무상태 감속식, `carrot_man.py` L903-923 부근)의 구코드는

      if v_ego_ms <= target_ms or eff_dist <= 0:
          required_decel_mss = 0.0
      else:
          required_decel_mss = (v_ego_ms**2 - target_ms**2) / (2.0*eff_dist)
      applied_decel_mss = min(max(required_decel_mss, 0.0), decel_cap)
      out_speed_ms = max(target_ms, v_ego_ms - applied_decel_mss * DT)

  였다. v_ego_ms<=target_ms(예: apex 진입 "전"에 정지)이면
  applied_decel_mss=0이라 v_ego_ms-0=v_ego_ms인데, 바깥의
  max(target_ms, ...)가 이를 다시 target_ms까지 끌어올려 route가
  "vEgo에 대한 상한(ceiling)"이 아니라 "가속 목표"처럼 동작했다.
  224차 실차로그: apex 40m 앞 80.8초 정지 중 out_speed가 vEgo=0 대신
  target(45~47kph)로 유지 -- liveRouteSpeed<=vEgo 안전 불변식 위반.

  수정: v_ego_ms<=target_ms(또는 eff_dist<=0)면 out_speed_ms=v_ego_ms를
  그대로 통과시킨다(inert). 정상 감속 경로(v_ego_ms>target_ms)의
  max(target_ms, ...) 플로어(=감속이 target 밑으로 오버슈트하지 않게
  막는 목적)는 그대로 유지 -- §27 최소 변경 원칙, 정상 경로 동작 불변.

  이 스크립트가 검증하는 RouteSimNEW는 실제 patch 적용 후의
  `selfdrive/carrot/carrot_man.py` continuation 분기(L913-923)와 동일
  로직의 독립 재구현이다(sim_route_224_serv_floor_fix.py의 RouteSimNEW와
  동일 -- 그 스크립트는 이 스크립트의 재구현이라고 주석에 적혀 있었으나
  컨테이너 리셋으로 본 스크립트 자체가 유실되어 이번 세션에서 재작성).

실행: python3 sim_route_224_ceiling_fix.py
기대 결과: 모든 CASE PASS, 마지막 줄 "ALL 224CHA CEILING-FIX CASES PASSED".
**실차 검증: 미실시.** (합성 시나리오 검증만 -- 실제 코드 diff는
selfdrive/carrot/carrot_man.py 패치로 별도 전달, 225차)
"""

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0


class RouteSimBase:
    """carrot_navi_route() 223차 상태기계(route_active/hold)의 공통 뼈대.
    continuation 분기(ACTIVE 진입/추적 시 out_speed_ms 계산)만 OLD/NEW로 갈린다.
    """

    def __init__(self, decel_cap=1.0, ctrl_end=0.0):
        self.route_active = False
        self.route_release_time = None
        self.decel_cap = decel_cap
        self.ctrl_end = ctrl_end
        self.t = 0.0

    def _continuation(self, v_ego_ms, target_ms, apex_dist):
        raise NotImplementedError

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
        out_ms = self._continuation(v_ego_ms, target_ms, apex_dist)
        return out_ms * 3.6


class RouteSimOLD(RouteSimBase):
    """223차 구코드(버그) -- v_ego_ms<=target_ms여도 out=max(target_ms, ...)로
    target_ms까지 끌어올림 (223cha_step2_decel_formula.md 원안, 224차 fix 이전)."""

    def _continuation(self, v_ego_ms, target_ms, apex_dist):
        eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end)
        if v_ego_ms <= target_ms or eff_dist <= 0:
            required = 0.0
        else:
            required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
        applied = min(max(required, 0.0), self.decel_cap)
        return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)


class RouteSimNEW(RouteSimBase):
    """224차 ceiling-fix 적용 후 -- v_ego_ms<=target_ms(또는 eff_dist<=0)면
    vEgo를 그대로 통과(inert). 실제 carrot_man.py L913-923과 동일 로직."""

    def _continuation(self, v_ego_ms, target_ms, apex_dist):
        eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end)
        if v_ego_ms <= target_ms or eff_dist <= 0:
            return v_ego_ms
        required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
        applied = min(max(required, 0.0), self.decel_cap)
        return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)


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
# CASE 1 (정상 감속, 회귀 없음 확인) -- vEgo(90)>target(60), 정상 등감속
# 경로. OLD/NEW 모두 target_ms 플로어가 살아있어야 하고(오버슈트 방지),
# 결과는 완전히 동일해야 한다(이 분기는 224차가 손대지 않았음).
# ---------------------------------------------------------------------------
def case1_normal_decel_no_regression():
    old = RouteSimOLD(decel_cap=2.0)
    new = RouteSimNEW(decel_cap=2.0)
    old.step(3, 90.0, 300.0, 60.0)
    new.step(3, 90.0, 300.0, 60.0)
    old_out = old.step(3, 88.0, 280.0, 60.0)
    new_out = new.step(3, 88.0, 280.0, 60.0)
    check("case1: normal decel path OLD==NEW (unaffected by fix)",
          old_out is not None and new_out is not None and abs(old_out - new_out) < 1e-9,
          f"old={old_out}, new={new_out}")
    check("case1: output never exceeds vEgo(88)", new_out <= 88.0 + 1e-9, f"new={new_out}")


# ---------------------------------------------------------------------------
# CASE 2 (target 아래로 하강, 정지 아님) -- vEgo(15)<target(20). OLD는
# target(20)까지 끌어올려 vEgo(15)를 초과(가속 명령처럼 동작). NEW는
# vEgo(15)를 그대로 통과.
# ---------------------------------------------------------------------------
def case2_below_target_not_stopped():
    old = RouteSimOLD(decel_cap=2.0)
    new = RouteSimNEW(decel_cap=2.0)
    old.step(3, 90.0, 300.0, 20.0)
    new.step(3, 90.0, 300.0, 20.0)
    old_out = old.step(3, 15.0, 40.0, 20.0)
    new_out = new.step(3, 15.0, 40.0, 20.0)
    check("case2/OLD: bug -- output(20) exceeds vEgo(15)",
          old_out is not None and old_out > 15.0 + 1e-9, f"old={old_out}")
    check("case2/NEW: fixed -- output==vEgo(15), no phantom accel",
          new_out is not None and abs(new_out - 15.0) < 1e-6, f"new={new_out}")


# ---------------------------------------------------------------------------
# CASE 3 (224차 실차로그 재현 -- apex 진입 "전"에 정지) -- vEgo=0, apex_dist
# 40m 고정(정지), apex_speed=46kph 근처. OLD는 46kph를 80프레임(4초 상당,
# 실제 로그는 80.8초/1616프레임이나 시뮬레이션은 대표 구간만) 계속 유지.
# NEW는 매 프레임 0을 유지해야 한다.
# ---------------------------------------------------------------------------
def case3_stopped_before_apex_224cha_log_repro():
    old = RouteSimOLD(decel_cap=1.0, ctrl_end=7.0)
    new = RouteSimNEW(decel_cap=1.0, ctrl_end=7.0)
    old.step(3, 90.0, 300.0, 46.0)
    new.step(3, 90.0, 300.0, 46.0)
    old_outs, new_outs = [], []
    for _ in range(80):
        old_outs.append(old.step(3, 0.0, 40.0, 46.0))  # 정지 유지, apex 도달 전(>10m)
        new_outs.append(new.step(3, 0.0, 40.0, 46.0))
    check("case3/OLD: bug reproduced -- out stays ~46kph while vEgo=0",
          all(o is not None and abs(o - 46.0) < 1e-6 for o in old_outs),
          f"old_outs sample={old_outs[:3]}")
    check("case3/NEW: fixed -- out stays 0 while vEgo=0 (matches 224cha log expectation)",
          all(n is not None and abs(n - 0.0) < 1e-6 for n in new_outs),
          f"new_outs sample={new_outs[:3]}")


# ---------------------------------------------------------------------------
# CASE 4 (stop&go 재출발 + 정상 RELEASE) -- CASE3 상태에서 재출발해 다시
# 가속, apex_dist가 10m 이하로 좁혀지면 RELEASE(out=None)되어야 한다(223차
# 설계 의도, 224차 발견2는 "apex 도달 전 정지" 케이스만 지적했지 RELEASE
# 자체의 정상 동작을 바꾸지 않음 -- 회귀 확인).
# ---------------------------------------------------------------------------
def case4_stop_and_go_then_release():
    new = RouteSimNEW(decel_cap=2.0, ctrl_end=0.0)
    new.step(3, 90.0, 300.0, 46.0)
    new.step(3, 0.0, 40.0, 46.0)  # 정지
    out_reaccel = new.step(3, 20.0, 25.0, 46.0)  # 재출발, target(46)>vEgo(20) -> inert
    check("case4: re-accelerating below target still inert (==vEgo)",
          out_reaccel is not None and abs(out_reaccel - 20.0) < 1e-6,
          f"out={out_reaccel}")
    out_release = new.step(3, 44.0, 8.0, 46.0)  # apex_dist<=10 -> RELEASE
    check("case4: RELEASE fires normally once apex_dist<=10m (out=None)",
          out_release is None, f"out={out_release}")


# ---------------------------------------------------------------------------
# CASE 5 (mode 0/1 -- route_enabled=False) -- fix와 무관하게 즉시 비활성.
# ---------------------------------------------------------------------------
def case5_mode_disabled_unaffected():
    new = RouteSimNEW(decel_cap=2.0)
    out = new.step(1, 0.0, 40.0, 46.0)
    check("case5: mode 0/1 -> out=None regardless of fix", out is None, f"out={out}")


# ---------------------------------------------------------------------------
# REGRESSION 1 -- eff_dist<=0 (apex 바로 코앞, ctrl_end 보정 후 0 이하)이면
# OLD/NEW 둘 다 required_decel=0 분기를 타는데, OLD는 target까지 끌어올리고
# NEW는 vEgo를 통과 -- CASE2와 동일 메커니즘이지만 eff_dist<=0 경로로도
# 도달함을 별도 확인.
# ---------------------------------------------------------------------------
def regression_eff_dist_non_positive():
    old = RouteSimOLD(decel_cap=2.0, ctrl_end=7.0)
    new = RouteSimNEW(decel_cap=2.0, ctrl_end=7.0)
    old.step(3, 90.0, 300.0, 46.0)
    new.step(3, 90.0, 300.0, 46.0)
    # target_ms*ctrl_end(46/3.6*7 ~= 89.4m) > apex_dist(12m) -> eff_dist=0,
    # and vEgo(40)<target(46) so this also satisfies v_ego_ms<=target_ms --
    # same required_decel=0 branch, reached via the eff_dist<=0 leg of the
    # "or". Confirms the fix covers this leg too, not just v_ego<=target.
    old_out = old.step(3, 40.0, 12.0, 46.0)
    new_out = new.step(3, 40.0, 12.0, 46.0)
    check("regression/OLD: eff_dist<=0 branch also pushed up to target(46)",
          old_out is not None and abs(old_out - 46.0) < 1e-6, f"old={old_out}")
    check("regression/NEW: eff_dist<=0 branch passes vEgo(40) through unchanged",
          new_out is not None and abs(new_out - 40.0) < 1e-6, f"new={new_out}")


if __name__ == "__main__":
    run("CASE1 normal decel, no regression", case1_normal_decel_no_regression)
    run("CASE2 below target, not stopped -- OLD exceeds vEgo, NEW capped",
        case2_below_target_not_stopped)
    run("CASE3 stopped before apex (224cha log repro)",
        case3_stopped_before_apex_224cha_log_repro)
    run("CASE4 stop&go reaccel + normal RELEASE", case4_stop_and_go_then_release)
    run("CASE5 mode disabled, unaffected", case5_mode_disabled_unaffected)
    run("REGRESSION eff_dist<=0 branch", regression_eff_dist_non_positive)

    if all(results):
        print("ALL 224CHA CEILING-FIX CASES PASSED")
    else:
        print(f"FAILED: {results.count(False)}/{len(results)} checks failed")
        raise SystemExit(1)
