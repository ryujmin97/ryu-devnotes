# toolkit/ CHANGELOG

새 도구 추가/기존 도구 함수 추가·변경 시 날짜 + 한 줄 요약을 여기에
남긴다. `README.md`도 같이 갱신할 것.

## 2026-08-29 (114차 — replay_margin_accel_weight_full.py 신규,
113차 유실분 대체+확장, ROUTE1 재평가)
- `replay_margin_accel_weight_full.py` 신규: margin_accel_weight(dist_w)
  까지 포함한 완전 재현(carrot_functions.py Params 기본값 대입) +
  LOW_SPEED_STRONG_DECEL/TTC danger override 포함. **113차가 만들었다는
  `replay_rise_rate_saturation.py`는 컨테이너 리셋으로 유실되어 레포에
  없었음 확인, 이 스크립트가 대체.** 핵심 발견: ROUTE1은 112차 threshold
  패치로 이미 saturation 0.951s→0.250s(danger override 조기발동)로
  해소, ROUTE2/3만 여전히 0.9~1.0s대 harsh. SMOOTH 라우트 전체 스캔에서
  진짜 위험과 무관한 0.448s 에피소드(track-switch 추정) 발견 — 단순
  threshold 판별지표의 한계 노출. 상세는 FINDINGS.md 114차 참고.

## 2026-08-29 (112차 계속2 — replay_low_speed_strong_decel.py 신규,
threshold 강화 효과 재정량화)
- `replay_low_speed_strong_decel.py` 신규: 라우트1 실측 CSV 기반
  threshold 발동 스캔 + jerk_boost 플리커링 점검 + weighted a_lead
  궤적 비교(오버라이드 유/무). **핵심 발견**: 라우트1 이벤트는 단일
  오탐 스파이크가 아니라 aLeadK가 최대 -2.96까지 악화되는 진짜 지속적
  감속이었고, TTC도 같은 구간에서 자연 하강(정상경로도 결국 수렴).
  threshold 강화(-1.8→-2.5)는 오탐을 "제거"가 아니라 "조기발동 구간을
  0.754s→0.410s(약 46%)로 단축"하는 효과였음 — 사용자 재확인 필요.


- `long_mpc.py`: `LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH` -1.8 -> -2.5
  (라우트1 실측 aLeadK=-2.07 오탐 해소, 3라우트 근거). `discontinuity_
  jerk_boost`에 신규 트리거 소스 `low_speed_strong_decel` 추가 —
  handoff/discontinuity_lc와 동일한 hold(4.0s)+release-rate(100/s)
  경로 재사용, danger 지속 중엔 a_change_cost=base 유지(즉시반응 방해
  없음)하고 해제 직후부터만 도달과정을 완만화.
- `sim_low_speed_decel.py`: 시나리오 E(라우트1 threshold 회귀 재현,
  신threshold 미발동 확인)/F(진짜 강한감속 -3.0 여전히 발동 확인)/
  G(jerk_boost 신규 소스 arm/hold/release 검증) 3건 추가, 기존 B는
  threshold 상수와 동기화하도록 하드코딩값 제거. 전체 7건 PASS.

## 2026-08-28 (111차, match_dashcam_clip_to_route.py 신규)
`_clip.mp4` 파일명 타임스탬프만으로 route CSV t구간 특정이 안 되는
문제(HUD 시:분만 표시, 저장시각≠시작시각, 최대 ~50초 편차 실측)
해결용. blinker 클러스터의 상대 시간차+급감속 강도로 매칭.
947fbb7dc6 클립 2건(113702/113848) 성공 매칭 검증 — README 참고.

## 2026-08-28 (109차, patched_replay_v109.py 신규)
옵션1 patch(`long_mpc.py`, `discontinuity_lc` 전용 danger confirm-hold
0.25s, 커밋 `b84eeb8`) 사전검증용 PATCHED replay 작성.
`LaneChangeGateReplay` 상속, `scan_force_revert_episodes.py`와 나란히
before/after 비교. 캐시 `a5b1ce4e42`에서 검증 완료(경미 사례 흡수,
지속 사례 축소+진짜위험 보존), 108차 severe 사례(947fbb7dc6)/handoff
사례(ad830211ff)는 원본 소실로 미검증 — FINDINGS.md 109차 참고.

## 2026-08-28 (108차, scan_force_revert_episodes.py 신규)
`replay_lane_change_discontinuity_gate.py`의 `LaneChangeGateReplay`
(duration_mode='full')로 여러 라우트를 라우트-전체-연속-재생 방식
일괄 스캔해 force_revert 에피소드를 뽑는 도구 신규 작성. 30라우트
실주행 확대검증(신규 18개+기존 캐시 12개)에 사용, 106차/107차의
"차선변경이 force_revert 필요조건" 결론 재확정(force_revert 5건 —
discontinuity_lc 3건 전부 blinker=True, handoff 2건 정상범위, 순수
discontinuity 0건). 개발 중 트리거 소스별 boost_s 미구분 버그가 있던
초안(`flicker_cluster_boost_replay.py`)은 허위 severe 사례를 냈던 것
확인 후 폐기 — 상세는 FINDINGS.md 108차 참고.

## 2026-08-28 (100차) — `verify_resample_np.py` 신규
- 99차가 찾은 carrot_man.py `LineString.interpolate()` 반복호출 →
  numpy 벡터화(`resample_10m_np`) 대체 패치 전, 원본과의 수치 동일성
  검증용 스크립트 신규 작성. 랜덤경로 20개+급커브+직선+경계조건+600m급
  전부 PASS(최대오차 1.2e-13m). 100차 패치(carrot_man.py) 채택 근거.

## 2026-08-26 (86차 체크포인트) — `decode_rlog.py` 잘린 rlog.zst 스트리밍 폴백 추가
- `c3-ms-curv` 실주행 로그 10개 route(00000329~00000332) CSV 추출 중
  `0000032e--8b55ac185d_x13seg`의 마지막 세그먼트(12번) `rlog.zst`가
  드라이브 종료 시점에 파일 자체가 잘려 기록됨(zstd 프레임 미완성) →
  기존 one-shot `dctx.decompress()`가 "did not decompress full frame"
  으로 전체 추출 중단시키는 문제 발견.
- `iter_events()`에 폴백 추가: one-shot 실패 시 `stream_reader`로 재시도
  — 잘린 지점까지의 유효 데이터는 정상 회수됨(zstd 프레임 경계 문제일
  뿐 내용 자체는 유효, `read_across_frames=True`). 폴백 발동 시
  stderr에 경고 로그 남김(일부 row 유실 가능성 인지용).
- 정상 파일로 회귀 테스트 통과(동일 이벤트 수 재현 확인). 해당 세그먼트
  재추출 결과 785 row 회수, 나머지 12개 세그(14400 row)와 합쳐
  15185 row 정상 완료.

## 2026-08-26 (80차 계속) — 미편입 검증 스크립트 4개 소급 정식 편입
- 80차 정책 강화(아래 항목) 직후 WIP.md/FINDINGS.md 전체를 훑어
  "toolkit 미편입" 상태로 세션 컨테이너(`work/`)에만 있다가 컨테이너
  리셋으로 유실된 재사용 가치 높은 검증 스크립트 4개를 식별, 현재
  코드 기준으로 재작성 후 정식 편입:
  - `sim_jerk_boost.py` (66/67차 방안G a_change_cost boost, 69차부터
    "실물 존재 확인" 미해결로 이월되던 항목 — 이번에 처음 실물 작성)
  - `sim_res_button.py` (79차 +RES accelCruise 버그 패치 검증)
  - `test_launch_bypass.py` (45차 launch bypass 로직 검증)
  - `test_scc_gate.py` (37차 SCC 단일점 폴백 dPath 게이트 검증)
- 4개 전부 현재 `long_mpc.py`/`cruise.py`/`radard.py`와 대조해 재검증
  통과 확인. `ryu` 코드 변경 없음(검증 스크립트만 추가).

## 2026-08-26 (80차) — 도구 재사용/신규저장 정책 강화 (코드 변경 없음, 문서만)
- 다른 계정 세션이 `toolkit/README.md`를 확인하지 않고 기존 도구를
  중복 재작성하는 사례가 반복돼 정책을 더 눈에 띄게 강화.
  `PROJECT_INSTRUCTIONS.md`(다른 계정이 그대로 붙여넣는 프로젝트
  지침 본문)에 "먼저 찾는다/새로 만들면 반드시 레포에 넣는다" 2개 규칙을
  직접 명시(기존엔 SETUP.md를 참고하라는 링크뿐이었음). `toolkit/
  README.md` 최상단에도 동일 내용의 필독 배너 추가. `SETUP.md`의
  0-1/0-2 항목(63차 도입)은 내용 변경 없이 그대로 유지 — 이번 변경은
  기존 정책을 더 강하게 노출시키는 것뿐, 새 규칙 추가 아님.

## 2026-08-26 (76차) — replay_lane_change_discontinuity_gate.py duration_mode='full' 추가
- 75차 gate_only 모드(게이트만 frac 무관 완화, hard-hold 1.0s 그대로)가
  남긴 한계(hard-hold 소진 후 실제 aEgo 최저점에서 무력화, WIP.md 75차
  계속2)에 대응 — `duration_mode='full'` 신규: 차선변경 중 discontinuity
  트리거를 소스 'discontinuity_lc'로 태깅해 handoff와 완전히 동일한
  게이트+hard-hold(4.0s)+release-rate(100/s) 경로를 타도록 재현.
  route2 t=1470.75 이벤트 재검증 — gate_only는 최저점(t=1472.40)에서
  a_change_cost=20으로 무력화, full은 500(완전부스트) 유지 확인.
  route1/route2 전체 회귀 스캔 — diff 프레임 전부 소스='discontinuity_lc'
  (일반 discontinuity/handoff 소스는 diff 0, danger_active 회귀 없음).
  상세는 FINDINGS.md 76차 참고.

## 2026-08-26 (73차 계속2) — replay_boost_duration.py split_gate 옵션 추가
- `BoostReplay`에 `split_gate` 파라미터 추가: 트리거 소스(dRel
  discontinuity vs 레이더 핸드오프)별로 boost 게이트 분리 — 레이더
  핸드오프(방안I) 트리거는 danger_active 단독 게이트, dRel
  discontinuity(방안C/G)는 기존 `frac<=0.0` 게이트 유지. 검증 결과
  게이트차단이 완전히 0으로 해소되고 duration 연장에 비례해 coverage가
  실제로 증가함 확인(route2 3.0s+split_gate 44.2%). danger_active
  회귀 자동 체크 로직도 추가(경고 없음 확인). `candidates` 튜플이
  `(label, boost_s, release_rate, split_gate)` 4-tuple로 변경.
  상세는 FINDINGS.md 73차 계속 참고.

## 2026-08-26 (73차) — replay_boost_duration.py 신규
- boost duration 연장 가설(72차) 검증용 replay 스크립트 신규 작성.
  `data_routes.py`로 route1/route2 실측 로드 → discontinuity 트리거+
  boost 게이트(danger_active/frac<=0.0)까지 실측 재현해 duration
  후보별 "실제 boost 적용 시간"을 위험구간 대비 커버리지로 비교.
  **핵심 발견: duration을 1.0→3.0s로 늘려도 커버리지 0.0% 그대로 —
  병목은 duration이 아니라 frac<=0.0 게이트 자체(72차 가설 정정).**
  상세는 FINDINGS.md 73차 참고.

## 2026-08-25 (63차/63차 계속) — 검증 스크립트 항상 toolkit 저장 원칙 시행
- **`sim_drel_discontinuity.py` 신규 편입**: 61차 계속(방안C, cutin
  dRel 불연속 감지) 로직 단위 합성검증. 원래 work/ 스크래치였다가
  컨테이너 리셋으로 유실 → 재작성하며 이번엔 toolkit에 정식 편입.
  6개 시나리오 PASS(기존4 + 신규등록 이중트리거/danger override
  독립성 2건 추가).
- **`replay_drel_discontinuity_real.py` 신규**: 방안C를 실측 CSV로
  PATCHED/UNPATCHED 비교 재생. r1-3(seg3) 원본 rlog 재검증에서
  **방안C가 r1-3류(radar 락온 빠름)엔 효과 있으나 r1-14류(radar
  락온 느림)엔 무효**임을 발견 — `frac_rate`/`frac_ttc`가
  `_vision_dRel_rate`를 discontinuity suppression과 무관하게 직접
  읽는 구조적 보호 공백. 방안 D(두 값도 함께 리셋) 후속 설계 필요.
  FINDINGS.md "[63차 계속, 중요]" 항목 참고.
- **[정책 변경]** 앞으로 신규 작성 검증/시뮬레이션 스크립트는 검증
  상태와 무관하게 **작성 즉시 toolkit에 커밋**한다(이전엔 "실제 로그
  검증 전까지 work/ 스크래치 유지" 원칙이었으나, 컨테이너 리셋으로
  같은 스크립트를 최소 2번(58차1번 `test_visiontrack_gate.py`, 이번
  `sim_drel_discontinuity.py`) 재작성하는 낭비가 반복돼 원칙 폐기).
  자세한 내용은 `SETUP.md` 참고.

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

## 2026-08-25 (72차 계속3, data/routes/ 신설)
- `data/routes/` 구조 신규: 라우트별 추출 CSV를 gzip 압축해 devnotes
  레포에 직접 저장(route_id 폴더 아래 `route.csv.gz` + `meta.json`),
  세션마다 로그 zip 재업로드/재추출 없이 재사용 가능하게 함.
  route1(`ea5bcc0566`, x19seg, 22800행)/route2(`a5b1ce4e42`, x7seg,
  7859행) 최초 등록 — 둘 다 72차 "boost 윈도우 구조적 부족" 가설
  재현에 쓴 검증 세트. 목록/구조는 `data/routes/README.md` 참고.
- `data_routes.py` 신규: `load_route()`/`list_routes()` — 위 gzip
  캐시를 `analysis_helpers.load_csv()`와 동일한 형태로 로드.

## 2026-08-26 (75차, replay_lane_change_discontinuity_gate.py 신규)
- `replay_lane_change_discontinuity_gate.py` 신규: replay_boost_duration.py의
  BoostReplay 로직을 재사용해, 차선변경(blinker+hold) 중 discontinuity
  트리거도 frac 게이트를 무관하게 완화하는 방향(b)을 정량 검증. route2
  t=1460~1480/1535~1550 두 구간 + route1/route2 전체 회귀 diff 스캔.
  결과 요약은 FINDINGS.md "75차 계속2" 참고.

## 2026-08-26 (84차, sim_route_dynamic_cap.py 신규)
- `sim_route_dynamic_cap.py` 신규: route 커브 lookahead 300m 고정 캡을
  v_ego/accel_limit 기반 동적 캡(300~500m)으로 교체한 로직(`carrot_man.py
  compute_route_lookahead_distance()`) 회귀 검증. 저속 floor 유지/고속
  ceil clip/단조성/예외 안전폴백 4개 시나리오 PASS. 상세는 FINDINGS.md
  84차 항목 참고.

## 2026-08-26 (86차, five_item_scan.py 정식 편입)
- `five_item_scan.py` 신규: 55/56차의 "5개 항목 종합분석"(카메라인식감속/
  정지앞차감속/정지후재출발/레이더락온저크/곡선구간감속) 절차를 재현하는
  `stopped_lead_decel_events`/`launch_after_stop_events`/
  `radar_lockon_jerk_events` 3개 함수 신규 구현(기존 55차 로직 설명을
  기반으로 재현) + 기존 `vision_to_radar_crossover`/`turn_speed_violations`
  통합. work/ 스크래치로만 2회(56차/86차) 유실됐던 것을 이번에 정식 편입.

## 2026-08-26 (90차, sim_route_curvature_sample.py 신규)
- `sim_route_curvature_sample.py` 신규: 89차 대안1(route 곡률 샘플링
  chord 축소, sample 4->2/3) 검증. raw navi_points가 로그에 없어
  desiredCurvature 시간적분으로 실주행 경로를 재구성해 대체 입력으로
  사용. 결과: sample 축소 효과가 미미(~2.5km/h)해 실제 관측된 48km/h
  갭을 설명 못함 -- 대안1 단독으로는 불충분하다는 결론. 상세는
  FINDINGS.md 90차 참고.
- 2026-08-27 (93차): `sim_route_margin_regression_scan.py` 신규 —
  91차(ROUTE_ENTRY_MARGIN_KPH) 회귀검증용 전체구간 margin 스윕
  스크립트. 국도 연속곡선 route(0000032d--c0e3054c4a)로 검증, 직선
  오탐 0건/조기개입 정점목표값 불변/역전버그 0건 확인.

## 2026-08-27 (94차, sim_drel_discontinuity_d.py 신규)
- `sim_drel_discontinuity_d.py` 신규: 63차 계속(r1-14 사각지대)에서
  발견됐던 "방안C만으로는 frac_rate/frac_ttc가 discontinuity 트리거
  이후에도 오염된 채 유지"되는 문제를 해소하는 94차(방안D, discontinuity
  트리거 시 `_vision_dRel_rate`/`_vision_dRel_rate_window`/
  `_vision_dRel_prev`도 함께 리셋) 로직 단위 검증. 4개 시나리오 전부 PASS
  — r1-14류(radar 락온 지연) 재현 시 UNPATCHED는 트리거 이후에도
  frac_rate=1.0 유지 vs PATCHED는 트리거 프레임에서 즉시 0으로 리셋,
  정상 완만접근/r1-3류(radar 즉시 락온) 회귀 없음 확인. 상세는 WIP.md/
  FINDINGS.md 94차 참고.

## 2026-08-28 (101차 후속 — CPU/메모리 전체 재점검)
- 신규: `toolkit/scan_perf_antipatterns.sh` — 실시간 루프 파일들에서
  deepcopy/미캐싱 Params.get/print/re.compile/threading/subprocess/
  unbounded append/dict 누적/비벡터화 for-loop 등 CPU·메모리 안티패턴
  후보를 grep으로 일괄 스캔. 매치는 컨텍스트 확인 필수(오탐 흔함).

## 2026-08-28 (107차, radar_source_flicker_scan 신규)
- `analysis_helpers.radar_source_flicker_scan()` 신규: 106차 "차선변경 중
  leadRadar 핸드오프 반복 급감속" 정량화용. leadRadar(True/False) 엣지가
  짧은 시간(window_s) 안에 min_flips회 이상 몰리면 클러스터로 묶고,
  blinker 겹침 여부/최대 dRel 점프/would_trigger_ttc_danger를 함께 계산.
  **107차에서 leadRadarTrackId(63차 계속3에 이미 존재, 106차가 "없음"으로
  오판했던 컬럼)를 확인해보니 이 차량(SCC 단일점, 코너레이더 없음)에서는
  radar=True 프레임의 값이 항상 0으로 고정 — 트랙ID 자체는 변별력 없음
  확인(캐시 라우트 3건 전수). 캐시된 12개 라우트 전체 스캔 결과 51클러스터
  중 21건(41%)만 blinker 겹침, 59%는 블링커 무관 — 106차의 "차선변경
  특유의 버그"라는 결론이 표본(3건)에 국한된 것이었을 가능성 제기됨.
  상세는 WIP.md/FINDINGS.md 107차 참고.
