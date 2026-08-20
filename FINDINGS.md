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
