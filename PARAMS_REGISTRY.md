# PARAMS_REGISTRY — 튜닝 상수 레지스트리

여러 파일에 흩어진 튜닝 상수를 한곳에서 추적. 값이 바뀌면 이 표도 같이
갱신. "검증상태" 컬럼이 NEEDS_VALIDATION인 항목은 로그 분석 요청 시
우선순위로 챙길 것.

## selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| MARGIN_ACCEL_GATE_FULL / NONE | 1.5 / 1.0 | 여유거리 클수록 aLead 흔들림 무시 | NEEDS_VALIDATION |
| LEAD_ACQ_RAMP_TIME | 5.0s | 리드 인식 후 선제감속 하한선 도달 시간 | NEEDS_VALIDATION (2026-08-18 로그로 검증 실패, 데이터 부족) |
| LEAD_ACQ_MIN_V_EGO | 3.0 m/s | 이 속도 미만 미적용 | - |
| LEAD_ACQ_CONFIRM_TIME | 0.2s | 블립 무시, 램프 시작 조건 | - |
| LEAD_ACQ_LOSS_GRACE_TIME | 0.5s | 순간유실 허용 시간 | - |
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

## selfdrive/carrot/carrot_man.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| vturn_lookahead_horizon_s | 4.5s | 커브 조기감속 예측구간 | 검증됨 |
| vturn_decel_rc | 0.25s | 감속 저역통과 시정수 | 검증됨 |
| vturn_accel_rc | 0.6s | 가속복귀 저역통과 시정수 | 검증됨 |
| TARGET_LAT_A | 1.6 m/s^2 | 목표 횡가속도 기준 | - |

---
갱신 이력:
- 2026-08-18: 최초 작성 (c3-ms-dev HEAD 8dbed620887b 기준)
