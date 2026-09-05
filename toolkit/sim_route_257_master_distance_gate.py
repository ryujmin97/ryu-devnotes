"""257차 -- Master 지시(255차계속 이어짐, 지선생 경유): INERT의 ACTIVE 진입
조건을 `v_ego_ms > target_ms`(현재 255차/HEAD `d1bba17` 코드, 226차 이후
유지)에서 "apex까지 남은 거리가 accel_limit(AutoNaviSpeedDecelRate)
기준 필요감속거리 이하로 좁혀지는 순간"(거리/감속능력 기반 게이트)으로
재정의하는 안을 검증한다.

Master 원문 요지:
  - vEgo>target 그 자체는 ACTIVE 조건이 아니다(현재 코드 L1130
    `elif v_ego_ms > target_ms: route_active=True`는 이 정의를 위반).
  - INERT 동안은 Route=None, vCruise를 향해 정상 가속/유지.
  - 매 프레임 D_required = (vEgo^2-target^2)/(2*a_fixed) 계산, apex_dist
    <= D_required가 처음 TRUE인 순간에만 INERT->ACTIVE.
  - 226차 ceiling(out_speed=apex_speed) 유지 로직은 설계 대상에서 제외
    (256차 세션에서 Claude<->ChatGPT가 시뮬레이션으로 검토했던 정적/동적
    두 축 논쟁을 Master가 최종 결정으로 종결 -- WIP.md/FINDINGS.md 256차
    참고).

이 스크립트가 검증하는 것: (1) 현재(255차) 코드가 실제로 246차 CRITICAL
freeze(vEgo=4.9->rising, apexDist=480m, target=5.0kph, vCruise=94kph)를
"v_ego가 target을 미세하게 넘는 순간부터" 재현하는지 최초로 폐루프
시뮬레이션으로 직접 확인(246/253차는 open-loop 재생이라 이 경계 케이스를
정면으로 다루지 않았음 -- FINDINGS.md 246차 "253차 갱신" 항목 참고,
253차는 "0건"이라 보고했지만 그건 후보 필터링 개선 효과와 뒤섞여있을
가능성이 있어 이 스크립트로 순수 상태머신 로직만 분리해 재확인).
(2) Master 제안(DIST_GATE, a_fixed=AutoNaviSpeedDecelRate로 가정 -- 아래
"미확정 가정" 참고)이 그 freeze를 해소하는지.
(3) DIST_GATE가 226차 정적 케이스(Stop&Go, vCruise 무한개방)에서 이미
알려진 문제를 재도입하지 않는지(Master가 226차 논쟁 자체를 폐기했으므로
이건 "회귀 확인용"이 아니라 "새 설계의 실제 동작 확인용"으로 기록만 함).

**미확정 가정(Master 확인 필요)**: D_required 계산에 쓰는 a_fixed를
`AutoNaviSpeedDecelRate`(실제 감속 캡과 동일 상수)로 둔다 -- Master
예시(2.0 m/s^2)는 설명용 임의값이었고, 실제 상수를 재사용하면
"진입 즉시 required_decel==decel_cap"이 되어 진입-감속 시작이 매끄럽게
이어진다(진입 게이트와 감속 캡이 동일 기준이므로 불연속 없음). 이
가정이 틀렸다면(예: 게이트 전용 별도 상수가 필요하다면) 아래
`GATE_DECEL_MSS`만 분리하면 됨(코드 구조상 이미 분리돼 있음).

실행: python3 sim_route_257_master_distance_gate.py
"""

ROUTE_SPEED_LOOP_DT = 0.05
CTRL_END = 0.0
AUTO_NAVI_DECEL_RATE = 1.0     # PARAMS_REGISTRY 등록값(100=1.00 m/s^2)
GATE_DECEL_MSS = AUTO_NAVI_DECEL_RATE  # 미확정 가정: 게이트=감속캡과 동일 상수


def kph(v):
    return v * 3.6


def ms(v):
    return v / 3.6


class CurrentProd:
    """255차/HEAD(d1bba17) carrot_navi_route() INERT/ACTIVE 분기 그대로
    재구현(release 조건은 이번 실험 변수가 아니므로 간략화하되 핵심
    ACTIVE 진입/유지 로직은 라인 대 라인 대응)."""

    def __init__(self, decel_cap=AUTO_NAVI_DECEL_RATE, ctrl_end=CTRL_END):
        self.route_active = False
        self.decel_cap = decel_cap
        self.ctrl_end = ctrl_end

    def step(self, v_ego_ms, apex_dist, target_ms):
        eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end)
        if self.route_active:
            # 간략화된 release: 목표속도 도달 또는 거리 소진 시 해제
            if eff_dist <= 0 or v_ego_ms <= target_ms:
                self.route_active = False
                return None
            required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            applied = min(max(required, 0.0), self.decel_cap)
            return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
        else:
            if eff_dist <= 0:
                return v_ego_ms
            elif v_ego_ms > target_ms:
                # 현재 코드 L1130 -- Master가 위반이라 지적한 바로 그 줄
                self.route_active = True
                required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                applied = min(max(required, 0.0), self.decel_cap)
                return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
            else:
                return target_ms  # 226차 ceiling(out=apex_speed) -- Master가 폐기 지시


class MasterDistGate:
    """Master 신규 설계: Route=None(INERT) 유지, 매 프레임 D_required 재평가,
    apex_dist<=D_required(=required_decel>=GATE_DECEL_MSS와 동치)가 처음
    TRUE인 순간에만 INERT->ACTIVE. v_ego<=target 여부와 무관하게 이 조건만
    본다(Master 지적: v_ego>target 자체는 트리거 아님)."""

    def __init__(self, decel_cap=AUTO_NAVI_DECEL_RATE, gate_decel=GATE_DECEL_MSS,
                 ctrl_end=CTRL_END):
        self.route_active = False
        self.decel_cap = decel_cap
        self.gate_decel = gate_decel
        self.ctrl_end = ctrl_end

    def step(self, v_ego_ms, apex_dist, target_ms):
        eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end)
        if self.route_active:
            if eff_dist <= 0 or v_ego_ms <= target_ms:
                self.route_active = False
                return None
            required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            applied = min(max(required, 0.0), self.decel_cap)
            return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
        else:
            if v_ego_ms <= target_ms:
                return None  # 감속 자체가 무의미 -- Route=None, 항상 INERT
            if eff_dist <= 0:
                # 거리 소진 상태에서 뒤늦게 v_ego>target 발견 -- 더 미룰 수
                # 없으므로 강제 ACTIVE(최선의 감속이라도 즉시 시작).
                self.route_active = True
                return v_ego_ms - self.decel_cap * ROUTE_SPEED_LOOP_DT
            required_now = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            if required_now >= self.gate_decel - 1e-9:
                self.route_active = True
                applied = min(max(required_now, 0.0), self.decel_cap)
                return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
            else:
                return None  # 아직 D_required > apex_dist -- 진짜 INERT 유지


def replay_246cha_scenario(sim_cls, name, comfort_accel=1.0):
    """246차 실측 근사(FINDINGS.md 246차 원문 수치) -- vEgo=4.9->20.0kph로
    5.1초간 상승, apexDist=480->470m(거의 고정), target=5.0kph,
    vCruise=94kph(93~94kph 관측치 반영). '자유가속 자체가 억제되는가'만
    본다(정확한 도로 물리 재현이 아니라 246차가 관측한 입력궤적 근사)."""
    sim = sim_cls()
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
    print(f"--- {name} ---")
    for (t, v, d, o, active) in trace[::10]:
        o_s = f"{o:6.1f}" if o is not None else "  None"
        print(f"  t={t:4.1f}s vEgo={v:6.1f}kph apex_dist={d:6.1f}m out={o_s} active={active}")
    final_v = trace[-1][1]
    frozen_frames = sum(1 for (t, v, d, o, a) in trace if o is not None and abs(o - v) < 2.0)
    print(f"  6초 후 vEgo={final_v:.1f}kph (vCruise=94), "
          f"|out-vEgo|<2kph(freeze 판정) 프레임 {frozen_frames}/{len(trace)}")
    print()
    return final_v, frozen_frames, len(trace)


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return cond


if __name__ == "__main__":
    print("=" * 78)
    print("246차 CRITICAL freeze 시나리오 재현 -- CurrentProd(255차) vs MasterDistGate")
    print("=" * 78)
    fv_cur, fr_cur, n = replay_246cha_scenario(CurrentProd, "CurrentProd (255차/HEAD d1bba17)")
    fv_new, fr_new, _ = replay_246cha_scenario(MasterDistGate, "MasterDistGate (신규 설계)")

    results = []
    results.append(check(
        "CurrentProd: 246차처럼 vEgo가 target을 넘는 즉시 freeze(자유가속 억제) 재현",
        fr_cur > n * 0.5, f"frozen_frames={fr_cur}/{n}, 6초 후 vEgo={fv_cur:.1f}kph"))
    results.append(check(
        "MasterDistGate: freeze 없이 지속적으로 가속(0 frozen frames, |out-vEgo|<2kph 프레임 없음)",
        fr_new == 0, f"frozen_frames={fr_new}/{n}, 6초 후 vEgo={fv_new:.1f}kph"
        " (comfort_accel=1.0 m/s^2 가정상 6초로는 vCruise 도달 전이나, 자유가속 자체는 막히지 않음)"))

    print()
    print("=" * 78)
    print("안전성 확인: MasterDistGate 진입 시점에 실제로 target까지 감속을")
    print("완료할 여유가 있는가 (a_fixed=decel_cap 가정의 타당성)")
    print("=" * 78)
    # 매우 급격한 시나리오(짧은 apex_dist, 높은 vCruise)로 스트레스
    worst_overrun = 0.0
    for d0 in [30, 50, 80, 120, 200, 400]:
        for vcr in [60, 90, 120]:
            sim = MasterDistGate()
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
            overrun = max(0.0, kph(v) - 50.0)
            worst_overrun = max(worst_overrun, overrun)
    results.append(check(
        "MasterDistGate: a_fixed=decel_cap 가정 하 apex 도달 시 target 초과 없음(진입 게이트가 항상 충분한 여유 확보)",
        worst_overrun < 0.5, f"worst_overrun={worst_overrun:.2f}kph (스윕 18케이스)"))

    print()
    if all(results):
        print("ALL 257CHA CHECKS PASSED -- Master 설계로 246차 CRITICAL 해소 + 안전성 확인")
    else:
        print(f"FAILED: {results.count(False)}/{len(results)} checks failed")
        raise SystemExit(1)
