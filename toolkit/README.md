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
leadRadar, leadModelProb, leftBlinker, rightBlinker, laneChangeState,
laneChangeDirection`
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
**2026-08-22 수정(43차)**: `leftBlinker`/`rightBlinker`(carState,
운전자 방향지시등)와 `laneChangeState`/`laneChangeDirection`
(lateralPlan, off/preLaneChange/laneChangeStarting/laneChangeFinishing)
4개 컬럼 추가 — dRel 급점프가 "vision 노이즈"인지 "ego 차선변경으로
리드 타겟이 바뀐 것"인지 CSV만으로 구분 가능해짐. 세그 경계
carryover도 동일하게 적용됨. **이 컬럼들이 없는 과거 CSV(42차 이전)로
이미 "vision 노이즈"라고 결론낸 이벤트가 있다면, 실제로는 이
컬럼들을 볼 수 없어서 차선변경 가능성을 아예 검증하지 못한 상태였을
수 있음 — 재검증 필요.**

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
- `curve_exit_no_accel_scan(rows, ...)` / `_v2` / `_v3` / `_v4` — 커브
  탈출 후 미가속 스캔 (v3: vCruiseCluster 캡 여유폭 필터 추가, "vCruise"
  아닌 "vCruiseCluster" 필드 필수 — extract_log.py 47차 이후 CSV만
  지원. **v4(48차, 최신 권장)**: 정차상태 오탐 배제 +
  `cap_margin_thresh_kph` 5.0→6.5 상향 — route6/7/8 실측으로 v3의
  근접 후보들이 실제로는 vTurnSpeed 완전 해제 후 순수 vCruiseCluster
  캡 제한이었음을 확인, v4 적용 시 0건으로 수렴. FINDINGS.md 48차 참고)
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
- `curve_apex_vs_gap_delta(rows, entry_thresh=5.0, exit_thresh=3.0,
  unrestricted_ds=180.0, min_event_rows=3)` — (2026-08-22, 46차 계속
  신규) `|steeringAngleDeg|>=entry_thresh` 진입/`<exit_thresh` 이탈로
  커브 이벤트 분리 후, 이벤트별 "조향각 정점(apex) 시점" vs
  "vEgo(kph)-desiredSpeed 최대 초과폭(max gap) 발생 시점"의 시간차
  (`delta_gap_minus_apex`, 음수=gap이 apex보다 먼저)를 계산. "정점
  감속 부족"이 실제로는 사전감속 부족의 연장인지 구분하는 용도 —
  route2(f3db6ca89d) 32건에서 초과 24건 중 79%가 gap을 apex보다 평균
  1.26초 먼저 찍는 것으로 확인(FINDINGS.md 46차 계속 항목 참고).
  호출부에서 `max_gap > 0`으로 먼저 필터링해 "실제 초과 사례"만 볼 것
- `vturn_release_lag_scan(rows, entry_thresh=5.0, exit_thresh=3.0,
  min_event_rows=3, curvature_release_hold_s=0.3, vturn_rise_thresh_kph=1.5,
  vturn_rise_hold_s=0.3, search_window_s=8.0)` — (2026-08-23, 49차 신규)
  apex(조향각 정점) 통과 후 "곡률이 실제로 완화되기 시작한 시각"
  (`curvature_release_t`, steeringAngleDeg 비증가 전환 근사)과 "vTurnSpeed
  출력이 실제로 오르기 시작한 시각"(`vturn_rise_t`) 사이 지연(`lag_s`)을
  측정 — `vturn_speed()`(carrot_man.py) 자체는 apex 통과 즉시 release가
  시작되는 구조(argmin+lookahead_pos>0 필터)이지만, 체감상 "탈출 후에도
  안 풀린다"는 게 구조 문제가 아니라 `vturn_accel_rc` 저역통과 스무딩
  지연 때문인지를 보는 용도. **주의**: modelV2 raw 배열(orientationRate/
  velocity/position, argmin 이전 필터-전 값)은 CSV에 없어 steeringAngleDeg를
  근사 proxy로 씀 — argmin 전환 시각 자체의 정확한 검증은 아님(그러려면
  modelV2 raw 재현 별도 과제 필요). 합성 시나리오 2건(지연 1.2s 재현/
  무지연)으로 로직 검증 완료, **실제 로그 검증은 아직**(route7/route8
  raw CSV가 컨테이너에 없어 다음 세션 신규 로그로 진행 필요).
  (특히 route1류 고속도로에서는 잡음성 조향 이벤트가 섞여 max_gap이
  크게 음수로 나오는 경우가 많음).
- `dRel_jump_ego_maneuver_overlap(rows, events, blinker_window_s=1.0,
  curvature_reversal_window_s=1.0, curvature_reversal_thresh=0.0005)` —
  (2026-08-22, 44차 신규) `curve_lead_dRel_jump_events()`가 찾은 각
  점프 이벤트에 `blinker_on`/`laneChangeState_active`/
  `curvature_reversal`/`likely_ego_maneuver` 플래그를 추가. **route B
  seg10 이벤트(42차가 "vision 노이즈"로 오판했다가 44차에서 ego 우측
  blinker+조향 급반전과 겹치는 것으로 정정된 사례)를 계기로 추가** —
  이후 "곡선 구간 dRel 점프 = vision 노이즈"로 성급히 결론내리기 전에
  이 함수부터 돌려서 ego 자신의 조향/신호와 겹치는지 스크리닝할 것.
  **`extract_log.py` 43차(2026-08-22) 이후 버전 CSV 필요**(blinker/
  laneChangeState 컬럼) — 구버전 CSV는 항상 False로만 나와 결과를
  신뢰할 수 없음. `likely_ego_maneuver=True`가 "안전과 무관"을
  의미하지 않음(1차 스크리닝용, 자세한 주의사항은 함수 docstring
  참고).

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

## verify_and_extract_frames.py
**목적**: `extract_dashcam_frames.py`를 감싸는 상위 도구. route_dir
(세그먼트 여러 개) 전체를 스캔해 target time마다 "이 t가 실제로 어느
세그먼트의 유효 시간 범위 안에 있는지"부터 자동 검증한 뒤 해당
세그먼트에서 프레임을 추출한다. 세그먼트를 직접 지정해야 했던 기존
방식(route.csv를 수동 대조) 대신 라우트 하나만 넘기면 됨.
**전제**: extract_dashcam_frames.py와 동일 (세그먼트 폴더에 qcamera.ts
+ rlog.zst/qlog.zst, ryu 레포 clone).
**주요 함수**:
- `discover_segments(route_dir)` — qcamera.ts+로그 파일이 둘 다 있는
  세그먼트 폴더 목록(이름순=시간순)
- `build_route_time_index(route_dir, repo_dir)` — 세그먼트별
  (t_min, t_max, frame index) 구축
- `resolve_segment_for_time(route_index, target_t)` — target_t가 속한
  세그먼트 자동 판정 (IN_RANGE / NEAREST_OUT_OF_RANGE / NO_SEGMENTS)
- `verify_and_extract(route_dir, repo_dir, target_times, out_dir, ...)`
  — 위 과정 전체 + 프레임 추출까지 한 번에 수행, `(report, manifest)`
  리턴. `out_of_range_gap_s`(기본 2.0s) 넘게 범위를 벗어난 시각은
  OUT_OF_RANGE로 판정하고 추출을 건너뜀(엉뚱한 세그먼트의 프레임을
  잘못 뽑는 것 방지).
**출력**: `<out-dir>/manifest.json`(extract_dashcam_frames.py와 동일
포맷 + `segment` 필드) + `<out-dir>/verify_report.json`(타임스탬프별
검증 상태) + stdout 요약표.
**사용**:
```bash
python3 verify_and_extract_frames.py /home/claude/work/routeB \
    --repo /home/claude/ryu \
    --times 1895.6,1896.2,1896.5,1896.85,1897.6 \
    --out-dir /home/claude/work/frames/eventB_seg10 --context 1
```
**42차(2026-08-22)에서 신규 작성**: qcamera 포함 로그 업로드 시
표준 분석 절차(로그+영상 대조)의 기본 진입점으로 사용.

## sim_frac_rate.py
**목적**: (2026-08-21, 28차 신규) 26차 patch(`5cc0900`, 아직 origin
미push)의 `frac_rate` 게이트 로직 — 클램프(30m/s, 접근 방향만) +
3프레임 중앙값 + 기존 TAU=1.0s 저역통과 → `VISION_CLOSING_RATE_
GATE_CAUTION`(-5.5)~`GATE_DANGER`(-10.0) 선형 정규화 — 를 CSV 위에서
프레임 단위로 정확히 재현. `sim_vision_rate.py`(a4b5550의 grace-aware
리셋 버그 검증용)와는 다른 목적이니 혼동 주의.
**입력**: `extract_log.py`로 뽑은 route CSV.
**출력**: 세그먼트별 `max_frac_rate`/`min_filt_rate` 요약 + (t범위
지정 시) 프레임별 상세 테이블(`filt_rate`, 클램프/중앙값 없는 참고용
`raw_rate_lp`, `frac_rate`, 게이트 활성 여부).
**사용**:
```bash
python3 sim_frac_rate.py /home/claude/work/route.csv [t_lo] [t_hi]
# 29차: 문턱 후보 스윕 (파일 수정 없이)
SIM_GATE_CAUTION=-3.0 SIM_GATE_DANGER=-8.0 python3 sim_frac_rate.py /home/claude/work/route.csv
```
**28차 결과**: 세그7/세그12 실측 두 사례 모두 `frac_rate` 전 구간
0.000(전혀 미발동) 확정 — 문턱값(-5.5)이 실측 피크(-3.2~-3.5)보다
구조적으로 높음. FINDINGS.md 28차 항목 참고.
**29차**: `SIM_GATE_CAUTION`/`SIM_GATE_DANGER` 환경변수 override
추가(기본값은 -5.5/-10.0로 기존과 동일). 문턱 재설계 스윕용.

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

## replay_lookahead_v1.py
**목적**: (2026-08-23, 53차 신규) lookahead horizon 가설(ii) 직접 검증용.
`extract_log.py` CSV의 `vTurnSpeed`는 저역통과 필터(`vturn_decel_rc`)를
거친 최종 출력이라, "필터가 늦춘 것"과 "애초에 lookahead_horizon_s(8.0s)
윈도 안에 급조임 지점이 안 들어와 있었던 것"을 구분 못 함 — 이 스크립트는
`carrot_man.vturn_speed()`의 물리공식(v_i^2=v_f^2+2ad, argmin)을 modelV2
원본(`orientationRate.z`/`velocity.x`/`position.x`)에서 **필터 적용 전(raw)**
값으로 프레임 단위 재현해 이 둘을 분리한다.
**입력**: route_dir(세그먼트 폴더들, 각 rlog.zst 포함), `ryu` 레포 clone 필요
(modelV2 스키마).
**출력**: CSV(`t, seg, raw_kph, filtered_kph_replica, apex_pos_m, apex_t_s,
curv_direction_replica`) — `t`는 `extract_log.py`와 동일 절대
`logMonoTime` 기준이라 route.csv와 직접 join 가능.
**주요 함수**: `compute_vturn_frame(...)` — 필터 전 argmin 계산만 순수
분리(단위 테스트 가능하도록 설계). `apply_lowpass(...)` — 실제 코드와
동일한 조건부(decel_rc/accel_rc) 저역통과 1스텝.
**한계**: modelV2 이벤트(~20Hz)를 carrot_man 20Hz 틱 1개로 근사(49차와
동일 전제, 완전히 같은 타이밍은 아님). `AutoCurveSpeedFactor`/
`AutoCurveSpeedAggressiveness` 사용자 실제 런타임값이 devnotes에 없어
코드 기본값(1.2/1.0)을 기본 사용 — 다르면 `--factor`/`--aggr`로 override.
**검증 상태**: 합성 시나리오(원거리 급커브 vs 완전 직선) 2건으로 로직
단위 검증 완료(급커브 케이스: raw_kph<100 확인/직선: raw_kph>200 확인),
저역통과 1스텝 방향성(decel_rc 적용) 검증 완료. cereal/log.capnp 필드
경로(`orientationRate.z`/`velocity.x`/`position.x`)도 직접 확인.
**실제 로그(raw rlog) 검증은 아직 미실시** — 다음 세션 route4(또는
동급 급조임 사례) rlog로 raw_kph가 실제 몇 초 전부터 낮게 나오는지
확인 필요.
**사용**:
```bash
python3 replay_lookahead_v1.py /home/claude/work/route4 \
    /home/claude/work/route4_lookahead.csv --repo /home/claude/ryu \
    --print-window 12337.6 12346.6
```

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
