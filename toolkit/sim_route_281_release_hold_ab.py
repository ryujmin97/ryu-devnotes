#!/usr/bin/env python3
"""
sim_route_281_release_hold_ab.py (281차 신규)

목적: ROUTE_RELEASE_HOLD_S(2.0s, 223차 설계)가 지금(280차, carrot_man.py
HEAD 7571e63) 시점에도 여전히 필요한지 오프라인 합성 시나리오로 검증한다.

배경(정적분석, §28):
223차 당시엔 confidence blend(266차)가 없어서 RELEASE 직후 노이즈로 재검출된
candidate가 있으면 그 즉시 ACTIVE로 재진입해 감속 명령이 그대로 나갔다 --
253차가 실측 corpus로 "hold 없으면 인위적 ENGAGE/RELEASE 진동 발생"을 직접
확인한 근거가 여기 있다(devnotes WIP.md 253차).

하지만 266차 confidence blend + 257/258차 거리기반 ACTIVE 게이트 이후에는
구조가 바뀌었다:
  - 신규/재탐색 candidate는 streak=1 -> confidence=0.0(정확히) ->
    eff_apex_speed=v_ego_kph -> required_decel_mss=0 -> 게이트 통과 불가.
  - speed_reached RELEASE 직후에는 v_ego_ms<=target_ms 조건이 즉시
    INERT-stay를 강제.
  - dist_reached RELEASE 직후에는 eff_dist<=0(근접 apex, 224차 원 설계)이
    즉시 pass-through(INERT 유지)를 강제.
이 3개 경로가 hold와 무관하게 "RELEASE 직후 즉시 재-ACTIVE"를 이미 막고
있다면, hold의 실질 효과는 "노이즈 재래치 방지"가 아니라 "다음 실제 커브로의
정당한 전환을 최대 2초 추가 지연"으로 좁혀진다는 가설을 검증한다.

시나리오:
  A. 노이즈 재래치 -- RELEASE 직후 같은 지점에서 candidate가 즉시(streak=1)
     재검출될 때, hold=0으로도 ACTIVE 재진입이 막히는지 확인.
  B. 근접 2연속 커브(S커브) -- apex1 RELEASE 직후 짧은 간격(0.3~1.5s)으로
     실제 apex2가 나타날 때, hold=2.0 vs hold=0에서 ACTIVE 재진입 시점이
     얼마나 벌어지는지(추가 지연폭) 정량화.
  C. 원거리 재가속 -- RELEASE(dist_reached) 후 차가 다시 가속해 실제로
     목표속도를 다시 초과할 때, hold가 이 정당한 재개입까지 지연시키는지.

실차 검증: 미실시(오프라인 합성 시나리오 전용, §29).
"""
import math

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_ACTIVE_RELEASE_MARGIN_RATIO = 1.1
ROUTE_RELEASE_DIST_M = 10.0
CONFIDENCE_TAU = 6.3
DECEL_RATE = 1.00      # PARAMS_REGISTRY baseline (AutoNaviSpeedDecelRate=100)
CTRL_END = 2.0          # autoNaviSpeedCtrlEnd 추정치(vturn_safe_time=2.0s 등 유사 파라미터 참고, 실제값 미확인)


def confidence_from_streak(streak, tau=CONFIDENCE_TAU):
    if streak <= 1:
        return 0.0
    return 1.0 - math.exp(-(streak - 1) / tau)


class RouteStateSim:
    """carrot_man.py L858-1300 RELEASE/ACTIVE/INERT 상태기계를 그대로 포트."""

    def __init__(self, hold_s):
        self.hold_s = hold_s
        self.route_active = False
        self.release_t = None
        self.t = 0.0

    def step(self, v_ego_kph, apex_dist, apex_speed, apex_mode, apex_streak):
        """apex_mode: 'matched'/'held'/'new'/'passed'/'lost'/'none'
        apex_dist/apex_speed: None이면 유효 apex 없음.
        반환: (out_speed_kph or None, active:bool, in_hold:bool)"""
        self.t += ROUTE_SPEED_LOOP_DT
        v_ego_ms = v_ego_kph / 3.6

        # --- hold 게이트 (L858-865) ---
        if self.release_t is not None:
            if (self.t - self.release_t) < self.hold_s:
                return None, False, True
            self.release_t = None

        if apex_mode == "none" or apex_speed is None:
            if self.route_active:
                self.route_active = False
                self.release_t = self.t
            return None, False, False

        if self.route_active:
            apex_passed_or_lost = apex_mode in ("passed", "lost", "new")
            speed_reached = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
            dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
            if apex_passed_or_lost or speed_reached or dist_reached:
                self.route_active = False
                self.release_t = self.t
                return None, False, False
            conf = confidence_from_streak(apex_streak)
            eff_speed = conf * apex_speed + (1 - conf) * v_ego_kph
            target_ms = eff_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * CTRL_END)
            if eff_dist <= 0 or v_ego_ms <= target_ms:
                out_ms = v_ego_ms
            else:
                req = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                app = min(max(req, 0.0), DECEL_RATE)
                out_ms = max(target_ms, v_ego_ms - app * ROUTE_SPEED_LOOP_DT)
            return out_ms * 3.6, True, False
        else:
            conf = confidence_from_streak(apex_streak)
            eff_speed = conf * apex_speed + (1 - conf) * v_ego_kph
            target_ms = eff_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * CTRL_END)
            if v_ego_ms <= target_ms:
                return None, False, False
            elif eff_dist <= 0:
                return v_ego_kph, False, False
            else:
                req = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                if req >= DECEL_RATE:
                    self.route_active = True
                    app = min(max(req, 0.0), DECEL_RATE)
                    out_ms = max(target_ms, v_ego_ms - app * ROUTE_SPEED_LOOP_DT)
                    return out_ms * 3.6, True, False
                return None, False, False


def scenario_a_noise_relatch(hold_s):
    """ACTIVE로 목표속도(60kph)에 도달해 speed_reached로 RELEASE된 그 다음
    프레임, 노이즈로 같은 지점(apex_dist 동일, streak=1='new')이 즉시
    재검출되는 최악 케이스. hold=0에서도 즉시 재-ACTIVE가 안 되는지 확인."""
    sim = RouteStateSim(hold_s)
    v = 100.0 / 3.6
    apex_speed, apex_dist = 60.0, 300.0
    log = []
    active_before_release = False
    reentered_immediately = False
    for i in range(40):
        vkph = v * 3.6
        out, active, in_hold = sim.step(vkph, apex_dist, apex_speed, "matched", 20)
        if active:
            v_next = min(v, (max(out, apex_speed) if out else v*3.6)/3.6) if out else v
            v = out / 3.6 if out is not None else v
        log.append((i, round(vkph,1), out, active, in_hold))
        if not active and any(l[3] for l in log[:-1]):
            active_before_release = True
            # 다음 프레임: 노이즈로 즉시 'new' 재검출(streak=1), 동일 apex_dist
            for j in range(5):
                out2, active2, hold2 = sim.step(v*3.6, apex_dist, apex_speed, "new", 1)
                log.append((f"{i}+noise{j}", round(v*3.6,1), out2, active2, hold2))
                if active2:
                    reentered_immediately = True
            break
    return reentered_immediately, log


def scenario_b_s_curve_gap(hold_s, gap_s):
    """apex1(60kph@40m) RELEASE 이후 gap_s 뒤 apex2(45kph@80m, 실제 다음
    커브, streak가 매 프레임 +1씩 정상적으로 쌓임)가 나타날 때, ACTIVE
    재진입까지 걸리는 총 시간(t_release ~ t_active2)을 측정."""
    sim = RouteStateSim(hold_s)
    v = 100.0 / 3.6
    apex_speed1, apex_dist1 = 60.0, 300.0
    t_release = None
    # phase1: apex1 접근 -> ACTIVE -> RELEASE
    for i in range(400):
        vkph = v * 3.6
        out, active, in_hold = sim.step(vkph, apex_dist1, apex_speed1, "matched", 20)
        if out is not None:
            v = out / 3.6
        apex_dist1 = max(0.0, apex_dist1 - v * ROUTE_SPEED_LOOP_DT)
        if not active and sim.release_t is not None and t_release is None:
            t_release = sim.t
            break
    if t_release is None:
        return None
    # phase2: gap_s 동안 apex 없음(직선), 이후 apex2 정상 재탐색(streak 매 프레임 증가)
    apex_dist2 = 60.0
    apex_speed2 = 45.0
    streak2 = 0
    t_active2 = None
    gap_frames = int(gap_s / ROUTE_SPEED_LOOP_DT)
    for i in range(1200):
        vkph = v * 3.6
        if i < gap_frames:
            out, active, in_hold = sim.step(vkph, None, None, "none", 0)
        else:
            streak2 += 1
            mode = "new" if streak2 == 1 else "matched"
            out, active, in_hold = sim.step(vkph, apex_dist2, apex_speed2, mode, streak2)
            apex_dist2 = max(0.0, apex_dist2 - v * ROUTE_SPEED_LOOP_DT)
        if out is not None:
            v = out / 3.6
        if active and t_active2 is None:
            t_active2 = sim.t
            break
    if t_active2 is None:
        return None
    return t_active2 - t_release


def scenario_c_reaccel_after_release(hold_s):
    """dist_reached로 RELEASE된 직후 차가 다시 가속해(vCruise 등 타 소스)
    실제로 apex_speed*1.1을 다시 초과하는 정당한 재개입 케이스에서, hold가
    이 재개입까지 지연시키는 시간을 측정."""
    sim = RouteStateSim(hold_s)
    v = 70.0 / 3.6
    apex_speed, apex_dist = 40.0, 150.0
    t_release = None
    for i in range(400):
        vkph = v * 3.6
        out, active, in_hold = sim.step(vkph, apex_dist, apex_speed, "matched", 20)
        if out is not None:
            v = out / 3.6
        apex_dist = max(0.0, apex_dist - v * ROUTE_SPEED_LOOP_DT)
        if apex_dist <= ROUTE_RELEASE_DIST_M and t_release is None and sim.release_t is not None:
            t_release = sim.t
            apex_dist = 60.0  # RELEASE 후 (예: vturn 핸드오프 실패 등으로) 재가속 재현
            break
    if t_release is None:
        return None
    # 재가속: vCruise가 다시 밀어올림
    t_active2 = None
    for i in range(200):
        v = min(v + 0.5 * ROUTE_SPEED_LOOP_DT, 70.0/3.6)  # 완만히 재가속
        vkph = v * 3.6
        out, active, in_hold = sim.step(vkph, apex_dist, apex_speed, "matched", 20)
        apex_dist = max(0.0, apex_dist - v * ROUTE_SPEED_LOOP_DT)
        if active and t_active2 is None:
            t_active2 = sim.t
            break
    if t_active2 is None:
        return None
    return t_active2 - t_release


if __name__ == "__main__":
    print("=== 시나리오 A: RELEASE 직후 노이즈 즉시 재검출(streak=1) ===")
    for hold in (0.0, 2.0):
        reentered, log = scenario_a_noise_relatch(hold)
        print(f"hold={hold}s -> 즉시 재-ACTIVE 발생: {reentered}")

    print()
    print("=== 시나리오 B: 근접 2연속 커브, hold별 추가 지연폭 ===")
    for gap_s in (0.3, 0.6, 1.0):
        row = []
        for hold in (0.0, 0.5, 1.0, 2.0):
            dt = scenario_b_s_curve_gap(hold, gap_s)
            row.append(f"hold={hold}:{dt:.2f}s" if dt is not None else f"hold={hold}:N/A")
        print(f"실제 커브간격 gap={gap_s}s -> " + ", ".join(row))

    print()
    print("=== 시나리오 C: dist_reached RELEASE 후 정당한 재가속 재개입 지연 ===")
    for hold in (0.0, 1.0, 2.0):
        dt = scenario_c_reaccel_after_release(hold)
        print(f"hold={hold}s -> RELEASE~재-ACTIVE까지: {dt:.2f}s" if dt is not None else f"hold={hold}s -> N/A")
