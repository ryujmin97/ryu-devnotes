# 223차 STEP1 — 코드 감사 (KEEP/DELETE/MODIFY/NEW)

Base commit: 7519a3a91df530ee6667183759b6c94afa8ae287 (221차: route ceiling vCruise->vEgo 재교체 + lookahead 300m->600m)
대상 파일: selfdrive/carrot/carrot_man.py, selfdrive/carrot/carrot_serv.py
분석 방법: 정적 코드 리딩만 수행 (실행/시뮬레이션 없음). 실차 검증: 미실시.

## A. Mode 게이팅 (design doc §0, §3)

**확인 결과: 설계 지시의 가정이 코드와 일치함.**

- `common/params_keys.h` 기본값 1, `settings.cc`에 "0: off, 1:vision, 2:vision+route, 3: route" UI 설명 존재 → mode 0~3만 사용자가 설정 가능.
- `carrot_serv.py:1102` `if self.turnSpeedControlMode in [1,2]:` → vturn 참가 조건
- `carrot_serv.py:1119` `if self.turnSpeedControlMode in [2,3,4]:` → route 참가 조건 (4는 UI 범위 밖, 죽은 코드/안전마진)
- 실질적으로 design doc 표와 정확히 일치: Mode0(둘다off) / Mode1(vturn only) / Mode2(vturn+route) / Mode3(route only)

**중요 발견 — design doc §3 요구사항 미충족:**
현재 `carrot_navi_route()`(carrot_man.py:645~)는 **turnSpeedControlMode를 전혀 참조하지 않는다.** Mode 0/1이어도 curve search / apex 선택 / calculate_current_speed / ramp limiter / boost 로직이 매 20Hz 프레임마다 그대로 실행되고, 그 결과값(route_speed)이 `carrot_serv.py`의 arbitration 단계(`speed_n_sources.append`, 1119줄)에서만 mode에 따라 채택 여부가 갈린다.
→ design doc §3 ("Mode 0/1에서는 계산 자체가 실행되지 않도록")을 만족하려면 `carrot_navi_route()` 진입부에 mode 게이트를 새로 추가해야 함 → **NEW**.

## B. KEEP

| 항목 | 위치 | 사유 |
|---|---|---|
| candidates 선정 (가장 가까운 감속필요지점, `candidates[0]`) | carrot_man.py:874-878 | design doc §5와 정확히 일치 — 이미 "가장 가까운 curve 1개" 방식. 179차/196차에서 이미 이 형태로 정착됨. 재사용 가능 |
| 직선 폴백 (`candidates` 비었을 때 전역 min) | carrot_man.py:875 | 유지해도 무방 (design doc이 명시적으로 문제삼지 않음) |
| GPS 위치 유효성 자체 검사 (`cc_pose_valid`, navigation path 계산용) | carrot_serv.py 별도 위치 (미조사, STEP1에서 시간상 미착수) | design doc §16: "GPS 위치 검증 자체는 KEEP" — 단 다음 세션에서 navigation path 계산 경로에 실제로 쓰이는지 별도 확인 필요 |
| `ROUTE_CURVE_NEGLIGIBLE_THRESHOLD`, `ROUTE_CURVATURE_FINE_SAMPLE` 등 곡률 계산 상수 | carrot_man.py:63,79 | Route 감속의 "방향(상향/하향)" 문제가 아니라 곡률 계산 정확도 문제 → design doc 삭제대상 목록에 없음 → KEEP |
| `route_lookahead_m = 600.0` (221차 확정값) | carrot_man.py:744 | design doc이 lookahead 값 자체를 문제삼지 않음 |

## C. DELETE (design doc이 명시적으로 삭제 지시)

| 항목 | 위치 | design doc 근거 |
|---|---|---|
| `_route_speed_prev`, ramp limiter (`lo`, `hi`, `max_step_kmh`, `accel_limit_kmh`의 램프 적용부) | carrot_man.py:511, 1163-1178 | §15 |
| `hi = math.inf` 상향 무제한 로직 (172/173차) | carrot_man.py:1170 | §1, §15 |
| GPS uncertainty gate (`ROUTE_POSITION_UNCERTAIN_DT_S`, `position_dt_since_fix`, `cc_pose_valid`) — **ramp limiter와 결합된 부분만** | carrot_man.py:118, 1173-1176 | §16 (GPS 검증 자체 KEEP, 이 게이트만 삭제) |
| `route_ceiling_kph = min(v_ego_kph, ROUTE_MAX_SPEED_KPH)` 및 3항 `min()` ceiling 전체 | carrot_man.py:1087-1088 | §13 |
| `ROUTE_MAX_SPEED_KPH = 150.0` 상수 및 관련 sentinel 사용 전체 재검토 | carrot_man.py:197, 661,674,712,718 | §13 — 단, sentinel(비활성 표시값) 용도까지 완전히 없앨지는 STEP3(arbitration 확인)에서 결정 필요. design doc은 "150 ceiling" 삭제를 말하지만 "비활성 상태를 나타낼 sentinel 자체"까지 없애라는 뜻인지는 불명확 → **사용자 확인 필요 항목으로 별도 표시** |
| `_route_apex_boost_armed`, `_route_apex_boost_armed_speed`, `_route_apex_speed_prev`, `ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH`, `ROUTE_VEGO_BOOST_MAX_MSS`, `required_decel_mss`, `boosted_mss` | carrot_man.py:169,177,517-518,1094-1124 | §14 |
| `sharpest_candidate_speed` (207차 도입, ceiling 항에서 사용) | carrot_man.py:1088 부근 (변수 정의부는 미조사) | §13 |

## D. MODIFY (일부 로직은 남기되 내부 계산 방식 교체)

| 항목 | 위치 | 변경 방향 |
|---|---|---|
| raw out_speed 계산: `calculate_current_speed(apex_dist, apex_speed, 0, decel_rate)` | carrot_man.py:846 부근 | §7,§8 — 현재 함수는 vEgo 미입력, 거리기반 ceiling formula(`sqrt(target²+2·decel·dist)`, carrot_serv.py:419-434)를 그대로 재사용 중. design doc은 이 재사용이 "현재속도에서 시작하는 감속"이 아니라고 명시적으로 지적 → **STEP2에서 신규 감속식 확정 후 이 호출부 교체 필요** |
| Mode 게이트 위치: 현재 arbitration(carrot_serv.py:1119)에만 존재 | carrot_serv.py:1119, carrot_man.py:645(함수 진입부) | §3,§18 — carrot_navi_route() 진입부에도 mode 게이트 추가, mode 전환 시 상태 초기화(§18) 로직 신규 필요 |

## E. NEW (설계 지시가 요구하지만 현재 코드에 없음)

| 항목 | design doc 근거 |
|---|---|
| `route_active` 상태값 (현재는 route_enabled에 해당하는 것도 명시적 변수 없이 mode 조건문으로만 존재, active 개념 자체가 없음) | §2 |
| Apex 도달 후 **2초 완전 OFF (release hold timer)** — 현재 코드에는 이 개념이 전혀 없음. apex 통과 즉시(무상태 구조상) 다음 프레임에 바로 다음 candidate로 자동 전환됨 (196차 무상태 설계) | §11, §12, CASE 9/10/11 |
| Mode 전환 시 명시적 상태 초기화 (`route_active=False`, `route_release_time=None`, target/apex clear) | §18 |
| `carrot_navi_route()` 진입부 mode 게이트 (curve search 자체를 스킵) | §3 |
| 신규 감속식 (vEgo 기반, "현재속도에서 curve target까지") | §7 |

## F. 사용자 확인 필요 (독단적으로 진행 불가 — PROJECT_INSTRUCTIONS.md §33/§5)

1. **203차 vEgo-anchor+debounce 설계와의 정면 충돌**: devnotes 기록상 203차는 `ROUTE_MAX_SPEED_KPH=150` 유지 + vEgo-anchor(`hi=vEgo_kph`) + debounce gate 조합을 설계 중이었음. 223차는 150 ceiling과 hi=inf/vEgo 상향로직을 전부 삭제하라고 지시. **두 방향이 근본적으로 다른 설계 철학**(점진적 보정 vs 전면 재설계) — 어느 쪽을 채택할지 확인 필요.
2. **196차의 relative severity 게이트 제거 사실**: 이전 세션 기억(userMemories)에는 "179-181차 relative severity gate는 보존해야 함"이라고 되어 있었으나, 실제 코드(196차 커밋)에서 이미 제거되어 있음을 확인함. 기억이 GitHub 상태보다 오래된 사례 — 223차 작업은 현재 코드(gate 없음) 기준으로 진행해도 되는지, 아니면 이것도 재검토 대상인지 확인 필요.
3. **ROUTE_MAX_SPEED_KPH sentinel 용도**: ceiling으로서의 150은 삭제 대상이 명확하나, "route 비활성/미계산" 상태를 나타내는 sentinel 값 자체(211차 도입)까지 없앨지, 다른 방식(예: None)으로 대체할지 미결정.

## G. STEP2/STEP3 착수 전 필요 정보 (다음 세션)

- carrot_serv.py의 최종 arbitration 전체 흐름(`speed_n_sources` → `min()` → 최종 출력)의 정확한 위치와 mapTurnSpeedFactor 등 곱셈 적용 순서를 이번엔 일부만 확인함(1090-1120줄). 전체 확인 필요.
- `autoNaviSpeedDecelRate` 등 decel_rate 관련 파라미터가 신규 감속식에 그대로 재사용 가능한지 확인 필요.

실차 검증: 미실시. 이번 세션은 정적 코드 리딩(STEP1)만 수행함.
