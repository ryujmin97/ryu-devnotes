"""
LOW_SPEED_GAP_OPEN_* 합성 검증 (신규 방안 -- 6님 제보 "저속에서 앞차 멀어질 때
너무 급하게 재가속 -> 다시 붙을 때 급브레이크" 대응)

목적: 저속(<=40km/h)에서, 이미 desired_distance보다 충분히 벌어진 상태
(gap_ratio >= MARGIN_ACCEL_GATE_FULL, 기존 dist_w 경계 재사용)에서 앞차가
강하게 가속(멀어짐)할 때만 자차 MPC에 넘기는 a_lead에 상한(ACCEL_CAP)을
건다. "정지 후 정상 출발" 재발(45차 사례와 동일 함정)을 막기 위해
(1) _launch_bypass_active 구간은 명시적으로 제외하고,
(2) gap_ratio가 낮은(아직 desired_distance 이내로 쫓아가는 중) 정상 주행/
    출발 연장 구간도 게이트 자체가 안 열리도록 설계.

process_lead()의 관련 분기만 순수함수로 재현(실제 acados MPC는 안 거침).

검증 항목:
  A) 고속 회귀: v_ego가 게이트(40km/h) 밖인 전 구간에서 patched/unpatched
     a_lead 시퀀스가 100% 동일해야 한다 (diff 0).
  B) 정상 출발(launch bypass, v_ego 0->5m/s 구간): a_lead가 강하게 양수여도,
     그리고 dRel/desired_distance가 우연히 1.5를 넘어도, bypass 중엔 캡이
     걸리면 안 된다 (45차 재발 방지 -- defense in depth).
  C) 정상 출발 연장(bypass 해제 후 5m/s~11.11m/s(40km/h) 구간): 아직
     desired_distance 근처로 쫓아가는 중(gap_ratio<1.5)이라 캡이 걸리면
     안 된다 -- "너무 천천히 출발" 오탐 방지의 핵심 시나리오.
  D) 이벤트 재현: 저속 + 이미 gap_ratio>=1.5로 벌어진 상태 + 앞차 강한 가속
     지속 시, a_lead가 ACCEL_CAP으로 클램프돼야 한다.
  E) 오탐 방지: 저속 + gap_ratio>=1.5이지만 앞차 가속이 완만(threshold
     미달)한 경우엔 캡이 걸리면 안 된다 (patched/unpatched diff 0).
  F) 경계 전이: gap_ratio가 1.5를 넘나들 때 예외 없이 즉시 반응하는지,
     그리고 그 전이 순간 a_lead에 생기는 단차(discontinuity) 크기를
     측정해서 보고한다 (하드 클램프라 순간적으로 a_lead가 뚝 떨어지는
     역효과가 있는지 -- 있다면 방안I류 완만화가 별도로 필요할 수 있음,
     NEEDS_VALIDATION 항목으로 남김).
"""
import numpy as np

# --- long_mpc.py 기존 상수 재현 ---
MARGIN_ACCEL_GATE_FULL = 1.5
MARGIN_ACCEL_GATE_NONE = 1.0
LAUNCH_BYPASS_STOP_V_EGO = 0.3
LAUNCH_BYPASS_EXIT_V_EGO = 5.0
DT = 0.05  # 20Hz

# --- 신규 상수(제안값, NEEDS_VALIDATION) ---
LOW_SPEED_GAP_OPEN_V_EGO_GATE = 40.0 / 3.6      # ~11.11 m/s
LOW_SPEED_GAP_OPEN_A_LEAD_THRESH = 1.0          # m/s^2
LOW_SPEED_GAP_OPEN_ACCEL_CAP = 0.5              # m/s^2
LOW_SPEED_GAP_OPEN_MARGIN_RATIO = MARGIN_ACCEL_GATE_FULL  # 1.5, 기존 dist_w 경계 재사용


class LaunchBypassState:
    """process_lead()의 launch bypass 상태 갱신부만 재현."""
    def __init__(self):
        self.active = False

    def update(self, v_ego):
        if v_ego < LAUNCH_BYPASS_STOP_V_EGO:
            self.active = True
        elif v_ego >= LAUNCH_BYPASS_EXIT_V_EGO:
            self.active = False
        return self.active


def apply_gap_open_cap(a_lead, v_ego, dRel, desired_distance, launch_bypass_active, patched):
    """신규 로직. patched=False면 항상 원본 a_lead 그대로 반환(회귀 비교용)."""
    if not patched:
        return a_lead, False
    if desired_distance <= 1.0:
        return a_lead, False
    gap_ratio = dRel / desired_distance
    apply = (
        v_ego <= LOW_SPEED_GAP_OPEN_V_EGO_GATE
        and a_lead >= LOW_SPEED_GAP_OPEN_A_LEAD_THRESH
        and (not launch_bypass_active)
        and gap_ratio >= LOW_SPEED_GAP_OPEN_MARGIN_RATIO
    )
    if apply:
        return min(a_lead, LOW_SPEED_GAP_OPEN_ACCEL_CAP), True
    return a_lead, False


def scenario_A_high_speed_regression():
    """고속(게이트 밖, 항상 40km/h 초과) 전 구간에서 patched/unpatched a_lead
    시퀀스 diff 0 확인. gap_ratio/a_lead 둘 다 게이트 조건을 만족하도록 흔들어서
    (v_ego 게이트만으로 확실히 막히는지 확인)."""
    n = 300
    v_ego_const = 15.0  # m/s (=54km/h), 게이트(11.11)보다 위
    bypass = LaunchBypassState()
    diffs = []
    for i in range(n):
        t = i * DT
        a_lead = 1.5 + 0.5 * np.sin(t)          # threshold(1.0) 항상 초과
        dRel = 40.0 + 10.0 * np.sin(t * 0.7)
        desired_distance = 20.0                  # gap_ratio 최대 2.5까지 -- 게이트 조건(margin) 항상 만족
        lb_active = bypass.update(v_ego_const)
        a_u, _ = apply_gap_open_cap(a_lead, v_ego_const, dRel, desired_distance, lb_active, patched=False)
        a_p, _ = apply_gap_open_cap(a_lead, v_ego_const, dRel, desired_distance, lb_active, patched=True)
        diffs.append(abs(a_u - a_p))
    max_diff = max(diffs)
    print(f"[A] 고속 회귀검증: max|a_lead diff| = {max_diff:.6f}  ({'PASS' if max_diff == 0.0 else 'FAIL'})")
    return max_diff == 0.0


def scenario_B_launch_bypass_exclusion():
    """정지->출발 초기 구간(v_ego 0->5m/s, launch bypass 활성 구간): a_lead가
    강하게 양수(2.5 m/s^2)이고 dRel/desired_distance가 우연히 1.5를 넘도록
    구성해도(정지 직후라 실제로는 드문 조합이지만 defense-in-depth 검증 목적),
    bypass 중엔 캡이 걸리면 안 된다."""
    n = 100  # 5s
    a_lead = 2.5  # threshold(1.0)보다 훨씬 강한 가속
    desired_distance = 5.0  # 일부러 작게 잡아 gap_ratio가 쉽게 1.5를 넘도록
    dRel = 8.0  # gap_ratio = 1.6 >= 1.5
    bypass = LaunchBypassState()
    ok = True
    v_ego = 0.0
    for i in range(n):
        t = i * DT
        v_ego = min(4.9, 1.2 * t)  # LAUNCH_BYPASS_EXIT_V_EGO(5.0) 밑에 머물도록
        lb_active = bypass.update(v_ego)
        a_p, capped = apply_gap_open_cap(a_lead, v_ego, dRel, desired_distance, lb_active, patched=True)
        if not lb_active:
            print(f"    [경고] t={t:.2f} v_ego={v_ego:.2f} bypass가 예상보다 일찍 해제됨(시나리오 구성 재검토 필요)")
        if capped:
            ok = False
            print(f"    [FAIL] t={t:.2f} v_ego={v_ego:.2f} bypass 중인데 캡이 걸림 (a_lead {a_lead}->{a_p})")
    print(f"    launch bypass {n}프레임 동안 캡 미적용 확인: {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_C_normal_launch_extension():
    """bypass 해제 후(5m/s~11.11m/s, ~18~40km/h) 정상 출발 연장 구간: 자차가
    아직 desired_distance 이내로 쫓아가는 중(gap_ratio<1.5)이므로, 앞차가
    강하게 가속 중이어도 캡이 걸리면 안 된다 -- '너무 천천히 출발' 오탐
    방지의 핵심 시나리오."""
    n = 150  # 7.5s
    a_lead = 2.0  # threshold 초과, 강하게 가속
    desired_distance = 15.0
    dRel = 14.0  # gap_ratio = 0.933 < 1.5 (아직 목표거리 이내로 따라가는 중)
    bypass = LaunchBypassState()
    ok = True
    for i in range(n):
        t = i * DT
        v_ego = min(11.0, 5.0 + 0.8 * t)  # 5m/s에서 시작해 게이트(11.11) 근처까지 가속
        lb_active = bypass.update(v_ego)
        # dRel도 서서히 desired_distance에 가깝게 수렴(정상 추종 중이라는 가정)
        dRel_t = min(desired_distance * 1.2, dRel + 0.3 * t)  # gap_ratio 최대 1.2대까지만
        a_p, capped = apply_gap_open_cap(a_lead, v_ego, dRel_t, desired_distance, lb_active, patched=True)
        if capped:
            ok = False
            print(f"    [FAIL] t={t:.2f} v_ego={v_ego:.2f} gap_ratio={dRel_t/desired_distance:.2f} "
                  f"정상 출발 연장 구간인데 캡이 걸림")
    print(f"    출발 연장(18~40km/h) {n}프레임 동안 캡 미적용 확인: {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_D_event_reproduction():
    """이벤트 재현: 저속(30km/h) + 이미 gap_ratio>=1.5로 벌어진 상태 +
    앞차가 강하게(2.0 m/s^2) 가속 지속 -- a_lead가 CAP(0.5)으로
    클램프돼야 한다."""
    n = 100
    v_ego = 30.0 / 3.6  # 8.33 m/s, 게이트(11.11) 안
    a_lead = 2.0
    desired_distance = 15.0
    dRel = 24.0  # gap_ratio = 1.6 >= 1.5
    bypass = LaunchBypassState()
    bypass.active = False  # 이미 정상주행 중(출발 상태 아님)
    capped_frames = 0
    final_a = None
    for i in range(n):
        lb_active = bypass.update(v_ego)  # v_ego가 계속 5.0 이상이므로 active=False 유지
        a_p, capped = apply_gap_open_cap(a_lead, v_ego, dRel, desired_distance, lb_active, patched=True)
        if capped:
            capped_frames += 1
        final_a = a_p
    ok = (capped_frames == n) and (final_a == LOW_SPEED_GAP_OPEN_ACCEL_CAP)
    print(f"    {n}프레임 중 캡 적용 프레임={capped_frames}, 최종 a_lead={final_a} "
          f"(기대: {LOW_SPEED_GAP_OPEN_ACCEL_CAP}) -- {'PASS' if ok else 'FAIL'}")
    return ok


def scenario_E_false_positive_guard():
    """저속 + gap_ratio>=1.5로 벌어진 상태이지만 앞차 가속이 완만
    (threshold(1.0) 미달, 0.5)한 경우: 캡이 걸리면 안 된다
    (patched/unpatched diff 0)."""
    n = 100
    v_ego = 25.0 / 3.6
    a_lead = 0.5  # threshold 미달
    desired_distance = 12.0
    dRel = 20.0  # gap_ratio = 1.667 >= 1.5 (거리 조건은 만족)
    bypass = LaunchBypassState()
    diffs = []
    for i in range(n):
        lb_active = bypass.update(v_ego)
        a_u, _ = apply_gap_open_cap(a_lead, v_ego, dRel, desired_distance, lb_active, patched=False)
        a_p, _ = apply_gap_open_cap(a_lead, v_ego, dRel, desired_distance, lb_active, patched=True)
        diffs.append(abs(a_u - a_p))
    max_diff = max(diffs)
    print(f"[E] 완만가속 오탐방지: max|diff| = {max_diff:.6f}  ({'PASS' if max_diff == 0.0 else 'FAIL'})")
    return max_diff == 0.0


def scenario_F_ratio_boundary_transition():
    """gap_ratio가 1.5 경계를 위/아래로 넘나들 때 예외 없이 즉시 토글되는지,
    그리고 그 전이 순간 a_lead에 생기는 단차(하드클램프로 인한 역-discontinuity)
    크기를 측정해서 보고한다. 이 단차 자체가 새로운 저크 소스가 될 수 있어
    NEEDS_VALIDATION으로 별도 표기."""
    n = 300
    v_ego = 20.0 / 3.6  # 게이트 안, 고정
    a_lead = 2.0  # threshold 항상 초과
    desired_distance = 15.0
    bypass = LaunchBypassState()
    bypass.active = False
    max_step = 0.0
    prev_a = a_lead
    toggled_correctly = True
    for i in range(n):
        t = i * DT
        # dRel을 12~24m 사이로 sin 왕복 -> gap_ratio 0.8~1.6 사이를 넘나듦
        dRel = 18.0 + 6.0 * np.sin(t * 1.2)
        gap_ratio = dRel / desired_distance
        lb_active = bypass.update(v_ego)
        a_p, capped = apply_gap_open_cap(a_lead, v_ego, dRel, desired_distance, lb_active, patched=True)
        expected_capped = gap_ratio >= LOW_SPEED_GAP_OPEN_MARGIN_RATIO
        if capped != expected_capped:
            toggled_correctly = False
            print(f"    [FAIL] t={t:.2f} gap_ratio={gap_ratio:.3f} 기대 capped={expected_capped} 실제={capped}")
        step = abs(a_p - prev_a)
        max_step = max(max_step, step)
        prev_a = a_p
    discontinuity = a_lead - LOW_SPEED_GAP_OPEN_ACCEL_CAP
    print(f"    경계 전이 {n}프레임 예외 없이 토글: {'PASS' if toggled_correctly else 'FAIL'}")
    print(f"    사이클간 최대 a_lead 변화폭={max_step:.3f} m/s^2 "
          f"(캡 진입 시 이론적 최대 단차={discontinuity:.3f} -- 하드클램프이므로 "
          f"완만화(rise-rate류) 없이 순간 반영됨. 값이 크면 방안I류 jerk 완만화 병행 검토 필요, NEEDS_VALIDATION)")
    return toggled_correctly


if __name__ == "__main__":
    results = {
        "A_high_speed_regression": scenario_A_high_speed_regression(),
        "B_launch_bypass_exclusion": scenario_B_launch_bypass_exclusion(),
        "C_normal_launch_extension": scenario_C_normal_launch_extension(),
        "D_event_reproduction": scenario_D_event_reproduction(),
        "E_false_positive_guard": scenario_E_false_positive_guard(),
        "F_ratio_boundary_transition": scenario_F_ratio_boundary_transition(),
    }
    print("\n=== 요약 ===")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    all_pass = all(results.values())
    print(f"\n전체: {'ALL PASS' if all_pass else 'SOME FAILED'}")
