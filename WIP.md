# WIP — 중단 지점 체크포인트

세션 정상 종료가 아니라 사용자 요청으로 여기서 저장한 중단 지점.
다음 세션(다른 계정 포함)은 여기부터 이어받는다.

---

## 완료된 것 (2026-08-20, 이번 세션 — 260819-5 로그 분석, 사용자 "체크포인트 저장" 요청)
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
   우선순위는 보통.

## 참고 — 코드 diff 상태
이번 세션 코드 변경 없음. 위 1번(extract_log.py 패치)은 여전히 코드
작성 전, 방향만 제안된 상태.
