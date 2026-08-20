# LAST_ANALYZED — 브랜치별 마지막 커밋 분석 지점

새 세션에서 "최신 커밋 분석"을 요청받으면, 여기 기록된 커밋 이후만
`git log <기록된 해시>..HEAD`로 훑는다. 매번 최근 30개를 처음부터
다시 보지 않기 위함.

분석을 마칠 때마다 이 파일을 갱신한다 (해시 + 날짜 + 한줄 메모).

---

## c3-ms-dev
- last_analyzed_commit: `4c15987`
- date: 2026-08-20
- note: 4c15987 = 7차 세션에서 만든 vturn_lookahead_horizon_s 4.5s→6.5s
  패치(로컬 커밋 `1827c1e`)가 `git am`+`git push`로 반영된 커밋
  (`b403d52..4c15987`). 신규 분석 대상 아님(우리가 만든 패치), 참고용
  기록만.
- note: 8dbed620887b 이후 신규 커밋 1개(3660091, CarrotWeb gdrive 재진입/
  핸드셰이크 타임아웃) 확인했으나 이미 FINDINGS.md에 기록된 이슈라 재분석
  생략. 대신 x11seg 실주행 로그 분석 수행 — LEAD_ACQ_LOSS_GRACE_TIME
  NEEDS_VALIDATION 갱신, 정지 리드 추종 클린 케이스 기록. 상세는
  FINDINGS.md/PARAMS_REGISTRY.md 참고.
  같은 날 x16seg(16.44km/955s) 라우트 추가 분석 — 종방향 harsh brake
  15건 전부 운전자 개입(cruiseEnabled=False) 확인해 ADAS 활성구간
  급제동 0건, 근접 컷인 유사 이벤트 매끈한 반응 확인, carrot_serv.py
  speed_n_sources min() 히스테리시스 부재로 인한 src/desiredSpeed
  플리커 신규 발견, LEAD_ACQ_LOSS_GRACE_TIME 5번째 초과 샘플 확보.
  코드 변경 없음(관찰/분석만).
  2026-08-20: f7b1546(system/loggerd MAX_SEGMENTS_PER_ROUTE 40->20,
  carrotweb 로그탭 라우트당 세그먼트 수 축소 요청 대응) master가 patch
  적용 + push 완료, HEAD 반영. 실기기 검증(라우트 20개 단위 분할 확인,
  carrotweb 로그탭 표시 확인)은 아직 NEEDS_VALIDATION — FINDINGS.md
  참고.
  2026-08-20 (같은 날, 2차): 신규 커밋 없음(HEAD f7b154638cf2 그대로) —
  라우트 260819-1(x20seg, 25.6km/1200s) 실주행 로그 분석 수행. 코드
  변경 없음(관찰/분석만). 주요 발견 2건: (1) LEAD_ACQ_LOSS_GRACE_TIME
  0.5s 초과 사례 6~7건 신규 확보(유실시간 최대 2.46s로 확대) + 정차열
  중 dRel 8~12.5m 감소 재포착 신규 패턴(리드 대체 의심). (2)
  speed_n_sources 플리커가 국도뿐 아니라 고속 커브 전반에서 재현
  (A→B→A 패턴 49건). harsh brake/turn violation/steering
  oscillation/cut-in은 전부 클린. 상세는 FINDINGS.md/PARAMS_REGISTRY.md
  참고.

  2026-08-20 (3차): 라우트 260819-2(x20seg, 10.29km/1199.9s, 시내/정체
  위주, avg 30.9km/h) 실주행 로그 분석. 코드 변경 없음(관찰/분석만).
  주요 발견 2건: (1) extract_log.py가 세그먼트 파일마다 leadStatus를
  False로 강제 초기화하는 버그 확인 — 순간유실 16건 전부 세그먼트 경계와
  타임스탬프 완전 일치(diff=0.000s), 실제 리드 유실 아닌 도구 아티팩트.
  LEAD_ACQ_LOSS_GRACE_TIME 관련 과거 누적 증거 재검토 필요 (PARAMS_REGISTRY
  하향 조정). (2) seg24 t=1505.78~1507.88: 고속(112km/h) 순항 중 새 리드
  포착 후 leadDRel은 연속인데 leadVRel/leadVLead만 한 프레임 만에 불연속
  점프(-4.6→-26.2m/s) — 시스템 감속(-4.61m/s²까지 매끈히 상승)이 운전자
  급브레이크(-7.46m/s²) 개입으로 이어짐. TTC가 DANGER(2.5s) 문턱을 못
  넘은 채 반응 강도가 유지된 점, LeadBlend 게이트가 dRel 점프만 감지해
  이런 vRel-only 불연속을 놓칠 수 있는 점 신규 확인 — NEEDS_VALIDATION.
  그 외: harsh_brake 45건 전부 운전자 브레이크 개입 중(cruiseEnabled 무관),
  turn_speed_violation 0건, steering oscillation 0건, cut-in 12건 전부
  저속(<7m/s) 정체구간, speed_n_sources 플리커 330건(기존 이슈 재확인,
  신규 아님). 상세는 FINDINGS.md/PARAMS_REGISTRY.md 참고.

  2026-08-20 (4차): 신규 커밋 없음(HEAD f7b154638cf2 그대로) — 라우트
  260819-3 분석. zip 안에 route ID가 다른 두 부팅 세션이 섞여있어
  route3a(6ef53b224d, x15seg, 15.58km/894.9s)/route3b(ba55f880d1,
  x5seg, 3.53km/301.5s)로 분리 추출. 코드 변경 없음(관찰/분석만).
  harsh_brake ADAS 활성 중 0건 계속 재확인, turn_speed_violation 0건.
  extract_log.py 세그먼트 경계 아티팩트 13건 추가 재확인(패치 미적용
  상태 그대로). 저속 리드 대체 패턴 36m 점프 극단 사례 확보했으나
  해당 구간 cruiseEnabled=False(운전자 수동 주차)라 제어 영향 없음.
  steering_oscillation_detector 오탐 2건 유형 확인(급커브 단일 S자
  조향 vs 운전자 수동 조작) — 탐지기 개선 여지 기록. 상세는
  FINDINGS.md/PARAMS_REGISTRY.md 참고.

  2026-08-20 (5차): 신규 커밋 없음(HEAD f7b154638cf2 그대로) — 라우트
  260819-4(x20seg, route ID `ba55f880d1` seg5~24, 19.0km/1200.2s,
  route3b의 직접 연속분) 분석. 코드 변경 없음(관찰/분석만).
  harsh_brake 22건 전부 단일 정차 이벤트(disengage/re-engage로 교차
  검증) — ADAS 활성 중 급제동 0건 5개 라우트 연속 재확인.
  turn_speed_violation/cut-in/steering_oscillation 전부 0건.
  LEAD_ACQ_LOSS_GRACE_TIME: 단기 유실 8건 중 세그먼트 경계 아티팩트는
  1건뿐, 나머지 7건은 진짜 유실(0.5s 초과 5건 포함) — 재검토 판단에
  실사례 비중 근거 추가. 신규 관찰: dRel/vRel 대형 불연속 점프 26건이
  LeadBlend 게이트 임계값을 훨씬 초과함에도 급제동 없이 무해하게
  해소(260819-2 seg24의 문제 사례와 대조되는 반례). 상세는
  FINDINGS.md/PARAMS_REGISTRY.md 참고.

  2026-08-20 (6차, 260819-5): 신규 커밋 없음(HEAD f7b154638cf2 그대로) —
  라우트 260819-5 분석. route5a(`ba55f880d1` seg25~39, x15seg,
  route3b/260819-4 직접 연속분)+route5b(신규 `dc8bdc7d4d` seg0~4,
  x5seg). 코드 변경 없음(관찰/분석만). route `ba55f880d1`가
  seg0(260819-3)~seg39(260819-5)까지 끊김 없이 40개 세그먼트로 이어진
  걸 보고 MAX_SEGMENTS_PER_ROUTE=20 패치 실기기 미반영 반증으로 처음
  판단했으나, **정정**: 로그 시각(8/19 12:41~13:00)이 패치 커밋
  f7b154638cf2(8/20 00:57)보다 이전이라 40개 동작이 정상이었음(오판,
  FINDINGS.md [WONTFIX] 정정 기록 — 진짜 검증은 패치 이후 로그로
  다시 필요). 그 외: harsh_brake ADAS 활성 중 0건 7개 라우트
  연속 재확인, turn_speed_violation 0건, LEAD_ACQ_LOSS_GRACE_TIME
  route5a real 1건(무해 해소), route5b는 real 유실 다수 확인됐으나
  전부 cruiseEnabled=False 구간이라 표본 부적합. dRel/vRel 원거리
  요동 노이즈 재확인. 상세는 FINDINGS.md 참고.

  2026-08-20 (7차, 260819-6): 신규 커밋 없음(HEAD f7b154638cf2 그대로) —
  라우트 260819-6 분석. route6a(`dc8bdc7d4d` seg5~22, x18seg, route5b
  직접 연속분, 8.57km/1043.2s)+route6b(신규 `f7e0bb3abd` seg0~1,
  x2seg, 0.4km/121.6s). 코드 변경 없음(관찰/분석만). **주 목적: 사용자가
  제기한 "커브 탈출 후 재가속 지연" 가설을 `curve_exit_no_accel_scan`
  으로 검증 시도했으나, 후보로 뽑힌 이벤트를 프레임 단위로 대조한
  결과 전부 오탐(선행차 추종 정차 감속 또는 S자 연속커브 재진입을
  "커브 탈출"로 오판)으로 확인 — 가설을 확증도 반증도 못함. 스캔
  도구에 leadStatus 필터/직선 지속시간 조건 추가하는 개선 방향
  제안(코드 미착수).** 그 외: harsh_brake ADAS 활성 중 0건 8개 라우트
  연속 재확인, turn_speed_violation 0건. LEAD_ACQ_LOSS_GRACE_TIME
  스캔에서 6~36초짜리 긴 유실 다수 신규 발견했으나 개별 대조 결과
  전부 무해(개활도로 선행차 소실 또는 저속 코너 시야이탈, vturn이
  코너 중엔 이미 저속 유지 중이라 리스크 없음) — PARAMS_REGISTRY
  판단 변경 없음. MAX_SEGMENTS_PER_ROUTE 검증용 로그(패치 커밋 이후
  기록분)는 이번에도 미확보(로그 시각이 패치보다 이전). 상세는
  FINDINGS.md 참고.

  2026-08-20 (8차, 260819-7): 신규 커밋 없음(HEAD f7b154638cf2 그대로) —
  라우트 260819-7 분석. route `f7e0bb3abd` seg2~23(x22seg, route6b의
  직접 연속분, 32.73km/1319.9s, avg 89.3km/h — 이번 로그부터 처음으로
  고속도로 위주 구간 확보). 코드 변경 없음(관찰/분석만, 단
  `toolkit/analysis_helpers.py`에 `curve_exit_no_accel_scan_v2` 함수
  추가는 완료). **주 목적: "커브 탈출 후 재가속 지연" 가설 재검증.**
  v2(leadStatus 필터+직선유지 조건) 스캔으로 오탐 1건 추가 배제했으나,
  남은 후보를 프레임 대조한 결과 3번째 오탐 패턴(vCruiseCluster 캡으로
  이미 목표속도 근접, 가속할 여지 자체가 없었던 상황) 신규 확인 — 가설은
  이번에도 확증/반증 못함, v3 개선 방향(목표속도 여유폭 필터) 제안.
  부가: 커브 진입 중(아직 안 끝난 상태) vturn 감속이 진행 중인데 운전자가
  브레이크로 개입한 신규 패턴 1건 발견(표본 1건, INVESTIGATING) — 곡률
  조임 속도 대비 vturn_decel_rate/lookahead가 충분한지 의문 제기.
  코드 리딩 중 PARAMS_REGISTRY의 vturn_decel_rc/accel_rc 값이 구버전
  기록(0.25/0.6)이라 현재 코드(0.15/0.15, a94a58b 재설계 반영)와
  불일치함을 확인해 정정. 그 외: harsh_brake 12건 중 11건은 기존 패턴과
  동일(disengage 인접), 1건은 위 신규 패턴. turn_speed_violation 0건,
  steering_oscillation 0건. LEAD_ACQ_LOSS_GRACE_TIME 0.5s 초과 6건
  전부 고속 개활도로/완만한 커브 상황 무해 재확인. 상세는 FINDINGS.md/
  PARAMS_REGISTRY.md 참고.

  2026-08-20 (9차, 260819-8, 사용자 "체크포인트" 요청): 신규 커밋
  없음(HEAD f7b154638cf2 그대로) — 라우트 260819-8 분석. route8a
  (`f7e0bb3abd` seg24~39, x16seg, 260819-7 직접 연속분, 27.27km/959.9s,
  avg 102.3km/h) + route8b(신규 `da28883b75` seg0~4, x5seg,
  5.93km/272.0s, 시내 저속 혼합). 코드 변경 없음(관찰/분석만).
  **route8a는 harsh_brake/turn_speed_violation/steering_oscillation/
  cut-in/curve_exit_v2 전부 0건 — 지금까지 중 처음으로 전 카테고리
  클린한 순수 고속도로 라우트.** 커브 콘텐츠 자체가 거의 없어(curvature
  threshold 초과 39/19145 프레임) 커브 관련 가설 2건(탈출 후 재가속
  지연/진입 중 과소감속) 모두 이번 세션엔 진전 없음. route8b harsh_brake
  16건은 disengage 직후 저속 정차 감속으로 기존 패턴과 동일(신규 아님).
  LEAD_ACQ_LOSS_GRACE_TIME: route8a에서 기존 최대(2.46s)를 크게 넘는
  긴 유실(최대 222.85s) 다수 확인했으나 harsh_brake 등 다른 지표가
  전부 0건이라 고속도로 선행차 부재로 판단, 무해. MAX_SEGMENTS_PER_ROUTE
  관련 참고 관찰 추가(route `f7e0bb3abd`가 정확히 40세그먼트 후 boot
  변경과 함께 종료 — 캡 발동인지 우연한 재부팅 겹침인지 로그만으론
  구분 불가, 여전히 패치 이전 시점이라 미검증). 상세는 FINDINGS.md
  참고. **사용자 요청으로 이번 세션은 여기서 체크포인트 저장** —
  WIP.md 참고.

  2026-08-20 (6차): 신규 커밋 1개 — `b403d52` (long_mpc.py, vision-only
  원거리 리드 closing-rate 크로스체크, VISION_CLOSING_RATE_TAU=1.0s/
  MIN_TIME=0.5s 신설). 사용자가 실차 `git am` + push 완료 확인
  (`f7b1546..b403d52`). 코드 상세는 FINDINGS.md "[PATCH_APPLIED,
  NEEDS_VALIDATION] 비전-only 원거리 리드 closing-rate 크로스체크"
  참고. **aEgo 실측 대조는 아직 미완료 — 다음 세션 최우선 과제.**

## c3-ms
- last_analyzed_commit: (아직 분석 안 함)
- date: -
- note: -

## c3-atune
- last_analyzed_commit: (아직 분석 안 함)
- date: -
- note: -
