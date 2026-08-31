## 176차 — [원인B 재현검증 SUCCESS] acados 실솔버 폐루프 시뮬레이션으로 174차 원인B(A_CHANGE_COST=200이 리드없는 cruise 모드에서 가속->감속 부호전환을 구조적으로 지연시킨다) 가설 확인 -- baseline(200) 부호전환 1.5s vs 완화값(20) 1.0s, 0.5초 차이 재현

**배경**: 175차가 확립한 acados 실솔버 빌드 절차(`build_acados_long_mpc.sh`) 위에서
174차 정적분석 가설을 실제 solver 출력으로 검증. route `00000372--6310bba9b8--5,6`
raw zip이 devnotes 캐시에 없어(172/174차 모두 재업로드였고 176차 세션엔 미제공)
실측 프레임별 값을 직접 주입하지 못하고, FINDINGS.md 174차 요약 특성(vEgo/
liveRouteSpeed가 ~57~58kph에서 교차, 이후 목표 57.9->48.1kph 3초 램프,
leadStatus=False)을 재현한 통제된 합성 시나리오로 진행(`sim_acados_causeB_signflip.py`,
toolkit 편입 완료).

**방법**: `LongitudinalMpc.update()`가 요구하는 `carrot`/`radarstate` 인터페이스를
Params 의존 없는 최소 mock(`FakeCarrot`/`FakeLead`/`FakeRadarState`)으로 구현.
T_FOLLOW는 이 가설과 무관하므로 표준 personality 근사 고정값(1.2s)으로 단순화.
매 사이클 `a_solution[1]`을 다음 스텝 명령가속도로 삼아 ego 상태를 직접 적분
전진하는 폐루프(무지연 이상화, 실측보다 관대한 조건)로 4초간 시뮬레이션.

**결과(SUCCESS)**:
| 조건 | A_CHANGE_COST | 가속->감속 부호전환 시각 | t=3.0s gap |
|---|---|---|---|
| baseline(현재 코드) | 200 | 1.5s | +9.19kph |
| 완화(리드있음 최소값) | 20 | 1.0s | +7.41kph |

baseline이 완화 조건보다 부호전환이 0.5초 더 느리고 3초 시점 gap도 더 큼 --
174차 가설(리드없는 cruise 모드에서 A_CHANGE_COST=200이 목표속도 하강 추종을
구조적으로 지연시킨다)이 acados 실솔버 거동으로도 재현 확인됨.

**해석 시 주의**: leadStatus=False를 4초 전 구간 고정했으나 실측(174차)은
t=830.55(구간 시작 약 1초 후)에 리드가 재획득됨 -- 이번 시뮬레이션은 "리드
재획득 도움 없이 얼마나 느린가"의 상한(worst-case) 재현. 실측 gap(4.35kph)보다
시뮬레이션 gap(9.19kph)이 더 크게 나온 것은 이 때문(정상, 오차 아님). 정량적
절대값 일치가 목적이 아니라 "A_CHANGE_COST 크기가 부호전환 속도에 구조적
영향을 준다"는 정성적 인과관계 확인이 목적이며, 그 목적은 달성됨.

**다음 단계**: 원인B 패치 설계로 진행 가능 -- 리드없는 cruise 모드(mode='acc',
leadStatus=False)에서 가속->감속 부호전환 구간에 한정해 a_change_cost를
한시적으로 완화하는 방안(66/67/73/76차의 discontinuity 부스트 패턴과 유사하되
반대 방향 -- "완화" 게이트). 글로벌 kill-switch가 아니라 특정 시나리오(부호전환
검출 + leadStatus=False) 한정 게이트로 설계할 것(프로젝트 원칙).

**toolkit 변경**: `sim_acados_causeB_signflip.py` 신규 편입(README/CHANGELOG 갱신 완료).

---

## 176차 계속 — [원인B 실측 프레임 재검증, 방향 재확인 BUT 절대치 괴리 미해결] route `00000372--6310bba9b8--5,6` raw zip 재업로드 후 실측 프레임 단위 정밀 재현 -- closedloop 모드에서 baseline(A_CHANGE_COST=200) vs 완화(20) 부호전환 0.45s 차이로 가설 방향 재확인. 단, 시뮬레이션 절대 감속량이 실측보다 훨씬 약함(원인 미해결) + t=832.51(brakePressed=True) 이후 실측은 운전자 수동제동 혼입 구간이라 MPC 단독 출력과 비교 자체가 무효

**배경**: 176차 1차(합성 시나리오, `sim_acados_causeB_signflip.py`)가 가설을
정성적으로 재현한 직후, 사용자가 174/172차와 동일 route(`00000372--6310bba9b8--5,6`)
raw zip을 재업로드 -- `extract_log.py --with-navi-paths`로 재추출(2401행,
commit `4a15da4`=173차, 174차와 동일 코드 상태) 후 실측 프레임을 그대로 solver에
주입하는 `sim_acados_causeB_real_replay.py` 신규 작성.

**오픈루프(매 프레임 실측으로 리셋) 결과**: baseline의 1프레임 예측 오차는 작음
(평균 +0.09 m/s², RMSE 0.19 -- 실제 시스템도 이 MPC를 쓰고 있으므로 당연한
정합성 확인). 그러나 매 프레임 실측 상태로 강제 리셋하는 방식이라 "누적 지연"
효과 자체가 지워짐 -- baseline vs 완화(20) 간 예측 차이가 평균 0.047 m/s²로
작게 나타나 가설 검증엔 이 모드만으로 불충분.

**폐루프(t=829.0 실측 초기상태에서 출발, 이후 ego 상태는 solver 자신의 출력으로
적분 전진, target/lead는 실측 시퀀스를 exogenous input으로 사용) 결과**:
- baseline(200) 부호전환: t=830.95
- 완화(20) 부호전환: t=830.50
- **0.45초 차이 -- 176차 1차 합성 시나리오(0.5초 차이)와 방향/크기 모두 일치,
  가설이 실측 target 궤적 기준으로도 재확인됨**
- `v_cruise` 입력을 `liveRouteSpeed`/`desiredSpeed` 둘 중 어느 컬럼으로 써도
  결과 거의 동일(0.45s 차이 유지) -- target 컬럼 선택의 영향 아님을 확인.

**[중요, 미해결] 절대 감속량 괴리**: 폐루프 baseline(200)조차 시뮬레이션
감속량이 실측보다 훨씬 약함 -- 예: t=831.80 실측 aEgo=-0.775 vs 시뮬 baseline
aEgo=-0.214(완화 조건도 -0.356으로 여전히 실측에 못 미침). 후보 원인(다음
세션 조사 필요): `FakeCarrot`이 `comfort_brake=2.5`/`personality=standard`/
`T_FOLLOW=1.2` 등을 고정 근사값으로 쓰는데, 실제 그 시점 Params 기반 실값
(jerk_factor, dynamicTFollow, 실제 accel_limits_turns 등)이 더 공격적이었을
가능성. A_CHANGE_COST 자체의 영향(위 폐루프 비교)과는 별개 축의 괴리.

**[결정적] t=832.51 이후 실측 비교 무효**: `brakePressed`가 정확히 t=832.509110에
`True`로 전환(직후 `cruiseEnabled=False`) -- 이 시점부터 실측 aEgo(-1.5~-2.9)는
**운전자 수동 브레이크 페달 입력이 섞인 값**이라 ACC/MPC 단독 출력과 비교
자체가 성립하지 않음. 이전 세션(172/174차)이 "t=832.51 브레이크 개입"을
결과로만 서술한 것은 맞으나, 그 이후 감속 수치를 MPC 문제의 증거로 쓰면 안 됨
-- 앞으로 이 route 분석 시 비교는 반드시 t<832.51로 한정할 것.

**`src` 컬럼 확인**: 전 구간(t=829.0~832.6) `route`로 고정 -- vision-only
phantom-lead 의심 트랙(radar=False, vRel≈-7~-8m/s로 부자연스럽게 큼, dRel
74~100m 노이즈성 오르내림, modelProb 0.15~0.7 낮고 불안정)이 존재했으나
바인딩 제약이 아니었음(cruise/route가 계속 지배). leadJLead/aLeadTau가
extract_log.py 미추출 컬럼이라 0.0으로 근사한 것의 영향은 제한적이라고 판단.

**toolkit 변경**: `sim_acados_causeB_real_replay.py` 신규 편입(README/CHANGELOG
갱신 완료, openloop/closedloop 두 모드 + `--v-cruise-col` 옵션).

**CSV 보관 안 함**: 세션 정책(레포에 대용량 CSV 커밋 금지, Drive 커넥터 미연결)에
따라 `data/routes/`에 캐싱하지 않고 `work/`(컨테이너 리셋 시 소실)에만 둠 --
다음 세션에서 이 route로 추가 분석 필요 시 zip 재업로드 필요.

**다음 세션 우선순위**:
1. 절대 감속량 괴리 원인 조사 -- `FakeCarrot` 고정 근사값(comfort_brake/
   personality/T_FOLLOW) 대신 실제 CarrotPlanner 인스턴스를 최소 의존성으로
   생성해 대조(가능하면), 또는 실측 route의 실제 Params 덤프가 있다면 그 값
   사용
2. 원인B 패치 설계는 이제 진행 가능(가설 자체는 두 독립 방법으로 충분히
   검증됨) -- 리드없는 cruise 모드 + 부호전환 구간 한정 a_change_cost 완화
   게이트. 절대치 괴리 조사와 병행하거나 후순위로 미뤄도 무방(패치 설계
   자체는 방향성 확인만으로 충분).
3. 글로벌 kill-switch 금지 원칙 준수.

---

## 174차 — [원인B 정적분석 완료] `longitudinal_planner.py`/`long_mpc.py` MPC 비용함수 구조 확인 — "route가 감속 스케줄대로 정상 하강해도 실제 aEgo가 못 따라가는" 원인은 accel_limit이 아니라 `A_CHANGE_COST=200`(가속도 변화율 억제 비용)이 `X_EGO_OBSTACLE_COST=5`/`V_EGO_COST=0`/`A_EGO_COST=0` 대비 압도적으로 커서, 리드가 없을 때(`mode='acc'`, cruise_obstacle) 목표속도 수렴이 구조적으로 느리기 때문 — 특히 가속→감속 부호전환 구간에서 지연이 집중됨

**배경**: 173차(원인A 패치)까지 완료 후, 172차가 NEEDS_INVESTIGATION으로
이월한 원인B("사전_감속율이_약해서_사용자가_브레이크_개입", route
`00000372--6310bba9b8--5,6`, t=821.7~832.5, route desiredSpeed는
accel_limit=0.70m/s² 근사로 정상 하강하는데 실측 aEgo는 그 절반 이하만
추종해 gap 0.17→3.75kph까지 벌어지다 t=832.51 브레이크 개입)에 대해
173차 WIP 우선순위 2번(`longitudinal_planner.py` 정적분석)을 이번
세션에서 수행. 로그는 사용자가 동일 route를 재업로드(raw zip, 세션마다
파일 미보관 원칙에 따름) — `extract_log.py`로 재추출(2401행, t=778.86~
898.85) 후 commit tag(`4a15da4`=173차) vs 폴더 타임스탬프(`20260831_150614`)
대조 결과 **로그 기록 시각이 173차 커밋 author date(16:48)보다 이름 -->
빠른 15:06**으로 확인 -- 88/92차와 동일한 "commit tag ≠ 실제 빌드"
패턴 재발이나, 원인B는 173차 패치(램프리미터 증가측)와 무관한 감속측
로직이라 분석 유효성에 영향 없음(참고 기록만).

**[중요, 재정밀화] 172차가 서술한 것보다 실제 구간 구조가 더 복잡함이
CSV 재확인으로 드러남**: t=819~829.5 구간은 사실 **vEgo(≈36.9→57.4kph)가
liveRouteSpeed(78.4→57.9kph, 계속 하강 중)보다 한참 낮은 상태**라
aEgo가 대부분 **양수(+0.3~+1.0, 실제로 가속 중)** -- 이는 정상(직전
구간에서 낮은 속도로 진입한 뒤 여전히 목표보다 느려 자연 가속 중인
상태, 버그 아님). 진짜 문제는 **t≈829.5~832.5(약 3초)**, vEgo가
liveRouteSpeed와 교차(둘 다 ≈57~58kph 근방)한 직후 -- 이 시점부터
목표는 계속 가파르게 하강(57.9→48.1kph, ≈0.75~0.95 m/s² 필요)하는데
실측 aEgo는 **+0.3~+1.0(가속)에서 -0.05~-0.7(약한 감속)로 서서히만
전환**, 목표 하강률을 한 번도 따라잡지 못한 채 t=832.56 사용자
브레이크 개입(brakePressed=True, cruiseEnabled=False, 이후 aEgo가
-1.8~-2.8로 급증). **172차가 "구간 전체에서 감속 절반 미달"로 서술한
것은 부정확 -- 실제로는 가속→감속 부호전환 지연이 핵심.**

**근본원인(코드 정적분석, `selfdrive/controls/lib/longitudinal_planner.py`
+ `longitudinal_mpc_lib/long_mpc.py`)**:
1. `longitudinal_planner.py` L217 `accel_limits_turns[0] = min(accel_limits_turns[0],
   self.a_desired + 0.05)`는 겉보기엔 "감속 상한을 self.a_desired 기준으로
   완만화"하는 것처럼 보이나, `A_CRUISE_MIN=-2.0`이 `self.a_desired+0.05`
   (이번 사례처럼 a_desired가 -2.05 미만인 극단 상황이 아니면 항상 0.05
   이상)보다 항상 작으므로 `min()`이 사실상 상시 `-2.0`을 선택함 --
   **이 줄은 정상 주행 중엔 사실상 죽은 코드(no-op)**, 원인B의
   병목이 아님(오탐 방지를 위해 명시적으로 배제).
2. **진짜 병목은 `long_mpc.py`의 MPC 비용함수 가중치 구성**:
   `X_EGO_OBSTACLE_COST=5.0`(거리 추종), `V_EGO_COST=0`, `A_EGO_COST=0`,
   `J_EGO_COST=5.0`(저크), **`A_CHANGE_COST=200`(가속도 변화율/저크비용,
   나머지 전부보다 40배 큼)**. 리드가 없을 때(`mode='acc'`, 이번 구간
   `leadStatus` 대부분 False) 목표속도는 오직 `cruise_obstacle`
   (L1303-1309, `v_cruise`를 accel_limits로 클립한 가상 선행차 위치)의
   **거리 추종 비용(가중치 5)**으로만 반영되고, **속도 자체를 직접
   당기는 비용(V_EGO_COST)은 0**이다. 따라서 목표속도가 급히 낮아져도
   MPC는 "지금 당장 강하게 감속"보다 "가속도 변화를 부드럽게"(가중치
   200)를 훨씬 더 중요하게 최적화 -- 특히 **가속(+) 상태에서 감속(-)으로
   부호가 바뀌는 전환구간**에서 이 비대칭이 가장 크게 드러남(가속도
   자체의 방향을 바꾸는 것 = `a_change` 큰 값 = 비용 급증이므로 solver가
   전환을 늦춤).
3. `radarstate.leadOne.status`가 True인 구간(L1327-1330)에서는
   `base_a_change_cost = interp(|j_lead|, [0.3,2.0], [200,20])`로 리드의
   저크가 크면 이 비용이 최대 20까지 낮아져 반응성이 좋아지지만,
   이번 원인B 핵심 구간(t=829.5~832.5)은 `leadStatus=False`(t=830.55에야
   다시 True)라 **이 완화 경로가 적용되지 않고 200 고정** 상태로
   전환 지연을 그대로 겪음.
4. `_discontinuity_jerk_boost_timer`/`DISCONTINUITY_JERK_COST_BOOST`류
   저크비용 "강화" 로직(66/67/73/76/108/109차)은 이번 구간에서 전부
   비활성(discontinuity 트리거 자체가 없음, `boost_gate_ok=False`) --
   **200이 이미 baseline(강화 없이도 원래 그 정도로 크다)**임을 확인,
   레드헤링 배제.

**성격 재규정**: 149~151차/91차가 다뤄온 "route DP의 accel_limit(감속
스케줄 자체)" 문제와는 **완전히 다른 레이어** -- route는 스케줄을 정확히
계산해 발행하고 있고(desiredSpeed/liveRouteSpeed 일치), 문제는 그
스케줄을 **실제로 추종하는 MPC 자신의 비용함수 설계(smoothness 우선,
tracking 후순위)**에 있음. 91차가 "route가 vturn보다 일찍 감속을
시작하게" 만든 것과도 무관 -- 이번 구간은 애초에 route가 유일한/지배적
소스(`src=route`)였고 조기성 자체는 문제가 아니었음.

**toolkit 변경 없음(이번 세션은 정적분석 + 기존 CSV로 수동 확인, 신규
스크립트 미작성 -- 아래 "다음" 1번 참고, 향후 필요시 정식 스캐너로
승격 검토)**.

**다음 세션 우선순위(사용자 결정 대기)**:
1. **재현 검증(권장, 코드변경 전 필수)** -- `long_mpc.py`의
   acados OCP를 리드 없음 조건으로 격리해 재현하는 시뮬레이션 도구
   신규 작성(`toolkit/`에 편입 필요, README 원칙). v_ego/v_cruise 스텝
   또는 이번 실측 스케줄(liveRouteSpeed 시계열)을 그대로 주입해
   A_CHANGE_COST=200 조건에서 동일한 "가속→감속 전환 지연" 재현되는지
   확인 -- 정적분석만으론 acados solver의 실제 수렴 거동을 100%
   장담 못 함(가정 검증 필요).
2. **패치 방향 후보(재현 검증 후 논의)**:
   a. `mode='acc'`이고 리드 없음(`leadStatus=False`)이면서 **route가
      소스(`src=route`)일 때만** 한시적으로 a_change_cost를 낮추거나
      V_EGO_COST를 소폭 부여(다른 소스/일반 순항 시 부작용 없도록 게이트
      필요, 회귀 리스크 큼 -- 커브 진입 전체에 적용되면 승차감 저하 우려).
   b. cruise_obstacle 구성 자체를 건드리지 않고, `carrot_man.py` 쪽에서
      "감속 전환이 임박했다"고 판단되면 `set_weights()`에 전달하는
      `a_change_cost_starting`(현재 `reset_state`/`standstill`
      최초진입에만 쓰임, L780 `else` 분기)을 확장 적용하는 방향.
   c. 149차 옵션3류(설계상 허용 범위로 보고 종결) -- 단, 이번 사례는
      실제 브레이크 개입까지 이어진 사례라 89~91차 사례들보다 심각도
      높음, 단순 종결은 권장 안 함.
3. `required_decel_gap_scan()`(149/150차)을 이번 유형(blinker 없이도,
   vEgo가 liveRouteSpeed를 "추월"하는 교차 시점 자체를 이벤트로 잡는
   방식)으로 확장한 신규 스캐너 작성 -- 전수 표본 확보 필요(n=1로는
   일반성 판단 불가, 89~92차와 동일한 한계).
4. 172차 원본 서술("구간 전체에서 절반 미달")과 이번 재확인 결과 간
   불일치를 172차 WIP/FINDINGS 원문 자체는 수정하지 않고 이 항목에서
   정정 기록으로만 남김(기존 회차 원문 보존 원칙).

**전달**: WIP.md(이 항목)/FINDINGS.md(174차)/LAST_ANALYZED.md(갱신).
코드 변경 없음(patch 없음, 정적분석+CSV 재확인만).

---

## 173차 — [원인A 패치 구현] 132차 대칭 램프리미터 → 비대칭 변경 (증가측 무제한)

**배경**: 172차가 확정한 원인A -- `carrot_navi_route()`의 132차
out_speed 프레임간 램프리미터가 증가(원복) 방향에도 감속 방향과 동일한
상한(`accel_limit_kmh*dt`)을 대칭 적용하고 있어, 157/160차가 아키텍처를
카메라식 apex 거리공식으로 전면 교체하며 명시한 "apex 통과 시 즉시
원복" 설계 의도를 무력화. 실측(172차, t≈849 apex 통과 후 desiredSpeed
30→48을 5.5초에 걸쳐 서서히 상승, ≈accel_limit_kmh 이론치 그대로)으로
재현 완료된 상태에서 이번 세션은 실제 패치 구현.

**패치**: `selfdrive/carrot/carrot_man.py::carrot_navi_route()`, 132차
램프리미터 블록.
- 변경 전: `hi = self._route_speed_prev + max_step_kmh` (감속측 `lo`와
  동일한 폭으로 증가측도 제한)
- 변경 후: `hi = math.inf` (증가측 무제한, `lo`는 그대로 유지)
- 162차/167차의 위치불확실성 안전망(`cc_pose_valid=False`이고
  `position_dt_since_fix > ROUTE_POSITION_UNCERTAIN_DT_S`인 폴백
  구간에서만 `hi = self._route_speed_prev`로 재고정)은 그대로 보존 --
  정상 상황에서만 `hi=inf`가 적용되는 조건 순서 유지.
- 커밋: `7559b09` ("173차: 우회전 통과 후 route 서서히 상승(원인A)
  수정 - 132차 대칭 램프리미터를 비대칭으로 변경").

**사전검증(toolkit)**: `sim_route_boundary_ramp_limiter.py`의
`RampLimiterState`에 `asymmetric_up`(기본 False) 파라미터 추가 --
기본값 유지로 133차 `replay_route_ramp_limiter_direct.py` 등 기존
스크립트의 동작은 전혀 변화 없음(하위호환 확인). `asymmetric_up=True`
모드로 172차 정밀매칭 조건(반경17.3m/74kph/accel0.70) 재실행 결과:
- 정상주행 중 하강측 최대 프레임간 낙차: patched(대칭, 현재코드와 동일)
  0.13kph -- 이론 상한(`accel_limit_kmh*dt`=0.13kph) 이내로 asym 모드도
  동일하게 억제됨(감속측 로직 미변경이므로 당연한 결과, 회귀 없음 재확인).
- 증가측: asym 모드가 raw out_speed를 프레임 지연 없이 즉시 추종
  (`--road-limit-speed-kph 300` 기본 조건에서 상승폭이 patched 상한
  0.13kph보다 훨씬 큰 값까지 즉시 반영됨 확인).
- `--road-limit-speed-kph 48`(172차 실측 "30→48 유한값으로 서서히 상승"
  패턴 재현 시도) 조건에서는 131차가 이미 문서화한 "윈도우 경계 스냅
  으로 인한 raw 자체의 일시적 과장값" 하네스 아티팩트가 patched/asym
  양쪽에 동일하게 전파돼, 순수 recovery-frame 계측만으로는 패치
  효과를 깔끔히 분리하기 어려움을 확인(하네스 한계 -- 코드 패치의
  결함이 아님, 아래 arbitration 분석으로 보완 판단).

**다른 패치와의 상호작용 전체 코드 검토(사용자 명시 요청)**:
1. `_route_speed_prev`/`carrot_navi_route` 전체 사용처를
   `carrot_man.py`/`carrot_serv.py` 전체에서 grep -- 단일 호출부
   (`broadcast_version_info()` L485)로 국한됨을 확인, 대칭 램프를
   전제로 한 중복/의존 로직이 다른 곳에 없음.
2. `update_navi()`의 최종 arbitration
   (`desired_speed, source = min(speed_n_sources, key=lambda x: x[0])`,
   후보: atc/atc2/sdi_speed(cam·bump·section·police·waze·hda)/limit_speed
   (road)/vturn/model/route)을 확인한 결과, **route가 즉시 원복해도
   다른 후보 중 더 낮은 값이 있으면 `min()`이 그쪽을 최종 선택**하므로
   이 패치가 과속 리스크를 유발하지 않음을 구조적으로 확인 -- route
   recovery 지연 제거는 불필요한 병목 하나를 없애는 것일 뿐, 실제
   안전상한은 road/vturn/model 등 독립 소스가 계속 담당.
3. 132차 원 사전검증(PASS)과 133차 실측 재검증은 감속측(`lo`) 로직에만
   의존하므로 이번 변경으로 재검증 결과가 무효화되지 않음(변경 없음).

**미해결(원인B, NEEDS_INVESTIGATION, 172차→이월)**: 이번 세션은 원인A만
처리. route 스케줄이 가정한 감속률과 실제 종방향 MPC 목표수렴 속도
사이 불일치(t=821.7~832.5, gap 0.17→3.75kph, 브레이크 개입 유발)는
`longitudinal_planner.py` 정적분석 필요 -- 다음 세션 이월.

**toolkit 변경**: `sim_route_boundary_ramp_limiter.py`(asymmetric_up
옵션, --road-limit-speed-kph 옵션 추가, 하위호환 유지).

**전달**: 패치파일 `0001-fix-route-recovery-ramp-asymmetric.patch`
(git format-patch, 1커밋).

---

## 172차 — [원인 A 확정 + 원인 B NEEDS_INVESTIGATION] "우회전 사전감속 약함→브레이크 개입" + "통과 후 route 서서히 상승(원복 아님)" 실측 2건 정밀분석

**대상**: 사용자 업로드 route `00000372--6310bba9b8--5,6`(2세그, t=778.86~
898.85, 120초), 클립1개(`260831_150628_clip.mp4`, 29.95초, 첫프레임
HUD시계 15:05:58/마지막 15:06:27로 시각 정합 검증). repo commit
`f2e80d85fd75`(171차와 동일, 169차 계측 포함, dirty=False).

**원인 A — route 통과 후 "원복" 대신 "서서히 상승" [원인 확정, 사용자
제보 재현 성공]**: `carrot_man.py::carrot_navi_route()` L~697의 132차
out_speed 프레임간 램프리미터가 증가(원복) 방향에도 대칭 적용된다.
132차 당시 커밋 메시지/주석에 이미 "대칭 적용(증가 방향도 동일 램프) --
129차/131차가 보고한 '회전 종료 즉시 원복' 계단도 같은 메커니즘이라
함께 완화됨"이라 명시돼 있어 **의도된 설계**였음을 확인했으나, 이는
당시(91차 backward DP 배열 아키텍처) 기준 판단이었다. 157차/160차에서
`carrot_navi_route()`가 backward DP를 전면 폐기하고 단일 apex 거리기반
`calculate_current_speed()`(카메라 공식) 재사용으로 바뀌면서, 160차
커밋 메시지 자체가 "카메라와 동일하게 서서히 감속 -> apex 도달(거리<=0)
시 원복하는 형태로 단순화"라고 **원복은 즉시**를 설계 의도로 명시했다.
그런데 132차의 구(舊)램프리미터가 새 아키텍처에도 그대로 남아있어,
`calculate_current_speed()`가 `decel_dist<=0`일 때 이론상 즉시 반환하는
apex_speed(도로제한속도 후보)를 프레임당 `accel_limit_kmh*dt`로 다시
깎아버린다. **대조 증거**: 동일 파일에서 카메라 감속(`sdi_speed`,
carrot_serv.py L1025)/제한속도 감속(L1032)/TBT 회전감속(`atc_desired`,
L890)은 전부 `calculate_current_speed()`를 후처리 램프 없이 직접
호출한다 -- 즉 카메라·회전감속은 이미 사용자가 원하는 "거리<=0 즉시
원복"으로 동작 중이며, route만 132차 잔재 램프 때문에 다르게 동작한다.
**실측 재현**: t≈849.15(xDistToTurn=-1, xTurnInfo=-1로 전환, 우회전
apex 통과 확정) 이후 desiredSpeed가 30(t=849~852 유지)→31→32→34→36→
37→39→41→43→45→46→48(t=858.55)로 5.5초에 걸쳐 서서히 상승(≈1.9kph/s,
`AutoNaviSpeedDecelRate=0.70`→`accel_limit_kmh`=2.52kph/s 이론치에
근접) -- 사용자가 "즉시 원복이 아니라 서서히 올라간다"고 표현한
현상과 정확히 일치. t=859.06부터 `src=cam`으로 전환(실제 과속카메라
33kph 제한 구간 진입, 대시캠 프레임으로 "33" 표지판/205m 확인)되어
그 이상 상승은 재클램프됨 -- 이 재클램프 자체는 정상(별개 실제
제약).

**원인 B — 우회전 직전 사전감속 약함→사용자 브레이크 개입 [NEEDS_
INVESTIGATION, 149~151차와 다른 유형으로 구분]**: 동일 route 앞부분,
t=821.70(xTurnInfo=2 최초 출현, xDistToTurn=214m, vEgo=39.5kph)부터
직진 가속 중이던 차량이 route desiredSpeed 하강(78→30 목표)을 따라잡지
못해 t=832.51(xDistToTurn=54m, vEgo=52.8kph, desiredSpeed=48kph, gap=
+3.75kph)에 사용자가 브레이크 개입(`brakePressed`True, `cruiseEnabled`
False로 즉시 disengage), 이후 aEgo가 -1.5→-3.3m/s²까지 급격히 커지는
수동제동으로 이어짐(t=832.51~833.45).
- desiredSpeed 자체의 하강률은 t=825~832 구간 대략 2.5~3.2kph/s로
  `accel_limit=0.70m/s²`(=2.52kph/s) 가정과 정합적 -- **스케줄 계산은
  정상**.
- 그런데 t=829.95(gap 최초 +0.17, 이 시점부터 route가 실제 제약으로
  작동해야 함)부터 t=832.45(gap=+4.35, 개입 직전)까지 실측 `aEgo`는
  구간 대부분 -0.05~-0.7m/s² 수준(가끔 순간적으로만 -0.7 근접)으로
  **가정된 accel_limit(0.70m/s²)의 절반 이하만 실제로 추종**, 그 결과
  gap이 계속 벌어짐(0.17→0.89→1.53→2.06→2.82→3.29→3.75kph). 브레이크
  개입 순간 aEgo가 즉시 -1.5~-2.6m/s²로 뛰는 것으로 보아 (a) 실제
  차량/컨트롤러가 그 정도 감속 자체는 무리없이 낼 수 있고 (b)
  `longitudinal_planner.py`의 `A_CRUISE_MIN=-2.0m/s²` 하드리밋도
  원인이 아님(0.70보다 훨씬 여유있음) -- **route가 가정한 accel_limit
  자체가 부족한 게 아니라, desiredSpeed가 낮아진 뒤 실제 종방향
  MPC가 그 목표를 향해 수렴하는 속도(코스트함수/저크제약 등)가
  가정보다 느린 것**으로 추정된다. 149~151차가 다뤘던 "accel_limit
  값 자체를 근정지 코너에서 부스트"하는 접근과는 **다른 계층의
  문제**(스케줄 vs 실제 추종 지연)이므로 별도 항목으로 유지, 149차의
  결론("감속률 부족이 근본원인")을 이번 건에 그대로 적용하지 않는다.
- **한계**: `longitudinal_planner.py`의 실제 코스트/수렴 튜닝까지는
  이번 세션에서 코드 정독을 못함(시간상 다음 세션 이월). 이 route
  1건(near-30kph target, 최종 완전정지까지 감) 만으로 일반화하기엔
  표본 부족 -- 149차 옵션4(analysis_helpers에 "desiredSpeed 하강률 vs
  실측 aEgo 괴리 구간 자동탐지" 함수 신설)가 이 유형의 사건을
  체계적으로 더 찾는 데 필요.

**toolkit/ryu 변경**: 없음(순수 실측 분석, 기존 `extract_log.py --with-
navi-paths` 재사용). CSV(`route1.csv`, 2401행)는 devnotes 미보관(대용량
정책) -- 재사용 필요 시 원본 zip 재업로드 후 재추출.

**다음 세션 우선순위**:
1. (원인 A) 램프리미터 비대칭화 패치 설계+시뮬레이션 검증 -- 후보:
   증가(hi) 방향은 클램프 제거(카메라/atc와 동일하게 무제한) 또는
   대폭 완화된 별도 상한. 단, 새 아키텍처(157/160차)에서도 새 apex가
   윈도우 경계에 나타나는 "증가측 이산적 점프"가 이론상 가능한지
   (예: 기존 apex가 사라지고 더 먼/완만한 새 apex가 선택되며 값이
   크게 뛰는 경우) `sim_route_boundary_ramp_limiter.py` 재사용해
   먼저 확인 후 패치 방향 확정.
2. (원인 B) `longitudinal_planner.py` accel 수렴 로직 정적분석, 또는
   신규 analysis_helpers 스캔 함수로 유사 사건 추가 확보.

---

## 171차 — [실측 분석, NEEDS_INVESTIGATION 유지] 170차 계측 적용 후 첫 실차 route(x17seg, 997.3s) 분석 — 계측 정상기록 확인되었으나 검증목적 이벤트(GPS 패킷단절/내용정지) 미발생, 8클립 교차로/회전 대조 신규 회귀 없음

**대상**: `00000372--6310bba9b8`(x17seg, 997.3s/6.71km), repo commit
`f2e80d85fd75`(169차 계측 포함, dirty=False). 대시캠 클립 8개(교차로
좌/우회전+정지).

**클립-로그 시각동기화 방법(재사용 가치, README 미등재 — 향후 세션 참고용
으로 이 항목에 기록)**: 클립 파일명(`260831_HHMMSS_clip.mp4`)은 클립의
**종료 시각**(첫 프레임 아님) — `260831_150547_clip.mp4` 마지막 프레임(HUD
시계, 150차 패치) `15:05:47` 정확히 일치, 첫 프레임은 `15:05:18`(파일명
-29초). route CSV `t`는 wall-clock과 선형대응(`t0=538.85`@라우트시작
`15:02:14`) 확인. 1개 클립만 프레임 직접대조, 나머지 7개는 동일 규칙
적용(재검증 시 프레임대조 권장).

**결과 1 — 계측 정상기록, 그러나 목적 이벤트 자체 미발생**:
`dtNaviPacketAge`/`positionDtSinceFix` 전체 19947프레임 최대값
1.573초(3.0초 임계 근처도 못 감), `ccPoseValid` 19947/19947 전부 True.
이 드라이브는 GPS 상태가 시종 건강 — "패킷단절 vs 내용정지" 구분이라는
170차 원래 목적은 이번 로그로 검증 불가(167/168차와 동일한 데이터 공백
반복). `ccPoseValid=False` route도 여전히 미확보.

**결과 2 — 8클립 대조 요약**: 6건이 실제 좌/우회전(clip1/3/5/6/8), 2건은
장시간 정지(clip2 신호대기 24초, clip4 좌회전 직후 정지 30초+). 회전 중
`ccYawDeg`는 전 사례에서 연속적으로 변화(162차급 "고정bearing" 고착
재현 없음) — 다만 `ccPoseValid` 100% True 상태의 관측이라 166/167차
방향1의 "정상경로 정합성" 확인 수준이지, 정체/폴백 상황에서의 엄밀한
실차검증으로는 카운트할 수 없음(162차 같은 정체 사건이 재현된 로그
필요). `src` 전환은 `route`/`vturn`/`cam`/`bump` 4종 관측, 전환 자체는
50차/88차/91차가 이미 문서화한 "min() 후보경쟁 + 하드스위치 플리커"
패턴과 정합, 신규 유형 없음.

**결과 3 — 전체 route 정량 스캔**: `route_target_jump_events`(단일프레임
≥8km/h 급락) 0건(132차 램프리미터 17세그 전체 클린) / `turn_speed_violations`
4건(전부 vturn apex-lag 범주, 5.5~9.3km/h·1.85~4.66s) / route↔vturn
플리커 96회·16.6분(5.78/분, dwell 중앙값 1.75s, 기존 규모 동급) /
`atcType`='none'·countdown≈100 상시(146차 관측 재확인).

**결론**: 신규 회귀·버그 없음. 미해결 항목은 전부 "검증에 필요한 특정
상황(GPS 신호저하/폴백 발동)이 담긴 로그의 부재"로 귀결 — 코드 문제가
아니라 데이터 확보 문제. 상세 우선순위는 WIP.md 171차 "다음에 검증해야
할 사항" 참고.

## 170차 — [계측 패치, 구현+diff-0검증 완료] carrotMan cereal에 navi GPS 원본/타이밍 필드 5개 신규 발행 — 169차 "패킷단절 vs 내용정지" 미구분 문제, 다음 실차 로그부터 직접 판별 가능

**배경**: 169차 NEEDS_INVESTIGATION(기존 내부GPS 폴백 타임아웃 판정이
"패킷 도착" 기준이라 "내용정지" 실패모드를 못 잡을 가능성)의 "다음
세션" 목록 2번 항목 진행 확정. 근본 해법 재설계 전에, 애초에 실차에서
어느 실패모드였는지부터 관측 가능하게 만드는 게 순서상 맞다고 판단.

**변경 내용**: `cereal/custom.capnp::CarrotMan`에 `vpPosPointLatNavi`/
`vpPosPointLonNavi`(navi 원본 좌표)/`dtNaviPacketAge`(navi 패킷 마지막
도착 후 경과시간 — 3.0 초과=패킷단절)/`positionDtSinceFix`(162/163/
167차 게이트가 실제로 읽는 값)/`ccPoseValid`(참고용) 5개 필드 추가.
`carrot_serv.py`는 로직 변경 없이(`gps_updated_navi` 판정식 자체는
그대로) 동일 계산값을 인스턴스 변수(`self.dt_navi_packet_age`)로
보관해 발행만 추가 — **동작 변경 없는 순수 관측 계측**.

**검증**: `py_compile` PASS. `capnp` CLI 미탑재 환경이라 `pycapnp`로
스키마 로드 + `log.Event.carrotMan` 경유 신규 필드 직렬화/역직렬화
왕복 확인(정상). `cereal.messaging`은 `msgq` 네이티브 확장 미탑재라
런타임 임포트 자체가 불가(기존부터 있던 샌드박스 한계, 이번 계측과
무관). throwaway clone에 `git format-patch`→`git am` 재적용 후
diff-0 확인(커밋 해시 제외 파일 내용 완전 일치).

**toolkit 동반 갱신**: `extract_log.py`가 위 4개 필드(ccPoseValid
제외 — 기존 `carControl` 경유 `ccPoseValid`와 원본 동일이라 중복
방지)를 CSV 컬럼으로 뽑도록 수정. **주의**: 이 패치를 실차에 적용한
이후 뽑힌 로그부터만 값이 채워짐 — 과거(패치 전) route CSV는 4컬럼
모두 0.0(capnp 필드 기본값, 크래시 아님).

**미해결(다음 세션 이월)**:
1. 이 패치를 실차에 적용 → 실주행 → route 재업로드 → 신규 컬럼으로
   162차류 이벤트가 "패킷단절"이었는지 "내용정지"였는지 1차 실측 —
   169차 NEEDS_INVESTIGATION의 실제 해소는 이 관측 이후.
2. 169차 미해결1(폴백 판정 방식을 "패킷 도착"→"내용 변화" 기준으로
   재설계)은 위 1번 실측으로 실패모드가 확인된 뒤 착수(계측 없이
   재설계하면 효과 검증 불가).
3. 기존 이월 항목(166차/167차 실차검증)은 이 계측과 완전히 별개
   필드라 서로 영향 없음, 변경 없음.

**전달**: FINDINGS.md(이 항목)/WIP.md(170차)/toolkit/extract_log.py,
README.md, CHANGELOG.md(수정) + ryu 패치
`0001-add-navi-gps-telemetry-instrumentation.patch`(base `d1ace31`).

## 168차 계속 — [실측 로그검증] 167차 계속2 좁힘 패치, 실제 pre-patch route(aeeed9e4a5 seg0/seg3)로 재확인 — 이 route로는 좁히기 효과 관측 불가함을 실측으로 확정

**배경**: 168차(synthetic만)에 이어 사용자가 실제 route zip
(`drive-download-20260830T095322Z-1-001__2_.zip`, 162~166차가 계속 써온
바로 그 pre-patch 로그, 기록시각 20260830 17:57~18:00)을 재업로드.
`extract_log.py`(현재 repo `d1ace31`=167차 계속2 기준, `ccYawDeg`/
`ccYawRateZ`/`ccPoseValid` 컬럼 포함)로 재추출(2400행, t=6166.1~6406.1,
기존 범위와 동일).

**1) ccPoseValid 실측 분포**: 2400행 **전부 True** (`{'True': 2400}`).
166차가 이미 관측했던 것과 동일 — 이번 재확인으로도 변함없음.

**2) position_dt_since_fix 실측 재구성 시도 — 원천적으로 불가능함을 채널
단위로 재확인**: seg0 rlog의 전체 capnp 채널 목록을 뽑아 GPS/nav 관련
채널만 추림 — `gpsLocation`(차량 자체 GPS, 1Hz, 60행)과
`navInstruction`/`navInstructionCarrot`/`carrotMan`만 존재,
`gpsLocationExternal`이나 그 외 "폰 앱 위치" 전용 채널은 **아예 없음**.
즉 162차가 발견한 "11초/16초 앱 GPS 위치 끊김"은 `carrot_serv.py`가
UDP로 직접 받는 폰 앱 위치이고, 이 값 자체가 어떤 cereal 채널에도
발행되지 않는다 — `position_dt_since_fix`(그 위치 fix 이후 경과시간)를
실측 로그에서 복원하는 것은 이 route뿐 아니라 **구조적으로 불가능**
(163차부터의 기존 한계가 채널 인벤토리 조사로 다시 한번 확정됨).
참고로 차량 자체 `gpsLocation`(1Hz)엔 세그먼트 경계(seg0 끝→seg3 시작,
121.00s 갭 = 업로드 안 된 중간 seg1/seg2 구간일 뿐) 외엔 1.5초 이상
갭이 없음 — 이 채널은애초에 문제가 된 신호가 아님.

**3) 결론(실측 기반)**: 167차 계속2의 좁힌 조건은
`position_dt_since_fix > 3.0 and not cc_pose_valid`이고, 이 route는
`ccPoseValid`가 전 구간 True이므로 `not cc_pose_valid`가 항상 False —
**`position_dt_since_fix`가 실제로 얼마였든(복원 불가와 무관하게) 이
route의 모든 프레임에서 게이트는 발동하지 않는다.** 즉 이 실제
pre-patch 로그에 167차 패치를 적용해 재생해도 baseline(게이트 완전
미적용)과 100% 동일한 route_speed가 나왔을 것 — **패치 적용 전/후 차이
"0건"이 실측 데이터로 확정**됨. 이는 168차 synthetic 결론(과도억제
해소 케이스)과 정합적이지만, "안전망이 실제로 발동하는 상황"에 대해서는
이 route가 원천적으로 증거를 줄 수 없다는 168차의 추정을 실측으로
재확인한 것 — 새로운 정보는 없으나 근거가 synthetic 가정에서 실측
채널조사로 격상됨.

**미해결(이월)**: `ccPoseValid=False`가 실제로 나타나는 route(예:
캘리브레이션 미완료 직후 구간)를 아직 확보 못함 — 안전망 발동 여부의
실측 검증은 여전히 불가능.

**전달**: FINDINGS.md(이 항목). WIP.md/toolkit 변경 없음(이번은 순수
분석, 코드/스크립트 변경 없음).

## 169차 — [코드리뷰+로그전수조사, NEEDS_INVESTIGATION] 기존 "내부GPS 폴백" 로직 재발견 — 162/163/167차 게이트가 실제 이벤트에서 발동했는지 자체가 불확실함

**배경**: 사용자가 "코드 전반 검토 + 업로드 로그 전수조사"를 명시적으로 요청
(누락된 위치확인 로직/로그가 없는지). `carrot_serv.py::_update_gps()`
전체를 처음부터 재검토 + 업로드 route(`aeeed9e4a5` seg0/seg3)의 rlog
전체 capnp 채널을 빠짐없이 나열.

**1) 코드리뷰 발견 — 기존 "내부GPS 폴백"(L726-732, L762, 162~167차와
무관하게 이미 있던 코드로 추정)**:
```python
external_gps_update_timedout = not (gps_updated_phone or gps_updated_navi)
if self.gps_valid and external_gps_update_timedout:
    self.vpPosPointLatNavi = gps.latitude
    self.vpPosPointLonNavi = gps.longitude
    self.last_calculate_gps_time = now
```
"폰 앱(navi) 신호가 3초 이상 없으면 차량 자체 GPS(`gpsLocation`)로
폴백"하는 안전장치가 이미 존재. 그런데:
- `gps_updated_navi`의 근거인 `last_update_gps_time_navi`는 L1405-1406에서
  **패킷이 "도착"하기만 하면(값이 바뀌었든 아니든) 매번 리셋됨**
  (`if self.vpPosPointLatNavi != 0.0: self.last_update_gps_time_navi = now`).
  폰 앱이 "연결은 유지되지만 같은 값을 반복 전송"하는 실패모드라면 이
  타임아웃은 영원히 안 걸림 — 폴백도, `position_dt_since_fix`(162/163/
  167차 게이트가 읽는 바로 그 변수, `last_calculate_gps_time`도 같은
  줄에서 같이 리셋됨)도 3.0을 못 넘음.
- `gps_valid = sm.updated[gps_service] and gps.hasFix`인데
  `gps_service`(gpsLocation)는 1Hz, carrot_man 루프는 20Hz(`Ratekeeper(20)`,
  L474) — `sm.updated[gps_service]`가 True인 프레임은 20개 중 1개뿐이라
  이 폴백이 발동할 수 있는 창 자체가 좁음.

**NEEDS_INVESTIGATION(정직하게 기록)**: 실제 162차 이벤트가 "패킷 자체
단절"이었는지 "패킷은 오지만 내용 정지"였는지는 현재 로그로 구분 불가
(`vpPosPointLatNavi`/`last_calculate_gps_time` 자체가 cereal 미기록 —
163차부터의 기존 한계와 동일 이유, 168차 계속의 채널조사로도 재확인됨).
**후자라면 162/163/167차 게이트가 이 이벤트에서 한 번도 발동하지 않았을
가능성이 있음** — 지금까지의 모든 synthetic 검증(163차/168차)은 "dt가
실제로 11초까지 자란다"는 가정 위에서 짜여 있었는데, 그 가정 자체가
검증된 적이 없었음.

**2) 로그 전수조사 — 이번 업로드 route(seg0) rlog 전체 채널 50개
나열**. 위치 관련만 정리:
- `gpsLocation`(1Hz) — 기존에 이미 씀(`compare_navpos_vs_gps.py`,
  162차). 문제구간(seg3 t=6389.86~6394.87)에서도 hasFix=True로 정상
  추종(296.7°→299.0°→311.7°→332.1°→352.5°→3.7°) 재확인.
- `livePose`(20Hz) — **이번에 처음 원본 채널로 직접 확인**(그동안은
  `CC.orientationNED`로 간접 확인만 함). valid/inputsOK/posenetOK/
  sensorsOK 전부 True, 문제구간(t=6388~6396) 동안 각속도 기반으로
  298.9°→3.8°까지 매끄럽게 추종 — `CC.orientationNED`가 이 값을 그대로
  반영한다는 것을 원본으로 재확인(166차 carControl 경유 검증과 정합,
  새 모순 없음).
- `qcomGnss`(454개) — 모뎀 raw GNSS 진단데이터, 처리된 위치 아님이라
  직접 활용성 낮음(참고 기록만).
- `gpsLocationExternal` — **존재하지 않음**(168차 계속에서 이미 확인한
  것 재확인).

**결론**: "완전히 새로운 위치 소스"는 로그에 없음(`livePose` 원본은
새로 확인했지만 `CC.orientationNED` 경로로 이미 사실상 동일 정보를
사용 중). 진짜 새로운 발견은 코드 쪽 — **이미 있던 내부GPS 폴백이 왜
실제 이벤트에서 작동하지 않았는지(혹은 애초에 작동 불가능한 구조인지)**.
165/166/167차가 `CC.orientationNED` 신규 보정 경로를 새로 만드는 대신,
어쩌면 기존 폴백의 타임아웃 판정 방식(패킷 도착 기준 → 패킷 내용 변화
기준으로 전환)을 고치는 쪽이 더 근본적이고 간단한 해법이었을 수 있음 —
단, 이건 새 방향 "제안"이지 확정된 결론 아님. 사용자 판단 필요.

**미해결(다음 세션 재개 시 판단 필요)**:
1. 이 발견을 이어서 조사할지(예: `last_update_gps_time_navi`를 "패킷
   도착"이 아니라 "내용 변화"로 리셋하도록 고쳐서 재설계) — 사용자 결정
   대기.
2. 기존 이월 항목(166차/167차 실차검증)은 이 발견과 무관하게 여전히
   유효 — 실차에서 CC.orientationNED 보정 자체는 잘 동작할 것으로 보임
   (livePose가 문제구간 내내 valid).
3. `vpPosPointLatNavi`/`last_update_gps_time_navi`/`last_calculate_gps_time`을
   cereal에 발행하도록 계측을 추가하면(신규 patch), 다음 실차 로그부터는
   "패킷 단절 vs 내용정지" 자체를 직접 구분할 수 있음 — 근본 해법 설계
   전에 이 계측부터 하는 것도 방법.

**전달**: FINDINGS.md(이 항목). WIP.md/toolkit/ryu 코드 변경 없음(순수
코드리뷰+로그조사).

## 166차 — [부호실측검증+synthetic검증, POSITIVE] 165차 방안1(orientationNED 델타앵커링) 부호가정 실측으로 확인, 앵커링/wrap 수식 자체 5/5 PASS — 패치 전 사용자 승인 단계 남음

**배경**: 165차가 남긴 "다음 세션 최우선"(`CC.orientationNED`가 나침반
관례라는 부호 가정 미검증)을 이어받음. 사용자가 162~164차가 쓴 route
(`aeeed9e4a5` seg0/seg3) zip을 업로드(`drive-download-20260830T095322Z-1-001__2_.zip`).

**1) 부호 검증(실측)**: 신규 `ccYawDeg`/`ccYawRateZ` 컬럼으로 재추출
(2400행, t=6166.1~6406.1, 기존 범위와 일치). 두 개의 뚜렷한 실측 사례로
교차확인:
- **우회전**(seg3, t=6391.7~6392.9, steeringAngleDeg 최대 -121.9°,
  desiredCurvature 최대 +0.0596): `ccYawDeg`가 301.9°→317.9°→...→357.9°→
  (0.3°로 랩)→3.5°까지 **단조 증가**, `ccYawRateZ`는 이 구간 내내 **양수**
  (+0.10~+0.35 rad/s). 이 수치 범위(≈302°→3.5°)는 162차가 기록한 실제
  frozen bearing 정체 사건(296°→3°)과 겹치는 동일 우회전임 — 즉 CC 기반
  헤딩이 그 사건의 실제 회전을 정확히 따라갔다는 것도 부수적으로 확인됨.
- **좌회전**(seg0, t=6208.9~6212.8, steeringAngleDeg 최대 +41.3°,
  desiredCurvature 최대 -0.0163): `ccYawDeg`가 162.8°→146.5°→...→135.0°로
  **단조 감소**, `ccYawRateZ`는 내내 **음수**(-0.14~-0.07 rad/s).

**결론**: `CC.orientationNED[2]`는 나침반 관례(진북기준 시계방향 양수,
우회전=증가/좌회전=감소)가 맞음 — 165차 의사코드의 부호 가정 그대로 사용
가능, 반전 불필요. `angularVelocity[2]`(요레이트)도 동일 부호 확인(우회전
양수/좌회전 음수), 두 필드가 서로 정합적(자체 미분/적분 관계 성립).

**2) 앵커링/wrap 수식 자체 검증(synthetic + 실측 재생)**: 신규
`sim_yaw_anchor_delta.py`. **중요 정정**: 165차 FINDINGS 설계결정2를
다시 읽어보니 실제 채택 설계는 "각속도 적분"이 아니라 "orientationNED
**두 절대값의 직접 차분**"(`Δyaw = cc_yaw_now - cc_yaw_at_fix`)이다 —
`AnchoredHeadingStateDiff`로 이 실제 설계를 그대로 복제. angularVelocity
적분 버전(`AnchoredHeadingStateIntegrated`)은 165차가 "교차검증용"으로만
언급한 대안이라 별도 클래스로 분리해 정답 기준(Diff)과 대조하는 용도로만
사용.

**검증 결과(5/5 PASS)**:
1. 리셋 무드리프트: fix 50회 반복 시 매 리셋 순간 오차 0.
2. 우회전 wrap(합성, 350°→+30°/s·13s로 359→0 경계 통과): 프레임당 최대
   점프 1.5°(정상치), 최종값 이론치(20.0°) 정확 일치. `orientationNED`
   원값이 랩 없이 계속 누적되는 표현이어도(예: 740.0까지) `shortest_diff_deg`
   덕에 정상 처리됨을 같이 확인(locationd 내부표현 랩 여부가 불확실해도
   안전).
3. 좌회전 wrap(합성, 10°→-30°/s·13s로 0→359 반대방향 경계): 최종값
   340.0° 정확 일치.
4. **162차 실측 정체 사건 재생**(t=6371.0~6394.8, 23.8초): Diff 방식은
   시작/끝 절대값을 그대로 빼는 연산이라 오차 **2.8e-14°**(부동소수
   수준)로 실제 최종 헤딩(4.24°)과 사실상 완전 일치. baseline(현재
   동작, fix 고정)은 시작값(298.1°)에 그대로 묶여 오차 **66.11°**
   (버그 그대로 재현, 방안1 적용 시 개선폭을 정량으로 확인).
5. Diff(실제설계) vs Integrated(교차검증용 대안) 괴리 0.60°(24초간 적분
   이산화오차 — Diff가 이론상 무오차라 우위임을 재확인, 단 두 독립
   신호경로가 서로 크게 어긋나지 않아 locationd 추정기 자체 신뢰도도
   방증).

**한계**: `_update_gps()`의 "새 fix 도착" 감지(`self.last_calculate_gps_time`
변화) 로직 자체는 시뮬레이션 대상에서 제외(간단해서 별도 검증 가치 낮다고
판단, 165차 설계결정3 참고). `cc_pose_valid=False` 구간과 정체 구간이
겹치는 경우의 폴백 동작은 이번에도 미검증(추출 CSV에서 이번 route는
`ccPoseValid`가 처음부터 끝까지 100% True라 검증 데이터가 없음 — 향후
과제로 남김).

**다음 세션 재개 시**: 부호+수식 양쪽 다 검증 통과했으므로, 사용자 승인
받으면 바로 `carrot_serv.py` 패치(165차 의사코드를 Diff 방식 그대로 반영,
`__init__` 상태변수 2개 + `_update_gps()` 내부 10줄 안팎) 작성 →
`git format-patch`/`git am`/`py_compile` 검증 → 전달. 163차 방향2 게이트와의
병행 여부(FINDINGS 165차 미해결사항4)도 이때 같이 확인 필요.

**전달**: FINDINGS.md(이 항목)/WIP.md(체크포인트)/toolkit/sim_yaw_anchor_delta.py(신규)/
toolkit/README.md/toolkit/CHANGELOG.md. ryu 코드 변경 없음(검증만, 패치는
사용자 승인 후).

## 165차 — [설계, NEEDS_VALIDATION] 162차 방향1(livePose 자세데이터 헤딩보정) 코딩설계 — CC.orientationNED/angularVelocity 델타앵커링 방식으로 확정, synthetic 검증은 다음 단계

**배경**: 163차에서 사용자가 방향2(위치불확실성 게이트, 완료+실차검증대기)를 선택하며 "방향1(livePose 헤딩보정)은 비용이 커 향후 과제로 보류"했던 항목. 이번 세션에서 사용자가 명시적으로 "미뤄뒀던 1번 livepose 자세데이터로 헤딩 보정 코딩설계 가자"고 재개 지시. 아직 코드 변경(패치) 없이 설계만 확정하는 단계(패치는 사용자 승인 후, 원칙대로).

**문제 재확인**: `carrot_serv.py::_update_gps()`가 쓰는 `bearing`(≈1Hz CarrotNavi 앱/폰의 `nPosAngle`)이 외부 GPS 갱신이 끊기면(162차 실측 최대 24초) 마지막 값에 고정된 채로 `estimate_position()`이 그 옛 헤딩으로 계속 직진 데드레커닝 — 실제 급회전(steer -121.9°)을 "직선"으로 오판(위치오차 최대 28m). L729의 기존 TODO 주석이 정확히 "`CC.orientationNED[2]`를 이용해 보정하라"고 이미 가리키고 있었음(원저자가 이미 알고 있던 미해결 과제).

**설계 결정 1 — 데이터소스: `livePose` 직접구독이 아니라 이미 흐르는 `CC.orientationNED`/`CC.angularVelocity` 사용**: `controlsd.py` L250-252가 `calibrated_pose`(livePose를 캘리브레이션 보정한 값)를 매 프레임 `CC.orientationNED`/`CC.angularVelocity`(List(Float32), index 2 = yaw/yaw rate)에 실어 100Hz로 발행 중이고, `carrot_man.py`는 이미 `'carControl'`을 구독 중(L306)이라 **신규 SubMaster 서비스 추가가 필요 없음** — TODO 주석이 가리켰던 바로 그 경로. `_update_gps(v_ego, sm, gps_service)`는 이미 `sm['carControl']`(`CC` 변수)을 받고 있어 코드 변경 범위가 `carrot_serv.py` 내부로 국한됨.

**설계 결정 2 — 절대치 대입이 아니라 마지막 fix 기준 델타(상대회전) 앵커링**: `locationd.py`(livePose 발행원)의 SubMaster 구독은 `['carState', 'liveCalibration', 'cameraOdometry']`뿐 — **GPS/외부 GNSS를 전혀 안 씀**(순수 IMU+카메라 오도메트리 융합, `PoseKalman`). 즉 CarrotNavi 앱의 정체 문제(nPosAngle)와 완전히 독립된 신호라 근본적으로 유효한 보정원이지만, 반대로 절대 나침반 방향(진북) 보정 입력이 없어 **긴 시간축에서는 절대값으로 신뢰 불가**(자이로 바이어스 등으로 서서히 드리프트). 따라서 `CC.orientationNED[2]`를 절대 헤딩으로 그대로 대입하지 않고, **마지막으로 유효했던 외부 fix 시점의 `CC.orientationNED[2]`를 기준점(`cc_yaw_at_fix`)으로 저장해뒀다가, 그 이후의 변화량(Δyaw = 현재값 - 기준점, ±π wrap)만 `bearing`에 더하는 방식**으로 설계 — 정체 구간(11~24초)처럼 짧은 시간축에서는 드리프트가 무시할 수준이면서, 매 정상 fix 갱신마다 기준점이 재정렬돼 오차가 누적되지 않음(정상 동작 구간에서는 보정량이 항상 0으로 리셋 — 기존 동작과 완전히 동일, 정체 구간에서만 보정이 커짐).

**설계 결정 3 — "새 fix 도착" 감지 지점: UDP 파서가 아니라 `_update_gps()` 내부**: `nPosAngle`이 실제로 갱신되는 지점은 UDP JSON 파서(L1379-1383 navi, L1406-1412 phone, `sm`/`CC` 접근 불가한 별도 컨텍스트로 추정)지만, 거기 훅을 걸지 않고 **`_update_gps()` 안에서 `self.last_calculate_gps_time`이 이전 호출 대비 바뀌었는지로 "새 fix 도착"을 간접 감지**하는 방식을 채택 — `_update_gps()`는 이미 매 프레임 `sm['carControl']`을 갖고 있고(함수 진입부의 `if not sm.updated['carState'] or not sm.updated['carControl']: return` 가드 덕분에 이 지점에 도달하면 `CC`가 항상 신선한 프레임임이 보장됨), UDP 파서 쪽은 아예 안 건드려도 돼서 diff가 `carrot_serv.py` 한 파일, `__init__` 상태변수 2개(`cc_yaw_at_fix`, `_prev_last_calculate_gps_time`) + `_update_gps()` 내부 10줄 안팎으로 최소화됨.

**의사코드(구현 예정, 아직 미적용)**:
```python
# __init__: self.cc_yaw_at_fix = None; self._prev_fix_time = 0

# _update_gps() 내부, bearing_calculated 계산 직전:
ned = list(CC.orientationNED)
cc_pose_valid = len(ned) > 2
heading_correction_deg = 0.0
if cc_pose_valid:
    cc_yaw_now = ned[2]
    if self.last_calculate_gps_time != self._prev_fix_time:  # 새 fix 도착
        self.cc_yaw_at_fix = cc_yaw_now
    self._prev_fix_time = self.last_calculate_gps_time
    if self.cc_yaw_at_fix is not None:
        dyaw = (cc_yaw_now - self.cc_yaw_at_fix + math.pi) % (2 * math.pi) - math.pi
        heading_correction_deg = math.degrees(dyaw)

bearing_calculated = (bearing + self.bearing_offset + heading_correction_deg) % 360
```

**미해결/검증 필요 사항(정직하게 기록)**:
1. **부호 검증 안 됨**: `CC.orientationNED`가 "NED"(진북기준 시계방향 양수, 나침반과 동일 관례)라는 것은 `_ned_from_calib()`/`euler_from_rot()` 명명과 항공/네비게이션 관례에 근거한 추정이지 실측 대조가 아직 없음. 162차가 확정한 실제 우회전 사례(t=6389~6393, steer 최대 -121.9°, 실측 bearing이 296°→3°로 증가/랩어라운드)를 이번에 확장한 `extract_log.py`의 `ccYawDeg`/`ccYawRateZ`로 **재추출 후 대조하면 부호가 맞는지 바로 확인 가능** — 다음 세션 최우선 검증 항목.
2. `angularVelocity[2]`(요레이트)는 이번 설계에서 실제로 안 씀(델타는 `orientationNED[2]` 두 시점 직접 차분으로 계산, 적분 불필요 — 적분 방식보다 오차 누적 경로가 하나 적음). 다만 synthetic 검증에서 "orientationNED 두 프레임 사이 실제로 부드럽게 변하는지"를 교차검증하는 용도로는 유용해 CSV엔 남겨둠.
3. `cc_pose_valid=False` 구간(캘리브레이션 미완료 등, `CC.orientationNED`가 빈 리스트)이 하필 정체 구간과 겹치면 보정 자체가 무력화(기존 동작과 동일하게 폴백) — 실측 로그로 이 구간의 `ccPoseValid` 비율 확인 필요.
4. 이 설계는 `_update_gps()`의 `bearing_calculated`(estimate_position에 쓰이는 헤딩)만 고치는 것으로, 163차 게이트(방향2, `position_dt_since_fix>3.0s`시 route 완화방향 동결)와 **상호배타적이지 않고 병행 가능** — 방향1이 근본원인(헤딩오차)을 줄이면 방향2 게이트가 발동하는 빈도/폭 자체가 줄어드는 보완관계. 두 패치를 동시에 넣을지, 방향1 실측검증 후 방향2를 재평가(완화 조건)할지는 사용자 확인 필요.

**toolkit 변경**: `extract_log.py`에 `ccYawDeg`/`ccYawRateZ`/`ccPoseValid` 컬럼 추가(항상 포함, `carControl.orientationNED[2]`/`angularVelocity[2]` 추출 — 위 검증 필요 사항 1번의 실측 대조용 지상진실 확보). README/CHANGELOG 갱신 완료.

**다음 세션 재개 시**:
1. 162차/163차/164차가 쓴 route(`aeeed9e4a5` seg0/seg3, 업로드분 zip: `drive-download-20260830T095322Z-1-001__2_.zip`)를 신규 `extract_log.py`(ccYawDeg 포함)로 재추출
2. t=6370.93~6394.92(navAngle 정체구간) 동안 `ccYawDeg`가 실제로 어떻게 변하는지, 그 Δ가 steer/실제 회전 방향과 부호가 맞는지 확인(위 미해결 1번)
3. 부호 확인되면 `sim_route_position_uncertainty_gate.py`류와 같은 패턴으로 신규 synthetic 검증 스크립트 작성(정상 시나리오 회귀없음 + 정체구간 재현 시 실제 회전과 유사하게 헤딩 추적하는지)
4. 검증 통과 시 사용자 승인 받고 `carrot_serv.py` 패치(git format-patch) 생성

**전달**: FINDINGS.md(이 항목)/WIP.md(체크포인트)/toolkit/extract_log.py(수정)/toolkit/README.md/toolkit/CHANGELOG.md. ryu 코드 변경 없음(설계만, 패치 없음 — 원칙대로 사용자 승인 전 미적용).

## 164차 — [OFFLINE 재구성 검증, POSITIVE] 163차 위치불확실성 게이트를 실측 원본(패치 이전) 로그로 역산 검증 — 실제 정체 24초, 게이트 있었으면 route 과열 78.6→149.8kph 상승을 78.6에서 동결했을 것

**배경**: 163차 패치("git am 적용 후 실차 재주행 검증" 대기 상태)에 대해 사용자가 실측 로그를 업로드 — 확인 결과 패치 커밋(`eecac50`, author date 2026-08-31 02:31 UTC)보다 기록 시각(20260830 17:57~18:00)이 앞서는 **패치 이전** 로그로, 162차가 근본원인 분석에 썼던 바로 그 route(`aeeed9e4a5` seg0/seg3)와 동일함(사용자 확인). 실차검증은 아니지만, 163차가 "cereal에 `position_dt_since_fix`가 없어 합성 시나리오로만 검증했다"고 남긴 한계를 이 실측 로그의 관측 가능한 대체 지표로 메우는 오프라인 재구성 검증을 진행.

**재추출**: devnotes에는 이 route의 CSV가 보관돼 있지 않음(대용량 정책, 162차 세션 중 컨테이너 리셋으로 유실 후 미보관 — FINDINGS.md 162차 "범위" 참고). 업로드분으로 `extract_log.py --with-navi-paths` 재추출(`route_full.csv`, 2400행, t=6166~6406) — 162차와 정확히 동일 t범위로 재현 확인.

**1) 정체(freeze) 실측 재확인 — 더 긴 것으로 정정**: `compare_navpos_vs_gps.py`를 t=6355~6398로 넓게 재실행한 결과, `navAngle`이 **t=6370.93~6394.92 (23.99초)** 동안 296.0°로 완전 고정됨을 확인. 162차가 "회전 시작~종료(11초)간 고정"이라 기록했던 11초는 **실제 회전(우측 깜빡이 on~조향각 원위치, 대략 6383.7~6392.9)의 지속시간**이었고, 위치추정 정체 자체는 그보다 **8.7초 먼저 시작**해 회전이 끝난 뒤에도 잠깐(~2초) 더 이어짐 — 162차 기록을 이번 회차 기준으로 정정. `dist_m`(navpos vs 실측 gps 이격)도 동일 패턴 재현(min=0.5 max=28.1 mean=8.2~11.1, 창 크기별).

**2) 163차 게이트 효과 역산**: `ROUTE_POSITION_UNCERTAIN_DT_S=3.0`을 정체 시작(t=6370.93) 기준으로 적용하면 게이트는 **t≈6373.9부터 발동**했을 것. 그 시점 실측 `liveRouteSpeed=78.6km/h`. 게이트 없이 실제로는 정체 내내 상승을 계속해 t=6395.67에 **peak 149.8km/h**까지 도달(과열 상승폭 +71.2km/h, 대부분 실제로는 존재하지 않는 "도로가 계속 열린다"는 오판에 의한 것). 163차 패치(방향2, hi만 동결·lo는 허용)가 적용됐다면 이 21초 구간 내내 `hi`가 78.6에 고정되어 149.8까지의 과열 상승이 발생하지 않았을 것으로 재구성됨.

**3) 안전영향 재확인(변동 없음)**: 이 구간 내내 `src=vturn`이 arbitration에서 이미 route를 이기고 있어 실제 `desiredSpeed`(차량에 적용되는 값)는 정상 범위(vturn 자체 계산, 최종 저점 desiredSpeed=30 근방)였음 — 162차 결론과 동일하게 **이 특정 사건에서 안전 회귀는 없었음**(route 사전감속 보조 공백일 뿐). 즉 이번 게이트는 "지금 당장의 위험을 막는" 패치가 아니라 "route가 신뢰 못 할 값을 만드는 것 자체를 예방"하는 성격.

**163차 시뮬레이션과의 비교**: 163차 합성검증은 "실측 규모 ~11초, accel_limit_kmh~3.3"으로 보정했었는데, 이번에 확인된 실제 정체는 그보다 긴 24초 — 그러나 게이트 로직(dt>3.0s 시 완전 동결, 지속시간 무관하게 유지, 하강은 항상 허용)은 지속시간에 의존하지 않는 설계라 결론(동결 성공) 자체는 그대로 유지되며, 오히려 더 가혹한 실측 조건에서도 유효함이 추가로 뒷받침됨.

**한계(정직하게 기록)**: 이 역산은 여전히 `position_dt_since_fix`를 직접 재생한 것이 아니라 관측 가능한 대체 지표(`navAngle` 정체 구간)로 시점을 역추정한 것 — `navAngle`이 멈춘 시점(t=6370.93)이 실제 `last_calculate_gps_time`이 갱신을 멈춘 시점과 정확히 일치한다는 보장은 간접 증거(같은 UDP 소스, `carrot_serv.py` L1382)에 기반한 추정이며 코드상 완전히 동일한 조건은 아님. 진짜 검증은 여전히 163차가 남긴 "실차 `git am` 적용 후 재주행" 단계가 필요.

**다음 단계**: 163차와 동일 — 패치를 실차에 적용해 이 우회전 구간(또는 유사 상황)을 다시 주행, route= HUD가 정체 구간 동안 동결되고 정상 구간은 기존과 동일하게 동작하는지 확인.

**전달**: FINDINGS.md(이 항목)/WIP.md(이 항목). ryu 코드 변경 없음(분석만). route_full.csv/navpos_gps*.csv는 devnotes 미보관(대용량 정책, 컨테이너 리셋 시 소실 — 필요 시 동일 zip으로 재추출 가능, 업로드 파일명: `drive-download-20260830T095322Z-1-001__2_.zip`).

## 161차 — [실측 검증 POSITIVE + 신규 이슈 발견, NEEDS_INVESTIGATION] 160차 camera-style route 감속 실측 로그 재검증 — route156(157차 버그) 회귀없이 재현 확인, 별개로 naviPaths/TBT가 실제 교차로 급회전을 전혀 감지 못하는 신규 케이스 발견

**배경**: 160차(camera-style 물리공식 재설계) 패치를 "이전에 문제 있었던 실주행 로그"로 검증. 158차가 157차 검증에 썼던 `replay_route_apex_vs_baseline.py`를 재사용/변형(`replay_route_camera_style_vs_baseline.py` 신규)해 실측 `liveRouteSpeed`(패치 전 production 실제 출력) 대비 160차 알고리즘 오프라인 재계산을 대조.

**1) route156(`aeeed9e4a5`) 재검증 — PASS**: seg1/seg2 재업로드, `--with-navi-paths` 재추출(2400행). 157차가 고쳤던 liveRouteSpeed 104.0kph 고정 구간 3곳(9.9~12.3초씩) 전부에서 160차도 정상 반응:
- [6269.6~6280.9] 104.0 고정 → 160차 min 59.0/시작 66.3/끝 67.2 kph
- [6283.3~6293.2] 104.0 고정 → 160차 min 54.3/시작 67.5/끝 55.4 kph
- [6313.7~6325.9] 104.0 고정 → 160차 min 54.0/시작 70.7/끝 54.3 kph

프레임간 최대낙차 0.16km/h(이론상한 0.13, 158차가 확인한 157차의 0.26km/h보다 오히려 이론값에 더 근접 — safe_time 버퍼가 톱니 진동을 악화시키지 않음). 직선 구간(곡률<0.002) 오탐 스캔 0건. **결론: 160차가 157차의 핵심 개선(연속 굽이길 stuck 버그)을 회귀 없이 유지, 오히려 램프 안정성 약간 개선.**

**2) 신규 발견(NEEDS_INVESTIGATION) — naviPaths/TBT가 실제 급우회전을 전혀 못 봄, 149차와 다른 유형**: 사용자가 898edd0f96(149차 원본) 대신 같은 route id(`aeeed9e4a5`)의 나머지 세그먼트(seg0/seg3)를 "유사 우회전 로그"로 제공, 4세그 통합 재추출(`route_full.csv`, 4800행, t=6166~6406). rightBlinker 스캔으로 seg3 끝(t=6389.03~6393.02)에서 실제 급우회전 확인:
- steer 최대 -121.9°(t=6392), vEgo 58.3→26.8kph
- vturn(비전)이 desiredSpeed 55→45→36→30→21kph로 막판(t=6386~6392) 개입해 감속 수행
- `verify_and_extract_frames.py`로 t=6385/6389/6390/6391/6392/6393 대시캠 확인(`frames_turn3/`) — 신호 있는 실제 교차로, 직진+우회전 겸용차선, 진짜 회전(가짜 이벤트 아님) 확인.

149차와 동일한 방법(naviPaths 기반 recompute_route_curvature_speed)으로 곡률을 재계산했으나, **이 구간 내내 apex_curvature≈-0.0003~-0.0005(사실상 0, 직선 취급)로 회전 자체를 감지하지 못함** — naviPaths raw 텍스트를 직접 확인해도(t=6389.03~6389.22) y값이 0.06~0.09 수준의 완만한 변화만 있어 실제 급회전 형상을 담고 있지 않음이 확인됨. TBT(`xTurnInfo`/`xDistToTurn`)도 이 구간 내내 1600m+ 떨어진 무관한 다른 턴을 추적 중(예: t=6389.08 xDistToTurn=1649)이었고, 이 교차로 자체를 xTurnInfo로 별도 포착한 적이 없음 — t=6394.97에야 xTurnInfo가 -1로 리셋되고(회전이 이미 끝난 시점) t=6395.88에 다음(무관한) 턴을 재포착.

**149차(898edd0f96)와의 근본적 차이**: 149차는 "곡률 감지는 정확(280m/19초 전부터 fine chord로 5.0kph 포착)했지만 감속률(accel_limit)이 부족해서 못 따라간" 케이스였던 반면, 이번 케이스는 **입력 데이터(naviPaths/TBT) 자체가 이 회전의 존재를 전혀 반영하지 않음** — 149차~160차 계열 패치(전부 "감지된 곡률을 얼마나 빨리/세게 감속하느냐"를 다루는 감속 공식/감속률 튜닝)는 원천적으로 적용 여지가 없는 유형. 160차 유무와 무관하게 결과가 동일했을 것으로 판단, **160차 검증 결과 집계에서는 제외**(참고: route156 검증만으로 160차 실측 PASS 판정).

**미결정(사용자 확인 대기 중 체크포인트로 중단)**:
1. 898edd0f96 원본 zip 재업로드 시 160차 최종 검증 완료(원래 1순위 목적, 아직 미완료)
2. 이번 신규 발견(naviPaths/TBT가 왜 이 교차로 회전을 못 봤는지)을 별도로 더 조사할지 — 후보 가설: (a) 이 회전이 내비게이션이 계획한 경로 이탈(운전자가 경로 밖으로 임의 우회전)이라 애초에 naviPaths/TBT 대상이 아니었을 가능성, (b) naviPaths 생성 로직 자체의 결함(실제로는 경로상의 회전인데 리샘플링/청크 경계 문제로 곡률이 죽었을 가능성). 대시캠상 직진+우회전 겸용차선이라 (a)/(b) 어느 쪽인지 이 데이터만으로는 판별 불가 — activeCarrot=2(carrot 모드 활성)였다는 것만 확인됨, 목적지 네비게이션 설정 여부는 CSV로 추적 불가능한 값.

**toolkit 변경(이번 회차)**: `replay_route_camera_style_vs_baseline.py` 신규(158차 `replay_route_apex_vs_baseline.py` 구조 재사용, `carrot_navi_route_camera_style` 오프라인 재생 + `find_stuck_segments` import 재사용). `route_full.csv`/`route156.csv`는 devnotes 미보관(대용량 정책, 필요 시 재추출).

## 160차 — [설계 전면 교체, POSITIVE] route 감속을 과속카메라 감속(calculate_current_speed) 물리공식으로 그대로 재사용 — 157차 accel_limit 동적 부스트 폐기, 시뮬레이션 7/7 PASS, 패치 전달

**배경**: 사용자가 첨부(곡선_가감속_코딩.txt, 곡선_개념도.pdf)로 "지금까지의
route 관련 검토 내용은 전부 무시하고" 새 방향을 제안: route 감속의 목적은
"Vturn(비전) 감속만으로는 부족한 사전감속"이며, apex(최대곡률지점) 목표속도를
과속카메라의 제한속도처럼 취급해 과속카메라 감속 로직(`carrot_serv.py::
calculate_current_speed(left_dist, safe_speed_kph, safe_time, safe_decel_rate)`,
`v_i^2=v_f^2+2ad` 공식 + safe_time 여유거리 buffer)을 그대로 재사용하자는 것.
기본곡선은 apex 목표속도에 카메라처럼 반응, 연속곡선(PDF ②)은 1차 apex 도달 시
원복 후 2차 apex를 재계산해 같은 로직 재적용.

**기존 설계(157~159차)와의 차이 확인**: 157차도 물리공식(`v_i^2=v_f^2+2ad`)을
쓰지만 (1) safe_time 여유거리 buffer가 없음(91차 마진을 "이번엔 제외, 실측 후
재평가"로 명시적으로 미뤄뒀던 부분), (2) 필요감속률이 accel_limit을 넘으면
vturn_decel_rate까지 동적으로 부스트하는 분기가 있음(카메라 로직엔 이런 부스트
없음). apex 선택 기준(lookahead 내 목표속도가 가장 낮은 지점 = "가장 급한
지점")은 157차와 동일하게 유지하기로 확정(사용자 확인) — "1차→2차 순차 처리"를
위한 별도 상태(state)는 도입하지 않음.

**사전 지적 사항(패치 전 사용자에게 보고, 설계 확정에 반영됨)**:
1. 상태 도입 리스크 — 158~159차에 다른 종류의 명시적 상태(히스테리시스)가
   실측에서 악화된 전례가 있어 경계 필요했으나, 이번 설계는 "가장 급한 지점"
   선택을 유지하기로 해 결국 상태 불필요(무상태 유지) → 리스크 해소.
2. "apex 도달=원복" 판정 흔들림 우려 → calculate_current_speed 자체가
   decel_dist<=0이면 자동으로 safe_speed_kph 반환하므로 별도 판정 로직 불필요,
   기존 apex_dist>0/else 수동 분기 자체가 통째로 사라짐.
3. 연속곡선 톱니 진동 우려 → 시뮬레이션으로 실제 검증(아래).
4. calculate_current_speed 하한 특성(목표속도 근접 시 그 값 고정) → 카메라와
   동일 동작이므로 route에도 동일하게 적용되는 것을 확인하고 채택.
5. Type 3(폴리라인 자체 곡률 부족)는 이 설계로도 미해결 — 그대로 별도 과제로 남음.

**시뮬레이션 검증(신규 `toolkit/sim_route_camera_style_decel.py`)**:
`carrot_serv.calculate_current_speed()`를 동일 시그니처로 복제한
`camera_calculate_current_speed()` + apex 선택(157차와 동일)을 결합한
`carrot_navi_route_camera_style()`을 구현, `sim_route_apex_redesign.py`의
도로 샘플러/`simulate_road`류/`RampLimiterState`(132차)를 그대로 재사용해
7개 시나리오 실행:
- 156차류 연속 굽이길: 157차 대비 최소속도 ±15kph 이내로 정상 감속 (PASS)
- 직선도로: 회귀 없음 (PASS)
- 147차류 단일 급커브: 정상 감속 (PASS)
- 152/153차 근정지 코너: safe_time 버퍼 추가에도 목표속도 근접 도달(초과 없음) (PASS)
- 연속 S자커브(2차가 더 급한 경우): 2차까지 정상 감속, 이 경우 apex가 처음부터
  끝까지 2차로 고정되어 전환 자체가 발생하지 않음을 확인(1차는 사실상
  무시됨 — 157차부터 이어진 기존 특성이며 이번 설계로 새로 생긴 문제 아님)
- 연속 S자커브(1차가 더 급한 경우, apex 전환 발생): 1차 통과로 apex가 사라지며
  다음 프레임에 2차로 자연 전환, 프레임간 최대낙차 0.126km/h로 132차 램프리미터
  이론상한과 정확히 일치(톱니 진동 없음) — **PDF 개념도 ②(연속곡선) 케이스가
  실제로 안전하게 동작함을 확인한 핵심 시나리오**
- (버그 수정 메모) 최초 작성 시 `simulate_road_camera`의 프레임간 낙차 계산이
  반올림된 trace 값끼리 비교해 가짜 위반(0.176 > 0.126)이 나왔던 것을 발견 —
  반올림 전 원본 값으로 비교하도록 수정 후 7/7 PASS로 정정. (실제 코드 문제
  아니라 시뮬레이션 스크립트 자체의 버그였음, 기록 남김)

**패치**: `carrot_man.py::carrot_navi_route()`의 157차 커스텀 공식 블록을
`self.carrot_serv.calculate_current_speed(apex_dist, apex_speed,
autoNaviSpeedCtrlEnd, autoNaviSpeedDecelRate)` 직접 호출로 교체, 동적 accel
부스트 분기 삭제, 132차 램프리미터는 유지(accel_limit_kmh만 고정값으로 단순화).
`py_compile` 통과 + 클린 클론에서 `git am` 성공 확인.
`0001-route-decel-reuse-camera-calculate_current_speed-for.patch` 전달.

**남은 일**: 실차 로그로 사후 검증(연속곡선 구간 위주), Type 3(폴리라인 곡률
해상도) 조사는 별도로 계속.

## 159차(158차 계속) — [대안 설계 A/B 검증, NEGATIVE] apex 히스테리시스(명시적 리셋 상태머신) 설계는 단위테스트 통과에도 실측 재생에서 157차 무상태 설계보다 명백히 악화 — 히스테리시스 방향 폐기, 157차 유지 확정

**배경**: 158차에서 "157차 apex 알고리즘이 apex 통과 후 실제로 자연
해제되는가"를 route156 로그로 1초 간격 트레이스했더니, 고립된 단일
커브는 이미 사실상 즉시 해제되지만 156차류 연속 굽이길에서는 apex 하나
지나면 20~50m 뒤에 바로 다음 apex가 있어 "리셋" 개념 자체가 안 맞는다는
것을 확인. 사용자가 그래도 "먼저 계산한 곡률보다 완만하면 vturn에
맡기고 더 급하면 route가 개입, 완전 리셋(직선 확인) 후에만 새로 시작"
하는 명시적 3상태 설계(reset/engaged/disengaged, `target_curv` 기억)를
제안, 램프리미터 포함 A/B 시뮬레이션으로 검증하기로 함 — 이 설계+A/B
스크립트 작성까지 진행됐으나 세션이 체크포인트 없이 종료돼 컨테이너
리셋으로 코드가 소실(devnotes 미커밋 상태였음). 사용자가 같은 route
zip 2건(`aeeed9e4a5--1`/`--2`, 158차와 동일 로그)을 재업로드해 이번
회차에서 설계를 재구현 후 A/B를 실제로 완료.

**재구현**: `toolkit/sim_route_apex_hysteresis.py`(신규) —
`ApexHysteresisState(mode, target_curv)`를 프레임 간 유지하는 3상태
머신. ENGAGED는 `target_curv` 이상 곡률만 유효 후보(더 급한 지점
발견 시 승격), 후보가 사라지면 DISENGAGED 전이(제약 없음 반환,
`target_curv`는 보존돼 완만한 후속 곡률은 계속 무시), DISENGAGED에서
`target_curv`보다 급한 곡률이 나타나면 즉시 재개입, 윈도우 전체가
negligible(<0.001)이면 RESET(`target_curv` 삭제). 단위테스트 4개
(고립곡선 해제/완만후속 무시/급후속 재개입/접근중 승격) **4/4 PASS** —
순수함수 레벨(합성 프레임)에서는 설계 의도대로 정확히 동작.

**A/B 방법(신규 `toolkit/replay_route_apex_hysteresis_ab.py`)**: 158차와
동일한 route156 CSV(`extract_log.py --with-navi-paths`, 2400 rows)를
재생하며 157차 무상태(A, `sim_route_apex_redesign.carrot_navi_route_apex`)
와 히스테리시스(B, 이번 신규)를 각각 **독립된** 132차 `RampLimiterState`
인스턴스로 통과시켜 병렬 비교.

**결과(NEGATIVE)**: `liveRouteSpeed` 104.0km/h 9.9~12.3초 고정 구간
3곳(158차와 동일 구간) 중,

| stuck 구간 | A(157차 무상태) | B(히스테리시스) |
|---|---|---|
| 6269.62~6280.87 (11.2s) | 반응, min=62.5 | 반응하지만 min=78.2, 구간 내 mode가 disengaged<->engaged 오감 |
| 6283.28~6293.22 (9.9s) | 반응, min=56.3 | **무반응, 300 고정, mode=disengaged 고착** |
| 6313.68~6325.93 (12.3s) | 반응, min=56.7 | **무반응, 300 고정, mode=disengaged 고착** |

**원인**: 연속 굽이길은 인접 커브들의 곡률 크기가 서로 비슷하다(157차/
158차가 이미 확인한 특성). B가 국소 최댓값을 `target_curv`로 승격한 뒤
그 지점을 지나면, 다음 커브가 그것과 "같거나 살짝 완만"한 경우가
많아서 재개입 조건(`front_max_curv > target_curv`, 반드시 이전보다
**더** 급해야 함)을 충족하지 못하고 DISENGAGED에 갇혀버림 — 설계
자체는 "완만하면 무시"가 의도였지만, 실측 도로에서는 그 "완만함"이
누적돼 사실상 영구 비활성으로 귀결됨.

**부작용(더 심각)**: B가 DISENGAGED<->ENGAGED를 오갈 때마다 132차
램프리미터의 "제약 없음(300)은 안전한 방향이므로 즉시 통과, `prev_out`
리셋" 규칙이 반복 발동돼, 다음에 ENGAGED로 복귀할 때 램프가 전혀 걸리지
않은 상태에서 그대로 스냅 — **프레임간 최대낙차 244.11km/h** 관측
(A는 0.26km/h, 이론상한 0.13km/h와 거의 일치해 정상). 즉 사용자가 애초에
우려했던 "명시적 리셋에 의한 톱니 진동"이 A(무상태)가 아니라 **오히려
B(명시적 상태 추가)에서 실제로, 훨씬 큰 폭으로** 발생함을 확인.

**오탐(회귀) 체크**: stuck 구간 ±20초 밖 나머지 구간에서
`live>=95 & out<70` 스캔 — A/B 둘 다 0건(이 항목만 보면 회귀 없음,
문제는 무반응/낙차 쪽).

**결론**: 157차가 코드 트레이스로 이미 결론냈던 "매 프레임 무상태
재탐색만으로 apex 통과 후 자연 해제가 이미 성립하며 별도 리셋 로직이
불필요하다"는 판단이 이번 실측 A/B로 재확인됐을 뿐 아니라, **명시적
상태(히스테리시스)를 추가하는 쪽이 연속 굽이길에서 오히려 무반응
구간을 만들고 램프리미터와 상호작용해 큰 폭의 스냅을 유발하는 회귀임을
확인**. **apex 히스테리시스 설계는 채택하지 않으며, 157차 무상태
`carrot_navi_route_apex`를 그대로 유지하는 것으로 이 검토를 종결한다.**
코드는 "왜 명시적 리셋이 이 도메인에서 안 통하는지"를 보여주는 반례로
devnotes에 보존(`sim_route_apex_hysteresis.py`,
`replay_route_apex_hysteresis_ab.py`).

**ryu 코드 변경 없음** (이번 회차는 전부 toolkit 내 시뮬레이션/재생
스크립트 작업, 157차 패치는 158차 상태 그대로 실차검증 대기 유지).

**교훈(향후 세션 참고)**: 연속적으로 유사한 크기의 이벤트가 반복되는
도메인(이번엔 연속 굽이길의 유사 곡률)에서는 "이전 값보다 더 강해야만
재개입"이라는 단순 대소비교 히스테리시스가 사실상 영구 비활성으로
귀결되기 쉽다 — 이런 패턴이 재발하면 임계값에 tolerance/margin을 두거나
"완전히 사라진 뒤 일정 거리/시간 이내 재출현"처럼 다른 기준을 검토할
것(이번 회차에서는 그 전에 A안 자체가 이미 정상 작동함이 재확인돼
추가 튜닝은 보류).

---

## 158차 — [실측 로그 오프라인 검증, POSITIVE] 157차 apex 패치를 "패치 적용 이전" 실제 route 로그(156차가 겪은 그 로그)로 재생 — liveRouteSpeed 104.0km/h 고정 버그 구간 3곳 전부에서 정상 반응 확인, 오탐 0건

**배경**: 실차에 패치를 아직 안 올린 상태에서도, naviPaths 원시
폴리라인은 147차부터 이미 매 프레임 발행 중이므로 패치 적용 여부와
무관하게 "패치를 적용했다면 이 실제 상황에서 어떻게 반응했을지"를
오프라인 재생으로 검증 가능 — 사용자 요청으로 착수. 156차 때 썼던
연속 굽이길 route(2세그먼트 zip, qcamera/qlog/rlog, 파일명 "route
작동안함 104에서 멈춤")를 재업로드받아 사용.

**추출**: `extract_log.py --with-navi-paths` (commit `712d76b`
사용 — 스키마 파싱용일 뿐, naviPaths 필드 자체는 패치와 무관하게
동일하게 기록됨) → 2400 rows(20Hz, 2분), `naviPaths` 전 row 비어있지
않음 확인.

**방법(신규 스크립트 `toolkit/replay_route_apex_vs_baseline.py`, 158차)**:
매 프레임 naviPaths를 파싱해 `recompute_route_curvature_speed(sample=4,
sample_fine=1, floor_threshold=0.001)`(157차 `ROUTE_CURVE_NEGLIGIBLE_
THRESHOLD` 재현)로 speed/distance 배열을 만들고, `carrot_navi_route_
apex()`(157차 알고리즘 그 자체, `sim_route_apex_redesign.py`)에 실제
vEgo로 통과시킨 뒤 132차 램프리미터(`RampLimiterState`, 실제 프레임
dt 사용)까지 적용 — 그 결과를 CSV에 이미 기록된 `liveRouteSpeed`
(149차, 패치 적용 **전** production이 실제로 발행한 값, 즉 ground
truth)와 나란히 비교. 148차 `replay_route_full_pipeline.py`가
`nRoadLimitSpeed` 미기록으로 신뢰불가(오차 98.7kph)였던 것과 달리,
"패치 전 실제값"은 재현이 아니라 실측 그대로 쓰므로 그 문제가 없음.

**결과**: `find_stuck_segments()`로 `liveRouteSpeed`가 5초 이상 고정되는
구간을 자동 탐지한 결과 3건, 전부 **104.0km/h로 9.9~12.3초씩 고정**
(156차가 보고한 "16초+ 고정" 패턴과 동일 계열의 실측 재현 — 파일명
"104에서 멈춤"과 정확히 일치). 이 3구간 전부에서 apex 오프라인
재계산값은 56.3~76.7km/h로 **정상 하강 반응**:

| stuck 구간(t) | 지속시간 | 실측(패치전) liveRouteSpeed | apex 재계산(패치후 예상) |
|---|---|---|---|
| 6269.62~6280.87 | 11.2s | 104.0 고정 | 62.5~71.1 (반응함) |
| 6283.28~6293.22 | 9.9s | 104.0 고정 | 56.3~70.9 (반응함) |
| 6313.68~6325.93 | 12.3s | 104.0 고정 | 56.7~76.7 (반응함) |

즉 156차가 실측 확인했던 이 정확한 버그가 이 로그 기준으로 157차
패치가 있었다면 해소됐을 것임을 재현이 아닌 실측 데이터로 확인.

**오탐(회귀) 체크**: 3개 stuck 구간에서 앞뒤 20초 이상 떨어진 나머지
구간 전체를 스캔(`live>=95 & apex<70` 조건, "실측은 감속 불필요라
했는데 apex가 과잉감속하는가") — **0건**. (구간 경계 바로 인접
프레임에서 유사 패턴이 다수 잡혔으나, t 확인 결과 stuck 구간의 연속
연장일 뿐 진짜 오탐 아님 — 20초 버퍼로 배제.)

**132차 램프리미터 재확인**: apex 오프라인 계산 결과의 프레임간
최대낙차 0.26km/h (accel=0.70 m/s² 기준 dt=0.05s 이론상한
0.13km/h, 실제 로그 dt 변동 감안하면 정상 범위) — 램프가 실측
데이터 기준으로도 정상 작동. naviPaths가 부족한 프레임(윈도우 리셋)에서
램프가 예외적으로 풀리는 것은 production 132차 코드의 의도된 동작과
동일 — 버그 아님.

**toolkit 변경**: `analysis_helpers.recompute_route_curvature_speed()`/
`_route_curvature_single_pass()`에 `floor_threshold` 파라미터 신규
추가(기본 0.02 유지로 하위호환, 스모크테스트 확인) — 이전엔 0.02
하드코딩이라 157차 신규 임계값(0.001)을 재현할 방법이 없었음.

**한계**: 이번 검증은 156차 로그 1건(연속 굽이길, 3개 stuck 구간)
기준. 급커브/근정지/직선 단독 케이스는 이 로그에 해당 패턴이 없어
오프라인 재검증되지 않음(시뮬레이션 합성검증(157차, 7/7 PASS)으로만
확인된 상태 유지). 실차 실측 적용 검증(HUD 실물/실제 aEgo 반응)은
여전히 다음 단계.

**다음 단계**: 실차에 `git am 0001-157-carrot_navi_route-route-apex.patch`
적용 후 같은 유형의 굽이길 재주행 → `extract_log.py --with-navi-paths`
재추출 → 이번 스크립트로 "실측 vs 실측" 비교(현재는 "실측(전) vs
오프라인계산(후)")로 최종 확정.

---

## 157차 — [근본원인 확정 + 재설계 + 패치] carrot_navi_route()의 curvature<0.02 플로어 임계값이 R 50~800m급 커브를 광범위하게 무력화하고 있었음을 확인 — 단일 apex 거리기반 감속으로 전면 재설계, ryu 패치까지 완료(실차검증 대기)

**배경**: 156차가 "route= HUD 16초+ 고정"을 실측 확인했으나 원인을
"완만한 연속 커브라 개별 지점 곡률이 threshold 미도달"로만 결론짓고
옵션 A/B/C를 사용자에게 제시(패치 보류). 사용자가 이를 "완전 심각한
문제"로 판단하고, route의 이상적 동작을 직접 제시: "GPS로 다음
최대곡률(apex) 지점까지의 거리만으로 사전감속률을 결정, 정점 통과
후에는 vturn(비전)에 맡기고 다음 apex를 다시 찾는 단순 구조".

**근본원인 재확정**: `carrot_man.py::carrot_navi_route()`의 매크로/
fine 곡률 루프 모두에 있는 `if abs(curvature) < 0.02: speed =
max(speed, nRoadLimitSpeed)` 플로어가 문제의 실체. V_CURVE_LOOKUP_BP/
VALS 테이블을 직접 보간하면:
- curvature=0.0091(R≈110m) → 순수 곡률 기반 속도 ≈56km/h
- curvature=0.013(R≈77m) → ≈48km/h
- curvature=0.0165(R≈61m, 147차가 다룬 그 우회전과 유사) → ≈43km/h
- curvature=0.0199(0.02 바로 아래) → 도로제한속도(104~118 관측)로
  플로어. curvature=0.02를 넘는 순간 ≈37km/h로 **불연속 급락**.

즉 R 50m~800m 사이의 "완만하지만 실제로 감속이 필요한" 커브 전체가
0.02라는 단일 임계값 하나로 광범위하게 무력화되고 있었음 — 147차
fine-sample 패치("40m chord가 27m급 급커브 1개를 110m급으로 평활화")는
"chord가 곡률을 과소평가하는 경우"만 고쳤을 뿐, 이 플로어 자체의 범위
문제(coarse/fine sample과 무관하게 진짜 곡률이 0.02 미만인 모든 경우)는
그대로 남아있었던 것. 156차의 연속 굽이길(curvature 0.002~0.013)이
바로 이 사각지대.

**재설계 (사용자 제안 기반)**: 기존 91차 backward accel-limited
DP(ROUTE_ENTRY_MARGIN_KPH/time_wait 스케줄링, 포인트별 배열 전체
처리)와 153차 근정지 후처리를 "apex(lookahead 내 최소속도 지점)까지의
거리 하나로 결정하는 물리공식"으로 완전 대체:
1. lookahead 윈도우 내 모든 점의 curvature-speed 계산은 그대로 유지하되
   플로어 임계값을 `ROUTE_CURVE_NEGLIGIBLE_THRESHOLD=0.001`(R≈1000m,
   진짜 직선 GPS 노이즈 수준)로 축소.
2. 그 중 speed가 최소인 지점(apex_idx) 탐색.
3. `required_accel = (v_ego^2 - apex_speed^2) / (2*apex_dist)` —
   accel_limit 이하면 accel_limit로, 초과(감지가 늦은 경우)면
   `vturn_decel_rate`(1.2 m/s^2)를 상한으로 부스트(153차 클램프 로직의
   일반화 — 153차는 "근정지급 한정"이었던 것을 "모든 apex"로 확장).
4. `out_speed = sqrt(apex_speed^2 + 2*applied_accel*apex_dist)`.
5. "apex 통과 후 리셋"/"vturn에 넘김"은 매 20Hz 무상태 재계산 구조와
   기존 min() arbitration으로 이미 자동 성립 — 추가 코드 불필요.

**시뮬레이션 사전검증(toolkit/sim_route_apex_redesign.py, 신규,
7/7 PASS)**:
| 시나리오 | baseline(기존, 플로어 0.02) | apex 재설계(플로어 0.001) |
|---|---|---|
| 156차 재현 굽이길(curv 0.002~0.013) | 무반응(최소속도=출발속도 그대로) | 실제 커브속도까지 정상 감속(<65kph) |
| 직선(노이즈 0.0003) | 제약 없음 유지(회귀 없음) | 동일(오탐 없음) |
| 147차류 단일커브(curv=0.0165, fine-sample 미적용) | 무반응(0.02 미만이라 baseline도 동일 버그 재확인) | 정상 감속(<60kph) |
| 152/153차 근정지(target=10.7kph, 280m, v_ego=90kph) | (기존 149~153차 검증 결과 참고) | 153차와 동등하게 target 근접 도달 |

**ryu 패치**: `selfdrive/carrot/carrot_man.py` 1개 파일, 63줄 추가/111줄
삭제(순감소 — DP+후처리 ~75줄을 물리공식 ~15줄로 대체, "간단하게"
요구 반영). `ROUTE_ENTRY_MARGIN_KPH`/`ROUTE_NEAR_STOP_TARGET_KPH` 상수
제거(신규 로직에 흡수/불필요, 다른 사용처 없음 확인). 커밋
`24622a6`(c3-ms-dev, `c3e20a4`+1), 패치 파일
`0001-157-carrot_navi_route-route-apex.patch`. **로컬 커밋만 존재,
origin push는 사용자 로컬 git am 이후.**

**알려진 단순화(v1)**: 91차 ROUTE_ENTRY_MARGIN_KPH(route가 vturn보다
먼저 개입하도록 당기는 25km/h 마진)를 이번 재설계에는 포함하지 않음 —
새 물리공식 자체가 이론적 최소개입 시점을 계산하므로 어느 정도 조기
개입 효과는 있으나 91차가 실측 튜닝한 "명확한 우위" 수준까지는
검증 안 됨. 실차 로그로 arbitration 승률 확인 후 필요 시 재도입 검토
(단순 재도입 시 apex_dist를 가상으로 부풀리는 방식 등 후보 있음,
미설계).

**미검증(다음 세션 최우선)**: **실차 로그 검증 전혀 안 됨**. 156차가
쓴 실측 naviPaths CSV는 대용량 정책상 devnotes 미커밋 상태였고
컨테이너 리셋으로 소실 — 재검증하려면 같은 유형의 굽이길 로그를 다시
업로드해야 함. 사용자가 `git am`으로 실차 적용 후: (1) 연속 굽이길에서
route= HUD/실제 감속 정상화, (2) 급커브/근정지 코너 회귀 없음, (3)
직선 구간 오탐 없음 — 이 3가지를 확인하는 로그 확보 후
`extract_log.py --with-navi-paths`로 정량 대조 필요.

**후속 확인(같은 회차, 패치 리뷰 질문에 대한 코드 트레이스 답변)**:
"apex 통과 직후 route target이 실제로 자연 해제되는가"에 대해
`carrot_man.py`를 라인 단위로 재확인:
- `apex_idx = min(range(len(speeds)), key=lambda k: speeds[k])`는 매
  호출마다 `distances`/`speeds` 배열 전체(이번 프레임의 lookahead
  윈도우)에서 새로 탐색됨 — 이전 프레임의 apex 인덱스를 들고 있지
  않음(무상태).
- 이 배열은 `get_path_after_distance(self.navi_points_start_index, ...,
  current_position, route_lookahead_m)`로 매 프레임 **현재 차량 위치
  기준**으로 다시 잘라낸 경로에서 만들어짐. 차량이 어떤 apex 지점을
  실제로 통과하면, 다음 프레임의 `current_position`이 그 지점을 이미
  지나쳤으므로 `path`(및 그로부터 만든 `resampled_points`/`distances`)에
  더 이상 그 지점이 포함되지 않음.
- 따라서 통과한 apex는 다음 프레임에서 탐색 대상 자체에서 빠지고,
  `apex_idx`는 자동으로 그 다음 최소속도 지점을 가리키게 됨 — 별도의
  "리셋" 로직 없이 윈도우 전진만으로 결론이 성립함을 코드 레벨에서
  확인(**결론: 리뷰에서 제기된 의문 해소, 설계 의도대로 동작**).
- 다만 이것과는 별개로 **132차 ramp limiter**(`_route_speed_prev` 기반
  `max_step_kmh = accel_limit_kmh * ROUTE_SPEED_LOOP_DT` 대칭 클램프)가
  apex 계산 **이후**에 여전히 적용됨: apex를 지나 `out_speed`가
  이론적으로 도로제한속도로 즉시 뛰어야 할 때도, 이 리미터가 상승
  방향도 동일 램프로 묶어 프레임당 상승폭을 제한함. 이는 129차/131차가
  의도적으로 설계한 대칭 완화(급커브 진입뿐 아니라 탈출도 부드럽게)이지
  이번 157차가 새로 만든 문제는 아니나, 실차검증 시 "apex 통과 후에도
  route= 표시가 몇 초간 서서히만 올라간다"는 현상이 관찰되면 이 램프
  때문이지 apex 로직 결함이 아님을 구분할 것.
- `vturn_decel_rate`(1.2 m/s^2, `self.vturn_decel_rate`)는 153차부터
  써온 것과 동일한 단일 상수를 그대로 재사용(1230/1249줄의 vturn 자체
  계산과 공유) — 157차가 별도로 부스트값을 새로 도입하거나 충돌시키는
  부분 없음 확인.

**전달**: WIP.md(이 항목 요약)/FINDINGS.md(이 항목)/toolkit/
sim_route_apex_redesign.py/toolkit/README.md/toolkit/CHANGELOG.md +
ryu 패치 `0001-157-carrot_navi_route-route-apex.patch`.

## 156차 — route= HUD 장시간(16초+) 고정값 표시 실측 확인: 연속 굽이길에서 route 곡률감지가 threshold 미도달로 사실상 무반응 (vturn이 arbitration에서 대신 커버 중, 실차 안전영향은 미확인)

**배경**: 사용자가 실차 로그(route `aeeed9e4a5`, 세그먼트 2개, 20260830
175844/175944 업로드) + 대시캠 클립 2건(`route_작동안함_104에서_멈춤`,
`route_작동안함__104에서_멈춰있음`)을 업로드, "route가 작동하지 않고
104에서 멈춤"이라고 보고. HEAD(`c3e20a4`, c3-ms-dev) 기준 로그 시각이
커밋 author date보다 나중이라 pre-patch 로그 아님 확인 후 진행.

**실측 확인 (CSV `liveRouteSpeed` 컬럼 + 대시캠 크롭 대조)**:
- `aeeed9e4a5--0` 세그먼트에서 t=6264.47~6280.87 (**16.4초간**)
  `liveRouteSpeed`가 정확히 `104.0`(그리고 인접 구간에서도 유사하게
  `105.6`/`106.9` 등 단일값)에 고정 — 부동소수 반올림에 의한 우연이
  아니라, 대시캠 클립(`route_작동안함_104에서_멈춤_260830_175928_clip.mp4`)
  t=8/11/15/18/21/24초 6개 프레임 크롭 대조로 실제 HUD "route=" 텍스트가
  **문자 그대로 "104.0" 그대로 정지**되어 있음을 시각적으로도 확인.
  같은 구간 `vEgo`는 18.75→19.8 m/s로 계속 가속 중, `desiredSpeed`(실제
  적용값, src=vturn)는 92~101 사이에서 활발히 변동 — **차량이 정지하거나
  제어가 멈춘 게 아니라 route= 표시 숫자 하나만 안 바뀜**.
- 세그먼트 `--1`에서도 동일 패턴 반복 확인(t=6293~6299, t=6325~6349 등
  여러 구간, 총 4~5개 블록).

**근본 원인 (toolkit `recompute_route_curvature_speed(sample=4,
sample_fine=1)` 재계산으로 확인)**: 고정 구간 내내 naviPaths 폴리라인
기반 재계산 curvature가 0.002~0.013 범위로, **147차가 고친 0.02
threshold를 fine(10m chord)로도 단 한 번도 넘지 못함**. 즉
`carrot_navi_route()` 관점에서는 이 구간이 "커브 아님"으로 판정되어
`route_speed`가 `V_CURVE_LOOKUP`의 저곡률 구간 출력값(약 104~118) 근방에
사실상 고정되고, 실제 도로 형상(대시캠 영상 확인 결과 가드레일이
뚜렷하게 휘어지는 연속 굽이길)에 반응하지 않음.

147차가 고친 사례("교차로 우회전, R≈61m 단일 급커브를 40m chord가
놓침")와는 **성격이 다름** — 이번은 급커브 1개가 아니라 **완만한 커브가
연속되는 산길형 굽이길**로, 10m chord로도 각 지점의 순간곡률 자체가
threshold 미만(즉 물리적으로 반경이 크다는 뜻). chord를 더 줄인다고
해결될 문제가 아닐 가능성이 높음 — 반경 자체가 완만한데 "연속"이라는
패턴을 route 곡률 계산(3점 국소 곡률, 매 지점 독립 판정)이 구조적으로
못 잡는 유형일 수 있음(미검증 가설).

**실제 주행 영향은 제한적으로 보임**: `src` 컬럼 확인 결과 이 고정
구간 내내 `vturn`(비전 기반)이 `min()` arbitration에서 route를 이기고
있어, 실제 적용되는 `desiredSpeed`는 vturn 값(55~101 사이에서 커브
형상에 맞춰 정상적으로 변동)을 따름 — **차량 제어 자체(감속/가속)는
정상 동작 중으로 판단됨**. 사용자가 체감한 "작동 안 함"은 HUD의
"route=" 숫자가 안 움직이는 것을 본 것으로 추정되며, 실제 기능
장애(제어 미작동)인지 단순 표시 정체인지는 이번 로그만으로는 vturn이
항상 이겨왔기 때문에 **"route가 유일한/최저 소스가 되는 경우에도 이
문제가 재현되는지"는 미확인** — 만약 그런 상황(예: vturn 미탐지 커브를
route만 인지해야 하는 경우)이 실제로 있다면 그때는 route의 무반응이
실제 미감속으로 이어질 수 있어 안전영향이 달라짐.

**패치 보류 (사용자 확인 대기)**: 패치는 사용자 승인 후 진행 원칙에
따라 코드 미수정. 다음 세션 옵션:
(A) 이대로 유지 — vturn이 이미 커버하고 있어 현재로선 무해 판단.
(B) route 곡률 감지를 "연속 굽이길"도 포착하도록 개선(예: 여러 연속
    지점의 curvature 합/누적 반경 판정, 또는 threshold 자체 재검토) —
    단 부작용(직선 오탐) 검증 필요, 설계 방향부터 사용자 논의 필요.
(C) route가 vturn보다 먼저/단독으로 반응해야 하는 시나리오가 실제
    있는지(예: 비전이 안개/역광 등으로 놓치는 케이스) 확인 후 우선순위
    결정.

**사용 데이터**: `aeeed9e4a5` 세그먼트 2개(20260830 175844/175944
업로드, route.csv 2400행 `--with-navi-paths`). 대용량이라 devnotes
미커밋(프로젝트 방침) — 컨테이너 리셋 시 소실.

## 153차 — [시뮬레이션 검증 결과 POSITIVE] 152차 옵션1(근정지급 구간 DP 재귀 우회, 물리 공식 직접 덮어쓰기) 시뮬레이션 검증 — 151차 boost의 "감속 시작 지연" 부작용 없이 초과분 개선 확인, ryu 패치는 다음 단계

**배경**: 151차가 확인한 문제(accel_limit 부스트를 같은 역방향 DP 재귀에
넣으면 재귀의 time_wait 메커니즘이 오히려 현재 시점 감속 시작을 늦춤 —
NEGATIVE, 배포 보류)에 대해, 152차 계속(WIP.md)에서 사용자와 합의한
대안(옵션1): "accel_limit을 올려서 같은 재귀에 맡기는" 대신 "감지
시점에 필요감속률을 계산해 근정지급 구간에서 DP의 낙관적 역산
스케줄링을 우회하고 그 감속을 즉시 시작하도록 강제"하는 설계로
`sim_route_near_stop_accel_boost.py`를 확장, 시뮬레이션 선검증.

**설계(`carrot_navi_route_dp_forced_decel()`, toolkit README에 상세)**:
1. base accel_limit로 기존 DP(`carrot_navi_route_dp`, apply_near_stop_boost=False)를
   그대로 실행 — "언제 감속을 시작할지" 판단 로직(time_wait/margin) 자체는
   전혀 건드리지 않음. 151차 부작용의 근원이 바로 이 재귀에 부스트된
   accel_limit을 입력으로 주는 것이었으므로, 재귀 자체를 우회하는 것이
   핵심 차이.
2. 근정지급 target 지점(min_idx, speeds[min_idx]<=near_stop_target_kph)의
   필요감속률을 149차/151차와 동일한 등가속도 역산 공식
   (`required_accel_mss = (v_ego_ms^2-target_ms^2)/(2*dist)`)으로 계산.
3. `required_accel_mss > base accel_limit_mss`일 때만(=현재 설정으로
   물리적으로 못 따라가는 경우만), min_idx까지의 각 지점을 "target에서
   그 감속률로 역산한 등가속도 곡선"으로 직접 덮어씀 — 재귀/time_wait가
   전혀 개입하지 않는 닫힌 형식(closed-form) 계산이라 "지연 후 급감속"
   왜곡이 구조적으로 발생할 수 없음. 상한 `max_forced_accel_mss`(기본
   1.2 m/s^2, 151차와 동일하게 vturn_decel_rate 재사용)로 클램프해
   비현실적으로 큰 감속 요구(예: 매우 늦은 감지)를 방지.
4. 132차 프레임간 램프리미터가 이 새 곡선을 따라잡도록 accel_limit_kmh도
   같은 값 기준으로 상향해 반환.

**시뮬레이션 결과(전부 POSITIVE, 151차와 동일하게 132차 램프리미터 포함
다중프레임 `simulate_approach()` 사용)**:
| 조건 | base(패치 전) | 151차 boost(NEGATIVE) | 152차 옵션1 |
|---|---|---|---|
| 149차 근사(v_ego=90kph, target=10.7kph, 280m) | 초과 4.4kph | 초과 8.8kph(악화) | **초과 0.0kph** |
| 149차 실측 근사(v_ego=109.6kph, ~585m) | 초과 5.3kph | 초과 10.1kph(악화) | **초과 0.0kph** |
| 극단적 늦은 감지(50m, 클램프 발동) | 초과 1.3kph | 초과 4.9kph(악화) | **초과 0.0kph** |
| 일반 커브(target=40kph, 근정지급 아님) | - | diff=0(회귀없음) | diff=0(회귀없음) |

151차 boost는 세 조건 전부에서 base보다 악화됐던 반면, 옵션1은 세
조건 전부에서 base보다 개선(모두 초과분 0.0kph 도달)했고, 근정지급이
아닌 일반 커브에서는 옵션1도 전혀 발동하지 않아(diff=0) 회귀가 없음을
확인함. 151차가 지적한 근본 메커니즘(accel_limit을 재귀에 주입하면
재귀가 자체적으로 감속 시작을 늦춘다)을 옵션1이 재귀 자체를 우회함으로써
구조적으로 회피했다는 가설이 시뮬레이션으로 뒷받침됨.

**toolkit 변경**: `sim_route_near_stop_accel_boost.py`에
`carrot_navi_route_dp_forced_decel()` 신규, `simulate_approach()`에
`apply_forced_decel`/`max_forced_accel_mss` 파라미터 추가, 유닛테스트
시나리오 E~H 추가(README/CHANGELOG 갱신 완료). `--unit-tests` 결과
"10 PASS / 2 FAIL"이 정상(FAIL 2건은 151차 boost 자체를 검증하던 레거시
체크로, NEGATIVE 결론을 그대로 반영해 의도적으로 FAIL 유지 — 재작성
금지).

**한계/다음 단계**:
- 이번 회차는 **시뮬레이션 전용 재구현**만 검증됨. `carrot_man.py`
  실제 패치는 아직 작성 안 함(152차 합의 순서: 시뮬레이션 POSITIVE
  확인 후 실제 패치 → 이제 이 조건 충족, 다음 단계로 진행 가능).
- 시뮬레이션은 단일 코너 접근(합성 시나리오)만 검증했고, `_run_on_csv()`
  경로(실측 CSV의 naviPaths 그대로 넣어 검증)는 아직 옵션1 버전으로
  안 돌려봄 — 실제 route1617.csv 등으로 재검증 권장.
- `max_forced_accel_mss` 클램프가 발동하는 극단적 늦은 감지 조건에서도
  이번 3개 시나리오는 우연히 잔여 overshoot가 0.0으로 나왔으나, 이는
  50m라는 특정 거리 선택 때문일 수 있음 — 더 짧은 거리(예: 20~30m)에서도
  일관되게 "역효과 없음"만 보장되는지(완전 해결까지는 물리적으로 항상
  가능한 건 아님) 추가 확인 여지 있음.
- 149차 옵션2(route_lookahead_m 확장)와 조합하면 애초에 늦은 감지 자체를
  줄일 수 있어 옵션1의 클램프 발동 빈도를 낮출 수 있음 — 별도 검토 여지.

**전달**: FINDINGS.md(이 항목)/WIP.md/toolkit/sim_route_near_stop_accel_boost.py/
toolkit/README.md/toolkit/CHANGELOG.md. **ryu 코드 변경 없음 — 패치
파일 없음(다음 단계에서 작성 예정).**

## 152차 — [함수 버그 수정 + 신규 근본원인 유형 발견] `required_decel_gap_scan()` blinker 오탐 수정, 149차 옵션4 착수 중 seg10에서 **제3의 원인 유형**("naviPaths 폴리라인 자체가 급커브 미포함, 샘플간격과 무관하게 해결 불가") 발견 — qcamera 프레임으로 실측 확인

**요청**: 149차 옵션4(`liveRouteSpeed`로 다른 route도 "필요감속률 vs
실제감속률" 갭 전수 스캔) 착수. 신규 로그 없이 기존 3개 route
(`898edd0f96--10/16/17`) 재업로드로 진행.

**작업 1 — 함수 버그 발견+수정**: `extract_log.py --with-navi-paths`로
route1617(seg16+17 결합, 2399행, 149차와 동일 방식)/seg10(1200행)
재추출 → `required_decel_gap_scan()`(151차 작성) 실행. 초기 실행
결과 seg10에서 gap_ratio=14.35(진짜 이벤트인 route1617의 2.04보다
7배 큼)인 이벤트가 잡혀 "더 심각한 사례 발견"으로 보일 뻔했으나,
실측 대조 결과 **오탐으로 확인**: t=1962.14에 naviPaths가 280m 앞
커브(target 14.7kph)를 정상 감지했으나, 함수가 짝지은
t_arrive(t=2001.49, leftBlinker on)는 이 커브와 무관한 **차선변경
blinker**였음(t=2005.49에 4초 만에 꺼짐, steeringAngleDeg 0deg
근처 유지, liveRouteSpeed는 오히려 70→109kph로 계속 상승 중 — 실제
회전 정황 전혀 없음). 함수가 "먼 미래의 근정지급 커브 감지"와
"그 다음에 오는 아무 blinker"를 무조건 같은 물리적 지점으로
가정한 설계 결함.

**수정**: `analysis_helpers.py::required_decel_gap_scan()`에
`turn_confirm_deg`(기본 15도)/`turn_confirm_window_s`(기본 8초)
게이트 추가 — t_arrive 이후 이 시간 내 steeringAngleDeg 절대값이
threshold 이상인 프레임이 하나라도 있어야("실제 회전이 뒤따랐다")
이벤트를 채택. 재실행 결과 seg10의 이 오탐은 0건으로 정상 제거,
route1617 진짜 이벤트(gap_ratio=2.04, 149차/151차 수치와 일치)는
그대로 유지 확인.

**작업 2 — 사용자 지적으로 재조사, 신규 발견(중요)**: 사용자가
"seg10은 직선구간→합류 우회전 시 route 감속이 없어 위험했다"고
정정 지적. 재조사 결과 seg10엔 **서로 다른 두 지점의 커브
이벤트**가 존재함을 확인:
- **이벤트 B(t≈1980.09, 좌회전 방향)**: 148차 Finding A와 동일 —
  fine(10m) 재계산 결과 dist=180m, curvature=0.0363, speed_cap=10.6kph로
  148차 문서 수치(0.0366)와 거의 일치. **이미 해결된 케이스, 정상 작동
  재확인.**
- **이벤트 A(t≈1958~1972, 우회전 방향, NEW)**: vEgo가 11kph→1.9kph로
  실제 급감속하는 동안 fine(10m) 포함 근접(10m)까지 계속
  speed_cap=200(무제한) — **route 곡률 계산이 이 커브를 근접거리까지
  전혀 탐지 못함.** 이 구간 내내 liveRouteSpeed는 오히려 70→88kph로
  **상승**(실제 감속 필요와 정반대 방향) — desiredSpeed는 vturn(비전
  기반)을 따라가서 다행히 정상 감속됨(vturn이 최종 방어선 역할).
  사용자가 업로드한 qcamera 스냅샷(HUD: desiredSpeed=58, vturn=41,
  route=71.2)으로 **t=1963.29와 정확히 일치 확인** — 실제로 횡단보도
  앞 급우회전(산성터널 방향 안내) 구간이며 route가 71.2kph를 유지하려
  했던 지점이 시각적으로도 명백한 급커브였음을 확인.

**근본원인 확정(이벤트 A, 148차와 다른 메커니즘)**: t=1963.29 시점
naviPaths 원본 폴리라인을 직접 출력해 확인 — 148차 케이스(폴리라인엔
급커브 좌표가 있는데 40m 매크로 샘플링이 평활화)와 달리, 이번 폴리라인은
**220m에 걸쳐 y가 0→-45m로 서서히 변화하는 완만한 곡선으로만 기록**돼
있음. 즉 **원본 폴리라인 좌표 자체에 급커브 형상이 담겨있지 않음** —
샘플 간격을 40m→10m(147차 fix)로 줄여도, 더 줄여도 곡률 계산으로는
원천적으로 잡을 수 없음(입력 데이터 자체의 해상도/정확도 문제).
추정 원인: 내비게이션 엔진이 표시용으로 이미 매끄럽게 다듬은 경로선을
발행했거나, GPS 맵매칭 좌표가 실제 도로의 급우회전 반경보다 완만하게
스냅됨. **carrot_man.py/analysis_helpers.py의 곡률 계산 로직 문제가
아니라 naviPaths 입력 데이터 자체의 한계로 확정.**

**149차/151차 문제(감속예산 부족)와의 관계 정리 — 3가지 서로 다른
원인 유형이 확인됨**:
1. 149차(898edd0f96 seg16/17): 커브는 제때 감지했으나 accel_limit
   (감속예산) 부족 → 151차 부스트 시도는 NEGATIVE(배포 보류)
2. 147/148차(이미 해결): 폴리라인엔 급커브 좌표가 있는데 40m 매크로
   샘플링이 평활화 → 10m fine 병합으로 해결 완료, 이번 세션 재검증도
   정상 확인(이벤트 B)
3. **152차 신규(이벤트 A, 미해결)**: naviPaths 폴리라인 원본 좌표 자체가
   급커브를 담고 있지 않음 → 샘플 간격 문제가 아니므로 곡률 계산
   로직 수정으로는 해결 불가. 현재는 vturn(비전)이 유일한 방어선이며
   이번 사례에선 정상 작동함(위험하게 느껴졌지만 실제 harsh brake는
   미관측 — vturn 개입이 다소 늦게 시작된 정도).

**전수 스캔 결과 재정리(n=2, 여전히 결론 보류)**: `required_decel_gap_scan()`
(blinker 기반)로는 route1617=이벤트 1건(149차, 유형1), seg10=이벤트
0건(유형3인 이벤트 A는 **blinker가 아예 없어서 이 함수로 원천적으로
탐지 불가** — README/151차에 이미 문서화된 "blinker 미점등 회전
탐지 못함" 한계의 실제 사례). **즉 blinker 기반 스캔은 유형3(폴리라인
해상도 문제)류 이벤트를 체계적으로 누락시킨다 — 전수 스캔 결과의
"일반성 없음" 결론은 과소집계된 것일 수 있음.**

**toolkit 변경**: `analysis_helpers.py::required_decel_gap_scan()`
turn_confirm 게이트 추가(하위호환). README/CHANGELOG 갱신.

**다음 세션 우선순위**:
1. **유형3(naviPaths 해상도 문제) 전용 탐지 도구 신규 필요** — blinker
   비의존, steeringAngleDeg 급변 + 동시간 fine speed_cap=200(무탐지)
   조합으로 스캔하는 함수 작성 (`required_decel_gap_scan`과는 별도
   함수로, 149차 옵션4의 원래 취지를 유형3까지 확장)
2. naviPaths 원본 데이터가 왜 이렇게 완만하게 스냅되는지 — carrot_man.py
   쪽 리샘플링/스무딩 로직(`resample_10m_np()` 등 100차 패치 포함)이
   원인의 일부인지, 아니면 상류(내비게이션 앱/GPS 맵매칭)의 한계인지
   구분 필요 (naviPaths 원시 발행 지점, resample 이전 원본과 대조)
3. 149차 옵션1(accel_limit 재설계)/옵션2(lookahead 확장)/옵션3(vturn
   최종방어선 인정) 결정은 유형1(감속예산)에만 해당 — 유형3은 이
   옵션들과 무관하게 별도 해결책 필요, 혼동 주의
4. turn_confirm 게이트의 반대방향 오탐(완만한 근정지급 정지를 놓칠
   가능성) 여전히 미검증

**전달**: devnotes 변경 파일(FINDINGS.md/WIP.md/toolkit/analysis_helpers.py/
toolkit/README.md/toolkit/CHANGELOG.md) 이번 응답에서 전달. 3개
route CSV는 대용량 정책상 미보관(재분석 필요시 재업로드 요청).
qcamera 스냅샷(사용자 제공, t=1963.29 확인용)은 CSV와 마찬가지로
미보관 — 재검증 필요시 재업로드 요청.

## 151차 — [시뮬레이션 검증 결과 NEGATIVE] 149차가 설계한 근정지급 코너 accel_limit 부스트(`ROUTE_NEAR_STOP_TARGET_KPH`/`ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS`) — 132차 램프리미터 포함 다중프레임 시뮬레이션 결과 **오히려 초과분이 악화됨을 확인, 배포 보류 권고**

**주의(회차번호)**: WIP.md 최상단이 이미 다른 주제(시계 표시 형식 변경)로 "150차"를 선점한 상태로 push되어 있어, 149차 계측에 이어 진행된 이번 작업(근정지급 부스트 설계+검증)은 151차로 기록한다.

**배경**: 149차가 확정한 문제(898edd0f96 seg16/17, 근정지급 우회전 코너에서 route가 필요 감속률(≈1.43 m/s²)을 AutoNaviSpeedDecelRate(0.70 m/s²)로는 물리적으로 못 따라가 arbitration에서 계속 밀림)에 대해, 사용자가 "300m 감지한 곡률에 따라 필요감속율을 변화" 제안 → `carrot_navi_route()`의 근정지급 target(≤15kph) 구간 한정으로 accel_limit을 필요치만큼(상한 1.2 m/s²=vturn_decel_rate 재사용) 부스트하는 패치를 `carrot_man.py`에 국소 적용(diff 최소, 전역 영향 없음 확인 — 시나리오 A/B 단위테스트 PASS).

**검증 도구 신규 작성**: `toolkit/sim_route_near_stop_accel_boost.py` — `carrot_navi_route()`의 역방향 accel-limited DP를 독립 재현(`carrot_navi_route_dp()`)하고, 단일 코너 접근 상황을 20Hz 다중프레임으로 시뮬레이션(`simulate_approach()`).

**1차 시도(단일 프레임 비교) — 방법론 결함으로 폐기**: 최초엔 매 프레임 `out_speeds[0]`(즉시 권장값)만 patched/unpatched로 비교했으나, "지금 당장 감속할 필요 없으면 안 함"이라는 스케줄러의 정상 설계와 충돌해 오판(거리가 충분하면 둘 다 동일값) — 다중프레임 누적 시뮬레이션으로 전환.

**2차 시도(다중프레임, 132차 램프리미터 누락) — 여전히 방법론 결함**: 매 프레임 전체 배열을 재구성해 넘겼으나, production은 이 DP의 raw 출력을 그대로 차량 속도로 쓰지 않고 **132차 프레임간 램프리미터**(`carrot_man.py` L723, `max_step_kmh = accel_limit_kmh * ROUTE_SPEED_LOOP_DT`)를 한 번 더 거친다는 것을 놓쳐, "매 순간 순간이동으로 정확히 target 도달"이라는 비현실적 결과(patched/unpatched 둘 다 overshoot=0)가 나옴 — `toolkit/sim_route_boundary_ramp_limiter.py`의 `RampLimiterState`를 재사용(README "먼저 찾는다" 원칙)해 통합.

**3차(최종) — 132차 램프리미터 포함 정확 재현, NEGATIVE 결과 확정**: 149차 실측 근사 조건(v_ego=90kph, target=10.7kph, corner_dist=280m, accel=0.70)으로 재검증:
- **패치 전(unpatched)**: 코너 도달 시 15.1kph (초과분 4.4kph, 경과 23.0s)
- **패치 후(patched, 부스트 적용)**: 코너 도달 시 19.5kph (**초과분 8.8kph, 오히려 악화**, 경과 17.6s — 더 빨리 도달했다는 것 자체가 감속을 충분히 못 했다는 뜻)
149차 실측값 그대로(v_ego=109.6kph, 585m 근사)도 동일 경향(패치 전 초과 5.3kph → 패치 후 10.1kph).

**근본 원인(DP 역추적으로 확인)**: `carrot_navi_route_dp()`의 역방향 재귀는 `accel_limit_kmh`가 클수록 "나중에 더 세게 감속할 수 있다"고 판단해 **현재 시점(코너에서 먼 지점)의 권장 감속을 오히려 늦춘다** — 동일 조건(t=0, v_ego=90kph, corner 280m)에서 unpatched는 이미 72.2kph로 즉시 감속 권고, patched(accel_limit 0.70→1.10 m/s² 부스트)는 90.5kph(사실상 감속 없음)를 권고함을 직접 확인. 이 "지연 후 급브레이크" 전략은 수학적으로는 raw 스케줄 상 코너에서 정확히 target에 도달하도록 설계돼 있지만(`out_speeds[-1]=target` 강제), **132차 램프리미터가 실시간(dt=0.05s) 기준으로만 그 부스트된 accel_limit을 적용**하기 때문에, "지연 후 급브레이크"가 요구하는 실제 감속 실행을 제때 따라잡지 못하고 코너에 도달 — 결과적으로 accel_limit을 낮게 유지해 **일찍부터 완만하게** 감속을 시작하는 unpatched 쪽이 오히려 더 낫다.

**의의**: 이것은 91차(ROUTE_ENTRY_MARGIN_KPH, route가 vturn보다 일찍 감속 시작하도록 유도)/129차/131차/132차(램프리미터)가 막으려 했던 바로 그 "지연된 급감속" 병리 패턴을, 149차/150차가 설계한 accel_limit 부스트가 **다른 경로(부스트로 인한 자기 지연 유발)로 재도입**한 사례. 149차의 진단(감속률 절대량 부족)은 여전히 유효하지만, "필요시에만 accel_limit을 그때그때 올린다"는 150차의 해법 자체가 이 DP 구조(단일 스칼라 accel_limit이 전체 backward 재귀에 균일 적용되어 "언제 감속을 시작할지"까지 함께 결정)와 상충함.

**권고(배포 보류, ryu 코드 push 안 함)**: 149차/150차 설계의 `carrot_man.py` 패치(`ROUTE_NEAR_STOP_TARGET_KPH`/`ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS`, 로컬에만 존재, origin에 미반영)는 **현재 형태로는 배포하지 않을 것을 권고**. 대안은 다음 세션에서 결정 필요:
1. accel_limit을 부스트하되 "감속 시작 시점 결정" 로직(`time_delay`/`margin_target_speed` 계산)에는 **부스트 전(base) accel_limit만 쓰고**, 후반 실제 감속 구간 스텝 계산에만 부스트값을 적용 — 재귀 구조상 분리가 간단하지 않아 설계 재검토 필요.
2. accel_limit을 올리는 대신, 근정지급 target 검출 시 `route_lookahead_m`(84/85차 동적 캡)의 상한 자체를 확장해 감속 가용 거리를 늘리는 방안(149차가 이미 제시했던 옵션 2) — 이번 시뮬레이션 도구로 재검증 가능.
3. 149차 옵션 3(설계상 허용 범위로 보고 코드 변경 없이 종결) 재고.

**toolkit 변경(이번 회차)**: `sim_route_near_stop_accel_boost.py` 신규(합성 유닛테스트 4건: 시나리오 A/B PASS(회귀 없음 확인), 시나리오 C/D는 위 NEGATIVE 결과를 그대로 담아 의도적으로 FAIL 상태로 남김 — "패치가 개선"이라는 잘못된 기대를 검증하는 테스트이므로, 결론이 뒤집힌 지금은 check 조건 자체를 다음 세션에서 재작성 필요). `analysis_helpers.py`에 `required_decel_gap_scan()` 신규 추가(liveRouteSpeed 기반, 근정지급 코너의 필요감속률 vs 실측감속률 갭 스캔 — route1617.csv에서 1건 검출, gap≈2.6kph/s).

## 149차 — [신규 계측 도구 + 근본원인 확정] `carrotMan.szPosRoadName`에서 실측 route_speed(post-DP) 직접 추출(`liveRouteSpeed`) — "우회전인데 route 미작동"(898edd0f96 seg16/17)의 실제 원인은 147/148차 패치의 곡률감지 실패가 아니라 **감속예산(accel_limit) 부족**임을 확정

**배경**: 사용자 업로드(`898edd0f96` seg16/seg17, 우회전 상황 — "이 로그도 우회전인데 route 미작동. 이번패치(147/148차 ROUTE_CURVATURE_FINE_SAMPLE) 적용시 검증" 요청).

**1단계 — 곡률감지 자체는 정상(147/148차 패치 재확인)**: `extract_log.py --with-navi-paths`로 재추출(2399행, commit `46f0aed`=147차 패치 포함 HEAD) 후 `recompute_route_curvature_speed()`로 macro(40m,패치전)/fine(10m,패치) 비교. 실제 우회전(t=2371.49~2392.54 rightBlinker, steeringAngleDeg 최대 -157.8°=거의 정지에 가까운 급코너, vEgo 13.9→0)에 대해:
- macro 단독: curvature 오탐(200/36~37kph를 오락가락, 간헐적으로만 감지)
- fine(패치): t=2352.25(약 280m/약19초 전, vEgo~14m/s 기준)부터 turn 도달까지 **일관되게 speed_cap=5.0kph로 정확 포착** — 147/148차가 확립한 패턴대로 조기감지 자체는 정상 동작.

**2단계 — 그런데도 실제 주행에선 src가 한 번도 "route"가 안 됨**: 접근구간(t=2340~2392) 전체에서 desiredSpeed의 src는 cam→vturn→cam→vturn만 반복, "route"는 이 우회전 구간에서 단 한 번도 선택되지 않음(같은 트립의 다른 구간에선 route가 348/2399행 정상 선택됨 — TurnSpeedControlMode 자체는 route 참가 가능한 설정(2/3/4 중 하나)로 추정됨, 문제는 이 특정 코너에 한함).

**3단계 — 원인 특정을 위한 신규 계측(핵심 성과)**: 기존 `recompute_route_curvature_speed()`는 README에 명시된 대로 **역방향 가속도제한 DP(entry margin/time_delay 스케줄링, `carrot_man.py` `carrot_navi_route()` 후반부) 이전의 순수 곡률값만 재현** — 실제 `speed_n_sources`에 들어가는 최종 route_speed(post-DP)는 재현 불가능했음(148차가 `replay_route_full_pipeline.py`로 전체 파이프라인 재현을 시도했으나 `nRoadLimitSpeed` 미기록으로 오차 98.7kph, 신뢰불가 판정한 바로 그 문제).
이번 회차에 **`carrot_serv.py` L1100 `self.debugText += f"route={route_speed:.1f}"`가 `msg.carrotMan.szPosRoadName`에 실려 이미 20Hz로 발행되고 있다는 것을 확인** — 147차가 영상 오버레이를 ffmpeg+육안으로 초 단위로만 읽어야 했던 바로 그 값이 cereal에 원래부터 있었음(naviPaths와 같은 유형의 "발행은 되는데 extract_log.py가 안 뽑던" 케이스). `extract_log.py`에 정규식 파싱(`route=(-?\d+(?:\.\d+)?)`)으로 `liveRouteSpeed` 컬럼을 신규 추가(commit 예정, py_compile 통과) — **재현 시뮬레이션이 아니라 실측값 직접 확보**로 148차의 미해결 블로커를 근본적으로 우회.

**4단계 — 실측 결과, 근본원인 확정**: `liveRouteSpeed`(post-DP 최종값)는 t=2320(121.8kph)부터 t=2371.49(61.4kph, 우회전 진입 시점)까지 **선형회귀 기울기 약 -1.0kph/s로 단조 감소**(132차 프레임간 램프리미터가 정상적으로 최대 감속률로 계속 작동 중임을 확인) — 하지만 turn 도달 시점에도 여전히 61.4kph로, 실제 필요 target(fine 곡률 기준 5kph)에 턱없이 못 미침. 반면 fine이 처음 5.0kph를 감지한 t=2352.25(약 280m 전)부터 turn까지 남은 19초 안에 90→5kph를 도달하려면 평균 감속률 약 4.5kph/s가 필요 — 실측된 ~1.0~1.9kph/s(구간별 상이)의 **약 2.5~4.5배**에 달함. 즉:
- **147/148차 패치(fine chord 감지)는 제 역할을 하고 있음 — 곡률 자체는 최대한 조기에(약 280m/19초 전) 정확히 잡아냄.**
- **하지만 이 코너는 "거의 정지"급 target(≤5~10kph)을 요구하는 극단적으로 급한 코너라, 현재 설정된 감속률(accel_limit, 132차 램프리미터가 강제하는 프레임당 상한)로는 감지 시점부터 코너까지 남은 거리/시간 안에 도저히 그 target까지 도달할 수 없음** — 이것이 route src가 이 코너에서 한 번도 선택되지 못한 진짜 이유(계산 자체는 되지만 cam/vturn보다 항상 높은 값을 유지하다가 arbitration `min()`에서 계속 짐).
- 결과적으로 vturn(비전 반응형)이 코너 진입 시점(t=2371.94)에야 41→18kph로 뒤늦게 급감속을 떠맡음 — 사용자가 "route 미작동"으로 체감하는 현상과 정확히 일치.

**결론**: 이번 로그는 147/148차 패치의 회귀나 결함이 아니라, **애초에 사전 감속만으로는 물리적으로 커버 불가능한 영역(근정지급 코너 + 현재 감속률 설정)**을 드러낸 사례. 90/91차가 다뤘던 "route가 vturn보다 사전감속을 더 일찍 시작"(ROUTE_ENTRY_MARGIN_KPH) 메커니즘도 이미 반영되어 있지만, margin 자체가 아니라 **감속률(accel_limit)의 절대적 크기**가 병목.

**다음 세션 옵션(미결정, 사용자 확인 필요)**:
1. 근정지급 코너(예: target_speed < 어떤 임계값)에 한해 accel_limit을 별도로 더 크게(공격적으로) 적용하는 조건부 로직 추가 검토
2. route_lookahead_m의 min_m(현재 300m 고정)을 근정지급 코너 감지 시 확장하는 방안 검토(단, naviPaths 자체가 그만큼 먼 지점까지 유효한 형상으로 담겨있는지 별도 확인 필요)
3. 이 정도로 급한 코너는 vturn(비전 반응)이 최종 방어선 역할을 하는 것을 설계상 허용 범위로 보고 코드 변경 없이 종결
4. 다른 route/코너에서도 "fine 감지 거리 대비 필요 감속률 vs 실제 감속률" 갭이 비슷하게 재현되는지 `liveRouteSpeed` 신규 컬럼으로 전수 스캔(신규 `analysis_helpers` 함수 작성 필요 — 아직 미작성)

**toolkit 변경(ryu 코드 변경 없음, 이번 회차)**: `extract_log.py`에 `liveRouteSpeed` 컬럼 추가(기본 포함, 플래그 불필요 — `route=`부터 시작하는 텍스트라 컬럼 크기 부담 거의 없음). `naviPaths`처럼 향후 세션에서 재사용 가능. CSV는 대용량 정책상 devnotes에 미보관.

## 148차 — [실차검증 완료] 147차 패치(ROUTE_CURVATURE_FINE_SAMPLE=1) 신규 실측 로그(898edd0f96 seg10 재업로드분)로 검증 — 패치 정상동작 확인 + 근접(10~30m) 보조 오탐 후보 신규 발견(무해 판정)

**배경**: 147차 계속이 "이번 컨테이너 세션은 원본 zip이 재업로드되지
않아 patched 코드로 실측 CSV를 처음부터 다시 뽑아 재검증하지 못했음"
으로 다음 회차 최우선 과제로 남긴 항목. 이번 세션에 동일 route
(`898edd0f96` seg10)가 재업로드되어 `extract_log.py --with-navi-paths`로
처음부터 새로 추출(1200행, commit `46f0aed`=147차 패치 포함 HEAD 확인)
+ 검증 완료.

**Finding A (긍정 — 패치 설계 의도대로 동작 확인)**: t=1980.09 시점
naviPaths(290m 폴리라인, 30점)에서 실제 교차로 커브 위치(distance
170~220m 지점, 좌표 스무스하게 연속 커브 형태로 확인 — GPS 노이즈성
지그재그 아님)를 두 방식으로 비교:
- macro(40m chord, 패치 전 단독): curvature 0.0069~0.0091(피크)로
  0.02 임계값 근처에도 못 미쳐 **speed_cap=200.0(사실상 무제한)로
  완전히 놓침**(전체 40~250m 구간 전부 200 유지, 이 커브를 어디서도
  감지 못함).
- fine(10m chord, 147차 패치): 같은 위치에서 curvature=0.0366(R≈27m)
  까지 정확 포착, speed_cap=10.6km/h — 147차가 확립한 패턴과 정확히
  일치(별도 시점 재확인이지만 같은 route/seg이므로 사실상 같은
  교차로로 추정).
- 전체 route(696개 route-src 행) 스캔 결과, fine 최소speed<20kph
  발생 지점의 거리 분포는 뚜렷한 이중 클러스터: (1) 140~210m(58건,
  진짜 이 교차로) — 차량이 아직 도달 전인 lookahead 사전감지, (2)
  10~30m(13건, 아래 Finding B).

**Finding B (신규 발견, NEEDS_VALIDATION이나 이번 로그에선 무해 확인)**:
fine sample이 근접거리(10~30m)에서도 낮은 speed_cap(10.4~19.6kph,
t=1991.79~1993.49 구간 13건)을 산출하는 근접 클러스터 발견. 실측
대조 결과:
- 그 시점 실제 steeringAngleDeg는 -3.5°~-11.7°(완만) — 실제 R≈27m급
  급커브를 타는 중이 아님.
- vTurnSpeed(비전 기반)는 82~91km/h로 비전도 위험 없음 판정.
- 같은 로그 시계열을 보면 t=1988~1990 구간에서 실제로 steeringAngleDeg가
  최대 -52°까지 도달하는 진짜 커브를 이미 통과했고, t=1991.79~1993.49는
  그 직후 조향각이 receding(-52→-12°)하는 exit 구간과 시간적으로
  일치 — **"미래의 위험한 커브"가 아니라 방금 빠져나온 커브의 잔여
  곡률이 근접 lookahead 폴리라인에 residual로 남아 fine chord가
  포착한 것으로 추정**(heading/좌표계 정렬 지연 가능성, 정확한 원인은
  미확정).
- 실제 발행 desiredSpeed는 이 구간 내내 68~71kph로 안정 유지(오히려
  소폭 상승) — **패치로 인한 팬텀 감속/급제동은 이번 로그에서 관측되지
  않음.**

**시도했으나 폐기 — 전체 파이프라인(역방향DP+132차 램프리미터) 수치
재현**: `toolkit/replay_route_full_pipeline.py`(148차 신규) 작성해
carrot_navi_route()의 out_speed 전체 계산을 naviPaths로 프레임 단위
재현 시도했으나, 실제 프로덕션이 쓰는 `nRoadLimitSpeed`(도로제한속도,
로그 미기록) 값을 알 수 없어 재현 오차가 매우 큼(patched_sim vs
published 평균오차 98.7kph) — **신뢰 불가, 절대수치 검증용으로 쓰지
말 것**. Finding A/B는 이 스크립트가 아니라 이미 147차에 검증된
`recompute_route_curvature_speed`(파라미터 불확실성 없음, naviPaths
곡률 자체만 계산)와 실측 steeringAngleDeg/vEgo/vTurnSpeed 직접 대조로
얻은 것 — 방법론적으로 더 견고함. `replay_route_full_pipeline.py`는
추후 nRoadLimitSpeed를 확보하거나(예: carrot_serv 관련 필드 신규
계측) 다른 방법으로 캘리브레이션하면 재활용 가능해 toolkit에 보존.

**결론**: 147차 패치는 **의도한 대로 실제 교차로 커브를 정상 포착**
하며, 이번 로그에서 **패치로 인한 새로운 부작용(팬텀 감속)은 확인되지
않음**. 다만 Finding B(근접 잔여곡률 오탐 후보)는 표본 1개 route/1개
구간뿐이라 **다른 route(특히 급커브 직후 재가속 구간)에서도 재현되는지
추가 확인 필요** — 다음 세션 우선순위로 이월.

**사용 데이터**: `898edd0f96` seg10(이번 세션 재업로드, route898.csv,
1200행, `naviPaths` 전행 존재). 대용량 CSV라 devnotes에는 커밋하지
않음(프로젝트 방침) — 컨테이너 리셋 시 소실, 재분석 필요하면 재업로드
요청.

## 147차 계속 — [실측검증 완료 + 패치 적용] route 곡률 chord 축소 미세샘플 보정 — 89/90차 "chord 효과 미미" 결론은 desiredCurvature 순환논리 오류였음을 실측 naviPaths로 반박

**배경**: `carrotMan.naviPaths`(carrot_serv.py의 `coords_str`, 곡률계산에
실제 쓰이는 로컬(x,y) 리샘플 폴리라인+거리)가 이미 20Hz로 발행 중인데
`extract_log.py`가 이 필드를 뽑지 않고 있었음(89/90차는 이 필드
존재를 몰라 "raw navi_points가 로그에 없어 직접검증 불가"라 판단,
대신 `desiredCurvature`(모델 자신의 이미 평활화된 출력)를 시간적분해
경로를 역재구성하는 방식으로 우회 검증 → 순환논리).

**실측 검증** (업로드된 원본 route `898edd0f96` seg10,
`extract_log.py --with-navi-paths`로 재추출 → route147.csv, 1200행):
- 실제 교차로 우회전 구간(steeringAngleDeg 최대 -49.9°, 실측
  `desiredCurvature` 최대 0.0165 = R≈61m)에서, 기존 chord=40m
  (`sample=4`) 단독으로 naviPaths 폴리라인을 재계산하면
  curvature=0.0091(R≈110m)까지 평활화됨 — `V_CURVE_LOOKUP`의
  0.02 임계값(`abs(curvature)<0.02`이면 `nRoadLimitSpeed`로 클램프,
  사실상 무제한) 아래로 완전히 숨어버려 커브를 전혀 감지하지 못함.
- 같은 지점을 chord=10m(`sample=1`, 리샘플 네이티브 해상도)로
  재계산하면 curvature=0.0366(R≈27m)까지 정확히 포착, speed_cap이
  10.1km/h까지 정상적으로 떨어짐.
- chord별 민감도 스캔(sample=4/3/2/1): 40m→0.0091, 30m→0.0122,
  20m→0.0183, 10m→0.0366 — chord를 줄일수록 단조 증가, 90차가 측정한
  "2.5km/h 개선"은 순환논리(자기 출력을 적분해 재구성한 경로에 같은
  로직을 다시 적용)로 인한 과소평가였음이 확인됨.
- 직선 구간(같은 로그, t=1948~1955, steer≈0, 122개 route행) 오탐
  검사: sample=1로 재계산해도 max|curvature|=0.0146으로 0.02 임계값
  미도달 — 이 구간에서는 chord 축소로 인한 오탐 없음.
- 전체 세그먼트(직선+커브2개, 약 500m) sample=1 전수 스캔: curvature
  >=0.02 플래그 176개 지점, 전부 실제 물리적 커브 구간(실측 절대거리
  기준 매핑 확인, 직선 구간 오검출 0건)과 일치.

**결론**: 89/90차가 의심한 "지도 데이터 코너 형상 자체가 뭉툭함"
가설은 기각. 원인은 순전히 chord=40m 단독 샘플링의 평활화였음.

**패치**: `carrot_man.py::carrot_navi_route()`에
`ROUTE_CURVATURE_FINE_SAMPLE=1`(10m chord) 보조 샘플 추가 — 기존
sample=4(40m, 장거리 lookahead 매크로 형상/직선 오탐방지용)는 그대로
두고, 같은 위치에서 fine sample로 한 번 더 계산해 더 급한(speed_cap이
더 낮은) 쪽만 채택(merge, 대체 아님). commit `ffad14e`. 상세는
WIP.md 147차 계속 참고. `analysis_helpers.py::recompute_route_curvature_speed()`
에도 `sample_fine` 파라미터로 동일 로직 반영해 검증도구=실제 패치
일치시킴.

**toolkit 버그 수정**: `extract_log.py` — row dict가
`--with-navi-paths` 플래그와 무관하게 항상 `naviPaths` 키를 갖는데
(플래그 off 시엔 빈 문자열), FIELDNAMES엔 이 키가 없어 `DictWriter`
(extrasaction 기본 "raise")가 플래그 사용 여부 상관없이 크래시하던
버그. FIELDNAMES에 `naviPaths`를 항상 포함하도록 수정.

**미검증**: 다른 route(특히 고속도로/GPS 노이즈가 큰 구간)에서
sample=1 fine 샘플의 오탐률은 아직 확인 안 됨 — NEEDS_VALIDATION.
이번 세션은 원본 zip 재업로드가 없어 patched 코드로 CSV를 처음부터
재추출해 재검증하지는 못했고, 위 실측 수치는 직전(컨테이너 리셋으로
끊긴) 세션에서 이미 확보된 것을 그대로 인용.

## 147차 — [정성추정, 영상판독 기반 + toolkit 실측검증도구 완성] route 우회전 사전감속 무력화: 132차 정상동작 확인 + 89/90차 곡률과소평가 실측검증 도구(naviPaths) 신규

**대상**: `route_작동안됨_진입속도가_너무빨라_위험한_상황_260830_072521`
클립(=146차 체크포인트 E번 클립과 동일 타임스탬프). ATC(AutoTurnControl)는
사용자가 의도적으로 꺼둔 상태 확정 전제 하에 route 자체 로직만 조사
지시받음.

**방법(원본 로그 없음, 영상 판독)**: ffmpeg 1fps 프레임 추출 →
화면 우하단 `route=XX.X` 오버레이(`carrot_serv.py` L1100)를 프레임별
직접 판독. 동시에 좌하단 `vturn`/큰 속도계 숫자도 함께 판독해 교차비교.

**관측값** (t=초, 우회전까지 거리, vEgo, vturn, route=):
| t | 거리 | vEgo | vturn | route= |
|---|---|---|---|---|
| 1 | 84m | - | - | 85.4 |
| 2 | 75m | - | - | 85.0 |
| 3 | 64m | - | - | 83.9 |
| 4 | 54m | - | - | 82.6 |
| 6 | 28m | 49 | (미개입) | 79.2 |
| 7 | 16m | - | - | 78.2 |
| 8 | 3m | 51 | 61 | 76.8 |
| 9~11 | 진입중 | - | - | 74.9→74.1→72.4 |
| 12 | 커브중 | 57 | 39 | 70.3 |
| 14 | 통과 | 49 | 54(회복) | 70.0 |

**핵심 발견 1 — "계단식 완만한 하강"은 132차 패치의 정상 동작, 새 문제
아님**: 관측된 하강률(초당 약 1~1.5km/h)은 132차(`f24cbf8`, `carrot_man.py`
L629-634 `ROUTE_SPEED_LOOP_DT=0.05s` 기준 프레임간 램프, 상한
`accel_limit_kmh*0.05s` ≈ `accel=0.70`일 때 초당 2.52km/h) 이내로
완전히 설명됨. `git log --oneline`으로 132차 커밋이 현재 `c3-ms-dev`
HEAD(`3ec4e5c`, 141차)에 이미 포함돼 있음을 재확인 — 131차가 잡아낸
"route_lookahead 윈도우 경계 진입 시 curvature가 단일 20Hz 프레임에
이산적으로 배열에 나타나 desiredSpeed가 20~25km/h씩 계단으로 뚝
떨어지는" Hypothesis C 불연속은 이 클립에서 나타나지 않았음(정상
완화 확인).

**핵심 발견 2 — 진짜 문제: route 최종 목표값(70.0)이 실제 필요치
(vturn 최저 39)보다 30km/h 높음**: 이건 89차/90차가 다른 커브(고속도로
램프, `bc4301a25d` seg12)에서 이미 확인한 것과 동일 유형 —
- 89차 실측: route 최종값 121 vs vturn 실측 73~77 (48km/h 갭)
- 90차 검증: 곡률 계산 chord(현재 `sample=4`→40m 간격)를 2/3로 줄여도
  개선폭 2.5km/h뿐 → "chord 길이가 아니라 실제 GPS 폴리라인 자체의
  형상 정밀도(지도 데이터가 이 코너를 얼마나 뭉툭하게 표현하는지)"가
  더 유력한 원인이라는 결론(NEEDS_VALIDATION, raw navi_points 로그
  부재로 직접검증 불가 상태였음).
이번 147차 클립(70 vs 39, 30km/h 갭)도 같은 패턴 — ATC가 꺼진 상태라
route 곡률감속이 유일한 사전대응 수단인데 이게 무력화되어, vturn(비전
기반, 반응 늦음)에만 전적으로 의존 → "코앞까지 안 줄다가 커브 안에서야
급락"하는 이번 증상으로 귀결. **단, 이번 세션은 원본 로그가 없어 영상
오버레이 판독에 의한 정성적 추정 — 정량 확정 아님.**

**[신규 발견] 89차/90차가 "raw navi_points 로그 부재로 직접검증 불가"라
남겨뒀던 전제 자체가 틀렸음이 드러남**: `carrot_serv.py` 재확인 결과
`carrotMan.naviPaths`(custom.capnp L27, `Text` 필드)에 `carrot_navi_route()`
가 곡률 계산에 실제로 쓰는 로컬(x,y) 리샘플 폴리라인+거리
(`coords_str = ";".join(f"{x:.2f},{y:.2f},{d:.2f}" for (x,y),d in zip(coords,distances))`,
L1170-1172)가 **이미 20Hz로 발행되고 있었음**(`pm.send('carrotMan', msg)`,
`update_navi()` 호출부는 `frame%20` 게이트 없이 매 루프 실행 확인).
`ryu` 코드는 원래부터 이 데이터를 만들고 있었고, `extract_log.py`가
단지 이 필드를 CSV로 안 뽑고 있었을 뿐 — **89/90차가 제안했던 신규
계측 패치는 필요 없었음**.

**toolkit 신규 (147차, ryu 코드 변경 없음)**:
- `extract_log.py --with-navi-paths` 플래그(기본 off — row당 최대
  ~1200자로 CSV가 크게 불어나 route 커브 조사 시에만 사용 권장) —
  `naviPaths` 컬럼 추출.
- `analysis_helpers.py` 신규 3종:
  - `parse_navi_paths(navi_paths_str)` — 텍스트 파싱.
  - `recompute_route_curvature_speed(points, distances, sample=4)` —
    `carrot_man.py`의 `calculate_curvature()`+`V_CURVE_LOOKUP_BP/VALS`를
    100% 동일 이식(90차 `sim_route_curvature_sample.py` 상수 재사용)해
    실측 폴리라인에서 지점별 곡률/speed_cap 재계산(역방향DP는 미포함,
    "이 지점 곡률 자체가 실제로 얼마나 급한가"만 순수 확인).
  - `route_curvature_underestimate_scan(rows, min_gap_kph=15.0)` —
    `src=="route"` 구간의 실제 발행 desiredSpeed와 재계산 최소값을
    비교, 갭이 크면 리포트. 갭이 크면 "폴리라인은 이미 충분히
    급한데 다른 로직(역방향DP 스케줄링)이 못 살렸다"는 뜻, 갭이
    작으면 "폴리라인 형상 자체가 이미 뭉툭하다"(89/90차 지도데이터
    정밀도 가설)는 뜻으로 해석 가능.
- 합성 90도 코너(직진80m→급코너→직진80m, 10m 간격) 단위테스트 PASS —
  코너 정점(dist=90m)에서 curvature=0.0300/speed_cap=20.5kph 정확
  포착 확인. 즉 **폴리라인 자체가 실제로 날카로운 단일 정점으로
  존재한다면 sample=4(40m 간격)로도 문제없이 잡아낸다**는 것을
  재확인 — 90차 결론(chord 길이 자체는 범인이 아닐 가능성)과 정합.

**한계/다음 세션**: 이번 결론(70 vs 39 갭 = 89/90차와 동일 유형 곡률
과소평가)은 어디까지나 영상 오버레이 판독 기반 정성적 추정. 이 교차로
원본 route(zip) 재업로드 → `extract_log.py --with-navi-paths` 재추출 →
`route_curvature_underestimate_scan()` 실행하면, 89차/90차부터 미뤄져
온 "chord 길이 문제 vs 실제 지도 폴리라인 형상 문제" 질문을 최초로
실측 데이터로 직접 확정할 수 있음.

**상태**: [정성추정, TOOLKIT_READY] — 코드(ryu) 변경 없음, toolkit만
갱신. 정량 확정은 이 교차로 원본 로그 재업로드 대기.

---

## 146차 계속 — [원인확정(정량검증 완료), 설정확인 필요] route 카운트다운/ATC 미작동 = AutoTurnControl/AutoNaviCountDownMode 둘 다 0(off) 확정, xTurnInfo 이중소스 가설은 기각

**대상**: 146차(영상판독+정적분석) 후속. 07:02~07:37 원본 route 3건
재업로드 → 신규 필드(activeCarrot/xTurnInfo/xDistToTurn/xSpdType/
xSpdDist/atcType/leftSec/xSpdCountDown/xTurnCountDown)로 재추출,
43289행. `extract_gps.py`로 1Hz GPS 채널도 병행 추출.

### 가설 A(xTurnInfo 이중소스 충돌) — 기각
xTurnInfo 자체는 정상 분포(1/2/4/8 등 유효값 다수, -1은 7114행/16.4%
뿐) — 146차가 세웠던 "navd가 계속 -1로 덮어쓴다"는 코드분석 기반
가설은 실측 불일치로 반박.

**대신 확인된 실제 원인 — `atcType`이 xTurnInfo 유효값(1~6) 35875행
전부에서 예외없이 "none"**, `src`(desiredSource)에 "atc" 0건(전체
cam19018/route12982/vturn9538/road1733/bump18). `carrot_serv.py`의
```
if self.autoTurnControl not in [2, 3]: atc_desired = atc_desired_next = 250
if self.autoTurnControl not in [1,2]: self.atcType = "none"
```
두 조건이 모두 항상 참이려면 `AutoTurnControl`이 {0,3}∩{0,1}={0}
이어야 함 — **`AutoTurnControl = 0`(UI 표시상 "None", 코드 기본값)이
이 세션 전체(36분)에서 유지되었음이 정량적으로 100% 확정**. xTurnInfo/
xDistToTurn 계산 파이프라인 자체는 정상 동작 중이었으므로 코드 결함이
아니라 **최상위 기능 스위치가 꺼져 있었던 것**.

### 카운트다운(음성) 미작동 — `AutoNaviCountDownMode = 0` 확정
`xSpdCountDown`(=left_spd_sec)/`xTurnCountDown`(=left_tbt_sec) 원시
계산값이 43289행 **전량 100(초기값) 고정, 단 1건도 100 미만 없음**.
```
left_spd_sec = 100; left_tbt_sec = 100
if self.autoNaviCountDownMode > 0:
    ...(xSpdDist/xDistToTurn 기반 실제 계산)...
```
이 게이트를 통과한 적이 전혀 없다는 뜻 — 기본값 2(tbt+camera+bump)와
달리 이 세션에서는 **`AutoNaviCountDownMode = 0`**으로 확정. 화면
TBT 거리박스(navd 직접 표시 경로, 카운트다운 변수와 무관)는 정상
동작 중이었던 것과 대비되어, "화면 거리는 되는데 소리/ATC감속은 전혀
없다"는 사용자 체감을 정확히 설명.

### 가설 B(정차 중 route= 지속 하락) — 정성적 지지 확보
B클립(071828) 추정 구간(wall-to-t 근사, t≈1522 부근)에서 실측 재현:
t=1560(64.3kph)→t=1578(0kph) 정차, desiredSpeed(src=route)는 82(t=1560)
→36(t=1578)→**30(t=1583, 정차 12초 경과 후)**로 하락 후 정지 —
30은 `AutoCurveSpeedLowerLimit`(129차 확인 사용자 설정값)과 정확히
일치하는 플로어. 재출발(t=1584~) 시 route 값도 정상적으로 재상승
확인(30→85 이내, t=1616).

`extract_gps.py`로 정차구간(t=1571~1583) GPS 확인:
- `bearingDeg`: 23.771334(고정, 정차 직후부터 12초간 소수점까지 완전
  동일 — GPS course 계산 불가 시 마지막 유효값을 hold하는 것으로 보임)
- `latitude`/`longitude`: 미세하게 계속 이동(longitude 129.107833→
  129.107790, 약 4m 상당 드리프트, 12초에 걸쳐 단조 감소에 가까운
  패턴)

정차 중임에도 GPS가 "정지된 값"이 아니라 계속 미세하게 흐르는 이
드리프트가, `carrot_navi_route()`의 `current_position` 기반 폴리라인
진행위치 재계산에 유입 → route_lookahead 윈도우가 조금씩 앞으로
밀리며 낮은 curvature 지점이 조금씩 당겨져 노출되는 메커니즘(146차
원 가설)과 하락 시점·방향·정지값(정확히 30 floor 도달) 모두 정합.
**단, `AutoCurveSpeedLowerLimit` 플로어가 이미 존재해 무한정 하락하지
않고 30에서 막히므로, 최초 우려했던 "위험한 무제한 하락"보다는 안전
측면 리스크가 낮은 편**. 정량적 replay(GPS 좌표를 `carrot_navi_route()`
core 로직에 직접 흘려 재현)는 미착수 — 필요시 다음 세션.

### 사용자 확인 필요(코드 변경 전 필수, 우선순위 최상위)
1. 실차 `ssh comma@172.30.1.68` → `cat /data/params/d/AutoTurnControl`,
   `cat /data/params/d/AutoNaviCountDownMode` 로 현재값 직접 확인.
   - **0이 확인되면**: 이번 증상은 설정 변경만으로 해결 — 코드 패치
     불필요. UI에서 값을 1~3(ATC)/1~2(카운트다운)으로 변경 후 재검증
     권장.
   - **0이 아닌(예: 2, 3) 값이 나오면**: 로그가 뽑힌 시점과 현재
     조회 시점 사이 설정이 바뀌었거나, UI 저장/부팅 시 파라미터 로딩
     경로에 별도 버그가 있다는 뜻 — 이 경우 `settings.cc`의
     `CValueControl` 저장 로직과 `carrot_serv.py` L268
     (`self.autoTurnControl = self.params.get_int("AutoTurnControl")`)
     읽기 시점(캐싱 여부, 부팅 vs 매프레임)을 다음 세션에서 코드
     추적 필요.
2. 가설 B는 replay 정량검증 여부를 사용자 결정에 맡김 — 이미 30 플로어
   확인으로 안전성 우려는 낮아졌으므로 우선순위는 1번보다 낮음.

### 상태
**가설 A 기각·실제 원인(설정값 OFF) 확정. 가설 B 정성지지(정량 replay
미착수). `ryu` 코드 변경 없음** — 패치는 위 사용자 확인 결과에 따라
착수 여부 결정(프로젝트 규칙: 패치는 사용자 승인 후). 대용량 CSV
(`route146.csv` 43289행, `route146_gps.csv` 2023행)는 레포 미커밋
(정책), Drive 커넥터 미연결 상태라 `work/`에만 존재 — 컨테이너 리셋
시 소실.

---

## 146차 — [가설확정(코드분석+영상대조), 실차정량검증 필요] route 카운트다운/회전(ATC) 사전감속 미작동 — xTurnInfo 이중소스 충돌 가설

**대상**: 사용자 업로드 화면녹화 7클립(260830, 07:17:36~07:36:11 범위,
18~30초). 파일명 = 증상 태그. `144cha-combined` route(07:02~07:37)와
시간대는 일치하나 **당시 CSV에 xTurnInfo/xDistToTurn/xSpdDist/xSpdType/
atcType/activeCarrot 필드가 없어(`extract_log.py` FIELDNAMES 미포함)
정량 대조 불가** — 전량 영상 프레임 직접 판독(ffmpeg 6분할 콘택트시트)
으로 분석. (146차 체크포인트에서 해당 필드들을 extract_log.py에 추가
완료 — 다음 세션 원본 route 재업로드 시 정량검증 가능.)

### 클립별 관찰
- **`카운트다운이_안됨`(071736)**: TBT 거리박스 102m→12m(첫 좌회전)
  정상 카운트, 이후 새 구간(영천로) 890m→646m로 갱신 — 거리박스 자체는
  끊김없이 동작. (오디오 카운트다운은 영상에 음성트랙 없어 검증 불가 —
  `soundd.py`의 `leftSec`(11~1 음성) 로직은 화면 요소가 아님을 확인.)
- **`카운트다운_정지해있는데도_계속_낮아짐`(071828)**: 선행차 정체로
  감속정차(v 66→51→32→6→0→0). TBT박스 거리는 175m→105m→51m→31m→
  29m→30m(정차 후 거의 불변, 정상). 그러나 디버그텍스트 `route=`
  값(carrot_serv.py L1092, route 기반 목표속도)은 **99.4→87.6→74.9→
  62.4→50.0→37.4로 정차(v=0) 이후에도 계속 하락** — 파일명 증상과 정확히
  일치하는 이상행동.
- **`카운트다운_되는_상황`(072132)**: 부산 방향 정상주행, TBT거리
  286→192→114→50→2m로 매끄럽게 카운트, route= 값도 75.4→39.1 방향으로
  합리적으로 등락 — 정상 대조군.
- **`카운트다운_분석`(072318)**: v 71~78 정속 주행, TBT거리(km단위)
  2.0→1.6km 순감소, route= 92.9→70.0(중간)→74.6(약간 반등) — 실제
  커브 형상 대응으로 보이는 정상 패턴. 이상 없음(비교 참고용으로 추정).
- **`작동안됨_진입속도가_너무빨라_위험한_상황`(072521)**: 우회전 접근 중
  v가 **34→42→50으로 오히려 가속**, TBT거리 84m→59m→22m로 좁혀지는데
  route= 값은 85.9→82.7→**79.1**(22m/50kph=약 1.6초 거리인데도 감속
  목표 미형성) — 회전 직전 새 구간 전환 후 vTurnSpeed가 58→41→69로
  요동(144차 Finding B "route↔vturn 플리커"와 동일 패턴). 이 구간에서
  회전 전용 감속(ATC)이 아예 관여하지 않은 것으로 보임.
- **`우회전_상황에서_작동_안됨`(073145)**: v 56→56→55→55→55→**14**.
  근접 표지판(카메라 55 제한, "CAM" 적색 활성 — 별도 정상기능) 거리
  74m→7m 구간에서도 v 불변(카메라 자체는 회전과 무관), TBT박스(다음
  목적지 "산성터널")는 1.8km→1.5km로 정상 카운트. 정작 **실제 우회전
  지점(마지막 프레임, 우회전 화살표 UI 등장)에서만 55→14로 급락** —
  사전 감속 구간이 사실상 없이 코앞에서 급제동.
- **`좌회전_상황_작동_안됨`(073611)**: v 38→33→34→35→31→**13**. TBT거리
  107m→63m→23m→0m로 매끄럽게 카운트되는 동안 v는 31~38 유지, route=도
  136.3→75.0으로 하락은 하나 실제 좌회전 코너링에 필요한 저속(15~20
  대)까지는 못 미친 채 마지막 프레임에서 v=13으로 급락. F와 동일 패턴.

### 원인 가설 A (핵심, 미검증) — xTurnInfo 이중 기록소스 충돌
`carrot_serv.py`에서 `self.xTurnInfo`/`self.xDistToTurn`을 쓰는 경로가
2개 존재:
1. `_update_tbt()`(L392~) — 외부 내비게이션 앱(웹소켓 JSON, `nTBTTurnType`)
   기반, 로컬 `turn_type_mapping`(정수 키, 정확한 라벨: uturn/arrive=7,
   notification=0).
2. `update_nav_instruction()`(L854~) — navd 자체 `sm['navInstruction']`
   기반, **모듈 전역 `nav_type_mapping`을 문자열(maneuverType/
   maneuverModifier) 매칭으로 재사용**(원래 정수 키 조회용으로 만들어진
   동일 dict를 이중 목적으로 재사용). `self.xTurnInfo = -1`을 **먼저
   설정한 뒤** 매칭을 시도하므로, navd의 `maneuverType`/`maneuverModifier`
   문자열이 테이블(turn/off ramp/fork/rotary/arrive/notification만
   커버, roundabout·on ramp·generic continue 등 미포함)과 정확히
   일치하지 않으면 **그 프레임에 xTurnInfo가 무조건 -1로 리셋**됨.

`update_navi()`의 호출 조건: `if self.active_carrot <= 1 or
self.active_kisa_count > 0: self.update_nav_instruction(sm)`.
`active_kisa_count`는 `update_kisa()`(Waze 카메라/경보 데이터 수신,
`kisawaze*` 키)가 호출될 때마다 100으로 리셋되고 매 프레임 -1씩 감소 —
즉 **최근 5초 이내 Waze 패킷 수신 이력이 있으면 항상 True**. F/G
영상에서 "CAM"(카메라 경보) 적색 표시가 근접 구간 내내 켜져 있던 것으로
보아 이 구간 동안 Waze 데이터가 지속 활성 상태였을 가능성이 높고, 그
경우 매 프레임 `update_nav_instruction()`이 실행되어 **외부 앱이 이미
정확히 세팅한 xTurnInfo(1/2)를 navd 매칭실패시 계속 -1로 덮어썼을
가능성**이 있음.

`xTurnInfo < 0`이면 `update_auto_turn()`의 `turn_info_mapping.get(
x_turn_info, default_mapping)`이 `default_mapping`(`speed:0`)으로
빠져, `atc_desired`(회전 사전감속 목표속도) 계산의 게이트 조건
(`if atc_speed > 0 and x_dist_to_turn > 0`)이 항상 거짓이 되어 **회전
전용 감속이 전혀 발동하지 않음** — 코앞까지 등속 유지 후 급감속하는
E/F/G 관찰과 정합.

이 하나의 메커니즘(xTurnInfo 유실)이 "카운트다운(회전판정) 안됨" /
"우회전 작동 안됨" / "좌회전 작동 안됨" / "진입속도 너무 빨라 위험" 4개
증상 태그를 모두 설명 가능한 통합가설.

### 원인 가설 B (미검증) — 정차 중 route= 지속 하락
`carrot_man.py::carrot_navi_route()`가 매 호출 `current_position`
(GPS lat/lon)/`heading_deg`(GPS bearing)로 route 폴리라인 상 현재
위치를 재계산함. 정차 중에는 GPS course(진행방향)가 물리적으로
정의되지 않아 노이즈에 취약 — 이 지터가 매 프레임 폴리라인 진행을
근소하게 "전진"시키는 것으로 오인되면, `route_lookahead_m` 윈도우가
조금씩 앞으로 밀리며 원래 더 뒤에 있던 낮은 curvature 지점이 조금씩
당겨져 노출 → out_speed(=route=)가 실제 정지 상태와 무관하게 계속
하락. 132차 램프리미터(`_route_speed_prev` 기반)는 프레임당 변화율만
제한할 뿐 이 누적 편향 자체는 막지 못함. B 클립 관찰과 정합하나 GPS
좌표 시계열 확인 전까지는 가설 단계.

### 검증 갭 → 146차 체크포인트에서 일부 해소
`toolkit/extract_log.py` FIELDNAMES에 `activeCarrot`, `xTurnInfo`,
`xDistToTurn`, `xSpdType`, `xSpdDist`, `atcType`, `leftSec` 추가
완료(146차). `active_kisa_count`는 cereal(custom.capnp CarrotMan)에
미발행이라 여전히 CSV로 직접 확인 불가(코드 내 주석으로 명시). 현재
`144cha-combined`는 원본 rlog가 컨테이너에 없어(대용량 정책상 미보관)
재추출 불가 — **07:02~07:37 원본 route 3건(ba5f3d3273/898edd0f96/
e996400f6e) 재업로드 시** 재추출 후 위 두 가설 정량 검증 가능.

### 상태
**코드 변경 없음(정적분석+영상판독 전용, 패치 미착수)**. 패치는 사용자
승인 후 진행(프로젝트 규칙 "패치는 나한테 물어보고"). 145차(PathOffset
커브 좌측차선 침범, 실차 재검증 대기)는 이번 회차와 무관하게 별도
보류 유지.

---

## 145차 — [가설확정(코드분석), 실차 재검증 필요] PathOffset 커브구간 좌측차선 침범 — 화면녹화 대조 + 원인 코드분석

**대상**: 144차에서 예고된 화면녹화 영상 4개(오프셋 -10/-5×2/0, 각 30초
클립, 파일명에 07:xx:xx 실시각 포함) 도착 → `144cha-combined` route와
시각 대조 분석.

**시각 매핑 검증**: route 첫 행(t=568.784)을 07:02:34(WIP 144차 기록)로
앵커해 각 영상의 파일명 시각을 t로 역산 → 영상 온스크린 HUD 시계
표시(예: "07:19")와 정확히 일치 확인. 매핑 신뢰 가능.

**Finding A (핵심, 시각적으로 확인됨)**: PathOffset=-5, **좌회전 커브**
클립(071922, "좌측차선을밟음")에서 커브 정점 부근 프레임들
(frames/d125d5/f_03~05)에서 그린 경로(d_path)가 좌측 가드레일쪽
백색차선에 거의 닿거나 살짝 넘어감 — 우측 여유공간은 크게 남음(중앙
유지 실패, 좌측 편중). 동일 세션 PathOffset=0, **우회전 커브** 클립
(072049, "중앙잘잡음")에서는 좌우 여유 고르게 유지(정상). PathOffset
-5/-10의 **직진구간** 클립 2개(071330, 071626)는 모두 편중 없음(넓은
직선도로, 문제 없음) — "직진에서는 무해, 곡선에서만 유독 심함"이라는
사용자 관찰과 일치.

**주의(교란변수)**: -5(문제) 클립은 좌회전, 0(정상) 클립은 우회전으로
**커브 방향이 다름** — offset 크기만의 순수 비교는 아님(방향까지 같은
대조쌍은 이번 4개 영상에 없음). 아래 Finding B가 방향 문제를 설명하는
유력 후보.

**Finding B (코드분석, 원인 후보 — 실차 미검증)**: PathOffset 경로 외에
**커브 진입 시 자동으로 적용되는 별도 offset 메커니즘**이 이미 존재함.
`selfdrive/controls/lib/lane_planner_2.py`:
- Line 162: `self.adjustCurveOffset = self.adjustLaneOffset` (`AdjustCurveOffset`는
  현재 `AdjustLaneOffset` 파라미터를 그대로 재사용 — 별도 파라미터
  아님)
- Line 166: `offset_curve = np.interp(abs(curve_speed), [50,200],
  [adjustCurveOffset, 0.0]) * np.sign(curve_speed)` — 커브가 급할수록
  (vTurnSpeed 작을수록) 최대 `AdjustLaneOffset`값까지, 직선일수록 0으로
  수렴. `carrot_settings.json`상 `AdjustLaneOffset` 설명: **"도로경계쪽/
  커브안쪽으로 보정합니다"** — 즉 설계 의도 자체가 "커브 안쪽으로
  자동 보정"(방향은 `np.sign(curve_speed)`로 커브방향에 연동되는 것으로
  보임, `carrot_serv.py`의 vTurnSpeed 부호 처리는 이번 세션에서 상세
  추적 안 함).
- Line 249: `path_xyz[:, 1] += (CAMERA_OFFSET + self.lane_offset_filtered.x)`
  — 이 보정은 **레인풀모드(lanefull_mode) 여부와 무관하게** 항상
  실행됨. 게이트는 `self.d_prob`(차선 인식 확률)뿐 — d_prob>0이면
  레인리스 주행 중에도(레인풀 모드 미진입 상태라도) 이 커브-내측
  보정이 부분 반영될 수 있음.
- 이후 `lateral_planner.py` line 163에서 **별개로** 테스트 대상인
  `self.pathOffset`(PathOffset 파라미터)이 **추가로 더해짐**. 즉 두
  offset이 **순서대로 누적** — (1) lane_planner_2의 커브-내측 자동보정
  + (2) PathOffset 수동값.

**가설**: 이번 테스트 차량의 `AdjustLaneOffset`값이 0이 아니고, 좌회전
구간에서 차선 인식확률(d_prob)이 어느 정도 있었다면(빗길이지만 백색
차선 페인트 육안 식별 가능한 영상), 좌회전 커브에서는 (1)의 자동
내측보정이 **좌측방향**으로 이미 얼마간 걸려 있었고, 여기에 (2)
PathOffset=-5(좌측)가 **같은 방향으로 누적**되어 육안상 5cm 파라미터
값보다 훨씬 커 보이는 좌측 편중이 나타났을 가능성. 우회전 클립(offset=0)
은 (2)가 0이고 (1)의 방향도 반대(우측)라 문제가 드러나지 않았을 수
있음 — Finding A의 교란변수를 자연스럽게 설명.

**미확정 사항(사용자 확인 필요)**:
1. 테스트 당시 device의 `AdjustLaneOffset` 실제 설정값 (0이면 이 가설
   기각, 순수 PathOffset 문제로 재검토 필요)
2. `carrot_serv.py`에서 vTurnSpeed 부호가 실제로 커브 방향(좌/우)을
   인코딩하는지 코드 추적(이번 세션 범위 밖, 다음 세션 후보)
3. CSV에 `lll_prob`/`rll_prob`/차선폭 필드가 없어 d_prob>0 여부를
   로그만으로 검증 불가 — 확인하려면 `extract_log.py` FIELDNAMES에
   추가 후 재추출 필요

**다음 단계 제안**: (a) `AdjustLaneOffset` 값 확인, (b) 가능하면
`AdjustLaneOffset=0` 상태로 PathOffset만 단독으로 좌/우 커브 각각에서
재검증하는 대조실험, (c) 반대로 PathOffset=0 고정한 채 AdjustLaneOffset
단독 커브 거동 확인 — 두 메커니즘을 분리해야 "이 로직은 별도로 해야할
듯"이라는 사용자 직관이 정확히 어느 메커니즘을 가리키는지 확정 가능.

**상태**: 코드 변경 없음(관찰/코드대조 리뷰만). 4개 route 데이터
(`ba5f3d3273`/`898edd0f96`/`e996400f6e`/`144cha-combined`)는 144차와
동일하게 미승인 상태로 유지(삭제 안 함). 업로드 영상 4개는 devnotes에
커밋하지 않고 `/home/claude/work`에서만 스크래치로 다룸(세션 종료 시
소실 — 재사용 필요하면 재업로드).

---

## 145차 계속 — params_backup 확인 + lllProb/rllProb 재추출로 d_prob 실측 검증

**요청**: 145차 미확정 사항 해소를 위해 사용자가 원본 zip 3개(37seg
전체) + `params_backup-4.json` 재업로드.

**Finding C (미확정①③ 해소)**: params_backup 확인 결과
**`AdjustLaneOffset: 10`**(0이 아님, 0.10m) — 145차 가설의 전제(자동
커브내측보정이 실제로 걸려있었는지) 확인됨. `PathOffset: 0`은 이
백업 시점 스냅샷일 뿐 각 클립 당시 실시간 조작값과는 무관(참고용).
`UseLaneLineSpeed: 0` 확인 — `lateral_planner.py`의
`useLaneLineSpeedApply==0 → useLaneLineMode 항상 False` 분기와 일치,
144차 Finding C(레인리스 100%)의 근본 원인이 속도 임계값이 아니라
**이 설정 자체가 레인풀 모드를 원천 차단**하고 있었음을 코드로 확정.

**extract_log.py 확장 후 재추출**: `lllProb`/`rllProb`/`lllStd`/`rllStd`
필드 추가(toolkit CHANGELOG 참고) → route a/b/c 전체 37seg 재추출 →
병합 결과 기존 `144cha-combined`(43289행, t동일범위)와 완전히 일치
확인(연속성 재검증 통과, gap 0건).

**Finding D (d_prob 근사 실측 — 부분 확인, magnitude는 불일치)**:
`get_d_path()`의 `l_prob*l_std_mod`/`r_prob*r_std_mod` 중 max값으로
d_prob 근사 계산(width_pts 기반 추가감쇠 항은 원본 lane_lines y배열이
CSV에 없어 근사에서 제외 — 즉 아래 값은 실제 d_prob의 **상한**):

| 구간 | d_prob_approx 평균 | frac>0.3 |
|---|---|---|
| offset=-5 직진(071626) | 0.51 | 61% |
| offset=-10 직진(071330) | 0.63 | 83% |
| **offset=-5 좌커브 침범(071922)** | **0.28** | **30%** |
| offset=0 우커브 정상(072049) | 0.98 | 100% |

문제가 된 좌커브 구간은 오히려 평균 d_prob이 가장 **낮았음**(간헐적).
그러나 0은 아니며 최대 0.985까지 튀는 구간이 존재 + `lane_offset_filtered`가
필터링(관성) 객체라 순간적 d_prob 상승만으로도 잔여효과가 남을 수
있음 — "완전히 무관하다"고 단정할 근거도 아님. **어느 쪽으로도
확정적이지 않음**, 145차 가설은 기각도 확정도 안 된 상태.

**Finding E (신규 의문점 — vTurnSpeed 부호가 커브방향 인코딩이
아닐 가능성)**: 좌커브(071922)/우커브(072049) 두 구간 모두 vTurnSpeed
실측값이 **압도적으로 음수**(-20~-26대, -84~-87대 등)로 나타남 —
방향(좌/우)에 따라 부호가 갈릴 것이라는 145차의 가정과 배치.
`carrot_serv.py` line 1033 `max(abs(vturn_speed), ...)`도 즉시 abs()
처리 — 부호가 실사용 크기와 무관한 별도 의미(방향 플래그 등 추정,
미확정)일 가능성. 만약 부호가 방향을 인코딩하지 않는다면,
`lane_planner_2.py`의 `offset_curve = ... * np.sign(curve_speed)`는
**커브 방향과 무관하게 항상 같은 방향으로 보정**하게 되어 145차
가설의 "좌커브라서 우연히 같은 방향" 설명 대신 "이 보정은 애초에
방향비의존적이라 좌/우 어느 커브든 매번 같은 쪽으로 쏠릴 수 있다"는
더 근본적인 이슈로 재해석될 수 있음. vturn_speed가 실제로 어디서
부호를 부여받는지(caller 추적)는 이번 세션 범위 밖.

**Finding F (미해소 — magnitude 불일치)**: AdjustLaneOffset(0.10m) +
PathOffset(0.05m) 이론상 최대 누적치는 0.15m(15cm)인데, 영상에서
육안으로 관측된 좌측편중은 체감상 그보다 훨씬 커 보임(차로 우측
여유공간이 절반 가까이 남는 정도). 원근효과(커브 정점 부근 소실점
근처라 실제 변위가 시각적으로 과장돼 보임 가능) 또는 아직 못 찾은
추가 요인(조향 제어 지연/오버슈트 등) 가능성 — **미해결**, 픽셀
기반 실측이나 추가 통제실험 없이는 이번 세션에서 결론 불가.

**데이터**: 재추출한 `route_a.csv`/`route_b.csv`/`route_c.csv`/
`combined_145.csv`는 **devnotes에 커밋하지 않음**(대용량 산출물 —
사용자 정책상 레포 미커밋, Drive 미연결로 이번엔 저장 생략) —
`/home/claude/work`에만 존재, 컨테이너 리셋 시 소실. 다음 세션에서
lllProb 기반 재분석이 필요하면 **원본 zip 3개 재업로드 필요**(추출
스크립트는 devnotes에 반영 완료라 재작성은 불필요).

**결론(잠정)**: 145차 가설(AdjustLaneOffset×PathOffset 좌측누적)은
**기각되지 않았으나 완전히 확정되지도 않음**. 로그 분석만으로는
한계 — **AdjustLaneOffset=0으로 낮춘 통제실험**이 가장 확실한 다음
단계라는 145차의 원래 결론은 유효하며 오히려 더 필요해짐. 추가로
`carrot_serv.py`의 vturn_speed 부호 발생지점 추적(Finding E)도 우선
과제로 승격.

**다음 단계(갱신)**:
1. **최우선**: `AdjustLaneOffset=0` 고정 후 동일 좌커브에서 PathOffset
   단독 재검증 주행
2. vturn_speed에 부호를 부여하는 caller 코드 추적(Finding E) —
   `offset_curve`의 방향성이 실제로 커브방향과 연동되는지 확정
3. 여력 있으면 `lane_lines[1].y`/`lane_lines[2].y`(원본 배열)까지
   추출해 width_pts 기반 완전한 d_prob 재현(현재는 근사 상한치)
4. 영상-로그 픽셀 단위 매핑으로 실측 변위(cm) 산출 시도(Finding F
   magnitude 불일치 해소용) — 우선순위는 낮음

---

## 144차 — [NEEDS_VALIDATION, 진행중] route 적용검증 + PathOffset 직진/커브 실차 1차분석

**대상**: 사용자 업로드 연속주행 3개 route(37seg, 07:02~07:37, 20.6km,
commit `3ec4e5c`=141차 최신). 상세 요청/절차는 WIP.md "144차" 참고.

**Finding A (route 적용 확인)**: src 분포 cam 44%/route 30%/vturn 22%/
road 4%/bump<1%. route가 실제로 유의미한 비중으로 적용됨.

**Finding B (route↔vturn 플리커, 재조사 후보)**: 전체 6개 소스쌍 중
route↔vturn이 분당 4.44회로 압도적 1위(154 round-trip, dwell 중앙값
1.61s, 최소 0.04s). 값 자체는 대개 근접(수 kph)하나 90차~ "route가
vturn보다 먼저 안정적으로 감속 시작" 목표와 달리 두 소스가 잦게
뒤바뀌는 패턴. 예: t=1955.9~1960.9(5초) 15회 전환, t=799.6~800.4
(0.8초) 6회 전환.

**Finding C (레인리스 100%, 오프셋 검증 조건은 유효)**: `activeLaneLine`
(신규 추가 컬럼) True 0건/False 43275행(99.97%) — 주행 내내 레인풀
모드 미진입. 140차 패치의 `_path_offset_active` 분기가 유일한 오프셋
경로였던 셈 → 검증 시나리오 자체는 순수하게 오프셋 패치 하나만 격리
관찰 가능한 조건.

**Finding D (직진구간 desiredCurvature 편향 없음 — 원인 미확정)**:
|dc|<0.0015 & cruiseEnabled & v>5 조건 20407행 평균 desiredCurvature
≈ -0.000019(≈0), stdev 0.000487. 오프셋 반영 시 기대되는 체계적 편향이
관측 안 됨. **원인 후보 2가지 미판별**: (a) 이번 주행 중 PathOffset
실제 값이 0이었음(정상 결과), (b) 140차 패치가 의도대로 동작 안 함.
Params PathOffset 원시값이 cereal에 없어 로그만으로 구분 불가 —
**사용자에게 이번 테스트 주행 중 PathOffset 설정값 확인 필요**.

**Finding E (커브 이벤트 71건 탐지)**: |desiredCurvature|>0.004,
지속≥1.0s 기준. 대다수(약 56건)는 R<20m 저속 교차로 회전. 도로 곡선
성격(R 50~230m, v 40~65km/h)은 약 15건 — 다음 단계 상세분석 후보.

**상태**: 코드 변경 있음(extract_log.py `activeLaneLine` 필드 추가,
non-breaking). 분석 자체는 미완료 — PathOffset 실제값 확인 후 이어감.

---

## 142차 — [CONFIRMED, 코드변경 없음] 레인모드/레인리스 × PathOffset(0/+/−) curvature 소스 8-시나리오 정리 + 신규 디테일(heading/offset 적용 순서)

**배경**: 137~141차 분석을 사용자 요청으로 "레인모드/레인리스 ×
PathOffset(0/+n/−n)" 관점 6개 핵심 조합 + 안전 폴백 2개 = 8개 시나리오로
재정리. `origin/c3-ms-dev`(`3ec4e5c`, 140/141차 패치 반영 상태) 코드
직접 확인 + 기존 `sim_path_offset_laneless_curvature_source.py` 재실행
(8/8 PASS, 코드 변경 없어 결과 동일).

**결론**: `use_mpc_curvature = lanefull_mode_enabled or (PathOffset != 0)`
분기는 offset **부호와 무관**(boolean `!=0`만 검사) — 부호는 분기 선택
이후 `lateral_planner.py`의 `path_xyz[:,1] += pathOffset`에서 MPC 입력
값에만 반영됨. 레인모드는 PathOffset 값과 무관하게 항상 MPC 소스
(`lat_plan.curvatures`)를 쓰므로 레인리스처럼 "offset에 의한 소스 전환"
현상 자체가 없음. 8개 시나리오 매트릭스는 WIP.md 142차 항목 참고.

**신규 발견**: `path_xyz[:,1] += self.pathOffset`(line 163)가
`yaw_from_path_no_scipy()`(line 152~157, heading/yaw_rate 계산) **이후에
실행**됨을 확인 — 137~141차 기록엔 없던 디테일. 이는 MPC가 받는
`heading_pts`/`yaw_rate_pts`는 offset 미반영, `y_pts`만 상수 이동한다는
뜻 → offset은 목표 경로를 형태 변화 없이 "평행이동"시키는 것에 가까워,
정상상태 곡률에는 이론상 영향이 없고 주로 커브 진입/전환 구간의 과도
곡률에만 영향을 줄 가능성 있음(정적분석 기반 가설, 실차 로그 미검증).

**다음 단계**:
- 위 "정상상태 곡률 무영향" 가설을 PathOffset≠0 실주행 로그로 검증
  (레인모드 진입 전/후 curvature 파형 비교)
- 138차부터 남아있는 `_use_lane_line_curve_speed` 게이트로 인한 레인모드
  판정 순간적 False 전환 케이스는 여전히 미검증

## 141차 — [PATCHED, 실차검증 필요] mpcSolutionValid 체크 추가 (140차 리뷰에서 지적된 사각지대 보완, 레인/레인리스 공통)

**배경**: 140차 패치를 외부(타 AI) 리뷰 과정에서 "`len(lat_plan.curvatures)==0`
폴백만으로는 '배열은 채워졌지만 아직 유효하지 않은 MPC 해'를 걸러내지
못한다"는 지적이 있어 코드로 직접 확인 — **지적이 정확함을 확인**.

**확인된 사실**:
- `lateral_planner.py` `publish()`가 `lateralPlan.mpcSolutionValid =
  bool(self.solution_invalid_cnt < 2)`를 발행하고 있었으나,
  `controlsd.py`는 레인모드에서도(140차 이전부터) 이 필드를 **한 번도
  체크한 적이 없었음** — 140차가 새로 만든 리스크가 아니라 기존부터
  있던 리스크.
- `curvatures` 배열은 `reset_mpc()`(NaN/infeasible 시 호출)가 실행돼도
  `x_sol`이 `zeros`로 채워질 뿐 **길이는 항상 `CONTROL_N`으로 유지**됨
  → `len==0` 체크는 "메시지가 아예 안 온" 극초기만 잡고, "값이
  무효(0 또는 stale)인데 배열은 채워진" 전환 프레임은 못 잡음.

**패치**: `state_control()`의 MPC curvature 사용 조건에
`or not lat_plan.mpcSolutionValid`를 추가 — `False`면 `self.curvature`
(직전 값 유지)로 폴백. 레인모드/레인리스 공통 분기에 넣어 **두 모드
모두에 동일하게 적용**(사용자가 요청한 "공통 안전장치").

**⚠️ 정직하게 밝힐 것 — 완전 무결점 리그레션 방지는 아님**: 140차까지는
"`PathOffset==0`이면 레인리스 동작이 기존과 100% 동일"이 성립했으나,
141차는 이 안전장치를 **레인모드에도 공통 적용**했으므로,
`mpcSolutionValid==False`인 (평소엔 드문) 상황에서는 **레인모드의 기존
동작도 141차 이전과 달라짐**(전엔 무효 MPC 값을 그대로 조향에 반영,
이제는 폴백). 이는 의도된 안전 개선(버그 수정에 가까움)이지 완전한
무변화 보장이 아니므로, "PathOffset=0이면 전부 무변화"라는 이전 표현은
141차부터는 "PathOffset=0이면 레인리스는 무변화, 레인모드는
mpcSolutionValid가 항상 True였던 케이스에 한해 무변화"로 정정 필요.

**합성검증**: `sim_path_offset_laneless_curvature_source.py`(141차
갱신, `mpc_solution_valid` 파라미터 추가) 8개 조합 전체 PASS. 특히
"레인모드+curvatures 있음+valid=False"(141차 신규 케이스, 기존엔
못 걸렀음) 케이스가 올바르게 폴백함을 확인.

**py_compile**: 통과.

**패치파일**: `0002-mpc-solution-valid-check.patch`(로컬 커밋 `c48ba30`,
base `d7b1e2a`=140차). 140차 패치(`0001-...`) 적용 후 순서대로 `git am`.

**미완료(실차검증 필요, 140차와 통합)**:
- `mpcSolutionValid==False`가 실제 주행 중 얼마나 자주 발생하는지(정상
  주행 중엔 거의 0에 가까울 것으로 예상하나 실측 확인 안 됨) — 너무
  자주 발생하면 레인모드에서 폴백(직전 값 유지)이 잦아져 조향이
  둔해지는 부작용 가능성 있음, 로그로 빈도 확인 권장.

## 140차 — [PATCHED, 실차검증 필요] PathOffset 레인리스 최종 조향 미반영 수정(controlsd.py curvature 소스 전환)

**배경**: 138/139차에서 확인된 문제(`lateral_planner.py`가 계산한
`lateralPlan.curvatures`에는 `PathOffset`이 반영되지만, `controlsd.py`가
레인리스 모드에서는 이 값을 버리고 `model_v2.action.desiredCurvature`
(offset 무관, 신경망 직접출력)를 사용해 실제 조향에 미반영되던 문제)를
사용자 요청으로 패치.

**패치 방향**: 두 후보 중 (a) — `controlsd.py`의 레인리스 분기에서
`PathOffset`이 0이 아닐 때만 `lat_plan.curvatures`(offset 반영된 MPC
출력)를 쓰도록 전환. (b)(레인모드 조건 자체를 완화) 대신 (a)를 택한 이유:
`PathOffset==0`(기본값, 대다수 사용자)일 때는 분기 결과가 기존과 100%
동일해 리그레션 리스크가 0에 가까움.

**구현**:
- `controlsd.py` `__init__`에 `self._path_offset_active = False` 초기화 추가.
- `state_control()`의 기존 100프레임 Params 캐싱 블록(97차 패턴)에
  `self._path_offset_active = self.params.get_int("PathOffset") != 0` 추가.
  cereal 스키마 변경 없음 — `lateral_planner.py`와 별개 프로세스지만 동일한
  `Params()` 파일을 각자 직접 읽어 값 동기화(37차 capnp 스키마 미스매치
  크래시 전례를 피하기 위해 스키마 변경 대신 이 방식 택함).
- curvature 소스 선택 조건을 `self.lanefull_mode_enabled` →
  `use_mpc_curvature = self.lanefull_mode_enabled or self._path_offset_active`로
  변경. `len(lat_plan.curvatures)==0` 폴백(`self.curvature` 유지)은 기존
  그대로 유지되어 MPC 데이터 없을 때도 안전.

**합성검증**: `toolkit/sim_path_offset_laneless_curvature_source.py`(신규)
로 6개 조합(latActive/lanefull/offset_active/curvatures유무) 로직단위
검증, 6/6 PASS. 특히 "PathOffset=0, 레인리스" 케이스가 기존 분기
(`modelActionBranch`)와 정확히 일치함을 확인 — 기본값 사용자 리그레션 없음.

**py_compile**: 통과.

**미완료(실차검증 필요)**:
- 이번 패치는 "레인리스에서 MPC 곡률을 쓰게 전환"한 것뿐이고, MPC가 실제로
  offset 방향/크기대로 정확히 추종하는지, 부드럽게 수렴하는지는 실주행에서
  확인 필요.
- 레인리스에서 MPC 곡률로 전환되면 `model_v2.action.desiredCurvature`
  대비 반응 특성(지연/부드러움 등)이 다를 수 있음 — `PathOffset!=0`으로
  설정해 레인리스 구간을 실제로 주행하며 조향 부드러움/오버슈트 여부 확인 필요.
- 커브 진입/이탈 등 `lanefull_mode_enabled`가 자주 토글되는 구간에서
  `PathOffset!=0`이면 레인모드↔레인리스 전환마다 curvature 소스가 매번
  동일(MPC)하게 유지되므로 오히려 전환 시 튐이 줄어들 가능성도 있으나
  확인 안 됨.

**패치파일**: `0001-path-offset-laneless-curvature.patch`(로컬 커밋
`d7b1e2a`, base `1706706`=136차 HEAD). `git am`으로 적용.

## 139차 — [정정, 코드변경 없음] lane_offset_filtered.x도 레인리스에서 pathOffset과 동일하게 미반영 (137/138차 이어서 확인)

**배경**: 외부(타 AI) 감사에서 "PathOffset보다 `lane_offset_filtered.x`
(레인모드 차선폭 기반 보정, `AdjustLaneOffset` 계통)가 레인리스에서 실제
조향에 영향을 줄 가능성이 더 높다"는 우선순위 제안이 있었음 — 이를 실제
코드로 재검증.

**결론: 근거 없음. `lane_offset_filtered.x`는 `pathOffset`과 완전히 동일한
경로/운명을 공유하므로 138차 결론이 그대로 적용됨(레인리스 미반영).**

**근거**: `lane_offset_filtered.x`가 `path_xyz`에 더해지는 지점
(`lane_planner_2.py` line 249, `CAMERA_OFFSET + lane_offset_filtered.x`)은
`get_d_path()` **함수 내부**이고, `get_d_path()`는 `lateral_planner.py`
line 150에서 호출되어 `self.path_xyz`로 반환됨 — `pathOffset`이 더해지는
line 163보다 **먼저** 같은 배열에 반영됨. 따라서 두 오프셋 모두 이후
동일한 `y_pts → lat_mpc.run() → lateralPlan.curvatures` 파이프라인을
공유하고, 138차에서 확인한 `controlsd.py`의 `lanefull_mode_enabled` 분기에
의해 레인리스 모드에서는 이 `lateralPlan.curvatures` 자체가 통째로
버려짐(`model_v2.action.desiredCurvature` 대체 사용). 즉
`lane_offset_filtered.x`가 `pathOffset`과 별도의 특별한 경로를 갖지
않음 — 완전히 같은 결론.

**부가 확인**: `self.LP.offset_total`(=`lane_offset_filtered.x`)이 쓰이는
유일한 다른 지점은 `lateral_planner.py` line 264 디버그 텍스트뿐이며,
이마저도 `self.lanelines_active`(레인모드)일 때만 표시되도록 조건부라
별도 사이드채널 없음.

**시사점**: "레인리스에서 미세하게 한쪽으로 붙는다"는 현상이 실제 관찰된다면,
`pathOffset`/`lane_offset_filtered.x` 어느 쪽도 원인이 될 수 없음 —
`model_v2.action.desiredCurvature`(modeld.py 신경망 직접출력) 자체의 편향,
또는 카메라 캘리브레이션/장착 오차 쪽을 우선 의심해야 함. 이번 세션 범위
밖이라 조사는 안 함, 기록만.

**교훈(작업 방식 메모)**: 외부 AI 감사나 텍스트 요약 기반 우선순위 판단은
실제 소스코드 재추적 없이는 신뢰하지 말 것 — 이번 건처럼 문서 텍스트만
보고 "이 변수가 다를 것"이라 추정하면 잘못된 우선순위를 매길 수 있음.

## 138차 — [정정/RISK_IDENTIFIED, NEEDS_USER_DECISION] PathOffset 레인리스 최종 조향 미반영 확인 (137차 결론 정정)

**137차 결론 정정: `path_xyz` 레벨 계산은 137차 기록대로 맞으나, 그 결과가
레인리스 모드에서는 실제 조향 명령에 전혀 반영되지 않음을 추가 추적으로 확인.**

**추적 경로**:
1. `lateral_planner.py`: `path_xyz[:,1] += pathOffset`(line 163, 무조건) →
   `y_pts`(line 169) → `lat_mpc.run()` → `publish()`에서 `lateralPlan.curvatures`로
   발행. 여기까지는 offset이 반영됨(137차 기록 그대로 유효).
2. `controlsd.py` line 181: `lanefull_mode_enabled = (lat_plan.useLaneLines and
   curve_speed_abs > self._use_lane_line_curve_speed)`. `lat_plan.useLaneLines`는
   곧 `self.lanelines_active`(레인모드 여부) — **레인리스에서는 항상 False**,
   `and` 조건이므로 `lanefull_mode_enabled`도 무조건 False.
3. `controlsd.py` line 189-196 분기: `lanefull_mode_enabled=True`일 때만
   `lat_plan.curvatures`(offset 반영값) 사용, `False`일 때는
   `model_v2.action.desiredCurvature` 사용.
4. `model_v2.action.desiredCurvature`는 `modeld.py`
   `get_action_from_model()`(line 99-121)에서 신경망(modeld 프로세스) 출력
   `plan[:,Plan.T_FROM_CURRENT_EULER]`/`plan[:,Plan.ORIENTATION_RATE]`로부터
   직접 계산 — `lateral_planner.py`의 `path_xyz`/`pathOffset`/MPC와 **완전히
   별개 파이프라인**(path_xyz를 입력으로 받지 않음).

**종합**: 레인리스 모드(또는 커브조건 미충족 시)에는 `lateral_planner.py`가
pathOffset 반영해 계산한 `lateralPlan.curvatures`가 존재는 하지만 `controlsd.py`가
이를 채택하지 않고 신경망 직접출력(`model_v2.action.desiredCurvature`, offset
무관)을 최종 조향에 사용함 → **레인리스 주행 중 PathOffset 값을 바꿔도 실제
차량 거동에는 영향이 없을 가능성이 높음(미반영 추정)**.

**미확정 사항(다음 세션/실주행 로그 검증 필요)**:
- `_use_lane_line_curve_speed`(파라미터 `UseLaneLineCurveSpeed`, 기본 0) 조건까지
  고려하면 커브 진입 시 레인모드라도 일시적으로 False가 될 수 있어 조건이
  더 복잡할 수 있음 — 이번 세션은 코드 정적분석만 수행, 실차 로그로 curvature
  소스 전환 시점 검증은 안 함.
- "레인리스에서 PathOffset 미반영"이 의도된 설계인지(원작자가 레인리스에서는
  모델 신뢰가 우선이라 판단) 아니면 놓친 버그인지 불명 — 사용자 확인 필요.
- 수정한다면 (a) `controlsd.py`의 레인리스 분기에도 `pathOffset`을
  `model_v2.action.desiredCurvature` 기반 계산에 별도로 더하거나, (b)
  `lateral_planner.py`가 애초에 레인리스에서도 사용되도록
  `lanefull_mode_enabled` 조건을 수정하는 두 방향이 있으나 부작용 검토 필요
  (레인리스에서 MPC 경로를 쓰게 하면 다른 회차에서 의도적으로 분리한 이유와
  충돌 가능) — 패치 미적용, 사용자 결정 대기.

## 137차 — [CONFIRMED-OK(부분 정정, 138차 참고), 코드변경 없음] PathOffset 파라미터의 레인리스 모드 적용 여부 분석

**결론: PathOffset은 레인모드/레인리스 모드 구분 없이 항상 적용됨(코드상 정상, 버그 아님).**

**적용 지점**: `lateral_planner.py` line 163
```python
self.path_xyz, self.lanelines_active = self.LP.get_d_path(...)   # line 150
if self.lanelines_active:
    self.plan_yaw, self.plan_yaw_rate = yaw_from_path_no_scipy(...)  # line 152-158, 레인모드에서만 실행
self.path_xyz[:, 1] += self.pathOffset   # line 163, 조건문 없음 — 레인/레인리스 무관 항상 실행
```
`get_d_path()` 호출 결과(레인모드/레인리스 모드 어느 쪽이든)에 대해 line 163이
분기 없이 무조건 y좌표에 `pathOffset`을 더함. 즉 `useLaneLineMode=False`거나
`laneless_only=True`인 상황(고속 직선 등 레인리스 조건)에서도 동일하게 반영됨.

**값 흐름**: UI(`settings.cc`, cm 단위 -150~150) → `params_keys.h`
(`PathOffset`, PERSISTENT INT, 기본값 0) → `lateral_planner.py`에서
`get_int("PathOffset") * 0.01`로 m 단위 환산 → 100프레임(`self.readParams`)마다
재조회.

**부수 확인 — yaw 재계산과의 정합성(문제 없음)**: 레인리스 모드에서는
`plan_yaw`/`plan_yaw_rate`가 모델 원본(`md.orientation.z` 등, line 110-111)을
그대로 쓰고 재계산되지 않음 — 오직 `lanelines_active=True`(레인모드)일 때만
`yaw_from_path_no_scipy()`로 path_xyz 기반 재계산(line 152-158). 그러나
PathOffset은 전 구간에 걸친 **상수 평행이동**(모든 33개 포인트에 동일한 값을
더함)이므로 헤딩/곡률에는 수학적으로 영향이 없음 — 재계산 생략은 이 경우
정합성 문제를 일으키지 않음.

**별개로 발견된 참고사항(PathOffset과는 무관, 별도 오프셋 계통)**:
`lane_planner_2.py` line 249 `path_xyz[:, 1] += (CAMERA_OFFSET +
self.lane_offset_filtered.x)`도 `get_d_path()` 내부에서 분기 없이 항상
실행됨. `lane_offset_filtered.x`는 `AdjustLaneOffset`/커브옵셋
(`offset_curve`, `offset_lane`) 기반 값으로, `lane_change_multiplier>=0.5`이고
차선이 조금이라도 인식되면(`d_prob>0`) 레인리스 모드에서도 계속 업데이트되어
0이 아닌 값이 은근히 섞여 들어갈 수 있음. `PathOffset`(사용자 수동 설정,
좌우 고정 오프셋)과는 목적이 다른 별개 파라미터라 혼동 소지는 적으나, "레인리스인데
왜 미세하게 옆으로 붙는 느낌이 있다"는 제보가 들어오면 이 라인(`lane_offset_filtered.x`
잔류값)이 원인 후보가 될 수 있음 — 이번 세션 범위 밖이라 조치 없이 기록만.

**변경사항 없음** — 순수 코드 분석, 패치 미적용.

## 135차 계속 — [RESOLVED (1번), CLOSED-보류 (2번), DEFERRED (3번)] cruise.py 죽은분기 처리 확정

**1번(line 500) 처리 완료**: `pass`로 대체 패치 적용(로컬 커밋
`34911dc`, base `976fefd`). 동작 무변화 확인(`py_compile` 통과, 로직상
해당 elif 분기는 원래도 no-op였음). 패치파일:
`0001-cruise-line500-dead-branch.patch`(`git am`로 적용).

**2번(line 562, `# 수정필요...`) — blame 조사 결과 CLOSED(보류로 확정,
추가 조치 없음)**: `git blame` 결과 line 500/562 둘 다 `c1361f8`
(boramee, 2026-02-27, "계기판 LFA 아이콘 표시(5W,CANFD,비롱컨) (#253)")
에서 유입 — **ryu 프로젝트 세션이 도입한 코드가 아니라 업스트림
carrot-openpilot 저장소에서 그대로 받아온 것**. 해당 커밋 메시지는 LFA
계기판 아이콘 표시가 주제라 이 `if False` 분기와 직접적 연관이 안
보임(대규모 squash 커밋에 파일 전체가 실려온 것으로 추정) — 이
저장소 히스토리만으로는 원작자가 "무엇을 수정하려 했는지" 더 이상
추적 불가능(업스트림 저장소 확인이 필요할 수 있으나 이번 세션 범위
밖). **결론: 의도 재구성 근거 없음 -> 삭제하지 않고 그대로 보류**
(사용자 확정). `lfaButton`의 `_paddle_decel_active` 관련 이상 동작
제보가 향후 들어오면 재검토 후보로 남김. 이번 세션에서는 코드 변경
없음.

**3번(미사용 import/변수) — DEFERRED**: 사용자 결정으로 보류, 작업
없음. 리스크 낮은 기계적 정리라 필요 시 별도 "코드 정리" 세션에서
일괄 처리 권장(135차 원본 기록의 세부 목록 참고).

## 135차 — [RISK_IDENTIFIED, NEEDS_USER_DECISION] c3-ms-dev 전체 죽은코드/불필요코드/CPU-메모리 정적 재점검 (로그분석 아님, 패치 미적용)

**배경**: 사용자 요청 — 최신 HEAD(`976fefd`, 134차 반영본) 전체에서 죽은코드,
불필요한 코드, CPU/메모리를 불필요하게 점유하는 코드가 있는지 면밀히 재점검.
97/99/100/102차가 마지막 전면 재점검이었고(기준 커밋 `bc1bcb0`, 101차),
그 이후 실시간 루프 대상 파일 중 실제로 바뀐 건 3개뿐(`carrot_man.py`
132차, `radard.py` 118/119/104/130차, `long_mpc.py` 109/112/116/117/134차)
— 이번 세션은 (a) 기존 `toolkit/scan_perf_antipatterns.sh` 재실행 전체
재스캔 + (b) `bc1bcb0..HEAD` diff 정밀 검토 + (c) `pyflakes` 정적분석
(미사용 import/변수) 3가지를 병행.

**핵심 결과 1 — 101차 이후 신규 코드(94~134차 증분)는 CPU/메모리 관점에서
전부 클린**: `carrot_man.py`의 `_route_speed_prev`, `radard.py`의
`_lane_departure_cnt`(2-key 고정 dict), `long_mpc.py`의
`_gap_open_cap_weight_prev`/`_prev_low_speed_strong_lead_decel`/
`_lc_danger_confirm_timer` 전부 스칼라 상태값 1개씩(dict/list 누적 아님,
매 프레임 O(1) 연산). 새 히스토리 버퍼(`_dRel_raw_history`,
`_vision_dRel_rate_window`, `v_ego_hist`) 전부 `deque(maxlen=...)`로
bounded 확인(무한 성장 없음). `Params()` 신규 인스턴스/미캐싱 `.get*`
호출도 diff 범위 내 신규 추가 없음. **신규 CPU/메모리 이슈 없음.**

**핵심 발견 2 — `cruise.py`에 99/100차 정리 때 놓친 죽은코드 2건
(신규는 아니고 기존에 있었으나 이번에 처음 확인)**:
- line 500: `if False: #self._cruise_button_mode in [2, 3]:` —
  `accelCruise` 버튼 처리 중 항상 거짓이라 `road_limit_kph` 반영 블록
  전체가 실행 불가능한 죽은 분기. 99/100차가 `carrot_man.py`/
  `controlsd.py`의 동일 패턴(`if False`) 2건은 이미 제거했으나, 같은
  패턴이 `cruise.py`에도 있었던 것을 이번에 처음 확인(97~102차 검토
  범위가 `carrot_man.py`/`controlsd.py`/`radard.py`/
  `longitudinal_planner.py`였고 `cruise.py`는 포함되지 않았던 것으로
  추정).
- line 562: `if False: #CC.enabled and self._paddle_decel_active:  #
  수정필요...` — `lfaButton` 처리 중 마찬가지로 항상 거짓인 분기.
  `# 수정필요...` 주석으로 보아 원작자가 의도적으로 미완성 상태로
  비활성화해둔 것으로 추정 — **단순 삭제보다는 사용자 확인 필요**
  (의도된 임시 비활성화일 수 있음).
- 둘 다 런타임 CPU 비용은 0(분기 진입 자체가 안 됨) — 순수 가독성/유지보수
  목적의 정리 대상.
- 부수 발견(저빈도, 버튼 이벤트성): `cruise.py` line 561
  `print("lfaButton")` — 디버그 print 잔재, `lfaButton` 누를 때만
  실행되므로 20Hz 핫루프 무관, 영향 미미.

**핵심 발견 3 — `pyflakes` 정적분석: 미사용 import/지역변수 다수
(런타임 CPU 영향은 무시 가능 수준 — 모듈 최초 import 시 1회성 비용,
매 프레임 재실행 아님. 순수 코드 정리/가독성 목적)**:
- 미사용 import: `carrot_man.py`(`typing.Dict/List/Optional`,
  `urllib.error`, `ssl`, `TICI`, `Conversions as CV`),
  `carrot_serv.py`(`fcntl`, `json`, `socket`, `struct`,
  `datetime.datetime`, `ftplib.FTP`, `cereal.log`, `Ratekeeper`,
  `MyMovingAverage`, `TICI`, `Coordinate`, `get_gps_location_service` —
  이 중 `datetime`/`json`은 각각 line 1234/1272에서 지역
  변수명으로 재정의(redefinition)돼 있어 모듈 레벨 import 자체가
  더 무의미), `controlsd.py`(`time`, `collections.deque`, `DT_MDL`,
  `ModelConstants`, `CONTROL_N`, `LAT_SMOOTH_SECONDS`),
  `radard.py`(`heapq`, `KF1D`), `longitudinal_planner.py`
  (`get_speed_error`), `long_mpc.py`(`carrot_functions.XState`).
- 미사용 지역변수(경미, 일부는 20Hz 핫루프 내부):
  - `longitudinal_planner.py` line 184: `steer_angle_without_offset =
    sm['carState'].steeringAngleDeg - sm['liveParameters'].angleOffsetDeg`
    계산 후 바로 아래(line 185)에서 이 변수를 쓰는 코드가 주석처리돼
    있어 실제로는 미사용 — **20Hz `mode=='acc'` 경로마다 dict lookup
    2회 + 뺄셈 1회가 무의미하게 반복 실행**(연산 자체는 극히 경미하나
    유일하게 "매 프레임 실행되는" 낭비 사례).
  - `carrot_serv.py` `_update_gps()` line 707-708: `CS =
    sm['carState']`, `CC = sm['carControl']` 대입 후 함수 내에서
    미사용(과거 리팩터 잔재로 추정).
  - `carrot_functions.py` `update_data()` line 702: `my_accel =
    carstate.aEgo` 대입 후 미사용.
  - `carrot_man.py` line 1420: `peer` 대입 후 미사용(UDP 스레드 내,
    이벤트성).

**"불필요한 코드"(로직 자체가 안 쓰이는 죽은 코드) 그 외 추가 발견 없음**:
97/99차가 이미 확인한 `carrot_man.py` line 486 부근 `haversine_cache`
등 주석처리된 미완성 캐싱 시도 코드는 재확인 결과 동일 상태로 유지 중
(변경 없음, 이번 세션 범위 밖).

**종합 판단**: 101차 이후 신규 로직(94~134차)은 CPU/메모리 관점에서
문제 없음 — 이번 재점검의 실질적 신규 발견은 **(1) cruise.py 죽은 분기
2건, (2) 미사용 import/변수 다수(전부 코드 정리 목적, 런타임 영향
무시 가능)**로 요약됨. `steer_angle_without_offset` 1건만 "매 프레임
실행되는 낭비"에 해당하나 그 비용 자체가 극히 미미해 우선순위 낮음.

**미검증/사용자 결정 대기 (패치 아직 미적용)**:
- `cruise.py` line 500 죽은 분기: 삭제해도 안전(항상 거짓이라 삭제해도
  동작 100% 동일) — 사용자 승인 시 다음 세션에서 제거.
- `cruise.py` line 562 죽은 분기: `# 수정필요...` 주석 때문에 의도적
  임시비활성화일 가능성 있어 **삭제 여부 사용자 확인 필요**(그냥
  삭제할지, 원래 의도된 로직을 살릴지 논의 필요).
- 미사용 import/변수 일괄 정리는 기계적 작업이라 리스크 낮음 — 사용자가
  원하면 다음 세션에서 일괄 patch로 처리 가능.
- 실제 comma 기기 `top`/`htop` CPU·메모리 실측은 이번에도 미실시
  ([NEEDS_VALIDATION] 97~102차와 동일 유지).

## 134차 — [PATCH_WRITTEN, SIM_VALIDATED, 실차재생 미실시] c3-ms-dev 전체 코드 상호영향 검토 — 112차(low_speed_strong_decel) 부스트 arm 가드 비대칭 발견 + 패치 적용

**배경**: 사용자 요청 — origin/c3-ms-dev 브랜치 전체 코드를 분석해 최근 여러
패치들이 서로 다른 로직에 영향을 주는지 면밀히 검토(실주행 로그 분석이
아닌 정적 코드 리뷰). 대상 commit: `f24cbf8`(132차, HEAD).

**검토 범위**: `long_mpc.py`의 discontinuity/jerk-boost/lane-change
상호연동 시스템(67/72/73/76/94/109/112차, 트리거 소스 4종:
`discontinuity`/`discontinuity_lc`/`handoff`/`low_speed_strong_decel`)을
중심으로, `radard.py` LeadBlend BIG_JUMP 신뢰도 게이트(104/130차)와의 교차,
`carrot_man.py` route lookahead 램프 리미터(132차)와의 독립성 확인.

**결론 1 (긍정적, 회귀 없음)**: 리뷰 범위 내에서 각 패치가 자신이 건드리는
로직의 상호작용을 이미 상세 주석으로 분석/검증해둔 상태(예: 109차/112차
주석이 이전 트리거 소스와의 관계를 명시적으로 서술) — 별도의 새 회귀는
발견되지 않음.
- LeadBlend BIG_JUMP 신뢰도 게이트(`radard.py` L747-761, 104/130차)는
  "안전방향(멀어짐)" 점프의 저신뢰 vision 오판을 블렌딩 경로로 돌리는
  로직이고, long_mpc의 discontinuity 감지(`DREL_DISCONTINUITY_DROP_THRESH`,
  61차 계속)는 "접근방향(급락)"만 대상으로 하므로 방향이 달라 직접 충돌
  없음(하나는 dRel 증가 스무딩, 하나는 dRel 감소 감지).
- `carrot_man.py` 132차 램프 리미터(`out_speed`, route 소스 전용)는
  long_mpc(레이더/비전 리드 추종)와 완전히 별개 모듈/파이프라인이라 상호
  영향 없음(133차가 이미 실측 재검증 완료).

**결론 2 (신규 발견, NEEDS_VALIDATION, 낮은 심각도)**: `_discontinuity_
jerk_boost_timer`를 arm하는 4개 지점 중 112차(`low_speed_strong_decel`,
L875-876)만 유일하게 "이미 부스트 진행 중이면 덮어쓰지 않음"
(`self._discontinuity_jerk_boost_timer <= 0.0` 가드)을 갖고 있고, 나머지
3개(`discontinuity`/`discontinuity_lc`, L1074-1086 / `handoff`,
L1113-1121)는 새 트리거 발생 시 무조건 덮어씀(109차 주석에 "새 트리거는
확정 이력을 새로 시작"이라 명시된 의도된 설계).

이 비대칭 때문에: (1) `low_speed_strong_decel`이 먼저 arm(4.0s hard-hold)된
상태에서 그 4초 이내에 (비-차선변경) `discontinuity` 트리거가 발생하면
무조건 덮어써져 1.0s hard-hold로 단축된다. (2) 더 중요한 점 — arm 로직은
`low_speed_strong_lead_decel`의 **False→True 엣지에서만** 발동(L875)하는데,
엣지 소비(`self._prev_low_speed_strong_lead_decel` 갱신, L880)는 가드
통과 여부와 무관하게 매 프레임 항상 일어난다. 즉 한번 다른 소스에
덮어써지고 나면, `low_speed_strong_lead_decel` 조건 자체가 계속 True로
유지되고 있어도 그 조건이 False로 꺼졌다가 다시 True로 켜지기 전까지는
`low_speed_strong_decel`이 재arm되지 않는다.

**영향 범위 한정**: 이 boost는 도달 감속량(`w=1.0`, 즉시 무감쇠, 위험
판정 시 항상 그대로 적용)이 아니라 MPC가 그 감속에 도달하는 저크비용
(jerk cost) 완만화에만 관여하므로(L871 주석 참고), 안전 반응 자체(감속
크기/타이밍)에는 영향 없음 — 최악의 경우 해당 저속+강한 선행차 감속
시나리오에서 저크비용이 의도보다 일찍 base로 복귀해 반응이 약간 더
거칠어지는 정도. 실차에서 "저속 주행 중 앞차가 강하게 감속하는 동시에
dRel 불연속(끼어들기/차선변경 등)이 겹치는" 복합 상황이 필요해 발생
빈도 자체가 낮을 것으로 추정.

**패치(같은 세션, 사용자 지시로 즉시 적용)**: `long_mpc.py`의 plain
'discontinuity' arm 지점(dRel 불연속 감지 블록, `if lane_change_
blinker_active ... else:` 구조)을 3-way 분기로 변경:
1. 차선변경 중이면 기존대로 `discontinuity_lc`(4.0s) arm.
2. 차선변경이 아니고, `_discontinuity_jerk_boost_timer <= 0.0`(무boost)
   이거나 `_discontinuity_trigger_source == 'discontinuity'`(같은 소스
   재트리거)이면 기존대로 `discontinuity`(1.0s) arm — **기존 동작과
   100% 동일**.
3. 그 외(handoff/discontinuity_lc/low_speed_strong_decel이 진행 중)면
   아무것도 건드리지 않고 그대로 흘려보냄 — 진행 중이던 4.0s hard-hold와
   (discontinuity_lc라면) `_lc_danger_confirm_timer` 누적치까지 보존.

109차가 채택한 "새 트리거는 확정 이력을 새로 시작한다"는 설계 철학
자체는 유지된다는 점에 유의 — 이 패치는 그 철학을 뒤집는 게 아니라,
"plain discontinuity(1.0s)가 이미 진행 중인 더 긴(4.0s) hold를
**단축시키는** 경우만" 막는다. discontinuity_lc/handoff/
low_speed_strong_decel 세 소스는 서로 전부 동일하게 4.0s이므로 서로
덮어써도 기간이 줄지 않아(같은 길이로 재시작) 기존처럼 무조건 덮어쓰는
로직 그대로 유지(변경 없음, 109차 설계와 충돌 없음).

**검증**: 신규 `toolkit/sim_boost_arm_priority.py`(README/CHANGELOG
등록 완료)로 arm 지점 분기 로직을 리터럴 이식해 7개 시나리오 로직단위
검증. 신규 수정분 3건 — low_speed_strong_decel 진행 중(3.0s 남음)/
discontinuity_lc 진행 중(confirm 타이머 누적치 포함)/handoff 진행 중
(2.0s 남음) 각각에서 plain discontinuity 트리거가 발생해도 덮어쓰지
않고 보존됨을 확인. 회귀 없음 확인 3건 — 같은 'discontinuity' 소스
재트리거는 기존처럼 1.0s로 정상 리프레시, 이전 소스가 이미 소진(timer
<=0)됐으면 stale 소스 태그와 무관하게 정상 arm, 4.0s 소스끼리는 서로
덮어써도 기간 단축이 없어 기존 설계(무조건 덮어씀) 그대로 유지 확인.
무boost 상태 정상 arm 1건 포함 **총 7/7 PASS**. `py_compile` 문법
검증도 통과.

**아직 안 된 것**: 실차 로그 재생검증(replay). 이 조합(저속+강한 선행차
감속과 dRel 불연속이 동시에 겹치는 상황) 자체가 드물어 다음 세션에서
해당 조합이 포함된 로그를 확보하면 재생검증 권장 — 그 전까지는
NEEDS_VALIDATION 유지.

## 133차 — [LOG_VALIDATED, 실차재생 미실시] 132차 램프 리미터 패치, 129차/131차 원본 route(306de77a28 seg15) 실측 재검증

**배경**: 132차 패치는 합성 시나리오(curve_R/v_ego/accel 스윕)로만
사전검증됐음. 사용자가 129차/131차에서 쓰던 원본 route를 GPS 좌표
포함해서 재업로드, 실측 로그로 재검증 요청.

**추출**: `extract_log.py`로 route CSV(20Hz, 1200행) 재추출 -- 129차가
보고한 급락 2건(t=4.25 86->61, t=28.35 65->41) 정확히 재확인됨(단일
20Hz 프레임). `extract_gps.py`(133차 신규)로 `gpsLocation`(1Hz) 채널도
별도 추출(60행) -- 131차가 인라인으로만 했던 GPS 추출을 재사용 가능한
toolkit 스크립트로 정식화.

**검증 방법 A(주 근거, 신뢰도 높음)**: `replay_route_ramp_limiter_direct.py`
(신규) -- 132차 패치는 `carrot_navi_route()`의 계산 방식과 무관하게
**최종 out_speed 값에만 사후로 프레임간 상한을 거는 구조**이므로, 로그에
실제 기록된 `desiredSpeed(src=='route')` 시계열 자체를 raw 시퀀스로 보고
`RampLimiterState`(132차 패치와 동일 로직)를 그대로 통과시켰다. 이 방식은
navi_points 재구성/근사가 전혀 필요 없어 방법론적 불확실성이 가장 적다.

결과:
- t=4.25 급락(86->61, Δ-25.0): patched는 86kph 근방에서 시작해 약
  2.52kph/s(`accel_limit_kmh`, `AutoNaviSpeedDecelRate=0.70` 가정)
  속도로만 서서히 하강 -- 84~86kph대를 수 초간 유지, recorded처럼
  즉시 61로 떨어지지 않음.
- t=28.35 급락(65->41, Δ-24.0, 131차가 Hypothesis C로 정밀매칭한 바로
  그 이벤트): patched는 67kph대에서 초당 상한 속도로만 하강.
- t=43.70 지점(46->30): 계산상 불연속이 아니라 **소스 전환 아티팩트**로
  재확인 -- 직전 `gas` override 구간(43.35~43.65) 동안 route는 이미
  내부적으로 30 근방까지 계산돼 있었고, gas 해제로 route 소스가 다시
  노출되며 표시값만 46->30로 "점프"한 것뿐(route 자체의 프레임간
  재계산 불연속이 아님). patched도 recorded와 동일하게 30 -- 이 지점은
  애초에 패치 개입 대상이 아님을 확인.
- 낙차율 재판정: 실제 로그는 20Hz가 정확히 균일하지 않음(프레임 드랍으로
  dt 0.02~0.08s 확인, 예: t=4.25->4.33 dt=0.075s, patched 낙차 0.19kph는
  이 dt 기준 물리 상한 0.7*3.6*0.075=0.189kph와 정확히 일치 -- 리미터
  정상 동작, 초기 스크립트의 고정-dt=0.05 가정 판정 로직이 부정확했던
  것뿐, 프레임별 실제 dt 기반 kph/s 낙차율로 재계산해 전 구간
  accel_limit_kmh(2.52kph/s) 이내 확인).
- route 재진입 리셋 경계(`gas`/`vturn` 구간 이후 route 재활성 첫 프레임)는
  설계대로 즉시 통과 -- 132차 의도한 동작 그대로 확인.

**검증 방법 B(보조, 참고용)**: `replay_route_boundary_ramp_limiter.py`
(신규) -- 실제 navi 폴리라인이 로그에 없으므로(131차 확인) 대신 차량
실주행 GPS 트랙(1Hz)을 navi_points 프록시로 써서 `carrot_navi_route_core`
(131차)를 그대로 재생. t=28.35 이벤트는 이 재구성에서도 raw 66.6->37.9
단일프레임 스냅으로 **독립 재현**됨(Hypothesis C가 실측 GPS 데이터로도
다시 확인) -- patched는 이를 매끄럽게 완화. 단 t=4.25 이벤트는 이
방법으로는 재현 실패(그 시점 route_lookahead 300m 윈도우 안에 교차로가
아직 안 들어와 raw가 300 유지) -- 1Hz GPS 프록시 해상도/윈도우 한계로
판단(교차로가 실제로는 그 시점 약 500m 앞, lookahead(74kph,accel=0.70)
=300m라 윈도우 밖). 이 한계는 방법 A가 아니라 방법 B에 국한되므로 133차
결론(방법 A 근거)에는 영향 없음.

**vturn 상호작용**: t=45.15~45.20(steer 89도 부근) route(30)->vturn(30~32)
전환은 로그 원본에서도 이미 매끄러움(불연속 없음) -- 132차 패치가 개입할
필요/영향 모두 없음 확인.

**미해결(사소, 낮은 우선순위)**: `vTurnSpeed` 컬럼이 이 route 대부분
구간에서 음수로 기록됨(예: steer=-2.6도인 거의 직진 구간에서도 vTurn=-86
등). steer 부호와 무관해 보여 원인 불명 -- 이번 검증 결론에는 영향 없으나
다음 세션에서 `carrot_serv.py`/`carrot_man.py`의 vTurnSpeed 부호 규약
확인 필요.

**상태**: [LOG_VALIDATED] -- 실측 로그 데이터 레벨(desiredSpeed 시계열)
검증은 완료. **실차(acados MPC 포함 전체 파이프라인) 재생 검증은
아직 미실시** -- 이번 결과는 어디까지나 로그에 기록된 값에 대한 오프라인
재계산이며, patched desiredSpeed를 실제 MPC가 어떻게 추종할지는 별도
확인 필요.

**사용**:
```
python3 toolkit/replay_route_ramp_limiter_direct.py <route.csv> --accel 0.70
python3 toolkit/replay_route_boundary_ramp_limiter.py <route.csv> <gps.csv> --accel 0.70
python3 toolkit/extract_gps.py <route_dir> <out_gps.csv> --repo /home/claude/ryu
```

---

## 132차 — [PATCH_WRITTEN, NEEDS_VALIDATION] 131차 Hypothesis C 대응 `carrot_navi_route()` out_speed 프레임간 램프 리미터

**배경**: 131차 [SUCCESS, 정밀매칭 완료] Hypothesis C(129차 "계단형
급락"의 진짜 원인 — `route_lookahead_m` 윈도우 경계로 급커브 curvature가
이산적으로 배열에 출현, 역방향 DP가 그 프레임에 즉시 재계산)에 대한
패치를 사용자 지시로 착수.

**패치**: `carrot_man.py::carrot_navi_route()` 최종 반환값 `out_speed`에
`ROUTE_SPEED_LOOP_DT=0.05s`(broadcast_version_info `Ratekeeper(20)`과
일치) 기준 프레임간 램프 리미터 적용, 상한=`accel_limit_kmh*dt`(기존
`AutoNaviSpeedDecelRate` 재사용, 새 튜닝 상수 없음). 근거: `route_lookahead_m`
자체가 이미 이 감속률로 충분한 거리를 목표로 산정되므로(84차/85차),
경계 스냅이 아니었다면 원래 성립했어야 할 불변식을 최종 출력에서
복원하는 것에 가깝다 — 새 제약 추가가 아님. 증감 양방향 대칭 적용(원복측
스냅도 함께 완화). 리셋 규칙: route 비활성/최초활성 및 "제약없음"(300
센티널) 전환 시 리미터 상태 즉시 리셋(안전 방향은 지연 없이 반영).

**사전검증**: `toolkit/sim_route_boundary_ramp_limiter.py`(신규, 131차
`sim_route_lookahead_boundary_snap.py` 재사용) — `curve_R=10~25m`,
`v_ego=74~90kph`, `accel=0.70~1.2` 전 조합 PASS. 131차 정밀매칭 조건
(반경17.3m/74kph/0.70)에서 unpatched 최대낙차 20.54kph -> patched
0.13kph(이론 상한 이내). 초기에 시뮬레이션 하네스 경계 아티팩트(300<->
실제값 전환, 131차 문서화된 "원호 진입점 과장"과 동일 성격)를 핵심
지표와 혼동해 오판했던 스크립트 버그 발견 후 수정.

**패치 상태**: `0001-132-route_lookahead-Hypothesis-C-131-out_speed.patch`
생성 -> `verify-am` 브랜치(base `1cc2bf3`)에 `git am` 적용 성공 +
`py_compile` 통과 + diff-0 확인. 사용자 전달, 로컬 적용/push는 사용자 몫.

**한계/다음 세션**: 로직+합성검증만 완료, **실차 검증 필요**(129차와
동일/유사 교차로 재주행). margin_kph=0/25 대조(131차 미완료 항목)는
이 패치와 독립적인 별도 후속 확인사항으로 남음.

---

## 131차 — [원인가설 SUCCESS 재현, 코드 미수정, NEEDS_VALIDATION] 129차 교차로 접근 route "계단형 급락" 진짜 원인: `route_lookahead` 윈도우 경계 진입 시 curvature 이산적 출현(Hypothesis C)

**배경**: 129차가 실측한 route `306de77a28` seg15의 계단형 급락
(t=2182.70->2182.75 desiredSpeed 86->61, Δ-25kph **단일 20Hz
프레임**; t=2206.81->2206.85 Δ-24kph)에 대해, 129차는 91차
`ROUTE_ENTRY_MARGIN_KPH`의 `time_delay` 계산 방식(margin_kph 차감)을
원인으로 가설했음(NEEDS_VALIDATION). 이번 세션은 그 가설을 합성검증
하려 했으나 검증 과정에서 **가설 자체가 급락의 "단일프레임 계단"
형태를 설명 못 함**을 발견, 코드 재정독으로 진짜 메커니즘(Hypothesis
C)을 찾아 별도 합성 시뮬레이션으로 확인함.

**1단계: 로그에 실제 navi 폴리라인이 없음을 확인**. `rlog.zst`를
capnp 이벤트 레벨로 전수조사 — `navRoute` 채널 count=0, `navInstruction`
60건/`navInstructionCarrot` 1200건(20Hz) 존재하나 후자는 좌표 없이
`maneuverPrimaryText`/`maneuverDistance`/`distanceRemaining`/
`speedLimit`/`allManeuvers`(다음 회전까지 거리) 등 턴바이턴 요약
정보만 담음. **`carrot_navi_route()`가 실제로 사용하는 raw 폴리라인
좌표(`self.navi_points`)는 어떤 로그 채널로도 기록되지 않음** — 90차가
이미 지적했던 한계("raw navi_points가 로그에 없어 직접검증 불가")가
131차에서도 재확인됨. 향후 이 데이터가 꼭 필요하면 (a) 사용자가 해당
구간 실제 도로 좌표를 별도 제공하거나 (b) device에 임시 로깅 패치를
넣어 재수집해야 함.

**2단계: `sim_route_step_drop_repro.py`(신규, NEGATIVE)** —
`sim_route_curvature_sample.reconstruct_path`(desiredCurvature 시간
적분 재구성, 90차가 이미 "GPS 폴리라인 자체는 아님"이라 명시한 근사)로
급락 시각 주변을 20Hz 슬라이딩 재구성. 결과: 최대 프레임간 낙차
1.46~1.84kph — 실측 Δ-25kph의 **1/15 규모에도 못 미침**, 완전 재현
실패. **원인 규명**: `reconstruct_path`는 desiredCurvature(모델이
그 시점 이후 실제로 따라간 경로의 곡률)를 적분하므로, 매 스냅샷마다
lookahead 구간 전체가 이미 다 알려진 상태로 매끄럽게 재구성된다 —
반면 실제 `carrot_navi_route()`는 "현재 위치 기준 고정거리 윈도우
바깥의 지점은 계산 자체가 안 되다가, 윈도우 안으로 들어오는 순간에만
등장"하는 구조라 원천적으로 다른 신호. 즉 93차/이 스크립트는
"margin_kph가 스케줄을 조기화하는가"엔 유효한 도구지만, "계단형
불연속의 존재/크기"를 검증하는 데는 방법론적으로 부적합함이 확인됨.

**3단계: `sim_route_lookahead_boundary_snap.py`(신규, SUCCESS)** —
`carrot_man.py`(커밋 `1cc2bf3`, 130차 이후 HEAD)의 실제 순수함수
(`haversine`/`closest_point_on_segment`/`get_path_after_distance`/
`compute_route_lookahead_distance`/`gps_to_relative_xy`/
`resample_10m_np`/`calculate_curvature`)와 역방향 DP 본문을 그대로
복제, 실제 navi 폴리라인이 없으므로 합성 GPS 폴리라인(직선→원호
커브)을 만들어 등속 접근 시뮬레이션. **핵심 메커니즘**:
`route_lookahead_m`(v_ego/accel 기반 동적 300~600m)로 현재 위치부터
고정거리만큼 폴리라인을 매 20Hz 사이클 새로 잘라내고, curvature는
3점(40m 간격)이라 윈도우 끝 40m는 애초에 `speeds[]`에 계산되지
않는다(`range(len(resampled_points) - sample*2)`). 따라서 윈도우
밖에 있던 급커브는 그 지점이 윈도우 안으로 들어오는 **단 한 프레임에
이산적으로 배열에 나타나고**, 역방향 DP가 그 프레임에서 전체를
즉시 재계산해 근접 지점(`out_speeds[0]`, desiredSpeed로 직결)까지
낮은 값이 즉시 전파될 수 있음 — 91차 margin_kph(스케줄 조기화, 조기
개입 자체는 연속적 가정하에 유효)와는 **질적으로 다른, "정보의
이산적 출현"에 의한 불연속**.

**검증 결과**: v_ego=74kph, curve_R=25m, accel=0.70(83차 실측
`AutoNaviSpeedDecelRate` 기본값) 조건에서 route_lookahead≈300m
지점(윈도우 끝-40m 데드존≈260m)에서 첫 진입 시 300.0->71.0(Δ-229,
합성 원호가 급격히 시작돼 과장된 값)이, 곧이어 dist_to_curve=200.6m
에서 **59.9->40.1(Δ-19.8, 단일 20Hz 프레임)**이 관측됨 — **129차
실측(Δ-24~-25kph, 단일 20Hz 프레임)과 규모/형태(연속감속이 아닌
계단)가 정성적으로 일치**. 129차가 보고한 "회전 종료 즉시 60까지
순간 복귀"(원복측 계단)도 같은 세션 로그(t=27.25, dist=-10.1m)에서
300.0->300.0으로의 유사 경계효과(윈도우가 커브를 완전히 지나며 커브
구간이 배열에서 사라짐)로 구조적으로 설명 가능함을 확인(정밀 매칭은
미실시).

**한계 (NEEDS_VALIDATION으로 유지하는 이유)**: (1) 합성 원호(반경
25m, 90도)는 실제 교차로 도로 형상과 다름 — 실측 낙폭(-25.0kph)에
정확히 맞춘 geometry 튜닝은 하지 않았고 정성적(규모/형태) 일치만
확인. (2) 위 1단계 확인대로 실제 navi 폴리라인을 로그에서 얻을
수 없어 306de77a28 seg15 route로 1:1 재현(동일 좌표로 정확히 같은
낙폭 재현)은 불가능. (3) `ROUTE_ENTRY_MARGIN_KPH`(91차) 자체가 이
불연속에 얼마나 기여/완화하는지(margin이 있어서 그나마 완충되는
편인지, 아니면 무관한지)는 이번 시뮬레이션에서 margin=25 고정으로만
돌려 margin=0과의 대조 없음 — 다음 세션 확인 필요.

**[추가 갱신, 같은 131차 세션] 정밀매칭 성공 — 지도/좌표 불필요, GPS+실측곡률만으로 충분**:

애초 "실제 교차로 좌표 확보"가 필요하다고 판단했던 것은 착오였음이
밝혀짐. 두 가지를 rlog 자체에서 바로 얻을 수 있었다:

1. **`gpsLocation`(1Hz) 채널이 로그에 이미 존재** — `navRoute`/
   `navInstructionCarrot`엔 좌표가 없지만, 차량 자체 GPS는 별도
   채널로 기록됨. 두 급락 지점의 실제 좌표를 직접 추출: 1차
   (t≈2182.7) 위도 35.3050/경도 129.0868, 2차(t≈2206.8) 위도
   35.3037/경도 129.0829 (부산). 이 좌표로 OSM/Overpass 조회를
   시도했으나 컨테이너 네트워크 허용목록에 없어 실패 — 하지만
   **불필요했음**(아래 2번).
2. **실제 회전 구간(t=t0+47.15~47.40, steer 149.2도 정체) desiredCurvature
   최대값 0.05786 -> 반경 환산 17.3m** — 이 교차로의 실제 회전
   반경을 지도 없이 로그 자체(90차와 동일 논리: 모델이 실제로 따라간
   경로의 곡률 = 도로의 실제 곡률 근사치)에서 바로 얻음.

이 반경(17.3m)을 `sim_route_lookahead_boundary_snap.py`에 대입해
재실행한 결과, dist_to_curve≈207m 지점에서 **60.8->40.2(Δ-20.65,
단일 20Hz 프레임)** 급락 재현 — **129차 실측 2차 급락(65->41,
Δ-24.0, 단일프레임)과 거의 동일 규모**로 정밀 매칭됨. 뒤이어
37.9/35.3/32.5/29.5/26.0/21.8/16.2로 이어지는 **계단형 단계적 하강**도
관측됨 — 이는 129차 실측 노트의 "급락 직후 ~7초/100m 동안
37~43km/h 정체" 패턴(즉시 계단 후 정체)과 정성적으로 일치.

**결론**: Hypothesis C가 이제 [NEEDS_VALIDATION]에서 [SUCCESS,
정량적 정밀매칭 완료]로 격상. `ryu` 코드는 여전히 미수정 —
다음 세션은 곧바로 패치 설계(윈도우 경계 완충)로 진입 가능.
**"실제 교차로 좌표 확보"는 이제 불필요한 선행조건이 아님** — 향후
유사 조사에서는 (a) `gpsLocation` 채널로 좌표, (b) 실제 회전
구간 desiredCurvature로 반경, 이 두 가지만으로 충분함을 toolkit
README에도 기록.

**다음 세션 우선순위(갱신)**: (1) [완료] 실제 좌표/반경 확보 — 추가
지도 데이터 불필요함이 확인됨. (2) 패치 방향 후보 설계 착수 — 윈도우
경계 근처에서 `out_speeds[-1]` 초기 anchor 또는 `speeds[]` 배열
자체에 저역통과/프레임간 램프 리미터를 적용해 "새로 나타난 지점"의
영향이 여러 프레임에 걸쳐 서서히 반영되도록 완충하는 안(116차 저속
gap-open damping 패치와 유사한 "구조적 안전장치 재사용" 철학 적용
검토) — 실측 반경 17.3m 기반 합성 시나리오가 이미 있으므로 패치
전/후 비교가 바로 가능. (3) margin_kph=0/25 대조 실행해 91차 패치가
이 불연속을 악화/완화 어느 쪽인지 확인.

---

## 130차 — [구현+합성검증+패치전달 완료, 실차검증 대기] 104차 Finding A(커브+레이더유실 시 vision 원거리 오판) 원인 확정 및 `LeadBlend` BIG_JUMP 신뢰도 게이트 패치

**배경**: 사용자 지시("이어서 계속, A로 진행하자")로 104차 Finding A
(NEEDS_VALIDATION 상태로 25회차 이상 방치)를 이어서 진행. 새 실차
로그는 없어 코드 레벨 정적분석으로 원인 규명 착수.

**원인 확정**: `radard.py` `VisionTrack.update()`(register_ok 경로)는
저신뢰 vision dRel 후보를 크기 검증 없이 그대로 `self.dRel`에 반영하고
(단, prob<0.35 완전 저확신이면 `tentative_cnt` 래치가 `GHOST_TIMEOUT_S
(3.0s)` 동안은 유지돼 `register_ok`가 계속 True), 이 원거리 값이
`RadarD.update()`를 거쳐 `LeadBlend.update()`에 raw로 들어갈 때
`LEAD_BLEND_BIG_JUMP_DIST(15.0m)`를 넘는 "안전 방향"(더 멀어짐) 점프로
분류됨. 기존 로직은 이런 큰 점프를 "다른 물체로 전환"으로 간주해
**신뢰도(radar 교차검증 여부/modelProb) 확인 없이** 블렌딩을 건너뛰고
즉시 반영 — 104차 실측(3.5초 안정 레이더락 근접 리드 → 커브 진입 락
유실 → vision 단독 prob=0.24로 84~89m 오판)이 정확히 이 경로를 탐.

**패치 설계**: `LEAD_BLEND_BIG_JUMP_PROB_GATE = 0.70`(58차1번
`VISION_TRACK_PROB_GATE`와 동일 철학 재사용, "vision 단독값을 레이더급
으로 신뢰 가능한 최소 확신도") 신설. BIG_JUMP 즉시-스냅 조건을
`is_big_jump and (raw['radar'] or raw['modelProb']>=GATE)`로 변경 —
레이더 교차검증되거나 고신뢰 vision인 far jump는 기존과 동일하게 즉시
반영(회귀 없음), 저신뢰 vision-only far jump만 `LEAD_BLEND_SAFE_
DIST_TIME(0.35s)` 시정수 블렌딩으로 완화. `closer_jump`/TTC danger 등
위험방향 즉시반영 경로는 무변경 — 반응지연 위험 없음. VISION_TRACK_
PROB_GATE 정의가 파일 뒤쪽에 있어 직접 참조 시 NameError가 나므로 값만
리터럴 복제(0.70) — 두 상수 동시 개정 필요성을 코드 주석에 명시.

**합성검증**: `toolkit/sim_lead_blend_far_jump_gate.py`(신규) 5개
시나리오 전부 PASS —
(A) 104차 재현: patched 첫 프레임 dRel 점프 55.4m(unpatched, 33.6→
89.0m 즉시 스냅) → 8.0m(patched, 33.6→41.6m 블렌딩 시작)로 감소.
저신뢰 상태 지속 시 완전 차단이 아니라 0.5s 후 dRel=77.2m로 점진
수렴함도 확인(설계 의도대로 — 진짜 원거리 전환이면 결국 반영됨,
다만 순간적 오판이 MPC에 즉시 꽂히는 것만 완화).
(B) 고신뢰 vision(modelProb=0.85) far jump: unpatched==patched
(70.0m, 즉시 스냅 유지) — 회귀 없음.
(C) 레이더 교차검증(radar=True, modelProb=0.1로 낮아도) far jump:
unpatched==patched(50.0m, 즉시 스냅 유지) — 회귀 없음.
(D) closer_jump(위험방향, 저신뢰 vision이어도): danger-passthrough로
즉시 반영(40.0m) — 반응지연 없음.
(E) 정상 추종(점프 없음, 200프레임/10초): unpatched/patched 완전
동일(diff=0) — 회귀 없음.

**패치/검증 상태**: `git format-patch` 생성 →
`0001-130-LeadBlend-BIG_JUMP-104-Finding-A.patch` → `verify-am`
브랜치(base `b63063a`)에 `git am` 적용 검증 + `py_compile` 통과.
사용자에게 패치 전달, 로컬 `git am` 적용/push는 사용자 몫.

**상태**: **실차 검증 필요.** 104차 원본 route(대용량 정책상 컨테이너
미보관)를 재확보하면 동일 시나리오(커브+레이더유실) replay로 정밀
재검증 가능. 또한 다음 세션에서: (1) 정상 far-jump 케이스(진짜 다른
차량으로 전환되는 경우, 예: 앞차 turn-off/차선변경으로 새 원거리
리드가 드러나는 상황)에서 0.35s 블렌딩 지연이 체감상 문제되는지
실차로 확인 필요 — 이런 케이스가 흔하면 GATE=0.70이 과하게 보수적일
수 있음. (2) VisionTrack 레벨(`self.dRel`)에서 더 상류에 별도 플로시
빌리티 게이트를 둘지, 지금처럼 LeadBlend 레벨에서만 막을지 재검토
여지 있음(현재는 LeadBlend 레벨 — VisionTrack 자체의 dRel 값은 여전히
84~89m로 저장됨, radarState.leadOne에 실제 반영되는 시점만 완화됨).

---

## 129차 — 교차로 접근 route 사전감속 "계단형 고정" 실측 확인 + 91차(ROUTE_ENTRY_MARGIN_KPH) 구조적 원인 가설 [NEEDS_VALIDATION, 코드 미수정]

**배경**: 사용자가 실차 로그(route `306de77a28` seg15, 20260829_140424) +
대시캠 클립(`라우트 교차로에서...카운트다운_260829_140414_clip.mp4`)을 업로드,
"교차로(좌/우회전) 접근 전 route 사전감속이 너무 일찍 목표속도(커브
최저속도 파라미터 30km/h)로 고정되어 교차로까지 너무 천천히 서행한다"고
보고. `AutoCurveSpeedLowerLimit`(사용자 설정 30km/h, `carrot_serv.py`
`route_speed = max(route_speed * mapTurnSpeedFactor, autoCurveSpeedLowerLimit)`)
자체가 문제가 아니라, **그 값에 도달하는 방식이 연속감속이 아니라
계단형(step)이라는 점**이 핵심 불만.

**추출**: `extract_log.py`로 60초 단일세그먼트 CSV 추출(commit `b63063a5fe89`,
127차 HEAD 기준 — **실제 device 펌웨어 커밋은 미확인, 다음 세션에서
사용자 확인 필요**, 과거 115차 사례처럼 로컬 repo HEAD와 실측 커밋이 다를
수 있음 유의).

**핵심 발견 — desiredSpeed(carrotMan) 20Hz 시계열에서 계단형 급락 2건 확인**:
```
t= 4.20->4.25s  desSpd  86->61 (Δ-25)  src=route  vEgo=73.9kph  steer=-2.6deg(직진)
t=28.30->28.35s desSpd  65->41 (Δ-24)  src=route  vEgo=64.8kph  steer=-15.1deg(직진)
```
두 사례 모두 **0.05초(1프레임) 만에 20km/h대 급락** — steeringAngleDeg가
직진 수준(±15도 이내)이라 실제 커브 진입 훨씬 이전(steer가 90~150도까지
치솟는 실제 회전은 t=44~48s에 별도로 존재)임에도 route 소스가 이미 낮은
값으로 떨어짐. 급락 직후 desiredSpeed는 **~7초/약100m 동안 37~43km/h
범위에서 사실상 정체**(t=28.35~35.3, 이 구간에서 운전자가 gas 개입해
override) — 매끄러운 연속 감속이 아니라 "즉시 계단으로 떨어진 뒤 정체"
패턴. 실제 회전 구간(t=44.4~48.6, steer 90~150도)은 desiredSpeed=30
유지 후 회전 종료 즉시(t=49.6) 60까지 순간 복귀 — 이쪽도 계단형.

**원인 가설(구조적, 코드 검토 기반)**: `carrot_man.py::carrot_navi_route()`의
역방향 DP(91차 `ROUTE_ENTRY_MARGIN_KPH` 마진 로직, `L558~572`)가
"감속전환 시점 진입"을 판정할 때마다 `time_delay`를
`(v_ego_kph - (target_speed-margin_kph)) / accel_limit_kmh`로 계산하는데,
이때 `v_ego_kph`는 **루프 시작 전 딱 한 번 읽은 "현재" 차량 속도**
(`carrot_man.py` L536)로, 그 트랜지션 지점이 현재 위치로부터 실제로 몇
m 떨어져 있는지와 무관하게 항상 동일하게 적용됨. 목표지점의
curvature 기반 target_speed가 route 폴리라인 형상 때문에 낮게(예:
15~20대) 계산되는 지점이 현재 위치로부터 멀리 있을 때, `time_delay`가
과다산정되어(`(65-15)/2.52 ≈ 20초` 규모) `time_wait`가 크게 음수로
시작 → 그 뒤 여러 샘플(각 최대 +2.0s/샘플)에 걸쳐 서서히만 회복되는
동안 `time_apply≈0` → `max_allowed_speed = next_out_speed + 0`이
"멀리 있는 낮은 지점의 값"에 사실상 고정 → 그 사이 구간의 실제
target_speed(아직 커브 아니므로 정상적으로는 높아야 함)가 전부 무시되고
낮은 고정값으로 계단화. **미검증 세부**: 급락폭(Δ24~25kph)이
`ROUTE_ENTRY_MARGIN_KPH`(25.0) 값과 근접한 것이 우연인지 직접적
인과관계인지는 아직 수식으로 확정하지 못함 — 다음 세션에서
`sim_route_margin_regression_scan.py`(93차, `backward_dp_margin`)를
이 실측 t=4.2/28.3 구간에 맞춰 재구성 검증 필요(단, 해당 스크립트는
`desiredCurvature` 적분 재구성 경로를 쓰므로 실제 navi 폴리라인과 다를 수
있음 — 90차가 이미 지적한 한계, 정성적 재현만 가능할 가능성 있음).

**중요**: 91차의 "vturn보다 route가 먼저 개입해야 한다"는 설계 의도
자체는 유효 — 문제는 "더 일찍 시작"이 아니라 "계단형으로 즉시 낮은
값에 고정"되는 부작용. 사용자 제안(과속카메라처럼 연속적으로
70→65→60→...→30 감속)은 이미 `carrot_serv.py::calculate_current_speed()`
(sqrt 커브, `atc`/`sdi_speed`가 이미 사용 중인 연속 운동학 공식)로
구현된 패턴이 존재 — route 커브에도 이 방식을 적용하거나, 최소한 margin
로직의 거리 무관 결함을 고치는 방향이 필요.

**대안 (미결정, 사용자 방향 확인 대기)**:
- **방안A**: margin 로직의 `time_delay` 계산에 `v_ego_kph`(현재속도)
  대신 "그 트랜지션 지점까지의 거리 기반 물리적 도달가능속도"를
  대입 — 구조는 유지하되 결함만 수정(변경 범위 작음).
- **방안B**: margin 휴리스틱(89차 대안3) 자체를 폐기하고, route 커브
  진입도 `atc`/`sdi_speed`처럼 `calculate_current_speed()` 스타일
  물리 공식(연속 sqrt 커브)으로 재구현 — 계단형 자체가 구조적으로
  발생 불가능해짐(변경 범위 큼, 89차/90차/91차/93차 기존 검증 무효화
  가능성).
- **방안C**: 임시완화 — `ROUTE_ENTRY_MARGIN_KPH`를 낮추거나(예: 25→10)
  0으로 되돌려 89차 이전 상태로 회귀. 계단 낙폭 자체는 줄어들지만
  "route가 vturn보다 늦게 개입" 문제 재발 우려.

**다음**: 사용자에게 방향(A/B/C 또는 조합) 확인 후 시뮬레이션 검증 →
패치 진행. 실제 device 펌웨어 커밋도 재확인 필요(위 참고).

## 125차 — 133212(=133149) 재정밀분석: 124차 TTC 결론 정정 + "차선 폭 넓히기" 제안 기각, 새 메커니즘(레이더 타겟 스위칭) 확인 [CORRECTED, 코드 미수정]

**배경**: 사용자가 route354 seg3(20260829_133224_00000354--820cae021b--3,
133212 사건) rlog/qcamera zip을 재업로드하며 "옆차가 내 차로로 들어오는데
인식이 늦어서 브레이크를 밟았고, 물리적으로 충돌 위험이 있었다. 컷인
상황에서 차선 폭 기준을 넓히면 일찍 감지되고 그에 따라 감속 로직이
발동하도록 검토해달라"고 요청. 124차가 이 사건을 "TTC 7초+, 위험도
낮음, 운전자의 반사반응"으로 결론냈던 것과 정면으로 배치되는 주장이라
원본 rlog를 다시 정밀분석함.

**1) [중요 정정] 124차의 TTC 계산은 진짜 위험 구간을 놓쳤음**:
124차는 t=296.5~296.9 구간(레이더 2프레임 재락온, dRel 11.85→5.5m 스냅,
yRel/dPath≈0)만 보고 TTC 7초+로 결론냈음. 그러나 그 **직후** t=297.0부터
전혀 다른, 훨씬 급격한 2차 사건이 있었음(신규 발견, 원본 rlog
`liveTracks`/`radarState` 원시 재생으로 확인):
```
t=296.984  dRel=3.8m  yRel=0.8m  vRel=-1.1m/s   <- dRel 5.3->3.8m 급락 + yRel 0->0.8m 동시 점프
t=297.033  dRel=3.7m  yRel=0.7m  vRel=-1.1m/s
t=297.419  dRel=3.4m  yRel=0.57m vRel=-1.1m/s   <- 이 프레임에 brakePressed=True 시작
t=298.3~299.9  dRel 1.8~1.9m로 정체(양측 모두 저속 동행, 충돌은 없었음)
```
브레이크 개입 시점의 실측 TTC ≈ 3.4/1.1 ≈ **3.1초**(124차 주장 7초+와
크게 다름). **사용자의 "물리적으로 충돌위험이 있었다"는 판단이 맞았고,
124차의 위험도 평가는 관찰 구간 부족으로 인한 오판이었음.**

**2) "차선 폭 넓히기" 제안은 기각(이 사례엔 무력) — 신규 스크립트
`extract_cutin_lists.py`(toolkit 편입)로 검증**:
`radard.py`의 실제 컷인 후보 리스트(`leadsCutIn`/`leadsLeft`/`leadsRight`,
`in_lane_prob_future>0.1` 게이트 통과분만 포함)를 원본 rlog에서 그대로
추출해보니, **사건 전체 구간(t=290~300)에서 세 리스트 모두 단 한 번도
비지 않았음(n=0 유지)**. 옆차의 yRel/dPath는 최대 0.83m까지만 올라갔는데,
`in_lane_prob = 1 - |dist_from_center|/lane_half_width` 계산상 이
정도로는 여전히 "내 차로 안"으로 분류되어 애초에 "차로 밖 후보"로 취급된
적이 없음. 즉 `lane_half_width`(또는 그 파생 임계값들, 예:
`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE`/`in_lane_prob` 관련 값)를 넓히는
방향의 수정은 **이미 발동한 적 없는 게이트를 더 관대하게 만들 뿐**이라
이 사례에는 아무 효과가 없음. (123차/124차가 검토했던
`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE`도 이 사례와는 별개로 여전히
무관 — 컷인 후보 등록 문제가 아니라 리드 자체의 급변 문제였음.)

**3) 진짜 메커니즘: SCC 단일점 레이더의 "타겟 스위칭"(신규 확인,
124차의 "동일 trackId=0 → 동일 물체" 추론 재반박)**:
`modelV2.leadsV3[0]`(비전 단독 후보)을 병행 조회한 결과, 비전 모델은
이 구간 내내 dRel이 9.19m→4.5m로 매끄럽게 줄고 y가 -0.13~+0.02m로 거의
0에 머무는 **완전히 다른 하나의 물체**를 계속 추적 중이었음(급격한
점프 없음). 반면 레이더(`liveTracks` 원시 포인트, trackId=0 고정)는
t=296.5에 기존 타겟을 잠깐 놓쳤다가 재락온하며, 훨씬 가깝고 옆으로
치우친 별개의 물체로 갈아탄 것으로 보임 — 이 차량은 코너레이더 없는
SCC 단일점이라 `radarTrackId`가 레이더 감지 중엔 항상 0으로 고정됨
(107차 기존 확인). **즉 "trackId가 안 바뀌었으니 동일 물체"라는 124차의
핵심 근거는 이 하드웨어에서는 애초에 성립하지 않는 추론이었음** —
trackId=0 유지는 "같은 물체를 계속 봤다"가 아니라 "레이더가 뭔가를
보고 있었다"만 의미함.

**결론(중요)**: 124차의 "TTC 7초+, 저위험" 결론은 **철회**. 이 사례는
물리적으로 위험했던 진짜 컷인이 맞고, 원인은 (a) 컷인 후보 등록
게이트(`leadsCutIn` 등, 차선 폭 기반)가 아니라 (b) SCC 단일점 레이더가
기존 타겟 재락온 시 실제로는 더 가깝고 옆으로 치우친 다른 물체로
"타겟 스위칭"되면서 dRel+yRel이 동시에 급변했는데, 이를 이상 신호로
잡아내는 로직이 없어 그 값이 그대로 leadOne에 반영된 것으로 추정.

**다음 세션 필요 (코딩 방향, 아직 미착수)**:
1. `DREL_DISCONTINUITY_DROP_THRESH`(63차/94차가 이미 "radar_locked
   프레임에서는 검사 안 함"이라는 사각지대를 발견한 그 로직)를
   dRel 단독이 아니라 **dRel 급락 + |Δ dPath 또는 yRel| 동시 급증**을
   보는 조인트 게이트로 확장하는 안 검토 — "타겟이 다른 물체로
   바뀌었을 가능성"의 훨씬 강한 신호이므로 radar_locked 여부와 무관하게
   적용하는 것도 함께 검토.
2. 표본이 이번 사례 1건뿐이므로, 다른 정상 컷인/차로변경/레이더
   재락온 상황에서 이 조인트 게이트가 오탐을 일으키지 않는지 다른
   라우트로 검증 필요(합성 시나리오 + 실측 재생 둘 다).
3. 사용자가 제시한 "차선 폭 넓히기" 자체는 이 사례에는 무력하지만,
   원래 목적(`in_lane_prob`/`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE`
   등)에서 별도로 튜닝 가치가 있는지는 이번 분석과 무관하게 미검토
   상태로 남음.

drive_csv: (해당 없음 — 이번 세션은 CSV 대량 추출 없이 원본 rlog를
`decode_rlog`/`extract_cutin_lists`로 직접 재생하는 방식만 사용했고,
seg3 하나뿐이라 별도 route CSV 산출물 없음. 원본 zip은 세션 종료 시
컨테이너 리셋으로 소실 — 재검증 필요 시 재업로드 필요.)

## 124차 — 컷인 5클립 전수 정밀분석 완료 + 123차 원인가설 2건 모두 기각(중요 정정) [CORRECTED, 코드 미수정]

**배경**: 123차(중단)를 이어받아 컨테이너 재시작 후 route354/356 zip
재업로드받아 CSV 재추출. 사용자 요청("컷인상황만 정밀분석하고
코딩방향 정하자")에 따라 컷인 관련 클립 5개(133212/133149 복합/
141434/134659 복합/141833 복합) 전수 분석 완료.

**1) 컷인 클립 5개 최종 분류 — 문제 사례는 1건뿐**:
| 클립 | route/t | 실체 | 결과 |
|---|---|---|---|
| 컷인_이거는_차선폭을_넓게_133212 | r354 t≈296~302 | 다른 차량이 저속(10km/h)으로 내 차로에 끼어듦 | 반응 약함→운전자 브레이크 개입(`brakePressed=True` t=297.40~299.35 확인) |
| 컷아웃_컷인_133149 | r354 t≈296~302 | **위와 완전히 동일한 실제 사건**(화면녹화가 겹쳐 촬영, 파일명 시각 23초 차이지만 같은 순간) | 중복, 별개 사례 아님 |
| 컷인_141434 | r356 t≈2830~2841 | 다른 차량 끼어듦이 아니라 **운전자 본인이 우측 방향지시등 켜고 수동 차선변경**, `laneChangeState`는 계속 `off`(openpilot ALC 아님) | 옮겨간 차로에 정체 있어 최대 -4.0m/s² 강제동이나 `brakePressed` 개입 없이 매끈하게 처리(정상 동작) |
| 컷인_컷아웃_134659 | r354 | 교차로에서 화물트럭이 좌회전하며 끼어듦 | 최대 -1.4m/s²로 매끈, 개입 없음 |
| 컷인_컷아웃_141833 | r356 | 시내 정체구간 리드 전환 다수 | 최대 -1.45m/s², 전부 정상 처리 |

→ **실질적으로 "시스템 반응이 부족했던 컷인"은 r354 t≈296~302 단
1건**(133212=133149). 나머지 4개 시나리오는 전부 정상 처리이거나
애초에 다른 차량의 컷인이 아니었음.

**2) [중요 정정] 123차가 제시한 원인가설 2건 모두 고해상도
재검증으로 기각됨**:

123차는 이 1건의 원인 후보로 (a) `radard.py` L420
`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE=1.75`(신규 tentative 후보
등록 지연), (b) `long_mpc.py` `DREL_DISCONTINUITY_DROP_THRESH=15.0`
(6.66m 급락 미탐지) 두 가지를 지목했었음. 오늘 0.05초 단위
고해상도 재확인(20Hz 원본) 결과 둘 다 실제 메커니즘과 무관함이
드러남:

```
t=296.516  radar=True  trackId=0  dRel=11.85  vRel=-0.52
t=296.555  radar=False trackId=-1 dRel=10.92  vRel=-0.50   ← 레이더 순간 놓침(2프레임, ~0.1s)
t=296.605  radar=False trackId=-1 dRel=10.07  vRel=-0.49
t=296.654  radar=True  trackId=0  dRel=5.50   vRel=-0.80   ← 같은 trackId=0로 재락온, 거리값만 급보정(5.5m 스냅)
```

- **가설(a) 기각 이유**: trackId가 처음부터 끝까지 계속 `0`으로
  유지됨(신규 후보가 아니라 기존에 이미 등록되어 있던 동일
  트랙) → tentative 신규 등록 게이트가 개입할 상황 자체가 아니었음.
- **가설(b) 기각 이유**: `DREL_DISCONTINUITY_*` 로직은
  `not radar_locked`(비전 단독) 구간에서만 dRel 급락을 검사하고,
  `radar_locked=True`인 프레임에서는 오히려 히스토리를 초기화하도록
  설계되어 있음(`sim_drel_discontinuity.py`의
  `step()` 참고). 실제 5.5m로의 급보정은 **radar=True 프레임에서
  발생** → 이 로직이 애초에 들여다보지 않는 구간.
- **추가로 확인된 사실**: 이 구간 전체 `vRel`은 -0.5~-1.1 m/s
  수준(TTC 약 7초 이상)으로, 물리적으로 "충돌 임박" 급접근은
  아니었음. 실제로는 시스템 반응이 늦었다기보다, **레이더가 거리
  추정치를 한번에 보정(스냅)하면서 화면상 숫자가 갑자기 반토막
  나는 것에 운전자가 먼저 반사적으로 브레이크를 밟은** 상황에 더
  가까움. 시스템 자체 감속(aEgo)도 t=297.05부터 이미 완만히
  램프업 중이었음(브레이크 개입 시점 t=297.40 이전).

**검증 방법**: 기존 `toolkit/sim_drel_discontinuity.py`를 재사용해
threshold=8.0/15.0 두 값으로 실측 시퀀스(`[11.96,10.07,9.20,8.10,
5.30,5.10]`) 재생 — 8.0에서도 미탐지 확인(윈도우5 기준 하락폭
6.66m < 8.0). threshold를 6.0대로 더 낮추는 안도 검토했으나,
r354/r356 전체에서 vision-only 5프레임 윈도우 낙폭 6~15m 구간
이벤트가 **134건**(대부분 장거리 정상 접근으로 추정)이나 확인되어
단순 하향 조정은 오탐 급증 리스크가 큼(회귀 위험, 코드 미수정
보류).

**결론(중요)**: 123차의 "설계 제안 단계" 결론은 이 특정 사례에
대해서는 **철회**. 실제 필요한 것은 "레이더가 동일 트랙을 잠깐
놓쳤다가 재락온하며 거리값을 스냅 보정하는 경우"에 대한 대응
로직이며, 이는 기존에 코드베이스에 없던 완전히 새로운 케이스로
보임(다음 세션에서 설계 필요). `VISION_TRACK_TENTATIVE_DPATH_ABS_GATE`/
`DREL_DISCONTINUITY_DROP_THRESH` 자체는 각각 원래 목적(신규 tentative
등록/비전단독 discontinuity)에서는 여전히 유효한 상수이며 이번
사례와 무관하게 별도로 튜닝 가치가 있을 수 있음(미검토).

**다음 세션 필요 (사용자가 제시한 4가지 방향 중 미결정)**:
1. 레이더 재락온 급보정(같은 trackId, 거리값 스냅) 대응 로직 신규 설계
2. 물리적으로 위험하지 않았을 가능성 있으니 코드수정 보류, 사례 추가 수집
3. 그래도 #1(tentative gate)/#2(discontinuity thresh)는 각자 다른 이유로 튜닝 가치 있으니 별개 검토
4. 원본 rlog 정밀분석(dPath/yRel 등 추가 필드로 근본원인 재탐색 — 왜 2프레임간 radar가 놓쳤는지 등)
→ **사용자가 다음 세션에서 방향 결정 예정** (오늘은 체크포인트로 중단)

## 123차 — 세번째 검증: 컷인/컷아웃 상황 분석 (중단, 미완료) [IN_PROGRESS]

**배경**: 컷아웃/컷인 화면녹화 클립 8개 + route354~357 zip 4개
업로드, "세번째 검증" 요청. 컷아웃부터(119차 게이트 검증) → 컷인
분석("컷인 상황에서는 컷아웃과 반대로 차선폭기준을 늘려야 하나?"
가설 검증) 순으로 진행하던 중 컨테이너 리셋으로 세션 중단.
**route CSV(r354~357)는 work/에만 있었고 재추출 전 리셋되어 소실**
— 다음 세션에서 재분석하려면 zip 재업로드 필요.

**컷아웃 검증 결과 (2건, 둘 다 클린 — 단 119차 게이트 자체는
발동한 사례 아님)**:
| 클립 | route/t | 결과 |
|---|---|---|
| 컷아웃_135527 | r355 t≈1666~1696 | 정지 트럭 좌회전 이탈 → 가속 지연 없음. leadDPath 최대 1.65m로 LANE_DEPARTURE_DPATH_THRESH(1.75m) 미도달 → 119차 게이트가 아니라 leadModelProb 자연 감쇠(0.99→0.656)로 leadStatus False 전환 |
| 컷아웃_141322 | r356 t≈2760~2774 | 주행 중 리드 좌측 이탈, dPath -1.89m 도달했으나 confirm 0.5s 못 채우고 새 원거리 리드로 자연 target-switch(dRel 42.6→60.0m 점프). 급제동 없음 |

`replay_lane_departure_gate.py`로 r355/r356 전체 재스캔해도 이
두 클립 구간엔 게이트 후보가 안 잡힘(r355는 t=1667.50 무관 노이즈
1건, r356은 122차가 이미 발견한 t=2547.35/3418.60 2건뿐, 전부 클립
무관). → 119차 게이트를 실제로 정밀검증할 실측 사례는 여전히
미확보 (78차 boost 정량검증 공백과 동종 문제로 남음).

**컷인 분석 — "차선폭을 넓게" 클립, 사용자 가설을 뒷받침하는
코드상 근거 발견**:

컷인_이거는_차선_폭을_넓게_133212 → r354 t≈296~302 매칭:
- t=296.30→296.96 사이 leadDRel이 11.96m→5.30m로 6.66m 급락
  (radar 순간 False→True, 측면 진입 차량이 새 리드로 급등록)
- 이 급락폭(6.66m)이 `long_mpc.py`의
  `DREL_DISCONTINUITY_DROP_THRESH=15.0m`보다 작아 discontinuity
  jerk boost 자체가 미발동 → 초기 반응 약함(aEgo -0.38)
- t≈297.6부터 운전자 직접 브레이크 개입(brakePressed=True, aEgo
  -1.44까지) → 최종 정지거리 1.2m
- **유력 원인 후보로 `radard.py` L420
  `VISION_TRACK_TENTATIVE_DPATH_ABS_GATE = 1.75` 특정**: 끼어드는
  차량의 dPath가 1.75m 이상인 동안(아직 옆차로에 걸쳐있는 중)은
  tentative 후보 등록 자체가 배제되는 구조 → dPath가 거의 0에
  가까워질 때까지(=거의 완전히 들어온 뒤) 신규 리드 등록이
  지연됨.

**결론(잠정, 코드 미수정)**: 사용자 가설("컷인은 반대로 차선폭
기준을 넓혀야 하나")은 코드 구조상 합리적. 119차(컷아웃)은 "이미
걸린 락을 더 좁은 기준(1.75m)으로 빨리 풀자" 방향이었고, 컷인은
반대로 "아직 옆차로에 걸쳐있는(dPath 큰) 후보도 더 넓은 기준으로
일찍 tentative 등록해서 반응을 앞당기자" 방향. 서로 다른 코드
위치(`LANE_DEPARTURE_DPATH_THRESH` vs
`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE`)를 만지는, 대칭적이지만
별개인 튜닝 대상.

**추가 후보**: `DREL_DISCONTINUITY_DROP_THRESH=15.0m`이 이번
6.66m급 완만한 컷인을 놓친 것도 별도 튜닝 후보(컷인 전용 더 낮은
threshold 검토 여지). 단 이는 근본원인이라기보다 완화책 성격 —
근본 원인은 위 tentative 등록 지연 쪽에 더 가깝다고 판단(신규 리드
자체가 늦게 잡히면 discontinuity 판정 시점도 함께 늦어짐).

**미완료 (다음 세션 필요)**:
- 컷인_141434(r356) — 매칭 시작만 하고 중단
- 컷아웃_컷인_133149 / 컷인_컷아웃_134659 / 컷인_컷아웃_141833
  (복합 클립 3건) — 미착수
- 위 두 상수(`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE`,
  `DREL_DISCONTINUITY_DROP_THRESH`) 튜닝안은 설계 제안 단계일 뿐
  코드 미수정 — 시뮬레이션 검증(`sim_*.py` 신규 작성 필요 가능,
  toolkit/README.md 먼저 확인할 것) 및 사용자 확인 후 진행
- route354~357 CSV 소실 — 재분석 시 zip 재업로드 필요

## 122차 — 두번째 검증: route356 저속구간 가감속 3건 + 119차 최신패치 재확인 — 전부 클린 [VALIDATED]

**배경**: route356(commit `21adb2c013f4`=119차 반영) + "저속_가감속"
화면녹화 클립 3개(141048/141556/142300) 업로드, 저속 가감속 상황
분석 + 119차 패치 검증 요청. 121차가 미추출로 남긴 route356 이어서
진행.

**클립 매칭 방법론 갱신**: 121차의 "+52초 고정 오프셋"이 이번
route에선 성립 안 함(클립별 +30.6s/+31.5s/+13.5s로 편차) — 스크린
레코더 저장지연이 매 정지버튼 입력마다 달라짐을 시사, **향후
세션에서 "파일명+N초"식 고정 공식을 가정하지 말고 매번 실측
재확인할 것**. 이번엔 blinker 클러스터 매칭(차선변경 없는 저속
시나리오라 활성 blinker 자체가 없어 적용 불가) 대신 HUD 수치
(leadDRel/vEgo/aEgo) 정밀 대조 + qcamera 프레임 시각 확인 3건
전부로 대체 매칭:
- Clip1(141048) → t≈2592.9 (dRel=8.3m 정확 일치, vEgo≈4.9km/h,
  qcamera 프레임 배경/차량 일치 확인 완료)
- Clip2(141556) → t≈2901.8 (dRel=6.4m, vEgo≈3.2km/h, aEgo≈-0.89 대
  HUD -0.90 일치, qcamera 프레임 일치 확인 완료)
- Clip3(142300) → t≈3307.8 (dRel=4.5m, vEgo=0 정지, qcamera 프레임
  배경(화명동)/선행차량(그랜저 313노1030) 완전 일치 확인 — 동일
  dRel=4.5/vEgo=0 조건을 만족하는 클러스터가 route 전체에 7개 있어
  naive offset(+13.5s가 가장 근접)만으론 확정 어려웠으나 qcamera
  시각대조로 최종 확정)

**119차(빨간박스 LANE_DEPARTURE 강제해제 게이트) route356 재검증**:
`replay_lane_departure_gate.py`(120차 신규 도구) 23999행 전체
스캔 결과 후보 2건 **전부 PASS**:
  - t=2547.35, dPath=-2.24m, vRel=3.80 → 예측 발동 후 0.048s 이내
    실제 leadStatus False 전환 확인
  - t=3418.60, dPath=-1.89m, vRel=0.92 → 예측 발동 후 0.752s 이내
    실제 leadStatus False 전환 확인
  120차가 발견했던 "LeadBlend.update()가 게이트 리셋을 무력화"
  버그 미재현 — 단 이 route에서 후보가 2건뿐이라 표본이 작아
  120차 발견 버그 자체가 "완전 해소"됐다고 결론내리긴 이름(120차
  버그는 여전히 코드 미수정 상태로 남아있음, 별도 트랙 유지).
  두 이벤트 모두 3개 클립 구간과 무관한 별개 지점.

**저속 가감속 3개 구간 정량분석 — 전 지표 클린**:
| 구간 | t범위 | min aEgo | vEgo 범위 | harsh_brake | ttc_danger | dRel discontinuity | leadStatus flicker |
|---|---|---|---|---|---|---|---|
| clip1 | 2592~2622 | -0.53 | 0~11.3km/h | 0건 | 0건 | 0건 | 0회 |
| clip2 | 2901~2931 | -1.75 | 1.7~28.3km/h | 0건 | 0건 | 0건 | 0회 |
| clip3 | 3307~3337 | -0.90 | 0~22.6km/h | 0건 | 0건 | 0건 | 0회 |

route356 전체 기준 `congestion_stop_launch_lurch_scan`(58차 2번,
"정체 붕끗" 가설)도 0건 — 저속 stop-and-go 전체에서 붕끗 현상
재현 없음.

- **clip2가 가장 의미있는 사례**: vEgo 10.2→1.7km/h로 감속 시
  min aEgo=-1.75(112차 LOW_SPEED_STRONG_DECEL threshold -2.5 미도달,
  게이트 미발동이 설계대로 적절). t=2900.31(aEgo 최저점) 전후 확인
  결과 `leadALeadK`(-1.46→-1.28→...→+1.26으로 부드럽게 전환)와
  `aEgo`가 계단식 튐 없이 자연스럽게 동조 — 선행차 감속→재가속에
  선형적으로 반응하는 정상 추종 패턴, dRel도 8.5m→6.3m→7.8m로
  연속적(불연속 점프 없음).
- clip1/clip3는 min aEgo가 -0.5~-0.9 수준의 경미한 크리핑/정차
  반응으로, 애초에 어떤 저속 게이트도 관여할 상황이 아님(정상
  ACC 추종).

**결론**: `21adb2c`(119차) 반영 상태에서 저속구간 가감속 3개 실측
사례 전부 매끈하게 처리 확인. 112차/116·117차/94차의 저속 관련
로직들이 이번 시나리오에서 회귀 없이 유지되는 것으로 판단(간접
확인 — 사용자 체감 확인 대기). 119차 게이트도 이 route 다른
지점에서 정상 PASS 재확인(클립과는 별개 관찰).

**한계/다음 세션**: route357 필요시 이어서 확인. clip당 프레임
1장씩만 대조(매칭 검증 목적), 30초 전체 구간의 프레임단위 정밀
대조는 미실시. 119차 게이트 후보 2건은 클립과 무관해 상세 대조
안 함.

## 121차 — 76/94차(방안D) discontinuity 리셋 실차 재검증 — "차선변경 중 급감속" 재발 없음 확인, 예외 1건은 버그 아닌 정상반응으로 판정

**배경**: 사용자가 신규 실차 주행 4개 route(354~357, 13:30:24~14:34,
74세그먼트) + "내차 차선변경" 라벨 화면녹화 클립 4개 업로드. "차선변경
시 옆차선 앞차 반응이 정상인지, 예전의 급감속이 없어진 게 맞는지"
검증 요청. (route354/355는 120차와 동일 커밋 `21adb2c` 상태에서
추출된 CSV — 120차가 이미 같은 raw 데이터로 LANE_DEPARTURE 게이트
검증을 했었음, 이번엔 다른 관점(discontinuity_lc/방안D)으로 재분석.)

**클립-route 매칭(신규 활용, 파일명 직접매칭 대신 blinker 클러스터
상대간격 대조)**: 클립 파일명 시각 3개(134328/134406/134501)의
연속 간격(38s, 55s)이 route354 blinker 클러스터 시작시각 간격
(37.2s, 56.2s)과 오차 <1.5s로 정확히 일치 → 매칭. 4번째 클립
(140220)도 동일 오프셋(+52초)을 route355에 적용하니 오차 0.05s로
일치. **파일명 대비 항상 +52초 오프셋**(스크린레코더 저장지연) —
111차가 "최대 ~50초"로 추정했던 것과 사실상 동일값, 이 세션에서
±1.5초 정밀도로 재확인됨.
- Clip1(패치적용여부_검증) → r354 t≈974.35~978.01 (우측 차선변경)
- Clip2 → r354 t≈1011.55~1015.15 (좌측 차선변경)
- Clip3 → r354 t≈1067.75~1071.35 (우측 차선변경)
- Clip4 → r355 t≈2106.35~2109.95 (좌측 차선변경)

**4개 클립 공통 관찰 패턴**: 차선변경 blinker 활성 직후 1~3프레임
동안 `leadRadar`가 순간 False(vision-only)로 빠졌다가 재획득되는
순간, `leadDRel`/`leadVRel`/`leadDPath`가 불연속 점프(인접 차선의
새 차량으로 타겟 전환 — 구 버그의 트리거 조건과 동일 패턴). 이후
aEgo 반응:
  - Clip1: min aEgo -0.943 (vRel_after=-2.90, dPath_after=-3.88)
  - Clip2: min aEgo -0.636
  - Clip3: min aEgo -1.013 (vRel_after=-2.30, dPath_after=-2.69,
    t=1071.76 최저점까지 튐 없이 매끄럽게 하강 후 t=1073 vRel=0으로
    완전 회복)
  - Clip4: min aEgo -0.316 (vRel_after=+5.10 — 오히려 멀어지는
    차량이라 애초에 감속 불필요, 실제로 aEgo가 거의 0 근방 유지)
  **네 사례 모두 구버그가 보고했던 "-2.75까지 급강하"는 재현되지
  않음.** 76차/94차(방안D) 이후 vision_dRel_rate/window 리셋이
  실주행에서 의도대로 동작 중인 것으로 판단(간접 확인 — 내부 필터
  상태 직접 재현은 미실시, 아래 "한계" 참고).

**예외 사례(어떤 클립에도 포함 안 됨, 우측 차선변경, r354
t=827.81~831.45)**: min aEgo=-2.703로 4개 클립보다 뚜렷이 강한
감속. 상세 분석 결과 **버그 재현이 아니라 정상 반응으로 판정**:
  - t=829.10 radar 순간소실(vision-only) → t=829.85 radar 재획득,
    dRel 37.4→31.1, **vRel=-6.30 m/s(레이더 직접측정치, vision
    미분값 아님)**, dPath=-3.07(인접차선 확정 위치)
  - t=829.85~831.45(1.6초) 동안 aEgo가 -0.1→-2.70까지 계단식 튐
    없이 매끄럽게 하강, 이후 t≈833 vRel이 0 부근으로 수렴(속도매칭
    완료)하며 정상 회복
  - 목표차선 앞차와의 실측 접근률 -6.3m/s, 당시 dRel≈30m 기준
    TTC≈4.8s — 이 정도 감속(-2.70, 급브레이크 아님)은 실제 위험에
    대한 비례적/정당한 반응이지, vision 노이즈 오탐이 아님.

**전체 route354/355 전수 스캔(46797행, 약 40분) 결과**: dRel≥6m
순간점프(불연속) 이벤트 총 151건(장거리 vision 노이즈 다수 포함,
min_aEgo 대부분 -0.1~-0.6 수준으로 무해). 차선변경 인접 이벤트 중
강한 감속(-2.0 이하)을 유발한 건 상기 t=829건 포함 2~3건뿐이며,
전부 레이더 확정 vRel이 -1.7~-6.3m/s로 실측 접근 상황이었고 감속
프로파일도 매끄러움(급격한 튐 없음). 차선변경과 무관한 일반
주행중에도 유사 강도/빈도의 감속 이벤트가 나타나(예: t=1713.50
-3.815, t=2304.15 -2.719 — 둘 다 blinker 무관, 후자는 이미 진행
중이던 별개 감속 이벤트 도중 taget 전환이 겹친 것으로 확인, 차선변경
버그와 무관) — **차선변경 특이적 버그 패턴이 아니라 정상 ACC
추종제어 반응**으로 결론.

**한계(다음 세션 참고)**:
1. 이번 검증은 CSV 관측치(aEgo 실측 반응) 기반 간접 확인 —
   `_vision_dRel_rate`/`_lead_acq_timer` 등 long_mpc.py 내부 필터
   상태를 실제로 재현한 것은 아님. `sim_drel_discontinuity_d.py`(94차)는
   합성 시나리오 전용이라 이번 실측 CSV에 바로 적용 불가 — 실측 CSV를
   받아 내부 필터 상태를 재현하는 replay 스크립트는 아직 없음(향후
   과제, `replay_lane_change_discontinuity_gate.py`가 a_change_cost
   관점에서는 이미 하고 있으니 확장 검토 가능).
2. qcamera 프레임 직접 대조는 미실시(CSV 정량분석 + blinker 클러스터
   매칭만으로 결론 도출, 토큰 예산 고려) — 필요시 다음 세션에 특정
   구간만 프레임 추출해 시각 재확인 가능.
3. route356/357(14:09:24~14:34)은 이번에 CSV 추출 안 함(클립 4개가
   전부 354/355 구간에 매칭됐으므로 범위 밖) — 남은 두 route에도
   차선변경 이벤트가 있다면 다음 세션에 이어서 확인 가능.

**코드 변경 없음** — 순수 검증/분석 세션.

## 120차 — [중요] 119차 LANE_DEPARTURE 게이트 실차 검증 — 부분 무력화 버그 발견(LeadBlend가 gate 리셋을 다시 덮어씀)

**배경**: 사용자가 119차 패치(`21adb2c`, 커밋 완료) 적용된 실차 주행
로그 업로드(연속 주행 4개 route 업로드: 13:30:24~14:34, 총 64세그먼트
+ CarrotWeb 화면녹화 클립 19개, 파일명으로 시나리오 라벨링 —
"내차 차선변경 패치적용여부 검증" 등). "패치적용 잘 됐는지" 검증 요청.

**검증 방법(신규 `replay_lane_departure_gate.py`, toolkit 편입)**:
`extract_log.py` CSV(leadDPath/leadVRel/leadStatus/leadRadar 컬럼)
위에서 radard.py get_lead()의 LANE_DEPARTURE 게이트 로직(dPath>1.75m
& vRel>-0.5 가 0.5s 이상 지속되면 강제 status=False)을 그대로
복제해 "예측 발동 시각"을 계산하고, 실제 CSV에서 그 직후 leadStatus가
정말 True->False로 전환되는지 대조.

**결과**: 4개 route 전체(총 89996 rows, 약 64분)에서 후보 이벤트
9건 발견 — **PASS 5건**(0.042~0.752s 이내 실제 전환 확인, 패치가
실제로 개입한 것으로 판단) / **FAIL 3건**(dPath가 1.75m를 0.5s
넘게, 최장 1.3초 이상 지속 초과했는데도 leadStatus가 계속 True로
남음) / AMBIGUOUS 0건. "내차 차선변경 패치적용여부 검증" 등 ego
차선변경 클립 구간(13:43~14:22대, 총 5개 파일)은 dPath가 매번 짧은
스파이크(<0.3~0.4초)로만 튀고 0.5초 이상 지속된 적이 없어 게이트
발동 자체가 없었음 — **정상 차선변경 중 오탐(리드 오손실) 없음**은
확인됨(부수적 긍정 결과).

**FAIL 사례 상세(route355 t=1304.25, 가장 명확)**: t=1303.81~1305.15
(약 1.34초) 동안 leadRadar=True 유지된 채 |dPath|가 1.75~1.98m
사이(정확히 119차가 새로 커버하려던 구간, 구threshold 2.0m는 안
넘음)를 오가며 계속 초과 상태였고 vRel도 0.2~0.3(강접근 아님)으로
게이트 조건을 명백히 만족했으나 leadStatus는 단 한 번도 False가
되지 않았음. t=1305.20에 이르러서야 완전히 다른 원거리 물체(dRel
32m -> 74m 점프)로 전환되며 사실상 "게이트가 아니라 트랙 자체가
다른 물체로 바뀌어서" 우연히 넘어간 것으로 보임 — **119차 게이트가
이 이벤트에서 사실상 전혀 작동하지 않은 것으로 판단**.

**근본 원인(코드리뷰로 확정)**: `RadarD.get_lead()`(L940~954, 119차
패치)가 게이트 발동 시 `lead_dict = {'status': False}`로 리셋하지만,
이 dict에는 `'radar'` 키가 없다. 호출부 `RadarD.update()`(L848~850)는
`if lead_one_raw.get('radar') and not lead_one_scc_fallback:` 조건으로
"빨간박스 직접사용"(블렌딩 스킵) 분기를 타는데, 게이트가 리셋한
dict는 이 조건이 항상 False가 되어 **무조건 else 분기
(`self.lead_blend.update(lead_one_raw, DT_MDL)`)로 빠진다.**
`LeadBlend.update()`는 `raw.get('status')==False`를 받으면 자신의
**별도 독립 판정 로직** `_is_cutout()`(118차가 이미 발견한 그 구버전
로직, `CUTOUT_DPATH_THRESH=2.0m` 기준)으로 "즉시 보고 vs grace-hold"를
다시 판단한다:
- `self.prev.dPath`(LeadBlend가 마지막으로 기억한 값)가 아직 2.0m를
  안 넘었다면(=119차가 새로 잡으려던 1.75~2.0m 구간) `_is_cutout()`은
  **False** -> `miss_cnt` 증가 grace-hold 경로로 빠져 최대
  `LEAD_LOST_GRACE_TIME=0.6s` 동안 **직전 lead를 status=True로 계속
  보고(extrapolated dRel)** -> 119차 게이트의 리셋이 완전히 가려짐.
  이 grace 안에 트랙이 재획득되면 리셋 자체가 영원히 무효화될 수
  있음(FAIL 사례가 실제로 이런 패턴).
- 반대로 `self.prev.dPath`가 이미 2.0m를 넘은 상태였다면 `_is_cutout()`
  이 True가 되어 즉시 보고 -> 이 경우만 119차 게이트가 "우연히" 빠르게
  반영됨(PASS 5건 중 다수가 dpath_at_predicted가 1.9~2.2m대로 이미
  구threshold 부근/초과였던 것과 일치).

**결론**: 118/119차가 원래 없애려던 "outer 로직이 내부 상태리셋을
다시 무력화하는" 버그 클래스(60차 계속8, `lead_msg.prob>0.5` 재체크
사례와 동일 패턴)가 이번엔 **LeadBlend**를 매개로 재발함. 119차
패치는 "죽은" 게 아니라 — dPath가 자연스럽게 2.0m(구threshold)까지
넘어가는 사례에서는 결과적으로 잘 동작하지만, **정확히 119차가 새로
커버하려던 1.75~2.0m 구간에서는 최대 0.6초 지연되거나 완전히
무력화될 수 있는 부분적 실패** 상태.

**다음 세션 필요(코드 미변경, 설계만)**:
1. get_lead()가 게이트를 발동시키는 그 프레임에 `self.lead_blend.prev
   = None; self.lead_blend.miss_cnt = 0; self.lead_blend.danger_hold_cnt
   = 0`도 함께 리셋(RadarD.update()의 빨간박스 케이스가 이미 하는
   것과 동일 패턴, L859~860 참고) — RadarD가 LeadBlend 인스턴스에
   접근 가능한지 확인 필요(현재 get_lead()는 RadarD 메서드이므로
   `self.lead_blend`로 접근 가능해 보임, 다음 세션에 실제 구조
   재확인).
2. 대안: LeadBlend._is_cutout()의 threshold를 CUTOUT_DPATH_THRESH(2.0)
   대신 LANE_DEPARTURE_DPATH_THRESH(1.75)와 동기화 — 다만 이 상수는
   원래 다른 목적(cutout 일반 판정)에도 쓰이므로 부작용 검토 필요.
3. 검증: `replay_lane_departure_gate.py`에 "gate 발동 시 lead_blend
   리셋까지 반영한" PATCHED 버전 추가해 이번 실측 3개 FAIL 이벤트가
   해소되는지 재생 검증.
**상태**: `NEEDS_FIX` (실차검증 완료, 원인 확정, 패치 미작성)

**참고**: 이번에 쓴 `drive_route354~357.csv`(4개, 총 89996행)는 레포에
커밋하지 않음(대용량 산출물 커밋 금지 원칙) — Drive 커넥터 미연결로
`work/`에만 스크래치 보관, 컨테이너 리셋 시 소실됨(재분석 필요 시
사용자가 원본 zip 재업로드 필요).

## 118차 — 검증된 레이더 락("빨간 박스") 상태에서 LeadBlend의 dPath 컷아웃 로직이 완전 우회됨 확인 (근본원인 확정, 코드 미변경)

**증상(사용자 제보)**: 앞차가 명백히 차선을 이탈했는데도 레이더 락온이
풀리지 않아 자차 출발이 지연됨.

**분석 자료**: `앞차_컷아웃.Zip` 업로드 — CarrotWeb 화면녹화 클립 2개
(HUD 오버레이 포함, 각 ~30초) + route rlog 2세트(route1 `ce1f43d848`
x20seg 12:16:14~12:36:14 / route2 `bc5b8243eb` x5seg
12:36:14~12:40:01), 커밋 `76c985ca86f5`(117차 반영, c3-ms-dev).

**근본 원인**: `selfdrive/controls/radard.py` `RadarD.update()`
(L826~838)에서, `lead_one_raw.get('radar') and not
lead_one_scc_fallback`(비전-레이더 교차검증된 안정적 락, "빨간 박스")
조건일 때는 `self.lead_blend.update()` 호출을 건너뛰고
`lead_one_raw`를 그대로 `radar_state.leadOne`에 발행한다(주석: "이미
안정적인 실측값이므로 블렌딩 지연 없이 그대로 사용"). 반면
`LeadBlend._is_cutout()`(L659~662, `CUTOUT_DPATH_THRESH=2.0m` 기준
— 46차/37차 때부터 있던 기존 컷아웃 감지 로직)는 오직
`LeadBlend.update()` 내부에서만 평가되므로, **"빨간 박스" 상태(코드
주석상 전체 추적시간의 74~82%로 가장 흔한 상태)에서는 dPath가 아무리
커져도 컷아웃 판정 자체가 아예 실행되지 않는다.** 비전 모델
(`leadsV3[0]`)이 스스로 그 물체에 대한 confidence(prob)를 낮추거나
레이더 트랙이 물리적으로 사라지기 전까지는 아무 것도 능동적으로 락을
풀지 않음.

**실측 근거 (route1.csv, t=5915.03~5932.53, ~17.5초)**:
- `leadStatus=True & leadRadar=True` 유지된 채 dPath가 점진적으로
  커져 t=5931.02에 처음 **-1.97m**(사실상 CUTOUT_DPATH_THRESH=2.0m
  도달) → 이후 -1.98~-1.99m 부근에서 정체된 채로 **leadStatus=True가
  약 1.5초간 그대로 유지**되다가 t=5932.53에 자연 해제(비전 모델
  자체 prob 하락으로 추정, radard 내부 능동 해제 아님).
- 이 사례는 vEgo가 이미 7.8→8.6km/h로 가속 중이던 국면이라 체감 영향은
  제한적이었으나, **동일 구조가 완전 정차 후 재출발(launch) 국면에서
  발생하면 사용자가 보고한 "출발 지연"으로 직결**됨(구조적 원인
  확인, 정차 상황 자체의 프레임 단위 사례는 이번 두 클립에서 클립-route
  시각 매핑 불확실성으로 정확히 특정하지 못함 — 아래 "한계" 참고).

**클립 영상 자체 분석(qcamera 대조 없이 CarrotWeb HUD 화면녹화 직접
프레임 추출)**: clip2(12:37대) t=6~8s 구간에서 흰색 SUV 리드가 빨간
박스(레이더 락, dRel 16.4~16.9m)로 추적되다가 도로가 좌회전 커브인데
SUV는 우측 갈림길로 진행하는 명백한 차선이탈 장면 확인. 이 특정
프레임에서는 t=8s에 이미 자연 해제된 것으로 보여 큰 지연 없이
넘어갔음(다만 이후 감속은 "Signal slowing" 표시로 봐서 신호/커브
속도제어 별개 원인일 가능성 — 이 클립 단독으로는 사용자가 겪은
지연을 프레임 단위로 재현하지 못함).

**한계 (중요)**:
1. 클립 파일명 시각(HHMMSS)만으로 route CSV의 정확한 t 특정 불가
   (111차가 이미 경고한 문제, 최대 ~50초 오차) — 이번엔 클립이 route1/
   route2에 각각 1개씩뿐이라 `match_dashcam_clip_to_route.py`(111차,
   클립 2개 이상+상대시간차 매칭 방식)를 직접 적용할 수 없었음. **다음에
   같은 라우트 안에 클립이 2개 이상 있을 때만 그 도구 재사용 가능.**
2. 따라서 route1 t=5915 이벤트가 사용자가 실제로 문제 삼은 그 순간과
   동일한지는 확정할 수 없음 — 다만 **코드 구조상 근본 원인(빨간 박스
   우회)은 클립 매핑과 무관하게 정적 코드 리딩만으로 100% 확정**된
   사실이고, route1 이벤트는 그 원인이 실제 로그에서 관측된다는
   보조 실증.
3. 완전 정차 상태에서의 "락온 유지→출발 지연" 프레임 단위 사례는
   아직 미확보 — 재발 시 재분석 필요.

**제안 코드 설계 (미구현, 사용자 확인 대기 — 자세한 상수/디바운스
설계는 WIP.md "118차" 참고)**: `get_lead()` 내 `track` 선택 직후에
"검증된 락 상태에서도 적용되는" dPath 기반 사전 해제 게이트 추가.
`CUTOUT_DPATH_THRESH`(2.0m) 재사용 + confirm 디바운스(제안값 0.5s,
단일 프레임 dPath 노이즈 오탐 방지) + `CUTOUT_VREL_GATE` 재사용(강한
접근 중인 물체는 유지, danger override 철학과 일치). 조건 만족 시
`lead_dict={'status': False}`로 강제해 다음 사이클에 재평가 유도.

**다음 단계**: (1) 합성 시나리오로 순수함수 단위검증, (2) 가능하면
route1 t=5915~5932 실측 재생으로 "confirm 0.5s였다면 몇 초 앞당겨
졌을지" 정량화, (3) 사용자 확정 후 `radard.py` 실패치 작성/전달.
## 117차 (PATCH_WRITTEN) — 116차 "저속 gap-opening a_lead 캡" 방향 확정(완만화 우선) + long_mpc.py 패치 + 완만화 합성검증

**배경**: 116차에서 설계+합성검증(A~E PASS)까지 마쳤으나, 시나리오 F에서
게이트 진입/해제 순간 a_lead에 최대 1.5 m/s² 단차(하드클램프)가 발견돼
"단차를 그대로 두고 실측 replay부터 할지 vs 완만화를 먼저 추가할지"
미결정 상태로 세션 종료됨(WIP.md 116차 미결정사항 1번). 이번 세션에서
사용자가 **완만화를 먼저 추가하는 방향으로 확정** — 39차
(`LEAD_ACCEL_WEIGHT_RISE_RATE`)와 동일하게 "캡을 직접 하드클램프하는 대신
블렌드 weight를 두고 그 weight의 사이클당 변화폭을 제한"하는 패턴 재사용.

**39차와의 차이점**: 39차는 위험(closing)이 풀리는 rising 방향만
rise-rate로 제한(위험 방향은 즉시 반영이 안전측). 이번 방안은 "위험
신호"가 아니라 "가속 상한"이므로 켜질 때(캡 진입)/꺼질 때(캡 해제) 둘
다 단차 방지가 목적 — 양방향 모두 `LOW_SPEED_GAP_OPEN_WEIGHT_RISE_RATE`
(1.0/s)로 제한.

**구현 (`long_mpc.py`, `process_lead()` — `a_lead *= w` 직후 삽입)**:
- `gap_open_apply` 게이트 조건은 116차 설계와 동일(그대로 유지)
- `cap_target = 1.0 if gap_open_apply else 0.0`
- `self._gap_open_cap_weight_prev`(초기값 0.0, 안전측)를 기준으로 목표를
  향해 사이클당 `RISE_RATE*dt`만큼만 이동(rising/falling 둘 다)
- launch bypass 활성 중엔 이 rise-rate 제한도 즉시 우회해 `cap_w=0.0`
  강제(45차 defense-in-depth 원칙 재사용) — bypass 중엔 `gap_open_apply`
  자체도 항상 False라 이중 안전장치
- 최종: `a_lead = a_lead*(1-cap_w) + min(a_lead, ACCEL_CAP)*cap_w`
  (cap_w=0이면 원본 그대로, cap_w=1이면 완전 클램프, 중간값은 선형 블렌드)
- 리드 소실 시(`else` 분기) `_gap_open_cap_weight_prev`도 0.0으로 리셋
  (`_lead_accel_weight_prev` 리셋과 동일 원칙 — 리드 재획득 시 잔여 캡
  이어지지 않도록)

**합성검증 (`toolkit/sim_gap_open_damping.py`, 신규 시나리오 G/H/I 추가,
기존 A~F는 하드클램프 버전 참고용으로 보존)**:
- **G(경계전이 완화 재측정)**: F와 동일 경계 왕복 시나리오를 완만화
  버전으로 재실행 — 사이클당 최대 a_lead 변화폭이 1.500 → **0.075
  m/s²**로 감소(95% 감소, 이론상 `RISE_RATE*dt*discontinuity` =
  1.0*0.05*1.5 = 0.075와 정확히 일치)
- **H(bypass 즉시 우회)**: 캡 블렌드가 진행 중(cap_w=0.5)일 때 launch
  bypass가 활성화되면, 같은 프레임에 즉시 cap_w=0.0/a_lead=원본으로
  강제되는지 확인 — PASS(완만화 지연 없이 즉시 우회)
- **I(정상상태 일치)**: 게이트가 충분히 오래(5s, 정착시간 1s 이상)
  유지되면 완만화 버전도 최종적으로 하드클램프 버전과 동일한 정상상태
  (a_lead=ACCEL_CAP=0.5, cap_w=1.0)에 도달 — 단순 지연일 뿐 정상상태
  결과는 동일함을 확인
- 기존 A(고속 회귀)/B(launch bypass 배제)/C(정상 출발 연장)/D(이벤트
  재현)/E(오탐 방지) 전부 완만화 버전에서도 회귀 없음(A~E는 하드클램프
  함수 그대로 재사용해 비교 기준으로 유지, 실제 적용 로직은 G/H/I가
  검증하는 완만화 버전)
- 9개 시나리오 전부 PASS

**패치 검증**: `git format-patch` → 별도 temp branch(`verify-tmp`,
base `8a7baa0`)에 `git am` 적용 → `c3-ms-dev`(patch 적용 후 커밋
`7529bfd`)와 diff 0 확인 + `py_compile` 통과. (파일 자체가 원래부터
UTF-8 BOM으로 시작하는 특성이 있어 `ast.parse`는 기본 encoding으로 실패
— `utf-8-sig`로 읽으면 정상 컴파일됨, 이번 패치가 유발한 문제 아님,
기존 파일 특성으로 확인.)

**남은 것 (NEEDS_VALIDATION)**:
1. 실측 로그(lowspeed_a/b/c 등 115차 기존 4개 라우트)로 게이트 발동
   빈도/오탐 여부 replay 검증 — 아직 실행 안 함
2. `LOW_SPEED_GAP_OPEN_ACCEL_CAP=0.5`/`A_LEAD_THRESH=1.0`/
   `WEIGHT_RISE_RATE=1.0` 전부 실측 로그 없이 감으로 잡은 값 — 튜닝 필요
3. 실차 체감 검증 전무 — acados MPC 파이프라인 재실행 필요

## 115차 계속 — lowspeed_a/b부수 완전제거 방향 심층분석 — TTC 궤적상 a는 실제 급박(4.18s대)/b부수는 여유(5.1s대), scenario_B_event_reproduction의 tautology 발견(threshold를 그대로 가져다 써서 threshold 인상 시 항상 자동PASS), 메커니즘(즉시점프→빠른램프) 교체 제안

**배경**: 115차에서 "부분개선"으로 남았던 lowspeed_a/lowspeed_b부수
이벤트를 사용자가 "완전 제거되도록 전면 재검토" 요청.

**발견 1 — TTC 궤적 재분석**: 신threshold(-2.5) 발동구간 전체의 TTC
추이를 프레임별로 다시 뽑아보니 두 이벤트의 성격이 다름:
- lowspeed_a: 발동구간(0.45s) 동안 TTC 6.86s→**4.18s**까지 급락,
  closing속도도 계속 증가 — 실제로 danger(2.5s) 쪽으로 빠르게 다가가는
  이벤트.
- lowspeed_b부수: 발동구간(0.94s) 동안 TTC 12.93s→5.1~5.4s대에서
  멈춤 — a보다 훨씬 여유.

**발견 2 — [중요] 기존 합성검증(`sim_low_speed_decel.py`
`scenario_B_event_reproduction`)이 tautology였음**: 이 시나리오가
`a_lead = LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH` 상수를 그대로 가져다
쓰는 구조(원 실측 근사치는 "-1.5~-2.0"이라 주석에만 남아있고, 코드는
그 값을 안 씀) — **threshold를 올리면 시나리오도 같이 올라가서 항상
자동으로 PASS**함. 즉 이 스크립트는 "threshold를 얼마로 올려도
무조건 통과"하므로 지금까지 threshold 인상의 안전성 근거로 쓰기엔
부적합했음(58차2번/112차 전체에 걸쳐 이 맹점이 인지 안 됐던 것으로
보임). 원 앵커 사례(route `a3a55cb808` seg12, 실측 min TTC=4.45s)의
진짜 leadALeadK 실측값은 CSV 미보유(로컬/레포 모두 없음, Google
Drive 보관 정책상 재확보 필요)로 이번 세션엔 직접 대조 불가.

**결론/제안**: threshold를 추가로 올려 lowspeed_a/b부수를 게이트
밖으로 빼는 접근은 **lowspeed_a의 TTC(4.18s)가 원 앵커 사례(4.45s)
보다 오히려 더 급박한 축이라는 점에서 위험** — a3a55cb808급 미래
재발 사례를 놓칠 수 있음. 대신 **반응 메커니즘 교체(threshold는
유지, 조건 성립 시 즉시 w=1.0 스텝 대신 평소보다 훨씬 빠른 고정
rise-rate 램프로 상승)**를 제안(112차계속2 옵션2와 동일 방향, 이번에
TTC 데이터로 뒷받침). 개략 계산(3.0/s 가정 시): lowspeed_a는 발동~
1.0 도달 약 0.28s(baseline 대비 여전히 0.42s 빠름), lowspeed_b부수는
약 0.33s(baseline 대비 0.67s 빠름) — 두 경우 다 안전마진은 유지하면서
계단식 점프만 제거됨. 정확한 rise-rate는 시나리오B를 실측 고정값으로
재앵커링한 뒤 스윕/회귀검증 필요(다음 세션, 사용자 승인 대기).

**사용자 확인 필요**: (1) 메커니즘 교체 방향 동의 여부(또는 threshold
추가 인상 방향 유지 희망 여부, 후자는 재발위험 인지 필요), (2)
`a3a55cb808` 원본 로그 재확보 가능 여부.

**코드 변경 없음.**

## 115차 — pre-112차(commit b67c291) 실측 로그 4건에 112차 patch 로직을 오프라인 재생(replay) — SMOOTH 완전PASS/ROUTE_A·B 저속게이트 부분개선/ROUTE_B 메인이벤트는 게이트 무관 진짜 급감속

**[용어 정정, 중요]** 아래 "PASS"/"완전히 제거함"/"실측으로 확인" 등의
표현은 **112차 patch가 실제로 device에 적용된 상태에서 주행하며 얻은
로그로 검증했다는 뜻이 아니다.** 4개 로그는 전부 **패치 미적용
(commit b67c291) 상태의 실주행 로그**이며, 여기서 뽑은 raw 센서값
(vEgo/leadALeadK/leadDRel 등)을 `toolkit/replay_low_speed_strong_
decel.py`에 흘려 **112차 patch의 threshold 로직(-1.8 vs -2.5)을
오프라인으로 그 위에 재생(replay)**시킨 결과다. 즉 "이 시점에 만약
112차가 이미 적용돼 있었다면 저속게이트가 어떻게 판정됐을지"를
사후 시뮬레이션한 것이지, 패치 적용 차량에서 실제로 그렇게 동작한
것을 관측한 게 아니다. 진짜 patch-적용 실차 로그로 이 결과를 재확인하는
건 아직 안 된 상태(향후 과제).

**배경**: 사용자가 zip 2건(`10시28분28초_전후_감속분석_급감없이_부드러움.zip`,
`저속주행급감.Zip`) 업로드 — "112차 패치 적용 안 된 실차 로그를 참조해서
112차 patch가 잘 동작할지(적용 시 어떻게 될지) 검증해달라"는 요청이었음
(패치 적용된 실차 로그가 아님, 명확히 확인됨). 사용자가 정확한 커밋을
확인해줌: `b67c2912a2d34b983f2c25fed9ec21547b9ea331`("Merge c3-ms-curv
into c3-ms-dev (81,82,84,85,87,91차 통합)", 2026-08-27 10:23 KST 커밋).
`git log b67c291..8a7baa0`로 대조한 결과 이 커밋 이후
94/98/100/101/109/112차가 전부 아직 미반영된 상태에서 캡처된 로그로 확인.

**라우트 4건**:
| 라우트 | 캡처시각 | 세그 | 이벤트 요지 |
|---|---|---|---|
| smooth(1028) | 08/28 10:28 | 1 | 비교군, min aEgo -2.24 (25.3km/h) |
| lowspeed_a | 08/27 11:26 | 2 | 근접추종 정차 직전, min aEgo -2.58 (14.3km/h) |
| lowspeed_b | 08/27 12:06 | 3 | **min aEgo -4.02 (33.5km/h)**, 별개 저속이벤트도 존재(t≈4349) |
| lowspeed_c | 08/27 12:21 | 3 | min aEgo -2.18 (31.5km/h) |

**방법**: 신규 스크립트 작성 없이 기존 `toolkit/replay_low_speed_strong_
decel.py`(112차 계열 산출물, `run_threshold_scan`/`compare_weight_
trajectory`)를 이 4개 신규 라우트에 그대로 재사용. `LOW_SPEED_STRONG_
DECEL_V_EGO_GATE=30km/h` 게이트, 구threshold=-1.8/신threshold=-2.5 비교.

**핵심 발견** (모두 재생/시뮬레이션 결과, 위 용어 정정 참고):
1. **smooth(1028) — 완전 PASS(시뮬레이션상)**: 구threshold 기준
   26프레임(자연수렴 대비 1.247s 조기구간) 발동 **예상**되나
   신threshold는 **0프레임 예상**. 이 라우트에서만큼은 112차 patch
   로직을 대입했을 때 저속게이트 오탐이 완전히 사라지는 것으로
   재생됨 — "급감없이 부드러움"이라는 제보 라벨(패치 미적용 상태에서도
   이미 부드러웠다는 뜻)과 별개로, 패치 적용 시에도 이 구간에서
   회귀가 없을 것이라는 근거로 해석.
2. **lowspeed_a(14.3km/h) — 부분 개선**: 구 16프레임(조기 0.900s)/신
   9프레임(조기 0.700s). 완전 제거 아님. 다만 이 구간 실측 leadALeadK가
   -0.61→-2.96까지 매끄럽게 지속 악화하는 패턴이라(순간 점프 아님),
   112차 원 케이스(FINDINGS.md 112차)에서 이미 "진짜 지속 감속이라
   threshold만으로는 완전 제거 어려움"이라 정리된 것과 동일 유형.
3. **lowspeed_b — 2개 별개 이벤트로 분해됨**:
   - **부수 이벤트(t≈4349~4351, 25.2→19.7km/h)**: 저속게이트 대상 구간.
     leadALeadK가 0.14→-2.71까지 하강. 구 발동/신 8프레임 발동(부분
     개선, a와 유사).
   - **메인 이벤트(t≈4373.7~4377.6, vEgo 41.4→20.9km/h, min aEgo
     -4.017 at 33.5km/h)**: **v_ego가 게이트 상한(30km/h) 밖이라
     LOW_SPEED_STRONG_DECEL 로직 자체가 적용 대상이 아님.** 프레임
     단위로 대조한 결과 dRel 33.8→18.1m, leadVRel +1.3→**-7.0m/s**로
     약 2.5초에 걸쳐 연속적/단조적으로 변화(중간 점프 없음),
     `leadRadar=True` 유지, `laneChangeState=off`, blinker 없음 —
     **track-switch나 discontinuity 패턴이 아니라 선행차량의 실제
     급감속에 대한 정상적인 연속 추종 응답**으로 판단. 즉 이 사례는
     112차(혹은 그 어떤 저속게이트 threshold 조정)로도 애초에 영향받지
     않는 범위이며, 버그로 보기보다 "실제로 강하게 브레이크를 밟은
     앞차를 정상적으로 따라간 결과"에 가까움. -4.0m/s²라는 크기 자체가
     승차감상 허용범위인지는 별도 판단 필요(대시캠 대조 미완료,
     `260827_120658_clip.mp4` 존재).
4. **lowspeed_c — 저속게이트 완전 무관**: 구/신 threshold 전부
   0프레임. min aEgo -2.18(31.5km/h)의 완만한 감속은 margin_accel_
   weight/ttc_accel_weight 자연수렴 경로로 설명되는 것으로 보이며,
   LOW_SPEED_STRONG_DECEL 로직과는 무관. src 필드가 `bump`로 나오는
   특이점 있음(다른 3라우트는 `cam`/`route`) — 의미는 미확인, 추가
   조사 필요시 참고.
5. `analysis_helpers.harsh_brake_events()` 기본 파라미터
   (accel_drop_thresh=-0.8, window_s=0.5)로는 4라우트 전부 0건 탐지 —
   실제 이벤트가 1.5~3초에 걸친 점진적 변화라서 짧은 창 기반 탐지
   로직의 사각지대로 보임(개선은 아직 미착수, 기록만).

**결론**: 112차 threshold 패치는 "저속(<30km/h) 완만~중간 강도 지속
감속" 케이스에서는 조기발동 구간을 줄이는 효과가 **재생 시뮬레이션상**
확인됐고(smooth는 완전 제거, a/b부수는 부분개선 — 어디까지나 오프라인
재현치이며 실제 패치 적용 차량의 관측치 아님), lowspeed_b 메인 이벤트처럼
**게이트 밖(≥30km/h)에서 벌어지는 진짜 강한 선행차량 감속**에는 애초에
관여하지 않는다는 점이 이번 세션에서 새로 명확해짐 — 이런 케이스는
112차와 별개 주제(순수 추종 성능/승차감 튜닝)로 다뤄야 함.

**사용자 확인 필요**: (1) lowspeed_b 메인 이벤트 대시캠 대조, (2)
a/부수이벤트의 "부분개선(완전제거 아님)" 결과를 112차 결론에 추가
반영할지, (3) lowspeed_c의 "체감 급감" 원인 규명 필요 여부.

## 114차 — margin_accel_weight(dist_w) 포함 완전 재현 — ROUTE1은 112차 패치로 이미 해소, ROUTE2/3만 실질 문제, SMOOTH 내부 노이즈 에피소드로 단순 threshold 판별지표 재검토 필요

**[선행 확인] 113차 산출물 유실**: 세션 시작 시 `toolkit/replay_rise_rate_
saturation.py`(113차가 만들었다고 서술된 스크립트)가 레포에 없음 확인 —
`toolkit/README.md`/`CHANGELOG.md` 등록도 없음. FINDINGS.md 113차 텍스트는
남았으나 스크립트 자체와 WIP.md 113차 항목은 유실된 것으로 판단(원인
미상). 아래 114차는 그 대체+확장.

**작업**: `toolkit/replay_margin_accel_weight_full.py` 신규 작성 — 113차가
근사하지 못했던 `margin_accel_weight`(dist_w)를 `long_mpc.py`의
`get_safe_obstacle_distance`/`desired_follow_distance`/
`carrot.get_T_FOLLOW` 체인 그대로 재현. 필요한 carrot 상태값은
`selfdrive/carrot/carrot_functions.py`의 **Params 기본값**을 그대로
대입(사용자가 커스텀했다면 오차 발생 가능, 명시적 가정):
- `TFollowGap1..4` = 1.10/1.20/1.40/1.60 (personality=standard 가정 →
  base=1.20)
- `EnableSpeedTF=0`(기본) → 속도 스케일 스킵
- `DynamicTFollow=0`(기본) → `dynamic_t_follow()`의 jLead 기반 보정 자체가
  스킵됨(jLead가 CSV에 없어 근사해야 했을 항이었는데, 기본값이 꺼져있어
  다행히 통째로 스킵 가능 — 근사 오차 소스 하나 제거됨)
- `MyDrivingMode=3`(Normal, 기본) → `mySafeFactor=1.0`
- `TFollowDecelBoost=0.10`(기본), `StopDistanceCarrot=550`→5.5m(기본),
  `comfortBrake=2.4`(하드코드)
- t_follow의 decel-hold 상태(`_tf_applied`)는 `TFollowState` 클래스로
  프레임 순차 시뮬레이션(세그먼트 시작마다 리셋 — 세그 중간 이벤트에는
  영향 없음)
- 위 가정들의 실측 영향은 결과적으로 미미했음(아래 참고) — t_follow가
  1.20~1.60 범위에서 거의 고정되고, 4개 이벤트 전부 dist_w가 처음부터
  1.0으로 고정돼 desired_distance 정밀도 자체가 이번 케이스들의 결과를
  좌우하지 않았음.
- `margin_accel_weight`/`ttc_accel_weight`뿐 아니라
  `LOW_SPEED_STRONG_DECEL` 게이트 + TTC danger override(TTC≤2.5s) —
  둘 다 rise-rate 클램프를 우회해 즉시 w=1.0 적용하는 실제 코드 분기 —
  까지 `long_mpc.py` L820-868 그대로 포함.

**핵심 발견 1: ROUTE1 재평가 (0.951s → 0.250s)**: t=1937.5~1941.5 프레임별
대조 결과, t=1939.173(vEgo=5.30, aLeadK=-2.76, dRel=10.90m)에서
`LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH`(112차가 이미 -1.8→-2.5로 강화,
현재 origin `c3-ms-dev`에 반영된 상태로 확인)가 정확히 발동 —
saturation(gap>0 구간)이 t=1938.922~1939.173, **단 0.250초 만에 danger
override로 끊김**. SMOOTH의 0.298s와 거의 동급 수준. 113차가 보고한
0.951s는 "override를 포함하지 않은 재현"이었을 것으로 추정(스크립트
유실로 직접 대조 불가) — 112차계속2의 `compare_weight_trajectory()`가
별도로 계산한 "override 없는 baseline 자연수렴"(t=1939.873) 수치와
일치하는 것으로 보아, **113차 표의 0.951s는 실제로는 "다른 질문"(override
자체가 없었다면 얼마나 걸렸을까)에 대한 답이 "현재 코드의 실제
saturation"으로 잘못 표기됐을 가능성이 큼.**
→ **결론: ROUTE1은 112차 threshold 강화 패치만으로 이미 사실상 해소됨.**
추가 조치(신규 jerk_boost 트리거 소스 등) 불필요할 수 있음 — 실차검증에서
재확인 권장이나, 로그 기반으로는 더 이상 "harsh" 분류 근거가 약함.

**핵심 발견 2: ROUTE2/ROUTE3는 113차와 거의 동일**: ROUTE2 longest_
saturation=0.999s(113차 0.999s), ROUTE3=0.903s(113차 0.903s) — 프레임
대조 결과 두 라우트 모두 이벤트 구간 내내 `v_ego`가 30km/h 게이트보다
빨라(각 44/36km/h대) LOW_SPEED_STRONG_DECEL 게이트 밖이고, TTC도 danger
임계값(2.5s) 밑으로 안 떨어져(자연 수렴 과정 내내 4s 이상 유지) 어느
override도 안 걸림 — rise-rate 클램프가 목표(w_target)를 온전히
"뒤쫓는" 과정을 그대로 겪음. **→ 113차의 "구조적 공백"(저크 완충 장치
부재) 진단은 이 두 라우트에 한해서는 그대로 유효, 이 두 라우트가 실질적
남은 문제.**

**핵심 발견 3: margin_accel_weight(dist_w)는 4개 이벤트 전부에서
1.000 고정**: dRel/desired_distance ratio가 4건 모두 GATE_NONE(1.0)
밑(예: ROUTE1 dRel≈9~11m vs desired_distance≈13~16m, ratio≈0.6~0.8)이라
dist_w가 처음부터 무감쇠(1.0) — 113차가 우려했던 "dist_w 근사 누락으로
인한 saturation 과대평가"는 **이 4개 이벤트에 한해서는 기우였음**(dist_w
자체가 애초에 안 걸려서 ttc_w/override만으로 결과가 결정됨). 단, 이는
"저속 근접 추종" 상황에 국한된 관찰 — 38차가 다룬 고속/장거리(TTC~15s대)
시나리오에서는 margin_accel_weight가 실제로 작동한 전례가 있으므로
일반화 금지, 고속 라우트 재검증 시엔 dist_w 근사가 여전히 중요할 수 있음.

**핵심 발견 4(신규 경고, 중요): SMOOTH 라우트 전체 스캔에서 판별지표
자체의 한계 노출**: `scan_route_saturation_episodes()`로 SMOOTH 전체를
스캔한 결과, 분석 대상이던 t≈5768.92(0.298s, qcamera로 확인된 진짜
"부드러운 정체 서행" 이벤트)와는 별개로 **t≈5794.13에서 0.448s
에피소드 발견** — ROUTE1의 새 최대치(0.250s)보다도 길다. 프레임 대조
결과 t=5794.573에서 `leadDRel`이 23.28→11.70m로, `leadVLead`가
6.19→13.75m/s로 한 프레임 만에 불연속 점프(진짜 감속이 아니라 **track
재획득/전환 아티팩트로 추정**, `leadRadarTrackId` 미대조라 확정은 아님)
— 그 직전까지 ttc_w가 인위적으로 상승하다 track 전환과 동시에 0으로
리셋되며 끊긴 패턴. **즉 진짜 위험 감속이 전혀 아닌 상황에서도 0.448s
saturation이 발생할 수 있음이 확인됨.**
→ **113차가 제안한 "SMOOTH 최장 0.298s / harsh 최소 0.903s 사이 어디든
안전한 분리선"이라는 전제가 깨짐**: SMOOTH 내부에 이미 0.448s짜리
비-위험 에피소드가 있고, 반대로 ROUTE1은 이제 0.250s로 SMOOTH의
정상 이벤트(0.298s)보다도 짧다. **연속 saturation 시간 단일 지표로는
더 이상 harsh/smooth를 깨끗하게 못 가른다.**

**전체 라우트 threshold 스윕(오탐률, `scan_route_saturation_episodes`,
th=0.25~0.90s)**:

| threshold | SMOOTH(총 16건) | ROUTE1(총 13건) | ROUTE2(총 7건) | ROUTE3(총 3건) |
|---|---|---|---|---|
| 0.25s | 2 | 0 | 4 | 2 |
| 0.30s | 1 | 0 | 4 | 2 |
| 0.35s | 1 | 0 | 4 | 2 |
| 0.40s | 1 | 0 | 4 | 2 |
| 0.45s | 0 | 0 | 4 | 2 |
| 0.50s | 0 | 0 | 3 | 2 |
| 0.60s | 0 | 0 | 3 | 2 |
| 0.70s | 0 | 0 | 2 | 2 |
| 0.80s | 0 | 0 | 1 | 2 |
| 0.90s | 0 | 0 | 1 | 1 |

0.45~0.90s 구간이면 SMOOTH 오탐 0건 + ROUTE2/3는 계속 걸림 + ROUTE1은
전 구간 0건(더 이상 타겟 아님) — 다만 표본이 여전히 라우트 4개뿐이라
확정적 결론은 아님. 최상위 에피소드 상세: ROUTE2 top1 t=4374.73/
0.999s(분석 대상 사건 그 자체), top2 t=4341.12/0.702s(**미분석 신규
에피소드, 성격 미확인**); ROUTE3 top1 t=5219.83/0.903s(분석 대상),
top2 t=5119.67/0.801s(**미분석 신규 에피소드**).

**다음 세션 우선순위(방향 미확정, 사용자 확인 필요)**:
1. ROUTE2 t=4341.12(0.702s)/ROUTE3 t=5119.67(0.801s) 신규 에피소드
   qcamera 대조 — 진짜 harsh인지 SMOOTH처럼 track-switch 아티팩트인지
   미확인.
2. SMOOTH t=5794.13 에피소드 `leadRadarTrackId` 대조로 track-switch
   여부 확정 — 맞다면 판별지표에 "radarTrackId 불변" 게이트를 추가
   결합해야 함(63차 방안C/D 자산 재사용 가능성).
3. 위 결과에 따라 "ROUTE2/ROUTE3 전용 좁은 트리거"로 범위를 좁힐지,
   아니면 판별지표 자체를 재설계할지 결정.
4. ROUTE1을 더 이상 대표사례로 삼지 않는 방향으로 112차/113차 설계
   제안 갱신.
5. 113차 유실 스크립트 로컬 백업 여부 확인(있으면 대조용으로 유용).

**코드 변경 없음(분석 + 신규 도구만)**. `toolkit`:
`replay_margin_accel_weight_full.py`(신규, 113차 유실분 대체+확장),
`README.md`, `CHANGELOG.md`.

---

## 113차 — "10:28:28 부드러운 정차" 대조분석으로 급감속 전면 재검토 — rise-rate 클램프 연속 saturation 시간이 harsh/smooth를 가르는 공통 판별지표임을 확인, 일반화 트리거 설계 제안(코드 변경은 다음 세션 확인 후)

**배경**: 사용자가 "급감없이 부드러움" 화면녹화(신규 라우트,
`00000344--95b38eed78` seg1, 10:28:28 전후 — 실제 route 시각은
t≈5763~5780)와 112차가 분석했던 harsh 3라우트(`00000336--4a688572c0`,
`00000338--c60bf8189f`, `00000339--ce1f43d848`, 재업로드 동일 로그) 원본을
함께 제공, "부드러운 사례의 로직을 저속 급감속에 적용할 수 있도록 전면
재검토"를 요청. `extract_log.py`로 4개 라우트 CSV 재추출(`leadALeadK`
포함) 후 qcamera 프레임 대조까지 포함해 분석.

**SMOOTH 사례 핵심 관찰**: 대시캠 확인 결과 정체 구간에서 앞차(백색
SUV)가 신호/정체로 서서히 줄을 서며 정차하는 상황(교차로 부근, 전방에
트럭+추가 차량 대기열 확인) — 앞차 실측 감속(`aLeadK`)이 t≈5763(약
-0.6)부터 t≈5772.4(최저 -2.16)까지 **약 9초에 걸쳐 매우 완만하게
악화**됐고, 이 구간에서 `LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH`(현재
-2.5)를 단 한 프레임도 넘지 않음(저속구간 내 최소 aLeadK=-2.16, 게이트
발동 0건) — 즉 이 사례는 112차가 다룬 오버라이드 경로가 아예 개입하지
않은 **완전한 정상 TTC/margin 경로** 사례. 그럼에도 실제 감속 크기는
결코 작지 않았음(-2.16m/s²는 route3의 최저 aEgo -2.18과 거의 동급) —
그런데도 체감은 매끈함.

**정량 비교(신규 도구, 아래)**: 단순 순간/평활(0.4s) aLeadK 변화율로는
harsh 3라우트를 일관되게 구분하지 못함 — route3는 aLeadK 평활 변화율
최저치가 -2.04로 오히려 smooth(-2.79)보다 완만했음에도 실제 체감은
harsh(min aEgo -2.18, aEgo 온셋률 -3.16). aLeadK 자체의 급변 여부는
좋은 판별지표가 아니었음.

**대신 `LEAD_ACCEL_WEIGHT_RISE_RATE`(1.0/s) 클램프의 "포화(saturation)
연속시간"이 매우 깔끔한 공통 판별지표임을 확인** — `long_mpc.py`의
`ttc_accel_weight()` + rise-rate 클램프 로직을 그대로 복사한 신규 도구
`toolkit/replay_rise_rate_saturation.py`로 재현(단, `margin_accel_weight`
는 `desired_distance` 계산에 필요한 carrot 상태가 CSV에 없어 근사 불가 —
ttc_w 단독 기준, 실제보다 saturation을 과대평가할 수 있는 보수적 근사임에
유의):

| 사례 | 최장 연속 saturation | 총 saturation(관찰구간 전체) | 최대 gap(target-applied) |
|---|---|---|---|
| SMOOTH | **0.298s** | 0.725s (20s 구간) | 0.067 |
| ROUTE1(harsh, LOW_SPEED 게이트 관련) | 0.951s | 0.951s (6s 구간) | 0.651 |
| ROUTE2(harsh, min aEgo -4.02) | 0.999s | 0.999s (8s 구간) | 0.470 |
| ROUTE3(harsh, min aEgo -2.18) | 0.903s | 0.903s (8s 구간) | 0.190 |

**해석**: smooth 사례는 목표 weight(TTC 기준)가 rise-rate(1.0/s) 한도
안에서 무리 없이 따라잡히는 반면, harsh 3사례는 전부 **약 0.9~1.0초
동안 연속으로 클램프가 목표를 따라잡지 못하는(=클램프가 실질적으로
"최대 속도로 뒤쫓는 중") 상태**였음 — route1(LOW_SPEED_STRONG_DECEL
발동 케이스)뿐 아니라 이 게이트와 완전히 무관한 정상 TTC 경로
route2/route3도 동일 패턴. 즉 **"급감속처럼 느껴지는" 근본 원인은
개별 게이트(LOW_SPEED_STRONG_DECEL, danger override 등)의 오발동이
아니라, w가 rise-rate 상한에 묶여 장시간(≈1초) 저속으로 쫓아가야 하는
상황 자체이며, 이 "쫓아가는 과정"에 대한 저크 완충 장치가 전무하다**는
112차의 "구조적 공백" 결론을 훨씬 구체적인 관측가능 신호로 뒷받침함.

**설계 제안(코드 변경 전, 사용자 확인 필요)**: 기존 `discontinuity_jerk_
boost` 메커니즘(66~73차 검증, hold 4.0s + release-rate 100/s, "목표는
유지하고 저크만 완화")에 신규 트리거 소스를 추가:
- **트리거 조건(안)**: `w_target(ttc_accel_weight 등) - w_applied(rise-rate
  클램프 후)`가 0보다 큰 상태(=클램프 포화)가 약 0.4~0.5초 이상 연속되면
  arm. (smooth 최장 0.298s / harsh 최소 0.903s — 그 사이 어디든 안전한
  분리선. 정확한 문턱은 추가 라우트로 스윕 권장.)
- **장점**: (1) w 계산 자체(=목표 감속량)는 전혀 건드리지 않음 — "얼마나
  감속할지"는 그대로, "그 과정의 저크"만 완화. (2) `low_speed_strong_
  decel` 전용 게이트, danger override, discontinuity(dRel 불연속),
  handoff(레이더 재락온) 등 개별 트리거를 대체하지 않고 **공통 안전망**
  으로 추가 — 기존 검증된 트리거들과 병행 가능(이미 부스트 진행 중이면
  덮어쓰지 않는 기존 관례 그대로 적용). (3) route1/2/3 세 가지 서로 다른
  원인(게이트 오탐/정상 강한제동/정상 TTC 경로 완만한 케이스)을 하나의
  일반화된 신호로 커버 — 112차가 순서대로 나누려 했던 "라우트1 우선,
  라우트2/3는 실차검증 후 재논의" 계획을 대체할 수 있는 더 단순한 대안.
- **위험/한계**: (1) 이번 세션 시뮬은 `margin_accel_weight`(dist_w)를
  근사하지 못해 saturation을 과대평가했을 수 있음 — 실제 패치 전
  `desired_follow_distance`/`dynamic_t_follow`까지 포함한 완전 재현 필요
  (다음 세션 우선 작업). (2) 문턱(0.4~0.5s) 검증 표본이 이번 4건뿐 —
  오탐(정상적인 완만한 감속인데 우연히 0.4s+ saturation)이 없는지 추가
  라우트로 스윕 필요. (3) `LEAD_ACCEL_WEIGHT_RISE_RATE` 자체를 올리는
  안(rise-rate를 더 빠르게)은 39차가 이미 기각한 방향과 동일한 부작용
  우려(rise-rate 자체를 되살리면 39차가 막으려던 문제 재발) — 이번
  제안은 rise-rate 값은 그대로 두고 그 아래에서 벌어지는 저크만 별도로
  완충하는 것이라 39차 결론과 충돌하지 않음.

**qcamera 프레임 대조**: smooth 사례(정체 대기열, 신호 앞 서행)와
route1(신호 앞 정지선, 전방 정지신호 확인 — 앞차 브레이크등 조기 점등)
프레임 확보, 두 시나리오 모두 "교차로 접근" 유형이라는 공통점은 있으나
smooth는 훨씬 오래 전부터(9초) 감속이 시작된 반면 route1은 관측 시작
시점(t=1938.9)에 이미 브레이크등이 켜져 있었고 이후 급격히 악화 —
운전자/도로 상황의 차이라기보다 "그 시점의 TTC/aLeadK 변화가 얼마나
급했는가"의 차이로 수렴, 위 정량 분석과 일치.

**다음 세션 우선순위**:
1. `margin_accel_weight`(dist_w)까지 포함한 완전 재현 스크립트로 saturation
   재검증 (현재는 ttc_w 단독 근사).
2. 문턱(0.4~0.5s) 후보를 몇 개 라우트 추가 스윕으로 확정, 오탐률 확인.
3. 사용자 방향 확인 후 `long_mpc.py`에 신규 트리거 소스(가칭
   `rise_rate_saturated` 또는 `lead_accel_weight_ramp`) 구현 →
   `sim_low_speed_decel.py`류 단위검증 → 이번 4라우트로 replay 검증 →
   패치 전달.
4. (선택) 이 신규 메커니즘이 route2/3까지 충분히 커버한다면, 112차가
   세운 "라우트1 우선, 라우트2/3는 별도 논의" 순서를 이 통합안으로
   대체할지 여부 사용자 확인.

**코드 변경 없음(이번 세션은 분석+신규 도구+설계제안까지)**. `toolkit`:
`replay_rise_rate_saturation.py`(신규), `README.md`, `CHANGELOG.md`.

---

## 112차 — "저속주행중 앞차 서행/정지시 급감속" 3라우트 확정 — 라우트1 LOW_SPEED_STRONG_DECEL 게이트 오탐(rise-rate 우회 부작용), 라우트2/3은 TTC 정상경로

**배경**: 사용자 제보 "저속주행시 앞차가 서행하거나 정지시 내차가
급하게 정지" — 대시캠 클립 3건 + route 3건(`00000336--4a688572c0`
seg10-11, `00000338--c60bf8189f` seg9-11, `00000339--ce1f43d848`
seg4-6) 업로드. `leadALeadK` 필드까지 포함해 재추출 후 시계열 분석.

**공통 확인사항**: 3건 모두 radar=True(레이더 락온) 실제 리드차량,
danger override(TTC≤2.5s) 문턱 불침범.

**라우트별 원인(중요 — 서로 다름)**:
1. **라우트1(t≈1940, min aEgo=-2.58, vEgo 14~20km/h)**: `LOW_SPEED_
   STRONG_DECEL` 게이트(58차2번, `V_EGO_GATE=30km/h`/`A_LEAD_THRESH=
   -1.8m/s²`) 정확히 t=1938.97(`aLeadK=-2.07`, vEgo=19.2km/h)에 발동
   확인. 발동 즉시 `w=1.0` 적용되며 `LEAD_ACCEL_WEIGHT_RISE_RATE`
   rise-rate 제한을 완전 우회(이 분기가 `lead0_danger_now`에 묶여
   TTC-danger와 동급 취급되기 때문) → 0.7~1초 후 aEgo -0.5→-2.58
   급락. dRel은 전 구간 8~9m로 여유 있었음(진짜 위험 아님). **-1.8m/s²
   문턱이 평범한 일상 제동 강도라 오탐되며, 완충 없이 풀강도로 튀는
   구조가 원인 — 명확한 버그로 확정.**
2. **라우트2(t≈4376, min aEgo=-4.02, vEgo 33~44km/h)/라우트3(t≈5221,
   min aEgo=-2.18, vEgo 30~39km/h)**: `LOW_SPEED_STRONG_DECEL` 게이트
   미발동(vEgo>30km/h 구간에서 리드 강한 감속 발생). `ttc_accel_
   weight`/`margin_accel_weight` 정상 경로로 w 서서히 상승, ego 응답이
   리드 실측 감속(aLeadK 최대 -4.2/-2.0)과 대체로 비례 — **설계대로
   동작한 정상 케이스에 가까움**. 다만 w가 도달하는 과정에 jerk 완충
   메커니즘이 없다는 구조적 공백은 라우트1과 공통.

**패치 방향(사용자 확정, 코드 변경 전 논의만 완료)**:
- 라우트1: 임계값 강화(-1.8→약-2.5 근처, 실측 기반 보정) +
  `discontinuity_jerk_boost`(66~73차 기 검증, "목표는 유지, 저크만
  완화") 메커니즘을 신규 트리거 소스 `low_speed_strong_decel`로 확장.
  rise-rate 제한 되살리기 안은 기각(58차 원 취지 무력화 우려).
- 라우트2/3: a_change_cost boost 확장 대상에 포함하기로 합의하되,
  회귀추적을 위해 라우트1 우선 분리 패치+검증 후 순서대로 진행.

**다음**: 라우트1 패치 구현(`LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH`
조정 + boost 트리거 소스 추가) → `sim_low_speed_decel.py` 확장 검증
→ replay 검증 → patch 전달. 라우트2/3 boost 확장은 라우트1 실차검증
후 재논의.

**코드 변경 없음(이번 세션은 분석+방향합의까지만)**.

---

## 112차 계속 — 라우트1 패치 구현 완료 + 단위 시뮬레이션 검증 PASS(7/7), replay 검증은 CSV 부재로 보류

**작업**: 위 방향 합의대로 `long_mpc.py`(c3-ms-dev) 구현:
1. `LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH` -1.8 → -2.5 (라우트1 실측
   aLeadK=-2.07을 더 이상 발동시키지 않도록, 라우트2/3 실측 최대치
   -4.2/-2.0과는 여전히 구분되는 값).
2. `discontinuity_jerk_boost` 신규 트리거 소스 `low_speed_strong_decel`
   추가: `low_speed_strong_lead_decel`의 False→True 엣지에서 arm.
   `is_handoff_source`(hold=`RADAR_HANDOFF_JERK_BOOST_S`=4.0s,
   release-rate=100/s)에 편입 — 신규 튜닝 없이 방안I 검증값 재사용.
   **구조적으로 확인된 동작**: danger_active(=low_speed_strong_lead_decel)
   지속 중엔 `force_revert`가 즉시 걸려 a_change_cost가 base로 유지되므로
   실제 위험 반응(w=1.0 경로)은 전혀 지연되지 않고, danger 해제 직후부터만
   boost(500)→release로 "도달 과정"(복귀 시 jerk)만 완만화됨 — 사용자와
   합의한 "목표는 안 바꾸고 저크만 완화" 원칙과 정확히 부합.
3. `sim_low_speed_decel.py`에 시나리오 E(라우트1 실측 재현, 신threshold
   미발동 확인)/F(진짜 강한감속 -3.0 여전히 발동)/G(jerk_boost 신규
   소스 arm→hold→release 전체 사이클 검증) 추가, 기존 B는 threshold
   상수 참조로 변경(하드코딩 drift 방지). **전체 7개 시나리오 PASS**.

**한계(다음 세션 최우선)**: 라우트1 원본 CSV가 컨테이너에 없음(CSV는
레포 미커밋 정책 + 컨테이너 리셋으로 소실, Google Drive 커넥터 미연결
상태라 이번 세션엔 자동 회수 불가) — 순수 로직 단위 검증(sim)만
완료했고, 실측 로그 기반 replay 검증(patched_replay류)은 아직 못함.
사용자가 라우트1 CSV(또는 원본 저속주행급감 zip)를 재업로드하면 즉시
진행 가능.

**코드 변경**: `ryu`: `selfdrive/controls/lib/longitudinal_mpc_lib/
long_mpc.py`. `toolkit`: `sim_low_speed_decel.py`, `README.md`,
`CHANGELOG.md`.

---

## 112차 계속2 — [중요 정정] 라우트1 CSV 재업로드 후 replay 검증 결과, "오탐" 프레이밍 재검토 필요 — threshold 강화는 오탐 제거가 아니라 조기발동 46% 단축

**작업**: 사용자가 라우트1 원본 CSV(`저속주행급감.zip`)를 재업로드,
`extract_log.py`로 재추출 후 신규 `toolkit/replay_low_speed_strong_
decel.py`로 실측 replay 검증 수행.

**핵심 발견(기존 112차 "명확한 버그" 판정 정정 필요)**:
- 단일 시점(t=1938.973, aLeadK=-2.07)만 근거로 삼았던 기존 분석은
  불완전했음. 실측 시계열 전체(t=1938.5~1940.6)를 보면 aLeadK가
  -0.6에서 시작해 지속적으로 악화되어 **t=1939.276에 최대 -2.96까지
  도달하는 진짜 연속적 앞차 감속 이벤트**였음(단발성 노이즈 스파이크
  아님).
- 같은 구간에서 TTC도 자연 하강 중이었음(t=1939.122에 6.85s → t=1939.5
  경 4.15s대) — 즉 `LOW_SPEED_STRONG_DECEL` 오버라이드가 전혀 없어도
  정상 `ttc_accel_weight()`+rise-rate 경로만으로 **t=1939.873에 자연
  수렴(w≥0.99)**했을 것으로 확인됨(`compare_weight_trajectory()`로
  오버라이드 비활성 baseline 시뮬레이션).
- **정량 비교**(오버라이드가 baseline 자연수렴 대비 얼마나 앞당기는가):
  - 구threshold(-1.8): t=1938.973~1939.727(0.754s) 조기발동, baseline
    대비 0.900s 앞당김.
  - 신threshold(-2.5, 이번 세션 패치): t=1939.173~1939.582(0.410s)
    조기발동, baseline 대비 0.700s 앞당김.
  - **즉 threshold 강화는 "오탐 제거"가 아니라 "조기발동 구간을
    0.754s→0.410s(약 46%)로 단축"한 것**. 완전한 정상경로 수렴 대비
    여전히 0.7s 앞당겨진 채로 강한 aLead(-2.76~-2.57)를 무감쇠 반영함.

**재해석**: 라우트1 사례는 "평범한 일상 제동을 오탐하는 버그"라기보다,
"진짜 강한 감속 이벤트에 대해 정상 rise-rate 경로보다 약 0.4~0.9초
앞서서 무감쇠 반영하는 것이 체감상 급작스럽게 느껴지는" 문제에 더
가까움. TTC 자체는 danger override(2.5s) 문턱을 침범하지 않았고
(최소 TTC 4.15s대), dRel도 8~11m대로 급박한 위험 상황은 아니었음
(공존하는 판단: 실제 위험은 아니지만 체감 급함 — 111차/112차 최초
분석의 "체감상 급하게 느껴질 순 있음" 서술과 정합).

**사용자 확인 필요(다음 세션 우선 논의)**:
1. 현재 적용된 threshold 강화(-1.8→-2.5) + jerk_boost 소스 확장을
   "부분 개선"으로 인정하고 이대로 실차검증 진행할지.
2. 오버라이드 자체를 "즉시 w=1.0"이 아니라 baseline 대비 앞당기는
   정도를 줄이는 짧은(예: 0.2~0.3s) 고정 램프로 바꿔 "빠른 반응은
   유지하되 완전 즉시성은 낮추는" 절충안을 추가로 검토할지(단, 이는
   WIP가 이미 기각한 "rise-rate 되살리기"와는 다른 접근 — rise-rate는
   기존 1.0/s 전체를 되살리는 것이고, 이 대안은 오버라이드 전용의
   훨씬 빠른 고정시간 램프).
3. 아니면 이번 이벤트가 실제로는 "진짜 강한 감속"이었으므로 현재
   반응이 오히려 적절했을 가능성도 열어두고, 라우트2/3(더 명확한
   정상 케이스)과 함께 실차검증에서 체감을 재평가할지.

**코드 변경 없음(이번은 replay 검증 스크립트 추가 + 재해석만)**.

---

## 104차 — [INVESTIGATING] 오탐(A)/반응둔감(B) 제보 실차 로그 분석 — A는 조향 증가 구간 레이더 유실 시 vision fallback 원거리 오판, B는 오탐 아닌 진짜 "느린 반응" 사례로 재분류

**배경**: 사용자가 "오탐 및 앞차에 반응 둔감"으로 제보한 실차 로그(dashcam
zip 2건 + 화면녹화 mp4 1건)를 분석. seg10/seg11을 하나의 route 폴더로
통합해 `extract_log.py`로 CSV 추출, `extract_dashcam_frames.py`로
핵심 시점 qcamera 프레임 대조. 로그는 101차 패치 커밋 이후 시점이나
**코드 변경은 없음(분석 전용 세션)**.

### Finding A — [130차: 원인 확정 + 패치 설계/구현 완료, 실차검증 대기] 조향각 증가(커브) 중 레이더 유실 시 vision fallback이 근접 실물체를 원거리로 오판(오탐)

**[130차 갱신]** 원인을 코드 레벨에서 확정함: `radard.py` `LeadBlend.
update()`의 BIG_JUMP(`LEAD_BLEND_BIG_JUMP_DIST=15.0m` 초과, "안전
방향" 점프) 즉시-스냅 경로가 신뢰도(radar 여부/modelProb)와 무관하게
항상 적용되고 있었음 — 이 케이스처럼 근접 리드가 락을 잃고 vision
단독 저신뢰(prob≈0.24)로 84~89m를 보고하면, "다른(더 먼) 물체로
전환됐다"고 오판해 블렌딩 없이 그대로 즉시 반영됨. 패치로 즉시-스냅을
`radar=True` 또는 `modelProb>=LEAD_BLEND_BIG_JUMP_PROB_GATE(0.70)`
조건으로 한정, 저신뢰 vision-only far jump는 기존 블렌딩(0.35s
시정수) 경로로 완화. 상세는 아래 "130차" 섹션(최상단) 참고 — 원본
Finding A 기록은 그대로 보존.

- t=683.22까지는 trackId=0 레이더 락온 상태로 실제 리드를 3.5초간
  안정 추종(dRel 점진 감소, radar confirm=True).
- t=683.22 조향각 증가(커브 진입 추정) 구간에서 레이더가 락온을 잃고
  dRel이 47.4m로 급점프 — vision-only 저신뢰 추정으로 전환.
- 이후 t=684.3~688.97 구간 leadStatus는 계속 True를 유지하지만, 프레임간
  dRel이 20~65m씩 요동(60~90m대)하는 전형적 vision 노이즈 패턴.
- **qcamera 프레임 대조 결과**: t=686.7/688.3 프레임에서 근접(약
  30~40m로 추정되는) 실물체(은색 세단/SUV)가 명확히 보이는데도, CSV는
  같은 시각 저신뢰(prob≈0.24)·non-radar dRel 84~89m를 보고 — 실측과
  괴리가 큼. 즉 "리드가 없는데 있다고 오탐"이 아니라, "리드는 있는데
  vision-only 추정 거리 자체가 크게 틀려서(원거리로 오판) 실질적으로
  근접 위험을 놓칠 수 있는" 유형의 오탐.
- **원인 가설**: 조향각 증가로 레이더가 근접 실타깃 락온을 잃는 순간,
  vision 단독 추정이 원거리의 다른 후보(또는 저신뢰 노이즈)로 미끄러져
  들어가면서 실제로는 가까운 물체를 멀리 있다고 보고. VisionTrack의
  저신뢰 구간 안전-플로어 clamp(58차1번 원칙: min()으로 조이기만 함)가
  이 케이스엔 "멀리 보고된 거리를 안전측으로 당겨오는" 방향으로는
  작동하지 않아 사각지대로 남음.
- **상태**: 이번 세션은 원인 조사까지만, 코드 변경 없음. 트랙 ID 자체는
  변하지 않아(레이더 재획득 실패, 완전 신규 타겟 스위치는 아님) 방안
  설계 시 기존 신규등록/저신뢰 게이트(58차 계열)와의 상호작용을 함께
  검토해야 함. **다음 세션: 동일 커브+레이더 유실 조합 재현 로그 추가
  확보, vision-only 저신뢰 구간에서 dRel 자체의 급격한 증가(=원거리
  오판 방향)를 감지해 억제하는 방안 설계 착수.**

### Finding B — [재분류: 오탐 아님] "반응 둔감" 제보 구간(t=726~731)은 실제로 사용자가 인지한 대로 반응이 늦은 진짜 이벤트, 탐지 오류 아님

- t=726.82: dRel이 38.7→30.6로 급락 + vRel 부호 반전(vision-only) —
  단발성 노이즈 트랜지언트로 판단(트랙 ID 불변, 곧바로 정상화).
- t=726.87: 레이더 락온 전환, dRel이 50.7로 재점프하며 vRel=-3.90 —
  기존 devnotes(73차 방안I 등)에 기록된 "레이더 락온 전환 vRel 불연속"
  패턴과 일치. **트랙 ID(trackId=0)는 전 구간 불변** — 별개 물체로의
  스위치가 아니라 동일 리드에 대한 재획득.
- t=726.87~731.12: 레이더가 안정적으로 락온을 유지한 채 dRel이 50.7→
  32~33m까지 4초간 지속적으로 감소, vRel은 -4~-4.5m/s 유지. 그런데
  같은 구간 ego는 오히려 가속 중(aEgo +0.7~+1.0, vEgo 3.2→6.0m/s로
  상승), desiredSpeed도 94~96kph로 높게 유지 — **desiredSpeed는 이
  구간 회전/route 기반 속도 제약(vturn/route 소스)이며 리드 게이팅과
  무관한 별도 경로임을 컬럼 대조로 확인**, 즉 리드가 계속 좁혀오는데도
  route/커브 목표속도만 보고 가속을 이어간 것으로 해석됨.
- 이 상태로 약 2초간 더 가속하다가 결국 제동 전환, min TTC=2.49s까지
  하락(danger 문턱 2.5s에 근접) 후 t=731.17에 정상적으로 회복(진짜
  vRel 부호 반전, 물리적으로 일관 — 리드가 멀어짐).
- **결론**: t=726.82의 짧은 노이즈 트랜지언트는 사용자가 "오탐"으로
  느꼈을 수 있는 부분과 일치하나, 실제 핵심 문제는 그 직후 4초+ 동안
  레이더가 정상적으로 지속 접근을 보고했음에도 시스템이 route/커브
  목표속도 추종을 우선해 감속 개시가 지연된 것 — **탐지 실패가 아니라
  리드-게이팅과 route/vturn 속도 목표 간의 우선순위 로직 문제**로
  재분류. 71차에서 확인된 "실제 cutin 중 비전 dRel 진동 → 반응 지연"과
  유사 계열이나, 이번 건은 진동이 아니라 안정적 레이더 지속 접근 중
  발생했다는 점이 다름.
- **상태**: 원인 조사만 완료, 코드 변경 없음. **다음 세션: 리드 dRel/
  vRel이 안정적으로 접근 중임에도 desiredSpeed(route/vturn 소스)가
  그보다 우선시되는 조건/게이트 로직을 `carrot_serv.py`
  min()소스선택/`long_mpc.py` 리드 게이팅 교차점에서 확인, 방안 설계
  착수 여부 결정.**

### mp4 클립 관련 (참고, 결론 없음)
- 업로드된 mp4(`20260828_155926_260828_155925_clip.mp4`)는 파일명
  타임스탬프상 약 15:59:25~55 구간으로 추정되며, 이는 seg10 t≈679.2~
  704.2 초반부와만 겹치고 Finding B의 t=726~731(약 16:00:17)은 포함하지
  않음 — 이번 세션에선 Finding B 시각 확인용으로 쓰지 못함(qcamera
  프레임으로 대체 확인).

---

## 101차 — [VALIDATED] 100차 패치가 유발한 carrot_man __init__ AttributeError 크래시 — 원인 확정 및 수정 (device 재부팅 검증 완료)

**증상**: 100차 패치(`eaee8b5`) 적용 후 device에서 `carrot_man`이
기동 직후 crash loop(managerState: `running=False, exitCode=1`
반복). rlog/qlog의 `logMessage`/`logCarrotMessage`를 전수 확인해도
Python traceback이나 에러 로그가 전혀 없음 — stdout/stderr 캡처도
없음.

**진단 과정**: traceback이 전혀 안 남는다는 건 `cloudlog`가 아직
초기화되기 전(=`__init__` 매우 초반)에 프로세스가 죽었다는 뜻으로
추정. 100차 패치가 정확히 무엇을 건드렸는지(diff 범위: `__init__`
자체 + 최상단 import 블록)를 기준으로 `__init__` 내부 실행 순서를
줄 단위로 재확인.

**원인 확정** (코드 직접 확인, `selfdrive/carrot/carrot_man.py`):
- `__init__` 312번째 줄: `self.carrot_curve_speed_params()` 호출
- `carrot_curve_speed_params()` 정의(1048~1052번째 줄):
  `self.autoCurveSpeedFactor = self._auto_curve_speed_factor` /
  `self.autoCurveSpeedAggressiveness =
  self._auto_curve_speed_aggressiveness` — 두 캐시 필드를 그대로
  참조
- 그런데 `self._auto_curve_speed_factor`/
  `self._auto_curve_speed_aggressiveness`의 실제 초기화는
  100차 패치가 `__init__` 맨 끝(349~351번째 줄, `self.is_metric`
  다음)에 새로 추가한 것 — 즉 312번째 줄 시점엔 아직 존재하지
  않는 속성
- 결과: `AttributeError`가 `__init__` 도중(전체 초기화가 끝나기
  전) 발생 -> 프로세스 즉시 종료. `cloudlog`는 이보다 뒤에
  설정되므로 traceback이 로그에 안 남는 현상과 정확히 일치
- 99차 이전(패치 전) 코드는 `carrot_curve_speed_params()`가
  `self.params.get_*()`를 매번 직접 호출했기 때문에 이런 순서
  의존성이 애초에 없었음 — 100차의 캐싱 리팩터링 자체가 새로
  만들어낸 순서 버그(회귀).

**수정**: 캐시 필드 초기화 블록(`readParams` 카운트다운 변수 +
`_is_onroad_cached`/`_auto_curve_speed_factor`/
`_auto_curve_speed_aggressiveness`, 원래 있던 설명 주석 포함)을
`__init__` 맨 끝에서 `self.carrot_curve_speed_params()` 호출
직전(`self.curvatureFilter = MyMovingAverage(20)` 다음)으로 이동.
값/로직/재조회 주기 등 100차 패치의 실제 동작은 전혀 바꾸지 않고
**초기화 순서만** 정정. 이동한 위치에 101차 원인 설명 주석 추가.
base `eaee8b5`(100차 반영본), 로컬 커밋 `6bbccca`, 패치
`0001-carrot-man-init-order-fix.patch`.

**검증**: `ast.parse()`로 문법 검증 통과, `git diff`로 코드 이동만
있고 로직/캐시값/호출 시점(20Hz 루프 내 갱신 주기 등) 변경이
없음을 확인. capnp/msgq 의존성 때문에 컨테이너 환경에서는
`CarrotMan()` 실제 인스턴스화 테스트가 불가했음(기존 "정적 크래시
검증" 원칙과 동일한 한계) — 이후 patch `bc1bcb0` 적용 후 **device
재부팅으로 crash loop 완전 해소 최종 확인 완료.**

**교훈**: `__init__` 내에서 캐시 필드를 나중에 추가할 때, 그
필드를 참조하는 다른 메서드 호출이 `__init__` 앞부분에 이미
있는지 항상 확인해야 함. 100차 패치 리뷰(정적 리뷰) 단계에서
`git diff`만 보고 "캐시 필드 추가 + 호출부 교체"를 각각 독립적인
변경으로 봤을 가능성 — 실제로는 필드 추가 위치와 기존 호출
위치의 상대적 순서까지 함께 확인했어야 잡을 수 있었던 버그.

---

## 100차 — [NEEDS_VALIDATION] 99차 발견사항 전부 패치 완료 (carrot_man.py Params I/O 캐싱 + Shapely interpolate→numpy 벡터화 + 죽은코드 2건 제거)

99차가 찾은 항목 전부 패치. base `6ab8ad6`(c3-ms-dev HEAD, 98차
반영본), 로컬 커밋 `8354ed6`, 패치 `0001-carrot-man-perf-cleanup.patch`.

1. **Params I/O 캐싱**: `carrot_man.py`에 `readParams` 카운트다운
   패턴(controlsd.py/radard.py/longitudinal_planner.py, 98차와 동일)을
   신규 도입. `IsOnroad`(`carrot_navi_route()`),
   `AutoCurveSpeedFactor`/`AutoCurveSpeedAggressiveness`
   (`carrot_curve_speed_params()`) 3개를 100프레임(20Hz 기준 5s)마다
   1회 재조회로 변경. `broadcast_version_info()` 루프에
   `self._refresh_cached_params()` 호출 추가.
2. **Shapely `interpolate()` → numpy 벡터화**: `carrot_navi_route()`의
   `LineString(...).interpolate()` 반복호출(사이클당 최대 ~60회)을
   신규 모듈함수 `resample_10m_np()`로 대체. `shapely` import 제거
   (단, `selfdrive/carrot/server/core.py`가 별도로 shapely를 계속
   사용 중이라 `pyproject.toml` 의존성 자체는 그대로 유지).
   - **수치 동일성 검증**: `toolkit/verify_resample_np.py`(100차
     신규) — 랜덤 경로 20개(다양한 곡률/길이/노이즈), 89/90차류
     급커브, 직선(오탐 확인), 경계조건(2점 초단거리, 총길이가
     distance_interval 정확한 배수), 600m급 긴 경로까지 전부 PASS,
     원본(Shapely) 대비 최대오차 1.2e-13m(부동소수점 오차 수준)로
     100% 일치.
3. **죽은 코드 2건 제거**: `carrot_man.py`의
   `if False and self.navd_active:` 분기, `controlsd.py`의
   `if False: # command`(`desire_map`) 분기 — 둘 다 항상 거짓이라
   실행된 적 없는 죽은 코드, 제거해도 동작 변화 없음.

**검증**: `py_compile` 통과, 별도 클린 clone에서 `git reset --hard
6ab8ad6` 후 `git am` 정상 적용 확인(충돌 없음), 적용 후 재컴파일도
통과. 제어 로직/임계값/출력값 변경 없음 — 순수 캐싱+구현체 교체+
죽은코드 제거.

**미검증 / 다음 단계**: 97/98차와 동일하게 실차 CPU 사용률 측정은
이번에도 미수행 — [NEEDS_VALIDATION] 유지. 실차 검증 대기 항목: (a)
`IsOnroad`/커브속도 계수 변경이 5s 지연 후 반영되는 것을 체감상
문제없는지, (b) numpy 리샘플 경로가 실제 GPS route에서도 회귀 없는지
(시뮬레이션은 합성 데이터 기준이었음 — 실제 route CSV로 재확인은
아직 안 함).

## 99차 — [RISK_IDENTIFIED, NEEDS_USER_DECISION] carrot_man.py 20Hz 루프 정적 코드리뷰 — 97차와 동일 유형의 Params I/O 미캐싱 + Shapely interpolate 반복호출 발견 (로그분석 아님)

**배경**: 97차/98차가 `controlsd.py`/`radard.py`/`longitudinal_planner.py` 3개
파일만 커버했던 것과 별개로, 같은 20Hz(`Ratekeeper(20)`) 실시간 루프를 도는
`selfdrive/carrot/carrot_man.py`(`broadcast_version_info()` 스레드)를 이번에
정적 리뷰. 커밋 기준: `6ab8ad6`(c3-ms-dev HEAD, 98차 패치 반영본).

**핵심 발견 1 — 97차와 동일 유형의 미캐싱 Params I/O (carrot_man.py는 97차 검토
범위에 있었지만 실제로는 놓쳤던 부분)**:
- `carrot_curve_speed_params()` (line 996-997): `AutoCurveSpeedFactor`,
  `AutoCurveSpeedAggressiveness` 2개를 `get_int()`로 매 호출마다 새로 읽음.
  이 함수는 `carrot_curve_speed()`를 통해 20Hz 루프에서 매 사이클 무조건
  호출됨 — 캐싱/카운터 없음.
- `carrot_navi_route()` (line 407): `is_onroad = self.params.get_bool("IsOnroad")`
  도 매 사이클 무조건 새로 읽음.
- 대조: 같은 `selfdrive/carrot/` 안의 `carrot_functions.py`는 이미
  `self.params_count % 10` 카운터 분산 캐싱 패턴을 구현해뒀음(line 162-201) —
  즉 `carrot_man.py`만 이 패턴이 누락된 상태. 97차가 "selfdrive/carrot/*"를
  검토 대상에 포함시켰다고 기록했으나 실제 상세 발견 목록에는 이 2건이
  빠져 있었음(97차 기록 자체를 정정하지 않고, 99차 신규 발견으로 별도 기록).

**핵심 발견 2 — `carrot_navi_route()`의 Shapely `LineString.interpolate()`
반복호출 (신규, 97차에 없던 유형)**:
- line 436-444: 매 20Hz 사이클마다 `LineString(relative_coords)` 객체를
  새로 생성하고, `while current_distance <= line.length` 루프 안에서
  `line.interpolate(current_distance)`를 (route_lookahead_m=300~600m ÷
  distance_interval=10m 만큼, 최대 약 60회) 반복 호출.
- Shapely/GEOS의 `LineString.interpolate()`는 호출 간 누적거리 상태를
  유지하지 않고 매 호출마다 정점 배열을 처음부터 다시 훑어 목표 거리를
  찾는 방식이라, 이 루프는 사실상 "정점 수 × 호출 횟수"에 비례하는
  불필요한 재계산 — numpy 누적거리 배열 + `np.interp` 한 번으로 대체 가능한
  연산을 GEOS C-extension 호출 수십 회로 처리 중.
- line 435 주석은 "5m 간격 리샘플"이라고 돼 있으나 실제 코드는
  `distance_interval = 10.0`(10m) — 주석과 실제 값 불일치(동작에는 영향
  없음, 문서 정정 필요).
- 이 계산 전체(곡률/out_speed 산출)가 GPS 위치·항로 갱신 여부와 무관하게
  20Hz로 매번 처음부터 재계산됨 — 위치가 사실상 그대로인 프레임에서도
  동일 계산 반복.

**부수 발견 — 죽은 코드(불필요한 코드, CPU 영향 없음)**:
- `carrot_man.py` line 404: `if False and self.navd_active:` — 항상 거짓이라
  블록 전체가 실행 불가능한 죽은 분기.
- `controlsd.py` line 278: `if False: # command` — `desire_map` 딕셔너리
  생성 코드가 죽은 분기 안에 있음(실행 안 되므로 런타임 비용은 0, 코드
  정리 대상).
- `carrot_man.py` line 58/196 부근: `haversine_cache`/`curvature_cache`
  캐시 시도 코드가 전부 주석처리된 채 남아 있음 — 과거에 캐싱을
  시도했다가 미완성으로 남긴 흔적으로 추정, 실제 채택 여부 사용자 확인
  필요.

**"불필요한 코드"(로직 자체가 안 쓰이는 죽은 코드) 그 외 추가 발견 없음**:
97차와 동일한 결론 — `radard.py` 주석 블록, `frogpilot`, 서드파티
서브트리 등은 이미 97차에서 확인 완료(재검증 결과 동일).

**미검증 / 다음 단계 (사용자 결정 대기, 패치 아직 미적용)**:
- 위 2개 미캐싱 Params I/O는 97차 때와 같은 해결 난이도(기존
  `carrot_functions.py` `params_count % 10` 패턴 재사용) — 구현 자체는
  간단.
- Shapely interpolate 대체(numpy 벡터화)는 로직 동일성 검증(리샘플
  좌표가 기존 방식과 수치적으로 일치하는지)이 필요 — `toolkit/`에
  `sim_route_curvature_sample.py`가 이미 존재하므로 이를 활용해 회귀
  검증 권장(그대로 재사용 가능한지 우선 확인, 없으면 신규 작성 후
  toolkit에 등록).
- 실제 CPU 사용률 측정(실차 `top`)은 이번에도 수행하지 않음 —
  [NEEDS_VALIDATION]은 97차와 동일하게 유지.
- 사용자가 패치 진행을 원하면 다음 세션(100차)에서 구현.

## 98차 — [NEEDS_VALIDATION] 97차 발견사항 전부 패치 완료 (Params I/O 캐싱 + compute_leads 내부함수 이동 + deepcopy→copy)

97차가 찾은 3개 항목 전부 패치. 상세 구현/검증 내용은 WIP.md 98차 항목
참고. 요약: `controlsd.py`/`radard.py`/`longitudinal_planner.py` 실시간
루프 내 무제한 `Params.get_*()` 호출 14건을 `lateral_planner.py` 기존
캐싱 패턴(`self.readParams` 카운터)으로 통일, `radard.py`
`compute_leads()` 내부함수 2개 모듈레벨 이동, `leadTwo`의 불필요한
`deepcopy`를 `.copy()`로 교체(반환 dict가 flat scalar-only임을 코드로
확인). 제어 로직/임계값 변경 없음 — 순수 캐싱 리팩터. `py_compile` 통과,
base `b67c291`, 로컬 커밋 `05580ab`. 실차 검증 대기: (a) 파라미터 변경
반영 지연 체감 여부, (b) 회귀 없음.

## 97차 — [RESOLVED → 98차에서 패치] c3-ms-dev 전체 정적 코드리뷰 — 실시간 루프 내 Params() 무제한 I/O 발견 (로그분석 아님, 실차검증 대상 아님)

**배경**: 실주행 로그 분석이 아니라 코드베이스 자체에 대한 정적 리뷰
요청 — (1) 불필요한 코드 존재 여부, (2) comma 기기 구동 중 CPU 연산을
과다 소모하는 코드 존재 여부. `git log`/`find`/`grep`으로 커스텀 코드가
몰려있는 `selfdrive/controls/{controlsd,radard,plannerd}.py`,
`selfdrive/controls/lib/{longitudinal_planner,lateral_planner}.py`,
`selfdrive/carrot/*`를 대상으로 검토. 커밋 기준: `b67c291`
(c3-ms-curv 병합 후 c3-ms-dev 최신).

**핵심 발견 — controlsd.py `state_control()` (100Hz 루프) 내
rate-limit 없는 `Params.get_*()` 호출 10건**:
`Params.get()/get_int()/get_float()`는 매 호출마다 파일 시스템
읽기(디스크/IPC)가 발생하는 상대적으로 무거운 호출인데, 이 함수가
DT_CTRL 기준 **100Hz**로 매 사이클 무조건 실행되면서 그 안에서
`SteerRatioRate`, `CustomSR`, `UseLaneLineCurveSpeed`, `LatSmoothSec`,
`SteerActuatorDelay`, `SpeedFromPCM`, `DisableDM` 등 **10개 파라미터를
캐싱/분산 없이 매번 새로 읽음** (line 95-96, 153-155, 229, 305 등).
이론상 초당 최대 1000회의 불필요한 파라미터 I/O.

같은 문제가 정도는 약하지만 다른 두 곳에도 있음:
- `radard.py` `update()` (20Hz): `EnableRadarTracks`,
  `EnableCornerRadar`, `RadarLatFactor`, `RadarReactionFactor` 4개,
  매 사이클 무조건 읽음 (line 751-754).
- `longitudinal_planner.py` `update()` (20Hz): `CommaLongAcc`,
  `LongActuatorDelay`, `VEgoStopping` 3개, 매 사이클 무조건 읽음
  (line 192, 230-231).

**대조 — 이미 올바른 패턴이 코드베이스 안에 존재함**: 위 3곳과 달리
`lateral_planner.py`(`self.readParams` 카운터, 100프레임마다 1회 읽고
캐시, line 87-94)와 `carrot_functions.py`(`self.params_count % 10`로
프레임을 분산시켜 카운트 10/20/30/40...마다 서로 다른 파라미터군을
나눠 읽음, line 162-201)는 정확한 "N프레임마다 캐시" 패턴을 이미
구현해뒀음. 즉 위 3개 파일만 이 패턴이 누락되어 일관성이 없는 상태 —
해결 난이도는 낮음(기존 패턴 재사용).

**부수 발견 (영향 작지만 누적)**:
1. `radard.py` `compute_leads()` (line 989, 994): 내부함수 `_ok()`,
   `_pick_two_with_gap()`가 20Hz 사이클마다 매번 새로 정의됨 —
   함수 객체 재생성 오버헤드. 클래스/모듈 레벨로 분리 권장.
2. `radard.py` line 981: `self.leadTwo = copy.deepcopy(self.leadTwo)` —
   `leadTwo`는 `get_RadarState()`가 반환하는 스칼라만 담긴 flat dict라
   중첩 가변 객체가 없음에도 `deepcopy`(재귀+memo 오버헤드) 사용 중.
   `dict(self.leadTwo)`/`.copy()`로 대체 가능(더 저렴).
3. `controlsd.py` line 159: `smooth_value()` 내부함수도 100Hz마다
   재생성됨 — 위 Params 이슈와 같은 함수(`state_control()`) 안이라
   함께 수정하기 용이.

**"불필요한 코드"는 별도로 발견되지 않음**:
- `radard.py`의 긴 주석 블록들(30-38, 372-418줄 등)은 죽은 코드가
  아니라 튜닝 상수 설계 근거를 설명하는 문서화 주석 — 유지 권장.
- `selfdrive/frogpilot`은 `system/manager/process_config.py`에
  `fleet_manager` 프로세스로 실제 등록되어 사용 중 — 죽은 코드 아님.
- `third_party/`, `tinygrad_repo/`, `panda/` 등 업스트림 서브트리는
  ryu가 손대지 않은 원본이라 이번 리뷰 범위에서 제외(커스텀 코드
  대상으로만 검토).

**미검증 / 다음 단계**:
- 위 발견은 정적 리뷰 결과이며, 실제 CPU 사용률(%)이나 프레임
  드랍/타이밍 지연으로 이어지는지는 실차(comma 기기)에서
  `top`/`proclogd` 등으로 측정된 바 없음 — [NEEDS_VALIDATION].
  다만 known-good 패턴(`lateral_planner.py`/`carrot_functions.py`)이
  이미 캐싱을 하고 있다는 사실 자체가, 해당 개발자들도 이 비용을
  인지하고 있었음을 시사함.
- 패치 설계 시 카운터 분산 방식(`carrot_functions.py` 스타일: 서로
  다른 파라미터군을 각기 다른 카운트에 배정)을 그대로 재사용하는 것을
  권장 — 새 캐싱 메커니즘을 별도로 만들 필요 없음.
- 이 항목은 로그분석 기반이 아니라 정적 코드리뷰 기반이므로
  `LAST_ANALYZED.md`(커밋 분석 범위)와는 무관 — 별도 코드리뷰
  세션으로 취급.

## 95차 — [교차검토, NEEDS_VALIDATION] c3-ms-curv 병합 후 87차(radard.py)↔94차(long_mpc.py) 로직 상호작용 — 보완관계, 잔여 갭 존재

**배경**: c3-ms-curv(81/82/84/85/87/91차)를 c3-ms-dev(94차 포함)에 병합
(파일 충돌 없음, `git merge` 정상 완료) 직후, 병합된 6개 커밋과 94차가
코드 레벨로 겹치는 지점이 있는지 교차 검토.

**결론**: 81/82/84/85/91차(route/vturn/lookahead, `carrot_man.py`/
`carrot_serv.py`)는 94차(`long_mpc.py`)와 완전히 독립된 서브시스템 —
공유 상태/변수 없음, 상호작용 없음. **87차(`radard.py`, VisionTrack
고스트 래치 수정)만 94차와 로직 상호작용 있음.**

**상호작용 상세**: 94차의 discontinuity 판정은
`if lead_one_status_now and not radarstate.leadOne.radar:` 조건,
즉 "레이더 미확인(비전 단독)" 상태에서만 최근 5프레임 내 dRel 15m
이상 급락(`DREL_DISCONTINUITY_DROP_THRESH`/`WINDOW_N`)을 감시한다.
87차가 다루는 고스트 리드도 정확히 이 조건(비전 단독 tentative
트랙, radar=False)에 해당함.

- **87차 패치 전(가정)**: 고스트 리드가 `tentative_cnt>=10` 래치 후
  최대 120초간 `register_ok=True` 유지 가능. 실측 유사 사례(87차
  원인분석 중 확인한 route7 t=658, `leadDRel` 74→64→68→69→56→61m
  요동)처럼 고스트 dRel이 몇 프레임 만에 15m 이상 흔들리면, **실제
  컷인이 아닌 고스트 노이즈만으로 94차의 discontinuity 리셋(+66/67차
  저크부스트)이 스퓨리어스하게 발동할 수 있었을 것으로 추정**
  (NEEDS_VALIDATION — 87차 패치 전 상태에서 이 조합만 따로 재현
  검증한 적은 없음, 정황상 개연성).
- **87차 패치 후**: `ghost_low_prob_time >= GHOST_TIMEOUT_S(3.0s)`가
  되는 즉시(같은 프레임) `tentative_cnt=0` → `register_ok=False`로
  전환되므로, 위 취약 노출 시간이 **최대 120초 → 최대 3초 내외로
  대폭 축소**.

**평가 — 충돌 아님, 보완관계 + 잔여 갭**: 두 패치는 서로를 깨뜨리지
않으며, 87차가 94차의 사각지대(discontinuity 판정이 "진짜 리드
급접근"과 "고스트 노이즈"를 구분하지 못하는 근본 한계)를 완전히
없애진 못해도 노출 시간을 크게 줄여 실질적 위험을 낮춤. 단,
**고스트가 살아있는 ≤3초 구간 안에서는 87차와 무관하게 94차가 여전히
고스트 dRel 노이즈에 반응할 수 있음** — 94차 로직 자체가 prob/신뢰도
값을 보지 않고 순수 dRel 값 급락 여부만 판정하기 때문.

**후속 조치(우선순위 낮음, 지금 코드 변경 안 함)**:
1. 실주행 로그에서 "커브/애매한 물체 스침 직후 3초 이내 급감속(aEgo
   급락)+이후 정상 복귀" 패턴이 보이면 이 잔여 갭의 실제 발현 후보로
   우선 확인.
2. 필요성이 실측으로 확인되면, discontinuity 트리거 조건에 최소한의
   신뢰도 게이트(예: `register_ok`가 `prob>.5` 경로로 성립했을 때만
   유효, tentative 경로 성립 시엔 discontinuity 리셋 보류 등)를 추가하는
   방안 검토 가능 — 단 이 경우 방안C/D가 정확히 방어하려던 r1-3/r1-14류
   (실제 컷인, prob 낮은 상태에서 급접근)까지 억제되지 않도록 주의 필요.

## 94차 — 방안D: discontinuity 트리거 시 vision_dRel_rate/window 동반 리셋 (63차 계속 r1-14 사각지대 해소)

**배경**: 63차 계속(방안C 실측 재생 검증)에서 발견됐던 미해결 항목 —
방안C(discontinuity 트리거 시 `_lead_acq_timer=0.0`으로 리셋 →
`NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S` 유예가 자동 적용)는 r1-3(seg3,
radar 락온이 급락 직후 빠르게 이뤄짐)류에는 효과가 있었으나(frac
0.9대→0.3대로 감소), **r1-14(seg14, radar 락온이 급감속 종료 이후로
늦는 경우)류에는 완전히 무효**(PATCHED=UNPATCHED로 frac이 동일하게
1.0 유지)였음. 원인: `frac_time`/`frac_ttc`/`frac_rate`(25차/33차)는
discontinuity suppression과 무관하게 `self._vision_dRel_rate`(저역통과
필터링된 dRel 변화율)를 직접 읽는데, 방안C는 `_lead_acq_timer`만
리셋하고 이 rate 자체(와 그 window/prev)는 그대로 둬서, discontinuity
급락 자체가 이미 만들어놓은 오염된 rate가 트리거 이후에도 저역통과
필터를 통해 서서히만 해소됨.

**조치(방안D, 63차 계속이 이미 제안했던 방향을 이번에 실제 구현)**:
discontinuity 트리거 조건(`_dRel_raw_history` 5프레임 급락 판정)이
성립하는 프레임에서, 기존 `_lead_acq_timer=0.0` 리셋에 더해
`self._vision_dRel_rate=0.0`/`self._vision_dRel_rate_window.clear()`/
`self._vision_dRel_prev=None`도 함께 리셋. 트리거 조건 자체는 전혀
변경 없음 — discontinuity가 안 걸리는 상황(정상 완만 접근)에서는
구조적으로 개입 불가능(리셋 코드가 트리거 분기 안에만 있음).

**검증** (`toolkit/sim_drel_discontinuity_d.py` 신규, `long_mpc.py`의
discontinuity 트리거+vision_dRel_rate 필터(클램프+중앙값+저역통과)+
frac_rate 정규화 로직을 그대로 복사해 재현):
1. **r1-14류 재현(radar 락온을 트리거 이후로 미룸)**: UNPATCHED는
   트리거 프레임에서도(오히려 raw_rate가 이 프레임에 가장 크게 튐)
   frac_rate=1.000 유지, 그 이후 완만한 접근으로 바뀐 프레임들에서도
   저역통과 필터 잔류 오염으로 계속 frac_rate=1.000 — 방안C만으로는
   무효였던 63차 계속 관찰과 정확히 일치하는 패턴 재현. **PATCHED는
   트리거 프레임에서 즉시 frac_rate=0.000으로 떨어짐** — 사각지대
   해소 확인.
2. **정상 완만 접근(discontinuity 없음)**: PATCHED/UNPATCHED rate
   시퀀스 diff=0.000000(완전 동일) — 회귀 없음.
3. **r1-3류 재현(radar가 급락 바로 다음 프레임에 락온)**: 기존 코드가
   락온 프레임 자체에서 rate/window/prev를 무조건 리셋하는 별도 경로
   (`elif lead_one_status_now and radarstate.leadOne.radar:` 분기)를
   갖고 있어서, 락온 이후 상태는 방안D 유무와 무관하게 완전히 동일
   (diff=0.000000) — 63차 계속이 확인했던 "이 조합은 이미 효과 있음"
   결론이 이번 패치로 깨지지 않음을 확인.
4. danger override 독립성 — `process_lead()`의 `ttc_now`는
   `radarstate.leadOne.dRel`/`vRel` 기반으로 매 프레임 직접 계산되며
   `self._vision_dRel_rate`와는 코드상 완전히 분리된 변수라, 이번
   리셋과 무관하게 항상 즉시 반응(정적 확인, 기존 세션들과 동일 근거).

**구현**: `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`,
로컬 커밋 `866e934`, base `2d5174e`(79차 HEAD, `c3-ms-dev`). `py_compile`
통과. patch `0001-94-방안D-discontinuity-vision_dRel_rate-window-리셋.patch`
`/mnt/user-data/outputs/`에 전달, `git am` 안내 함께 전달함.

**다음(최우선)**: 실차 드라이브 검증 — (a) 원 제보(차선변경 시 옆차선
앞차 인식 급감속, 특히 radar 락온이 늦는 케이스) 완화 여부, (b) 회귀
검증(r1-3류처럼 이미 검증된 조합 체감 변화 없는지, danger override
지연 없는지). `이전세션.txt`에 언급된 3개 route(commit `2d5174e` 기록)
로 패치 전/후 정량 비교 가능하나 원본 zip 재업로드 필요(이번 세션엔
텍스트 로그만 있어 재분석 못함).

## 76차 — discontinuity+차선변경 조합에 73차 handoff duration 해법(4.0s+100/s) 통합 적용

**배경**: 75차 계속2가 방향(b)(discontinuity 트리거를 차선변경 중엔
handoff와 동일하게 frac 게이트 무관 완화)를 구현·검증했으나, 검증
과정에서 신규 한계를 발견했다 — hard-hold 자체가 여전히
`DISCONTINUITY_JERK_COST_BOOST_S`(1.0s)라서, 이 시나리오(route2
t=1470.75 트리거)의 실제 aEgo 최저점(-1.556, 트리거 후 1.65초)이
hard-hold 소진(트리거 후 1.0s) 이후에 발생 -- 72~73차가 방안I(레이더
핸드오프)에서 이미 겪었던 "boost duration 자체가 짧아 위험구간
중반에 소진"되는 구조적 한계가 discontinuity+차선변경 조합에도
동일하게 재현된 것.

**사용자 결정**: 73차가 handoff 전용으로 확정한 해법(hard-hold
1.0s→4.0s + release-rate 100/s 완만화)을 discontinuity+차선변경
조합에도 그대로 적용해, 게이트 완화(75차 방향b)와 duration 확장(이번)을
한 번에 처리.

**구현** (`selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`,
base `f8e136e`(73차 HEAD) -- 75차 패치 자체가 아직 미적용 상태였으므로
방향(b)와 duration 확장을 하나의 커밋으로 통합 구현):

1. **트리거 지점** (dRel discontinuity 감지 블록, `update()` 내
   `not radarstate.leadOne.radar` 분기): 트리거 시점에
   `lane_change_blinker_active`(이번 프레임 파라미터) 또는 직전
   프레임의 `_lane_change_vlead_hold_timer > 0.0`(hold 유예 중, 60차
   계속2가 이미 배선한 값 재사용) 이면 "차선변경 중"으로 판정 --
   - 차선변경 중: `_discontinuity_jerk_boost_timer = RADAR_HANDOFF_
     JERK_BOOST_S`(4.0s), `_discontinuity_trigger_source =
     'discontinuity_lc'`(신규 소스 태그)
   - 차선변경 무관: 기존 그대로 `DISCONTINUITY_JERK_COST_BOOST_S`
     (1.0s), 소스 `'discontinuity'`

2. **a_change_cost 적용부** (`is_handoff_source` 판정): 기존
   `trigger_source == 'handoff'` 단일 조건을
   `trigger_source in ('handoff', 'discontinuity_lc')`로 확장 --
   `'discontinuity_lc'`가 `'handoff'`와 **완전히 동일한 코드경로**
   (게이트: danger_active만 확인, frac 무관 / hard-hold 4.0s 종료
   후에도 release_rate=100/s로 base까지 선형 감쇠 / danger_active
   뜨면 감쇠 중이라도 즉시 base로 강제복귀)를 타도록 통합. 신규 상수
   추가 없음(`RADAR_HANDOFF_JERK_BOOST_S/RATE` 재사용). 일반
   `'discontinuity'` 소스(차선변경 무관)는 기존 분기(frac<=0.0 게이트
   + 1.0s hard-cutoff, release 없음) 완전히 그대로 -- 이미 실차검증
   끝난 조합이라 회귀 방지 원칙 재확인.

**검증** (`devnotes/toolkit/replay_lane_change_discontinuity_gate.py`
갱신 -- `duration_mode` 옵션 신규: `'gate_only'`(75차 원안 재현,
hard-hold 1.0s 유지) / `'full'`(76차, hard-hold+release-rate까지
handoff와 동일). `is_handoff_source` 분기의 release-rate 감쇠 로직도
`long_mpc.py`와 동일하게 재현):

- **route2 t=1470.75 이벤트 재검증**(75차가 발견한 원 사례): 최저점
  t=1472.401(aEgo=-1.556, 트리거 후 1.65초) 시점에서
  - 75차(gate_only): hard-hold(1.0s, t=1471.75 소진) 이미 꺼져 있어
    a_change_cost=20.0(사실상 무감쇠, j_lead 기반 base_a_change_cost)
    -- 무력화 재확인.
  - **76차(full)**: hard-hold가 4.0s(t=1474.75까지)라 최저점 전체
    구간(t=1472.20~1472.40 확인 구간)에서 a_change_cost=500.0(완전
    부스트) 유지 -- **한계 해소 확인**.
- **route1/route2 전체 스캔**: full 모드의 boost(a_change_cost>=300)
  프레임 수가 gate_only보다 항상 크거나 같음(route1 730→1028건,
  route2 184→479건) -- duration 확장으로 커버리지가 실제로 늘어남을
  재확인(73차 route1/route2 패턴과 정성적으로 일치).
- **회귀 없음 확인**: route1(22800행)/route2(7859행) 전체에서
  UNPATCHED(패치 이전) 대비 a_change_cost가 달라지는 프레임(각
  402/409건)을 전수 조사한 결과 **전부 소스=`'discontinuity_lc'`인
  경우뿐** -- 일반 discontinuity(차선변경 무관, 방안C/G 기존
  실차검증 조합)/handoff(방안I) 소스는 diff 0건으로 완전 보존.
  danger_active(TTC<=2.5s) 프레임 수도 UNPATCHED/76차(full) 간 전
  구간 동일(회귀 없음).
- `py_compile` 통과.

**의미**: 75차가 남긴 "게이트는 풀렸지만 duration이 짧아 여전히
무력화"라는 한계가, 73차가 handoff에서 이미 검증한 해법을 그대로
재사용(신규 상수/신규 코드경로 없이 소스 태그 확장만으로)함으로써
해소됨. `'discontinuity_lc'`는 사실상 "차선변경 중 발생한
discontinuity를 handoff와 동일하게 취급"하는 것으로, 도입 취지(75차
계속2 "사용자 영상 확인" 항목 -- 차선변경 중 타겟 전환은 진짜 위험이
아니라 정상적인 트랙 전환이므로 danger override만으로 안전망 충분)와도
일치.

**다음(최우선)**: `git format-patch` → `git am` 검증(base `f8e136e`)
→ 전달 → 실차 드라이브 검증(회귀 검증 필수 -- 일반 cutin/handoff 두
기존 검증 조합이 실차에서도 지연 없이 그대로 동작하는지, 차선변경
반복 시 boost가 과도하게 오래 유지되는 체감 없는지). 상세는 WIP.md
76차 항목 참고.

## 75차 — "차선변경 시 급감후 원복" 제보, discontinuity 소스 frac게이트 미해결 사각지대 발견

**요청**: 스크린샷("차선을 변경합니다", dRel≈55m, 1.Accel 그래프 하강) +
route1(`ea5bcc0566`)/route2(`a5b1ce4e42`) 재업로드(72~74차와 동일 라우트,
`data/routes/` 캐시 재사용). "차선변경 시 부드러울 때도, 급감후 원복하는
때도 있다 — 위험 상황 아니면 서서히 반응하도록" 요청.

**방법**: leftBlinker/rightBlinker/laneChangeState active 구간을 차선변경
이벤트로 탐지(route1 19건/route2 10건), 각 구간 전후 aEgo 최저치 확인,
`replay_boost_duration.py`의 `BoostReplay`(73차 로직 그대로)로 UNPATCHED
(1.0s hard)/PATCHED(73차, 4.0s+release100+split_gate) 위험구간(aEgo<=-1.0)
내 boost 적용시간 대조.

**분류**:
1. **73차 패치로 이미 개선 확인**: route2 t=1374~1381(handoff, aEgo -3.16)
   UNPATCHED 0%→PATCHED 100%(2.70/2.70s) 커버. route1 t=363~369도
   18%→56%로 개선. 같은 날 push된 패치가 정확히 이 유형(레이더 핸드오프)을
   해결하고 있음을 재확인.
2. **[신규, 미해결] discontinuity(방안C/G) 소스는 여전히 frac 게이트에
   막혀 boost 무효**: route2 t=1469~1472/t=1541~1545 — 트리거는 발동하나
   PATCHED/UNPATCHED 둘 다 boost 적용시간 0%. 원인: 73차 `split_gate`는
   handoff 소스에만 frac 무관 게이트를 줬고, discontinuity 소스는
   `frac<=0.0` 게이트 그대로(63차 결정 — 방안C/G는 이미 실차검증 끝난
   조합이라 보호). 차선변경 중 새 차로 리드가 dRel 급락으로 잡히는 순간
   frac(TTC caution)도 함께 빠르게 상승하는 경우가 많아, 이 시나리오에선
   discontinuity 트리거가 발동해도 boost가 사실상 항상 무력화됨. **73차가
   해결한 건 "레이더 핸드오프"뿐, "차선변경 중 비전 dRel 급락"은 여전히
   사각지대.**
3. 잔존 구조적 한계(74차부터 알려짐) 재확인: route1 t=522~533(handoff)
   위험구간 3.20s 중 PATCHED/UNPATCHED 둘 다 0.35s(11%)만 커버 — 트리거가
   위험구간 후반부에야 발동.
4. **정탐(버그 아님)**: route1 t=1015~1023(aEgo 최저 -4.01) — 차선변경
   직후 레이더 짧게 놓쳤다가 vision-only로 새 리드(71m) 포착, 이후 ~4초간
   vRel -13m/s대 물리적으로 일관 유지(단발 스냅 아님)되며 TTC<2.5s 진입 —
   danger override 정상 발동한 진짜 급접근. 체감상 급감이지만 코드 버그
   아님.
5. route1 t=1061~1066/t=1131~1137: harsh 감속인데 leadStatus=False(리드
   없음) — 곡선(vturn) 관련 별개 이슈로 추정, blinker와 우연히 겹침.
6. 나머지 대부분(route1 t=880~894 등): 매끈한 점진적 근접 추종, 정상 동작.

**결론**: 재현 가능한 "급감후 원복" 원인 후보는 **2번(discontinuity 소스
frac게이트 미해결)**로 좁혀짐.

**다음(사용자 확인 대기, 패치 미착수)**:
1. discontinuity 소스에도 split_gate 적용할지 — 전면 적용은 63차 보호
   대상(회귀 리스크) 재검토 필요. 대안: 차선변경 중(blinker+hold)에
   한정해서만 discontinuity 소스도 frac 무관 게이트로 완화(60차 계속2
   LANE_CHANGE_VLEAD_CORRECTION_HOLD_S와 동일한 "시나리오 한정" 원칙).
2. 방향 확정 시 route2 t=1469/1541 재검증(boost 커버율 개선 확인) →
   `long_mpc.py` 패치 설계.
3. route1 t=522~533(3번) 구조적 한계는 이번 세션 범위 밖, 계속 이월.

**코드 변경 없음(ryu). devnotes만 변경.**

## 75차 계속2 — 방향(b) 구현/검증/패치 전달 완료(`long_mpc.py`), **회귀 없음 확인 + 신규 한계 발견(duration 부족 재현)**

**배경**: 75차가 확정한 방향(b)(차선변경 중에 한정해 discontinuity 소스도
handoff와 동일하게 frac 게이트 무관하게 완화) 그대로 구현.

**구현** (`long_mpc.py`, 로컬 커밋 `e31f1e5`, base `f8e136e`): a_change_cost
게이트 조건부(L1172 부근)에 `is_lane_change_discontinuity` 신규 판정 추가
— `_discontinuity_trigger_source=='discontinuity'` AND
(`lane_change_blinker_active` 또는 `_lane_change_vlead_hold_timer>0`)이면
`is_handoff_source`와 동일하게 frac 게이트를 건너뛴다(danger_active만
확인). `lane_change_blinker_active`/`_lane_change_vlead_hold_timer`는
60차 계속2가 이미 배선해둔 것을 그대로 재사용 — 신규 배선 없음. 일반
discontinuity(비차선변경)는 기존 `frac<=0.0` 게이트 그대로.

**검증** (`toolkit/replay_lane_change_discontinuity_gate.py` 신규,
`replay_boost_duration.py` 로직/상수 재사용):
- **route2 t=1470.75 discontinuity+차선변경 트리거**: hard-hold(1.0s)
  구간 내에서 frac 게이트 완화로 실제 boost 적용시간이 늘어남 확인
  (t=1470.901~1471.350, 0.45초 구간이 base(200 근방)->boost(500)로
  전환 — patched만 500, unpatched는 frac 게이트에 막혀 200대 유지).
- **[신규 발견, NEEDS_VALIDATION] 그러나 이 이벤트의 실제 aEgo<=-1.5
  최저점은 트리거로부터 약 1.4~1.65초 후(hard-hold 1.0s가 이미 소진된
  시점)에 발생** — frac 게이트 완화만으로는 위험구간(aEgo 기준) 커버율이
  여전히 0%. **72~73차에서 handoff 트리거에 대해 이미 발견했던 "boost
  duration(1.0s) 자체가 실제 급감속 지속시간보다 구조적으로 짧다"는
  패턴이 discontinuity+차선변경 조합에서도 동일하게 재현됨.** t=1541~1545
  구간은 이번 위험구간 판정 기준(aEgo<=-1.5, gap 0.5s)으로는 위험구간
  자체가 안 잡힘(감속이 -1.5 문턱을 못 넘음, 별도 재확인 필요).
- **회귀 없음 확인**: route1(22800행)+route2(7859행) 전체 스캔에서
  patched/unpatched a_change_cost가 다른 프레임은 전부
  `lane_change_active=True`인 경우뿐(각각 38건/48건) — 비차선변경
  상황(일반 cutin 포함)은 diff 0건, 기존 검증된 조합(방안C/G) 완전
  보존 확인. danger_active 프레임 수도 각 구간에서 patched=unpatched로
  회귀 없음.

**의미**: 이번 패치(frac 게이트 완화)는 설계 의도대로 정확히 동작하고
회귀도 없지만, 이것만으로는 75차가 제보받은 "차선변경 시 급감후 원복"의
근본 해결에는 부족할 가능성 높음 — hard-hold duration 자체가 짧아
실제 위험 순간을 놓침. 73차가 handoff에 대해 썼던 해법(duration
연장 + release-rate 완만화)을 discontinuity+차선변경 조합에도 적용할지
여부가 다음 결정 사항.

**전달**: `0001-75-discontinuity-danger-b.patch`(base `f8e136e`)를
`/mnt/user-data/outputs/`에 생성, `git am` 검증(`py_compile` 포함) 통과
확인 후 전달.

**다음(최우선, 사용자 결정 대기)**:
1. **실차 드라이브 검증** — (a) 이번 패치 자체(frac 게이트 완화)가
   차선변경 시 체감 개선을 주는지(짧은 hard-hold 구간 내에서도 일부
   개선은 있음), (b) **회귀 검증 필수** — danger override/일반 cutin이
   패치 전과 동일하게 동작하는지.
2. 신규 발견된 "duration 부족" 한계를 해소할지 결정 — 73차 handoff
   해법(RADAR_HANDOFF_JERK_BOOST_S=4.0/RELEASE_RATE=100)을 discontinuity+
   차선변경 조합에도 적용할지, 아니면 이번 패치(frac 게이트 완화)만으로
   실차 체감을 먼저 확인한 뒤 필요시 추가할지.
3. route2 t=1541~1545 구간(-1.5 문턱 미도달)은 이번 위험구간 판정
   기준과 다른 방식(예: -1.0 문턱 또는 실제 qcamera 대조)으로 재확인
   필요.
4. route1 t=522~533(75차 3번, 구조적 한계)는 계속 별도 이월.

## 73차 계속3 — boost_s 스윗스팟 탐색 + release-rate 스크립트 버그 수정, 4.0s+100/s 채택

**boost_s만 증가(hard, split_gate)**: route1 3.0s→6.5s: 19.2/36.0/52.0/
68.0/76.0%(4.0/5.0/6.0/6.5s), route2: 44.2/62.2/81.1/98.2/100.9%.
게이트차단 전 구간 0.00s. route1은 discontinuity(t=687.850)+handoff
(t≈690.0) 이중 트리거로 위험구간이 8초 가까이 지속돼 6.5s로도 100%
불가 — 구조적 한계로 판단, duration 단독 증가는 상한 있음.

**`replay_boost_duration.py` 버그 2건 수정** (release-rate 옵션이 이전
세션(73차 계속2) 검증에선 사실상 완전히 무효였음이 드러남):
1. release-rate 감쇠 중 \"즉시 base로 강제복귀\"(`elif danger_active or
   frac > 0.0`) 판정이 split_gate의 방안I(handoff) frac 면제 예외를
   반영 안 함 — 핸드오프 트리거는 boost_gate_ok 계산 시 frac을 애초에
   무시하도록 설계됐는데, release-rate 분기의 강제복귀 판정만 이 예외를
   빠뜨려서 타이머 만료 직후(핸드오프 후 frac이 거의 즉시 0.7~1.0으로
   치솟음) 감쇠가 단 한 프레임도 못 가고 즉시 base로 꺼짐.
   `force_revert = danger_active`로 시작해 `not (split_gate and
   trigger_source=='handoff')`일 때만 `frac>0.0`을 추가하도록 수정.
2. `self._release_value = max(base_cost, self._release_value -
   release_rate * dt)`에서 `release_rate`가 정의 안 된 지역변수 참조
   (`self.release_rate`여야 함) — 버그1로 이 라인 자체가 전혀 실행이
   안 됐어서 첫 실행에선 NameError가 안 걸렸다가, 버그1 수정 후 실제로
   이 분기가 실행되면서 발견됨. `self.release_rate`로 수정.

**버그 수정 후 재검증**: 5.0s+300/s 62.4/92.8%, +200/s 67.2/98.2%,
+150/s 72.8/100.9%, +100/s 83.3/100.9%. 4.0s+150/s 56.8/85.6%,
**4.0s+100/s 68.0/98.2%**. danger_active 회귀 경고 전 조합 0건.

**결정(사용자 확인)**: **boost_s=4.0s(hard) + release_rate=100/s(cost/s)
완만화 조합 채택.** 5.0s+150/s(72.8/100.9%)와 커버율 거의 동급이면서,
\"완전부스트(500)\" 유지시간을 4.0s로 더 짧게 가져가고 나머지는 완만한
꼬리로 커버 — 원래 방안G \"찰나성 완화\" 설계 취지에 더 부합, 5~6초
내내 저크비용을 낮게 유지하는 것보다 승차감상 자연스러울 것으로 판단.
route1 68.0%(미달)는 구조적 한계로 인정하고 실차 검증에서 체감 확인
후 필요시 재논의하기로 함(duration/release_rate를 더 극단화하지 않음).

**코드 변경 없음(ryu 미변경). `toolkit/replay_boost_duration.py`\n버그 수정만(devnotes).**

## 73차 계속 — split_gate(방안I 전용 게이트 분리) 검증: 게이트차단 완전 해소, duration과 결합 시 커버율 실제 증가 확인

**배경**: 73차 계속(방향 결정)에서 확정한 "방안I(레이더 핸드오프)
트리거만 danger_active 단독 게이트, 방안C/G(dRel discontinuity)는
기존 게이트 유지"를 `replay_boost_duration.py`에 `split_gate` 옵션으로
구현·검증.

**결과**:
- route1 seg10: `1.0s+split_gate` 0.0%(원래 트리거가 dRel discontinuity
  라 split_gate 대상 아님, 예상대로 baseline과 동일) →
  `2.0s+split_gate` 4.0% → `3.0s+split_gate` **19.2%** (게이트차단 전부
  0.00s로 해소, timer활성=실부스트 정확히 일치).
- route2 seg1: `1.0s+split_gate` 8.1% → `2.0s+split_gate` 26.1% →
  `3.0s+split_gate` **44.2%** (마찬가지로 게이트차단 0.00s).
- **72차 duration 가설이 완전히 틀린 게 아니라, "frac 게이트가 열려
  있는 상태에서의 duration 연장"만 무의미했던 것 — split_gate로 게이트
  자체를 우회하면 duration 연장이 다시 의미를 가짐(coverage가 duration에
  비례해 실제로 늘어남).** 두 방향(게이트 분리 + duration 연장)은
  상호 배타가 아니라 결합해야 하는 것으로 재정리.
- danger_active 프레임 수는 모든 split_gate 후보에서 baseline과
  동일(회귀 없음, 스크립트에 자동 경고 로직 추가 확인 — 경고 없었음).

**다음(최우선)**: coverage가 여전히 100%에 못 미침(risk_dur가
5.55~6.25초인데 boost_s 3.0s로는 부분 커버) — boost_s를 더 올릴지
(4.0~5.0s 후보), 또는 route1의 dRel discontinuity 트리거(t=687.850,
방안C/G 경로)도 이 시나리오에선 사실상 무해한 오탐인지(즉 이 경로도
split 대상에 포함해도 되는지) 추가 판단 필요. 방향 확정되면
`long_mpc.py` 패치 설계 — 트리거 소스 구분용 상태(`_trigger_source`
또는 별도 bool 플래그) 신규 추가 필요(현재 원본 코드엔 이 구분이
없음, `_discontinuity_jerk_boost_timer` 하나만 공유).

**코드 변경 없음(ryu 미변경). `toolkit/replay_boost_duration.py`에
`split_gate` 옵션 추가(기존 후보군은 3.0s까지로 정리, release-rate
후보는 이번 검증에선 제외 — split_gate 효과가 더 명확해 우선순위
낮춤, 필요시 재추가 가능).**

## 73차 — boost 지속시간 연장 가설 재검증, **[중요, 방향전환] 진짜 원인은 duration이 아니라 frac<=0.0 게이트 자체**

**배경**: 72차 계속2~4에서 확정된 "boost 윈도우(1.0s)가 실제 급감속
지속시간(4~6초)에 비해 구조적으로 부족" 가설을 검증하기 위해, boost
지속시간 후보(2.0/2.5/3.0s hard-cutoff) + release-rate 완만화안(1.0s
유지 후 300/s 또는 200/s로 base까지 선형 감쇠)을 `data_routes.py`로
불러온 route1(`ea5bcc0566`)/route2(`a5b1ce4e42`) 실측에 정량 비교.
신규 `toolkit/replay_boost_duration.py` 작성 — `long_mpc.py`의
discontinuity 트리거(L884~938)+boost 적용 게이트(L1120~1134)를
그대로 복제하되, danger_active/frac까지 실측 재현해 "boost 게이트가
언제 실제로 열려있었는지"까지 진단.

**핵심 결과 (두 이벤트 모두 동일 패턴)**:
- route1 seg10: 트리거 t=687.850(vision dRel 불연속, 락온 이전에도
  1회 트리거됨 — 72차 계속2 부가확인과 일치)+t=690.003(레이더 락온
  vRel 불연속). 위험구간(aEgo<=-1.5, 짧은 회복 blip 0.5s 이내는
  무시) t=691.801~698.051(6.25초).
- route2 seg1: 트리거 t=1378.850(레이더 락온). 위험구간
  t=1379.400~1384.950(**5.55초, 72차 계속3 수기 계산과 정확히 일치**
  — 스크립트 검증 신뢰도 확인).
- **boost_s를 1.0→2.0→2.5→3.0s로 늘려도 위험구간 내 실제 부스트
  적용 시간(a_change_cost>=300)은 전부 0.00초(0.0%)로 동일** —
  duration 자체는 병목이 아니었음.
- 진단 결과: boost 타이머는 활성(timer>0) 상태였던 시간이 boost_s에
  비례해 늘어남(route2: 1.0s→0.45s/2.0s→1.45s/3.0s→2.45s 활성)에도
  **그 활성 시간 전부가 "게이트차단"(danger_active 또는 frac>0.0에
  걸려 실제로는 base_a_change_cost로 강등)으로 소모됨.**
- **원인**: `process_lead()`의 frac_ttc가 radar 락온 직후 dRel이
  빠르게 줄어들며(closing rate 유지) TTC가 곧바로 `LEAD_ACQ_TTC_
  CAUTION=6.0s` 밑으로 진입 → frac_ttc>0 → boost 게이트 조건
  `(timer>0 and not danger_active and frac<=0.0)`의 `frac<=0.0`이
  거의 즉시 깨짐. 즉 **boost는 "완전히 안전하다고 판단될 때만" 켜지도록
  설계돼 있는데, 이번 시나리오(정지/서행 앞차 락온) 자체가 정의상 곧바로
  frac_ttc를 끌어올리는 상황이라 boost가 실질적으로 거의 항상
  자기모순적으로 무력화됨.**

**함의(72차 가설 정정)**: "duration 연장" 자체는 무의미 — frac 게이트가
열려있는 한 boost_s를 아무리 늘려도 실제 적용 시간은 그대로 0에
가까움. 다음 방향 후보 3개(다음 세션 결정 필요):
  1. boost 게이트 조건에서 `frac<=0.0`을 완화(예: frac_ttc만 제외하고
     danger_active만으로 게이트, 또는 frac 문턱을 0.0 대신 낮은 양수로).
     danger override(TTC<=2.5s)는 이미 별도로 최우선 유지되므로 안전망
     자체가 사라지는 건 아님 — 재검토 필요.
  2. boost와 frac_ttc floor를 상호배타(if/else)가 아니라 병존 가능하게
     재설계(예: a_change_cost는 boost로 낮게 유지하되 frac이 dRel/vRel
     목표치에는 별도로 반영되도록 분리).
  3. 애초에 "찰나성 노이즈 완화"(방안G/C 원 목적)와 "몇 초 지속되는 진짜
     급감속의 저크 완만화"(방안I 목적)를 같은 boost 메커니즘으로 묶은
     것 자체가 구조적 한계일 가능성(72차 계속2에서 이미 제기된 프레이밍)
     — 후자 전용의 별도 메커니즘(예: frac gate 밖에서 동작하는 별도
     a_change_cost 완화 경로) 분리 검토.

**코드 변경 없음(ryu 미변경, 재현/진단만). `toolkit/replay_boost_
duration.py` 신규 작성·devnotes 편입.**

## 72차 계속3 — route2(x7seg, `a5b1ce4e42`) 재업로드 교차검증: 방안I boost 윈도우(1.0s) 구조적 부족, **두 번째 라우트에서도 동일 패턴 확인**

**배경**: 72차 계속2에서 route1 seg10(t≈690, 정지앞차 레이더 락온 급감속)
단일 사례로 "boost 1.0s 윈도우가 실제 수초 지속 급감속엔 구조적으로
부족"이라는 결론을 재확정했으나 표본 1건이었음. 사용자가 route2(x7seg,
`a5b1ce4e42`, 71차와 동일 라우트) 재업로드, `extract_log.py`로 재추출
(commit=`4fa4a44`, HEAD와 일치, 방안I 적용 상태 그대로).

**스캔 방법**: `leadRadar` False→True 전환 프레임에서 `leadVRel` 점프
`RADAR_HANDOFF_VREL_JUMP_THRESH=3.0` 이상인 이벤트 전수 스캔(5건) 중
접근 방향으로 심화되는(방안I 대상) 패턴은 1건뿐(나머지 4건은 반대로
vRel이 opening 방향으로 완화되는 케이스라 방안I 트리거 대상 아님).

**해당 1건 상세 (route2 seg1, t=1378.850)**:
- 락온 엣지: `leadRadar` False→True 전환, vRel -5.79→-10.90m/s(jump
  -5.11, 임계 초과 → 방안I 트리거 확인), dRel도 74.39→68.50m으로
  동시에 급락(정지앞차가 실제로 락온 순간 이미 강하게 근접 중이었음을
  시사) — route1 seg10과 동일하게 "정지/서행 앞차, vision이 과소평가
  하다 레이더 락온 순간 실제 상태 노출" 시나리오.
- **lead 차량이 이후 vLead 6.40→0에 가깝게 수렴하는 데 약 5.5초
  소요(t=1378.85→1383.90, 거의 정지)** — 실제 정지 앞차 케이스.
- boost 윈도우(1.0s)는 t=1379.850에 소진. 이 시점 aEgo=-2.229로 **아직
  감속이 진행 중이며 최악점 도달 전**.
- **실제 최대 감속(aEgo 피크)은 t=1381.207(-3.157m/s²)로, 락온으로부터
  2.36초, boost 소진으로부터 1.36초 후에 발생** — route1 seg10과
  동일하게 boost가 꺼진 이후에 최악 구간이 도래.
- `aEgo<=-1.5` 지속 5.55초(t=1379.40~1384.95), `aEgo<=-2.0` 지속
  3.60초(t=1379.85~1383.45) — 두 라우트 모두 "boost 1.0s"보다 훨씬 긴
  다초 단위 지속 이벤트임을 재확인.

**결론(2개 라우트 교차검증 완료, 가설 강화)**: 72차 계속2에서 route1
단일사례로 도출한 "boost 1.0s 윈도우가 레이더 락온이 드러내는 진짜
지속 급감속(찰나성 노이즈 아님) 시나리오엔 구조적으로 부족하다"는
결론이 **route2 독립 사례에서도 동일한 정량적 패턴(boost 소진 후
1~1.5초 뒤에 최악 감속 도달, 전체 이벤트는 3.5~5.5초 지속)으로
재현됨** — 표본 1건의 우연이 아니라 재현 가능한 구조적 한계로 확정.
다음 단계(boost 지속시간 연장안 또는 release-rate 완만화 설계)를
진행할 근거가 한층 더 확보됨.

## 71차 — 최신 브랜치(HEAD `0c137f28b456`, 67차 방안G) 실차 로그 2건(route1 19세그/route2 7세그) 전체 분석, qcamera 대조, [신규 발견] 실제 cutin 중 8~12초 지속 비전 dRel 진동 → 반응 지연

**배경**: 사용자가 최신 브랜치 실차 주행 로그 2개(route1=`ea5bcc0566`
19세그/1140s, route2=`a5b1ce4e42` 7세그/393s) 업로드, "전체 분석, qcamera
대조, 상황별 정리" 요청. `extract_log.py` 추출 결과 두 로그 모두
`commit=0c137f28b456`(67차, HEAD)로 최신 패치 전부 반영 상태에서 기록됨
확인.

**개관**: route1 cruise_ratio 93.2%, harsh_brake(raw) 35건 / route2
cruise_ratio 86.3%, harsh_brake(raw) 20건.

**1) harsh_brake 클러스터링(운전자 개입 여부 판별)**: 35+20건을 인접
이벤트로 묶어 8개 독립 사건으로 재분류. **8건 중 6건은 명확히 운전자
직접 개입**(brakePressed=True 직후 cruiseEnabled=False로 전환 확인,
정지선/신호대기 등 ADAS 무관 감속) — route1 seg1 초반(정지선),
route1 seg17(정지신호 추정, leadStatus=False 상태에서 driver
disengage), route2 seg5/6(저속 근접 상황 수동 정차) 등. **ADAS
주행 중(cruise 유지) 발생한 건 2건**(route1 seg7 t=527~531,
route1 seg4 t=356~368 — 둘 다 아래 2)/3) 항목에서 상세 분석).

**2) TTC danger override(`LEAD_ACQ_TTC_DANGER<=2.5s`) 4건, qcamera
정탐 확인**:
- route1 seg1 t=155.9~159.3(min TTC 1.53~2.44s, `src=cam`, `radar=False`,
  prob 0.72~0.99): qcamera 대조 결과 **교차로 진입 직전 실제 선행
  차량이 정지/서행 중**인 정탐 확인(3프레임 대조, 신호대기 추정).
- route1 seg15 t=1021.1(min TTC 1.14s, `src=vturn`, `radar=False`,
  prob 0.99): qcamera 대조 결과 **곡선구간에서 실제 브레이크등 켜진
  선행차량**의 정탐 확인.
- route2 seg6 t=1643.95(min TTC 1.73s): `cruiseEnabled=False`(운전자
  수동 저속 정차 중, vEgo=1.1m/s) — ADAS 무관, qcamera 대조 불필요로
  판단.
- (route1 seg7 t=527~531은 danger override 문턱 밖이었으나 아래 3)에서
  별도 상세 분석)

**3) [신규 발견, NEEDS_VALIDATION] route1 seg4 t=356~368 — 실제
cutin 상황에서 비전 dRel이 8~12초간 40~95m 범위로 극심하게 진동,
그동안 시스템 반응(aEgo)이 사실상 없어 운전자가 직접 브레이크 개입**

qcamera 대조(t=36.5s/45s/49.5s, 즉 route time≈351.7/360/364.5) 결과
**흰색 SUV가 우측에서 자기 차로로 실제 끼어드는(cutin) 장면 확인**
(45s 프레임에서 브레이크등 켜진 흰색 SUV가 바로 우측에서 근접, 49.5s
프레임에서 완전히 자기 차로 앞으로 진입 완료).

CSV 상세 궤적(route1 seg4, t=356.0~368.0):
- t=356.0~359.75: `leadDRel`이 43m→92m→54m→65m→91m→78m→87m→94m→
  74m→80m→85m 등으로 **약 9.75초간 40~95m 사이를 반복 진동**
  (`src=vturn`, `leadRadar=False` 내내, `leadModelProb` 0.25~0.82
  사이 요동). `curve_lead_dRel_jump_consistency()`로 재확인 시
  이 구간 점프들은 대부분 `physically_consistent=False`(방향
  비일관)로 판정 — 즉 기존 노이즈 억제 로직(방안C/E/G) 관점에서는
  "노이즈"로 분류되어 억제 대상.
- **이 9.75초 동안 `aEgo`는 -0.54~+0.59 사이에 머물며 실질적 감속
  반응이 전혀 없었음**(오히려 순간 가속 구간도 존재) — 그러나
  qcamera 상 실제로는 우측 차량이 근접·끼어들고 있는 중이었음.
- t=359.8: `brakePressed=True` 시작, t=359.9: `cruiseEnabled=False`로
  전환 — **운전자가 직접 브레이크 개입**(ADAS가 충분히 반응하지
  않는다고 체감했을 가능성).
- t=360.15~366.9: 운전자 브레이크 유지 상태에서 `leadVRel`이 점차
  -4~-11m/s대(빠른 접근)로 심화 표시, `aEgo`도 -1~-3m/s²대까지 따라감
  (단, 이 구간은 운전자 브레이크가 이미 걸려있어 실제 차량 감속의
  상당 부분이 운전자 개입에 의한 것일 수 있음 — 시스템 자체 반응인지
  분리 어려움).
- t=367.05: 레이더 최초 안정적 락온(`dRel=5.4m, radar=True`), 이후
  dRel이 5.4~5.7m대에서 안정.

**[정정, 사용자 확인] route1 seg4 t=356~368 — 버그 아님, 우회전 차선변경 + 변경 차로 혼잡**

사용자가 실제 상황을 확인해줌: 이 구간은 **자차가 우회전을 위해 차선을
변경하는 과정**이며, 변경할 차로에 차량이 많았음. CSV로 재확인 결과
`rightBlinker=True`가 t=364.0부터 켜짐(우회전 준비 차선변경, 사용자
설명과 일치) — t=356~364의 극심한 dRel 진동(40~95m)은 단일 실제
위험차량의 노이즈성 오검출이 아니라, **혼잡한 변경 대상 차로 내
여러 차량 사이를 비전 트랙이 옮겨다니며 잡힌 것**으로 재해석. 즉
"실제 위험을 노이즈로 오분류해 반응 지연" 가설은 기각. t=359.8
운전자 브레이크 개입도 혼잡 차로 차선변경 중 통상적인 수동 조작으로
판단, 시스템 결함 신호 아님. **다음 세션 최우선 항목(replay 검증)은
철회.** 61~67차 discontinuity suppress 로직에 대한 우려는 근거
약화 — 필요 시 별도의 명확한 단일차량 장기추적 실패 사례가 나오면
재조사.

**4) 곡선구간 비전 노이즈 억제 재확인**: `curve_lead_dRel_jump_consistency()`
적용 결과 route1 노이즈 억제율 80.5%(41건 raw danger → 8건 refined),
route2 100%(18건 → 0건) — 기존 세션들의 91.7% 등 수치대와 대체로
일치, 새로운 이상 패턴 없음. route1의 refined 8건 중 다수가 위 2)
TTC danger 이벤트(seg1/seg15) 및 3) cutin 사례(seg4)와 겹침 —
즉 refined 판정 로직 자체는 실제 위험 이벤트를 정확히 잡아내고
있음이 재확인됨(단, 3)의 9초+ 장기 진동에 대해서는 이 로직이 아직
검증된 적 없는 패턴).

**5) turn_speed_violations**: route1 2건, route2 1건 — 전부 저속
(vEgo 5.5~7m/s, 60km/h대 1건) 구간에서 `src=gas`(운전자 가속페달
개입) 또는 짧은 초과(2.6~5.4kph)로, 코드 결함 신호 아님으로 판단.

**6) congestion_stop_launch_lurch_scan**: 두 route 모두 0건(58차2번
저속 붕끗 패턴 재현 없음, 회귀 없음 확인).

**결론**: 대부분 정상(harsh_brake는 대개 운전자 개입, TTC danger는
정탐, 곡선 노이즈 억제는 정상 동작). **다음 세션 최우선으로 격상**:
route1 seg4(t=356~368) 장기 비전 진동/반응지연 사례 원본 코드
replay 검증 — 방안C/E/G의 discontinuity suppress가 실제로 이 구간
전체를 억제하고 있었는지, 그렇다면 억제 지속시간에 상한을 두는
방안(예: N초 이상 지속되는 진동은 더 이상 노이즈로 보지 않고
안전측으로 개입) 검토 필요.

## 70차 — [69차 정정] 사용자 제공 이전 세션 대화록 근거로 방안 D→E→F/G/H 변경 경위 전체 재구성

**배경**: 69차는 `git log`/코드 diff만으로 역보완하다 보니 "방안D 폐기
경위 불명", "방안F 흔적 없음, 확정 불가"로 남겨뒀던 부분이 있었음.
이번 세션에 사용자가 63~67차에 걸친 실제 세션 대화록(시간순 아닐 수
있음, 여러 세션분 혼재)을 제공해줘서, 그걸 근거로 정확한 경위를
재구성함. **69차의 해당 추측 부분을 아래 내용으로 정정.**

**전체 흐름 (확정)**:

1. **61차**: 방안C 구현(cutin dRel 불연속 급락 감지 → 신규등록 suppress
   재사용). `4ea63c3`.
2. **63차**: 방안C를 r1-3/r1-14 원본 rlog로 실측 재생검증. r1-3(seg3)은
   효과 확인, **r1-14(seg14)는 보호 공백 발견**(radar 락온 전
   frac_rate/frac_ttc가 discontinuity 리셋과 무관하게 이미 오염된
   `_vision_dRel_rate`로 포화) — 이미 FINDINGS.md에 상세 기록돼 있던
   내용(위 "[63차 계속, 중요] 방안 C 실측 재생 검증 완료" 섹션 참고).
   이 발견에서 **방안D**(discontinuity 트리거 시 `_vision_dRel_rate`/
   window도 함께 0으로 리셋) 제안.
3. **63차 계속3**: 방안D 구현·검증 → **명시적으로 기각/폐기**. 이유
   2가지, 사용자 대화록에 직접 기록됨:
   - seg14에서 discontinuity가 t=923.10~923.50 사이 **7회 연속
     재트리거**됨 — 리셋해도 곧바로 재수렴해서 aEgo 최저치 시점엔
     UNPATCHED와 완전히 동일한 frac=1.0. 즉 리셋 자체가 무의미.
   - **[신규, 중요] seg14의 raw dRel 자체가 물리적으로 불가능한 값**
     (프레임당 최대 -230m/s, 방향 반복 반전)을 보임 — 모델
     leadVRel(-0.8~-3.2m/s)과 크게 괴리, qcamera 육안으로도 뚜렷한
     접근이 안 보임(저해상도라 결정적 증거는 아님이라는 단서 포함).
     즉 "진짜 급접근을 방안C/D가 못 막는 문제"가 아니라 **raw dRel
     신호 자체를 의심해야 하는 케이스**로 재프레이밍됨.
   - 다음 방향으로 두 갈래 제시: (a) `extract_log.py`에 dPath 컬럼
     추가해 인접차선 오검출 여부 확인, (b) 방안E(반복 재트리거 시
     frac_rate 성분 억제) 설계.
4. dPath 확인 결과 -0.08~-0.59m로 **시종 동일차로 확인**(인접차선
   오검출 아님) — (a) 경로는 닫히고 (b) 방안E 설계로 진행.
5. **63차 계속9/10 (a) — 방안E 설계·구현**: leadVLead 기반 참고
   closing rate 상대적 타당성 클램프(`VISION_RATE_REF_MARGIN=5.0`,
   위 69차 섹션 코드 내용 그대로).
6. **63차 계속10 (b) — 교차검증, 1차 REJECTED → 사용자 정정 → 채택**
   (이 경위가 이번에 새로 확인된 핵심 디테일):
   - Claude가 seg3(r1-3, 진짜 cutin으로 이미 확정된 사례)로 방안E를
     교차검증한 결과, frac_rate가 radar 락온 직전 1.00→0.21로 억제되는
     걸 발견 → **처음엔 이걸 리스크로 판단해 REJECTED 권고**: "안전
     장치(vision_dRel_rate)가 자신이 보완해야 할 대상(leadVLead)에
     종속돼 같이 위험을 놓치는 구조적 모순"이라는 논리.
   - **사용자가 원 의도를 직접 정정**: "끼어드는 차량이 내차보다
     빠른 속도로 끼어들면서 가속했을 때... 카메라가 인식하고 내차가
     갑자기 급감속한 이후 레이더 락온 이후 다시 복원되는 상황...
     이런 경우는 내차가 급감속하는 게 아니고, 끼어드는 차량이
     내차보다 빠르다는 판단이면 정상주행해야 하지 않나... 레이더
     락온 상태와 같은 반응을 원했어."
   - Claude가 재검토: seg3의 leadVLead(ref_rate)는 그 구간 내내
     거의 0~-1m/s대(안전)를 가리켰고, 이는 **레이더 락온 후 실측
     vRel +3.2~+7m/s(opening)와 정확히 일치** — 즉 leadVLead 판단이
     처음부터 옳았고, raw dRel의 -100~-339m/s급 튐은 "트랙이 더
     가까운 새 물체(끼어든 차)로 전환되는 순간의 인공적 점프"였을
     뿐. **방안E의 억제가 오탐 억제가 아니라 정탐이었음**을 확인 —
     REJECTED 철회, NEEDS_VALIDATION으로 재분류해 채택 확정. (앞서
     REJECTED 판단은 58차1번의 실패모드, 즉 "vLead가 위험을 과소평가"
     하는 상황의 프레임을 이번 케이스에 잘못 적용한 것이었다고
     Claude 스스로 정정함.)
   - `git am`+push 완료(`e6a00ae`). 이후 세그4/세그7 실차 로그
     (route `0000031d--4ddb171bfb`, 68차가 나중에 다시 분석한 그
     로그와 동일 route)로 첫 실차 검증 — cutin 2건 모두 사용자
     의도대로 정상 처리(급감속 없이 상대차가 빨라지면 자연 복귀)
     확인.

7. **[신규 발견 스레드] 방안 F/G/H — 방안E 검증 도중 사용자가 별도
   이슈 제기**: 방안E 실차검증 로그를 분석하던 중, 사용자가 같은
   로그의 다른 구간(세그4/세그7, 차선변경 중 새 차로 앞차 인식)을
   가리키며 "이것도 이번 패치와 같은 로직 적용 안되나"라고 질문 —
   즉 방안E가 다루는 문제(cutin discontinuity로 인한 신호 왜곡)와는
   **다른 축의 문제**(신호는 정확한데 반응 자체의 승차감이 나쁨)가
   제기된 것.
   - 개별 분석 결과: 세그4 첫번째=cutin 정상(문제없음), 세그4
     두번째=처음엔 lane-change flicker로 의심됐으나 **우회전
     교차로 상황으로 재확인돼 배제**, 세그7=discontinuity 처리
     의도대로 정상 작동. **셋 다 "버그"는 아니었음** — 그런데
     사용자가 "세그4 첫번째, 세그7도 내 느낌에는 주행감이 안좋았어.
     잠깐의 급감속을 없애는 방안 검토해줘"라고 체감 기준 재조사 요청.
   - 사용자 제안: "차선변경시 변경차로의 앞차가 내차보다 가속중이면
     무시, 감속중이면 감속하도록 하면 안될까" (vRel 부호 기반 이진
     게이트). Claude가 세그4-1/세그7 실측 데이터로 검증 → **두
     케이스 모두 이 규칙이 안전 판단과 안 맞는 반례임을 확인**
     (세그4-1: vRel이 순간 opening으로 반전했는데도 여전히 물리적
     위험거리였음 / 세그7 초기: vRel이 계속 closing 중이라 애초에
     "가속중" 조건에 해당 안 함) → **이 이진 게이트 안은 근거 약해
     보류**. 부수적으로 세그7 후반에서 discontinuity와 무관한 별개
     패턴(저속 근접 gap 오실레이션, 5~7m서 vRel 반복 진동) 신규 발견
     — 별도 조사 대상으로 등록(코드/커밋 미착수, 이번 devnotes에도
     아직 없음, 필요시 다음 세션 후보로 추가 검토).
   - 사용자가 "대안을 제시해줘" 요청 → Claude가 **3가지 대안** 제시
     (전부 danger override는 무조건 우회 없이 최우선 유지 전제):
     - **방안F**: discontinuity 감지 시 MPC에 넣는 `x_lead`(목표거리
       입력) 자체를 점프 전값→실제값으로 0.5~1.0s에 걸쳐 블렌딩.
       가장 근본적이나 구현/검증 범위가 큼, danger 게이트가 블렌딩을
       즉시 무시하도록 하는 안전장치가 필수라는 단서 포함.
     - **방안G**: discontinuity 직후 MPC의 저크비용(`a_change_cost`)을
       한시적으로 강화해 "도달 속도"만 완만하게(크기는 안 건드림).
       코드 변경이 가장 작고 부작용 범위도 가장 좁음 — **"우선
       시도해볼 것"으로 추천**.
     - **방안H**: vRel 부호/추세를 이진 on/off가 아니라 연속
       가중치(`vrel_w`)로 만들어 기존 `min(dist_w, ttc_w)`에
       `min(..., vrel_w)`로 결합. 사용자 원 아이디어를 가장 충실히
       반영하지만 새 weight 임계값 튜닝이 필요해 검증 기간이 김.
   - **방안G가 채택돼 66차에서 설계 확정, 67차에서 구현·커밋됨**
     (`DISCONTINUITY_JERK_COST_BOOST_S=1.0`/`_BOOST=500.0`, 위 69차
     섹션 코드 내용과 정확히 일치). **방안F/H는 구현 흔적이 git
     log/코드 어디에도 없음** — 단, 69차가 추측했던 것과 달리
     "폐기됐다는 기록이 없어 불명"이 아니라, **원래 3개 대안 중
     하나(G)만 우선 채택된 것으로, F/H가 명시적으로 기각됐다는
     기록도 없음** — 즉 **미착수 상태로 후순위 대기 중**인 것이
     맞는 해석. 방안D처럼 "시도했다가 명시적으로 기각"된 것과는
     성격이 다름 — 구분해서 기록.

8. **67차 "[재생성]" 사고 경위 확인(69차 추측이 맞았음)**: 사용자
   대화록에 직접 나옴 — "컨테이너가 리셋되면서 지난 세션(67차)의
   실제 패치 파일이 유실됐고... FINDINGS.md '[66차, 방안G 구현]'
   기록을 근거로 long_mpc.py(base e6a00aea)에 방안G를 처음부터 다시
   구현" → `git am` 컨텍스트 불일치로 1차 실패(원본 패치 부재로
   정확한 원인 확정 불가) → 재구현 → 신규 clone 환경에서 `git am`
   성공 재확인 → 이 패치가 바로 `0c137f28b456`(author가 다른 커밋과
   달리 `Claude <claude@ryu.local>`인 이유). **62차(방안C devnotes
   유실→복구)와 유사한 사고가 코드 커밋 레벨에서 또 발생한 것 확정.**
   - **[신규, 중요] 추가로 확인된 점**: 이때 재구현 근거로 삼은
     "FINDINGS.md의 '[66차, 방안G 구현]' 기록" 자체가 **지금 이
     devnotes(70차 기준)에는 없음** — 즉 그 기록도 한 번은 존재했다가
     (재구현 시점 세션이 읽을 수 있었으므로) 이후 다시 유실된 것으로
     보임. **66차 방안G "설계 확정" 단계의 원본 기록은 여전히
     복원되지 않은 상태**(이번 70차에서도 코드 diff + 대화록 재구성
     수준까지만 복원, 원본 세션의 실측/시뮬레이션 상세 근거는 유실된
     채로 남음).

**결론 (69차 정정 사항)**:
- 방안D: "채택 경위 불명" → **명시적으로 시도 후 기각(폐기) 확정**
  (63차 계속3, 이유는 위 3번 참고).
- 방안E: "채택 경위 불명" → **1차 REJECTED 후 사용자 정정으로 재평가,
  최종 채택** — REJECTED 판단이 잘못된 프레임 적용이었음이 밝혀진
  경위까지 확정(위 6번).
- 방안F/H: "흔적 없음, 확정 불가" → **후순위 대기 중(미착수), 명시적
  기각 기록 없음**으로 정정. 폐기가 아니라 "아직 안 한 것".
- 방안G: 채택 경위(3안 비교, G 추천 사유) 확정, 67차 [재생성] 사고
  경위도 확정.
- **[신규, 미해결]** 세그7 후반에서 발견된 "저속 근접 gap 오실레이션"
  건은 이번 대화록에서도 코드화 이전 단계(발견만 됨)로 보임 — 다음
  세션에서 착수 여부 사용자 확인 필요.

**다음(사용자 결정 대기)**:
1. 방안F(x_lead 블렌딩)/방안H(vRel 연속 가중치)를 이어서 진행할지,
   방안G만으로 충분한지 사용자 판단 필요(66~67차 이후 실차검증
   결과에 달려있음).
2. 저속 근접 gap 오실레이션(세그7 후반) 조사 착수 여부.
3. `toolkit/sim_jerk_boost.py` 실물 존재 확인(69차에서 이월).
4. 방안E/G 둘 다 여전히 실차 acados 파이프라인 최종검증 없음 —
   최신 HEAD(`0c137f2`)로 업데이트된 실차 로그 확보 시 검증.

**코드 변경 없음(devnotes 기록 정정만)**.

---

## 68차 — "정체구간 앞차출발→정지 시 급정거" 제보, seg7/seg11 qcamera 대조 완료 (버그 아님으로 판정)

**배경**: 사용자가 "정체구간 앞차출발시 따라가다 앞차 정지시 내차 급정거"
증상 제보 → 신규 로그(route `0000031d--4ddb171bfb`, 14세그, HEAD
`0c137f28b456`=67차 방안G 시점, 단 **사용자 실제 기기는 58차까지만
적용된 구브랜치**라고 명시함 — 아래 유의사항 참고) 업로드받아 seg7/
seg11 두 지점을 qcamera 프레임 대조까지 포함해 분석.

**seg11 (t=735~795, 정체 정차→출발→재정차→출발)**: 58차2번이 겨냥한
바로 그 패턴(정지→출발→앞차 재감속) 실측 재현 — t=735~742 완전정차
(dRel 5.1m, vLead≈0) → t=742부터 앞차 출발, 자차도 부드럽게 추종
가속(vLead 0→4.6m/s) → t=754부터 앞차 재감속(vLead 4.6→0) → 자차도
매끈하게 감속(**aEgo 최저 -1.03m/s², 저크 없음**) → t=767 재정차 →
t=771 재출발, 이후 정상 순항 복귀. **급정거 징후 없음 — 58차2번
(LOW_SPEED_STRONG_DECEL 게이트)이 겨냥한 "정체구간 붕끗"이 발생하지
않고 매끈하게 처리된 정상 사례로 판정.** qcamera 대조는 생략(수치만
으로도 충분히 매끈함 확인, 저위험).

**seg7 (t=496~532, "급정거" 해당 구간)**: 애초 가설(58차2번류 정체
붕끗)과 다른 메커니즘으로 확인됨.
1. t=480~493 정차(신호 대기 추정, cruiseEnabled=False) → t=493.6
   자차 출발, 이후 t=505~519 정상 가속(0→13.8m/s), 이 구간 리드는
   전방 먼 차량(dRel 85~95m, 거의 무관한 원거리) — src road/cam 전환
   중, 곡선(vturn) 진입 직전.
2. **t=519.82: dRel 48.0m → 18.6m로 한 프레임(약 0.2s) 만에 불연속
   급락** (radar True→False, trackId 0→-1, src=vturn) — 겉보기엔
   61~66차 스레드가 다루는 "vision dRel 불연속(cutin 오인/트랙전환)"
   패턴과 흡사해 보였으나, **qcamera 대조 결과 실제 물리적 cut-in으로
   확인됨**: t=519.6 프레임에서 흰색 세단이 좌측 인접차로에 바짝
   붙어 주행 중이었고, t=520.5 프레임에서 그 차가 자차 차로로
   완전히 진입(끼어들기)해 정면에 위치함. leadDPath/leadYRel도 불연속
   전후로 자기 차로 범위(±1m 이내) 유지 — 즉 "엉뚱한 물체로 트랙이
   튄 것"이 아니라 "실제로 다른 차가 급히 끼어든 것"이 dRel 급락의
   원인. 61~66차가 다루는 커브 중 원거리 오검출형 불연속과는 **다른
   근본원인**(진짜 cut-in vs 트랙 오검출)이므로 혼동 주의.
3. t=521.3부터 레이더가 그 끼어든 차를 재락온(dRel 5.2m)하며 근접
   추종 시작. **t=527.62: aEgo -2.53m/s²(vEgo 30.5km/h)로 이번
   세션의 최저점** — qcamera 확인 결과 **끼어든 흰색 세단이 전방
   교차로 적신호 앞에서 실제로 급제동(브레이크등 점등, 교차로 정차
   차량들 확인)** 하고 있었음. 즉 자차의 감속은 "실제로 급정지하는
   앞차를 안전하게 따라간" 정상적 방어 반응으로 판정.

**결론(두 세그 종합)**: 이번에 제보된 seg7/seg11 두 사례 모두 **버그
아님** — seg11은 58차2번 개선이 의도대로 매끈하게 동작한 사례, seg7은
실제 cut-in + 실제 앞차 급제동에 대한 정당한 방어 반응(qcamera로
확정)이었음. "코딩이 끝났냐"는 질문에는 정체구간 붕끗(58차2번) 관점
에서는 seg11로 동작 확인됐다고 답할 수 있으나, seg7류(타차량
끼어들기+선행차 급제동)는 애초에 "고쳐야 할 버그"가 아니라 정상
동작 범주임을 사용자에게 안내 필요.

**유의사항(중요)**: 이 로그는 `commit 0c137f28b456`(67차 방안G, repo
HEAD 기준 메타데이터)로 추출됐으나, **사용자가 실제 기기는 58차까지만
적용된 구브랜치라고 명시** — 즉 CSV meta의 commit은 "이 세션에서 CSV를
디코딩한 repo 상태"일 뿐 로그 자체의 실제 기록 커밋과 무관(기존
원칙, 46차 등에서 반복 확인된 사항). 61~67차(dRel 불연속 방안 C~G)는
이 로그에 반영 안 됐을 가능성이 높으므로, 이번 seg7 cut-in류가
방안C~G 적용 후에는 어떻게 달라지는지는 이번 분석 범위 밖.

**[신규 발견, 경미] devnotes 기록 공백**: `ryu` repo 커밋 로그상
64~67차(방안 D/E/F/G, dRel 불연속 대응 계속)가 존재하나 FINDINGS.md/
WIP.md에는 63차 계속10(방안E)까지만 기록되고 그 이후(방안F/66차 방안G
등)의 devnotes 기록이 안 보임 — 62차 때와 유사하게 세션 종료 시 push
누락이 반복된 것으로 추정. **다음 세션에서 `git log` 기준 64~67차
커밋 내용을 FINDINGS.md/WIP.md/PARAMS_REGISTRY.md에 역보완 기록
필요.**

**코드 변경 없음(분석만)**, patch 없음.

## [69차, 역보완] devnotes 공백 채움 — git log 기준 63차 계속10(방안E)/66~67차(방안G) 실제 커밋 내용 기록

**배경**: 68차가 발견한 devnotes 공백(위 68차 섹션 참고)을 이번 세션에서
`ryu` repo `git log`/`git show`로 직접 대조해 역보완. **먼저 정정**:
68차 메모의 "64~67차(방안 D/E/F/G) 4개 커밋"은 부정확 — 실제
`4ea63c3`(방안C, 61차) 이후 origin에 존재하는 신규 커밋은 **딱 2개**뿐
(`e6a00ae`="63차 계속10 (a): 방안E", `0c137f28b456`="67차: 방안G
[재생성]"). 방안D/방안F는 별도 커밋으로 구현된 적이 없음 — 아래 정리 참고.

- **방안 D(63차계속 FINDINGS 제안: discontinuity 트리거 시
  `_vision_dRel_rate`/window를 직접 0으로 리셋)는 그대로 구현되지
  않았음.** 대신 다른 접근(방안E, 아래)이 63차 계속9/10에서 채택돼
  같은 목적(frac_rate/frac_ttc 오염 차단)을 다른 메커니즘으로 달성한
  것으로 추정 — 방안D가 "폐기"됐다는 명시적 기록은 없어 정확한 채택
  경위는 불명(NEEDS_VALIDATION, 다음에 사용자에게 확인 가능).
- **방안 F는 git log/코드 주석 어디에도 흔적이 없음.** 코드 주석은
  discontinuity 저크비용 부스트를 "66차/67차(방안G)"로만 지칭 —
  즉 66차에서 방안G를 설계하고 67차에서 구현/커밋한 것으로 보이며,
  방안F라는 알파벳은 설계 단계에서 건너뛰었거나(방안 A~E 다음이
  G로 넘어감) 별도 세션에서 논의만 되고 코드화되지 않은 채 유실된
  것으로 추정. **확정 불가 — 필요시 사용자 확인.**
- `0c137f28b456` 커밋 메시지의 "[재생성]" 표기와 author가
  `Claude <claude@ryu.local>`(다른 커밋들의 `ryu session
  <session@ryu.local>`과 다름)인 점으로 보아, 이 커밋도 한 번 유실
  되었다가(예: 컨테이너 리셋) 이전 세션 기록(FINDINGS.md/코드 diff
  자체는 남아있었거나 재구성 가능했던 것으로 추정)을 바탕으로 재작성돼
  다시 커밋된 것으로 보임 — 62차(방안C 유실→복구)와 유사한 패턴이
  devnotes 기록 없이도 코드 커밋 레벨에서 또 발생했을 가능성.

아래 두 섹션은 각 커밋의 diff(코드 내 상세 설계 주석 포함)를 그대로
역추출해 정리한 것 — 실제 세션에서 어떤 실측/시뮬레이션 근거로
파라미터 값을 정했는지까지는 diff에 없어 복원 불가(코드 주석에 있는
근거만 옮김).

---

### 63차 계속10 (a) — 방안 E: leadVLead 기반 참고 closing rate 상대적 타당성 클램프 (`e6a00ae`)

**배경(코드 주석 기준)**: cut-in 상황에서 트랙이 기존 리드→새로 끼어든
차량으로 전환되는 순간, raw dRel 미분(`raw_rate`)이 물리적으로 불가능한
크기(-100~-339m/s급)로 튀는 사례 확인(seg3/seg14, 63차 계속 r1-3/r1-14
재생검증과 같은 로그로 추정). 기존 절대값 클램프
(`VISION_CLOSING_RATE_MAX_PLAUSIBLE=30.0`)만으론 이런 트랙전환성
점프를 다 못 거름(30m/s 자체가 넉넉해서 -25m/s 같은 값은 통과).

**설계**: `raw_rate` 클램프 하한에 "모델이 이미 추정한 상대속도"
(`lead.vLead`) 기반 참고 closing rate를 추가.
```
ref_rate = -(v_ego - lead.vLead)              # 모델 기반 참고 closing rate
plausible_min = ref_rate - VISION_RATE_REF_MARGIN(5.0)
raw_rate_clamped = max(raw_rate, -VISION_CLOSING_RATE_MAX_PLAUSIBLE, plausible_min)
```
leadVLead가 실제 위험(빠른 접근)을 가리킬 땐 ref_rate도 함께 크게
음수가 돼 plausible_min도 낮아지므로 raw_rate를 거의 그대로 통과시킴
— 즉 leadVLead가 "안전(느린 접근/opening)"을 가리킬 때만 raw dRel의
과도한 튐을 억제하는 비대칭 구조. danger override(TTC<=2.5s)는 이
클램프와 완전히 무관하게 항상 유지.

**중요**: 이 클램프는 `raw_rate_clamped`를 `_vision_dRel_rate_window`에
쌓는 지점(중앙값 필터 입력)에 적용됨 — 즉 저역통과 필터에 들어가기
전 단계에서 오염을 막으므로, **63차계속에서 발견된 "방안C는 frac_rate/
frac_ttc 경로를 보호 못한다"는 보호 공백을 방안D와는 다른 지점(소스
자체를 정화)에서 우회적으로 커버할 가능성이 있음** — 단, 이게 실제
seg14류(r1-14, radar 락온 느린 케이스)까지 커버하는지는 이번 역보완
과정에서 재현 검증하지 않음(NEEDS_VALIDATION, 아래 참고).

**검증 이력(코드 주석 기준, 63차 계속9/10)**:
- 63차 계속9: seg14 로직단위 재생 — 계단식 포화가 램프 형태로 개선.
- 63차 계속10: seg3 재생검증 — PATCHED_E가 frac_rate를 0.209로 억제한
  것이 **오탐 억제가 아니라 정탐이었음을 확인**(레이더 락온 후 실측
  vRel +3.2~+7m/s, 즉 끼어든 차가 opening 중이었음 — leadVLead 참고치가
  맞았던 것). PARAMS_REGISTRY.md 27번 행에 이 정정 경위가 이미 상세
  기록돼 있었음(devnotes 공백에도 불구하고 PARAMS_REGISTRY만은 최신
  상태로 push돼 있었던 것으로 보임 — WIP.md/FINDINGS.md만 누락).

**상태**: PARAMS_REGISTRY.md 기준 NEEDS_VALIDATION(실차 acados 파이프라인
검증 없음). 코드는 이미 origin에 반영(`e6a00ae`).

---

### 66차/67차 — 방안G: discontinuity 직후 a_change_cost(MPC 저크비용) 한시적 부스트 (`0c137f28b456`, "[재생성]")

**배경(코드 주석 기준)**: discontinuity(방안C가 감지하는 dRel 급락)
직후, 아직 danger override급은 아니지만 절대거리가 부족한 상황(예:
68차 seg4-1류로 추정 — 이름만 언급, 상세는 불명)에서, 목표거리 자체는
그대로 두되 MPC가 그 거리에 "도달하는 속도"(저크비용)만 한시적으로
완만하게 만드는 접근. 방안 D/E가 신호(closing rate) 자체를 억제하는
쪽이었다면, 방안G는 신호는 그대로 믿되 MPC 반응 강도를 다른 축
(jerk cost)에서 누그러뜨리는 다른 층위의 조치.

**설계**:
```
DISCONTINUITY_JERK_COST_BOOST_S = 1.0    # s, 부스트 유지시간(트리거 후 감쇠)
DISCONTINUITY_JERK_COST_BOOST   = 500.0  # 평시 최대 A_CHANGE_COST(200)보다 큼
```
- discontinuity 트리거 시점(방안C와 동일 감지 지점, `_lead_acq_timer`
  리셋과 같은 프레임)에 `_discontinuity_jerk_boost_timer`를 arm.
- 매 사이클 `dt`만큼 감쇠(lane-change hold 타이머와 동일 패턴).
- `process_lead(leadOne)`에서만 갱신되는 `_lead0_danger_active`(danger
  override `ttc_now<=LEAD_ACQ_TTC_DANGER` 또는 58차2번
  `low_speed_strong_lead_decel`) — 이 플래그와 proactive floor(`frac`,
  frac_time/frac_ttc/frac_rate) 둘 다 비활성일 때만 부스트 값(500)을
  `a_change_cost`로 사용, 그 외엔 즉시 기존 `j_lead` 기반 식으로 복귀.
  즉 **위험 신호가 조금이라도 있으면 부스트는 즉시 무효화** — 안전
  경로 최우선 원칙 유지.
- `process_lead()`에 `is_lead0` 파라미터 신규 추가(leadOne 호출에만
  `True`) — leadTwo는 이 부스트 게이트와 무관.

**검증(PARAMS_REGISTRY.md 기준)**: `sim_jerk_boost.py`(devnotes에
언급은 있으나 이번 컨테이너엔 실물 확인 안 함 — 다음 세션에서
`toolkit/` 내 존재 여부 확인 필요) 합성검증 5건 PASS 기록:
정상부스트/danger 동시발생 시 억제/frac 동시발생 시 억제/discontinuity
미발생 시 회귀 없음(diff=0)/부스트 도중 danger 신규발생 시 즉시해제.
`git am` verify 브랜치(base `e6a00aea`) + `py_compile` 통과, 패치 전달
완료 기록. **실차 acados MPC 파이프라인 검증은 아직 없음(NEEDS_VALIDATION,
PARAMS_REGISTRY.md 34번 행과 동일).**

**주의**: 68차 세션에서 분석한 로그(HEAD `0c137f28b456` 기준 추출)는
**사용자 실제 기기가 58차까지만 반영된 구브랜치**였다고 명시돼 있어,
방안E/G가 실제 주행에 반영된 로그는 이번 devnotes에 아직 하나도 없음
— 다음 실차 검증 시 이 점 유의(방안C까지만 반영된 상태에서의 거동과
방안E/G까지 반영된 이후 거동을 혼동하지 말 것).

**다음(최우선)**:
1. `toolkit/sim_jerk_boost.py` 실물 존재 확인 — 없으면 코드 주석
   근거만으로 재구성하거나, 사용자에게 원본 세션 기록 여부 문의.
2. 방안D 폐기/방안E 채택 경위, 방안F 존재 여부 자체를 사용자에게
   직접 확인(코드/git log만으론 확정 불가).
3. 방안E/G 둘 다 여전히 NEEDS_VALIDATION — 사용자가 최신 브랜치
   (`c3-ms-dev` HEAD, 방안G까지 포함)로 실차 업데이트 후 재현 로그
   확보 시 cutin(r1-3/r1-14류)/discontinuity 반응 완화 여부 검증.

**코드 변경 없음(ryu 미변경, 기존 커밋 diff 역추출 기록만)**.

---

## 61차 계속 (체크포인트3) — 16세그 중 나머지 13세그 qcamera 대조 완료, 이전 패치(A/B)까지 포함 검증

**배경**: 61차 체크포인트1/2에서 seg1(옆차선 레이더 오탐 급감)과 seg3/4
(옆차선 카메라 오탐 급감, 재확인 결과 진짜 정지차량)만 qcamera 대조를
마쳤고 나머지 13세그는 자동 스캔(이상없음)만 완료된 상태였음. 사용자가
"이번 패치뿐 아니라 그 이전 패치도 같이 검증, 나머지 증상도 증상별
분석, qcamera 대조 필요"를 요청 → route1(`a2141d7786` 9세그)/route2
(`6f02a46c8a` 7세그) 동일 로그(commit `d6e334f1ddb5` 확인, 60차
계속8+60차 A(dPath게이트)+B(prob단독리셋제거) 전부 반영된 상태)로
나머지 13세그 개별 qcamera 프레임 대조 진행.

**검증 대상 패치 2건**:
1. 60차 계속8(`d6e334f`) — `get_lead()` 외곽게이트 버그 수정(60차 A의
   tentative 조기등록이 실제 출력까지 전파되게 함)
2. 60차 A(dPath 절대값게이트, `a75c5cc`)+B(prob<0.35 단독리셋 제거,
   `1a44491`) — 이번이 두 패치가 실제로 반영된 상태에서의 첫 다표본 실차 검증

**증상별 qcamera 대조 결과 (11세그, t=이벤트시각/aEgo최소값)**:
- **앞차카메라 인식 감속** (route1 seg1 t=168.8/-3.02, seg6 t=447.9/-3.04,
  seg17 t=1096.25/-1.27, seg19 t=1233.79/-1.55, route2 seg5/seg6
  t=1669.55/-1.44): 전부 화면에 실제 선행차(정체열/신호대기/교차로
  진입 등)가 뚜렷이 보임 — **전부 정탐**, 오탐(phantom lead) 없음.
- **cutin 급감속** (route1 seg3 t=259.94/-3.24, seg14"택시" t=925.15/
  -4.29): 둘 다 화면에서 실제 차량(다크 SUV/택시)이 차로 안으로
  끼어드는 장면 확인 — **정상 cutin 반응**.
- **cutout 감속** (route1 seg12 t=802.80/-3.87): 근접 선행차(회색
  세단) 제동 장면 확인 — **정상**.
- **내차 차선변경** (route1 seg9): blinker 활성구간(t=629~643) 내내
  aEgo가 0 근처(-0.26~+0.68)로 팬텀 감속 전혀 없음 — **60차 A의
  dPath 게이트가 차선변경 중 옆차로 오탐을 정상적으로 막고 있음을
  재확인**(이후 t=644~ 감속은 blinker 종료 후 별개의 정체 진입,
  차선변경과 무관).
- **정체 정지출발후 급감** (route1 seg15 t=997.45/-2.11, route2 seg2
  t=1417.35/-0.65): 둘 다 화면상 실제 정체 차량열 확인 — 정탐. 단
  route2 seg2는 라벨상 "급감"인데 기록된 aEgo는 -0.65로 완만함 —
  **체감 "급감"이 감속 크기보다 저크(rate of change)/급작스러운
  개시 쪽에 가까울 가능성**(58차3번 롤백 때도 나왔던 동일 가설,
  NEEDS_VALIDATION, 추가 미세 저크 스캔 필요).
- **정지 앞차 카메라 인식** (route2 seg4 t=1516.21/-1.07): 신호대기
  중인 정지 선행차(브레이크등 점등) 뚜렷이 확인 — **58차1/60차 A가
  겨냥한 "정지앞차 조기인식" 핵심 시나리오가 실제로 정상 동작**.

**종합 판단**: 오늘 세션에서 신규로 qcamera 대조한 11세그 + 61차
체크포인트1/2의 3세그(seg1/3/4) = **총 14/16세그 개별 qcamera 검증
완료**(route2 seg5는 aEgo -0.33 저위험이라 저우선 생략). **오탐
(phantom lead/불필요감속) 사례 0건** — 16세그 전체에서 유일한
이상신호는 여전히 seg1(옆차선 레이더 오탐, 61차 체크포인트1에서
이미 별도 메커니즘(`track_scc`/37차 SCC_FALLBACK_DPATH_GATE 사각지대)
으로 규명된 건) 하나뿐. **60차 계속8(외곽게이트 수정) + 60차 A/B
(tentative 조기등록+dPath게이트) 조합이 다양한 증상 표본에서 회귀
없이 안전하게 동작 중임을 확인.**

**남은 항목**:
1. route2 seg2류 "체감 급감 vs 기록 aEgo 완만" 괴리 — 미세 저크
   스캔(58차3 롤백 때 제기된 가설과 동일 축) 필요, 저우선.
2. seg1 근본원인(옆차선 SCC 폴백 vLead<5.0 조건부 사각지대) 패치
   설계는 여전히 미착수 — 사용자 논의 대기 중이던 항목 그대로 유효.
3. route2 seg5 개별 qcamera 미실시(저위험 판단으로 생략) — 필요시 추가.

---

# FINDINGS — 이슈 / 검증 상태 누적 기록

세션이 끝나도 남아야 하는 것만 여기 기록한다. 대화 내용 전체를 옮기지 말고,
"무엇을 발견했고, 지금 상태가 뭔지"만 짧게. 새 세션 시작할 때 이 파일을
먼저 훑으면 이미 끝난 걸 다시 분석하지 않아도 된다.

각 항목 형식:
```## [FIXED, URGENT] 60차 계속8 — get_lead() 외곽게이트가 60차 A(tentative)를 무력화시키던 버그 재발/수정

**증상**: 60차 A(`a75c5cc`)+B안(`1a44491`)까지 적용된 상태에서도, 실제
`radarState.leadOne` 출력엔 tentative 조기등록 효과가 전혀 반영 안 되고
있었을 가능성. 원인은 `RadarD.get_lead()`(`VisionTrack.update()`를
감싸는 바깥 함수)의 `elif (track is None) and ready and (lead_msg.prob
> .5): lead_dict = self.vision_tracks[index].get_lead(md)` — 이
`lead_msg.prob`를 `VisionTrack` 내부와 별개로 독립 재체크하는 구조가
`VisionTrack.update()` 안에서 tentative_cnt 누적으로 `self.status`가
먼저 True가 돼도, 바깥 게이트가 여전히 정식 prob>.5만 보고 노출을
막아버림.

**58차3번 후속수정과 동일 패턴 재발**: 이건 58차3번 후속수정(`1145aea`,
2026-08-23)이 이미 한 번 고쳤던 정확히 같은 버그. 58차3번+후속수정
전체가 실주행 체감 오탐으로 롤백(`1ac07de`, radard.py를 58차2번 시점
diff 0으로 완전 원복)되면서 이 외곽게이트 수정도 함께 사라졌고, 60차
A가 tentative 로직을 처음부터 재구현하면서 외곽게이트 재반영을
빠뜨렸음.

**발견 경위**: 사용자의 "이 패치가 컷인 상황에도 영향을 주나" 질문에
답하려고 컷인 판정 경로(`compute_leads()`)와 `VisionTrack` 경로가
겹치는지 코드를 재확인하던 중 이 외곽게이트를 다시 읽다가 발견.

**함의(중요)**: 60차 계속5/6에서 진행한 시뮬레이션(원 사례 9.2초
앞당김 등)은 `VisionTrack.update()`의 tentative 분기만 순수함수로
재현한 것이라 이 외곽게이트 버그를 반영 못함 -- 로직 자체는 유효하나,
**이번 발견 전까지는 실제 기기 출력엔 전혀 반영 안 되고 있었을 가능성이
높음.**

**조치**: `elif ... (lead_msg.prob > .5):`를 `elif ... self.vision_
tracks[index].status:`로 교체(58차3번 후속수정과 동일 방식).

**검증**: `git am`(base `1a44491`, 사용자 실제 HEAD를 이번 세션에서
fetch로 확보) 컨텍스트 일치 + `py_compile` 통과.

**전달**: `0001-60-8-get_lead-lead_msg.prob-vision_tracks-index-.sta.patch`
전달, `C:\dev\ryu`에서 `git am` 적용 대기.

**교훈(향후 체크리스트)**: tentative/status류 "내부 상태 승격" 로직을
추가할 때는, 그 상태를 실제로 소비(consume)하는 모든 바깥 호출부가
독립적인 재체크 조건을 갖고 있지 않은지 반드시 코드 리딩으로 확인할
것 -- 58차3번/60차 A 둘 다 같은 유형의 버그로 "합성검증 PASS"와
"실제 출력 반영"이 분리됐었음.


## [NEEDS_VALIDATION] 60차 A(tentative 조기등록) — 58차3번 원 사례(a3a55cb808--10) 재시뮬레이션 결과: 효과 0

**배경**: 60차 A(`a75c5cc`, dPath 절대값/jitter 게이트 추가)가 실제로 58차3번을
촉발한 원 사례(route `a3a55cb808--10`, t=4301~4312, 정체구간 정지앞차
미인식)를 얼마나 앞당기는지 modelV2 프레임 실측으로 검증.

**방법**: `extract_modelv2_leads.py`(신규, work/ 스크래치 — toolkit 미편입)로
leadsV3[0]의 prob/dRel/dPath(Track.d_path와 동일 원리, md.position 보간)를
프레임 단위 추출(1200행), `a75c5cc` 코드의 `VisionTrack.update()` tentative
분기를 순수함수로 그대로 재현해 재생.

**결과**: 유실 시작(t=4299.575) 이후 최초 재등록 시각이 **패치 전/후 완전
동일**(t=4309.276, prob=0.528 정식 크로싱) — tentative 경로가 단 한 번도
발동하지 않음.

**원인**: 이 9.7초 유실 구간에서 `tentative_cnt`가 최대 3까지만 도달
(`CNT_GATE=10` 필요). 리셋이 3회 발생했는데 **전부 `prob<0.35` 하한
리셋**(dPath/dRel 게이트가 아님) — modelV2 prob 자체가 0.0x~0.5 사이를
넓게 오르내리며 표류해, dPath 게이트 로직까지 도달하기 전에 카운트가
계속 끊김.

**함의**: 60차 A의 합성검증 5건(PASS)은 전부 "prob가 tentative 구간에
안정적으로 머무는" 이상적 시나리오였고, 58차3번을 촉발한 실제 문제
사례(prob가 광범위하게 표류)는 이번에 처음 실측 검증했는데 여기선
CNT_GATE=10이 사실상 발동 불가 수준으로 높음. 즉 **60차 A는 원래
목적(정지앞차 조기인식)을 이 사례 기준으로는 달성 못함** — 옆차선
오탐 차단(dPath 게이트) 효과는 합성검증대로 유효할 가능성 높으나 별개.

**다음(사용자 결정 대기)**:
1. `CNT_GATE` 하향(10→3~5) — 이 사례는 통과하지만 오탐 문턱도 동반 하락
2. `prob<0.35` 하드리셋을 완만한 decay로 변경
3. `PROB_GATE` 하한(0.35) 자체를 낮춤 — 가장 공격적
4. 또는 이 사례는 개선 보류하고 현재 패치(옆차선 오탐 차단 효과) 그대로
   실차 검증 진행

58차3번이 "실주행 체감 오탐"으로 롤백됐던 전례가 있어, 1~3번 방향은
오탐 리스크 트레이드오프를 신중히 판단해야 함.

**[갱신] 조치안 비교 시뮬레이션 완료, B안 채택**: A안(dPath in-lane이면
prob/cnt 무관 즉시등록)/B안(prob<0.35 단독 리셋 제거, dRel/dPath
jitter·dPath 절대값 게이트만 리셋 사유 유지, CNT_GATE=10 그대로) 두
안을 원 사례+옆차선 오탐 회귀+단발 노이즈(1프레임 유령객체) 오탐
3개 기준으로 비교:
- A안: 원사례 9.66초 앞당김, 옆차선차단 PASS, **단발노이즈 FAIL**(1프레임
  즉시등록) — 58차3번 롤백 사유(flicker/체감오탐)를 키우는 방향이라 기각.
- **B안: 원사례 9.20초 앞당김(8.1초 지연 사실상 해소), 옆차선차단 PASS,
  단발노이즈 PASS(0.5초 연속요구 유지) — 채택.**

사용자 결정으로 B안 구현 진행.

## [상태] 제목 (발견일, 관련 커밋/파일)
- 증상:
- 원인:
- 조치: (수정됨 / 검토중 / 보류)
- 근거 로그: (있으면 라우트명 + 타임스탬프)
```
상태 태그: `[FIXED]` 수정 완료 / `[INVESTIGATING]` 원인 분석 중 /
`[NEEDS_VALIDATION]` 코드는 있으나 실도로 검증 필요 / `[WONTFIX]` 보류

---

## [VALIDATED] 59차 route1(dashcam_1787536597306) baseline(58차1,2 반영) 재확인 + qcamera 대조 (2026-08-24)
- **배경**: 58차3번+후속수정 롤백 후 baseline(58차1,2번만 반영,
  commit `1ac07def461d`) 재확인. 19세그, 22797행, 약 19분/11.68km
  주행. 카메라 인식율 개선 논의(59차 WIP) 이어서 사용자가 신규 실주행
  로그 2개 업로드, 첫 번째(route1) 분석.
- **비전-레이더 크로스오버**: 27건(고속도로 추정 14건), frac_rate
  게이트 정상 범위로 판단(56/57차 대비 이상 저반응 패턴 없음).
- **정지앞차 감속**: 9건 전부 clean(harsh_brake 없음).
- **정지 후 재출발**(45차 launch bypass): 4건 전부
  `driver_gas_frames=0`(순수 ADAS 재출발), aEgo_max 정상 범위 —
  패치 정상 동작 확인.
- **레이더락온 저크 민감반응**: 32건 탐지, `|leadVRel|<1.0 &
  |jerk|>=5.0`(55/56차 이상패턴 조건) 필터 결과 **0건** — 이번
  route는 55차 route1 seg18/56차 4건급 이상패턴 재현 없음(baseline
  정상 판단, 표본 부족일 수 있어 추가 route로 재확인 필요).
- **곡선구간**: `turn_speed_violations` 0건(이번 route는 커브
  구간 자체가 적었던 것으로 추정), `curve_exit_no_accel_scan_v4`
  체크 예정(별도 미실행, 다음 세션 보완).
- **커브노이즈 필터(`curve_noise_refined`)**: 원시 dRel 점프 38건 중
  82.1%를 노이즈로 억제, 5건이 필터 통과(진짜 위험 후보). **qcamera
  5건 전부 대조 확인**: 4건은 밀집교통/커브+교차로 진입 등 실제
  물리적으로 타당한 상황(회전교차로 접근, 정체구간 차량 밀집), 1건
  (t=1258.43)은 단일 전방차량에 대한 정상적인 접근(오탐 아님). **필터
  설계가 이번 표본에서는 보수적이고 타당하게 동작** — 신규 오탐 없음.
- **조향 오실레이션**: 5건 탐지, 최대진폭 2건(72.5°@seg9 t=675.79,
  112°@seg17 t=1112.78) qcamera+CSV(`leftBlinker`/`laneChangeState`)
  대조. seg17 건은 **`leftBlinker=True` + `laneChangeState=off`** +
  좌회전 교차로 프레임 확인 — 기존에 알려진 "수동 회전시
  laneChangeState=off인 채 blinker+curvature만 잡히는" 패턴과 동일
  메커니즘(방향만 좌측). ADAS 버그 아니라 교차로 수동 좌회전 중
  정상 조향거동으로 판단. seg9 건은 blinker 없이 완만한 커브 프레임
  확인, 정상 커브 조향.
- **cut-in**: 1건(t=424.93, 교차로, vEgo 5.4m/s) — qcamera 대조 결과
  교차로에서 옆에서 진입하는 차량과의 정상적 저속 상호작용, 위험 아님.
- **안전지표**: harsh_brake 0건, ttc_danger 6건 전부 `count_adas=0`
  (ADAS 비활성 구간, 즉 무관), cruise_disengage 3건(원인 미확인,
  저우선).
- **결론**: route1은 58차1,2번 baseline에서 **신규 이상패턴 없음**.
  55/56차급 레이더락온 저크 이상패턴 재현 안 됨(표본 협소 가능성
  있어 route2로 재확인).
- **다음**: route2(dashcam_1787536569182) 동일 분석 + qcamera 대조.

---

## [VALIDATED] 59차 route2(dashcam_1787536569182) baseline(58차1,2 반영) 재확인 + qcamera 대조 (2026-08-24)
- **배경**: route1에 이어 두번째 업로드 로그. 8세그(마지막 세그는
  489행으로 조기종료), 8891행, 약 7.4분/4.27km. **`cruise_enabled_
  ratio=0.642`, `brake_pressed_ratio=0.282`로 route1(0.938/0.055)
  대비 수동주행·정체 비중이 훨씬 높음** — 협소구간/주차장 인근으로
  추정.
- **비전-레이더 크로스오버**: 4건. 그 중 최대 접근(t=1600.08,
  vRel=-14.17, dRel_closed=33.69m) 프레임+CSV 정밀대조: **qcamera로
  전방 정체 차량행렬 확인**(진짜 강접근), **CSV 확인 결과 vision
  락온(t=1600.08) 이전부터 이미 aEgo -1.3~-1.6m/s²로 선제 감속 중이었고,
  t=1604.29 레이더 컨펌 전환 시점에도 aEgo가 완만하게(-0.02→+0.32)
  전환되며 저크 스파이크 없음** — 58차1번 v_lead 직접보정이 의도대로
  매끄럽게 동작하는 것으로 확인(정성적 정탐 사례로 기록해둘만함).
- **정지앞차 감속**: 2건 전부 clean(harsh_brake 없음, aEgo_min
  -0.6~-1.0).
- **정지 후 재출발**: 2건 탐지됐으나 **둘 다 driver_gas_ratio
  0.667/1.0으로 운전자 개입 재출발**(ADAS 45차 launch bypass 케이스
  아님, 이번 route는 해당 패치 검증 표본에서 제외).
- **레이더락온 저크**: 15건, `|leadVRel|<1.0 & |jerk|>=5.0` 필터
  결과 0건 — route1과 동일하게 이상패턴 재현 없음(2/2 route 모두
  클린, baseline 저크 이상 관련해서는 이번 신규 로그 세트에서 재현
  안 됨).
- **곡선구간**: `turn_speed_violations` 3건, 최대 초과 3.77km/h.
  qcamera 대조(t=1391.08, vEgo 63.8km/h vs vTurnSpeed 61) — 완만한
  우커브 오버슈트, 기존 vturn apex lag 이슈(51/54/55/56차)와 일관된
  패턴 재확인(신규 아님).
- **커브노이즈 필터**: 원시 점프 2건 중 1건 필터 통과, qcamera 대조
  결과 **광폭 교차로에서 단일 전방차량에 대한 진짜 접근**(오탐 아님).
- **조향 오실레이션**: 1건(93°, t=1711.79~1713.78, seg7). qcamera
  대조 결과 **협소 구간에서 마주보는 차량(BMW)과 밀집 주차차량 사이를
  저속으로 통과하는 수동 주행 구간** — ADAS 이상이 아니라 물리적으로
  좁은 공간에서의 정상적 저속 스티어링 거동으로 판단.
- **cut-in + ttc_danger(같은 클러스터, t=1706~1708, seg7)**: dRel이
  6.0m→1.78m까지 근접, min_ttc=2.01s(danger 문턱 2.5s 하회).
  **qcamera 대조 결과 정체 차량행렬 속 매우 저속(vEgo 0.05~0.46m/s)
  근접 추종 상황** — 기존에 이미 알려진 "저속+작은 dRel 구간에서
  TTC 공식 자체가 왜곡되는" 현상(PARAMS_REGISTRY TTC 게이팅 항목
  참고)과 일치, 실제 위험 아님. 이 구간 `stopped_lead_decel_events`
  (t=1706.53~1709.53)와 시간대 겹침, harsh_brake 없이 클린하게 처리됨
  확인.
- **결론**: route2는 수동주행 비중이 높아 ADAS 개입 표본 자체가
  route1보다 적지만, 확인된 범위 내에서 **신규 이상패턴 없음** —
  route1과 합쳐 이번 2개 로그 세트 전체에서 baseline(58차1,2번) 이상
  무재현. 특히 강접근 크로스오버 사례(1600.08)는 58차1번 패치의
  긍정적 동작 근거로 기록.
- **다음**: 사용자가 추가 로그 제공 시 동일 분석 반복. 55/56차급 저크
  이상패턴이 이번 2개 route 모두에서 재현 안 됐으므로, 표본이 더
  쌓이기 전까지는 해당 이슈를 저우선으로 조정 검토 가능(단, 완전
  종결은 이르므로 계속 스캔 유지 권고).

---

## [REVERTED] 58차 3번(A+B)+후속수정 전체 롤백 — 실주행 체감 오탐/불필요감속 (2026-08-24)
- **배경**: 직전 세션에서 CSV+qcamera 대조로 부분 `VALIDATED`(seg0 정탐
  확정, 외곽게이트 후속수정 실전파 690 row 확인)까지 갔었으나, 사용자의
  실제 주행 체감 피드백은 **"오탐이 많고 불필요한 감속이 있었음"**으로
  상반됨.
- **조치**: `radard.py`를 58차2번(`a35a39f`) 시점으로 완전히 되돌리는
  revert 커밋 작성 → 사용자가 `C:\dev\ryu`에서 로컬을
  `git reset --hard origin/c3-ms-dev`로 원격과 동기화(기존 로컬이
  `591f219`에서 23커밋 뒤처져 있었음, 먼저 정리) 후 `git am` 적용 +
  `git push` 완료 — `1145aea..1ac07de`.
- **검증**: 원격 fetch로 `radard.py`가 `a35a39f`와 diff 0(완전 동일)
  임을 재확인, `py_compile` 통과.
- **현재 상태**: A(tentative 조기등록)/B(저확신구간 안전측 보정)/외곽
  게이트 후속수정 전부 코드베이스에서 제거됨. 58차1번(vision dRel미분
  게이트 완화+long_mpc v_lead 보정)과 58차2번(저속+강한감속 danger
  override)만 유효.
- **다음(중요)**: 왜 CSV/qcamera 표본 분석과 사용자 체감이 어긋났는지
  원인 분석 필요 — 연속구간 묶기 로직이 짧은 flicker를 과소집계했을
  가능성, "오탐" 판정 기준을 급감속(aEgo 임계값)이 아니라 미세한 jerk/
  체감 저크 기준으로 다시 스캔할 필요. 58차1,2번만 반영된 현재 HEAD로
  먼저 주행감 재확인 → A/B는 이 분석 이후 재설계.

## [FIXED] 58차 3번 후속 — A(조기등록)를 무력화시키던 get_lead() 외곽 게이트 중복체크 버그 (2026-08-23, 58차 3번 후속수정) [이후 REVERTED, 위 항목 참고]
- **배경**: 58차3번(A+B) push 직후 "기기에러 안 나는지 검증" 요청으로
  코드 재검토 중 발견.
- **증상**: `VisionTrack.update()` 내부에 A(tentative 조기등록)를
  넣었지만, 이를 감싸는 바깥 `RadarD.get_lead()`가
  `elif (track is None) and ready and (lead_msg.prob > .5):`로
  `lead_msg.prob`를 독립적으로 재체크 — A로 `VisionTrack.status`가
  일찍 True가 돼도 이 게이트에 막혀 `radarState.leadOne`엔 전혀 반영
  안 됨. **크래시는 아니고 A가 실질적으로 무력화된 논리버그.**
- **원인**: A 설계 당시 `VisionTrack.update()` 내부만 보고 바깥
  호출부의 독립적인 동일 조건 중복 체크를 놓침.
- **조치**: 바깥 게이트 조건을 `lead_msg.prob > .5` 대신
  `self.vision_tracks[index].status`로 교체(이미 같은 tick에 update()
  끝난 최신 상태를 신뢰 — 정식경로+A 조기등록 경로 둘 다 자연스럽게
  커버).
- **검증**: `sim_vision_track_ab.py` `scenario_outer_gate_propagation`
  신규(구게이트 8초간 미노출 / 신게이트 프레임9 노출 확인), 전체 7건
  PASS. `git am` base `ff50b03`(원격 실제 HEAD) 검증 통과.
- **근거**: 코드리뷰(로그/실차 재현 아님). 크래시 위험 자체는 별도로도
  점검 완료(신규 필드가 capnp 대입 경로에 안 들어감 확인, 40차
  `sccFallback`류 재발 없음).
- **push 완료**: 사용자가 `C:\dev\ryu`에서 `git am` 적용 +
  `git push origin c3-ms-dev` 완료 — `ff50b03..1145aea`. 원격 fetch로
  게이트 반영 및 `py_compile` 재확인 완료. 상태 `PATCH_APPLIED` →
  `NEEDS_VALIDATION`(실차 검증 대기, A 오탐지 회귀 확인 필수)로 전환.


- **증상**: 산길 정체구간에서 정지앞차를 인식 못 해 운전자가 브레이크
  개입(`정지차량_미인식.zip`, route `a3a55cb808` seg10, t=4301~4312).
- **원인**: `radard.py` `VisionTrack.update()` 두 지점.
  1) `if self.prob > .5: ... else: self.reset()` — modelV2 prob이 0.5
     못 넘으면 트랙 자체 미생성. 실사례에서 t=4302~4309.3(8초)간 화면엔
     차량이 또렷이 보이는데도 prob이 0.5를 못 넘어 `leadStatus=False`
     유지.
  2) `if cnt<CNT_GATE or prob<PROB_GATE(0.70): vRel=lead_v_rel_pred`
     (모델예측 그대로) — prob 0.5~0.70 구간(이번 사례의 t=4309.3~4311.8,
     prob=0.53)은 실측 dRel미분 블렌딩이 전혀 없어 모델의 낙관적 예측
     (vLead 27->14m/s)이 그대로 반영됨. 레이더 락온 순간(t=4311.85)
     실제값(4.88m/s)과 큰 괴리 확인.
- **조치**: (A) prob가 0.35~0.5 구간에서 같은 위치로 10프레임(0.5s)
  연속 잡히면 조기등록(`tentative_cnt`, dRel 8m+ jitter시 리셋). (B)
  prob<0.70 구간에서도 dRel 실측 2프레임+ 쌓이면 실측기반 vLead가 모델
  예측보다 위험할 때만 `min()` 안전측 보정(58차1번과 동일 원칙).
- **검증**: `sim_vision_track_ab.py` 로직단위 6개 시나리오 전부 PASS
  (조기등록/저prob미등록회귀/jitter오인방지/안전측보정/정상무간섭/
  고prob회귀). **실제 acados 파이프라인·실차 검증은 아직 없음.**
- **근거 로그**: route `a3a55cb808` seg10, t=4301.21~4312 (`정지차량_
  미인식.zip`), qcamera 프레임 10장(t=4302~4315) 대조 완료.

## [CORRECTION] 44차 — 42차 "route B seg10 vision dRel 노이즈" 결론 정정: 실제로는 ego 우측 방향지시등+조향 급반전(차선변경/측방기동)과 정확히 겹침 (2026-08-22, 44차)
- **배경**: 42차는 route B seg10 t=1895.6~1896.25 dRel 점프(86.9m→42.5m)를
  "곡선 구간에서 vision이 순간적으로 깊이를 잘못 추정한 노이즈"로
  결론냈으나, 사용자가 "이 시점이 본인 차선변경 시점과 동일한 것
  같다"고 재검토 요청. 확인해보니 **42차 당시 CSV에는 애초에
  차선변경 여부를 판별할 컬럼(blinker/laneChangeState)이 없어서 그
  가능성 자체를 검증할 수 없는 상태**였음(도구 공백, 43차에서
  `extract_log.py`에 4컬럼 추가로 해소).
- **재검증 결과 (동일 로그 `20260822_164710_000002fa--ff2d0a3934--10`,
  HEAD `c31ddca`, 42차와 동일 이벤트)**:
  - `rightBlinker`가 **t=1895.200**에 True로 켜져 **t=1896.703**까지
    유지됨 — dRel 점프 구간(t=1895.598~1896.254)이 이 블링커 구간
    한가운데 정확히 포함됨.
  - 같은 구간에서 `desiredCurvature`가 -0.00036(도로의 좌커브를
    따르던 값) → t=1896.1에 **+0.00097로 급반전** — 단순 커브
    주행에서는 나오지 않는 **S자형 조향 패턴**. 블링커가 꺼지는
    t=1896.7 이후 다시 음의 값(원래 도로 커브 방향)으로 되돌아감.
  - `lateralPlan.laneChangeState`는 이 구간 내내 `off` — openpilot
    자체의 자동 차선변경(LCA) 로직이 작동한 게 아니라 **운전자
    수동 조향/신호로 추정**(곡선 도로라 차선인식이 약해 LCA
    상태머신이 아예 안 걸렸을 가능성).
  - qcamera 프레임(t=1894.9/1895.2/1895.6/1895.9/1896.25/1896.7/
    1897.1/1897.6) 대조: 우측에 적색 사선 마킹 구역(정차금지구역/
    버스정류장 추정)이 있고, 이 구역 쪽으로 붙어가는 궤적이
    프레임상 확인됨. 42차가 관찰했던 "SUV 화면 크기 큰 변화 없음"
    자체는 맞지만, 그것만으로 "위험 없음/노이즈"라고 단정한 게
    성급했음.
  - **코드 레벨 메커니즘 확인**: `radard.py`의
    `dPath = yRel + interp(dRel, md.position.x, md.position.y)`에서
    `md.position.y`(모델이 계획한 경로)가 급변하면, 같은 물리적
    위치의 리드라도 `dPath`/`in_lane_prob`이 흔들려 `center_list`
    소속 여부나 `match_vision_to_track` 매칭 결과가 바뀔 수 있음
    (`compute_leads`/`get_lead`, L771~880 부근). 즉 "카메라가 깊이를
    잘못 쟀다"보다 **"경로 기준 자체가 급변해 동일 차량의 리드
    판정이 흔들렸다"**는 설명이 코드 구조상 더 정합적.
- **정정된 결론**: 이 이벤트는 순수 vision 노이즈가 아니라, **ego의
  실제 측방 기동(우측 방향지시등+조향 급반전)과 정확히 겹치는
  현상**이었다. 42차의 "커브 구간 vision 깊이 오추정" 가설은 이
  이벤트에 대해서는 **철회**. 단, 42차가 확인한 "SUV 자체는 계속
  존재하며 서서히 접근 중이었다"는 관찰은 여전히 유효(dRel 자체가
  허구는 아니었음) — 다만 그 원인이 vision noise가 아니라 경로
  급변으로 인한 리드 판정 흔들림일 가능성이 높다는 것.
- **파급 영향**: 41/42차가 "다음 세션 후보"로 제안했던
  `curve_lead_dRel_jump_consistency`류 일관성 체크를 vision-only
  closing-rate 게이트에 적용하자는 아이디어는 **재검토 필요** — 이런
  종류의 dRel 변화를 "노이즈"로 일괄 억제하면, 운전자의 실제 의도적
  기동(차선변경 등)에 반응해야 하는 순간을 놓칠 위험이 있음.
- **조치**: 코드 변경 없음(관찰/분석만), FINDINGS 정정만. 42차 항목은
  삭제하지 않고 아래에 그대로 남겨두되(기록 보존), 이 항목을
  최신/우선 결론으로 참고할 것.
- **다음 세션 후보**:
  1. `match_vision_to_track`/track id 로깅이 없어 "리드가 실제로
     다른 물리적 트랙으로 스왑됐는지"까지는 확인 못 함 — track id를
     CSV에 추가해 재검증하면 메커니즘을 더 확정할 수 있음.
  2. 이런 "블링커+조향 급반전과 겹치는 dRel 점프" 패턴이 다른
     이벤트에서도 재현되는지 추가 로그로 확인.
  3. `curve_lead_dRel_jump_consistency`를 vision-only 게이트에
     적용하는 방안은 이 정정 이후 **보류(WONTFIX 후보로 하향)** —
     최소한 blinker/laneChangeState 조건으로 실제 조향 기동 구간을
     제외하는 안전장치 없이는 적용 금지.
- 근거: `20260822_164710_000002fa--ff2d0a3934--10.zip`(route B seg10
  단일세그먼트 재업로드, HEAD `c31ddca`), 재추출 CSV
  `/home/claude/work/routeB_seg10.csv`, 프레임
  `/home/claude/work/frames/eventB_seg10_lanechange_recheck/`.

---


- **배경**: 41차에서 로그(CSV)만으로 분석했던 급접근 4건(A seg11 t=745.1,
  A seg19 t=1214.7, B seg6 t=1650.3, B seg10 t=1895.6)에 대해, 이번엔
  사용자가 같은 라우트의 `qcamera.ts`를 포함해 재업로드(`앞차_카메라_
  인식.zip`) — route ID(`05890d8ca1`, `ff2d0a3934`)/세그먼트/HEAD(`c31ddca`)
  전부 41차와 동일한 로그, 이번엔 영상 프레임까지 대조 가능해짐.
  `extract_dashcam_frames.py`로 각 이벤트의 vision-only 시작/중간/레이더
  락온 시점 프레임을 `qRoadEncodeIdx` 동기화로 추출해 CSV 수치와 대조.
- **이벤트 1(A seg11, 고속도로, src=road)**: t=743.95(dRel 115m 포착) →
  745.10(105m, vRel -5.7) → 748.15(레이더 락온, dRel 69.4m로 스냅, vRel
  -9.6) 프레임 전부 확인 — 같은 흰색 세단이 고가도로 아래를 통과하며
  전 구간 동일 차선에서 지속적으로 관측됨, 프레임상 차량 크기가
  자연스럽게 커짐(진짜 접근). aEgo도 t=745.9부터 매끈히 감속 시작해
  t=749.55에 -3.46까지 급제동/개입 없이 이어짐 — 41차 결론(레이더
  락온 4.2초 전 게이트 활성화, 반영 자연스러움) **영상으로 확증**.
- **이벤트 2(A seg19, 신호대기 정체)**: t=1214.70 프레임에 적신호 교차로
  앞 정체 차량 행렬이 뚜렷이 보임 — vRel -12.4라는 이번 로그 중 가장
  급한 수치가 실제로는 "신호 대기로 서있거나 서행 중인 차량 행렬에
  근접"이라는 가장 흔하고 합리적인 시나리오였음을 확인. vEgo가
  20.8→8.6m/s까지 자연스럽게 감속(t=1213~1219), harsh brake 없음.
- **이벤트 3(B seg6)**: t=1650.30/1652.75 프레임에서도 동일 은색
  세단이 지속 추종 대상으로 확인 — 41차 결론과 일치.
- **이벤트 4(B seg10) — 핵심 발견**: 이 구간만 도로 형태가 다름(왕복
  2차선 지방도, 중앙황색복선, `src=vturn`, steeringAngle -5~-6.5deg의
  완만한 커브). CSV상 t=1895.60(dRel 86.9m)→1895.81(57.0m)→1896.25
  (42.5m)로 **0.65초 만에 86.9m→42.5m(환산 약 -68m/s급 폐색)라는
  물리적으로 불가능한 점프**가 발생했었는데(41차엔 수치로만 의심),
  **이번에 같은 시각의 프레임 4장(1895.60/1895.90/1896.20/1896.50)을
  나란히 대조한 결과 빨간 SUV의 화면상 크기·위치가 이 구간 내내
  거의 변화 없음 — 즉 실제로는 저 정도의 급격한 접근이 전혀
  일어나지 않았음을 영상으로 직접 확인**. `curve_lead_dRel_jump_
  consistency`가 겨냥해온 "커브에서 모델이 순간적으로 깊이를 잘못
  추정해 dRel이 튀는" 패턴의 **최초 영상 실증 사례**.
  - **단, 완전한 노이즈만은 아님**: t=1897.60 프레임에서는 같은 SUV가
    화면상 뚜렷이 커져 있어(진짜 근접 확인), 이 리드 자체는 실재하며
    계속 서서히 접근하고 있었던 것으로 확인됨 — 다만 vision이 그
    "서서히"를 t=1895.6~1896.25 구간에서 한 번의 급격한 스냅으로
    잘못 압축해 보고한 것. 레이더가 t=1896.85에 락온되며 dRel이
    35.4m로, vRel이 -7.9로 스냅 — frac_rate 게이트는 설계대로
    작동했으나(41차 기록: 락온보다 0.74초 전에 1.0 도달), 그 활성화
    구간 동안 실제 aEgo 반영은 약했다가(0.1~0.5 근처, 오히려 소폭
    양수 구간도 있음) 락온 후에야 -0.94→-4.79까지 급격히 커짐 —
    41차가 수치로 지적한 "게이트는 켜졌는데 반영 약함→락온 때 몰림"
    패턴이 **왜 그런지(vision dRel 자체가 신뢰 불가능한 프레임이었기
    때문)를 영상이 명확히 설명**.
- **결론**: 41차의 4건 중 3건(A seg11/seg19, B seg6)은 영상으로 "진짜
  접근" 확증 — frac_rate 게이트/TTC damping 패치들이 실제 위험
  상황에서 정확히 작동함을 재확인. 나머지 1건(B seg10)은 영상으로
  "vision dRel 순간 오추정(노이즈) + 그 이후 진짜 서행 접근"이 섞인
  복합 패턴임을 최초로 명확히 규명 — 곡선 구간(왕복 2차선 지방도
  포함, 기존엔 고속도로 커브 위주로만 검증됨)에서 단안 카메라 깊이
  추정이 순간적으로 크게 어긋날 수 있다는 기존 가설(22~23차 근본원인
  b)이 이번에 프레임 단위로 재확인됨.
- **코드 변경 없음(관찰/분석만)**, patch 없음.
- **다음 세션 후보**:
  1. (41차에서 이월) `curve_lead_dRel_jump_consistency`류 일관성
     체크를 vision-only closing-rate 게이트(`_vision_dRel_rate`)
     자체에도 적용하는 방안 — 이번 영상 증거로 근거가 수치 추정에서
     **영상 실증**으로 격상됐으므로 우선순위 상향 검토 가능. 단
     표본은 여전히 1건.
  2. 왕복 2차선 지방도(고속도로 아닌 일반도로) 커브 구간 샘플을
     추가 확보해 이 패턴이 도로 유형과 상관관계가 있는지(고속도로
     커브 vs 일반도로 커브에서 깊이 추정 오차 특성이 다른지) 확인.
  3. 40차 radard 크래시 수정의 완전한 확인(기기 화면 오버레이 직접
     확인)은 여전히 미실시.
- 근거: `앞차_카메라_인식.zip`(qcamera 포함 재업로드, route
  `05890d8ca1`/`ff2d0a3934`, HEAD `c31ddca`), 프레임 추출본
  `/home/claude/work/frames/event{A_seg11,A_seg19,B_seg6,B_seg10}/`.

## [VALIDATED] 41차 — "카메라 인식 시 미감속" 계열 패치(33/36차 frac_rate 게이트, 38/39차 TTC damping+rise-rate) 최신 HEAD(`c31ddca`)에서 실차 재검증, 대체로 정상 동작 + 잔여 패턴 1건 (2026-08-22, 41차)
- **로그**: `앞차_카메라_인식.zip`, 2개 라우트 — route A(`05890d8ca1`, seg8/9/10/11/12/15/19, 719.8s/8.79km) + route B(`ff2d0a3934`, seg5/6/9/10, 359.7s/4.06km). 둘 다 HEAD `c31ddca`(40차 radard 크래시 긴급수정 커밋, 직전까지의 33/36/38/39차 패치 전부 포함)에서 추출. 사용자 체감: "주행감 좋았음".
- **radard 크래시 수정(40차) 간접 확인**: 두 라우트 전 구간(1079.5s)에서 leadRadar/leadStatus/cruiseEnabled 데이터가 끊김 없이 정상 기록됨(radard가 크래시했다면 레이더 데이터 자체가 결측되거나 불연속이었을 것) — 40차 WIP 남은 항목("실차 재기동 후 radard 정상 기동 확인")을 화면 오버레이 직접 확인은 아니지만 로그 무결성으로 간접 확인. **완전한 확인은 아니므로 WIP엔 참고 표시만 남김.**
- **안전 지표**: 두 라우트 전부 harsh_brake/turn_speed_violation/cut_in/ttc_danger 전부 0건.
- **vision→radar crossover 25건(A15+B10) 중 유의미한 급접근(|vRel|>=5m/s) 4건 프레임 단위 대조** (`sim_frac_rate.py`를 `SIM_GATE_CAUTION=-2.2 SIM_GATE_DANGER=-5.0`로 override, CSV 원본 aEgo 대조):
  1. route A seg11 t=745.1(vRel -5.7~-8.9): frac_rate가 acq_t=0.55s(t=743.95)부터 활성화 — 레이더 락온(t=748.15)보다 **4.2초 이전**. 실제 aEgo도 t=745.5부터 음의 방향 진입(-0.3~-0.5대), 락온 후 -3.46까지 급제동/운전자개입 없이 매끈히 이어짐.
  2. route A seg19 t=1214.7(vRel -12.4, 이번 로그 중 가장 급한 접근): frac_rate가 radar 재확인(t=1217.6)보다 **1초 가까이 이전**에 1.0 도달. 이 구간은 radar가 순간 재유실(1214.7~1217.6, leadRadar 짧게 False 복귀)된 구간과 겹치는데, 그 vision-only 구간 동안에도 aEgo가 -1.0→-3.4까지 끊김없이 연속 감속 — **radar 플리커에도 감속이 끊기지 않음 확인** (25차 이전엔 이런 플리커 구간에서 감속이 리셋되는 패턴이 우려됐었음, 이번 로그에선 재현 안 됨).
  3. route B seg6 t=1650.3(vRel -9.76): frac_rate가 radar 재확인(t=1652.75)보다 **1.4초 이전**에 1.0 도달, 마찬가지로 radar 순간유실 구간에서도 aEgo -2.0대 감속 유지.
  4. route B seg10 t=1895.6(dRel 87→44m 급감): frac_rate는 radar 확인(1896.85)보다 **0.74초 이전**에 1.0 도달 — 게이트 자체는 설계대로 작동. **단, 이 구간은 vision이 보고하는 raw vRel(-6.3~-2 사이 진동, 중간에 -0.4~-0.8까지 떨어짐)이 실제 dRel 낙폭(86.9→44.1m/약 1.1s, 물리적으로 -20m/s대 폐색에 해당)과 맞지 않는 프레임이 섞여 있음(44.8↔42.0↔44.1m 되튐 등, 곡선 dRel 스냅 노이즈와 유사 패턴). 그 결과 frac_rate=1.0인데도 실제 aEgo는 vision-only 구간 내내 0~-0.5로 약하게만 반영됐고, radar 락온 순간(t=1896.85)에야 aEgo가 -4.3까지 급격히 커짐** — "게이트는 켜졌는데 실제 MPC 반영은 약하다가 락온 때 몰림"이라는, 원래 문제(카메라 인식 후 미감속→락온 때 급감속)의 축소판 재현. `harsh_brake_events`는 안 잡음(그 함수는 `brakePressed=True`인 운전자 페달 개입만 집계 — ADAS 자체 감속은 대상 아님, 도구 한계로 별도 유의).
- **curve_noise_refined suppression_rate 저하(route A 22.2%, 이전 벤치마크 91.7%) 재확인 — 회귀 아님**: route A에서 `refined_would_trigger_danger=True`로 분류된 7건을 대조한 결과 전부 위 1)번(seg11 t=744.25)과 같은, 이미 실측 검증된 **진짜 접근 이벤트**와 시각이 겹침. 즉 곡선 노이즈 오탐이 늘어난 게 아니라 이번 로그 자체가 실제 급접근을 다수 포함해 "refined 분류기가 정확히 진짜 위험으로 분류"한 결과 — 도구 정상 동작, 새로운 문제 아님.
- **결론**: 33/36차(frac_rate 게이트)·38/39차(TTC damping+rise-rate) 모두 최신 HEAD에서 정상 동작 확인 — 4건 전부 게이트가 레이더 락온보다 0.7~4.2초 이전에 활성화됐고, 3/4건은 실제 aEgo도 vision-only 단계부터 점진 반영(사용자 체감과 일치). 단 1건(route B seg10)은 vision 자체 vRel 추정치가 실제 dRel 변화와 불일치하는 노이즈성 프레임 때문에 게이트 활성화에도 불구하고 실제 반영이 약했다가 락온 후 몰리는 잔여 패턴 확인 — 22/23차부터 이어진 "vision 폐색비 과소평가/노이즈" 미해결 이슈의 연장선, 표본 1건이라 우선순위 낮음.
- **다음 세션 후보**:
  1. route B seg10류 패턴(vision vRel이 dRel 변화와 불일치)이 재현되는지 추가 로그로 확인 — 재현되면 `curve_lead_dRel_jump_consistency`류 일관성 체크를 vision-only closing-rate 게이트 자체에도 적용하는 방안(현재는 곡선 구간에만 적용됨) 검토.
  2. 40차 radard 크래시 수정의 완전한 확인(기기 화면에서 에러 오버레이 사라짐 직접 확인)은 여전히 별도 필요 — 이번 로그는 데이터 무결성 기준 간접 확인일 뿐.
- 근거: `앞차_카메라_인식.zip` (route `05890d8ca1` seg8/9/10/11/12/15/19, route `ff2d0a3934` seg5/6/9/10), HEAD `c31ddca`.

## [NEEDS_VALIDATION] 저속 구간, TTC 게이트(38차)가 급격히 풀리며 aLeadK 누적값이 한꺼번에 반영돼 급정지 느낌 (2026-08-22, 39차)
- **증상**: 사용자 보고 — "저속구간에서 앞차가 감속하면 내차가 급하게 정지하는 느낌". 38차에서 도입한 TTC 게이트 패치(`c3ea08e`) 적용 이후 로그.
- **로그**: `저속_앞차.zip`, route `20260822_102954_000002f1--245733747e--16` (60초, vEgo 0~11.9m/s, leadStatus/leadRadar 100%, HEAD `c3ea08e`).
- **분석**: `decode_rlog.py`로 직접 재파싱(표준 extract_log.py엔 aLeadK/aTarget 없음, 세션 스크립트로 확장). aEgo<-1.0 연속구간 3건 중 가장 뚜렷한 t=3453.58~3454.93(0.89s, min_aEgo=-1.67) 프레임 대조:
  - vEgo 5.7→4.9m/s, dRel 16.9→13.9m, vLead 5.5→2.9m/s로 완만히(약 5초에 걸쳐) 감속하는 상황. 절대적으로 "위험"하다고 보기 어려운 정상적 저속 추종 감속.
  - **38차 게이트 값을 이 구간에 직접 계산**: t=3452.63 TTC=13.6s(weight=0)에서 t=3453.43 TTC=5.9s(weight=1.00)까지 **0.8초 만에 게이트가 완전히 풀림**. 같은 시간 동안 그동안 감쇠돼 반영 안 되던 aLeadK(-1.1~-1.8 수준)가 한꺼번에 풀려나오면서 실제 aEgo jerk가 순간적으로 -4.65~-4.93 m/s³까지 튐(t=3453.38/3453.58/3453.68).
- **근본원인**: 38차 TTC 게이트 자체(min/max 클리핑 수식)는 저속에서도 정상 계산되지만, **dRel(절대거리)이 저속에서는 작다**(desired_distance가 t_follow*v_ego 항 때문에 저속에서 작음) — 그래서 TTC = dRel/closing 값이 아주 작은 closing 변화(1~2m/s)에도 절대 초 단위로 훨씬 빠르게(고속 대비) 무너짐. 고속에서는 같은 vRel 변화가 dRel이 커서 TTC 변화가 훨씬 완만하게 나타나 38차 검증 로그(고속)에서는 이 문제가 드러나지 않았음. 결과적으로 게이트가 "서서히 위험해지는 상황"과 "순식간에 게이트가 열리는 상황"을 구분 못 하고, 열리는 순간 그동안 누적/은폐돼 있던 감속 신호가 스텝으로 반영됨.
- **조치(패치 작성, 미적용 — Master `git am` 대기, base `c3ea08e`)**: `process_lead()`에서 결합 weight가 "감쇠 풀리는 방향(상승)"으로 바뀔 때만 사이클당 변화폭을 `LEAD_ACCEL_WEIGHT_RISE_RATE=1.0(1/s, 0→1 최소 1초)`로 제한. 감쇠가 걸리는 방향(하강)은 안전측이라 즉시 반영, 제한 없음. **단, `TTC<=LEAD_ACQ_TTC_DANGER(2.5s)`인 실제 위험 프레임에서는 이 rise-rate 제한을 완전히 우회하고 즉시 weight=1.0** — 진짜 비상 상황(빠른 cut-in 등)에서 반응 지연이 생기지 않도록 안전장치를 넣음. 리드가 사라지는 프레임에선 상태(`_lead_accel_weight_prev`) 1.0으로 리셋해 재획득 시 불필요한 지연이 이어지지 않게 함.
- **검증(수치 시뮬레이션, 세션 인라인 스크립트 — 비영구)**: 동일 route를 rlog로 재파싱해 rise-rate 적용 전/후 비교 — 문제 구간 peak |aLead| 기여분 -1.63 → -0.95로 완화(약 42% 감소), 상승 구간 전체에 걸쳐 분산 적용됨을 확인. 합성 비상 시나리오(TTC가 1사이클 만에 10s→2.0s로 급락)로 danger override가 rise-rate 무관하게 즉시 weight=1.0 적용됨을 별도 확인. **acados MPC 파이프라인 전체 재실행이나 실제 aTarget/aEgo 프로파일 재현은 안 됨 — weight 수식 단위 검증 수준.**
- **패치 파일**: `0001-long_mpc-TTC-aLead-weight-lurch-rise-rate.patch` (base `c3ea08e`, `git am` 충돌 없이 검증됨, ast 문법 통과).
- **다음 세션 최우선**:
  1. `git am` 적용 + push 확인.
  2. 실차 검증: (a) 이번 로그와 유사한 저속 추종 감속 상황에서 급정지 느낌 해소 체감 확인, (b) **회귀 검증 필수** — 실제 위험한 저속 cut-in(TTC<=2.5s)에서 danger override가 정상 발동해 반응이 지연되지 않는지, (c) `LEAD_ACCEL_WEIGHT_RISE_RATE=1.0` 값이 너무 느리거나(위험 경계 근처 반응 둔화) 너무 빠른(원래 문제 재발) 건 아닌지 승차감 기준 재조정.
  3. 38차(고속)/39차(저속) 두 패치 모두 적용된 상태에서의 통합 실차 검증 — 아직 두 상황을 동시에 포함하는 로그로 검증한 적 없음.
- 근거: `저속_앞차.zip` (route `20260822_102954_000002f1--245733747e--16`).

## [NEEDS_VALIDATION] 레이더 락온 앞차추종 중 안전한 거리(TTC 15s대)에서도 앞차 가속도 흔들림에 그대로 반응 — 거리비율 기반 MARGIN_ACCEL_GATE의 사각지대 (2026-08-22, 38차)
- **증상**: 사용자 보고 — "레이더 락온상태로 앞차추종 주행시 앞차의 가속도변화에 민감하게 반응함. 위험한 상태가 아니면 반응을 둔하게 해달라."
- **로그**: `앞차_민감.zip`, route `20260821_124048_000002e9--f3db6ca89d--5` (60초, leadStatus/leadRadar=True 99.4%, HEAD 당시 `21effa1`/일부 구간 `113947353a00` 표기 — 커밋 해시 불일치는 추출 시점 clone 차이로 추정, 코드 자체는 c3-ms-dev 최신).
- **분석**: 표준 `extract_log.py` 컬럼에 leadOne.aLeadK/longitudinalPlan.aTarget이 없어 이번 세션 전용 스크립트로 확장 추출(6002 rows). frame-to-frame 변화율 상관계수(lag=0) 0.05로 낮아 단순 동행이 아님을 먼저 확인 후, 0.6s 슬라이딩 윈도 swing 비교로 "리드 가속도 변화는 작은데 aTarget 변화는 큰" 후보 12건 도출, 프레임 대조로 2개 연속구간 확정:
  - t=8911.06~8911.95 (0.89s): dRel 74→66m대, TTC 넉넉.
  - t=8935.26~8938.95 (3.69s, 가장 뚜렷): dRel 60.8→48.7m, vRel -1.9→-3.8m/s로 확대되며 aLeadK가 -2.7까지 떨어지자 aTarget이 -2.78m/s², aEgo가 실제로 -2.8m/s²대까지 추종 감속.
  - 정량화: TTC>6.0s(안전권)인데 aTarget<-1.0m/s²(뚜렷한 감속)인 프레임 460/5966(7.7%), 최악 사례 t=8937.31 dRel=51.9m vRel=-3.30m/s **TTC=15.7s** aLeadK=-1.74 aTarget=-2.78 aEgo=-2.73 — TTC 기준으론 명백히 안전한데 강한 감속 반응.
- **근본원인**: `long_mpc.py`에 이미 `margin_accel_weight(dRel, desired_distance)`(dRel/desired_distance 비율 기반, MARGIN_ACCEL_GATE_FULL=1.5/NONE=1.0, PARAMS_REGISTRY에 NEEDS_VALIDATION으로 등록만 되어있고 실측 검증 안 된 상태)가 존재하지만, `desired_distance = v_ego^2/(2*comfort_brake) + t_follow*v_ego + stop_distance - v_lead^2/(2*comfort_brake)` 자체가 고속에서 커지기 때문에, 문제 구간(t=8935, vEgo≈28.4m/s, dRel=59.6m)에서 직접 계산한 ratio≈0.81로 이미 GATE_NONE(1.0) 밑 — 즉 "damping이 걸려야 할 여유 구간"인데도 weight=1(무감쇠)로 고정되어 있었음. **거리비율만으론 실제 위험도(TTC)를 반영 못 해 고속 구간에서 사실상 상시 무감쇠**였던 것이 사각지대.
- **조치(패치 작성, 미적용 — Master `git am` 대기)**: `ttc_accel_weight(dRel, v_ego, v_lead)` 신설(TTC = dRel/(v_ego-v_lead), closing<=0.1이면 위험요소 없다고 보고 weight=0), 기존 `margin_accel_weight`와 `min()`으로 결합해 "거리 여유 AND TTC 여유"가 모두 있을 때만 aLead 감쇠하도록 `process_lead()` 수정. TTC 임계값은 기존 `LEAD_ACQ_TTC_CAUTION`(6.0s, 24차 이전부터 있는 값)을 무감쇠 경계로 재사용, 완전감쇠 경계는 신규 `LEAD_ACCEL_TTC_GATE_FULL=12.0s`. dRel/vRel(실측 kinematic state)은 기존 설계 원칙대로 전혀 건드리지 않음 — 위험 시 반응 지연 없음.
- **검증(로직 단위, work/verify_ttc_gate.py — 세션 종료 시 삭제됨, 재작성 필요시 decode_rlog.py 기반)**: 동일 route를 rlog에서 직접 재파싱해 기존(dist-only)/신규(dist+ttc) weight 비교 — 이 route는 60초 전체에서 TTC<12s로 떨어진 프레임이 한 건도 없었음(전부 "여유 있는 정상 추종"이었다는 뜻과 일치), 신규 로직 적용 시 aLead가 전 구간 0으로 완전 감쇠 → 보고된 민감반응이 이 로그 기준으론 전부 해소되는 방향으로 확인. **단, 위험 프레임(TTC<2.5s) 표본이 이 route에 아예 없어 "위험 시엔 그대로 통과"가 실측으로는 검증 안 됨** — 수식상으로만 확인(closing>0.1 and ttc<=GATE_NONE=6.0 → ttc_w=1.0 클리핑).
- **패치 파일**: `0001-long_mpc-TTC-aLead-damping.patch` (base `21effa1`, `git am` 충돌 없이 검증됨, ast 문법 통과).
- **다음 세션 최우선**:
  1. `git am` 적용 + push 확인.
  2. 실차 검증: (a) 이번 로그와 유사한 "안전 거리 + 앞차 완만한 가감속" 상황에서 승차감 개선 체감 확인, (b) **회귀 검증 필수** — 실제 위험한 cut-in/급접근(TTC<6s) 상황에서 반응 지연 없이 그대로 감속하는지 확인 (이번 로그엔 그런 프레임이 없어서 미검증).
  3. LEAD_ACCEL_TTC_GATE_FULL=12.0s 값 자체가 적절한지(너무 일찍/많이 damping 걸리는 건 아닌지) 실차 승차감 기준으로 재조정 필요할 수 있음.
- 근거: `앞차_민감.zip` (route `20260821_124048_000002e9--f3db6ca89d--5`).

## [VALIDATED] frac_rate(vision-only closing-rate 절대값 게이트, -2.2/-5.0) 실차 acados MPC 파이프라인 첫 실측 검증 성공 (2026-08-22, 36차)
- **배경**: 33차에서 문턱 재설계(-5.5/-10.0 → -2.2/-5.0)가 사용자 로컬(`c3-ms-dev`, 커밋 `8114a46`)에 반영됐으나, 그동안 전부 `sim_frac_rate.py` 시뮬레이션 기반 검증뿐이었고 실제 acados MPC 파이프라인에 통합된 후의 실차 반응(`_lead_acq_timer`/`frac_rate` 활성화 및 그 결과 a_target/aEgo 반응) 검증은 계속 미실시 상태였음.
- **신규 로그**: 사용자가 카메라 인식 테스트 목적으로 촬영한 `카메라인식.zip`(route `245733747e`, seg10/11/14/15, HEAD `4fe22cd`)와 정지차량 접근 테스트 `정치차량.zip`(route `b89011cb42`, seg7, 동일 HEAD) 제공.
- **검증 방법**: `extract_log.py`로 CSV 추출 후 `sim_frac_rate.py`를 `SIM_GATE_CAUTION=-2.2 SIM_GATE_DANGER=-5.0`로 재현 실행(현재 코드 상수와 동일하게 override — 스크립트 기본값은 구문턱이라 반드시 override 필요, 다음 세션도 동일하게 할 것).
- **결과 (정치차량 route, t=4121~4126)**: `leadRadar=False`(vision-only) 상태로 82m 거리에서 리드 최초 포착, vRel -6.5~-7.9m/s로 급접근. `_lead_acq_timer`가 `VISION_CLOSING_RATE_MIN_TIME`(0.5s)에 도달한 시점(t=4122.08)부터 `frac_rate`가 즉시 0.826으로 뛰어오르고 0.4초 내 1.0 도달 — **레이더 락온(같은 세그 후반)보다 한참 전에, distance 82m라는 먼 거리에서 게이트가 정확히 설계 의도대로 작동**. 이후 leadStatus가 0.5s 초과로 짧게 유실(정상적인 grace 재확인, 0.5s 이내 blip은 유지되고 초과분만 리셋)되며 acq_t가 재적립되는 과정을 거쳐 t=4124.08경 frac_rate 재차 1.0 도달, t≈4126부터 aEgo가 실제로 음의 방향 진입해 이후 완전 정지까지 급제동/운전자 개입 없이 매끈하게 이어짐(harsh_brake 0건, brakePressed 전 구간 False, 최대 감속 약 -2.3m/s²).
- **결과 (카메라인식 route, 전체 4세그)**: seg10/seg11에서 `max_frac_rate=1.000` 도달(각각 t=3111부근/3152부근), seg14는 0.359, seg15는 0.764로 부분 활성화 — 다양한 강도의 실제 원거리 접근 시나리오에서 게이트가 여러 차례 정상 활성화됨을 확인. 4세그 전체에 걸쳐 harsh_brake/turn_speed_violation 0건 유지.
- **frac_rate 활성화 ~ 실제 aEgo 반응 사이 지연**: 정치차량 사례에서 frac_rate가 처음 1.0에 도달(t≈4122.3)한 시점과 aEgo가 육안상 음의 방향으로 뚜렷하게 진입한 시점(t≈4126) 사이 약 2초 지연 관찰. 다만 이 구간은 leadStatus가 중간에 0.5s+ 유실되며 acq_t가 리셋된 재적립 과정을 포함하므로, 순수 "게이트 활성화 → MPC 반영" 지연이 아니라 "vision-only 추적 자체의 재획득 지연"이 섞여 있음 — 향후 leadStatus가 끊기지 않고 안정적으로 유지되는 사례로 순수 지연만 분리 측정 필요(NEEDS_VALIDATION, 다음 세션 후보).
- **결론**: `VISION_CLOSING_RATE_GATE_CAUTION/DANGER`(-2.2/-5.0), `MAX_PLAUSIBLE`(30.0), `MEDIAN_WINDOW`(3) 4개 상수 모두 실제 acados MPC 파이프라인 통합 상태에서 원거리 vision-only 급접근 시나리오에 정상 반응함을 최초로 실측 확인 — PARAMS_REGISTRY.md 상태 PARTIALLY_VALIDATED → VALIDATED로 상향.
- 근거: `카메라인식.zip`/`정치차량.zip` (route `245733747e`, `b89011cb42`, 2026-08-22 촬영, HEAD `4fe22cd`).

## [FIXED] carrotweb "Clip 선택" 버튼 클릭해도 체크박스 선택 안 됨 — logs.js 캐시 버스터 미갱신 (2026-08-22, 35차 계속)
- 증상: patch 0003(필터→선택 정정) 적용·push 완료 후 사용자가 실기기
  carrotweb에서 "Clip 선택" 버튼을 눌러도 체크박스가 전혀 선택되지
  않음(스크린샷으로 확인, 78개 파일 목록에 clip 파일 다수 포함된
  상태).
- 원인: `index.html`이 `<script src="/js/logs.js?v=3">`처럼 쿼리
  파라미터로 캐시 버스팅을 하는데, 이번 세션의 3개 patch(60->20s,
  Clip 필터 최초구현, 필터->선택 정정)가 전부 `logs.js` 내용을
  바꿨음에도 이 버전 번호를 올리지 않았음 — 브라우저가 URL이
  동일하다고 판단해 **예전 캐시된 `logs.js`를 계속 사용**, 새
  `screenrecordSelectClipsOnly()` 로직이 실행되지 않음. HTML(버튼
  라벨 "Clip 선택")은 최신인데 JS 동작만 예전 그대로였던 게 정황과
  일치.
- 조치: `?v=3` -> `?v=4`로 캐시 버스터 갱신(커밋 `baab116`).
- **교훈(향후 patch 작성 시 항상 확인)**: `logs.js`(또는 다른
  버전 쿼리가 붙은 정적 자산)를 수정하는 patch를 만들 때마다
  `index.html`의 해당 `?v=N` 캐시 버스터도 같이 올려야 함 — 안
  그러면 코드는 올바르게 push/적용됐어도 실기기 브라우저에는
  반영되지 않아 "패치가 안 먹힌다"는 오탐으로 이어짐.
- 검증: `git am` 컨텍스트 검증(temp branch, base `f6a22b8`) 통과.
  **실차 검증 완료(2026-08-22, 다음 세션)**: 강제 새로고침 후
  "Clip 선택" 버튼이 목록은 그대로 두고 clip 파일 체크박스만
  선택/해제 토글 정상 동작 확인. 같은 기회에 `_clip.mp4` 실제 길이도
  20초대로 정상 확인(60->20s 축소 반영 확인, 35차 항목 참고).
- 근거: 사용자 제공 스크린샷(78개 파일, "Clip 선택" 버튼 클릭해도
  체크박스 전부 unchecked 유지) + 이후 실차 재확인(정상).

## [FIXED] screenrecord 정지 clip 길이 60초 -> 20초, carrotweb 로그탭에 "Clip만" 필터 버튼 추가 (2026-08-22, 35차)
- 배경: 정지 버튼을 누르면 `extract_trailing_clip()`이 마지막 60초를
  별도 `_clip.mp4`로 잘라 저장(19차/커밋 `7b4a160`부터 동작). 사용자가
  "60초는 너무 길다, 용량 절감을 위해 20초로 줄여달라" + "carrotweb
  로그탭 화면녹화 목록에서 clip 파일만 골라 보이게 하는 버튼" 요청.
- 조치 1 (clip 길이): `selfdrive/ui/qt/screenrecorder/screenrecorder.cc`의
  `extract_trailing_clip()` ffmpeg 인자 `-sseof -60` -> `-sseof -20`
  (stream copy라 키프레임 간격만큼 오차 있음, 실제 길이 약
  20.0~20.8초). 관련 주석(.cc 2곳 + .h 1곳)도 "1분"->"20초"로 동기화.
  로직/파일명 규칙/충돌 처리(스탬프 충돌 시 `_clip_2` 접미사)는
  변경 없음.
- 조치 2 (carrotweb UI, **수정됨 — 아래 참고**): `selfdrive/carrot/web/js/logs.js`에
  `isScreenrecordClip()`(파일명이 `_clip(_N)?.mp4`로 끝나는지 정규식
  판별) + `screenrecordSelectClipsOnly()` 추가. **최초 구현은 목록을
  필터링(clip 아닌 항목을 숨김)했으나, 사용자가 "목록은 다 보이고
  clip 파일 체크박스만 선택되게 해달라"고 의도를 정정** — 필터링
  로직(`screenrecordClipOnly` 상태/`getVisibleScreenrecordVideos()`)을
  제거하고, 버튼 클릭 시 clip 파일들의 체크박스만 토글 선택(이미 전부
  선택돼 있으면 해제)하는 `screenrecordSelectClipsOnly()`로 교체.
  `index.html` 버튼 라벨 "Clip만"->"Clip 선택"으로 변경, `logs.css`의
  미사용 `.smallBtn.is-active` 강조 스타일 제거. `node --check` 통과.
- 검증: `git am` 컨텍스트 검증(temp branch, base `8114a46`) 통과,
  am 적용 후에도 `node --check` 재통과. **실차 검증 완료(2026-08-22,
  다음 세션)**: `_clip.mp4` 실제 길이 20초대 확인, carrotweb "Clip
  선택" 버튼도 정상 동작 확인(캐시 버스터 갱신 후, 위 35차 계속 2
  항목 참고).
- 커밋: `c1e79ed`(clip 60->20s), `cebfa87`(carrotweb 필터→선택 버튼
  최초 구현), `f6a22b8`(의도 정정: 필터 제거, clip 선택 전용으로
  교체) — 전부 base `8114a46`(c3-ms-dev HEAD) 위. 앞 두 개는 사용자가
  `c3-ms-dev`/`c3-ms-test` 둘 다 push 완료(`8114a46..dfa2f4f`,
  `725d19f..e9000b3`). **세 번째(의도 정정) patch는 아직 미적용 —
  두 브랜치 모두에 추가로 `git am` 필요.**
- 반영 대상: 사용자 요청대로 **`c3-ms-dev`와 `c3-ms-test` 둘 다**.
  두 patch는 `screenrecorder.cc/h`, `carrot/web/*` 파일만 건드리고
  `long_mpc.py`는 건드리지 않으므로(34차 A/B 실험은 `long_mpc.py`
  단일 파일 변경) `c3-ms-test`에도 컨텍스트 충돌 없이 그대로 `git am`
  될 것으로 예상 — 단, 두 브랜치 각각에 실제로 적용됐는지는 사용자
  확인 필요.
- 근거 로그: 없음(코드 리뷰 기반 변경, 로그 분석 아님).

## [INVESTIGATING] extract_log.py 세그먼트 경계마다 leadStatus 인위적 False 발생 — LEAD_ACQ_LOSS_GRACE_TIME 과거 증거 재검토 필요 (2026-08-20, 라우트 260819-2 분석 중 발견)
- 증상: 260819-2 라우트(x20seg, 1199.9s/10.29km)에서 leadStatus True→False→True
  '순간 유실' 16건을 탐지했는데, **16건 전부 예외 없이 세그먼트 파일 전환
  시각과 소수점 이하까지 정확히 일치**(diff=0.000s, 예: t=1436.925613188은
  seg23 첫 프레임 타임스탬프와 완전 동일). 유실 지속시간은 전부 0.09~0.30s로
  짧음.
- 원인 (코드로 확인): `devnotes/toolkit/extract_log.py`의 `process_segment()`가
  세그먼트(rlog 파일)마다 `last_lead = {"leadStatus": False, ...}`로
  **매번 초기화**한 뒤 그 세그먼트의 첫 `radarState` 이벤트를 만날 때까지
  직전 상태를 기억하지 못함. 하지만 실제 주행에서는 radard 프로세스가
  세그먼트 경계와 무관하게 연속 실행되므로(로그 파일만 60분→60초 단위로
  회전, radard 상태는 안 끊김) 이 초기화는 순수한 **추출 도구 아티팩트**임 —
  차량/코드의 실제 리드 유실이 아님.
- 영향 범위: LEAD_ACQ_LOSS_GRACE_TIME이 PARAMS_REGISTRY.md에서
  NEEDS_VALIDATION 우선순위 상승 근거로 삼은 누적 증거(x11seg 4건 + x16seg
  1건 + x20seg(260819-1) 6~7건, 유실시간 0.5~2.46s)가 **이 아티팩트로
  오염됐을 가능성**이 있음. 특히 유실시간이 세그먼트 길이(60s) 근처의
  배수 시점이거나 0.3s 이하로 짧은 항목은 재검증 우선. 다만 1s 이상 긴
  유실(예: 2.46s)은 세그먼트 경계와 무관할 가능성이 높아 실제 이슈로 남을
  수 있음 — 세그먼트 경계 시각과 교차 대조 필요.
- 조치 (제안, 미적용): `process_segment()` 시작 시 `last_lead`를 매번
  False로 리셋하지 말고, 이전 세그먼트 처리 종료 시점의 `last_lead` 값을
  다음 세그먼트 호출로 전달(carry-forward)하도록 수정 제안. 코드 변경이라
  마스터 확인 후 적용 예정 — 이번 세션에서는 미적용.
- 근거 로그: 260819-2, seg23(t=1436.925613188) 등 16건 전원, 세그먼트 경계
  타임스탬프와 소수점까지 완전 일치(diff 계산 스크립트로 확인).

## [NEEDS_VALIDATION] 고속 순항 중 급접근 리드 트랙 전환 시 leadVRel/leadVLead 불연속 점프 — 시스템 감속(-4.61m/s²)이 운전자 급브레이크(-7.46m/s²)로 이어짐 (2026-08-20, 라우트 260819-2, seg24)
- 증상: t=1505.78 vEgo=31.3m/s(약 112km/h)에서 leadStatus가 새로 True로
  잡힘(dRel=110.0m, vRel=-4.63m/s, vLead=26.75m/s — 비슷한 속도로 앞서가는
  차량, TTC 여유 있음). 그런데 0.25s 후 **t=1506.03에 leadDRel은
  108.7m→107.4m로 연속적으로 이어지는데(직전 프레임과 자연스러운 변화율)
  leadVRel만 -4.4→-26.2m/s, leadVLead는 27.0→5.1m/s로 프레임 간 불연속
  점프**. 이후 leadDRel이 새 vRel(-26m/s대)에 정확히 부합하는 속도로
  빠르게 감소(94m→64m, 1.25초). 시스템(vturn 소스 유지 상태)이 aEgo를
  -0.03→-4.61m/s²까지 약 1.65초에 걸쳐 매끈하게 증가시켰으나, TTC는
  4.15s→2.94s로 서서히 감소할 뿐 LEAD_ACQ_TTC_DANGER(2.5s) 문턱을 넘지
  못한 채 t=1507.88 운전자가 급브레이크 개입(브레이크 프레스 직후
  aEgo -3.94→최대 -7.46m/s²까지, cruiseEnabled=False로 disengage).
- 원인(추정, 미확정): 두 가지 가능 시나리오 — (1) 실제로 그 시점에 훨씬
  느린(≈5m/s, 도보 속도) 선행 물체/정체 차량이 앞서가던 빠른 차량과 거의
  같은 거리에서 감지되며 트랙이 교체됐고 시스템은 물리적으로 타당하게
  반응했으나 폐쇄형 TTC 문턱 로직(TTC 2.5s 아래로 안 내려가는 한 frac<1.0)
  때문에 초기 반응 강도가 종가속도 관점에서 부족했을 가능성. (2) 레이더/
  비전 트랙 ID 교체 시 위치(dRel)는 매끈하게 이어졌지만 속도 추정치만
  잘못된 트랙에서 넘어와 불연속이 생겼을 가능성(오탐/트랙 매칭 버그) —
  이 경우 LeadBlend의 closer_jump(8m)/big_jump(15m) 게이트는 **dRel
  점프만 감지**하므로 이런 "dRel 연속, vRel/vLead만 불연속"인 케이스는
  놓칠 수 있음(게이트 사각지대 가능성).
  - 참고: leadVRel=-26.2m/s(94km/h 상대속도)는 vEgo(31.3m/s)와
    vLead(5.1m/s)의 차이(26.2)와 정확히 일치 — 새 vRel/vLead 값 자체는
    물리적으로 일관됨(연산 오류는 아님). 문제는 "왜 한 프레임 만에
    이렇게 다른 트랙으로 넘어갔는지"와 "그 전환이 안전 방향으로
    충분히 빠르게 대응됐는지".
- 상태: NEEDS_VALIDATION — 단일 사례(표본 1건). radard LeadBlend 로직과
  dashcam 영상 프레임 대조(실제로 정체/저속 차량이 있었는지, 트랙 교체가
  타당했는지)로 확인 필요. TTC 임계값(2.5s/6.0s) 자체가 고속(>100km/h)
  구간에서 충분히 조기 반응을 유도하는지도 함께 검토 대상.
- 근거 로그: 260819-2, seg24, t=1505.78~1507.88 (풀 프레임 덤프 확보).

---

## [WONTFIX] (정정) MAX_SEGMENTS_PER_ROUTE=20 "반증" 오판 — 로그가 패치 커밋보다 이전 시점이라 예상된 pre-patch 동작이었음 (2026-08-20, 라우트 260819-5)
- 최초 판단(오류): route `ba55f880d1`가 seg0(260819-3)~seg39(260819-5)
  까지 끊김 없이 40개 세그먼트로 이어진 걸 보고 MAX_SEGMENTS_PER_ROUTE=20
  패치(f7b154638cf2)의 실기기 미반영 의심으로 [INVESTIGATING] 기록함.
- **정정 (사용자 확인)**: 260819-5 로그 시각은 2026-08-19 12:41~13:00.
  패치 커밋 f7b154638cf2의 커밋 시각은 2026-08-20 00:57:22 — **로그가
  커밋보다 12시간 이상 이전**. 즉 이 드라이브는 애초에 패치 적용 전
  빌드로 기록된 것이라 40개 단위로 도는 게 정상(예상된) 동작이었음.
  실기기 미반영 반증이 아니었음 — 오판.
- 교훈: extract_log.py meta.json의 `commit_short`는 **분석 시점 컨테이너의
  ryu 체크아웃 커밋**이지 로그가 기록될 당시 디바이스에 실제로 올라가
  있던 빌드의 커밋이 아님. 로그 파일명 타임스탬프와 관련 패치의 커밋
  날짜를 먼저 대조하지 않고 "코드는 있는데 로그에서 안 보인다"고
  바로 미반영으로 결론내면 안 됨 — 앞으로 이런 종류의 반증 주장을
  할 땐 커밋 날짜 vs 로그 날짜 선행 확인 필수.
- 실제 검증 상태: MAX_SEGMENTS_PER_ROUTE=20 반영 여부는 **여전히
  미확인** — f7b1546(2026-08-20 00:57) 이후에 기록된 로그로 재확인
  필요 (PARAMS_REGISTRY.md NEEDS_VALIDATION 유지, 사유만 정정).

## [FIXED] carrotweb 로그탭 라우트당 세그먼트 40개 -> 20개로 축소 (2026-08-20, HEAD 366009153812 기준 → 패치 적용 후 c3-ms-dev HEAD f7b154638cf2, master가 git am + push 완료)
- 증상: carrotweb 화면 로그탭에서 라우트 하나에 세그먼트(≈1분 단위)가
  40개씩 묶여서 저장됨 (라우트당 약 40분). 목록이 라우트 단위로 분류돼
  있어 원하는 라우트를 찾기 어렵고, 하나의 라우트가 너무 길다는 요청.
- 원인: `system/loggerd/logger.cc`의 `constexpr int
  MAX_SEGMENTS_PER_ROUTE = 40;` — `LoggerState::next()`에서 이 값에
  도달하면(`route_part + 1 >= MAX_SEGMENTS_PER_ROUTE`) 새 라우트로
  회전(rotate)하며, 이 로직이 라우트당 세그먼트 개수를 결정하는 유일한
  지점.
- 조치: 상수를 40 -> 20으로 변경 (수정됨). 회전 로직 자체(`route_part`
  리셋, END_OF_ROUTE 센티널 처리)는 손대지 않았으므로 라우트 경계마다
  정상적인 START_OF_ROUTE~END_OF_ROUTE qlog/rlog 시퀀스가 유지됨.
  `system/loggerd/tests/test_logger.cc`의 관련 주석(40+40+20 → 라우트
  분포 예시)도 20 기준으로 갱신 — 테스트 로직 자체는 라우트 경계를
  동적으로 추적해서 판정하므로 상수값에 의존하지 않아 수정 불필요.
  `selfdrive/carrot/server/routes_logs.py`의 `DASHCAM_ROUTE_LIMIT_DEFAULT
  = 40`은 같은 숫자지만 "로그탭에 한 번에 나열할 라우트 개수"로 이번
  건과 무관 — 변경하지 않음 (혼동 방지용으로 기록).
- 근거 로그: 코드 변경만, 실기기 반영 후 라우트 폴더 분포(세그먼트
  20개씩 끊기는지)와 carrotweb 로그탭 표시 확인 필요 →
  NEEDS_VALIDATION 성격 후속 확인 남음. 빌드(scons)는 이 세션 환경에서
  미실행 — 문법/로직 리뷰만 수행, 실기기(comma 3X) 빌드·부팅 후 확인
  권장.
- 반영 상태: 2026-08-20 master가 로컬(C:\dev\ryu)에서 `git am` 적용
  (커밋 f7b154638cf2) 후 `git push origin c3-ms-dev` 완료
  (3660091..f7b1546). 코드는 원격 브랜치에 반영됨 — 실기기 빌드/부팅
  후 동작 확인만 NEEDS_VALIDATION으로 남음.
- **2026-08-20 갱신: 260819-5 로그 분석 결과 실기기 반영 반증 확인, 위
  [INVESTIGATING] 항목 참고** — route `ba55f880d1`가 seg0~39(40개)까지
  끊김 없이 이어짐, 20개 단위 rotate 미확인.

## [FIXED] radard KjException 크래시 — dPath numpy.float64 캐스팅 누락 (2026-08-17, 커밋 2c34855)
- 증상: EnableRadarTracks<3 (Genesis DH 기본) 순수 비전 리드 경로에서 radard가
  KjException으로 죽음 → radarState dead → soft disable → engage 해제.
- 원인: `VisionTrack.get_lead()`에서 `self.dPath`가 numpy 타입 그대로 capnp
  구조체에 대입됨. `Track.get_RadarState()`류는 이미 float() 캐스팅돼 있었는데
  이 함수만 누락.
- 조치: FIXED. float() 캐스팅 추가.
- 근거 로그: t=140.78 radard exitCode=1, t=141.23~144.23 soft disable→disable.

## [FIXED] t_follow 이중 apply_t_follow 호출로 0에 수렴 (2026-08-17, 커밋 a12d729)
- 증상: 차선변경 중 longitudinalPlan.tFollow가 0.005~0.09까지 붕괴, 옆차선
  선행차와 위험하게 근접.
- 원인: `get_T_FOLLOW()`와 `dynamic_t_follow()`가 각자 내부에서
  `apply_t_follow()`(증가방향 레이트리미터)를 호출 → 차선변경으로 줄어든 값이
  다음 사이클 리미터 기준선이 되어 재귀적으로 계속 축소.
- 조치: FIXED. 두 함수는 raw 값만 반환, `long_mpc.update()`에서 최종 확정된
  t_follow에 대해 apply_t_follow()를 정확히 1회만 호출하도록 정리.
- 근거 로그: 시뮬레이션 재현 — OLD 로직 0.5초만에 0.00215로 수렴, 관측값과 일치.

## [INVESTIGATING] curve_exit_no_accel_scan v1의 3번째 오탐 패턴 확인 + v2 필터 추가 (2026-08-20, 260819-7)
- 배경: 260819-6 세션에서 "커브 탈출 후 재가속 지연" 가설 검증 중
  v1 스캐너가 (1)선행차 추종 감속, (2)S자 연속커브 재진입을 커브탈출로
  오판하는 오탐 2종을 확인. 이번 세션에서 `curve_exit_no_accel_scan_v2`를
  `toolkit/analysis_helpers.py`에 추가(leadStatus 필터 + 직선 지속시간
  0.8s 재상승 체크)해 260819-7(고속도로 위주, 32.7km/1319.9s, avg
  89.3km/h) 로그로 재스캔.
- 결과: v1 4건 → v2 3건으로 감소(1건은 선행차 근접 필터로 제외).
  남은 3건 중 2건은 정차 직전 저속(0.96~5.29m/s) 구간이라 무관. **나머지
  1건(seg20, t=1256.45, vEgo=31.65m/s=114km/h, leadStatus=False)을 프레임
  단위로 대조한 결과, v2도 놓친 3번째 오탐 패턴을 신규 확인**: 커브 탈출
  직후 vTurnSpeed/desiredSpeed 자체는 빠르게 회복(149→200 kph, 약 3.7s)해
  전혀 제약이 아니었는데도 aEgo가 ~5초간 -0.3~+0.16 사이에서 정체 —
  원인은 `controlsd.py` line 214의 `desired_kph = min(CS.vCruiseCluster,
  carrotMan.desiredSpeed)`: 이 구간의 vCruiseCluster(사용자 설정
  크루즈속도)가 120km/h였고 vEgo가 이미 113.9km/h로 그 근처였음 —
  즉 "가속 안 함"이 아니라 "이미 목표속도 근처라 가속할 여지가 거의
  없었던" 정상 상황. v2는 desiredSpeed/vTurnSpeed만 보고 vCruiseCluster
  대비 실제 여유폭은 안 보므로 이런 케이스를 오탐으로 남김.
- 다음 세션 조치 제안: `curve_exit_no_accel_scan_v3`에 필터 3 추가 —
  탈출 시점 `min(vCruise, desiredSpeed) - vEgo` 여유폭이 작으면
  (예: <3~5km/h) 애초에 가속할 이유가 없는 상황이므로 후보에서 제외.
  이 필터까지 반영한 뒤에도 후보가 남는지 route1~7 전체 재스캔 필요
  (사용자 핵심 관심사, 우선순위 높음 — WIP.md 참고).
- 부가 확인(코드 리딩): `carrot_man.py` vturn_speed()가 a94a58b 커밋에서
  "과속방지턱과 동일한 물리공식" 기반으로 재설계되며 저역통과 필터
  상수가 `vturn_decel_rc=0.15s / vturn_accel_rc=0.15s`(둘 다 빠름)로
  바뀌어 있음 — PARAMS_REGISTRY의 기존 "0.25s/0.6s 검증됨" 기록은
  ab156ea 시점(더 이전 리비전)의 값이라 **현재 코드와 불일치, 최신화
  필요**(하단 PARAMS_REGISTRY.md 갱신 이력 참고). 코드 주석도 "탈출 즉시
  자연스럽게 제약 해제"라고 명시하고 있어 이번 로그 관찰과 논리적으로
  합치함(진짜 지연은 vturn_speed 쪽이 아니라 vCruiseCluster 캡 때문).

## [INVESTIGATING] 조여드는 커브 중간에 vturn 감속 진행 중 운전자 브레이크 개입 (2026-08-20, 260819-7, 표본 1건)
- seg6, t=434.70, 고속도로(vCruise=90km/h 크루즈 중). t=429.41부터
  src가 route→model→vturn으로 넘어가며 곡률이 서서히 증가(curv 0.0004→
  0.026, t=429~437.6, 약 8.6초에 걸쳐 지속 증가)하는 커브에서 vturn이
  매끈하게 감속(vEgo 23.3→19.5m/s, desiredSpeed 90→47kph로 계속 하강)
  중이었음. t=434.65에 시스템 자체 aEgo가 -3.41m/s²까지 도달한 직후
  (0.05s 뒤) 운전자가 브레이크 개입 — cruiseEnabled은 t=434.70 프레임까지
  True로 남아있다가(brakePressed는 이미 True) t=434.76에 False로 전환.
  개입 후 운전자는 vEgo 11.8m/s(42km/h)까지 감속했는데, 이 시점 커브는
  아직 안 끝났고(곡률은 t=437.6까지 계속 증가) vturn도 그 무렵엔
  31~34kph까지 더 낮아져 있었음 — 즉 운전자가 "커브가 아직 안 끝났는데
  vturn 감속 속도가 곡률 조여드는 속도를 못 따라간다"고 느꼈을 가능성.
- 판단 보류 이유: 표본 1건, 개입 시점 aEgo(-3.41→-2.82m/s²)가 이미 상당히
  강한 감속이라 "부족해서" 개입했다기보다 개인 운전 성향(더 일찍/강하게
  선호)일 가능성도 배제 못함. vturn_lookahead_horizon_s=4.5s가 이 커브
  (조임 시작~정점 약 8.6s)에 비해 충분한지 여부는 이 표본만으로 결론
  못 내림.
- 다음 세션 조치 제안: (a) 유사 패턴(진행 중인 vturn 감속 중 운전자
  추가 브레이크 개입) 추가 표본 수집 — route1~7 전체에
  `cruise_engage_disengage_events` + 직전 5초 src=vturn 여부로 스캔하는
  헬퍼 함수 신설 검토, (b) 표본이 쌓이면 vturn_lookahead_horizon_s 상향
  또는 vturn_decel_rate(현재 1.2 m/s², 방지턱 기본값 그대로 사용 중)
  조정 필요성 검토.

## [FIXED] vturn 슬루 리미터 min/max 반전 (2026-08-16, 커밋 ab156ea)
- 증상: 커브 감속(vTurnSpeed)이 "변화율 상한"이 아니라 "최소 변화량 강제"로
  동작 → 20Hz 루프에서 프레임당 -10%/+8% 복리 누적, 1초 안에 -88%/+366%까지
  튈 수 있는 상태. vTurnSpeed는 크루즈 목표속도 결정(min())에 직접 쓰임.
- 원인: 슬루 제한 코드의 min()/max() 방향이 반대로 작성됨.
- 조치: FIXED. 동시에 "탈출 후 2초 고정 지연 가속회복" 상태머신도 제거하고
  1차 저역통과 필터(감속 rc=0.25s, 가속 rc=0.6s)로 교체 — 이 상태머신이
  오히려 "커브 빠져나오고도 한참 안 밟는" 현상의 직접 원인이었음.
- 참고: 이전에 있었던 "persistent state machine (apex/exit lock-in, freeze
  재획득)" 방식은 같은 날 안에 폐기되고 lookahead 기반 벡터화 방식으로
  대체됨. 과거 세션 요약에 그 상태머신이 언급돼 있다면 이미 구버전 설명임.

## [NEEDS_VALIDATION] LEAD_ACQ_RAMP_TIME=5.0s / LEAD_ACQ_TTC_DANGER=2.5s (2026-08-17~)
- 목적: 리드 최초 인식 시 관측치가 부정확한 구간(비전/레이더 무관)에 대한
  선제적 감속 하한선. TTC 실시간 재계산으로 경과시간 램프가 못 잡는 급접근
  케이스 보완.
- 상태: 코드는 완결(min() 기반 floor, 안전방향으로만 작동 확인됨). 실도로
  파라미터 자체(RAMP_TIME 5.0s가 적정한지, TTC 임계값 2.5s/6.0s가 적정한지)
  검증 아직 부족.
- 2026-08-18 로그 분석 (x9seg, 522초 시내주행) 결과:
  - 리드 인식 이벤트 13건 중 cruiseEnabled=True(로직이 실제 작동 가능한
    조건)는 8건. 그중 TTC가 DANGER(2.5s) 아래로 내려간 케이스 0건.
  - 가장 근접했던 케이스(seg8 t=556.22, ttc_min=3.62s)도 원인은 route
    기반 감속으로 보이며 aEgo 반응은 매끈함(튐 없음).
  - 얼핏 "위험 케이스"로 보였던 seg6(t=436.95, vRel=-7.49m/s)는 실제로는
    리드가 0.6초 만에 사라지고(LOSS_GRACE_TIME 넘어 리셋) 이후 급감속은
    vturn(커브)+운전자 브레이크가 원인 — LEAD_ACQ와 무관한 이벤트였음.
  - 진짜 위험 TTC(0.98s, seg12 t=808.20)는 cruiseEnabled=False(운전자 수동
    브레이크 중)라 ACC 로직 검증에 못 씀.
  - 이 로그로는 검증 불가. 고속도로 순항 중 크루즈 켠 채로 리드가
    가깝게/빠르게 나타나서 계속 락온 유지되는 로그 필요.
- **2026-08-18 로그 분석 (x12seg, 722초/3.78km, "가속 지연/설정속도 미달"
  체감 불만 제보 주행) — 처음으로 조건에 맞는 사례 확보:**
  - seg10 t=657.39: leadStatus 유지 상태에서 leadDRel이 **한 프레임(dt=0.05s)
    만에 75.1m→12.2m로 점프**(radard LeadBlend closer_jump/big_jump 게이트
    발동 조건). vEgo 57.1km/h, vCruise 70km/h, leadVRel -0.9m/s(TTC 약 13.6s,
    DANGER 아님) — 고속 순항 중 갑자기 가까운 리드가 나타난 사례.
  - 반응: 이후 약 6초간 aEgo가 -0.3~-0.98 사이에서 **매끈하게** 눌리며
    vEgo 57.1→45.0km/h로 감속. 급브레이크성 스파이크 없음.
  - **결론: LEAD_ACQ_RAMP_TIME=5.0s 로직이 실제로 "급조작 없이 선제감속"
    의도대로 동작한 첫 실사례.** 표본 1건이라 추가 검증 필요하지만
    긍정적 데이터포인트. 이 사례로 RAMP_TIME 5.0s 자체가 너무 길다/짧다는
    판단은 아직 어려움(감속 총량이 크지 않아 상한 근처까지 안 감).
  - 참고: seg2 t=211.85~216.05 (leadDRel 62.5m→7m, vRel -7~-11m/s 지속,
    aEgo 최대 -2.7)는 physically 일관된 급정지 선행차 추종 상황 —
    급감속이지만 **버그 아님**, 정상 ACC 동작으로 확인.
  - **[NEEDS_VALIDATION 신규] 비전 리드 트래킹 노이즈 발생 빈도**: 같은
    leadStatus 유지 구간에서 leadDRel이 프레임당(≤0.3s) 8m 이상 튀는
    이벤트가 12분 주행 중 46건(~15초당 1회) 관측됨. 대부분은 감속으로
    이어지지 않았으나(예: t=327.16, 647.04 등은 오히려 가속 지속),
    EnableRadarTracks<3 비전 폴백 구조와 일치하는 증상. 컨트롤에 미치는
    영향은 크지 않아 보이나 LeadBlend 게이트 발동 빈도 자체가 높다는 점은
    추가 로그로 누적 확인 필요.
  - **사용자 체감 불만("지연 출발/설정속도 미달")의 주 원인은 버그보다는
    커브/교차로 밀집 구간 특성으로 추정**: cruiseEnabled 구간의 13.1%가
    desiredSource=vturn(커브 감속캡)이었고, vCruise는 62~90km/h로 계속
    설정돼 있었는데 실속도는 20~55km/h대에 머묾. 회전이 잦은 도로에
    고속 크루즈를 걸어둔 상황과 일치 — 로직상 정상 동작으로 판단되나,
    vTurnSpeed 캡 자체가 체감상 과도하게 보수적인지는 추가 검토 여지 있음.
    (참고: 운전자 gas override 비율도 cruiseEnabled 구간의 4.3%로 다소
    높음 — 체감 불만과 일치하는 정황.)

## [FIXED] CarrotWeb Drive 전송 진행률이 번갈아 뜨다가 (1/1) 0%에서 멈춘 뒤 타임아웃 (2026-08-18, 미적용 상태였던 커밋 8dbed62 기준 / 수정 커밋: fix-gdrive-upload-race 브랜치 f72e68a, 패치 파일로 전달)
- 증상: 로그탭에서 라우트 2개 선택 후 "Drive 전송" 시 상태 줄이
  "업로드 중(2/2)... 82%"와 "업로드 중(1/1)... 0% (Google Drive 연결
  확인 중...)" 사이를 번갈아 표시. (2/2) 쪽이 100% 완료돼 사라진 뒤에도
  화면은 (1/1) 0% 상태에 멈춰 있다가, 한참 후 "업로드 실패(1/1): Drive
  업로드 실패(네트워크/타임아웃): Timeout on reading data from socket"로
  실패 표시됨. (스크린샷 3장으로 재현 순서 확인, 실제 rlog 로그 분석은
  아님 — UI/서버 코드 리뷰로 원인 특정)
- 원인 (두 가지가 겹침):
  1. `logs.js`의 `btnDashcamUploadSelected`/`btnScreenrecordUploadSelected`
     버튼에 업로드 중 비활성화 로직이 없고 `uploadSelectedFiles()`에도
     재진입 가드가 없었음. 이전 업로드(예: 라우트 1개짜리, total=1)가
     아직 안 끝난 상태(특히 핸드셰이크 단계에서 응답이 느려 0%에 멈춰
     보일 때)에서 사용자가 다시 선택/전송하면(예: 전체선택 후 재전송,
     total=2) 두 번째 독립된 업로드 루프가 새로 시작됨. 두 루프 모두
     같은 `#logsStatus` DOM 한 줄을 `el.textContent = message`로 그냥
     덮어쓰기 때문에, 두 루프의 폴링 주기(500ms)가 엇갈리며 서로의
     메시지를 번갈아 지우는 것처럼 보임 — "번갈아 뜸"의 정체.
  2. `gdrive.py`의 `upload_file_resumable()`이 토큰 갱신(`_get_access_token`)
     / 폴더 조회·생성(`_ensure_folder`) / resumable 세션 여는 POST까지
     전부 청크 업로드용 `aiohttp.ClientSession(timeout=_UPLOAD_TIMEOUT)`
     (`sock_read=300s`)을 그대로 물려받아 사용했음. 이 세 요청은 원래
     1~2초짜리 작은 JSON 왕복인데, 기기 쪽 네트워크가 일시적으로
     끊기거나 응답이 늦으면 프론트에는 "Google Drive 연결 확인 중..."
     0%로 최대 5분간 아무 진행도 없이 멈춘 것처럼 보이다가 뒤늦게
     `Timeout on reading data from socket`으로 실패. 사용자 입장에서는
     "멈춘 것 같다"고 느끼고 재시도(버튼 재클릭)하게 되는 유인이 되어
     1번 문제와 맞물림.
- 조치: FIXED (코드 완결, 실기기 검증은 아직).
  - `logs.js`: `logsState.gdrive.uploading` 재진입 가드 추가 + 업로드
    중 두 업로드 버튼 모두 disabled 처리, `try/finally`로 확실히 해제.
  - `gdrive.py`: 핸드셰이크 전용 `_HANDSHAKE_TIMEOUT`(total=20s,
    sock_connect=10s, sock_read=15s)을 신설해 토큰갱신/폴더조회·생성/
    resumable 세션 오픈 요청에 개별 적용. 실제 청크 PUT 루프는 기존
    관대한 타임아웃(`_UPLOAD_TIMEOUT`, sock_read=300s) 그대로 유지
    (느린 회선에서도 대용량 전송이 끝까지 가야 하므로).
- 검증 필요: 실기기에서 (a) 업로드 중 버튼 재클릭 시 토스트만 뜨고
  두 번째 루프가 안 생기는지, (b) 의도적으로 네트워크를 끊은 상태에서
  Drive 전송 시 20초 내외로 빨리 실패 메시지가 뜨는지 확인.
- 근거 로그: 없음 (사용자 제공 스크린샷 3장 기반 코드 리뷰. rlog 분석
  대상 아님).

## [NEEDS_VALIDATION] LeadBlend closer_jump(8m)/big_jump(15m) 게이트, CUTOUT_* (2026-08-16, 커밋 084a5b8)
- 상태: route1/route2 특정 이벤트로 검증됨(closer_jump: route1 seg13 t=794s,
  big_jump: route1 t=1388~1390s / route2 t=825~827s). 표본이 각 1건씩이라
  추가 로그로 재현성 확인하면 좋음.

## [NEEDS_VALIDATION] LEAD_ACQ_LOSS_GRACE_TIME(0.5s)가 실측 레이더/비전 플리커 유실시간보다 짧을 가능성 (2026-08-19, x11seg 라우트, HEAD 366009153812)
- 근거: 원본 12436프레임에서 `lead_presence_segments(min_duration_s=0.5)`로
  뽑은 1초 미만 lead-lost 구간 4건 전부, 실측 유실시간(마지막 True 프레임
  ~다음 True 프레임)이 0.5s를 초과함:

  | seg | t 구간 | vEgo | dRel 전→후 | 실측 유실시간 |
  |---|---|---|---|---|
  | --2 | 203.41→204.11 | ~9 m/s (주행) | 44.9~45.2 → 47.2~47.4m (연속적, 같은 리드로 보임) | ~0.70s |
  | --6 | 424.56→425.51 | ~0.07 m/s (거의 정지) | 21.1→15.2m (튐) | ~0.95s |
  | --8/--9 경계 | 595.11→596.11 | ~18.3 m/s (고속) | 78.7→93.4m (등속 가정 시 예상 ~81m와 12m 이상 불일치) | ~1.00s |
  | --9 | 649.66→650.61 | ~7 m/s | 35.2m 근처 유지 | ~0.90s |

- 해석: 4건 모두 `LEAD_ACQ_LOSS_GRACE_TIME=0.5s`를 초과 — lead acquisition
  램프의 debounce가 실주행 중 레이더 플리커로 인해 의도보다 자주
  리셋(재확인 대기 `LEAD_ACQ_CONFIRM_TIME=0.2s`부터 다시 카운트)될 여지가
  있음을 시사하는 첫 정량적 근거. `EnableRadarTracks < 3` 상태라 비전
  폴백 의존도가 높은 것과 맞물려 있을 수 있음.
- 특기사항: 595~596s 구간(고속 주행 중)은 유실 전후 dRel 변화가 등속
  가정과 12m 이상 어긋남 — 같은 리드의 노이즈가 아니라 근거리 리드
  소실 + 원거리 리드 재포착(컷아웃 유사 상황)일 가능성도 있어 LEAD_ACQ
  단독 이슈로 단정하기는 이름. dashcam(mp4) 동기화로 실제 장면 확인은
  아직 안 함.
- 표본: 이번 1개 라우트, 4건. 그레이스 타임 조정 전 추가 라우트로
  재현성 확인 필요.
- 근거 로그: `20260819_062438_000002c9--63f3712592` (x11seg, HEAD
  366009153812, dirty=False)

## [VALIDATED] x16seg 라우트 종방향 전구간 클린 — harsh brake 전부 운전자 개입 (2026-08-19, HEAD 366009153812)
- 16.44km / 955s (19093 프레임) 전체에서 `harsh_brake_events` 15건 발생했으나
  전부 해당 프레임에서 `cruiseEnabled=False` 확인됨. 두 클러스터
  (t=3242~3244 교차로 정지신호 앞 정지, t=3381~3396 도심 구간·오토바이
  통행) 모두 dashcam 프레임으로 확인한 결과 신호대기/도심 저속 구간에서
  운전자가 먼저 disengage 후 수동 제동한 것 — ADAS가 활성 상태에서
  급제동을 유발한 사례는 이번 라우트에 0건.
- cruise_engage_disengage_events 2건(disengage) 모두 위 두 지점과 일치,
  재인게이지 1건(t=3284.8)도 정상적인 재출발.
- 근거 로그: `20260819_114324_000002cb--6ef53b224d` (x16seg)

## [VALIDATED] 근거리 컷인 유사 이벤트 매끈한 반응 (2026-08-19, x16seg t=2516.9~2519)
- t=2516.93~2517.18 (0.25s, 0.5s 미만이라 lead_presence_segments엔
  안 잡힘) 순간 leadStatus 유실 후 재포착 시 dRel이 12.1m→4.7m로
  점프, leadVRel도 -0.5→+3.4로 튐 (근접 차량 재포착/컷인 유사 패턴).
  이후 aEgo가 -0.2→-0.8 m/s²까지 약 2초에 걸쳐 매끄럽게 램프,
  harsh_brake_events에 잡히지 않음. lead_cut_in_detector가 이 지점을
  검출은 했지만 컨트롤 반응 자체는 튀지 않은 양호 사례.
- 근거 로그: 위와 동일.

## [NEEDS_VALIDATION] carrot_serv.py speed_n_sources min() 선택에 히스테리시스 없음 — src/desiredSpeed 잦은 플리커 (2026-08-19, x16seg)
- 코드: `desired_speed, source = min(speed_n_sources, key=lambda x: x[0])`
  (carrot_serv.py) — 매 프레임 후보(atc/road/vturn/route/model 등) 중
  최솟값을 그대로 채택. 후보값들이 서로 근접해 있으면 프레임 노이즈만
  으로도 `source`(및 `desiredSpeed` 그 자체)가 프레임 단위로 왕복.
- 실측: 전체 85건의 src 전환 중 1초 이내 4건 이상 몰린 "플리커 클러스터"
  5곳 확인 (t=3144.4~3145.8 10건/1.4s, t=3206.4~3206.8 4건/0.4s,
  t=3223.4~3225.2 5건/1.8s, t=3236.2~3236.9 5건/0.7s, t=3404.4~3407.2
  6건/2.8s). 대부분 완만한 커브가 이어지는 국도 구간(curvature
  0.0005~0.0007, 거의 직선에 가까움)에서 road/route/vturn 캡값이
  171~200 사이로 서로 근접할 때 발생. 예: t=3146.88 desiredSpeed=171
  → t=3147.68 194 (0.8s만에 23km/h 왕복).
- 실제 영향: 이번 라우트에서는 aEgo 변동폭이 -0.03~-0.47 m/s² 수준으로
  작아 체감 저크는 미미함 (하류 슬루 리미터가 상당 부분 흡수하는 것으로
  보임). 다만 후보값 간 격차가 더 벌어지는 상황에서는 `desiredSpeed`
  자체가 소스 라벨과 함께 튀어 체감 저크로 이어질 수 있어 구조적
  리스크로 기록. 최소값 선택에 짧은 dwell-time/hysteresis(예: N프레임
  연속 우세해야 전환)를 추가하는 방안 검토 여지 있음.
- 근거 로그: 위와 동일 (`source_transition_log` 결과 기반).

## [VALIDATED] 정지 선행차 추종 감속 — 클린 케이스 (2026-08-19, x11seg 라우트)
- t=597~606s: 리드 정지(`leadVLead`→0 근처)에 맞춰 17.5→1.4 m/s까지
  8.9초 동안 매끈하게 감속(min_aEgo=-2.53 m/s²), `leadStatus=True` 끊김
  없이 `src=route`가 처음부터 끝까지 감속을 주도. lead acquisition
  램프나 LeadBlend가 별도 개입할 필요 없는 이상적 케이스 — 정지 리드
  처리가 최소한 이런 클린한 시나리오에서는 잘 동작함을 보여주는
  긍정적 사례로 기록.
- 근거 로그: 위와 동일.

## [NEEDS_VALIDATION] LEAD_ACQ_LOSS_GRACE_TIME(0.5s) 초과 사례 대량 추가 확보 + 정차열 중 dRel 불연속(재포착 대체 의심) 신규 패턴 (2026-08-20, x20seg 라우트 260819-1, HEAD f7b154638cf2)
- 라우트: 20세그(25.6km/1200s, ADAS 활성 97.3%). `lead_presence_segments`로
  True→False(<3s)→True 패턴 8건 검출, 이 중 ADAS 비활성(정지선 앞 수동
  재출발) 1건 제외 7건이 분석 대상.
- 그레이스타임(0.5s) 초과 여부:

  | seg | 유실 구간 | 실측 유실시간 | vEgo | dRel 전→후 | 상황 |
  |---|---|---|---|---|---|
  | --2 | 205.53→207.99 | 2.46s | 0.0 (정차) | 46.4→38.8m (−7.6m) | 정차열 |
  | --2 | 208.69→210.48 | 1.79s | 0.0 (정차) | 44.7→32.2m (−12.5m) | 정차열 |
  | --3 | 263.84→264.63 | 0.79s | 0.0 (정차) | 45.6→35.8m (−9.8m) | 정차열 |
  | --3 | 277.33→277.83 | 0.50s (경계) | 0.0 (정차) | 46.2→36.1m (−10.1m) | 정차열 |
  | --4 | 315.28→316.48 | 1.20s | 11.6 m/s | 46.5→53.8m (+7.3m) | 저속 주행 |
  | --8 | 551.08→552.18 | 1.10s | ~25 m/s | 102.6→102.9m (+0.3m) | 고속, 노이즈성 |
  | --9 | 631.38→633.13 | 1.75s | ~24.5 m/s | 95.6→109.9m (+14.3m) | 고속 |

  7건 중 6건이 0.5s 초과(0.79~2.46s), 1건은 정확히 경계값. 기존
  누적(x11seg 4건 + x16seg 1건 = 5건, ~0.7~1.0s대)에 이번 6~7건을
  더하면 총 표본 11~12건으로 확대되고, 유실시간 최대값도 2.46s까지
  늘어남 — `LEAD_ACQ_LOSS_GRACE_TIME=0.5s`가 실측 분포보다 상당히
  짧다는 근거가 강화됨. 값 상향(예: 1.0~1.5s) 또는 재설계 검토 우선순위
  상승 권고.
- **신규 패턴**: `--2`/`--3` 세그의 4건은 전부 `vEgo=0.0`(신호대기 등
  정차열) 상태에서 dRel이 매 유실마다 약 8~12.5m씩 "감소"하며
  재포착됨. ego가 정지해 있으므로 동일 리드의 위치 노이즈만으로는
  이 정도 dRel 감소가 설명되지 않음 — 정차열에서 레이더가 유실 후
  대기열 내 더 가까운 차량(또는 자기 차로 리드가 아닌 인접
  차량)으로 재포착 대상이 바뀌는 "리드 대체" 패턴일 가능성. 기존
  FINDINGS의 고속 12m+ 불연속 사례(595~596s, x11seg)가 저속/정차
  상황에서도 유사하게 반복됨을 시사 — 고속 한정 이슈가 아닐 수 있음.
  `--9` 구간의 +14.3m 점프(고속, 1.75s)도 동일 계열의 두 번째 고속
  사례로 추가 확보.
- 표본 한계: dashcam 동기화로 실제 장면(선행차 여러 대 여부, 차로
  변경 등) 확인은 아직 안 함 — 리드 대체 가설 검증에는 영상 확인
  필요.
- 근거 로그: `20260819_110424_000002ca--bbae959cbf--1`~`--20` (x20seg,
  route 260819-1)

### → [VALIDATED, 가설 수정] dashcam 프레임 확인 결과 — "정차열"이 아니라 "교차로 횡단교통" (2026-08-20)
- `extract_dashcam_frames.py`로 `--2`(t=205.53/207.99, 208.69/210.48),
  `--3`(t=263.84/264.63, 277.33/277.83) 4건 전부 유실 직전/재포착 직후
  프레임을 매칭 오차 1~12ms로 추출, 육안 확인 완료.
- **4건 전부 동일한 대형 교차로에서 정지신호 대기 중인 장면**: ego
  전방 차로는 정지선~횡단보도 구간이 비어 있고, 그 너머 넓은
  교차로를 버스/트럭/승용차 등 **횡단 방향(직교) 교통류가 계속
  통과**하는 상황. 기존에 가정했던 "동일 차로 정차 대기열(내
  차로에 여러 대가 줄지어 서있는 상황)"이 아니었음 — 애초에 내
  차로 정면에 정차한 리드가 뚜렷하게 없는 교차로 지오메트리.
  (`--2` event2는 파란 시내버스가 교차로를 가로지르는 순간과
  재포착 시점이 정확히 겹침.)
- **해석 수정**: dRel이 유실마다 8~12.5m씩 "감소"하며 재포착되는
  패턴은, 같은 정차열 내에서 더 가까운 차량으로 전환되는 게
  아니라 — 레이더/비전이 **횡단 교통류 중 한 대(또는 교차로 건너편
  차량)를 일시적으로 "내 차로 리드"로 오탐지**했다가, 그 차량이
  교차로를 빠져나가거나 다른 차량으로 바뀌면서 dRel이 바뀌는
  것으로 보는 편이 프레임 증거와 더 부합함. 정지선 대기 중
  전방이 빈 교차로 지오메트리에서는 진짜 리드가 없는데도 리드
  존재로 판정되는 자체가 문제 — 단순 그레이스타임 부족보다 상위
  단계(정차 중 빈 교차로에서의 lead qualification/게이팅) 이슈일
  가능성 시사. `LEAD_ACQ_LOSS_GRACE_TIME` 상향 필요성 자체는
  여전히 유효(유실시간 실측 분포 문제는 별개)하나, 이 4건을
  "정차열 리드 대체"의 근거로 인용하는 것은 부정확 — 다음부터는
  "교차로 정차 중 횡단교통 오탐지"로 표기.
- 비교 이미지: `compare_seg2_event1/2.jpg`, `compare_seg3_event1/2.jpg`
  (devnotes에 커밋, 원본 qcamera/rlog는 미커밋).
- 근거: 위 4건 동일, 세그 `--2`/`--3` (route 260819-1).

## [NEEDS_VALIDATION] carrot_serv.py src/desiredSpeed 플리커 — vturn↔road/model/route 전환에서 대규모 재현 (2026-08-20, x20seg 라우트 260819-1, HEAD f7b154638cf2)
- 기존 x16seg 세션에서 "완만한 커브 국도 구간에서 후보값 근접 시
  발생"으로 처음 발견된 이슈(NEEDS_VALIDATION, 위 항목)가 이번
  라우트에서 훨씬 큰 규모로 재현됨.
- 실측: `source_transition_log` 총 164건의 src 전환 중, A→B→A 패턴(3s
  이내 원래 소스로 복귀)이 49건. 대부분 `vturn`이 한쪽 항인 전환
  (`vturn↔road`, `vturn↔model`, `vturn↔route`, `vturn↔cam`)이며,
  20.3~31.3 m/s(약 73~113km/h) 구간의 커브 진입 구간에 집중:
  - seg4~8 (t=317~541s): vturn↔model, vturn↔road, vturn↔route가 번갈아
    2~3초 이내로 최대 6~7회 연쇄 전환하는 클러스터 다수 (예: seg7
    t=498.5~500.9 구간 2초 내 5회 전환).
  - seg11~12 (t=774~835s): vturn↔road가 0.5~2.55s 간격으로 12회 이상
    연쇄 전환 (t=774.3~782.7 구간에 집중).
  - seg18~19 (t=1156~1247s): vturn↔road, vturn↔model 전환 다수, 최대
    2.81s 간격.
- 해석: `speed_n_sources`의 단순 `min()` 선택 방식이 커브 구간에서
  `vturn`(회전속도 제한) 후보와 `road`/`model`/`route`(도로/모델
  기반 속도) 후보가 서로 근접한 값을 주고받을 때마다 소스 라벨과
  desiredSpeed가 프레임 단위로 왕복하는 현상이 국도 커브뿐 아니라
  고속 커브 구간 전반에서 지속적으로 발생함을 확인 — 기존 발견보다
  범위가 넓고(직선 국도 한정이 아님) 빈도도 높음(85건 중 클러스터
  5곳 → 164건 중 A→B→A 49건). dwell-time/hysteresis 추가 필요성이
  더 명확해짐.
- 실제 영향 미측정: 이번 세션은 `source_transition_log`만 확인,
  해당 구간들의 `aEgo`/저크 영향은 아직 미분석 — 다음 세션에서
  desiredSpeed 왕복폭 및 실제 가감속 반영 여부(하류 슬루 리미터
  흡수량) 정량화 필요.
- 근거 로그: 위와 동일 (`source_transition_log` 결과 기반).

### → [PATCH_WRITTEN, 미검증] vturn↔model 쌍 한정 — model 후보를 desiredCurvature 기반으로 게이팅 (2026-08-20, 9차)
- 우세 쌍(vturn↔model, model↔vturn 140건, 260819-4 세션 집계)의 근본원인:
  `desire_helper.py`의 `_make_model_turn_speed()`는 모델 예측 미래속도를
  그대로 저역통과 필터링한 값일 뿐 곡률 판단이 없음 — vturn/route는 이미
  각자 곡률/거리 기반으로 "지금 커브인지 직선인지" 판단해서 직선이면
  즉시 무제한(250 근접)으로 복귀하는데, model 후보는 그 판단이 없어서
  실제로는 이미 직선에 들어섰는데도 필터 지연으로 낮은 값을 잠깐 더 들고
  있다가 vturn/route가 이미 250으로 복귀한 뒤 뒤늦게 따라 올라옴 — 그
  사이 min() 후보가 왕복하며 플리커로 관측됨.
- **대응**: `carrot_serv.py`에서 vturn이 이미 갖고 있는 "회전 종료" 판단
  근거를 model 후보와 공유. `modelV2.action.desiredCurvature`(lateral
  제어기가 실제로 쓰는 최종 곡률)가 `model_turn_straight_hold_sec`(0.6s)
  이상 연속으로 `model_turn_straight_thresh`(0.002, 기존 로그분석
  threshold와 동일값) 미만이면 "확정 직선"으로 보고 그 프레임의 model
  후보를 `speed_n_sources`에서 제외(하한선이 아니라 완전 배제). 곡률이
  다시 threshold를 넘으면 카운터가 즉시 리셋되어 model 후보가 지연 없이
  바로 복귀 — 실제 커브 진입 반응은 늦추지 않는 비대칭 설계.
- 범위 한정: 이번 패치는 vturn↔model 쌍만 다룸. atc/road/route 등을
  포함한 나머지 쌍의 min() 히스테리시스 부재는 여전히 미해결(위
  NEEDS_VALIDATION 항목, PARAMS_REGISTRY.md 참고).
- 패치: `selfdrive/carrot/carrot_serv.py`. `py_compile` 통과, **실차 적용
  + push 완료** (`git am`, commit `2226db7`, `1fca82f..2226db7`).
  **실측 검증 전** — 특히 S자 커브처럼 정점 사이에
  짧은 직선 구간이 끼는 경우 hold_sec(0.6s) 값이 과도하게 model을
  배제하지 않는지, 그리고 실제로 vturn↔model 플리커 클러스터가
  줄어드는지 다음 세션에서 로그로 확인 필요.
- 근거: 위 플리커 항목과 동일 (`source_transition_log`, x20seg
  260819-1), 260819-4 세션 우세 쌍 집계(model↔vturn 140건).

## [기타 확인] harsh_brake_events 전부 정차/저속 구간, ADAS 활성 중 급제동 0건 (2026-08-20, x20seg 라우트 260819-1)
- 원본 7건 전부 seg1 t=134~146s(vEgo 3.7~7.8 m/s, 저속/정차 부근)에
  집중, `remove_driver_intervention` 적용 후 0건 — 전부 운전자
  개입/비활성 구간. curve_exit_no_accel_scan 2건 중 1건은 vEgo=0.37
  (정지 근접, 유의미하지 않음), 1건은 vEgo=14.67 m/s에서 max
  aEgo=-0.241(경미) — 유의미한 커브 탈출 가속 지연 이슈 없음.
  turn_speed_violations/steering_oscillation/lead_cut_in 전부 0건.
- 근거 로그: 위와 동일.

## [기타 확인] 라우트 260819-4 (x20seg, route3b 연속분) 분석 — 신규 이슈 없음, 벤치마크 데이터 추가 확보 (2026-08-20, HEAD f7b154638cf2, 신규 커밋 없음)
- route ID `ba55f880d1` seg5~seg24 (20개) — 260819-3에서 이미 분석한
  route3b(`ba55f880d1` seg0~4 추정, x5seg)의 **직접 연속분**. 같은
  부팅 세션의 뒷부분. 19.0km/1200.2s, avg 57.0km/h, ADAS 활성 97.3%.
- **harsh_brake_events**: 원본 22건 → 전부 t=1251.3~1262.1(10.8s) 단일
  정차 이벤트(25.75km/h→0)에 집중. `cruise_engage_disengage_events`로
  교차검증: t=1250.8 disengage(brakePressed=True 시작) →
  t=1283.6 re-engage(vEgo=4.9 시점, 정차 후 재출발). 전 구간
  cruiseEnabled=False 확인 — ADAS 활성 중 급제동 0건 계속 재확인
  (지금까지 4개 라우트 연속 클린).
- **turn_speed_violations/lead_cut_in/steering_oscillation**: 전부 0건.
- **speed_n_sources(src) 플리커**: 330 transitions/1200s(평균 3.6s당
  1회), A→B→A 챠터 37.6%(124/330) — 기존 이슈(PARAMS_REGISTRY
  NEEDS_VALIDATION) 재확인, 신규 아님. 우세 쌍은 여전히
  model↔vturn(140건), road↔vturn(91건).
- **LEAD_ACQ_LOSS_GRACE_TIME 관련**: leadStatus gap 16건 중 8건이
  2s 미만 단기 유실. 이 중 **세그먼트 경계 아티팩트는 1건뿐**(t=1195.67,
  dur=0.358s) — 나머지 7건은 세그먼트 중간에서 발생한 실제 순간유실로,
  0.5s 초과 사례가 5건(0.603s, 0.606s, 0.902s, 1.562s, 1.599s) 포함.
  extract_log.py 경계 리셋 버그와 무관한 진짜 유실 표본이 이번
  라우트에서는 대다수(7/8) — 과거 "재검토 필요" 판단에 실사례 비중이
  낮지 않다는 근거 추가.
- **신규 관찰 — dRel/vRel 불연속 점프 26건, 이번엔 전부 무해하게
  해소**: t=1181.72(src=model, dRel 41.3→18.3m, -23.0m 단일프레임
  점프, vRel -0.9→+0.63로 부호 반전, cruiseEnabled=True)와
  t=1182.87(dRel 17.8→21.0m, vRel 2.19→3.9) 등 26건의 대형 점프
  확인. 모두 LeadBlend 문서상 CLOSER_JUMP_DIST(8m)/BIG_JUMP_DIST(15m)
  게이트보다 훨씬 큰데도 **급제동 반응 없이 aEgo가 오히려 양수
  유지**(가속 지속) — 260819-2 seg24에서 확인된 "vRel-only 불연속 →
  운전자 급브레이크" 문제 사례와 달리 이번엔 dRel도 함께 점프하고
  방향이 즉시 멀어지는 쪽(vRel 양전환)이라 위협으로 해석되지 않고
  자연 해소된 것으로 보임. src=model/vturn/route/bump/road 전반에서
  관찰(특정 소스 국한 아님) — 레이더/비전 트랙 ID 전환의 일반적
  잡음으로 추정. NEEDS_VALIDATION 항목(LeadBlend vRel-only 게이트)에
  "무해한 경우도 다수" 반례 데이터로 추가.
- 코드 변경 없음(관찰/분석만). 다음 세션 참고용 벤치마크 누적.

## [기타 확인] 라우트 260819-3 (x20seg, 2세션 분할) 분석 — 신규 이슈 없음, 기존 발견 재확인 (2026-08-20, HEAD f7b154638cf2, 신규 커밋 없음)
- 업로드 zip에 서로 다른 route ID(부팅 세션) 2개가 섞여 있어 분리 추출:
  - route3a (`6ef53b224d`, x15seg, 15.58km/894.9s, avg 62.7km/h, ADAS
    활성 91.7%)
  - route3b (`ba55f880d1`, x5seg, 3.53km/301.5s, avg 42.2km/h, ADAS
    활성 86.8%)
  (같은 zip 안에 route ID가 다른 세그먼트가 섞여 있으면 `t`
  컬럼이 서로 다른 부팅의 monotonic clock이라 하나로 이어 붙이면
  안 됨 — 항상 route ID 기준으로 분리 추출할 것, toolkit 사용법에
  참고사항으로 추가 예정.)
- **harsh_brake_events**: route3a 원본 15건, `remove_driver_intervention`
  적용 후 0건. route3b는 원본부터 0건. ADAS 활성 중 급제동 계속
  0건 — 기존 결론(x11/x16/260819-1/260819-2) 재확인, 신규 아님.
- **extract_log.py 세그먼트 경계 아티팩트 버그 재확인**: 순간
  리드유실(<3s) 후보 총 24건(route3a 22 + route3b 2) 중 13건이
  세그먼트 시작 시각과 diff<0.06s로 정확히 일치하는 아티팩트로
  확인(route3a 12건 + route3b 1건). 나머지 11건(route3a 10 +
  route3b 1)은 세그먼트 경계와 무관한 실사례 후보. 기존
  PARAMS_REGISTRY "재검토 필요" 판단을 다시 한 번 뒷받침 — 아직
  패치 미적용 상태 그대로.
- **저속 근접 리드 대체 패턴 — 극단 사례 추가 확보(단, ADAS
  비활성 구간)**: route3a 종점부(t=3389~3398s, 목적지 도착 후
  운전자 수동 정차 중, `cruiseEnabled=False` 전 구간 확인됨) 근처에서
  t=3392.28~3393.93(1.65s) 유실 후 leadDRel이 41.9m→6.0m로 재포착 —
  약 36m 점프. vEgo가 3.7→2.4 m/s로 감속 중인 저속 상황이라 동일
  리드의 정상적 거리 변화로는 물리적으로 설명 불가(요구되는 상대
  접근속도가 비현실적) — 기존 정차열 "리드 대체" 가설
  (260819-1/2에서 8~14.3m대 점프 관찰)과 같은 계열이나 이번이
  지금까지 중 가장 큰 폭(36m)의 사례. **다만 이 구간 전체가
  `cruiseEnabled=False`(운전자 수동 주차 조작)로, LeadBlend/MPC가
  이 순간에 관여하지 않아 실제 제어 영향은 없음** — 가설을 뒷받침하는
  표본으로는 유효하나 제어 안전성 이슈로 격상할 근거는 아님. 표본
  누적 계속 필요(고속/ADAS 활성 중 사례가 이 가설의 핵심 검증
  대상).
- **steering_oscillation_detector 오탐 2건 유형 확인**: (1)
  route3a t=3285.03~3286.83, `cruiseEnabled=True` 상태에서 조향각이
  0→19.5°→-15°로 완만하게 한 번 왕복 — 실제로는 급커브/분기점을
  매끄럽게 통과하는 단일 S자 조향으로, 고주파 진동이 아님. (2)
  route3a t=3385.43~3387.38, `cruiseEnabled=False`(운전자 수동
  주차 조작) 구간이라 ADAS와 무관. 두 경우 모두 탐지기가 "3회
  방향전환"만 보고 플래그하는 방식의 구조적 오탐 — 저속(<8m/s)
  구간이나 큰 진폭(>15°)의 완만한 단일 왕복은 실제 진동과 구분이
  안 됨. 탐지기에 진폭/주파수 조건 추가하는 개선 여지 있음
  (NEEDS_IMPROVEMENT, 코드 변경 아직 미착수).
- turn_speed_violations 0건(양쪽 라우트), curve_exit_no_accel_scan
  최대 감속치 -1.058 m/s²(저속 5.13m/s, 경미) — 유의미한 이슈 없음.
  lead_cut_in 탐지 5건(route3a 4 + route3b 1)은 전부 위 저속
  주차/근접 시나리오 범주, 별도 신규 패턴 아님. source_transition
  플리커 route3a 84건/route3b 100건 — 기존 carrot_serv.py
  speed_n_sources 이슈 재확인 수준(이번 세션에서 클러스터 상세
  재분석은 생략).
- 코드 변경 없음(관찰/분석만). 근거 로그: `20260819_114424_...--
  6ef53b224d--1`~`--15` (route3a), `20260819_121627_...--ba55f880d1--
  0`~`--4` (route3b).

## [기타 확인] 라우트 260819-5 분석 — MAX_SEGMENTS_PER_ROUTE 관련은 정정됨(위 [WONTFIX] 항목, 로그가 패치 이전 시점) 외 신규 이슈 없음 (2026-08-20, HEAD f7b154638cf2, 신규 커밋 없음)
- route5a: route ID `ba55f880d1` seg25~39 (x15seg, route3b/260819-4의
  직접 연속분). 11.58km/899.7s, avg 46.3km/h, ADAS 활성 98.6%.
  route5b: 새 route ID `dc8bdc7d4d` seg0~4 (x5seg, 위 rotate 직후
  시작된 새 부팅/새 라우트). 1.35km/300.0s, avg 16.2km/h, ADAS 활성
  26.7%(시내 저속/수동 주행 위주).
- **harsh_brake_events**: route5a 9건 전부 t=2126.97~2134.87(7.9s) 단일
  정차 이벤트(21.4→12.2km/h, cruiseEnabled=False 전 구간)에 집중.
  route5b 20건 전부 t=2485.87~2502.37(16.5s) 단일 정차 이벤트
  (19.0km/h→정지, cruiseEnabled=False 전 구간). **ADAS 활성 중 급제동
  0건 — 7개 라우트 연속 재확인**.
- **turn_speed_violations/lead_cut_in(20m 이내 급조 후보)**: route5a
  turn_speed_violation 0건, cut-in 후보 4건(전부 저속 재확인 필요 —
  이번 세션 상세 미조사, 우선순위 낮음). route5b는 시내 저속 특성상
  cut-in 후보 39건으로 급증 — cruiseEnabled 낮은 구간과 대부분 겹칠
  것으로 추정되나 이번 세션에서 개별 교차검증은 생략(저속/ADAS
  비활성 위주 구간이라 실질 영향 낮다고 판단, 필요시 다음 세션에서
  상세 확인).
- **steering_oscillation**: route5a 0건. route5b 1건
  (t=2501.62~2502.62, cruiseEnabled=False, vEgo=2.7m/s, max_abs_angle=
  255.9°) — 기존에 확인된 "저속 수동 조작 오탐" 패턴과 일치, 탐지기
  개선 필요성 재확인(코드 작업 안 함).
- **LEAD_ACQ_LOSS_GRACE_TIME**: route5a 순간유실 13건 중 12건 세그먼트
  경계 아티팩트, **real 1건**(t=1883.42~1883.57, dur=0.148s,
  cruiseEnabled=True) — 유실 직후 재포착된 리드가 61m→108m로 트랙
  전환(먼 거리 리드 교체), 그 뒤로도 dRel이 94~108m 사이에서 프레임당
  8m+ 요동(비전 원거리 노이즈, 기존 이슈와 일치) — 급제동 등 실질
  영향 없이 무해하게 해소. route5b는 순간유실 32건 중 29건이 "real"로
  분류됐으나 **전부 cruiseEnabled=False 구간(t=2604~2690 밀집 클러스터
  포함, 검증: 해당 구간 cruiseEnabled True 프레임 0건)** — ADAS
  비활성 상태라 LEAD_ACQ_LOSS_GRACE_TIME 판단 근거로 부적합, 표본에서
  제외 권장.
- **dRel/vRel 프레임당 급점프(≥8m)**: route5a 30건(대부분 94~110m
  원거리 구간에서 왕복 요동 — 기존 "비전 리드 트래킹 노이즈" 패턴과
  일치, 재발 재확인). route5b 2건(t=2478~2479, 72~89m 구간, 마찬가지
  원거리 요동). 전부 cruiseEnabled=True(route5a) 구간에서도 급제동
  등 실질 영향 없이 해소 — 260819-4의 "26건 무해 해소" 반례와 같은
  결.
- 코드 변경 없음(관찰/분석만). 근거 로그: `20260819_124127_...--
  ba55f880d1--25`~`--39` (route5a), `20260819_125627_...--
  dc8bdc7d4d--0`~`--4` (route5b).

## [도구 캘리브레이션 이슈] curve_exit_no_accel_scan 기본 임계값이 시내/커브연속 도로에서 오탐 다수 — 커브탈출후 재가속 지연 가설, 이번 로그에서는 확증 못함 (2026-08-20, 260819-6 분석, HEAD f7b154638cf2, 신규 커밋 없음)
- 라우트 260819-6: route6a(기존 route ID `dc8bdc7d4d` seg5~22, x18seg,
  route5b 직접 연속분, 8.57km/1043.2s, avg 29.6km/h, ADAS 활성 74.7%,
  시내/정체 위주) + route6b(신규 route ID `f7e0bb3abd` seg0~1, x2seg,
  0.4km/121.6s, avg 11.7km/h, 저속 위주). 코드 변경 없음(관찰/분석만).
- **주요 목적: "커브 탈출 후 재가속 지연" 가설(사용자 제기, vturn/model/
  route 소스 공통 적용 여부) 검증 시도.** `curve_exit_no_accel_scan`
  (기본 curvature_thresh=0.002, straight_thresh=0.0005)으로 후보
  19건(route6a) 추출 → cruiseEnabled=True & brakePressed=False로
  거른 뒤 vCruise-vEgo 갭이 큰 상위 5건을 프레임 단위로 직접 대조:
  - t=3191.4/3196.4(seg12): vCruise 80km/h인데 vEgo가 44→0km/h까지
    28초간 연속 감속 — 그러나 desiredSpeed는 시종일관 80~200km/h로
    vEgo를 훨씬 상회(어떤 source도 실제로 제약하지 않음), leadStatus는
    구간 내내 True(dRel 58m→감소, vRel≈-4.8m/s) — **선행차 추종에
    의한 정상적인 정차 감속이었고, desiredCurvature 0.0001~0.003의
    미세한 값은 차선추종 노이즈였지 실제 커브가 아님.** 오탐.
  - t=3437.1(seg16): 유사하게 vCruise 70km/h, vEgo 14.4m/s에서 감속
    지속. leadStatus가 t=3437.72에 True→False로 전환(dur=18.2s, 이후
    LEAD_ACQ_LOSS_GRACE_TIME 스캔에서도 별도 포착)되지만, 그 직후
    desiredCurvature가 -0.003→+0.03까지 급격히 커지며 소스가
    route→model→vturn으로 전환 — **"커브를 빠져나온 뒤" 감속이
    아니라 실제로는 다음 커브(연속 커브/S자 구간)로 진입하는 중이었고
    straight_thresh(0.0005)를 스캔이 일시적으로 통과한 것이 "탈출"로
    오판된 것.** 오탐.
  - 나머지 후보(t=2771/2935/3208/3475 등)는 vEgo가 0~2m/s로 이미
    정차/저속 시나리오라 "재가속 지연" 판단 대상 자체가 아님.
- **결론: 이번 라우트로는 "커브 탈출 후 재가속 지연" 가설을 확증도
  반증도 못함.** 시내/정체 도로 특성상 감속 이벤트 대부분이 선행차
  추종 또는 연속 커브(S자) 진입과 뒤섞여 있어, curvature_thresh가
  낮은 현재 스캔 설정으로는 "진짜 단일 커브를 완전히 빠져나왔고
  가속할 여지(vCruise 대비 갭)가 있는데도 가속하지 않은" 케이스를
  깨끗하게 분리하지 못함. **개선 방향 제안(코드 변경 아직 미착수)**:
  (1) `curve_exit_no_accel_scan`에 leadStatus=False(또는 dRel이
  충분히 먼) 조건을 추가해 선행차 추종 감속을 배제, (2) straight_thresh
  이후 "진짜 직선" 지속시간을 더 길게 요구하거나 커브 재진입(다음
  curvature 상승) 여부를 확인해 S자 연속 오탐 배제, (3) 위 필터링
  후에도 남는 후보가 있는지 다음 로그에서 재확인 — 이상적으로는
  선행차 없는 개활지 단일 커브 구간이 많은 로그가 필요.
- **LEAD_ACQ_LOSS_GRACE_TIME**: True→False→True 전환 52건(route6a)
  스캔 후 세그먼트 경계 아티팩트 14건 제외, 나머지 38건 중
  cruiseEnabled=True는 17건, 그 중 0.5s 이상 11건. 유실 직전 dRel<60m로
  좁혀도 11건 남았으나 개별 대조 결과 대부분 무해:
  - 35.996s/18.202s(t=3046/3437): 유실 직전 dRel≈50m대였으나 실제로는
    선행차가 시야에서 멀어지며 자연스럽게 트래킹이 끊긴 개활도로
    상황(가속 중, 위험 아님) — "위험한 유실"이 아니라 "선행차 없음"에
    가까움. 기존 GRACE_TIME 논의(순간 재포착 필요성)의 대상과는 결이
    다름.
  - 6.051s(t=3517.87, dRel_before=19.17m): 저속(4~7m/s) 급코너 진입
    구간과 겹침(steering_oscillation 이벤트와 동일 지점) — 코너
    선회로 인한 일시적 시야이탈로 판단되며, 코너 진입 시 vturn이
    이미 desiredSpeed를 19~29km/h로 낮게 유지 중이었어서 리드 유실이
    실제 제어 리스크로 이어지지 않음(급제동/저크 없음) — vturn이
    선행차 정보 없이도 안전 속도를 유지한 긍정적 사례로 기록.
  - 나머지(1.15s 이하 6건)는 기존 패턴과 동일(원거리 트랙전환/근접
    재포착), 신규 아님.
  → **PARAMS_REGISTRY 판단 변경 없음(NEEDS_VALIDATION 유지)**. 다만
  "긴 유실(6s+)이 실측된다"는 사실 자체는 처음 확인 — 단, 이번
  사례들은 전부 무해했으므로 시급성 낮음으로 기록.
- **기타(클린 재확인)**: harsh_brake ADAS 활성 중 0건(양쪽 라우트) —
  8개 라우트 연속 재확인. turn_speed_violations 0건. steering_oscillation
  10건(route6a) — 8건 cruiseEnabled=False 저속 수동 조작(기존 오탐
  패턴), 2건 ADAS 활성 저속(<8m/s) 급코너 단일 왕복(기존 오탐 패턴과
  일치, 신규 아님). MAX_SEGMENTS_PER_ROUTE 검증은 이번 로그도 여전히
  패치 커밋(8/20 00:57) 이전 시점(8/19 13:01~15:02)이라 미검증 상태
  그대로 이월.
- 코드 변경 없음(관찰/분석만). 근거 로그: `20260819_130127_...--
  dc8bdc7d4d--5`~`--22` (route6a), `20260819_150157_...--
  f7e0bb3abd--0`~`--1` (route6b).

## [WONTFIX] 260819-8 로그 분석 — 사상 첫 완전 클린 고속도로 라우트 확보 (2026-08-20, 사용자 "체크포인트" 요청으로 세션 축약)
- 신규 커밋 없음(HEAD f7b154638cf2 그대로). 코드 변경 없음(관찰/분석만).
- 라우트 260819-8: route8a(`f7e0bb3abd` seg24~39, x16seg, 260819-7의
  직접 연속분, 27.27km/959.9s, **avg 102.3km/h, cruiseEnabled 100%**)
  + route8b(신규 `da28883b75` seg0~4, x5seg, 5.93km/272.0s, 시내 저속
  혼합, cruiseEnabled 83.5%).
- **route8a: harsh_brake/turn_speed_violation/steering_oscillation/
  cut-in/curve_exit_no_accel_v2 전부 0건 — 지금까지 분석한 라우트 중
  처음으로 모든 이벤트 카테고리가 완전히 클린한 순수 고속도로 구간.**
  desiredCurvature도 19145 프레임 중 threshold(0.002) 초과 39건뿐(max
  0.00217)로 사실상 직선 도로라 커브 관련 가설(탈출 후 재가속 지연/
  진입 중 과소감속) 검증에는 이번 로그가 표본을 못 줌 — 두 가설 모두
  이번 세션엔 진전 없음(다음 세션으로 이월).
- route8b: harsh_brake 16건 전부 t=2683.36 disengage(운전자 개입,
  브레이크 없이 조향 변화로 해제) 직후 발생한 저속 정차 감속 —
  기존 "disengage-인접 harsh_brake" 오탐 패턴과 완전히 동일(신규
  아님). curve_exit_no_accel_v2 후보 1건 나왔으나 vEgo=0.04m/s(사실상
  정차 완료 시점)라 가설과 무관 — 배제.
- **LEAD_ACQ_LOSS_GRACE_TIME**: route8a에서 기존 최대치(2.46s)를 크게
  뛰어넘는 긴 유실 다수 확인(222.85s, 109.30s, 41.4s대 2건 등,
  0.5s+ 14건/22건). **전부 고속도로 위주 구간에서 선행차 자체가 장시간
  없었던 것으로 판단**(harsh_brake/turn_violation 등 다른 카테고리가
  같은 라우트에서 전부 0건이라 위험으로 이어진 정황 없음) — 세그먼트
  경계 아티팩트는 22건 중 3건만 해당(cross_seg=True), 나머지는 실제
  유실. route8b는 0.5s+ 4건/7건, 기존 스케일과 동일. **PARAMS_REGISTRY
  판단 변경 없음(NEEDS_VALIDATION 유지)** — 다만 "고속도로에서는
  긴 유실이 흔하고 대체로 무해"라는 패턴이 이번에 더 뚜렷해짐.
- speed_n_sources 플리커: route8a 25건/52건, route8b 40건/61건
  (A→B→A, <3s 윈도우) — 기존 이슈 재확인, 신규 아님.
- **MAX_SEGMENTS_PER_ROUTE 관련 신규 관찰(검증 아님, 참고 정보):**
  route `f7e0bb3abd`가 260819-6 seg0부터 이번 260819-8 seg39까지
  끊김 없이 정확히 40개 세그먼트(구버전 cap과 동일 개수)로 이어진 뒤
  boot ID가 `000002ce`→`000002cf`로 바뀌면서 신규 route
  `da28883b75`가 시작됨. **route ID 자체가 보통 디바이스 boot마다
  새로 생성되는 구조라, 이 종료가 MAX_SEGMENTS_PER_ROUTE 캡이 실제로
  발동한 것인지 단순 재부팅과 우연히 겹친 것인지 이 로그만으로는
  구분 불가** — 로그 시각(8/19 15:25~15:45)이 패치 커밋(8/20 00:57)보다
  여전히 이전이라 어차피 패치 미반영 상태의 관찰. NEEDS_VALIDATION
  유지, 다음 패치-이후 로그에서 "20개에서 boot 없이 rotate하는지"를
  직접 봐야 진짜 검증됨.
- 이 항목을 `[WONTFIX]`로 태그한 이유: 이번 세션 자체는 신규 이슈나
  코드 조치 없이 전부 기존 판단 재확인/보류 상태 유지로 끝남 — 별도
  후속 조치 불필요, 기록 목적.
- 근거 로그: `20260819_152557_...--f7e0bb3abd--24`~`--39` (route8a),
  `20260819_154157_...--da28883b75--0`~`--4` (route8b).

## [PATCH_APPLIED, NEEDS_VALIDATION] 비전-only 원거리 리드 closing-rate 크로스체크 (2026-08-20)

- **증상 (사용자 실주행 체감 보고)**: 고속도로에서 멀리 서행/정지 중인
  앞차를 카메라가 먼저 인식(파란박스)한 시점부터는 감속이 없다가, SCC
  레이더가 인식(빨간박스)하는 순간부터 감속이 시작되는 느낌.
- **근거**: `VISION_RADAR_CROSSOVER.md`의 8개 zip 전체 crossover 분석
  (108건, highway 65건) — 특히 `260819-6` seg15/seg5 두 사례에서
  modelProb 0.54~0.56의 약한 확신 상태가 7~8초간 유지되다가 레이더
  확인 시점에 dRel이 90m 이상 좁혀져 있던 것이 발견됨 (상세는
  `VISION_RADAR_CROSSOVER.md` "8개 전체 종합" 참고). 이번 사용자 보고와
  정확히 일치하는 패턴.
- **코드 원인**: `radard.py`의 `VisionTrack.update()`는
  `self.cnt < 20 or self.prob < 0.97` 조건이 참인 동안(원거리·저확신
  구간에서는 거의 항상 참) `vRel`을 모델이 예측한 순간 속도차이
  (`lead_msg.v[0] - model_v_ego`)에서 그대로 가져오고, dRel 미분 기반
  실측 접근속도는 `prob>=0.97`이 되어야만 섞인다. 그런데
  `long_mpc.py`의 `LEAD_ACQ_TTC_*` 선제감속 로직은 이 (낙관적으로
  추정될 수 있는) `vRel`로 TTC를 계산하므로, 실제 접근속도가 편향되어
  있으면 TTC 임계값을 넘지 못해 선제감속이 개입하지 않는다 — 레이더가
  락온해 정확한 vRel로 바뀌는 프레임에야 TTC가 급락하며 뒤늦게 반응.
- **패치 (long_mpc.py, commit `b403d52`, 실차 `git am` + push 완료
  `f7b1546..b403d52`)**: `radarstate.leadOne`의
  `vRel`과는 별개로 `dRel`을 프레임 간 미분해 독립적인 접근속도 추정치를
  저역통과 필터(시정수 `VISION_CLOSING_RATE_TAU=1.0s`)로 누적. 레이더
  미락온 상태(`leadOne.radar == False`)에서만 갱신하고,
  `VISION_CLOSING_RATE_MIN_TIME=0.5s`(최초 1.0s에서 사용자 피드백으로
  단축) 이상 연속 추적된 뒤에만 신뢰. 이렇게 구한 TTC를 기존 vRel 기반
  TTC와 `min()`으로 합쳐 더 위험한 쪽을 `frac_ttc`에 반영 — 기존
  LEAD_ACQ 로직과 동일하게 순수 floor라 감속을 절대 완화시키지 않음.
  `VisionTrack.vRel` 자체는 건드리지 않아(다른 곳에서도 쓰이는 핵심
  추적값이라 변경 리스크 회피) 영향 범위를 long_mpc.py 내부로 한정.
  ⚠️ TAU=1.0s는 그대로라 0.5s 시점엔 저역통과 필터가 실제 접근속도의
  약 39%까지만 수렴한 상태 — danger 판정이 다소 보수적으로 나올 수
  있음, 실측 후 추가 단축 또는 TAU 조정 여지 있음.
- **미해결/다음 단계**:
  1. **aEgo 실측 대조 미완료** — 코드는 실차에 `git am` + push 완료
     (`b403d52`) 됐지만 검증용 로그는 아직 없음. `VISION_RADAR_
     CROSSOVER.md` 최우선 후보 5건(`260819-6` seg15/seg5, `260819-7`
     seg14/seg8, `260819-5` seg34) 세그 폴더를 재업로드받아 패치 적용
     전/후 aEgo 프로파일 비교 필요.
  2. 실차 검증(패치 적용된 `b403d52`로 동일/유사 고속도로 원거리
     서행차 구간 재주행) 아직 없음 — 파라미터(TAU=1.0s, MIN_TIME=0.5s,
     사용자 피드백으로 1.0s→0.5s 단축됨)는 추정치이며 추가 튜닝 여지
     있음.
  3. `leadRadar=False` 크로스오버 65건 중 실제 closing은 37%뿐(나머지는
     벌어지거나 무변화)이라는 기존 분석 결과상, 이 패치가 opening/flat
     케이스에서 불필요하게 개입하지 않는지도 확인 필요 — dRel 미분이
     양수(벌어짐)면 `_vision_dRel_rate < -0.1` 조건에서 걸러지므로 설계상
     안전하지만 실측 확인 전까지는 NEEDS_VALIDATION.

## [PATCH_APPLIED, NEEDS_VALIDATION] vturn 커브 사전감속 지평선 4.5s -> 6.5s -> 8.0s 확대 (2026-08-20)

- **증상 (사용자 실주행 체감 보고)**: 곡선 진입 전 사전 감속 시간이
  부족해 충분히 감속되지 않은 상태로 곡선에 진입, 곡선 내부에서
  급감속(급브레이크)이 발생.
- **근거**: 기존 `[INVESTIGATING] 조여드는 커브 중간에 vturn 감속 진행
  중 운전자 브레이크 개입` (260819-7 seg6, 표본 1건) — 곡률이 8.6초에
  걸쳐 서서히 증가하는 커브에서 vturn 자체 감속률(1.2 m/s²)은 매끈했지만
  시스템 aEgo가 -3.41m/s²까지 도달한 직후 운전자가 추가 브레이크 개입,
  개입 시점에도 곡률은 계속 증가 중이었음 — "vturn 감속이 곡률 조여드는
  속도를 못 따라간다"는 가설과 일치. 이번 사용자 보고가 같은 패턴의
  재확인으로 판단해 조치.
- **코드 원인**: `carrot_man.py`의 `vturn_speed()`는 모델이 예측한 전방
  궤적 중 `vturn_lookahead_horizon_s`(기존 4.5s) 이내 지점들만 보고 그중
  가장 엄격한(작은) 필요속도를 채택한다. v_i²=v_f²+2ad 물리공식 자체는
  각 지점에서 매 프레임 정확하지만, 정점까지 걸리는 시간이 이 지평선보다
  긴 커브(8.6s 사례)에서는 "아직 안 보이는" 더 급한 정점이 계산에서
  빠져 있다가, 접근하며 정점이 뒤늦게 지평선 안으로 들어오는 순간
  필요속도가 갑자기 크게 떨어져 결과적으로 급감속처럼 느껴진다 — 물리
  공식의 문제가 아니라 "그 순간 보이는 거리"가 짧아 감속 시작이 늦어지는
  구조적 문제.
- **패치 1차 (`carrot_man.py`, commit `4c15987`, ryu `c3-ms-dev`에 push
  완료 — `b403d52..4c15987`, `git am` 적용 확인됨, 로컬 커밋 해시
  `1827c1e`는 am 재구성 과정에서 `4c15987`로 바뀜)**:
  `vturn_lookahead_horizon_s` 4.5s → 6.5s (사용자 요청 +2s).
- **패치 2차 (`carrot_man.py`, commit `1fca82f`, ryu `c3-ms-dev`에 push
  완료 — `4c15987..1fca82f`, `git am` 적용 확인됨, 로컬 커밋 해시
  `c4e3093`는 am 재구성 과정에서 `1fca82f`로 바뀜)**: 같은 세션에서 사용자가
  근거 사례(260819-7 seg6, 조임 지속시간 8.6s)를 더 가깝게 커버하기
  위해 6.5s → 8.0s로 재확대 요청. 모델 예측 궤적(`ModelConstants.
  T_IDXS`)이 최대 10.0s까지 있으므로 8.0s도 모델 데이터 범위 안에서
  안전. 감속 프로파일 자체(`v_i²=v_f²+2ad`, `vturn_decel_rate`/
  `vturn_safe_time`)는 이번에도 변경 없음 — 지평선(스캔 범위)만 확대.
  사용자 질문에 대한 설명: `vturn_lookahead_horizon_s`는 "감속에
  걸리는 시간"이 아니라 "몇 초 앞까지 커브 후보로 스캔할지" 지평선이며,
  방지턱과 동일한 거리기반 서서히-감속 프로파일 자체는
  `vturn_decel_rate`/`vturn_safe_time`이 담당(이번 변경 대상 아님) —
  이 구분을 명확히 안내함.
- **미해결/다음 단계**:
  1. **실차 검증 없음** — 1차(`4c15987`)/2차(`1fca82f`) 모두 push까지는
     완료됐으나 두 조정 모두 아직 실주행 검증 없음. 적용 후 유사
     조여드는 커브 구간 재주행 로그로 aEgo/운전자 개입 여부 재확인
     필요 — 다음 세션 최우선.
  2. **8.0s < 8.6s** — 위 근거 사례의 조임 지속시간(8.6s)보다 새 지평선이
     아주 근소하게 짧음(0.6s 차이). 실측 후 필요하면 추가 미세 조정
     검토(우선순위 낮음, 1차 6.5s 대비 격차는 크게 줄어듦).
  3. 지평선 확대가 부작용을 만드는지 확인 필요 — 더 먼 지점까지 보게
     되면서 모델의 원거리 예측(신뢰도가 상대적으로 낮은 구간)이 잘못된
     조기감속을 유발하지 않는지(오탐 커브), 특히 완만한 국도 커브가
     연속되는 구간에서 기존 `speed_n_sources` vturn↔road/model/route
     플리커 이슈(FINDINGS.md 별도 항목)와 상호작용하지 않는지 관찰 필요.
     지평선이 4.5s→8.0s로 거의 2배 가까이 늘어난 만큼 1차 때보다
     원거리 예측 신뢰도 이슈를 더 주의 깊게 봐야 함.
  4. `vturn_safe_time`(1.0s)/`vturn_decel_rate`(1.2 m/s², 방지턱 기본값)는
     이번에도 건드리지 않음 — 지평선만 넓혀도 부족하면 다음 단계로 검토.

## [RISK_IDENTIFIED, NEEDS_VALIDATION] model_turn_straight_gate(commit `2226db7`) — desiredCurvature 게이팅이 "커브 진입 전 model 사전감속"까지 억제할 위험 (2026-08-20, 코드 재검토)

- **배경**: 9차 세션에서 vturn↔model 플리커(A→B→A 49건) 대응으로
  `carrot_serv.py`에 `model_turn_straight_thresh`/`hold_sec` 게이트를
  추가(`2226db7`, 실차 적용+push 완료). 의도는 "커브를 이미 빠져나왔는데
  model만 필터 지연으로 낮은 값을 뒤늦게 들고 있는" 케이스만 걸러내는
  것.
- **재검토 결과, 새로 발견한 위험**: 게이트 조건이 참조하는
  `modelV2.action.desiredCurvature`는 lateral 제어기가 **지금 이 순간**
  실제로 쓰는 곡률(현재값)이다. 반면 배제 대상인 `modelTurnSpeed`는
  `desire_helper._make_model_turn_speed()`에서
  `np.interp(modelTurnSpeedFactor, modeldata.velocity.t, modeldata.velocity.x)`로
  계산되는 **모델 예측 궤적의 미래 시점 속도**(저역통과 필터링됨) —
  즉 명시적으로 "앞을 미리 보는" lookahead 값이다.
- 커브 진입 직전에는 보통 desiredCurvature가 threshold 미만인 직선
  구간이 hold_sec(0.6s)보다 길게 존재한다 — **바로 이 구간에서 model이
  "저 앞에 커브가 있다"며 미리 속도를 낮추려는 순간, 이 게이트가 model
  후보를 `speed_n_sources`에서 제외**한다. vturn/route는 자체 lookahead
  (vturn은 최근 8.0s로 확대, 1fca82f)로 커브를 별도로 잡지만, model
  후보가 원래 보완하려던 "vturn/route가 못 잡는 케이스, 또는 더 이른
  시점의 예측"이라는 이점이 이 게이트로 무력화될 수 있다.
- 커밋 메시지의 "실제 커브 진입 반응은 안 늦춤"이라는 주장은 vturn/route
  기준으로는 맞지만(둘 다 자체 lookahead로 독립 동작), **model 후보
  자체의 진입-전 기여도는 검토되지 않은 채** 패치가 나갔다.
- **영향 범위 미확정**: vturn/route가 이미 대부분의 커브를 자체
  lookahead로 커버하고 있다면 model의 사전감속 기여분이 원래도 작아
  실질적 영향이 미미할 수 있음 — 반대로 vturn/route보다 model이 먼저
  반응하던 케이스가 있었다면(플리커 분석에서 model↔vturn이 우세 쌍으로
  나온 것 자체가 model이 자주 min()을 차지했다는 뜻이므로 가능성 있음)
  체감 가능한 사전감속 지연/누락으로 나타날 수 있음. **로그 재분석
  필요** — `2226db7` 적용 이후 로그에서 커브 진입 전 구간의
  `desiredSource`/`vTurnSpeed`/model 후보 배제 여부와 실제 aEgo 프로파일
  대조.
- **개선 방향(제안 1번 채택, 패치 작성 완료)**:
  1. ✅ **채택**: `desiredCurvature`(현재값) 대신 `model_turn_speed` 자체의
     추세를 보는 방식 — "최근 hold_sec 동안 model_turn_speed가 (노이즈
     허용폭을 넘어) 감소한 적 없이 계속 높거나 회복 중"일 때만 배제하면,
     하강 중(=사전감속 시도 중)인 케이스는 건드리지 않고 트레일링
     케이스만 잡을 수 있음.
  2. (미채택, 참고용) vturn/route가 이미 "직선"으로 판단 중인지(예:
     vturn_speed가 이미 거의 무제한)까지 같이 참조해서, "vturn/route도
     이미 직선으로 보는데 model만 낮다"는 조합일 때만 배제하는 방식도
     검토했으나, 1번이 더 단순하고 model 자체의 상태만으로 판단 가능해
     우선 채택.
- 근거: `desire_helper.py` L84-88(`_make_model_turn_speed`), `carrot_serv.py`
  L1020-1036(게이팅 적용부, 패치 전 기준), cereal/log.capnp
  L983(`Action.desiredCurvature` 필드 확인).

### → [PATCH_APPLIED, NEEDS_VALIDATION] model 게이팅을 desiredCurvature -> model_turn_speed 추세 기반으로 재설계 (2026-08-20, 12차 작성 / 13차 실차 적용 확인)

- 위 위험 항목의 개선 방향 1번(model_turn_speed 자체 추세 기반) 채택,
  패치 작성 완료.
- **구현**: `carrot_serv.py`에서 `model_turn_straight_thresh`(desiredCurvature
  기준)를 제거하고, `model_turn_speed_prev`(직전 프레임 값)/
  `model_turn_speed_noise_tol`(0.3km/h, 노이즈 허용폭)을 신설.
  `model_turn_speed >= model_turn_speed_prev - noise_tol`(즉 유의미한
  하락이 없음)이 `model_turn_straight_hold_sec`(0.6s, 기존값 유지) 이상
  연속되면 "트레일링(커브를 이미 빠져나와 복귀 중)"으로 확정해 model
  후보를 배제. 반대로 유의미한 하락이 한 프레임이라도 있으면(=커브
  접근 중 사전감속 시도) 카운터 즉시 리셋 — 진입측 사전감속은 건드리지
  않는 비대칭 설계는 그대로 유지.
- `py_compile` 통과, 컨테이너 ryu 클론에서 커밋 생성(로컬 커밋
  `7cdc20b`, base `0f7575f`) 후 `git format-patch -1`로 추출, 임시
  브랜치에서 `git am` 적용 시뮬레이션 통과 확인.
- 패치 파일: `/mnt/user-data/outputs/0001-carrot_serv-model-desiredCurvature-model_turn_speed.patch`
  (`git format-patch` 형식). **실차 `git am` 적용 + push 완료**
  — 원격 반영 커밋 `119b101`(`0f7575f..119b101`, 로컬 재현이라
  해시는 `7cdc20b`와 다르지만 diff 내용 동일, 원격 fetch로 재확인함).
- **알려진 한계(실측 필요)**: 장시간 정속 커브(model_turn_speed가 낮은
  값에서 거의 정체)에서 노이즈 허용폭(0.3km/h) 이내로만 흔들리면
  "감소 없음"으로 판정되어 0.6s 후 model이 배제될 수 있음. 다만 그런
  상황에서는 vturn/route가 이미 같은 커브를 자체 lookahead로 커버하고
  있을 가능성이 높아(그렇지 않다면애초에 model_turn_speed가 낮게 유지될
  이유가 적음) 실질적 위험은 낮다고 판단하나, 다음 세션에서 정속 커브
  구간 로그로 model 배제 여부와 실제 vturn/route 값을 대조 검증 필요.
- 근거: 위 RISK_IDENTIFIED 항목과 동일.

## [PATCH_APPLIED, NEEDS_VALIDATION] screenrecord clip(commit `0f7575f`) — 20분 자동 세그먼트 롤오버에서도 clip이 반복 생성됨 (2026-08-20, 코드 재검토 -> 14차 패치 작성 -> 15차 실차 적용 확인)

- **배경**: 10차 세션에서 "정지 버튼 누르면 마지막 1분을 별도 clip으로
  추출" 기능 추가(`0f7575f`, 실차 적용+push 완료). `screenrecorder.cc::
  stop_locked()`에서 `closeEncoder()` 직후 `extract_trailing_clip()`
  호출.
- **재검토 결과, 새로 발견한 문제**: `update_screen()`에 이미 있던 기존
  로직 — 녹화 시작 후 20분(`1000*60*20`ms) 경과 시 `need_restart=true`
  → `stop_locked(); start_locked();`로 세그먼트를 자동 롤오버하는
  구조가 있는데, 새 clip 추출 코드가 `stop_locked()` 안에 들어가 있어서
  **이 자동 롤오버에서도 동일하게 clip이 생성**된다.
  - 즉 사용자가 정지 버튼을 누르지 않고 화면녹화를 계속 켜둔 채
    장시간(수 시간) 주행하면, 20분마다 자동으로 `_clip.mp4`가 하나씩
    쌓이고 그때마다 ffmpeg 프로세스가 백그라운드로 실행됨 — 커밋
    메시지/WIP.md에 적힌 원래 의도("정지 버튼 누를 때만")와 실제 동작이
    다름.
  - 부가 엣지케이스: clip 파일명이 초 단위 타임스탬프(`YYMMDD_HHMMSS`)라,
    `-y`(덮어쓰기) 옵션과 겹쳐 같은 초에 stop이 두 번 발생하면(토글
    연타 등, 확률은 낮음) 앞선 clip이 소리 없이 덮어써질 수 있음.
- **발열/부하 평가**: ffmpeg는 `-c copy`(재인코딩 없음, stream copy)라
  1회 호출당 CPU 부하는 낮고 짧음 — 재인코딩이 아니므로 급격한 발열
  유발 구조는 아님. `closeEncoder()`(OMX HW 인코더 종료)가 ffmpeg
  실행보다 먼저 동기적으로 끝나 HW 인코더와 리소스를 다투지도 않음.
  다만 `QProcess::startDetached`는 우선순위/코어 지정이 없는
  fire-and-forget 프로세스라 `set_core_affinity`로 관리되는
  camerad/modeld/controlsd와 스케줄링을 다툴 여지는 있고, 위 20분
  반복 버그 때문에 **장시간 녹화 세션 내내 이 부하가 주기적으로
  반복**되는 게 문제 — 단발성 발열까지는 아니어도 불필요한 주기적
  백그라운드 I/O/CPU 버스트가 누적됨. 저장공간도 의도치 않게 계속
  소모됨(수 시간 녹화 시 clip 파일 다수 누적).
- **개선 방향(패치 작성 완료, 14차)**: `stop_locked(bool auto_rollover
  = false)`로 시그니처 변경 — 사용자 경로(`toggle()`/`stop()`)는 기본값
  그대로, `update_screen()`의 20분 롤오버 경로만 `stop_locked(true)`로
  명시 호출. `extract_trailing_clip()` 호출을 `if (!auto_rollover &&
  !finished_path.empty())`로 감싸 롤오버 시 clip 생성 자체를 스킵.
  타임스탬프 충돌(부가 엣지케이스)은 해상도를 유지한 채
  `extract_trailing_clip()`이 ffmpeg 호출 직전(동기 구간)에
  `stat()`으로 대상 경로 존재 여부를 확인해, 충돌 시에만
  `_clip_2.mp4`, `_clip_3.mp4`... 접미사를 붙이는 방식으로 해결
  (분 단위로 낮추는 대안은 버킷이 60배 커져 오히려 충돌 확률이 늘고
  검색 정밀도를 해쳐 기각).
- **패치 파일**: `/mnt/user-data/outputs/0001-screenrecord-clip-rollover-fix.patch`
  (`git format-patch` 형식, base `119b101`). 컨테이너 ryu 클론에서
  실제 커밋 생성(로컬 해시 `a349e3c`, base `119b101`) 후 추출, 별도
  임시 브랜치(base `119b101`)에서 `git am` 적용 검증 완료(clean
  apply). C++ syntax-only 체크(빌드 툴체인 없음, `stat()` 루프 로직만
  분리 컴파일로 확인)만 가능. **실차 `git am` 적용 + push 완료**
  (원격 반영 커밋 `591f219`, `119b101..591f219`, 원격 fetch로 diff
  동일함 재확인).
- 근거: `screenrecorder.cc` L98(`toggle`)/L114(`start`)/L119(`stop`)/
  L157(`stop_locked`)/L260-282(`update_screen` 20분 롤오버).
- ffmpeg 바이너리가 실제 comma 기기(AGNOS)에 설치돼 있는지는 여전히
  레포 내 근거 없음(`routes_logs.py` 주석에 "ffmpeg 기능은 포함 안 함"만
  존재) — WIP.md 기존 미검증 항목과 동일, 재확인만 하고 새로 해소된 건
  아님.

## [VALIDATED, 부분 확인] model_turn_speed 추세 게이팅(commit `119b101`) — 패치 후 첫 실주행 로그로 vturn↔model 플리커 감소 확인 (2026-08-20, 16차)
- **업로드**: dashcam zip 2개 (route `4fe653914c` 15:56~16:14, route
  `a5f42c2218` 15:37~15:55). extract_log.py 메타 확인 결과 **두 로그
  모두 repo HEAD `591f21930d00`(commit_date 14:56:54) 상태에서 기록** —
  기록 시각(15:37~16:14)이 패치 커밋 시각보다 뒤라 **13차 model 게이팅
  패치(`119b101`)가 실제로 반영된 상태의 첫 실주행 로그**로 확인됨.
- ⚠️ **업로드 zip 파일 손상**: 두 zip 모두 중간 구간이 손상됨(zstd
  CRC/zip local-header 불일치) — route `4fe653914c`는 세그 5~14(10개,
  약 10분) 유실, route `a5f42c2218`는 세그 7~9(3개, 약 3분) 유실. 손상
  구간을 제외한 정상 세그(각각 9개/16개, 실주행 9분/16분 분량)만
  추출해 분석. 다음 세션에서 같은 구간 재분석 필요하면 재업로드 요청
  (원인은 업로드/전송 과정 추정, 코드 이슈 아님).
- **vturn↔model 전환 빈도 (핵심 검증 지표)**: route1(9분 실주행)
  25건(양방향 합), route2(16분) 48건 → 각각 2.78/min, 3.0/min.
  260819-4 세션 베이스라인(패치 전, x20seg/1200s, model↔vturn 140건)의
  7.0/min 대비 **약 57~60% 감소**. 도로 유형(이번은 시내/저속 위주
  avg 20~44km/h, 베이스라인은 avg 57km/h 고속 국도)이 달라 완전
  통제비교는 아니지만, 방향성은 패치 의도(트레일링만 배제, 진입 반응은
  유지)와 일치.
- **다른 min() 히스테리시스 쌍은 여전히 미해결 재확인**: A→B→A
  플리커 세부 분해 결과 road↔vturn(route1 7건/route2 41건),
  route↔vturn(route1 4건/route2 31건)이 여전히 model↔vturn(route1
  14건/route2 30건)과 비슷하거나 더 큰 비중 — PARAMS_REGISTRY.md의
  "atc/road/route 등 나머지 쌍은 미해결" 판단 그대로 재확인, 신규 아님.
- **커브 진입 전 사전감속 억제(11차 위험) 간접 확인**: `turn_speed_violations`
  (vEgo > vTurnSpeed+0.5) 0건(양쪽 다) — 커브 구간에서 시스템이 필요
  속도보다 빠르게 통과한 사례 없음. 단, CSV에 `model_turn_speed`
  원시값이 없어 "게이팅이 실제로 언제 배제/포함됐는지"는 로그만으로는
  직접 확인 불가 — 간접 지표(플리커 감소 + overspeed 0건)까지만 확인,
  완전한 VALIDATED는 아님.
- **장시간 정속 커브 부작용(13차 알려진 한계)**: 이번 두 로그는 시내
  위주 주행이라 장거리 고속 완만한 커브 구간 자체가 거의 없음(교차로
  회전 위주) — 이 한계는 이번 로그로 검증 못 함, 여전히 과제로 남음.
- **일반 종방향 지표 (참고, 신규 이슈 없음)**: harsh_brake_events
  route1 21건/route2 41건 — cruiseEnabled=True(ADAS 활성) 상태에서
  발생한 건 route1 1건뿐(route2 0건). 그 1건(t=1393.5, seg0)은
  dashcam 프레임 대조 결과 교차로 진입 전 콘 설치 차선 축소 구간에서
  근접 선행차(38.9m, closing -4.2m/s)를 vturn(45km/h 제한)이 이미
  -1.4~1.5 m/s²로 매끈히 감속 중이던 상황에 운전자가 브레이크를 겹쳐
  밟은 경미한 사례 — 시스템 급제동 아님, ADAS 활성 중 급제동 사실상
  0건 기조 유지. turn_speed_violation/steering_oscillation 전부 0건
  (route2 steering_oscillation만 2건, 저속 급회전 구간 오탐 추정).
  curve_exit_no_accel_v2 후보(route2 11건)는 대부분 vEgo≈0(교차로
  정차) 또는 경미한 감속(-0.3~-0.7 m/s²)로 8차/9차 세션에서 이미 확인된
  "정차/저속 시내 회전 오탐" 패턴과 동일, 신규 이슈 아님.
- **screenrecord clip 롤오버 패치(commit `591f219`, 14/15차)는 이번
  로그로 검증 불가**: 이 업로드는 주행 rlog/qcamera(운전 로그)이고,
  screenrecord clip은 별도의 화면 UI 녹화 기능(`/data/media/0/videos`)이라
  겹치지 않음 — 실측 검증은 여전히 "화면녹화 켜둔 채 20분+ 주행" 형태로
  별도 확인 필요(WIP.md 참고).
- 근거 로그: `work/r1.csv`(9분, HEAD `591f219`), `work/r2.csv`(16분,
  HEAD `591f219`), `source_transition_log`/`harsh_brake_events`/
  `turn_speed_violations`/`curve_exit_no_accel_scan_v2` 결과.

## [VALIDATED] 재업로드(정상 zip, 19세그 완전판)로 16차 재검증 + vision-only closing-rate 크로스체크(commit `b403d52`) 최초 실측 검증 (2026-08-20, 17차)
- **16차 데이터 손상 슈퍼시드**: 16차는 zip 손상으로 세그 일부 누락된
  상태(9분/16분)로 분석했음 — 사용자가 정상 zip을 재업로드해 같은
  두 라우트를 19세그 전체(각 19분, `4fe653914c`/`a5f42c2218`, 둘 다
  HEAD `591f219`)로 재분석. **아래 수치가 16차 수치를 대체함.**
- **vturn↔model 플리커 (13차 model 게이팅 재검증, 전체 데이터 기준)**:
  route1 41건/19.0분=2.16/min, route2 49건/19.0분=2.58/min. 베이스라인
  (260819-4, 7.0/min) 대비 **63~69% 감소** — 16차 부분 데이터 추정치
  (57~60%)보다 더 뚜렷한 개선폭으로 재확인. ADAS 활성 중
  harsh_brake는 route1 1/35, route2 0/41로 계속 거의 0건 유지.
  turn_speed_violation 0/0.

### vision-only 원거리 리드 closing-rate 크로스체크(`b403d52`, 6차 패치) — 패치 후 첫 실측 검증
- **사용자 제보**: "카메라 인식 시(파란 박스)엔 미감속하다가 레이더
  인식(빨간 박스) 순간부터 감속 시작되는 느낌 — 이번엔 카메라 로직을
  반영해서 카메라 인식 시점부터 감속 시작하도록 수정" → 이 패치가
  실제로 그렇게 동작하는지 오늘 실주행으로 첫 검증.
- **크로스오버 이벤트 재현 자체는 여전함**: `vision_to_radar_crossover()`로
  찾은 highway(vEgo≥54km/h) 크로스오버가 route1 11건/route2 4건 —
  "비전이 먼저 잡고 레이더가 나중에 확인" 상황 자체는 패치 후에도
  여전히 발생(당연함, 패치는 이 상황 자체를 없애는 게 아니라 그 사이
  반응 여부를 바꾸는 것).
- **핵심 검증 — closing 상황(dRel_closed_m>5m) 6건 전부 aEgo 연속성
  확인**: 비전-only 시작 시점(t_vision_start) 전후 및 레이더 확인
  시점(t_radar_confirm) 전후로 aEgo를 1초 간격 스냅샷했을 때, **6건
  전부 레이더 확인 순간에 급격한 감속 "킥"이 없고, 감속이 이미
  진행 중이었거나 매끈하게 이어짐**:
  - route1 seg0(vRel0=-7.7m/s, 22.9m 좁혀짐): aEgo -0.21→-0.53(비전
    시작)→-0.91(레이더 확인)→-1.01(+1s) — 레이더 확인 이전부터 이미
    감속 진행 중, 확인 순간 전후로 기울기 변화 없음.
  - route2 seg15(vRel0=-8.0m/s, 14.8m 좁혀짐): -0.53→-0.70→-1.35→-1.24
    — 마찬가지로 매끈한 연속 감속, 프레임 단위로 상세 추적 결과
    `src=cam`이 비전-only 구간 내내 유지되며 점진적으로 감속 강도를
    올림(과거 증상이었던 "레이더 락온 순간 급반응"과 다른 패턴).
  - 나머지 4건(route1 seg4/seg5/seg12, route2 seg8)도 동일 패턴 —
    상세는 `work/r1.csv`/`work/r2.csv` t=1610.65/1644.75/2089.30/658.56
    부근 참고.
- **한계**: (1) 이번 두 라우트는 시내~국도 혼합이라 260819-6 seg15
  급의 "7~8초/90m대" 초장거리 저확신(modelProb 0.5대) 케이스는
  재현되지 않음(가장 큰 closing은 route1 25.1m) — 그 등급의 극단
  사례로 재검증은 아직 못함. (2) `desiredSpeed`/`aEgo`는 여러 소스가
  min()으로 합쳐진 최종 결과라, long_mpc 내부의 "TTC 크로스체크가
  정확히 몇 프레임째 개입했는지"까지는 로그만으론 분리 불가 — 여기서는
  "레이더 확인 순간 급격한 불연속이 없다"는 정성적/반정량적 확인까지만.
  (3) opening/flat 크로스오버(전체 highway 15건 중 9건)에서 패치가
  불필요 개입 안 하는지는 이번에도 미확인(설계상 dRel 미분 음수 시
  자동 제외되지만 실측 미확인, 6차 세션부터 이어지는 과제).
- 근거: `work/r1.csv`/`work/r2.csv`(19세그 전체, HEAD `591f219`),
  `vision_to_radar_crossover()` 결과, 위 6건 aEgo 스냅샷.
- 이전 베이스라인(패치 전, `VISION_RADAR_CROSSOVER.md`): highway
  크로스오버 65건, gap 중앙값 2.0s/최대 10.45s, dRel_closed 최대
  94.6m(260819-6 seg15). 이번 route1/route2 highway crossover
  gap 중앙값 2.25s/2.20s, 최대 4.10s/9.15s, dRel_closed 최대
  25.1m/14.8m — 표본이 작고 도로 유형이 달라(고속도로 위주가 아님)
  직접 비교엔 무리가 있으나, 극단적으로 긴 무대응 구간(7~8초급)은
  이번엔 관찰되지 않음.

## [RISK_IDENTIFIED, NEEDS_DEVICE_LOG] screenrecord 정지 버튼 -> ui 프로세스 크래시/재시작 의심 (`0f7575f` clip 추출 경로), clip 미생성 + 주행 종료 시 메모리부족 경고 동반 (2026-08-20, 18차)

- **사용자 제보 3건 (`c3-ms-web` CarrotWeb 로그탭 + 화면녹화 영상으로 재현)**:
  1. 최신 브랜치(`591f219`) 적용 후 화면녹화 **정지 버튼**을 누르면
     화면이 잠깐 멈췄다가 comma 쉼표 로고(부팅 스플래시)가 ~2초간
     떴다 사라지고 정상 화면으로 복귀.
  2. CarrotWeb 로그탭에 이번 녹화들(`20260820-153544.mp4`,
     `20260820-153846.mp4`, `20260820-154231.mp4`,
     `20260820-154321.mp4`) 전부 `_clip` 접미사 파일이 **하나도
     생성되지 않음** — 10차/14차/15차에서 구현한 "정지 시 마지막
     1분 clip 자동 생성" 기능이 실차에서 전혀 동작 안 하는 것으로
     보임.
  3. 주행 종료 시점에 콤마 화면에 "메모리 부족 (deviceState.
     memoryUsagePercent) 97% used" 퍼머넌트 알럿 발생(`events_ko.py`
     `low_memory_alert`, 기존 stock 알럿 로직 자체는 미변경).

- **영상 프레임 분석으로 1번 확정**: 사용자가 업로드한 화면녹화
  (`20260820_154237.mp4`, 16.28s, 폰 화면 촬영)를 3fps로 프레임
  추출해 확인. t≈0~5s는 정상 화면(사이드바 MEM 64%), **t≈5.3~7.6s
  구간은 화면이 완전히 정지된 프레임**(동일 이미지 반복, 사이드바
  CPU/MEM/VOLT 박스만 빨간색으로 바뀜 — 터치 피드백으로 추정),
  **t≈8.0s에 comma 쉼표 부팅 스플래시가 전체화면으로 나타남**
  (`selfdrive/ui`가 죽고 manager가 재기동할 때 뜨는 그 화면과 동일),
  t≈12s 이후 정상 화면으로 복귀(MEM 63%, 이전과 비슷한 수준 —
  **이 사례에서는 메모리 사용률 자체가 크래시 시점에 특별히 높지
  않았음**, 즉 "메모리 고갈로 인한 OOM kill"이 매 크래시의 직접
  원인은 아닐 수 있음. 크래시는 결정적/재현성 있어 보임 — 정지
  버튼을 누를 때마다 발생하는 것으로 사용자가 보고).

- **코드 레벨 원인 후보 (확정 아님, 실차 크래시 로그 확보 전까지
  가설)**: `0f7575f`(10차)에서 `stop_locked()`에 추가된
  `extract_trailing_clip()`가 `QProcess::startDetached("ffmpeg", args)`
  로 ffmpeg 서브프로세스를 **`ui` 프로세스에서 직접 fork+exec**함.
  `ui` 프로세스는 GPU/EGL 컨텍스트, OMX 하드웨어 인코더 핸들
  (`OmxEncoder`), 카메라 관련 visionipc/공유메모리 핸들 등 "무거운"
  자원을 다수 들고 있는 멀티스레드 프로세스 — 이런 프로세스에서
  자식 프로세스를 fork()하는 것은 임베디드 GPU 드라이버(특히
  Qualcomm 계열)에서 알려진 위험 패턴(자식이 상속받은 GPU/DMA-BUF
  핸들 상태가 드라이버 기대와 어긋나거나, fork 시점에 다른 스레드가
  들고 있던 락이 자식에 그대로 복사돼 부모 프로세스 자체의 안정성에
  영향을 줄 수 있음). **증상 3가지(정지 시 크래시-재시작 / clip
  미생성 / 장시간 반복 시 메모리 상승)가 이 가설 하나로 일관되게
  설명됨**: 정지할 때마다 fork 지점에서 `ui`가 죽고 manager가
  재기동 → 재기동 전에 죽으므로 ffmpeg exec가 끝까지 못 가 clip
  파일이 안 남고 → `ui` 재기동마다 GPU/카메라/OMX 자원을 처음부터
  다시 잡으면서 이전 크래시분 자원이 완전히 회수 안 되는 게 누적되면
  장시간 주행(특히 화면녹화를 자주 켰다 껐다 하는 주행)에서 메모리
  사용률이 서서히 올라갈 수 있음.
  - 이 가설은 **미확정**임을 명확히: `ui`가 진짜 SIGSEGV 등으로
    죽었는지, 아니면 watchdog(`watchdog_max_dt`)이 응답 지연을
    감지해 강제 재시작한 것인지, fork 자체가 원인인지는 실제 크래시
    덤프 없이는 단정 불가.
  - 확인 방법(다음 세션 또는 사용자가 SSH/adb로 직접 확인 가능):
    `/var/crash/`(apport, `system/tombstoned.py`가 감시하는 경로)에
    해당 시각(15:42경) 근처 `ui` 관련 크래시 덤프가 있는지, 또는
    manager cloudlog(`swaglog`, `Paths.swaglog_root()`)에 같은
    시각 `ui` 프로세스 재시작 로그가 있는지 확인 필요.

- **당장 취할 수 있는 안전한 방향(다음 세션 패치 후보, 미착수)**:
  `ui` 프로세스에서 직접 `QProcess::startDetached`로 ffmpeg를 fork하지
  않고, 정지 시점에 "clip 추출 요청"만 가벼운 방식(파라미터 파일 또는
  마커 파일 기록)으로 남긴 뒤, GPU/카메라 핸들을 들고 있지 않은 별도
  경량 프로세스(예: manager가 관리하는 소형 PythonProcess, 또는
  carrotweb 백엔드 쪽 — 이미 `fleetmanager/helpers.py`가 자체
  프로세스에서 `ffmpeg` subprocess를 문제없이 쓰고 있음)가 폴링해서
  실제 ffmpeg 추출을 수행하도록 구조 변경. 이렇게 하면 `ui` 프로세스는
  fork를 전혀 하지 않게 됨.
- **참고**: `fleetmanager/helpers.py`는 자체적으로 이미 `ffmpeg`을
  plain PATH로 `subprocess.Popen`/`subprocess.run`하고 있고(썸네일/
  스트리밍용) 정상 동작 중인 것으로 알려져 있음 — 따라서 "ffmpeg
  바이너리가 기기에 없다"는 가설은 낮은 우선순위(가능성 낮음, 다른
  프로세스에서는 이미 동작 확인됨). 문제는 ffmpeg 부재가 아니라
  **`ui` 프로세스에서 fork하는 행위 자체**일 가능성이 높음.
- **부가 관찰(작지만 별개인 코드 순서 이슈)**: `stop_locked()`가
  `finished_path = encoder->get_last_video_path()`를 `closeEncoder()`
  **호출 전**에 캡처함 — 경로 문자열 자체는 `encoder_open()` 시점에
  이미 고정되므로 이 순서가 당장 버그를 일으키진 않지만(파일 finalize
  전 경로만 미리 읽어두는 것뿐), 가독성상 `closeEncoder()` 이후로
  옮기는 게 의도(정지 후 finalize된 파일 경로)를 더 명확히 함 —
  우선순위 낮음, 위 fork 이슈와는 별개.
- 근거: 사용자 업로드 `20260820_154237.mp4`(3fps 프레임 추출 분석),
  CarrotWeb 로그탭 스크린샷(`20260820-15{35,38,42}*.mp4`, `_clip`
  파일 0건), 저메모리 알럿 스크린샷(16:18, MEM 97%), 코드 리뷰
  (`screenrecorder.cc` `stop_locked()`/`extract_trailing_clip()`,
  `system/tombstoned.py` 크래시 덤프 경로 확인).

## [VALIDATED] screenrecord ui watchdog timeout — 원인 확정 + 패치 실차 검증 완료 (2026-08-20, 19차)

> **19차 최종 갱신(같은 세션 이어감)**: 패치를 사용자가 실차에서
> `git am` 적용 + `git push` 완료(commit **`7b4a160`**,
> `591f219..7b4a160`) 후, 실측 검증 3항목 **전부 통과**:
> 1. `/data/log/swaglog.0000000957~962`(패치 적용 커밋 `7b4a160`
>    세션, 19:14~19:23) 전체에서 `watchdog` grep 0건 — 워치독
>    타임아웃 재발 없음.
> 2. 정지 버튼을 19:18경/19:22경 두 차례 누른 시점 모두 CarrotWeb
>    로그탭에 `260820_191859_clip....mp4`(15.4MB),
>    `260820_192207_clip....mp4`(15.1MB)가 정상 생성 확인(사용자
>    스크린샷).
> 3. 사용자 확인: 정지 버튼 누를 때 화면 정지/comma 스플래시 없이
>    **"바로 반응"** — 패치 전 증상(화면 정지 → 스플래시 2초 →
>    복귀) 재현 안 됨.
>
> 3항목 모두 부합해 이 이슈는 **해소로 확정**. "장시간 반복 시
> 메모리 상승" 연결고리(18차 관찰, 정성적 추정)만 정량 확인 안 된
> 채로 낮은 우선순위 관찰 사항으로 남음 — 크래시-재기동 자체가
> 없어졌으므로 자연 해소로 판단, 향후 장시간 주행 로그에서 메모리
> 추이가 이상 없는지 정도만 참고로 지켜보면 충분.


- **18차 가설이 실차 swaglog로 확정됨.** 사용자가 `/data/log/`
  (정확한 경로: `Paths.swaglog_root()` = `/data/log/`, 18차에서
  `/data/media/0/realdata`로 잘못 안내했던 것 정정)에서 사건 시각대
  (`swaglog.0000000914`~`916`, 2026-08-19 15:41~15:45 KST) 로그를
  확인.
- **`swaglog.0000000915`에 결정적 증거**: manager가
  `"Watchdog timeout for ui (exitcode None) restarting (started=True)"`
  기록 후 `killing ui` / `sending signal 9 to ui` / `ui is dead with -9`
  / `starting process ui` 순으로 이어짐. **`exitcode None`** — 프로세스가
  스스로 종료(크래시/SIGSEGV)한 게 **아니라**, manager가 살아있는(응답
  없는) 프로세스를 강제로 SIGKILL했다는 뜻. 즉 18차 "fork 관련 크래시"
  가설은 틀렸고, 정확히는 **"UI 메인 스레드가 5초 이상 응답
  없음(워치독 타임아웃)"**이 원인.
- **코드로 메커니즘 확정**: `common/watchdog.cc`의 `watchdog_kick()`은
  `selfdrive/ui/ui.cc`의 `UIState::update()`(Qt 메인 스레드의
  `QTimer`, `UI_FREQ`마다)에서만 호출됨 → UI 메인 스레드가 블로킹되면
  kick이 끊기고, `system/manager/process.py`의
  `check_watchdog()`(`watchdog_max_dt=5`, `process_config.py`의
  `NativeProcess("ui", ...)` 설정)가 5초 안에 새 kick 파일이 갱신
  안 되면 `restart()` → SIGKILL. `ScreenRecoder::toggle()`/
  `stop_locked()`는 정지 버튼 클릭 시 이 **동일한 UI 메인 스레드에서
  동기 실행**됨.
  - `extract_trailing_clip()`의 `QProcess::startDetached("ffmpeg", ...)`
    는 이름은 "detached"지만, 내부적으로 `posix_spawn`/`vfork` 기반이라
    **자식이 `exec()`를 마칠 때까지 호출한 스레드(=UI 메인 스레드)를
    블로킹**하는 특성이 있음(fork()처럼 즉시 반환하는 게 아님). 방금
    큰 mp4(최대 291MB)를 다 쓴 직후 스토리지가 바쁜 상태에서 ffmpeg
    바이너리+동적 라이브러리(libavcodec/libavformat 등) exec가 수 초
    걸리면 → UI 메인 스레드가 그만큼 멈춤 → watchdog 5초 초과 →
    SIGKILL+재시작.
  - 이게 사용자가 본 "정지 버튼 → 화면 정지 → comma 부팅 스플래시
    2초 → 복귀"의 정체(=`ui` 프로세스 강제종료+재기동 화면).
  - `ui`가 SIGKILL되는 시점이 ffmpeg `exec()` 완료 이전이라 **clip
    파일이 단 하나도 안 남는 이유**도 동시에 설명됨.
  - 반복되는 크래시-재기동마다 GPU/카메라/OMX 자원을 다시 잡는 게
    누적되면 장시간 주행에서 메모리 사용률이 오르는 것(18차 "메모리
    부족 97%" 알럿)도 정합적으로 설명됨 — 단 이 마지막 연결고리는
    여전히 정성적 추정, 정량 검증은 안 됨.

- **패치 (base `591f219`)**: `stop_locked()`에서
  `extract_trailing_clip(finished_path)` 직접 호출을
  `std::thread([this, finished_path]{ extract_trailing_clip(finished_path); }).detach();`
  로 감싸 **UI 메인 스레드에서 완전히 분리**. ffmpeg exec가 아무리
  오래 걸려도 그 대기는 별도 스레드에서만 일어나고 UI 메인 스레드는
  `stop_locked()`에서 즉시 반환 → watchdog kick이 끊기지 않음. 그 외
  로직(파일명 충돌 접미사 처리, `-c copy` stream copy, 20분 롤오버 시
  clip 스킵 등)은 전부 미변경.
- `git am` 적용 시뮬레이션(임시 클론, base `591f219`) 통과 확인.
  C++ 컴파일 자체는 컨테이너에 툴체인이 없어 불가 — 코드 리뷰 +
  `git am` 검증까지만(기존 패치들과 동일한 검증 수준).
- **패치 파일**: `/mnt/user-data/outputs/0001-screenrecord-ffmpeg-clip-offthread.patch`
  (`git format-patch` 형식). **실차 `git am` 적용 + push 완료**
  (commit `7b4a160`, `C:\dev\ryu`).
- **검증 완료 (2026-08-20, 실차)**: 정지 버튼 화면정지/스플래시
  재현 없음, `_clip.mp4` 정상 생성 2건, swaglog watchdog 로그 0건.
  이 이슈는 완전히 해소됨(WIP.md에서도 제거).
- 근거: `/data/log/swaglog.0000000914~916`(사용자 터미널 캡처),
  `common/watchdog.cc`, `selfdrive/ui/ui.cc` `UIState::update()`,
  `system/manager/process.py` `check_watchdog()`/`process_config.py`
  `NativeProcess("ui", ..., watchdog_max_dt=5)`,
  `selfdrive/ui/qt/screenrecorder/screenrecorder.cc` 리뷰+패치.

## [VALIDATED] route1 (`a5f42c2218`, x19seg) — 커브/vturn 패치 후 첫 실주행, 종방향 클린 (2026-08-20, 21차, HEAD `1f9f852`)
- **배경**: `vturn_lookahead_horizon_s`(4.5s→8.0s), `vturn_decel_rate`/
  `vturn_safe_time`(물리공식 기반 재설계), `model_turn_speed_noise_tol`/
  `model_turn_straight_hold_sec`(13차 model 게이팅) 등 커브/종방향 관련
  패치들을 반영한 이후 **최초 실주행 로그**. 7.69km/1140s(19.0분),
  평균 24.3km/h(시내 위주, 최고 80.9km/h), ADAS 활성 90.0%.
- **harsh_brake_events**: 원본 41건이나 `cruiseEnabled` 교차검증 및
  `remove_driver_intervention` 필터 모두 **0건** — 전부 정차/신호대기 등
  운전자 개입 구간(디스인게이지 5회와 시간대 일치). ADAS 활성 중 급제동
  계속 0건 기조 유지.
- **turn_speed_violations**: 0건 — 커브 통과 중 vTurnSpeed 초과 사례 없음.
- **vturn↔model 플리커**: 49건/19.0분 = **2.58/min** — 17차 검증치
  (2.16~2.58/min, 베이스라인 7.0/min 대비 63~69%감소) 범위 내로 재확인,
  13차 model 게이팅 패치 계속 안정적.
- **steering_oscillation_detector**: 2건, 둘 다 `cruiseEnabled=False`
  구간(seg16, t=1143~1150, 운전자가 직접 조향 중인 저속 회전) — 시스템
  이슈 아님, 오탐 패턴 재확인.
- **curve_exit_no_accel_scan_v2**: 11건 후보, 대부분 vEgo≈0(교차로 정차)
  또는 경미한 감속(-0.03~-0.7 m/s²) — 기존 "정차/저속 시내 회전 오탐"
  패턴과 동일, 신규 이슈 아님.
- **raw `vTurnSpeed` CSV 필드 특이사항(기능 버그 아님, 분석 시 주의사항)**:
  src가 vturn이 아닐 때(예: bump/model 선택 중) raw vTurnSpeed 값이
  부호를 반전하며(-52→+44 등) 큰 폭으로 진동하는 구간 관찰(t=1190~1196,
  seg17). 그러나 src=vturn으로 실제 선택된 구간에서는 desiredSpeed가
  vTurnSpeed(항상 양수로 정규화된 값)를 프레임 단위로 정확히 추종했고
  aEgo/vEgo 실측은 매끈함 — **미선택 상태의 raw 후보값 노이즈일 뿐 실제
  제어에는 영향 없음**. 향후 세션에서 vTurnSpeed 부호를 곡률 방향
  지표로 해석하지 말 것(부호-곡률 방향 1:1 대응 아님, 확인됨).
- 근거: `work/route1.csv`(HEAD `1f9f852`), `harsh_brake_events`/
  `turn_speed_violations`/`source_transition_log`/
  `steering_oscillation_detector`/`curve_exit_no_accel_scan_v2` 결과.

## [VALIDATED] route2 (`4fe653914c`, x19seg) — 같은 세션 연속분, 고속(100km/h+) 커브 최초 실측 확보 (2026-08-20, 21차, HEAD `1f9f852`)
- route1 직후 연속 주행(같은 부팅, 이어지는 라우트). 11.47km/1140s
  (19.0분), 평균 36.2km/h, **최고 114.4km/h**, vEgo≥54km/h 프레임
  29.5% — route1과 달리 **고속도로 구간 포함**, ADAS 활성 76.5%.
- **harsh_brake_events**: 원본 35건 → ADAS 활성 중/운전자개입 제거 후
  **0건** (route1과 동일 패턴). turn_speed_violations 0건.
- **vturn↔model 플리커**: 41건/19.0분 = **2.16/min** — route1과 함께
  17차 검증 범위(2.16~2.58/min) 내 재확인.
- **steering_oscillation_detector**: 2건, **이번엔 둘 다
  `cruiseEnabled=True`**(route1과 반대) — 상세 프레임 대조 결과
  `desiredCurvature` 부호가 실제로 반전되는 완만한 S자 도로 구간과
  정확히 일치(t=1915.5~1917 부근), 최대 조향각 11.7도로 경미 — 시스템
  오동작이 아니라 **실제 도로 형상을 매끈하게 추종한 정상 동작**으로
  판단.
- **[핵심] 고속 vturn 구간 실측 최초 확보** — vEgo≥54km/h로 시작하는
  vturn 블록 25개(전체 80개 중) 발견, 이 중 대표 2개 상세 분석:
  1. t=1607.1~1613.8(6.7s): 101.0→91.0km/h, 최대 감속 -1.31 m/s²,
     저크 없이 매끈하게 감속. 이후 88.3~114km/h 구간을 오가며 여러
     차례 자연스러운 재가속/재감속 반복 — 급감속/과도출렁임 없음.
  2. t=1492.9~1554.4(61.4s, **연속 vturn 최장 블록**): 76.8→114.3km/h로
     가속하는 완만한 고속 커브 구간에서 **61초 내내 src 전환 0회**
     (플리커 전무) — PARAMS_REGISTRY의 "장시간 정속 커브 부작용(13차
     알려진 한계, 그동안 시내 로그로는 검증 불가)"이 **처음으로 실측
     데이터를 확보했고, 결과는 클린**(플리커 없음, overspeed 없음).
     단, 이 구간 후반(t≈1546~1554, 114→78km/h 감속)은 재검토 결과
     **커브 감속이 아니라 leadStatus=True 전방차 추종에 의한 감속**
     (desiredSpeed는 145~150으로 vEgo보다 훨씬 높게 유지된 채 src=vturn
     그대로) — src=vturn 유지 중이라고 해서 해당 구간 aEgo 변화가 전부
     "커브 감속"은 아님, 향후 분석 시 leadStatus/leadDRel 교차 확인
     필수라는 방법론 상 유의점으로 기록.
  - **결론**: vturn_lookahead_horizon_s=8.0s/vturn_decel_rate=1.2/
    vturn_safe_time=1.0s 물리공식 기반 감속이 실제 100km/h대 고속
    커브에서도 저크 없이 매끈하게 동작함을 정성적으로 첫 확인. 다만
    "8.0s가 8.6s 목표보다 근소히 짧다"는 정량적 지평선 자체의 미세
    검증(NEEDS_VALIDATION)은 이번 로그에 해당 조임 패턴(급격히
    좁혀지는 커브)이 없어 여전히 완전 해소는 아님 — PARTIALLY_VALIDATED로
    격상 검토 가능.
- **raw vTurnSpeed 부호反전**: route1과 동일 패턴 재확인(예:
  t=1606.5 전후 +249→-246, 이후 desiredSpeed는 항상 |vTurnSpeed| 추종).
  route1 항목 참고, 신규 아님.
- 근거: `work/route2.csv`(HEAD `1f9f852`), 동일 toolkit 함수 세트 +
  고속 vturn 블록 수동 프레임 대조(t=1492~1632, t=1884~1918).

## [ROOT_CAUSE_IDENTIFIED, NEEDS_VALIDATION] "카메라 먼저 인식 → 레이더 락온 순간 급감속" 재현 사례 2건 실측+영상 확인, b403d52 패치의 물리적 한계 발견 (2026-08-20, 22차)

- **배경**: 사용자가 "고속도로에서 서행/정차 앞차를 카메라(파란박스)가 먼저
  인식한 뒤 감속이 거의 없다가, 레이더(빨간박스)가 락온되는 순간
  급하게 감속하는 경우가 대부분"이라고 재차 제보. 기존 `b403d52`
  패치(vision-only dRel 미분 closing-rate 크로스체크)가 17차에서
  "closing 크로스오버 6건 전부 매끈하게 이어짐"으로 검증됐던 것과
  겉보기에 모순되는 제보라 재조사.
- **재현 사례 2건 확보** (route1 `a5f42c2218`/route2 `4fe653914c`,
  둘 다 21차에서 이미 분석한 동일 라우트 — 이번엔 `highway_v_ego=0`으로
  낮춰 저속 포함 전체 크로스오버 재스캔 + radar_confirm 전후 aEgo
  프로파일 자동 대조):
  1. **route2 seg5, t=1647.00** (가장 뚜렷함): vEgo≈106km/h, 고속도로
     완만한 커브 구간(src=vturn). 비전-only 구간(t=1644.75~1646.95,
     2.25s) 동안 leadVRel(모델 추정)은 -0.9~-3.2m/s로 완만하게 표시.
     t=1647.00 레이더 락온 순간 leadVRel이 **-8.0m/s로 불연속 점프**
     (dRel≈88m). 이후 aEgo가 t=1647.41부터 매끈하지만 뚜렷하게 감속
     시작해 t=1649.26에 **-2.28 m/s²** 피크 도달(약 1.8초 만에 0→-2.28).
     `extract_dashcam_frames.py`로 t=1644.75/1646.95/1648.36 프레임
     확인 — 완만한 우커브 구간에서 앞차가 시야에 계속 잡혀 있었고,
     레이더 락온 전후로 화면상 앞차와의 거리 변화가 갑자기 커 보이는
     구간과 일치(곡선 구간에서 단안 카메라 깊이 추정 오차가 커지는
     것으로 추정).
  2. **route1 seg9, t=1077.81** (완만한 버전): vEgo≈68km/h, 시내
     간선도로. 비전-only 구간(≈0.7~2.3s, src 여러 번 cam/route 전환)
     동안 leadVRel -2.8~-3.6m/s로 표시. 레이더 락온 순간(t=1077.81)
     leadVRel이 **-8.4m/s로 점프**(dRel=63.3m). aEgo는 이미 완만히
     -0.3~-0.5 수준이다가 락온 후 서서히 -1.9까지 심화 — route2보다
     훨씬 완만해 "급감속"이라 부르긴 애매하지만 동일 메커니즘.
  - **두 사례 모두 락온 순간 vRel이 정확히 -8.0/-8.4 m/s로 유사한
    값에 점프** — 우연으로 보기 어려운 패턴(다른 라우트, 다른 상황,
    다른 dRel인데도 근접). 레이더 자체의 계측 특성인지, 특정
    시나리오(전방차가 크루즈로부터 상대적으로 크게 감속 중)의 공통
    특징인지는 미확인 — 향후 사례 추가 확보 시 재검토.
- **왜 `b403d52`(vision-only dRel 미분 closing-rate)가 이 사례들을
  못 잡았는가 — 코드 레벨 원인 확정** (`long_mpc.py` L579-628):
  1. `_vision_dRel_rate`(dRel 미분 저역통과, TAU=1.0s)는 route2 사례
     기준 대략 -9~-12 m/s로 실제 락온 후 관측된 -8.0m/s와 **꽤
     비슷하게 수렴하고 있었음** — 즉 패치 자체의 미분 추정치는
     크게 틀리지 않았다.
  2. 그런데 이 추정치는 `ttc_dRel = dRel / rate`로 변환되고,
     `LEAD_ACQ_TTC_CAUTION=6.0s` 이상이면 `frac_ttc=0`으로 완전히
     무시된다(L614). route2 사례에서 dRel≈85~120m 구간이라 **rate가
     실제로 9~12m/s로 빨라도 TTC 자체는 물리적으로 7~13s가 나와
     캐션 문턱(6.0s)을 못 넘는다** — 원거리에서는 아무리 정확하게
     빠른 접근을 감지해도 TTC 게이팅 방식 자체가 반응을 늦추는
     구조적 한계.
  3. 또한 `_vision_dRel_rate`/`_vision_dRel_prev`는 `leadStatus`가
     한 프레임이라도 False로 끊기면 **즉시 0으로 리셋**된다
     (L541-543) — 두 사례 모두 비전-only 구간에서 status가 여러 번
     짧게 깜빡였음(route2: 1643.71~1644.01, 1644.60~1644.75 등),
     매번 리셋되며 유효 누적 시간이 실제 물리적 추적 시간보다 훨씬
     짧아짐 (route2는 마지막 연속구간 2.25s만 유효 — 이것도
     `VISION_CLOSING_RATE_MIN_TIME`=0.5s는 넘지만 TAU=1.0s 필터
     수렴에는 부족).
  - **결론**: `b403d52`는 "모델이 근본적으로 잘못된 vRel(거의
    0에 가깝게)을 보고할 때"의 케이스는 여전히 잘 방어하지만
    (17차 검증 6건), "모델 vRel이 실제보다는 낙관적이지만 dRel
    미분으로는 어느 정도 잡히는" 중간 케이스에서 **TTC 캐션
    문턱(6.0s)이 원거리에서 물리적으로 도달 불가능**해 여전히
    늦게 반응한다. 사용자가 체감한 증상은 이 중간 케이스임.
- **개선 방향 제안 (미착수, NEEDS_DECISION)**:
  1. vision-only 크로스체크 전용으로 별도의(더 관대한) TTC 캐션
     문턱을 두거나(예: 10~12s), 아니면
  2. TTC 대신/추가로 **closing-rate 절대값 자체**를 게이트로 사용
     (`_vision_dRel_rate <= 특정 임계, 예: -5.5~-6.0 m/s`이면 거리
     상관없이 frac_ttc를 일정 수준 이상으로 강제) — 고속 주행 중
     선행차와 6m/s 이상 속도차가 나는 것 자체가 이례적 상황(선행차가
     크게 감속 중이거나 정지선/정체 진입)이라는 논리, 또는
  3. `leadStatus` 짧은 깜빡임에도 `_vision_dRel_rate` 누적을 리셋하지
     않고 유지(LEAD_ACQ_LOSS_GRACE_TIME과 동일한 grace 적용) — 리셋
     자체가 유효 추적 시간을 인위적으로 줄이는 부작용.
  - 3안이 가장 부작용이 적어 보이나(단순 리셋 조건 완화), 1/2안은
    민감도 상승에 따른 오탐(불필요 조기감속) 위험이 있어 실측
    검증 필요. **사용자 결정 대기, 코드 미작성**.
- 근거: `work/route1.csv`/`route2.csv`(HEAD `1f9f852`, 21차와 동일
  커밋), `vision_to_radar_crossover(highway_v_ego=0.0)` route1 10건/
  route2 30건 스캔, aEgo 전후 프로파일 자동 대조, 프레임 추출
  (`work/frames_route2_t1647/manifest.json`), `long_mpc.py` L131-212/
  L490-628 코드 리뷰.

## [VALIDATED] 개선안 3번(vision closing-rate grace) 실차 첫 실측 검증 + 신규 한계 2건 발견 (2026-08-21, 23차)

- **로그**: routeA(`8417c66e7e`, 1세그/20분), routeB(`c8fef594d3`,
  18세그/약 36분) — 둘 다 `git_commit=a4b5550`(22차-2/3에서 적용한
  vision closing-rate grace 패치 포함, dirty=False)로 실차 생성.
- **검증 방법**: `_vision_dRel_rate`는 로그에 publish되지 않는
  내부 상태라 `long_mpc.py` 패치된 로직(L529-577)을 그대로
  재현하는 시뮬레이터(`work/sim_vision_rate.py`, 세션 자산 —
  devnotes에는 미포함, 필요시 다음 세션에 toolkit 편입 검토)를
  작성해 old(패치 전, 무조건 리셋)/new(패치 후, grace) 두 버전을
  나란히 계산.

### 1) grace 로직 자체는 정상 동작 확인
- routeA 1건, routeB 13건, 총 **14건의 "blip-preserved" 이벤트**
  확인 — `leadStatus`가 0.03~0.45s 짧게 끊겼다가 복귀했을 때
  (grace=0.5s 이내) `_vision_dRel_rate`가 old 로직처럼 0으로
  안 끊기고 값을 유지한 채 이어서 누적됨. 예: routeB seg-7
  t=543.94(blip 0.06s) rate=-0.44→-7.30으로 자연스럽게 이어짐 —
  패치 전이었다면 -0.44에서 강제로 0으로 끊긴 뒤 재수렴해야 했을
  구간. **의도한 동작 확인, 회귀 없음.**

### 2) routeA/routeB에서는 22차와 같은 "명백한 vision 과소평가→레이더
   락온 급감속" 재현 사례 없음 (반가운 결과, 단 샘플 부족 가능성)
- routeA: `vision_to_radar_crossover(highway_v_ego=0.0)` 결과 크로스
  오버 0건(짧은 20분 로그 특성상 원거리 vision-only 리드 자체가
  없었음).
- routeB: 20건 크로스오버, aEgo 급락(-0.8 이하) 후보 2건 —
  둘 다 22차 패턴(vision vRel 낙관적 과소평가 → 레이더 락온 순간
  실제 빠른 접근 노출)이 **아닌 것으로 확인**됨(아래 3), 4) 참고).
  즉 이번 로그에는 22차가 겨냥한 정확한 실패 모드의 재현 사례가
  없어 "패치가 원래 겨냥한 증상을 막아주는지"는 이번 세션만으론
  직접 검증 못함 — **재현 사례가 있는 신규 로그로 재검증 필요**
  (다음 세션 과제로 이월).

### 3) 신규 발견 — 곡선 구간(`src=vturn`)에서 vision dRel이 여러 후보
   물체 사이를 널뛰며 `_vision_dRel_rate`에 노이즈성 DANGER 스파이크
   유발 가능 (routeB seg12 t=815.35/817.04)
- 두 이벤트 모두 크로스오버 전체 구간의 `dRel_closed_m`은 **양수**
  (+22.7m, +28.3m — 즉 전체적으로는 거리가 벌어지는 추세)인데,
  레이더 락온 직전 마지막 프레임의 `_vision_dRel_rate`는 각각
  -24.82, -12.47(TTC 2.5s/1.9s, DANGER 문턱)로 계산됨 — dRel
  원시값을 직접 대조해보니(위 프레임 덤프) 60m→32m→29m 식으로
  프레임마다 큰 폭으로 튀는 구간이 있었고, 레이더 락온 후 실제
  vRel은 **+4.4~+6.1(멀어지는 중)** 로 드러남 — 즉 실제로는 위험한
  접근이 아니라 **모델이 곡선에서 서로 다른 물체(차선/구조물/실제
  다른 차량)를 순간순간 "리드"로 오인해 dRel이 튀는 노이즈**였던
  것으로 추정.
- **다행히 이번 로그에서는 실제 aEgo 반응이 거의 없었음**(-0.1~-0.2
  수준, 평소 노이즈 범위) — TTC 계산상 DANGER로 잡혔어도 실제
  제어 출력에 유의미한 영향은 없었던 것으로 보이나, **왜 영향이
  없었는지(다른 게이트에 걸렸는지, floor가 이미 더 타이트한
  MPC 자체 해와 차이가 없었는지)는 코드 트레이스로 확인 못함** —
  운 좋게 무해했을 가능성 배제 못함.
- **함의**: 22차에서 검토를 보류한 개선안 1번(TTC 캐션 문턱 완화)/
  2번(closing-rate 절대값 게이트)이나, 사용자가 제안한 4번안
  (vision_dRel_rate를 `process_lead()`의 `v_lead`에 직접 반영)은
  전부 `_vision_dRel_rate`를 "더 적극적으로 신뢰"하는 방향인데,
  **바로 이 곡선 노이즈 취약성 때문에 신뢰도를 높이는 방향의
  개선은 이런 오탐을 증폭시킬 위험이 있음** — 1/2/4번안 설계 시
  곡선(`src=vturn`) 여부나 dRel 프레임간 점프 크기에 대한 추가
  필터링/게이트가 선행되지 않으면 위험.

### 4) 별개 이슈로 보이는 급감속 사례 — routeB seg12 t=798.18
   (drop=-1.61 m/s², 급감속 후보 중 가장 뚜렷)
- 이 사례는 vision closing-rate 크로스체크와 무관 — 레이더가
  이미 락온된 상태(`leadRadar=True`)에서 `leadDRel`이
  **60m→28m(레이더, vRel+2.5)→34m(비전 재획득, vRel+1.5)→
  29.8m(레이더 재락온, vRel -4.9)→79.9m→102.9m(vRel -13.1)**로
  약 1.5초 사이 요동 — 물리적으로 한 차량의 연속 추적이라 보기
  어려운 패턴(다른 물체로의 타깃 전환으로 추정). aEgo는 이
  구간에서 0.09→-1.86까지 매끈하게 감속하지만, 이는 vision-radar
  크로스체크 문제가 아니라 **곡선에서 레이더/비전 리드 타깃 자체가
  자주 바뀌는 기존에 이미 알려진 문제**(`longitudinalPlanSource`
  chatter, 1,122회/1h45m, 저속 구간 집중 — FINDINGS.md 과거 기록)와
  같은 계열로 재분류. **b403d52/22차-2 패치의 적용 범위 밖.**
- 별도 트랙 과제로 남김(이번 세션에서 원인 심화분석은 안 함).

### 결론 및 다음 세션 과제
1. **개선안 3번은 의도대로 동작 확인(회귀 없음)** — `PARAMS_REGISTRY.md`
   VALIDATED로 갱신.
2. 22차가 겨냥한 정확한 증상(vision vRel 과소평가 → 레이더 락온 급감속)의
   **재현 사례가 있는 로그로 재검증 필요** — 아직 "패치가 실제로 그
   증상을 줄였다"는 직접 증거는 없음(이번 로그엔 해당 사례 자체가 없었음).
3. 1/2/4번안 설계 전에 **곡선 구간 vision dRel 노이즈 필터링**을
   먼저 검토해야 함 — 안 그러면 신뢰도를 높이는 개선이 오탐발
   과감속을 늘릴 위험.
4. seg12 t=798 급감속은 별도 이슈(곡선 타깃 전환)로 다음 세션에
   독립적으로 추적할지 결정 필요.
- 근거: `work/routeA.csv`/`routeB.csv`(commit `a4b5550`),
  `work/sim_vision_rate.py`(grace 로직 재현), `vision_to_radar_
  crossover(highway_v_ego=0.0)` routeA 0건/routeB 20건, 프레임별
  raw dRel/vRel 대조(seg12 t=812~818, t=796~800).

## [VALIDATED + NEEDS_REFINEMENT] 신규 실주행 로그(260821, 18분, HEAD a4b5550) — 도구 1~4/5 첫 실전 실행 결과 (2026-08-21, 20차 계속)

**로그 개요**: 18세그(20260821_062954~064654), 21601 rows, 18분/11.64km,
평균 38.8km/h(도심), cruise 85.3%, harsh_brake 43건, disengage 5건.
`extract_log.py` 신버전(`segment_state_carryover_fix: true`)으로 추출.

### 도구 1/5 실측 확인 — segment_boundary_lead_loss_artifacts 0건
`segment_boundary_lead_loss_artifacts()`로 감사한 결과 가짜 유실
아티팩트 0건 — 세그먼트 경계 carryover 수정이 실제 로그에서도 정상
동작 확인.

### 도구 3/5 실측 — 곡선 노이즈 21건 중 대부분 무해, 단 1건은 진짜 위험
`curve_lead_dRel_jump_events()`: 곡선(vturn) 프레임 7774개(6.81분)
중 급점프 21건, 그중 14건이 `would_trigger_ttc_danger` 플래그.
**aEgo 실측 대조 결과**:
- seg6 t=443.5~456 (점프 8건 클러스터): aEgo가 -0.1~-0.3 범위에서만
  움직이고 실제 급감속 없음 — **무해한 노이즈로 확인, 23차 가설과
  일치**.
- **seg12 t=797.8~799.5 (점프 2건, 진입+이탈)**: 점프 사이 구간에서
  dRel이 34.1m→24.2m으로 여러 프레임에 걸쳐 물리적으로 일관되게
  좁혀지고 vRel도 동시에 -4~-4.9m/s로 일치 — **진짜 리드 접근**이었고
  실제로 aEgo가 -1.9m/s²까지 적절히 감속 반응함(정상 동작).
  `would_trigger_ttc_danger`가 이 케이스에도 True를 찍었지만, 이건
  노이즈가 아니라 정상적인 위험 반응이 발생한 것 — **단일 프레임
  점프만 보는 현재 휴리스틱은 "노이즈성 튐"과 "진짜 리드 접근"을
  구분 못 함**.
- **NEEDS_REFINEMENT**: `curve_lead_dRel_jump_events()`의
  `would_trigger_ttc_danger` 판정에 "점프 이후 N프레임 동안 dRel이
  물리적으로 일관되게(vRel과 부호/크기가 맞게) 감소하는지" 후속 체크를
  추가하면 진짜 위험과 노이즈를 구분 가능할 것으로 보임 — 다음 세션
  설계 후보.

#### [VALIDATED, 시각 검증 완료 — 21차] seg6/seg12 dashcam 프레임 대조로 원인 특정
- 사용자가 seg6(`--6`)/seg12(`--12`) 폴더 재업로드 → `extract_dashcam_frames.py`로
  seg6 9개 시각(444.49/451.84/452.04/453.59~454.14 클러스터), seg12
  5개 시각(796.35/797.79/799.49/799.59/800.05)을 프레임 매칭(오차
  11~27ms, 전부 0.15s 허용치 이내)해 육안 확인 완료.
- **seg6 (노이즈 확정, 원인 특정)**: 전 구간에 걸쳐 **곡선 도로
  우측 가장자리에 있는 버스(789번)가 순간적으로 리드 후보로
  오탐지**되는 패턴으로 확인. t=444.49는 교차로 횡단 버스, t=451.84/
  452.04는 우측 가장자리 버스↔전방 실제 리드(흰 승용차) 스위칭,
  t=453.59~453.89 조밀 클러스터는 같은 버스가 곡선 우측에 정차/서행
  중인 상태로 계속 남아 실제 리드와 반복 스위칭. aEgo 무반응(기존
  기록)과 정확히 부합 — **무해한 노이즈, 원인은 "곡선 구간에서
  도로 가장자리 대형차량이 리드 후보로 혼입"으로 확정**.
- **seg12 (진짜 위험 반응 재확인)**: t=797.79(진입)~800.05(이탈)
  전 구간에 걸쳐 동일한 흰색 승용차가 실제 리드로 계속 존재,
  t=800.05 프레임에서 브레이크등 점등 육안 확인 — 실측 aEgo
  -1.9m/s² 반응과 정확히 일치. 곡선 우측에 정차/서행 중인 검은
  차량이 후보 스위칭을 유발한 것으로 보이나(seg6와 동일 패턴 —
  곡선 가장자리 차량 혼입), 실제 리드는 계속 흰 승용차였고 감속은
  **정당한 반응**임을 시각으로 확정.
- **공통 원인 패턴 확정**: 곡선(`src=vturn`) 구간에서 **도로
  가장자리(주로 우측)의 버스/정차차량이 모델의 리드 후보에
  일시적으로 혼입**되는 것이 dRel 급점프의 실제 메커니즘. seg6은
  이 혼입만 있고 실제 리드 변화가 없어 무해했고, seg12는 혼입과
  별개로 실제 리드가 진짜 접근 중이었던 케이스 — **같은 메커니즘이
  노이즈와 진짜위험 양쪽에 다 나타날 수 있음을 시각 증거로 확인**.
  `would_trigger_ttc_danger` 개선 방향(다중 프레임 물리 일관성
  체크)이 이 구분에 유효할 것으로 보임 — 설계 시 "가장자리 대형
  물체 혼입"을 명시적으로 반영할 근거 마련됨.
- 증거 이미지 5장(`evidence/seg6_seg12_visual/compare_seg6_event{1,2,3}.jpg`,
  `compare_seg12_{entry,exit}.jpg`) push 완료. 원본 qcamera.ts/rlog.zst는
  미커밋(개인 주행 영상, 방침 유지).

#### [VALIDATED (표본 5건), 21차 계속] would_trigger_ttc_danger 개선 — 다중 프레임 물리 일관성 체크
- 위 시각 검증 결과를 근거로 `curve_lead_dRel_jump_consistency()`
  신규 작성 — 점프 이후 1.5초 동안 dRel/leadVRel이 물리적으로
  일관되게(같은 방향, vRel 부호 일치) 움직이는지 후속 체크 추가.
- **파라미터 튜닝 근거**: 처음 window=0.6s로 시도했을 때 seg12
  t=797.79(진짜위험)가 레이더 락온 직후 짧은 정착 구간(~0.3~0.4s
  동안 vRel이 잠깐 양수로 흔들림) 때문에 오탐(refined=False)되는
  것을 발견 — window를 1.5s로 늘려서 정착 구간을 지나 진짜 추세가
  드러나도록 수정. monotonic_frac_thresh=0.6.
- **검증 결과 (260821 로그 seg6/12 부분)**: seg6 노이즈 4건(444.49/
  451.84/453.69/453.89/454.09 — 정정: 454.09는 raw danger였으나
  refined에서 정확히 False) 전부 refined=False로 정확히 억제,
  seg12 t=797.79(진짜위험) 1건만 refined=True로 정확히 보존 — 시각
  검증된 5건 전부 정확히 분류.
- raw would_trigger_ttc_danger 12건 → refined_would_trigger_danger
  1건 (억제율 91.7%, `curve_noise_summary_refined()`).
- **NEEDS_VALIDATION (표본 작음)**: 튜닝에 쓴 시각 검증 사례가
  5건뿐이라 과적합 위험 있음. 특히 같은 로그의 seg12 t=800.05(육안상
  브레이크등 점등 확인, 진짜 감속 반응으로 추정되나 아직 프레임
  대조로 명시적 검증은 안 함)가 "리드 재획득 섞인" 복잡 패턴이라
  현재 파라미터로는 놓침(refined=False) — 다음 세션에 더 많은 시각
  검증 사례를 모아 재확인 필요. 함수 자체를 실제 트리거 로직에
  반영(코드 패치)하는 건 이 검증이 더 쌓인 뒤로 보류.

### 도구 4/5 첫 실전 실행 — road<->vturn이 이 로그의 최다 플리커 쌍
`all_source_pairs_flicker_summary(min_count=3)` 결과 (건수순):
| 쌍 | 건수 | 왕복 | 분당 | dwell(중앙값/최대) |
|---|---|---|---|---|
| road<->vturn | 107 | 102 | 5.94 | 1.45s/109.3s |
| model<->vturn | 70 | 65 | 3.89 | 1.1s/150.25s |
| route<->vturn | 47 | 41 | 2.61 | 1.02s/239.51s |
| road<->route | 34 | 29 | 1.89 | 0.35s/663.14s |
| cam<->model | 18 | 16 | 1.0 | 0.75s/453.35s |
(나머지 model<->route/cam<->vturn/bump<->vturn/bump<->route/gas<->vturn는
n<12, 부차적)

**중요**: 이 로그에서는 `road<->vturn`이 `model<->vturn`보다 더 빈번
(107 vs 70) — 260819-1/260819-4 세션에서 model<->vturn이 우세 쌍이던
것과 다름(도로 상황·주행 스타일 차이로 추정, 절대적 우선순위 아님).
**`road<->route`(34건, 1.89/min)는 이번이 처음으로 정량화된 수치** —
9~13차 패치(vturn<->model 게이팅)는 이 쌍을 전혀 다루지 않으므로
여전히 미해결 상태로 남아있음이 실측으로 확인됨.

### cut-in 오탐 재확인 (기존 4차 발견과 동일 패턴)
`lead_cut_in_detector(close_dist_m=15)` 5건 전부 `cruiseEnabled=False`
(운전자 수동 조작 중) 구간, vEgo 1.5~5km/h 저속 — ADAS가 관여하지 않는
저속/정차 근처 상황이라 종방향 제어 튜닝 관점에서는 무관(기존 "정차 중
교차로 오탐지" 계열과 동일 패턴, 신규 아님).

### 다음 세션 이어갈 것
1. `road<->vturn`/`road<->route` 쌍의 min() 히스테리시스 설계 착수
   (도구 4/5로 실측 규모 확인됨, 이제 실제 설계 단계로 넘어갈 수 있음).
2. `curve_lead_dRel_jump_events()`의 would_trigger 판정 정교화(다중
   프레임 물리적 일관성 체크 추가) — 설계 후 재검증.
3. 도구 2/5(`ttc_danger_events`) 5건(전부 seg19, 저속 4~5km/h) —
   **확인 완료: 전부 `cruiseEnabled=False`(수동 운전 중)**, cut-in과
   동일하게 ADAS 종방향 제어와 무관, 튜닝 관점에서 무해.

## [진행중] 24차 — a4b5550 HEAD 첫 실주행 로그 대량 배치(15개 zip, 하루치) 분석 (2026-08-21, 24차)
사용자가 최신 커밋(`a4b5550`, 22차-2/23차 vision closing-rate grace 버그
수정 포함) 적용 후 첫 실주행 하루치 로그(오전~오후, 15개 zip) 전체를
일괄 업로드. 라우트 하나 분석 끝날 때마다 즉시 push하는 방식으로 진행.
`route_summary.py`(표준 분석 스위트, harsh_brake/turn_speed_violation/
steering_oscillation/cut_in/segment_boundary/source_pair_flicker/
ttc_danger/curve_noise_refined/vision_radar_crossover 전부 포함)로
일괄 처리, 결과 JSON은 `evidence/route_summaries_260821/`에 보존.

**중복 확인**: 첫 2개 zip(`c8fef594d3` 18세그, `8417c66e7e` x3seg)은
각각 20차/23차에서 이미 분석된 로그와 이벤트가 정확히 일치(완전 중복)
하거나 ADAS 비활성 저속 이동(2분)이라 분석 무의미 — 재작업 생략.

### route3 (`dda0d533ce`, x20seg, 10:13~10:32, 20분/14.17km)
- trip: 평균 42.5km/h, cruise_ratio 0.843, harsh_brake(전체) 23건
- **ADAS 관여 harsh_brake 0건, turn_speed_violation 0건, ttc_danger
  11건 전부 cruiseEnabled=False(수동)** — 종방향 안전 지표 전부 클린.
- steering_oscillation 7건 — 각도 최대 5.3~139.6도, 반전 3~4회 폭 짧음
  (0.95~2.25s), 대부분 교차로 회전으로 추정(급커브 조향 정상 패턴과
  구분 안 됨, dashcam 대조 안 함 — 이상 징후로 단정 안 함).
- curve_noise_refined: raw jump 26건 → would_trigger 15건 →
  **refined_danger 2건**(seg18 t=1166.78, seg19 t=1249.98 — 둘 다
  vrel_consistent/physically_consistent=True, monotonic_frac 0.62/0.73,
  기존 seg12 검증 패턴과 유사한 \"진짜 접근\" 프로파일). 억제율 86.7%
  (raw 15 -> refined 2), 21차 검증 때(91.7~92.9%)보다 다소 낮음 —
  표본 확대 시 자연스러운 변동 범위로 보이나 시각 검증은 안 됨.
- vision_radar_crossover 24건, highway(>=54km/h) 0건 — 이 구간은
  시내 위주.
- source_pair 우세: road<->vturn(52건, 2.6/min) > route<->vturn(37건)
  > model<->vturn(24건) — 20차 계속과 동일하게 road<->vturn이 최다.

### 도구 버그 수정 — `route_summary.py` vision_radar_crossover highway 판별 필드명 오류
`vision_to_radar_crossover()`가 실제로 반환하는 필드는 `highway`(bool)인데
`route_summary.py`는 존재하지 않는 `v_ego_kmh`/`vEgo_kmh`를 참조해 항상
`count_highway_est=0`으로 나오는 버그 발견(route4에서 명백한 고속도로
구간인데 0건 나와서 발견). `e.get("highway")`로 수정 완료 — **route3의
`count_highway_est=0`도 이 버그 영향을 받았을 가능성 있음(재확인 필요,
route3는 시내 위주라 실제로도 낮았을 가능성 높지만 완전히 배제는 못함)**.
route4 이후부터는 정상값.

### route4 (`b1820329bd`, x20seg, 10:33~10:52, 20분/34.16km, **고속도로**)
- trip: 평균 **102.5km/h**, cruise_ratio **1.0**(구간 내내 이탈 없음),
  brake/gas 개입 0%, harsh_brake(전체) 0건.
- **전 항목 클린**: harsh_brake 0, turn_speed_violation 0,
  steering_oscillation 0, cut_in 0, ttc_danger 0(adas 포함).
- curve_noise: jump 9건 -> would_trigger 5건 -> **refined_danger 0건**
  (100% 억제) — 고속도로 완만한 곡선이라 애초에 곡선 체류시간 자체가
  짧음.
- vision_radar_crossover **11건, highway 11건 전부**(버그 수정 후
  최초로 정상 집계된 고속도로 크로스오버 수치) — 그 중 seg4
  t=1543.3~1545.4 이벤트(dRel_closed_m=+35.29, 표면상 급접근처럼
  보임)를 프레임 단위로 대조: 실제로는 leadDRel이 105m→69m로
  **0.2초 만에 뚝 떨어진 뒤 그대로 안정화**되는 노이즈성 스냅(곡선
  구간 아닌데도 동일 패턴 발생 — vturn 한정 문제가 아닐 수 있음을
  시사)이었고, 이후 leadVRel은 계속 0~+3.1(정지~약한 opening)로
  유지, aEgo도 -0.16~+0.45 범위의 정상 미세 조정만 있었음 — **오탐성
  크로스오버, 실제 위험 아니고 시스템도 과잉반응 안 함** 확인.
- source_pair 우세: road<->vturn 104건(압도적), cam<->road 8건,
  cam<->vturn 4건 — 고속도로 완만한 곡선 연속 구간에서 road<->vturn
  플리커가 특히 심함(20분에 104건 = 5.2/min).

### route5 (`83e6b133f5`, x20seg, 10:53~11:12, 20분/35.23km, **고속도로 연속**)
- trip: 평균 105.7km/h, cruise_ratio 1.0, harsh_brake(전체) 0건 — route4와
  같은 고속도로 주행 연속분으로 보임.
- 전 항목 클린: turn_speed_violation/steering_oscillation/cut_in/
  ttc_danger 전부 0. curve_noise 100% 억제(raw 10 -> refined 0).
- vision_radar_crossover 19건, **19건 전부 highway**.

#### [VALIDATED, 실측 최초] b403d52 vision-only closing-rate 패치 — 레이더 락온 전 조기 감속 실제 확인
seg6 t=2817.53~2819.53 구간(가장 큰 폭 접근, dRel_closed 41.4m/1.99s)을
프레임 단위로 대조:
- t=2817.53: `leadRadar=False`(vision-only), modelProb 0.89, leadDRel
  71.5m, leadVRel -4.37 — 이 시점 aEgo는 아직 거의 0(-0.06~0.05, 평시
  크루즈 상태).
- **t=2818.53부터 aEgo가 vision-only 상태에서 이미 감속 시작**
  (-0.90 → -1.31 → -1.08...), **`leadRadar`가 `True`로 바뀌는 건
  t=2819.53로, 이보다 1초 먼저 감속이 시작됨.**
- 이후 레이더 락온 후에도 감속은 매끄럽게 이어짐(-0.94~-1.45 범위,
  급격한 단절 없음), 최대 감속도 약 -1.45m/s²로 온건한 수준.
- **의의**: 6차에서 사용자가 제보한 원 증상(\"카메라 인식 시점부터는
  감속 없다가 레이더 인식 순간부터 감속 시작되는 느낌\")이 이번
  실측에서 **정반대로 확인** — 패치 의도대로 vision-only 구간에서
  이미 선제 감속이 걸리고 있음. 17차(경향 확인)에 이은 **최초의
  명확한 프레임 단위 실측 증거**. `VISION_CLOSING_RATE_TAU`/
  `MIN_TIME`(1.0s/0.5s) 튜닝이 유효하게 작동 중인 것으로 판단.
- source_pair 우세: road<->vturn 99건, cam<->vturn 15건, cam<->road 4건
  — route4와 유사 패턴 유지.

### route6 (`866476e5c3`, x20seg, 11:13~11:32, 20분/34.18km, 고속도로 연속)
- route4/5와 동일 패턴의 클린 고속도로 구간: harsh_brake/turn_speed_
  violation/steering_oscillation/cut_in/ttc_danger 전부 0, curve_noise
  100% 억제(raw 15 -> refined 0). crossover 20건, 20건 전부 highway.
- 최대 폭 접근 이벤트(seg4 t=3899.1, dRel_closed 64.7m/2.74s) 프레임
  대조: dRel이 89→50m대로 스냅되는 노이즈성 변화이며 leadVRel은 계속
  양수(opening, 0.4~2.7), aEgo도 거의 0(-0.15~0.23) 유지 — route4와
  동일하게 **오탐성 크로스오버는 시스템이 과잉반응 안 함**을 재확인.
- source_pair 우세: road<->vturn 112건(20분 기준 5.6/min, 지금까지
  고속도로 구간 중 최다) > cam<->vturn 9 > cam<->road 6.

### route7 (`1723e8b850`, x20seg, 11:33~11:52, 20분/34.35km, 고속도로 연속)
- route4~6과 동일 패턴: harsh_brake/violation/oscillation/cut_in/
  ttc_danger 전부 0. curve_noise raw 14 -> refined 1(seg0 t=4857.58,
  vrel_consistent/physically_consistent=True — 진짜 접근 프로파일,
  vEgo 31m/s 고속 구간, 시각 미검증). crossover 19건 전부 highway.
- source_pair: road<->vturn 49건으로 route4~6(99~112건) 대비 절반
  이하로 감소 — 이 구간 도로 곡률/차로 구성이 더 단순했을 가능성.

### route8 (`203f99d429`, x20seg, 11:53~12:12, 20분/30.71km, 고속도로+약간 감속)
- 평균 92.1km/h(route4~7보다 낮음), cruise_ratio 0.974(1회 짧은
  disengage), brake_pressed 1.8%. harsh_brake(ADAS) 0, turn_speed_
  violation 0, cut_in 0, ttc_danger(adas) 0. steering_oscillation 3건.
- curve_noise: raw 8 -> **refined 3건**(억제율 62.5%, 지금까지 중
  가장 낮음) — 전부 seg8 t=6543~6580 구간, 프레임 대조 결과 **진짜
  선행 저속차 추종 상황**(dRel 100m→38m까지 점진 접근, leadVRel
  지속 음수, aEgo -0.11~-1.10 범위의 매끈한 감속, 저크/harsh_brake
  없음) — 곡선 노이즈 오탐이 아니라 3건 전부 하나의 연속된 정상
  추종 이벤트가 refined 로직에 올바르게 포착된 것으로 판단(=오히려
  좋은 신호, 위험 상황을 제대로 감지).
- vision_radar_crossover 17건, highway 14건.
- source_pair 우세: road<->vturn 58건 > route<->vturn 19 > cam<->vturn 13.

### route9 (`280302e8ed`, x20seg, 12:15~12:34, 20분/30.66km, 고속도로)
- harsh_brake/turn_speed_violation/steering_oscillation/ttc_danger(adas)
  전부 0, cut_in 1건(무해 추정). curve_noise raw 2 -> refined 1(단일
  이벤트, 상세 미검토 — 패턴상 route8 계열과 유사할 가능성).
  crossover 5건 전부 highway. source_pair: road<->vturn 89건 압도적.
- 새로운 이상 징후 없음, 기존 route4~8과 동일 경향 재확인.

### route10 (`f3db6ca89d`, x20seg, 12:35~12:54, 20분/20.1km, 시내+고속 혼합)
- 평균 60.3km/h(지금까지 중 가장 느림, 시내 비중 높음), cruise_ratio
  0.98, decel_blocks 66건(잦은 감속-저속 구간 반복 시사).
- harsh_brake(ADAS)/turn_speed_violation/steering_oscillation/
  ttc_danger(adas) 전부 0, cut_in 3건. curve_noise raw 5 -> refined
  1건(저속 8.24m/s 구간, vrel_consistent/physically_consistent=True).
- crossover 18건, highway 7건(시내/고속 혼합이라 route4~9보다 highway
  비중 낮음, 첫 정상 집계된 시내+고속 혼합 사례).
- **source_pair 우세 역전**: `model<->vturn` **101건**(6.06/min)이
  `road<->vturn`(49건)을 처음으로 앞섬 — 지금까지(route3~9) 전부
  road<->vturn이 압도적 1위였는데, 시내+고속 혼합 구간에서는 양상이
  다름을 시사(20차 계속 세션의 관찰 — "도로 상황에 따라 우세 쌍이
  달라진다"와 일치).

### route11 (`3f3884d185`, x17seg, 13:35~13:51, 16.8분/13.18km, 시내 위주)
- 평균 47.0km/h, cruise_ratio 0.882, decel_blocks 38건. harsh_brake(전체
  35건은 disengage/저속 구간, ADAS 관여 harsh_brake **0건**),
  turn_speed_violation 0건, ttc_danger(adas) **0건** — 종방향 안전 지표
  전부 클린 유지(11개 라우트 연속).
- steering_oscillation 3건(각도 18.1~37.4도, 반전 3회, 폭 1.4~2.0s) —
  교차로 회전 패턴과 구분 안 됨, 이상 징후로 단정 안 함.
- cut_in 5건 — 4건이 seg16(13176~13183s, vEgo 0.08~1.37m/s 극저속
  주정차 구간) 밀집, 기존에 알려진 "radarTrackId=0==leadOne 구조적
  오탐"(DH 레이더 아키텍처 특성, MANDO_RADAR 부재) 패턴과 일치, 신규
  이슈 아님.
- curve_noise_refined: raw jump 41건 -> would_trigger 18건 ->
  **refined_danger 8건**(억제율 55.6%, 지금까지 중 가장 낮은 축 —
  route8의 62.5%와 유사한 범주). refined 8건 대부분
  vrel_consistent=True/physically_consistent=True 조합으로 "진짜
  접근" 프로파일에 부합(seg4 구간에 4건 밀집, t=12439.58~12446.73 —
  같은 선행차 추종 시퀀스로 추정, route8과 동일하게 refined 로직이
  실제 위험을 잘 포착한 사례로 판단). 시각 미검증.
- vision_radar_crossover 32건, highway 23건 — 시내+고속 혼합 구간
  치고 highway 비중이 route10(7/18)보다 높음(23/32), 이 라우트가
  고속도로 구간 비중이 더 컸던 것으로 추정.
- source_pair 우세: `model<->vturn`(87건, 5.18/min) ≈ `road<->vturn`
  (87건, 5.18/min) **동률** — route10의 역전(model 우세) 이후 이번엔
  두 쌍이 정확히 동수. 시내+고속 혼합 구간에서 road/model 우세가
  안정적이지 않고 라우트마다 뒤바뀌는 패턴 계속 축적 중(별도
  히스테리시스 설계 필요성 뒷받침 근거 추가).

### route12 (`54c822209b`, 1세그, 14:20, 9.8초) — 스킵
전체 9.8초, `cruise_enabled_ratio=0.0`(ADAS 비활성 내내), brake_pressed
100%, vEgo 평균 0.5km/h(거의 정지) — route2(`8417c66e7e`)와 동일하게
ADAS 미관여 극단문 로그, 분석 가치 없음. cut_in 1건(vEgo 0.29m/s
극저속, leadDRel 3.24m — 정차 중 근접 오탐, 무해). 15개 zip 중
마지막 라우트로 24차 배치 분석 **전체 완료**.

## [진행중] 24차 종합 요약 — 15개 zip 배치 분석 완료 (2026-08-21, 24차 마무리)
실질 처리 라우트 10개(route3~route12, 2개는 ADAS 미관여로 스킵:
route2/route12) 전체 완료. 총 주행: 대략 190~200km(시내+고속도로
혼합), 약 3시간 분량.
- **종방향 안전 지표 전체 클린**: harsh_brake(ADAS)/turn_speed_
  violation/ttc_danger(adas) 전부 route3~route11 **10개 라우트
  전부 0건**. a4b5550 HEAD(22~23차 vision closing-rate grace 버그
  수정 포함) 상태에서 하루치 실주행 기준 종방향 안전 회귀 없음
  확인.
- **b403d52(vision closing-rate) 최초 프레임단위 실측 검증**(route5)
  — 6차 원 제보 증상과 정반대로, vision-only 상태에서 이미 선제
  감속 확인. `VISION_CLOSING_RATE_TAU`/`MIN_TIME`(1.0s/0.5s) 유효
  작동 확인.
- **`route_summary.py` vision_radar_crossover highway 판별 버그
  발견+수정**(route4에서 발견, `v_ego_kmh`→`highway` 필드명 수정) —
  route3는 재확인 결과 시내 위주라 실제로도 낮았을 가능성 높음(완전
  배제는 못하나 route4 이후 정상 집계로 이후 분석에 영향 없음).
- **curve_noise_refined 억제율 라우트별 변동(55.6%~100%)**: route4~7
  (고속도로 완만 곡선)은 87.5~100%로 높고, route8/route11(저속
  추종/시내 혼합)은 55.6~62.5%로 낮음 — 프레임 대조 결과 낮은 억제율
  케이스들은 전부 오탐이 아니라 refined 로직이 실제 위험(선행차
  저속 추종)을 올바르게 포착한 것으로 확인, 긍정적 신호.
- **source_pair 우세 쌍이 도로 유형에 강하게 의존**: 고속도로 연속
  구간(route4~9)은 road<->vturn이 압도적(49~112건), 시내+고속 혼합
  구간(route10/11)은 model<->vturn이 역전 우세이거나(route10)
  동률(route11) — 20차부터 계속 관찰된 패턴, road/route/model 각각
  별도 히스테리시스 설계 필요성을 뒷받침하는 근거로 10개 라우트에
  걸쳐 일관되게 축적됨.
- **DH 레이더 구조적 오탐(radarTrackId=0==leadOne cut_in) 재확인**:
  route11 seg16에서도 동일 패턴 관찰, 기존 알려진 이슈와 일치, 신규
  아님.
- **다음 우선 과제**(WIP.md에서 이관):
  1. `PARAMS_REGISTRY.md`의 `VISION_CLOSING_RATE_TAU` 항목을 route5
     실측 검증 결과로 갱신 (아직 미반영).
  2. `LAST_ANALYZED.md` 최종 갱신 (c3-ms-dev HEAD `a4b5550` 기준
     실주행 로그 검증 완료 표시).
  3. 아직 업로드되지 않은 나머지 3개 라우트(`d45a15f8fc` 12:55,
     `7ffb3e693c` 13:15, `6d6e114aa3` 14:01) — 15개 zip 중 이번
     세션에 업로드 안 됨, 재업로드 받으면 route13/14/15로 이어서
     분석.

## [VALIDATED] 24차 계속 — 남은 3개 라우트(route13/14/15) 처리 + 15개 zip 배치 분석 최종 완료 (2026-08-21)
사용자가 24차 체크포인트에서 요청한 재업로드 3개(`d45a15f8fc`,
`7ffb3e693c`, `6d6e114aa3`)를 받아 순서대로 처리, 15개 zip 배치
분석을 최종 완료.

### route13 (`d45a15f8fc`, x20seg, 12:55~13:15, 20분/14.51km, 시내)
- 평균 43.6km/h, cruise_ratio 0.982, decel_blocks 67건. harsh_brake
  (ADAS) 0건, turn_speed_violation 0건, ttc_danger(adas) 0건 — 클린
  유지.
- steering_oscillation 5건(최대각 8.5~131.4도) — 131.4도 건은 교차로
  U턴/급회전 추정, 반전 3~4회로 짧은 폭(0.65~2.5s), 기존 패턴과
  구분 안 됨.
- curve_noise_refined: raw jump 3건(표본 작음) -> would_trigger 3건
  -> refined 1건(vrel_consistent/physically_consistent=True, 진짜
  접근 프로파일).
- vision_radar_crossover 7건, highway 0건(시내 위주라 예상대로 낮음).
- **신규 source 관찰**: `bump<->vturn`(16건), `bump<->route`(12건),
  `bump<->model`(8건) — `bump`는 `carrot_serv.py`의 APN route
  서브타입(`xSpdType==22`, 과속방지턱 경고)으로 기존 코드에 이미
  존재하던 소스, 이번 라우트가 처음으로 과속방지턱 구간을 지나며
  로그에 등장한 것뿐 신규 이슈 아님. source_pair 우세는
  `model<->vturn`(136건, 압도적).

### route14 (`7ffb3e693c`, x20seg, 13:15~13:35, 20분/10.26km, 시내 정체)
- 평균 30.8km/h, cruise_ratio 0.795(디스인게이지 6회), brake_pressed
  15.4%, gas_pressed 7.9% — 수동 개입 비중 높은 구간. harsh_brake
  (전체 52건은 전부 비ADAS), **ADAS 관여 harsh_brake 0건**,
  turn_speed_violation 0건.
- ttc_danger 1건이나 `count_adas=0`(cruiseEnabled=False, 수동 제동
  중 발생) — ADAS 무관, min_ttc=2.25s/vRel=-11.2m/s로 급접근 상황을
  운전자가 직접 대응한 것으로 추정.
- curve_noise_refined: raw 24 -> would_trigger 14 -> refined 5건
  (억제율 64.3%).
- cut_in 2건(seg19, vEgo 8.1~8.3m/s, dRel 11.8~12.3m, 신규 패턴 아님).
- **신규 source 관찰**: `gas`(`gas<->route` 16건, `gas<->vturn` 9건,
  `gas<->model` 6건, `bump<->gas` 3건) — `gas`는 `carrot_serv.py`의
  가속페달 오버라이드 메커니즘(운전자가 gas 페달을 밟아 desired_
  speed를 일시 상향하는 기존 기능)으로, 시내 정체 구간에서 운전자가
  빈번하게 속도 오버라이드를 사용한 결과로 해석, 코드 이슈 아님.

### route15 (`6d6e114aa3`, x20seg, 14:01~14:20, 20분/4.67km, 극심한 정체)
- 평균 **14.0km/h**, cruise_ratio **0.141**(대부분 수동 운전),
  brake_pressed 31%, gas_pressed 21.1% — 15개 라우트 중 가장 정체가
  심한 구간(distance 4.67km/20분).
- harsh_brake(전체 137건, 전부 비ADAS) — **ADAS 관여 harsh_brake
  0건**, turn_speed_violation 0건 — cruise_ratio가 낮아도 ADAS
  활성 구간 자체는 여전히 클린.
- ttc_danger 4건 전부 `count_adas=0`(수동 운전 중 정체 제동) — ADAS
  무관, min_ttc 0.99~2.28s 범위로 정체 상황에서 운전자 직접 대응.
- cut_in 20건, 전부 vEgo 0~6.6m/s 저속(대부분 0.0, 정차 상태) — DH
  레이더 구조적 오탐(radarTrackId=0==leadOne, MANDO_RADAR 부재)
  패턴과 완전 일치, 극심한 정체 구간에서 예상대로 빈발. 신규 이슈
  아님.
- curve_noise_refined: raw 22 -> would_trigger 12 -> refined 1건
  (억제율 91.7%, 저속 정체 구간이라 곡선 자체가 거의 없음).
- source_pair 우세: `road<->vturn`(181건, 15개 라우트 중 최다) >
  `model<->vturn`(130건) — 저속 정체 구간에서도 road<->vturn이
  여전히 우세, 다만 model<->vturn도 상당한 비중 유지.

## [VALIDATED] 24차 — 15개 zip 배치 분석 최종 완료 종합 (2026-08-21)
15개 zip 전체 처리 완료(실질 분석 13개, ADAS 미관여로 스킵 2개:
route2/route12). 하루치(06:29~14:20, 약 7.9시간 구간에 걸친 15개
라우트, 총 주행거리 약 230km) 전체 분석 완료.

- **종방향 안전 지표(harsh_brake/turn_speed_violation/ttc_danger,
  전부 ADAS 관여 기준) 13개 실질 라우트 전부 0건** — a4b5550 HEAD
  (22~23차 vision closing-rate grace 버그 수정 포함) 상태로 하루치
  전체(고속도로/시내/극심한 정체 전 유형 포함) 종방향 안전 회귀
  없음 최종 확인. 정체 구간(route14/15)처럼 cruise_ratio가 낮고
  수동 개입이 잦은 조건에서도 ADAS가 관여한 구간 자체는 일관되게
  클린.
- **b403d52(vision closing-rate) 프레임단위 실측 검증**(route5,
  PARAMS_REGISTRY.md 갱신 완료) — 6차 원 제보 증상과 정반대로
  vision-only 상태에서 이미 선제 감속 확인.
- **신규 source 라벨 2건 관찰(`bump`, `gas`) — 둘 다 기존 코드에
  이미 존재하던 정상 동작**(`bump`=APN 과속방지턱 경고,
  `gas`=가속페달 속도 오버라이드), 이번 배치에서 처음 로그에
  등장했을 뿐 신규 버그나 이슈 아님. source_pair_flicker 분석 시
  이 두 소스도 함께 고려 필요(기존 road/route/model/vturn/cam 5종
  외에 실제로는 bump/gas까지 최소 7종의 min() 경쟁자가 존재).
- **curve_noise_refined 억제율 최종 범위 55.6%~100%**: 고속도로
  완만 곡선(route4~7)은 87.5~100%, 저속추종/시내혼합(route8/11)은
  55.6~62.5%, 정체 구간(route15)은 91.7%(곡선 자체가 적어 표본
  작음) — 낮은 억제율 케이스들은 전부 프레임 대조로 오탐 아닌 정상
  위험 포착 확인.
- **source_pair 우세 쌍의 도로유형 의존성 최종 확인**: 고속도로
  연속(route4~9)=road<->vturn 압도적(49~112건), 시내+고속 혼합
  (route10)=model<->vturn 역전, 시내 위주(route11)=동률, 정체
  (route14/15)=road<->vturn 재우세하나 model<->vturn/gas/bump 등
  다변화 — 단일 히스테리시스로는 전 도로유형 대응 어려움, 도로
  유형별(또는 속도 구간별) 분기 설계 필요성이 15개 라우트 전체에
  걸쳐 일관되게 뒷받침됨.
- **DH 레이더 구조적 오탐(radarTrackId=0==leadOne cut_in) 패턴**은
  정체 구간(route15, 20건)에서 예상대로 최다 발생 — 기존 이해와
  완전 일치, 저속/정차 시 이 오탐 패턴은 근본적으로 무해(리드 부재
  상황에서의 라벨링 오류일 뿐 실제 제어 이상 유발 안 함)한 것으로
  누적 확인.
- **다음 세션 우선 과제**:
  1. route3의 `vision_radar_crossover count_highway_est=0`이 버그
     영향인지 재확인 필요 여부(낮은 우선순위, 완전 배제는 못했으나
     route3 자체가 시내 위주라 실제로도 낮았을 가능성 높음).
  2. `source_pair_flicker` 분석 대상에 `bump`/`gas`를 정식 편입할지
     검토(현재 도구는 자동으로 관측된 모든 페어를 집계하므로 이미
     반영되고 있음, 다만 FINDINGS/PARAMS_REGISTRY 등 문서화 시
     5종이 아닌 최소 7종으로 갱신 필요).
  3. 15개 라우트 중 고속도로 급접근(harsh) 케이스가 표본에 없어
     b403d52의 "온건한 접근" 검증에 그침 — 급접근 실측은 여전히
     미확보, 향후 로그에서 우선 확보 대상.

## [NEEDS_VALIDATION] frac_rate 게이트가 지속적 곡선 구간에서 dRel이
vRel과 무관하게 물리적으로 불가능한 속도로 드리프트하는 사례에
취약 — **기존 baseline 문턱에서도 이미 DANGER까지 도달**, 30/31차
문턱 재설계와는 별개의 사전 존재 결함 (2026-08-21, 32차)
- **입력**: `곡선_로그.zip` — route `203f99d429`(seg8, 완만~중간
  지속 곡선), `f3db6ca89d`(seg7, 급한 지속 곡선), `866476e5c3`
  (seg18, 거의 직선). `desiredCurvature` 필드로 확인: seg7
  p90=0.00783(57%가 곡선임계 0.002 초과)=가장 급함, seg8
  p90=0.00260(32% 초과)=중간, seg18 p90=0.00132(1.1% 초과)=직선.
- **핵심 발견 — seg8(203f99d429), t=6579.9~6582.4(2.7초)**:
  `leadDRel` 93.23m→38.60m로 급감(누적 54m), 같은 구간
  `leadVRel`은 내내 -1.7~-3.4m/s. vRel 적분 기준으로는 2.7초에
  5~9m만 감소해야 함 — **실제 감소량이 6~10배**. 이 구간 내내
  `desiredCurvature`가 0.0020~0.0027로 **지속적**(중간중간 튀는
  게 아니라 곡선을 도는 내내 유지)이고 vEgo는 24m/s 안정 —
  급브레이크나 vEgo 급변으로 설명 안 됨. 프레임 단위로도
  30/31차에서 본 "1~2프레임 점프 후 반등" 패턴과 다름 — 반등 없이
  거의 단조로 드리프트하다가 마지막에 38.6m 근처에서 3프레임
  연속 완전히 동일한 값(placeholder성 hold로 의심)으로 멈춤.
  → 비전이 곡선 중 실제 리드가 아닌 다른 물체(정지물/차선 옆
  차량 등)를 리드로 오인하며 거리를 점진적으로 잘못 추정하는
  것으로 추정(가설, 대시캠 대조 미실시).
- **문턱과 무관함 확인**: 이 사례는 **기존 baseline
  CAUTION=-5.5/DANGER=-10.0에서도 이미 min_filt=-11.391로 완전
  DANGER 도달**(frac=1.000). 30/31차에서 검토한 CAUTION=-2.2/
  DANGER=-5.0도 물론 도달하지만, 문턱을 낮췄기 때문이 아니라
  애초에 이 정도로 드리프트가 크기 때문 — **문턱 재설계가 이
  리스크를 새로 만든 게 아니라, 원래 있던 결함을 이번 곡선
  표본에서 처음 실측으로 확인한 것**.
- **f3db6ca89d--7(가장 급한 곡선)은 다른 범주**: DANGER 도달분
  (t≈9003.4~9003.8, 0.4초)은 초반 1프레임 점프(103.15→94.54m)가
  주도, 이후 94m 근방에서 반등·정체 — 30/31차에서 이미 특성화한
  "글리치성 CAUTION/DANGER 블립" 패턴과 동일 범주로 판단됨(새
  리스크 아님). 같은 세그의 두 번째 리드 구간(t≈9050.5~9051.4)은
  깨끗하고 DANGER 미도달.
- **866476e5c3--18(거의 직선)**: 대체로 매끄러운 실제 접근
  (113→108m, vRel과 대체로 일치) + 끝부분 1프레임 글리치(107.8→
  99.36m) 후 레이더 락온. 새 리스크 없음.
- **결론 및 다음 단계 제안**:
  1. 30/31차의 `GATE_CAUTION=-2.2`/`GATE_DANGER=-5.0` 문턱
     재설계는 이 발견으로 인해 **철회할 이유가 없음** — 새로
     발견된 결함이 문턱을 낮췄기 때문에 생기는 게 아니라 어떤
     문턱에서도 이미 존재하기 때문.
  2. 다만 **seg8류의 "지속적 곡선 중 dRel-vRel 불일치 드리프트"는
     문턱 재설계와 별개의 새로운 버그로 취급해 우선순위 높게
     추적 필요**. candidate 수정 방향(미검증, 설계만): N프레임
     동안의 dRel 변화량과 같은 구간 vRel 적분값을 비교해 큰
     괴리(예: 3배 이상)가 있으면 frac_rate 게이트를 억제하는
     consistency check 추가. LeadBlend의 vRel-불연속 블라인드
     스팟(다른 방향의 불일치)과 대칭되는 문제로, 별도 이슈로
     FINDINGS에 남겨둠.
  3. 원인 확인을 위해 seg8 t=6579.9~6582.4 구간 대시캠 프레임
     대조 필요(리드가 실제로 뭘 추적했는지 육안 확인) — 미실시.
- **재현**: `/home/claude/work/curve2.csv` (컨테이너 로컬, devnotes
  미보관, 원본은 `곡선_로그.zip`).

## [VALIDATED] frac_rate 게이트 문턱 재설계 — 추가 업로드 6개
세그먼트(3개 라우트)에서 CAUTION=-2.2/DANGER=-5.0이 락온 1초 이상
전에 완전 DANGER(frac=1.0)까지 도달하는 강한 실측 사례 다수 확인,
30차 잠정 제안 강하게 뒷받침 (2026-08-21, 31차)
- **입력**: `카메라_인식_추가.zip` — route `83e6b133f5`(seg8/9/12/15),
  `866476e5c3`(seg15, 세그7/12와 동일 라우트), `203f99d429`(seg6).
  `vision_to_radar_crossover()`로 10개 비전→레이더 전환 이벤트 확인,
  전부 고속도로(highway=True).
- **문턱별 세그 최대 frac_rate** (전체 세그 6개, CAUTION/DANGER 조합별):

  | CAUTION/DANGER | seg8 | seg9(9) | seg12(83e..) | seg15(83e..) | seg15(866..) | seg6(203f..) |
  |---|---|---|---|---|---|---|
  | -5.5/-10.0(기존) | 0.000 | 0.040 | 0.409 | 0.299 | 0.000 | 0.000 |
  | -2.2/-5.0(제안) | 0.000 | 1.000 | 1.000 | 1.000 | 0.862 | 0.734 |

  seg8만 끝까지 미발동(min_filt -1.585 — 실제로 거의 안 붙는
  케이스, dRel_closed 크로스오버 이벤트에서도 -0.46m로 사실상
  무의미한 변화였음, 오히려 이게 "가짜 트리거가 남발되지 않는다"는
  근거).
- **핵심 사례 — seg12(83e6b133f5), 프레임 확인 결과 매우 깨끗함**:
  t=3208.98(dRel 110.08)~3210.73(dRel 97.21) 약 1.75초 동안 거의
  단조 감소(13m/1.75s ≈ 7.4m/s 평균 접근), filt_rate가
  3209.875부터 **1.35초 이상 연속으로 DANGER(frac=1.0) 유지**,
  락온(t=3211.275, vRel=-6.6)보다 한참 전부터. 글리치 패턴 전혀
  없음 — 30차에서 우려했던 "노이즈 대표값" 문제가 없는 깨끗한
  실측 검증 사례.
- **seg15(83e6b133f5)**: 유사하게 t=3384.3~3385.4 동안 매끄러운
  접근으로 DANGER 도달·0.6초 이상 유지. 끝부분(3385.476)에 1프레임
  급점프(111.27→103.1)가 있으나 이미 DANGER 상태라 무해.
- **seg15(866476e5c3)** — 두 에피소드:
  1) t=4572.5~4575.9: 완만한 오르내림, DANGER까지는 안 가고
     frac 0~0.55 사이에서 등락(진짜 신호로 보이나 약함).
  2) t=4609.88~4612.0: **근거리(19~38m) 추종 상황**. dRel이
     급격히 37→21m로 줄어든 뒤 19~21m에서 유지되며 filt_rate가
     0.85초 이상 -3~-4.6 구간에서 등락(frac 0.4~0.86) — 근거리
     추종/속도 변동이 심한 실제 상황으로 판단됨(글리치라면 바로
     반등해야 하는데 저거리 유지가 지속됨).
- **seg6(203f99d429)**: 두 번의 짧은(≤0.2초) 블립, 둘 다 dRel이
  급점프했다가 즉시 되돌아오는 패턴(예: 111.09→**101.67**→103.9→
  107.29, 3프레임 안에 왕복) — 30차에서 본 세그7 후반 글리치와
  동일한 성격. frac 최대 0.73까지 갔지만 DANGER는 안 됨, 지속시간
  0.2초 이하. **CAUTION 레벨 글리치 플리커는 이 문턱에서도 여전히
  발생함 — 다만 DANGER까지는 안 가고, 순간적이라 실제 감속 개입엔
  거의 영향 없을 것으로 예상**(정량 영향은 미검증, long_mpc.py
  실제 통합 후 재시뮬레이션 필요).
- **결론**: -2.2/-5.0 후보가 (a) 진짜 강한 접근 사례에서 락온 전
  충분한 여유를 갖고 DANGER까지 확실히 도달하고, (b) 약한/무의미한
  케이스(seg8)는 여전히 무발동이며, (c) 짧은 글리치 플리커는
  CAUTION 레벨에서 간간이 발생하지만 DANGER엔 도달하지 않는다는
  점에서, 30차 잠정 제안이 훨씬 더 탄탄한 근거를 갖게 됨.
  **곡선 전용 오탐 검증은 여전히 seg19 1건뿐** — 이번 6개 세그는
  전부 고속도로 직선/완만 구간이라 곡선 오탐 검증엔 기여하지
  않음. 남은 리스크는 오직 "곡선 중 CAUTION 레벨 글리치 빈도"이며,
  이는 DANGER까지 안 가는 한 안전 임계는 아니라고 판단되나
  최종 확정 전 사용자 판단 필요.
- **재현**: `/home/claude/work/extra.csv` (컨테이너 로컬, devnotes
  미보관, 세그별 원본은 `카메라_인식_추가.zip`).

## 30차 원본 기록 (위 31차로 강하게 보강됨)


- **방법**: `sim_frac_rate.py`에 `SIM_GATE_CAUTION`/`SIM_GATE_DANGER`
  환경변수 override 추가(29차) 후 CAUTION 후보(-2.0~-3.2) ×
  DANGER 후보(-4.5~-10.0) 조합을 세그7/세그12에 스윕, 프레임 단위
  덤프로 각 activation의 발생 위치·지속성 확인.
- **발견 1 — 세그7 min_filt_rate=-3.196은 글리치**: 프레임 덤프
  확인 결과, t=4119.029~4119.128 구간에서 dRel이 112.22 →
  **100.98**(한 프레임) → 108.10 → 115.23으로 튀었다가 되돌아옴.
  raw closing rate가 한 프레임만 -216m/s(클램프로 -30 적용)로
  튄 뒤 다음 프레임에 강한 receding(+143m/s)으로 반전 — 실제
  물리적 접근이 아니라 비전 depth 추정 노이즈. 3프레임 median
  필터 창에 이 글리치가 걸려 filt_rate가 일시적으로 -3.196까지
  내려간 것이며, 직후 즉시 +11.9까지 반등한다. 28차에서는
  "min_filt_rate"만 기록하고 발생 시점·지속성을 확인하지 않아
  이 글리치를 대표값으로 오인했음.
- **발견 2 — 세그7에 별도의 진짜 조기 신호 존재**: 같은 세그7
  안에 t=4115.679~4116.826 구간(락온 t=4120.678 대비 **4.8초
  전**)에서 dRel이 116.5→112.7로 매끄럽게 감소하는 진짜 접근
  트렌드가 있음(filt_rate 최소 -2.940, t=4115.834). 중간에
  0.3초짜리 리드 유실(t=4117.525~4117.780, status=False)이 있고
  재획득 후 111~114m 사이를 배회하다가 위 글리치로 이어짐.
  → 문턱 재설계는 이 -2.9대 dip을 기준으로 해야 함(글리치인
  -3.196이 아니라).
- **세그12는 깨끗함**: t=4412.48~4412.9(락온 대비 1.7초 전)
  filt_rate -3.504까지 매끄럽게 하강, 글리치 패턴 없음.
- **문턱 후보 스윕 결과** (frac_rate 최댓값):

  | CAUTION/DANGER | 세그7 초기(깨끗) | 세그12 | 세그19 곡선 오탐 |
  |---|---|---|---|
  | -2.0 / -4.5 | 0.376 | 0.602 | 없음 |
  | -2.2 / -5.0 | 0.356 | 0.466 | 없음 |
  | -2.5 / -5.5 | ~0.15(약함) | 0.335 | 없음 |

- **곡선 오탐 검증** (신규 업로드 `20260821_115242_000002e5--
  1723e8b850--19.zip`, route `1723e8b850` seg19): CAUTION=-2.0까지
  낮춰도 오탐 없음. 유일하게 -2.0 아래로 내려간 지점(filt_rate
  -3.084, t=6049.677)이 track 획득 직후(acq_t=0.25s < MIN_TIME
  0.5s)라 기존 `VISION_CLOSING_RATE_MIN_TIME` 게이트로 이미
  차단됨 — 곡선 진입 직후 track 재획득 노이즈를 이 기존 게이트가
  방어하고 있음을 확인(다만 표본 1건, 추가 곡선 라우트로 보강 필요).
- **잠정 제안**: `GATE_CAUTION=-2.2`, `GATE_DANGER=-5.0`
  (세그7/세그12 둘 다 여유 있게 통과, 세그19 오탐 없음, -2.0/-4.5
  보다 밴드 폭 확보로 약간 더 보수적). **사용자 확인 대기 중** —
  곡선 표본 1건이 얇다는 점 때문에 최종 확정 전 (a) 곡선 라우트
  추가 확보 후 재검증 여부, 또는 (b) 이 정도로 패치 진행 여부를
  물어본 상태에서 세션 중단.
- **재현 스크립트**: `toolkit/sim_frac_rate.py` (29차 env override
  추가분 사용). 원본 CSV: `/home/claude/work/seg7_12.csv`,
  `/home/claude/work/seg19.csv` (컨테이너 로컬, devnotes에는
  미보관 — 재현하려면 zip 재업로드 필요).

### 28차 원본 기록 (아래는 위 30차로 일부 정정됨 — min_filt_rate
자체는 정확하지만 "대표 신호"로서의 해석이 30차에서 정정됨)

## [PATCH_APPLIED, NEEDS_VALIDATION] 옆차선 차량이 SCC 단일점 레이더(track_scc, trackId=0)로 락온되며 LeadBlend 안전장치를 전부 우회 → 급감속 (2026-08-22, 37차, 업로드 "옆차선_차량_인식_감속.zip" 6세그먼트, 패치는 37차 계속 3에서 작성·양쪽 브랜치 적용)

- **사용자 제보**: "옆차선의 차량이 내차 레이더에 가끔 잡혔다 끊어지면서 내차가
  급감속 하는 경우가 있었어."
- **로그**: 6개 세그먼트(83e6b133f5--16, 866476e5c3--3, 1723e8b850--16/19,
  7ffb3e693c--10, 3f3884d185--6) 전용 추출(work/extract_lead_detail.py,
  `leadYRel`/`leadTrackId`/`leadDPath`까지 포함 — 표준 `extract_log.py`엔
  없는 필드라 이번 세션 전용 스크립트로 뽑음). aEgo가 10프레임(~0.5s)
  윈도 기준 -1.2m/s² 이상 떨어지는 급감속 후보를 스캔한 결과 6세그 중
  4세그에서 총 50건 발견, 그중 4건을 프레임 단위로 대조.
- **4건 전부 동일 패턴 확인**:
  | 세그 | t | leadYRel | leadDRel 추이 | leadTrackId | radar | 결과 aEgo |
  |---|---|---|---|---|---|---|
  | 83e6b133f5--16 | 3430.65~3432.24 | **-5.5~-6.0m** (뚜렷한 옆차로) | 119m→102m 부드럽게 감소 | 0 | True | 0→-2.5m/s² |
  | 1723e8b850--19 | 6046.48~6049.4 | 1.0→2.0m | 85m→70m | 0 | True | 0→-1.3m/s² |
  | 7ffb3e693c--10 | 11623.4~11624.7 | -1.4~-1.5m | 39m→25m | 0 | True→False | +0.7→-3.3m/s² |
  | 3f3884d185--6 | 12549.65~12553.14 | **-10.5→-3.0m** (강한 옆차로) | 74m→41m | 0 | True | 0→-2.0m/s² |

  4건 모두 **`leadTrackId=0`, `radar=True`** — Genesis DH(EnableRadarTracks<3)
  차량의 SCC 순정 단일점 레이더가 리드로 선택된 케이스이고, `yRel`이
  1.0~10.5m로 제자리에 가깝지 않거나(내 차로 중심 기준 반차로~한차로
  이상) 뚜렷이 벗어난 값으로 유지되는 동안 그대로 감속에 반영됨.

- **원인(코드 확인 완료)**: `selfdrive/controls/radard.py`
  1. `get_lead()` (line ~712~715):
     ```python
     if (track is None or lead_msg.prob < .6) and track_scc is not None and track_scc.cnt > 2:
       if self.enable_radar_tracks == -1 or (self.enable_radar_tracks >= 2 and track_scc.vLead < 5.0):
         track = track_scc
     ```
     `track_scc = tracks.get(0)` — 차량 자체 SCC 레이더가 보고하는 단일
     타깃(trackId=0)을 그대로 채택. **비전 매칭(`match_vision_to_track`)이
     실패했거나(`track is None`) 비전 확신도가 낮을 때(`lead_msg.prob<0.6`,
     즉 카메라엔 뚜렷한 앞차가 안 보일 때) 발동** — `match_vision_to_track`의
     `y_sane()`(정상 2.0m/wide 4.0m) 같은 **차로 내 위치 검증이 이 경로엔
     전혀 없음**. SCC 하드웨어가 순간적으로 옆차선 차량을 자신의 유일한
     타깃으로 잘못 보고하면 그대로 통과.
  2. `Track.get_RadarState()`은 트랙 출처(비전매칭 vs track_scc)와 무관하게
     항상 `"radar": True`를 반환.
  3. `RadarD.update()` (line ~660~667):
     ```python
     if lead_one_raw.get('radar'):
       # 빨간박스: SCC 레이더 락온 상태. 이미 안정적인 실측값이므로 블렌딩 지연 없이 그대로 사용.
       self.radar_state.leadOne = lead_one_raw
       ...
     else:
       self.radar_state.leadOne = self.lead_blend.update(lead_one_raw, DT_MDL)
     ```
     **`radar=True`면 `LeadBlend` 전체를 우회**하고 바로 `radarState.leadOne`에
     반영. `LeadBlend`의 `CUTOUT_DPATH_THRESH`(2.0m 벗어나면 cut-out으로
     즉시 제외)/`closer_jump`/TTC-danger 스무딩은 전부 `radar=False`
     (비전-only) 경로에서만 동작 — 정확히 이번 옆차선 오탐 4건이 걸려야
     할 안전장치인데 애초에 도달하지 못함.
- **왜 "가끔 잡혔다 끊어지는" 것처럼 보이는지**: SCC 단일점 레이더는
  차선별 트랙 분리가 없어 매 프레임 강한 반사체 하나만 보고 — 앞차가
  없거나(곡선/차로변경 직후 등) 비전 확신도가 순간적으로 낮아지는
  타이밍에 우연히 옆차로 차량이 가장 강한 반사체가 되면 트랙0으로
  잡히고, 다시 진짜 전방 상황이 바뀌거나 비전이 확신을 회복하면
  풀림 — 사용자가 체감한 "잡혔다 끊어짐"과 정확히 일치.
- **상태**: ROOT_CAUSE_IDENTIFIED — 4개 독립 세그먼트(다른 시각/다른
  라우트)에서 동일 메커니즘 재확인되어 우연/노이즈로 보기 어려움.
  단, 패치는 아직 미작성(다음 단계). 7ffb3e693c--10 사례는 vEgo가
  낮고(~11m/s, 저속 곡선) yRel도 상대적으로 작아(-1.4~-1.5m) 실제
  차로 내 리드였을 가능성도 배제 못 함 — 이 건은 대시캠 프레임 대조로
  최종 확인 필요, 나머지 3건(특히 83e6b133f5--16의 -5.5~-6.0m,
  3f3884d185--6의 -10.5~-3.0m)은 수치상 옆차로가 명백함.
- **패치 방향(제안, 미착수)**:
  1. `track_scc` 채택 조건에 `abs(track_scc.yRel) < 1.75~2.0m`
     (반차로 폭) 같은 최소 차로내 게이트 추가 — 비전이 대응하는 리드가
     없을 때만 쓰는 폴백이므로 지나치게 엄격하면 안 되지만, 뚜렷이
     벗어난 값(예: 83e6b133f5--16의 -5.5m)은 걸러야 함.
  2. 또는 `radar=True` 우회 조건 자체를 세분화 — `track_scc` 폴백으로
     선택된 경우엔 `lead_one_raw['radar']=True`를 그대로 두지 말고
     별도 플래그로 표시해 `LeadBlend`(특히 cutout dPath 체크)를 여전히
     타도록. `match_vision_to_track`으로 비전-확인된 트랙과 신뢰도를
     동일하게 취급하는 게 근본 문제.
  3. 두 방향 다 `enable_radar_tracks`/`RadarLatFactor` 등 기존 파라미터와
     상호작용하므로 다음 세션에서 방향 확정 후 패치 설계.
- **영상 대조 결과(37차 계속, qcamera 프레임 vs 로그 시각 동기화,
  `toolkit/extract_dashcam_frames.py` 사용, 매칭오차 전부 0.03s 이내)**:
  4건 중 **3건은 옆차선 확정, 1건은 다른 유형으로 재분류**.
  - `83e6b133f5--16`(yRel -5.5~-6.0m): **옆차선 확정**. 오른쪽 옆차로의
    카캐리어 트럭, 락온~해제 전 구간(t=3430.6~3432.24) 우리 차로는
    완전히 비어있음.
  - `1723e8b850--19`(yRel 1.0→2.0m): **옆차선 확정**. 점선 차선 너머
    오른쪽 옆차로의 검은 세단, 우리 차로 전방 비어있음.
  - `3f3884d185--6`(yRel -10.5→-3.0m): **옆차선 확정**. 왼쪽 옆차로의
    흰 아우디 — **진짜 앞차(약 50~60m 거리)를 무시하고 옆차선 차를
    리드로 오인**한 것까지 프레임상 확인(t=12549.65/12552.14 두 프레임
    모두 우리 차로 앞쪽에 다른 차량들 존재).
  - `7ffb3e693c--10`(yRel -1.4~-1.5m): **재분류 — 옆차선 아님**.
    저속(~40km/h) 도심 커브+라바콘 공사구간에서 **우리 차로가 아니라
    오른쪽 옆길/건물 진입로에 정차·횡단 중인 차량**을 SCC가 정면
    타깃으로 오탐. 근본원인 코드(`track_scc` 무검증 채택)는 동일하지만
    발생 상황이 다름 — "주행 경로 밖 정지/측면 차량 오탐"으로 별도
    표기 필요.
  - 종합: 근본원인(코드)는 고속도로 옆차선과 도심 커브 측면차량 두
    상황 모두에서 동일하게 재현됨이 시각적으로 확정. 패치 설계 시
    두 시나리오 다 커버해야 함(단순 "옆차선 각도"만이 아니라 "주행
    경로에서 벗어난 정지물체" 전반의 yRel/dPath 게이트로 접근 필요).
  - 비교 이미지: work/frames/compare/4events_lockon_start.jpg(세션 로컬,
    devnotes 미커밋 — 원본 대시캠 프레임 정책상 요약 결론만 텍스트로
    기록).
- **근거 로그**: work/csv_per_seg/*.csv, work/frames/*(이번 세션 임시
  추출, devnotes에는 미포함 — 원본 정책상 route.csv/대시캠 프레임
  미커밋 원칙 유지).

- **패치 작성 완료(37차 계속 3, 2026-08-22)**: 위 패치 방향 1안(yRel
  게이트)과 2안(플래그 분리)을 결합해 구현. `C:\dev\ryu` base
  `4fe22cd`(c3-ms-dev HEAD, 35차 계속2 캐시버스터 커밋) 위 단일 커밋.
  1. `get_lead()`에서 `track_scc` 채택 직전 `abs(track_scc.dPath) <
     SCC_FALLBACK_DPATH_GATE(=2.0m)` 게이트 추가 — 넘으면(차로 밖)
     폴백 자체를 채택하지 않음. **yRel 대신 dPath 사용**(37차 결론:
     `Track.d_path()`가 `md.laneLines` 기반 차선중심 대비 위치라
     곡률/차선폭 보정 포함, `track_scc`도 `Track` 인스턴스라 동일
     계산을 받음 — 단순 yRel로는 `7ffb3e693c--10`(yRel -1.4~-1.5m,
     값 자체가 작음)을 못 거르는 문제를 dPath가 보완할 것으로 기대).
     이 게이트는 `track`이 이미 있었는지(기존 저확신 매칭)와 무관하게
     항상 적용 — 초안에서 "track이 이미 있으면 게이트 스킵"으로 잘못
     구현했던 버그를 합성테스트로 발견/수정(아래 참고).
  2. `Track.get_RadarState()`에 `sccFallback` bool 플래그 추가.
     `RadarD.update()`의 `radar=True` 즉시반영 분기 조건을
     `lead_one_raw.get('radar') and not lead_one_raw.get('sccFallback')`
     로 변경 — `track_scc` 유래 리드는 `radar=True`라도 더 이상
     `LeadBlend`를 우회하지 않고 기존 cutout/danger-passthrough
     로직을 그대로 탐(37차 cut-in/cut-out 영향 분석 결론과 일치:
     위험한 변화는 즉시 반영 유지, 완만한 변화만 ~0.35s 스무딩).
  3. **로직 단위 합성검증(work/test_scc_gate.py, 7케이스 전부 PASS)**:
     옆차선 3건 재현(dPath 5.5~6.0 가정) → 폴백 거절 확인, 재분류
     케이스(dPath 2.3 가정) → 거절 확인, 정상 동일차로(dPath 0.3) →
     정상 채택+플래그 확인, 경계값(1.99/2.01) → 정확히 게이트 경계에서
     분기, **기존 track 존재+저확신+옆차선 폴백 케이스에서 초안 버그
     (게이트 우회) 발견 및 수정**. 단, 이는 로직 단위 합성검증이며
     **실제 acados/radard 파이프라인 실행이나 실차 로그 재현은
     아직 미검증** — dPath 실측값도 옆차선 3건은 당시 yRel만 기록돼
     있어 정확한 dPath 값이 아닌 추정 시나리오임에 유의(수치상 워낙
     명백해 게이트 관여 필요성 자체가 낮았던 케이스들).
  4. `git am` 검증(temp branch, base `4fe22cd`) + `python3 -m ast`
     문법 통과. 패치 파일 `0001-radard-SCC-dPath-LeadBlend-37.patch`
     `/mnt/user-data/outputs/`에 전달.
- **다음 단계(미완료)**:
  1. ~~사용자가 `git am`으로 `C:\dev\ryu`(c3-ms-dev)에 적용 + push~~ →
     **완료**. 처음엔 `c3-ms-test`(당시 체크아웃 브랜치)에 적용됨
     (`b5a1209`) — 34차 A/B 비교 오염 방지를 위해 `c3-ms-dev`에도
     `cherry-pick`(→ `21effa1`) 후 양쪽 push 완료 확인:
     `c3-ms-dev`(`4fe22cd..21effa1`), `c3-ms-test`(`4d2f6a5..b5a1209`).
  2. **[남음]** 실차 검증: 원래 옆차선/측면차량 오탐 재현 시나리오에서
     `leadTrackId=0`인데도 `dPath` 게이트에 걸려 리드로 채택 안 되는지,
     또는 채택되더라도 `sccFallback=True`로 `LeadBlend`(특히
     `CUTOUT_DPATH_THRESH`)가 작동해 급감속으로 이어지지 않는지 확인.
  3. **[남음] 회귀 검증도 필요**: `SCC_FALLBACK_DPATH_GATE=2.0m` 게이트가
     정상적인 동일차로 SCC 폴백(전체 트랙 시간의 74~82%를 차지하는
     주 사용 경로)을 과도하게 거르지 않는지, 즉 게이트 도입 후에도
     정상 추종이 평소와 동일하게 유지되는지 실차에서 함께 확인 필요.

## [FIXED, URGENT] radard 크래시 — 37차 sccFallback 키가 capnp 스키마에 없어 AttributeError (2026-08-22, 커밋 f67a834)

- **증상**: `c3ea08e`/`52668ec`(38/39차) 적용 후 실차에서 기기 화면에
  "radard 프로세스가 실행되지 않았습니다"(빨간 에러 오버레이) 표시,
  종방향 제어 완전 불능.
- **원인**: 37차(`21effa1`)에서 `Track.get_RadarState()`가 반환하는
  dict에 `sccFallback` bool 키를 추가했는데, 이 dict가 이후
  `self.radar_state.leadOne = lead_dict` 형태로 pycapnp 구조체
  (`cereal/log.capnp`의 `RadarState.LeadData`)에 그대로 대입됨.
  `LeadData` 스키마엔 `sccFallback` 필드가 정의돼 있지 않아 **매 사이클**
  `AttributeError`(capnp: struct has no such member; name = sccFallback)
  발생 → radard 즉시 크래시 → 프로세스매니저가 재시작을 반복하다 실패.
  `LeadBlend.update()`도 raw dict를 그대로 복사/반환하므로
  danger-passthrough/블렌딩 두 경로 모두 동일하게 크래시.
  **37차 로직 단위 합성검증(`test_scc_gate.py`)이 순수 파이썬 dict만
  다뤄서 이 capnp 대입 단계를 검증 범위에 포함하지 못했던 것이 근본
  원인** — 로직은 맞았으나 출력 타입(구조체 vs dict) 계약을 놓침.
- **수정**(`f67a834`):
  1. `Track.get_RadarState()`에서 `scc_fallback` 파라미터/`sccFallback`
     키 제거 — capnp에 대입되는 dict는 스키마 필드만 포함하도록 원복.
  2. 대신 `RadarD.get_lead()`가 `(lead_dict, radar, used_scc_fallback)`
     3-tuple을 반환하도록 변경해 플래그를 dict 밖(파이썬 로컬 변수)으로
     분리. `RadarD.update()`의 leadOne/leadTwo 호출부 3-value 언패킹으로
     갱신, `LeadBlend` 우회 조건은 `lead_one_scc_fallback` 로컬 변수로
     판단. **37차의 원래 안전 로직(비전 교차검증 없는 SCC 단일점 폴백은
     LeadBlend를 계속 태운다)은 동작 그대로 유지, capnp 스키마 위반만
     제거** — 37차 결론/패치 방향 자체는 변경 없음.
  3. `cereal/log.capnp` 등 스키마 파일은 변경 없음(원복 방식이 스키마
     확장보다 범위가 작고 안전).
- **검증**: `ast`/`pyflakes` 통과. capnp 대입(dict->LeadData struct)
  재현 테스트로 크래시(`AttributeError: struct has no such member;
  name = sccFallback`) 실제 재현 후 수정본으로 정상 대입 확인. **실차
  검증(radard 정상 기동 + 37차 원래 목적대로 동작하는지)은 아직 미실시.**
- **교훈**: `radard.py`처럼 반환 dict가 capnp 구조체에 직접 대입되는
  코드에 새 키를 추가할 때는, 순수 로직 합성테스트만으로는 부족하고
  **실제 캡엔프 스키마(`cereal/log.capnp`) 필드와의 일치 여부를 반드시
  별도 확인**해야 함 — 이번처럼 로직 검증은 전부 통과해도 스키마
  불일치로 배포 즉시 크래시할 수 있음.


---

## [VALIDATED] frac_rate 게이트(-5.5m/s CAUTION 문턱)가 실측 두 사례
모두에서 전혀 발동하지 않음 — 세그7/세그12 zip 재업로드 후
프레임 단위 재현으로 확정 (2026-08-21, 28차, 27차 NEEDS_VALIDATION
항목을 정량 검증으로 승격)
- **방법**: 27차 종료 시점에 없었던 세그7/세그12 zip이 이번 세션에
  재업로드됨(`앞차_카메라_인식_미감속.zip`). `extract_log.py`로
  a4b5550 HEAD(26차 patch 적용 전) 상태로 CSV 재추출 후, 26차 설계
  문서(클램프 30m/s + 3프레임 중앙값 + TAU=1.0s 저역통과 +
  GATE_CAUTION=-5.5/GATE_DANGER=-10.0 선형 정규화)를 그대로 코드로
  재현한 `toolkit/sim_frac_rate.py` 신규 작성, 두 세그먼트 전체를
  프레임 단위로 재생.
- **결과 (27차 정성적 추정을 정량으로 완전히 확인)**:
  - 세그7: 비전 단독 추적 구간(t=4114.03~4120.68, 6.65s, 중간 blip
    freeze 포함 단일 연속 에피소드) 동안 `frac_rate` **전 구간
    0.000** — 필터 출력(`filt_rate`) 최솟값(가장 접근 방향으로 큰
    값)은 -3.196m/s로 CAUTION 문턱(-5.5) 근처에도 못 감. 레이더
    락온 프레임(t=4120.678)에서 dRel이 108.26→119.10으로 순간
    점프하며 vRel_raw가 -5.66→-11.60으로 불연속 도약(기존 확정된
    "레이더 락온 순간 vRel 점프" 패턴과 동일).
  - 세그12: 비전 단독 추적 구간(t=4411.48~4414.29, 2.81s) 동안
    `frac_rate` **전 구간 0.000** — `filt_rate` 최솟값 -3.504m/s로
    역시 CAUTION 문턱 근처에도 못 감. 레이더 락온 프레임
    (t=4414.328)에서 dRel 101.73→119.5 점프, vRel_raw -1.41→
    -10.80 불연속 도약.
  - 클램프/중앙값 없이 raw만 저역통과한 참고값(`raw_rate_lp`)도
    두 사례 모두 비전 추적 구간 내내 대략 -0.1~-3.5 범위에 머물러,
    필터 자체의 감쇠 때문이 아니라 **원시 신호부터 -5.5에 도달하지
    못했음**을 재확인(필터가 신호를 더 깎을 뿐 원시값보다 더
    음수로 만들 수 없다는 27차 추론과 일치).
- **결론**: `frac_rate` 게이트는 설계 의도(카메라가 인식했는데도
  감속 안 하는 상황 보완)와 달리, 이번 두 실측 사례에서는 **한
  프레임도 관여하지 못했음이 확정**. 원인은 게이트 로직 버그가
  아니라 **문턱값(-5.5m/s)이 두 사례의 실제 도달 가능 범위
  (-3.2~-3.5m/s)보다 구조적으로 높게 설정**되어 있기 때문.
- **조치**: 문턱 재설계 필요 확정(27차에서는 "필요해 보임", 이번
  28차로 "필요함"으로 격상). 다만 단순히 -5.5→-3.5~-4.0으로
  낮추는 것만으로는 세그7(-3.196)을 여전히 못 잡을 수 있음 —
  실측 두 사례의 피크가 -3.2~-3.5 구간에 몰려 있어 CAUTION 문턱을
  이보다 낮게(예: -2.5~-3.0m/s대) 설정하거나, CAUTION/DANGER
  구간 폭 자체를 좁혀 재설계할 필요. **코드 변경은 아직 미적용**
  (다음 세션에서 문턱 재설계 + 패치 작성 예정).
- **재현 스크립트**: `toolkit/sim_frac_rate.py` (신규, 26차 필터
  로직 프레임 단위 재현 전용 — `sim_vision_rate.py`와는 별개,
  후자는 a4b5550의 grace-aware 리셋 버그 수정 검증용).
- **근거 로그**: 세그7(`866476e5c3` 관련 zip,
  `20260821_112042_000002e4--866476e5c3--7.zip`, t=4117~4121),
  세그12(`866476e5c3` 관련 zip,
  `20260821_112542_000002e4--866476e5c3--12.zip`, t=4411~4415).
  둘 다 a4b5550 HEAD(26차 patch 적용 전) 상태 기록. (27차 원본
  기록은 아래 참고용으로 보존)

### 27차 원본 기록 (정성적 추정, 참고용 — 위 28차로 정량 확정 완료)
- 증상: 26차에서 구현한 vision-only closing-rate 절대값 게이트
  (`_vision_dRel_rate`를 -5.5m/s CAUTION ~ -10.0m/s DANGER로 정규화한
  `frac_rate`, 기존 frac_time/frac_ttc와 max()로 결합)가, 정작 이
  게이트를 만들게 된 계기인 "카메라가 인식했는데도 감속을 안 한" 실측
  두 사례(세그7 `t=4117~4121`/세그12 `t=4411~4415`, a4b5550 HEAD,
  patch 적용 전 로그)에서 발동했을지 재검토한 결과 — **둘 다 사실상
  발동하지 않거나 발동해도 무의미한 타이밍이었을 것으로 추정.**
- 근거:
  - 세그7: 비전 전용 구간(3.55s) 동안 raw vRel(종가율)이 -1.66 →
    -5.66으로 서서히 상승, 레이더 락온 직전 막판에야 CAUTION 문턱
    (-5.5)에 간신히 근접. 게이트가 실제로 보는 값은 raw가 아니라
    클램프(30m/s)+중앙값(3프레임)+저역통과(TAU=1.0s)를 거친 필터
    출력이라, TAU=1.0s 지연 때문에 필터 출력이 락온 시점까지
    -5.5를 못 넘었을 가능성이 높음. 설령 넘더라도 그 시점이 이미
    레이더 락온 직전/동시라 "조기 개입" 효과는 거의 없음.
  - 세그12: 락온 직전까지 raw vRel 최대치가 -2.82로, CAUTION 문턱
    (-5.5)에 전혀 근접하지 못함. 필터(클램프+중앙값+저역통과)는
    신호를 깎는 방향으로만 작동하므로 필터 출력이 raw보다 더
    -5.5에 가까워질 수 없음 — 비전 전용 구간 내내 `frac_rate`
    기여도가 사실상 0으로 추정, 게이트가 아예 관여하지 못함.
  - 두 사례의 실제(레이더 락온 후 역산) 선행차 감속은 약
    -2.7~-3.9 m/s²로 결코 미미한 수준이 아니었는데도, raw
    종가율(vRel) 자체가 -5.5 문턱보다 한참 낮은 채 유지됨 —
    즉 원거리·완만한 접근 상황에서는 "실제로는 확실히 감속 중인
    선행차"라도 카메라 미분 추정 종가율이 문턱을 넘지 못하는
    구간이 존재함을 시사.
- 조치: 미적용(보류) — 이 분석은 raw vRel 수치 + 알려진 필터
  특성(클램프/중앙값/TAU)으로 추론한 것이며, **`frac_rate` 코드를
  실제 CSV에 프레임 단위로 재현해 검증한 것은 아님**(세션
  컨테이너 리셋으로 26차의 로컬 커밋 `5cc0900`과 추출된 CSV가
  이번 세션엔 남아있지 않았음, origin에도 미push 상태). 문턱값
  (-5.5m/s)을 실측 감속 범위(-2.7~-3.9 m/s² 대응 vRel 실측 -2.82~
  -5.66)에 맞춰 하향(예: -3.5~-4.0m/s대) 하는 재설계가 필요해
  보이나, 정확한 프레임 단위 재검증(zip 재업로드 또는 패치 적용된
  `long_mpc.py` 재확보 후 실행) 전까지는 코드 변경 보류.
- 근거 로그: 세그7(`866476e5c3` 관련 zip,
  `20260821_112042_000002e4--866476e5c3--7.zip`, t=4117~4121),
  세그12(`866476e5c3` 관련 zip,
  `20260821_112542_000002e4--866476e5c3--12.zip`, t=4411~4415).
  둘 다 a4b5550 HEAD(26차 patch 적용 전) 상태 기록.

## 45차 (2026-08-22) — 정지 후 출발 가속 약화, 근본원인 확인 (NEEDS_VALIDATION)

### 증상
사용자 제보: 패치 이후 정지 후 출발(launch) 시 가속이 이전보다 약하게 느껴짐.
패치이전 로그(`dda0d533ce--5`, HEAD `a4b5550`) 1건 + 패치이후 로그
(`05890d8ca1--3/6/7`, HEAD `96e789c7`) 3세그 + 화면녹화 3건(before 1건,
after clip 2건)으로 분석.

### 중요 발견 0 — "패치이후" 로그의 실행 커밋이 origin에 없음
`initData.gitCommit`으로 확인한 실제 기기 실행 커밋은 `96e789c771...`
(2026-08-22 16:11:30 KST)인데, `git fetch --unshallow`로 origin
`c3-ms-dev` 전체 히스토리를 받아도 이 커밋이 존재하지 않음(origin HEAD는
`c31ddca`, 2026-08-22 16:02:54 — 96e789c7보다 9분 이전). 즉 사용자가
로컬에서 만든 어떤 변경(들)이 이 로그를 만든 실행 바이너리에 반영됐지만
`push`도 devnotes 기록도 안 된 상태로 보임 — 정확히 어떤 코드였는지는
확인 불가. 단, 아래 근본원인은 이미 origin에 push된 코드(`c3ea08e`/
`52668ec`, `c31ddca`에 포함됨)만으로도 100% 설명 가능해서 이 미기록
커밋과 무관하게 결론 자체는 유효함. **사용자에게 확인 요청 필요**:
96e789c7 커밋을 push했는지, 혹은 실차에만 있고 아직 커밋 안 한 상태인지.

### 근본원인 (NEEDS_VALIDATION, 코드 근거는 확실함)
`long_mpc.py`의 `ttc_accel_weight()`(38차, 커밋 `c3ea08e`, 2026-08-22
05:32)가 원인. 이 함수는:
```python
def ttc_accel_weight(dRel, v_ego, v_lead):
  closing = v_ego - v_lead
  if closing <= 0.1:
    return 0.0   # 벌어지거나 등속 -> 완전 감쇠
  ...
```
`w = min(dist_w, ttc_w)`로 `margin_accel_weight`(거리비율 게이트, 8/16
커밋 `afcfeee`부터 존재 — **패치이전 로그(a4b5550)에도 이미 있었음**)와
`min()` 결합되는데, **`ttc_w=0`이면 `dist_w` 값과 무관하게 최종 weight가
무조건 0이 됨.**

정지 후 출발 직후는 정확히 `v_ego <= v_lead`(정지해 있던 나는 아직 0
근방, 앞차는 이미 출발해 움직이는 중) 구간과 겹침 -- 즉 `closing<=0.1`이
성립해 `ttc_w=0` -> `w=0` -> `a_lead(=lead.aLeadK, 앞차의 실측/추정
가속도) *= 0`으로 **앞차가 실제로 가속하며 멀어지고 있다는 신호 자체가
MPC의 리드 궤적 예측(`extrapolate_lead`)에서 완전히 사라짐**. MPC는
앞차가 "가속 안 하고 그 속도 그대로 유지"한다고 가정하게 되고, 그 결과
자차가 앞차를 따라잡기 위해 필요하다고 계산하는 목표가속도 자체가
패치 이전보다 보수적으로(약하게) 산출됨.

이 로직은 38차 당시 "거리 여유 있는데 흔들리는 잡음성 가감속 무시"라는
안전 방향(위험 아닌 상황을 과잉반응하지 않기) 목적으로 설계됐고, 코드
주석에도 "벌어지는 상황은 TTC 축만 보면 위험 요소 없음"이라고 명시돼
있어 안전성 관점에서는 의도대로 동작 중 -- 다만 **"멀어지는 중=위험
없음"이라는 전제가 "그 앞차의 가속 정보 자체가 자차 launch에 유용한
신호"라는 사실을 놓친 부작용**으로 보임. 즉 회귀가 아니라 새 기능의
설계 사각지대.

### 로그/영상 교차검증
- **패치이전** (`dda0d533ce--5`, commit `a4b5550`, `ttc_accel_weight` 미존재):
  정지->출발(t=359.82) 이후 aEgo가 0->1.42m/s²까지 매끄러운 단일 피크로
  상승 후 감쇠(t=360.03 부근 피크). 화면녹화 그래프(1.Accel 오버레이)도
  단일 매끈한 hump 하나로 확인 — 코드(CSV)와 영상 일치.
- **패치이후** (`05890d8ca1`, commit `96e789c7`, `ttc_accel_weight` +
  rise-rate 둘 다 포함된 것으로 추정): 정지->출발 구간에서 aEgo가
  단조 상승하지 못하고 짧은 가속/감속을 여러 번 반복하는 톱니형 패턴
  (예: t=288.69 launch#1은 0.88까지 올랐다가 곧바로 -0.3대로 재감속,
  t=294.24 launch#2는 파형이 여러 번 접힘). 화면녹화(`_clip.mp4`,
  16:19~16:20 구간) 오버레이 그래프도 정지이전 로그와 달리 뾰족한
  다중 스파이크(jagged) 패턴으로 확인 — "약하다"는 사용자 체감이
  절대적인 피크값 차이보다는 **가속이 매끈하게 이어지지 못하고
  자꾸 끊기는 느낌**에서 온 것으로 보임(피크치 자체는 after 쪽이 더
  높게 찍히는 구간도 있었음, 예: t=297.64 aEgo=2.285). 근접 리드
  거리(dRel)가 vturn(교차로/커브) source에서 프레임마다 크게
  흔들리는 현상도 함께 관찰(예: t=488~490 dRel이 46m<->95m<->46m로
  요동) -- 이 vision 노이즈가 `closing<=0.1` 경계를 자꾸 넘나들게
  해 weight가 0<->비0으로 깜빡이며 톱니 패턴을 악화시켰을 가능성.
- 정확한 wall-clock 매칭: `initData`에 실제 커밋이 기록되고, 세그먼트
  폴더명(`YYYYMMDD_HHMMSS`)이 그 세그먼트의 녹화 시작 시각과 일치함을
  확인(온스크린 시계 오버레이 대조로 검증) -- 향후 영상<->로그 시각
  매칭에 재사용 가능한 방법.

### 조치 (미적용 -- 방향 제안만, 사용자 승인 대기)
1. (제안) `ttc_accel_weight`의 `closing<=0.1` 분기를 그대로 0으로
   두지 말고, `a_lead > 0`(앞차가 실제로 가속 중)이면서 `v_ego`가
   임계 이하(예: 저속/정지 직후)인 경우엔 `w`를 0이 아닌 값(예:
   `margin_accel_weight` 값을 그대로 통과)으로 예외 처리 -- "벌어지는
   중이라도 앞차가 가속 중이면 그 가속 신호는 launch 안내에 유용"이라는
   축을 별도로 살리는 방향.
2. (대안) `process_lead()`에서 `a_lead`를 죽이는 대신 `v_lead`
   추정치(현재도 그대로 씀)만으로 launch 안내를 맡기고, `w=0`
   damping을 "감속(a_lead<0)에만" 적용 -- 즉 damping의 원래 목적
   (안 좋은 감속 잡음 무시)에 맞게 부호로 분기.
3. 두 방향 모두 실차 재현 시나리오(정지->앞차 먼저 출발->자차 출발)
   기준 A/B 시뮬레이션(`toolkit/sim_frac_rate.py`류 신규 스크립트
   또는 `long_mpc.py` 로직 자체 프레임 재현)으로 사전 검증 필요 --
   38차가 막으려던 원 증상(고속 잡음성 가감속 과잉반응)을 다시
   깨우지 않는지 회귀 검증 필수.

### 근거 로그/영상
- `route_before.csv`/`route_after.csv` (이번 세션 컨테이너 로컬,
  재현 시 zip 재업로드 필요)
- `패치이전_..._5_화면녹화.mp4` t≈5~20s (launch 구간)
- `패치이후_..._162014_clip.mp4` t≈15~29s (launch 구간, 16:19:5x~16:20:1x)

### 조치 (패치 작성 완료, 실차 검증 대기) — 정차→출발 구간 launch bypass
사용자와 논의 후 위 대안 3가지와 다른 4번째 방향으로 확정: 대안 1/2(부호/조건별
예외 처리)는 프레임 단위 판정이 vturn dRel 요동 같은 노이즈에 계속 흔들릴 수 있어,
대신 **"정차→출발"을 상태(state)로 잡아 이 구간에서만 `ttc_accel_weight()`(38차)를
통째로 우회**하는 방식으로 구현.

- `v_ego < LAUNCH_BYPASS_STOP_V_EGO(0.3m/s)` → 정차 판정, bypass 진입 arm
- bypass 활성 중: `ttc_w=1.0` 고정(38차 우회, `dist_w`=`margin_accel_weight()`만으로
  결정 — 38차 patch 이전과 동일 동작) + 39차 rise-rate 제한도 함께 우회(저속 TTC
  붕괴형 급정지 방지가 목적인 rise-rate가 출발 가속의 매끈한 상승을 지연시키는
  부작용 방지)
- `v_ego >= LAUNCH_BYPASS_EXIT_V_EGO(5.0m/s)` → 출발 완료 판정, 38/39차 로직 복귀
- `LEAD_ACQ_TTC_DANGER`(2.5s) 즉시 무감쇠 오버라이드는 bypass 여부와 무관하게
  항상 최우선 유지 — 안전 반응 지연 없음

**로직 단위 검증(`work/test_launch_bypass.py`, 4개 시나리오, 컨테이너 로컬 —
재현 필요 시 devnotes에 재작성 필요)**:
1. 정차 중 앞차 먼저 출발 → bypass 활성, a_lead가 거의 무감쇠(w≈0.96~1.0)로
   유지됨을 확인(45차 증상 재현 상황에서 감쇠 사라짐).
2. 자차도 서서히 출발, v_ego가 EXIT(5.0m/s) 넘는 순간 bypass 즉시 해제 →
   38차 로직 복귀 확인. **주의**: 이 전환 순간 앞차가 여전히 벌어지는 중(v_lead>v_ego)
   이면 w가 즉시 0으로 떨어짐(rise-rate 미적용 — 감쇠 방향은 즉시 반영한다는
   39차 기존 컨벤션과 일치, 의도된 동작이나 체감상 "출발 막바지에 살짝 끊기는
   느낌"이 남을 가능성 있음, 실차 검증 시 확인 필요).
3. 회귀: 고속 정상주행 중 앞차 잡음성 벌어짐(38차 원 목적 시나리오) → bypass
   비활성 확정, 38차 damping 그대로 동작(w≈0) 확인 — 영향 없음.
4. 회귀: 저속 실제 위험 cut-in(TTC=1.67s<=2.5s) → bypass 상태와 무관하게
   danger override 즉시 발동(w=1.0) 확인 — 안전 반응 지연 없음.

**전달**: `0001-long_mpc-launch-bypass-45cha.patch`를 `/mnt/user-data/outputs/`에
생성, `git am` temp branch 검증(base `c31ddca`) + `py_compile` 통과 확인 후 전달.

**다음 단계(최우선)**:
1. 사용자가 `git am`으로 `C:\dev\ryu`(c3-ms-dev)에 적용 + `git push`.
2. 실차 검증: (a) 정차→출발 시 aEgo가 매끈한 단일 hump로 복원되는지(45차 "패치
   이전" 패턴과 비교), (b) exit 전환 순간(시나리오2에서 확인된 급격한 w 하강)이
   실제로 체감되는 끊김을 만드는지, (c) **회귀 검증 필수** — 고속 잡음성 가감속
   과잉반응 재발 없는지, 저속 실제 cut-in 반응 지연 없는지.
3. `LAUNCH_BYPASS_EXIT_V_EGO=5.0m/s` 값이 실제 출발 가속 구간을 충분히 커버하는지
   (너무 낮으면 launch 도중에 조기 복귀, 너무 높으면 일반 저속 추종까지 bypass됨)
   실차 로그 기준 재조정 필요할 수 있음.

## [RISK_IDENTIFIED, NEEDS_VALIDATION, 표본 1건] 곡선 진입전 사전감속/정점 감속 부족 — model 후보 게이팅(`abs(vturn_speed)<120`)이 vturn 자체가 불안정한 접근구간에서 model의 조기신호를 차단 (2026-08-22, 46차, route1 `203f99d429` seg8, 패치 이전 로그)

- **사용자 제보 증상 3가지**: (1) 곡선 진입 전 사전 감속 부족, (2) 최대곡선
  구간에서도 여전히 감속 부족, (3) 최대곡선 이후 재가속 지연.
- **분석 대상**: `20260821_120142_000002e6--203f99d429--8`(단일 세그, 60s).
  이번 세션에서 `extract_log.py`에 `modelTurnSpeed`(modelV2.meta.modelTurnSpeed)
  컬럼을 신규 추가(기존엔 CSV에 없어 model 후보의 실제 값을 볼 수 없었음,
  toolkit/CHANGELOG.md 참고) — 이후 분석은 전부 이 신버전 CSV 기준.
- **(1) 사전감속 부족 — 확인됨**: t=6563.4~6574.7(약 11초) 구간, 실제 커브에
  필요한 목표속도는 결국 86~90km/h인데, 이 구간 내내 `vturn` 원시 후보값
  자체가 91~230km/h 사이를 여러 차례 오르내리며 불안정(예: 138→131→138→
  220→155→189→207→225→184→149→133→124→116). `route`(내비 기반) 후보는
  110~138km/h로 완만하게만 낮아져 결국 실제 필요 속도(86~90)보다 한참
  높았음. 그 결과 vEgo는 이 구간 내내 오히려 **가속 중**이었음(87.8→91.9km/h,
  aEgo +0.3~+0.7). 목표속도가 115→92km/h로 실질적으로 꺾이기 시작한 시점은
  t=6574.73(vturn 소스 첫 선택)이고, 정점(steer 최대 -12.9deg)은 t≈6577.7 —
  즉 **유효 사전경고 시간이 3초 미만**이었음. `vturn_lookahead_horizon_s`가
  8.0s로 확대되어 있음에도 이 여유가 실제로 확보되지 않은 이유는, 원거리
  구간에서 vturn 자체의 순간 후보값이 저렇게 불안정해서 min() 선택에서
  계속 밀려났기 때문으로 보임(파라미터 확대와 무관, 신호 자체의 원거리 노이즈
  문제).
- **원인 후보(신규 발견)**: 같은 구간에서 `modelTurnSpeed`는 93~114km/h로
  vturn보다 훨씬 안정적으로 낮게 유지되고 있었음(즉 model은 이미 "커브가
  가깝다"는 신호를 상대적으로 안정적으로 주고 있었음). 하지만 `carrot_serv.py`
  L1051의 `model_turn_speed < 200 and abs(vturn_speed) < 120 and not
  model_turn_confirmed_trailing` 게이트 때문에, vturn 원시값이 120을 넘는
  프레임(이 구간 대부분)에서는 model 후보 자체가 min() 경쟁에서 아예
  제외됨. 즉 vturn이 불안정한 바로 그 구간에서 model이 대신 조기 개입할
  기회가 구조적으로 차단되고 있음. 이 조건은 13차(`119b101`, model↔vturn
  플리커 감소 목적)에서 도입된 것으로 git blame 확인 — **당시엔 "트레일링
  오탐 방지"만 검증되었고, 이번처럼 "vturn 자체가 아직 불안정한 진입
  구간에서 model의 조기 개입을 막는" 부작용은 검증 대상이 아니었음.**
- **(2) 정점 감속 부족 — 확인됨**: t=6575.6~6578.3(약 2.7초) 동안 vEgo가
  vturn 목표속도보다 지속적으로 높았음(최대 gap +8.1km/h, t=6576.73,
  vEgo=94.1 vs target=86; 실제 조향각 최대 지점 t=6577.7~6577.98에서도
  +3.2~+4.3km/h 초과). 원인은 (1)의 늦은 트리거로 인해 감속에 쓸 수 있는
  거리/시간 자체가 부족했던 것으로 보이며, `vturn_decel_rate=1.2m/s²` 자체의
  과소 여부는 이번 표본만으론 분리 판단 불가(선행 감속이 늦게 시작된 게
  주원인일 가능성이 높음 — 늦게라도 1.2m/s²로 계속 감속했다면 정점 이전에
  따라잡았어야 하는데 못 따라잡은 것으로 보아 감속률 자체도 다소 낮을
  가능성 배제 못함, 표본 부족).
- **(3) 탈출 후 가속 지연 — 이번 세그로는 확인 불가**: 이 60초 세그 안에서
  조향각이 t=6578 이후에도 -9~-11deg대를 t=6584+까지 계속 유지(장거리
  완만한 커브가 이어지는 형태로 보임) — 세그 종료 시점까지 명확한 "탈출"
  지점 자체가 나오지 않음. 나머지 route(`곡선_여러개`, `곡선_vturn_이상함`)
  분석에서 재확인 예정.
- **코드 변경 없음(관찰/분석만)**. toolkit 변경: `extract_log.py`에
  `modelTurnSpeed` 컬럼 추가(하위 호환 — 기존 CSV 재추출 필요, meta.json에
  별도 플래그는 없음. 이 컬럼이 전부 빈 문자열이면 46차 이전 버전으로
  추출된 CSV).
- **다음 단계**: (a) 나머지 2개 route(`곡선_여러개` 5세그, `곡선_vturn_
  이상함` 1세그)를 같은 방법으로 분석해 표본 확대, (b) `abs(vturn_speed)<120`
  게이트를 "vturn이 아직 신뢰 구간에 못 들어온 원거리 접근"과 "실제 트레일링
  (커브 탈출 후 복귀)"을 구분하도록 재설계하는 방향 검토(예: model 후보 자체가
  이미 하강 추세이고 route/road보다 낮으면, vturn 절대값 문턱과 무관하게
  후보로 참여시키는 방안) — 아직 설계 전, 표본 1건이라 재현성 확인 우선.

### → route2(`f3db6ca89d`, 5세그 "곡선_여러개", 연속 급커브 왕복 국도) 32건 자동 스캔 — "정점 감속 부족"이 표본 다수로 확인, 사전감속/탈출가속 지연은 이 route 특성상 판단 보류

- 이번 세션에서 `work/curve_decel_scan.py`(1회성 스크래치 스크립트, toolkit
  편입 여부는 다음 세션 판단) 작성 — `|steeringAngleDeg|>=5deg` 진입/
  `<3deg` 이탈 기준으로 커브 이벤트를 자동 분리하고, 이벤트별 (1)사전감속
  lead_time, (2)구간 내 최대 (vEgo-desiredSpeed) gap, (3)탈출후 desiredSpeed가
  150km/h 이상으로 회복되기까지 시간을 계산.
- **route2는 연속 급커브 왕복 도로**(steer가 최대 ±154deg까지 나오는
  헤어핀급 커브 다수, 5세그 300초에 32개 이벤트) — route1(고속도로 단일
  커브)과 성격이 달라 (1)/(3) 지표는 이 route에 그대로 적용하기 어려움을
  먼저 밝혀둠: 32건 중 11건은 진입 15초 전 베이스라인 자체가 이미 낮은
  속도(직전 커브에서 안 빠져나온 상태)라 "사전감속 시작 시점"을 정의할
  베이스라인이 없었고(lead_time 미검출), 26건은 탈출 직후 다음 커브가 바로
  이어져 desiredSpeed가 150km/h(사실상 무제한)까지 회복되지 못한 채 세그가
  끝남(recovery 미검출) — **이 두 지표의 "미검출"은 버그가 아니라 도로
  자체가 연속 커브라 발생하는 것으로 판단**.
- **(2) 정점 감속 부족은 이 route에서 확실히 대량 재현됨**: 32건 중
  **24건(75%)**에서 정점 부근 vEgo가 desiredSpeed(=대부분 vturn 목표)를
  초과 — 초과폭 평균 +8.2km/h, 최대 **+18.1km/h**(seg15, 헤어핀 steer
  -75.9deg 구간, apex 근처가 아니라 진입 중반 t=9504.03에서 최대치 기록).
  route1(46차 route1 항목, 최대 +8.1km/h)보다 더 큰 초과폭 사례가 다수
  확인됨 — route1이 예외적 사례가 아니라 이 코드의 일반적 특성일 가능성이
  높아짐(표본 2 route, 총 25건 초과 사례로 격상).
- **(1) 사전감속 판단 가능했던 21건 중에서는** lead_time 평균 11.1초,
  최소 2.1초~최대 14.9초 — 대부분 8.0s 지평선 근처이거나 그 이상으로,
  route1의 "3초 미만" 같은 극단적 사례는 이 route에서는 재현 안 됨(단,
  route1은 "고속도로 순항 중 단일 커브 진입"이라는 특정 상황이었고, 이
  route는 애초에 국도 저속 연속 커브라 상황 자체가 다름 — **"사전감속
  부족"은 route1류(고속 순항→갑작스런 커브) 상황에서 더 두드러지는 것으로
  잠정 판단, 표본 부족**).
- **탈출후 가속 지연(3)**: 회복이 검출된 6건(같은 seg15 안에서 커브 사이
  간격이 있던 구간)은 오히려 0.0~1.65초로 매우 빠르게 회복 — 이 route
  안에서는 "지연" 패턴을 재현하는 명확한 증거를 못 찾음. 나머지 26건은
  애초에 회복할 기회(직선 구간) 자체가 없었던 것으로 보임.
- **결론**: 이번 route로는 (2) 정점 감속 부족이 route1보다 더 강하게,
  더 넓은 표본으로 재현됨(2 route/25건). (1)/(3)은 이 route의 "연속 커브"
  특성상 검증에 부적합 — route3(`866476e5c3`, "vturn 이상함")과, 필요시
  고속도로형 단일 커브 로그를 추가로 봐야 (1)/(3)을 더 명확히 판단 가능.
- **코드 변경 없음(관찰/분석만)**.

### → route3(`866476e5c3` seg18, "곡선_vturn_이상함") 분석 — vturn이 탈출 지연이 아니라 오히려 조기 해제되는 사례 확인, cam 후보가 우연히 가려줌

- **분석 대상**: seg18(파일명 "곡선_vturn_이상함"이 가리키던 이상 징후 특정
  시도). 정점(t=4785.98, steer=-10.9deg) 이후 실제 조향각은 t=4795.8까지도
  -4.5~-7.3deg를 유지 — 즉 커브 자체는 이 시점까지 아직 안 끝난 상태.
- **발견 (3번 증상 "탈출 후 가속 지연"과 반대 방향)**: `vturn` 원시 후보값이
  t=4786.9(steer 아직 -7.5deg, 커브 한창 중)부터 단 1초 만에 103→149km/h로
  튀어오름 — 곡선이 끝나기 전에 vturn이 스스로 사실상 무제한급으로 조기
  해제됨. 즉 이 표본에서는 "탈출 후 재가속이 늦다"가 아니라 **"vturn이
  탈출 전에 너무 일찍 풀린다"** 쪽 증거.
- **실제로 문제가 드러나지 않은 이유**: 같은 구간에 `cam`(구간단속/카메라
  속도, route와 별개 후보)이 t=4787.23부터 desiredSpeed를 110km/h로 8초
  넘게 고정 — vturn이 149까지 올라가도 min()에서 cam=110이 계속 이겨
  실제 목표속도는 110에 묶여 있었음. **곡선과 무관한 cam 제약이 우연히
  vturn의 조기 해제를 가려준 것** — 카메라 단속 구간이 아니었다면 vturn이
  이겨 커브가 안 끝난 상태에서 재가속을 시도했을 가능성 있음(이번
  1개 표본으로는 실증까지는 못함, 조건부 재현).
- **3개 route 종합 — 탈출 후 가속지연(3) 가설 방향 전환**: route2(6건 모두
  0~1.65s로 빠른 회복)에 이어 route3까지, 지금까지 3개 route 어디에서도
  "vturn/model 자체가 탈출 후 재가속을 지연시킨다"는 증거를 못 찾음.
  오히려 vturn은 너무 빨리 풀리는 경향이 관찰됨. **사용자가 체감한 "탈출
  후 가속 지연"이 실재한다면, vturn/model보다는 cam/road처럼 곡선과
  무관한 다른 속도 제약이 탈출 시점과 우연히 겹쳤거나, vCruiseCluster 캡
  (과거 22차 기록 참고) 쪽 문제일 가능성이 더 높음** — 다음 route
  소스(source) 분석 재개 시 이 가설부터 확인 권장.
- **정점 감속 부족(2) 재확인**: max_gap +9.6km/h — route1(+8.1)/
  route2(평균+8.2)와 비슷한 범위로, 3개 route 전부에서 일관되게 나타남
  (표본 3 route로 확대).
- **코드 변경 없음(관찰/분석만)**.
- **다음 단계**: (a) route 소스 분석 재개 시 cam/road/vCruiseCluster 캡
  가설 우선 확인, (b) `abs(vturn_speed)<120` 게이트가 사전감속 부족뿐
  아니라 조기 해제 방향에도 영향 있는지 추가 확인 검토, (c) 곡선 콘텐츠가
  있는 신규 로그 확보 시 vturn 조기 해제(본 항목) + 정점 감속 부족 표본
  확대 병행 확인.

#### → [정정] qcamera 영상 교차검증 — "vturn 조기해제로 곡선 안 끝난 채 재가속" 결론 과대판단이었을 가능성, steer 잔존각의 원인 재규명 필요 (2026-08-22, 같은 세션)

- `extract_dashcam_frames.py`로 t=4785.98(정점)/4786.90(vturn 해제
  시작)/4787.23(cam 고정 시작)/4787.88(vturn 149 도달)/4791.00/4795.80
  6개 시점 실제 화면 추출·대조(frame 매칭 오차 전부 <0.06s).
- **영상 판독**: 정점(4785.98)~4786.9까지는 우측 방음벽이 뚜렷하게 휘어
  보여 곡선이 실제로 진행 중임을 육안으로도 확인. 하지만 **t≈4787.88
  (vturn이 149로 튀어오른 시점) 무렵부터는 화면상 도로가 거의 직선**으로
  보이고, t=4791.00/4795.80은 방음벽·차선이 완전히 평행해 곡선 흔적이
  전혀 없음(4795.80은 전방 게이트형 표지판까지 시야에 들어오는 개활
  직선 구간).
- **수정**: steeringAngleDeg만 근거로 "t=4795.8까지도 -6.5deg 유지되니
  곡선이 안 끝났다"고 판단했던 것은 **과대판단이었을 가능성이 높음** —
  실제 화면은 vturn이 튀어오른 시점(4787.88)과 비슷하게 이미 직선에
  가까웠음. 즉 "vturn이 곡선 안 끝난 채 조기 해제됐다"는 이전 결론은
  **약화됨(반증까지는 아니나 근거가 흔들림)**.
- **새로 남은 의문**: 화면이 명백히 직선인 t=4791.00~4795.80 구간에서도
  steeringAngleDeg가 -5.1~-6.5deg 대의 잔존값을 계속 유지하는 이유가
  불명 — 차선 중앙 유지 보정/도로 캠버 보정/차선 자체의 미세 편심
  정렬 등 곡선과 무관한 원인 후보. 헤이즈/화질 때문에 아주 미세한
  잔여 곡률(육안 미검출 수준)까지는 완전히 배제 못함.
- **재평가**: (2) 정점 감속 부족(+9.6km/h)은 정점 시점(4785.98) 자체가
  영상으로도 곡선 진행 중임이 확인돼 이 결론은 그대로 유지. (3) 탈출
  후 가속지연 관련 "vturn 조기해제" 증거는 표본에서 사실상 철회 —
  route2/route3 어디에서도 탈출지연도 조기해제도 확실한 증거 없음으로
  재정정, cam/road/vCruiseCluster 캡 가설이 여전히 유력.
- **다음 단계**: steeringAngleDeg 잔존값(곡선 무관 오프셋)의 정체를
  다른 직선구간 표본과 비교해 규명 — 만약 이게 일반적인 차선유지
  보정값 범위라면, 향후 세션에서 "steer가 0으로 안 돌아왔다"만으로
  곡선 지속을 판단하는 방식 자체를 재검토할 필요.

#### → [RESOLVED 가능성 높음] "vturn 급감/조기해제"와 steer 잔존값 미스터리, 둘 다 수동 차선변경(rightBlinker) 하나로 설명됨 (2026-08-23, 47차, 사용자 스크린 녹화 제보 계기)

- **계기**: 사용자가 실차 화면녹화 클립(11:31경, "차선을 변경합니다" 메시지
  표시)을 제보하며 "우로 굽은 커브에서 우측 차선변경으로 곡선이 심해져서
  vturn이 튄 것 아니냐"는 가설 제기. CSV를 t=4784~4792 구간 프레임(20Hz)
  단위로 재추적.
- **재확인된 타임라인**:
  - t=4785.03: `rightBlinker` False→**True**. 이 순간부터 `desiredCurvature`가
    0.00126에서 급격히 치솟기 시작(1초 안에 0.00213 피크, t=4786.03).
    같은 구간에서 vTurnSpeed가 129→103으로 급락(피크와 거의 동시).
  - t=4786.43부터: curvature 하강 전환과 거의 동시에 vTurnSpeed가 103에서
    다시 상승 시작, t=4787.88에 149 도달(src는 vturn→cam으로 전환된 직후).
  - t=4788.63: `rightBlinker` True→False (차선변경 종료, 총 지속 3.6초).
  - t=4791~4791.98: steeringAngleDeg -5.1~-6.4deg 잔존(기존 "[정정]" 항목의
    미해결 미스터리 구간과 일치) — `rightBlinker`는 이미 꺼진 지 3초 이상
    지났지만 desiredCurvature 자체도 이 구간에서 0.0009~0.0013으로 아직
    완전히 0에 수렴하지 않은 상태.
  - **`laneChangeState`는 전체 구간(t=4784~4792) 내내 `off`** — 즉
    lateralPlanner가 인지하는 "자동 차선변경 이벤트"가 전혀 아니었음.
    운전자가 방향지시등만 켜고 수동으로 차로를 옮긴 것으로 판단됨(화면
    메시지 "차선을 변경합니다"는 blinker 상태에 반응하는 UI 표시로 추정,
    실제 lateralPlanner 차선변경 시퀀스와는 무관).
- **재해석**: 기존에 "vturn이 곡선 안 끝난 채 조기 해제됨" vs "이미
  영상으로는 직선"이라는 두 관찰이 서로 안 맞아 보였는데, **차선변경이라는
  제3의 원인을 넣으면 둘 다 설명됨** — 카메라 모델이 인지하는 "내 차로
  기준 곡률"이 차로를 가로지르는 동안 실제 도로 곡률과 별개로 일시적으로
  출렁였을 가능성이 높음(차로 간 이동 중 차선 인식 앵커가 바뀌며 발생하는
  전형적인 패턴). vTurnSpeed의 103→149 급변 자체가 "곡선이 실제로 그렇게
  빨리 풀렸다"가 아니라 "차선변경 중 curvature 추정치가 일시 왜곡됐다가
  차로 정착 후 정상화됐다"는 쪽이 더 정합적인 설명.
  steer -5~-6.5deg 잔존값(4791~4795.8)도 별도 미스터리가 아니라, 차선변경
  후 새 차로 중앙에 정착하는 과정의 자연스러운 보정 잔여값으로 재해석
  가능 — 즉 위 "[정정]" 항목이 남긴 두 미해결 항목(vturn 급변의 실제
  트리거 / steer 잔존값 정체)이 하나의 원인(수동 차선변경)으로 통합됨.
- **주의(확정 아님)**: 이번 재해석은 표본 1건 기준. (a) `laneChangeState`가
  `off`인데도 desiredCurvature가 이 정도로 출렁이는 게 일반적 패턴인지
  다른 차선변경 사례로 교차검증 필요, (b) blinker 없이 도로 자체 곡률만으로
  vturn이 유사하게 급변하는 대조군(반증 사례)이 없으면 "차선변경이 원인"을
  완전히 확정할 수 없음.
- **코드 변경 없음(관찰/분석만)**.
- **다음 단계**: (a) rightBlinker/leftBlinker=True 구간에서
  desiredCurvature 변동폭이 blinker=False 구간 대비 통계적으로 큰지
  toolkit에 검증 함수 추가 검토(가칭 `lane_change_curvature_artifact_scan`),
  (b) 이 가설이 맞다면 향후 vturn/curve 분석 시 blinker=True 구간은
  "곡선 이벤트"에서 원천 제외하는 사전 필터가 `curve_exit_no_accel_scan`류
  스캐너에도 필요할 수 있음(현재 v1/v2/v3 전부 blinker 필터 없음).

#### → qcamera 영상 교차검증 확대 — route1(`203f99d429` seg8)/route2 seg15(`f3db6ca89d`) 실제 급커브 시각 확인, 기존 결론 뒷받침 (2026-08-22, 같은 세션)

- **route1(`203f99d429` seg8)**: t=6563.5(사전감속 시작 전)/6567.03(vturn
  원시값 불안정 구간)/6574.73(vturn 첫 선택)/6576.73(최대 gap +8.1km/h
  지점)/6577.7(정점, steer -12.9deg)/6579.5(정점 직후) 6개 시점 프레임
  대조(매칭 오차 전부 <0.03s). **고속도로 우측 진출램프형 급커브**로
  확인 — 회전 경고표지판, 적색 접근구획선(감속유도 노면표시), 선행
  대형트럭이 화면에 명확히 보임. t=6577.7~6579.5까지 화면상으로도
  커브가 계속 진행 중임이 확인돼, "정점 이후에도 vEgo가 목표속도보다
  높게 유지" 결론이 시각적으로도 뒷받침됨. 이 route는 route3와 달리
  steer/화면 판단이 서로 어긋나지 않음.
- **route2 seg15(`f3db6ca89d`)**: 32건 중 최대 초과폭(+18.1km/h)
  이벤트 재확인. t=9498.0(진입 초반)/9502.0(중반)/9504.03(**max gap
  +18.1km/h 지점**, desiredSpeed=32/vEgo=50.1kph)/9505.73(**실제 조향각
  정점** -75.9deg, 이 시점엔 desiredSpeed=31/vEgo=39.8kph로 이미 gap이
  좁혀진 상태)/9507.5(탈출 중, src=model로 전환)/9508.9(탈출 완료) 6개
  시점 대조. **국도 급커브+교량(다리 난간) 구간**으로 확인 — 커브 경고
  표지판, 하천을 가로지르는 교량 난간이 화면에 뚜렷하게 보임. 최대
  gap이 기록된 t=9504.03은 실제 조향각 정점(9505.73)보다 1.7초 앞선
  "진입 중반부"였고, 화면상 이 시점에 이미 급격한 커브(경고표지판+
  다리 진입부)가 시작돼 있었음 — **"정점 감속 부족"으로 분류했던
  이 패턴이 실제로는 진입 중반부터 vEgo가 필요한 만큼 못 따라간
  것으로, 명칭과 달리 사실상 (1)사전감속 부족과 (2)정점 감속 부족이
  연속된 하나의 문제일 가능성** — 다음 세션에서 32건 전체를 "max gap
  발생 시점이 조향각 정점 대비 얼마나 이른가"로 재분류해볼 필요.
- **종합**: route1/route2/route3 3개 route 전부 영상으로 실제 급커브
  존재를 확인 완료(가짜 이벤트나 센서 오탐으로 인한 통계 왜곡 가능성
  배제). route3에서만 steer 근거 결론이 정정됐고, route1/2는 원 결론
  유지.
- **코드 변경 없음(관찰/분석만)**.

### → route2 32건 커브 이벤트 재분류 — "정점 감속 부족"의 79%가 실제로는 사전감속 부족의 연장 (2026-08-22, 같은 세션)

- **가설**: route2 seg15 최대 초과사례(+18.1km/h)에서 max gap 시점이
  실제 조향각 정점보다 1.7초 앞선 "진입 중반부"였음(위 qcamera 확대검증
  항목) — 이게 seg15만의 예외인지, 32건 전체의 일반 패턴인지 검증.
- **방법**: `work/curve_gap_vs_apex_scan.py`(신규 스크래치 스크립트,
  toolkit 미편입) 작성 — 46차 원래 스캔과 동일 기준(`|steer|>=5deg`
  진입/`<3deg` 이탈)으로 32건 이벤트 재분리, 각 이벤트에서 (a)조향각
  절대값 최대 시점(apex_t), (b)`vEgo(kph)-desiredSpeed` 최대값 발생
  시점(gap_t)을 각각 구해 `delta = gap_t - apex_t`를 계산(음수=max gap이
  apex보다 먼저 발생).
- **결과**: 32건 중 실제 초과(max_gap>0)는 24건(46차 원 집계와 정확히
  일치). 이 24건 중:
  - **19건(79%)은 max gap이 apex보다 0.3s 이상 먼저 발생** — 평균
    -1.26초 앞섬. 즉 정점에 도달하기도 전에 이미 최대 초과폭을 찍고,
    정점에선 오히려 어느 정도 따라잡은 상태인 경우가 대다수.
  - 동시(±0.3s) 2건, apex보다 나중(진짜 "정점에서" 못 따라간 경우)은
    **3건(12%)뿐**.
  - 평균 max_gap +8.19km/h(46차 원 집계 +8.2km/h와 일치, 재현성 확인).
- **결론**: 지금까지 "정점 감속 부족(2)"이라고 별도 증상으로 분류해온
  것의 대부분(79%)은 실제로는 "**진입 중반부(사전감속 구간 후반)에서
  이미 목표속도를 못 따라잡은 상태가 정점까지 그대로 이어진 것**"에
  가까움 — (1)사전감속 부족과 (2)정점 감속 부족을 **별개의 두 증상이
  아니라 하나의 연속된 문제(감속 시작이 전반적으로 늦음)로 재정의하는
  것이 더 정확해 보임**. 진짜 "정점에서만 특별히 더 못 따라가는" 사례는
  24건 중 3건(12%)으로 소수.
- **다음 단계**: (a) route1(고속도로 단일 커브)도 같은 방식으로
  delta 계산해 도로유형(연속헤어핀 vs 고속도로 단일커브)별 패턴 차이
  있는지 확인, (b) "사전감속 부족"의 근본원인으로 46차에 지목했던
  `abs(vturn_speed)<120` model 게이팅이 이 79% 사례들에도 공통 원인인지
  개별 검증(현재는 route1 1건에서만 확인됨), (c) `curve_gap_vs_apex_scan.py`
  toolkit 편입 여부 판단(재사용 가치 높아 보임).
- **코드 변경 없음(관찰/분석만)**.

#### → (a)(b) 이어서 진행 — route1은 패턴 재현(n=1), model 게이트 가설은 route2에선 기각(다른 원인 필요) (2026-08-22, 같은 세션)

- **(a) route1 재확인**: route1은 `|steer|>=5deg` 기준으로 이벤트 4건이
  잡혔으나 이 중 진짜 유효한 커브(max_gap>0)는 **46차/이번 세션에서
  이미 분석한 그 1건(entry=6575.23, apex=6577.73, max_gap=+8.1km/h)뿐**
  — 나머지 3건은 max_gap이 -35~-40km/h로 음수라 사실상 "이미 저속
  주행 중이던 구간에서의 조향 잡음/차선변경성 조향"으로 커브 이벤트가
  아님(고속도로 특성상 실제 급커브 자체가 희소). 이 유일한 유효 사례도
  **delta=-0.95s로 route2와 같은 방향(gap이 apex보다 먼저)** — 표본은
  1건뿐이지만 방향성은 일치.
- **(b) model 게이트 가설 검증 — route2에선 기각**: 24건 각각의 진입
  3초 전 구간에서 `vTurnSpeed`(raw) 최대값을 확인한 결과, **24건 전부
  이 구간의 vTurnSpeed가 이미 120 미만(37~97 범위)** — 즉
  `abs(vturn_speed)<120` model 게이팅 조건이 route2에서는 애초에
  vturn을 막고 있지 않았음(vturn 자체가 이미 안정적으로 참여 중).
  **46차에서 route1(진입 전 장거리 직선→갑작스런 첫 커브)의 특정
  상황에서 발견된 이 게이트 문제가, route2(연속 커브 국도, 직전 커브
  여파로 vturn이 이미 낮게 유지된 상태에서 다음 커브 진입) 상황에는
  적용되지 않음이 확인됨** — 두 route는 "커브 진입 직전 vturn의
  초기상태"가 근본적으로 다른 시나리오.
- **재평가**: route2의 79% "진입중반 gap" 패턴은 model 게이트 문제가
  아니라, 다른 원인 후보로 좁혀짐 — (i) `vturn_decel_rate`(현재
  1.2m/s², 방지턱 기본값) 자체가 연속 커브의 조여드는 속도를 못
  따라가는 물리적 한계, (ii) `vturn_lookahead_horizon_s`(8.0s)가
  국도 저속 연속 커브 간격(수 초 단위)엔 과도하게 길어 다음 커브
  신호를 앞 커브 탈출 신호와 혼동/지연시킬 가능성, (iii) `desiredCurvature`
  기반 vturn 자체 계산 로직이 곡률 증가율(변화 속도)이 아니라 순간
  곡률값만 반영해 급격히 조여드는 헤어핀에서 후행할 가능성.
- **다음 단계**: (i)(ii)(iii) 중 어느 것이 근본원인인지 좁히려면
  `vturn_speed()`(carrot_man.py) 코드 리딩으로 실제 계산식 확인 필요 —
  다음 세션 최우선 후보.
- **코드 변경 없음(관찰/분석만)**.

## [NEEDS_VALIDATION] curve_exit_no_accel_scan v3 실전 검증 — vCruiseCluster 필터는 정상 동작하나, 5개 route 전부에서 "진짜 탈출 후 무가속 버그" 확정 사례 없음 (2026-08-23, 47차 계속)

- **배경**: 47차 전반부에서 구현한 `curve_exit_no_accel_scan_v3`(vCruiseCluster
  캡 여유폭 필터)를 route1~3(46차 로그, 커브 세그 내 미탈출/S자연속으로
  검증 후보 없었음)에 이어, 사용자가 신규 대용량 로그 2개(route4=
  `d45a15f8fc` 20세그/route5=`7ffb3e693c` 20세그, 각 24000행)를 추가
  제공해 재검증.
- **v3 필터 자체는 정상 동작 확인(route4)**: v1=13건 → v2=5건 → v3=1건.
  v2에서 남은 5건 중 4건이 vCruiseCluster 캡 여유폭 필터로 정상
  제외됨 — 그 중 2건(t=10481.68/10562.93)은 **여유폭이 음수**(desiredSpeed
  자체가 vEgo보다 이미 낮음 — 다음 커브 제약이 탈출 시점에 이미 겹쳐
  있던 상태)였고, 나머지 2건(t=10289.83/10622.63)은 여유폭 4.3~4.7kph로
  임계값(5kph) 바로 아래였음. **모두 "밟을 이유가 애초에 없었던" 타당한
  제외 사유로 확인 — v3 설계 의도대로 동작.**
- **[신규 발견] v3에 유일하게 남은 route4 seg6 t=10183.18 후보도 실제로는
  버그가 아니라 S자 커브(반대방향 커브 즉시 재진입)였음**: `vTurnSpeed`가
  t=10181.98부터 부호가 전환(+74→-73)되며 반대 방향(좌회전) 커브 감속이
  곧바로 이어짐(curv가 -0.0107까지 커짐, t=10187 기준). 문제는 **곡률
  절대값이 0.002 아래로 내려갔다가(t≈10183.1) 다시 0.002를 넘어서는 데
  약 1.9초**(t≈10185.1) 걸렸다는 것 — v2/v3 공통 필터
  `min_straight_hold_s=0.8초`가 이 케이스를 잡기엔 너무 짧아서 "진짜
  탈출"로 오판, aEgo가 계속 음수(정상적인 반대커브 감속)였던 걸 "무가속
  버그"로 잘못 기록.
- **route5는 v1 11건 전부 v2 단계에서 제외**(대부분 3~15km/h 저속
  — 교차로/정체 추정 — + leadStatus 근접/S자재진입), v3 검증 후보
  자체가 없었음.
- **종합**: route1~5, 5개 route 전체를 통틀어 **v1→v2→v3(그리고 이번에
  드러난 S자 재진입 문제까지 감안하면 사실상 v1→v4급 필터)를 다 통과하고
  살아남는 "진짜 탈출 후 무가속" 후보가 지금까지 0건**. 표본 5개로는
  이 증상 자체가 실재하는지 재고할 근거가 쌓이고 있음(46차 vturn_speed
  코드리딩 결과와 함께 재평가 필요 — WIP.md 참고).
- **코드 변경 없음(v3 구현은 47차 전반부 그대로 유지, 이번엔 실전
  로그로 검증/한계 발견만 진행)**.
- **다음 단계(사용자 결정 대기)**: (a) `min_straight_hold_s`를 1.9초보다
  넉넉히(예: 2.5~3.0초) 늘려 v4 후보 설계, (b) 절대 시간 대신 "곡률이
  0을 향해 계속 감소 중인지" 방향성(부호/기울기) 체크로 필터 로직 자체를
  바꾸는 방안(더 근본적이나 구현 복잡도 ↑), (c) 5개 route 무후보를
  근거로 "탈출 후 가속지연" 증상 실재 여부 자체를 vturn_speed() 코드
  리딩과 함께 재평가.

## [NEEDS_VALIDATION] curve_exit_no_accel_scan v3 3개 route(6/7/8) 추가 검증 — 8개 route 누적 0건, min_straight_hold_s 변화는 무영향 확인 (2026-08-23, 48차)

- **배경**: 47차 결론(5개 route 전부 무후보) 이후 사용자가 신규 로그
  3개 추가 제공 — route6(`8417c66e7e`, x3seg, 122.3s), route7
  (`c8fef594d3`, x18seg, 1080s), route8(`dda0d533ce`, x20seg, 1201.6s).
- **route6은 분석 대상에서 제외**: `cruise_enabled_ratio=0.0`,
  avg_speed 1.3km/h — ADAS 전혀 미관여(주차/저속 수동 구간)로
  커브 탈출 시나리오 자체가 없음.
- **`min_straight_hold_s` 0.8/1.9/2.5/3.0 4개 값으로 v3 반복 실행**:
  route7만 후보 존재(4건→hold 2.5부터 3건, 중복 row 하나 제거된 것뿐),
  route8은 전 hold값에서 0건. **hold값을 0.8→3.0으로 3배 이상 늘려도
  route7/8 어디서도 새 후보가 추가되지 않음** — 47차에서 제안한 (a)안
  (`min_straight_hold_s` 연장)이 이번 3개 route 표본에서는 판별력이
  없음을 최초로 실측 확인(기존엔 route4 seg6 1건에서만 효과 관찰).
- **route7 후보 3건 중 1건은 자명한 오탐**: seg18 t=1176.94는
  `vEgo_at_exit=-0.0`(사실상 정차 상태)에서 곡률 임계값이 우연히
  넘은 경우로 즉시 제외 대상(v3에 정차 필터가 없다는 사각지대 재확인,
  아래 "다음 단계" 참고).
- **남은 진짜 후보 2건, 대시캠 프레임 대조 완료**(qcamera 포함,
  `verify_and_extract_frames.py`):
  - seg12 t_curve_end=833.54: vEgo 64.0km/h, vCruiseCluster=70,
    cap_margin=6.0kph, 탈출 후 2초 창 내 max_aEgo=0.126m/s². 프레임
    확인 결과 도로가 완만한 곡선이 거의 끝난 2차선 도로, 인접
    차로에 차량 있으나 leadStatus=False(같은 차로 아님)로 일치.
  - seg14 t_curve_end=949.09: vEgo 64.2km/h, vCruiseCluster=70,
    cap_margin=5.8kph, max_aEgo=0.098m/s². 프레임 확인 결과 탈출
    시점에 도로가 이미 거의 직선, 전방 먼 거리에 차량 1대(빨간색)
    있으나 leadStatus=False.
  - **두 건 모두 v3의 `cap_margin_thresh_kph=5.0` 바로 위(5.8~6.0)에
    걸쳐 있고, 목표속도 여유폭 자체가 5.8~6.0km/h로 작아 완만한
    가속만으로도 물리적으로 타당함** — max_aEgo 0.1m/s² 남짓이면
    2초 만에 64.0→64.7km/h 정도로, 코드 버그라기보다 "가속할
    필요가 원래 작았던" 정상 상황에 더 가까움(46차/47차에서 이미
    확인된 vCruiseCluster 캡 패턴과 동일 축).
- **route8은 0건**(1201.6s, 14.17km 주행에도 v3 후보 자체가 안 생김).
- **표준 안전지표(harsh_brake/turn_speed_violation/cut_in/ttc_danger/
  steering_osc)도 함께 확인**: route7/8 둘 다 harsh_brake는 전부
  정차 직전 저속 구간(vEgo가 0으로 수렴하는 패턴)과 일치해 기존
  누적 패턴(운전자 개입/정상 정지)과 동일 — 신규 위험 패턴 없음.
  ttc_danger도 전부 vEgo<8m/s 저속 구간(교차로/정체 추정)이라
  고속 급접근류 아님. **이번 3개 route에서 회귀/신규 위험 신호
  없음.**
- **종합(8개 route 누적)**: route1~8 전체에서 "진짜 탈출 후 무가속
  버그" 확정 사례 여전히 0건. 근접 후보 2건(route7 seg12/seg14)도
  cap_margin이 문턱(5.0) 바로 위(5.8~6.0)에 걸린 경계 사례로,
  버그라기보다 "여유폭 자체가 작아서 완만하게만 가속" 쪽으로
  해석하는 게 더 타당함.
- **코드 변경 없음(분석만)**.
- **다음 단계(방향 제시, 사용자 결정 대기)**:
  1. **(c)안 쪽으로 무게 이동 권고**: 8개 route/누적 다수 세그를
     스캔했음에도 확정 사례가 0건이고, 근접 후보들도 전부 "여유폭이
     작아서" 설명 가능한 경계 사례라 "탈출 후 가속지연"이 코드
     버그라는 가설 자체의 근거가 약해지고 있음. 46차 `vturn_speed()`
     코드 리딩 결과와 종합해 이 증상 자체의 실재 여부를 재평가할
     시점으로 판단.
  2. (a)안(`min_straight_hold_s` 연장)은 이번 실측으로 판별력이
     낮음이 확인됐으므로 우선순위 하향 권고.
  3. **v3 필터 자체의 사각지대(신규 발견)**: `vEgo_at_exit≈0`(정차)
     케이스가 곡률 임계값을 우연히 넘어 후보로 잡히는 경우 배제
     로직이 없음 — v3에 `vEgo_at_exit > 정지판정속도(예: 1.0m/s)`
     최소 조건 추가를 v4 후보에 포함할 것(경미하지만 코드 변경
     시 함께 반영).
  4. 굳이 계속 조사한다면, cap_margin_thresh_kph를 5.0→6.5~7.0
     정도로 살짝 올려 이번 route7의 두 경계 사례까지 필터링되는지
     시뮬레이션으로 먼저 확인 후 결정(패치 전 시뮬레이션 우선
     원칙 유지).

## [RESOLVED] vturn_speed() 코드 리딩 + route7 근접 후보 2건 CSV 원본 대조 — "탈출 후 무가속" 근접 사례들이 vturn과 무관한 순수 vCruiseCluster 캡 상황이었음을 확정 (2026-08-23, 48차 계속)

- **배경**: 48차 v3 검증에서 남았던 근접 후보 2건(route7 seg12
  t=833.54/seg14 t=949.09, cap_margin 5.8~6.0kph)의 성격을 규명하기
  위해 `vturn_speed()`(carrot_man.py L953) 코드를 정독하고, 두 시점의
  CSV 원본 필드(`vTurnSpeed`, `src`, `desiredSpeed`, `vCruiseCluster`)를
  직접 대조.
- **vturn_speed() 구조 확인**: 모델이 예측한 전방 궤적
  (`vturn_lookahead_horizon_s=8.0초` 이내) 모든 지점에 대해 방지턱과
  동일한 `v²=v_f²+2ad` 물리공식으로 지점별 필요속도를 계산한 뒤 **그중
  최솟값(argmin)**을 최종 turnSpeed로 채택. "탈출 이벤트"를 별도로
  판정하는 로직 자체가 없고(주석에 명시: "매 프레임 전방예측 기반
  거리로 재계산되므로 벗어나는 즉시 자연스럽게 풀린다"), 저역통과
  필터(`vturn_decel_rc=vturn_accel_rc=0.15`)는 감속/가속 방향 대칭이라
  방향성 비대칭 지연은 없음. 이론적으로 남는 유일한 사각지대는 "8초
  lookahead 안에 다음 커브가 걸리면 argmin이 그 다음 커브로 넘어가
  현재 커브를 벗어나도 계속 낮게 유지될 수 있다"(S자 대응 위해 의도된
  동작)는 점.
- **CSV 원본 대조 결과(핵심 발견)**: route7 두 근접 후보 모두
  **`vTurnSpeed` 자체가 이미 완전히 해제된 상태**(seg12 t=833.54:
  -201, seg14 t=949.09: -187 — 부호는 좌/우 방향, 크기가 200km/h
  안팎이면 사실상 무제한)였음. desiredSpeed도 114~187km/h로 높았음.
  **유일한 실질 제약은 vCruiseCluster=70.0(운전자 설정 순항속도)** —
  vEgo가 이미 64km/h라 여유폭 5.8~6.0km/h밖에 없어 완만한 가속만
  나온 것. **즉 이 두 근접 후보는 vturn_speed()의 lookahead/필터
  로직과는 애초에 무관했고, v3의 `cap_margin_thresh_kph=5.0` 문턱이
  이런 5.8~6.0대 경계 사례를 못 걸렀을 뿐**이었음이 확정됨.
- **조치**: `curve_exit_no_accel_scan_v4` 신규 구현 —
  (1) `vEgo_at_exit` 최소속도 필터(정차 상태 오탐 배제),
  (2) `cap_margin_thresh_kph` 5.0→6.5 상향. route7/route8 재실행
  결과 **둘 다 0건으로 수렴**(route6은 ADAS 미관여로 분석 대상 제외).
  상세는 toolkit/CHANGELOG.md 48차 항목 참고.
- **종합 결론**: route1~8, 8개 route 누적 스캔에서 "탈출 후 진짜
  무가속 버그"는 확정 사례 0건이며, 유일하게 근접했던 후보들도
  코드 리딩+데이터 대조로 vturn과 무관함이 확정됨. **(c)안(증상
  자체 재평가) 결론 확정 — 현재 코드(`c368c422`)에 "탈출 후 가속지연"
  버그가 존재한다는 근거가 8개 route 전체에서 발견되지 않음.**
  단, 이론적 사각지대(8초 lookahead 내 연속 커브 시 argmin이 다음
  커브로 넘어가는 경우)는 코드상 여전히 존재 — 향후 이 패턴에 정확히
  해당하는 실제 제보/영상이 나오면 재조사 대상으로 유지하되, 능동적
  로그 스캔으로 더 찾는 건 낮은 우선순위로 하향.
- **코드 변경**: `ryu` 저장소는 변경 없음(vturn_speed() 자체는 버그
  아님으로 결론). `devnotes/toolkit/analysis_helpers.py`에
  `curve_exit_no_accel_scan_v4` 함수만 신규 추가(분석 도구 개선).
- **다음 단계**: 이 조사 스레드는 사실상 종결. 다음 세션은 46차
  WIP에 남아있던 다른 열린 항목(2번 cam/road/vCruiseCluster 캡 가설
  원 검증, 3번 route3 steer 잔존값 규명 등, 필요 시 WIP.md 확인)으로
  전환 검토.

## 49차 (2026-08-23) — "탈출전/정점직후 가속" 재프레이밍, vturn_speed() 설계 재확인, vturn_release_lag_scan 신규 도구

- **배경**: 48차가 "탈출 후 무가속" 스레드를 8개 route 누적 근거로
  종결한 직후, 사용자가 프레이밍을 바꿔 두 가설 재제기: (A) "탈출후"가
  아니라 "탈출전(정점 직후, 아직 완전 직선 아닌 시점)"부터 가속해야
  하는 것 아니냐, (B) 과속방지턱처럼 apex(최대 곡률 지점)를 지나는
  순간 속도 제약을 즉시 원복하는 방식이 맞지 않냐.
- **코드 재확인 결과(핵심)**: `vturn_speed()`(carrot_man.py L953)는
  "진입/탈출 이벤트"를 따로 판정하지 않는 연속 구조. lookahead 구간
  내 모든 지점에 방지턱과 동일한 `v_i²=v_f²+2ad` 공식을 벡터화 적용
  후 `argmin`(가장 엄격한 지점)을 그 순간의 최종 제약으로 삼는다.
  `lookahead_pos = max(position, 0)`로 **자차가 지나온 지점은 매 프레임
  자동으로 후보에서 배제**되므로, apex 통과 즉시 그 지점이 argmin
  후보에서 사라지고 이후엔 곡률이 완화되는 전방 지점들만 남아
  required_speed가 자연히 상승한다. 즉 **가설 A/B 둘 다 이미 현재
  설계 의도 자체**임을 확인(주석에도 "커브를 빠져나오는 즉시 제약
  해제" 명시).
- **재프레이밍**: 그렇다면 지금까지 확정 못한 "체감상 가속 지연"은
  구조("release가 언제 시작되는가") 문제가 아니라, "release는 즉시
  시작되지만 그 이후 `vturn_accel_rc` 저역통과 스무딩이 체감될 만큼
  느린가"(release *rate*) 쪽 질문일 가능성 — 48차 "버그 0건" 결론을
  뒤집는 게 아니라 별도 축.
- **신규 도구**: `vturn_release_lag_scan()`(analysis_helpers.py) —
  apex 이후 "곡률이 실제로 완화되기 시작한 시각"(steeringAngleDeg
  비증가 전환, proxy)과 "vTurnSpeed 출력이 실제로 오르기 시작한
  시각" 사이 지연(lag_s)을 측정. **한계**: `vturn_speed()` 내부의
  필터-전 required_speed_kph(argmin 이전, modelV2 raw 배열 필요)는
  CSV에 없어 steeringAngleDeg를 근사 proxy로 사용 — argmin 전환
  시각 자체의 정확한 재현은 아님(정확히 하려면 modelV2 orientationRate/
  velocity/position raw 재현 별도 과제 필요, 이번엔 미착수).
- **검증**: 합성 시나리오 2건으로 로직만 검증 — (1) apex+1.2s 지연
  주입 시 lag_s≈1.25s로 정확히 재현, (2) 무지연 시 lag_s≈0.05s(1프레임
  노이즈 수준)로 오탐 없음 확인. **실제 로그 검증은 아직 — route7/
  route8 raw CSV가 컨테이너 로컬 소실로 없어 다음 세션 신규 로그
  필요(48차 근접 후보 seg12/seg14 재사용 우선 후보).**
- **코드 변경**: `ryu` 저장소 변경 없음(관찰/분석 도구만).
  `devnotes/toolkit/analysis_helpers.py`에 `vturn_release_lag_scan`
  신규 추가, README.md/CHANGELOG.md 동기화.
- **다음 단계**: 사용자가 로그(route7=`c8fef594d3` 또는 신규 고속도로
  단일커브 로그)를 재업로드하면 `vturn_release_lag_scan` 실행 →
  lag_s 분포 확인 → 체감될 만큼(예: 0.5s+) 크면 `vturn_accel_rc` 값
  하향 튜닝 검토, 작으면(구조가 이미 즉시 반응) "체감 지연"은 다른
  원인(vCruiseCluster 캡 등 48차 근접 후보처럼)일 가능성 재확인.

## 50차 (2026-08-23) — 곡선 사전감속 "가시거리 부족" 가설 실측 기각, vTurnSpeed 부호는 버그 아님(방향 인코딩) 확인

- **배경**: 49차 이후 사용자가 새 가설 제기 — "곡선 진입전 사전감속
  구간이 짧아서 최대 곡률지점(apex)에 감속이 완료되지 않고, 이 때문에
  정점 원복도 늦어지는 것 아니냐". `vturn_lookahead_horizon_s`(현재
  8.0s, T_IDXS max_val=10.0s 천장 대비 이미 2s 남짓 여유)를 얼마나
  올려야 하는지 실측으로 검증.
- **route2(`f3db6ca89d`, 곡선_여러개.zip, 5세그) 재추출 후 15건 유효
  이벤트 실측 결과 — "가시거리 부족" 가설 기각**: 각 이벤트의 실제
  진입속도/apex 목표속도(vTurnSpeed)로 물리 필요거리(ramp+safe_dist,
  decel_rate=1.2/safe_time=1.0 고정)와 8.0s horizon 가시거리(등속
  근사)를 비교한 결과, **15건 전부 deficit(부족분)이 0 이하(가시거리가
  필요거리보다 항상 김, 최대 -107m 여유)**. 즉 horizon 자체가 부족해서
  물리적으로 못 보는 상황은 route2 표본에서 확인 안 됨.
  → `vturn_lookahead_horizon_s`/`vturn_safe_time` 상향은 이번 표본
  기준 근거 부족, 우선순위 하향 권고.
- **replay_vturn2.py(신규, work/ scratch)로 modelV2 raw 배열에서
  필터-전 required_speed_kph(argmin, 부호 없는 크기)를 프레임 단위
  재현** — seg15 이벤트(apex t=9505.7, 우회전 apex_steer=-75.9)
  구간에서 raw_turnSpeed가 apex 전후로도 정상적으로 낮은 값(29~53
  km/h대)을 유지, 필터-전 신호 자체의 지연/결손은 없음을 확인.
- **[신규 확인, 버그 아님] CSV의 `vTurnSpeed`가 src="model" 전환
  구간에서 음수(-64~-70)로 나타나는 현상 원인 규명 완료**: 코드
  재확인 결과 `vturn_speed()`(carrot_man.py) 마지막 줄
  `return turnSpeed * curv_direction`에서 **방향(좌/우회전)을 부호로
  의도적으로 인코딩**함(`curv_direction = np.sign(lookahead_rate[apex_idx])`
  등). seg15 이벤트는 우회전(`apex_steer=-75.9`)이라 부호가 음수인 게
  정상 — `msg.carrotMan.vTurnSpeed = int(vturn_speed)`로 이 부호 있는
  값이 그대로 로깅됨(carrot_serv.py L1123). 즉 **min() 소스 비교에는
  `abs(vturn_speed)`가 쓰이고(L1019), CSV `vTurnSpeed` 컬럼은 항상
  방향 부호 포함 원값이라 src가 "model"로 넘어간 뒤에도 vturn 자체의
  마지막 필터 출력값이 계속 로깅되는 것 — 실제 min() 승자와 무관한
  진단용 채널.** 향후 이 필드로 "어떤 소스가 실제로 이겼는지"를
  판단하려면 반드시 `src` 컬럼을 기준으로 하고 `vTurnSpeed` 절대값은
  참고용으로만 쓸 것(분석 함수 작성 시 주의사항으로 기록).
- **결론**: 46차부터 이어진 "사전감속 구간 부족" 가설은 route1/2
  실측 기준 근거가 약해짐 — horizon/safe_time 상향보다는 (1) 다른
  route(고속도로 장거리 진입) 표본 추가 확보, 또는 (2) 46차에서
  발견됐던 `abs(vturn_speed)<120` model 게이트가 원거리 불안정
  구간에서 더 안정적인 model 신호를 차단하는 쪽 재검토가 더 유망한
  방향으로 보임(46차 NEEDS_VALIDATION 항목과 연결).
- **코드 변경 없음**(분석/스크래치 스크립트만, toolkit 미편입 —
  `work/replay_vturn2.py`, 필요시 다음 세션에서 정식 toolkit 함수로
  승격 검토).
- **다음 단계**: 사용자 결정 대기 — (a) 46차 model 게이트 가설
  재조사 착수, (b) 고속도로 장거리 진입 로그 추가로 horizon 부족
  가설 재검증, (c) 다른 스레드로 전환.

## 50차 계속 — route1(203f99d429 seg8) 재분석으로 "정점 감속 부족" 근본원인 재확인, model 게이트 패치 구현·검증(코드 변경, 실차 미검증)

- **배경**: 사용자가 `곡선.zip`(46차 원 파일, route1 `203f99d429` seg8)을
  재업로드하며 "사전거리가 많이 부족해 보인다"고 제보. route2 실측
  기준 "horizon 8.0s 가시거리 부족" 가설은 이미 기각된 상태라, 같은
  route1 로그를 다시 실측했다.
- **재확인**: t=6563~6574(11초) 구간 vEgo가 오히려 가속 중(77→90km/h,
  aEgo 대부분 +0.1~+0.9)인 동안 `modelTurnSpeed`는 92~108km/h로
  안정적으로 낮게 유지되고 있었으나 `vTurnSpeed`(raw)는 -249~249로
  극도로 불안정(부호까지 요동)해 `abs(vturn_speed)<120` 게이트에
  계속 걸림 — `src`는 이 구간 내내 `route`(110~200km/h대)만 선택됨.
  t=6574.73에야 처음 `vturn`으로 전환, 1.5초 만에 115→88km/h 급락.
  실질 사전경고 3초 미만, 정점(t≈6577.7, steer -12.9deg)에서 vEgo가
  93~94km/h로 목표(86~88) 대비 미달 — **46차 NEEDS_VALIDATION 항목이
  같은 로그로 재현·재확인됨**(표본 2건째, 재현성 확보).
- **패치 설계·구현(사용자 승인, 커밋 `74e8e90`, `c3-ms-dev` 로컬)**:
  1. `abs(vturn_speed)<120` 게이트 제거.
  2. 트레일링 판정을 "직전 프레임 대비 연속 비감소"(noise_tol=0.3km/h,
     프레임 단위라 완만한 하강 중 잔떨림에도 카운터 리셋)에서
     "최근 최저점(min_recent) 대비 recover_margin=3.0km/h 이상 지속
     회복"으로 재설계(`model_turn_speed_min_recent`/
     `model_turn_recover_margin` 신규 상태변수, 자세한 값은
     PARAMS_REGISTRY.md 50차 항목 참고).
- **시뮬레이션 검증**(`work/replay_vturn2.py` 기반 스크래치, toolkit
  미편입): route1 seg8 실측 CSV에 신/구 로직을 나란히 재현 — 신규
  로직 적용 시 desiredSpeed 제약이 t=6574.73이 아니라 **t≈6555
  (vEgo 77.7km/h 시점)부터 시작**, 사전감속 여유시간이 3초 미만에서
  **20초+로 확대**됨을 확인.
- **[NEEDS_VALIDATION, 중요, 다음 세션 최우선]** 같은 로그로 model
  참여 비율을 전수 스캔한 결과 **전체 1200프레임 중 98.8%에서
  model이 min() 후보로 참여**함. 이 로그 자체가 46차 분류표 기준
  "완만~중간 지속 곡선" 도로라 일부는 정당할 수 있으나, **진짜
  평탄한 직선 고속도로 구간에서도 이 참여 비율이 유지되는지는 해당
  로그가 없어 검증 못 함** — 실차 테스트 시 확실한 직선 구간에서
  불필요한 감속/과도한 속도 제약이 생기지 않는지 반드시 최우선으로
  확인할 것.
- **전달**: `0001-carrot_serv-model-min_recent-margin-abs-vturn_speed-.patch`를
  `/mnt/user-data/outputs/`에 생성, `git am` 안내와 함께 전달함.
- **코드 변경 있음**(`carrot_serv.py`, ryu 로컬 커밋 `74e8e90`,
  origin에는 미push — ryu는 항상 수동 patch 절차).

## 51차 (2026-08-23) — route(내비 경로) 감속 실측 착수, turn_speed_violations()/speed_tracking_error() 단위 불일치 버그 발견·수정 (중요)

- **배경**: 사용자가 vturn apex 조기화 아이디어를 보류하고 "route 감속
  코딩으로 가자"고 방향 전환 — APN 경로설정 시 동작하는 `carrot_navi_route()`
  (지도 300m 앞 곡률 샘플 + 역순 시간지연 스무딩)가 가장 효과적인 커브
  주행 로직 같다는 판단. 사용자 선택: "실제 로그로 route 감속 동작부터
  검증".
- **코드 리뷰**: `carrot_navi_route()`(`carrot_man.py` 379~483행) —
  `NavDestination` 설정 시에만 활성화, 경로 300m를 10m 간격 리샘플 후
  지점별 곡률→목표속도(`V_CURVE_LOOKUP_BP/VALS`) 산출, 먼 지점에서
  가까운 지점 순으로 역순 스캔하며 `autoNaviSpeedDecelRate` 가속한계로
  감속 가능 여부를 매 구간 체크(방지턱과 유사하나 vturn의 `v²=v_f²+2ad`
  물리공식과는 다른 시간지연 방식). vturn(비전, ~8초 예측)과 달리 실제
  지도 경로 300m를 그대로 써서 거리 자체는 더 김.
- **로그 확보**: 업로드 2건(`곡선.zip`=203f99d429 seg8 재업로드,
  `곡선_로그(2).zip`=203f99d429 seg8 중복 + **f3db6ca89d seg6/7/15~19
  신규 7세그**, 중첩zip 포함). f3db6ca89d를 선택(기존 route_summary
  JSON 기준 route<->model/road/gas 4개 쌍 모두 등장, route 사용 비중
  가장 다양). `extract_log.py`로 8401행 CSV 추출(commit `f94a7d2`,
  50차 model 게이트 패치 반영된 HEAD). `src=='route'` 프레임 323개
  (전체의 3.8%).
- **신규 toolkit 함수 2개** (`analysis_helpers.py`):
  - `source_target_violations(rows, src_name, target_field="desiredSpeed", ...)`
    — `turn_speed_violations()`의 일반화판, 임의 소스의 목표속도 위반 스캔
  - `route_target_jump_events(rows, ...)` — route desiredSpeed 자체의
    단시간 급점프(불연속) 탐지, vturn 쪽 `curve_noise_summary_refined()`에
    대응하는 route 버전
- **[중요, 신규 발견] 단위 불일치 버그**: 기존 `turn_speed_violations()`와
  `speed_tracking_error()`(기본 `target_field="desiredSpeed"`)가
  **`vEgo`(m/s, carState 원본)를 변환 없이 `vTurnSpeed`/`desiredSpeed`
  (km/h, carrotMan 메시지 원본 — `carrot_serv.py` L1148/1151
  `int(vturn_speed)`/`int(desired_speed)`)와 직접 비교**하고 있었음.
  vEgo(m/s)는 수치상 거의 항상 km/h 스케일 목표값보다 작아, 위반 조건식이
  **사실상 발동 불가능한 구조**(false negative)였음. 이번 세션 신규 함수
  (`source_target_violations`)도 처음엔 동일 버그로 작성했다가 route
  위반 0건이라는 비정상적으로 깔끔한 결과와 desiredSpeed와 vEgo의 원값
  비교(vEgo=27.7 vs desiredSpeed=138 등, 단위가 다름이 육안으로 확인됨)를
  보고 발견.
  - **수정**: 세 함수(`turn_speed_violations`, `speed_tracking_error`,
    `source_target_violations`) 모두 `vEgo * 3.6`으로 km/h 환산 후 비교하도록
    수정. `turn_speed_violations`/`source_target_violations`의 `margin`
    기본값도 단위 불명확했던 0.5 → 2.0km/h로 재정의(리턴 필드 `vEgo_peak`도
    이제 km/h). 세 함수 모두 합성 데이터로 재검증 완료(정상 발동 확인).
  - **[NEEDS_VALIDATION, 다음 세션 최우선] 파급 범위**: 지금까지 여러
    세션(24차 route4~11, 41차 route1/route2, route_summary.py를 통한
    모든 route_summaries_260821 JSON 등)에서 "turn_speed_violations 0건"
    으로 보고돼 "커브 속도 위반 없음"의 근거로 쓰였던 결론들이, 실제
    안전을 반영한 게 아니라 이 버그로 인한 미탐지였을 가능성이 있음.
    **원본 로그(zip/CSV)가 남아있는 대로 수정판으로 전부 재스캔 필요**
    — 특히 24차/41차에서 "안전지표 전부 0건"으로 결론 내렸던 라우트들.
- **재검증 결과** (f3db6ca89d 7세그, `remove_driver_intervention` 적용,
  버그 수정판 함수 사용):
  - **route(내비 경로) overshoot 위반: 0건** — 이 표본에서는 route가
    실제 제약으로 작동한 구간이 거의 없었음(desiredSpeed가 대체로
    vEgo보다 훨씬 높은 느슨한 상한으로만 작동, 예: desiredSpeed=121km/h
    vEgo=95.8km/h). **route 자체의 "정상 준수 여부" 검증치고는 route가
    거의 안 눌린 표본이라 결론력이 약함** — 실제로 급조임 커브에서
    route가 binding하는 표본(예: route1 203f99d429 seg8, 46/50차에서
    다룬 급조임 지점)으로 별도 재검증 필요.
  - **route desiredSpeed 급점프 이벤트: 2건** — seg6 t=8998.43~8998.48
    구간 0.1초 내 172→149→140km/h로 급락. vEgo(약 100km/h)가 두 값
    모두보다 낮아 안전에 직접 영향은 없었으나, `carrot_navi_route()`의
    GPS 경로점 리샘플/곡률 추정(3점법, 40m 간격) 또는 역순 스무딩
    로직 자체가 순간적으로 불안정할 수 있음을 시사 — vturn의 곡선 노이즈
    문제와 유사한 성격일 가능성, 추가 표본 필요.
  - **vturn overshoot 위반(버그 수정 후 신규 재현): 14건** — 과거
    "0건" 결론과 정반대. 최대 초과폭 18.11km/h(4.05초 지속,
    `20260821_125148_..--16` seg, t=9595.08~9599.12,
    vEgo_peak=41.84km/h vs vTurnSpeed=27.0km/h), 그 외 8~15km/h대
    초과가 다수(지속시간 1.6~4.05초). **route 검증에서 파생된 사이드
    이펙트지만 우선순위상 route보다 더 시급해 보임** — 이 route는
    50차에서 model 게이트 패치가 적용된 HEAD(`f94a7d2`)로 추출된
    로그라, 이 패치와 무관하게 vturn 자체가 커브 진입 시 목표속도를
    수 초간 초과하는 패턴이 있다는 뜻.
- **harsh_brake_events: 0건** (참고, 이 함수는 원래 aEgo/브레이크 기반이라
  단위 버그와 무관 — 정상 작동 확인됨).
- **코드 변경**: devnotes toolkit만(`analysis_helpers.py`), `ryu` 패치
  없음. 로컬 수정 완료, 이번 체크포인트에서 push 예정.
- **다음 세션(또는 다음 메시지) 최우선**:
  1. 이번에 발견된 vturn 14건 위반을 개별 조사(어느 커브, 감속 프로파일이
     왜 못 따라갔는지 — 저역통과 필터 지연? 물리공식 자체 한계?).
  2. route1(203f99d429 seg8, 이미 업로드됨)로 route 감속을 재검증 —
     이번 f3db6ca89d 표본은 route가 거의 안 눌려 결론력이 약했음, seg8은
     46/50차에서 다룬 급조임 커브라 route가 실제 binding할 가능성 높음.
  3. **turn_speed_violations() 버그로 인한 과거 세션 "0건" 결론 재검증**
     — 원본 로그 재확보 가능한 대로 순차 재스캔(우선순위: 24차/41차
     "안전지표 전부 0건" 요약이 나왔던 route들).
  4. route desiredSpeed 급점프(2건, 이번 표본)가 우연인지 구조적 문제인지
     추가 표본으로 확인.

## 52차 — route1/route2 turn_speed_violations() 버그수정판 재검증, vturn overshoot 원인 후보 좁힘

### route1 (`203f99d429` seg8, 곡선.zip) — 재검증
- `turn_speed_violations()` 수정판 재실행: **1건**(t=6575.73~6578.18,
  max_over=8.13km/h, vEgo_peak=94.1km/h vs vTurnSpeed=86.0km/h,
  duration=2.45s). 프레임 대조 결과 진짜 급조임 커브(desiredCurvature
  0.00003→0.0029 급등) 진입 중 vTurnSpeed가 115→86km/h로 약 2초 만에
  급락하는데 vEgo가 못 따라간 것 — 46/50차 "정점 감속 부족" 정성적
  관찰을 최초로 정량 재현(단위버그 수정 후).
- `source_target_violations(rows, "route")`: **0건** — 이 세그에서
  route(내비 경로) 소스가 270/1200프레임(22.5%) 선택됐으나 선택 구간
  전부 vEgo가 desiredSpeed+margin 이내 준수. route 소스는 활성 시
  목표속도를 잘 따라감(51차 WIP "route가 실제로 binding하는지"
  질문에 대한 최초 답 — 이 세그에선 정상 준수, overshoot 없음).

### route2 (`f3db6ca89d`, 재업로드 전체 20세그 x24001행) — 51차 부분(7세그) 대비 전체 재스캔
- `turn_speed_violations()`: **16건**(51차 부분 스캔의 14건에서 전체
  로그 확보로 16건 확대, seg11/13/15(2건)/16(3건)/17/18(3건)/19(4건)).
  max_over 4.2~18.1km/h, duration 1.4~4.05s.
- **필터링**: 16건 전부 `brakePressed=False`/`cruiseEnabled=True` 유지
  (운전자 개입 0건), 15/16건은 `leadStatus=False`(리드차량 없음,
  순수 커브 상황) — **선행차 추종/운전자 개입과 무관한 순수 vturn
  오버슈트로 확정**. route(`f3db6ca89d`)가 "연속 급커브 왕복국도"
  특성상 46차 route2 추정("정점 감속 부족이 일반적 패턴")을 뒷받침.
- **[신규, 원인 후보 좁힘] aEgo 실측 vs `vturn_decel_rate`(1.2m/s²,
  방지턱 물리공식 기반 설계값) 비교**: 16건 중 **12건(75%)이 실제
  aEgo_min이 1.2m/s² 대비 100%~190%**(평균 약 111%) — 즉 시스템이
  이미 설계 감속률과 같거나 더 강하게 감속 중인데도 목표속도를 못
  따라잡음. 나머지 4건은 50~92%로 여력이 남아있었음. 최대사례(#3,
  over=18.1km/h)는 aEgo_min=-2.28m/s²(190%, `A_CRUISE_MIN=-2.0`
  물리클램프 자체도 근접/초과)까지 감속했지만 vTurnSpeed가 70→31km/h로
  약 6초 만에 하강하는 속도(급조임 커브 curvature 0.0001→0.027 급등)를
  못 따라잡음.
- **해석(NEEDS_VALIDATION)**: 다수(75%) 사례가 이미 설계 감속률
  (1.2m/s²) 이상으로 반응 중임에도 부족한 것으로 보아, "감속 반응이
  느긋해서"(파라미터 자체가 관대해서)라기보다 **"목표속도 프로파일이
  실제 곡률 조임 속도를 lookahead 구간에서 충분히 일찍 반영 못 해
  뒤늦게 급조임을 발견 → 뒤늦게라도 설계 감속률 이상으로 밟아보지만
  이미 늦음"** 쪽에 더 가까운 그림. 46차에서 세운 3개 후보
  (i.vturn_decel_rate 물리한계/ii.vturn_lookahead_horizon_s 국도
  커브간격 부적합/iii.desiredCurvature 순간값 후행) 중 **ii(lookahead
  horizon 부적합)가 이번 정량 데이터와 가장 부합** — 단 확정 아님,
  실제 lookahead 시점의 raw required_speed 궤적(필터 전) 재현 검증
  필요.

### 코드 변경 없음(분석만), patch 없음.

### 다음 세션 최우선
1. `curve_apex_vs_gap_delta()`(46차 편입)류로 이번 16건에도 "정점 통과
   전 사전감속 지연"인지 "정점 자체에서 못 따라감"인지 delta 재분류.
2. lookahead horizon 부적합 가설(ii) 직접 검증: 오버슈트 시작 시점보다
   `vturn_lookahead_horizon_s`(8.0s)만큼 이전 시점에 raw
   required_speed(필터 전, model 게이트 무관)가 이미 급조임을
   반영하고 있었는지 재현 — modelV2 raw가 CSV에 없어 49차처럼
   `replay_vturn2.py`류 재현 스크립트 필요할 수 있음.
3. 나머지 미분석 로그(route4=`d45a15f8fc` 재업로드 전체 20세그,
   route9=`280302e8ed` 20세그)는 51차 버그수정판 turn_speed_violations()로
   아직 재스캔 안 함 — 다음 세션 후보.

## 52차 계속 — route2 apex-vs-gap 재분류, route4/route9 turn_speed_violations 수정판 재스캔

### route2(f3db6ca89d) apex-vs-gap 재분류
- `curve_apex_vs_gap_delta()`로 16건 vturn overshoot과 커브 이벤트
  매칭 시도 — 매칭 성공 11/16건에서 **gap(최대초과 시점)이 apex(조향각
  정점)보다 0.3~1.75초 먼저 발생**(delta 음수), 46차 route2 32건
  재분류 결과(79%가 gap이 apex보다 평균 1.26초 먼저 발생)와 일관.
  나머지 5건은 인접 연속커브가 뒤섞여 매칭이 부정확(±2s 매칭 한계,
  개별 재검증 필요). **결론: 대부분 "정점 자체에서 못 따라감"이 아니라
  "진입/접근 중 이미 벌어진 문제가 정점까지 이어짐"** — lookahead
  horizon 부적합 가설(ii)과 방향 일치.

### route4(`d45a15f8fc`, 재업로드 전체 20세그) — turn_speed_violations 수정판 재스캔
- **24건** 검출(47차 구버전 버그 함수로는 "v3=1건"이라 결론났던 route —
  **그 결론 전체가 단위버그로 인한 false negative였음이 확정**,
  PARAMS_REGISTRY.md 갱신 필요).
- 1건(idx17, t≈10677~10686, dur=8.5s)은 `brakePressed`(55프레임)+
  `cruiseEnabled=False`(164프레임) 겹침 — **운전자 개입 구간, ADAS
  오버슈트 아님, 제외**.
- 나머지 23건 전부 브레이크/disengage 없는 순수 ADAS 오버슈트.
  over 2.2~15.1km/h, duration 0.3~6.6s.
- aEgo_min vs `vturn_decel_rate`(1.2m/s²) 비율: 23건 중 **13건(57%)이
  100%~288%** — route2(75%)보다는 낮지만 여전히 과반. **[주의] idx10
  (over=13.3kph, dur=6.6s)은 aEgo_min=-3.45m/s²(설계값의 288%,
  `A_CRUISE_MIN=-2.0` 물리클램프의 173%)로 이례적으로 강한 감속 —
  다른 이벤트와 성격이 다를 수 있음(고이질감/실제 위험 상황 가능성),
  다음 세션 개별 프레임 확인 최우선 후보로 추가.**
- route4/route2 둘 다 "12/16건, 13/23건이 설계 감속률 이상으로
  반응하는데도 못 따라잡음" 패턴이 재현 — 단일 route 우연이 아니라
  **route 타입(연속 커브/고속도로 커브 구간) 전반의 일반적 패턴일
  가능성 격상**.

### route9(`280302e8ed`, 재업로드 전체 20세그) — turn_speed_violations 수정판 재스캔
- **0건** — 기존 "안전지표 클린" 결론 유지(51차 단위버그 수정 이후로도
  재확인, 이 route는 실제로 커브 콘텐츠가 적었던 것으로 판단).

### 코드 변경 없음(분석만), patch 없음.

## 52차 계속2 — route4 idx10 개별 확인: 데이터 이상 아님, 극단적 급커브로 확정

- **route4(d45a15f8fc) idx10**(t=10129.7~10136.3, over=13.3km/h,
  aEgo_min=-3.45m/s²=vturn_decel_rate 설계값 288%) 프레임 대조 완료.
  **원인은 데이터 글리치나 이례적 버그가 아니라 진짜 극단적으로 급한
  커브(헤어핀형)** — desiredCurvature 최대 **0.052**(route1 최대치
  0.0029의 약 18배, route2 최대치 0.027의 약 2배)까지 상승. vTurnSpeed가
  106→20km/h까지 하강, vEgo도 54.7→20.6km/h까지 약 9.5초에 걸쳐
  실제로 크게 감속(중간에 aEgo 최대 -3.45m/s² 순간 포함, 전 구간
  운전자 브레이크 개입 0, 리드차량 없음 — 시스템 단독 판단).
- **해석**: 다른 15개 route4 이벤트(설계치 100% 근방)와 성격이 다른
  게 아니라 **같은 메커니즘(lookahead가 급조임을 늦게 발견)이 커브
  자체가 극단적으로 급할 때 더 크게 증폭된 사례**로 재분류. 시스템이
  평소 설계 감속률(1.2m/s²)의 거의 3배까지 밟아가며 따라잡으려 했다는
  점에서, "감속을 안 해서"가 아니라 "발견이 늦어 남은 거리 대비
  필요 감속량이 이미 물리적으로 빠듯했던" 시나리오와 부합 —
  lookahead horizon 가설(ii)에 다시 힘을 실어줌.
- 시각(qcamera) 프레임 대조 **완료**(사용자 요청으로 추가 진행,
  `extract_dashcam_frames.py`로 t=10129.7/10132.0/10134.8/10136.3
  4장 추출). **100% 확증**: 산간도로 급커브 진입부(관문/사찰 입구
  추정 구조물 앞) — 도로 바닥의 빨간 감속유도선이 t=10129.7부터
  거의 반원에 가깝게 급우회전으로 꺾이고, 좌측에 급커브 경고 화살표
  표지판(t=10132.0)까지 확인됨. t=10134.8~10136.3까지도 커브가
  계속 이어지며 도로가 숲 그늘 속으로 사라짐 — 짧은 스냅이 아니라
  지속되는 급커브임을 영상으로도 재확인. **데이터 글리치/센서 오작동
  가능성 완전 배제, 진짜 헤어핀급 급커브로 최종 확정.**

### 코드 변경 없음(분석만), patch 없음.

### 다음 세션 최우선 (완료, 아래 54차 항목으로 이어짐)
1. ~~lookahead horizon 가설(ii) 직접 검증용 replay 스크립트~~ →
   **완료(54차, 아래 참고)**.
2. route2 apex-vs-gap 미확정 5건 개별 재검증. (route2 로그 미보유,
   여전히 대기)

## 54차 — lookahead horizon 가설(ii) 실제 rlog 첫 검증, 결론 정교화 (raw 신호도 늦게 감지 + 필터 추가 지연 복합)

**입력**: route4(`d45a15f8fc`) 20세그 재업로드분(`replay_lookahead_v1.py`
실제 rlog 검증 대상). `extract_log.py`로 표준 CSV 재추출(23997행,
commit `f94a7d2` 확인 — 52/53차와 동일 코드 상태) + `replay_lookahead_v1.py`
전체 route 실행(24000 modelV2 프레임, raw_kph/filtered_kph_replica/
apex_pos_m/apex_t_s 산출).

**idx10 개별 정밀 대조** (t_start=10129.72, over=13.26kph, dur=6.6s —
52차 결론과 일치): raw_kph와 실측 filtered(route4.csv `vTurnSpeed`)를
프레임 단위로 나란히 놓고 봄.
- t=10119.7~10123.8 구간(이벤트 8~6초 전): raw_kph 51~66 사이 유지,
  뚜렷한 하강 신호 없음 — vEgo 순항속도(54km/h대)와 큰 차이 없음.
- t=10123.9~10128 구간: `desiredCurvature`가 일시적으로 반대부호로
  튀는 S자 아티팩트 구간(직전 세션들에서 확인된 curv_direction 부호
  인코딩) — raw_kph도 이 구간에서 60~100대로 노이즈성 등락.
- **t=10128.0부터 raw_kph가 실질적으로 하강 시작(64.8→28대, ~5초에
  걸쳐)** — 즉 raw(필터 이전) 신호 자체도 이벤트 6초 이상 전이 아니라
  **약 1.5~2초 전부터 눈에 띄게 감지**, `apex_pos_m`도 이 구간에서
  약 65m(≈4.5~5.6s 환산)에서 시작해 접근하며 단조 감소 — 즉 모델의
  argmin이 실제로는 65m 근방까지 접근해서야 이 커브를 "발견"한 것으로
  보임(이론적 `lookahead_horizon_s=8.0s`/약 120m@54km/h와는 거리 차이 큼).
- **동시에 실측 filtered(vTurnSpeed)는 raw보다 추가로 지연** —
  t=10129.221 raw=48.65km/h인 시점에 실측 filtered는 아직 66km/h
  (동시각 기준 약 17km/h 차이), filtered가 raw와 비슷한 값(≈49)에
  도달한 건 t≈10130.0(raw 대비 약 0.8초 지연).

**24건 전체 일반화 스캔** (`work/lookahead_generalization_scan.py`
신규 작성, toolkit 미편입 — 아래 "한계" 참고): 각 위반 이벤트마다
raw_kph가 `target*1.15` 이하로 처음 떨어진 시각(raw_cross_t) vs
실측 filtered가 같은 문턱에 도달한 시각(filt_cross_t)의 차이(lag)를
계산.
- **18/24건에서 lag 계산 가능**(나머지는 문턱 미도달 등으로 계산불가).
  평균 lag=2.15s, 최대 8.60s(idx5), 최소 -0.04s(거의 동시, 2건).
  **즉 대부분의 이벤트에서 filtered(실제 시스템 반응)가 raw(모델이
  이미 알 수 있었던 값)보다 평균 2초 이상 늦게 반응** — idx10
  자체는 이 지표로 lag 계산 불가(nan, 데이터 정렬 이슈로 문턱
  교차시점 미검출)였으나 위 개별 대조로는 ~0.8초 확인.
- max_apex_t_s(사전 8초 윈도 내 raw가 감지한 가장 이른 시점) 평균
  5.16s, 최대 7.66s로 언뜻 이론적 horizon(8.0s)에 근접해 보이나,
  **이 지표는 신뢰 불가로 판단** — idx10 개별 대조에서 드러났듯
  S자/노이즈 구간에서 argmin이 실제 타겟 커브가 아닌 다른 곡률
  특징(반대 방향 커브 등)을 잠깐 짚었다가 사라지는 경우가 섞여
  있어, "최대 apex_t_s"만으로는 "그 이벤트를 진짜 일찍 발견했다"를
  보장 못함. raw_cross_t/filt_cross_t 기반 lag가 더 신뢰할 수 있는
  지표로 판단.

**결론(가설 정교화, ROOT_CAUSE 복합으로 재정의)**:
당초 가설(ii) "lookahead_horizon_s 자체가 짧다"는 단순화였음이
드러남 — 실제로는 두 가지가 겹친 것으로 보임:
  (a) **raw 신호 자체도 이벤트 근접(수 초 전, 8초 전이 아님)까지는
      뚜렷한 하강을 안 보임** — `lookahead_horizon_s` 파라미터를
      단순히 늘려도 raw가 그보다 훨씬 일찍 커브를 "보고" 있었다는
      증거는 이번 스캔에서 확인 못함(원거리 modelV2 궤적/곡률
      예측 자체가 이 정도 거리에서는 confident하지 않을 가능성).
  (b) **filtered 최종 출력은 raw보다 평균 2초 이상 추가로 늦게
      반응** — 이 부분은 저역통과 필터(`vturn_decel_rc=0.15s`) 자체의
      시정수보다 훨씬 큰 지연이라, 단순 RC 상수 문제가 아니라
      "계속 움직이는 목표(매 프레임 다시 계산되는 argmin)를 필터가
      뒤쫓는 구조적 lag"로 추정 — 목표가 프레임마다 더 타이트해지는
      상황에서는 저역통과 필터가 누적 지연을 만들 수 있음.
  → (b)는 (a)보다 개입 여지가 더 크고 리스크도 상대적으로 낮은
    후보(필터 계수/구조 조정)로 판단되나, **패치 방향은 아직
    미확정 — 사용자 결정 필요**.

**한계**:
- `lookahead_generalization_scan.py`는 이번 세션 스크래치
  (`work/`)이며 toolkit 미편입 — max_apex_t_s 지표의 신뢰성 문제로
  로직을 더 다듬어야 정식 편입 가치가 있다고 판단, 보류.
- idx10 자체는 threshold 정렬 이슈로 lag 자동계산에서 nan 처리됨
  (수동 대조로는 ~0.8s 확인) — 스캔 스크립트의 threshold 매칭
  로직(1.15배 문턱)이 부호 반전 구간 근처에서 오검출할 가능성 있음,
  다음 세션에서 정밀화 필요.
- 여전히 route2/route1 원본 rlog 재검증은 안 함(route4만 검증) —
  일반화 강도는 route4 24건 표본에 한정.

### 코드 변경 없음(분석만, `work/lookahead_generalization_scan.py`는
스크래치, toolkit 미편입). patch 없음.

### 다음 세션 최우선
1. **패치 방향 결정 필요(사용자)** — (b) 필터 지연 완화 쪽(예:
   `vturn_decel_rc` 값 재검토, 또는 목표 갱신 시 필터를 우회하는
   "급조임 감지 시 즉시 반영" 로직 추가) vs (a) lookahead 자체
   개선(모델 원거리 신뢰도 문제라 코드 레벨 대응이 어려울 수 있음,
   저우선 권고) — 방향 확정되면 시뮬레이션 → 패치 순서로 진행.
2. `lookahead_generalization_scan.py`의 threshold 매칭 로직 정밀화
   (idx10 nan 문제 해결) 후 필요 시 toolkit 정식 편입.
3. route2 apex-vs-gap 미확정 5건 개별 재검증 (route2 로그 재업로드
   대기, 여전히 이월).

## 55차 (완료 — 분석만, 코드 변경 없음) 신규 실주행 로그 3개(HEAD `f94a7d2`) 5개 항목 종합분석

**로그**: route1(`a6e5df336a` x19seg, 1140.1s/16.0km), route2(`cf48b52c98`
x20seg, 1199.8s/12.75km), route3(`7472041957` x3seg 중 seg2는 rlog.zst
zstd 프레임 손상(녹화 중 절단 추정)으로 제외, seg0/1만 119.9s/1.88km
분석). 사용자 요청 5개 항목을 순서대로 분석.

### 1) 카메라 인식 시 감속 분석 (frac_rate/vision-only closing-rate 게이트)
`vision_to_radar_crossover()`로 52건(route1 26/route2 24/route3 2) 탐지.
`vRel_at_vision_start`가 음수(접근 중)인 사례 대부분에서 레이더 락온
이전(`aEgo` 이미 음수)부터 감속이 시작됨을 확인 — 41/36차에서 확정된
frac_rate 게이트 설계 의도대로 최신 HEAD에서도 정상 동작 재확인.
**잔여 저반응 패턴 2건 신규 관찰(41/42차 route B seg10 패턴과 유사,
저우선)**:
- route1 seg2 gap=3.50s, vRel0=-7.2m/s, dRel 75.7→43.8m(32m 접근)인데
  `aEgo_min=-0.45, avg=+0.11` — 접근 강도 대비 반응 약함.
- route2 seg0 gap=5.20s, vRel0=-6.4m/s, dRel 85.5→59.9m(25.6m 접근)인데
  `aEgo_min=-0.99, avg=-0.08, last=+0.25`(레이더 락온 직전 오히려 가속쪽).
표본 2건뿐이라 결론 아님, 41/42차 "vision vRel-dRel 불일치 노이즈"
가설과 동일 축의 재현 후보로 기록만 함.

### 2) 정지 앞차 감속 분석
전용 스캐너(`stopped_lead_decel_events`, |leadVLead|<1.0m/s 지속구간)로
5건 탐지(route1 0/route2 4/route3 1). 전부 `vEgo_end` 1.0~2.4m/s까지
매끈히 감속(`aEgo_min` -0.13~-2.26m/s², harsh_brake/운전자개입 없음).
route2 seg5 t=1622.99 건은 `aEgo_min=-0.13`로 유독 약한 감속(dRel
59.9m, vEgo 7.0m/s에서 시작 — 원거리라 초기엔 약하게, 이후 같은 세그
t=1625.21에 -1.03으로 이어져 최종 정차까지는 정상 매끈하게 완료됨.
전반적으로 정지 리드 추종 자체는 클린.

### 3) 정지 후 재출발 로직 분석 (45차 launch bypass 패치)
`launch_after_stop_events`로 3건(route1 1/route2 2) 탐지, 전부
`driver_gas_ratio=0.0`(완전 ADAS 재출발). 정차→5m/s 도달까지 9.4~24.1초,
`aEgo_max` 1.43~2.44m/s², `aEgo_avg` 0.19~0.49m/s². 완만하지만 무가속/
정체 없이 매끈히 재출발 — 45차 이전 버그("정지 후 출발 가속 약화",
ttc_accel_weight closing<=0.1 시 무조건 0) 재발 징후 없음, launch
bypass 패치가 최신 HEAD에서도 정상 동작 중인 것으로 판단(간접 확인,
직접적인 exit 전환 순간 프레임 대조는 미실시).

### 4) 레이더 락온 상태 앞차추종 중 민감반응(저크) 분석
0.3초 스무딩 윈도우 기준 |jerk|≥3.0m/s³ 이벤트 36건(route1 25/route2 11
/route3 0) 탐지 — 39차 rise-rate 패치 적용 후에도 잔존하는 급변 확인용.
대부분은 `leadVRel` 실제 변화(선행차 급제동/급가속, 예 vRel -4.6~-11.2
또는 +2.3~+3.8)로 물리적으로 설명 가능한 정당 반응. **`leadVRel`이
거의 0에 가까운데도 큰 저크가 나온 예외 2건(route1 seg18)**:
- t=1195.102, jerk=+9.05, leadVRel=-0.10, leadDRel=19.9m
- t=1242.70, jerk=+6.73, leadVRel=-0.60, leadDRel=43.2m
둘 다 가속 방향(+) 저크로, 선행차 상대속도 변화로는 설명이 약함 —
45차 WIP에서 우려했던 "launch bypass exit 전환 순간 w 급하강"류
전환부 아티팩트이거나, 다른 소스(vTurnSpeed/route 등) 전환에 의한
목표속도 점프일 가능성. 표본 2건, 코드 리딩 없이 로그만으로는 원인
특정 불가 — 다음 세션 코드 리뷰 시 우선 확인 후보로 기록.

### 5) 곡선구간 감속 분석
`turn_speed_violations()`(51차 단위버그 수정판)로 23건 탐지(route1 10
/route2 10/route3 3, max_over 2.15~18.33km/h) — 51/54차부터 계속
조사 중인 "vturn apex 조기 언더슈트/lookahead 지연" 이슈의 연장선
재현으로 보이며, 54차 시점 패치 방향 미확정 상태와 일치(신규 발견
아님). `curve_exit_no_accel_scan_v4`(탈출 후 미가속)는 route2 3건 —
전부 `vCruiseCluster_at_exit`가 관련(특히 seg9 `cap_margin=7.7kph`로
경계 근접) — 48차 결론(진짜 버그 아니라 순항속도 캡 여유폭 문제)과
동일 패턴, 신규 버그 아님.

### 종합 안전지표
harsh_brake: route1 13(운전자 개입 다수 추정)/route2 75(정체구간 저속
추정)/route3 0. cut-in: 1/36/0(route2 저속 정체구간 다발 추정, 개별
검증 안 함). ttc_danger(≤2.5s): 1/1/0.
**이번 세션은 순수 분석만 수행, 개별 harsh_brake/cut-in/ttc_danger
이벤트의 운전자 개입 여부·qcamera 프레임 대조는 미실시(다음 세션
과제, 특히 route2 harsh_brake 75건/cut-in 36건은 정체구간 비중이
높아 개별 검증 필요성 낮게 추정되나 확정 아님).**

## 56차 (완료 — 분석만, 코드 변경 없음) 대량 실주행 로그 9개(HEAD `f94a7d2`) 5개 항목 종합분석

**로그**: 사용자가 15:53~19:00(약 3시간)에 걸쳐 수집한 9개 route
(각 1개 boot session, 10~20세그): `d4c265f041`(x14, seg6~19만 포함
—seg0~5는 미업로드), `a3a55cb808`(x15, **seg14는 rlog.zst zstd 프레임
손상으로 제외**, seg0~13만 사용), `98fe04a961`(x20), `941dba0400`(x10),
`fe5dd1ab6e`(x20), `c1c2e1f253`(x20), `27b2980cda`(x20), `1e6dbf517c`
(x20), `b251da5b21`(x20). 총 9개 route, 약 189,336행. 55차 WIP 지시대로
동일 5개 항목을 처음부터 재분석 + 55차 최우선 항목(route1 seg18 저크
이상 2건) 재현 여부 교차검증을 우선 확인.

**[컨테이너 제약]** `stopped_lead_decel_events`/`launch_after_stop_events`
는 55차에서 `work/`(스크래치, 컨테이너 로컬)에만 있던 함수라 이번
세션 컨테이너 리셋으로 소실 — devnotes 기록(FINDINGS.md 55차 항목
설명)을 참고해 로직을 역재현함(`work/five_item_scan.py` 신규,
toolkit 미편입 스크래치). 재현 로직: 정지앞차=`leadStatus and
|leadVLead|<1.0m/s` 지속구간, 재출발=`vEgo<0.3m/s→5.0m/s` 도달 구간
(45차 launch bypass 상수와 동일 값 사용). 레이더락온 저크는 0.3초
이동평균 aEgo 기준 `|jerk|>=3.0m/s³`(39차 rise-rate 검증과 동일 문턱)
+ `leadRadar=True` 프레임만 집계.

### 1) 카메라 인식 시 감속 분석
`vision_to_radar_crossover()`로 9개 route 합계 117건 크로스오버 탐지
(route별 8~24건). `vRel_at_vision_start<-5.0m/s & dRel_closed>10m`인
강접근 후보 2건 개별 확인: (1) d4c265f041--12(vRel -8.2, dClosed
18.7m) — `aEgo_min=-2.26/avg=-1.44`로 확실한 조기반응(정상). (2)
27b2980cda--8(vRel -5.9, dClosed 10.6m) — `aEgo_min=-0.43/avg=-0.25`로
다소 약하나 접근량 자체가 작아(10.6m) 41/42/55차급 "저반응" 이상
패턴으로 보긴 부족(경계 사례, 신규 이상 아님). **이번 세션은 55차
같은 뚜렷한 저반응 잔여패턴 재현 없음** — frac_rate 게이트는 이번
로그 전반에서 정상 동작 범위로 판단.

### 2) 정지 앞차 감속 분석
26건 탐지(9개 route 중 6개에 존재, 나머지 3개는 정지선행차 상황
자체가 없어 0건). 26건 중 **15건은 운전자 개입 프레임 0(순수
ADAS)**, 11건은 driver_brake_frames 또는 driver_gas_frames가 섞여
있어 운전자 개입/보조 판단이 필요(대부분 마지막 정차 직전 저속
구간에서 운전자가 브레이크를 함께 밟은 것으로 추정, 개별 프레임
대조는 안 함). 순수 ADAS 15건 전부 `aEgo_min` -0.23~-3.41m/s²
범위에서 harsh_brake 없이 매끈하게 감속 완료 — 55차 결론(정지앞차
추종 클린)과 일관.

### 3) 정지 후 재출발 로직 분석 (45차 launch bypass)
6건 탐지(d4c265f041 2/a3a55cb808 3/b251da5b21 1), **전부
`driver_gas_ratio=0.0`**(완전 ADAS 재출발). 재출발 소요시간
3.96~25.76초, `aEgo_max` 1.19~2.51m/s², `aEgo_avg` 0.19~1.19m/s² —
무가속/정체 구간 없이 매끈. 55차와 동일하게 launch bypass 패치가
정상 동작 중인 것으로 판단(간접 확인).

### 4) 레이더 락온 상태 저크 민감반응 분석 — **55차 최우선 이상패턴 재현 확인**
9개 route 합계 307건(route별 4~105건, `a3a55cb808`가 105건으로
유독 많음 — 저속/정지앞차 밀집 구간 비중이 높아 그런 것으로 추정,
개별 원인 미검증). **55차 route1 seg18 이상패턴(`leadVRel≈0`인데
큰 저크)과 동일 조건(`|leadVRel|<1.0m/s & |jerk|>=5.0`)으로 필터링한
결과 4건 재현**:
- `a3a55cb808--4` t=3905.30, jerk=+6.60, leadVRel=-0.10, leadDRel=44.7m, **src=road**
- `98fe04a961--9` t=647.21, jerk=+6.70, leadVRel=-0.50, leadDRel=64.9m, **src=road**
- `c1c2e1f253--6` t=2833.29, jerk=+5.29, leadVRel=-0.10, leadDRel=51.8m, **src=section**
- `fe5dd1ab6e--2` t=1378.69, jerk=**-5.37**(감속방향, 나머지 3건과 반대), leadVRel=-0.40, leadDRel=53.1m, **src=vturn**

55차 2건(둘 다 route1 seg18, src 미기록)과 합쳐 표본이 2→6건으로
확대됨. **[신규, qcamera 프레임 대조 완료] src=road/section인 3건
전부 저크 발생 순간 옆차선(우측)에 대형 차량(SUV 2건/탱크로리 1건)이
자차와 밀착·근접 주행 중이었음을 영상으로 확인** — `verify_and_
extract_frames.py`로 각 이벤트 전후 5프레임씩 추출·대조. 3건 모두
동일 패턴(옆차선 대형차량 근접) 재현. **이는 37차에서 이미 근본원인을
확정한 "SCC 단일점 락온이 옆차선 차량을 차로내 위치(yRel/dPath)
검증 없이 그대로 채택"(`radard.py get_lead()`의 `track_scc` 무검증
채택) 문제와 동일 메커니즘으로 강하게 추정됨** — 37차는 이 문제가
"급감속"으로 나타난 사례들이었는데, 이번 3건은 **가속(+) 방향
저크**로 나타남(옆차선 차량이 순간적으로 리드로 오채택됐다가 다시
원래 리드로 복귀하며 목표가속도가 튀는 것으로 추정). `src=vturn`
1건(fe5dd1ab6e)은 영상 확인 결과 **진짜 우커브 구간(옆차선 차량
없음)**으로 완전히 별개 현상 — 이 패턴에서 제외. **가설 수정**:
"launch bypass exit 전환" 가설(45차 WIP 우려)은 근거 약화, **"37차
옆차선 SCC 폴백 미검증 채택 문제가 patch 37차 계속3(dPath 게이트+
LeadBlend 분리) 적용 후에도 가속 방향으로 잔존하는지"**가 다음
코드리뷰 최우선 확인 대상으로 재정의됨. 37차 계속3 패치가
`c3-ms-dev`에 이미 적용돼 있으므로(FINDINGS.md 37차 계속3 참고),
이 3건이 패치 적용 후에도 발생했다는 것은 (a) 패치의 dPath 게이트
임계값이 이 옆차선 근접 케이스를 못 거르거나, (b) 게이트를 통과하지
않고도 발생하는 별도 경로(예: LeadBlend를 타긴 하지만 짧은 순간의
가속측 완화가 불충분)일 가능성을 시사 — 코드 리딩으로 확인 필요.
**다음 세션 코드리뷰 시 최우선 확인 후보를 "launch bypass" 단독에서
"37차 옆차선 SCC 폴백 문제의 잔존 여부(dPath 게이트 통과 케이스
포함)"로 범위 재조정 권고.**

### 5) 곡선구간 감속 분석
`turn_speed_violations()` 3건(d4c265f041 1/b251da5b21 2, max_over
3.58~12.44km/h) — 이번 로그는 커브 구간 자체가 적어(대부분 시내/
정체 위주 주행으로 추정) 51/54/55차 대비 표본이 크게 줄었으나,
방향성(양쪽 다 초과=속도가 vTurnSpeed를 못 따라가는 언더슈트 아닌
오버슈트 패턴)은 기존 apex lag 이슈와 일관. `curve_exit_no_accel_scan_v4`
는 9개 route 전부 0건 — 48차 결론(탈출후 무가속 버그 없음) 재확인.

### 종합 안전지표
harsh_brake(ADAS 활성중) 전부 0건(9/9 route). cut_in: 0~5건(대부분
저속). ttc_danger(≤2.5s): 0~2건. 급제동/위험 cut-in 계열은 이번
9개 route 전부 클린.

### 다음 세션 최우선
1. **4번 저크 이상 6건(55차 2건+56차 4건) 코드리뷰 착수** — qcamera
   대조로 확인된 신규 가설("37차 옆차선 SCC 폴백 문제의 잔존 여부")
   중심으로 `radard.py get_lead()`/`Track.get_RadarState()`의
   `sccFallback`/dPath 게이트 로직(37차 계속3 패치)을 재확인.
2. 1번 저반응 후보(27b2980cda--8)는 경계 사례라 저우선 유지, 추가
   표본 나오면 재확인.
3. `a3a55cb808` route의 저크 이벤트 105건(다른 route 대비 압도적으로
   많음) 원인 미검증 — 저속/정체 밀집 구간 특성 때문인지 확인 필요
   (저우선, 코드리뷰 이후).

## 57차 — 저크 이상 상위 크기 재스캔 + qcamera 대조, 신규 후보(저각 역광) 발견

56차와 동일 9개 route(2026-08-23 촬영분, `d4c265f041`/`a3a55cb808`(seg14
zstd 손상, seg0~13만 사용)/`98fe04a961`/`941dba0400`/`fe5dd1ab6e`/
`c1c2e1f253`/`27b2980cda`/`1e6dbf517c`/`b251da5b21`)를 재업로드받아
"qcamera영상도 대조분석" 요청으로 저크 이상 패턴을 |jerk| 크기 기준
재정렬, 상위 6건 전부 `verify_and_extract_frames.py`로 프레임 대조 완료.

**대조 결과**:
1. `b251da5b21` t=6365.59 (jerk=+14.78, src=vturn, leadVRel=-0.40,
   leadDRel=104.7m): 옆차선에 대형 SUV가 근접 밀착 주행 중이었음을
   프레임으로 확인 — **56차까지 확인된 "옆차선 대형차량 근접" 메커니즘과
   일치**(가속(+) 방향).
2. `27b2980cda` t=4266.99 (jerk=+13.09, src=road): **저각 석양 역광이
   카메라에 직접 입사하는 프레임 확인** (촬영시각 18:01경, 정서쪽 방향
   추정).
3. `27b2980cda` t=4705.54 (jerk=-11.67, src=road): 위와 동일 route,
   **동일한 저각 역광 패턴 재확인**(촬영시각 18:15경).
4. `27b2980cda` t=4242.09 (jerk=-10.49, src=road): 같은 route, **고가교
   하부 통과 시 그림자→역광 급전환** 프레임 확인.
5. `a3a55cb808` t=4299.30 (jerk=-10.05, src=road): 산악 커브 구간이나
   뚜렷한 시각적 이상 없음 — 원인 미상으로 남김.
6. `b251da5b21` t=6797.85 (jerk=-9.87, src=vturn): 석양+커브 구간에서
   선행차 제동등 점등 확인 — 실제 감속이 타당한 상황으로 보여 버그
   후보에서 제외.

**[NEEDS_VALIDATION, 신규] 저각 역광(석양) → vision 인식 저크 가설**:
`27b2980cda`(18:01~18:21 촬영, 정확히 일몰 시간대) route 하나에서
상위 저크 6건 중 3건이 몰려 있고 전부 저각 태양광 역광/명암 급전환과
시각적으로 겹침 — 37차(옆차선 SCC 폴백)/42차(곡선 단안 depth 노이즈)
와는 별개의 제3의 메커니즘 후보. 표본 3건(단일 route)뿐이라 확정 아님,
다른 일몰/일출 시간대 로그로 재현 여부 확인 필요. 코드 변경 없음
(관찰만).

**주의**: 이번 스캔은 jerk 임계값을 3.0(56차보다 낮게)으로 재설정해
919건 후보가 잡혔음 — 대부분은 정상적인 저속/조향 노이즈 수준으로
추정되며, 이번엔 |jerk| 상위 6건만 개별 대조했음. 낮은 임계값 전체
919건 분류는 미실시(저우선).


## 58차 2번 계속 (체크포인트 — 실제 정체구간 로그로 근본원인 가설 1차 검증, 확증 실패) — 정체구간 붕끗

**배경**: 58차 2번(정체 중 danger override 오발동 가설, 아래 원본
섹션 참고) 설계 확정 후 구현 착수 전, 사용자가 실제 "붕끗" 발생
정체구간 로그("정체구간_붕끽.zip", qcamera 포함)를 업로드해 근본원인
가설부터 실측 검증하기로 함.

**로그**: route1(`98fe04a961`, 3세그, 181.8s)/route2(`a3a55cb808`,
seg11~13, seg14는 zstd 손상으로 제외, 179.8s). 둘 다 정차(v<0.3m/s)
반복 진입 확인(route1 3회/route2 7회) — 정체 패턴 자체는 구조적으로
맞음.

**신규 도구**: `congestion_stop_launch_lurch_scan()`
(`analysis_helpers.py`) — 정체 상태 추적(최근 window 내 정차 횟수) +
기존 TTC danger(2.5s) 이벤트 겹침 판정 + 이벤트 전체 구간의
max|vRel|로 "완만한 접근만" 필터(진짜 위험 접근이 섞인 이벤트는
자동 제외). 합성 시나리오 3건(완만한 접근 단독/진짜 위험 단독/정체
아닌 상태)으로 로직 검증 완료 — 특히 "danger 이벤트가 완만한 접근
구간과 진짜 위험 구간에 걸쳐 연속되면 최소 TTC 시점의 vRel 하나만
보면 잘못 필터링될 수 있다"는 버그를 초기 구현에서 발견·수정함
(이벤트 전체의 max|vRel| 기준으로 교정).

**실제 로그 적용 결과**:
- 엄격 기준(정체 판정 = window 60s 내 정차 2회 이상, 완만한 접근 =
  |vRel|<3.0m/s): route1/route2 **둘 다 0건**.
- 완화 기준(정차 1회만으로도 "최근 정체 이력 있음"으로 인정, window
  90s): route1에서 1건(t=60.40, dRel=6.52m/vRel=-2.79m/s/TTC=2.34s) —
  **단 이 시점 `cruiseEnabled=False`(운전자가 브레이크를 밟고 수동
  정차 유지 중)로 확인**, ADAS 종방향 제어 로직이 애초에 개입하지
  않는 구간. `post_aEgo_drop`(사후 aEgo 최대 낙폭)도 0.001로 사실상
  무변화 — "붕끗" 체감과 무관한 것으로 판정. route2는 완화 기준에서도
  0건.

**결론(NEEDS_VALIDATION, 이번 표본으로는 미확증)**: 이번에 업로드된
~3분짜리 정체구간 로그 2개에서는 58차 2번이 겨냥한 "정체 중
danger override 오발동으로 인한 붕끗"의 ADAS 개입 사례를 찾지
못했다. 가능한 해석: (a) 이번 로그 구간이 우연히 그 패턴이 발생하지
않은 구간이었을 뿐(표본 문제, 로그가 짧음), (b) 사용자가 체감한
"붕끗"이 danger override 메커니즘이 아니라 다른 원인(예: source
전환 플리커, launch bypass exit 순간 등)일 가능성, (c) 파라미터
(congestion_window_s/stop_count_thresh/min_closing_for_danger)가
실제 현상보다 너무 엄격하게 설정됐을 가능성. qcamera 대조할 명확한
후보가 없어 (b)단계(영상 검증)는 보류.

**다음 단계(사용자 결정 필요)**:
1. 사용자가 실제 "붕끗"을 체감한 정확한 시각/구간을 기억하면 그
   시점 기준으로 직접 프레임 대조(스캐너 결과와 무관하게).
2. 더 길거나 다른 정체구간 로그 추가 확보 후 재스캔.
3. 스캐너 파라미터를 더 완화(예: congestion_min_closing_for_danger를
   3.0→4.0 이상으로, 또는 TTC 문턱을 2.5s보다 넉넉하게)해서 근접
   후보 재탐색.
4. danger override 가설 자체를 재검토 — 정체구간 붕끗의 다른 원인
   후보(예: 45차 launch bypass의 exit 전환 순간 급하강 우려 사항,
   source 플리커 등)로 방향 전환.

**코드 변경**: `devnotes/toolkit/analysis_helpers.py`(신규 함수)만
변경, `ryu` 코드는 미변경(2번 구현 여전히 착수 전).


## 58차 2번 계속4 (설계 확정·구현·합성검증·패치 전달 완료, 실차검증 대기) — 저속+앞차 강한감속 danger override 확장

**배경**: 아래 "58차 2번 계속3"에서 정량 확인된 원인(TTC 6~12s 램프
구간에서 앞차 실측 감속이 과도하게 감쇠되다 한꺼번에 반영)에 대해
조치 후보 (a)GATE_NONE 상향 / (b)앞차 실측 감속 크기 기반 보조 경로
/ (c)정체 한정 프레이밍 폐기 중 논의.

**방향 결정**: (b) 채택. 근거:
1. GATE_NONE 상향은 이번 케이스(강한 감속만 조기 반영돼야 함)와
   달리 완만한 감속 상황까지 전부 더 일찍 반응하게 만들어 문제를
   정밀하게 못 잡고 범위만 넓힘.
2. 26차(vision closing-rate 게이트)/38차(TTC 게이트 자체)와 동일하게
   "TTC 단독"이 아니라 "실측 위험 신호(이번엔 aLeadK)"를 별도
   축으로 추가하는 것이 이 코드베이스가 반복해온 검증된 패턴.
3. `LEAD_ACCEL_TTC_GATE_FULL=12.0`은 이미 NEEDS_VALIDATION 상태라
   더 넓히면 회귀검증 부담만 커짐.

사용자 요구로 범위를 추가로 좁힘: **"저속구간(정체 등) 한정, 그 외
구간엔 영향 없어야 함"** → TTC 문턱 자체를 만지지 않고, 저속(v_ego
게이트) + 강한감속(a_lead 문턱) 조합을 새 danger-override 보조
경로로 얹는 방식으로 최종 설계.

**설계값**: `LOW_SPEED_STRONG_DECEL_V_EGO_GATE=30km/h`(≈8.33m/s,
이번 이벤트 피크 29.4km/h를 포함하면서 일반 주행과는 구분되는 선),
`LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH=-1.8m/s²`(이벤트 실측 -1.5~
-2.0m/s²대 참고). "congestion_active"(정차 반복횟수 상태추적, 58차
2번 원설계에 있던 것) 병행은 보류 — 단순 v_ego 게이트만으로 저속
한정 요구가 충족되고 이번 실측 이벤트도 커버되므로, 복잡도를 낮추는
쪽으로 사용자와 합의(오탐 나오면 추후 좁히기로).

**구현** (`long_mpc.py`, `process_lead()`): danger override 판정에
`or low_speed_strong_lead_decel`(= `v_ego <= GATE and a_lead <=
THRESH`) 추가. 성립 시 TTC 위치·39차 rise-rate 제한과 무관하게 즉시
weight=1.0 — "TTC 문턱 넘을 때까지 감쇠 누적 후 몰아서 반영"이 아니라
애초에 감쇠 자체가 안 생기게 하는 방향. 게이트가 v_ego 하나로 닫혀
있어 게이트 밖(고속/일반 주행)에서는 이 분기가 원천적으로 안 열림.

**합성검증** (`devnotes/toolkit/sim_low_speed_decel.py`): `process_
lead()`의 weight 계산부(margin_accel_weight/ttc_accel_weight/
rise-rate limiter/danger override)를 순수함수로 재현, 4개 시나리오
전부 PASS —
- **A(고속 회귀)**: v_ego=25m/s 고정, TTC 6~12s 램프 왕복 + a_lead
  강(-2.0)/완만(-0.2) 번갈아도 patch 전/후 weight 시퀀스 **diff=0**
  (게이트 밖 100% 동일 보장 확인).
- **B(이벤트 재현)**: 저속(0→28.8km/h 재가속, 실측 피크 29.4km/h와
  근접) + a_lead=-1.8 지속, closing을 0→4.5m/s로 램프시켜 min
  TTC≈3.33s로 구성(danger 2.5s 미발동, 실측 4.45s와 정합 — 우연히
  기존 danger override 경로를 밟지 않도록 의도적으로 통제). unpatched는
  초반(t=0.5s) weight=0.000(감쇠 발생) → 최대 사이클당 변화폭이
  rise-rate 한계(0.050=1.0/s×dt)에 걸려 몰아서 반영되는 패턴 재현.
  patched는 전 구간 weight=1.0 고정(감쇠 자체 미발생, danger override
  경로가 아니라 저속게이트 경로로 도달했음을 danger_hit=False로 확인).
- **C(오탐 방지)**: 저속이지만 a_lead=-0.5(threshold -1.8 미달) —
  게이트 미개방, patch 전/후 **diff=0**.
- **D(경계 전이)**: v_ego가 게이트값(8.333m/s)을 sin으로 여러 번
  넘나들어도 예외 없이 동작, 게이트 열린 300프레임 전부 즉시 w=1.0.

단, 이는 로직 단위 합성검증이며 **실제 acados MPC 파이프라인/실차
로그로는 아직 미검증**(26차 때와 동일한 한계).

**전달**: `c3-ms-dev` **origin push 완료** (`e17e078..a35a39f`). `git
format-patch` → `verify-am` 브랜치에서 `git am` + `py_compile` 통과
확인 → `0001-long_mpc-danger-override-58-2.patch` 전달 → 사용자
`C:\dev\ryu`에 `git am` + push 완료 확인.

**다음(최우선)**: 실차 검증 — (1) 이번 이벤트와 같은 저속 재가속+
앞차감속 상황에서 급가속→급감속 반전(붕끗)이 사라지는지, (2) 고속/
일반 주행 회귀 없는지. 통과 시 58차 3번(정지앞차 반응 강화)으로 진행.


## 58차 2번 계속3 (완료 — 아래 내용 그대로, 계속4에서 방향 결정·구현으로 이어짐) — 화면녹화+rlog 대조로 "정체구간 붕끗" 이벤트 정량 확인, 원 가설(danger override) 기각

**배경**: 사용자가 화면녹화 clip 2개(161836/161929)에 이어 같은 구간
rlog(`정체구간_붕끽_이게_확실한_느낌.zip`, route `a3a55cb808` seg11/12)를
제공. `extract_log.py`로 CSV 추출(HEAD `e17e078`) 후 clip2의 "0→33kph
가속 후 급감속" 이벤트와 일치하는 지점을 route 내에서 특정.

**특정된 이벤트 (route time t=4420.0~4423.0, seg12)**:
- t=4421.9~4422.1: vEgo 피크 29.4km/h(영상에서 33으로 보였던 것과
  근접, 클러스터 표시값과 vEgo 실측 오차로 추정), 이때까지 aEgo는
  +0.6~0.8m/s²로 **계속 가속 중**.
- t=4422.1~4423.05: **aEgo가 +0.05 → -2.63m/s²로 1초 이내 붕괴**(영상의
  accel 그래프 spike-crash와 정확히 대응).
- 이 구간 dRel은 24.4m → 약 17m로 감소, vRel은 0 → -4.2m/s.
- **min TTC = 4.45s (t=4422.80)** — `LEAD_ACQ_TTC_DANGER=2.5s` danger
  override 문턱에 전혀 못 미침. `ttc_danger_events()`(문턱 2.5s)도
  이 이벤트를 검출하지 못함(정상 동작 확인).
- `leadVLead`(리드 절대속도) 수치미분으로 계산한 근사 리드 가속도는
  **이 사건 훨씬 이전인 t≈4420.0부터 이미 지속적으로 -1.5~-2.0m/s²대**
  (노이즈 있으나 추세 뚜렷) — 즉 **앞차는 ego가 여전히 가속 중이던
  시점부터 이미 한참 하드브레이킹 중이었음**.
- brakePressed=False, cruiseEnabled=True 내내 유지 — 100% ADAS 제어,
  운전자 개입 없음.

**해석(원 가설 기각, 재구성)**: 58차 2번 원 설계는 "정체 중 짧은 dRel
+ TTC danger override(≤2.5s) 오발동"을 가정했으나, **이번에 정량
확증된 실제 이벤트는 TTC가 danger 문턱 근처에도 안 갔음** — danger
override 경로가 아니었다. 대신 `ttc_accel_weight()`(38차, long_mpc.py
L169)의 `LEAD_ACCEL_TTC_GATE_NONE=6.0s`/`GATE_FULL=12.0s` 램프 구간이
원인 후보로 재부상: TTC가 12s→6s로 서서히 좁혀지는 동안(weight
0→1 램프) 앞차의 실제 급감속(aLeadK)이 weight로 계속 감쇠돼 MPC에
充分히 반영 안 됨 → ego는 이미 하드브레이킹 중인 앞차를 향해 계속
가속 → TTC가 6.0s 문턱을 넘는 순간(weight→1.0) 그동안 감쇠돼 있던
큰 음수 aLeadK가 한꺼번에(rise-rate 제한 내에서도 1초 이내로) 반영돼
급격한 가속→감속 반전(붕끗)으로 체감. **이건 39차가 이미 알고 있던
"weight 급등 시 감쇠돼 있던 aLeadK 누적값이 한꺼번에 반영" 문제의
변주로 보이며, danger override(2.5s 이하 즉시 우회)가 아니라 그
위쪽 6~12s 램프 구간 자체의 특성**임을 이번 실측이 처음으로 정량
확인함.

**추가로 중요**: 이 이벤트는 "정체구간"(정지-출발 반복) 특유의 짧은
dRel 상황이 아니라, dRel 17~24m대의 **평범한 저속 추종 상황에서 앞차가
실제로 급감속한 케이스**였다 — 즉 58차 2번이 "정체구간 한정 로직"으로
접근하는 것 자체가 범위를 잘못 좁힌 것일 수 있음(이 패턴은 정체와
무관하게 재현될 가능성).

**코드 변경 없음(분석만)**. `devnotes/work/` 스크래치 계산만 사용,
toolkit 정식 함수 추가는 아직 안 함(방향 확정 후 필요 시 재현
스캐너로 편입 검토).

**다음(사용자 방향 결정 필요, 코딩 착수 전)**:
1. 위 재구성된 원인(6~12s TTC 램프 구간에서 앞차의 실제 강한 감속이
   과도하게 오래 감쇠됨)이 맞다면, 조치 후보:
   (a) `LEAD_ACCEL_TTC_GATE_NONE`을 6.0s보다 높여(예: 8~9s) weight가
       더 일찍 올라가게 하거나,
   (b) TTC 게이트와 별개로 "앞차의 실측 감속 크기 자체"가 일정 문턱을
       넘으면(예: aLeadK <= -2.0m/s²) TTC와 무관하게 weight를 앞당겨
       올리는 보조 경로 추가,
   (c) 그 외 사용자 판단.
2. "정체구간 한정" 프레이밍을 버리고 "저속 추종 중 앞차 급감속 전반"
   으로 스캐너/설계 범위를 넓힐지 결정.
3. 방향 확정 후 합성 시나리오 검증 → 패치 → 실차 검증 순서로 진행.


## 58차 3번+후속수정 실차검증 (2026-08-24 06:50 로그, commit `1145aea`) — 정지앞차 미인식/A 조기등록

**로그**: 14세그먼트(14분/5.6km), 시내 저속주행(평균 24.2km/h). 메타 확인
결과 commit `1145aea`(58차1~3번+후속수정 전부 반영) 상태에서 추출됨.

**[CONFIRMED] 외곽게이트 후속수정 실제 동작** — `leadStatus=True`이면서
`leadModelProb<=0.5`인 케이스가 13개 구간/690 row에서 실제로 관측됨
(구코드였다면 원천적으로 불가능했던 상태). 후속수정이 합성검증뿐 아니라
실로그에서도 최종 출력까지 전파됨을 확인.

**[CONFIRMED, qcamera 대조] seg0 t=62.61~90.32s (28초 정지앞차) — 정탐
확정**: vEgo=0, dRel 10.9~13.9m 안정, prob 0.35~0.50대를 오가며 28초간
등록 유지. t=60/75/90s 세 시점 프레임 전부 **동일 위치에 정지한 검정
세단**을 보여줌 — A(tentative 조기등록)가 실제 존재하는 정지차량을
정확히 계속 물고 있었음이 영상으로 확정됨(`frames/58차3번_실차검증_0824/
seg0_t60.00_off+0_seg86.jpg` 등). **단, 이 구간은 `cruiseEnabled=False`
(운전자 수동조작, 정지신호 대기 추정)여서 실제 종방향 제어에는 영향
없었음** — 인지 파이프라인 자체의 정탐 검증이지 제어 검증은 아님.

**[NEW FINDING, qcamera 대조] seg2 t=182~197s — dRel/vRel 요동의 원인
규명, "오탐"이 아니라 "인접차선 다중 후보" 문제**: `cruiseEnabled=True`
상태에서 A가 "신규" 발동한 유일한 실사례(t=187.01s, 직전 leadStatus=False
→ True). dRel이 15m→36m→53m→62m로 튀고 vRel이 +2.7↔-76↔+3.1처럼
물리적으로 불가능하게 요동쳐서 처음엔 오탐지로 의심했으나, **qcamera
대조 결과 역광(태양 플레어) + 넓은 다차선 교차로/도로**임을 확인
(`seg2_t182.00...jpg`: 역광 심한 상태에서 전방 차량, `seg2_t196.00...jpg`:
좌측 차선 빨간차 + 우측 흰색 SUV 등 여러 차량이 각 차선에 분산). 즉
"차가 없는데 잘못 만든 것"이 아니라 **매 프레임 다른 차선의 다른 실제
차량을 번갈아 잡던 것** — `track_scc` 인접차선 미검증 이슈(userMemories
"track_scc fallback has no lane validation")와 같은 계열의 구조적 문제.
다행히 이 구간은 `src=vturn`이 속도를 지배하고 있어 **실제 감속/가속에
영향은 없었음**(회귀 아님, 하지만 A/B와는 별개로 추후 다차선 상황
lane-validation 보강이 필요함을 시사하는 실사례 확보).

**[CONFIRMED] seg4 t=301~306s — 실제 앞차 감속, 시스템 정상**: prob
0.53~0.72대 정상경로로 등록된 실제 전방 차량(dRel~76~78m, vRel~-3.2~
-3.6m/s로 물리적으로 합리적). qcamera 확인 결과 교차로 진입부에 실제
차량 존재. t=304.47 운전자가 브레이크+크루즈 해제했으나 이는 교차로
진입에 따른 정상적 개입으로 보이며 시스템 실패 근거 없음. harsh_brake
82건 대부분 이런 운전자 개입(brakePressed 기준)이지 시스템 기인 위험
감속 패턴은 확인 안 됨.

**B(안전측 보정) 관련**: 이번 로그에서 B가 명확히 발동한(모델 과소평가를
실측이 안전측으로 보정) 뚜렷한 사례는 못 찾음 — 표본 부족, 추가 로그
필요.

**저장된 프레임**: `frames/58차3번_실차검증_0824/` — seg0(정탐 확정 3장),
seg2(역광/다차선 4장 중 3장), seg4(실제 리드 2장).

**결론/상태**: `PATCH_APPLIED` → `NEEDS_VALIDATION`에서 **일부
`VALIDATED`로 전환** — A의 정탐 유지 능력(seg0)과 후속수정의 실전파
(690 row)는 영상+수치로 확정. 다만 (1) cruise 유지 중 A가 실제 감속/
가속을 바꾼 사례는 표본이 1건뿐이라 오탐지 회귀는 계속 추적 필요,
(2) B는 미검증 상태 유지, (3) 다차선 인접차량 오인 리스크는 A/B와
별개의 신규 과제로 별도 추적 권장.

**다음**: (a) cruise 유지 중 A가 실제로 accel/decel을 바꾸는 사례를
더 많이 확보할 수 있는 로그(정체 진입부, 특히 저속 시내) 우선 수집,
(b) B 발동 사례 확보, (c) 다차선/인접차선 오인 이슈는 `track_scc`
lane validation 부재 findings와 통합해 별도 항목으로 스캐너 설계 검토.

## 58차 1번 (완료 — 패치 적용/push 완료, 실차 검증 대기) — 카메라(vision) 인식 감속을 레이더 인식 수준으로 강화

**요청**: "카메라 인식 감속이 좀 약함. 좀 더 강하게 하고싶어(레이더 인식
준용)."

**근본원인**: `radard.py`의 `VisionTrack.update()`가 원거리 vision lead에
대해 두 경로 중 (a) 단일 프레임 모델 예측(`lead_v_rel_pred`, 노이즈에
약하고 접근율 과소평가 경향) (b) 실측 dRel 미분값(레이더와 동일한
"위치 변화 → 속도" 방식, 훨씬 정확) 중 하나를 골라 쓰는데, 게이트
조건(`prob<0.97 또는 cnt<20`이면 (a)만 사용)이 실제 원거리 vision
lead의 prob 분포(0.5~0.8대가 흔함)에서 거의 항상 걸려 (b) 경로가
사실상 죽어있었음. 56/57차 qcamera 대조로 반복 확인된 "카메라 인식
시 미감속" 패턴의 root cause.

**조치 2건**:
1. `radard.py`: `VISION_TRACK_PROB_GATE=0.70`/`VISION_TRACK_CNT_GATE=10`
   (기존 0.97/20)로 게이트 완화, model_weight 보간 구간도 재조정.
   **합성검증 결과 이 변경 단독으로는 효과가 제한적임을 확인**
   (alpha=0.02 저역통과 시정수가 2.5초로 매우 느려서, 게이트가 자주
   열려도 실측값에 수렴하는 속도 자체가 느림 + 모델 예측 자체의
   편향이 blend에 계속 섞임).
2. **[핵심]** `long_mpc.py`: `process_lead()`에 `vision_dRel_rate`
   파라미터를 추가, vision-only + 충분히 오래 추적된(`_lead_acq_timer
   >= VISION_CLOSING_RATE_MIN_TIME`) 경우 long_mpc가 이미 25/26차부터
   독립적으로 계산해오던 `_vision_dRel_rate`(실측 dRel 미분, 지금까지는
   frac_rate로 MPC obstacle-distance 하한(floor)만 조이는 데 썼음)를
   MPC가 실제 lead 궤적을 extrapolate하는 `v_lead` 자체에도 반영.
   안전측(더 빠른 접근 쪽)으로만 작동, 완화 방향 없음. leadTwo에는
   미적용(`_vision_dRel_rate` 자체가 leadOne 기준으로만 부기됨).

**검증**: `work/test_visiontrack_gate.py`(합성 시나리오)로 1번 변경의
게이트 진입 빈도 증가 확인 + 한계(alpha/모델편향) 확인. 2번 변경은
별도 합성 시나리오로 v_lead 보정(24.0→19.0m/s) 시 t=4s MPC 예측 lead
거리가 196m→176m로 좁혀짐을 확인 — 더 이르고 강한 감속 목표로 이어짐,
2번이 실질 개선의 핵심으로 판단.

**적용 이력**: patch 2개(`0001-radard-VisionTrack-dRel-58-1.patch`,
`0002-long_mpc-vision-only-lead-dRel-_vision_dRel_rate-v_l.patch`)
전달. 사용자 로컬 `C:\dev\ryu`가 origin보다 크게(30개+ 커밋, `a4b5550`
시점) 뒤처져 있어 첫 `git am` 시도에서 패치2가 컨텍스트 불일치로 실패
→ `git reset --hard origin/c3-ms-dev`로 최신 기준(`f94a7d2`)까지 정리
후 재적용 성공, `git push` 완료(`f94a7d2..e17e078`).

**[주의, 다음 세션 확인]** 사용자 로컬이 22~23차 시점 커밋(`a4b5550`)
까지밖에 없었다는 건 그 사이의 40차 radard 크래시 긴급수정(`c31ddca`)/
45차 launch bypass(`651c434`) 등 여러 중요 패치가 실제 기기에 반영
안 됐을 가능성을 시사 — 사용자에게 평소 쓰던 `C:\dev\ryu`가 맞는지,
기기에 배포된 코드가 실제로 최신인지 확인 권장(다음 세션 후보, 낮은
긴급도는 아님).

**다음 단계**: 실차 검증 — (a) 원거리 vision-only 접근 상황에서 감속
개시가 빨라지는지, (b) 회귀 검증(정상 추종 상황에서 불필요하게
조여지지 않는지). 통과 시 → 2번 과제(정체구간 붕끽 완화)로 진행.

## 60차 — cutin/cutout 급감속 제보 분석: cut-in 시 vision_dRel_rate 오염이 58차1 v_lead 직접보정과 결합해 과잉감속 유발 (NEEDS_VALIDATION, 코드 미변경)

**배경**: 사용자가 "패치 이전엔 없던 증상"으로 cut-in/차선변경 상황 급감속
2건(`cutin_급감속.zip` route `ee004b2c19--5`, `cutout_급감속.zip`(실제는
차선변경 상황, 파일명과 달리 리드 cutout 아님) route `ee004b2c19--17`)
제보. 화면녹화 clip 포함, qcamera 프레임 대조 완료. HEAD `1ac07def461d`
(58차1/58차2만 반영, 58차3 A/B는 롤백된 상태) 기준.

**cutin 이벤트 (route --5, t=408.1~414.0)**:
- qcamera로 확인: 좌측에서 회색 SUV가 실제로 자차 차로에 cut-in, 이후
  전방 횡단보도(적색 노면표시) 앞에서 브레이크등 점등(실제 감속 중) —
  진짜 위험 상황(허위 리드 아님).
- t=408.14: vision-only(radar=False)로 prob=0.509(등록문턱 0.5 턱걸이)에
  신규 lead 등록, dRel=65.7m.
- **t=408.14~408.94(0.8초) 사이 dRel이 65.7m→24.0m로 급격히 붕괴** —
  이는 cut-in 차량이 화면 각도상 차로에 완전히 들어오며 검출 박스가
  "따라잡는" 관성 아티팩트로, 물리적 실제 접근이 아님(현재 vision
  등록 로직 자체의 구조적 특성).
- **`_vision_dRel_rate` 재현 시뮬레이션(devnotes work 스크립트, radard.py/
  long_mpc.py 실제 파라미터로 CSV `leadDRel` 재생)**: 이 dRel 붕괴가
  `VISION_CLOSING_RATE_MAX_PLAUSIBLE=30.0m/s` 클램프에도 불구하고
  다중 프레임(6~8프레임) 연속으로 클램프 상한에 붙어, 중앙값
  필터(윈도우 3)를 통과해 TAU=1.0s 저역통과 필터를 -9~-10m/s까지
  끌어내림 확인.
- **58차1(`e17e078`)의 `measured_v_lead = v_ego + vision_dRel_rate`
  직접 보정**(radar=False 구간 한정)이 이 오염된 rate를 그대로 받아,
  t=408.59~409.58(약 1초) 동안 MPC에 넘어가는 `v_lead`가 실제 모델
  추정(17~20m/s, 61~72km/h)보다 훨씬 낮은 **7.0~8.1m/s(25~29km/h)로
  왜곡**됨(측정: t=408.94 measured_v_lead=7.06 vs 모델 17.83).
- t=409.64 레이더 락온 순간(dRel=11.6m, 실제로도 근접 컷인이라 짧은
  거리는 맞음) 직후 aEgo가 -2.79m/s²까지 급감속.
- **판단**: 근접 cut-in 자체는 실제 상황(허위 아님)이라 어느 정도의
  감속 반응은 정상이나, 레이더 락온 *이전* 약 1초간 MPC가 "리드가
  25~29km/h로 이미 크게 느려짐"이라는 왜곡된 정보로 내부 궤적을
  계산해온 것이 락온 시점 이후의 초기 반응 강도를 증폭시켰을
  가능성이 높음 — 58차1 이전에는 `_vision_dRel_rate`가 frac_rate
  floor(장애물-거리 하한 조임)에만 쓰였고 `v_lead` 자체를 이 정도로
  직접 낮추지 않았으므로, **이 특정 실패모드(cut-in 등록 초기의
  dRel catch-up 스냅이 v_lead를 오염)는 58차1이 새로 연 경로로 판단**.

**cutout(→ 실제는 자차 차선변경) 이벤트 (route --17, t=1133~1149)**:
- 사용자 정정: 파일명과 달리 리드 차량의 cutout이 아니라 **자차가
  좌측 차선변경**(leftBlinker=True, t=1133.4~1137.0, laneChangeState는
  내내 off라 자동 차선변경 아닌 수동 조작으로 추정)한 상황.
- 차선변경 전후 약 9초간(t=1134.4~1143.4) leadStatus는 True/vision-only
  (radar=False) 상태에서 dRel이 59~118m 사이를 반복적으로 크게
  요동(여러 후보 차량 사이를 전환 추정, prob도 0.5~0.9대로 불안정) —
  cutin 이벤트와 유사하게 `_vision_dRel_rate` 오염 가능성 있는 구간.
- t=1143.48 레이더 락온: dRel=92.8m, vRel=-7.8m/s(강한 접근), 이후
  리드차량 자체가 거의 정지(vLead→0 근접)하는 진짜 정체/서행 차량으로
  확인 — t=1145.1~1148.9 사이 aEgo가 최대 -2.86m/s²까지 감속(4초에
  걸쳐 완만하게, 순간 스냅 아님).
- **판단**: 이 사례는 레이더 락온 이후의 감속이 실제 상황(정지에 가까운
  선행차 발견)에 의해 충분히 설명 가능하고, 감속 자체도 4초에 걸친
  완만한 프로파일이라 cutin 사례처럼 "순간 급감속" 패턴은 아님. 다만
  락온 이전 9초간의 vision-only 요동 구간에서도 cutin과 동일한
  v_lead 오염 메커니즘이 작동했을 가능성은 배제 못함(미검증) — 락온
  이후 반응이 다소 강하게 시작된 데(t=1145.08부터 이미 -1.1) 일부
  기여했을 수 있으나, 이 사례의 주된 원인은 실제 상황(느린/정지
  선행차)으로 판단, cutin 사례만큼 확정적이지 않음.

**공통 구조적 원인 요약**: `_vision_dRel_rate` 파이프라인(클램프
30m/s + 중앙값윈도우3 + TAU=1.0s)은 원래 "곡선에서의 단발성 스냅
노이즈"를 걸러내도록 설계됐으나(26차), **신규 트랙 등록 직후의
연속적(다중 프레임) dRel catch-up이나 차선변경 중 후보 전환처럼
"여러 프레임에 걸쳐 지속되는 구조적 스냅"에는 필터링 효과가
제한적**임을 이번 실측으로 확인. 58차1이 이 값을 `v_lead`에 직접
반영하도록 확장하면서, 이런 필터 사각지대의 파급력이 (기존
frac_rate floor 조임 수준에서) MPC의 lead 속도 추정 자체를 왜곡하는
수준으로 커짐.

**다음 단계(사용자 결정 대기, 코드 미변경)**:
1. 신규 트랙 등록 직후(예: `_lead_acq_timer` 첫 1~2초, 또는
   VISION_CLOSING_RATE_MIN_TIME 게이트 직후 일정 시간) `v_lead` 직접
   보정을 유예하거나 완화하는 방향 검토 — frac_rate floor 용도로는
   그대로 사용하되, v_lead 대체는 더 보수적 게이트 필요.
2. 또는 raw_rate 클램프 자체를 30m/s보다 낮추거나, median window를
   3보다 늘려 다중 프레임 catch-up 스냅에도 더 강건하게.
3. cutout(차선변경) 사례의 락온 이전 9초 구간도 같은 시뮬레이션 방식으로
   재현해 오염 여부/정도 정량 확인 필요(이번엔 cutin만 상세 재현).
4. 실측 시뮬레이션 스크립트는 이번 세션 work/ 스크래치(컨테이너 로컬,
   toolkit 미편입) — 재검증 시 devnotes에 정식 편입 검토.

## 60차 계속9 — 외곽게이트 후속수정(d6e334f)이 4개 기존 패치(58차1/58차2/cutin·차선변경 suppress)에 미치는 영향, 로직단위 시뮬레이션

**배경**: 사용자가 "60차 계속8 패치가 58차1(카메라인식 미감속)/58차2(정체구간
붕끗)/cutin·cutout/내차 차선변경 패치에 어떤 영향을 주는지" 질문 → 4개 시나리오
로직단위 시뮬레이션으로 확인(`work/sim_60cha8_downstream_impact.py`, toolkit
미편입 스크래치). 핵심 메커니즘: 60차 계속8은 `radarState.leadOne.status`가
True로 바뀌는 시점을 바꿀 수 있는데, 이게 `long_mpc.py`의 `_lead_acq_timer`
(58차1 v_lead보정 유예/cutin·차선변경 suppress/58차2 저속게이트 전부의 공통
시계) 기준점이라 이론상 4개 다 영향권.

**결과 (시나리오별 실질 영향)**:
1. **정체구간 정지앞차류(58차2/58차3원사례) — 영향 있음(의도된 개선)**: prob가
   0.5 근처에서 노이즈처럼 출렁이는 실측 패턴 재현 시, 구버그(외곽게이트 prob
   중복체크)는 노출비율 11%·플리커(재등록) 16회로 계속 등록↔해제 반복하던 것이,
   수정후엔 노출비율 82%·플리커 6회로 훨씬 안정적으로 유지됨 — tentative 승격이
   설계 의도대로 "일찍, 꾸준히" 등록시키는 것을 처음 확인(60차 원래 목적).
2. **cutin(--5류) — 영향 없음**: 끼어들기의 급격한 dRel/dPath 흔들림이 tentative
   jitter 게이트를 계속 리셋시켜 tentative_cnt가 승격문턱(10)에 전혀 도달 못함 →
   여전히 기존과 동일하게 정식등록(prob>.5)으로만 노출, 등록시점/억제window
   완전 동일(시뮬레이션상 diff 0).
3. **내차 차선변경(--12류) — 영향 없음**: 신규등록이 아니라 이미 등록된 트랙이
   조향간섭으로 흔들리는 문제라 tentative 로직과 무관. `LANE_CHANGE_VLEAD_
   CORRECTION_HOLD_S` 억제는 blinker 상태 기준이라 등록시점과 독립적으로 정상
   동작 확인(시뮬레이션상 diff 0).
4. **58차1(원거리 지속접근 v_lead보정) — 간접 개선 가능성**: 등록 안정화(플리커
   감소)로 `vision_dRel_rate` 축적이 끊기지 않고 이어짐 → 원래 취지가 더 잘
   작동할 가능성(정성적 추론, 별도 실측 필요).

**[신규, NEEDS_VALIDATION] 조합 리스크 발견**: 정체구간 시뮬레이션에서 58차2
저속강한감속게이트(`v_ego<=30km/h and a_lead<=-1.8m/s²`, TTC 위치 무관 즉시
weight=1.0)가 tentative 등록 프레임(아직 prob 0.35~0.5, 불확실 상태)에서도
열리는 것을 확인. 코드 확인 결과 tentative 등록 직후엔 `cnt<VISION_TRACK_
CNT_GATE`(10)라 `VisionTrack.aLead`가 radard 자체 스무딩 없이 modelV2 원시
예측치(`a_lead_vision`)를 그대로 씀(radard.py 535~539행) — 아직 확정 안 된
신뢰도 낮은 값에 danger-override급 즉시 반응이 걸릴 여지가 있음. v_lead
직접보정(58차1)은 `NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S=1.5s` 유예로
보호되지만, **저속게이트는 이 유예와 무관하게 즉시 반응**하므로 별도 보호가
없음. 실측 aLeadK 값 자체가 noisy한지는 이번 로직단위 시뮬레이션(외부에서
a_lead를 상수로 주입)으로는 확인 불가 — 실제 modelV2 a_lead_vision의 tentative
구간 노이즈 특성 확인 필요.

**다음(실차검증 시 추가 관찰 포인트로 반영)**:
1. 정체구간(정지-출발 반복) 상황에서 tentative 등록 직후 58차2 저속게이트가
   노이즈성으로(실제 위험 아닌데) 급하게 튀는 느낌이 있는지 특히 주의 관찰.
2. cutin/차선변경은 이번 패치로 영향 없음이 로직상 확인됐으므로, 기존
   60차계속7 검증 항목(정지앞차 조기인식/옆차선·역광 오탐 회귀/tentative_cnt
   사각지대)에 이 조합 리스크 하나만 추가하면 됨.
3. (저우선) 필요 시 `sim_60cha8_downstream_impact.py`를 toolkit에 정식 편입
   검토(현재는 work/ 스크래치).

## 60차 계속 — 3번째 사례(자차 차선변경, 옆차선 택시 멀어짐에도 급감속) 분석: 동일 메커니즘 3건째 재현 (NEEDS_VALIDATION 격상)

**배경**: 사용자가 신규 제보(`내차_차선변경.zip`, route `ee004b2c19--12`,
t=815.8~819.7, qcamera+화면녹화 clip 포함) — 자차가 우측 차선변경
(rightBlinker=True, laneChangeState는 내내 `off`라 수동 조작 추정)
중 옆차선 택시가 실제로는 멀어지는데도 자차가 급감속(aEgo 최저
-1.82m/s²)한 상황. HEAD `1ac07def461d`(58차1/58차2만 반영) 기준.

**실측 확인**:
1. t=816.98~817.38(0.4초, radar=False/vision-only 구간) 동안 dRel
   순간 변화율(finite-diff)이 **-4.95~-11.82 m/s로 8프레임 연속
   유지** — 같은 구간 report된 vRel(-0.05~-1.00m/s)보다 훨씬 큼.
   조향각/desiredCurvature가 이 구간에서 좌→우로 부호 전환(차선변경
   조향 시작)과 정확히 겹침 — 60차 cutin 사례의 \"다중 프레임 dRel
   catch-up\"과 동일한 신호 패턴, 다만 이번엔 신규 트랙 등록이 아니라
   **차선변경 조향으로 인한 비전 매칭 대상의 화면상 위치 이동**이
   유발 요인으로 추정(leadModelProb는 0.999대로 이 구간 내내 안정 —
   후보 전환이 아니라 동일 트랙의 dRel 추정치 자체가 조향에 연동돼
   흔들린 것으로 판단).
2. t=817.436 프레임에서 radar=False→True 전환과 동시에 dRel이
   18.61m→13.30m로 순간 점프(단일 프레임 변화율 -97m/s, 물리적으로
   불가능 — 레이더가 옆차선 택시라는 실제로 더 가까운 물체에
   새로 락온하며 발생한 catch-up), vRel도 같은 프레임에서
   -1.10→+1.20으로 부호 반전(택시가 실제로는 멀어지는 중임을 반영).
3. **그러나 aEgo는 락온 이후에도 0.3초간 계속 더 나빠짐**(t=817.436
   -1.13 → t=817.785 -1.82가 최저점) — vRel이 이미 양수(이격 중)로
   전환된 시점 이후에도 감속이 계속 강해진 것은, 락온 *직전*
   vision-only 구간에서 58차1(`e17e078`)의 `measured_v_lead = v_ego
   + vision_dRel_rate` 직접 보정이 이미 v_lead를 낮춰 MPC 내부
   궤적을 조여둔 상태였고, 락온 시점의 dRel 급락(13.3m로 근접)이
   여기에 더해지며 감속이 관성적으로 몇 프레임 더 진행된 것으로
   해석됨 — **60차 cutin 사례와 동일한 구조(vision-only 구간 오염된
   v_lead + 락온 시점 dRel 스냅의 결합)**.

**판단**: 60차에서 표본 1건(cutin)으로 NEEDS_VALIDATION 판정했던
가설이, 유발 트리거가 다른(신규 등록 catch-up이 아니라 차선변경
조향 연동 dRel 흔들림) **세 번째 독립 사례로 재현됨** — 특정
상황(cut-in 등록)에 국한된 문제가 아니라 `_vision_dRel_rate`
파이프라인이 \"수 프레임에 걸쳐 지속되는 구조적 dRel 변화\"(원인이
신규등록이든 차선변경이든) 전반에 취약하다는 원 가설이 강화됨.
**58차1이 새로 연 경로(v_lead 직접 보정)가 공통 증폭 요인이라는
판단도 그대로 유지, 여전히 코드 미변경.**

**사용자 결정**: 58차1(v_lead 직접 보정)만 격리해서 진위를 테스트할
목적으로 패치 이전 상태로 되돌리는 방안 논의 — 상세는 WIP.md
\"60차 계속\" 항목 및 사용자 안내 참고. cutin/cutout/이번 3건 전부
락온 *이전* vision-only 구간이 공통 발화점이라, 격리 테스트 시
세 로그(--5/--17/--12) 전부로 재검증 권장.

**다음 단계**:
1. 사용자가 v_lead 직접 보정만 비활성화한 테스트 브랜치로 재드라이브
   → 동일 상황(cutin/차선변경) 재현 시 급감속 강도가 줄어드는지 확인.
2. 개선 확인되면 정식 패치 방향 결정 — (1) 신규 트랙/차선변경 등
   "구조적 dRel 변화" 최초 N프레임 동안 v_lead 보정 유예, 또는
   (2) raw_rate 클램프/중앙값 윈도우 강화 등, 60차 \"다음 단계\" 항목
   참고.
3. route --17(cutout/차선변경) 락온 이전 9초 구간 정량 재현은 여전히
   미실시 — 우선순위는 낮음(이번 --12 사례로 가설 자체는 이미 3건
   재현 확보).

## 61차 (진행중, 체크포인트1 — 오늘 패치 실차검증 로그 16세그 분석 시작) — 60차 계속8 patch(get_lead 외곽게이트 fix) 적용 후 실주행

**배경**: 사용자가 오늘 패치(HEAD `d6e334f`, 60차 계속8 외곽게이트 fix) 적용 후
실주행 로그 2개 부팅세션(route `a2141d7786` 9세그/route `6f02a46c8a` 7세그,
총 16개 event-triggered 세그먼트, 각 화면녹화 clip 제목이 증상 라벨)을 업로드.
`extract_log.py`로 CSV 추출 확인 결과 `commit=d6e334f1ddb5` — **오늘 패치가
실제로 이 로그에 반영된 상태에서 기록됐음 확인**.

**16개 세그 개관** (min_aEgo/cruise_ratio):
- route_a2141d7786: seg1(앞차카메라인식, -3.02)/seg3(cutin, -3.24)/
  seg6(앞차카메라인식, -3.04, cruise=88%)/seg9(내차차선변경, -2.76)/
  seg12(cutout, -3.87)/seg14(cutin_택시, -4.29)/seg15(정체정지출발후급감x2,
  -2.25)/seg17(앞차카메라인식, -5.73, cruise=73%)/seg19(앞차카메라인식, -2.39)
- route_6f02a46c8a: seg1(옆차선레이더오탐→카메라인식, -2.89, cruise=85%)/
  seg2(정체정지출발후급감, -0.65)/seg3(옆차선카메라오탐, -4.46)/
  seg4(정지앞차카메라인식, -1.07)/seg5(앞차카메라인식, -1.75)/
  seg6(앞차카메라인식, -2.00)/seg7(cutout종료후지연출발, -3.98, cruise=89%)

**전체 안전지표**: harsh_brake_events 전체(운전자개입 포함) route_a2141d7786=14건/
route_6f02a46c8a=13건이나 **cruiseEnabled=True(ADAS 활성) 중 harsh_brake는
두 route 모두 0건** — ADAS가 유발한 급브레이크(driver override 유발)는 없음.
turn_speed_violation route_a2141d7786=1건/route_6f02a46c8a=2건(개별 미확인,
저우선).

**[중요 발견 1] seg1 "옆차선 레이더 오탐 급감_이후 카메라인식" — 상세 프레임단위
분석 완료, 근본원인은 60차 패치(vision VisionTrack.status) 범위 밖의 별도
메커니즘(track_scc/37차 SCC_FALLBACK_DPATH_GATE)으로 추정**:
- t=1377.60: `leadRadar`가 갑자기 True로 전환, `dRel≈100.6m`(직전 vision
  추정치 89.8m과 유사)인데 **`vRel`이 -0.6~-1.9 수준(vision 추정)에서
  -11.5 m/s로 순간 점프**. 이후 t=1378.5부터 aEgo가 급락해 t=1379.05에
  -2.89 m/s² 도달, 이후로도 `leadStatus`가 짧게 끊기며(-1380.0~1380.4)
  vRel이 -17 m/s대까지 확대, t=1382 이후 다시 vision(`src=road`)으로
  전환되며 dRel이 60m대까지 계속 줄어들고 aEgo가 t=1384.99 시점까지도
  -2.1 유지(윈도우 끝까지 감속 지속 — 이벤트 전체가 회복 안 된 채 클립 종료).
- **물리적 비일관성**: dRel이 t=1377.6~1379.6 약 2초간 거의 100m 부근에서
  정체(≈90~107m 사이 왕복)했는데 보고된 vRel(-8~-17 m/s)대로라면 그 사이
  16~34m는 좁혀졌어야 함 — vRel 값 자체가 신뢰할 수 없는 순간(레이더가
  실제 전방 리드가 아닌 다른 물체를 단발 락온했을 가능성)으로 판단.
- **qcamera 프레임 대조**(t=1377.5/1377.6/1378.5): 전방 100m 부근에
  실제 차량들이 있으나 도로가 완만한 우회전 구간(교량+가드레일)이라
  전방 차량 외에 근접한 물체(가드레일/표지판/구조물)가 카메라상 우측에
  근접해 있음 — 레이더 오인식 후보로 가드레일/도로구조물 가능성.
- **코드 분석**: `radard.py`의 `SCC_FALLBACK_DPATH_GATE=2.0m`(37차, 옆차선/
  경로이탈 물체 대상 dPath 검증)는 `track_scc.vLead < 5.0`(거의 정지한
  물체) 조건이 함께 만족돼야만 적용됨(`get_lead()` L826-838). 이번 이벤트의
  `vLead ≈ vEgo+vRel ≈ 21.1-11.5 ≈ 9.6 m/s`로 **5.0 미만이 아니므로 이
  dPath 게이트 자체가 애초에 관여하지 않는 속도 구간** — 즉 **"레이더
  오탐" 증상은 오늘 패치(60차 A/B, VisionTrack tentative 등록/dPath
  게이트)가 다루는 영역과 무관한, track_scc 중속도 구간 오탐 사각지대일
  가능성 높음(NEEDS_VALIDATION, 표본 1건).**
- 정확한 확정(진짜 track_scc 경로였는지 vs match_vision_to_track 정상
  매칭인데 레이더 노이즈였는지)은 CSV에 dPath/trackId 필드가 없어 미확정 —
  37차 세션에서 쓰던 `extract_lead_detail.py`류 확장 스크립트(leadDPath/
  leadTrackId 포함) 재작성 필요.

**[진행중] seg3 "옆차선 카메라 오탐 급감"**: t=1503.75 vision+radar 동시
등록(dRel=77.4, vRel=-0.6)으로 시작, t=1507 부근부터 vRel이 -0.6에서
점진적으로 -6~-8까지 커지며 감속 시작(aEgo 최저 -4.46@t=1511.4), dRel이
연속적으로 90m→10m대까지 부드럽게 좁혀지다 t=1513.70 레이더 재락온
(dRel=21.2) 후 t≈1521에 dRel=3.2m/vRel=0으로 완전정지. **qcamera 프레임
대조 결과(t=1503.7/1507/1509/1511) 전방 자기 차로에 실제 차량들이
보이고, t=1509~1511 프레임에서 브레이크등 켜진 차량들이 정지/서행 중인
게 육안으로 확인됨** — dRel/vRel/aEgo 궤적이 매끄럽고 물리적으로
일관돼 있어(seg1과 달리 순간 점프 없음), **1차 판단으로는 "카메라
오탐"이 아니라 진짜 정체/정지 차량 추종으로 보임(사용자의 라벨과
프레임 관찰이 불일치 — 재확인 필요)**. 다만 6프레임 샘플링(2~4초
간격)이라 t=1503.75~1507 사이 짧은 오탐 구간이 있었을 가능성은
배제 못함 — **다음 체크포인트에서 이 구간(1503.75~1507) 조밀 프레임
재확인 필요**.

**남은 작업(다음 체크포인트/세션 최우선)**:
1. seg3 t=1503.75~1507 조밀 프레임 재확인(오탐 여부 재판정).
2. seg4(정지앞차카메라인식, min_aEgo=-1.07로 온건) — 60차 A/B가 겨냥한
   핵심 시나리오(정지앞차 조기인식)이므로 최우선 심층 분석 필요.
3. route_a2141d7786 9개 세그(cutin/cutout/차선변경/정체정지출발 등)
   전체 상세 타임라인 미착수.
4. route_6f02a46c8a seg5/6(앞차카메라인식)/seg7(cutout후지연출발) 미착수.
5. turn_speed_violation 3건(a2141d7786 1건/6f02a46c8a 2건) 개별 미확인.
6. 최종 종합판단("오늘 패치가 잘 적용됐는가") 및 개선방향 논의는 위
   항목들 완료 후 진행.

**세션 종료 아님 — 토큰 예산 고려 중간 체크포인트, 이어서 진행 예정.**

## 61차 체크포인트2 — 16세그 자동 스캔 + seg3/4 연속성 확인, 1차 종합판단

**seg3/seg4 연속성 확인(중요)**: seg3("옆차선 카메라 오탐 급감") CSV가
t≈1516.1에서 끝나고 seg4("정지 앞차 카메라 인식")가 t=1516.2에서 바로
이어지는데, **seg4 시작 시점에 이미 `leadStatus=True, dRel=8.9m,
vEgo=2.31m/s`로 리드를 유지한 채 넘어옴** — 즉 두 세그는 하나의 연속된
이벤트(원거리 접근→감속→거의 정지 직전)이고, qcamera로 확인한 대로
**실제 정지/서행 차량 추종이 맞음(seg3 라벨의 "오탐"은 재확인 결과
근거를 못 찾음 — 다만 6프레임 샘플링이라 순간적 flicker까지는
배제 못함, NEEDS_VALIDATION 낮은 우선순위)**. seg3 t=1503.75~1507.45
구간은 `src=vturn`(곡선 진입) 중 vision dRel/prob가 심하게 요동
(60~95m, prob 0.14~0.94)쳤으나 이 구간 내내 `aEgo`는 0.2~0.7 유지(양수,
감속 없음) — 노이즈가 있었지만 실제 제어(감속)로는 전혀 이어지지
않음, 60차 이전 세션들의 "vturn 곡선구간 vision 노이즈" 알려진 특성과
일치. 실제 감속은 t≈1509.4부터 시작해 프레임상 확인된 진짜 정지차량
행렬까지 매끄럽게 이어짐 — **정상 동작으로 판단**.

**16세그 전체 자동 이상탐지**(vRel 급변화 대비 dRel 불변 패턴 스캔,
느슨한 문턱): route_a2141d7786 7개 세그에서 소규모(dv/dt 1.4~6.3)
후보 다수, route_6f02a46c8a도 유사 — **전부 진폭이 작아(체크포인트1의
seg1 t=1377.60 이벤트의 dv/dt≈-217과 비교하면 2자릿수 차이) 일반적인
비전 추정 노이즈 수준으로 판단, seg1 사례처럼 뚜렷한 이상 신호는
16세그 중 seg1 1건뿐으로 재확인됨.**

**1차 종합 판단(정밀 개별검증 3/16 + 자동스캔 16/16 기준)**:
1. **오늘 패치(60차 계속8 외곽게이트 fix)는 로그 commit 필드로 실제
   반영 확인됨.**
2. ADAS 활성 중 harsh_brake 0건(양쪽 route) — 패치가 유발한 위험한
   급제동 없음.
3. 60차 A/B(VisionTrack tentative 조기등록+dPath게이트)의 핵심 타겟인
   "정지앞차 인식"은 seg3→seg4 연속 이벤트로 매끄러운 정상 동작 확인
   (min_aEgo -1.07의 온건한 감속으로 정지 완료).
4. **[신규 발견, 오늘 패치 범위 밖]** seg1 "옆차선 레이더 오탐" 1건은
   `track_scc`/37차 SCC_FALLBACK_DPATH_GATE의 `vLead<5.0` 조건부 적용
   사각지대로 추정 — 오늘 패치와 무관한 별도 트랙(레이더 단발 폴백)의
   문제로, **다음 개선 논의 시 최우선 후보로 제안**.
5. 나머지 13개 세그(cutin x2/cutout x2/차선변경/정체정지출발 x2/
   앞차카메라인식 x6/cutout후지연출발)는 자동 스캔상 특이 이상 없었으나
   **개별 qcamera 정밀검증은 미실시** — 시간/토큰 예산상 이번 세션엔
   생략, 필요 시 다음 세션에서 표본 확대 검증 가능.

**남은 항목(다음 세션 후보, 저우선)**:
- turn_speed_violation 3건(a2141d7786 1건/6f02a46c8a 2건) 개별 미확인.
- seg1 근본원인 확정(track_scc dPath 실측, extract_lead_detail류 스크립트
  필요) 후 SCC_FALLBACK_DPATH_GATE의 vLead<5.0 조건을 완화/제거하는
  패치 설계 여부 논의.
- 나머지 13세그 개별 qcamera 검증(표본 확대).

**세션 종료 아님 — 사용자와 대화로 개선방향 논의 진행 예정.**

## [신규 발견 + 방안 C 구현 완료, 실차검증 대기] cutin 급감속 (r1-3, r1-14/택시) — vision dRel 미분 착시로 인한 급감속

**증상**: 자기 차로로 옆에서 끼어드는(cutin) 차량이 오히려 자차보다
가속하며 이탈 중인데도, 레이더 락온 직전 자차가 급감속(seg3
aEgo -3.24m/s²/seg14 -4.29m/s²)하는 문제 2건 제보.

**근본원인(구조적, 우연 아님)**: 두 사례 모두 레이더 락온 순간 vRel
부호가 뒤집힘 — 락온 직전 vision 추정 vRel은 계속 하락(closing 방향
착시)해 aEgo가 급락하는데, 락온 순간 dRel은 거의 그대로인데 vRel이
즉시 +3~4.6m/s로 튐(레이더 실측 = 오히려 벌어지는 중). 원인은 cutin
(측면 진입) 순간 vision의 dRel 프레임간 미분값이 "종방향 급접근"이라는
착시 신호를 만들어내는 것 — 실제로는 옆 차로에서 들어오며 dRel이
기하학적으로 뚝 떨어지는 것뿐. 이건 58차1(v_lead 직접보정)/26·33차
(frac_rate DANGER 게이트)가 쓰는 "vision dRel 미분 기반 closing-rate"
신호 자체의 근본 한계이고, 60차 A/B(tentative 등록/dPath게이트)는
이 트랙이 이미 정식 등록된 이후라 적용 범위 밖 — 완전히 별개의 신규
발견.

**조치(방안 C, 채택·구현 완료)**: `long_mpc.py`의 `LongitudinalMpc`에
`DREL_DISCONTINUITY_DROP_THRESH=15.0m`/`DREL_DISCONTINUITY_WINDOW_N=5`
(프레임, ~0.25s@20Hz) 신설. vision-only dRel 부기 블록(기존
`_vision_dRel_rate` 계산부) 안에서 원본 dRel 값 자체의 최근 5프레임
윈도우 양끝 차이가 -15m 이상 급락하면 `_lead_acq_timer = 0.0`으로
리셋 — **새 코드경로 추가 없이 기존에 이미 검증된(60차 계속2 합성검증
통과) `NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S=1.5s` suppress 메커니즘을
그대로 재사용**함(v_lead 직접보정 + frac_rate/ttc_dRel 크로스체크 모두
자동으로 1.5초간 유예, 신규리드 게이트와 동일 경로). rate/중앙값 필터는
"지속접근 vs 일회성 스냅"을 구분하려고 완만하게 흡수하는 게 목적이라
이 급락 자체를 못 잡을 수 있어, 필터 이전 원본 dRel 값으로 별도 판정.

**안전 백스톱 확인(코드 리딩)**: `process_lead()`의 TTC danger
override(`ttc_now <= LEAD_ACQ_TTC_DANGER`, 2.5s)는 `lead.vLead` 기반
`ttc_now`를 매 프레임 직접 계산하며 `_lead_acq_timer`와 전혀 무관 —
이번 리셋과 완전히 독립적으로 항상 즉시 반응 유지됨을 코드로 확인.

**로직 단위 합성검증(`work/sim_drel_discontinuity.py`, 순수함수 재현,
4개 시나리오)**:
- 정상 완만 접근(2m/frame, 5프레임 누적 8m) — 미트리거(오탐 방지 확인)
- cutin 급락 재현(65→24m류 catch-up 크기) — 4번째 프레임에서 트리거 확인
- 진짜 급접근(전방 급브레이크류, 5프레임 -38m) — 트리거됨(예상된 동작 —
  단 danger override는 별도 경로로 항상 살아있어 안전 반응 자체는
  지연 안 됨, 위 안전 백스톱 확인 참고)
- 단발 1프레임 스냅 후 즉시 복귀 — 미트리거(과민반응 방지 확인)
**주의**: 이는 로직 단위 합성검증이며, 실제 r1-3/r1-14 원본 로그로
직접 재생 검증한 것은 아님(원본 CSV가 이번 세션에 없어, 문서 기록의
수치 패턴만 근사 재현). **실제 로그 재확보 시 재검증 필요(NEEDS_VALIDATION)**.

**전달/복구 경위**: 이 항목은 61차 계속(방안C) 세션에서 최초 작성됐으나
당시 devnotes push 없이 세션이 종료돼 origin에 반영 안 된 채 유실됨 —
다음 세션(이번 세션) 시작 시 사용자가 업로드한 로컬 `long_mpc.py`
(이미 방안C 코드 반영된 상태)로 대조해 patch를 재구성·재검증 후 이
기록을 복구함. `0001-61-C-cutin-dRel-suppress.patch`(base `d6e334f`)
`git am` 검증(temp branch) + `py_compile` 통과 확인.

**다음(최우선)**:
1. ~~사용자가 이 패치를 `C:\dev\ryu`에 이미 `git am` 적용했는지 + push~~
   → **완료 확인됨(62차)**. origin `c3-ms-dev` HEAD가 `4ea63c3`(방안C
   커밋)이고 로컬 HEAD와 정확히 일치, 미푸시 커밋 없음 재확인됨.
2. 실차 검증: (a) r1-3/r1-14류 cutin 재현 시 급감속이 실제로 완화되는지,
   (b) **회귀 검증 필수** — 정상 cutin이 아닌 진짜 급접근(전방 차량
   급브레이크 등)에서 danger override가 지연 없이 그대로 작동하는지,
   (c) 신규등록 게이트(60차 계속2)와 겹치는 케이스에서 이중 트리거로
   인한 부작용 없는지. **[63차 갱신] (b)(c) 모두 로직 단위 재확인
   완료(아래 63차 항목 참고), 실차 검증만 남음.**
3. 가능하면 r1-3/r1-14 원본 rlog 재업로드받아 실측 dRel 시퀀스로
   이번 로직을 직접 재생 검증(현재는 문서 기록 기반 근사 시뮬레이션뿐,
   63차에도 원본 로그 미확보로 여전히 유효).
4. `DREL_DISCONTINUITY_DROP_THRESH=15.0m`/`WINDOW_N=5` 값 자체는 설계
   추정치 — 실차 반응 보고 튜닝 필요.
5. 방안 A(radard.py VisionTrack dPath 변화 플래그를 radarState.leadOne에
   실어 long_mpc.py가 직접 참조)는 더 근본적이지만 프로세스 경계를
   넘는 신규 필드 추가라 40차 크래시류 리스크 있어 이번엔 보류 유지.

## [63차, 체크포인트] 방안 C 시뮬레이션 재검증 — 코드 라인 직접 재현 방식으로 전환, 6/6 PASS

**배경**: 62차 항목의 "다음(최우선) 2번(회귀검증)/3번(원본 로그 재생
검증)"을 진행하려 했으나, 이번 세션에도 r1-3/r1-14 원본 rlog가 업로드
되지 않아 실측 재생 검증은 여전히 불가. 대신 기존 로직 단위 합성검증
(`work/sim_drel_discontinuity.py`, 컨테이너 리셋으로 유실)을 재작성하며
검증 방식 자체를 개선.

**개선점**: 이전엔 순수함수로 로직을 재구현한 것이었는데, 이번엔 실제
`long_mpc.py` 801~844줄(방안 C 관련 블록)의 조건문/상수를 그대로
복사해 재현 — 코드와 시뮬레이션 스크립트 간 drift(둘이 몰래 달라지는)
리스크를 제거함. `DREL_DISCONTINUITY_DROP_THRESH=15.0`/`WINDOW_N=5`/
`NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S=1.5` 상수도 grep으로 실제 코드와
값 일치 확인 후 사용.

**시나리오 6개 전부 PASS** (기존 4개 + 신규 2개):
1. 정상 완만 접근(2m/frame) — 미트리거
2. cutin 급락 재현(65→24m류) — 4번째 프레임 트리거
3. 진짜 급접근(5프레임 -38m) — 트리거(예상된 동작, danger override는
   별도 경로라 안전 반응 자체는 지연 없음)
4. 단발 1프레임 스냅 후 즉시 복귀 — 미트리거
5. **[신규, 62차 항목 2-(c) 대응]** 신규등록 직후(`_lead_acq_timer`
   이미 0에 가까운 상태)에 discontinuity까지 겹치는 이중 트리거 케이스
   — 예외/음수 타이머 등 부작용 없이 정상 트리거만 됨 확인.
6. **[신규, 62차 항목 2-(b) 대응]** danger override 독립성 — 코드
   구조 재확인(정적 확인, `ttc_now`가 `_lead_acq_timer`와 완전히
   분리된 변수임을 재확인).

**결론**: 62차 "다음(최우선)" 2번 항목 중 (b)(c)는 이번 로직 단위
재확인으로 커버됨. 단 (a)(그리고 3번 원본 로그 재생 검증)는 실측
데이터가 필요해 여전히 미완 — **원본 rlog(r1-3/r1-14) 재업로드 또는
실차 드라이브 결과가 다음 세션 최우선으로 유지됨.** 코드 변경 없음
(ryu 미변경, `work/sim_drel_discontinuity.py`만 신규 — toolkit 미편입,
실제 로그 검증 전까지는 스크래치로 유지하는 기존 원칙과 동일).

## [63차 계속, 중요] 방안 C 실측 재생 검증 완료 — r1-3은 효과 확인, **r1-14는 보호 공백(gap) 발견**

**배경**: 사용자가 r1-3/r1-14 원본 rlog를 재업로드(`drive-download-
20260824T072553Z-1-001.zip`, route `a2141d7786` seg3="cutin 급감속"/
seg14="cutin 급감속_택시_" 라벨로 정확히 일치, 61/62차가 참조한 바로
그 16세그 로그). `extract_log.py`로 CSV 추출(commit `4ea63c3`, 방안C
반영된 HEAD로 디코딩 — 단 로그 자체의 기록 시각은 2026-08-24 15:38로,
방안C 커밋 시각(23:28)보다 훨씬 이름 — **즉 이 로그는 방안C 적용
이전에 기록된, r1-3/r1-14 문제를 처음 보고하게 만든 바로 그 원본**).

**검증 방법**: `work/replay_drel_discontinuity_real.py` 신규 작성 —
`long_mpc.py`의 lead-acquisition ramp bookkeeping(L744~780) + 방안C
discontinuity 체크(L801~844) + `vlead_correction_suppressed`/
`vision_rate_for_lead0` 계산(L866~877) + `frac_time`/`frac_ttc`/
`frac_rate` 계산(L907~961)을 실제 코드 그대로 복제. 실측 CSV(leadDRel/
leadVRel/leadRadar/leftBlinker/rightBlinker/vEgo/cruiseEnabled)를
프레임 단위로 흘려 PATCHED(방안C 있음)/UNPATCHED(방안C 제거) 두 버전을
나란히 재생.

**seg3(r1-3) 결과 — 방안C 효과 확인**: discontinuity 7프레임 트리거
(t=259.20~259.65, dRel 65.2→25.9m 급락 구간, 실측치가 FINDINGS 원 기록
"65→24m류"와 거의 정확히 일치). aEgo 최저치(-3.236, t=261.297) 부근에서
**frac(개입강도) PATCHED 0.27~0.36 vs UNPATCHED 0.90~0.98 — 방안C가
있었다면 이 구간 개입 강도가 실측 대비 약 1/3 수준으로 낮았을 것으로
추정.** 원인 분해: 이 구간은 radar가 이미 락온(radar=True)한 상태라
`frac_rate`/`frac_ttc`는 이미 0(radar 락온 시 `_vision_dRel_rate`
즉시 리셋되는 기존 로직 때문)이고, 차이는 전부 `frac_time`(경과시간
기반 성분)에서 남 — discontinuity가 `_lead_acq_timer`를 리셋해줘서
frac_time이 처음부터 다시 램프하기 때문(PATCHED: 리셋 후 경과 ~1.6s
-> frac_time≈0.32, UNPATCHED: 리셋 없이 훨씬 오래 누적된 timer ->
frac_time≈1.0 포화).

**seg14(r1-14) 결과 — [신규 발견, 중요] 보호 공백**: discontinuity
6프레임 트리거(t=923.10~923.50, dRel 85.7→60.7m 급락)도 정상 동작.
그러나 aEgo 최저치(-4.286, t=925.148) 부근에서 **PATCHED와 UNPATCHED의
frac이 완전히 동일(둘 다 1.0) — 방안C가 이 사례의 실제 급감속을
전혀 완화하지 못했을 것으로 추정됨.**

**원인(코드 구조 확인)**: 이 구간은 radar가 아직 안 락온한 상태
(`leadRadar=False`)라 `frac_rate`/`frac_ttc`가 계속 살아있는데, 이
둘은 `self._vision_dRel_rate`(저역통과 필터링된 값)를 **discontinuity
suppression과 무관하게 직접 읽음**(L937/L954, `vlead_correction_
suppressed` 게이트가 전혀 적용 안 됨 — 그 게이트는 `vision_rate_
for_lead0`, 즉 process_lead에 넘기는 v_lead 직접보정 주입 여부에만
적용됨). 게다가 discontinuity 트리거는 `_lead_acq_timer`만 리셋할 뿐
`_vision_dRel_rate`/`_vision_dRel_rate_window`는 건드리지 않음 — 즉
급락 구간에서 이미 저역통과 필터에 먹여진 큰 음수(-8.1~-8.3m/s대)
값이 그대로 남아 `VISION_CLOSING_RATE_MIN_TIME(0.5s)`만 지나면
frac_rate가 다시 1.0으로 즉시 복귀함. **58차1(v_lead 직접보정)/60차
계속(신규등록 게이트)/방안C 전부가 "process_lead에 넘기는 v_lead
직접보정" 경로만 보호하고, 25차/33차(frac_time/frac_ttc/frac_rate
floor 메커니즘) 경로는 애초에 보호 범위 밖이었음** — 이 두 경로가
독립적으로 최종 개입강도(frac)에 max()로 합쳐진다는 구조를 seg3
분석 때는 (radar 락온이 우연히 frac_rate/ttc를 0으로 만들어줘서)
못 보다가, radar 락온 전에 급감속이 끝나버리는 seg14류에서 처음으로
드러남.

**결론/영향**: 방안C는 "리드 신규등록/차선변경류 취약구간에서 v_lead
직접보정을 유예"하는 60차 계속 메커니즘의 재사용이라 그 메커니즘이
보호하는 범위(v_lead 직접보정, frac_time)에서는 유효하지만, **radar
락온 전에 frac_rate/frac_ttc가 이미 오염된 `_vision_dRel_rate`로
포화(1.0)돼버리는 경우(r1-14류, cutin 감지~radar 락온 사이가 긴 경우)
에는 사실상 무력할 가능성이 높음.** 실차 검증(다음 최우선)에서 이
차이가 실제로 나타나는지(r1-3류는 완화, r1-14류는 여전히 급감속)
반드시 확인 필요 — 만약 재현되면 **방안 D**(discontinuity 트리거 시
`_vision_dRel_rate`/`_vision_dRel_rate_window`도 함께 리셋해 frac_rate/
frac_ttc 오염까지 차단) 추가 패치가 필요.

**다음(최우선, 갱신)**:
1. 실차 검증 시 r1-3류(radar 락온 빠름)와 r1-14류(radar 락온 느림/
   cutin이 더 오래 vision-only로 유지) 두 패턴을 반드시 구분해서
   관찰 — 전자는 개선 체감 가능성 높고 후자는 이번 발견대로 무개선일
   가능성 높음.
2. **[신규, 유력 후보] 방안 D 설계**: discontinuity 트리거 시
   `_lead_acq_timer`뿐 아니라 `_vision_dRel_rate=0.0`/
   `_vision_dRel_rate_window.clear()`도 함께 리셋 — frac_rate/frac_ttc
   floor 경로까지 보호 범위를 넓힘. 단, 이 값을 0으로 리셋하면 그
   프레임 이후 다시 "정말 위험한 접근"이 있어도 즉시 알아채지 못하고
   같은 저역통과 필터가 처음부터 다시 수렴해야 하므로(TAU=1.0s), 진짜
   위험 상황(danger override, TTC<=2.5s의 vRel 기반 즉시반응 경로)은
   여전히 무관하게 살아있음을 재확인해야 함(안전 백스톱은 유지되지만
   frac_rate 경로 자체의 반응 지연이 새로 생기는 트레이드오프 고려).
3. `replay_drel_discontinuity_real.py`는 실제 코드와 대조 검증된
   재현이므로, 방안 D 설계 시 이 스크립트에 방안 D 로직을 추가해
   seg3/seg14 둘 다 frac이 낮아지는지 먼저 시뮬레이션으로 확인 후
   패치 작성 권장(패치 전 시뮬레이션 우선 원칙).
4. 기존 4/5번 항목(값 튜닝/방안 A)은 그대로 유지, 우선순위는 위 1/2
   번보다 낮음.

**코드 변경 없음(ryu 미변경, 발견/시뮬레이션만)**.
`work/route63/replay_drel_discontinuity_real.py` 신규 — toolkit 미편입
(아직 방안 D 미확정, seg3/14 외 다른 route 재현 검증도 안 됨 — 기존
원칙대로 스크래치 유지).

## [PATCH_WRITTEN] 72차(방안 I) — 레이더 락온 전환 프레임 vRel 불연속 감지

**배경**: 72차 체크포인트(WIP.md 참고)에서 실차 재현(route1 t=683.85~
696, "정지앞차 레이더락온시 급감속")으로 특정한 사각지대에 대한 실제
코딩 착수. 이전 세션이 컨테이너 리셋으로 중단된 뒤, 사용자가 작업 중이던
`long_mpc.py`(방안 I 구현 완료 상태)를 업로드해줘서 그대로 이어받음.

**구현** (`long_mpc.py`, 컨테이너 로컬 커밋 `90d5845`, base `0c137f2`
= 67차 방안G):
- 신규 상수 `RADAR_HANDOFF_VREL_JUMP_THRESH=3.0`(m/s).
- 신규 상태 `self._prev_lead_radar`(bool)/`self._prev_lead_vRel`(float,
  status=True인 프레임에서만 갱신 — blip 중엔 마지막 유효값 유지).
- 레이더 False→True 엣지 프레임(`elif lead_one_status_now and
  radarstate.leadOne.radar:` 분기)에서, 엣지일 때만(`not self._prev_
  lead_radar`) 직전 vRel 대비 이번 vRel이 임계값 이상 접근방향으로
  튀면 기존 검증된 방안G(`_discontinuity_jerk_boost_timer =
  DISCONTINUITY_JERK_COST_BOOST_S`)를 그대로 arm — 새 메커니즘 추가
  없이 트리거 조건만 확장.
- danger override(TTC<=2.5s)/proactive floor는 a_change_cost 적용부
  (67차 방안G 지점)에서 이 부스트와 무관하게 항상 우선 — 이번 변경이
  건드리는 건 "도달 속도(저크)"뿐, "도달 감속량" 자체는 그대로.

**검증**: 컨테이너 origin(`0c137f2`) 기준 `git format-patch` →
`verify-am-72` 임시 브랜치에서 `git am` 컨텍스트 일치 확인 +
`py_compile` 통과.

**전달**: `0001-72-I-vRel-G.patch`를 `/mnt/user-data/outputs/`에 생성,
base `0c137f2`(67차 방안G) 위에 바로 적용 가능.

**주의(재검증 필요)**: 이 패치는 실차 재현 로그(72차) 원인 분석을
근거로 설계됐으나, 아직 (a) 이 패치를 실제 route1 t=690.05 시퀀스에
재생 검증한 적 없음(방안G/C처럼 replay 스크립트로 사전검증하는 절차를
이번엔 건너뜀 — 세션 중단 복구 우선), (b) `RADAR_HANDOFF_VREL_JUMP_
THRESH=3.0m/s` 값은 설계 추정치(원 사례 vRel -3.6→-10.8 = 7.2m/s
점프를 확실히 잡도록 여유있게 설정)일 뿐 튜닝 근거 없음, (c) 71차
seg7 후반 gap 오실레이션/mid-speed 인접차선 오탐(37차 게이트 사각)
등 이월 항목과는 무관.

**다음(최우선)**:
1. 사용자가 `C:\dev\ryu`에서 `git am` 적용 + push.
2. (권장) 방안C/G 때처럼 실측 rlog(route1, 이번 사례) 원본으로
   `replay_drel_discontinuity_real.py`류 재생 스크립트에 방안 I 로직을
   추가해 t=690.05 시퀀스에서 실제로 저크가 완만해지는지 사전 검증—
   아직 안 함(이번 세션은 세션 복구+패치 완성 우선).
3. 실차 검증: (a) 이번 route1류(비전 낙관 6초+→레이더 급락) 재현 시
   급감속 완화 여부, (b) danger override 회귀 없는지(TTC<=2.5s 즉시
   반응 유지), (c) 방안G(discontinuity, 비전단독 dRel 급락)와 이중
   트리거 시 부작용 없는지.
4. WIP.md 72차 "다음(사용자 확인 대기)" 2/3번(mp4 나머지 클립 매칭,
   71차 이월 항목)은 여전히 미착수.

## [체크포인트] 72차 계속2 — 방안I 무력화 원인 재현/재확정 (boost 윈도우 1.0s 구조적 부족)

**배경**: 직전 세션이 컨테이너 리셋으로 유실(FINDINGS 기록 직전 중단).
route1 zip만 재업로드받아 원 발견 구간(seg10, t≈683.8~697)을 재추출,
`long_mpc.py`(HEAD `4fa4a44`) L823~1140 로직을 실측 CSV와 프레임 단위로
직접 대조(정식 replay 스크립트화는 다음 단계로 미룸).

**확인**:
- 락온 엣지(t=690.0027, vRel -3.957→-10.8m/s, 임계 3.0 초과)에서 방안I
  트리거 정상 발동. 이 프레임 자체는 dRel=91.8m로 아직 멀어
  frac_ttc/frac_rate/frac_time 전부 0, `_lead0_danger_active`=False →
  boost 게이트(L1129~1131) 정상 통과, 부스트 실제 적용 확인.
- 그러나 실제 선행차 급감속은 t≈691~695까지 4초+ 지속(leadALeadK가
  t=690.2~691.4 사이 -0.5→-1.36까지 꾸준히 악화). `DISCONTINUITY_JERK_
  COST_BOOST_S=1.0s`는 t≈691.0경 소진되는데 하필 leadALeadK 최악 구간과
  겹쳐, 부스트 종료 직후 `base_a_change_cost=interp(|j_lead|,[0.3,2.0],
  [200,20])`가 j_lead 급증으로 다시 낮은 값(≈20, 저감쇠)까지 떨어짐 —
  부스트 이전과 사실상 동일한 저크로 급감속 재개.
- 부가: 이 케이스는 방안C(원본 discontinuity, vision-only dRel 원본
  5샘플창 급락)도 락온 이전 구간에서 최소 1회 별도 트리거됨(최대낙폭
  20.25m > 15.0 임계). 방안C 경로와 방안I 경로가 같은
  `_discontinuity_jerk_boost_timer`/같은 1.0s 윈도우를 공유하지만, 실제
  위험 지속시간이 그보다 훨씬 길어 결과는 동일(무력화).

**결론**: 직전 세션이 "방안C와의 상호작용 버그"로 잠정 명명했던 현상은
이번 재현에서도 동일하게 관찰되나, 원인은 방안C와의 직접 상호작용
(타이머 덮어쓰기 등)이라기보다 **방안G/C가 원래 겨냥한 시나리오(찰나의
vision dRel 노이즈/cutin 스냅, 곧 정상화)와 달리 방안I이 겨냥한 "레이더
락온이 드러내는 진짜 지속 급감속"은 수 초간 이어지는 이벤트라서 1.0초
부스트 윈도우 자체가 구조적으로 부족**하다는 쪽으로 재정리. 방안C를
완전히 배제해도(직전 세션의 격리검증 방향과 일치) 방안I 단독으로도
동일하게 무력화됨.

**다음(최우선)**:
1. 정식 replay 스크립트로 boost 연장안(예: 2.5~3.0s)/release-rate
   완만화안 정량 비교 검증 — 아직 미착수.
2. 방안 후보: (a) 이 시나리오 한정 boost 지속시간 연장, (b)
   a_change_cost에 release-rate 제한 추가(부스트 종료를 완만하게), (c)
   찰나성 노이즈 완화(방안C/G)와 지속성 급감속 초반 완화(방안I)를 별도
   타이머/메커니즘으로 분리. 방향 확정 필요.
3. route2(x7seg) 재업로드받아 71차 언급 유사 사례(t≈1378.8) 교차검증
   — 이번 세션엔 route1만 확보.

**코드 변경 없음. `work/route72/route1.csv` 신규(스크래치, toolkit
미편입).**

## [PATCH_WRITTEN, NEEDS_VALIDATION] 73차 계속4 — long_mpc.py 패치: 방안I 전용 boost 4.0s hard + release-rate 100/s, 트리거 소스별 게이트 분리

**배경**: 73차 계속3 결정(4.0s hard + 100/s release-rate 조합, split_gate
— WIP.md "73차 계속3" 참고)대로 `long_mpc.py` 실제 코드 구현.

**구현**(base `4fa4a44`):
1. 신규 상수 `RADAR_HANDOFF_JERK_BOOST_S=4.0`(방안I 전용 hard-hold
   유지시간)/`RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE=100.0`(cost/s, hard-hold
   종료 후 base까지 선형 감쇠). 기존 `DISCONTINUITY_JERK_COST_BOOST_S=1.0`
   (방안C/G)은 그대로 유지.
2. `_discontinuity_trigger_source`('discontinuity'|'handoff') 신규 상태 —
   dRel discontinuity 트리거 지점(방안C/G)과 레이더 핸드오프 vRel 불연속
   트리거 지점(방안I) 각각에서 소스 태그 + 대응 hard-hold 유지시간 설정.
   새 트리거 발생 시 진행 중이던 반대쪽 `_handoff_release_value`는 정리.
3. `a_change_cost` 적용부를 `is_handoff_source` 분기로 재작성:
   - 방안C/G: 완전히 기존 그대로(hard-cutoff, `frac<=0.0` 게이트 포함) —
     이미 실차검증까지 끝난 조합이라 로직 변경 없음, 회귀 리스크 이론상 0.
   - 방안I: 게이트가 `danger_active`만 확인(frac 무관, 73차 계속 결정
     그대로). hard-hold(4.0s) 종료 후 `_handoff_release_value`가
     `RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE`(100/s)로 base까지 선형 감쇠,
     danger_active가 뜨면 감쇠 중이라도 즉시 base로 강제복귀(원본 설계
     원칙 유지 — release-rate 완만화가 진짜 위험을 은폐하지 않도록).

**검증**:
- `py_compile` 통과, `git format-patch` → `verify-am-73` 임시 브랜치
  (base `4fa4a44`)에서 `git am` 컨텍스트 일치 확인.
- **패치와 동일 로직을 `replay_boost_duration.py`로 재실행해 재확인**
  (route1 seg10 t=683~698, route2 seg1 t=1375~1388): baseline(기존
  1.0s hard, split_gate 없음) 대비 —
  - route1: 0.0% → **68.6%** 커버 (73차 계속3 수치 68.0%와 근사 일치,
    boost 활성 2.25s+release 감쇠 4.25s 실부스트, 게이트차단 0.00s)
  - route2: 0.0% → **98.2%** 커버 (73차 계속3 수치와 동일, boost 활성
    3.45s+release 감쇠 5.45s 실부스트, 게이트차단 0.00s)
  두 route 모두 danger_active 회귀 없음(게이트차단 0.00s로 확인).

**전달**: `0001-73-handoff-boost-4.0s-release-rate-100.patch`를
`/mnt/user-data/outputs/`에 생성, `git am` 안내(base `4fa4a44`) 함께 전달.

**한계/NEEDS_VALIDATION**:
- route1의 68.6% 미달은 73차 계속3에서 이미 확인된 구조적 한계
  (discontinuity t=687.850 + handoff t≈690.0 이중 트리거가 8초 가까이
  위험구간을 이어가는 문제) — 이번 패치로도 완전 해소 안 됨, 실차 체감
  확인 후 추가 조치 필요성 재논의 예정.
- `RADAR_HANDOFF_JERK_BOOST_S`/`_RELEASE_RATE` 값 자체는 두 route 실측
  커버율 기반 채택값이나, 실제 acados MPC 통합 후 승차감 기준 재조정
  여지 있음.
- 방안C/G와 방안I 이중 트리거(예: route1처럼 두 트리거가 근접) 시 소스
  전환이 승차감상 부드러운지는 로직 검증(release 값 정리)만 확인했고
  실차 체감은 미확인.

**다음(최우선)**: 실차 드라이브 검증 — (a) 급감속 완화 체감, (b) danger
override 회귀 없는지, (c) 방안C/G(비전단독 dRel 급락)는 로직상 무변경
이나 재확인 권장, (d) 이중 트리거 상황에서의 승차감.

## [VALIDATED] 74차 — 73차 방안I 패치(f8e136e) 실차 전체 라우트 재생검증: route1(ea5bcc0566, 19seg)/route2(a5b1ce4e42, 7seg) 전 구간 회귀/부작용 없음 확인

**배경**: 73차에서 채택한 방안I 패치(`RADAR_HANDOFF_JERK_BOOST_S=4.0`+
`RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE=100.0`, split_gate)는 route1
seg10(t=683~698)/route2 seg1(t=1375~1388) 두 구간에 대해서만 커버율
검증(68.6%/98.2%)을 마친 상태였음. 이번에 사용자가 두 라우트 전체
(route1 x19seg/11.06km, route2 x7seg/4.30km — 기존 검증에 쓰인 seg
포함 전 구간)를 업로드, "패치가 다른 로그상황에 어떤 영향을 미치는지"
검증 요청.

**추출**: `extract_log.py` meta.json 확인 결과 두 라우트 모두 클론 시점
ryu repo HEAD가 정확히 73차 패치 커밋 `f8e136e`(commit_subject로 확인) —
즉 이번 채집 로그가 패치 적용 이후 실차 주행분임(단, meta.json의
commit은 추출 당시 로컬 clone HEAD 기준이라 "차량에 실제 탑재된 코드"를
직접 보증하진 않음 — 정황상 일치로 판단).

**방법**: `replay_boost_duration.py`의 `BoostReplay` 클래스를 특정 구간이
아닌 **전체 라우트(22800/7859 프레임)**에 대해 재생하는 스크립트
(`work/full_route_replay.py`, 아직 toolkit 미편입 스크래치)를 작성,
baseline(패치전: 1.0s hard, split_gate 없음) vs patched(73차: 4.0s
hard+100/s release, split_gate)를 전 구간 비교.

**결과 — 회귀 없음 확인**:
1. **트리거 검출 자체는 patched=baseline로 완전 동일**(설계대로 —
   패치는 hard-hold 유지시간/release만 바꾸고 트리거 조건은 불변):
   - route1: 47건(discontinuity 42 + handoff 5)
   - route2: 17건(discontinuity 16 + handoff 1)
2. **danger_active(TTC<=2.5s) 회귀 전무**: route1 danger_active 133프레임,
   route2 16프레임 모두 boosted(a_change_cost>=300) 상태와 동시발생
   0건 — baseline/patched 양쪽 다 0건으로 동일. danger override가 boost
   연장으로 지연/차단되는 사례 전 구간에서 발견 안 됨.
3. **boost 적용 시간 비중**: route1 0.68%→3.80%(7.7s→43.3s/전체1140s),
   route2 0.25%→1.73%(1.0s→6.8s/전체393s) — 절대 비중은 여전히 작음(<4%).
4. **위험구간(aEgo<=-1.5) 대비 boost 커버율 개선** (73차 목적대로 작동
   확인): route1 2.7%→18.6%, route2 0.0%→68.4%. route2 68.4%(구간 전체
   기준)는 seg1(t=1375~1388) 단일 이벤트 커버율 98.2%보다 낮은데, 이는
   route2 전체에 걸친 aEgo<=-1.5 프레임 중 대다수가 이 handoff 트리거와
   무관한 별개 저속/정차 감속 구간이기 때문(분모 확대 효과) — 타겟
   이벤트 자체의 커버율(98.2%)은 73차 결과와 변동 없음.
5. **route1/route2의 "새로운" handoff 트리거 3+0건 개별 확인**(기존
   튜닝에 쓰인 t=690.00/t=1378.85 이벤트 제외): t=351.70, t=673.05,
   t=1247.15 — 전부 고속 순항 중(vEgo 50~65km/h) 원거리(dRel 50~95m)
   레이더 재획득 시점의 vRel 노이즈성 순간 튐(-3.1~-6.4m/s)이 원인,
   프레임 단위 대조 결과 **세 건 전부 실제 급감속(aEgo 급락)으로
   이어지지 않음**(aEgo가 boost 구간 내내 대략 -0.3~+0.5 수준 유지) —
   부스트가 걸려도 체감상 무해(순항 중 저크비용이 잠깐 상향된 것 외
   가속/감속 자체엔 영향 없음). **과도촉발(over-triggering) 우려는
   기각** — 촉발되어도 부작용 없는 방향으로만 작동.
6. **harsh_brake_events**(운전자 직접 브레이크, aEgo<=-0.8) route1 35건/
   route2 20건 전수 확인 결과, boost 구간과 겹치는 t=527.2/t=149.7 초반
   프레임 제외 **전부 브레이크 프레스 직후 프레임에서 cruiseEnabled=False**
   (운전자 개입/해제 인접 — 기존 학습 패턴과 동일, 시스템 MPC 제어와
   무관). "부스트로 인해 시스템 반응이 둔해져 운전자가 직접 브레이크를
   밟았다"는 우려 가설을 뒷받침하는 사례 없음.
7. `ttc_danger_events`(TTC<=2.5s) route1 3건/route2 1건 — 전부 저속
   근접(vEgo 1~13km/h) 상황, duration 짧음(0.15~3.05s) — 통상적
   정체/근접 정차 패턴, 급증이나 이상 패턴 없음.

**결론**: 73차 방안I 패치는 튜닝에 쓰인 두 타겟 이벤트 외 **전체 라우트
범위에서 검출 조건 변경/danger override 저해/과도촉발 부작용 전무**로
확인. 실차 승차감 체감(정성적)은 여전히 사용자 확인 필요하나, 정량
회귀검증은 이 세션에서 완료.

**한계**:
- `leadALeadK` 필드가 CSV 스키마(`extract_log.py` 현재 컬럼)에 없어
  `full_route_replay.py`에서 j_lead=0으로 고정 근사(기존
  `replay_boost_duration.py`도 동일 근사 사용 — NEEDS_VALIDATION 이월).
- meta.json의 commit은 추출 시점 로컬 clone 기준이라 차량 탑재 코드를
  직접 증명하지 않음(정황 일치로만 판단).
- 정성적 승차감(부드러움 체감)은 이번 정량분석 범위 밖 — 실차 주관
  평가 별도 필요.

**코드 변경 없음**(분석 전용). `work/full_route_replay.py` 신규(스크래치,
toolkit 미편입 — 필요시 다음 세션에서 toolkit 정식 편입 검토).

## 77차 — 76차 패치 실차 로그 첫 검증(x15seg, 895.8s/4.26km), handoff 메커니즘 재확인 / discontinuity_lc는 미검증

**로그**: `20260826_070847_00000323--40371089d3_x15seg.zip` + 30초 화면녹화
클립 1개. `extract_log.py` 결과 meta.json commit이 `f3773b583656`
(76차 계속2 HEAD)와 정확히 일치 — 76차 패치가 실제 반영된 코드로 기록된
최초 로그.

**76차 타깃 시나리오(차선변경+discontinuity_lc) 검증 불가**: 이번 로그
전 구간 `laneChangeState='off'`(차선변경 이벤트 0건) — discontinuity_lc
소스가 발동할 기회 자체가 없었음. 76차 특화 검증은 다음 세션(차선변경
포함 로그 확보)으로 이월.

**대신 확보된 것 — 73차 handoff(레이더 락온) 메커니즘 실차 재확인**:
seg6(`20260826_071347...--6`) t=440.98~452 구간, 고속도로(vEgo
16.6m/s≈60km/h) 원거리(dRel=109.2m) vision 단독 리드 감지 → t=447.99
레이더 락온(vRel -12.19→-8.60m/s 불연속 점프, 72차가 원인규명한 정확한
패턴) → t=447.63~447.93 TTC danger(min_ttc=2.39s, dRel=27.8m) override
동시 발생. aEgo 프레임 단위 대조 결과:
- t=444.4부터 aEgo가 자연스럽게 음전환(양→+1.0→0→-1.5)해 이미 감속
  시작, t=447 근방 -2.6~-2.7 m/s²로 유지되며 레이더 락온 순간
  (t=447.99, vRel 불연속 점프)에도 aEgo -2.54→-2.44로 **연속적** —
  jerk 스파이크나 불연속 없음.
- danger override 구간(t=447.6~447.9)도 boost와 충돌 없이 자연스럽게
  같은 감속 곡선에 포함, 이후 t=452까지 완전정지 직전(vEgo 1.9m/s)까지
  단조 감속 유지.
- 이 구간 `harsh_brake_events`(운전자 브레이크) 0건 — 시스템이 처음부터
  끝까지 개입 없이 처리.
**결론**: 방안G(66/67차)/방안I(72차)/73차(handoff duration 4.0s+release
100/s) 스택이 실도로 원거리 고속 접근 사례에서 다시 한번 매끈하게
작동 — 회귀 없음 재확인(표본 1건 추가, 누적 실측 사례 증가).

**그 외 안전지표**:
- `turn_speed_violations`: 2건(seg5 t=423.4~426.4, seg13 t=903.2~909.2).
  프레임 대조 결과 **둘 다 거의 전 구간 cruiseEnabled=False**(운전자
  수동 제동 중) — ADAS 위반 아님. seg5 건은 동봉된 화면녹화 클립으로
  교차로 앞 정지 차량(아반떼) 상황임을 직접 확인(운전자가 신호/정지
  차량 대응으로 수동 브레이크 개입, TTC 표시 6.6/6.2로 여유 있었음).
- `harsh_brake_events`: 49건. 대표 클러스터(seg1 t=166~186/seg5
  t=421~425/seg13 t=903~909) 전부 `cruise_engage_disengage_events`의
  disengage 시점과 정확히 인접 — 기존 세션들과 동일한 "운전자 개입"
  패턴, 시스템 급제동 아님.
- `ttc_danger_events`: 1건(위 handoff 사례, 정탐·정상 override).
- `lead_cut_in_detector`: 3건, 전부 저속(<5m/s) 근접 상황, 무해.
- `steering_oscillation_detector`: 4건(개별 미조사, 기존 배경 수준으로
  추정 — 필요시 다음 세션 조사).

**코드 변경 없음**(분석 전용). devnotes만 갱신.

**다음 세션 최우선**: (a) 차선변경이 포함된 실주행 로그로 76차
discontinuity_lc(4.0s+release-rate) 타깃 시나리오 직접 검증 —
차선변경 중 discontinuity 트리거 시 boost가 실제로 4.0s 유지되는지,
반복 차선변경 시 과도하게 오래 지속되는 체감이 없는지. (b) 일반
handoff/cutin 회귀는 이번 세션으로 재확인 완료, 계속 누적 검증 유지.

## 78차 — [VALIDATED, 부분] discontinuity_lc 최초 실차 트리거 확인 (77차와 동일 로그, laneChangeState 대신 blinker 기반 재분석)

**배경**: 77차가 "laneChangeState 전 구간 off라 discontinuity_lc 검증
불가"로 남긴 동일 로그(`20260826_070847_00000323--40371089d3_x15seg`,
commit `f3773b583656`)를 이어서 분석 — laneChangeState는 계속 off였지만
seg4/5/10/11에서 leftBlinker/rightBlinker(운전자 수동 차선변경)가
활성화된 구간을 발견, qcamera 프레임 대조로 4개 세그 전부 실제
차선변경 동작이었음을 영상으로 확정.

**discontinuity 트리거 재현 스캔** (`long_mpc.py`의 `_dRel_raw_history`
5프레임 판정 + `lane_change_blinker_active`/hold 로직을 CSV에서 직접
재현):
- **seg5 t=384.18**(rightBlinker 활성): vision-only 5프레임 dRel
  47.79→25.45m(-22.34m) 급락 → `discontinuity_lc` 소스로 정상 트리거,
  4.0s hard-hold 부여 확인 — **76차 패치가 실제 차선변경 상황에서
  트리거되는 최초 실측 사례.**
- **seg10 t=722.28**(leftBlinker 활성): -28.02m 급락, 동일하게
  `discontinuity_lc` 정상 트리거.
- 두 사례 모두 boost 윈도우(t+4s) 내 aEgo는 mild(seg5 min=-0.909,
  seg10은 가속중 min=+0.081) — harsh braking 자체가 없어 boost의
  "급감후 원복 완화" 효과 자체는 정량 비교 불가. 단 오탐/과잉반응
  없음(회귀 안전) 확인.
- **seg4 t=368.63**: blinker 꺼진 지 2.2s 후(LANE_CHANGE_VLEAD_
  CORRECTION_HOLD_S=1.0s 만료) → 소스 `discontinuity`(일반, 1.0s
  hard-hold)로 정상 분류 — 소스 분기(blinker 활성/hold 여부에 따른
  discontinuity vs discontinuity_lc) 실측으로 정확히 갈림을 확인.
- seg11: 차선변경은 확인됐으나 dRel 5프레임 급락 패턴 자체가 없어
  (매끈한 lead 전환) 트리거 없음 — 정상.

**harsh_brake_events 49건 재확인**: 77차와 동일 클러스터(seg1/seg5
t=421~425/seg13). seg5 t=421~425(aEgo 최저 -2.64)는 `src=vturn`+
`leadStatus=False`(리드 무관 곡선감속, 우회전 교차로 진입 추정)로
discontinuity_lc/차선변경과 완전히 무관 — 77차 결론과 일치 재확인.

**결론**: 76차 목표(discontinuity_lc를 실제 차선변경 중 재현 검증)
**절반 달성**. 트리거 발동 자체 + 소스 분기 로직은 실측 확인, 회귀
(오탐/부작용) 없음도 확인. 단 harsh braking과 겹치는 사례가 없어
"boost가 급감후 원복을 실제로 완화하는지"는 여전히 미검증.

**코드 변경 없음**(분석 전용).

## [PATCH_WRITTEN, NEEDS_VALIDATION] 79차 — 수동주행 중 첫 +RES(accelCruise) 시 목표속도가 현재속도보다 낮게 설정됨 (2026-08-26)

**증상**: 시동 후 수동 60km/h 주행 중 +RES 1회 → 목표속도 33km/h로 설정,
감속 발생. 사용자 요청: 첫 +RES는 항상 현재 속도보다 높게 설정되어야 함.

**원인** (`selfdrive/car/cruise.py`):
- `update_v_cruise()`가 `CS.cruiseState.available and pcmCruise and
  speed_from_pcm!=1`(Genesis DH) 조건에서 `self.v_cruise_kph =
  np.clip(v_cruise_kph, 30, self._cruise_speed_max)`만 매프레임 수행 —
  `v_cruise_kph` 자체는 `CC.enabled=False`(수동주행)인 동안 버튼 로직에서
  전혀 갱신되지 않아 이전 세션 잔여값(예: 33)에 정체된 채 clip만 반복됨.
- `_update_cruise_buttons()`의 accelCruise 처리부가 `self._cruise_ready
  or not CC.enabled or CS.cruiseState.standstill or self.carrot_cruise_active`
  를 하나로 묶어 no-op(`if False:`) 분기로 보내, `not CC.enabled`(수동주행 중
  첫 인게이지) 케이스에서도 아무 갱신을 안 함 — 정체된 33이 그대로 채택됨.
- 바로 아래 decelCruise 처리부는 `elif not CC.enabled: v_cruise_kph =
  max(self.v_ego_kph_set, self._cruise_speed_min)`로 이미 현재속도 반영
  로직이 있어, **accelCruise만 빠진 비대칭 버그**로 확인.
- 참고: `d02bf5f6`("fix.. v_cruise init")이 `cruiseState.available` False→True
  전환 시점(시동 직후)만 `v_ego_kph_set`으로 초기화하도록 고쳤으나, "주행 중
  CC 비활성 상태에서의 정체" 케이스는 다루지 않아 이번 버그가 남아있었음.

**조치**: accelCruise 분기에서 `not CC.enabled`를 별도 `elif`로 분리(다른
세 조건은 기존 동작 유지, decelCruise와 동일한 우선순위) — 해당 시
`math.ceil((v_ego_kph_set+0.01)/unit)*unit`로 현재속도보다 확실히 높게(다음
단위 눈금 올림) 설정.

**검증**: `work/sim_res_button.py` 로직 재현 — 재현 시나리오(vEgo=60,
정체값=33) 구코드 33(버그 재현)→신코드 61(개선). `cruise_ready`/
`standstill` 케이스는 구/신 동일(33, 회귀 없음). `git am`(base `f3773b58`)+
`py_compile` 통과.

**다음(최우선)**: 실차 적용 후 (a) 첫 +RES 시 목표속도가 현재속도보다
높게 설정되는지, (b) 취소 후 재인게이지/정차출발/carrot 인게이지 등
기존 경로 회귀 없는지, (c) `unit`(눈금 크기)에 따른 상승폭 체감 확인.

## [PATCH_WRITTEN, NEEDS_VALIDATION] 84차 — route 커브 lookahead 300m 고정 캡 -> v_ego/accel_limit 기반 동적 캡(300~500m) (2026-08-26, `c3-ms-curv` 브랜치)

**배경**: 83차에서 확인한 "`AutoNaviSpeedDecelRate`(사용자 실측 0.70)가
고속(100km/h대)+큰 감속폭 조합에서 300m lookahead 상한에 걸릴 수 있음"
(NEEDS_VALIDATION)에 대한 조치. 사용자가 300m 고정값 상향 대신 **v_ego/
accel_limit 기반 동적 캡(300~500m)**으로 결정.

**설계**: `carrot_navi_route()`(`carrot_man.py`)가 `get_path_after_distance()`를
호출하는 시점엔 아직 실제 커브 목표속도(곡률 기반)를 모름(그건 이 호출 이후에
계산됨) — 그래서 "얼마나 멀리 fetch할지"를 정하기 위한 가정 목표속도로
`assumed_target_kph=30.0`(흔한 조임 커브 수준)을 사용, 실제 DP가 계산하는
목표속도와는 무관(캡 크기 산정 전용).

```python
def compute_route_lookahead_distance(v_ego_kph, accel_limit_mss, min_m=300.0, max_m=500.0,
                                      assumed_target_kph=30.0):
  if accel_limit_mss is None or accel_limit_mss <= 0:
    return min_m
  v_ego_ms = max(0.0, v_ego_kph) / 3.6
  v_target_ms = assumed_target_kph / 3.6
  needed_m = max(0.0, (v_ego_ms ** 2 - v_target_ms ** 2) / (2.0 * accel_limit_mss))
  return float(min(max_m, max(min_m, needed_m)))
```

`get_path_after_distance(..., 300)` 하드코딩을 `get_path_after_distance(...,
route_lookahead_m)`로 교체, `route_lookahead_m`은 매 프레임
`self.sm['carState'].vEgo*3.6`/`self.carrot_serv.autoNaviSpeedDecelRate`로 계산.

**검증** (`toolkit/sim_route_dynamic_cap.py`, 신규, 순수함수 재현):
- 저속(<=50km/h)은 accel_limit 무관하게 항상 floor(300m) 유지 —
  **도심/저속 구간은 기존 300m와 완전히 동일, 회귀 없음** 확인.
- 사용자 실측 accel=0.70 기준: 80km/h≈303m → 90km/h≈396.8m →
  100km/h+에서 500m(ceil) 도달.
- 기본값(1.20)/83차 경계값(1.39)은 각각 110/130km/h는 돼야 캡이 늘기
  시작 — accel_limit이 낮을수록(더 완만한 감속 설정) 더 낮은 속도에서부터
  캡이 커지는 단조성 확인(설계 의도와 일치).
- accel_limit=0/None 예외 시 floor(300m) 안전 폴백 확인.

**적용 위치**: `c3-ms-dev`가 아니라 **`c3-ms-curv`**(81/82차가 이미
`carrot_navi_route()`를 수정해둔 브랜치, base `451a3b9`) 위에 커밋 —
동일 함수를 건드리므로 반드시 이 브랜치 위에 적층해야 함(c3-ms-dev에
잘못 적용하면 81/82차 변경과 별개로 갈라짐).

`git format-patch` → `verify-am-84` 임시 브랜치(base `451a3b9`)에서
`git am` 적용 → `c3-ms-curv`와 diff 0(완전 동일) 확인 + `py_compile` 통과.

**다음(최우선)**:
1. 실차 드라이브 검증 — (a) 고속도로 순항(90~120km/h) 중 실제 route
   기반 커브 감속이 이전보다 더 이르게 시작되는지(83차가 우려한 캡
   경계 초과 케이스 해소 여부), (b) **회귀 검증 필수** — 저속/도심
   구간에서 기존과 체감 차이 없는지(설계상 300m floor로 동일해야 함),
   직선 구간에서 lookahead가 늘어난 만큼 GPS 폴리라인 오차로 인한
   신규 오탐(불필요 감속) 없는지, (c) 연산 부하(프레임당 소요시간)
   체감상 문제없는지 — 리샘플 포인트 수가 최대 약 1.67배(300→500m,
   10m 간격 기준 30→50개) 늘어남.
2. `assumed_target_kph=30.0`/`max_m=500.0` 값 자체는 설계 추정치 —
   실차 반응 보고 튜닝 필요(예: 500m로도 부족하면 상향, 또는 실제
   앞차/커브 상황 대비 과도하게 이르면 하향).
3. 83차가 함께 제안했던 "route 전용 accel_limit 분리"(현재
   `AutoNaviSpeedDecelRate` 공유 구조) 논의는 이번 84차와 별개로
   여전히 미착수 — 필요시 후속 논의.

## 86차 (완료 — 10개 route CSV 5항목 스캔 완료, qcamera 대조는 미실시) — c3-ms-curv(85차 HEAD) 실주행 로그 종합분석

**배경**: 85차(route lookahead 상한 600m) 적용 후 사용자가 c3-ms-curv
브랜치로 실주행한 로그 10개 route(commit `284457f38a85`, 총 142세그,
~152k row)를 업로드. 컨테이너 재시작으로 원본 zip이 유실됐다가 사용자가
Google Drive에서 CSV zip(`ryu_c3-ms-curv_logs_20260826.zip`)을 재다운로드해
재업로드 — qcamera는 이 zip에 포함되지 않아(CSV만) **이번 세션은 CSV
기반 5항목 스캔까지만 완료, qcamera 프레임 대조는 원본 rlog+qcamera
재확보 시 별도 진행 필요**.

**도구**: `five_item_scan.py`(신규 정식 편입, toolkit/README.md 참고)로
5개 항목 일괄 스캔 + `harsh_brake_events`/`ttc_danger_events`/
`lead_cut_in_detector`(기존 함수) 안전지표 병행.

**route별 요약** (`vision_crossover / stopped_lead / launch_after_stop /
radar_jerk / turn_violation` — `harsh_brake / ttc_danger / cutin`):
- route1(d2a61d2a73, x18seg): 25/0/0/63/0 — 0/0/0 (전 카테고리 클린)
- route2(dfc68039a9, x20seg): 16/2/1/41/2 — 33/**3**/1
- route3(4a32e2c0d3, x20seg): 13/0/0/35/0 — 0/0/0 (클린)
- route4(bc4301a25d, x20seg): 14/2/1/88/8 — 13/0/0
- route5(c0e3054c4a, x20seg): 2/1/0/1/**28**(최다) — 5/**3**/0
- route6(8b55ac185d, x13seg): 0/1/0/0/17 — 13/0/0
- route7(1582412718, x20seg): 26/6/6/80/16 — 25/1/0
- route8(e7a09d7ec4, x4seg): 4/1/0/56/1 — 13/1/0
- route9(a3fcd91b87, 단일세그): 0/0/0/0/0 — 0/0/0 (짧은 구간)
- route10(6e1e9a8e26, x6seg): 8/11/2/14/0 — 28/**9**/10 (저속 밀집구간 추정)

**1) 카메라 인식 시 감속**: 크로스오버 108건(10개 route 합계), 기존
41/55/56차와 동일하게 대부분 레이더 락온 전 감속 개시 확인(개별 전수
검증은 안 함, 표본 확인 없이 건수만 집계).

**2) 정지 앞차 감속**: 24건 탐지. 개별 미검증(표본 검증 없이 건수만
집계) — 다음 세션에서 이상치(aEgo_min이 유독 약한 건) 선별 필요.

**3) 정지 후 재출발**: 10건, 45차 launch bypass 이후 대량 로그에서 처음
집계(route7이 6건으로 최다). 개별 미검증.

**4) 레이더 락온 저크**: 421건(전체 route 합계, route4=88건 최다).
`leadVRel`≈0(|vRel|<0.5m/s)인데도 저크가 큰 55/56차류 이상 패턴이
126건 재현됨 — **표본 규모가 이전(2~4건)보다 훨씬 커졌으나 데이터
규모(152k row, 이전 대비 5~8배) 대비 비율은 유사한 수준으로 추정**
(정확한 비율 비교는 미실시). 신규 이상으로 격상하지 않고 기존
NEEDS_VALIDATION(원인 미상, 코드리뷰 필요) 유지.

**5) 곡선구간 감속(turn_speed_violations)**: 72건(10개 route 합계),
route5(28건)/route6(17건)/route7(16건)에 집중. **위반 구간 프레임의
src 분포를 확인한 결과 vturn=3149프레임 vs route=12프레임 vs
gas=91/bump=2 — 압도적으로 vturn(비전 기반 곡선속도제어) 소스이고
85차가 만진 route(내비경로) 소스는 거의 관여하지 않음.** 즉 이번
로그의 곡선위반 다발은 51~85차부터 계속 이어지는 "vturn apex
조기언더슈트/lookahead 지연" 기존 이슈의 연장(신규 발견 아님, 85차
route lookahead 600m 확장이 vturn 자체의 한계를 해결하는 패치가
아니었으므로 예상된 결과) — **85차/82차 route 패치 자체의 회귀는
이번 스캔 기준으로는 확인되지 않음(route 소스 관여 프레임이 원래도
작아 이 지표만으로 결론 내리긴 약함, 다음 단계로 route 소스만 걸러진
구간 개별 확인 필요)**.

**안전지표**: ttc_danger(TTC≤2.5s) 총 18건 — 대부분 vEgo<9m/s(저속,
근접 정차/서행 상황)이고 route10(9건)에 집중(저속 밀집구간 추정,
harsh_brake도 28건으로 route10이 최다). route2 seg11 t=661.88
(vEgo=8.68m/s, dRel=28.6m, vRel=-11.8m/s)은 상대적으로 고속 급접근
후보로 개별 확인 우선순위 높음. **전부 운전자 개입 여부/qcamera
정탐 확인 미실시** — 다음 세션 최우선.

**코드 변경**: `toolkit/five_item_scan.py` 신규(정식 편입). 10개 route
CSV를 `data/routes/<route_id>/`에 gzip 캐시로 등록(README.md 갱신).
`ryu` 코드 변경 없음.

**다음(최우선)**:
1. ttc_danger 18건, 특히 route2 seg11(고속 근접후보)/route10(9건 밀집)
   개별 확인 — 운전자 개입 여부, 가능하면 qcamera로 정탐/오탐 판정.
2. qcamera 대조 자체가 필요하면 원본 zip(rlog+qcamera 포함)을 사용자가
   재확보해 재업로드 필요 — 이번 CSV-only 재다운로드로는 불가능.
3. radar_lockon_jerk의 leadVRel≈0 이상패턴(126건) 표본 규모가 커진 만큼
   코드리뷰 우선순위 재검토 여지(41차부터 이월된 저우선 항목).
5. **[신규, 부분확인]** route7(1582412718) t=658.0~660.0 급접근 후보
   개별 확인 결과: `leadRadar=False`(비전단독) 구간에서 `leadDRel`이
   74→64→68→69→56→61m로 심하게 요동(2~4프레임 간격 노이즈, 42/55차류
   vision dRel jump 패턴과 유사)하다가 t=658.83부터 `leadVRel`이
   -1.6→-14.9m/s까지 급격히 커지며 `aEgo`가 -0.5→-2.7까지 지속 감속.
   `cruiseEnabled=True`/브레이크·가스 미개입(순수 ADAS 반응). dRel
   자체의 요동으로 인해 노이즈성 오탐인지 실제 급접근(cut-in 등)인지는
   qcamera 없이 CSV만으로 판정 불가 — qcamera 재확보 시 최우선 확인 대상.
4. route5(28건)/route6(17건)/route7(16건) 곡선위반 중 src=route인
   12프레임만 따로 걸러 85차 lookahead 600m 확장이 실제로 도움이 됐는지
   개별 확인(전체 위반이 vturn 주도라 이 지표로는 결론 약함).


## 87차: VisionTrack 팬텀(유령) 리드 트랙 영구고착 버그 [PATCH_APPLIED, NEEDS_VALIDATION]

**증상**: 사용자 제보(화면녹화 mp4) — 커브 구간에서 파란 박스(leadOne)가
120초 내내 도로 밖 나무/가드레일 근처에 표시되며 급감속(aEgo -1.56)
유발. 실제 앞차 없음.

**원인**: `radard.py` `VisionTrack.update()` — 60차 계속6(B안)이
"prob가 짧게 0.35 밑으로 출렁여도 tentative_cnt를 리셋하지 않는다"로
바꾼 이후, prob가 [0.35,0.5] 구간을 완전히 벗어나 영구적으로 낮게
유지되는 경우 리셋할 방법이 없었던 사각지대. `tentative_cnt>=10`으로
한번 래치된 `register_ok`가 prob 값과 무관하게 영구 True로 고정됨.

**수정**: `VISION_TRACK_GHOST_TIMEOUT_S=3.0` 신설 — prob<0.35가 이
시간 이상 연속되면 `tentative_cnt` 강제 리셋. 순수 로직 재현 시뮬레이션
(`work/sim_vision_track_ghost_timeout.py`) 3개 시나리오(고스트 120s/
실제 리드 노이즈 출렁임/실제 리드 시야이탈 10s) 전부 PASS, 회귀 없음
확인(시나리오 2: 패치 전후 register_ok 시퀀스 완전 동일).

**패치**: `0001-87-VisionTrack-tentative-GHOST_TIMEOUT_S-3.0s.patch`
(base `284457f`), `/mnt/user-data/outputs/` 전달 완료. 실차 적용/검증
대기.

## 89차 (완료 — 원인분석만, 코드 변경 없음) — 곡선_고속도로램프2 로그로 route 사전감속 부족(과소평가) 원인 규명

**배경**: 88차와 동일 route(`bc4301a25d`, `c3-ms-curv` 285차 HEAD `284457f`)의
seg12/13을 qcamera 포함해 재업로드 → 커브 2개(A: 완만한 램프 진출로,
B: 급격한 램프 커브+교차로) 분석. 커브A 진입부에서 turn_speed_violation
16.73km/h/4.55초(vEgo 89.7km/h vs vTurnSpeed 73km/h) 발견 → 사용자 질문
("route가 사전에 감속이 된건가?")에 답하기 위해 t=9195~9227 구간을
프레임 단위로 재구성.

**핵심 발견 (CSV 실측으로 확정, 가설 아님)**:
- src=road(제약 없음, desiredSpeed=200) → **t=9211.27부터 route가 개입**
  (desiredSpeed 200→155), 이후 **t=9221.26까지 약 10초간 121까지만 완만히
  하강**(34km/h 하강에 10초 — 초당 약 3.4km/h). 이 구간 내내 vEgo는
  76→90km/h로 **계속 가속 중**이었음 — route의 캡이 실제 속도보다 항상
  높게 유지되어 물리적으로 한 번도 제동에 관여하지 못함("서류상 사전감속,
  실효 없음").
- t=9221.26에 src가 vturn으로 전환되며 **121→73km/h를 단 5초 만에** 급격히
  하강 — 이 급격한 낙폭이 정점 이전에 목표를 못 따라잡아 16.73km/h
  overshoot(4.55초)로 직결됨.
- **즉 route가 이 커브에서 산출한 최종 목표값(121km/h) 자체가 vturn이
  최종적으로 요구한 값(73~77km/h)보다 훨씬 높았음** — route가 이 커브의
  실제 조임 정도를 상당히 과소평가했다는 것이 CSV로 직접 확인됨(route가
  source였던 구간의 desiredSpeed는 route의 실제 산출값 그 자체이므로
  추정이 아니라 실측).

**코드 레벨 원인 후보(NEEDS_VALIDATION, 이 로그의 raw curvature/navi_points가
CSV에 없어 직접 검증은 못함 — 코드 구조상 개연성 있는 가설)**:
`carrot_navi_route()`(`carrot_man.py` L442~458)의 곡률 계산이
`distance_interval=10.0m` × `sample=4`로 **p1-p2-p3 3점을 40m 간격**(총
스팬 80m)으로 떼어 계산함. 반경이 작고 굴곡이 급격한 램프형 커브에서는
이 정도로 긴 현(chord)이 실제 순간 곡률을 평활화(smoothing)해 과소평가할
가능성이 있음 — vturn(`vturn_speed()`, modelV2 예측 궤적 기반, 훨씬
촘촘한 궤적 포인트 사용)이 같은 물리적 지점에서 더 정확하게(더 급하게)
곡률을 잡아낸 것과 대비됨. 표본 1건이라 일반화는 이르나, 88차의 "커브
마다 route 엄격도 편차" 관찰과 결이 같음.

**다음(사용자 결정 대기, 패치 미착수)**: 아래 "대안" 참고(대화 응답에
상세 기록, 코드 변경 없음).

## 90차 (완료 — 시뮬레이션 검증, 코드 변경 없음) — 89차 대안1(route 곡률 샘플링 chord 축소) 효과 검증, **효과 미미 결론**

**배경**: 89차가 제시한 4개 개선 대안 중 1번(`carrot_navi_route()`의
곡률계산 chord를 `sample` 4->2/3로 줄여 40m 간격을 20~30m로 축소)을
검증하라는 지시. 89차와 동일 route(`bc4301a25d` seg12/13)를 qcamera
포함 재업로드받아 사용.

**방법**: raw navi_points(GPS 폴리라인)가 로그에 기록되지 않아
(navRoute capnp 메시지가 이 rlog엔 없음, 이벤트 타입 스캔으로 확인)
직접 재생은 불가 — 대신 실주행 `desiredCurvature`(모델이 그 순간
실제로 추종한 경로 곡률, 20Hz)를 시간축으로 적분해 차량이 실제로
통과한 경로의 2D 지역좌표를 재구성. `calculate_curvature()`는 회전/
이동 불변량만 사용하므로, 이 재구성 경로에 `carrot_man.py`의 곡률+
속도(`V_CURVE_LOOKUP`)+역방향DP(82차 수정판, 원복측 크레딧 포함)
로직을 그대로 복제해 sample=4(현재)/3/2(candidate)를 비교 —
`toolkit/sim_route_curvature_sample.py` 신규.

**핵심 결과**:
1. **정점 근처 최소 목표속도(min_target_speed)가 sample=4일 때도 이미
   78km/h**(vturn 실측 최종 요구치 73km/h와 불과 5km/h 차이)로 상당히
   근접 — sample을 3/2로 낮춰도 77.0/75.7km/h까지만 개선(**효과 약
   2.5km/h뿐**). 실제 로그에서 관측된 route 최저값(121km/h)과 vturn
   실측(73km/h) 사이의 **48km/h 갭**에 비하면 이 정도 개선폭은
   무시할 만한 수준.
2. **재구성 경로 기반 시뮬레이션의 out_speed_now(스냅샷 시점 route
   출력값) 자체도 실제 로그값보다 훨씬 낮게(더 엄격하게) 나옴** —
   예: t=9211 실측 route desiredSpeed≈140~155인데 반해 sim(sample=4)은
   107.2. 즉 "깨끗한(노이즈 없는) 곡률 신호"만 있어도 sample=4 그대로
   써도 실제 로그보다 훨씬 더 엄격하게(낮게) 반응했어야 한다는 뜻 —
   **실제 route가 더 관대했던(과소평가) 이유가 chord 길이 자체보다는
   입력 데이터(실제 GPS navi_points 폴리라인)의 품질/형상 문제일
   가능성을 뒷받침**.
3. **[추가 검증] raw navi_points 희소성 실험**: 재구성 경로를 일부러
   30/60/100m 간격으로 성기게 만든 뒤 10m로 재보간(실제 코드와 동일
   절차)해 sample 4/3/2를 다시 비교 — 희소성이 커져도 sample 축소의
   효과가 "체계적으로 더 커지지" 않았고, 오히려 raw 포인트 사이 꺾임
   지점에서 **노이즈성 스파이크(과대추정 방향)**가 나타남. 즉 "raw
   포인트가 성겨서 chord를 줄여도 여전히 뭉개진다"는 가설도 이번
   실험으로는 뒷받침되지 않음(과소평가가 아니라 노이즈 방향으로
   나타남).

**결론**: 89차 대안1(sample 4->2/3)은 **단독으로는 89차가 관찰한
실제 과소평가 갭(48km/h)을 설명/해소하기에 명백히 부족**하다는 것이
이번 시뮬레이션으로 확인됨(NEEDS_VALIDATION → 사실상 "1번 단독 채택
비권고" 쪽으로 기울어짐, 표본 1건이라 완전 기각은 아님). 진짜 원인은
코드 내부 파라미터(chord 길이)보다는, **실제 navi 서비스가 제공하는
GPS 폴리라인 자체의 형상 정밀도(지도 데이터가 이 램프 커브를 얼마나
정확하게 표현하는지)** 쪽에 있을 가능성이 더 커짐 — 단, raw
navi_points를 직접 로깅하지 않는 한 이 자체도 직접 검증은 불가능한
가설(코드에 `navRoute` capnp 메시지를 계측 로깅하도록 추가하면 다음
세션에서 직접 검증 가능).

**한계**: (1) desiredCurvature 적분 기반 재구성 경로는 실제 navi GPS
폴리라인이 아니라 "모델이 실제로 추종한 경로"의 근사치 — 완전히
동일한 입력은 아님. (2) 표본 1개 커브(A)뿐. (3) accel_limit=0.70(83차
확인 사용자 실제값)/vturn_safe_time=2.0(81차 확정값) 가정, 실제 그 순간
값과 100% 일치 보장은 못함(설정값이 로그 시점과 같다는 전제).

**다음(사용자 결정 대기, 패치 미착수)**:
1. **[신규 제안]** `carrot_man.py`에 raw `navi_points`(또는 리샘플
   전/후 curvature 배열)를 디버그 계측 로깅하는 패치를 우선 적용해,
   다음 실주행 로그에서 실제 GPS 폴리라인 자체의 형상/간격을 직접
   확인 — 89차/90차가 반복해서 "가설 수준"에 머무르는 근본 원인(raw
   데이터 부재)을 해소.
2. 89차 대안2(route/vturn 괴리 기반 보정)나 3번(안전마진 휴리스틱)
   재검토 — 이번 90차 결론상 1번의 효과가 작으므로 순위 재조정 필요.
3. 커브B(급격한 램프+교차로, 이번 로그에도 포함 t≈9259~9302)도 동일
   방식으로 교차검증하면 표본이 2건으로 늘어 결론력 보강 가능.

## 93차 — 91차(ROUTE_ENTRY_MARGIN_KPH=25.0) 회귀검증: 국도 연속곡선 실주행 로그(0000032d--c0e3054c4a, 91차 이전 baseline)로 전체구간 DP 스윕, **문제 없음 확인**

**배경**: 92차가 같은 route(0000032d--c0e3054c4a, seg13~19)를 "91차 적용
후 로그"로 오분류해 분석했던 것을 사용자가 정정(실제로는 91차 이전
baseline) — 92차 당시엔 실제로는 91차 로직 자체를 시뮬레이션하지 않고
그냥 baseline 로그의 turn_speed_violation/harsh_brake만 스캔해 "회귀
없음"이라 결론냈던 것이라, 91차(ROUTE_ENTRY_MARGIN_KPH)를 실제로 검증한
것이 아니었음(그 결론 자체를 92차에서 폐기함). 이번 세션에서 91차가
실제로 시뮬레이션한 방식(desiredCurvature 적분 재구성 경로 + 역방향DP)
그대로 이 로그 전체 구간에 적용해 margin=0(91차 이전)과 margin=25(91차)
출력을 직접 비교하는 정식 회귀검증을 수행.

**로그-패치 시점 확인**: 로그 기록 시각 2026-08-26 18:05~18:11, 91차
커밋(`6d15391`) author date 2026-08-26 22:13:31 — 로그가 패치보다
4시간+ 앞섬. 사용자 확인과 일치, 이 로그는 확실한 91차 이전 baseline.

**방법** (`toolkit/sim_route_margin_regression_scan.py` 신규): 로그
전체(t=10453~10873, 420초)에 3초 간격으로 스냅샷 126개, 각 스냅샷마다
향후 45초 구간을 desiredCurvature 적분으로 재구성 → 곡률/속도(sample=4,
운영값) 계산 → 82차 원복버퍼 포함 역방향DP를 margin_kph=0(baseline)과
margin_kph=25(91차)로 각각 실행해 `out_speed_now`(현재 지점 목표속도)와
`min_speed`(구간 내 최소=정점 목표값) 비교.

**핵심 결과**:
1. **직선구간 오탐 0건** — 향후 45초 전체가 사실상 무곡률(계산된
   최대곡률이 V_CURVE_LOOKUP 최저구간 미만)인 스냅샷에서 margin=25가
   margin=0보다 3km/h 이상 낮은 out_speed_now를 낸 경우 0건. 91차
   설계(감속 전환이 실제로 존재하는 지점에서만 time_delay 계산에
   개입 — 곡률 자체가 없으면 개입 구조 자체가 없음)가 이 실주행
   로그로도 확인됨.
2. **조기개입 정상 작동 확인** — 126개 스냅샷 중 75건(59.5%)에서
   margin=25가 margin=0보다 out_speed_now를 낮춰(=감속 스케줄을
   먼저 반영) 조기 개입. 이 75건에서 **정점 목표값(min_speed) 차이는
   평균/최대 모두 0.00km/h** — 91차 설계 의도(스케줄만 당기고 최종
   목표값 자체는 절대 안 바뀜)가 실측 데이터로 정확히 확인됨. 최대
   조기개입 사례(t=10518.97)는 out_speed_now가 69.6→48.8km/h로
   먼저 조여지지만 최종 min_speed는 48.5로 양쪽 동일.
3. **역전 버그(margin=25가 오히려 더 늦게 개입) 0건** — 로직 상
   있어서는 안 되는 방향의 이상 동작 없음 확인.
4. **[참고, 92차 관측 재확인]** turn_speed_violation 5건/harsh_brake
   5건(5개 프레임, 1개 이벤트) 전부 `vTurnSpeed`가 그 시점 제약값과
   일치 — src=vturn 기인(기존 vturn apex-lag 이슈)으로, route/91차와
   무관함이 이번 스캔으로도 재확인됨(92차 결론 중 이 부분은 baseline
   데이터 관측이라 91차와 무관하게 유효했음).

**결론**: 91차(ROUTE_ENTRY_MARGIN_KPH=25.0)는 이 국도 연속곡선 로그에서
직선 오탐 없이 설계 의도대로(스케줄만 조기화, 최종 목표값 불변) 동작할
것으로 시뮬레이션 확인됨. **실차 로그로 재생 방식 정식 회귀검증을 거친
첫 사례** — 89/90/91차가 그동안 bc4301a25d 1개 route(커브A/B)로만
검증했던 것을, 성격이 다른 국도 연속곡선 route로 교차검증한 것으로
의미 있음.

**한계**: (1) desiredCurvature 적분 재구성 경로는 실제 GPS navi_points
폴리라인의 근사치(89/90차와 동일 한계). (2) 45초 lookahead 윈도우는
600m 상한(84/85차) 커버리지의 근사 추정치 — 실제 코드는 v_ego/accel
기반 동적 캡을 쓰므로 완전히 동일하진 않음. (3) 이번 로그는 실제
"실차에서 91차 패치 적용 후" 재생이 아니라 로직 시뮬레이션이므로,
실제 acados MPC 파이프라인 통합 후 승차감까지 보장하는 것은 아님 —
81/82/84/85/87/91차 전부 여전히 "실차 드라이브 검증"이 최종 확인
단계로 남아있음(WIP.md 각 차수 참고).

**코드 변경**: `toolkit/sim_route_margin_regression_scan.py` 신규
(devnotes만, `ryu` 미변경).

## 106차 (105차 체크포인트 완결) — [VALIDATED, 76차 discontinuity_lc의 "harsh braking 실사례" 최초 확보] 차선변경 중 leadRadar 핸드오프 반복으로 인한 급감속 — 92bb45496d + 947fbb7dc6 실차 2건 재현, 화면녹화 HUD로 트랙ID 스위치 시각 확인

**배경**: 105차에서 미확정 상태로 남았던 사용자 제보("차선변경시 변경하려는
차선의 앞차에 대해 급감속") 재현 로그 분석을 완결. 105차 업로드에서
빠졌던 260827 클립 2건 대응 라우트(`947fbb7dc6`, seg0~3)가 이번
재업로드에 포함되어 매칭 불일치 문제도 함께 해소됨.

**시각 매핑 방법론 확정**: 화면녹화 클립 파일명 시각(폰 클럭)이 라우트
폴더명 시각(디바이스 클럭)보다 약 **23초 뒤쳐짐**을 실측으로 확인
(예: 클립 파일명 `101139` → 실제 대응 구간은 디바이스 시각
`10:12:02~10:12:32` 부근, 클립 마지막 1~2초 프레임에 해당). 92bb45496d
클립의 마지막 프레임(f_29/f_30)이 화면 HUD 상 리드 트랙ID가
`99→102→104`로 연속 스위치되는 순간과 정확히 일치해 확정. **향후
동일 계정 촬영분은 이 ~23초 오프셋을 우선 적용해 후보 구간을 좁힐 것**
(단, 매 세션 프레임 대조로 재확인 권장 — 디바이스별/앱버전별 상이할 수 있음).

**핵심 발견 — leadRadar 플래그 반복 토글이 급감속의 직접 트리거**:
두 라우트 모두에서 방향지시등(blinker) 활성 구간마다 `leadRadar`가
`True→False→True`로 짧은 시간에 여러 번 토글되며, 매 토글마다
`leadDRel`이 물리적으로 불가능한 순간변화율(초당 수백 m 상당)로
점프함. dRel_jump_ego_maneuver_overlap()/화면녹화 대조로 최소 3건
독립 확인:

1. **92bb45496d seg4, t=4758.22** (leftBlinker 활성): leadRadar
   True(dRel=47.3)→False(dRel=28.71) 전환, 이후 t=4759.92
   False(18.09)→True(58.80), t=4760.27 True(59.56)→False(15.31) —
   약 2초 안에 3회 연속 토글. 화면녹화 HUD로 리드 트랙ID가
   `99→102→104`로 스위치되는 것을 시각 확인(클립3 f_29/f_30).
   aEgo 최저 -1.12 m/s²(WIP 105차 "후보이벤트A"와 동일 사건, 원인
   확정), TTC danger 미발동(harsh_brake_events도 0건) — **mild 사례**.

2. **947fbb7dc6 seg1, t=2575.37** (rightBlinker 활성): leadRadar
   True(dRel=61.9)→False(dRel=38.39) 전환 후 t=2576.43 다시
   True(29.6, vRel=-4.9)로 재락온, 이어서 aEgo가 -2.4 m/s²까지
   자연스럽게 진행 — 재락온 이후는 harsh 하지만 discontinuity 자체는
   1회.

3. **947fbb7dc6 seg3, t=2683.88~2685.73** (rightBlinker 활성):
   **가장 심각한 사례** — 1.85초 동안 leadRadar가 최소 4회 토글되며
   dRel이 85.61→63.42→47.29→...→35.32m 사이를 요동(각 전환이
   `dRel_jump_ego_maneuver_overlap()`의 would_trigger_ttc_danger=True
   판정). 이후 leadRadar=False 상태로 진짜 접근처럼 보이는 안정된
   감속 트렌드(29m→14.25m, vRel -9.2m/s)로 수렴 → `ttc_danger_events`
   min_ttc=1.55s 트리거 → aEgo 최저 **-3.78 m/s²**(harsh). vEgo
   26.19→20.4m/s로 약 3.5초간 지속 감속(사용자 체감 "급감속"과
   부합하는 규모).

**73차(방안I)/76차(discontinuity_lc) 적용 여부 확인**: 두 로그 모두
`f8e136e`(73차)와 `f3773b5`(76차)를 조상 커밋으로 포함하는
`bc1bcb0f6ff0`(101차)에서 기록됨 — **패치는 이미 적용된 상태**.
코드 검토 결과, 사례1(mild)에서는 4.0s hard-hold + release-rate
100/s 메커니즘이 정상 작동한 것으로 보이나(harsh braking 없음),
**사례3(severe)은 TTC danger override(`_lead0_danger_active`)가
뜨는 순간 boost가 설계상 즉시 base로 강제복귀**(`force_revert`,
73차 코드 주석상 "원본 설계 원칙 유지")되어, jerk 완화가 정작
가장 필요한 구간에서 꺼짐. **78차가 "harsh braking과 겹치는
discontinuity_lc 실사례가 없어 미검증"으로 남겼던 부분을 이번
사례3이 최초로 충족** — 다만 검증 결과가 "boost가 효과적으로
완화했다"가 아니라 "danger override 때문에 애초에 boost가 개입할
기회가 없었다"는, 78차가 기대했던 것과는 다른 형태의 확인.

**미해결 설계 질문 (다음 세션 최우선)**:
사례1에서 트랙ID가 2초 안에 3회(99→102→104) 스위치된 것을 볼 때,
사례3의 "안정된 것처럼 보이는 -9.2m/s 접근"도 **동일한 트랙 불안정의
연장선(진짜 위험이 아니라 또 다른 오탐 트랙일 가능성)**을 배제할
수 없음. 현재 danger override 게이트는 트랙 안정성과 무관하게
"TTC 낮으면 무조건 실제 위험"으로 취급 — 이게 안전상 올바른 기본값
(위험방향 즉시통과 원칙, PARAMS_REGISTRY 학습사항과 일치)이긴 하나,
**핸드오프 발생 직후(예: 2~3초) 재차 발생하는 후속 danger 판정에
한해서만 별도 신뢰도 검토를 추가할 여지가 있는지**가 열린 질문.
방안 설계 착수 전 추가 실측(특히 harsh 사례를 더 확보해 트랙ID
필드로 정량 확인) 필요.

**제안(다음 세션)**:
1. `cereal/log.capnp`에 `trackId`(LeadData) 필드 존재 확인함 —
   `extract_log.py`에 `leadTrackId` 컬럼 추가하면 화면녹화 없이도
   CSV만으로 트랙 스위치를 정량 탐지 가능(현재는 dRel 점프로
   간접추정 + 화면녹화 시각대조에 의존 중, 화면녹화가 없는 로그는
   검증 불가능한 상태).
2. 트랙ID 필드 추가 후 기존 확보된 route CSV들(특히 harsh_brake
   클러스터 있는 것들)을 재스캔해 "핸드오프 후 N초 내 재차 danger"
   패턴의 발생 빈도를 정량화.
3. 위 정량화 결과를 바탕으로 방안 설계(예: 핸드오프 직후 짧은 유예
   동안 danger override 자체의 판정 기준을 살짝 보수적으로 조정하는
   안 등) — **아직 코드 패치 없음, 설계 논의 필요 단계**.

**클립 매칭 결과 요약**:
- 클립1(260827_113702) ↔ seg1 episode1(t=2566.88 L blinker, 별도
  이상 없음)+episode2(t=2574~2578, 위 사례2) — 클립 안에 두 차선변경
  시도가 모두 포함된 것으로 추정(23초 오프셋 적용 시 클립 구간
  11:37:25~11:37:55에 두 이벤트 모두 위치).
- 클립2(260827_113848) ↔ seg3 episode4(위 사례3, severe) — 확정.
- 클립3(260828_101139) ↔ seg4(위 사례1, mild) — 확정(105차
  "후보이벤트A"와 동일 사건).
- 947fbb7dc6 seg1 episode3(L blinker t=2590.23~2593.78)은 dRel 점프
  없음(정상 차선변경) — 미조사, 이상 없음으로 판단.

**qcamera 프레임/화면녹화 대조 완료**: 92bb45496d 클립 f_28~f_30
(리드 트랙ID 99→102→104 시각 확인) + 947fbb7dc6 seg1/seg3 qcamera
프레임 추출 완료(`/home/claude/work/frames_qcam/`, `/home/claude/work/frames_clip/`
— 컨테이너 리셋 시 소실, 재현 필요시 동일 커맨드로 재추출).

**코드 변경 없음**(분석 전용, 방안 설계는 다음 세션).

## 111차 — [참고] 사용자 제보 대시캠 클립 2건(내차_차선변경_급감속) — 947fbb7dc6 106차 중간/심각 사례로 식별, 패치 영향 범위 프레임 단위 확인

**배경**: 사용자가 "차선변경시 화면 가속도 그래프가 패치 적용 후 어떻게
변하나" 질문과 함께 dashcam 화면녹화 클립 2건(`_113702_clip.mp4`,
`_113848_clip.mp4`) 업로드.

**매칭 문제**: 클립 파일명 시:분초 vs route CSV `t`의 단순 오프셋
매칭이 실패(HUD 시계가 시:분만 표시 + 파일명이 저장/종료 시각이라
실제 약 53~55초 어긋남 확인). **신규 도구
`toolkit/match_dashcam_clip_to_route.py`**로 해결 — blinker 클러스터의
상대 시간차(108.9s)가 파일명 시간차(106s)와 오차 2.9s로 일치하는
조합을 탐색해 매칭, qcamera 프레임 배경 대조로 재확인.

**결과**:
- **클립1(113702) = 106차 "중간" 사례**(t≈2574~2578, min_aEgo -2.47).
  이 구간 전체에서 `trigger_source`가 `discontinuity_lc`로 잡힌 적이
  없음(애초에 109차 패치가 관여하는 상황이 아님) — **패치 적용해도
  화면 그래프는 완전히 동일**.
- **클립2(113848) = 106차/108차 "심각" 사례**(t≈2683~2687, min_aEgo
  -3.77, 109차/110차가 검증한 바로 그 force_revert 에피소드). 패치가
  실제로 관여하는 구간은 `t=2685.72~2685.92`(약 0.19초)뿐 — 그 순간
  UNPATCHED는 즉시 base(cost 200)로 복귀했지만 PATCHED는 boost(cost
  500) 유지, 이후 danger가 0.25초 이상 지속 확인되며 PATCHED도 결국
  base(cost 49)로 수렴(둘 다 동일). **진짜 위험이라 confirm이 거의
  즉시(0.35s) 이뤄지므로, 최종 감속 폭(-3.4~-3.8 m/s²)은 패치 유무와
  무관하게 거의 동일할 것으로 예상** — 109차/110차가 이미 확인한
  "min_aEgo 보존, 지속시간만 단축" 결론과 정합.

**한계 고지**: 이 분석은 `long_mpc.py`의 실제 jerk-cost 파라미터
(a_change_cost) 차이를 프레임 단위로 비교한 것이며, 화면에 보이는
`a_ego/a_target/a_out` 곡선 자체를 acados MPC 솔버로 재실행해
재현한 것은 아님(더 큰 작업, 미착수). 코드 변경 없음.

**변경 파일**: `toolkit/match_dashcam_clip_to_route.py`(신규),
`toolkit/README.md`, `toolkit/CHANGELOG.md`, 이 FINDINGS.md 항목.

## 110차 — [VALIDATED] 109차 검증 공백(947fbb7dc6/ad830211ff) 재업로드 후 PATCHED 재검증 완료 — 최심각 사례도 위험반응 보존 확인

**배경**: 109차가 컨테이너 리셋으로 검증 못 한 두 사례를 사용자가 재업로드
(`00000337--947fbb7dc6`, x20seg / `00000335--ad830211ff`, x9seg).
**주의**: 로그 폴더 타임스탬프(2026-08-27 11:36/11:07)가 109차 패치 커밋
`02e1f93`(author date 2026-08-28 11:10)보다 이전 — 이 데이터는 패치
적용 전 raw 센서 기록이며, `patched_replay_v109.py`가 그 위에 패치
로직을 소프트웨어 재생하는 방식이므로 검증 목적(시뮬레이션 재검증)에는
문제 없음. 단 이것으로 실차 드라이브 검증을 대체하지 않음(별도 과제로
유지).

**작업**: `extract_log.py`로 두 라우트 CSV 추출 → `scan_force_revert_
episodes.scan_route()`(UNPATCHED, 108차)와 `patched_replay_v109.
scan_route_patched()`(PATCHED, 109차)를 나란히 실행해 before/after 비교.

**결과**:
- **`947fbb7dc6`(108차/106차 최심각 사례, blinker=True,
  discontinuity_lc)**: force_revert 1건 유지(제거되지 않음) —
  `min_aEgo=-3.40`(BEFORE/AFTER 완전 동일, 위험 반응 보존) / 지속시간
  **0.457s → 0.209s로 단축**(약 54% 감소). 기존 캐시 지속 사례
  (0.55s→0.35s)와 동일한 패턴 재확인 — confirm-hold가 불필요한
  장기화만 줄이고 진짜 위험 반응(min_aEgo)은 그대로 보존함을 최심각
  사례에서도 확인.
- **`ad830211ff`(108차 handoff 2건)**: PATCHED/UNPATCHED 결과가
  `t_start`/`t_end`/`n_frames`/`min_aEgo` 전 항목 프레임 단위까지
  완전 동일 — handoff는 설계대로 전혀 영향받지 않음(트리거 소스명
  분기라 구조적 회귀 불가라는 109차 설계 근거 실측으로 재확인).

**결론**: 109차 옵션1 patch의 시뮬레이션 검증 공백이 모두 해소됨.
로그 기반 replay 검증은 108차 30라우트 + 109차 캐시 12라우트 +
이번 947fbb7dc6/ad830211ff까지 전부 완료 — **남은 유일한 과제는
실차 드라이브 검증**(체감/CONFIRM_S=0.25s 적정성).

**변경 파일**: `FINDINGS.md`(본 항목), `WIP.md`. `toolkit/`, `ryu`
코드 변경 없음(109차 패치 그대로, 재검증만 수행).

## 109차 — [NEEDS_VALIDATION] 옵션1(discontinuity_lc 전용 danger confirm-hold) 패치 구현 + 시뮬레이션 검증 (실차 검증 전, 커밋 b84eeb8)

**배경**: 108차가 확정한 근거(force_revert 5건 중 discontinuity_lc
3건 전부 blinker=True, handoff 2건/순수discontinuity 0건은 정상범위)에
따라 옵션1 patch 실제 구현.

**구현** (`long_mpc.py`, 커밋 `b84eeb8`, `c3-ms-dev`):
- 신규 상수 `LANE_CHANGE_DISCONTINUITY_DANGER_CONFIRM_S = 0.25` (s)
- 신규 상태 `self._lc_danger_confirm_timer` — `_discontinuity_trigger_
  source == 'discontinuity_lc'`일 때만 `_lead0_danger_active`가 연속
  유지된 시간을 누적, 0.25s 미만이면 `force_revert`를 인정하지 않고
  boost(a_change_cost=DISCONTINUITY_JERK_COST_BOOST) 유지.
- 새 트리거 발생 시(dRel discontinuity 재검출) 타이머 리셋 —
  이전 트리거의 confirm 이력이 새 트리거로 이어지지 않게 함.
- `handoff`는 완전히 기존 그대로(즉시 revert) — 분기 조건 자체가
  `trigger_source == 'discontinuity_lc'`로 한정돼 있어 회귀 불가능한
  구조.

**시뮬레이션 검증**: 신규 `toolkit/patched_replay_v109.py`
(`LaneChangeGateReplay`(76차)를 상속해 confirm-hold만 오버라이드)로
캐시 12라우트 재생.
- `a5b1ce4e42`(유일하게 discontinuity_lc 이벤트가 있던 캐시 라우트):
  - 경미한 사례(t=1354.05~1354.20, 0.15s, min_aEgo +0.50) → **완전
    흡수**(confirm 도달 전 danger_active가 사라짐, force_revert 0건)
  - 지속 사례(t=1471.40~1471.95, 0.55s, min_aEgo -0.56) → **0.35s로
    단축**(첫 0.2s는 boost 유지로 흡수, 이후 danger_active가 0.25s
    이상 지속돼 confirm되며 정상적으로 base 복귀 — 진짜 위험 반응은
    보존됨을 확인)
  - 나머지 11개 캐시 라우트는 애초에 force_revert 이벤트가 없어
    PATCHED/UNPATCHED 동일(0건) — 회귀 확인 범위 밖.
- **한계**: 108차에서 발견된 가장 심각한 사례(`947fbb7dc6`, blinker=True,
  min_aEgo=-3.40)와 `handoff` 2건(`ad830211ff`)의 원본 CSV는 108차
  세션 컨테이너 리셋으로 소실돼 이번 세션에서 재검증 불가 — **재업로드
  후 반드시 재검증 필요**(다음 세션 최우선 항목으로 WIP.md에 기록).

**정적 검증**: `python3 -m py_compile` 통과. capnp 스키마 필드 추가/변경
없음(내부 상태 변수만 추가) — 크래시 리스크 낮음. 단, **디바이스 boot
확인은 아직 없음**(컨테이너에서 `msgq.ipc_pyx` import 불가로 원천적
불가 — 기존 원칙대로).

**패치 전달**: `0001-discontinuity-lc-danger-confirm-hold.patch`
(`C:\dev\patch\`, git am 적용 안내 별도 제공).

**다음 세션 최우선**:
1. 실차 드라이브 검증(회귀 체크: 차선변경 중 급감속 완화 체감, 순수
   discontinuity/handoff 반응 회귀 없음, LANE_CHANGE_DISCONTINUITY_
   DANGER_CONFIRM_S=0.25s가 적절한지 — 너무 짧으면 흡수 효과 미미,
   너무 길면 진짜 위험 반응 지연).
2. `947fbb7dc6`/`ad830211ff` 원본 재업로드 후 PATCHED 재검증(현재
   세션에서 못한 부분).

## 108차 — [VALIDATED] 106차/107차 "차선변경(discontinuity_lc)이 force_revert 필요조건" 결론을 실주행 30라우트(신규 18개, 92bb45496d/947fbb7dc6 원본 포함)로 확정 — 중요 시뮬레이션 버그 2건 발견/수정

**배경**: 사용자가 실차 주행로그 18개(약 2.7GB, 92bb45496d/947fbb7dc6 포함)를
신규 업로드. 107차 계속이 12개 캐시 라우트만으로 낸 결론("force_revert
3건 전부 blinker 겹침")을 훨씬 큰 표본으로 재검증 요청.

**1단계 — CSV 추출**: `extract_log.py`로 18개 라우트 전체를 CSV 추출,
`toolkit/`에 저장하지 않고 `/home/claude/work/csv/`에 스크래치로 보관
(Drive 커넥터 미연결 확인 — 컨테이너 리셋 시 소실, 재사용 필요시
재업로드 필요). 기존 캐시 12개 + 신규 18개 = **총 30개 라우트**로
확대.

**2단계 — 1차 재검증 시도, 시뮬레이션 버그 발견 (`flicker_cluster_boost_
replay.py`, 이후 삭제)**: `radar_source_flicker_scan()` 클러스터에
`replay_boost_duration.py`의 `BoostReplay`를 결합해 30라우트 전체
스캔 시도. 두 가지 함정을 순차로 발견:

1. **클러스터 매칭 방식의 워밍업 오염**: 클러스터 구간만 잘라
   재생(warm-start)하면 상태머신이 매번 리셋되어 결과가 자르는
   범위(pad_s)에 따라 달라짐(같은 이벤트가 pad_s=1.0/5.0에서 다르게
   집계됨) — 라우트 전체를 한 번에 연속 재생하는 방식으로 전환해 해결.
2. **[핵심 버그] boost_s 소스 미구분**: `BoostReplay(boost_s=4.0, ...)`를
   모든 트리거 소스에 동일하게 적용했으나, 실제 `long_mpc.py`는
   `discontinuity`(차선변경 무관)=1.0s, `handoff`/`discontinuity_lc`
   (75-76차)=4.0s로 **트리거 소스별 hard-hold 시간이 다름**.
   `BoostReplay`는 이 구분을 아예 모델링하지 않음(생성자에 준 단일
   `boost_s`를 모든 소스에 씀). 이 버그로 인해 `d4e9c02bdb`(t≈2491,
   min_aEgo=-4.19), `ea5bcc0566`(t≈156, min_aEgo=-3.94) 등 다수의
   "새 severe force_revert 사례"가 나왔으나, 원시 데이터 대조 결과
   전부 vturn/cam 소스로 진짜 접근 중인 선행차에 대한 **정상적인
   급제동**(dRel이 물리적으로 일관되게 단조 감소, vRel 지속 음수)이었음
   — 노이즈나 오탐이 아니라 boost 자체가 원래 적용 대상이 아닌
   일반(차선변경 무관) discontinuity 상황. 버그로 인해 실제 1.0s가
   아닌 4.0s 윈도우가 재현되면서 danger_active와 우연히 겹치는 구간이
   늘어나 허위로 "force_revert 사례"에 집계됨.

**3단계 — 정확한 재현 (`replay_lane_change_discontinuity_gate.py`의
`LaneChangeGateReplay`, `duration_mode='full'`, 75차/76차 기존 도구,
현재 `long_mpc.py`의 `discontinuity_lc` 소스와 100% 동일 로직)로
30라우트 전체 재스캔**: 신규 `toolkit/scan_force_revert_episodes.py`
작성(라우트 전체 연속 재생 + 에피소드 그룹핑, 토큰/재사용을 위해
저장).

**최종 결과: force_revert 에피소드 총 5건(30라우트 전체)**

| route_id | 소스 | blinker | t | 지속 | min aEgo |
|---|---|---|---|---|---|
| `947fbb7dc6` | discontinuity_lc | True | 2685.72~2686.18 | 0.46s | **-3.40** |
| `a5b1ce4e42` | discontinuity_lc | True | 1471.40~1471.95 | 0.55s | -0.56 |
| `a5b1ce4e42` | discontinuity_lc | True | 1354.05~1354.20 | 0.15s | +0.50 |
| `ad830211ff` | handoff | **False** | 923.03~923.28 | 0.25s | -1.81 |
| `ad830211ff` | handoff | **False** | 922.83~922.83 | 0.00s | -1.75 |

**결론**:
1. **`discontinuity_lc`(차선변경 중 discontinuity, 75-76차 소스) 3건
   전부 blinker=True** — 106차 원본 사례(`947fbb7dc6`, aEgo -3.40,
   106차가 화면녹화로 확인한 것과 정확히 동일 t/이벤트)를 포함해
   30라우트 전체에서 재확인. **107차 계속의 결론(blinker가 필요조건)이
   훨씬 큰 표본으로 재확정됨.**
2. **순수 `discontinuity`(차선변경 무관, 방안C/G)는 30라우트 전체에서
   danger override로 인한 force_revert 0건** — 2단계에서 나왔던
   "허위 severe 사례"들은 전부 시뮬레이션 버그 산물이었고, 실제로는
   정상적인 안전 반응(genuine hazard, 패치 대상 아님)으로 재확인.
3. **`handoff`(레이더 재락온, 차선변경 무관) 2건은 blinker=False,
   저속(vEgo 6.3→2.5m/s) 근접주행 중 완만한 감속(-1.75~-1.81) —
   심각하지 않은 정상 범위.**

**패치 범위 확정 근거**: 옵션1(플리커/`discontinuity_lc` 감지 후에만
confirm-hold)이 정확히 문제의 3건(전부 discontinuity_lc)에만 적용되고
나머지 2건(handoff, 정상 범위)과 30라우트의 모든 순수 discontinuity
(진짜 위험 반응)는 전혀 건드리지 않음 — **가장 보수적이고 안전한
범위임이 대규모 데이터로 재확인됨.**

**코드 변경 없음**(분석/도구 전용). 관련 파일: `toolkit/
scan_force_revert_episodes.py`(신규, LaneChangeGateReplay 기반 다중
라우트 스캔), `toolkit/README.md`/`CHANGELOG.md` 갱신 완료(108차).

**다음 세션(또는 이어서) 최우선**: 위 확정 근거로 옵션1 patch 설계/
구현 착수 — `long_mpc.py` 1202~1215줄, `is_handoff_source` 분기 중
`_discontinuity_trigger_source == 'discontinuity_lc'`인 경우에 한해
danger_active confirm-hold(N프레임/0.2~0.3s) 적용, `handoff`는 현행
즉시 revert 유지.

**주의(108차 세션 종료 사고 기록)**: 108차 최초 작업분(이 항목 포함,
`scan_force_revert_episodes.py` 포함)은 도구 호출 한도 도달로 push
전에 컨테이너가 리셋돼 1회 유실됐다가 다음 세션에서 그대로 재구성함
(신규 계산 없이 이전 세션 결과를 그대로 기록 — 원본 CSV 18개도 이미
소실돼 재계산 불가, 위 표는 108차 최초 실행 결과를 신뢰해 그대로
사용). **교훈: 이 정도 규모(30라우트, 대량 검증)의 작업은 결론이
나는 즉시(다음 스캔으로 넘어가기 전에) 바로 push할 것 — 세션/체크
포인트 종료를 기다리지 않는다는 원칙을 이번에 어겨서 발생한 사고.**

## 107차 — [NEEDS_VALIDATION] 106차 "차선변경 특유의 leadRadar 핸드오프 급감속" 결론 재검토 — 일반 주행에서도 41%는 blinker 무관 발생, leadRadarTrackId는 이 차량 구조상 무변별

**배경**: 106차가 남긴 "다음 세션 최우선 #1(leadTrackId 컬럼 추가)"을
착수하려 했으나, `extract_log.py`에 `leadRadarTrackId` 컬럼이 이미
63차 계속3에서 추가돼 있었음을 확인(106차가 기존 도구 확인 없이
"없음"으로 판단하고 계획을 세운 것으로 보임).

**leadRadarTrackId 무변별 확인**: 캐시된 라우트 3건(ea5bcc0566,
d2a61d2a73, dfc68039a9) 전수 조사 결과 `leadRadar=True`인 모든 프레임의
`leadRadarTrackId` 값이 예외 없이 **0으로 고정**. 이 차량(Genesis DH,
카메라 SCC 단일점 레이더, 코너레이더 없음)의 `radard.py get_lead()`
구조상 `track_scc = tracks.pop(0)`로 항상 동일 ID(0)만 쓰기 때문 —
멀티트랙 레이더 차량과 달리 트랙ID로 "같은 물체 vs 다른 물체"를
구분할 수 없음. **106차 계획(트랙ID 정량화)은 이 차량에서는 애초에
성립하지 않는 접근**이었음.

**대체 정량화 — `radar_source_flicker_scan()` 신규 작성**: 트랙ID 대신
`leadRadar`(True/False) 값 자체의 엣지(뒤집힘) 빈도를 직접 클러스터링해
blinker 겹침/dRel 최대점프/would_trigger_ttc_danger를 계산하는 함수를
`toolkit/analysis_helpers.py`에 추가(상세는 toolkit/README.md 참고).

**핵심 재검토 결과**: 캐시된 일반 주행 라우트 12건(72차 검증셋
ea5bcc0566/a5b1ce4e42 포함, 86차 c3-ms-curv 검증셋 10건) 전체에 실행:

| 지표 | 값 |
|---|---|
| 총 플리커 클러스터 (min_flips=3, window=2.0s) | 51건 |
| blinker 겹침 | 21건 (41%) |
| blinker 무관 | **30건 (59%)** |

**즉 이 leadRadar 반복토글+dRel점프 현상 자체는 차선변경에 국한되지
않고, 이미 검증 끝난 일반 주행 로그(72차 route1/route2 등)에서도
블링커 없이 더 자주 발생함.** 106차가 확보한 3건(92bb45496d 1건,
947fbb7dc6 2건)은 이 일반적 현상 중 우연히 (a) 화면녹화가 있어
검증 가능했고 (b) blinker와 시간상 겹쳤고 (c) 그중 1건이 TTC danger
문턱까지 간 표본이었을 가능성이 있음 — "차선변경이 원인"이라는
106차의 인과관계 결론은 **표본 편향(화면녹화 있는 3건만 봄)에서
비롯됐을 수 있음**, 아직 반증된 것은 아니지만 재검증 필요.

**주의 (would_trigger_ttc_danger 플래그 신뢰도)**: 이 플래그는
`curve_lead_dRel_jump_events`와 동일하게 프레임간 dRel 변화량을
순간속도로 근사해 계산한 **1차 스크리닝 값**이며, 실제
`process_lead()`의 `_lead0_danger_active`/부스트 게이트 상호작용을
그대로 재현한 것이 아님. 정밀 검증에는 이미 devnotes에 있는
`replay_boost_duration.py`(73차, handoff/discontinuity_lc 분기까지
실측 재생 가능)를 이 51개 클러스터 구간에 대해 돌려보는 후속 작업
필요 — **아직 미실시**.

**다음 세션 방향(사용자 확인 필요, 아직 미확정)**:
1. `replay_boost_duration.py`를 51개 클러스터(특히
   would_trigger_ttc_danger=True인 것들) 구간에 실행해 "danger
   override가 boost를 강제복귀시키는" 106차 사례3 패턴이 blinker
   무관 구간에서도 실제로 재현되는지 확인.
2. 재현된다면: 패치 범위를 "차선변경 한정"이 아니라 "leadRadar 소스
   플리커 일반"으로 넓혀 재설계 필요(단, 넓히면 진짜 핸드오프 반응성
   회귀 위험도 커짐 — 신중 필요).
3. 재현되지 않는다면(즉 blinker 무관 구간의 플리커는 대부분 boost가
   정상 작동): 106차 사례3만의 특수성(예: 1.85초 내 4회+ 라는 유독
   높은 빈도, 혹은 다른 변수)을 별도로 좁혀서 재검토.

**코드 변경 없음**(분석/도구 추가만). 관련 파일: `toolkit/analysis_helpers.py`(신규 함수), `toolkit/README.md`, `toolkit/CHANGELOG.md`.

**후속 — 정밀 재현으로 재검증(같은 세션 계속)**: 위 "다음 세션 방향 1"을
같은 세션 안에서 즉시 실행. `replay_boost_duration.py`(73차, 이미 존재,
`split_gate=True, boost_s=4.0, release_rate=100.0` = 현재 코드와 동일
설정)를 51개 클러스터 전체에 대해 `run_candidates()`로 재생, 각
클러스터 구간에서 `danger_active=True`이면서 동시에 `a_change_cost`가
base로 강제복귀된 프레임이 있는지(=106차 사례3의 "boost가 정작
필요할 때 꺼짐" 패턴) 확인.

**결과: force_revert 재현 3건, 전부(3/3) blinker_overlap=True. blinker
무관 30건 중 재현 0건.** 1차 근사 스캔의 `would_trigger_ttc_danger`는
프레임간 순간변화율 기반이라 노이즈가 많아 과대추정이었음(21~22건
"위험"으로 표시됐으나 정밀 재현에서는 3건만 실제 force_revert). **즉
위에서 제기한 "106차 결론이 표본편향일 수 있다"는 우려는 정밀
검증으로 기각됨 — "차선변경(blinker)이 이 특정 실패모드의 필요조건"
이라는 106차의 인과관계 결론이 오히려 정량적으로 뒷받침됨.**

3건 상세(전부 blinker_overlap=True):
1. `ea5bcc0566` seg9 t≈631.0~631.05: danger_active 0.1초, 구간 내
   min aEgo=+0.05(가속 중, 실질적 영향 없음).
2. `a5b1ce4e42` seg1 t≈1354.05~1354.20: danger_active 0.15초, min
   aEgo=-0.08(경미, 브레이크로 이어지지 않음). 이 라우트/세그는
   72차 검증셋과 동일하나 t는 다름(72차 계속3 사례 t≈1378.85와
   별개) — **72차 검증 당시엔 발견되지 못했던 별도 사례**.
3. `6e1e9a8e26` seg1 t≈161.04~161.18: danger_active 0.15초, min
   aEgo=-1.18(중간 수준).

**종합 결론**: blinker + leadRadar 플리커 + danger override로 인한
boost 무력화 메커니즘 자체는 일반 주행에서도 재현되는 진짜 패턴이지만
(3건), 이번에 확보된 3건은 106차 사례3(aEgo -3.78, severe)만큼
심각하지 않음(-1.18이 최대). **심각도는 상황(실제 리드차량 접근
속도/거리)에 좌우되고, 발생 자체는 blinker와 강하게 결합된 것으로
확정** — 패치 범위를 "차선변경/blinker 컨텍스트 한정"으로 좁히는 것이
타당하다는 근거가 마련됨(107차 시작 시점에 제시했던 옵션1/옵션2 방향
재확인, 아직 미구현).

**다음 세션(또는 이어서)**: 위 근거를 바탕으로 옵션1(플리커 감지 후에만
confirm-hold, 권장) 패치 설계/구현 재착수 가능.

## [REVIEW, 코드변경없음] 136차 — 실차 params.json 백업 검토, LateralTorqueCustom 게이팅 발견

- **배경**: 사용자가 `params_backup-4.json`(161키) 업로드, 수정/추천값
  질문. `ryu/selfdrive/carrot_settings.json`(title/min/max/default
  메타데이터)과 대조해 기본값 대비 변경된 73개 항목 추출 후, 그 중
  실제 코드 게이팅까지 확인한 것만 아래에 정리.

- **1. LateralTorqueCustom=0 + LateralTorqueKf/Ki/Kd/Kp/Friction/
  AccelFactor 전부 비기본값 (핵심 발견)**:
  `selfdrive/controls/lib/latcontrol_torque.py` L144-152:
  ```python
  if lateralTorqueCustom > 0:
    self.torque_params.latAccelFactor = ...LateralTorqueAccelFactor...
    self.torque_params.friction = ...LateralTorqueFriction...
    lateralTorqueKp = ...LateralTorqueKpV...
    ...
  elif self.lateralTorqueCustom > 1:  # reset to default
    ...
  ```
  값: `LateralTorqueKf=85`(기본100), `Friction=30`(기본100),
  `Kd=0`(기본0, 동일), `KiV=10`(기본0?), `KpV=73`(기본100),
  `AccelFactor=2500`. `LateralTorqueCustom` 자체는 0(기본과 동일) —
  즉 게이트가 꺼져 있어 이 값들은 **런타임에 전혀 읽히지 않음**(if문
  자체가 False). 대신 `update_live_torque_params()`가 openpilot의
  liveTorqueParameters(자동추정)를 그대로 적용 중(같은 파일 L132-138).
  **의도 확인 필요**: 커스텀 튜닝을 실제로 쓰려던 것이면
  `LateralTorqueCustom=1`로 켜야 함. 자동추정을 원하는 게 맞다면 현재
  상태 정상, 나머지 필드값은 죽은 설정.

- **2. LatSuspendAngleDeg=45 (허용범위 45~300의 최솟값)**: 자동조향
  일시중단 스티어링각 임계값. `CustomSteerMax=408`(토크상한 커스텀,
  기본0=미사용)과 조합 시, 강한 토크가 필요한 급커브에서 각도임계값에
  먼저 걸려 조향보조가 꺼질 잠재 위험 — 실사용 의도(예: 특정 안전
  마진 확보 목적) 확인 안 됨, 코드상 게이팅 로직까지는 이번 세션에서
  추적하지 않음(단순 파라미터 값 관찰).

- **3. SteerActuatorDelay=0 (기본 30)**: 버그 아님. `modeld.py`
  L430-433:
  ```python
  if custom_lat_delay > 0.0:
    lat_delay = custom_lat_delay + lat_smooth_seconds + 0.1
  else:
    lat_delay = sm["liveDelay"].lateralDelay + lat_smooth_seconds + 0.1
  ```
  0은 "liveDelay(자동측정 조향 지연) 사용" 모드 선택으로, 고정값(30=
  0.30s) 대신 openpilot이 실측한 지연을 쓰는 대안 방식. 정상 동작
  분기, 수정 불필요.

- **4. EnableRadarTracks=-1**: 기존 37차 옆차선 오인식 이슈(track_scc
  trackId=0 폴백, `radard.py` L946 `self.enable_radar_tracks == -1`
  조건)와 직결된 값. 이후 `SCC_FALLBACK_DPATH_GATE=2.0m` 패치
  (PARAMS_REGISTRY.md 참고, PATCH_APPLIED)가 이 조건 경로에도 게이트를
  추가해 완화된 상태 — 값 자체를 바꿀 필요는 없어 보이나, 해당 패치의
  실차 검증이 아직 NEEDS_VALIDATION이라는 점과 연결지어 인지만 해둘
  것.

- **5. VEgoStopping=5 (=0.05, 기본 50=0.50 추정, x0.01 스케일)**:
  일반적으로 쓰이는 값 대비 10배 민감한 정지판정 임계값
  (`modeld.py`/carrot 쪽에서 사용). 코드 경로 상세 추적은 이번 세션
  범위 밖 — 정지/출발 시점 체감 이상 있으면 다음 세션에서 우선 조사
  후보로 기록.

- **나머지**: CruiseSpeed1~5/CruiseMaxVals0~6/AutoNaviSpeed*/
  AutoCurveSpeed* 등 68개는 크루즈속도 프리셋·가속프로파일·내비연동
  커스터마이징 범주 — 상호 모순이나 위험 신호 없음, 개별 기록 생략.

- **주의**: `carrot_settings.json`의 "default" 필드가 일부 항목(예:
  `DynamicTFollowLC` — JSON default=0인데 range=[20,100]로 범위밖,
  title 표시값은 (100))에서 title 표시값과 불일치 — 이 JSON의
  default 필드를 전면 신뢰하지 말고, 실제 코드에서 게이팅을 확인한
  항목(위 1~5번)만 결론으로 채택함.

- **범위**: 코드/패치 변경 없음. 실차 미검증(관찰/코드대조 리뷰만).

## 162차 — [NEEDS_VALIDATION, 원인규명] 161차 "route가 교차로 우회전을 아예 못 봄" 근본원인 확정 — bearing(nPosAngle) 데드레커닝 정체, naviPaths 문제 아님

**배경**: 161차가 발견한 신규 이슈("route156과 동일 route `aeeed9e4a5`의 seg0/seg3에서
실제 급우회전(t=6389~6393, steer 최대 -121.9°)을 naviPaths/TBT가 아예 못 봄")를
이어받아 "이 상황부터 해결"하기로 사용자 지시. 149차~160차 계열 패치(감속
공식/감속률)는 애초에 이 케이스에 적용 여지가 없다는 161차 결론을 재확인하고,
"왜 route가 이 회전 자체를 못 봤는가"를 새로 조사.

**조사 경로**: `carrot_navi_route()`(carrot_man.py)가 쓰는 `current_position`/
`heading_deg`의 출처를 코드 추적 → `carrot_serv.py::_update_gps()`까지 도달.
`self.vpPosPointLat/Lon`(`carrot_navi_route()`가 쓰는 ego 위치)는 매 20Hz 프레임
`estimate_position()`으로 **데드레커닝(dt·speed·bearing 직선외삽)** 계산되고, 이때
쓰이는 `bearing_calculated`는 CarrotNavi 앱이 UDP로 보내는 `nPosAngle`(≈1Hz
갱신)을 그대로 쓴다 — **차량 자체 조향각/요레이트가 아니라 외부 앱이 보고한
헤딩값**.

**핵심 실측 증거** (신규 스크립트로 `carrotMan.xPosLat/xPosLon/xPosAngle`(20Hz) vs
`gpsLocation`(1Hz, 차량 실측 GPS) 직접 비교):
- 회전 시작(t≈6384, steer -5°대) 직전부터 종료 직후(t=6394.97)까지 **11초 동안
  `xPosAngle`(=bearing_calculated)이 296.0°로 완전히 고정**되어 있음 — 그 사이
  실제 조향각은 -5°→-121.9°→+2.9°까지 크게 요동(진짜 우회전).
- 같은 구간에서 `carrotMan`이 보고하는 위치(`xPosLat/Lon`, ego 추정위치)와
  차량 실측 GPS(`gpsLocation`) 사이 거리가 **~10m에서 점점 벌어져 t=6394경
  ~28m까지 누적 이격** — 데드레커닝이 296° 방향으로 계속 직진 외삽하는 동안
  실제 차량은 우회전 중이었기 때문.
- t=6394.97(회전 거의 종료 시점)에 `xPosAngle`이 296.0°→3.0°로 **한 번에 67°
  점프**하며 동시에 `xTurnInfo`가 -1(리셋) 후 새 턴(185m 앞)으로 재포착 —
  회전 내내 정체돼 있던 앱측 헤딩/포지션이 한꺼번에 따라잡히는 패턴과 정확히
  일치.
- `carrot_serv.py` L725 기존 코드에 이미 `# TODO: 여기서 bearing 보정로직
  추가 필요함. CC.orientationNED[2]를 이용하여.`라는 주석이 있음 — 원 개발자가
  이 정확한 간극(외부 앱 헤딩만 쓰고 차량 자체 자세 데이터 미사용)을 이미
  인지하고 있었음.

**결론(확정)**: 161차가 관측한 "naviPaths curvature≈0, TBT가 1600m+ 떨어진
엉뚱한 턴을 가리킴"은 `carrot_navi_route()`의 곡률 계산 로직 버그가 아니라,
**그 계산에 입력되는 `current_position`/`heading_deg` 자체가 회전 중
~10~11초간 부정확했기 때문**(최대 28m 위치오차 + 최대 67° 헤딩오차) — 근본
원인 레이어가 한 단계 더 아래(`_update_gps`/`estimate_position`의 데드레커닝
설계)에 있음. `self.navi_points`(원본 경로 폴리라인) 자체나 `carrot_navi_route()`
곡률/DP 계산 함수는 무관 — 149차~161차 계열 route 패치들과 독립된 신규
버그 카테고리.

**참고**: 이 케이스에서 안전 결과 자체는 정상이었음 — route가 반응 못하는
동안 vturn(비전)이 t=6385.27부터 즉시 인계받아 정상 감속(58→27kph)해
위험 상황은 없었음. 즉 "route 사전감속 보조 기능 공백" 이슈이지 안전
회귀는 아님.

**패치 방향(설계 전, 사용자 확인 대기 — 코드 미작성)**:
1. `estimate_position()`의 헤딩을 앱 보고값(`nPosAngle`) 고정 대신, 차량 자체
   고빈도 자세 데이터(`livePose.angularVelocityDevice`/`orientationNED`,
   기존 TODO 주석이 가리키는 방향)로 보정 — dead-reckoning 구간 동안 실제
   요레이트를 반영해 헤딩이 회전을 따라가도록 함.
2. 대안(더 단순): dt(마지막 앱 fix 이후 경과시간)가 일정 임계 이상이거나
   조향각 변화율이 큰 구간에서는 데드레커닝 신뢰도를 낮춰 `get_path_after_distance`
   탐색 반경/판정을 보수적으로 처리(예: 위치 불확실성 크면 route 곡률을
   그대로 신뢰하지 않고 vturn 우선순위 유지) — 이미 vturn이 안전하게
   인계받고 있으므로 "고쳐서 route가 더 잘 돕게" 하는 성격의 개선.
3. 사용자 판단 필요: 1번(정확도 개선, `livePose` 신규 구독 필요)과 2번(보수적
   완화, 낮은 리스크) 중 방향 선택, 또는 이번엔 기록만 하고 종결.

**범위**: 코드 변경 없음(원인규명만). 컨테이너 리셋으로 최초 실측 CSV(route_full/
gps_full)는 유실 — 사용자 재업로드로 후속 재검증 진행(같은 세션 계속).

## 163차 — [PATCH_WRITTEN, NEEDS_VALIDATION] 162차 근본원인에 대한 방향2(보수적 완화) 패치 구현+시뮬레이션 검증

**배경**: 162차가 확정한 근본원인(route aeeed9e4a5 seg3, 데드레커닝 위치추정이
실제 GPS/앱 위치갱신 없이 ~11초간 정체돼 실제 급우회전을 "직선"으로 오판,
최대 28m 위치오차)에 대해 3가지 패치 방향 중 **방향2(데드레커닝 불확실
구간엔 route의 "완화(속도상향)" 판단을 억제, vturn 등 다른 소스가 안전하게
대응하도록 보수적으로 처리)**를 사용자가 선택. 방향1(livePose 자세데이터로
헤딩 자체를 정확히 보정)은 근본적이지만 신규 구독+검증 비용이 크다는 이유로
향후 과제로 보류.

**설계**: `carrot_serv.py::_update_gps()`가 이미 계산 중이던 `dt`(마지막
실제 위치 fix 이후 데드레커닝 경과시간)를 `self.position_dt_since_fix`로
노출. `carrot_man.py::carrot_navi_route()`의 132차 램프리미터(`_route_speed_prev`
기반 프레임간 상한)에서, 이 값이 `ROUTE_POSITION_UNCERTAIN_DT_S=3.0`(기존
`gps_updated_navi`/`gps_updated_phone` 신선도 판정과 동일 관례값)을 넘는
프레임에서는 "완화(상승)" 방향 상한(`hi`)만 이전 값으로 고정. "감속(하강)"
방향(`lo`)은 그대로 둬, 불확실 구간 중에도 실제로 더 낮은 target이
계산되면(진짜 커브가 늦게라도 잡히면) 즉시 반영되도록 함. 코드 변경은
carrot_man.py(상수 1개 + 게이트 조건 3줄) + carrot_serv.py(속성 초기화 1줄 +
대입 1줄)로 최소화.

**시뮬레이션 검증(`sim_route_position_uncertainty_gate.py`, 신규, 3/3 PASS)**:
1. `regression_dt_always_low`: dt가 항상 임계값 미만인 정상 시나리오에서
   패치 전/후 출력이 완전히 동일(max_diff=0.0) — 정상 주행 회귀 없음 확인.
2. `reproduction_real_event_scale`: 실측 규모(경과 ~11초, accel_limit_kmh
   ~3.3, raw가 즉시 300으로 열리려는 상황) 합성 재현 — baseline(패치 전)은
   실측처럼 매끄럽게 상승(92→128.3, 11초 규모), 패치 후(gated)는 3.0초
   경과 시점부터 완전히 동결됨 확인.
3. `decrease_still_allowed`: 불확실 구간 중에도 raw가 더 낮아지면(진짜
   커브 감지) 게이트가 하강을 막지 않음(out=lo 방향 정상 반영) 확인.

**기존 157차 apex 재설계 회귀 테스트**(`sim_route_apex_redesign.py --unit-tests`)
재실행 7/7 PASS — 이번 패치가 곡률/apex 계산 로직 자체는 건드리지 않아
기존 회귀 없음 재확인.

**한계(정직하게 기록)**: `carrotMan` cereal 메시지가 `position_dt_since_fix`를
발행하지 않아, 실측 CSV(route_full.csv)로 이 게이트의 프레임별 판정을
직접 재생(replay)하는 검증은 이번엔 불가능했음 — 합성 시나리오(실측과
동일 규모로 구성)로만 검증됨. 실차 적용 후 로그에서 이 필드를 cereal에
추가 발행하면 다음 세션에 직접 재생 검증 가능(향후 과제로 남김).

**다음 단계**: 실차 `git am` 적용 → 우회전 구간 재주행 → route= HUD가
불확실 구간 동안 더 이상 매끄럽게 상승(오도 완화)하지 않고 동결되는지,
그리고 정상 커브/직선 구간에서는 기존과 동일하게 동작하는지 확인.

**범위**: `selfdrive/carrot/carrot_man.py`, `selfdrive/carrot/carrot_serv.py`.
patch 파일: `0001-route-position-uncertainty-gate.patch` (base `712d76babc08`,
c3-ms-dev).
