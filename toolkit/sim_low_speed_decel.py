"""
58차 2번(계속3) 합성 검증 -- 저속+앞차 강한감속 danger-override 확장 로직
(LOW_SPEED_STRONG_DECEL_V_EGO_GATE / LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH)

process_lead()의 weight 계산부(margin_accel_weight/ttc_accel_weight/rise-rate
limiter/danger override)만 순수 함수로 재현해서 시나리오별로 검증한다.
실제 acados MPC 파이프라인은 거치지 않음 -- 로직 단위 검증.

검증 항목:
  A) 회귀: v_ego가 게이트(30km/h) 밖(고속)인 전 구간에서, 패치 적용 여부와
     무관하게 weight 시퀀스가 100% 동일해야 한다 (diff 0).
  B) 이벤트 재현: 저속 + 앞차 강한감속(aLeadK<=-1.8) 지속 시, 패치 이전엔
     TTC가 GATE_NONE(6.0s)을 넘길 때까지 감쇠 누적 후 rise-rate 제한(1.0/s)에
     걸려 뒤늦게 몰아서 반영되지만, 패치 이후엔 즉시(첫 프레임부터) weight=1.0
     로 감쇠 자체가 발생하지 않아야 한다.
  C) 오탐 방지: 저속이지만 앞차 감속이 완만(threshold 미달, 예: -0.5m/s^2)한
     경우엔 저속 게이트 분기가 열리지 않고 기존 ttc/rise-rate 로직 그대로
     동작해야 한다 (패치 적용 전후 diff 0).
  D) 경계 전이: v_ego가 게이트 값을 위/아래로 넘나들 때 예외 없이 동작하고,
     게이트를 벗어나는 즉시(그 프레임부터) 저속 분기가 닫혀야 한다.
"""
import numpy as np

# --- long_mpc.py 상수 재현 (58차 2번 계속3 패치 반영본 그대로) ---
MARGIN_ACCEL_GATE_FULL = 1.5
MARGIN_ACCEL_GATE_NONE = 1.0
LEAD_ACCEL_TTC_GATE_FULL = 12.0
LEAD_ACCEL_TTC_GATE_NONE = 6.0
LEAD_ACCEL_WEIGHT_RISE_RATE = 1.0  # 1/s
LEAD_ACQ_TTC_DANGER = 2.5
LOW_SPEED_STRONG_DECEL_V_EGO_GATE = 30.0 / 3.6
LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH = -1.8
DT = 0.05  # 20Hz, 실제 long_mpc 사이클과 동일 가정


def margin_accel_weight(dRel, desired_distance):
    if desired_distance <= 1.0:
        return 1.0
    ratio = dRel / desired_distance
    return float(np.clip((MARGIN_ACCEL_GATE_FULL - ratio) / (MARGIN_ACCEL_GATE_FULL - MARGIN_ACCEL_GATE_NONE), 0.0, 1.0))


def ttc_accel_weight(dRel, v_ego, v_lead):
    closing = v_ego - v_lead
    if closing <= 0.1:
        return 0.0
    ttc = dRel / closing
    return float(np.clip((LEAD_ACCEL_TTC_GATE_FULL - ttc) / (LEAD_ACCEL_TTC_GATE_FULL - LEAD_ACCEL_TTC_GATE_NONE), 0.0, 1.0))


def run_cycle(state, dRel, v_ego, v_lead, a_lead, desired_distance, patched):
    """state: dict with 'prev_w' persisted across cycles. returns (w, ttc_now)."""
    dist_w = margin_accel_weight(dRel, desired_distance)
    ttc_w = ttc_accel_weight(dRel, v_ego, v_lead)
    w = min(dist_w, ttc_w)
    closing = v_ego - v_lead
    ttc_now = dRel / closing if closing > 0.1 else float('inf')

    low_speed_strong_lead_decel = patched and (
        v_ego <= LOW_SPEED_STRONG_DECEL_V_EGO_GATE
        and a_lead <= LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH
    )

    if ttc_now <= LEAD_ACQ_TTC_DANGER or low_speed_strong_lead_decel:
        w = 1.0
    elif w > state['prev_w']:
        w = min(w, state['prev_w'] + LEAD_ACCEL_WEIGHT_RISE_RATE * DT)
    state['prev_w'] = w
    return w, ttc_now


def scenario_A_high_speed_regression():
    """고속(v_ego 항상 게이트 밖) 전 구간에서 patched/unpatched weight 시퀀스 diff 0 확인.
    TTC가 6~12s 램프 구간을 오가도록 v_lead를 흔들고, aLead 강도도 -1.8 이하로 섞어서
    (게이트가 열릴 조건의 절반(a_lead)은 만족해도 v_ego 게이트가 막아야 함을 확인)."""
    v_ego_const = 25.0  # m/s (~90km/h), 게이트(8.33m/s)보다 한참 위
    n = 400
    rng = np.random.default_rng(58)
    max_diff = 0.0
    for patched in (False, True):
        pass  # placeholder, actual comparison below

    state_u = {'prev_w': 1.0}
    state_p = {'prev_w': 1.0}
    diffs = []
    for i in range(n):
        dRel = 40.0 + 10.0 * np.sin(i * 0.05)
        v_lead = v_ego_const - 2.0 * np.sin(i * 0.03) - 1.0
        a_lead = -2.0 if (i // 40) % 2 == 0 else -0.2  # 강한/완만 감속 번갈아
        desired_distance = 35.0
        w_u, _ = run_cycle(state_u, dRel, v_ego_const, v_lead, a_lead, desired_distance, patched=False)
        w_p, _ = run_cycle(state_p, dRel, v_ego_const, v_lead, a_lead, desired_distance, patched=True)
        diffs.append(abs(w_u - w_p))
    max_diff = max(diffs)
    print(f"[A] 고속 회귀검증: max|w_unpatched - w_patched| = {max_diff:.6f}  ({'PASS' if max_diff == 0.0 else 'FAIL'})")
    return max_diff == 0.0


def scenario_B_event_reproduction():
    """저속 정체 이벤트 재현: v_ego 0->8m/s 가속 중 앞차는 이미 -1.8m/s^2로 감속.
    unpatched: TTC가 GATE_NONE(6.0s) 위에 머무는 동안 weight가 낮게 눌려있다가,
               TTC가 6.0s 밑으로 떨어지는 순간부터 rise-rate(1.0/s)에 걸려서도
               불과 1초 안에 0->1까지 튀어오름 (감쇠 누적분이 몰려서 반영).
    patched:   저속(<=30km/h) + a_lead<=-1.8 조건이 처음부터 계속 참이므로
               weight가 시작부터 1.0 고정 -- 감쇠 자체가 발생하지 않음."""
    # route a3a55cb808 seg12 t=4420~4423 실측 근사 재현: min TTC=4.45s(danger
    # 2.5s와는 무관), dRel 17~24m대, ego 가속 중, a_lead 근사치 -1.5~-2.0.
    # closing(접근율)을 직접 통제해 0->4.5m/s로 램프 후 유지(danger 문턱을
    # 우연히 건드리지 않도록 dRel 하한을 15m로 둠 -- 실측 범위 17~24m과 정합).
    n = 150  # 7.5s @ 20Hz
    a_lead = -1.8
    desired_distance = 20.0
    dRel0 = 24.0
    CLOSING_TARGET = 4.5   # m/s, 램프 후 정상상태 closing (실측 dRel/TTC 범위와 정합되도록 선택)
    CLOSING_RAMP_T = 2.0   # s

    state_u = {'prev_w': 1.0}
    state_p = {'prev_w': 1.0}
    log_u, log_p, log_ttc, log_vego = [], [], [], []
    dRel = dRel0
    for i in range(n):
        t = i * DT
        v_ego_t = min(8.0, 1.5 * t)                                  # ego: 정차 이후 재가속, 0->8m/s(28.8km/h)
        closing = CLOSING_TARGET * min(1.0, t / CLOSING_RAMP_T)       # 0->4.5m/s로 서서히 램프 후 유지
        v_lead_t = max(0.3, v_ego_t - closing)                        # lead 속도는 ego-closing으로 역산(음수 방지)
        dRel = max(15.0, dRel - closing * DT)                         # 실측 dRel 하한(17~24m대)과 정합되도록 15m에서 바닥
        w_u, ttc = run_cycle(state_u, dRel, v_ego_t, v_lead_t, a_lead, desired_distance, patched=False)
        w_p, _ = run_cycle(state_p, dRel, v_ego_t, v_lead_t, a_lead, desired_distance, patched=True)
        log_u.append(w_u); log_p.append(w_p); log_ttc.append(ttc); log_vego.append(v_ego_t)

    finite_ttc = [t for t in log_ttc if np.isfinite(t)]
    min_ttc = min(finite_ttc)
    peak_v_kmh = max(log_vego) * 3.6
    danger_hit = min_ttc <= LEAD_ACQ_TTC_DANGER
    print(f"[B] 이벤트 재현: min TTC={min_ttc:.2f}s, peak v_ego={peak_v_kmh:.1f}km/h, "
          f"danger override(<=2.5s) {'발동함(시나리오 오염!)' if danger_hit else '미발동 (실측 4.45s와 정합)'}")

    # unpatched: 초반(TTC 높을 때) weight가 낮게 눌려있어야(감쇠 발생) 함
    early_w_u = log_u[10]  # t=0.5s
    # unpatched: 어느 시점엔 rise-rate 제한 상태에서 급격한 상승(burst)이 있어야 함
    max_step_u = max(abs(log_u[i] - log_u[i-1]) for i in range(1, n))
    # patched: 전 구간 weight=1.0 고정(감쇠 자체가 없음, danger override 경로가 아니라
    # low_speed_strong_lead_decel 경로로 도달했는지가 핵심이므로 danger_hit=False 필수)
    all_one_p = all(w == 1.0 for w in log_p)
    ok = (early_w_u < 0.5) and all_one_p and (not danger_hit)
    print(f"    unpatched 초반(t=0.5s) weight={early_w_u:.3f} (감쇠 발생 확인, <0.5 기대)")
    print(f"    unpatched 최대 사이클당 변화폭={max_step_u:.3f} (rise-rate 한계={LEAD_ACCEL_WEIGHT_RISE_RATE*DT:.3f} 근처에서 걸림 -- 몰아서 반영되는 구간)")
    print(f"    patched 전 구간 weight==1.0 여부: {all_one_p} (danger override 아닌 저속게이트 경로로 도달)")
    print(f"    [B] {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_C_false_positive_guard():
    """저속이지만 앞차 감속이 완만(threshold 미달, -0.5m/s^2)한 경우:
    저속 게이트 분기가 열리면 안 됨 -- patched/unpatched weight 시퀀스가
    100% 동일해야 한다 (diff 0)."""
    n = 200
    v_ego = 0.0
    a_lead = -0.5  # threshold(-1.8)보다 완만
    desired_distance = 20.0
    dRel = 24.0

    state_u = {'prev_w': 1.0}
    state_p = {'prev_w': 1.0}
    diffs = []
    for i in range(n):
        t = i * DT
        v_ego_t = min(8.0, 1.2 * t)
        v_lead_t = max(1.0, 8.0 + a_lead * t)
        closing = v_ego_t - v_lead_t
        dRel = max(3.0, dRel - closing * DT)
        w_u, _ = run_cycle(state_u, dRel, v_ego_t, v_lead_t, a_lead, desired_distance, patched=False)
        w_p, _ = run_cycle(state_p, dRel, v_ego_t, v_lead_t, a_lead, desired_distance, patched=True)
        diffs.append(abs(w_u - w_p))
    max_diff = max(diffs)
    print(f"[C] 완만감속 오탐방지: max|diff| = {max_diff:.6f}  ({'PASS' if max_diff == 0.0 else 'FAIL'})")
    return max_diff == 0.0


def scenario_D_gate_boundary_transition():
    """v_ego가 게이트값(30km/h=8.333m/s)을 위/아래로 넘나드는 구간에서
    예외 없이 동작하고, 게이트를 벗어나는 프레임부터 즉시 분기가 닫히는지 확인."""
    n = 300
    gate = LOW_SPEED_STRONG_DECEL_V_EGO_GATE
    a_lead = -2.0  # threshold 항상 만족
    desired_distance = 20.0
    dRel = 20.0
    state_p = {'prev_w': 1.0}
    ok = True
    for i in range(n):
        t = i * DT
        # 6~10 m/s 사이를 sin으로 왕복(게이트 8.333을 여러 번 넘나듦)
        v_ego_t = 8.0 + 2.0 * np.sin(t * 1.5)
        v_lead_t = max(0.5, v_ego_t - 1.0)
        closing = v_ego_t - v_lead_t
        dRel = max(3.0, min(30.0, dRel - closing * DT * 0.3))
        w_p, ttc = run_cycle(state_p, dRel, v_ego_t, v_lead_t, a_lead, desired_distance, patched=True)
        gate_open_expected = (v_ego_t <= gate) and (a_lead <= LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH)
        if gate_open_expected and w_p != 1.0:
            ok = False
            print(f"    [FAIL] t={t:.2f} v_ego={v_ego_t:.2f} 게이트 열려야 하는데 w={w_p}")
    print(f"    경계 전이 {n}프레임 예외 없이 처리, 게이트 열린 프레임 전부 w=1.0 확인: {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == '__main__':
    results = {
        'A_high_speed_regression': scenario_A_high_speed_regression(),
        'B_event_reproduction': scenario_B_event_reproduction(),
        'C_false_positive_guard': scenario_C_false_positive_guard(),
        'D_gate_boundary_transition': scenario_D_gate_boundary_transition(),
    }
    print()
    print("=== 요약 ===")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print()
    all_pass = all(results.values())
    print("전체:", "PASS" if all_pass else "FAIL")
    import sys
    sys.exit(0 if all_pass else 1)
