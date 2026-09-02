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

## check_device_build.py (178차 신규)
**목적**: `extract_log.py` meta.json의 "repo commit"은 분석 컨테이너
checkout일 뿐 **디바이스가 실제로 실행한 빌드가 아님**(기존 원칙, 178차에서
실제로 이 구분이 결정적이었던 사례 발생). rlog/qlog의 `InitData` capnp
이벤트를 직접 읽어 디바이스가 기록한 `gitCommit`/`gitCommitDate`/
`gitBranch`/`dirty`를 추출하고, 로컬 repo 히스토리 존재 여부 + 특정 커밋의
조상인지까지 확인.
**의존성**: `decode_rlog.py`(get_schema/iter_events 재사용), `ryu` repo clone.
**사용**:
```bash
python3 check_device_build.py <route_dir> --repo /home/claude/ryu \
    [--compare-commit <hash>]
```
**주의**: `dirty=True`면 빌드 시점 워킹트리에 커밋 안 된 로컬 변경이 있었다는
뜻이므로, gitCommit 해시가 맞더라도 "그 커밋 코드 그대로 실행 중"이라고
단정할 수 없음. 또한 gitCommit 해시가 로컬(unshallow) repo 히스토리에
아예 없는 경우도 있을 수 있음(178차 실측 사례: 해시가 origin 어디에도 없고
GitHub이 "not our ref"로 거부 -- 원인 미상, 사용자 확인 필요한 케이스로
FINDINGS.md 178차 참고). 패치 반영 여부를 "확정"이 아니라 "확인 시도"로
취급하고, 불일치 발견 시 반드시 사용자에게 보고 후 빌드 절차를 확인할 것.

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
laneChangeDirection, activeLaneLine(144차), lllProb/rllProb/lllStd/
rllStd(145차 — modelV2.laneLineProbs[1]/[2], laneLineStds[1]/[2],
AdjustLaneOffset 게이트값 d_prob 재현용), activeCarrot/xTurnInfo/
xDistToTurn/xSpdType/xSpdDist/atcType/leftSec/xSpdCountDown/
xTurnCountDown(146차 — carrotMan의 route/TBT/ATC 회전제어·카운트다운
관련 필드. 146차 정량검증으로 "AutoTurnControl"/"AutoNaviCountDownMode"
설정값이 0(off)인지 판별하는 용도로 실사용 확인됨 — atcType이 항상
"none"이고 xSpdCountDown/xTurnCountDown이 항상 100이면 두 설정 모두
꺼져있다는 뜻. 주의: carrot_serv.py 내부 변수 `active_kisa_count`는
cereal에 미발행이라 이 CSV로는 뽑을 수 없음)`
**사용**:
```bash
python3 extract_log.py /home/claude/work/route /home/claude/work/route.csv \
    --repo /home/claude/ryu [--max-mb 400]
```
**2026-08-31 추가(169차 계측)**: `vpPosPointLatNavi`/`vpPosPointLonNavi`/
`dtNaviPacketAge`/`positionDtSinceFix` 컬럼 추가 -- carrot_serv.py
`_update_gps()`에 있던 "내부GPS 폴백" 타임아웃 판정이 "패킷 도착" 기준
이라 "패킷은 오지만 내용 정지"인 실패모드를 못 잡는 문제(FINDINGS.md
169차 NEEDS_INVESTIGATION)를 다음 실차 로그에서 CSV만으로 직접
구분하기 위한 계측. `dtNaviPacketAge > 3.0`이면 "패킷단절",
`dtNaviPacketAge < 3.0`인데 `vpPosPointLatNavi/LonNavi`가 여러 프레임
그대로면 "내용정지". `positionDtSinceFix`는 162/163/167차 게이트가
실제로 읽는 값(`carrot_serv.position_dt_since_fix`) 원본. 이 계측은
`0001-add-navi-gps-telemetry-instrumentation.patch`(169차)로 `ryu`
본체(`cereal/custom.capnp`, `carrot_serv.py`)에 실제로 적용해야만
새 rlog에 찍힘 -- **패치 적용 전 로그(과거 route)에는 이 4컬럼이
전부 0.0으로 나옴(capnp 기본값, 크래시 아님)에 주의**.

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
**2026-08-30 수정(144차)**: `activeLaneLine`(controlsState, `controlsd.py`
line360 `cs.activeLaneLine = self.lanefull_mode_enabled`) 컬럼 추가 —
140차 PathOffset 레인리스 반영 패치 실차검증에 필수. True=레인풀
(차선기반 MPC curvature 사용), False=레인리스(140차 패치 전이면
model_v2 직접출력, 140차 패치 후 PathOffset!=0이면 MPC curvature로
전환). **이 필드가 없는 과거 CSV로는 오프셋이 실제로 반영된 프레임인지
구분 불가능** — 오프셋 관련 재분석 시 반드시 재추출 필요. PathOffset
원시값(Params, cereal 미기록)은 여전히 CSV로 못 뽑음.
**2026-08-30 추가(149차)**: `liveRouteSpeed` 컬럼(기본 항상 포함, 플래그
불필요) — `carrotMan.szPosRoadName`에 `carrot_serv.py` L1100
`self.debugText += f"route={{route_speed:.1f}}"`로 이미 20Hz 발행
중이던 텍스트를 정규식(`route=(-?\d+(?:\.\d+)?)`)으로 파싱한 값.
이 값은 `calculate_curvature()`+`V_CURVE_LOOKUP`의 순수 곡률값이 아니라
**역방향 가속도제한 DP(entry margin/time_delay 스케줄링, `carrot_man.py`
`carrot_navi_route()` 후반부, 132차 램프리미터 포함)까지 통과한 최종
route_speed**다 — `recompute_route_curvature_speed()`(147차, DP 이전
순수 곡률만 재현)로는 원천적으로 재현 불가능했던 부분이자, 148차
`replay_route_full_pipeline.py`가 `nRoadLimitSpeed` 미기록으로 재현
포기(오차 98.7kph)했던 문제를 **재현이 아니라 실측 직접추출**로
해결한다. `desiredSpeed`/`src`(carrotMan.desiredSpeed/desiredSource,
이미 추출 중)와 나란히 놓고 보면 "route가 왜 arbitration에서 안
뽑혔는지"(값 자체가 안 낮아졌는지 vs 낮아졌는데 다른 소스가 더
낮았는지)를 직접 구분 가능(149차 실사용례: 전자로 확정 — FINDINGS.md
149차 참고). 파싱 실패(szPosRoadName에 "route="가 없는 프레임,
예: 132차 조건상 계산 자체가 스킵된 경우 등)면 빈 문자열.
**주의**: naviPaths와 마찬가지로 route src 관련 조사에서만 의미 있는
값 — TurnSpeedControlMode가 route를 애초에 후보에서 배제하는 설정
(1)이면 route_speed 자체는 계속 계산·발행되지만 항상 무시된다(코드
로직상 speed_n_sources 참가 여부와 route_speed 계산 자체는 무관).

**2026-08-30 추가(147차)**: `--with-navi-paths` 플래그(기본 off) —
켜면 `naviPaths` 컬럼(carrotMan.naviPaths, `carrot_navi_route()`가
곡률 계산에 실제로 쓰는 로컬(x,y) 리샘플 폴리라인+거리를
`"x1,y1,d1;x2,y2,d2;..."` 텍스트로 20Hz 발행 중이던 필드 — **ryu 코드는
원래부터 이 데이터를 발행하고 있었고, extract_log.py가 안 뽑고 있었을
뿐**, 89차/90차가 제안했던 신규 계측 패치는 불필요했음)을 채운다.
row당 최대 ~1200자로 다른 컬럼 대비 훨씬 커서 기본 추출엔 포함 안 함 —
route 커브/교차로 사전감속 관련 조사에서만 켤 것. 파싱/재계산은
`analysis_helpers.parse_navi_paths()` / `recompute_route_curvature_speed()` 참고.
```bash
python3 extract_log.py /home/claude/work/route /home/claude/work/route.csv \
    --repo /home/claude/ryu --with-navi-paths
```

**2026-08-31 추가(182차 계측)**: `naviPointsActive`/`navdActive`/
`dtRouteInactive`/`routeSource` 컬럼(기본 항상 포함) -- carrot_man.py의
`navi_points_active`(route 폴리라인 활성 플래그)가 이전엔 cereal 미발행이라
"route 사전감속이 61초간 전혀 없었음"(FINDINGS.md 182차, route=390.0
"제약없음" 기본값 노출) 같은 드롭아웃 현상을 rlog만으로 사후분석할 수
없었던 문제 대응. `dtRouteInactive`는 비활성 지속시간(초, True면 0.0),
`routeSource`는 마지막으로 route를 성공 수신한 경로("navd"=navd cereal
채널/"tcp_raw"=TCP 7709/"tcp_navi"=TCP 7712 handle_route, 성공 수신시만
갱신·비었으면 그대로 유지). **162/163차 게이트(positionDtSinceFix)와는
별개의 상위 실패모드**: 163차는 "route가 오는데 위치추정이 부정확한"
경우를 다루고, 182차는 "route 자체가 애초에 안 옴"인 경우. 진단은
`check_navi_route_activity.py` 참고. 이 계측은
`0001-navi-route-activity-instrumentation.patch`(182차)로 `ryu` 본체
(`cereal/custom.capnp`, `carrot_man.py`, `carrot_serv.py`)에 실제
적용해야만 새 rlog에 찍힘 -- **패치 적용 전 로그(과거 route)에는 이
4컬럼이 전부 기본값(False/False/0.0/"")으로 나옴(크래시 아님)에 주의**.

## scan_type3_curvature_blindspot.py
**목적**: 152차가 확정한 "유형3"(naviPaths 원본 폴리라인 좌표 자체가
급회전을 담고 있지 않은 경우 -- chord 샘플 간격을 줄여도 못 잡음) 이벤트를
blinker 없이 자동 탐지(`analysis_helpers.type3_curvature_blindspot_scan()`).
naviPaths가 근접(기본 50m 미만) 이후~원거리(기본 250m 이내) 구간에서
median 기준 사실상 직선(speed_cap이 임계값 이상)인데, 그 이후
lookahead_s(기본 6초) 안에 실제 steeringAngleDeg 급변(기본 60도 이상,
0.3초 이상 지속)이 오면 이벤트로 기록. 근접(0~50m) 구간은 ego 진입
앵커 전환 노이즈로 자체 curvature가 튈 수 있어(187차 발견) 판정에서
제외 — 이 노이즈를 포함해 min()으로 판정하면 실제 유형3 사례를 오히려
"이미 곡률을 잡고 있다"고 오탐할 수 있음(187차 seg14/15 검증으로 확인).
**사용**:
```bash
python3 extract_log.py <route_dir> <out.csv> --repo /home/claude/ryu --with-navi-paths
python3 scan_type3_curvature_blindspot.py <out.csv>
# 파라미터 조정 예:
python3 scan_type3_curvature_blindspot.py <out.csv> --lookahead 8.0 --steering-thresh 45.0
```
**의존성**: `analysis_helpers.load_csv`,
`analysis_helpers.type3_curvature_blindspot_scan`(내부적으로
`parse_navi_paths`/`recompute_route_curvature_speed` 재사용).
**전제**: `--with-navi-paths`로 뽑은 CSV 필요(없으면 이벤트 0건).
**187차 검증**: seg14/seg15(우회전 교차로 route 미탐지 실사례,
FINDINGS.md 187차)로 실행 시 확인된 실제 구간(t≈1370.06 포함,
t=1365.71~1376.56)을 정확히 이벤트로 포착.

**188차 추가(`type3_curvature_blindspot_scan_v2`, `--v2` 플래그)**:
v1(median 단독 판정)이 "far_window 안에 실제 짧은 커브가 있지만 앞뒤
긴 직선 때문에 median이 희석되는" 케이스를 오탐으로 잡는 것을
seg14/15 재검증 중 발견(신규 B, t=1352.76~1361.91 — 대시캠 확인 결과
일반 도로커브, naviPaths도 실제 곡률(d=80~100m, 5km/h)을 담고
있었음). v2는 1단계(median 후보 발굴)는 v1과 완전 동일하게 유지한
채, 2단계로 far_window 내 저속 지점의 연속길이(`--low-cap-run-m`,
기본 20m)/비율(`--low-cap-ratio`, 기본 0.15)을 추가 검사해 오탐을
분리한다. `--low-cap-eval-start`(기본 80m) 미만 구간은 근접 앵커전환
노이즈 번짐(188차 발견, 187차 사례 초반부에서도 관찰됨)으로 보고
2단계 판정에서 제외 — `near_field_guard_m`(1단계, 50m)와는 별개
파라미터. **188차 회귀테스트**: 187차 기존 사례+신규A(대시캠 확인된
진짜 유형3, t=1336.76~1346.65)는 accepted 유지, 신규B는 rejected로
정확히 분리됨(상세는 FINDINGS.md/WIP.md 188차 참고). 기본 CLI 동작은
여전히 v1(회귀 없음) — `--v2 --show-rejected`로 2단계 판정 + 오탐
사유 확인 가능.

**191차 추가(`type3_curvature_blindspot_scan_v3`, `--v3` 플래그)**:
190차 25분 전수스캔 중 발견한 새 오탐 유형(a) — 급정거/장기정차 후
xTurnInfo reset으로 naviPaths가 "제약없음" 기본값으로 복귀하는데,
정차 중에도 steeringAngleDeg는 감긴 채 유지되어 여러 프레임이 계속
후보를 생성·병합, 실제로는 route가 정상 완주한 급선회를 50초 이상의
긴 오탐 이벤트로 부풀리는 문제(190차 4번/6번)를 보완. v2 로직/파라미터는
그대로 두고, vEgo가 `--stop-v-ego-thresh`(기본 0.3m/s, 프로덕션
`LAUNCH_BYPASS_STOP_V_EGO` 재사용) 미만인 프레임은 (1) 후보 생성에서
제외, (2) 두 후보 사이에 `--min-stop-duration`(기본 1.0초) 이상 정차가
있으면 `--merge-gap` 이내라도 강제로 이벤트 분리하는 3단계 게이트를
추가. 합성 데이터 단위테스트로 게이트 동작 확인(WIP.md 191차 참고).
**190차 오탐 유형(b)(국지적 실제 커브가 far_window median에 희석/
low_cap_eval_start_m 경계를 비껴가는 문제)는 다루지 않음** — 관련
파라미터가 187차 확정사례를 지키도록 이미 튜닝되어 있어 실측 데이터
없이 건드리면 회귀 위험. **실측 8개 회귀 세트 재실행은 미실시**
(routeA.csv/routeB.csv 190차 종료 시 미보관, 원본 zip 재업로드 필요).
기본 CLI 동작은 여전히 v1 — `--v3 --show-rejected`로 3단계 판정 +
오탐 사유 확인 가능.

## check_navi_route_activity.py
**목적**: `naviPointsActive`(182차 계측) 연속 False 구간을 찾아 드롭아웃
지속시간/직전 route 소스/vEgo 범위를 리포트. 182차 계측 패치 적용 전
로그(구 CSV)에는 `--fallback-naviPaths`로 naviPaths 텍스트 공백 +
liveRouteSpeed==390.0 휴리스틱 근사 모드 사용 가능(정확도 낮음, 원인
소스는 알 수 없음 -- 182차 최초 분석이 실제 썼던 수동 방법과 동일).
**사용**:
```bash
python3 extract_log.py <route_dir> <out.csv> --repo /home/claude/ryu
python3 check_navi_route_activity.py <out.csv> --min-duration 3.0
# 계측 패치 적용 전 로그:
python3 extract_log.py <route_dir> <out.csv> --repo /home/claude/ryu --with-navi-paths
python3 check_navi_route_activity.py <out.csv> --fallback-naviPaths
```
**의존성**: `analysis_helpers.load_csv`.

**2026-08-31 추가(165차)**: `ccYawDeg`/`ccYawRateZ`/`ccPoseValid` 컬럼(기본 항상
포함, 플래그 불필요 — 프레임당 숫자 3개뿐). `carControl.orientationNED[2]`
(라디안, calibrated NED 요/헤딩)를 나침반 표기(0~360도)로 변환한 `ccYawDeg`,
`carControl.angularVelocity[2]`(calibrated 요레이트 rad/s 원시값) `ccYawRateZ`,
두 List가 실제로 채워져 있는지(`controlsd.py`가 `calibrated_pose is not None`일
때만 채움, 그 전엔 빈 List) 나타내는 `ccPoseValid`. **`livePose`를 직접 안 뽑고
`carControl`에서 뽑는 이유**: `carrot_serv.py` L729의 기존 TODO 주석이 이미
"`CC.orientationNED[2]`를 이용하여" 보정하라 명시해뒀고, `controlsd.py`
L250-252가 캘리브레이션 보정까지 끝낸 값을 100Hz로 `CarControl`에 이미
싣고 있어 `carrot_man.py`가 이미 구독 중인 `'carControl'`(L306)에서 바로 꺼내
쓸 수 있음(raw `livePose` 구독은 신규 서비스 추가+자체 캘리브레이션 처리가
필요해 더 무거움). 목적: 162차 근본원인(`_update_gps()`가 쓰는 bearing이
외부 GPS 정체 중 옛 헤딩으로 직진외삽)에 대한 **방향1(헤딩보정, FINDINGS.md
165차 설계)**의 synthetic/실측 검증용 지상진실(ground truth) 확보. **주의**:
165차 이전에 뽑힌 CSV(`aeeed9e4a5` seg0/seg3 등 162~164차가 쓴 것 포함)에는
당연히 없음 — 방향1 검증을 이 route로 하려면 반드시 재추출 필요.

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

**2026-08-30 추가(147차) — naviPaths 기반 route 곡률 과소평가 직접검증**:
`extract_log.py --with-navi-paths`로 뽑은 CSV 전용 신규 함수 3종.
- `parse_navi_paths(navi_paths_str)` — `"x1,y1,d1;x2,y2,d2;..."` 텍스트를
  `([(x,y),...], [d,...])`로 파싱.
- `recompute_route_curvature_speed(points, distances, sample=4, sample_fine=None)` —
  `carrot_man.py::carrot_navi_route()`의 3점 곡률(40m 간격)+
  `V_CURVE_LOOKUP` 계산을 실측 폴리라인에 그대로 재현해
  `(distance, curvature, speed_cap)` 리스트 반환. 역방향DP/시간지연
  스무딩은 미포함(순수 "이 지점 곡률이 실제로 얼마나 급한가"만 확인).
  **2026-08-30 추가(147차 계속)**: `sample_fine` 파라미터 — 지정하면
  매크로 `sample`(기본 4)은 그대로 두고 같은 폴리라인에 `sample_fine`
  간격(예: 1=10m chord)으로 한 번 더 계산해 같은 위치에서 speed_cap이
  더 낮은(더 급한) 쪽을 채택(merge)한 리스트를 반환. `carrot_man.py`의
  `ROUTE_CURVATURE_FINE_SAMPLE` 패치(147차 계속)와 완전히 동일 로직 —
  검증도구가 실제 프로덕션 패치와 항상 일치하도록 반영됨. 내부적으로
  단일 계산은 `_route_curvature_single_pass()` 헬퍼로 분리.
- `route_curvature_underestimate_scan(rows, min_gap_kph=15.0)` —
  `src=="route"`인 각 행에서 실제 발행된 `desiredSpeed`와
  `recompute_route_curvature_speed()`의 그 시점 최소값을 비교, 갭이
  `min_gap_kph` 이상이면 리포트. 갭이 크면 "폴리라인 자체는 이미
  충분히 급한데 다른 로직(역방향DP 스케줄링)이 못 살렸다"는 뜻, 갭이
  작으면 "폴리라인 형상 자체가 이미 뭉툭하다"(89차/90차가 의심했던
  지도 데이터 정밀도 가설)는 뜻으로 해석.
합성 90도 코너(직진80m-급코너-직진80m) 단위테스트로 정점에서
curvature=0.03/speed_cap=20.5kph 정확 포착 확인(PASS) — 실측 raw
navi_points가 있으면 sample 자체는 문제 없이 작동함을 재확인, 89차/90차가
남겨둔 "chord 길이 문제 vs 지도 데이터 형상 문제" 질문은 이제 실제
교차로 로그로 직접 답할 수 있음.

**2026-08-30 결론(147차 계속)**: `898edd0f96` seg10 실측으로 위 질문에
직접 답함 — **chord 길이 문제가 맞았음**. sample=4(40m) 단독은 실제
R≈27m 커브를 R≈110m로 평활화해 0.02 임계값 아래로 숨김(90차의
"chord 축소 효과 2.5km/h뿐" 결론은 `desiredCurvature`를 적분
재구성한 경로에 같은 로직을 다시 돌리는 순환논리 오류였음). sample=1
(10m)로는 R≈27m/10.1km/h까지 정확 포착, 같은 로그 직선구간에서는
오탐 없음(max curvature 0.0146 < 0.02 임계값). `ROUTE_CURVATURE_FINE_SAMPLE=1`
패치로 `carrot_man.py`에 반영 완료(commit `ffad14e`). 상세는
FINDINGS.md "147차 계속" 참고.

**버그 수정(147차 계속)**: `extract_log.py` — `process_segment()`가
만드는 row dict는 `--with-navi-paths` 플래그와 무관하게 항상
`naviPaths` 키를 갖는데(플래그 off 시엔 값만 빈 문자열), FIELDNAMES엔
이 컬럼이 없어 `csv.DictWriter`(extrasaction 기본 "raise")가 플래그
사용 여부와 상관없이 "dict contains fields not in fieldnames"로 항상
크래시하던 버그. FIELDNAMES에 `naviPaths`를 항상 포함하도록 수정 —
플래그 off일 땐 컬럼은 존재하되 값이 항상 빈 문자열.

- `required_decel_gap_scan(rows, near_stop_target_kph=15.0)` — (2026-08-30,
  151차 신규) `liveRouteSpeed`(149차) 컬럼을 이용해, 근정지급 target(기본
  ≤15kph) 코너에 대해 "fine 곡률 첫 감지 시점(t_detect)~코너 진입
  시점(blinker on, t_arrive)" 구간의 실측 감속률(`actual_decel_kphps`,
  liveRouteSpeed 선형회귀 기울기)과 물리적으로 필요한 감속률
  (`required_decel_kphps`, 등가속도 공식 역산)을 비교해 갭을 리포트.
  149차가 898edd0f96 seg16/17 단일 사례를 수작업으로 계산했던 것을
  일반화한 함수 — route1617.csv 재실행 결과 149차 수치와 근사 일치
  확인(gap≈2.6kph/s). **주의**: t_detect는 naviPaths 기반 fine 재계산
  최초 감지 시점을 근사하는 것이 아니라 liveRouteSpeed 자체의 하강
  추세 시작점을 찾는 방식(구현 단순화) — naviPaths 정밀 재계산과
  결합한 버전은 아직 없음.
  **2026-08-30 수정(152차, 버그)**: 초기 버전은 blinker onset을
  무조건 "감지된 근정지급 커브의 도착"으로 간주해, 관계없는 차선변경
  blinker와 우연히 시간상 인접한 커브 감지를 잘못 페어링하는 오탐이
  있었음(898edd0f96 seg10 실측에서 발견 — gap_ratio=14.35로 진짜
  이벤트(2.04)보다 커서 최우선순위로 오판될 뻔함). `turn_confirm_deg=
  15.0`/`turn_confirm_window_s=8.0` 파라미터 추가 — t_arrive 이후 이
  시간 내 steeringAngleDeg가 threshold를 넘는 프레임이 있어야 이벤트
  채택. FINDINGS.md 152차 참고. **한계(미검증)**: 이 게이트가 반대로
  실제 회전이지만 steer 변화가 작은 케이스(완만한 근정지급 정지 등)를
  false negative로 누락시킬 가능성은 아직 확인 안 됨.

## sim_route_near_stop_accel_boost.py (151차 신규)
**목적**: `carrot_navi_route()`의 "역방향 accel-limited DP"(target_speed
배열 -> out_speed 스케줄) 핵심 로직(`carrot_navi_route_dp()`)을 독립
재현하고, 149차/150차가 설계한 근정지급 코너 한정 accel_limit 부스트
(`ROUTE_NEAR_STOP_TARGET_KPH`/`ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS`)를 켰을
때/껐을 때(=패치 후/전)를 비교한다. 기존 `replay_route_ramp_limiter_direct.py`
/ `sim_route_boundary_ramp_limiter.py`는 132차 프레임간 스무딩(out_speed
사후 클램프)만 재현하고 이 배열->스케줄 변환 DP 자체는 재현하지 않아
신규 작성함.

**핵심 함수**:
- `carrot_navi_route_dp(speeds, distances, v_ego_kph, accel_limit_mss, apply_near_stop_boost, ...)`
  — production 로직 1:1 이식. `(out_speeds, accel_limit_kmh)` 튜플 반환
  — `accel_limit_kmh`는 이번 사이클 실제 사용값(부스트 반영)이라 호출부가
  132차 램프리미터를 정확히 재현하려면 이 값을 그대로 재사용해야 함
  (production `carrot_man.py` L723이 동일 지역변수를 재사용하는 것과 동일).
- `simulate_approach(target_speed_kph, corner_dist_m, v_ego_kph_start, accel_limit_mss, apply_near_stop_boost, dt=0.05, ...)`
  — 단일 코너 접근을 20Hz 다중프레임으로 시뮬레이션. 매 프레임 10m 간격
  전체 배열(가까운 순=index 0, 마지막만 target, 나머지는 200kph 무제한)을
  재구성해 DP 호출 후, **`sim_route_boundary_ramp_limiter.RampLimiterState`
  를 그대로 재사용**해 132차 프레임간 램프리미터까지 적용한 뒤 그 결과를
  다음 프레임의 v_ego로 채택. `(final_speed_kph, elapsed_s, trace)` 반환.
  **설계 시행착오 기록(중요, 재작성 방지용)**: 1차 시도(단일프레임 out_speeds[0]
  직접비교)와 2차 시도(다중프레임이지만 램프리미터 누락)는 둘 다 방법론
  결함으로 폐기됨(FINDINGS.md 151차 상세). 신규 시나리오 추가 시 반드시
  램프리미터 포함 다중프레임 방식을 따를 것 — 단일프레임/램프리미터 없는
  버전으로 되돌아가면 이미 확인된 오판을 반복하게 됨.
- `_run_on_csv(csv_path, accel)` — `--with-navi-paths`로 뽑은 실측 CSV에
  기록된 naviPaths+vEgo로 실제 프레임에서 패치 적용 시 route가
  arbitration에서 선택됐을 가능성이 있는 프레임을 스캔(근사, 다른
  소스의 2차 효과는 미반영).

**결론(151차, 2026-08-30)**: 149차 근사조건(v_ego=90kph, target=10.7kph,
280m)으로 유닛테스트 실행 결과 **부스트 적용 시 코너 도달 초과속도가
오히려 악화**(4.4kph→8.8kph) — accel_limit을 올리면 DP가 "나중에 더
세게 감속 가능"이라 판단해 현재 시점 감속 시작을 늦추는데, 132차
램프리미터는 실시간 기준으로만 그 부스트를 적용해 실제로는 따라잡지
못함. **149차/150차 설계의 `carrot_man.py` 부스트 패치는 배포 보류
권고**(로컬에만 존재, origin 미반영). 상세는 FINDINGS.md 151차 참고.

**사용**:
```bash
python3 sim_route_near_stop_accel_boost.py --unit-tests
python3 sim_route_near_stop_accel_boost.py <route.csv> --with-navi-paths로 뽑은 것 --accel 0.70
```
**의존성**: `analysis_helpers.py`(`parse_navi_paths`/`recompute_route_curvature_speed`),
`sim_route_boundary_ramp_limiter.py`(`RampLimiterState`).

**2026-08-30 확장(153차, 152차 옵션1) — `carrot_navi_route_dp_forced_decel()`,
결과 POSITIVE**: 151차 boost(위 결론)는 accel_limit을 올려서 **같은
역방향 DP 재귀**(`carrot_navi_route_dp`)에 넣었는데, 그 재귀의
time_wait/margin 메커니즘이 "accel_limit이 크면 나중에 더 세게 감속
가능"이라 판단해 오히려 현재 시점 감속 권고를 늦추는 부작용이 있었음
(NEGATIVE). 이번 함수는 그 재귀 자체를 우회한다:
1. base accel_limit로 기존 DP를 그대로 실행(감속 시작 시점 판단 로직
   불변, 151차 부작용의 근원 원천 차단).
2. 근정지급 target 지점(min_idx)의 필요감속률(required_accel_mss,
   149차/151차와 동일 등가속도 역산 공식)을 계산.
3. `required_accel_mss > base accel_limit_mss`인 경우에만, min_idx까지의
   각 지점을 "target에서 required_accel_mss(상한 `max_forced_accel_mss`,
   기본 1.2 m/s^2=vturn_decel_rate 클램프)로 역산한 등가속도 곡선"으로
   직접 덮어씀(재귀/time_wait 미개입 — 즉시 감속 곡선 강제).
4. accel_limit_kmh도 같은 값 기준으로 상향 반환해 132차 램프리미터가
   이 곡선을 따라잡을 수 있게 함.

**시뮬레이션 결과(유닛테스트 시나리오 E~H, 전부 PASS)**: 149차 근사조건
(v_ego=90kph, target=10.7kph, 280m)에서 코너 도달 초과분이 base
4.4kph → 옵션1 **0.0kph**(151차 boost는 8.8kph로 오히려 악화). 149차
실측조건(v_ego=109.6kph, ~585m)도 5.3→**0.0**(boost 10.1). 클램프가
실제로 발동하는 극단적 늦은 감지(50m) 조건에서도 1.3→**0.0**(boost
4.9)으로 역효과 없이 개선. 일반 커브(근정지급 아닌 target)는 옵션1도
diff=0으로 회귀 없음 확인(시나리오 A/B/E).

**주의**: 시나리오 C/D(151차 boost 자체를 검증하던 레거시 체크, target
"패치 후 개선"을 boost 기준으로 검증)는 151차 NEGATIVE 결론을 그대로
반영해 의도적으로 FAIL 상태 유지 중(README/CHANGELOG 반복 언급 —
재작성하지 말 것, boost 방식이 실제로 나쁘다는 증거로 보존).
`--unit-tests` 총합 "10 PASS / 2 FAIL"이 정상 상태.

**아직 안 한 것(다음 세션)**: 이 함수는 시뮬레이션 전용 재구현 —
`carrot_man.py` 실제 패치는 아직 작성 안 함. 152차 합의(WIP.md) 순서상
이 POSITIVE 결과 확인 후 실제 패치 단계로 진행 예정. 패치 시 production
`carrot_navi_route()`도 동일하게 "base DP 실행 → 근정지급 구간만
후처리로 물리곡선 덮어쓰기" 구조로 삽입해야 하며, 기존 149차/150차가
로컬에만 남겨둔 미배포 boost 패치(`ROUTE_NEAR_STOP_TARGET_KPH`/
`ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS`, accel_limit을 DP 입력 자체에 주입하는
방식)와는 다른 코드 경로이므로 그 로컬 패치를 재사용하지 말 것.

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

## sim_boost_arm_priority.py (134차 신규)
**목적**: `_discontinuity_jerk_boost_timer`/`_discontinuity_trigger_source`를
arm하는 4개 트리거 지점(discontinuity/discontinuity_lc/handoff/
low_speed_strong_decel)이 서로를 덮어쓸 때의 우선순위/기간을 검증. 134차
정적 리뷰에서 발견한 "112차(low_speed_strong_decel)는 자기 자신을
보호하는 가드가 있지만, 반대로 plain 'discontinuity'(1.0s)가 이미 진행
중인 더 긴 hold(4.0s 소스들)를 덮어써 단축시키는 경우는 보호가 없었다"는
비대칭 문제의 패치(같은 세션에서 적용, long_mpc.py 해당 arm 지점에
elif 가드 추가)를 검증.
**의존성**: 없음(표준 라이브러리만).
**주요 함수**: `BoostArmState` -- arm 지점 4곳의 분기 로직을 리터럴
이식(`arm_discontinuity_or_lc`/`arm_handoff`/`arm_low_speed_strong_decel`).
**커버 시나리오(7개)**: 무boost 정상 arm, 더 긴 hold(low_speed_strong_decel/
discontinuity_lc/handoff) 진행 중 plain discontinuity가 덮어쓰지 않고
보존(신규 수정 검증 3건, discontinuity_lc는 confirm 타이머까지 보존 확인
포함), 같은 소스 재트리거는 기존처럼 정상 리프레시(회귀 없음), 이전
소스가 이미 소진됐으면 stale 태그와 무관하게 정상 arm, 4.0s 소스끼리는
서로 덮어써도 기간 단축이 없어 기존처럼 무조건 덮어쓰는 설계 유지 확인.
**결과**: 7/7 PASS.
**사용**: `python3 sim_boost_arm_priority.py`

## sim_gap_open_damping.py (116차 신규, 117차 완만화 버전 추가)
**목적**: 6님 제보("저속에서 앞차 멀어질 때 너무 급하게 재가속 -> 다시
붙을 때 급브레이크") 대응 신규 방안 — 저속(<=40km/h)에서 이미
desired_distance보다 충분히 벌어진 상태(gap_ratio >=
MARGIN_ACCEL_GATE_FULL=1.5, 기존 dist_w 경계 재사용)에서 앞차가 강하게
가속 중일 때만 MPC에 넘기는 a_lead에 상한(`LOW_SPEED_GAP_OPEN_ACCEL_CAP`)을
거는 로직의 단위 검증. `process_lead()`의 관련 분기만 순수함수로 재현.
**핵심 설계**: 45차("정지 후 출발 가속 약화") 재발을 막기 위해
(1) `_launch_bypass_active` 구간 명시적 제외, (2) gap_ratio가 낮은
(desired_distance 이내로 정상 추종 중인) 구간은 게이트 자체가 안 열림 —
정상 출발이 "너무 천천히" 되는 오탐을 구조적으로 차단.
**의존성**: 없음(표준 라이브러리만).

**116차 — 하드클램프 버전, 시나리오 A~F(전부 PASS, 참고용으로 보존)**:
A(고속 회귀 diff=0)/B(launch bypass 중 defense-in-depth 캡 미적용)/
C(bypass 해제 후 18~40km/h 정상 출발 연장 구간 캡 미적용 — 오탐 방지
핵심)/D(이벤트 재현, gap_ratio>=1.5+강한가속 지속 시 a_lead가 CAP(0.5)로
클램프)/E(완만가속 오탐방지, diff=0)/F(gap_ratio 1.5 경계 전이 — 예외
없이 즉시 토글되나, **캡 진입 순간 a_lead에 최대 1.5 m/s² 단차(하드클램프,
완만화 없음) 발생 확인**).

**117차 — 완만화(rise-rate 블렌드) 버전 추가, 실제 long_mpc.py 패치와
동일 로직(`apply_gap_open_cap_smoothed`, `GapOpenCapState`)**: F에서
발견된 단차를 39차(`LEAD_ACCEL_WEIGHT_RISE_RATE`)와 동일 패턴으로 해소 —
캡을 직접 하드클램프하지 않고 블렌드 weight(`cap_w`, 0=무캡~1=완전캡)를
`LOW_SPEED_GAP_OPEN_WEIGHT_RISE_RATE`(1.0/s)로 진입/해제 양방향 모두
사이클당 변화폭 제한. 신규 시나리오 3건 전부 PASS: **G**(경계전이 재측정
— 사이클당 최대 변화폭 1.500→0.075 m/s², 95% 감소, 이론값과 일치)/
**H**(bypass 즉시 우회 — cap_w가 중간값(0.5)으로 램프 진행 중이어도
bypass 활성 시 같은 프레임에 즉시 cap_w=0.0 강제)/**I**(정상상태 일치 —
게이트 유지 5s 후 하드클램프 버전과 동일한 최종값(a_lead=0.5, cap_w=1.0)
도달, 지연만 있을 뿐 결과는 동일).
**사용**: `python3 sim_gap_open_damping.py` (A~I 9개 시나리오 전부 실행,
요약 출력)

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

## replay_margin_accel_weight_full.py (114차, 신규)
**목적**: 113차가 근사 못 했던 `margin_accel_weight`(dist_w)까지 포함해
`long_mpc.py`의 lead-accel damping weight(dist_w/ttc_w/rise-rate 클램프/
LOW_SPEED_STRONG_DECEL 게이트/TTC danger override)를 실측 CSV 위에서
완전 재현. desired_distance 계산에 필요한 carrot 상태값은
`selfdrive/carrot/carrot_functions.py`의 **Params 기본값**(TFollowGap2=
1.20/ComfortBrake=2.4/StopDistanceCarrot=5.5/EnableSpeedTF=0/
DynamicTFollow=0/MyDrivingMode=Normal)을 대입 — personality=standard
가정, 사용자가 Params를 커스텀했다면 오차 가능(스크립트 상단 docstring에
가정/한계 전부 명시).
**113차 스크립트(`replay_rise_rate_saturation.py`) 관련 중요 공지**:
그 스크립트는 컨테이너 리셋으로 유실되어 레포에 존재하지 않음(FINDINGS.md
서술만 남음) — 이 스크립트가 그 대체+확장판. 113차 수치와 직접 재현
비교는 불가했으나, ROUTE1 결과가 크게 달라진 것으로 보아(0.951s→0.250s)
113차 스크립트는 LOW_SPEED_STRONG_DECEL/TTC danger override 로직을
포함하지 않았을 가능성이 높음(114차 FINDINGS.md 참고).
**주요 함수**:
- `run_window(rows, t_lo, t_hi)` — 지정 시간범위 프레임별 dist_w/ttc_w/
  w_target/w_applied/danger_now/gap 리스트 리턴.
- `longest_saturation_run(frames)` / `total_saturation_time(frames)` —
  gap>0(클램프가 목표를 못 따라잡는 상태) 연속/총 시간.
- `scan_route_saturation_episodes(rows, thresholds)` — 라우트 전체를
  순차 재생(세그 경계 상태 이어받음, leadStatus False 구간에서 rise-rate
  상태 리셋)해 threshold별 에피소드 개수 카운트(오탐률 스윕용). 리턴:
  `(threshold별 count/max_duration 딕셔너리, 전체 에피소드 리스트)`.
- `TFollowState` — decel-hold+boost t_follow를 세그먼트 단위로 순차
  시뮬레이션하는 상태 클래스(carrot_functions.py
  `_apply_decel_hold_and_boost_t_follow` 리터럴 이식).
**114차 핵심 발견**: ROUTE1은 이미 112차 threshold 강화(-1.8→-2.5)
패치로 danger override가 0.25s만에 발동해 SMOOTH 수준으로 saturation이
짧아짐(더 이상 harsh 아님). ROUTE2/3는 override 게이트 밖(v_ego>30km/h)
이라 여전히 0.9~1.0s대 saturation. SMOOTH 라우트 전체 스캔에서 진짜
위험과 무관한 0.448s 노이즈성 에피소드(track-switch 추정)가 발견돼
"연속 saturation 시간 단일 지표" 판별법의 한계가 드러남 — 상세는
FINDINGS.md "114차" 참고.
**의존성**: 없음(표준 라이브러리만).
**사용**:
```bash
python3 replay_margin_accel_weight_full.py <route.csv> <t_lo> <t_hi>   # 특정 구간
python3 replay_margin_accel_weight_full.py <route.csv>                 # 전체 스캔+threshold 스윕
```

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

## replay_lane_departure_gate.py (120차, 신규)
**목적**: 119차 실제 패치(radard.py get_lead() LANE_DEPARTURE 게이트,
1.75m/0.5s/vRel>-0.5)가 실차에서 실제로 동작했는지 실측 route CSV로
검증. `sim_lane_departure_gate.py`(119차, 근사 합성검증)의 실측 replay
버전 — 119차가 "다음 세션 필요"로 남겨둔 항목.
**핵심 아이디어**: leadStatus=True 구간에서 |leadDPath|>1.75 &
leadVRel>-0.5가 0.5s 지속되는 "예측 발동 시각"을 계산 후, 그 직후
실제 CSV에서 leadStatus가 True->False로 전환되는지 대조(PASS/FAIL/
AMBIGUOUS 판정).
**의존성**: 없음(표준 라이브러리만).
**120차 핵심 발견**: 4개 route(89996행) 스캔 결과 PASS 5/FAIL 3 —
FAIL 사례는 `LeadBlend.update()`가 게이트의 status=False 리셋을
자신의 구버전 `_is_cutout()`(2.0m 기준)으로 재판정해 최대
`LEAD_LOST_GRACE_TIME`(0.6s) 동안 리셋을 무력화하는 구조적 버그(118/
119차가 원래 잡으려던 "outer 로직 무력화" 버그 클래스 재발). 상세는
FINDINGS.md "120차" 참고.
**주의**: dPath는 게이트 발동 "이후" 값이 로그에서 사라지므로(status
False가 되며 필드가 비게 됨), 발동 이전 상승 구간만으로 예측 —
정밀한 "게이트가 정말 그 프레임에 개입했는지"는 leadStatus 실제
전환 타이밍과의 대조로 간접 판단(직접 확정 아님, verdict 필드의
note에 판단 근거 명시).
**사용**:
```bash
python3 replay_lane_departure_gate.py <route.csv> [<route.csv> ...]
```

## extract_cutin_lists.py (125차, 신규)
**목적**: rlog에서 `radarState`의 `leadOne`/`leadsCutIn`/`leadsLeft`/`leadsRight`
리스트(radard.py `compute_leads()`가 실제로 산출한 최종 결과 그대로)를
시간별로 추출. `extract_log.py`는 최종 선택된 leadOne만 CSV로 뽑기 때문에,
"인접 차선 차량이 실제로 언제부터 cutin/left/right 후보로 잡혔는지"를
보려면 이 스크립트가 필요함. 125차, 컷인_이거는_차선_폭을_넓게(133212)
정밀분석 계기로 작성 — 게이트/hysteresis 로직을 재구현하지 않고 실제
publish된 리스트를 그대로 읽으므로 로직 drift 위험이 없음.
**입력**: route_dir(세그먼트 여러 개) 또는 단일 세그먼트 폴더 둘 다 지원.
**출력**: `--json` 없으면 지정 시간창(`--t-lo`/`--t-hi`)을 사람이 읽기 좋게
stdout 출력. `--json <path>`면 라우트 전체를 JSONL로 저장(leadOne dict +
cutIn/left/right 리스트 전체 보존).
**125차 핵심 발견**: r354 t≈296~299 컷인 사례를 이 스크립트로 재생한 결과
`leadsCutIn`/`leadsLeft`/`leadsRight`가 사건 전체 구간에서 단 한 번도
비지 않았음(n=0 유지) — 옆차의 yRel이 최대 0.83m로, `in_lane_prob`
계산상 "여전히 내 차로 안"으로 분류되어 애초에 "차로 밖 후보" 게이트가
개입한 적이 없었음. 즉 `lane_half_width` 관련 임계값을 넓히는 방향의
수정은 이미 발동한 적 없는 이 게이트를 더 관대하게 만들 뿐이라 이 사례엔
무력함(FINDINGS.md "125차" 참고). 이 발견은 `decode_rlog.py`의
`liveTracks`(원시 레이더 포인트, yRel/dRel raw) + `modelV2.leadsV3[0]`
(비전 단독 후보 x/y)를 병행 조회해서 얻음 — 이 두 신호는 아직 별도
toolkit 함수로 감싸지 않았으니, 다음에 유사 분석이 필요하면 이
스크립트의 `process_route()`와 나란히 `decode_rlog.iter_events()`를
`liveTracks`/`modelV2` 필터로 직접 순회하는 패턴을 참고할 것.
**사용**:
```bash
python3 extract_cutin_lists.py <route_or_seg_dir> --repo /home/claude/ryu \
    --t-lo 294 --t-hi 300
python3 extract_cutin_lists.py <route_dir> --repo /home/claude/ryu \
    --json /home/claude/work/cutin_lists.jsonl
```

## replay_route_full_pipeline.py (148차, 신규 — NEEDS_VALIDATION)
**목적**: `carrot_navi_route()`의 out_speed 전체 계산(매크로 sample=4
곡률 → 147차 sample_fine=1 병합 → 91차 margin_kph 역방향DP → 132차
프레임간 램프리미터)을 `extract_log.py --with-navi-paths`의
`naviPaths`(carrot_navi_route()가 실제 쓰는 리샘플 폴리라인 그 자체)로
프레임 단위 재현 시도.
**주의(중요) — 신뢰 불가**: 실제 프로덕션이 쓰는 `nRoadLimitSpeed`
(도로제한속도, Params/navi service 값, CSV에 미기록)를 알 수 없어
`road_limit_speed=200.0` 가정으로 대체 — 실측 route898.csv 검증 결과
patched_sim vs 실제 published desiredSpeed 평균오차 98.7kph(신뢰불가
수준). **절대수치(out_speed 값 자체) 검증에는 쓰지 말 것.** 148차의
실제 결론(Finding A/B)은 이 스크립트가 아니라 이미 검증된
`recompute_route_curvature_speed`(파라미터 불확실성 없음, 곡률만
계산)와 실측 steeringAngleDeg/vEgo/vTurnSpeed 직접대조로 얻음.
**향후 재사용**: nRoadLimitSpeed를 확보(예: carrot_serv 관련 필드
신규 계측 후 재추출)하거나 다른 방법으로 캘리브레이션하면 재현
정확도를 재검증해 볼 수 있음 — 프레임간 낙차(오탐 시 급브레이크 여부)
같은 상대적/구조적 지표는 절대오차와 무관하게 유효할 가능성 있음
(148차에서 미검증).
**의존성**: numpy.
**사용**: `python3 replay_route_full_pipeline.py <route.csv> [--accel 0.70]`

## replay_route_apex_vs_baseline.py (158차, 신규 -- 실측 패치 검증, POSITIVE)
**목적**: `extract_log.py --with-navi-paths`로 뽑은 "패치 적용 이전"
실측 로그를 20Hz 프레임 단위로 재생해, 157차 apex 알고리즘
(`sim_route_apex_redesign.carrot_navi_route_apex`)이 그 실제 상황에서
어떻게 반응했을지 오프라인으로 계산하고, CSV에 이미 기록된
`liveRouteSpeed`(149차, 패치 적용 전 실제 production이 낸 값 --
역방향DP+132차 램프까지 통과한 실측 ground truth)와 비교한다.
148차 `replay_route_full_pipeline.py`(신뢰불가, 미기록 `nRoadLimitSpeed`
가정치 필요, 평균오차 98.7kph)와 달리 "패치 전 실제로 어떻게 나왔는지"는
재현이 아니라 실측값 그대로 쓰므로 절대오차 문제가 없다 -- apex
알고리즘의 floor 분기(곡률이 거의 0인 프레임)에만 `road_limit_speed`
가정치(기본 200.0)가 남아있는데, 그 경우엔 애초에 apex 자체가
무의미(직선)하므로 판정("반응함 vs 무반응", "오탐 유무")에 영향이
제한적.
**의존성**: `analysis_helpers.py`(`load_csv`/`parse_navi_paths`/
`recompute_route_curvature_speed`(`floor_threshold` 인자, 158차 신규 --
기본 0.02=패치 전, 0.001=157차 재현)), `sim_route_apex_redesign.
carrot_navi_route_apex`, `sim_route_boundary_ramp_limiter.
RampLimiterState`(132차 램프 재사용).
**주요 함수**:
- `find_stuck_segments(rows, field, min_len_s, tol)` -- 지정 필드가
  `min_len_s`초 이상 거의 고정(`tol`)되는 구간 자동 탐지 (156차/158차
  "route= N초+ 고정" 패턴).
- `replay(rows, accel_limit_mss)` -- 프레임별 apex 오프라인 계산 +
  132차 램프 적용, dt는 실제 로그 프레임 간격 사용(고정 0.05s 아님).
- `summarize_stuck_segment(...)` -- 실측 고정값 vs apex 재계산값 대조
  요약 텍스트 생성.
**158차 실측 검증 결과**: 156차가 준 실제 route 로그(2세그먼트, "route
작동안함 104에서 멈춤")로 실행 -- `liveRouteSpeed`가 104.0km/h로
9.9~12.3초씩 3회 고정되는 실측 버그 구간 전부에서, apex 오프라인
재계산은 56.3~76.7km/h로 정상 반응(157차 패치가 이 실제 로그의 버그를
해결했을 것을 실측 데이터로 확인, `NEEDS_VALIDATION` -> 오프라인
검증완료로 격상). stuck 구간과 20초 이상 떨어진 구간에서는 오탐(과잉
감속) 0건. 프레임간 최대낙차 0.26km/h로 132차 램프리미터도 정상 작동
(naviPaths 부족 프레임에서 램프가 리셋되는 것은 production과 동일한
정상 동작, 버그 아님). 상세는 FINDINGS.md 158차 참고.
**사용**:
```bash
python3 replay_route_apex_vs_baseline.py <route.csv> --accel 0.70
# 프레임별 전체 결과 덤프:
python3 replay_route_apex_vs_baseline.py <route.csv> --accel 0.70 --json out.json
```

## sim_route_apex_hysteresis.py (158차계속/159차, 신규 — 대안 설계 검증, NEGATIVE)
**목적**: 157차 `carrot_navi_route_apex`(매 프레임 무상태 전역탐색)에
대해 "apex마다 명시적 리셋을 넣으면 연속 굽이길에서 톱니 진동이 생기지
않는가"라는 우려를 검증하기 위해 설계한 3상태(reset/engaged/disengaged)
히스테리시스 대안. `ApexHysteresisState`(mode, target_curv)를 프레임 간
유지하며: ENGAGED는 `target_curv` 이상 곡률만 후보(더 급하면 승격),
후보가 사라지면 DISENGAGED(제약 없음 반환, target_curv는 보존, 완만한
커브는 계속 무시), DISENGAGED에서 target_curv보다 급한 커브가 나타나면
즉시 재개입, 윈도우 전체가 negligible이면 RESET(target_curv 삭제).
**의존성**: `sim_route_apex_redesign.curve_speed`(곡률->속도 변환 재사용).
**주요 함수**:
- `carrot_navi_route_apex_hysteresis(state, merged, v_ego_kph,
  accel_limit_mss, max_accel_mss, negligible_curv)` — `merged`는
  `analysis_helpers.recompute_route_curvature_speed()`와 동일 포맷
  `[(distance, curvature, speed), ...]`. `state`를 in-place 갱신.
- `make_frame(dist_curv_pairs, ...)` — 단위테스트용 합성 프레임 생성.
**단위테스트(4/4 PASS)**: 고립곡선 통과 후 해제, 완만한 후속곡선 무시,
더 급한 곡선 재개입, 접근 중 target_curv 승격 — 4가지 시나리오 모두
설계 의도대로 순수함수 레벨에서는 정상 동작.
**158차계속/159차 실측 A/B 결과(NEGATIVE, 채택 보류)**: 단위테스트는
전부 통과했지만 실제 route156 로그(연속 굽이길)에 132차 램프리미터까지
포함해 재생하면(`replay_route_apex_hysteresis_ab.py`) 157차 대비 명백히
악화됨 — 상세는 그 스크립트 항목 및 FINDINGS.md 159차 참고. **결론: 이
스크립트는 채택하지 않음, 157차 무상태 설계를 그대로 유지.** 코드는
"명시적 리셋이 왜 안 통하는지"를 보여주는 반례로 devnotes에 보존.
**사용**:
```bash
python3 sim_route_apex_hysteresis.py --unit-tests
```

## replay_route_apex_hysteresis_ab.py (158차계속/159차, 신규 — A/B 비교, 157차 우위 확정)
**목적**: 157차 무상태(A) vs `sim_route_apex_hysteresis`(B)를 같은
실측 CSV(158차와 동일 route156 로그, naviPaths 필요)로 나란히 재생 —
각각 독립된 `RampLimiterState` 인스턴스를 통과시켜 최종 out_speed를
비교. `replay_route_apex_vs_baseline.find_stuck_segments()` 재사용.
**주요 함수**:
- `replay_ab(rows, accel_limit_mss)` — 프레임별 `{a_out, b_out, b_mode}`
  리스트 반환.
- `frame_delta_stats(result, key)` — 프레임간 절대낙차 max/mean.
- `summarize_segment(...)` — stuck 구간별 A/B 대조 텍스트.
**158차계속/159차 실측 결과(route_aeeed9e4a5, 2400 rows)**: `liveRouteSpeed`
104.0km/h 9.9~12.3초 고정 구간 3곳 중 **A는 3/3 정상 반응(56.3~76.7
km/h)한 반면 B는 1/3만 반응(그마저 min=78.2)하고 나머지 2곳은 구간
내내 mode=disengaged로 고착돼 완전 무반응(300 그대로)**. 원인:
연속 굽이길은 인접 커브들의 곡률 크기가 서로 비슷해서, B가 한 번
`target_curv`를 국소최댓값으로 승격한 뒤 그 지점을 지나면 다음 커브가
그보다 "같거나 살짝 완만"한 경우가 많아 재개입 조건(`front_max_curv >
target_curv`)을 충족 못 하고 DISENGAGED에 갇힘. 게다가 B가
DISENGAGED<->ENGAGED를 오갈 때마다 132차 램프리미터의 "제약 해제는
안전한 방향이므로 즉시 통과, 상태 리셋" 규칙이 반복적으로 발동돼
**프레임간 최대낙차 244.11km/h**(A는 0.26km/h, 이론상한 0.13km/h와
거의 일치)까지 튀는 것을 확인 — 사용자가 애초에 우려했던 "명시적 리셋의
톱니 진동"이 A(무상태)가 아니라 오히려 **B(히스테리시스)에서 실제로,
훨씬 심하게** 발생함을 실측으로 확인. 오탐(과잉감속) 스캔은 A/B 둘 다
0건으로 동일(구간 밖에서는 문제 없음). mode 전이 11건/2400프레임.
**결론**: 157차 코드트레이스(윈도우 전진만으로 자연 해제가 이미
성립)가 실측으로도 재확인됐고, 오히려 명시적 상태를 추가하는 쪽이 램프
리미터와 상호작용해 회귀를 유발함 — **히스테리시스 방향 폐기, 157차
그대로 유지가 최종 결론.**
**사용**:
```bash
python3 replay_route_apex_hysteresis_ab.py <route.csv> --accel 0.70
```

## replay_route_camera_style_vs_baseline.py (161차, 신규 — 160차 실측 검증)
**목적**: extract_log.py --with-navi-paths로 뽑은 실측 로그를 20Hz 프레임
단위로 재생해, 160차 camera-style route 감속 알고리즘
(sim_route_camera_style_decel.carrot_navi_route_camera_style)이 그 실제
상황에서 어떻게 반응했을지 오프라인으로 계산하고, CSV에 이미 기록된
liveRouteSpeed(실측 ground truth)와 비교한다. 158차
`replay_route_apex_vs_baseline.py`(157차용)와 구조가 거의 동일 —
`find_stuck_segments`는 그 파일에서 그대로 import해서 재사용, `replay()`만
carrot_navi_route_camera_style 호출로 교체.
**주의**: carrot_navi_route_camera_style()은 v_ego_kph를 안 씀(거리만으로
계산하는 카메라 공식 특성) — 157차용 replay와 인자 구성이 다름.
**의존성**: analysis_helpers.py(load_csv/parse_navi_paths/
recompute_route_curvature_speed), sim_route_camera_style_decel.py
(carrot_navi_route_camera_style), sim_route_boundary_ramp_limiter.py
(RampLimiterState), replay_route_apex_vs_baseline.py(find_stuck_segments)
**161차 실측 검증 결과**: route156(`aeeed9e4a5`) 재생 — 157차가 고쳤던
liveRouteSpeed 104.0kph 9.9~12.3초 고정 구간 3곳 전부에서 160차도 정상
반응(54.0~70.7kph). 프레임간 최대낙차 0.16km/h(이론상한 0.13, 157차의
0.26보다 이론값에 더 근접). 직선구간 오탐 0건. 상세는 FINDINGS.md 161차
참고. **주의**: 같은 세션에서 이 route의 다른 세그먼트(seg0/seg3)의 실제
우회전 이벤트(t=6389~6393)에 이 스크립트를 돌려본 결과 naviPaths 자체가
그 회전을 감지 못하는(apex_curvature≈0) 별개의 신규 이슈를 발견함 —
149차~160차 계열(감속 공식/감속률)로는 해결 불가능한 유형이므로 160차
검증 결과 집계에서는 제외, FINDINGS.md 161차에 별도 기록.
**사용**:
```bash
python3 replay_route_camera_style_vs_baseline.py <route.csv> \
    [--safe-time 2.2] [--decel 0.70] [--start-t T0] [--end-t T1] [--json out.json]
```
**2026-08-31 추가(179차)**: `--apex-mode {sharpest,nearest,both}` 옵션
추가(기본 sharpest, 기존 동작 그대로 호환). `both`로 실행하면 160/161차
apex(sharpest)와 179차 apex(nearest)를 같은 프레임에서 나란히 계산해
차이를 요약 출력(최대 절대차, 1km/h 초과 차이 프레임 수) + `--json` 덤프
시 `{"sharpest": [...], "nearest": [...]}` 형태로 저장. route 00000374
실측 재생 결과(FINDINGS.md 179차): 129/450 유효 프레임에서 1km/h+ 차이,
최대 9.72km/h(near가 더 높음, floor 근접 잡음 지점 문제) 확인.
**사용(both)**:
```bash
python3 replay_route_camera_style_vs_baseline.py <route.csv> --apex-mode both --json out.json
```
**2026-08-31 추가(180차)**: `--apex-mode`에 `relative_gated`(179차 후속2/
180차 프로덕션 반영 게이트, road_limit_speed=200.0/relative_severity_ratio=
0.85 고정 — `carrot_man.py` 프로덕션 기본값과 동일)와 `both_relative`
(nearest vs relative_gated 나란히 비교, "sharpest vs nearest 차이" 출력을
`{m0} vs {m1} 차이`로 일반화해 재사용) 신규 추가. 합성 스팟체크(근접 floor
잡음 3점 + 원거리 실제 급커브 1점 시나리오)로 relative_gated가 sharpest와
동일 결과(81.2km/h)를 내고 nearest(199.5km/h, 잡음에 낚임)와 다름을
확인 — 179차 실측 문제(route 00000374 t≈753.5~759.3)에 대한 실측 A/B
재검증은 해당 CSV 재확보 후 별도 수행 예정(FINDINGS.md 180차 참고).
**사용(both_relative)**:
```bash
python3 replay_route_camera_style_vs_baseline.py <route.csv> --apex-mode both_relative \
    --start-t 736.8 --end-t 782.7 --json out.json
```
**2026-08-31 추가(179차 후속, NEGATIVE 결과)**: `sim_route_camera_style_decel.py`에
`carrot_navi_route_camera_style_nearest_severity_gated()`(도로제한속도
대비 비율 최소심각도 게이트, 3단 폴백) + `noise_then_real_curve_curvature_fn()`
(검증1 지오메트리 합성 재현) 추가. 유닛테스트로 "이 게이트는 작동하지
않음"을 확정(5~95% 전 구간 비율 스캔에서 curve1 유지+noise 차단을 동시
만족하는 비율 0건) -- lookup 테이블 저곡률 구간 비선형성 때문에 noise가
curve1보다 항상 더 "심각"하게 계산됨. 상세는 FINDINGS.md 179차 후속 참고.
이 방향은 폐기, 대안(상대적 심각도 비교/연속성 게이트)은 미착수 제안만
기록됨.
**2026-08-31 추가(179차 후속2, 대안1 POSITIVE / 대안2 NEGATIVE 확정)**:
`sim_route_camera_style_decel.py`에 대안 두 개를 모두 구현 + 실함수 호출
유닛테스트로 확정(15/15 PASS, 신규 3건 추가) —
`carrot_navi_route_camera_style_nearest_relative_gated()`(도로제한속도
절대비율 대신 "같은 lookahead 윈도우 내 sharpest 대비 상대 심각도 비율"을
게이트 기준으로 사용, 기본 relative_severity_ratio=0.85): 검증2(연속
S자커브 curve1)는 게이트 없는 nearest와 동일 결과(대응력 유지), 검증1
(근접잡음 vs 원거리 실제커브)은 잡음을 차단하고 sharpest(원거리 실제커브)
와 정확히 일치 — **POSITIVE, 이 방향 채택 유력**.
`carrot_navi_route_camera_style_nearest_persistence_gated()`(인접
min_persist_points개 연속 지점이 모두 threshold 미만이어야 apex 인정,
기본 2): 검증2의 curve1이 fine-sample 특성상 단일 지점에서만 threshold를
넘는 것으로 확인돼(curve2는 2개 연속) curve1 대응력이 깨짐 —
**NEGATIVE, 폐기**. 상세는 FINDINGS.md 179차 후속2 참고.

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

## sim_lane_departure_gate.py (119차, 신규)
**목적**: 118차 설계 제안("빨간 박스"/검증된 레이더락 상태에서도 적용되는
차선이탈 강제해제 게이트, `radard.py`에는 아직 미반영)의 파라미터
(`LANE_DEPARTURE_DPATH_THRESH`, `LANE_DEPARTURE_CONFIRM_S`) 후보를
코드 반영 전에 합성 시나리오로 사전 검증. `_is_cutout()`
(`radard.py` L657~662) 상수(`CUTOUT_DPATH_THRESH=2.0`,
`CUTOUT_VREL_GATE=-0.5`)를 그대로 가져와 대조 기준으로 사용.
**의존성**: 없음(표준 라이브러리만, `random`/`math`는 표준).
**시나리오 4건**: (1) 정상 커브 dPath 노이즈(±0.3~0.9m, 118차 기록
실측 스윙 범위) 200회 몬테카를로 오탐율, (2) route1
t=5915.03~5932.53 실측 이벤트 근사 재현(118차 WIP.md 기록 수치 기반
`frac**1.6` 성장 곡선 근사 — **정밀 replay 아님**, route1.csv가 이
세션에 없어 실측 프레임 단위 재현은 불가), (3) 단일 프레임 노이즈
스파이크(confirm_s 디바운스 확인), (4) 강접근 중(vRel<-0.5) dPath
초과 시 danger override 철학과 충돌하지 않는지.
**핵심 발견 (119차)**: 실측 이벤트(시나리오2)에서 dPath가 최대
-1.97~-1.99m까지만 도달하고 2.0m를 한 번도 안 넘음 → **기존
CUTOUT_DPATH_THRESH=2.0m을 그대로 재사용하면 이 게이트가 이 사례에
전혀 트리거되지 않음**(118차 "기본안"은 이 특정 이벤트에 무력).
1.75m/confirm_s=0.5로 좁히면 t=15.25s(원본 기준 t≈5930.28)에 강제
해제 → 자연해제(17.50s) 대비 **2.25초 단축**. 정상 커브 노이즈
200회 시행에서 1.75m/2.0m/2.30m 모두 오탐 0건(노이즈 최대치
0.9~1.05m로 1.75m와 0.85m 이상 여유 있음 — 단, 이 노이즈 모델은
118차가 기록한 범위를 그대로 쓴 근사치이며 더 급한 커브의 dPath
거동은 별도 검증 필요, 아래 한계 참고).
**한계 (명시)**:
- route1.csv 미보유로 인해 시나리오2는 "선형 아님, 참고용" 근사 —
  다음 세션에 route1 원본(또는 캐시)이 확보되면
  `replay_lane_departure_gate.py`류로 정밀 재현 필요.
- 시나리오1 정상 커브 노이즈 모델은 118차가 육안 프레임 분석에서
  기록한 스윙 범위(±0.3~0.9m) 하나에만 근거 — 표본이 이벤트 1건뿐이라
  더 급한 실제 커브(급커브/급차선변경 등)의 정상 dPath 거동은
  대표하지 못할 수 있음.
**사용**: `python3 toolkit/sim_lane_departure_gate.py`

## sim_lead_blend_far_jump_gate.py (130차, 신규)
**목적**: 104차 Finding A(NEEDS_VALIDATION) — 레이더 락온 근접 리드가
커브 진입 중 락을 잃고 vision-only 저신뢰(prob≈0.24)로 폴백되는 순간
84~89m 원거리로 오판되는데, 기존 `LeadBlend` BIG_JUMP(>15m 안전방향)
즉시-스냅 로직이 신뢰도와 무관하게 그대로 반영하던 문제를 재현하고,
130차에서 반영한 신뢰도 게이트(`radar=True` 또는
`modelProb>=LEAD_BLEND_BIG_JUMP_PROB_GATE(0.70)`일 때만 즉시 스냅,
아니면 기존 블렌딩 경로로) 패치를 검증.
**의존성**: 없음(표준 라이브러리만). `radard.py`를 capnp/cereal 의존성
때문에 직접 import할 수 없어 `LeadBlend` 로직을 patched/unpatched
두 버전으로 문자 그대로 복제.
**시나리오 5건**: (A) 104차 실측 근사 재현 — patched가 즉시 89m로
스냅하지 않고 시정수(0.35s)로 점진 전환하는지, (B) 고신뢰
vision(modelProb=0.85) far jump 회귀 없음, (C) 레이더 교차검증
(radar=True, modelProb 낮아도) far jump 회귀 없음, (D) closer_jump
(위험방향)는 저신뢰여도 danger-passthrough로 즉시 반영(반응지연
없음), (E) 정상 추종 중(점프 없음) patched/unpatched 완전 동일.
**결과**: 5/5 PASS. patched 첫 프레임 dRel 점프 55.4m→8.0m로 감소
(즉시 원거리 오판 노출 완화, 완전 차단은 아니고 0.35s 시정수로
점진 반영 — 그 사이 레이더 재획득/vision 신뢰 회복 시 정상값으로
자연 수렴, 진짜 근접 위험은 기존 danger override가 그대로 처리).
**한계**: 로직 단위 합성검증만 완료. 실차 acados MPC 파이프라인
검증(동일 커브+레이더유실 재현 로그) 없음 — 104차가 확보한 원본
route는 이 세션 컨테이너엔 없어(대용량 정책상 미보관) replay 정밀
재현은 불가, 다음 세션 재확보 시 진행.
**사용**: `python3 toolkit/sim_lead_blend_far_jump_gate.py`

## sim_route_step_drop_repro.py (131차, 신규 — NEGATIVE 결과)
**목적**: 129차(교차로 접근 route 사전감속 "계단형 고정") 실측
급락(t=2182.70->2182.75, Δ-25kph 단일프레임)을 `sim_route_curvature_
sample.py`의 `reconstruct_path`(desiredCurvature 시간적분 재구성) +
`backward_dp_margin`으로 20Hz 슬라이딩 재현 시도.
**결과(NEGATIVE)**: 최대 프레임간 낙차 1.46~1.84kph에 그침 — 실측
Δ-25kph를 전혀 재현 못 함. **원인**: `reconstruct_path`가 desiredCurvature
시간적분 기반이라 매 스냅샷마다 lookahead 구간 전체가 "이미 다 아는"
상태로 재구성됨(실제 도로가 아니라 모델이 그 이후 실제로 따라간 경로를
재생하는 것) — 실제 `carrot_navi_route()`가 갖는 "고정거리 윈도우 경계
밖의 지점은 아예 존재하지 않다가 경계를 넘는 순간 이산적으로 나타난다"는
메커니즘이 원천적으로 없어 매끄럽게만 나옴. **후속**:
`sim_route_lookahead_boundary_snap.py`(131차)가 이 메커니즘을 직접
재현해 실측 규모의 단일프레임 급락을 재현 성공 — 이 스크립트의
방법론(desiredCurvature 재구성)은 "계단형 급락"류 조사에는 부적합하다는
것이 확인됨(단, 91차 margin_kph 회귀검증처럼 "스케줄이 조기화되는지"
확인 목적에는 여전히 유효 — 93차/이 스크립트 둘 다 그 결론은 재확인함).
**사용**: `python3 sim_route_step_drop_repro.py <route.csv> --t-center
<급락시각> --window 1.5 --fine-step 0.05`
**의존성**: `shapely`, `numpy`, `sim_route_curvature_sample.py`,
`sim_route_margin_regression_scan.py`.

## sim_route_lookahead_boundary_snap.py (131차, 신규 — Hypothesis C 재현 SUCCESS)
**목적**: 129차 "계단형 급락" 실측의 진짜 원인 가설(Hypothesis C):
`carrot_navi_route()`가 매 20Hz 사이클마다 `route_lookahead_m`(v_ego/
accel 기반 동적 300~600m) 거리만큼 **고정 GPS 폴리라인을 매번 새로
윈도우 절단**하고, 그 윈도우 끝점의 curvature-speed를 역방향 DP
초기앵커(`out_speeds[-1]`)로 쓴다. curvature는 3점(40m 간격)이라
윈도우 끝 40m는 애초에 speeds[] 배열에 계산되지 않는다 — 즉 "윈도우
밖의 급커브"는 그 지점이 윈도우 안으로 들어오는 **단 한 프레임에**
이산적으로 배열에 나타나고, 역방향 DP가 그 프레임에 전체를 즉시
재계산해 근접 지점(out_speeds[0], desiredSpeed로 이어짐)까지 낮은 값이
즉시 전파될 수 있다 — margin_kph 스케줄 조기화(91차/93차 검증대상)와는
질적으로 다른 "이산적 정보 출현" 불연속.
**방법**: `carrot_man.py`(커밋 `1cc2bf3`, 130차 이후 HEAD)의 순수함수
(`haversine`/`closest_point_on_segment`/`get_path_after_distance`/
`compute_route_lookahead_distance`/`gps_to_relative_xy`/
`resample_10m_np`/`calculate_curvature`)와 역방향 DP 본문을 그대로
복제(`carrot_navi_route_core`). 실제 navi 폴리라인은 로그에 없음(131차
확인, `navRoute` capnp 채널 count=0, `navInstructionCarrot`엔 좌표 없이
`maneuverDistance`/`speedLimit` 요약만 존재)이므로 **합성 GPS
폴리라인**(직선 후 원호 커브)을 만들어 등속 접근시키며 20Hz 반복 호출.
**결과(SUCCESS)**: v_ego=74kph, curve_R=25m, accel=0.70 조건에서
`route_lookahead≈300m`(윈도우 끝-40m 데드존≈260m 지점)에서 첫 진입 시
300.0->71.0(Δ-229, 극단값 — 원호 진입점이 커브 시작이라 과장)이,
곧이어 t=17.00에 59.9->40.1(**Δ-19.8, 단일프레임**)이 관측 — **129차
실측(Δ-24~-25kph, 단일 20Hz 프레임)과 규모/형태 모두 일치**.
**[131차 같은 세션 추가] 정밀매칭 완료 — 지도 API 불필요**: 실제
교차로 좌표/반경은 rlog 자체에서 얻을 수 있었다 — (1) `gpsLocation`
(1Hz) capnp 채널로 실제 GPS 좌표 직접 추출(navRoute/navInstruction
Carrot엔 좌표 없지만 이 채널엔 있음), (2) 실제 회전 구간의
desiredCurvature 최대값(1/curvature=반경, 90차와 동일 논리)으로
교차로 실제 회전 반경(이 route는 17.3m) 역산. 이 반경을 대입해
재실행하면 60.8->40.2(Δ-20.65, 단일프레임) — 129차 실측(65->41,
Δ-24.0)과 거의 동일 규모로 정밀 매칭됨(OSM/Overpass 등 외부 지도
API는 시도했으나 컨테이너 네트워크 허용목록에 없어 실패했고,
불필요했음이 판명). **향후 유사 조사 시 이 두 방법(gpsLocation
좌표 + 실측 desiredCurvature 반경 역산)을 먼저 시도할 것.**
**패치 방향 후보(미설계)**: 윈도우 경계 근처 curvature 배열에 진입
시 급격한 앵커 변화를 완충하는 저역통과/램프 리미터를 `out_speeds[-1]`
초기화 또는 speeds[] 자체에 적용하는 방안 — 실측 반경(17.3m) 기반
시나리오로 바로 전/후 비교 가능, 다음 세션 착수 필요.
**사용**: `python3 toolkit/sim_route_lookahead_boundary_snap.py
--v-ego-kph 74 --curve-radius-m 25 --accel 0.70
--straight-before-curve-m 700`
**의존성**: `numpy`만 (shapely 불필요 — carrot_man.py 실제 코드가
numpy 벡터화 resample 사용).

## sim_route_boundary_ramp_limiter.py (132차, 신규 — 패치 사전검증)
**목적**: 131차 Hypothesis C(`route_lookahead_m` 윈도우 경계 진입 시
curvature 배열에 급커브가 이산적으로 출현, 역방향 DP가 그 프레임에
즉시 전체 재계산 -> `out_speed` 단일 20Hz 프레임 급락)에 대한 패치
후보(`carrot_navi_route()` 최종 반환값 `out_speed`에 프레임간 램프
리미터 적용, 상한=`accel_limit_kmh*dt`)를 실제 코드 수정 전에 검증.
**방법**: `sim_route_lookahead_boundary_snap.py`(131차)의 순수함수
(`carrot_navi_route_core`)를 import해 그대로 재사용하고, 그 위에
`RampLimiterState`(patched 로직만) 클래스를 얹어 patched/unpatched를
같은 20Hz 루프에서 나란히 비교. 리셋 규칙(300 센티널 전환 시 즉시
통과+리셋 — "제약 해제" 방향은 지연 없이 반영)도 실제 패치와 동일하게
구현.
**결과(PASS)**: `curve_R=10~25m`, `v_ego=74~90kph`, `accel=0.70~1.2`
전 조합에서 정상주행 구간(300 센티널 전환 제외) 최대 프레임간 낙차가
이론 상한(`accel_limit_kmh*dt`) 이내로 억제됨. 131차 정밀매칭 조건
(반경17.3m/74kph/0.70)에서 unpatched 20.54kph -> patched 0.13kph.
**주의(스크립트 설계 교훈)**: 최초 버전은 300<->실제값 전환(시뮬레이션
하네스 경계 아티팩트, 131차가 이미 "원호 진입점 과장"/"윈도우이 커브를
완전히 지나며 소멸"로 문서화한 것과 동일 성격)까지 핵심 지표에 섞어
집계해 FAIL로 오판했음 — 정상주행 구간만 분리 집계하도록 수정 후 정상
판정. 향후 유사 램프리미터/경계값 검증 스크립트 작성 시 센티널값
전환 구간을 반드시 핵심 지표에서 분리할 것.
**사용**: `python3 toolkit/sim_route_boundary_ramp_limiter.py
--v-ego-kph 74 --curve-radius-m 17.3 --accel 0.70`
**의존성**: `sim_route_lookahead_boundary_snap.py`(같은 디렉토리, import).

**[173차 갱신] 비대칭(asymmetric_up) 모드 추가**: 172차가 확정한 원인A
(132차 대칭 램프가 160차 apex 재설계의 "즉시 원복" 의도를 무력화)
패치 후보 사전검증을 위해 `RampLimiterState.__init__(asymmetric_up=False)`
파라미터 추가 — 기본값 False로 기존 대칭 동작 완전 보존(133차
`replay_route_ramp_limiter_direct.py`/`replay_route_boundary_ramp_limiter.py`
등 기존 스크립트가 인자 없이 그대로 호출하므로 하위호환 필수, 실제로
동작 변화 없음 확인). `asymmetric_up=True`일 때만 증가(원복)측 상한을
`math.inf`로 두고 감속측(lo)은 그대로 유지. `run()`에 `--road-limit-speed-kph`
옵션도 추가(기본 300=기존과 동일, 172차 실측 패턴인 "커브 이후 유한한
도로제한속도로 서서히 상승" 재현용, 예: 48). **결과**: 정상주행 중
하강측 최대 낙차는 patched(대칭)와 동일하게 이론 상한 이내로 유지되고,
asym 모드의 증가측은 raw out_speed를 지연 없이 즉시 추종함을 확인
(PASS). 단, `--road-limit-speed-kph` 유한값 조합에서는 131차가 이미
문서화한 "윈도우 경계 스냅으로 인한 raw 자체의 일시적 과장값" 하네스
아티팩트가 patched/asym 양쪽에 동일하게 전파돼 recovery-frame 계측이
왜곡되는 경우가 있음(패치 차이가 아니라 하네스 한계) — 실제 코드
패치의 정당성은 기본(road_limit=300) 조건 결과와 arbitration 로직
분석(아래 173차 FINDINGS 참고)으로 판단.

## extract_gps.py (133차, 신규)
**목적**: `gpsLocation`(1Hz) capnp 채널 추출을 재사용 가능한 스크립트로
정식화(131차가 인라인으로만 했던 GPS 좌표 추출 -- navRoute/
navInstructionCarrot엔 좌표가 없지만 차량 자체 GPS는 이 채널에 별도
기록됨, 131차 확인).
**출력 CSV 컬럼**: `t, seg, latitude, longitude, altitude, speed,
bearingDeg, horizontalAccuracy`. `t`는 `extract_log.py`와 동일
`logMonoTime` 기준이라 route.csv와 join 가능(1Hz vs 20Hz라 가장 가까운
t로 매칭 또는 선형보간 필요).
**사용**: `python3 extract_gps.py <route_dir> <out.csv> --repo /home/claude/ryu`
**의존성**: `decode_rlog.py`.

## replay_route_ramp_limiter_direct.py (133차, 신규 — 132차 패치 실측 재검증 주 도구)
**목적**: 132차 램프 리미터 패치를 실측 로그로 재검증. 패치는
`carrot_navi_route()`의 내부 계산 방식과 무관하게 **최종 out_speed
값에만 사후로 프레임간 상한을 거는 구조**이므로, 로그에 실제 기록된
`desiredSpeed(src=='route')` 시계열 자체를 raw 시퀀스로 보고
`RampLimiterState`(sim_route_boundary_ramp_limiter.py, 132차와 동일
로직)를 그대로 통과시킨다. navi_points 재구성/근사가 전혀 불필요해
방법론적 불확실성이 가장 적은 검증 방법(133차 결론의 주 근거).
**핵심 로직**: `src=='route'`인 프레임만 추려 그 부분수열에만 리미터
적용(다른 소스 프레임 사이에 route가 잠깐 나타났다 사라지는 걸 route
값으로 착각하지 않도록). route 비활성 후 재진입 시 리미터 상태 리셋
(prev_out=None) -- 실제 패치와 동일 원칙. dt는 프레임별 실제 시간
간격을 그대로 사용(고정 0.05s 가정 안 함 -- 실제 로그는 프레임 드랍으로
dt 0.02~0.08s 폭 존재 확인됨).
**결과(133차, route 306de77a28 seg15)**: 실측 급락 2건(t=4.25 Δ-25.0,
t=28.35 Δ-24.0) 모두 patched에서 초당 accel_limit_kmh(2.52kph/s,
accel=0.70 가정) 상한 이내로 완화 확인. t=43.70 지점은 계산상
불연속이 아니라 소스전환(gas->route) 표시값 점프임을 재확인(패치
개입 대상 아님, patched==recorded==30). 판정은 고정 dt 대신 프레임별
실제 dt 기반 "낙차율(kph/s)"을 accel_limit_kmh와 직접 비교(초기 버전은
고정 dt=0.05 가정 판정 로직으로 인해 FAIL 오판 후 수정).
**사용**: `python3 replay_route_ramp_limiter_direct.py <route.csv>
--accel 0.70`
**의존성**: `sim_route_boundary_ramp_limiter.py`(RampLimiterState import).

## replay_route_boundary_ramp_limiter.py (133차, 신규 — 보조/참고용)
**목적**: 실측 GPS 트랙(1Hz, `gpsLocation`)을 navi_points 프록시로 써서
`carrot_navi_route_core`(131차, sim_route_lookahead_boundary_snap.py)를
실측 좌표로 재생 -- "왜"(어떤 메커니즘으로) 급락이 발생하는지까지
재현 시도. `replay_route_ramp_limiter_direct.py`(주 도구)와 달리 raw
out_speed 자체를 재구성하므로 근사 오차가 있다.
**결과**: t=28.35 이벤트(131차가 Hypothesis C로 정밀매칭한 그 이벤트)는
이 재구성에서도 raw 66.6->37.9 단일프레임 스냅으로 독립 재현 --
Hypothesis C가 실측 GPS 데이터로도 다시 확인됨. t=4.25 이벤트는 재현
실패(그 시점 route_lookahead(74kph,accel=0.70)=300m 윈도우 안에
교차로가 아직 안 들어옴 -- 실제 거리 약 500m로 추정, raw가 300 유지).
**한계**: 실제 navi 폴리라인이 아니라 차량 실주행 궤적 프록시(1Hz,
성긴 해상도) -- lookahead 윈도우가 짧은 시나리오에서는 재현 실패 가능.
133차 최종 결론은 이 스크립트가 아니라 `replay_route_ramp_limiter_direct.py`
(방법론적 불확실성 없음)를 근거로 함.
**사용**: `python3 replay_route_boundary_ramp_limiter.py <route.csv>
<gps.csv> --accel 0.70`
**의존성**: `sim_route_lookahead_boundary_snap.py`,
`sim_route_boundary_ramp_limiter.py`.

## sim_path_offset_laneless_curvature_source.py (140차 신규, 141차 갱신)
**목적**: `controlsd.py` `state_control()`의 curvature 소스 선택 분기
(`use_mpc_curvature = lanefull_mode_enabled or self._path_offset_active`)가
(a) `PathOffset==0`일 때 기존 동작과 100% 동일하고 (b) `PathOffset!=0`일
때만 레인리스에서 `lat_plan.curvatures`(offset 반영된 MPC 출력)로
전환되며 (c) `lat_plan.curvatures`가 비어있거나 `mpcSolutionValid=False`일
때 안전 폴백하는지를 로직단위(8가지 조합)로 검증. 137/138/139차에서
발견한 "PathOffset이 레인리스에서 최종 조향에 미반영" 문제를 140차에서
패치, 141차에서 `mpcSolutionValid` 체크(외부 리뷰 지적사항)를 추가한
직후 각각 사전검증용.
**결과**: 8/8 PASS(latActive/lanefull/offset_active/curvatures유무/
mpc_solution_valid 전 조합 기대대로 분기). 141차 신규 케이스(레인모드+
curvatures 있음+valid=False → 폴백, 기존엔 못 걸렀던 케이스) 포함.
**사용**: `python3 sim_path_offset_laneless_curvature_source.py`
**의존성**: 없음(표준 라이브러리만). **주의**: `controlsd.py`의 실제
분기 구조가 바뀌면(예: `use_mpc_curvature` 계산식, valid 체크 조건 변경)
이 스크립트의 `select_new_desired_curvature()`도 함께 갱신해야 함 —
리터럴 이식이라 자동 동기화 안 됨.

## sim_route_apex_redesign.py (157차, 신규 — 재설계 검증, POSITIVE)

**배경**: 156차가 실측으로 확인한 "route= HUD 16초+ 고정"(연속 완만한
굽이길, curvature 0.002~0.013)을 재조사 -- 근본 원인이 147차가 고친
coarse chord 문제가 아니라 `carrot_navi_route()`의
`if abs(curvature) < 0.02: speed = max(speed, nRoadLimitSpeed)` 플로어
로직 자체가 R 50m~800m급 커브 전체를 무력화하는 것으로 확인(사용자
지적, "완전히 심각한 문제"). V_CURVE_LOOKUP 테이블상 curvature
0.009~0.018 구간은 이미 45~56km/h급 커브 값을 내는데, 0.02 미만이라는
이유만으로 그 값이 버려지고 도로제한속도로 되돌려짐.

**사용자 제안 재설계**: "route의 역할은 사전에 GPS 경로로 다음
최대곡률(apex) 지점까지의 거리만 보고 미리 감속하는 것 -- 정점 이후는
vturn(비전)에 맡기고, 통과 즉시 다음 apex를 다시 찾는다"로 단순화.
기존 91차 backward DP(ROUTE_ENTRY_MARGIN_KPH/time_wait 스케줄링, 포인트별
전체 배열 처리) + 153차 근정지 후처리를 "apex(lookahead 내 최소속도
지점)까지의 거리 하나로 결정하는 물리공식" 5~10줄로 전면 대체.

**주요 함수**:
- `curve_speed(curvature, road_limit_speed, floor_threshold)` — 곡률->속도
  변환 공통 헬퍼. `floor_threshold=0.02`면 기존(버그 포함) 동작과 100%
  동일, 낮추면(예: 0.001) 그 버그 범위를 줄인 재설계 동작.
- `carrot_navi_route_baseline(speeds, distances, v_ego_kph, accel_limit_mss,
  vturn_decel_rate=1.2)` — 기존 프로덕션(backward DP + 153차 근정지
  후처리)을 그대로 재현. floor_threshold=0.02 고정 입력을 받는 `speeds`
  기준.
- `carrot_navi_route_apex(speeds, distances, v_ego_kph, accel_limit_mss,
  max_accel_mss=1.2)` — 재설계 핵심. apex_idx(최소속도 지점) 탐색 ->
  거리기반 필요감속률 계산 -> accel_limit(여유 시) 또는
  max_accel_mss(감지가 늦은 경우, 153차 클램프 로직의 일반화) ->
  out_speed 단일값 반환. 상태 없음(무상태), 배열 전체 재귀 없음.
- `winding_road_curvature_fn/straight_road_curvature_fn/
  single_sharp_curve_curvature_fn(...)` — 절대좌표 기준 곡률함수 생성기.
  `sample_curvature_road(curvature_fn, pos, road_len_m, road_limit_speed,
  floor_threshold)`가 차량 현재 위치(pos)부터 도로 끝까지 10m 간격으로
  샘플링해 매 프레임 (speeds, distances) 생성(production의 "현재
  위치부터 lookahead까지" 구조와 동일하게, 도로 패턴이 차량 이동에 따라
  실제로 진행되도록 절대좌표 기반으로 설계 -- 최초 버전은 상대좌표만
  써서 차량이 물리적으로 전진해도 커브 패턴이 고정된 채 재생되는 버그가
  있었음, 디버깅 후 수정).
- `simulate_road(sampler, road_len_m, v_ego_kph_start, accel_limit_mss,
  algo, ...)` — 132차 램프리미터(`sim_route_boundary_ramp_limiter.
  RampLimiterState` 재사용) 포함 다중프레임(20Hz) 완벽추종 시뮬레이션.
  `sim_route_near_stop_accel_boost.py::simulate_approach`와 동일 방법론을
  "단일 목표점"에서 "전체 도로 곡률함수"로 일반화.

**검증 결과(7/7 PASS)**:
| 시나리오 | baseline(기존, 플로어 0.02) | apex 재설계(플로어 0.001) |
|---|---|---|
| 156차 재현 굽이길(curv 0.002~0.013, v_ego=68kph 시작) | 무반응(최소속도=출발속도 그대로, 플로어 버그 재현) | 실제 커브속도까지 정상 감속(<65kph) |
| 직선(노이즈 0.0003) | raw out_speed>150(제약 없음, 회귀 없음) | 동일(오탐 없음) |
| 147차류 단일커브(curv=0.0165, fine-sample 미적용 축소재현) | 무반응(0.02 미만이라 baseline도 플로어 버그, 참고용) | 정상 감속(<60kph) — 임계값 자체를 우회하므로 chord 문제에 안 걸림 |
| 152/153차 근정지(target=10.7kph, corner=280m, v_ego=90kph) | (150/151/153차 기존 검증 결과 참고) | 153차 forced-decel과 동등하게 target 근접 도달 |

**한계/다음 단계**: 이번 시뮬레이션은 합성 도로 형상만 검증(156차 실제
naviPaths CSV는 대용량 정책상 미커밋 -> 컨테이너 리셋으로 소실, 재검증
필요 시 사용자가 동일 로그 재업로드 필요). 91차 ROUTE_ENTRY_MARGIN_KPH
(route가 vturn보다 먼저 개입하도록 당기는 마진)는 이번 재설계 v1에
포함하지 않음 -- 실차 검증 후 필요성 재평가 예정(FINDINGS.md 157차
참고).

**사용**: `python3 sim_route_apex_redesign.py --unit-tests`
**의존성**: `sim_route_boundary_ramp_limiter.py`(RampLimiterState 재사용).

## sim_route_camera_style_decel.py (160차 신규 — route 감속을 과속카메라 감속과 동일 공식으로)
**목적**: 사용자 설계("route 감속을 과속카메라 감속(calculate_current_speed)
로직과 완전히 동일하게, apex까지 남은 거리를 카메라의 xSpdDist 자리에 대입")를
`carrot_man.py`에 패치하기 전 검증. `carrot_serv.py::calculate_current_speed()`를
동일 시그니처로 복제한 `camera_calculate_current_speed()`와, 그 함수에 157차와
동일한 apex 선택("가장 급한 지점")을 결합한 `carrot_navi_route_camera_style()`을
구현. 도로 샘플러/다중프레임 접근 시뮬레이터/`RampLimiterState`(132차)는
`sim_route_apex_redesign.py`를 그대로 import해서 재사용(새로 안 만듦).
**157차와의 차이**: (1) safe_time 여유거리 buffer 신규 적용(91차에 미뤄뒀던
부분), (2) 필요감속률이 accel_limit을 넘으면 vturn_decel_rate까지 동적으로
부스트하던 157차 분기를 폐기(고정 decel_rate만 사용, 카메라와 동일). apex
선택 기준(목표속도 최저점)과 무상태(stateless) 구조는 157차와 동일 유지.
**주요 함수**:
- `camera_calculate_current_speed(left_dist, safe_speed_kph, safe_time, safe_decel_rate)`
  — `carrot_serv.calculate_current_speed()` 그대로 복제.
- `carrot_navi_route_camera_style(speeds, distances, safe_time, decel_rate_mss)`
  — apex 선택 + 카메라 공식 적용, `(out_speed, accel_limit_kmh)` 반환.
- `simulate_road_camera(sampler, road_len_m, v_ego_kph_start, safe_time, decel_rate_mss, dt=0.05, max_steps=6000)`
  — 132차 램프리미터 포함 다중프레임 접근 시뮬레이션.
- `double_curve_curvature_fn(apex1_m, apex2_m, curv1, curv2, width_m)` — 연속
  S자커브(곡선_개념도.pdf ② 케이스) 합성 도로 생성기, 신규.
**검증 결과(7/7 PASS)**: 156차류 굽이길/직선회귀없음/147차류 단일커브/152·153차
근정지 4개는 157차와 동일하게 정상 반응. 신규 2개(연속 S자커브 — 2차가 더 급한
경우/1차가 더 급해 apex가 전환되는 경우) 모두 PASS, 특히 **1차가 더 급한 경우
apex가 1차->2차로 자연 전환되는 구간의 프레임간 최대낙차가 132차 램프리미터
이론상한(accel_limit_kmh*dt)과 정확히 일치 — 톱니 진동 없음 확인**. 2차가 더
급한 경우는 apex가 시종일관 2차로 고정되어 1차가 사실상 무시되는데, 이는
157차부터 이어진 "가장 급한 지점" 선택 기준의 기존 특성이며 이번 설계로
새로 생긴 문제 아님(FINDINGS.md 160차 참고).
**주의(버그 수정 이력)**: 최초 작성 시 `simulate_road_camera`가 프레임간
낙차를 반올림된 trace 값끼리 비교해 가짜 위반이 나왔던 적이 있음 — 반올림
전 원본 값(`prev_unrounded`)으로 비교하도록 수정됨. 이 패턴을 다른 시뮬레이션
스크립트에서도 반올림 표시용 trace와 검증용 원본값을 반드시 분리할 것.
**사용**: `python3 sim_route_camera_style_decel.py --unit-tests`
**의존성**: `sim_route_apex_redesign.py`(샘플러/apex157차 함수), `sim_route_boundary_ramp_limiter.py`(RampLimiterState).

**2026-09-01 추가(183차, 프로토타입 -- 실측/프로덕션 미검증)**:
`carrot_navi_route_camera_style_nearest_relative_gated_min_of_both()` 신규.
180/181차 프로덕션 `relative_gated`(0.85)가 갖는 신규 edge case(1차=근접
완만한 진짜커브 / 2차=원거리 훨씬 급한 진짜커브, severity 격차 큼 --
예: curv1=0.010 vs curv2=0.03, apex2가 1차로부터 충분히 멀 때(≥250~300m
간격) 1차가 게이트에서 탈락해 apex가 2차로 건너뛰며 1차 진입 시 과속
상태가 됨, 유닛테스트로 재현: gated=72.6kph vs 1차고유속도=54.0kph)를
"게이트 없는 nearest(1차 자신의 감속요구)"와 "관계형 게이트를 통과한
후보(gated, 179~181차 노이즈 차단 로직 그대로)" 중 camera-style 공식
결과가 더 낮은(보수적인) 쪽을 채택하는 방식으로 보정 시도. 179~181차가
검증 완료한 두 케이스(검증1 노이즈 차단/검증2 curve1 유지) 모두 회귀
없이 재현하고, 신규 edge case에서 1차 진입 시 1차 고유속도(±2kph)로
정상 도달함을 유닛테스트로 확인(21/21 PASS, 기존 15/15 + 신규 6건).
**주의**: 근접 후보 자체가 노이즈이면서 우연히 그 지점이 윈도우 내
가장 급한 지점도 되는 경우(noise==sharpest)에는 기존 relative_gated와
동일하게 방어력이 없음(이 프로토타입이 새로 악화시키는 것은 아니나
해결하지도 않음, 별도 유닛테스트로 한계 확인함). **실측 로그 A/B
재검증(181차 방식) 및 프로덕션 반영은 사용자 확인 후 진행 예정 --
이번 회차는 시뮬레이션 프로토타입 단계.**

**2026-08-31 추가(179차)**: apex 선택기준을 "가장 급한 지점"(전역
min(speeds))에서 "가장 가까운 지점"(감속필요 최근접,
`speeds[k] < road_limit_speed`인 최소 index)으로 바꾼
`carrot_navi_route_camera_style_nearest(speeds, distances, safe_time,
decel_rate_mss, road_limit_speed=200.0)` 신규 추가 (`carrot_man.py` 179차
패치와 동일 로직). 위 문단의 "2차가 더 급한 경우 1차는 사실상 무시됨"
현상을 사용자가 정확히 지적(연속 좌회전 스크린샷 기반) — 신규 유닛테스트
3건으로 확정 검증(10/10 PASS):
1. sharpest는 1차 진입 직전에도 1차 고유 안전속도보다 5kph+ 과속 상태 유지
   (=1차 사실상 무시, 160차 기존 특성 재확인)
2. nearest는 1차 진입 직전 1차 고유 안전속도에 ±1kph 이내로 정확히 도달
3. 1차 통과 후(윈도우에서 사라진 뒤) 2차 접근 시 sharpest/nearest가
   완전히 수렴(0.01kph 이내) — **nearest가 1차를 제대로 처리하면서도
   2차 대응력은 전혀 희생하지 않음**을 확인.

**단, 별개의 반대 사례도 실측 로그(route 00000374)에서 발견됨(FINDINGS.md
179차 참고)**: 근접(10m) 지점이 실제 커브가 아니라 floor 임계값(0.001)
바로 위의 미세 곡률(거의 잡음 수준)이고, 진짜 급커브가 그보다 조금 더
멀리(60~100m) 있는 경우 -- 이 경우 nearest가 미세 곡률 지점에 apex를
고정해버려 sharpest 대비 최대 9.7km/h 더 높은(덜 안전한) 값을 냄. 즉
**"연속된 두 실제 커브(2차가 조금 더 급함)" 케이스에서는 nearest가
명백히 우월하지만, "근접한 미세잡음 vs 약간 먼 진짜 급커브" 케이스에서는
nearest가 오히려 불리할 수 있음** -- 두 특성이 공존. 최소 심각도 게이트
추가 여부는 사용자 판단 대기 중(FINDINGS.md 179차).
**사용(nearest)**: `carrot_navi_route_camera_style_nearest(speeds, distances, safe_time, decel_rate_mss)`

## compare_navpos_vs_gps.py (162차, 신규)
**목적**: `carrotMan.xPosLat/xPosLon/xPosAngle`(carrot_serv.py `_update_gps()`가
`estimate_position()`으로 데드레커닝한 ego 추정위치/헤딩, 20Hz)와
`gpsLocation`(차량 실측 GPS, 1Hz)을 시간 정렬해 거리(m) 이격을 계산.
naviPaths/route 곡률이 특정 구간에서 이상하게 0으로 나오면, `carrot_navi_route()`의
곡률/DP 계산 로직을 의심하기 전에 **입력값(current_position/heading_deg) 자체가
실측 GPS와 벌어져 있는지**부터 이 스크립트로 배제할 것.
**배경/발견**: route `aeeed9e4a5` seg3의 실제 급우회전 구간(t=6389~6393,
steer 최대 -121.9°)에서 이 이격이 최대 28m까지 누적되고, `xPosAngle`이 회전
내내(11초) 296.0°로 고정돼 있다가 회전 종료 직후 3.0°로 한번에 점프하는 패턴을
확인 — `bearing_calculated`가 CarrotNavi 앱의 ~1Hz `nPosAngle`을 그대로 쓰고,
그 사이는 직선 데드레커닝만 하기 때문(161차 "route가 커브를 못 봄" 이슈의
근본원인, FINDINGS.md 162차).
**CSV 컬럼**(`--out` 지정 시): `t, seg, navLat, navLon, navAngle, gpsLat, gpsLon, dist_m`.
**사용**:
```bash
python3 compare_navpos_vs_gps.py /home/claude/work/route [--repo /home/claude/ryu] \
    [--t-start 6383] [--t-end 6396] [--out out.csv]
```
**의존성**: `decode_rlog.py`. `extract_gps.py`와 달리 gpsLocation을 자체
내장 추출(별도 CSV 선추출 불필요, route_dir만 주면 됨).
**주의**: `gpsLocation`이 1Hz라 매칭은 가장 가까운 t 기준(선형보간 아님) —
dist_m의 프레임간 개별 값보다 **추세(지속 증가/유지)**로 판단할 것.
**검증(162차, 컨테이너 리셋 후 재실행)**: route `aeeed9e4a5` seg3 t=6383~6396
구간 재현 결과 min=0.7 max=28.1 mean=12.3 (n=260) — 최초 실행과 정확히 일치
확인 완료.

## sim_yaw_anchor_delta.py (165차 설계/166차 신규 — 앵커링/wrap 로직 검증, POSITIVE)
**목적**: 165차가 설계한 방안1(livePose 대신 이미 흐르는
`carControl.orientationNED[2]`를 마지막 fix 시점 절대값과 현재값의
**직접 차분**(Δyaw = cc_yaw_now - cc_yaw_at_fix)으로 앵커링해
`carrot_serv.py::_update_gps()` 헤딩 정체 버그를 고치는 방식, 적분 아님)의
앵커링/wrap 수식 자체를 ryu 코드와 독립적으로 순수함수로 복제해 검증.
`BaselineFrozenHeadingState`(현재 동작: fix 값을 다음 fix 올 때까지 고정),
`AnchoredHeadingStateDiff`(**실제 채택 설계**, orientationNED 두 시점
직접차분), `AnchoredHeadingStateIntegrated`(FINDINGS 165차가 교차검증용으로
언급한 대안 — angularVelocity 적분, 실제 설계 아님) 세 상태머신 비교.
**전제(166차 실측으로 확인 완료)**: `CC.orientationNED[2]`는 나침반 관례
(진북기준 시계방향 양수) — 우회전 시 증가, 좌회전 시 감소. `ccYawRateZ`
부호도 일치. 부호 반전 불필요.
**검증 결과(5/5 PASS)**: (1) fix 50회 반복 시 매 리셋 순간 오차 0(앵커링
코드 자체의 드리프트 없음), (2)(3) 합성 좌/우회전이 359→0/0→359 양방향
wrap 경계를 프레임당 최대점프 1.5°(정상 이동량)로 연속 통과, 최종값
이론치 정확 일치 — 입력 orientationNED가 랩 없이(raw) 계속 누적되는
경우까지 포함, (4) **166차 실측 정체 구간(route aeeed9e4a5 seg3,
t=6371.0~6394.8, 23.8초, 162차가 발견한 그 사건)을 그대로 재생 —
Diff 방식(실제 설계)은 절대값을 그대로 빼는 연산이라 오차 2.8e-14°
(부동소수 수준)로 실제 최종 헤딩(4.24°)과 사실상 완전 일치, baseline
(현재 동작)은 시작값(298.1°)에 고정돼 오차 66.11°(버그 재현, 방안1의
개선폭 정량 확인)**, (5) 실제 설계(Diff)와 교차검증용 대안(적분)이
같은 사건에서 0.60° 이내로 근접(두 독립 신호경로의 자체정합성 확인 —
적분측만 24초간 이산화오차 누적, Diff는 무오차이므로 실제 설계가
이론적으로도 우위).
**한계**: `_update_gps()`의 "새 fix 도착" 감지(`self.last_calculate_gps_time`
변화) 자체는 시뮬레이션 안 함 — `on_fix()` 호출 시점을 테스트가 직접 지정.
**사용**: `python3 sim_yaw_anchor_delta.py --unit-tests`
**의존성**: 없음(표준 라이브러리만). 실측 데이터는 파일 상단
`REAL_FREEZE_WINDOW_SAMPLES`에 120행 인라인 임베드(route CSV는 대용량
정책상 레포 미커밋 — 스크립트 자체가 재현 가능하도록 필요 구간만 내장).

## sim_route_position_uncertainty_gate.py (163차, 신규)
**목적**: 162차 방향2(보수적 완화) 패치 — `carrot_man.py::carrot_navi_route()`
132차 램프리미터에 추가한 "위치불확실성 게이트"(`position_dt_since_fix`가
`ROUTE_POSITION_UNCERTAIN_DT_S=3.0`을 넘으면 완화(상승) 방향만 동결, 하강은
그대로 허용) 사전검증. `RampLimiterState`(패치 전 기준선)와
`GatedRampLimiterState`(162차 패치와 동일 로직)를 나란히 구현해 비교.
**검증 결과(3/3 PASS)**: 정상 시나리오(dt 항상 낮음) 회귀 없음(출력 완전
동일), 실측 규모(경과 ~11초, accel_limit_kmh~3.3) 합성 재현에서 baseline은
매끄럽게 상승(실측 92→149 패턴과 동일 기울기)하는데 gated는 3.0초 이후
완전 동결, 불확실 구간 중에도 raw가 낮아지면(진짜 커브 감지) 게이트가
하강을 막지 않음 확인.
**한계**: `carrotMan`이 `position_dt_since_fix`를 cereal로 발행하지 않아
실측 CSV 직접 재생(replay) 검증은 불가 — 합성 시나리오로만 검증(FINDINGS.md
163차 참고, 향후 cereal 필드 추가 시 재생 검증 가능).
**사용**: `python3 sim_route_position_uncertainty_gate.py --unit-tests`
**의존성**: 없음(표준 라이브러리만, `sim_route_boundary_ramp_limiter.RampLimiterState`와
동일 인터페이스를 자체 재구현).

## build_acados_long_mpc.sh + acados_stub_prelude.py (175차, 신규)
`long_mpc.py`가 사용하는 **실제 acados 솔버**(purely-python 근사가 아님)를 이 컨테이너
안에서 코드젠+컴파일해서 살아있는 `LongitudinalMpc` 객체로 인스턴스화하는 절차.
기존 `sim_*`/`replay_*` 스크립트들은 전부 acados MPC 자체는 재현하지 않고 순수함수로
근사했었는데(FINDINGS 참고), 이건 그 한계를 처음으로 넘은 것 — A_CHANGE_COST 등 실제
비용함수 파라미터가 solver 출력에 미치는 영향을 직접 확인 가능해짐 (174차 원인B 재현검증
용도로 175차에 작성).

**사용**:
```
bash /home/claude/devnotes/toolkit/build_acados_long_mpc.sh
export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
export PYTHONPATH=/home/claude/ryu
python3 -c "
exec(open('/home/claude/devnotes/toolkit/acados_stub_prelude.py').read())
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc
mpc = LongitudinalMpc(mode='acc')
"
```

**소요**: 1~2분 (pip 설치 + acados 코드젠 + gcc 컴파일 2단계). 컨테이너 리셋마다 재실행 필요
(빌드 산출물은 세션 간 보존 안 됨 — repo에도 커밋하지 않음, `.so`/`c_generated_code/`는
`work/`급 산출물).

**의존성**: `pip install setproctitle smbus2 pyzmq casadi cython future-fstrings` (스크립트가
자동 설치). `third_party/acados/x86_64/{lib,t_renderer}` 사전빌드 바이너리가 ryu repo에
이미 포함돼 있어야 함(현재 c3-ms-dev에 있음, x86_64 전용 — larch64/Darwin 컨테이너에선
경로 수정 필요).

**제약**: `acados_stub_prelude.py`가 `Params`/`cereal.messaging`/`Events`를 전부 no-op으로
스텁하므로, `LongitudinalMpc.set_weights()/update()/run()` 등 solver 계산 자체는 정상이지만
Params에서 값을 읽는 분기는 전부 기본값으로 흐름. 재현 시뮬레이션 작성 시
A_CHANGE_COST 등 비교하려는 상수는 `long_mpc.py` 소스를 직접 patch하거나 인스턴스
속성을 덮어써서 주입해야 함(다음 세션에서 재현 스크립트 작성 시 이 패턴 사용 예정).

## sim_acados_causeB_signflip.py (176차, 신규 — 원인B 재현검증 SUCCESS)
`build_acados_long_mpc.sh`로 빌드한 실솔버 위에서 174차 원인B 가설("A_CHANGE_COST=200이
리드없는 cruise 모드에서 가속->감속 부호전환을 구조적으로 지연시킨다")을 폐루프
시뮬레이션으로 검증. `LongitudinalMpc.update()`가 요구하는 `carrot`/`radarstate` 객체를
Params 의존 없는 최소 mock(`FakeCarrot`/`FakeLead`/`FakeRadarState`)으로 직접 구현 --
`T_FOLLOW`는 이 가설과 무관하므로 표준(personality) 근사 고정값(1.2s)으로 단순화.

**제약(중요)**: route `00000372--6310bba9b8--5,6` raw zip이 devnotes 캐시에 없어(172/174차
모두 재업로드였고 176차 세션엔 미제공) 실측 프레임별 값을 그대로 주입하지 못함 -- 대신
FINDINGS.md 174차 요약 특성(vEgo/liveRouteSpeed가 ~57~58kph에서 교차, 이후 목표
57.9->48.1kph 3초 램프, leadStatus=False)을 재현한 **통제된 합성 시나리오**. leadStatus=False를
전 구간(3초) 고정했는데 실측은 t=830.55(구간 시작 후 약 1초)에 리드가 재획득됐으므로, 이
스크립트의 결과는 "리드 재획득 도움 없이 얼마나 느린가"의 **상한(worst-case) 재현** --
실측 gap(4.35kph)보다 시뮬레이션 gap이 더 크게 나오는 것은 정상(리드 재획득으로 인한
추가 제동 보조를 반영하지 않았기 때문).

폐루프 방식: 매 사이클 `a_solution[1]`을 다음 스텝 명령가속도로 삼아 ego 상태(v_ego/a_ego)를
직접 적분 전진 -- 실차의 롱컨트롤 추종 지연을 이상화(무지연)했으므로 실측보다 관대한(더
빠르게 반응하는) 조건. 그럼에도 baseline vs 완화 조건 간 차이가 나타나면 가설이 강하게
뒷받침됨.

**결과(SUCCESS, 가설 재현 확인)**:
| 조건 | A_CHANGE_COST | 가속->감속 부호전환 시각 | t=3.0s gap |
|---|---|---|---|
| baseline(현재 코드) | 200 | 1.5s | +9.19kph |
| 완화(리드있음 최소값) | 20 | 1.0s | +7.41kph |

baseline이 완화 조건보다 부호전환이 **0.5초 더 느리고**, 3초 시점 gap도 더 큼 --
174차 정적분석 가설(리드없는 cruise 모드에서 A_CHANGE_COST=200이 구조적으로 반응을
지연시킨다)이 acados 실솔버 거동으로도 재현 확인됨. 다음 단계(패치 설계)로 넘어갈 근거 확보.

**사용**:
```
bash devnotes/toolkit/build_acados_long_mpc.sh
export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
export PYTHONPATH=/home/claude/ryu
python3 devnotes/toolkit/sim_acados_causeB_signflip.py
```
**의존성**: `build_acados_long_mpc.sh` + `acados_stub_prelude.py`(위 항목) 선행 필요.

## sim_acados_causeB_real_replay.py (176차 계속, 신규 — 실측 프레임 재검증)
`sim_acados_causeB_signflip.py`(합성 시나리오)의 후속. 사용자가 174/172차와
동일 route(`00000372--6310bba9b8--5,6`) raw zip을 재업로드해 `extract_log.py
--with-navi-paths`로 재추출(2401행, commit `4a15da4`=173차, 174차와 동일 코드
상태)한 CSV를 실측 프레임 단위로 그대로 acados 실솔버에 주입해 원인B 가설을
재검증한다.

**두 모드**:
- `openloop`(기본 아님, `--mode openloop`): 매 프레임 `mpc.set_cur_state()`로
  실측 vEgo/aEgo로 강제 리셋 후 1스텝만 `update()` -- 1프레임짜리 국소 반응만
  보므로 "누적 지연" 효과가 지워짐. baseline 1프레임 예측 오차는 작음(평균
  +0.09 m/s², RMSE 0.19 -- 실차가 쓰는 MPC이므로 당연한 정합성 확인). baseline
  vs 완화(20) 간 예측 차이도 평균 0.047 m/s²로 작게 나옴 -- 이 모드만으론
  가설 검증에 불충분.
- `closedloop`(기본): t=829.0 실측 초기상태에서 출발, 이후 ego 상태는 solver
  자신의 `a_solution[1]`로 적분 전진(실측 dt 사용), target(`liveRouteSpeed`
  또는 `desiredSpeed`, `--v-cruise-col`)과 leadOne 트랙은 실측 시퀀스를
  exogenous input으로 그대로 사용.

**결과(가설 재확인)**: closedloop에서 baseline(200) 부호전환 t=830.95 vs
완화(20) t=830.50 -- **0.45초 차이**, `sim_acados_causeB_signflip.py`(합성,
0.5초 차이)와 방향/크기 일치. `v_cruise` 컬럼을 `liveRouteSpeed`/`desiredSpeed`
어느 쪽으로 써도 결과 거의 동일(target 컬럼 선택 문제 아님).

**[미해결] 절대 감속량 괴리**: baseline(200)조차 시뮬레이션 감속량이 실측보다
훨씬 약함(예: t=831.80 실측 aEgo=-0.775 vs 시뮬 baseline aEgo=-0.214). 후보
원인: `FakeCarrot`의 `comfort_brake=2.5`/`personality=standard`/
`T_FOLLOW=1.2` 고정 근사값이 실제 그 시점 Params 기반 값과 다를 가능성.
A_CHANGE_COST 자체의 영향(위 비교)과는 별개 축의 문제 -- 다음 세션 조사 필요.

**[결정적] t=832.51 이후 비교 무효**: `brakePressed`가 정확히
t=832.509110에 `True`로 전환(직후 `cruiseEnabled=False`) -- 이 시점부터
실측 aEgo(-1.5~-2.9)는 운전자 수동 브레이크 페달 입력이 섞인 값이라 MPC
단독 출력과 비교 자체가 무효. 이 route로 향후 비교 시 반드시 t<832.51로
한정할 것.

**`src` 컬럼 확인**: 전 구간 `route`로 고정 -- vision-only phantom-lead
의심 트랙(radar=False, vRel≈-7~-8m/s, dRel 74~100m 노이즈성, modelProb
0.15~0.7 낮고 불안정)이 존재했으나 바인딩 제약은 아니었음(cruise/route가
계속 지배). `leadJLead`/`aLeadTau`는 `extract_log.py` 미추출 컬럼이라
jLead=0.0으로 근사(영향 제한적으로 판단).

**CSV 보관 안 함**: 세션 정책(레포에 대용량 CSV 커밋 금지, Drive 커넥터
미연결)에 따라 `data/routes/`에 캐싱하지 않음 -- 이 route로 추가 분석
필요 시 zip 재업로드 필요.

**사용**:
```
bash devnotes/toolkit/build_acados_long_mpc.sh
export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
export PYTHONPATH=/home/claude/ryu
python3 devnotes/toolkit/sim_acados_causeB_real_replay.py <csv_path> \
    [--t-start 829.0] [--t-end 832.6] [--mode both|openloop|closedloop] \
    [--v-cruise-col liveRouteSpeed|desiredSpeed]
```
**의존성**: `build_acados_long_mpc.sh` + `acados_stub_prelude.py` 선행 필요.
CSV는 `extract_log.py --with-navi-paths`로 재추출 필요(캐시 없음).

## sim_causeB_patch_validate.py (177차, 신규 — 원인B 패치 검증)
176차가 검증한 원인B 가설(리드없는 cruise 모드에서 A_CHANGE_COST=200 고정이
route 감속 추종을 구조적으로 지연시킨다)에 대한 실제 패치(long_mpc.py 내
`route_decel_rate` 기반 a_change_cost 완화 게이트)를 검증한다.

**패치 구조**: `self.source=='cruise'`(리드/정지선이 아니라 순수 route/cruise
타겟이 지배)일 때만, route 목표속도(v_cruise) 하강률을 EMA(j_lead와 동일한
0.1/0.9 저역통과)로 추적해 `CRUISE_DECEL_RATE_RELAX_LOW`(0.3 m/s²)~`_HIGH`
(0.85 m/s²) 구간에서 `base_a_change_cost`를 200→20(`CRUISE_DECEL_RELAX_A_CHANGE_COST`)
까지 선형 완화. 리드 케이스의 기존 `np.interp(abs(j_lead), [0.3, 2.0], [200, 20])`
와 동일 패턴을 route 아날로그로 구현(PARAMS_REGISTRY.md 참고).

**검증 방식**: `mpc.a_change_cost`를 외부에서 강제 override하지 않는다(패치가
이미 update() 내부에서 매 사이클 자체 계산하므로 override는 즉시 덮어써져
무의미). 대신 "패치 OFF" 비교군은 모듈 상수 `CRUISE_DECEL_RATE_RELAX_LOW/HIGH`를
실행 중 비현실적으로 큰 값으로 monkeypatch(route_decel_rate가 항상 LOW 미만이
되어 완화가 절대 발동하지 않음 = 기존 200 고정과 동일) -- 프로덕션 코드에는
이런 토글을 두지 않는다(글로벌 kill-switch 금지 원칙, monkeypatch는 이
스크립트 안에서만 유효). 실제 production 순서(`longitudinal_planner.py` 220행
`set_weights()` -> 225행 `update()`)와 동일하게 매 사이클 `set_weights()`를
먼저 호출 -- 이걸 빠뜨리면 a_change_cost가 solver 비용행렬에 반영되지 않아
ON/OFF 결과가 동일하게 나오는 버그가 있었음(1차 검증 시 실제로 겪음, 기록).

**결과**: `sim_acados_causeB_signflip.py`(176차 1차)와 동일 합성 시나리오(174차
요약 특성) 기준 -- 부호전환 1.5s(OFF) → 1.25s(ON), t=3.0s gap 9.19→7.99kph
(약 13% 개선). **HIGH=1.0으로 최초 설계했으나 EMA(0.1/0.9) 평활화된
route_decel_rate 정상상태가 ~0.906까지만 도달해 완전완화(20)에 못 미침(개선폭
0.2s에 그침) → 0.85로 재조정, 0.25s로 소폭 상승.** 176차가 보여준 baseline vs
A_CHANGE_COST=20 상수 고정 간 차이(0.45~0.5s)에는 여전히 못 미침 -- EMA
평활화 자체가 노이즈성 route 흔들림에 즉각 반응하지 않기 위한 의도된 지연이라
구조적 트레이드오프. 다음 튜닝 후보: EMA 계수를 route 전용으로 더 빠르게(예:
0.2/0.8), 또는 route 하강률 대신 다른 신호(예: v_gap) 병용.

**미검증**: 실측 프레임(route `6310bba9b8`) 재검증 -- zip 재업로드 필요(캐싱
안 됨). `git am` 검증/실차 검증 모두 아직.

**사용**:
```
bash devnotes/toolkit/build_acados_long_mpc.sh
export LD_LIBRARY_PATH=/home/claude/ryu/third_party/acados/x86_64/lib
export PYTHONPATH=/home/claude/ryu
python3 devnotes/toolkit/sim_causeB_patch_validate.py
```
**의존성**: `build_acados_long_mpc.sh` + `acados_stub_prelude.py` 선행 필요.

## sim_route_hi_vego_anchor_203.py (203차, 신규 — hi=math.inf vs hi=vEgo A/B 재현)
202차가 제안한 "상승측(hi) 디바운스 게이트" 설계의 1단계 검증. `carrot_man.py`의
실제 램프 구조(150 cap + 199차 하강측 boost 로직)를 그대로 재현하되, 상승측
(`hi`)만 A(`hi=math.inf`, 현재 173차 설계)/B(`hi=vEgo_kph`, 203차 제안)로
병렬 계산. `would_bind`(route 후보가 실제 arbitration 승자값 이하가 되는
프레임 비율)를 실측 `desiredSpeed`(src 컬럼) 대비로 계산.

**결과 요약**: 북대전IC(t=450~498) would_bind A 37.1% → B 98.9%로 방향 확인.
단 스파이크가 "단발" 아니라 t=418.62~423.18(4.6초) 지속되는 고원임을 신규
발견 — apex_idx=21(진짜 커브) 전환 시점(t=423.23)부터 raw가 단조감소로
전환되어 이 시점 이후로는 `hi` 설정이 무관해짐.

**주의(데이터 한계)**: extract_log.py는 carrot_navi_route()가 선택한
apex(idx/dist/speed) 1개만 기록하고, 내부 candidates 리스트 전체(개수)는
텔레메트리에 없음. "candidates_empty"는 이 CSV로 직접 관측 불가(199차
8세그 로그 기준 activePoints=True 구간에서 apex_idx=-1 프레임 0건).

**사용**:
```
python3 devnotes/toolkit/sim_route_hi_vego_anchor_203.py [csv_path]
```
기본 csv_path는 `/mnt/user-data/uploads/199cha_8seg_route_extracted.csv`
(199차 8세그, `extract_log.py --with-navi-paths`로 재추출 가능, devnotes에
캐싱 안 됨 — §23).

## sim_route_hi_debounce_sweep_203.py (203차, 신규 — N프레임 디바운스 스윕)
"apex_idx 변화 + routeOutSpeed(150 cap 이전 원시값) 급등(≥20kph, ≥150kph)"을
스파이크 근사 신호로 삼아 armed(hi=vEgo)/disarm(hi=inf, N프레임 연속 무신호)
게이트를 N=3/5/8/10/60/92/100/120 프레임(0.15~6.0초)으로 스윕.

**핵심 발견**: N=92(4.6초)에서 disarm 시각이 진짜 커브 진입(t=423.23)과
정확히 일치 — 유효 신호. **그러나 동일 신호가 정상적인 연속곡선 통과 후
가속 구간(t=382~393, 실측 조향각/vEgo/src로 확인)에서도 반복 발생**, N=92
적용 시 이 구간 armed 비율 10.1/11초 — armed 동안 route 후보가 vEgo에
고정되므로 실제 가속을 억제할 위험. **"apex_idx 급변" 단독 신호로는 허위
스파이크와 정상 연속곡선 후보전환을 구분 불가**하다는 결론(FINDINGS.md
203차 참고). 이 결과를 근거로 203차 코드화는 보류, 사용자에게 3가지 방향
제시(candidate_count 실계측 추가 / 상승측 설계 자체 재검토 / 추가 로그
확보 후 재검증).

**사용**:
```
python3 devnotes/toolkit/sim_route_hi_debounce_sweep_203.py [csv_path]
```


## sim_route_205_vego_cap_ab_206.py (206차, 신규 -- 205차 패치 실차로그 A/B 재검증, NEGATIVE)
205차(out_speed 상한 고정 150 -> max(vEgo_kph, apex_speed)와 150 중 min으로
동적화)가 실제 202/203차 문제 로그(199차 8세그, 북대전IC 진입 26초 전
t=418.62~423.18 apex_idx 슬라이딩 스파이크/고원)에서 효과가 있는지 검증.
carrot_man.py L905~1038의 실제 코드 구조(raw 클리핑 -> 199차 boost ->
172/173차 비대칭 램프리미터 -> 162/167차 position-uncertainty 게이트)를
OLD(202차 고정 150)/NEW(205차 동적 상한) 두 갈래로 병렬 재현.

**핵심 발견(NEGATIVE)**: 문제의 스파이크/고원 구간(t=418.4~423.2) 및 이후
북대전IC 접근 구간(t=423~498) 전체에서 OLD와 NEW가 **완전히 동일**(would_bind
37.1%->37.1%, 프레임별 출력값 소수점까지 일치). 원인: 이 실패모드에서는
apex_idx 오선택이 raw out_speed뿐 아니라 apex_speed(목표속도) 자체도 함께
오염시켜(스파이크 구간 내내 raw==apex_speed, 둘 다 ~297~298로 동일) 205차
공식의 `max(vEgo, apex_speed)` 항이 항상 apex_speed(오염된 값)에 의해
지배되고 vEgo 하한이 전혀 작동하지 않음. 205차 WIP 검증에 쓰인 4개 합성
시나리오는 raw와 apex_speed를 독립 변수로 가정했으나(예: raw=298/apex=50),
실제 로그에서는 이 둘이 같은 근본원인(candidates 리스트 슬라이딩)으로
동시에 오염되어 분리되지 않음이 실측으로 확인됨.

전체 8세그(7,098 활성 프레임) 중 OLD!=NEW인 프레임은 56개뿐(t=524 부근
소규모 사례 1건, 원인 구간과 무관 -- raw와 apex_speed가 실제로 8kph 정도
벌어지는 경미한 후보전환 상황에서는 205차 공식이 의도대로 작동함을 확인,
단 이번 202/203차 핵심 실패모드와는 무관).

**참고**: OLD(202차 150고정) 자체는 이미 이 로그에서 상당한 개선을
보여줌(apex 최근접 프레임 t=461.08 기준 목표 대비 격차 4.3kph -- 202차
패치 이전 원본 분석의 ~170kph 격차 대비 큰 개선, 단 이 개선은 202차의
150 cap 자체에 의한 것이며 205차의 기여는 이 로그에서 사실상 0).

**결론**: 205차 패치는 코드 정적 검증/합성 시나리오상으로는 문제 없으나,
202/203차가 실제로 규명한 핵심 실패모드(apex_idx 슬라이딩으로 인한
raw/apex_speed 동시 오염)를 이 로그 기준으로는 해결하지 못함. 203차가
이미 보류해둔 근본 대응(candidate_count 실계측 계측 추가/상승측 게이트
재설계)이 여전히 유효한 다음 과제.

**사용**:
```
python3 devnotes/toolkit/sim_route_205_vego_cap_ab_206.py [csv_path]
```
기본 csv_path는 `/mnt/user-data/uploads/199cha_8seg_route_extracted.csv`.
