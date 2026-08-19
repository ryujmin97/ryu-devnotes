# FINDINGS — 이슈 / 검증 상태 누적 기록

세션이 끝나도 남아야 하는 것만 여기 기록한다. 대화 내용 전체를 옮기지 말고,
"무엇을 발견했고, 지금 상태가 뭔지"만 짧게. 새 세션 시작할 때 이 파일을
먼저 훑으면 이미 끝난 걸 다시 분석하지 않아도 된다.

각 항목 형식:
```
## [상태] 제목 (발견일, 관련 커밋/파일)
- 증상:
- 원인:
- 조치: (수정됨 / 검토중 / 보류)
- 근거 로그: (있으면 라우트명 + 타임스탬프)
```
상태 태그: `[FIXED]` 수정 완료 / `[INVESTIGATING]` 원인 분석 중 /
`[NEEDS_VALIDATION]` 코드는 있으나 실도로 검증 필요 / `[WONTFIX]` 보류

---

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
