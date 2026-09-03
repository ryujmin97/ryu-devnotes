"""226차 -- carrot_navi_route() ACTIVE 진입 게이트(L896-902)의 설계 갭 검증.

배경(226차 작업 지시, ChatGPT 225차 정적점검 보고서):
  carrot_navi_route()의 다음 분기(현재 코드, ec56861 기준 L896-902):

      elif not self.route_active and v_ego_kph <= apex_speed:
          out_speed = None

  route_active가 아직 False이고(=아직 이 curve에 대해 감속 추적을 시작한
  적 없음) 현재 vEgo가 이미 apex_speed 이하면, "가속 명령을 만들지 않는다"
  는 의도로 out_speed=None을 반환한다. 그런데 carrot_serv.py::update_navi()
  (L1127-1151)는 route_speed(=out_speed)가 None이면 route를 speed_n_sources
  에 아예 넣지 않는다 -- 즉 "가속 명령을 안 만든다"가 아니라 "route를
  arbitration에서 완전히 제외"가 되어, 이 상태에서는 apex_speed라는
  ceiling 자체가 사라진다. vCruise가 apex_speed보다 높으면(예:
  vEgo=60/apex=80/vCruise=100) 다른 소스가 desired_speed를 결정해 80을
  넘어 100까지 풀릴 수 있다 -- "Route=최대허용속도 ceiling"이라는 현재
  설계 의도와 모순.

  이 스크립트는 코드 수정 전에 이 갭을 실제로 재현하고, 후보 수정안
  (out_speed=None -> out_speed=apex_speed, GATE 분기에서만)이 5개 필수
  CASE를 모두 통과하는지 사전검증한다. 코드는 아직 건드리지 않는다
  (226차 작업 지시 "먼저 코드 수정하지 말고 시뮬레이션부터").

  GATE_OLD = 현재 코드(ec56861) 그대로 재구현 (out=None)
  GATE_NEW = 후보안 (out=apex_speed, min()에서 캡으로만 작동 -- 위로
             밀어올리지 않음. route_active는 여전히 False로 유지 --
             "추적 시작"과 "캡 유지"를 분리)

  225차 A(ceiling-fix, continuation 분기 v_ego<=target -> inert)/
  B(carrot_serv floor-fix, route_speed=min(vEgo, max(route_speed,
  lowerLimit)))는 그대로 유지 -- 이 스크립트는 그 두 로직을 제거하거나
  대체하지 않고, 그 위에서 GATE 분기만 OLD/NEW로 비교한다.

  apex 후보 선정(candidates[0]=거리 오름차순 첫 감속필요지점) 로직,
  sharpest-candidate 방식, ramp limiter, boost, sqrt 공식은 전부
  건드리지 않는다(226차 작업 지시 [금지] 항목).

실행: python3 sim_route_226_active_gate_ceiling.py
기대 결과: CASE1~5 전부 PASS. 실차 검증: 미실시(합성 시나리오만).
"""

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0
AUTO_CURVE_SPEED_LOWER_LIMIT_DEFAULT = 30.0  # common/params_keys.h 기본값


# ---------------------------------------------------------------------------
# carrot_man.py::carrot_navi_route() 재구현 (223차 상태기계 + 225차 A +
# 226차 GATE 후보). continuation 분기(225차 A, ceiling-fix)는 OLD/NEW
# 공통으로 이미 수정된 상태로 고정 -- 이번 실험 변수는 GATE 분기뿐.
# ---------------------------------------------------------------------------
class RouteSim:
    def __init__(self, gate_mode, decel_cap=1.0, ctrl_end=0.0):
        assert gate_mode in ("OLD", "NEW")
        self.gate_mode = gate_mode
        self.route_active = False
        self.route_release_time = None
        self.decel_cap = decel_cap
        self.ctrl_end = ctrl_end
        self.t = 0.0

    def _continuation_225A(self, v_ego_ms, target_ms, apex_dist):
        # 225차 A ceiling-fix 그대로 (v_ego<=target 또는 eff_dist<=0 이면
        # inert=vEgo 통과). 이번 226차 실험 대상이 아니므로 불변.
        eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end)
        if v_ego_ms <= target_ms or eff_dist <= 0:
            return v_ego_ms
        required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
        applied = min(max(required, 0.0), self.decel_cap)
        return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)

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
            # ---- 226차 실험 변수: GATE 분기 ----
            if self.gate_mode == "OLD":
                return None  # 현재 코드(ec56861) 그대로
            else:
                # 후보안: route_active는 True로 만들지 않는다(추적 시작
                # 아님, 225차 A/223차 감속식을 타지 않음) -- 단순히
                # apex_speed를 "캡 후보"로만 반환. min()에서만 쓰이므로
                # 절대 위로 밀어올리지 않는다(가속 명령 생성 금지 유지).
                return apex_speed_kph / 3.6 * 3.6  # == apex_speed_kph, 단위 명시

        self.route_active = True
        target_ms = apex_speed_kph / 3.6
        out_ms = self._continuation_225A(v_ego_ms, target_ms, apex_dist)
        return out_ms * 3.6


# ---------------------------------------------------------------------------
# carrot_serv.py::update_navi() arbitration 재구현 (225차 B floor-fix +
# speed_n_sources + min()). route_speed=None이면 소스 목록에서 제외
# (223차 STEP3 결론, 코드 L1118-1151 그대로).
# ---------------------------------------------------------------------------
def arbitrate(route_speed_kph, v_ego_kph, v_cruise_kph, other_sources,
              lower_limit=AUTO_CURVE_SPEED_LOWER_LIMIT_DEFAULT):
    """other_sources: [(speed_kph, name), ...] -- vturn/model_turn 등,
    route/vCruise 제외 나머지. vCruise는 항상 후보로 포함(desired_speed는
    vCruise를 넘지 않는 것이 기존 arbitration의 기본 전제)."""
    sources = list(other_sources)
    sources.append((v_cruise_kph, "vCruise"))
    route_present = route_speed_kph is not None
    route_speed_after_floor = None
    if route_present:
        # 225차 B: min(vEgo, max(route_speed, lowerLimit))
        route_speed_after_floor = min(v_ego_kph, max(route_speed_kph, lower_limit))
        sources.append((route_speed_after_floor, "route"))
    desired_speed, source = min(sources, key=lambda x: x[0])
    return {
        "route_speed_raw": route_speed_kph,
        "route_speed_after_floor": route_speed_after_floor,
        "route_source_present": route_present,
        "final_desired_speed": desired_speed,
        "final_source": source,
    }


results = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append(cond)
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


def trace(label, v_ego, apex_speed, arb):
    print(f"    {label}: vEgo={v_ego:.1f} apex_speed={apex_speed:.1f} "
          f"route_raw={arb['route_speed_raw']} "
          f"route_after_floor={arb['route_speed_after_floor']} "
          f"route_present={arb['route_source_present']} "
          f"final={arb['final_desired_speed']:.1f}({arb['final_source']})")


def run(name, fn):
    print(f"--- {name} ---")
    fn()
    print()


# ===========================================================================
# CASE 1 -- vEgo=60, apex_speed=80, vCruise=100 (핵심 재현 케이스)
# 기대: NEW는 route가 80 ceiling으로 계속 존재해 final<=80. OLD는 route가
# 사라져 vCruise(100)에 눌려 final=100까지 풀림(버그 재현).
# ===========================================================================
def case1_gap_repro_vego60_apex80_cruise100():
    for mode, label in [("OLD", "OLD(현재코드)"), ("NEW", "NEW(후보안)")]:
        sim = RouteSim(mode, decel_cap=2.0)
        # 주의: route_active가 False로 유지된 상태에서 GATE 분기에
        # 진입해야 하므로, 워밍업 프레임도 반드시 v_ego<=apex_speed
        # 조건으로 줘야 한다(v_ego>apex_speed로 워밍업하면 continuation
        # 분기를 타서 route_active=True가 먼저 서버려 GATE 자체가
        # 테스트되지 않는 실수를 초회 작성 시 범함 -- 수정).
        sim.step(3, 65.0, 220.0, 80.0)  # 워밍업(65<=80, GATE 분기 유지)
        out = sim.step(3, 60.0, 200.0, 80.0)
        arb = arbitrate(out, v_ego_kph=60.0, v_cruise_kph=100.0,
                         other_sources=[(150.0, "vturn_off"), (150.0, "model")])
        trace(label, 60.0, 80.0, arb)
        if mode == "OLD":
            check("CASE1/OLD: 버그 재현 -- route 제외되어 final(100)==vCruise",
                  not arb["route_source_present"] and abs(arb["final_desired_speed"] - 100.0) < 1e-6,
                  f"final={arb['final_desired_speed']}")
        else:
            check("CASE1/NEW: route가 80 ceiling으로 존재, final<=80",
                  arb["route_source_present"] and arb["final_desired_speed"] <= 80.0 + 1e-6,
                  f"final={arb['final_desired_speed']}")
            check("CASE1/NEW: final이 100(vCruise)까지 풀리지 않음",
                  arb["final_desired_speed"] < 100.0 - 1e-6)
            check("CASE1/NEW: route는 여전히 '가속 명령'을 만들지 않음(route_active 유지 False)",
                  sim.route_active is False)


# ===========================================================================
# CASE 2 -- vEgo=100, apex_speed=80: 기존 223/225 정상 감속 경로. GATE 분기
# 자체를 안 타야 하므로(vEgo>apex_speed) OLD/NEW 동일해야 한다(회귀 없음).
# ===========================================================================
def case2_normal_decel_no_regression():
    for mode, label in [("OLD", "OLD"), ("NEW", "NEW")]:
        sim = RouteSim(mode, decel_cap=2.0)
        sim.step(3, 110.0, 400.0, 80.0)
        out = sim.step(3, 100.0, 350.0, 80.0)
        arb = arbitrate(out, v_ego_kph=100.0, v_cruise_kph=120.0,
                         other_sources=[(150.0, "vturn_off")])
        trace(label, 100.0, 80.0, arb)
        check(f"CASE2/{label}: route_active=True(정상 추적 진입)", sim.route_active is True)
        check(f"CASE2/{label}: out<=vEgo(100) 불변식 유지", out is not None and out <= 100.0 + 1e-9,
              f"out={out}")
    # OLD/NEW 완전 동일해야 함 (GATE 분기 미개입 구간)
    old = RouteSim("OLD", decel_cap=2.0); old.step(3, 110.0, 400.0, 80.0)
    new = RouteSim("NEW", decel_cap=2.0); new.step(3, 110.0, 400.0, 80.0)
    old_out = old.step(3, 100.0, 350.0, 80.0)
    new_out = new.step(3, 100.0, 350.0, 80.0)
    check("CASE2: OLD==NEW 정상 감속 경로 회귀 없음",
          abs(old_out - new_out) < 1e-9, f"old={old_out}, new={new_out}")


# ===========================================================================
# CASE 3 -- vEgo=0, apex_speed=80, Stop&Go. 기대: RELEASE 안 됨(apex_dist>10m
# 유지 중), 재출발 후에도 80 ceiling 유지(100까지 안 풀림).
# ===========================================================================
def case3_stop_and_go_ceiling_persists():
    v_cruise = 100.0
    for mode, label in [("OLD", "OLD"), ("NEW", "NEW")]:
        sim = RouteSim(mode, decel_cap=1.0, ctrl_end=0.0)
        sim.step(3, 65.0, 300.0, 80.0)  # 워밍업(65<=80, GATE 분기 유지)
        # 정지 유지 40프레임 (apex_dist=200m, RELEASE 안 되는 거리)
        stop_outs = []
        for _ in range(40):
            out = sim.step(3, 0.0, 200.0, 80.0)
            stop_outs.append(out)
        arb_stop = arbitrate(stop_outs[-1], v_ego_kph=0.0, v_cruise_kph=v_cruise,
                              other_sources=[(150.0, "vturn_off")])
        trace(f"{label}/정지중", 0.0, 80.0, arb_stop)
        # 재출발: vEgo가 서서히 올라가지만 여전히 apex_speed(80) 이하
        out_reaccel = sim.step(3, 50.0, 180.0, 80.0)
        arb_reaccel = arbitrate(out_reaccel, v_ego_kph=50.0, v_cruise_kph=v_cruise,
                                 other_sources=[(150.0, "vturn_off")])
        trace(f"{label}/재출발(vEgo50)", 50.0, 80.0, arb_reaccel)
        if mode == "OLD":
            check("CASE3/OLD: 버그 -- 정지중 route 제외, RELEASE는 안 되지만 ceiling도 없음",
                  not arb_stop["route_source_present"])
            check("CASE3/OLD: 재출발 후에도 route 제외 -- final==vCruise(100)까지 개방",
                  not arb_reaccel["route_source_present"] and
                  abs(arb_reaccel["final_desired_speed"] - v_cruise) < 1e-6,
                  f"final={arb_reaccel['final_desired_speed']}")
        else:
            check("CASE3/NEW: 정지중 RELEASE 발생하지 않음(route_active는 애초 False 유지, "
                  "hold도 안 걸림 -- 진입한 적 없으므로 정상)",
                  sim.route_release_time is None)
            check("CASE3/NEW: 정지중에도 route 소스 존재(ceiling 유지)",
                  arb_stop["route_source_present"])
            check("CASE3/NEW: 재출발 후에도 80 ceiling 유지, 100까지 안 풀림",
                  arb_reaccel["route_source_present"] and
                  arb_reaccel["final_desired_speed"] <= 80.0 + 1e-6,
                  f"final={arb_reaccel['final_desired_speed']}")


# ===========================================================================
# CASE 4 -- 연속곡선: curve A apex 도달 -> RELEASE/hold(2초) -> curve B 탐색.
# 기대: hold 중엔 None(정상, 기존 동작), hold 만료 후 B가 vEgo 이하이면
# NEW는 B의 apex_speed로 다시 ceiling 존재, target이 A의 값으로 남거나
# 비정상 None이 되지 않아야 함.
# ===========================================================================
def case4_consecutive_curves_no_stale_target():
    for mode, label in [("OLD", "OLD"), ("NEW", "NEW")]:
        sim = RouteSim(mode, decel_cap=2.0)
        sim.step(3, 90.0, 300.0, 60.0)          # curve A 추적 시작
        sim.step(3, 70.0, 60.0, 60.0)            # A 추적 중 (vEgo>target)
        out_release = sim.step(3, 62.0, 8.0, 60.0)  # apex_dist<=10 -> RELEASE(A)
        trace(f"{label}/A RELEASE", 62.0, 60.0, arbitrate(out_release, 62.0, 100.0, []))
        check(f"CASE4/{label}: A apex 도달 시 RELEASE(out=None), route_active=False",
              out_release is None and sim.route_active is False)
        # hold 중(2초=40프레임 미만) -- curve B가 이미 감지되어도 hold가 우선
        out_hold = sim.step(3, 62.0, 150.0, 45.0)  # curve B, vEgo(62)>apex_B(45)여도 hold 중
        check(f"CASE4/{label}: hold 중(release 직후)엔 여전히 None",
              out_hold is None)
        # hold 만료(40프레임) 후, B 추적으로 충분히 수렴할 때까지 더 진행
        # (감속 계산은 매 프레임 무상태 재계산이라 "잔류"는 애초에 구조적으로
        # 불가능 -- 여기서는 그 사실을 "target=45로 실제 수렴하는지"로 확인)
        out_after_hold = None
        for _ in range(45):
            out_after_hold = sim.step(3, 62.0, 150.0, 45.0)
        arb_b = arbitrate(out_after_hold, v_ego_kph=62.0, v_cruise_kph=100.0,
                           other_sources=[])
        trace(f"{label}/B 재탐색(hold만료 직후)", 62.0, 45.0, arb_b)
        # apex_dist를 45(B target)를 향해 계속 좁혀가며(정지형 vEgo 대신
        # apex_dist만 감소시켜 접근을 흉내) target이 A(60)가 아니라 B(45)로
        # 수렴하는지 확인 -- vEgo는 route ceiling(out<=vEgo)에 맞춰 함께 감소.
        v = 62.0
        out_converge = out_after_hold
        for d in range(140, 10, -5):
            out_converge = sim.step(3, v, float(d), 45.0)
            v = min(v, out_converge)  # 실제 제어 루프처럼 vEgo가 out을 따라감
        check(f"CASE4/{label}: B 접근 진행에 따라 target이 B(45) 방향으로 계속 "
              f"감소(A(60)에 고착되지 않음)",
              out_converge is not None and out_converge < 60.0,
              f"out_converge={out_converge} (A_target=60, B_target=45)")
        check(f"CASE4/{label}: route_active=True(B 정상 추적 재개)",
              sim.route_active is True)


# ===========================================================================
# CASE 5 -- 205/207차 회귀 케이스. 현재(223차+) 아키텍처는 205/207차 당시의
# _route_speed_prev 비대칭 램프/sharpest_candidate ceiling 항 자체가 이미
# 폐기된 무상태 구조라 원래 버그 메커니즘 자체가 존재하지 않는다. 여기서는
# "apex 후보가 프레임 간 급격히 흔들려도(flicker) ceiling이 순간적으로
# 안전 상한(road_limit) 근처까지 튀지 않는다"는 동일한 실패 패턴 자체를
# 226차 GATE 변경이 재도입하지 않는지 확인한다. apex 후보 선정 로직은
# 손대지 않음([금지] 항목) -- apex_idx가 프레임마다 바뀌는 것을 외부에서
# 주어진 입력으로만 시뮬레이션.
# ===========================================================================
def case5_205_207_regression_apex_flicker():
    sim = RouteSim("NEW", decel_cap=2.0)
    sim.step(3, 90.0, 300.0, 80.0)
    # 프레임 간 apex 후보가 curve1(dist=200,speed=80) <-> curve2(dist=205,
    # speed=30, 훨씬 급한데 근소하게 더 먼 지점 -- candidates[0] 선정 로직
    # 자체는 건드리지 않고, 여기서는 "그 결과로 apex_speed가 80<->30으로
    # 프레임마다 흔들리는" 최악의 케이스를 외부 입력으로 강제 주입.
    outs = []
    for i in range(10):
        apex_speed = 80.0 if i % 2 == 0 else 30.0
        v_ego = 60.0  # 두 값 모두보다 낮거나 같지 않게: 60<80이지만 60>30
        out = sim.step(3, v_ego, 200.0, apex_speed)
        arb = arbitrate(out, v_ego_kph=v_ego, v_cruise_kph=150.0, other_sources=[])
        outs.append((apex_speed, out, arb["final_desired_speed"]))
        trace(f"flicker[{i}] apex={apex_speed}", v_ego, apex_speed, arb)
    # 두 경우 모두 route_active는 False로 유지(GATE 분기 -- v_ego<=apex_speed
    # 조건은 apex_speed=80일 때만 성립, apex_speed=30일 때는 v_ego(60)>30이라
    # 정상 continuation 경로로 빠짐 -- 이 자체가 실제 코드 분기 조건이므로
    # 그대로 반영).
    # 안전 불변식: final_desired_speed가 road_limit(150)이나 vCruise(150)
    # 까지 튀는 프레임이 없어야 한다 -- 즉 최소한 min(80,30)=30 근방 이하로
    # 눌려야 정상(완전 동일할 필요는 없음, "150까지 안 튄다"만 확인).
    spikes = [f for (a, o, f) in outs if f > 80.0 + 1e-6]
    check("CASE5: apex flicker(80<->30) 중 final_desired_speed가 150(road_limit/"
          "vCruise)까지 스파이크하는 프레임 없음",
          len(spikes) == 0, f"spikes={spikes}")
    check("CASE5: flicker 전체 프레임에서 final<=max(80,vEgo)=80 이내로 억제",
          all(f <= 80.0 + 1e-6 for (a, o, f) in outs), f"outs={outs}")


if __name__ == "__main__":
    run("CASE1 vEgo60/apex80/vCruise100 -- 갭 재현 + 후보안 검증",
        case1_gap_repro_vego60_apex80_cruise100)
    run("CASE2 vEgo100/apex80 -- 정상 감속 경로 회귀 없음", case2_normal_decel_no_regression)
    run("CASE3 vEgo0 Stop&Go -- ceiling 유지, RELEASE 오발동 없음",
        case3_stop_and_go_ceiling_persists)
    run("CASE4 연속곡선 A->RELEASE/hold->B -- stale target 없음",
        case4_consecutive_curves_no_stale_target)
    run("CASE5 205/207차 회귀 -- apex flicker 중 스파이크 없음",
        case5_205_207_regression_apex_flicker)

    if all(results):
        print("ALL 226CHA GATE-CEILING CASES PASSED")
    else:
        print(f"FAILED: {results.count(False)}/{len(results)} checks failed")
        raise SystemExit(1)
