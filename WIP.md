# WIP — 중단 지점 체크포인트

세션 정상 종료가 아니라 사용자 요청으로 여기서 저장한 중단 지점.
다음 세션(다른 계정 포함)은 여기부터 이어받는다.

---

## 완료된 것 (2026-08-20, 이번 세션 — 260819-8 로그 분석, 사용자 "체크포인트" 요청)
- 커밋 분석: HEAD f7b154638cf2 그대로, 신규 커밋 없음(확인만). 코드
  변경 없음(관찰/분석만).
- 라우트 260819-8 분석 완료 — route8a(`f7e0bb3abd` seg24~39, x16seg,
  260819-7 직접 연속분, 27.27km/959.9s, avg 102.3km/h, cruiseEnabled
  100%) + route8b(신규 `da28883b75` seg0~4, x5seg, 5.93km/272.0s, 시내
  저속 혼합, cruiseEnabled 83.5%).
- **route8a: harsh_brake/turn_speed_violation/steering_oscillation/
  cut-in/curve_exit_no_accel_v2 전부 0건 — 지금까지 분석한 라우트 중
  처음으로 모든 카테고리가 완전히 클린한 순수 고속도로 구간.** 다만
  desiredCurvature가 threshold 초과 39/19145 프레임뿐(사실상 직선)이라
  기존 커브 가설 2건(v3 여유폭 필터 적용한 재스캔 / 커브 진입 중
  과소감속 추가 표본 수집)은 이번 로그로는 표본을 못 얻어 **진전 없이
  그대로 이월**.
- route8b: harsh_brake 16건 전부 t=2683.36 disengage 직후 저속 정차
  감속 — 기존 disengage-인접 오탐 패턴과 동일(신규 아님).
  curve_exit_no_accel_v2 후보 1건은 vEgo=0.04m/s(정차 완료 시점)라
  가설과 무관해 배제.
- LEAD_ACQ_LOSS_GRACE_TIME: route8a에서 기존 최대(2.46s)를 크게 웃도는
  긴 유실 다수 확인(최대 222.85s) — 같은 라우트의 다른 이벤트 카테고리가
  전부 0건이라 고속도로 선행차 부재로 판단, 무해 재확인.
  PARAMS_REGISTRY 판단 변경 없음.
- speed_n_sources 플리커 재확인(route8a 25건/52건, route8b 40건/61건) —
  신규 아님.
- MAX_SEGMENTS_PER_ROUTE 관련 참고 관찰 추가: route `f7e0bb3abd`가
  260819-6 seg0~260819-8 seg39까지 정확히 40세그먼트 이어진 뒤 boot ID
  변경과 함께 종료 — 캡 발동인지 우연한 재부팅 겹침인지 로그만으론
  구분 불가(route ID는 통상 boot마다 새로 생성되는 구조). 여전히 로그
  시각이 패치 커밋 이전이라 NEEDS_VALIDATION 유지.
- FINDINGS.md/LAST_ANALYZED.md/PARAMS_REGISTRY.md 갱신 완료.
  `toolkit/` 코드 변경 없음(이번 세션은 기존 헬퍼만 사용).
- **이 항목은 사용자 요청 "체크포인트"에 따른 것 — 아래 미해결 항목
  (특히 6번 v3 필터, 7번 진입 중 과소감속 스캔 헬퍼)은 이번 세션에도
  착수하지 못했고 그대로 이월. 다음 세션은 커브 콘텐츠가 있는 로그
  확보 시 6/7번부터 재개할 것 (이번처럼 순수 고속도로/직선 위주 로그는
  두 가설 검증에 표본을 못 준다는 점 참고).**

## 완료된 것 (2026-08-20, 이번 세션 — 260819-7 로그 분석, 사용자 "체크포인트 저장" 요청)
- 커밋 분석: HEAD f7b154638cf2 그대로, 신규 커밋 없음(확인만).
- 라우트 260819-7 분석 완료 — route `f7e0bb3abd` seg2~23(route6b 직접
  연속분, x22seg, 32.73km/1319.9s, avg 89.3km/h). **처음으로 고속도로
  위주 로그 확보**(기존 로그들은 대부분 시내/국도).
- **주 작업 1: "커브 탈출 후 재가속 지연" 가설 검증 계속.**
  `toolkit/analysis_helpers.py`에 `curve_exit_no_accel_scan_v2` 신설
  (leadStatus 필터 + 직선유지 0.8s 조건, 260819-6에서 예고한 (a) 완료).
  260819-7 재스캔: v1 4건→v2 3건. 남은 3건 중 2건은 저속 무관, 1건
  (seg20 t=1256.45, 114km/h)을 프레임 대조 → **3번째 오탐 패턴 신규
  확인**: vCruiseCluster(사용자 설정 크루즈속도) 캡 때문에 desiredSpeed가
  이미 크게 올랐어도(149→200kph) vEgo가 애초에 그 근처(113.9 vs
  120km/h)라 가속할 여지가 거의 없었던 정상 상황. `controlsd.py:214`의
  `min(vCruiseCluster, carrotMan.desiredSpeed)` 캡 로직 확인함. 가설은
  이번에도 확증/반증 못함 — **v3 개선 방향: 탈출 시점
  min(vCruise,desiredSpeed)-vEgo 여유폭이 작으면(<3~5km/h) 후보 제외.**
- **주 작업 2 (부수 발견, 표본 1건, INVESTIGATING): seg6 t=434.70 —
  아직 안 끝난(곡률 계속 증가 중인) 커브에서 vturn이 매끈히 감속
  진행 중(aEgo 이미 -3.41m/s²)인데 운전자가 브레이크 개입.** "커브가
  덜 끝났는데 감속이 곡률 조임 속도를 못 따라간 것 아니냐"는 새로운
  방향의 가설 — 기존 "탈출 후 재가속 지연"과는 반대 방향(진입 중
  과소감속 의심). 표본 1건뿐이라 결론 보류, 추가 표본 수집 방법 제안
  (cruise_engage_disengage_events + 직전 5초 src=vturn 스캔 헬퍼 신설
  검토).
- **부가 발견(코드 리딩): PARAMS_REGISTRY의 vturn_decel_rc/accel_rc가
  구버전 값(0.25s/0.6s)으로 잘못 기록돼 있던 것 확인·정정** — 현재
  코드(`carrot_man.py`)는 a94a58b 커밋에서 물리공식 기반으로 재설계되며
  0.15s/0.15s로 이미 바뀌어 있음(더 빠른 필터). vturn_decel_rate=1.2m/s²,
  vturn_safe_time=1.0s도 PARAMS_REGISTRY에 신규 등록.
- 그 외: harsh_brake 12건 중 11건 기존 disengage-인접 패턴과 동일,
  1건은 위 신규 패턴. turn_speed_violation/steering_oscillation 0건.
  LEAD_ACQ_LOSS_GRACE_TIME 0.5s 초과 6건 전부 고속 개활도로 상황
  무해 재확인. MAX_SEGMENTS_PER_ROUTE: 이번 로그도 24개 세그먼트
  (seg0~23, route6b+route7) 연속이나 로그 시각(8/19 15:xx)이 패치
  커밋(8/20 00:57)보다 이전이라 여전히 검증 불가(반복 확인만).
- FINDINGS.md/LAST_ANALYZED.md/PARAMS_REGISTRY.md 갱신 완료.
  `toolkit/analysis_helpers.py`도 이번 세션에 수정됨(v2 함수 추가) —
  push 대상에 포함.
- **이 항목은 사용자 요청 "체크포인트 저장"에 따른 것 — 아래 미해결
  항목은 이번 세션에서도 완전히 해소되지 않았고 이월됨. 다음 세션
  우선순위(둘 다 사용자 핵심 관심사인 종방향 제어 품질과 직결):
  (a) v3 필터(목표속도 여유폭) 추가 후 route1~7 전체 재스캔,
  (b) "커브 진입 중 과소감속" 가설용 추가 표본 수집 도구 신설 +
  기존 로그 재스캔.**

## 완료된 것 (2026-08-20, 이번 세션 — 260819-6 로그 분석, 사용자 "체크포인트 저장" 요청)
- 커밋 분석: HEAD f7b154638cf2 그대로, 신규 커밋 없음(확인만).
- 라우트 260819-6 분석 완료 — route6a(`dc8bdc7d4d` seg5~22, x18seg,
  route5b 직접 연속분, 8.57km/1043.2s, 시내/정체 위주) +
  route6b(신규 `f7e0bb3abd` seg0~1, x2seg, 0.4km/121.6s, 저속 위주).
- **주 작업: 사용자가 이전 세션에서 제기한 "커브 탈출 후 재가속 지연"
  가설(vturn/model/route 공통, 완전 탈출 전 재가속 시작 가능 여부)을
  이번 실주행 로그로 검증 시도.** `curve_exit_no_accel_scan` 도구로
  후보 19건 추출 → cruiseEnabled/브레이크/vCruise갭 필터 → 상위 5건
  프레임 단위 직접 대조. **결과: 전부 오탐으로 판명** — (1) 두 건은
  desiredCurvature가 차선추종 노이즈 수준(0.0001~0.003)인데 실제로는
  선행차 추종에 의한 정상 정차 감속이었음(desiredSpeed가 시종
  vEgo보다 훨씬 높아 어떤 source도 실제 제약 안 함), (2) 한 건은
  "커브 탈출"이 아니라 S자 연속커브 사이 일시적 직선 통과 후 다음
  커브로 재진입하는 중이었음(desiredCurvature가 straight_thresh를
  잠깐 통과했다가 다시 급증). **이번 로그로는 가설을 확증도 반증도
  못함.**
- 개선 방향 제안(코드 미착수, 다음 세션 검토 대상으로 추가):
  1. `curve_exit_no_accel_scan`에 leadStatus=False(또는 dRel 충분히
     먼) 조건 추가 — 선행차 추종 감속을 커브탈출 후보에서 배제
  2. straight_thresh 이후 "진짜 직선" 지속시간 최소치 강화 또는 이후
     커브 재진입(curvature 재상승) 여부 체크 — S자 연속커브 오탐 배제
  3. 위 필터링 반영 후 재스캔, 그래도 안 남으면 선행차 없는 개활지
     단일 커브가 많은 로그로 재시도 필요 (사용자에게 그런 구간
     녹화 요청 검토)
- 부가 발견: LEAD_ACQ_LOSS_GRACE_TIME 스캔에서 6~36초짜리 긴 유실
  다수 신규 확인(기존 최대 2.46s 대비 이례적으로 김) — 개별 대조 결과
  전부 무해(개활도로 선행차 소실 또는 저속 급코너 시야이탈, 코너
  진입 시 vturn이 이미 저속 유지 중이라 리스크로 안 이어짐).
  PARAMS_REGISTRY 판단 변경 없음(NEEDS_VALIDATION 유지).
- 그 외: harsh_brake ADAS 활성 중 0건 8개 라우트 연속 재확인,
  turn_speed_violation 0건, steering_oscillation 10건 전부 기존
  오탐 패턴과 일치(신규 아님). MAX_SEGMENTS_PER_ROUTE 검증용
  패치-이후 로그는 이번에도 미확보(로그가 8/19, 패치는 8/20 00:57).
- FINDINGS.md/LAST_ANALYZED.md/PARAMS_REGISTRY.md 갱신 완료.
- **이 항목은 사용자 요청 "체크포인트 저장"에 따른 것 — 아래 미해결
  항목은 이번 세션에서도 착수하지 않았고 그대로 다음으로 이월됨.
  단, "커브 탈출 후 재가속 지연" 가설 검증은 위 개선 방향 3가지를
  다음 세션에서 이어서 진행할 것(신규 우선순위 항목 6번으로 아래
  추가).**

## 완료된 것 (2026-08-20, 260819-5 로그 분석, 사용자 "체크포인트 저장" 요청)
- 커밋 분석: HEAD f7b154638cf2 그대로, 신규 커밋 없음(확인만).
- 라우트 260819-5 분석 완료 — route5a(`ba55f880d1` seg25~39, x15seg,
  11.58km/899.7s, route3b/260819-4 직접 연속분) + route5b(신규
  `dc8bdc7d4d` seg0~4, x5seg, 1.35km/300.0s, 시내 저속/ADAS 비활성
  위주).
- **중요 발견(신규 미해결 항목으로 아래 목록에 추가): route
  `ba55f880d1`가 260819-3(seg0 추정)부터 260819-5(seg39)까지 끊김
  없이 40개 세그먼트로 이어진 뒤 rotate — MAX_SEGMENTS_PER_ROUTE=20
  패치(f7b154638cf2, 이미 원격 push 완료)가 이 드라이브 시점엔 디바이스에
  반영 안 됐을 가능성. PARAMS_REGISTRY.md FIXED→NEEDS_VALIDATION으로
  하향, FINDINGS.md [INVESTIGATING] 신규 항목 추가.**
- 그 외: harsh_brake ADAS 활성 중 0건 7개 라우트 연속 재확인,
  turn_speed_violation 0건. LEAD_ACQ_LOSS_GRACE_TIME: route5a real
  유실 1건(무해 해소, 원거리 트랙전환+비전노이즈 결합). route5b는
  real 유실 다수(29건) 확인됐으나 전부 cruiseEnabled=False 구간이라
  표본에서 제외 처리. dRel/vRel 원거리(90m+) 요동 노이즈 재확인(값
  변경 없음).
- FINDINGS.md/LAST_ANALYZED.md/PARAMS_REGISTRY.md 갱신 완료.
- **이 항목은 사용자 요청 "체크포인트 저장"에 따른 것 — 아래 미해결
  항목은 이번 세션에서도 착수하지 않았고 그대로 다음으로 이월됨
  (단, 신규 항목 5번 추가).**

## 완료된 것 (2026-08-20, 260819-4 로그 분석, 사용자 "체크포인트 저장" 요청)
- 라우트 260819-4 분석 완료: route ID `ba55f880d1` seg5~24 (x20seg,
  19.0km/1200.2s) — 260819-3에서 분석한 route3b(같은 route ID, seg0~4
  추정)의 직접 연속분. HEAD f7b154638cf2(신규 커밋 없음), 코드 변경
  없음(관찰/분석만).
- 주요 결과: harsh_brake 22건 전부 단일 정차 이벤트(disengage/
  re-engage 교차검증 완료) — ADAS 활성 중 급제동 0건 5개 라우트
  연속 재확인. turn_speed_violation/cut-in/steering_oscillation
  전부 0건. LEAD_ACQ_LOSS_GRACE_TIME 단기유실 8건 중 세그먼트 경계
  아티팩트 1건뿐, 나머지 7건 진짜 유실(0.5s 초과 5건) — 실사례 비중
  근거 추가. 신규: dRel/vRel 대형 불연속 점프 26건이 LeadBlend 게이트
  임계값(CLOSER_JUMP_DIST 8m/BIG_JUMP_DIST 15m) 초과함에도 급제동 없이
  무해 해소 — 260819-2 seg24 문제사례와 대조되는 반례 데이터 확보.
- FINDINGS.md/LAST_ANALYZED.md/PARAMS_REGISTRY.md 갱신 완료.
- **이 항목은 사용자 요청 "체크포인트 저장"에 따른 것 — 아래 미해결
  항목은 이번 세션에서도 착수하지 않았고 그대로 다음으로 이월됨.**

## 완료된 것 (2026-08-20, 260819-3 로그 분석)
- 라우트 260819-3 분석 완료. zip 안에 route ID가 다른 두 부팅
  세션이 섞여 있어 분리 추출:
  - route3a (`6ef53b224d`, x15seg, 15.58km/894.9s, avg 62.7km/h,
    ADAS 활성 91.7%)
  - route3b (`ba55f880d1`, x5seg, 3.53km/301.5s, avg 42.2km/h,
    ADAS 활성 86.8%)
  HEAD f7b154638cf2 (신규 커밋 없음, 코드 변경도 없음 — 순수 분석만).
- 주요 결과: harsh_brake ADAS 활성 중 0건 계속 재확인,
  turn_speed_violation 0건 — 전반적으로 클린. extract_log.py 세그먼트
  경계 아티팩트 버그 13건 추가 재확인(기존 판단 재확인, 패치 여전히
  미적용). 저속 리드 대체 패턴 36m 점프 극단 사례 확보했으나 해당
  구간이 cruiseEnabled=False(운전자 수동 주차)라 제어 영향 없음 —
  가설 뒷받침 표본으로만 유효. steering_oscillation_detector 오탐
  2건 유형 확인(급커브 단일 S자 조향 / 운전자 수동 조작) — 탐지기
  개선 여지 기록만 하고 코드 작업은 안 함.
- FINDINGS.md/LAST_ANALYZED.md/PARAMS_REGISTRY.md 갱신 완료.

## 이전 세션에서 넘어온 미해결 항목 (2026-08-20, 260819-2 분석 세션)
아직 방향 결정만 하고 코드 작업 전 상태 그대로 — 이번 세션에서도
착수하지 않음. 다음 세션 시작 시 아래 중 무엇을 할지 사용자에게
다시 물어볼 것:
1. `extract_log.py` 세그먼트 경계 버그 패치
   (제안된 수정 방향: `process_segment()` 시작 시 `last_lead`를 매번
   False로 초기화하지 말고, 이전 세그먼트 처리 종료 시점 값을
   다음 세그먼트 호출로 carry-forward). 260819-3 분석에서도 13건
   추가로 아티팩트 확인돼 우선순위 여전히 유효함.
2. 고속/ADAS 활성 중 급감속 이벤트(260819-2 seg24, t=1505.78~1507.88)를
   dashcam 영상으로 교차검증 (실제로 그 시점에 느린 선행차/정체가
   있었는지 vs 오탐 트랙전환인지 확인 필요 — 사용자가 원본 dashcam
   mp4를 아직 안 올림, 지금까지 업로드된 zip들은 rlog만 포함)
3. LeadBlend에 vRel-only 불연속 감지 게이트 추가 검토
   (현재 CLOSER_JUMP_DIST/BIG_JUMP_DIST는 dRel 점프만 봄 — vRel/vLead
   불연속만 있고 dRel은 연속인 케이스 대응 로직 설계 필요, 아직 설계
   착수 안 함)
4. (신규, 낮은 우선순위) `steering_oscillation_detector` 오탐 개선 —
   저속(<8m/s) 구간 및 큰 진폭(>15°)의 완만한 단일 왕복을 실제
   고주파 진동과 구분하는 조건 추가 검토
5. (정정됨, 260819-5 세션) MAX_SEGMENTS_PER_ROUTE=20 실기기 미반영
   의심을 처음 제기했다가 오판으로 정정 — 260819-5 로그(8/19
   12:41~13:00)가 패치 커밋 f7b154638cf2(8/20 00:57)보다 이전 시점이라
   40개 동작이 정상이었음. **다음 실주행 로그(패치 커밋 이후 기록된
   것)로 20개 단위 rotate 확인 필요** — 아직 미검증 상태 그대로,
   우선순위는 보통. 260819-6에서도 미확보(로그가 여전히 8/19).
6. (260819-6 세션 신규, 260819-7 세션에서 (a) 완료·부분 진행) "커브
   탈출 후 재가속 지연" 가설 — (a) leadStatus 필터+직선유지 조건은
   `curve_exit_no_accel_scan_v2`로 260819-7 세션에서 완료. 재스캔 결과
   3번째 오탐 패턴(vCruiseCluster 캡으로 가속 여지 자체가 없던 상황)
   신규 확인 — **다음 단계로 v3(목표속도 여유폭 필터) 추가 필요**,
   (b) route1~7 전체 재스캔은 아직 미착수(v3 완성 후 진행), (c) 개활지
   단일 커브 로그 요청은 보류(아직 필요성 판단 이르다).
7. (신규, 260819-7 세션) "커브 진입 중(탈출과 반대 방향) vturn 감속이
   곡률 조임 속도를 못 따라가 운전자가 개입" 가설 — 표본 1건(seg6
   t=434.70)뿐이라 결론 보류. 다음 세션 조치: 유사 패턴 스캔 헬퍼
   (disengage 직전 5초간 src=vturn 여부 체크) 신설 후 route1~7
   재스캔으로 표본 확보.

## 참고 — 코드 diff 상태
260819-8 세션: 코드 변경 없음(devnotes toolkit도 이번엔 수정 없이 기존
함수만 사용, ryu 레포도 변경 없음).
260819-7 세션: `toolkit/analysis_helpers.py`에 `curve_exit_no_accel_scan_v2`
함수 추가(devnotes 레포, ryu 코드 변경 아님 — push 시 FINDINGS 등과
함께 devnotes 커밋에 포함됨). ryu 레포 자체는 이번 세션 변경 없음.
위 1번(extract_log.py 패치)은 여전히 코드
작성 전, 방향만 제안된 상태. 6번은 (a)까지는 완료, v3(여유폭 필터)는
아직 코드 작성 전. 7번(진입 중 과소감속 스캔 헬퍼)도 아직 코드 작성
전, 방향만 제안된 상태. (260819-8 세션도 위 두 항목에 진전 없음 —
순수 고속도로 로그라 표본 부족.)
