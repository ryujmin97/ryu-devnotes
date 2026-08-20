# toolkit/ CHANGELOG

새 도구 추가/기존 도구 함수 추가·변경 시 날짜 + 한 줄 요약을 여기에
남긴다. `README.md`도 같이 갱신할 것.

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
