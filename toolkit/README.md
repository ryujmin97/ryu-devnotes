# toolkit/ 인덱스

> **[필독, 계정 무관 — 예외 없음] 로그분석/시뮬레이션/검증 스크립트가
> 필요한 요청을 받으면, 코드를 짜기 전에 이 파일부터 끝까지 훑어서
> 같은 목적의 함수/스크립트가 이미 있는지 확인한다.** 있으면 그대로
> (옵션만 조정해서) 재사용 — 새로 작성하는 건 여기 없을 때만.
> **새로 작성했다면 검증 상태(합성검증뿐이든 실측완료든)와 무관하게
> 반드시 이 폴더(`toolkit/`)에 저장하고, 이 README에 섹션 추가 +
> `CHANGELOG.md`에 한 줄 요약을 남긴 뒤 세션/체크포인트 종료 시 함께
> push한다.** `work/`에만 남겨두고 끝내지 않는다 — 컨테이너가
> 리셋되면 그대로 사라져서 다음 세션(다른 계정 포함)이 또 새로
> 작성하는 낭비가 반복된다 (58차1번/63차에서 이미 2회 반복돼 이 원칙이
> 생김, `PROJECT_INSTRUCTIONS.md`/`SETUP.md`에도 동일하게 명시됨).

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
**2026-08-26 수정(86차)**: 드라이브 종료 시점에 잘린 채로 기록된
`rlog.zst`(주로 마지막 세그먼트)는 one-shot `decompress()`가
"did not decompress full frame"로 실패함. `stream_reader` 폴백을
추가해 잘린 지점까지의 유효 데이터를 회수(내용 자체는 유효, zstd
프레임 경계 문제일 뿐). 폴백 발동 시 stderr 경고 출력 — 해당
세그먼트는 일부 row가 유실됐을 수 있음을 인지하고 사용할 것.
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

- `radar_source_flicker_scan(rows, min_flips=3, window_s=2.0, blinker_window_s=1.0, jump_thresh_m=8.0, ttc_danger_thresh=2.5)`
  (107차 신규): leadRadar(True/False) 값이 짧은 시간 안에 여러 번 뒤집히는
  "소스 플리커" 클러스터를 찾는다. 106차("차선변경 중 leadRadar 핸드오프
  반복 급감속") 정량화용으로 추가 — leadRadarTrackId는 이 차량(SCC 단일점
  레이더, 코너레이더 없음)에서 radar=True일 때 항상 0 고정이라 변별력이
  없음을 107차에서 확인(트랙ID로 "같은 물체 vs 다른 물체" 구분 불가), 대신
  leadRadar 엣지 빈도 + blinker 겹침 + dRel 점프 크기로 직접 정량화.
  **주의**: `would_trigger_ttc_danger`는 `curve_lead_dRel_jump_events`와
  동일하게 프레임간 순간변화율 기반 근사치(1차 스크리닝용)이며 실제
  a_change_cost 부스트/danger override 상호작용을 시뮬레이션한 값이
  아님 — 정밀 검증엔 `sim_jerk_boost.py` 병행 필요. 107차에서 캐시된
  일반 주행 12개 라우트 전체 스캔 결과 51클러스터 중 blinker 겹침은
  21건(41%)뿐 — 이 현상이 차선변경에 국한되지 않을 가능성 시사(상세는
  WIP.md/FINDINGS.md 107차 참고).

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

## analysis_helpers.py — congestion_stop_launch_lurch_scan (58차 2번 신규)
**목적**: "정체구간 붕끗" 근본원인 가설(58차 2번 설계: 정체 중 danger
override(TTC<=2.5s)가 완만한 접근에도 무감쇠로 튀는 것) 전용 스캐너.
`analysis_helpers.py`에 함수로 추가됨(다른 toolkit 스크립트에서 import).
**주요 파라미터**: `stop_v_ego`(정차 판정, 기본 0.3m/s)/
`congestion_window_s`(정체 판정용 최근 시간창)/
`congestion_stop_count_thresh`(window 내 정차 횟수 조건)/
`ttc_danger_thresh`(기존 LEAD_ACQ_TTC_DANGER 2.5s)/
`congestion_min_closing_for_danger`(이 값 미만 |vRel|만 "완만한 접근"
후보로 채택, 이벤트 전체 구간 중 한 번이라도 이 값을 넘으면 "진짜
위험"으로 판단해 후보에서 제외).
**주의**: `congestion_window_s`/`congestion_stop_count_thresh`/
`congestion_min_closing_for_danger`는 아직 실제 `ryu` 코드 상수가
아님(58차 2번 코드 미착수) — 이 스캔 전용 추정 파라미터, 실제 패치
상수값은 별도로 튜닝 필요.
**58차 2번 계속 세션 결과**: 실제 로그 2개(각 ~3분)에 엄격한 기준
(정차 2회 이상 window)으로는 0건, 완화 기준(정차 1회)으로도 route1에서
1건뿐이었고 그마저 `cruiseEnabled=False`(운전자 수동 조작 구간)라
ADAS 개입과 무관 — 이번 로그 표본에서는 설계가 겨냥한 "붕끗" 사례를
확증하지 못함(FINDINGS.md 58차 2번 계속 항목 참고).
**합성 시나리오 3건**(완만한 접근 단독/진짜 위험 단독/정체 아닌 상태)
으로 로직 자체는 검증 완료.

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

## sim_low_speed_decel.py
**목적**: 58차 2번("정체구간 붕끗") 패치 — `long_mpc.py`의
`LOW_SPEED_STRONG_DECEL_V_EGO_GATE`(30km/h)/`_A_LEAD_THRESH`(112차부터
-2.5m/s², 원래 -1.8) 게이트(저속+앞차 강한감속 시 danger override와
동일하게 즉시 무감쇠) 로직 단위 검증 + 112차부터
`discontinuity_jerk_boost` 신규 트리거 소스 `low_speed_strong_decel`
(a_change_cost 완만화 경로) 검증. `process_lead()`의 weight 계산부만
순수함수로 재현(실제 acados MPC는 안 거침).
**의존성**: 없음(표준 라이브러리만).
**시나리오 7건**: A(고속 회귀, patch 전/후 diff=0)/B(이벤트 재현,
unpatched 감쇠→rise-rate 한계로 몰려서 반영 vs patched 즉시 w=1.0)/
C(오탐 방지, 저속+완만감속은 게이트 미개방)/D(경계 전이, v_ego가
게이트값을 여러 번 넘나들어도 예외 없음)/**E(112차 신규: 라우트1
실측 aLeadK=-2.07 재현 — 신threshold -2.5에서 더 이상 저속게이트
미발동 확인, 오탐 해소)**/**F(112차 신규: 진짜 강한감속 -3.0은
threshold 강화 후에도 여전히 게이트 발동 — 원래 목적 보존 확인)**/
**G(112차 신규: jerk_boost 'low_speed_strong_decel' 소스 — danger
지속 중엔 a_change_cost=base 유지, 해제 직후 boost(500) 전환 후
hard-hold(4.0s)+release-rate(100/s)로 base까지 완만 감쇠)**.
**사용**: `python3 sim_low_speed_decel.py`

## replay_low_speed_strong_decel.py
**목적**: 112차 계속 — 라우트1 실측 CSV로 LOW_SPEED_STRONG_DECEL
threshold 강화(-1.8→-2.5) + jerk_boost 신규소스 검증. `sim_low_speed_
decel.py`(합성 시나리오)와 달리 실측 노이즈 데이터를 그대로 사용.
**핵심 발견(중요, 기존 분석 정정)**: 단일 시점(aLeadK=-2.07)만 봤던
기존 분석은 불완전 — 실제로는 aLeadK가 계속 악화돼 최대 -2.96까지
도달하는 **진짜 지속적 앞차 감속 이벤트**였고, 동시에 TTC도 6.85s→
4.15s로 자연 하강 중이었음(정상 ttc_accel_weight 경로도 결국 같은
구간에서 자연 수렴). `compare_weight_trajectory()`로 오버라이드
없는 baseline과 비교한 결과: baseline은 t=1939.873에 자연 수렴(w≥0.99)
하는데, 구threshold는 이보다 0.900s, 신threshold는 0.700s 앞당겨
w=1.0을 강제함. 즉 **threshold 강화는 오탐을 "제거"한 게 아니라
"조기발동 구간을 0.754s→0.410s로 약 46% 단축"한 것** — 원래
FINDINGS.md 112차의 "오탐 확정" 서술은 이번 실측 replay로 일부
정정 필요(사용자 확인 대기, 아래 FINDINGS.md 112차 계속2 참고).
**함수**: `run_threshold_scan()`(threshold별 발동 프레임/에피소드 스캔),
`run_jerk_boost_flicker_check()`(실측 노이즈 환경 재트리거 이상 점검),
`compare_weight_trajectory()`(오버라이드 유/무 weighted a_lead 궤적
비교 — 오버라이드의 실제 한계효용 정량화).
**의존성**: 없음(표준 라이브러리만).
**사용**: `python3 replay_low_speed_strong_decel.py <route.csv>`

## sim_vision_track_ab.py
**목적**: 58차 3번("정지앞차 미인식/과소반응", A+B) + 후속수정(외곽
게이트 버그) 검증. `radard.py` `VisionTrack.update()`의 tentative 조기
등록(A)/저확신구간 안전측 min() 보정(B)/`get_lead()` 외곽 게이트
전파(A 후속수정) 3개 로직 단위 재현.
**의존성**: 없음(표준 라이브러리만).
**시나리오 7건**: A-1(조기등록)/A-2(저prob 미등록 회귀)/A-3(jitter
오인승격 방지)/B-1(안전측 보정, "정지차량_미인식" 실사례 근사)/
B-2(정상상황 무간섭)/고prob 회귀/외곽게이트 전파(구게이트 prob>.5
중복체크 무력화 재현 vs 신게이트 status 기반 정상 전파).
**사용**: `python3 sim_vision_track_ab.py`

## sim_vision_gate_v_lead.py
**목적**: 58차 1번("카메라 인식 감속이 레이더 대비 약함 → 레이더
인식 수준으로 강화") 검증. `radard.py` `VisionTrack.update()`의 실측
dRel미분 blend 전환 게이트 완화(`VISION_TRACK_PROB_GATE` 0.97→0.70,
`VISION_TRACK_CNT_GATE` 20→10, 커밋 `1f0d292`) + `long_mpc.py`
`process_lead()`의 `_vision_dRel_rate`를 `v_lead`에 직접 min()
안전클램프로 반영(커밋 `e17e078`) 2건을 각각 순수함수로 재현.
**계기**: 58차1번 세션 당시 `work/test_visiontrack_gate.py`(스크래치)
로만 검증하고 toolkit에 편입 안 해서 컨테이너 리셋으로 소실됨 —
58차 3번 후속수정 세션에서 toolkit 정식 편입.
**의존성**: 없음(표준 라이브러리만).
**시나리오 8건**: 게이트완화 typical prob(0.75~0.85, 구게이트는
영원히 미전환 vs 신게이트는 프레임10 전환)/고prob 회귀(둘 다 전환되나
신게이트가 더 빠름)/저prob 무변화(신게이트도 0.70 미만이면 안 풀림)/
v_lead 안전측 보정(24.0→19.0)/완화방향 없음(min()이 더 큰 값 무시)/
레이더 리드 무간섭/MIN_TIME 게이트/극단 실사례 근사("정지차량_미인식"
케이스 수치, 27.0→6.0).
**사용**: `python3 sim_vision_gate_v_lead.py`

## sim_drel_discontinuity.py
**목적**: 61차 계속(방안 C, cutin dRel 불연속 급락 감지 → 신규등록
suppress 메커니즘 재사용) 로직 단위 합성검증. `long_mpc.py` 801~844줄
(방안C 관련 블록)의 조건문/상수를 코드 그대로 복사해 재현(순수함수
재구현이 아니라 리터럴 대조라 코드-스크립트 간 drift 없음).
**의존성**: 없음(표준 라이브러리만).
**시나리오 6건**: 정상 완만접근(오탐방지)/cutin 급락 재현(65→24m류)/
진짜 급접근(danger override 백스톱 확인용)/단발 1프레임 스냅(과민반응
방지)/신규등록 게이트와의 이중 트리거(부작용 없음 확인)/danger override
독립성(정적 코드 구조 확인).
**사용**: `python3 sim_drel_discontinuity.py`
**63차**: 컨테이너 리셋으로 유실됐던 걸 재작성하며 toolkit 정식 편입
(이전엔 work/ 스크래치로만 뒀다가 소실 → 63차부터 "검증 스크립트는
항상 toolkit에 저장" 원칙으로 변경, SETUP.md 참고).

## replay_drel_discontinuity_real.py
**목적**: 63차 계속 — 방안C를 **실측 CSV**(route.csv, `extract_log.py`
산출물) 위에서 프레임 단위로 재생해 PATCHED(방안C 있음)/UNPATCHED
(방안C 없음) 두 버전을 나란히 비교. `sim_drel_discontinuity.py`가
합성 시나리오였다면 이건 실제 로그 재생 버전 — `long_mpc.py`의
lead-acquisition ramp bookkeeping(L744~780) + 방안C discontinuity
체크(L801~844) + `vlead_correction_suppressed`/`vision_rate_for_lead0`
계산(L866~877) + `frac_time`/`frac_ttc`/`frac_rate` 계산(L907~961)을
실제 코드와 대조해 그대로 복제(단 acados MPC 자체는 재현 안 함 —
`frac`/`vision_rate_for_lead0`까지만 비교해도 "이 프레임에 방안C가
개입했는지/그 결과 무엇이 억제됐는지"는 정량 판단 가능).
**입력**: `extract_log.py`로 뽑은 route CSV (leadDRel/leadVRel/
leadRadar/leftBlinker/rightBlinker/vEgo/cruiseEnabled 컬럼 필요).
**주요 함수**: `run_segment(csv_path, seg_suffix, t_lo, t_hi)` —
지정 세그먼트/시간범위를 PATCHED·UNPATCHED 둘 다 재생해 프레임별
DataFrame 리턴. `summarize(name, res)` — discontinuity 트리거 프레임/
v_lead 직접보정 주입 프레임 수 비교/frac 최대·평균 비교/aEgo 최저치
부근 상세 테이블 출력.
**63차 계속 실측 검증 결과(중요)**: r1-3(seg3)류(radar 락온이 급락
직후 빠르게 이뤄지는 경우)는 방안C 효과 확인(frac 0.9대→0.3대로
감소, radar 락온이 frac_rate/ttc를 0으로 리셋해줘서 frac_time 개선분이
그대로 드러남). **r1-14(seg14)류(radar 락온 전에 급감속이 끝나는
경우)는 PATCHED=UNPATCHED로 완전히 동일(frac=1.0) — 방안C 무효 발견.**
원인: `frac_rate`/`frac_ttc`는 discontinuity suppression과 무관하게
`_vision_dRel_rate`를 직접 읽는데, 방안C는 `_lead_acq_timer`만
리셋하고 `_vision_dRel_rate`/`_vision_dRel_rate_window`는 그대로 둠 —
방안 D(두 값도 함께 리셋) 설계 필요. 상세는 FINDINGS.md "[63차 계속,
중요] 방안 C 실측 재생 검증 완료" 항목 참고.
**사용**:
```bash
python3 replay_drel_discontinuity_real.py
# 또는 개별 세그먼트만:
python3 -c "
from replay_drel_discontinuity_real import run_segment, summarize
res = run_segment('/home/claude/work/route.csv', '--3', t_lo=256.0, t_hi=262.0)
summarize('seg3', res)
"
```

## data_routes.py (72차 계속3, 신규)
**목적**: `data/routes/<route_id>/route.csv.gz`로 커밋해둔 라우트를
`analysis_helpers.load_csv()`와 동일한 `list[dict]`로 바로 불러온다.
로그 업로드 zip을 매 세션 다시 unzip + `extract_log.py` 하지 않고
재사용하기 위함 — replay/시뮬레이션 스크립트가 반복적으로 같은
라우트(예: route1 `ea5bcc0566` seg10, route2 `a5b1ce4e42` seg1)를
쓸 때 특히 유용.
**의존성**: 없음 (표준 라이브러리만).
**주요 함수**:
- `list_routes(devnotes_dir)` — 등록된 route_id 목록
- `load_route_meta(devnotes_dir, route_id)` — meta.json만 빠르게 확인
- `load_route(devnotes_dir, route_id)` — `(rows, meta)` 반환, gzip은
  임시파일로 풀었다가 자동 삭제
**등록된 라우트 목록/구조는 `data/routes/README.md` 참고.** 새 라우트
추가 시 그 문서의 "새 라우트 추가 절차" 따를 것.
**사용**:
```python
from data_routes import load_route
rows, meta = load_route("/home/claude/devnotes", "ea5bcc0566")
```

## replay_boost_duration.py (73차, 신규 / 73차 계속2 갱신)
**목적**: 방안I(72차) boost 지속시간(`DISCONTINUITY_JERK_COST_BOOST_S`)
후보(2.0/3.0s hard-cutoff) + `split_gate` 옵션(73차 계속 결정 — 트리거
소스별 게이트 분리: 레이더 핸드오프는 danger_active 단독, dRel
discontinuity는 기존 `frac<=0.0` 게이트 유지)을 `data_routes.py`로
불러온 실측 route1/route2에 정량 비교. discontinuity 트리거+boost
게이트(danger_active/frac<=0.0)까지 `long_mpc.py` 그대로 복제해,
"boost 타이머는 활성인데 게이트에 막혀 실제로는 base cost로 강등된
시간"까지 진단(73차 핵심 발견: duration이 아니라 게이트 자체가 병목
— FINDINGS.md 73차 참고. 73차 계속2: split_gate로 게이트차단을
해소하면 duration 연장이 다시 의미를 가짐 확인 — 두 방향은 결합해야
함).
**의존성**: `data_routes.py`, `numpy`.
**주요 함수**: `BoostReplay(boost_s, release_rate, split_gate)`(상태
머신), `run_candidates(rows, t_lo, t_hi, candidates)` —
candidates는 `(label, boost_s, release_rate, split_gate)` 4-tuple,
`summarize_event(...)` — 위험구간(aEgo<=risk_thresh, 짧은 회복 blip은
무시) 대비 후보별 timer활성/실부스트/게이트차단 시간 표 + danger_active
회귀 자동 경고.
**사용**:
```bash
python3 replay_boost_duration.py
```

## replay_lane_change_discontinuity_gate.py (75차 신규, 76차 갱신)
**목적**: 75차 방향(b)(discontinuity 트리거를 차선변경 중엔 handoff와
동일하게 frac 게이트 무관 완화) + **76차(duration_mode='full')**:
75차가 남긴 "hard-hold 1.0s 자체가 짧아 실제 aEgo 최저점을 놓침"
한계에 대응해, 차선변경 중 discontinuity 트리거의 hard-hold 유지시간/
release-rate까지 방안I(handoff)과 완전히 동일(4.0s+100/s)하게 맞추는
실제 `long_mpc.py` 패치(`discontinuity_lc` 소스 태그)를 재현·검증.
`LaneChangeGateReplay`에 `duration_mode`('gate_only'=75차 원안 /
'full'=76차) 옵션 추가, `is_handoff_source` 분기(release-rate 감쇠
포함)를 'handoff'/'discontinuity_lc' 공통 경로로 재현.
**핵심 발견(75차, gate_only 한계)**: route2 t=1470.75 트리거 직후
1.0s hard-hold 구간 내에서는 frac 게이트 완화로 boost 커버리지가
늘지만, 이 이벤트의 실제 aEgo 최저점(-1.556, 트리거 후 1.65초)은
hard-hold(1.0s, t=1471.75) 소진 후라 그 순간 a_change_cost가
20(무감쇠에 가까움)까지 떨어져 무력화됨.
**76차 확인**: 동일 이벤트에서 `duration_mode='full'`은 hard-hold가
4.0s(t=1474.75까지)라 최저점(t=1472.20~1472.40) 전 구간에서 a_change_
cost=500(완전부스트) 유지 — 한계 해소 확인. route1/route2 전체
스캔에서 full 모드 boost프레임 수가 gate_only보다 항상 크거나 같음
(route1 730->1028, route2 184->479, 커버리지 실제 증가 확인).
**회귀 체크**: route1/route2 전체에서 UNPATCHED 대비 a_change_cost가
달라지는 프레임(402/409건)은 전부 소스='discontinuity_lc'인 경우뿐 —
일반 discontinuity(차선변경 무관)/handoff 소스는 diff 0건(완전
보존), danger_active 프레임 수도 회귀 없음.
**의존성**: `data_routes.py`, `replay_boost_duration.py`(상수 일부
재사용, `RADAR_HANDOFF_JERK_BOOST_S/RATE`는 모듈에 없어 이 스크립트
안에서 실제 값 그대로 재정의), `numpy`.
**사용**:
```bash
python3 replay_lane_change_discontinuity_gate.py
```


## scan_force_revert_episodes.py (108차 신규)
**목적**: `replay_lane_change_discontinuity_gate.py`의
`LaneChangeGateReplay(duration_mode='full')`(75-76차, 현재
`long_mpc.py`의 `discontinuity_lc` 소스와 100% 동일 로직)를 여러
라우트에 대해 "라우트 전체 한 번에 연속 재생" 방식으로 돌려
force_revert(boost 타이머가 살아있는데도 danger_active에 밀려
a_change_cost가 boost 값 밑으로 떨어진 프레임) 에피소드를 자동
탐지/그룹핑한다. 106차/107차가 수작업/소규모 표본으로 냈던 "차선변경이
force_revert 필요조건" 결론을 30라우트 규모로 확정하는 데 사용됨
(108차, FINDINGS.md 참고).
**중요 — 반드시 이 도구를 쓸 것, 직접 재구현하지 말 것**: 108차에서
클러스터 구간만 잘라 warm-start로 재생하거나(pad_s에 따라 결과가
달라지는 아티팩트 발생), 트리거 소스별 hard-hold 시간 차이
(discontinuity=1.0s vs handoff/discontinuity_lc=4.0s)를 구분 안 하고
단일 `boost_s`로 재현하면 허위 severe 사례가 다수 발생함을 확인
(폐기된 `flicker_cluster_boost_replay.py`, 이 실수 기록은 FINDINGS.md
108차 "2단계" 참고). 이 함정을 피하려면 `LaneChangeGateReplay`를
그대로 재사용해야 한다.
**의존성**: `replay_lane_change_discontinuity_gate.py`.
**주요 함수**: `scan_route(route_id, rows, force_revert_cost_thresh=300.0)`
— 단일 라우트 스캔, `scan_many_routes(route_rows_map)` — `{route_id:
rows}` 딕셔너리를 받아 전체 에피소드 리스트를 합쳐 반환.
**사용**:
```python
from scan_force_revert_episodes import scan_many_routes
eps = scan_many_routes(route_rows_map)  # route_rows_map = {route_id: rows}
for e in sorted(eps, key=lambda x: x['min_aEgo']):
    print(e['route_id'], e['trigger_source'], e['blinker_active_at_start'],
          e['t_start'], e['duration_s'], e['min_aEgo'])
```
단독 실행(등록된 라우트 대상): `python3 scan_force_revert_episodes.py
/home/claude/devnotes <route_id1> <route_id2> ...`

## patched_replay_v109.py (109차 신규)
**목적**: 옵션1 patch(`long_mpc.py`, `LANE_CHANGE_DISCONTINUITY_
DANGER_CONFIRM_S`)를 실제 코드 배포 전에 검증하기 위해
`replay_lane_change_discontinuity_gate.py`의 `LaneChangeGateReplay`
(76차, full모드)를 상속, `discontinuity_lc` 트리거에 한해 danger_
active가 CONFIRM_S(0.25s, `long_mpc.py`와 반드시 동일값 유지) 동안
연속 유지돼야 force_revert를 인정하도록 오버라이드한 PATCHED 버전.
`scan_force_revert_episodes.py`(108차, UNPATCHED)와 나란히 돌려
before/after 비교하는 용도.
**검증 결과(109차)**: 캐시 `a5b1ce4e42`에서 경미한 force_revert(0.15s)
완전 흡수, 지속 사례(0.55s)는 0.35s로 단축(진짜 위험분은 보존) —
상세는 FINDINGS.md 109차 참고. **주의**: 108차 가장 심한 사례
(`947fbb7dc6`)와 `handoff` 사례(`ad830211ff`)는 원본 CSV 소실로 아직
이 도구로 검증 못함 — 재업로드 후 최우선 재검증 필요.
**의존성**: `replay_lane_change_discontinuity_gate.py`,
`replay_boost_duration.py`.
**주요 함수**: `PatchedLaneChangeGateReplay(lane_change_gate,
duration_mode='full')` — `step()`이 `force_revert` 키를 추가로 반환,
`scan_route_patched(route_id, rows)` — `scan_force_revert_episodes.
scan_route()`와 동일 인터페이스의 PATCHED 버전.
**사용**:
```python
from data_routes import load_route
from scan_force_revert_episodes import scan_route as scan_unpatched
from patched_replay_v109 import scan_route_patched

rows, meta = load_route("/home/claude/devnotes", "a5b1ce4e42")
eps_before = scan_unpatched("a5b1ce4e42", rows)
eps_after = scan_route_patched("a5b1ce4e42", rows)
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

## sim_jerk_boost.py
**목적**: 66차/67차(방안G) `a_change_cost`(저크비용) 한시적 부스트 로직
('discontinuity' 트리거 소스, 비-handoff 한정) 합성검증. 69차부터
"실물 존재 확인 필요"로 여러 세션 이월되던 항목 -- 80차에서 실제로
작성/저장(그 전까진 주석에서만 언급되고 실물이 없었음).
**의존성**: 없음(표준 라이브러리만).
**주요 함수**: `DiscontinuityBoostReplay` -- `trigger()`로 boost 타이머
arm, `step(frac, danger_active, base_a_change_cost)`로 매 프레임
`a_change_cost` 재현.
**커버 시나리오**: 정상 트리거 시 1.0s 전체 boost 유지 후 hard-cutoff,
frac>0에 의한 무력화(75차 발견 구조), danger override 최우선, 트리거
없는 구간 회귀 없음, boost 소진 후 지속 감속 한계(72차 실측, 방안I 도입
근거).
**주의**: 'handoff'/'discontinuity_lc' 소스(방안I, hard-hold+release-rate)는
범위 밖 -- `replay_boost_duration.py`가 담당.
**사용**: `python3 sim_jerk_boost.py`

## sim_res_button.py
**목적**: 79차("수동주행 중 첫 +RES 시 목표속도가 현재속도보다 낮게
설정" 버그) 패치 로직 순수함수 재현. `cruise.py`
`VCruiseCarrot._update_cruise_buttons()` accelCruise 분기 재현.
**의존성**: 없음(표준 라이브러리만).
**주요 함수**: `update_cruise_buttons_accel(..., patched=True/False)` --
patched=False로 79차 이전(버그) 동작, True로 패치 이후 동작 비교 가능.
**커버 시나리오**: 버그 재현(구코드 33 그대로) vs 패치 확인(신코드
현재속도보다 높은 다음 눈금), unit(눈금 크기) 반영, 기존 no-op 분기
(`_cruise_ready`/`standstill`/`CC.enabled=True`) 회귀 없음.
**사용**: `python3 sim_res_button.py`

## test_launch_bypass.py
**목적**: 45차(정지 후 출발 가속 약화 대응) launch bypass 로직 회귀
검증. `long_mpc.py` `process_lead()`의 `LAUNCH_BYPASS_STOP_V_EGO`/
`LAUNCH_BYPASS_EXIT_V_EGO` 상태 전환 + bypass 중 TTC 게이트/rise-rate
완전 우회 로직 재현.
**의존성**: 없음(표준 라이브러리만).
**주요 함수**: `LaunchBypassReplay.step(v_ego, x_lead, v_lead, ...)` --
`w`(lead accel damping weight), bypass 활성 여부, ttc_now를 프레임별로
리턴.
**커버 시나리오**: 정차→출발 구간 무감쇠 유지, EXIT_V_EGO 전환 순간 w
급변 가능성(45차가 발견, 회귀 아닌 알려진 설계 특성으로 문서화), bypass
중 danger override 최우선, 고속 정상주행 회귀 없음(39차 rise-rate 유지).
**주의**: `dist_w`(margin_accel_weight)는 1.0 고정 단순화 -- 실측 route
기반 재생은 `replay_boost_duration.py`류 참고.
**사용**: `python3 test_launch_bypass.py`

## test_scc_gate.py
**목적**: 37차(SCC 단일점 폴백 dPath 안전 게이트) 회귀 검증.
`radard.py` `RadarD.get_lead()`의 `track_scc`(trackId=0) 폴백 채택 시
`SCC_FALLBACK_DPATH_GATE`(2.0m) 검증 로직 재현.
**의존성**: 없음(표준 라이브러리만).
**주요 함수**: `get_lead_scc_fallback(track_present, lead_msg_prob,
track_scc_cnt, track_scc_dpath, track_scc_vlead, enable_radar_tracks=-1)`
-- (used_scc_fallback, gate_blocked) 튜플 리턴.
**커버 시나리오**: 옆차선 오검출 차단, 문턱(2.0m) 경계 케이스, 차로 내
정상 리드 채택 회귀 없음, 후보 조건 자체가 안 열리는 no-op 케이스,
track 존재+저확신(prob<.6) 상황에서도 게이트 우회 없음(60차 계속8 관련).
**사용**: `python3 test_scc_gate.py`

## sim_route_dynamic_cap.py (84차, 신규)
**목적**: 84차(route 커브 lookahead 300m 고정 캡 -> v_ego/accel_limit
기반 동적 캡) 로직 회귀 검증. `carrot_man.py`
`compute_route_lookahead_distance()` 순수함수 재현.
**의존성**: 없음(표준 라이브러리만).
**주요 함수**: `compute_route_lookahead_distance(v_ego_kph, accel_limit_mss,
min_m=300.0, max_m=500.0, assumed_target_kph=30.0)` — 캡 거리(m) 리턴.
**커버 시나리오**: 저속(<=50km/h) 전 accel_limit에서 floor(300m) 유지
(회귀 없음), 고속(130km/h)+낮은 accel(0.70) 조합 ceil(500m) clip,
accel_limit 낮을수록 같은 속도에서 캡이 더 크게(단조성), accel_limit=0/None
예외 시 floor(300m) 안전 폴백.
**사용**: `python3 sim_route_dynamic_cap.py`

## five_item_scan.py (55/56차 최초 작성, 86차 정식 편입)
**목적**: "5개 항목 종합분석" 표준 절차(카메라인식감속/정지앞차감속/
정지후재출발/레이더락온저크/곡선구간감속) 일괄 실행. 55차/56차에서
`work/`에만 있다가 두 번(56차/86차) 컨테이너 리셋으로 유실된 이력이 있어
이번에 정식 편입.
**의존성**: `analysis_helpers.py`(같은 폴더, `vision_to_radar_crossover`/
`turn_speed_violations`/`_f`/`_b` 재사용).
**주요 함수**: `run_five_item_scan(rows)` — 5개 함수 결과를 dict로 반환.
개별: `stopped_lead_decel_events(rows, v_lead_thresh=1.0, min_duration_s=1.0)`,
`launch_after_stop_events(rows, stop_v_ego=0.3, exit_v_ego=5.0)`(45차 launch
bypass 상수와 동일값), `radar_lockon_jerk_events(rows, jerk_thresh=3.0,
smooth_window_s=0.3)`(leadRadar=True 프레임만, 0.3s 이동평균 jerk).
**사용**: `python3 five_item_scan.py <csv_path>` (건수만 출력) 또는
`from five_item_scan import run_five_item_scan`.

## verify_resample_np.py (100차 신규)

99차(carrot_man.py 20Hz 루프 정적리뷰)에서 찾은 "Shapely
`LineString.interpolate()` 반복호출" 이슈를 numpy 벡터화 함수
(`resample_10m_np()`)로 대체하기 전, 두 방식이 수치적으로 동일한
결과를 내는지 검증하기 위해 작성.

**함수**: `resample_10m_shapely(points_xy, distance_interval)` — 원본
(carrot_man.py/sim_route_curvature_sample.py와 동일한 Shapely 기반
리샘플). `resample_10m_np(points_xy, distance_interval)` — 대체 후보
(numpy 누적거리 배열 + `np.interp` 스타일 벡터화, carrot_man.py 100차
패치에 실제 채택된 것과 동일 구현). `make_random_path(...)` — 급커브
포함 랜덤 GPS 스타일 경로 생성기(테스트용).

**검증 범위**: 랜덤 경로 20개(다양한 곡률/길이/노이즈) + 89/90차류
급한 램프커브 스타일 + 직선(곡률 0, 오탐 확인) + 경계조건(2점짜리
매우 짧은 경로, 총길이가 정확히 distance_interval의 배수인 경우) +
route_lookahead_m 최대치(600m)급 긴 경로.

**결과**: 전부 PASS, 원본(Shapely) 대비 최대오차 1.2e-13m(부동소수점
오차 수준) 이내로 100% 일치 — 좌표 개수/값 모두 동일.

**사용**: `python3 verify_resample_np.py` (인자 없음, 내장 테스트셋
전체 실행). 의존성: `shapely`(비교 기준용, numpy 버전 자체는 shapely
불필요), `numpy`.

**향후 재사용**: `carrot_man.py`의 GPS 경로 리샘플링 로직을 다시 만질
일이 있으면(예: 89차 대안1 - sample 값 축소) 이 스크립트의
`resample_10m_np()`를 그대로 가져다 쓰면 됨 — 별도 검증 없이 신뢰
가능.

## sim_route_curvature_sample.py (90차 신규)
**목적**: 89차 route 사전감속 과소평가 원인분석에서 나온 대안1(곡률
샘플링 chord 축소, `sample` 4->2/3)을 검증. raw navi_points(GPS
폴리라인)가 로그에 없어, 실주행 `desiredCurvature`(모델이 그 순간
실제로 추종한 경로 곡률)를 시간축으로 적분해 차량이 실제로 통과한
경로의 2D 지역좌표를 재구성 -- `calculate_curvature()`가 회전/이동
불변량만 쓰므로 이 재구성 경로에 `carrot_man.py`의 곡률+속도+역방향DP
로직을 그대로 복제 적용해 sample 값을 비교할 수 있음.
**의존성**: `shapely`(LineString 리샘플, `pip install shapely` 필요),
`numpy`, `analysis_helpers.load_csv`.
**주요 함수**: `reconstruct_path(rows, t_start, t_end)` — desiredCurvature
적분으로 경로 재구성. `resample_10m(points_xy)` — 원본과 동일한 10m
리샘플. `compute_curvatures_speeds(resampled_points, sample)` —
`calculate_curvature`+`V_CURVE_LOOKUP` 복제. `backward_dp(...)` — 82차
수정판 역방향DP 복제(원복측 vturn_safe_time 크레딧 포함). `run_snapshot()` —
특정 시점 스냅샷에서 sample 2/3/4 비교.
**사용**: `python3 sim_route_curvature_sample.py <csv_path> [--t-start] [--t-end]
[--accel-limit] [--vturn-safe-time]`
**90차 핵심 결과**: 89차 대안1(sample 4->2/3, chord 40m->20~30m)을 이
방식으로 검증한 결과, 정점 근처 최소 목표속도는 sample=4일 때도 이미
78km/h(vturn 실측 최종요구치 73km/h와 5km/h 차이)로 상당히 근접 —
sample을 2로 낮춰도 75.7km/h까지만 개선(효과 ~2.5km/h). 실제 로그의
route 최저값(121km/h)과 vturn 실측(73km/h) 사이 48km/h 갭에 비하면
미미한 수준. **raw navi_points 희소성(원시 GPS 포인트 간격) 실험도
병행 — 간격을 30/60/100m로 늘려도 sample 축소 효과가 체계적으로
커지지 않고 오히려 꼭짓점에서 노이즈성 스파이크만 커짐(과소평가가
아니라 노이즈 방향)**. 즉 **대안1(chord 축소)만으로는 89차가 관찰한
실제 과소평가 갭을 설명/해소하기 어렵다는 결론** — 진짜 원인은 코드
내부 파라미터가 아니라 실제 navi 서비스가 제공하는 GPS 폴리라인 자체의
형상(지도 데이터의 램프 곡선 표현 정밀도) 쪽일 가능성이 더 커짐
(NEEDS_VALIDATION, raw navi_points를 직접 로깅하지 않는 한 확정 불가).
상세는 FINDINGS.md \"90차\" 참고.

## sim_drel_discontinuity_d.py (94차, 신규)
**목적**: 94차(방안D, discontinuity 트리거 시 `_vision_dRel_rate`/
`_vision_dRel_rate_window`/`_vision_dRel_prev` 동반 리셋) 회귀검증.
63차 계속에서 발견된 r1-14 사각지대(방안C의 `_lead_acq_timer` 리셋만으로는
`frac_rate`/`frac_ttc`가 discontinuity 트리거 이후에도 오염된 채
DANGER급으로 유지되는 문제)가 이 패치로 실제 해소되는지 확인.
`long_mpc.py`의 discontinuity 트리거 블록 + vision_dRel_rate 필터
(클램프+중앙값+저역통과) + frac_rate 정규화를 그대로 복사해 재현.
**의존성**: `numpy`.
**시나리오 4건**: 1)r1-14류(radar 락온 지연) — UNPATCHED는 트리거 후에도
frac_rate=1.0 유지 vs PATCHED는 즉시 0. 2)정상 완만접근(discontinuity
없음) — rate 완전 동일(회귀 없음). 3)r1-3류(radar 즉시 락온) — 기존
코드의 무조건 리셋 경로가 이미 처리하므로 방안D 유무와 무관하게 락온
이후 동일(기존 검증된 조합 회귀 없음). 4)danger override 독립성(정적 확인).
**사용**: `python3 sim_drel_discontinuity_d.py`

---

## match_dashcam_clip_to_route.py (111차 신규)
**목적**: `_clip.mp4` 대시캠 화면녹화의 파일명 타임스탬프(HHMMSS)만으로는
route CSV의 정확한 `t` 구간을 특정할 수 없는 문제(HUD 시계가 시:분만
표시 + screenrecorder.cc 저장시각과 시작시각 어긋남, 111차 실측 최대
~50초 편차 확인) 해결. blinker 클러스터의 **순서/상대 시간차 + 급감속
강도**로 클립을 route t에 매칭.
**핵심 함수**: `find_blinker_clusters(rows)` — route CSV에서 blinker
활성 클러스터 전부 추출 + 각 구간 min_aEgo/시각. `match_clips(clusters,
clip_filename_seconds, tolerance_s=10)` — 클립 파일명 시각 리스트와
후보 클러스터 시간차를 비교해 매칭.
**검증(111차)**: `947fbb7dc6`의 두 클립(`113702`,`113848`, 파일명
시간차 106s)을 이 방법으로 매칭 — 후보 클러스터 시간차 108.9s(오차
2.9s)로 성공 매칭, qcamera 프레임 시각 대조로 재확인. 파일명 매칭
직접시도(seg0 시작시각 기준 단순 오프셋)는 실제로 53~55초 어긋나
실패했던 것과 대조.
**한계**: 클립 2~3개 전용(그 이상은 조합 폭발, 수동 검토 권장). 이
도구는 "언제" 일어났는지만 특정 — 화면 `a_ego/a_target/a_out` 그래프
자체를 재현하려면 별도로 `long_mpc.py` MPC 솔버 재실행 필요(미구현).

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

## sim_route_margin_regression_scan.py
**목적**: 93차 — 91차(ROUTE_ENTRY_MARGIN_KPH) 회귀검증용. `sim_route_
curvature_sample.py`의 재구성/곡률/DP 함수를 재사용하되 `backward_dp`에
91차 margin_kph 로직(감속전환 time_delay 계산에만 target_speed-margin
사용)을 추가한 `backward_dp_margin()` 제공. 로그 전체 구간을 지정 간격
(기본 3초)으로 스윕하며 margin=0 vs margin=25 결과를 비교, (1)직선구간
오탐 (2)조기개입 여부+정점목표값 불변 확인 (3)역전버그 3가지를 자동
판정.
**사용**:
```bash
python3 sim_route_margin_regression_scan.py <route.csv> \
    --step 3.0 --lookahead 45.0 --accel 0.70
```
`--accel`은 `AutoNaviSpeedDecelRate` 실측값(83차, 기본 0.70) 사용.
`--lookahead`는 84/85차 동적 캡(300~600m) 커버리지의 근사치 — 최소
40~50초 권장(고속 구간 600m 커버 위해).
**의존성**: `shapely`, `numpy`. `sim_route_curvature_sample.py` 재사용.

## scan_perf_antipatterns.sh
**목적**: 실시간 루프 파일(carrot_man.py/carrot_functions.py/
carrot_serv.py/controlsd.py/radard.py/longitudinal_planner.py/
long_mpc.py/cruise.py 등)에서 CPU/메모리 관련 정적 안티패턴 후보를
grep으로 일괄 스캔. "전체코드 CPU/메모리 재점검" 같은 요청에서 매번
grep 명령을 손으로 다시 짜지 않기 위한 도구(101차 후속 세션에서 사용한
패턴을 스크립트화).
**스캔 항목**: `deepcopy`, `Params()` 신규 인스턴스 생성, 미캐싱
가능성 있는 `.params.get*`, `print(`, 함수 내부 `re.compile`,
`threading.Thread`/`subprocess.*`, `.append(`(bounded 여부 확인용),
누적형 dict 캐시(`self.xxx = {}`), 비벡터화 `for ... in range(len(`.
**사용**:
```bash
bash toolkit/scan_perf_antipatterns.sh /home/claude/ryu
# 파일 목록을 직접 지정하려면:
bash toolkit/scan_perf_antipatterns.sh /home/claude/ryu selfdrive/carrot/carrot_man.py
```
**주의 (중요)**: 이 스크립트는 "의심 위치"만 찾아준다. 매치 하나하나가
실제 문제인지는 반드시 `sed -n 'N,Mp' <file>`로 컨텍스트(호출 빈도,
readParams류 캐싱 게이트 안에 있는지, deque(maxlen=..)로 bounded인지,
이벤트 트리거성인지 vs 매 프레임 실행인지)를 확인해야 한다. 오탐이
흔하다 — 101차 후속 스캔에서 나온 매치 대부분이 이미 97~100차에서
캐싱/bounded 처리가 되어 있는 것으로 확인됨(WIP.md/FINDINGS.md
"101차 후속 CPU/메모리 재점검" 참고).
