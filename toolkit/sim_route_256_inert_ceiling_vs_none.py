"""256차 -- INERT 분기(carrot_man.py L1140-1152) out_speed=apex_speed(ceiling,
226차/현재 production) vs out_speed=None(지선생 제안) 동적 가속 시나리오 검증.

배경 (255차 계속 세션 말미, Claude<->ChatGPT(지선생) 대화, devnotes 미반영
상태로 세션 종료):
  지선생 P0 주장: "INERT는 개입 없음(None)이어야 한다"(design/247cha §8
  문언 근거). Claude 반박: 이 out_speed=apex_speed 줄은 226차에 의도적으로
  도입된 안전장치이며(toolkit/sim_route_226_active_gate_ceiling.py CASE1-5로
  이미 검증됨), 제거 시 226차가 막았던 회귀(vCruise가 apex_speed 위로
  free-accel)가 재발한다. 지선생 후속 반론: "그 회귀는 정적 케이스에서만
  문제 -- 실제로는 매 프레임 재평가되므로, None으로 두어도 v_ego가
  apex_speed를 넘는 순간 즉시 ACTIVE로 재진입해 STEP2 감속식이 그 시점
  v_ego 기준으로 다시 매끈하게 감속을 계산하니 '갑자기 훅 튀어나오는'
  위험이 없어 보인다"(대화 원문). Claude 3차 응답: 226차 커밋 메시지가
  "route=(INERT 포함) 항상 vEgo 상한" 을 Master 작업지시로 명시했던 이력이
  있어 이건 AI가 코드로 판단할 사안이 아니라 시뮬레이션 근거를 갖춰
  Master 결정을 받아야 한다고 결론. 이 스크립트가 그 시뮬레이션이다.

  sim_route_226_active_gate_ceiling.py(226차)는 이미 "정적 단발 프레임"
  기준으로 OLD(None)의 버그(vCruise까지 개방)를 증명했다 -- 이 스크립트는
  그 결론을 대체하지 않고, 지선생이 새로 제기한 다른 축("실제로는 동적으로
  가속하다 건너뛰므로 갱신되는 시점의 v_ego 자체가 크게 튀지 않을 수
  있다")을 검증한다. 즉 이번 실험 변수는 "정적 vs 동적"이 아니라
  "None으로 뒀을 때 실제로 apex에 도달하는 순간까지 남는 거리로 감속을
  완료할 수 있는가"이다.

핵심 질문: v_ego가 target(apex_speed) 아래에서 vCruise를 향해 가속하다가
target을 넘는 순간(그 프레임에만) ACTIVE로 전환되고 STEP2 감속식이
그 시점의 (v_ego, apex_dist)로 재계산된다. 이때 요구 감속도
(v_ego^2-target^2)/(2*eff_dist)가 accel_limit(AutoNaviSpeedDecelRate,
PARAMS_REGISTRY 등록값 1.0 m/s^2)를 넘으면 물리적으로 target까지
감속을 완료 못하고 apex를 초과속도로 통과한다 -- 이건 226차 정적
케이스와 다른, 동적 시나리오 고유의 새로운 실패 모드다.

CEILING(A, 현재 production, out=apex_speed 유지)은 애초에 v_ego가
apex_speed를 넘어서게 두지 않으므로(가속 setpoint 자체가 apex_speed로
캡됨) 이 실패 모드가 구조적으로 발생하지 않는다 -- 이 스크립트는 그
비대칭성을 넓은 파라미터 스윕으로 정량화한다.

전제(단순화, 명시): 차량은 매 프레임(ROUTE_SPEED_LOOP_DT=0.05s) 물리
가속도 상한(COMFORT_ACCEL_MSS, 편안 가속 기준값) 이내로 desired_speed
쪽으로 가속한다고 가정(감속 시엔 route의 out_speed 자체가 이미 ramp된
목표속도이므로 그대로 추종). apex_dist는 v_ego*dt만큼 매 프레임
감소한다(직선 근사, 곡률에 의한 실거리 오차는 무시 -- 226차 스크립트와
동일한 단순화 수준).

이 스크립트는 코드를 수정하지 않는다. 결론에 따라 Master가 (A) 유지
또는 (B) 채택+추가 안전장치(예: 감속 여유폭 최소거리 확보)를 결정한다.

실행: python3 sim_route_256_inert_ceiling_vs_none.py
"""

ROUTE_SPEED_LOOP_DT = 0.05
DECEL_CAP_MSS = 1.0          # AutoNaviSpeedDecelRate 등록값(100=1.00 m/s^2)
CTRL_END = 0.0                # autoNaviSpeedCtrlEnd 기본 가정(0 -> eff_dist=apex_dist)
COMFORT_ACCEL_MSS = 1.2       # 가속측 상한(편안 가속 기준, 감속 캡과 별개 가정값 --
                               # 실측 스펙 없음, 감도분석으로 스윕에 포함해 보완)


def kph(ms):
    return ms * 3.6


def ms(kph_v):
    return kph_v / 3.6


class DynamicSim:
    """out_speed 계산(A/B 공통) + 단순 종방향 물리(가속 캡, 감속은 out_speed
    그대로 추종) 를 함께 굴리는 폐루프 시뮬레이터."""

    def __init__(self, mode, decel_cap=DECEL_CAP_MSS, comfort_accel=COMFORT_ACCEL_MSS,
                 ctrl_end=CTRL_END):
        assert mode in ("A_CEILING", "B_NONE")
        self.mode = mode
        self.decel_cap = decel_cap
        self.comfort_accel = comfort_accel
        self.ctrl_end = ctrl_end
        self.route_active = False
        self.max_required_decel = 0.0   # 관측된 최대 필요감속도(포화 여부 판정용)
        self.saturated_frames = 0
        self.apex_overrun_kph = 0.0     # apex 도달 시점 target 초과분(있다면)

    def _out_speed_ms(self, v_ego_ms, apex_dist, target_ms):
        """carrot_man.py carrot_navi_route() INERT/ACTIVE 분기 재구현
        (223/226/247차 유지 로직 그대로, GATE 분기만 mode로 실험)."""
        eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end)
        if self.route_active:
            if eff_dist <= 0 or v_ego_ms <= target_ms:
                self.route_active = False
                return None  # RELEASE(단순화 -- apex_passed_or_lost/speed_reached 통합)
            required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            self.max_required_decel = max(self.max_required_decel, required)
            if required > self.decel_cap + 1e-9:
                self.saturated_frames += 1
            applied = min(max(required, 0.0), self.decel_cap)
            return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
        else:
            if eff_dist <= 0:
                return v_ego_ms
            elif v_ego_ms > target_ms:
                self.route_active = True
                required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                self.max_required_decel = max(self.max_required_decel, required)
                if required > self.decel_cap + 1e-9:
                    self.saturated_frames += 1
                applied = min(max(required, 0.0), self.decel_cap)
                return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
            else:
                # ---- 256차 실험 변수(구 226차 GATE와 동일 지점) ----
                if self.mode == "A_CEILING":
                    return target_ms  # out_speed = apex_speed
                else:
                    return None       # out_speed = None (지선생 제안)

    def run(self, v_ego0_kph, apex_dist0_m, target_kph, v_cruise_kph, max_frames=4000):
        v_ego_ms = ms(v_ego0_kph)
        apex_dist = apex_dist0_m
        target_ms = ms(target_kph)
        v_cruise_ms = ms(v_cruise_kph)
        trace = []
        for i in range(max_frames):
            out_ms = self._out_speed_ms(v_ego_ms, apex_dist, target_ms)
            setpoint_ms = out_ms if out_ms is not None else v_cruise_ms
            setpoint_ms = min(setpoint_ms, v_cruise_ms)
            if setpoint_ms >= v_ego_ms:
                v_ego_next = min(setpoint_ms, v_ego_ms + self.comfort_accel * ROUTE_SPEED_LOOP_DT)
            else:
                # 감속: out_speed 자체가 이미 ramp된 목표이므로 그대로 추종
                v_ego_next = setpoint_ms
            trace.append((i * ROUTE_SPEED_LOOP_DT, kph(v_ego_ms), apex_dist,
                          None if out_ms is None else kph(out_ms), self.route_active))
            apex_dist -= v_ego_ms * ROUTE_SPEED_LOOP_DT
            v_ego_ms = max(0.0, v_ego_next)
            if apex_dist <= 0.0:
                break
        overrun = max(0.0, kph(v_ego_ms) - target_kph)
        self.apex_overrun_kph = overrun
        return trace, overrun


def run_sweep():
    print("=" * 78)
    print("256차 동적 스윕: A_CEILING vs B_NONE, apex 도달 시점 target 초과 여부")
    print(f"(decel_cap={DECEL_CAP_MSS} m/s^2 [PARAMS_REGISTRY 등록값],"
          f" comfort_accel={COMFORT_ACCEL_MSS} m/s^2 [가정값, 스펙 없음])")
    print("=" * 78)
    apex_dists = [40, 60, 80, 100, 150, 200, 300, 500]
    gaps_kph = [10, 20, 30, 45, 60]   # vCruise - target
    target_kph = 50.0
    rows = []
    for d in apex_dists:
        for gap in gaps_kph:
            v_cruise = target_kph + gap
            simA = DynamicSim("A_CEILING")
            simB = DynamicSim("B_NONE")
            # 워밍업: 둘 다 target보다 한참 낮은 속도로 진입(둘 다 INERT GATE
            # 분기부터 시작하도록 보장)
            _, overrunA = simA.run(v_ego0_kph=target_kph - 15.0, apex_dist0_m=d,
                                    target_kph=target_kph, v_cruise_kph=v_cruise)
            _, overrunB = simB.run(v_ego0_kph=target_kph - 15.0, apex_dist0_m=d,
                                    target_kph=target_kph, v_cruise_kph=v_cruise)
            rows.append((d, gap, overrunA, overrunB, simA.saturated_frames,
                         simB.saturated_frames, simA.max_required_decel,
                         simB.max_required_decel))

    hdr = f"{'apex_dist':>9} {'vCr-tgt':>8} {'A_overrun':>10} {'B_overrun':>10} " \
          f"{'A_sat_fr':>9} {'B_sat_fr':>9} {'A_maxdecel':>11} {'B_maxdecel':>11}"
    print(hdr)
    print("-" * len(hdr))
    b_overrun_cases = 0
    a_overrun_cases = 0
    for (d, gap, oa, ob, sa, sb, mda, mdb) in rows:
        flag = " <-- B만 초과" if ob > 0.5 and oa <= 0.5 else ("  <-- 둘다 초과" if oa > 0.5 and ob > 0.5 else "")
        print(f"{d:>9} {gap:>8} {oa:>9.1f} {ob:>9.1f} {sa:>9} {sb:>9} "
              f"{mda:>10.2f} {mdb:>10.2f}{flag}")
        if ob > 0.5:
            b_overrun_cases += 1
        if oa > 0.5:
            a_overrun_cases += 1
    print()
    print(f"요약: 전체 {len(rows)}개 시나리오 중 B_NONE이 apex 통과 시 target을\n"
          f"0.5kph 넘게 초과한 경우 {b_overrun_cases}건 / A_CEILING이 초과한 경우 {a_overrun_cases}건.")
    return rows, a_overrun_cases, b_overrun_cases


def print_example_trace():
    print()
    print("=" * 78)
    print("대표 사례 상세 트레이스 -- apex_dist=60m, target=50kph, vCruise=95kph")
    print("(가장 짧은 근거리+가장 큰 갭 조합, 위 스윕에서 saturation 발생 여부 확인용)")
    print("=" * 78)
    for mode in ("A_CEILING", "B_NONE"):
        sim = DynamicSim(mode)
        trace, overrun = sim.run(v_ego0_kph=35.0, apex_dist0_m=60.0,
                                  target_kph=50.0, v_cruise_kph=95.0)
        print(f"--- {mode} ---")
        # crossing 프레임(ACTIVE 최초 진입) 전후만 발췌 출력
        active_idx = next((i for i, r in enumerate(trace) if r[4]), None)
        lo = max(0, (active_idx or 0) - 2)
        hi = min(len(trace), (active_idx or 0) + 6)
        for (t, v, dist, out, active) in trace[lo:hi]:
            out_s = f"{out:6.1f}" if out is not None else "  None"
            print(f"  t={t:5.2f}s vEgo={v:6.1f}kph apex_dist={dist:7.1f}m "
                  f"out={out_s} route_active={active}")
        print(f"  apex 도달 시점 target(50kph) 초과분: {overrun:.1f} kph, "
              f"saturated_frames={sim.saturated_frames}, "
              f"max_required_decel={sim.max_required_decel:.2f} m/s^2 "
              f"(decel_cap={sim.decel_cap})")
        print()


if __name__ == "__main__":
    rows, a_cnt, b_cnt = run_sweep()
    print_example_trace()
    print("=" * 78)
    if b_cnt > 0 and a_cnt == 0:
        print("결론: 이 파라미터 범위에서 B_NONE(지선생 제안)은 A_CEILING(현재\n"
              "production, 226차)이 겪지 않는 새로운 실패 모드(apex를 target보다\n"
              "빠른 속도로 통과)를 발생시킨다 -- 근거리+큰 vCruise갭 조합에서\n"
              "required_decel이 decel_cap을 포화시키기 때문. 이는 226차 정적\n"
              "케이스(vCruise까지 무한정 개방)와는 다른 축의 문제이며, 지선생이\n"
              "든 '동적 재평가라 안전하다'는 반론이 근거리 시나리오에서는\n"
              "성립하지 않음을 보여준다. Master 결정 없이 코드는 수정하지 않음.")
    elif b_cnt == 0:
        print("결론: 이 파라미터 범위에서는 B_NONE도 target 초과 없이 apex에\n"
              "도달한다 -- 즉 이 스윕 범위 내에서는 지선생 반론이 성립한다. 단,\n"
              "226차 정적 케이스(vCruise까지 개방)의 문제 자체는 이 스크립트가\n"
              "다루는 축이 아니므로 별개로 여전히 유효. Master 검토 필요.")
    else:
        print("결론: A_CEILING도 일부 케이스에서 초과가 발생 -- comfort_accel/\n"
              "decel_cap 가정값 재검토 필요(코드 버그 가능성보다 시뮬레이션\n"
              "가정 오류 가능성 우선 의심, §28).")
