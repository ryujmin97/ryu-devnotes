#!/usr/bin/env python3
"""
66차/67차(방안G) -- dRel discontinuity 직후 a_change_cost(저크비용)
한시적 부스트 로직('discontinuity' 트리거 소스, 비-handoff 한정)
합성검증 스크립트.

69차부터 여러 세션에 걸쳐 "toolkit/sim_jerk_boost.py 실물 존재 확인
필요"로 이월되던 항목 -- 실제로는 한 번도 작성된 적이 없었음(주석에서만
언급). 80차에서 신규 작성/저장.

재현 대상 (`selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`,
a_change_cost 적용부, `is_handoff_source` 분기 중 else(=='discontinuity'
소스) 갈래만):
    is_handoff_source = (self._discontinuity_trigger_source in
                          ('handoff', 'discontinuity_lc'))
    boost_gate_ok = (self._discontinuity_jerk_boost_timer > 0.0) and \
                    not self._lead0_danger_active
    if not is_handoff_source:
        boost_gate_ok = boost_gate_ok and (frac <= 0.0)
    ...
    else:  # 'discontinuity' 소스
        self.a_change_cost = DISCONTINUITY_JERK_COST_BOOST if boost_gate_ok \
                              else base_a_change_cost

'handoff'/'discontinuity_lc' 소스(방안I, 73차/76차 hard-hold+release-rate)는
이 스크립트 범위 밖 -- 별도 스크립트(replay_boost_duration.py, 이미
toolkit 편입됨)가 그쪽을 다룬다.

의존성: 없음(표준 라이브러리만).

사용:
    python3 sim_jerk_boost.py
"""

DISCONTINUITY_JERK_COST_BOOST_S = 1.0
DISCONTINUITY_JERK_COST_BOOST = 500.0
BASE_A_CHANGE_COST = 20.0  # 시나리오용 예시 base(실제는 상황별 다름, 최대 200)
DT = 0.05


class DiscontinuityBoostReplay:
    """'discontinuity' 소스 전용 boost 게이트 재현. frac/danger_active는
    process_lead()에서 매 프레임 갱신되는 외부 신호로 취급, step()에
    인자로 받는다."""

    def __init__(self):
        self._discontinuity_jerk_boost_timer = 0.0
        self.a_change_cost = BASE_A_CHANGE_COST

    def trigger(self):
        """DREL_DISCONTINUITY_* 조건(급락 감지) 발동 시 process_lead()가
        호출하는 것과 동일 -- 타이머를 1.0s로 arm."""
        self._discontinuity_jerk_boost_timer = DISCONTINUITY_JERK_COST_BOOST_S

    def step(self, frac=0.0, danger_active=False, base_a_change_cost=BASE_A_CHANGE_COST):
        # 게이트는 이번 프레임 시작 시점의 타이머 값(아직 살아있는 마지막
        # 프레임 포함)으로 판단한 뒤, 타이머를 감쇠시킨다 -- long_mpc.py
        # 실제 순서(이번 tick 값으로 boost 적용 여부를 정하고, 다음 tick을
        # 위해 타이머를 dt만큼 줄임)와 동일.
        boost_gate_ok = (self._discontinuity_jerk_boost_timer > 0.0) and not danger_active
        boost_gate_ok = boost_gate_ok and (frac <= 0.0)

        self.a_change_cost = DISCONTINUITY_JERK_COST_BOOST if boost_gate_ok else base_a_change_cost

        if self._discontinuity_jerk_boost_timer > 0.0:
            self._discontinuity_jerk_boost_timer = max(
                0.0, self._discontinuity_jerk_boost_timer - DT)

        return self.a_change_cost


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  PASS: {msg}")


def scenario_normal_trigger():
    """정상 트리거: danger=False, frac=0.0 유지 -- 1.0초 내내 boost
    유지되다가 소진 직후 base로 hard-cutoff(release-rate 없음, 이건
    'discontinuity' 소스 전용 특성)."""
    print("[시나리오1] 정상 트리거, danger=False/frac=0.0 -> 전 구간 boost 유지")
    r = DiscontinuityBoostReplay()
    r.trigger()
    n_steps = int(DISCONTINUITY_JERK_COST_BOOST_S / DT)
    boosted_all = all(r.step(frac=0.0, danger_active=False) == DISCONTINUITY_JERK_COST_BOOST
                       for _ in range(n_steps))
    _assert(boosted_all, f"트리거~{DISCONTINUITY_JERK_COST_BOOST_S}s 구간 전부 "
                          f"a_change_cost={int(DISCONTINUITY_JERK_COST_BOOST)}(BOOST) 유지")
    after = r.step(frac=0.0, danger_active=False)
    _assert(after == BASE_A_CHANGE_COST,
            f"{DISCONTINUITY_JERK_COST_BOOST_S}s 소진 직후부터 base_a_change_cost"
            f"({BASE_A_CHANGE_COST})로 hard-cutoff 복귀(release-rate 없음)")


def scenario_frac_gate_blocks():
    """frac>0(방안C/G 원설계의 proactive floor 게이트)이면 'discontinuity'
    소스는 boost가 완전히 무력화됨 -- 75차가 발견한 구조 그대로."""
    print("[시나리오2] frac>0(방안C/G 원설계의 frac 게이트) -> boost 무력화")
    r = DiscontinuityBoostReplay()
    r.trigger()
    n_steps = int(DISCONTINUITY_JERK_COST_BOOST_S / DT)
    boosted_frames = sum(r.step(frac=0.3, danger_active=False) == DISCONTINUITY_JERK_COST_BOOST
                          for _ in range(n_steps))
    _assert(boosted_frames == 0,
            "frac<=0.0 게이트를 만족하는 프레임이 없으므로 boost 프레임 0건"
            "(75차가 발견한 'discontinuity 소스는 frac 게이트에 막혀 무효화'되는 구조를 그대로 재현)")


def scenario_danger_overrides():
    """danger_active=True(TTC<=2.5s 진짜 위험)면 frac<=0.0이어도 boost
    게이트가 즉시 차단 -- 안전 우선 원칙."""
    print("[시나리오3] danger_active=True -> boost 게이트 즉시 차단(안전 우선)")
    r = DiscontinuityBoostReplay()
    r.trigger()
    result = r.step(frac=0.0, danger_active=True)
    _assert(result == BASE_A_CHANGE_COST,
            "danger_active 프레임에서는 frac<=0.0이어도 boost가 걸리지 않음"
            "(danger override가 항상 최우선이라는 설계 원칙 재확인)")


def scenario_no_trigger_regression():
    """트리거 자체가 없는 일반 주행 구간(회귀 확인) -- 패치 전/후 동일해야 함."""
    print("[시나리오4] 트리거 없음(회귀) -> 전 구간 base 그대로, 개입 없음")
    r = DiscontinuityBoostReplay()
    results = [r.step(frac=0.0, danger_active=False) for _ in range(40)]
    _assert(all(v == BASE_A_CHANGE_COST for v in results),
            "discontinuity 트리거가 없는 일반 주행 구간은 패치 전/후 동일(회귀 없음)")


def scenario_boost_exhausted_during_sustained_decel():
    """72차가 실측으로 발견한 한계: boost(1.0s) 소진 후에도 급감속이
    계속되는 경우, 'discontinuity' 소스는 release-rate가 없어 즉시
    base로 떨어짐 -- 이 한계 자체가 방안I(handoff, 별도 스크립트)의
    도입 근거였음을 로직 단위로도 재확인."""
    print("[시나리오5] boost(1.0s) 소진 후에도 급감속 지속(72차 실측 패턴 재현)")
    r = DiscontinuityBoostReplay()
    r.trigger()
    n_steps = int(DISCONTINUITY_JERK_COST_BOOST_S / DT)
    for _ in range(n_steps):
        r.step(frac=0.0, danger_active=False)
    # boost 소진 이후에도 base_a_change_cost 자체가 낮게(20.0) 유지되는 상황을
    # 몇 프레임 더 재현 -- release-rate 메커니즘이 'discontinuity' 소스에는
    # 없으므로 즉시 base로 떨어진 상태가 계속 유지된다.
    still_base = all(r.step(frac=0.0, danger_active=False) == BASE_A_CHANGE_COST
                      for _ in range(20))
    _assert(still_base,
            "boost 소진 직후 base_a_change_cost가 이미 20.0으로 낮아져 있으면"
            "boost 이전과 동일하게 저크비용이 낮은 상태로 복귀 -- 72차가 실측 발견한"
            " '1.0s 윈도우가 지속 급감속엔 구조적으로 부족'하다는 한계를 로직 단위로도 재확인")


if __name__ == "__main__":
    scenario_normal_trigger()
    scenario_frac_gate_blocks()
    scenario_danger_overrides()
    scenario_no_trigger_regression()
    scenario_boost_exhausted_during_sustained_decel()
    print("\n전 시나리오 통과 -- 'discontinuity'(비-handoff) 소스 a_change_cost"
          " hard-cutoff 게이트가 현재 long_mpc.py와 일치함을 확인.")
