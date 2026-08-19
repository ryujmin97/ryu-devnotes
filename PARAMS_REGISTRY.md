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
| speed_n_sources min() 선택 | 히스테리시스 없음 (매 프레임 단순 min) | atc/road/vturn/route/model 등 후보 중 크루즈 목표속도 소스 선택 | NEEDS_VALIDATION (2026-08-19 x16seg + 2026-08-20 x20seg(260819-1) 로그: 국도 완만한 커브뿐 아니라 73~113km/h 고속 커브 구간 전반에서 vturn↔road/model/route 재현, x20seg에서 A→B→A 플리커 49건 확인 — dwell-time/hysteresis 추가 우선순위 상승, FINDINGS.md 참고) |

## selfdrive/carrot/carrot_man.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| vturn_lookahead_horizon_s | 4.5s | 커브 조기감속 예측구간 | 검증됨 |
| vturn_decel_rc | 0.25s | 감속 저역통과 시정수 | 검증됨 |
| vturn_accel_rc | 0.6s | 가속복귀 저역통과 시정수 | 검증됨 |
| TARGET_LAT_A | 1.6 m/s^2 | 목표 횡가속도 기준 | - |

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
