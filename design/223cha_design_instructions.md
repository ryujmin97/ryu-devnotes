# 223차 — Route 감속 로직 전면 단순화 재설계 지시

(수신: 지선생/ChatGPT 설계안, 원문 그대로 보존)

## 0. 가장 중요한 설계 의도

원칙 1. Route가 포함된 Parameter에는 무조건 Route 로직 적용

TurnSpeedControlMode 의미:
- 0 = off
- 1 = vision
- 2 = vision + route
- 3 = route

Route 적용 조건: `route_enabled = turnSpeedControlMode in [2, 3]`

- Mode 0 → Route OFF
- Mode 1 → Route OFF
- Mode 2 → Route ON
- Mode 3 → Route ON

"mode == 2"만 Route ON으로 해석하면 안 됨. Mode 2/3 차이는 Vision-Route 최종 제어 관계이지 Route 로직 적용 여부가 아님.
→ Parameter에 Route가 포함되어 있으면 Route 로직을 반드시 실행.

## 1. Route는 오직 감속만 담당한다

목적: Navigation 경로 앞쪽 curve로 인해 VTurn만으로는 늦게 감속하는 문제를 해결하기 위한 사전 감속.
방향: 현재 속도 → 낮은 curve target speed. 상향(가속) 기능 불필요.

삭제 대상(상향 관련):
- route upward recovery
- upward ramp
- hi = inf
- previous route speed를 이용한 상향 제어
- route speed를 높이는 보정
- route ceiling
- vEgo ceiling
- sharpest candidate ceiling
- 150 km/h ceiling

다른 조건문으로 우회 보존 금지.

## 2. Parameter와 route_active는 별개

- route_enabled = Parameter에 Route가 포함되어 있는가?
- route_active = 현재 실제 Route 감속을 수행 중인가?

예: Mode 2 + 직선 → route_enabled=True, route_active=False
예: Mode 3 + curve 발견 + 감속 필요 → route_enabled=True, route_active=True

## 3. Mode 0/1에서는 Route 로직 자체를 실행하지 않는다

curve search / apex selection / route target 계산 / route deceleration / route state machine / route release timer 자체가 실행되지 않도록 함.

Mode 전환 2→1, 2→0, 3→1, 3→0 시 즉시:
- route_active = False
- release timer clear
- current target clear
- current apex state clear

## 4. Mode 2/3 상태기계

Mode 2/3 → Route ENABLED
  → 2초 HOLD 중? YES → Route 완전 OFF
  → NO → 가장 가까운 유효 curve 1개 검색
    → 감속 필요? NO → Route OFF
    → YES → Route ACTIVE → 현재 차량 속도에서 curve target 방향으로 감속
      → curve/apex 도달 → Route 즉시 RELEASE → 2초 HOLD → 다시 nearest curve 검색

## 5. Curve는 항상 가장 가까운 하나만

여러 후보 중 가장 가까운 유효 curve 1개만 선택. 기존 `candidates[0]` 방식이 목적에 맞는지 확인 후 재사용. 여러 curve를 동시 상태로 관리(예약)하지 않음.

## 6. Route ACTIVE 진입 조건

반드시 `현재 차량 속도 > curve target speed`일 때만 ACTIVE.
- vEgo=80, target=50 → ACTIVE, 감속
- vEgo=45, target=50 → Route OFF (45→50으로 올리지 않음)

## 7. "현재속도에서 시작" 정확히 구현

기존 `calculate_current_speed()`는 vEgo를 입력받지 않음 (거리+target 기반 camera-style 물리식). 그 자체로는 "현재 차량속도에서 시작하는 감속식"이 아님. 무조건 KEEP 금지.

요구 흐름: 현재 vEgo → curve까지 남은 거리 → curve target speed → Route 감속.
새 감속식 필요 시 실제 코드 구조와 최종 arbitration 분석 후 최단순 방법으로 구현.

## 8. 이전 ceiling 공식 재사용 금지

`sqrt(target_speed² + 2*decel*distance)` 재사용 금지 (거리상 허용 가능 최대속도 ceiling 계산 성격 — 이번 목적 아님). dynamic_decel 증가 시 허용속도가 올라가는 기존 문제 재발 금지.

## 9. Route는 가속 명령을 절대로 생성하지 않는다

Invariant:
- 감속 필요할 때: route speed < 현재 vEgo 방향
- Route target >= 현재 vEgo: Route OFF

- vEgo=80,target=50 → 감속
- vEgo=50,target=50 → OFF
- vEgo=40,target=50 → OFF (50으로 올리지 않음)

## 10. Apex/Curve 도달 즉시 RELEASE

ACTIVE 상태에서 apex 도달 시: route_active=False, current target=clear, 즉시 해제.
이후 Mode 2는 기존 Vision/VTurn arbitration 재작동, Mode 3은 기존 Mode 3 제어 구조 재작동.
핵심: Route 감속 상태가 apex 이후 계속 유지되지 않음.

## 11. RELEASE 후 2초간 Route 완전 OFF

2초간: 새 curve 검색 X, 새 apex 선정 X, 새 target 생성 X, Route 감속 X.
목적: Curve A apex 직후 Curve B 즉시 감지되어 Route가 바로 재부착되는 현상 방지.

## 12. 2초 후 다시 검색

이전 Curve A를 이어서 추적하지 않음. 현재 위치에서 nearest valid curve 새로 검색 → 감속 필요 시 ACTIVE, 아니면 OFF.

## 13. 기존 205~221차 Ceiling 계열 삭제

삭제 대상: sharpest_candidate_speed, route_ceiling_kph, min(vEgo,150), 3항 min() ceiling, 150km/h fallback ceiling.
특히 221차 `route_ceiling_kph = min(vEgo, 150)`도 최종 설계에 남기지 않음. 이름 변경/이동으로 동일 ceiling 우회 유지 금지.

## 14. 기존 199차 BOOST 삭제 검토

삭제 검토 대상: _route_apex_boost_armed, ROUTE_VEGO_BOOST_MAX_MSS, required_decel_mss, boosted_mss, ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH.
새 상태기계(nearest curve→active→apex release→2초 hold)에서는 필요성 소멸 시 완전 삭제.

## 15. 기존 Ramp Limiter 삭제 검토

삭제 대상: _route_speed_prev, accel_limit_kmh, max_step_kmh, lo, hi. 특히 `lo = previous_route_speed - ...`처럼 이전 Route 속도가 현재 출력에 영향 주는 구조 불필요. Route는 현재 curve에 대한 현재 감속 요구만 계산.

## 16. GPS uncertainty gate 삭제 검토

Ramp limiter와 결합된 ROUTE_POSITION_UNCERTAIN_DT_S, position_dt_since_fix, cc_pose_valid 관련 Route relaxation gate 정리.
단, navigation path 계산에 필수적인 GPS 위치 유효성 검사 자체는 별도 KEEP. "GPS 위치 검증 자체"와 "Route relaxation gate"를 구분해서 삭제.

## 17. 상태는 최소한으로

유지: route_enabled, route_active, route_release_time, current_route_target_speed, current_route_apex_dist, current_route_apex_idx.
불필요(생성 금지): previous route speed, previous apex speed, boost armed, boost speed, ceiling state.

## 18. Mode 변경 시 상태 초기화

2/3 → 0/1: 즉시 route_active=False, route_release_time=None, current target=None, current apex=None.
0/1 → 2/3: 이전 Route 상태 복구하지 않고 새로 nearest curve 검색.

## 19. 최종 arbitration까지 확인

`carrot_navi_route()` 내부만 보고 끝내지 않음. 흐름: carrot_navi_route() → liveRouteSpeed → speed_n_sources → min() → 최종 speed control.
Mode 2/3에서 Route가 각각 최종 제어에 어떻게 들어가는지 실제 코드 기준 확인. Route OFF일 때 route source가 arbitration에 남아 이전 값으로 속도를 붙잡는 현상 없는지 확인.

## 20. 필수 검증 CASE (1~14)

1. Mode 1 → Route 계산 자체 OFF
2. Mode 0 → Route 계산 자체 OFF
3. Mode 2 → Route 적용
4. Mode 3 → Route 적용
5. Mode 2/3 직선 → Route OFF
6. vEgo < curve target → Route OFF (가속 안 함)
7. vEgo > curve target → Route ACTIVE, 감속
8. apex 도달 → 즉시 RELEASE
9. apex → 2초 → Route 완전 OFF
10. 2초 종료 → nearest curve 재검색
11. Curve A → Curve B: Apex A 직후 B로 즉시 전환되지 않아야 함
12. Mode 2/3 → Mode 1: Route state 즉시 초기화
13. Mode 1 → Mode 2/3: 새 Route search
14. Stop→Restart→Curve: 222차에서 확인된 `liveRouteSpeed > vEgo` 현상이 새 구조에서도 발생하는지 확인

## 21. 구현 순서

바로 코드 수정 금지. 순서:
1. STEP1 — 현재 코드 감사: KEEP/DELETE/MODIFY/NEW 최종 확정
2. STEP2 — 새 감속식 확정: vEgo를 실제 계산에 어떻게 반영할지 수식+코드흐름 설명
3. STEP3 — arbitration 확인: Mode 2/3에서 Route speed가 최종 제어에 어떻게 들어가는지 증명
4. STEP4 — 코드 수정: legacy 제거, 최소 상태기계 구현
5. STEP5 — simulation: 기존 sim_route_* 테스트 이용
6. STEP6 — diff 검토: 삭제 코드/신규 코드가 설계 의도와 일치하는지 확인
7. STEP7 — devnotes 기록: 설계결정/삭제한 legacy/새 상태기계/감속식/검증결과/미결사항 기록

## 22. 절대 잊지 말 것

Route 있는 Parameter → Route 사용 / Route 없는 Parameter → Route 사용 안 함.
Route 사용 시: 가장 가까운 감속 필요 curve 1개 → 현재 속도에서 target까지 감속 → apex 도달 → 즉시 RELEASE → 2초 OFF → 재검색.
Route는 감속만 한다 — 가속 로직 불필요. 보정식 계속 추가 금지, 원칙에 안 맞는 legacy 과감히 제거하여 단순/예측가능한 상태기계로 만들 것.
