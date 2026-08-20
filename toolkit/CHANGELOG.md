# toolkit/ CHANGELOG

새 도구 추가/기존 도구 함수 추가·변경 시 날짜 + 한 줄 요약을 여기에
남긴다. `README.md`도 같이 갱신할 것.

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
