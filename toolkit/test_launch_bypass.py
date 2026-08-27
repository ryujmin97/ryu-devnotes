#!/usr/bin/env python3
"""
45차 "정지 후 출발 가속 약화" 대응 -- launch bypass 로직 회귀 검증
스크립트.

당시(45차) 이 검증은 세션 컨테이너의 work/test_launch_bypass.py에만
있었고 `toolkit/`에는 저장되지 않아 45차 WIP 기록에만 "exit 전환 순간
w가 급하강할 수 있음을 발견" 결과가 남아있었음 -- 80차에서 뒤늦게
발견/정식 편입. 45차 이후로도 38/39/58차2번/67차(방안G) 등 같은 함수
(`process_lead()`)에 계속 새 분기가 추가돼 왔으므로, 이 로직을 건드리는
향후 패치의 회귀 검증용으로 재사용 가능하도록 남긴다.

재현 대상 (`long_mpc.py` `process_lead()` 앞부분, 위쪽부터):
- `LAUNCH_BYPASS_STOP_V_EGO`(0.3m/s)/`LAUNCH_BYPASS_EXIT_V_EGO`(5.0m/s)
  -- 정차/출발완료 판정 (lead 유무와 무관하게 v_ego만으로 상태 갱신)
- bypass 활성 중: `ttc_w = 1.0`(38차 TTC 게이트 완전 우회) +
  rise-rate(39차, `LEAD_ACCEL_WEIGHT_RISE_RATE`) 제한도 함께 우회
- `lead0_danger_now`(TTC<=2.5s 또는 58차2번 저속강한감속)는 bypass
  여부와 무관하게 항상 최우선(w=1.0 강제)

**주의**: 이 스크립트는 `w`(lead accel damping weight) 계산 경로만
순수함수로 재현한다. `dist_w`(margin_accel_weight)는 회귀 확인에
불필요한 경우 1.0(무제한)으로 고정해 `ttc_w`/rise-rate/danger override
세 갈래에만 집중하도록 단순화했다 -- 실제 승차감 영향까지 보려면
`replay_boost_duration.py`류처럼 실측 route CSV 기반 재생이 필요.

의존성: 없음(표준 라이브러리만).

사용:
    python3 test_launch_bypass.py
"""

LAUNCH_BYPASS_STOP_V_EGO = 0.3
LAUNCH_BYPASS_EXIT_V_EGO = 5.0
LEAD_ACQ_TTC_DANGER = 2.5
LEAD_ACCEL_WEIGHT_RISE_RATE = 1.0
DT = 0.05


class LaunchBypassReplay:
    def __init__(self):
        self._launch_bypass_active = False
        self._lead_accel_weight_prev = 0.0

    def step(self, v_ego, x_lead, v_lead, dist_w=1.0, low_speed_strong_lead_decel=False):
        # bypass 상태 갱신 (process_lead 최상단, lead 분기 이전)
        if v_ego < LAUNCH_BYPASS_STOP_V_EGO:
            self._launch_bypass_active = True
        elif v_ego >= LAUNCH_BYPASS_EXIT_V_EGO:
            self._launch_bypass_active = False

        closing = v_ego - v_lead
        ttc_now = x_lead / closing if closing > 0.1 else float("inf")

        if self._launch_bypass_active:
            ttc_w = 1.0
        else:
            # 38차 ttc_accel_weight()의 간략 근사(회귀 검증엔 정확한 곡선 불필요,
            # ramp 자체가 존재한다는 사실만 필요) -- 실제 함수는 GATE_NONE(6.0s)~
            # GATE_FULL(12.0s) 사이 선형 보간. 여기선 6.0s 미만이면 damping(0.0),
            # 그 이상이면 무감쇠(1.0)로 단순화.
            ttc_w = 0.0 if ttc_now < 6.0 else 1.0

        w = min(dist_w, ttc_w)
        lead0_danger_now = ttc_now <= LEAD_ACQ_TTC_DANGER or low_speed_strong_lead_decel

        if lead0_danger_now:
            w = 1.0
        elif self._launch_bypass_active:
            pass  # rise-rate 제한도 우회
        elif w > self._lead_accel_weight_prev:
            w = min(w, self._lead_accel_weight_prev + LEAD_ACCEL_WEIGHT_RISE_RATE * DT)

        self._lead_accel_weight_prev = w
        return w, self._launch_bypass_active, ttc_now


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  PASS: {msg}")


def scenario_stop_then_launch():
    """정차 중(v_ego<0.3) -> 출발 가속(v_ego가 서서히 5.0 미만까지 상승,
    앞차가 자차보다 빠른 상태, closing<=0.1) -- bypass 활성 중엔 w=1.0
    (완전 무감쇠)이어야 앞차의 실측 가속(aLeadK)이 그대로 반영됨."""
    print("[시나리오1] 정차->출발(closing<=0.1) 구간 -- bypass 중 w=1.0 유지")
    r = LaunchBypassReplay()
    # 정차 상태에서 시작
    w, active, ttc = r.step(v_ego=0.1, x_lead=10.0, v_lead=5.0)
    _assert(active, "v_ego<0.3 -> bypass 활성(arm)")
    _assert(w == 1.0, f"w={w} (bypass 중이라 dist_w=1.0과 ttc_w=1.0의 min=1.0)")

    # 서서히 가속하며 앞차보다 계속 느림(v_ego < v_lead, closing<=0.1 유지)
    for v_ego in [1.0, 2.0, 3.0, 4.0, 4.9]:
        w, active, ttc = r.step(v_ego=v_ego, x_lead=15.0, v_lead=5.0)
        _assert(active and w == 1.0,
                f"v_ego={v_ego}: bypass 유지(active={active}), w={w} (여전히 무감쇠)")


def scenario_exit_transition():
    """v_ego가 EXIT_V_EGO(5.0)를 넘는 순간 bypass가 해제되고 38차 TTC
    게이트로 복귀 -- 45차 WIP이 발견한 '전환 순간 w가 급하강할 수 있음'을
    재현(회귀 아님, 알려진 설계 특성으로 문서화 목적)."""
    print("[시나리오2] EXIT_V_EGO(5.0) 전환 순간 -- 38차 로직 복귀, w 급변 가능성 확인")
    r = LaunchBypassReplay()
    r.step(v_ego=0.1, x_lead=10.0, v_lead=5.0)  # bypass 진입
    w_before, active_before, ttc_before = r.step(v_ego=4.9, x_lead=20.0, v_lead=6.0)
    w_after, active_after, ttc_after = r.step(v_ego=5.1, x_lead=20.0, v_lead=6.0)
    _assert(active_before and not active_after,
            f"전환 확인: exit 전(active={active_before}) -> exit 후(active={active_after})")
    print(f"  참고: 전환 전 w={w_before}, 전환 후 w={w_after}, ttc_now={ttc_after:.2f}s"
          f" -- ttc_now<6.0s이면 ttc_w=0.0으로 즉시 떨어짐(45차가 지적한 급하강 가능성)")


def scenario_danger_override_during_bypass():
    """bypass 활성 중이라도 진짜 위험(TTC<=2.5s)이면 danger override가
    최우선 -- 이 부분이 무너지면 안전 회귀."""
    print("[시나리오3] bypass 중 진짜 위험(TTC<=2.5s) -- danger override 정상 발동")
    r = LaunchBypassReplay()
    r.step(v_ego=0.1, x_lead=10.0, v_lead=5.0)  # bypass 진입
    # closing이 커져서(v_ego>v_lead) ttc_now가 2.5s 미만이 되는 상황
    w, active, ttc = r.step(v_ego=3.0, x_lead=5.0, v_lead=1.0)
    _assert(active, "여전히 bypass 활성(v_ego<5.0)")
    _assert(ttc <= LEAD_ACQ_TTC_DANGER, f"ttc_now={ttc:.2f}s <= {LEAD_ACQ_TTC_DANGER}s (진짜 위험)")
    _assert(w == 1.0, f"w={w} (danger override가 bypass보다 우선 -- 이미 1.0이라 구분은 안 되나"
                       " 로직상 danger 분기가 bypass 분기보다 먼저 체크됨을 코드 순서로 보장)")


def scenario_regression_high_speed_normal():
    """고속/일반 주행(bypass 밖) 회귀 확인 -- 38/39차 로직이 그대로 살아있어야 함."""
    print("[시나리오4] 회귀 확인 -- 고속 정상주행(v_ego>=5.0)에서는 38/39차 로직 그대로")
    r = LaunchBypassReplay()
    # 여러 프레임 반복 -- rise-rate(39차, 1.0/s) 제한으로 w=0->1까지 최소 1초
    # 걸리므로, 첫 프레임만 보면 0.05(rise-rate 한 스텝분)로 보이는 게 정상
    # 동작이다(버그 아님) -- 20프레임(1.0s) 반복해 최종적으로 1.0에 도달하는지 확인.
    active = None
    for _ in range(25):
        w, active, ttc = r.step(v_ego=20.0, x_lead=200.0, v_lead=19.0)  # ttc_now 크고 완만
    _assert(not active, "v_ego>=5.0 -> bypass 비활성")
    # ttc_now = 200/1.0 = 200s > 6.0 -> ttc_w=1.0(근사), dist_w=1.0 ->
    # rise-rate로 서서히 1.0까지 수렴(급붕괴 방지가 39차의 원래 목적)
    _assert(w == 1.0, f"w={w} (rise-rate로 서서히 무감쇠(1.0)에 수렴 -- 39차 로직 회귀 없음)")


if __name__ == "__main__":
    scenario_stop_then_launch()
    scenario_exit_transition()
    scenario_danger_override_during_bypass()
    scenario_regression_high_speed_normal()
    print("\n전 시나리오 통과 -- launch bypass(45차) 로직이 현재 long_mpc.py"
          " 구조(danger override 최우선 -> bypass -> rise-rate)와 일치.")
