# toolkit/ 인덱스

세션 시작 시 (특히 "이번에 뭘 새로 만들지 vs 기존 걸 쓸지" 판단할 때)
가장 먼저 이 파일을 읽는다. 각 스크립트의 목적/입출력/의존성/사용
예시 한 줄씩만 정리. 함수 시그니처 상세는 각 파일 docstring 참고.

새 도구를 추가하거나 기존 도구에 함수를 추가하면 **이 README와
CHANGELOG.md를 같이 갱신**한다 (세션 종료 체크리스트에 포함됨).

---

## decode_rlog.py
**목적**: `rlog.zst` / `qlog.zst` → capnp Event 이터레이터. 다른 모든
로그 처리 스크립트(`extract_log.py`, `extract_dashcam_frames.py`)의
기반이 되는 저수준 디코더.
**의존성**: `pycapnp`, `zstandard`. `ryu` 레포 clone 필요 (`cereal/log.capnp`
스키마 로드).
**주요 함수**:
- `get_schema(repo_dir)` — capnp 스키마 로드 (import hook 처리 포함)
- `iter_events(path, repo_dir, max_output_mb=400)` — rlog/qlog 파일을
  열어 capnp Event를 하나씩 yield
**주의**: `capnp.remove_import_hook()`을 `capnp.load()` 이전에 반드시
호출. zstd 압축 해제 시 `max_output_size` 명시 필요.

## extract_log.py
**목적**: 라우트 폴더(세그먼트 여러 개) 전체를 순회하며 종방향/조향
관련 필드를 20Hz CSV 하나로 뽑는다. 로그 분석의 시작점 — 대부분의
분석 요청은 여기서부터 시작.
**입력**: `route_dir` (세그먼트별 `rlog.zst` 포함 폴더들의 상위 폴더)
**출력**: `<out.csv>` + `<out.csv>.meta.json` (추출 당시 repo commit
hash/branch/커밋 날짜·메시지/dirty 여부/추출 시각/row 수 —"이 로그가
어느 코드 상태에서 뽑힌 건지" 추적용)
**CSV 컬럼**: `t, seg, commit, vEgo, aEgo, brakePressed, gasPressed,
cruiseEnabled, vCruise, steeringAngleDeg, desiredCurvature, leadStatus,
leadDRel, leadVRel, leadVLead, src, desiredSpeed, vTurnSpeed,
leadRadar, leadModelProb`
**사용**:
```bash
python3 extract_log.py /home/claude/work/route /home/claude/work/route.csv \
    --repo /home/claude/ryu [--max-mb 400]
```
**2026-08-21 수정**: 세그먼트 경계에서 carState/controlsState/leadStatus
상태를 다음 세그먼트로 이어받는다. 이전 버전은 세그먼트마다
leadStatus를 강제로 False 리셋해, 실제로는 리드가 유지되고 있었는데도
새 세그먼트 시작 시 가짜 "순간유실" row가 찍히는 구조적 버그가 있었음
(세그먼트 경계와 diff=0.000s로 정확히 일치, FINDINGS.md 22차). 이
버전으로 뽑은 CSV는 `meta.json`에 `segment_state_carryover_fix: true`가
찍힌다. **이 필드가 없는 과거 CSV**는 `analysis_helpers.
segment_boundary_lead_loss_artifacts()`로 먼저 감사할 것.

## analysis_helpers.py
**목적**: `extract_log.py`로 뽑은 CSV를 후처리하는 함수 모음. 대부분의
"패턴 찾기" 분석(플리커, 급제동, 커브 위반, cut-in 등)은 여기서 시작.
**입력**: 모든 함수는 `load_csv()`가 만든 `list(dict)` (csv.DictReader
결과)를 받는다. 숫자 필드는 문자열로 들어오므로 각 함수 내부에서
`float()` 변환.
**주요 함수** (전체 시그니처는 파일 내 grep `^def` 참고):
- `load_csv(path)` / `load_meta(csv_path)` — CSV/meta.json 로드
- `compare_runs_by_commit(csv_paths)` — 여러 CSV를 commit hash 기준으로 비교
- `vision_to_radar_crossover(rows, min_gap_s, highway_v_ego)` — 비전→레이더
  전환(크로스오버) 이벤트 탐지
- `remove_driver_intervention(rows, ...)` — 운전자 개입 구간 제외
- `clean_decel_blocks(rows, ...)` — 감속 블록 정제
- `lead_presence_segments(rows, ...)` — 리드 존재 구간 세그먼트화
- `curve_exit_no_accel_scan(rows, ...)` / `_v2` — 커브 탈출 후 미가속 스캔
- `speed_tracking_error(rows, ...)` — 목표속도 추종 오차
- `turn_speed_violations(rows, ...)` — 커브 속도 위반 탐지
- `source_transition_log(rows)` — 속도 소스 전환 로그 (필드명
  `from_src`/`to_src`, `src_to` 아님— 헷갈리기 쉬우니 주의)
- `source_pair_flicker_stats(rows, src_a, src_b, transitions=None)` —
  (2026-08-21 신규) 임의의 두 소스(예: `road`,`route`) 사이의 플리커를
  정량화 — 전환 건수/분당 비율/A→B→A 왕복(연속, 사이에 제3소스 없을 때만)
  건수/체류시간(dwell) 통계. 지금까지 vturn↔model 등 특정 쌍만 세션마다
  수동으로 세던 것을 대체.
- `all_source_pairs_flicker_summary(rows, min_count=3)` — (2026-08-21
  신규) rows에 등장하는 모든 src 조합에 대해 위 함수를 자동 스캔,
  건수 내림차순 정렬로 리턴 — "우세 쌍이 뭔지" 자동 파악용
  (road↔route 등 이제껏 따로 집계 안 된 쌍도 여기서 함께 드러남).
- `cruise_engage_disengage_events(rows)` — 크루즈 on/off 이벤트
- `harsh_brake_events(rows, ...)` — 급제동 이벤트
- `lead_cut_in_detector(rows, close_dist_m)` — cut-in 탐지
- `trip_summary(rows)` — 트립 요약 통계
- `steering_oscillation_detector(rows, ...)` — 조향 발진(플리커) 탐지
- `segment_boundary_lead_loss_artifacts(rows, max_gap_s, tail_lookback_s)`
  — (2026-08-21 신규) 구버전 `extract_log.py`로 뽑은 CSV의 세그먼트
  경계 leadStatus 가짜 유실 아티팩트 후보를 탐지. `meta.json`에
  `segment_state_carryover_fix: true`가 있는 신버전 CSV에는 이
  아티팩트가 없으므로 실행 불필요 — `load_meta()`로 먼저 확인.
- `ttc_danger_events(rows, ttc_thresh, min_closing_vrel, min_duration_s)`
  — (2026-08-21 신규) 레이더 기반 raw TTC(=dRel/-vRel)가 문턱 이하로
  내려가는 구간 탐지. `LEAD_ACQ_TTC_DANGER` 등 위험 문턱 검증용.
- `scan_routes_for_ttc_danger(csv_paths, ttc_thresh, min_closing_vrel)`
  — (2026-08-21 신규) 여러 route.csv를 한 번에 스캔해
  `ttc_danger_events()` 결과를 합침. "희귀 이벤트 배치 스캐너" 용도.
- `regression_report(rows_before, rows_after, before_label, after_label,
  src_pair, ttc_thresh)` — (2026-08-21 신규) 패치 전/후 route CSV를
  받아 harsh_brake율/커브속도위반율/소스 플리커율(지정 쌍)/TTC
  DANGER 건수/jerk 통계를 자동 계산+비교(delta_pct). 대부분 분당
  비율로 정규화해 라우트 길이가 달라도 비교 가능.
- `regression_report_markdown(report, before_label, after_label)` —
  `regression_report()` 결과를 FINDINGS.md에 바로 붙여넣을 수 있는
  마크다운 표로 변환.
- `curve_lead_dRel_jump_events(rows, jump_thresh_m, max_dt_s,
  curve_src_values, ttc_danger_thresh)` — (2026-08-21 신규) 곡선
  구간(`src="vturn"`)에서 모델이 다른 물체를 리드로 오인해 leadDRel이
  프레임 간 급점프하는 노이즈 탐지(23차 발견 패턴). `VISION_CLOSING_
  RATE_TAU` 개선안(1/2/4번) 설계 전 선행검토용.
- `curve_noise_summary(rows, ...)` — 위 함수 결과를 요약 통계(곡선
  구간 체류시간 대비 점프 빈도, DANGER 문턱 넘김 건수)로 압축.
- `curve_lead_dRel_jump_consistency(rows, jump_thresh_m, max_dt_s,
  curve_src_values, ttc_danger_thresh, consistency_window_s=1.5,
  monotonic_frac_thresh=0.6, revert_frac_thresh=0.5)` — (2026-08-21,
  21차 신규) `curve_lead_dRel_jump_events()`의 개선판. 점프 이후
  1.5초 동안 dRel이 물리적으로 일관되게(같은 방향, leadVRel 부호도
  일치) 움직이는지 후속 체크를 추가해 "노이즈성 플리커"와 "진짜
  접근"을 구분. seg6/seg12 dashcam 시각 검증 5건(노이즈 4건+진짜위험
  1건)으로 파라미터 튜닝 및 검증 완료 — 5건 전부 정확히 분류.
  `refined_would_trigger_danger` 필드가 최종 판정. **표본이 작아
  추가 검증 필요**(자세한 한계는 함수 docstring 참고).
- `curve_noise_summary_refined(rows, ...)` — `curve_noise_summary()`의
  refined 버전. raw `would_trigger_ttc_danger` 대비
  `refined_would_trigger_danger` 억제 비율(`noise_suppression_rate`)을
  포함. 260821 로그 seg6/12 대조 결과 raw 12건 → refined 1건
  (억제율 91.7%).

**회귀 리포트 사용 예시**:
```python
from analysis_helpers import load_csv, regression_report, regression_report_markdown

before = load_csv("/home/claude/work/route_before.csv")
after = load_csv("/home/claude/work/route_after.csv")
report = regression_report(before, after, before_label="패치전(commit abc123)", after_label="패치후(commit def456)")
print(regression_report_markdown(report, "패치전(commit abc123)", "패치후(commit def456)"))
```

## extract_dashcam_frames.py
**목적**: `qcamera.ts` 프레임을 rlog의 `qRoadEncodeIdx` 이벤트와
동기화해 특정 시각(t)의 실제 화면을 이미지로 추출. 가설을 영상
증거로 검증할 때 사용 (예: "정차열 리드 대체 가설" 반증에 사용됨).
**전제**: segment 폴더에 `qcamera.ts` + `rlog.zst`(없으면 `qlog.zst`,
커버리지 낮음 경고) 필요. `ryu` 레포 clone 필요.
**주요 함수**:
- `find_segment_files(segment_dir)` — 세그먼트 내 로그/카메라 파일 탐색
- `build_frame_time_index(log_path, repo_dir, encode_field)` — 시간↔프레임
  인덱스 매핑 구축
- `nearest_frame_for_time(index, target_t)` — 특정 시각에 가장 가까운 프레임 탐색
- `extract_frame(qcamera_path, frame_number, out_path)` — 단일 프레임 추출
- `extract_frames_for_times(segment_dir, repo_dir, target_times, out_dir, ...)` — 다중 시각 일괄 추출
- `make_side_by_side(image_paths, labels, out_path, max_width)` — PIL 기반 비교 합성 이미지 생성
**사용**:
```bash
python3 extract_dashcam_frames.py <segment_dir> --repo /home/claude/ryu \
    --times 205.53,207.99,208.69,210.48 --out-dir /home/claude/work/frames --context 2
```

## sim_vision_rate.py
**목적**: `LEAD_ACQ` 상태머신(비전 전용 리드 감속 트리거, grace time
등)을 실제 코드 수정 없이 CSV 로그 위에서 시뮬레이션 — 패치 전/후
동작을 실차 적용 없이 비교 검증할 때 사용.
**주요 함수**: `simulate_route(route_csv, blip_reset_only=False)` —
`blip_reset_only=True`면 구버전(grace 무시, 즉시 리셋) 동작 재현,
`False`면 패치 후(grace-aware) 동작 재현.
**주의**: 파일 내 상수(`VISION_CLOSING_RATE_TAU`,
`LEAD_ACQ_LOSS_GRACE_TIME` 등)는 `ryu`의 실제 코드 값과 수동 동기화
상태 — 코드에서 값이 바뀌면 이 파일도 같이 갱신해야 정확한 시뮬레이션이 됨.
`PARAMS_REGISTRY.md`와 값이 다르면 그쪽이 최신일 가능성이 높으니 대조.

## push_via_api.py
**목적**: `GH_TOKEN` 환경변수로 GitHub Contents API를 통해
`ryu-devnotes` 저장소에 직접 파일을 커밋/push. 세션 종료 시 표준
저장 경로 (수동 clone/commit/push 불필요).
**주의**: 토큰은 반드시 환경변수로만 받고, 어떤 경우에도 stdout/stderr에
출력하지 않는다. fine-grained PAT(해당 repo 1개, Contents Read/write)
전제. **Git Trees API 사용 (2026-08-21~)** — blob 생성 → base_tree 위에
새 tree 생성 → commit 1개 생성 → ref 갱신 순서로 처리하므로, 파일이
몇 개든 항상 커밋 1개로 묶인다 (이전 버전은 Contents API PUT을 파일마다
반복해 파일 수만큼 커밋이 생겼음).
**사용**:
```bash
export GH_TOKEN="..."
python3 push_via_api.py --message "커밋 메시지" \
    FINDINGS.md=/home/claude/devnotes/FINDINGS.md \
    LAST_ANALYZED.md=/home/claude/devnotes/LAST_ANALYZED.md
```

---

## 아직 없는 카테고리 (필요해지면 추가)
- `toolkit/sim/` — 시뮬레이터 스크립트가 `sim_vision_rate.py` 하나를
  넘어 여러 개로 늘어나면 이 시점에 하위 폴더로 분리 검토.
- 커밋 분석 자동화는 `toolkit/` 밖의 `devnotes/analyze_commits.sh`가
  담당 (셸 스크립트, 이 README는 `toolkit/*.py`만 다룸).

## 새 도구 추가 시 체크리스트
1. 스크립트 상단 docstring에 목적/입출력/의존성/사용 예시 명시
   (기존 파일 스타일 참고)
2. 이 README에 섹션 추가 (목적/의존성/주요 함수/사용 예시)
3. `CHANGELOG.md`에 날짜 + 한 줄 요약 추가
4. 세션 종료 시 `push_via_api.py` 인자에 변경된 toolkit 파일 포함해서 push
