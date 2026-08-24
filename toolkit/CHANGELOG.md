# toolkit/ CHANGELOG

새 도구 추가/기존 도구 함수 추가·변경 시 날짜 + 한 줄 요약을 여기에
남긴다. `README.md`도 같이 갱신할 것.

## 2026-08-25 (63차 계속10 (b))
- `replay_vision_rate_integrated.py` 신규 — "로직단위 시뮬레이션 vs
  실제 통합 코드" 최종 대조용 범용 툴. `long_mpc.py` update()의 vision
  closing-rate 블록을 재구현하지 않고 마커 기준으로 문자 그대로 잘라와
  exec()으로 재생. seg3/seg14로 방안E(63차 계속9/10) 검증 — 로직단위
  결론(0.209/0.678)과 실제 코드 재생 결과(0.205/0.671) 거의 일치,
  drift 없음 확정. 이전엔 매 세션 `work/`에 1회용 스크립트로 만들고
  버려졌던 패턴(sim_e.py, replay_drel_discontinuity_real.py 등)을
  이번에 toolkit 정식 편입 — 향후 long_mpc.py 다른 블록 재검증 시도
  이 스크립트의 마커 교체 방식을 재사용 가능.

## 2026-08-24 (60차 계속4)
- `sim_vision_track_a_dpath.py` 신규 — 58차3번 A(tentative 조기등록)
  재설계 합성검증. dRel jitter 게이트만으론 옆차로에서 안정적으로
  유지되는 차량(dPath는 안 변함)을 못 거르는 설계 허점을 발견해
  dPath 절대값 게이트(1.75m)+jitter 게이트(1.5m) 이중 구조로 수정.
  5개 시나리오 전부 PASS(정지앞차 조기등록 유지/옆차선 승격 차단/
  dPath 요동 방지/중앙값필터 스냅 흡수/저prob 회귀). radard.py
  패치 적용·push 완료(`a75c5cc`), 실차검증 대기. WIP.md 60차 계속4
  항목 참고.

## 2026-08-23 (58차 3번 후속수정 — 오늘 커밋 5개 검증 도구 정리)
- **`sim_vision_gate_v_lead.py` 신규**: 58차 1번(카메라 인식 감속 강화,
  커밋 `1f0d292`/`e17e078`) 검증 도구. VisionTrack 게이트 완화(0.97/20
  → 0.70/10) before/after 비교 + long_mpc `v_lead` 안전측 min() 보정
  재현, 8개 시나리오 전부 PASS. 58차1번 세션 당시 스크래치
  (`work/test_visiontrack_gate.py`)로만 검증하고 미편입돼 소실됐던
  것을 오늘(58차3번 후속수정) 세션에서 toolkit 정식 편입.
- **README.md 소급 보강**: `sim_low_speed_decel.py`(58차2번)/
  `sim_vision_track_ab.py`(58차3번 A+B+외곽게이트) 두 파일도 그동안
  README에 섹션이 없었음(체크포인트 세션들에서 코드+검증만 하고 문서화
  누락) — 이번에 소급 추가. 오늘 커밋 5개(58차 1/2/3번 전체) 전부
  toolkit 시뮬레이션 도구로 커버 완료(총 3개 스크립트, 19개 시나리오
  전부 PASS 확인).

## 2026-08-22 (46차 계속)
- **`analysis_helpers.py`에 `curve_apex_vs_gap_delta()` 신규**: 커브
  이벤트별 "조향각 정점(apex) 시점" vs "vEgo-desiredSpeed 최대 초과폭
  (max gap) 발생 시점"의 delta 계산. **계기**: route2(f3db6ca89d) 32건
  분석에서 "정점 감속 부족"으로 분류했던 사례의 79%가 실제로는 max gap이
  apex보다 평균 1.26초 먼저 발생 — (1)사전감속 부족과 (2)정점 감속
  부족이 별개 증상이 아니라 하나의 연속 문제일 가능성 발견(FINDINGS.md
  "route2 32건 커브 이벤트 재분류" 참고). 원래 세션 스크래치 스크립트
  (`work/curve_gap_vs_apex_scan.py`)의 로직을 그대로 옮김 — route2.csv
  회귀검증으로 32건/초과24건 동일 결과 확인.

## 2026-08-22 (44차)
- **`analysis_helpers.py`에 `dRel_jump_ego_maneuver_overlap()` 신규**:
  `curve_lead_dRel_jump_events()`가 찾은 dRel 급점프 이벤트 각각에
  대해 ego 자신의 blinker/laneChangeState/desiredCurvature 부호반전
  (S자형 조향)과 겹치는지 자동 플래그. **계기**: route B seg10
  이벤트를 42차에서 "커브 vision 노이즈"로 오판했다가, 사용자가
  "본인 차선변경 시점과 겹친다"고 지적해 44차에서 정정한 사례
  (FINDINGS.md 44차) — 매번 사람이 CSV를 눈으로 대조하지 않아도
  이런 겹침을 놓치지 않도록 자동화. route B seg10 CSV로 검증:
  raw jump 11건 중 t=1895.7~1896.25(문제의 그 이벤트) 전부
  `curvature_reversal=True`+`blinker_on=True`로 정확히 플래그됨.
  **구버전(43차 이전) CSV로 뽑은 rows에는 안 통함** — leftBlinker/
  rightBlinker/laneChangeState 컬럼 자체가 없어 항상 False만 나옴.

## 2026-08-22 (43차)
- **`extract_log.py` 컬럼 추가**: `leftBlinker`/`rightBlinker`
  (carState, 운전자 방향지시등 의도), `laneChangeState`/
  `laneChangeDirection`(lateralPlan, 실제 궤적계획상 off/
  preLaneChange/laneChangeStarting/laneChangeFinishing 상태) 4개
  신규. 세그먼트 경계 carryover도 기존 leadStatus 패턴과 동일하게
  적용(`carry_lat` 추가) — 세그 경계에서 값이 반짝 리셋되는 아티팩트
  방지. **계기**: 42차에서 "vision dRel 점프 노이즈"로 결론낸 route B
  seg10 t=1895.6~1896.25 이벤트를, 사용자가 "그 시점이 본인 차선변경
  시점과 겹친다"고 재검토 요청 — 기존 CSV엔 차선변경 여부를 판별할
  컬럼이 아예 없어 그 가능성을 검증 못 하고 있었음(도구 공백). 이
  컬럼들로 ego 차선변경 시작/진행/종료 구간과 dRel 점프 시각을 직접
  대조 가능해짐. **주의**: 42차 CSV(구버전 extract_log.py로 추출)는
  이 컬럼이 없으므로, B seg10 재검증은 로그 재추출부터 다시 해야 함.

## 2026-08-22 (42차 계속)
- **`verify_and_extract_frames.py` 신규**: `extract_dashcam_frames.py`는
  세그먼트 폴더를 직접 지정받아야 했던 것을, route_dir(여러 세그먼트)
  전체를 스캔해 target time마다 올바른 세그먼트를 자동 매칭하도록
  래핑. 세그먼트 범위 밖(gap)이거나 매칭 오차가 큰 시각은
  OUT_OF_RANGE/WARN으로 명시 리포트 후 추출을 건너뛴다(잘못된
  프레임으로 결론 내리는 것 방지). 42차 세션에서 route.csv를 수동으로
  대조해가며 세그먼트를 찾던 작업을 자동화한 것 — 42차 이벤트 4건
  (route B seg10 t=1896.85 포함)으로 수동 결과와 동일 프레임(segmentId
  731, matched_t 일치) 재현 확인 + 세그먼트 gap(1750.0)과 완전
  범위밖(9999.0) 시각으로 OUT_OF_RANGE 판정 정상 동작 확인. **사용자
  요청으로 "로그 zip에 qcamera 있으면 항상 프레임 대조" 표준 절차의
  기본 진입점으로 사용할 것.**

## 2026-08-21 (29차)
- **`sim_frac_rate.py` 수정**: `VISION_CLOSING_RATE_GATE_CAUTION`/
  `GATE_DANGER`를 `SIM_GATE_CAUTION`/`SIM_GATE_DANGER` 환경변수로
  override 가능하게 함(기본값은 기존과 동일 -5.5/-10.0). 문턱
  재설계 후보 스윕을 파일 수정 없이 반복 실행하기 위함.

## 2026-08-21 (28차)
- **`sim_frac_rate.py` 신규**: 26차 patch(`5cc0900`)의 `frac_rate`
  게이트(클램프+중앙값+저역통과 → CAUTION/DANGER 정규화) 프레임 단위
  재현. 세그7/세그12 재업로드 zip으로 검증 → 두 사례 모두 게이트
  전 구간 미발동(0.000) 확정, FINDINGS.md `[VALIDATED]` 항목으로
  격상.

## 2026-08-21 (21차)
- **[20차 계속의 would_trigger_ttc_danger 개선 착수]** 다중 프레임
  물리 일관성 체크 추가.
  - `analysis_helpers.py`: `curve_lead_dRel_jump_consistency()`,
    `curve_noise_summary_refined()` 신규 — 점프 이후 1.5초 동안
    dRel/leadVRel이 물리적으로 일관되게 움직이는지 체크해 노이즈성
    플리커와 진짜 접근을 구분.
  - 21차에서 시각 검증한 seg6(노이즈 4건)/seg12(진짜위험 1건, t=797.79)
    실제 데이터로 파라미터(window=1.5s, monotonic_frac_thresh=0.6)
    튜닝 및 검증 — 5건 전부 정확히 분류 확인.
  - 260821 로그 seg6/12 부분(전체 아님) 대조 시 raw danger 12건 →
    refined danger 1건 (억제율 91.7%).
  - **한계**: 표본 5건으로만 튜닝됨. seg12 t=800.05(육안상 브레이크등
    확인됐으나 아직 미검증) 같은 "리드 재획득 섞인" 복잡 케이스는
    현재 파라미터로 놓침 — 다음 세션에 더 많은 시각 검증 사례로
    재확인 필요.

## 2026-08-21 (4)
- **[도구 후보 3번 완료]** 곡선(vturn) 구간 leadDRel 급점프 노이즈
  탐지 도구.
  - `analysis_helpers.py`: `curve_lead_dRel_jump_events()`,
    `curve_noise_summary()` 신규 — 23차에서 발견된 "곡선에서 모델이
    다른 물체를 리드로 오인해 dRel이 급점프하는 노이즈" 패턴을
    정량화. 점프 크기를 순간 접근속도로 환산해 TTC DANGER 문턱을
    넘길 만한 크기인지까지 1차 필터링.
  - 합성 데이터로 23차 실제 패턴(60m→32m→29m 급점프 후 회복)을
    재현해 검증 — 위험 방향 점프는 `would_trigger_ttc_danger=True`,
    회복 방향 점프는 `False`로 정확히 분류됨 확인.
  - **다음 단계**: `VISION_CLOSING_RATE_TAU` 개선안(1/2/4번) 설계
    전, 이 도구로 기존 routeA/routeB CSV 및 향후 로그에서 실제
    발생 빈도를 측정해 필터링 방식(곡률 게이트/점프크기 게이트 등)
    설계 근거로 사용 예정 — 아직 실 데이터로는 미실행.


## 2026-08-21 (3)
- **[도구 후보 2번 완료]** 패치 전/후 회귀 리포트 생성기.
  - `analysis_helpers.py`: `ttc_danger_events()` 신규 — 레이더 기반
    raw TTC(dRel/-vRel) 문턱 이하 구간 탐지. `scan_routes_for_ttc_danger()`
    신규 — 여러 CSV 일괄 스캔(도구 후보 5번의 배치 스캐너 역할 일부 겸함).
  - `regression_report()` / `regression_report_markdown()` 신규 —
    harsh_brake율/커브속도위반율/소스 플리커율(쌍 지정 가능, 기본
    vturn/model)/TTC DANGER 건수/jerk 통계를 patch 전후 CSV 2개로
    자동 diff, 분당 비율로 정규화. 세션마다(17/19/23차) 손으로 세던
    회귀 확인 작업을 대체.
  - 합성 데이터로 기능 검증 완료: flicker rate 감소/harsh_brake 감소
    시나리오에서 delta_pct가 방향/크기 모두 기대대로 계산됨,
    TTC danger 이벤트 탐지도 별도 케이스로 정탐 확인.
  - **다음 단계**: 실제 patch 전/후 route CSV 쌍이 생기면(예: 다음
    실주행 로그 분석 세션) 이 도구로 FINDINGS.md 갱신 시 표를 바로
    붙여넣을 수 있음 — 아직 실 데이터로는 미실행.

## 2026-08-21 (2)
- **[도구 후보 1번 완료]** `extract_log.py` 세그먼트 경계 아티팩트
  근본 수정 + 감사 도구 추가.
  - `extract_log.py`: `process_segment()`가 이전 세그먼트의
    carState/controlsState/leadStatus 상태를 이어받도록 수정
    (`carry_cs`/`carry_ctrl`/`carry_lead` 인자, 리턴값
    `(rows, last_cs, last_ctrl, last_lead)` 튜플로 변경). 이전에는
    세그먼트마다 leadStatus를 강제 False 리셋해 세그먼트 경계에서
    가짜 "순간유실" row가 찍히는 구조적 버그가 있었음 (22차 발견).
    `meta.json`에 `segment_state_carryover_fix: true` 필드 추가.
  - `analysis_helpers.py`: `segment_boundary_lead_loss_artifacts()`
    신규 — 구버전으로 뽑은 과거 CSV에서 세그먼트 경계와
    diff=0에 가까운 leadStatus False 구간을 자동 탐지해 "아티팩트
    의심" 여부를 표시. 합성 데이터로 단위 검증 완료(경계 정합
    케이스 정탐, 세그먼트 전체 유실 케이스는 제외 확인).
  - **다음 단계**: `LEAD_ACQ_LOSS_GRACE_TIME` 재검토 시 이 함수로
    과거 누적 증거(x11/x16/x20seg) 먼저 필터링, 남는 순수 유실만
    분석. `PARAMS_REGISTRY.md`도 갱신 필요(다음 세션 로그 분석 시).

## 2026-08-21 (1)
- `toolkit/README.md`, `toolkit/CHANGELOG.md` 신설 — 기존 6개 스크립트
  (decode_rlog, extract_log, analysis_helpers, extract_dashcam_frames,
  sim_vision_rate, push_via_api)를 표준 인덱스 문서로 정리. 세션 시작
  체크리스트에 "toolkit/README.md 먼저 확인" 항목 추가 (SETUP.md).
- `push_via_api.py` — Contents API 반복 PUT(파일당 1커밋) 방식에서
  Git Trees API(blob → base_tree 위 새 tree → commit 1개 → ref 갱신)
  방식으로 교체. 여러 파일을 push해도 커밋 1개로 묶임. CLI
  인터페이스(`--message`, `remote=local` 매핑)는 동일하게 유지 —
  기존 호출부 수정 불필요.

## 소급 기록 (정확한 날짜 불명 — 세션 로그 기준 대략적 순서)
- `decode_rlog.py` — rlog/qlog capnp 디코더 최초 작성 (capnp import
  hook, zstd max_output_size 함정 해결 포함).
- `extract_log.py` — 라우트 → CSV 추출 스크립트 최초 작성. 이후
  `commit` 컬럼 및 `.meta.json` (repo 상태 추적용) 추가. `leadRadar`/
  `leadModelProb` 필드 추가 (vision-only 감속 로직 검증 대비).
- `analysis_helpers.py` — 최초 `load_csv`/`trip_summary` 등 기본 함수로
  시작, 이후 세션마다 필요에 따라 `vision_to_radar_crossover`,
  `lead_cut_in_detector`, `curve_exit_no_accel_scan_v2`,
  `steering_oscillation_detector`, `source_transition_log`,
  `compare_runs_by_commit` 등 순차 추가.
- `extract_dashcam_frames.py` — "정차열 리드 대체 가설" 검증을 위해
  작성 (qRoadEncodeIdx 기반 프레임-시각 동기화, side-by-side 합성 이미지).
- `sim_vision_rate.py` — LEAD_ACQ 상태머신 시뮬레이션, patch 전/후
  동작(`blip_reset_only` 플래그) 비교용으로 작성.
- `push_via_api.py` — GitHub Contents API 기반 devnotes 자동 push
  스크립트 작성 (토큰 미출력 원칙 포함).

> 위 소급 기록은 각 파일이 "언제 어떤 이유로" 생겼는지 대략적 맥락만
> 남긴 것 — 정확한 세션 차수/날짜는 FINDINGS.md의 해당 이슈 항목을
> 참고. 이 시점 이후로는 실제 작업 날짜 기준으로 기록한다.

## 2026-08-21 (20차)
- `analysis_helpers.py`: `source_pair_flicker_stats()` /
  `all_source_pairs_flicker_summary()` 신규 — 도구 후보 4/5,
  min() 소스 선택 히스테리시스를 임의의 소스 쌍에 대해 범용 정량화
  (기존 vturn↔model 쌍 특별 취급을 대체, road↔route 등 미집계 쌍도
  자동 커버). 합성 데이터로 왕복 카운트/dwell/min_count 필터 단위
  검증 완료. 실제 route CSV 재대조는 다음 로그 분석 세션에서.

## 2026-08-22 (46차)
- `extract_log.py`: `modelTurnSpeed`(modelV2.meta.modelTurnSpeed) 컬럼
  신규 추가 — 그동안 CSV에 vTurnSpeed/src만 있고 model 후보의 실제 값이
  없어 "model 게이팅" 관련 분석(진입전 사전감속 부족 원인 조사)이 불가능
  했음. 세그먼트 경계 carryover도 다른 필드와 동일하게 적용. 하위호환:
  기존(46차 이전) CSV는 이 컬럼이 항상 빈 문자열 — 재추출 필요.

## 2026-08-23 (47차)
- `extract_log.py`: `vCruiseCluster`(carState.vCruiseCluster) 컬럼 신규
  추가 — 기존 `vCruise` 필드와는 별개 값인데 이름이 비슷해 혼동 유발
  가능성 있었음. `controlsd.py` line 214의 `min(CS.vCruiseCluster,
  desiredSpeed)` 캡이 실제로 참조하는 게 이 필드. 하위호환: 46차 이전
  CSV는 이 컬럼 없음 — vCruiseCluster 캡 관련 분석 시 재추출 필요.
- `analysis_helpers.py`: `curve_exit_no_accel_scan_v3` 신규 — v2(leadStatus
  필터+직선지속시간 재확인) 위에 vCruiseCluster 캡 여유폭 필터 추가
  (탈출 시점 `min(vCruiseCluster,desiredSpeed)-vEgo(kph)` < 5kph면 후보
  제외). route1/2/3(46차 로그) 재실행으로 문법/로직 검증 완료했으나,
  이 3개 로그로는 v3 필터가 실제로 뭔가를 걸러내는지까지는 확인 못함
  (route1/3은 v1 단계부터 0건 — 세그 내 커브 미탈출, route2는 v2
  단계에서 이미 4건 전부 필터링됨). FINDINGS.md 47차 항목 참고.

## 2026-08-23 (48차)
- `analysis_helpers.py`: `curve_exit_no_accel_scan_v4` 신규 — route6/7/8
  실전 검증(48차)에서 드러난 v3의 사각지대 2건 보완:
  (1) `vEgo_at_exit` 최소속도 필터(`min_vego_at_exit_mps=1.0`) 추가 —
  정차 상태에서 곡률 임계값이 우연히 넘는 오탐(route7 seg18) 배제.
  (2) `cap_margin_thresh_kph` 기본값 5.0→6.5 상향 — route7 seg12/seg14
  두 근접 후보를 CSV 원본(`vTurnSpeed`/`src` 필드)으로 직접 대조한 결과
  vTurnSpeed 자체는 이미 완전 해제(200km/h 안팎) 상태였고 순수
  vCruiseCluster 캡만 제한 요인이었음이 확인돼, 문턱을 살짝 올려 이런
  경계 사례까지 v4 단계에서 제외하도록 조정. 이 두 변경 적용 후
  route7/route8 둘 다 0건으로 수렴 확인(route6은 ADAS 미관여로 분석
  제외). FINDINGS.md 48차 항목 참고.

## 2026-08-23 (49차)
- `analysis_helpers.py`: `vturn_release_lag_scan` 신규 — 사용자가
  "탈출 후"가 아니라 "탈출전(정점 직후)부터 가속" 및 "과속방지턱처럼
  apex 통과 즉시 속도 원복" 프레이밍으로 재제기한 가설을 검증하기 위한
  도구. `vturn_speed()`(carrot_man.py) 코드 확인 결과 두 가설 모두
  이미 설계 의도(argmin + lookahead_pos>0 필터로 apex 통과 즉시 release
  후보 전환)와 일치함을 먼저 확인 -- 이 함수는 그 구조적 즉시성과 실제
  체감 사이의 간극이 `vturn_accel_rc` 저역통과 스무딩 지연 때문인지를
  CSV 필드(steeringAngleDeg proxy + vTurnSpeed)만으로 근사 측정.
  modelV2 raw(필터-전 required_speed_kph)는 CSV에 없어 완전한 검증은
  아님(한계 docstring에 명시). 합성 시나리오 2건(지연 재현/무지연)으로
  로직 검증 완료, 실제 로그 검증은 다음 세션(route7/8 CSV 컨테이너
  소실로 재확보 필요). FINDINGS.md/WIP.md 49차 항목 참고.

## 2026-08-23 (53차)
- `replay_lookahead_v1.py` 신규 작성 — lookahead horizon 가설(ii) 직접
  검증용. modelV2 원본(orientationRate.z/velocity.x/position.x)에서
  carrot_man.vturn_speed()의 필터 적용 전(raw) argmin required_speed_kph를
  프레임 단위로 재현. 합성 시나리오 2건(원거리 급커브/완전 직선)으로
  로직 검증 완료, cereal/log.capnp 필드 경로 확인 완료. 실제 rlog 검증은
  다음 세션 과제(README.md 참고).

## 2026-08-25 (63차 계속4)
- `extract_log.py`: `leadDPath`/`leadYRel`/`leadALeadK`/`leadRadarTrackId`
  컬럼 신규 추가(RadarState.LeadData 필드). 63차 계속3에서 발견한 seg14
  반복 discontinuity(raw dRel 프레임당 최대 -230m/s급 점프, closing/
  opening 반복)의 원인이 인접차선 오검출인지 실제 cut-in(트랙 전환)인지
  구분할 근거가 없었던 것을 해소. 특히 radarTrackId는 dPath보다 더
  직접적으로 "다른 물체로 넘어갔는지"를 잡을 수 있어 함께 추가.
  README.md 동기화 완료. `ryu` 코드 변경 없음(devnotes toolkit만).

## 2026-08-23 (58차 2번)
- `analysis_helpers.py`: `congestion_stop_launch_lurch_scan` 신규 —
  "정체구간 붕끗" 근본원인 가설(정체 중 danger override가 완만한
  접근에도 무감쇠로 튀는 것) 전용 스캐너. 정체 상태 추적(최근 window
  내 정차 횟수) + TTC danger 이벤트 겹침 판정 + 이벤트 전체 구간
  max|vRel|로 "완만한 접근만" 필터링(진짜 위험은 후보에서 제외).
  합성 시나리오 3건으로 로직 검증 완료. 실제 로그(정체구간_붕끽.zip,
  route1/route2 각 ~3분)에 적용 결과 엄격 기준 0건/완화 기준 1건
  (그마저 cruiseEnabled=False로 ADAS 무관) — 이번 표본에서는 가설
  확증 못함. README.md/FINDINGS.md/WIP.md 58차 2번 항목 참고.
