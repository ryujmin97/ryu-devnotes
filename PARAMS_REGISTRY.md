# PARAMS_REGISTRY — 튜닝 상수 레지스트리

여러 파일에 흩어진 튜닝 상수를 한곳에서 추적. 값이 바뀌면 이 표도 같이
갱신. "검증상태" 컬럼이 NEEDS_VALIDATION인 항목은 로그 분석 요청 시
우선순위로 챙길 것.

## selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| MARGIN_ACCEL_GATE_FULL / NONE | 1.5 / 1.0 | 여유거리 클수록 aLead 흔들림 무시 | NEEDS_VALIDATION |
| LEAD_ACQ_RAMP_TIME | 5.0s | 리드 인식 후 선제감속 하한선 도달 시간 | NEEDS_VALIDATION (2026-08-18 x12seg 로그에서 첫 적합 사례 확보, seg10 t=657.39 — 매끈한 감속으로 긍정적. 표본 1건, 추가 검증 필요) |
| LEAD_ACQ_MIN_V_EGO | 3.0 m/s | 이 속도 미만 미적용 | - |
| LEAD_ACQ_CONFIRM_TIME | 0.2s | 블립 무시, 램프 시작 조건 | - |
| LEAD_ACQ_LOSS_GRACE_TIME | 0.5s | 순간유실 허용 시간 | **재검토 필요** (2026-08-20, 260819-2 분석 중 extract_log.py가 세그먼트 경계마다 leadStatus를 인위적으로 False 리셋하는 도구 버그 확인 — 해당 라우트 순간유실 16건 전부 세그먼트 경계와 diff=0.000s로 정확히 일치, 실제 유실 아닌 추출 아티팩트. 과거 누적 증거(x11seg 4건+x16seg 1건+x20seg(260819-1) 6~7건)도 세그먼트 경계 여부 재대조 필요 — 특히 0.3s 이하 짧은 유실은 아티팩트 의심, 1s+ 긴 유실은 실사례 가능성 유지. 상세는 FINDINGS.md 참고, extract_log.py 수정 제안은 미적용 상태) |
| LEAD_ACQ_TTC_DANGER | 2.5s | TTC 이하면 frac=1.0 즉시 | NEEDS_VALIDATION |
| LEAD_ACQ_TTC_CAUTION | 6.0s | TTC 이상이면 TTC 성분 미개입 | NEEDS_VALIDATION |
| VISION_CLOSING_RATE_TAU | 1.0s | vision-only dRel 미분 접근속도 저역통과 시정수 | NEEDS_VALIDATION (2026-08-20 신규, 코드만 완료·aEgo 실측 대조 미완료) |
| VISION_CLOSING_RATE_MIN_TIME | **0.5s** (정정, 최초 1.0s에서 단축) | 이 시간 이상 연속추적 후에만 dRel 미분 TTC 신뢰 | NEEDS_VALIDATION (2026-08-20, 사용자 피드백으로 1.0s→0.5s 단축 — TAU=1.0s는 유지라 0.5s 시점엔 필터가 약 39%만 수렴한 상태, danger 판정이 다소 보수적일 수 있음. 실측 후 추가 단축/TAU 조정 여지) |

## selfdrive/controls/radard.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| LEAD_BLEND_TTC_DANGER | 2.5s | TTC 이하 즉시 반영 | FIXED (route1/2 검증됨) |
| LEAD_BLEND_DANGER_HOLD | 0.3s | 위험 판정 후 스무딩 우회 유지 시간 | - |
| LEAD_BLEND_SAFE_DIST_TIME | 0.35s | 안전방향 블렌딩 시정수 | - |
| LEAD_BLEND_CLOSER_JUMP_DIST | 8.0m | 이 이상 급접근 점프 시 즉시 반영 | 검증됨 (route1 seg13 t=794s, 표본 1건) |
| LEAD_BLEND_BIG_JUMP_DIST | 15.0m | 이 이상 안전방향 점프는 즉시 스냅 | 검증됨 (route1 t=1388~1390s / route2 t=825~827s, 표본 1건씩) |
| LEAD_LOST_GRACE_TIME | 0.6s | 리드 순간유실 홀드 시간 | - |
| CUTOUT_DPATH_THRESH | 2.0m | 컷아웃 판정 dPath 임계값 | NEEDS_VALIDATION |
| CUTOUT_VREL_GATE | -0.5 m/s | 컷아웃 판정 vRel 게이트 | NEEDS_VALIDATION |

## selfdrive/carrot/carrot_functions.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| lcAggressiveMaxTime | 8.0s | 차선변경 중 좁은 tFollow 유지 안전상한 (runaway guard) | FIXED/검증됨 (route1 422→0건, route2 363→0건) |
| tFollowLaneChangeHoldTime | 1.0s | 차선변경 종료 후 좁은 tFollow 고정 유지 | - |
| tFollowLaneChangeBlendTime | 1.5s | 이후 정상값으로 복귀하는 시간 | - |

## selfdrive/carrot/carrot_serv.py

| 상수/구조 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| speed_n_sources min() 선택 | 히스테리시스는 여전히 없음. **model 후보만** desiredCurvature 기반 게이팅 추가(아래 두 행) | atc/road/vturn/route/model 등 후보 중 크루즈 목표속도 소스 선택 | NEEDS_VALIDATION (2026-08-19 x16seg + 2026-08-20 x20seg(260819-1) 로그: 국도 완만한 커브뿐 아니라 73~113km/h 고속 커브 구간 전반에서 vturn↔road/model/route 재현, x20seg에서 A→B→A 플리커 49건 확인, 우세 쌍 vturn↔model. 2026-08-20(9차): vturn↔model 쌍에 한해 model 후보를 desiredCurvature 기반으로 게이팅하는 패치 작성(미적용/미검증). atc/road/route 등 다른 쌍의 히스테리시스는 여전히 미해결로 남음, FINDINGS.md 참고) |
| model_turn_straight_thresh | 0.002 rad/m | desiredCurvature가 이 미만이면 "거의 직선" 프레임 (기존 로그분석 threshold와 동일값 재사용) | ⚠️ RISK_IDENTIFIED (2026-08-20 도입, 실차 적용 완료(`2226db7`) — 11차 코드 재검토에서 위험 발견: desiredCurvature는 "현재" 곡률이라 커브 진입 전 직선 구간에서도 threshold 미만이 되므로, model의 사전감속(lookahead) 기여까지 같이 배제될 수 있음. FINDINGS.md 참고, 패치 방향은 논의됐으나 미작성) |
| model_turn_straight_hold_sec | 0.6s | 이 시간 이상 연속 직선이어야 model 후보를 min()에서 배제 | ⚠️ RISK_IDENTIFIED (상동 — thresh와 동일 위험 공유, FINDINGS.md 참고) |

## selfdrive/carrot/carrot_man.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| vturn_lookahead_horizon_s | **8.0s** (정정, 4.5s→6.5s→8.0s 2단계 확대) | 커브 조기감속 예측구간 | NEEDS_VALIDATION (2026-08-20, 1차 4.5s→6.5s push 완료(`4c15987`) 후 같은 세션에서 근거 사례(260819-7 seg6, 조임 지속시간 8.6s)를 더 가깝게 커버하기 위해 2차 6.5s→8.0s(`1fca82f`, push 완료). 8.0s도 8.6s보다 근소하게 짧음. 두 단계 모두 push는 완료됐으나 실차 검증 없음, FINDINGS.md 참고) |
| vturn_decel_rc | **0.15s** (정정, 기존 0.25s는 구버전 값) | 감속 저역통과 시정수(모델 노이즈 제거용, 감속 프로파일 자체는 물리공식이 결정) | 검증됨(2026-08-20, 260819-7 세션 코드 직접 확인 — a94a58b 커밋에서 물리공식 기반으로 재설계되며 값도 변경됨, 기존 표는 ab156ea 시점 값이라 최신화) |
| vturn_accel_rc | **0.15s** (정정, 기존 0.6s는 구버전 값) | 가속복귀 저역통과 시정수 | 검증됨(상동, 260819-7 세션 정정) |
| TARGET_LAT_A | 1.6 m/s^2 | 목표 횡가속도 기준(autoCurveSpeedAggressiveness로 배율 적용) | - |
| vturn_safe_time | 1.0s | 목표속도 여유 도달 시간(방지턱 AutoNaviSpeedBumpTime과 동일 기본값) | - (2026-08-20 신규 발견, 260819-7) |
| vturn_decel_rate | 1.2 m/s² | 방지턱 물리공식 기반 커브 감속률(AutoNaviSpeedDecelRate=120 동일값) | NEEDS_VALIDATION (2026-08-20 신규 발견, 260819-7 — 조여드는 커브 중 운전자 개입 표본 1건에서 이 값이 곡률 증가 속도 대비 충분한지 의문 제기됨, FINDINGS.md [INVESTIGATING] 참고) |

## selfdrive/carrot/server/gdrive.py (CarrotWeb Drive 업로드)

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| _HANDSHAKE_TIMEOUT | total=20s / sock_connect=10s / sock_read=15s | 토큰갱신·폴더조회생성·resumable세션오픈 전용 타임아웃(청크 PUT의 관대한 타임아웃과 분리) | NEEDS_VALIDATION (2026-08-18 신설, 실기기 네트워크 끊김 재현 검증 필요) |
| _UPLOAD_TIMEOUT | total=1800s / sock_connect=30s / sock_read=300s | 실제 파일 청크(8MB) PUT 전송용 (핸드셰이크 요청에는 더 이상 안 씀) | 기존값 유지 |
| UPLOAD_CHUNK_SIZE | 8MB | resumable 업로드 청크 크기 | - |

## system/loggerd/logger.cc

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| MAX_SEGMENTS_PER_ROUTE | 20 (기존 40) | 라우트당 최대 세그먼트 개수, 도달 시 새 라우트로 회전 (라우트당 최대 길이: 세그먼트 1개=1분 기준 약 20분, 기존 40분) | NEEDS_VALIDATION (2026-08-20, 260819-5 로그에서 route `ba55f880d1`가 seg0~39까지 40개 단위로 이어진 걸 실기기 미반영으로 오판했다가 정정 — 해당 로그(8/19 12:41~13:00)가 패치 커밋 f7b154638cf2(8/20 00:57)보다 이전이라 40개 동작이 정상. 진짜 검증은 패치 커밋 이후 기록된 로그로 다시 필요. 상세: FINDINGS.md [WONTFIX](정정 기록)) |

## 비전 리드 트래킹 노이즈 (신규 관찰, 특정 상수 아님)

| 항목 | 관찰값 | 용도 | 검증상태 |
|---|---|---|---|
| leadDRel 프레임당(≤0.3s) 급점프(≥8m) 발생빈도 | ~46건/722s (약 15초당 1회) | LeadBlend closer_jump/big_jump 게이트 발동 빈도 추정 | NEEDS_VALIDATION (2026-08-18 x12seg, 컨트롤 영향은 대부분 미미했으나 누적 확인 필요) |

---
- 2026-08-20: 260819-2 로그 분석 — LEAD_ACQ_LOSS_GRACE_TIME 근거였던 순간유실
  사례 중 상당수가 extract_log.py 세그먼트 경계 아티팩트로 확인돼
  "재검토 필요"로 하향/보류 조정 (상세: FINDINGS.md)
- 2026-08-20: 260819-3 로그(route3a+3b) 분석 — extract_log.py 세그먼트
  경계 아티팩트 버그 13건 추가 재확인(값 변경 없음, "재검토 필요"
  상태 유지). harsh_brake/turn_speed_violation 계속 클린 재확인.
- 2026-08-20: 260819-5 로그(route5a+5b) 분석 — MAX_SEGMENTS_PER_ROUTE
  실기기 미반영 "반증"으로 처음 기록했다가 정정: 로그가 패치 커밋보다
  이전 시점이라 40개 동작이 정상이었음(오판, 상세 FINDINGS.md). 검증
  상태는 NEEDS_VALIDATION 그대로(패치 이후 로그로 재확인 필요).
  LEAD_ACQ_LOSS_GRACE_TIME real 유실 route5b 다수 확인됐으나 전부
  cruiseEnabled=False라 표본 부적합 처리. 비전 원거리 리드 노이즈
  패턴 재확인(값 변경 없음).
  저속 리드 대체 패턴 극단 사례(36m 점프) 추가 확보했으나 해당 구간
  cruiseEnabled=False라 제어 영향 없음(상세: FINDINGS.md)
- 2026-08-20: 260819-4 로그(route3b 연속분, seg5~24) 분석 — 이번
  라우트는 경계 아티팩트가 8건 중 1건뿐이라 실사례 비중(7/8)이 높음,
  0.5s 초과 실유실 5건 확보(0.6~1.6s) — "재검토 필요"이지만 실사례
  존재 자체는 재확인됨. LeadBlend CLOSER_JUMP_DIST/BIG_JUMP_DIST
  게이트 관련: 게이트 임계값을 초과하는 대형 dRel/vRel 점프 26건이
  이번엔 전부 무해하게 해소(급제동 없음) — vRel-only 불연속이 항상
  위험으로 이어지진 않는다는 반례 데이터 추가(상세: FINDINGS.md)
- 2026-08-20: 260819-6 로그(route6a+6b) 분석 — LEAD_ACQ_LOSS_GRACE_TIME
  6~36초짜리 긴 유실 신규 발견(기존 최대 2.46s 대비 훨씬 김)했으나
  개별 대조 결과 전부 무해(개활도로 선행차 소실/저속 코너 시야이탈)
  — 상태 NEEDS_VALIDATION 유지, 시급성 낮음으로만 기록. 별건: 사용자
  제기 "커브 탈출 후 재가속 지연" 가설 검증 시도 — `curve_exit_no_accel_scan`
  기본 임계값이 시내/연속커브 도로에서 오탐(선행차 추종 정차/S자
  재진입을 커브탈출로 오판) 다수 발생해 이번 로그로는 가설 확증/반증
  둘 다 못함. 도구 개선 방향(leadStatus 필터, 직선 지속시간 조건)
  제안만 하고 코드 작업은 미착수(상세: FINDINGS.md)
- 2026-08-20: 260819-7 로그(고속도로 위주, 32.7km/1319.9s) 분석 —
  `curve_exit_no_accel_scan_v2` 신설(leadStatus 필터+직선유지 조건),
  4건→3건으로 감소했으나 남은 1건도 프레임 대조 결과 3번째 오탐 패턴
  (vCruiseCluster 캡으로 이미 목표속도 근처라 가속 여지가 애초에 없었던
  경우)으로 판명 — 가설 검증 여전히 미완료, v3 개선 방향(목표속도 여유폭
  필터) 제안. vturn_decel_rc/accel_rc 값 정정(0.25/0.6→0.15/0.15,
  코드 직접 확인). vturn_decel_rate=1.2m/s²/vturn_safe_time=1.0s 신규
  등록. 그 외: harsh_brake 12건 중 11건 disengage 인접(운전자 개입) 확인,
  1건은 진행 중인 vturn 감속 커브 도중 개입한 새 패턴(표본 1건,
  INVESTIGATING). turn_speed_violation 0건. LEAD_ACQ_LOSS_GRACE_TIME
  0.5s 초과 6건 모두 고속 개활도로/완만한 커브 상황 무해 재확인. 상세는
  FINDINGS.md 참고.

갱신 이력:
- 2026-08-18: 최초 작성 (c3-ms-dev HEAD 8dbed620887b 기준)
- 2026-08-18: x12seg 로그 분석 반영 (LEAD_ACQ_RAMP_TIME 첫 검증 사례,
  비전 리드 트래킹 노이즈 빈도 신규 관찰 항목 추가)
- 2026-08-18: CarrotWeb gdrive._HANDSHAKE_TIMEOUT 신설 (Drive 업로드
  진행률 번갈아 뜨는 버그 수정 관련, FINDINGS.md 참고)
- 2026-08-19: LEAD_ACQ_LOSS_GRACE_TIME NEEDS_VALIDATION으로 갱신
  (x11seg 로그 실측 플리커 4건 근거, FINDINGS.md 참고)
- 2026-08-20: system/loggerd/logger.cc MAX_SEGMENTS_PER_ROUTE 40 -> 20
  신설 (carrotweb 로그탭 라우트 세그먼트 수 축소 요청, FINDINGS.md 참고)
- 2026-08-20: 260819-8 로그 분석 — 값 변경 없음. LEAD_ACQ_LOSS_GRACE_TIME/
  MAX_SEGMENTS_PER_ROUTE 둘 다 NEEDS_VALIDATION 유지(고속도로 라우트에서
  긴 유실 다수 확인됐으나 전부 무해 재확인, MAX_SEGMENTS_PER_ROUTE는
  route ID 종료가 캡 발동인지 재부팅 우연인지 불명확한 참고 관찰만
  추가). 상세는 FINDINGS.md 참고.
- 2026-08-20 (신규 세션): VISION_CLOSING_RATE_TAU/MIN_TIME 신설 —
  vision-only 원거리 리드 closing-rate 크로스체크 패치(commit
  `b403d52`, 실차 `git am` + push 완료). 8개 zip 크로스오버
  분석(VISION_RADAR_CROSSOVER.md) 최우선 후보 5건 + 사용자 실주행
  체감 보고("카메라 인식 시점부터 감속 없다가 레이더 확인 순간부터
  감속") 기반 설계. aEgo 실측 대조는 아직 미완료 — 다음 세션에서 최우선
  후보 5건 세그 재업로드받아 검증 필요(FINDINGS.md 신규 항목 참고).
  같은 세션 내 사용자 피드백으로 MIN_TIME 1.0s→0.5s 단축(반응 지연이
  길다는 판단, TAU=1.0s는 유지).
- 2026-08-20 (7차): vturn_lookahead_horizon_s 4.5s→6.5s 확대(commit
  `4c15987`, ryu `c3-ms-dev` push 완료 `b403d52..4c15987`). "곡선 진입
  전 사전감속 부족으로 곡선 내 급감속" 사용자 보고 + 기존
  [INVESTIGATING] 260819-7 seg6 사례(조임 8.6s) 근거.
- 2026-08-20 (8차, 같은 트랙 이어감): 1차 push(`4c15987`) 확인 직후
  사용자가 6.5s→8.0s 재확대 요청(근거 사례 조임 8.6s에 더 근접하게).
  patch(`1fca82f`, push 완료). `vturn_lookahead_horizon_s`가
  "감속 소요시간"이 아니라 "커브 후보 스캔 지평선"이며, 방지턱과 동일한
  거리기반 서서히-감속 프로파일은 `vturn_decel_rate`/`vturn_safe_time`
  담당이라는 점 사용자에게 설명. 실차 검증 미완료 — 다음 세션 최우선.
- 2026-08-20 (10차): screenrecord "정지 시 마지막 1분 clip 자동 생성"
  기능 신규 (튜닝 상수 아님, 상수 없음 — clip 길이는 코드에 하드코딩
  `-sseof -60`). 실차 `git am` + push 완료(commit `0f7575f`,
  `2226db7..0f7575f`). 실측 검증(clip 생성 여부/길이/ffmpeg 경로)은
  아직 남음. 상세는 WIP.md 참고.
