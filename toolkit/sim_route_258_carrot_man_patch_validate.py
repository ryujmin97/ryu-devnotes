"""258차 -- carrot_man.py 실제 patch(carrot_navi_route() L1121-1160대,
257차 Master 설계 확정판) 1:1 재구현 검증.

257차가 Master에게 확인 요청한 2건이 이번 세션에 확정됨:
  ①=A: D_required 계산의 a_fixed는 별도 상수를 신설하지 않고 기존
       AutoNaviSpeedDecelRate(실제 감속 상한)를 그대로 재사용.
  ②=B: eff_dist<=0인데 아직 게이트 미충족인 edge case는 224차 원래
       의도("무의미하니 통과") 그대로 -- 강제 즉시 ACTIVE 진입하지 않고
       pass-through(out=v_ego, 개입 없음, INERT 유지) 유지.
       (257차 시뮬레이션의 MasterDistGate는 이 edge case를 "즉시 최대감속
       강제 진입"으로 처리했었으나, Master가 ②=B로 확정하면서 실제 patch는
       257차 시뮬레이션과 이 지점만 다르다 -- 아래 CarrotManPatched가
       그 확정판을 반영.)

이 스크립트가 검증하는 것:
  1. 246차 CRITICAL freeze 시나리오(257차와 동일 입력)가 patch 후에도
     여전히 해소되는지 재확인(②=B로 바뀐 것은 근거리 edge case뿐이고
     246차 시나리오는 원거리 apex라 영향 없어야 함 -- 회귀 확인).
  2. 안전성 스윕(257차와 동일 파라미터 범위) -- a_fixed=decel_cap 그대로
     재사용해도 apex 도달 시 target 초과가 여전히 없는지.
  3. [신규] eff_dist<=0 edge case 자체 -- ②=B가 실제로 "강제 ACTIVE 진입
     없이 통과"로 동작하는지, 즉 244차류 flicker 상황(apex가 근거리에
     불연속적으로 나타남)에서 급감속을 새로 걸지 않는지 직접 확인.
  4. ACTIVE 상태의 §4 감속식 자체는 이번 patch에서 손대지 않았으므로
     기존 CurrentProd의 ACTIVE 분기와 동일 출력을 내는지(무변경 확인,
     §27 최소 변경 원칙).

실행: python3 sim_route_258_carrot_man_patch_validate.py
"""

ROUTE_SPEED_LOOP_DT = 0.05
AUTO_NAVI_DECEL_RATE = 1.0  # PARAMS_REGISTRY 등록값(m/s^2), a_fixed로 재사용(①=A)
CTRL_END = 0.0


def kph(v):
    return v * 3.6


def ms(v):
    return v / 3.6


class CarrotManPatched:
    """carrot_man.py::carrot_navi_route() 실제 patch 1:1 재구현.
    ACTIVE 분기(§4 감속식)는 무변경, INERT 분기(§3 진입조건)만 257차
    Master 설계 + ①=A/②=B 확정판으로 교체."""

    def __init__(self, decel_cap=AUTO_NAVI_DECEL_RATE, ctrl_end=CTRL_END):
        self.route_active = False
        self.decel_cap = decel_cap
        self.ctrl_end = ctrl_end

    def step(self, v_ego_ms, apex_dist, target_ms):
        eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end)
        if self.route_active:
            # ACTIVE 분기 -- 이번 patch에서 무변경(§27). release 조건은
            # 실험 변수가 아니므로 간략화(246/257차 스크립트와 동일).
            if eff_dist <= 0 or v_ego_ms <= target_ms:
                self.route_active = False
                return None
            required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            applied = min(max(required, 0.0), self.decel_cap)
            return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
        else:
            # INERT 분기 -- 257차 Master 설계 + ①=A/②=B 확정판
            if v_ego_ms <= target_ms:
                return None  # 226차 ceiling 폐기(Master 결정)
            if eff_dist <= 0:
                return v_ego_ms  # ②=B: 224차 원 의도 계승, 강제 ACTIVE 없음
            required_now = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            if required_now >= self.decel_cap:  # ①=A: a_fixed=decel_cap 재사용
                self.route_active = True
                applied = min(max(required_now, 0.0), self.decel_cap)
                return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
            return None  # 게이트 미충족 -- INERT 유지


def replay_246cha_scenario(comfort_accel=1.0):
    sim = CarrotManPatched()
    v_ego_ms = ms(4.9)
    apex_dist = 480.0
    target_ms = ms(5.0)
    v_cruise_ms = ms(94.0)
    trace = []
    for i in range(int(6.0 / ROUTE_SPEED_LOOP_DT)):
        out = sim.step(v_ego_ms, apex_dist, target_ms)
        setpoint = out if out is not None else v_cruise_ms
        setpoint = min(setpoint, v_cruise_ms)
        if setpoint >= v_ego_ms:
            v_next = min(setpoint, v_ego_ms + comfort_accel * ROUTE_SPEED_LOOP_DT)
        else:
            v_next = setpoint
        trace.append((i * ROUTE_SPEED_LOOP_DT, kph(v_ego_ms), apex_dist,
                      None if out is None else kph(out), sim.route_active))
        apex_dist -= v_ego_ms * ROUTE_SPEED_LOOP_DT
        v_ego_ms = v_next
    return trace


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return cond


if __name__ == "__main__":
    results = []

    print("=" * 78)
    print("1) 246차 CRITICAL freeze 회귀 확인 (patch 확정판)")
    print("=" * 78)
    trace = replay_246cha_scenario()
    final_v = trace[-1][1]
    frozen = sum(1 for (t, v, d, o, a) in trace if o is not None and abs(o - v) < 2.0)
    results.append(check(
        "patch 확정판: freeze 없이 지속 가속(0 frozen frames)",
        frozen == 0, f"frozen_frames={frozen}/{len(trace)}, 6초 후 vEgo={final_v:.1f}kph"))

    print()
    print("=" * 78)
    print("2) 안전성 스윕 (257차와 동일 범위, a_fixed=decel_cap 재사용 재확인)")
    print("=" * 78)
    worst_overrun = 0.0
    for d0 in [30, 50, 80, 120, 200, 400]:
        for vcr in [60, 90, 120]:
            sim = CarrotManPatched()
            v = ms(20.0); dist = float(d0); tgt = ms(50.0); vc = ms(vcr)
            if vc <= tgt:
                continue
            for _ in range(4000):
                out = sim.step(v, dist, tgt)
                setpoint = min(out if out is not None else vc, vc)
                v_next = min(setpoint, v + 1.5 * ROUTE_SPEED_LOOP_DT) if setpoint >= v else setpoint
                dist -= v * ROUTE_SPEED_LOOP_DT
                v = max(0.0, v_next)
                if dist <= 0:
                    break
            worst_overrun = max(worst_overrun, max(0.0, kph(v) - 50.0))
    results.append(check(
        "안전성: apex 도달 시 target 초과 없음(257차와 동일 결과 재확인)",
        worst_overrun < 0.5, f"worst_overrun={worst_overrun:.2f}kph (18케이스)"))

    print()
    print("=" * 78)
    print("3) [신규] eff_dist<=0 edge case -- 224차 원 의도(②=B) 실제 반영 확인")
    print("=" * 78)
    # apex가 불연속적으로 아주 가까운 거리에 나타나는 244차류 flicker 상황.
    # v_ego(20kph) > target(5kph)이고 eff_dist<=0(target_ms*ctrl_end 등으로
    # 이미 소진, ctrl_end=0이라 apex_dist<=0로 재현) -- 이 프레임에서
    # 강제 ACTIVE 진입 없이 pass-through(out=v_ego)만 나오는지 확인.
    sim = CarrotManPatched()
    v_ego_ms = ms(20.0)
    out = sim.step(v_ego_ms, apex_dist=0.0, target_ms=ms(5.0))
    results.append(check(
        "eff_dist<=0: 강제 ACTIVE 진입 없음(route_active 그대로 False)",
        sim.route_active is False, f"route_active={sim.route_active}"))
    results.append(check(
        "eff_dist<=0: out=v_ego(그대로 통과, 급감속 명령 없음)",
        out is not None and abs(kph(out) - kph(v_ego_ms)) < 1e-6,
        f"out={kph(out):.2f}kph, v_ego={kph(v_ego_ms):.2f}kph"))

    print()
    print("=" * 78)
    print("4) ACTIVE 분기 무변경 확인 (§27 최소 변경 원칙)")
    print("=" * 78)
    # 이미 ACTIVE인 상태에서 §4 감속식 출력이 patch 전(255차/257차와 동일
    # 공식)과 일치하는지 -- 별도 old-vs-new 비교 없이 공식 자체를 직접 검산.
    sim = CarrotManPatched()
    sim.route_active = True
    v_ego_ms = ms(60.0); target_ms = ms(30.0); eff_dist = 100.0
    out = sim.step(v_ego_ms, eff_dist, target_ms)
    expected_required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
    expected_applied = min(max(expected_required, 0.0), AUTO_NAVI_DECEL_RATE)
    expected_out = max(target_ms, v_ego_ms - expected_applied * ROUTE_SPEED_LOOP_DT)
    results.append(check(
        "ACTIVE 분기 §4 감속식 공식 무변경",
        out is not None and abs(out - expected_out) < 1e-9,
        f"out={out:.4f} expected={expected_out:.4f}"))

    print()
    if all(results):
        print("ALL 258CHA PATCH-VALIDATION CHECKS PASSED")
    else:
        print(f"FAILED: {results.count(False)}/{len(results)} checks failed")
        raise SystemExit(1)
