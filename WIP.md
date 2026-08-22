# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

- 저장 시각: 2026-08-22 (46차, 진행중 — 사용자 요청으로 세그먼트 1개
  완료 시마다 체크포인트) "곡선구간 가감속 부족"(진입전 사전감속 부족/
  정점 감속 부족/탈출후 가속지연 3가지 증상) 제보로 패치이전 로그 3개
  업로드받아 분석 시작. **route1(`203f99d429` seg8) 완료** — 사전감속
  부족(1)/정점 감속 부족(2) 둘 다 데이터로 확인, 원인 후보로
  `carrot_serv.py`의 model 게이트 `abs(vturn_speed)<120`(13차 `119b101`
  도입)이 vturn 자체가 원거리에서 불안정한 구간에서 model의 더 안정적인
  조기 신호를 차단하는 것을 신규 발견(표본 1건, NEEDS_VALIDATION).
  탈출후 가속지연(3)은 이 세그 안에서 확인 못함(세그 종료 전 커브 안
  끝남). 상세는 FINDINGS.md/PARAMS_REGISTRY.md 46차 항목 참고.
  toolkit `extract_log.py`에 `modelTurnSpeed` 컬럼 신규 추가(이것 없이는
  model 후보 실제값 자체를 볼 수 없어서 분석 불가했음).
  **[갱신] route2(`f3db6ca89d`, 5세그 "곡선_여러개") 완료** — 연속 급커브
  왕복국도라 route1과 성격이 달라, `work/curve_decel_scan.py`(신규
  자동 스캐너, toolkit 미편입 스크래치)로 32개 커브 이벤트 일괄 분석.
  **정점 감속 부족(24/32건, 75%, 평균+8.2km/h/최대+18.1km/h)이 route1과
  합쳐 2 route/25건으로 확대 재현** — 이 문제는 특정 로그의 우연이 아니라
  일반적 패턴일 가능성 높아짐. 사전감속/탈출가속지연은 이 route가 연속
  커브 도로라 판단 부적합(N/A 다수, 도로 특성 때문이지 버그 아님).
  상세는 FINDINGS.md 46차 route2 항목 참고.
  **[갱신] route3(`866476e5c3` seg18, "곡선_vturn_이상함") 완료** —
  파일명이 가리키던 "이상함"의 정체 특정: vturn이 정점 통과 직후(아직
  곡선 안 끝난 시점, t=4786.9)부터 1초 만에 103→149km/h로 조기 해제됨.
  이번엔 cam(구간단속) 후보가 t=4787.23부터 110km/h로 8초 고정시켜
  min()에서 우연히 이겨 실제로는 문제가 안 드러남 — cam이 없었다면
  커브 안 끝난 채 재가속했을 가능성(표본 1건, 조건부 재현).
  **3번 증상("탈출 후 가속 지연")과 반대 방향 — route2/route3 어디서도
  탈출 지연 증거 없음, 오히려 vturn 조기 해제 경향.** 정점 감속 부족은
  +9.6km/h로 3 route 전부 일관 재현(표본 확대). 상세는 FINDINGS.md
  "route3(866476e5c3 seg18, 곡선_vturn_이상함) 분석" 항목 참고.
  **[정정, qcamera 영상 교차검증] "vturn 조기해제로 곡선 안 끝난 채
  재가속" 결론은 근거 약화** — 실제 영상 확인 결과 t≈4787.88(vturn
  149 도달 시점) 무렵 이미 화면상 도로가 거의 직선이었음(steer만
  보고 곡선 지속으로 판단한 게 과대판단). t=4791~4795.8은 완전 직선인데
  steer -5~-6.5deg 잔존 — 원인 불명(차선유지 보정 추정, 다음 세션
  규명 필요). (3) 탈출지연/조기해제 둘 다 표본에서 확실한 증거 없음으로
  재정정. (2) 정점 감속 부족은 영상으로도 곡선 진행 확인돼 그대로 유지.
  상세는 FINDINGS.md "[정정] qcamera 영상 교차검증" 항목 참고.
  **다음: route 소스(source) 분석 재개 — cam/road/vCruiseCluster 캡이
  탈출지연 체감의 실제 원인인지 가설 확인 우선. + steer 잔존값(곡선
  무관 오프셋) 정체 규명.** 코드 변경 없음.
  **[갱신] route1/route2 seg15도 qcamera 확대검증 완료** — 둘 다
  화면으로도 진짜 급커브(route1=진출램프+경고표지판, route2 seg15=
  국도 헤어핀+교량) 확인, 기존 결론(사전감속/정점감속 부족) 그대로
  유지. route2 seg15는 max gap 시점(9504.03)이 실제 조향각 정점
  (9505.73)보다 1.7초 앞선 진입중반이라 "정점 감속 부족"이 사실
  (1)사전감속 부족과 연속된 문제일 가능성 신규 제기 — 다음 세션에서
  32건 재분류 검토. 상세는 FINDINGS.md "qcamera 영상 교차검증 확대"
  항목 참고.
  **[체크포인트] route2 32건 재분류 완료** — `work/curve_gap_vs_apex_scan.py`
  신규 작성, 실제 초과사례 24건 중 **19건(79%)이 max gap을 apex보다
  평균 1.26초 먼저 찍음** — "정점 감속 부족"이 대부분 사전감속 부족의
  연장이라는 가설 강하게 뒷받침(24건 재현, 46차 원 집계와 일치).
  진짜 "정점에서만" 못 따라간 사례는 3건(12%)뿐. 상세는 FINDINGS.md
  "route2 32건 커브 이벤트 재분류" 항목 참고.
  **다음(진행중, 이어서 할 것)**: (a) route1도 같은 delta 계산 적용,
  (b) `abs(vturn_speed)<120` 게이트가 79% 사례들의 공통 원인인지 개별
  검증, (c) `curve_gap_vs_apex_scan.py` toolkit 편입 여부 판단.
  코드 변경 없음(스크래치 스크립트만 신규).
  **[체크포인트2] (a)(b) 완료** — route1은 유효 이벤트 1건뿐이지만
  delta=-0.95s로 route2와 방향 일치(표본 부족, 참고용). **(b) model
  게이트 가설은 route2에서 기각** — 24건 전부 진입 3초전 vTurnSpeed가
  이미 120 미만이라 게이트가 애초에 vturn을 안 막고 있었음. route1
  (장거리 직선 후 첫 커브)과 route2(연속 커브, 직전 커브 여파로 vturn
  이미 낮음)는 커브 진입 직전 vturn 초기상태가 다른 시나리오라 원인도
  다를 것으로 재평가. 새 후보 3개(vturn_decel_rate 물리한계/
  vturn_lookahead_horizon_s 국도 커브간격 부적합/desiredCurvature
  순간값만 반영해 조임 속도 후행) — 다음 세션 `vturn_speed()`
  (carrot_man.py) 코드 리딩으로 좁힐 것. 상세는 FINDINGS.md "(a)(b)
  이어서 진행" 항목 참고.
  **[체크포인트3, (c) 완료] `curve_apex_vs_gap_delta()` toolkit
  편입 완료** — `analysis_helpers.py`에 정식 함수로 추가(스크래치
  스크립트와 회귀검증 일치 확인), README.md/CHANGELOG.md 동기화.
  **1번(route2 32건 재분류) 작업 여기서 일단락.** 다음 세션 최우선:
  `vturn_speed()`(carrot_man.py) 코드 리딩으로 (i)vturn_decel_rate
  물리한계/(ii)vturn_lookahead_horizon_s 부적합/(iii)desiredCurvature
  순간값 반영 3개 후보 중 근본원인 좁히기. 이후 남은 2)cam/road/
  vCruiseCluster 캡 가설, 3)route3 steer 잔존값 규명 순서로 진행 예정.


- 저장 시각: 2026-08-22 (45차 계속 — "정지 후 출발 가속 약화" 조치 패치
  작성/전달 완료(**실차 검증 대기**). 사용자와 논의 후 "정차→출발"을
  상태(state)로 잡아 이 구간에서만 `ttc_accel_weight()`(38차)를 완전
  우회하는 launch bypass 방식으로 확정·구현. `LAUNCH_BYPASS_STOP_V_EGO
  =0.3m/s`(정차 판정)/`LAUNCH_BYPASS_EXIT_V_EGO=5.0m/s`(출발완료 판정,
  38/39차 로직 복귀) 신규 상수 2개 추가. bypass 활성 중엔 39차
  rise-rate 제한도 함께 우회. danger override(TTC<=2.5s)는 bypass와
  무관하게 항상 최우선 유지. `work/test_launch_bypass.py` 합성 시나리오
  4종(정차중 출발/exit 전환/고속잡음 회귀/저속 danger cut-in 회귀)
  로직 단위 검증 완료 — **exit 전환 순간 w가 급하강할 수 있음을 발견,
  실차 검증 시 체감 확인 필요**(상세는 FINDINGS.md 45차 "조치" 항목).
  `git am` temp branch 검증(base `c31ddca`) + `py_compile` 통과. patch
  `0001-long_mpc-launch-bypass-45cha.patch` 전달함(`/mnt/user-data/
  outputs/`, `git am` 안내 별도 전달).
  **다음 세션 시작할 것**: 사용자가 patch 적용+push 여부 확인 →
  실차 검증(위 FINDINGS.md 45차 "다음 단계" 참고) → 통과 시 EXIT_V_EGO
  값 실차 기준 재조정 검토.
  **[갱신] patch 적용/push 완료 확인** — origin `c3-ms-dev`
  `c31ddca..651c434` 확인. **다음은 실차 검증만 남음**(정차→출발 매끈한
  가속 복원 여부, exit 전환 순간 끊김 체감 여부, 고속/저속 회귀 없는지).

- 저장 시각: 2026-08-22 (45차 — 완료, 코드 변경 없음(분석만). "정지 후
  출발 가속 약화" 제보 분석 -> 근본원인 특정(NEEDS_VALIDATION):
  `long_mpc.py`의 `ttc_accel_weight()`(38차, `c3ea08e`)가
  `closing<=0.1`(앞차가 정지한 자차보다 이미 빠른, 즉 출발 직후 흔한
  상황)일 때 weight를 무조건 0으로 만들어 앞차의 실측 가속도
  (`aLeadK`)가 MPC 리드 예측에서 통째로 사라짐 -- 그 결과 출발 시
  목표가속도가 패치 이전보다 보수적으로 산출됨. 패치이전 로그(HEAD
  `a4b5550`, 이 로직 자체가 없던 시점)와 패치이후 로그 CSV+화면녹화
  영상(온스크린 1.Accel 그래프) 교차검증으로 뒷받침. 상세는
  FINDINGS.md 45차 항목 참고. **코드 수정은 미적용 -- 제안 3가지
  중 방향 사용자 결정 대기.**
  **[중요] 패치이후 로그의 실행 커밋(`96e789c7`)이 origin
  `c3-ms-dev`에 없음** -- 사용자가 로컬에서 만든 변경이 push/기록 안
  된 것으로 추정. 다음 세션 시작 전에 사용자에게 이 커밋을 push했는지
  확인 필요(단, 이번 45차 결론 자체는 이미 origin에 있는 코드
  (`c3ea08e`/`52668ec`)만으로 완전히 설명되므로 이 누락과 무관하게
  유효함).
  **다음 세션 시작할 것**: 위 3가지 조치안 중 방향 결정 -> 패치 작성
  (사용자 승인 후) -> 실차 재현 시나리오 기준 회귀검증(38차가 막으려던
  고속 잡음성 가감속 과잉반응이 재발하지 않는지 필수 확인).

- 저장 시각: 2026-08-22 (44차 — 완료. 42차 "B seg10 vision 노이즈"
  결론 정정에 더해, 재발 방지용 `analysis_helpers.
  dRel_jump_ego_maneuver_overlap()`을 toolkit에 신규 추가·push함
  (앞으로 곡선 구간 dRel 점프를 "vision 노이즈"로 성급히 결론내리기
  전에 이 함수로 ego blinker/조향반전 겹침부터 자동 스크리닝 가능).
  상세는 FINDINGS.md 44차 항목 + toolkit/CHANGELOG.md 44차 항목 참고.
  **다음 세션 시작할 것 없음** — 열린 항목은 저우선 후보 3개뿐
  (FINDINGS.md 44차 "다음 세션 후보" 참고).

- 저장 시각: 2026-08-22 (42차 — 41차와 동일 로그를 qcamera 포함해
  재업로드받아 4대 접근 이벤트 전부 프레임 대조 완료·push함. **다음
  세션 시작할 것 없음** — route B seg10 건이 "vision dRel 순간
  오추정+그 이후 진짜 서행 접근" 복합 패턴임을 영상으로 실증(상세는
  FINDINGS.md 42차 항목). 코드 변경 없음, 열린 항목은 저우선 후보
  3개뿐(아래 "42차" 섹션 참고). **사용자가 "로그 올리면 항상 qcamera
  영상과 같이 분석"을 표준 절차로 요청함 — 앞으로 rlog/zip 업로드 시
  qcamera가 포함돼 있으면 기본적으로 프레임 대조까지 함께 수행할
  것.**)

## 42차 (완료) — 41차 4대 이벤트 qcamera 프레임 대조, B seg10 노이즈 가설 영상 실증
- 상세는 FINDINGS.md 42차 항목 참고. 요약: A seg11/A seg19/B seg6
  3건은 영상으로 "진짜 접근" 확증. B seg10 1건은 커브 구간(왕복
  2차선 지방도)에서 vision dRel이 0.65초 만에 86.9m→42.5m로
  물리적으로 불가능한 점프를 보고했는데, 같은 시각 프레임들을
  대조하니 실제로는 그 정도 접근이 없었음을 확인(노이즈) — 단
  그 이후(t=1897.6) 프레임에선 같은 리드가 실제로 뚜렷이 가까워져
  있어, "노이즈 점프 + 그 이후 진짜 서행 접근"이 섞인 패턴으로 규명.
- **코드 변경 없음(관찰/분석만)**, patch 없음.
- **다음 세션 후보 (저우선)**:
  1. `curve_lead_dRel_jump_consistency`류 일관성 체크를 vision-only
     closing-rate 게이트 자체에 적용하는 방안 — 이번 영상 실증으로
     근거 격상, 단 표본 1건이라 여전히 저우선.
  2. 왕복 2차선 지방도 커브 샘플 추가 확보(고속도로 커브와 오차
     특성 비교).
  3. 40차 radard 크래시 수정 완전 확인(화면 오버레이 직접 확인)
     여전히 미실시.

## (이전 체크포인트, 아래부터는 41차 원본 기록 — 위 42차로 보강 완료)
- 저장 시각: 2026-08-22 (41차 — "앞차_카메라_인식.zip"(2라우트,
  1079.5s, HEAD `c31ddca`) 분석 완료·push함. **다음 세션 시작할 것
  없음 — 아래 "41차" 섹션은 완료 기록, 열린 항목은 저우선 후보 2개뿐
  (아래 "다음 세션 후보" 참고). 40차 radard 크래시 항목은 이번 로그로
  간접 확인됐으나 화면 오버레이 직접 확인은 여전히 미실시.**)

## 41차 (완료) — "카메라 인식 시 미감속" 계열 패치 최신 HEAD 재검증
- 상세는 FINDINGS.md 41차 항목 참고. 요약: 33/36차 frac_rate 게이트 +
  38/39차 TTC damping/rise-rate가 HEAD `c31ddca`에서 정상 동작 재확인
  (급접근 4건 전부 레이더 락온보다 0.7~4.2초 이전 게이트 활성화).
  40차 radard 크래시 수정도 로그 데이터 무결성으로 간접 확인(전 구간
  radar/leadStatus 정상 기록). 안전지표(harsh_brake/turn_speed_
  violation/cut_in/ttc_danger) 전부 0건, 사용자 체감도 양호.
  route B seg10에서 vision vRel-dRel 불일치 노이즈로 인한 "게이트는
  켜졌는데 반영 약함→락온 후 몰림" 잔여 패턴 1건 신규 확인(표본 작음,
  저우선).
- **코드 변경 없음(관찰/분석만)**, patch 없음.
- **다음 세션 후보 (급하지 않음)**:
  1. route B seg10류 vision vRel-dRel 불일치 패턴 재현 로그 추가 확보 시
     `curve_lead_dRel_jump_consistency`류 일관성 체크를 vision-only
     closing-rate 게이트에도 적용하는 방안 검토.
  2. 40차 radard 크래시 수정의 완전한 확인(기기 화면 에러 오버레이
     사라짐 직접 확인) — 이번 로그는 데이터 무결성 기준 간접 확인뿐.

## (이전 체크포인트, 아래부터는 40차 원본 기록 — 위 41차로 대체 완료)
- 저장 시각: 2026-08-22 (40차 — **[URGENT] radard 크래시 긴급 수정,
  패치 적용/push 완료.** origin `c3-ms-dev` HEAD `c31ddca`. **실차
  재기동 후 radard 정상 기동 확인만 남음** — 아래 "40차" 섹션 "다음
  단계" 2번부터 이어감.)

## 40차 (완료 — 패치 적용/push 완료, 실차 재기동 확인 대기) — radard 크래시("프로세스가 실행되지 않았습니다") 원인/수정

- **증상**: 38/39차 패치 적용 후 실차에서 radard 크래시, 화면에 빨간
  에러("radard 프로세스가 실행되지 않았습니다") 표시. 사용자가 스크린샷
  제보(핸드폰에서 세션 진행 중).
- **원인**: 37차(`21effa1`)가 `Track.get_RadarState()` 반환 dict에
  추가한 `sccFallback` 키가 capnp `RadarState.LeadData` 스키마에 없는
  필드라 대입 시 매 사이클 `AttributeError` 크래시. 상세는 FINDINGS.md
  "[FIXED, URGENT] radard 크래시" 항목 참고.
- **발견 경위(중요, 향후 참고)**: 이번 세션 컨테이너를 열어보니 이미
  로컬에 수정 커밋(`f67a834`, 커밋 메시지 "37차 후속")이 존재했으나
  **origin에는 미push, devnotes에도 미기록** 상태였음 — 즉 이전 세션
  (다른 계정 또는 컨테이너 재사용)에서 원인 파악+수정까지는 했지만
  patch 전달/devnotes 갱신 없이 끊긴 것으로 추정됨. 이번 세션에서
  patch 재생성 + devnotes 기록(FINDINGS/PARAMS_REGISTRY)을 완료함.
- **전달**: `0001-radard-sccFallback-radard-37.patch`를
  `/mnt/user-data/outputs/`에 생성, `git am` 안내와 함께 전달함(base
  `52668ec`, 즉 현재 `C:\dev\ryu`의 `c3-ms-dev` HEAD 위에 바로 적용
  가능 — origin `c3-ms-dev`도 아직 `f4160a7`이 최신이므로 사용자 로컬이
  이보다 최신(38/39차+screenrecorder 2건)이어도 이 patch는 radard.py만
  건드리므로 충돌 없이 적용될 것으로 예상).
- **경위(참고, 휴대폰 SSH 시도)**: 노트북 없는 상태에서 우선 휴대폰
  SSH(CarrotWeb 터미널)로 기기 로컬에 동일 수정을 직접 적용하는 스크립트
  (`toolkit/fix_radard_urgent_40cha.sh`, devnotes에 push해 curl로 기기에서
  받게 함)를 시도 — 로컬 커밋(`89382ac`)까지는 성공했으나 `git push`가
  SSH 공개키 미등록(`Permission denied (publickey)`)으로 실패. 이후
  사용자가 노트북으로 복귀해 아래 patch를 정상 `git am` + push 완료.
  **기기 로컬의 `89382ac` 커밋은 origin에 안 올라간 채 기기에만 남아있음**
  — 다음 기기 접속 시 `git fetch && git reset --hard origin/c3-ms-dev`로
  정리 권장(신규 push된 `c31ddca`와 충돌 방지, 아직 미실시).
- **다음 단계(최우선)**:
  1. ~~`git am`으로 `C:\dev\ryu`(c3-ms-dev)에 적용 + `git push`~~ →
     **완료**. `f4160a7..c31ddca` push 확인.
  2. **[남음]** 실차 재기동 후 radard가 정상 기동하는지(에러 오버레이
     사라지는지) 확인 — 이게 최우선 확인 사항. 재기동 시 기기 로컬의
     위 `89382ac`(미push, origin과 별개 커밋)과 새로 pull될 `c31ddca`가
     같은 내용이라 `git pull`이 아니라 `git fetch && git reset --hard
     origin/c3-ms-dev`로 기기 로컬을 origin과 맞추는 걸 권장(기기에서
     직접 pull 예정이라면).
  3. radard 정상화 확인 후, 37차 원래 목적(SCC 단일점 폴백 오탐 방지)이
     실제로 동작하는지 회귀 검증 — 이 항목은 37차/38차/39차 WIP 섹션의
     "남은 항목"과 통합해서 다음 실차 검증 세션에서 함께 확인.

## 39차 (완료 — 패치 적용/push 완료, 실차 검증 대기) — 저속 구간 TTC 게이트 급붕괴로 인한 급정지 느낌, rise-rate 패치
- 상세 원인/조치는 FINDINGS.md 39차 항목 참고. 요약: 38차 TTC 게이트가
  저속에서 dRel이 작아 순식간에 열리며 그동안 은폐된 aLeadK 감속값이
  한꺼번에 반영되는 lurch 발견 → weight 상승 방향에만 rise-rate 제한
  (`LEAD_ACCEL_WEIGHT_RISE_RATE=1.0`) 추가, 단 TTC<=2.5s(실제위험)는
  즉시 우회.
- 패치 `0001-long_mpc-TTC-aLead-weight-lurch-rise-rate.patch` (base
  `c3ea08e`, 38차 패치 위에 쌓임) Master가 `git am` 적용 + `git push` 완료.
  origin/c3-ms-dev HEAD: `52668ec` (2026-08-22).
- **남은 항목(38차와 함께 실차 검증 예정)**:
  1. 실차 검증: (a) 저속 추종 감속 시 급정지 느낌 해소 체감, (b) **회귀
     검증 필수** — 저속 실제 위험 cut-in(TTC<=2.5s)에서 danger override
     정상 발동해 반응 지연 없는지, (c) `LEAD_ACCEL_WEIGHT_RISE_RATE=1.0`
     값 승차감 기준 재조정 여부.
  2. 38차(고속)+39차(저속) 패치가 모두 적용된 상태의 통합 실차 검증 —
     두 상황이 섞인 로그로는 아직 검증한 적 없음.

## 38차 (완료 — 패치 적용/push 완료, 실차 검증 대기) — 앞차 가속도 민감반응, TTC 게이트
- 상세 원인/조치는 FINDINGS.md 38차 항목 참고. 요약: 거리비율 기반
  `MARGIN_ACCEL_GATE`가 고속 구간에서 사실상 상시 무감쇠였던 사각지대를
  `ttc_accel_weight()` 신설 + `min()` 결합으로 보완.
- 패치 `0001-long_mpc-TTC-aLead-damping.patch` — **Master가 `git am` +
  push 완료 확인** (`c3-ms-dev` `21effa1..c3ea08e`).
- **남은 항목(39차 rise-rate 패치와 함께 실차 검증 예정)**:
  1. 실차 검증: 이번 로그 재현 상황(안전거리+완만한 가감속)에서 승차감
     개선 체감 + **회귀 검증**(실제 위험 cut-in/급접근 시 반응 지연 없는지).
  2. `LEAD_ACCEL_TTC_GATE_FULL=12.0s` 값 실차 기준 재조정 필요할 수 있음.

## 37차 계속 3 (진행 중) — 패치 작성 완료, 실차 검증 대기

- 아래 "37차 (완료 — 근본원인/방향 확정)" 섹션의 결정된 방향(1안+2안
  결합)대로 `C:\dev\ryu` base `4fe22cd`(c3-ms-dev HEAD) 위에 패치 작성:
  1. `get_lead()`에 `SCC_FALLBACK_DPATH_GATE=2.0m` 게이트 추가(dPath
     기준, yRel 아님 — 곡률보정 커버 목적).
  2. `Track.get_RadarState()`에 `sccFallback` 플래그, `RadarD.update()`
     조건을 `radar and not sccFallback`으로 변경해 track_scc 폴백만
     LeadBlend를 계속 타도록 분리.
- **로직 단위 합성검증(work/test_scc_gate.py) 7케이스 전부 PASS** —
  특히 "기존 track 존재+저확신+옆차선 폴백" 케이스에서 초안 버그(게이트가
  track 존재 여부에 따라 스킵되던 버그) 발견/수정함. 단, 이는 로직
  단위 검증이며 실제 acados/radard 파이프라인이나 실차 로그 재현은
  아직 미검증.
- `git am` 검증(temp branch, base `4fe22cd`) + `ast` 문법 통과.
- **전달**: `0001-radard-SCC-dPath-LeadBlend-37.patch`를
  `/mnt/user-data/outputs/`에 생성, `git am` 안내와 함께 전달함.
- 상세는 FINDINGS.md/PARAMS_REGISTRY.md 37차 항목(갱신됨) 참고.
- **다음 단계(최우선)**:
  1. ~~사용자가 `git am`으로 `C:\dev\ryu`(c3-ms-dev)에 패치 적용 + push~~ →
     **완료**. `git am`이 처음엔 `c3-ms-test`(당시 체크아웃된 브랜치)에
     적용됨(`b5a1209`) — `long_mpc.py` 무관 커밋이라 컨텍스트 충돌
     없이 적용은 됐으나, 원래 목표인 `c3-ms-dev`가 아니었음. 당시엔
     34차 A/B 비교 오염 방지를 위해 양쪽 브랜치 모두에 반영(cherry-pick
     `b5a1209`→`21effa1` on `c3-ms-dev`)했으나, **이후 사용자가
     `c3-ms-test` 브랜치 자체가 불필요하다고 판단해 로컬+원격 삭제**
     (`git branch -D c3-ms-test` + `git push origin --delete
     c3-ms-test` 확인). 최종적으로 `c3-ms-dev`(`4fe22cd..21effa1`)
     하나에만 남음.
  2. **[남음]** 실차 검증: 원래 옆차선/측면차량 오탐 재현 시나리오 재현 시
     `dPath` 게이트에 걸려 리드 미채택되거나, 채택되더라도
     `sccFallback=True`로 `LeadBlend`가 작동해 급감속으로 안 이어지는지
     확인.
  3. **[남음] 회귀 검증 필수**: `SCC_FALLBACK_DPATH_GATE=2.0m`가 정상적인
     동일차로 SCC 폴백(전체 트랙 시간 74~82% 차지하는 주 경로)을
     과도하게 거르지 않는지, 게이트 도입 후에도 평소 추종이 동일하게
     유지되는지 확인.
  4. **34차(c3-ms-dev vs c3-ms-test A/B 실차 비교) 과제 자체가 취소됨**
     — 브랜치가 삭제됐으므로 아래 34차 섹션의 "다음 세션에서 이어갈 것"
     항목은 더 이상 유효하지 않음(취소 표시, 아래 34차 섹션 참고).

## 37차 (완료 — 근본원인/방향 확정, 패치는 위 "37차 계속 3"에서 작성) — 옆차선 차량 SCC 단일점 락온 급감속, 근본원인 확인

- 사용자가 업로드한 "옆차선_차량_인식_감속.zip"(6세그: 83e6b133f5--16,
  866476e5c3--3, 1723e8b850--16/19, 7ffb3e693c--10, 3f3884d185--6)을
  이번 세션 전용 스크립트(`work/extract_lead_detail.py` — 표준
  extract_log.py엔 없는 leadYRel/leadDPath/leadTrackId 포함)로 추출,
  4개 세그에서 급감속 후보 50건 중 4건 프레임 대조 완료.
- **결론(ROOT_CAUSE_IDENTIFIED)**: `radard.py`의 `get_lead()`가 비전
  매칭 실패/저확신 시 SCC 단일점 폴백(`track_scc`, trackId=0)을
  **차로내 위치(yRel/dPath) 검증 없이** 그대로 채택 → 이 트랙은 항상
  `radar=True`로 반환되고, `RadarD.update()`에서 `radar=True`면
  `LeadBlend`(cutout/closer_jump/TTC 스무딩)를 **전부 우회**하고 바로
  `radarState.leadOne`에 반영됨. 옆차선 차량이 SCC의 유일 타깃으로
  순간 잡히면 걸러낼 안전장치가 애초에 하나도 없음. 4건 전부
  `trackId=0, radar=True`로 동일 — 특히 `83e6b133f5--16`(yRel -5.5~-6.0m)
  과 `3f3884d185--6`(yRel -10.5~-3.0m)은 수치상 옆차로가 명백.
  상세는 FINDINGS.md/PARAMS_REGISTRY.md 37차 항목 참고.
- **영상 대조 완료(qcamera, extract_dashcam_frames.py)**: 4건 중 3건
  (`83e6b133f5--16`/`1723e8b850--19`/`3f3884d185--6`) **옆차선 확정**.
  `7ffb3e693c--10`은 **재분류** — 옆차선이 아니라 저속 도심 커브에서
  주행경로 밖(옆길/건물 진입로)의 정차·횡단 차량을 오탐한 케이스.
  근본원인 코드는 동일(`track_scc` 무검증 채택)하지만 발생 상황이
  다름 — 패치는 "옆차선"뿐 아니라 "주행경로 이탈 정지물체" 전반을
  커버해야 함. 상세는 FINDINGS.md 37차 항목 참고.
- **패치 방향 결정(37차, 이번 체크포인트)**: 주(main) = `track_scc`
  폴백 트랙에 별도 플래그를 달아 `LeadBlend`(특히 `CUTOUT_DPATH_THRESH`)
  를 계속 타도록 분리. 보조 = `get_lead()` 진입 시점에 관대한 yRel
  1차 필터(예: 3.0m 이상이면 후보 제외)로 극단 케이스 조기 차단.
  근거: `dPath`는 이미 `Track.d_path()`에서 `md.laneLines` 기반 차선
  중심 대비 위치로 계산됨(곡률/차선폭 보정 포함, 단순 yRel 아님) —
  `track_scc`도 `Track` 인스턴스라 이 계산을 동일하게 받음. 단순 yRel
  임계값(1번안)만으론 `7ffb3e693c--10`(yRel -1.4~-1.5m, 값 자체가
  작음)을 못 거르지만 dPath 기반 판정은 커브 보정까지 포함하므로
  이 케이스까지 커버될 가능성이 높음.
- **cut-in/cut-out 영향 분석 완료(37차)**: 코드 확인 결과, **cut-out
  감지는 이미 오늘도 `track_scc` 유래 리드에 적용되고 있음** — radar가
  매 프레임 True→False로 바뀌는 순간(트랙 소실 시 raw가 vision-only로
  fallback되며 radar=False가 됨) `else` 분기로 빠져 `lead_blend.update()`
  가 호출되고, 이때 쓰이는 `self.prev`는 track_scc 프레임에서도 매번
  `radar=True` bypass 중에 계속 갱신돼 옴(line 670 부근
  `self.lead_blend.prev = dict(lead_one_raw)`). 즉 패치는 cut-out
  판정 자체를 새로 추가하는 게 아니라, **트랙이 살아있는 동안(status
  유지)의 "급접근 인지" 판정을 track_scc까지 확장**하는 것.
  - 실제 위험한 cut-in(빠르게 끼어들며 closing/TTC<2.5s)은 `_is_dangerous()`
    의 danger-passthrough 경로를 그대로 타서 **패치 후에도 즉시 반영**
    (반응속도 저하 없음).
  - 다만 위험하지 않은 완만한 cut-in(서서히 합류, closing 아님)은
    현재 radar=True bypass 때는 raw 즉시 반영이었지만, 패치 후엔
    `LEAD_BLEND_SAFE_DIST_TIME`(0.35s)로 스무딩됨 — **완만한 cut-in에서
    약 0.35s 지연이 새로 생기는 게 유일한 실질적 사이드이펙트**.
    안전성엔 문제 없으나 실차 검증 시 "느린 끼어들기 반응이 예전보다
    부드러워졌는지" 체크 포인트로 삼을 것.
  - cut-out 반응속도는 이미 오늘과 동일(로직 변경 없음), 회귀 위험
    낮음.
  1. `get_lead()`의 `track_scc` 채택 조건에 최소 차로내 게이트
     (제안: `abs(track_scc.yRel) < 1.75~2.0m`) 추가 — 비전 대응 리드가
     없을 때만 쓰는 폴백이라 너무 엄격하면 안 됨, 튜닝 필요. 4건 중
     3건(-5.5~-6.0/-10.5~-3.0/1.0~2.0m)은 이 게이트로 걸러지지만
     `7ffb3e693c--10`(-1.4~-1.5m)은 값 자체가 작아 단순 yRel 게이트만
     으론 못 거를 수 있음 — dPath/커브 曲率 보정 병행 검토 필요.
  2. 대안/병행: `track_scc` 폴백 트랙은 `radar=True`를 그대로 두지
     말고 별도 플래그로 표시해 `LeadBlend`(특히 `CUTOUT_DPATH_THRESH`)를
     계속 타도록 분리.
  3. 위 1/2 방향 결정 후 패치 작성 → `git format-patch` →
     `C:\dev\patch\` 전달.
  4. 패치 적용 후 실차 검증(다시 옆차선/측면차량 오탐 재현 시
     `leadTrackId`/`leadYRel`이 게이트에 걸려 무시됐는지 확인).

## 36차 (완료) — frac_rate 게이트 실차 acados 파이프라인 첫 검증 성공
- 상세는 FINDINGS.md/LAST_ANALYZED.md/PARAMS_REGISTRY.md 36차 참고 (WIP
  중복 방지를 위해 요약만): 카메라인식/정치차량 로그로 33차 문턱
  재설계(-2.2/-5.0)가 실제 acados MPC 파이프라인에서 정상 활성화됨을
  최초 확인, PARAMS_REGISTRY 4개 상수 VALIDATED 상향.
- **다음 세션에서 이어갈 것**:
  1. frac_rate 활성화~aEgo 반응 사이 지연(관찰상 약 2초) 순수 측정 —
     leadStatus 끊김 없이 안정적으로 유지되는 원거리 접근 사례로
     재현 필요(현재 로그는 leadStatus 재획득 지연이 섞여 있어 순수
     게이트 지연으로 단정 못함).
  2. 34차(c3-ms-dev vs c3-ms-test 클램프+중앙값 필터 제거 A/B 실차
     비교)로 복귀 — 아래 34차 섹션 참고, 아직 미착수.

## 35차 계속 2 (완료) — "Clip 선택" 버튼 무반응 원인: 캐시 버스터 미갱신
- **증상**: patch 0003까지 두 브랜치 적용·push 완료 후 사용자가
  실기기에서 "Clip 선택" 버튼을 눌러도 체크박스가 선택 안 됨
  (스크린샷 확인).
- **원인/조치**: `index.html`의 `logs.js?v=3` 캐시 버스터를 이번
  세션 3개 patch가 전부 `logs.js`를 바꿨음에도 안 올려서 브라우저가
  구버전 JS를 계속 캐시 사용 중이었음 — `?v=4`로 갱신(커밋
  `baab116`). 상세는 FINDINGS.md 35차 계속 2 항목 참고.
- **전달**: `0004-carrotweb-logsjs-cache-buster-v4.patch`를
  `/mnt/user-data/outputs/`에 생성, `git am` 검증(temp branch) 통과.
- ~~사용자가 두 브랜치 모두에 patch 0004 적용~~ → **완료**.
  `c3-ms-dev`(`f9241db..4fe22cd`), `c3-ms-test`(`331d49a..4d2f6a5`)
  둘 다 `git am` 충돌 없이 적용 + push 확인.
- ~~실기기 강제 새로고침 후 "Clip 선택" 버튼이 clip 파일 체크박스만
  선택/해제 토글하는지 확인~~ → **완료(정상 동작 확인)**.
- ~~clip 실제 길이(20초대) 확인~~ → **완료(20초대 정상 확인)**.
- FINDINGS.md 35차/35차 계속 2 항목에 실차 검증 완료로 갱신함.
- **향후 원칙(중요)**: `logs.js`(또는 버전 쿼리 붙은 다른 정적
  자산)를 건드리는 patch는 항상 `index.html`의 해당 `?v=N`도 같이
  올릴 것 — 잊으면 push/적용은 성공해도 브라우저 캐시 때문에
  실제로 반영 안 되는 오탐 발생.

## 35차 계속 (완료, 위 "35차 계속 2"로 이어짐) — carrotweb Clip 버튼 의도 정정 (필터 아님, 선택 전용)
- **정정 배경**: 35차 최초 구현("Clip만" 버튼 = 목록 필터링, clip 아닌
  항목 숨김)을 사용자가 실제 의도와 다르다고 정정 — "목록은 전부
  표시하고, clip 파일들의 체크박스만 선택되게" 해달라는 것이었음.
- **조치**: `screenrecordClipOnly` 필터 상태/`getVisibleScreenrecordVideos()`
  제거, `screenrecordSelectClipsOnly()`(clip 파일 체크박스만 토글
  선택/해제)로 교체. 버튼 라벨 "Clip만"->"Clip 선택". 상세는
  FINDINGS.md 35차 항목(수정됨 표시) 참고. 커밋 `f6a22b8`(local,
  base `ec5767f`, 즉 최초 carrotweb 커밋 위에 얹은 델타).
- **전달**: `0003-carrotweb-logs-clip-select-not-filter.patch`를
  `/mnt/user-data/outputs/`에 생성, `git am` 검증(temp branch) +
  `node --check` 통과.
- **다음 세션(또는 다음 메시지)에서 이어갈 것 — 최우선**:
  1. ~~사용자가 두 브랜치 모두에 patch 0003 적용~~ → **완료**.
     `c3-ms-dev`(`dfa2f4f..f9241db`), `c3-ms-test`(`e9000b3..331d49a`)
     둘 다 `git am` 충돌 없이 적용 + push 확인.
  2. **[남음]** 실차 검증: `_clip.mp4` 실제 길이 20초대 확인, carrotweb
     "Clip 선택" 버튼 클릭 시 목록은 그대로 다 보이고 clip 파일
     체크박스만 선택되는지 확인(다시 누르면 해제).
  3. 검증 통과 후 → 34차(c3-ms-dev vs c3-ms-test A/B 실차 비교) 복귀.

## 35차 (완료, 위 "35차 계속"으로 정정됨) — screenrecord clip 20초 축소 + carrotweb Clip 필터
- **저장 시각(당시)**: 2026-08-22 — screenrecord clip 60s->20s +
  carrotweb "Clip만" 필터 버튼, 두 브랜치(c3-ms-dev/c3-ms-test) 적용·push
  완료, 실차 검증만 남음

## 35차 (패치 완료, 적용 대기) — screenrecord clip 20초 축소 + carrotweb Clip 필터
- **요청**: (1) 정지 clip 길이 60초 -> 20초(용량 절감), (2) carrotweb
  로그탭 화면녹화 목록에서 clip 파일만 필터링하는 버튼. 두 브랜치
  (`c3-ms-dev`, `c3-ms-test`) 모두 반영 + push까지 요청.
- **구현**: 커밋 2개, base `8114a46`(c3-ms-dev HEAD) —
  `c1e79ed`(clip 60->20s), `cebfa87`(carrotweb Clip만 필터 버튼).
  상세는 FINDINGS.md 35차 항목 참고. `git am` 검증(temp branch) +
  `node --check` 통과.
- **전달**: `0001-screenrecorder-clip-60-20.patch`,
  `0002-carrotweb-logs-Clip-clip.patch`를 `/mnt/user-data/outputs/`에
  생성, `git am` 안내 함께 전달함(아래 참고).
- **다음 세션(또는 다음 메시지)에서 이어갈 것 — 최우선**:
  1. ~~사용자가 `c3-ms-dev` 로컬에 두 patch `git am` 적용 + push~~ →
     **완료**. `git am` 컨텍스트 충돌 없이 그대로 적용, `git push
     origin c3-ms-dev` 확인(`8114a46..dfa2f4f`).
  2. ~~`c3-ms-test`에도 같은 두 patch 적용 + push~~ → **완료**.
     예상대로 `long_mpc.py` 무관이라 충돌 없이 적용, `git push origin
     c3-ms-test` 확인(`725d19f..e9000b3`).
  3. **[남음]** 실차 검증: 정지 버튼 눌러 생성된 `_clip.mp4` 실제 길이가
     20초대인지 확인, carrotweb 로그탭 화면녹화 탭에서 "Clip만"
     버튼 토글 시 clip 파일만 남는지 확인.
  4. 검증 통과 후 → 34차(c3-ms-dev vs c3-ms-test vision closing-rate
     A/B 실차 비교, 아래 34차 섹션) 원래 과제로 복귀.

## 34차 (완료, **이후 37차 계속3에서 취소됨 — c3-ms-test 브랜치 삭제**) — c3-ms-test 브랜치: 클램프+중앙값 필터 제거 A/B 실차 비교용
- **배경**: 33차까지 문턱 재설계(-2.2/-5.0)는 완료·push됨(`c3-ms-dev` HEAD
  `8114a46`). 이번 34차에서 사용자가 "지연도 문제될 듯하니 클램프+중앙값
  필터 자체를 뺀 브랜치를 만들어 두 브랜치(c3-ms-dev vs c3-ms-test)를
  실차로 비교해보자"고 요청.
- **주의**: 이건 28차에서 확정한 결론("클램프+중앙값이 지연을 유발해서
  frac_rate가 안 터진 게 아니라, raw 신호 자체가 옛 문턱 -5.5보다 낮았다")
  과는 별개의 질문 — 문턱 재설계(-2.2/-5.0) 이후에도 클램프(0프레임)+중앙값
  (최대 0.1s) 필터 자체의 잔여 지연이 반응 속도에 영향을 주는지는 아직
  실측된 적 없음. 사용자는 이 잔여 지연 자체가 궁금해서 A/B 실차 비교를
  요청한 것으로, 28차 결론을 뒤집는 게 아니라 별도 축(지연 vs 문턱)의
  검증임에 유의.
- **변경 내용**: `long_mpc.py`의 클램프(`VISION_CLOSING_RATE_MAX_PLAUSIBLE`
  =30.0)+3프레임 중앙값(`VISION_CLOSING_RATE_MEDIAN_WINDOW`=3) 단계를
  건너뛰고, `raw_rate`를 TAU=1.0s 저역통과 필터에 직접 투입하도록 변경.
  상수/deque 선언 자체는 diff 최소화 위해 남겨두고 미사용 처리(주석 추가).
  `VISION_CLOSING_RATE_GATE_CAUTION/DANGER`(-2.2/-5.0) 문턱값은 그대로
  유지 — 이번 실험은 필터 지연만의 영향을 분리해서 보기 위함.
- **리스크(사용자에게 사전 고지함)**: 25차에서 클램프+중앙값을 도입한
  원래 이유가 곡선 dRel 스냅 노이즈(91.7% 발생 패턴, 필터링 후
  -12~-25m/s 관측) 억제였음 — 이걸 빼면 TAU=1.0s 저역통과만으론 완전히
  못 걸러 곡선 구간에서 frac_rate가 노이즈성으로 튈(DANGER급 순간 개입)
  가능성 있음. **c3-ms-test 실차 검증 시 특히 곡선 구간 반응을 주의
  관찰**해야 함.
- **베이스/커밋**: `c3-ms-dev` HEAD `8114a46` 위에 단일 커밋(컨테이너
  로컬 `8c6e039`, 사용자 로컬 커밋 해시는 `git am` 적용 시 별도 생성됨)로
  `c3-ms-test` 브랜치 생성. patch(`0001-long_mpc-A-B-vision-closing-rate-c3-ms-dev.patch`)
  전달 → 사용자가 `git am` 컨텍스트 일치로 성공 → `git push origin
  c3-ms-test` 완료 확인(원격에 `c3-ms-test` 신규 브랜치 존재).
- **GH_TOKEN 스코프 확인**: 현재 세션 GH_TOKEN은 `ryu-devnotes` 리포
  1개(Contents R/W)로 한정 — `ryu` 리포는 스코프 밖이라 Claude가 직접
  push 불가, 항상 patch + 사용자 수동 push 절차(기존 지침과 일치, 예외
  아님).
- **[취소, 37차 계속3]** 사용자가 `c3-ms-test` 브랜치를 불필요하다고
  판단해 로컬(`git branch -D`) + 원격(`git push origin --delete
  c3-ms-test`) 삭제 확인. 아래 "다음 세션에서 이어갈 것" 항목은
  더 이상 유효하지 않음 — A/B 실차 비교 자체를 하지 않기로 함(원본
  기록 보존, 취소 사유는 사용자 판단으로 상세 불명).
- **다음 세션에서 이어갈 것 (최우선)** — ~~아래는 취소된 34차 과제
  원본, 참고용으로만 보존~~:
  1. 사용자가 `c3-ms-dev`와 `c3-ms-test` 두 브랜치로 각각 실차 주행,
     동일/유사 구간(가능하면 같은 날 왕복 등) 로그 확보.
  2. 두 로그를 `extract_log.py`로 각각 CSV 추출 후, 원거리(dRel 85~120m)
     접근 상황에서 a_target 개입 시점 차이(더 일찍 반응하는지) 비교.
  3. `c3-ms-test`에서 곡선 구간 frac_rate 오탐(노이즈성 DANGER 스파이크)
     발생 여부 확인 — 발생 시 34차 "리스크" 항목 확정, 필터 제거는
     되돌리고 다른 지연 단축 방안(TAU 단축 등) 검토로 전환.
  4. 오탐 없고 반응 속도 개선 확인되면 `c3-ms-test`를 `c3-ms-dev`에
     반영할지(또는 필터 자체를 경량화할지) 사용자와 논의.


- 저장 시각: 2026-08-21 (33차 — 32차에서 사용자 확인 대기 중이던
  두 갈래 중 (a) 문턱 재설계 패치 진행으로 결정, 패치 완성·전달함.
  `git am` 컨텍스트 불일치로 실패해 PowerShell 정규식 치환으로
  수동 반영, 사용자 로컬(`c:\dev\ryu`, c3-ms-dev)에 커밋 `8114a46`
  완료 확인(`Select-String`으로 259/260/716/717줄 반영 확인).
  **아직 origin push 전, 실차 실측 검증 전.** (b) "지속적 곡선
  dRel-vRel 불일치 드리프트" 결함은 32차 권고대로 이번 세션엔
  다루지 않고 별도 과제로 유지.)

## 33차 (완료) — VISION_CLOSING_RATE_GATE 문턱 재설계 패치 완성·전달
- **컨테이너 제약 확인**: 이번 세션 컨테이너는 origin에서 새로
  clone했기 때문에 26차 로컬 커밋(`5cc0900`, 클램프+중앙값 필터 +
  구문턱 -5.5/-10.0 게이트 신설)이 origin에 없어 존재하지 않음 —
  origin `long_mpc.py`에는 여전히 TTC 크로스체크(`ttc_dRel`)까지만
  있고 클램프/중앙값/절대값 게이트 블록 자체가 없음을 grep으로
  재확인(WIP.md 앞 세션 기록과 일치).
- **재구성 방법**: origin `a4b5550` 위에 (1) 26차 patch를
  `devnotes/WIP.md`/`sim_frac_rate.py` 기록 그대로 역설계 재현한
  커밋(로컬 `6864abd`, 구문턱 -5.5/-10.0), (2) 그 위에 30/31차
  확정 문턱(-2.2/-5.0)으로 바꾸는 델타 커밋(로컬 `d4b2fc5`) 순서로
  2단계 커밋. **사용자에게 전달하는 patch 파일은 (2)번 델타 커밋
  하나만** — 사용자 로컬 `C:\dev\ryu`엔 이미 (1)에 해당하는 진짜
  `5cc0900`이 `git am` 적용되어 있다는 전제(29차 확인) 이므로 그
  위에 문턱 변경분만 얹으면 됨.
- **적용 시 주의 (컨텍스트 매칭 리스크)**: 델타 patch는 이번 세션이
  *재구성한* 26차 커밋 텍스트를 기준으로 diff context를 만든 것이라,
  사용자 로컬의 진짜 `5cc0900` 코멘트/공백이 한 글자라도 다르면
  `git am`이 컨텍스트 불일치로 실패할 수 있음. **패치 실패 시엔
  아래 두 상수 값만 직접 수동으로 바꾸는 게 더 안전**:
  ```python
  VISION_CLOSING_RATE_GATE_CAUTION = -2.2   # 기존 -5.5
  VISION_CLOSING_RATE_GATE_DANGER  = -5.0   # 기존 -10.0
  ```
  (파일: `selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`,
  `VISION_CLOSING_RATE_MEDIAN_WINDOW` 상수 선언 바로 아래 블록)
- **전달**: `0001-long_mpc-VISION_CLOSING_RATE_GATE-5.5-10.0-2.2-5.0.patch`
  를 `/mnt/user-data/outputs/`에 생성, `git am` 안내 + 수동 대안
  함께 전달함. **실제로는 `git am` 컨텍스트 불일치로 실패**(예상된
  리스크, 위 "적용 시 주의" 참고) → PowerShell 정규식 치환(`-replace`)
  으로 두 상수값만 안전하게 변경 → 사용자가 `Select-String`으로
  259/260줄(선언부) + 716/717줄(사용처) 반영 확인 → 커밋 완료
  (로컬 `8114a46`, `c3-ms-dev`). **origin push는 아직 사용자가
  안 함 — 다음 메시지/세션에서 `git push` 확인 필요.**
- **검증 상태**: `py_compile` 통과. 실측 검증(30/31/32차 시뮬레이션
  기반)은 이미 충분(FINDINGS.md 31차) — 단 이 패치가 실제
  acados MPC 파이프라인에 통합된 후의 실차 반응(a_target 프로파일)
  검증은 아직 미실시, 다음 세션 최우선 과제.

## 다음 세션(또는 다음 메시지)에서 이어갈 것 (33차 기준, 최우선)
0. ~~origin push 확인~~ → **완료**. `a4b5550..8114a46` push 확인,
   fetch로 diff 최종 상태(GATE_CAUTION=-2.2/DANGER=-5.0) 재확인함.
1. 사용자가 실차 드라이브로 신규 로그 확보.
2. 신규 로그로 문턱 재설계(-2.2/-5.0)가 원거리 반응 지연을 실제
   MPC 출력(a_target)에서 개선하는지 실측 검증 — 지금까지는 전부
   `sim_frac_rate.py` 시뮬레이션 기반, 실제 acados 파이프라인
   integration 검증은 처음.
3. 검증 통과 후 → 32차에서 미룬 (b) "지속적 곡선 dRel-vRel 불일치
   드리프트"(`203f99d429--8` 사례) 원인 분석 착수: 대시캠 프레임
   대조(seg8 t=6579.9~6582.4) → consistency-check 설계(N프레임
   dRel 변화량 vs vRel 적분값 비교) → 별도 패치.
4. 그 외 대기 중: 옆차선 차량 락온 순간 급감속(25차부터 대기).

## 32차 (완료, 위 33차로 이어짐) — 곡선 오탐 검증 중 문턱과
무관한 새 결함(지속적 dRel-vRel 드리프트 불일치) 발견
(참고용 원본 CSV 경로 등은 컨테이너 로컬이라 이미 소실 — 재검증 필요
시 `곡선_로그.zip`/`카메라_인식_추가.zip` 등 재업로드 필요, 상세는
FINDINGS.md 32차 참고)

## 31차 (완료) — 6개 세그 추가 검증으로 문턱 재설계 근거 대폭 보강

## 30차 (완료) — 28차 min_filt_rate가 글리치였음을 발견, 문턱
재설계 근거 정정, 곡선 오탐 1차 검증

## 28차 (완료, 아래는 원본 기록 보존) — 세그7/세그12 실측으로 문턱
과보수 확정, 재설계 필요성 격상
1. `VISION_CLOSING_RATE_GATE_CAUTION` 문턱 재설계: 현재 -5.5m/s는
   실측 두 사례 피크(-3.196/-3.504m/s)보다 구조적으로 높아 전혀
   발동 못함이 확정됨. 단순 -3.5~-4.0 하향으론 세그7(-3.196)을
   여전히 놓칠 수 있음 — CAUTION을 -2.5~-3.0대로 더 낮추거나
   CAUTION~DANGER 구간 폭 자체를 좁히는 재설계 필요 (FINDINGS.md
   28차 항목 결론 참고).
2. 재설계한 문턱값으로 `sim_frac_rate.py`를 세그7/세그12에 재실행해
   실제로 frac_rate>0이 발동하는지, 발동 시점이 레이더 락온보다
   충분히 이른지 사전 검증 (패치 작성 전 시뮬레이션 단계에서 먼저
   확인 — 실차 검증 전 비용 절감).
3. 검증 통과 시 `long_mpc.py`의 `VISION_CLOSING_RATE_GATE_CAUTION`
   상수만 패치(다른 로직 변경 없음) → `git format-patch` →
   `C:\dev\patch\` 전달. 단, 26차 patch(`5cc0900`, 클램프+중앙값+
   frac_rate 게이트 자체)가 아직 `c3-ms-dev`에 미반영 상태이므로,
   **이번 문턱 재설계 패치는 26차 patch가 이미 적용된 로컬
   (`C:\dev\ryu`)에 순차 적용됨을 전제**로 작성할 것(즉 26차 patch
   재전달 여부를 사용자에게 먼저 확인 — 26차 patch를 이미
   `git am` 했는지 모름).
4. 완료 후 26차 WIP 원래 다음 과제(아래 26차 섹션 "다음 세션에서
   이어갈 것")로 복귀.

## 27차 (완료, 아래는 원본 기록 보존) — 세그7/세그12 no-decel 실측으로 frac_rate 문턱(-5.5m/s) 재검토

a4b5550 HEAD(26차 patch 적용 전) 시점 zip 2개
(`20260821_112042_...--7.zip`/`20260821_112542_...--12.zip`,
route `866476e5c3`)로 "카메라 인식했는데 감속 안 함" 실사례를
frame 단위 재확인 → 세그7(raw vRel -1.66→-5.66, 락온 직전 막판에야
CAUTION 근접)/세그12(raw vRel 최대 -2.82, 문턱 근처도 못 감) 둘 다
확인. 이어서 "이 두 사례에 26차 frac_rate 게이트를 적용했으면
감속이 됐을까"를 검토한 결과, **필터(클램프+중앙값+TAU=1.0s
저역통과) 특성상 세그7은 락온 시점까지 필터 출력이 -5.5를 못
넘었을 가능성이 높고 세그12는 raw 자체가 문턱에 한참 못 미쳐
게이트가 사실상 관여 못 했을 것**으로 추정 — FINDINGS.md
`[NEEDS_VALIDATION] frac_rate 게이트 문턱 과보수적 가능성` 항목으로
기록 완료. **코드 변경 없음(분석/추론만), 정확한 프레임 단위
재검증은 미수행**(이번 세션 컨테이너에 26차 로컬 커밋 `5cc0900`과
추출 CSV가 남아있지 않았음 — origin에도 미push 상태라 재확보
불가, zip 재업로드 또는 패치 적용된 `long_mpc.py` 재확보 필요).

## (27차 당시 다음 과제 — 28차에서 모두 완료, 결과는 위 28차 섹션 참고)
1. ~~zip 재업로드 후 프레임 단위 재현~~ → 완료(28차, `sim_frac_rate.py`).
2. ~~-5.5 문턱을 -3.5~-4.0대로 하향 검토~~ → 완료했으나 결론이
   갱신됨: 실측 피크가 -3.2~-3.5라 -3.5~-4.0로는 부족, 더 낮은
   -2.5~-3.0대 또는 구간 폭 재설계 필요로 결론 변경(28차 최우선
   과제 1번 참고).
3. → 28차 최우선 과제로 이어짐(위 참고).

## 26차 — 곡선 노이즈 필터(1) → closing-rate 게이트(2) 순서로 구현 완료

25차 종료 시점에 사용자가 방향을 결정: **곡선 노이즈 필터 먼저 →
2번(closing-rate 게이트) 순서로 진행**. 이전 세션(다른 계정)에서
`long_mpc.py`에 두 기능의 상수/설계 주석 블록만 추가된 상태(로직
미구현)로 파일이 남아 있었고, 이번 26차에서 실제 구현을 완료:

**구현 내용** (`c3-ms-dev` 로컬 커밋 `5cc0900`, `a4b5550` 위에 적층,
**아직 origin에 미push** — ryu는 항상 수동 patch 절차):
1. **곡선 노이즈 클램프+중앙값 필터**: `raw_rate`를
   `VISION_CLOSING_RATE_MAX_PLAUSIBLE=30.0 m/s`로 클램프(접근 방향만) 후
   `collections.deque(maxlen=VISION_CLOSING_RATE_MEDIAN_WINDOW=3)`에
   누적, 중앙값을 기존 저역통과 필터(TAU=1.0s) 입력으로 사용. 스냅-복귀
   패턴은 3프레임 다수결에 밀려 걸러지고 지속 접근은 그대로 반영됨.
   윈도우는 기존 3곳의 리셋 지점(radar lock-on 즉시, grace 초과, ramp
   전체 리셋)에서 동일하게 `.clear()`.
2. **Vision-only closing-rate 절대값 게이트**: `_vision_dRel_rate`(위
   필터 적용된 값)를 `VISION_CLOSING_RATE_GATE_CAUTION=-5.5m/s` ~
   `GATE_DANGER=-10.0m/s` 구간에서 `frac_rate`로 정규화, 기존
   `frac_time`/`frac_ttc`와 `max()`로 결합(순수 floor, 완화 방향 없음).
   원거리에서 TTC 문턱이 구조적으로 안 넘어가는 한계(22~25차 확정 근본원인
   a)를 rate 자체 게이트로 보완. 게이트도 vision-only + `_lead_acq_timer
   >= VISION_CLOSING_RATE_MIN_TIME` 조건은 기존 TTC 크로스체크와 동일하게
   적용.

**검증**: 합성 시나리오(정상 -5m/s 지속 접근 vs 15프레임째 8m 단일프레임
스냅)로 로직만 별도 스크립트 재현 — 기존(미적용) 방식은 스냅 프레임에서
필터값이 -10.68m/s로 튐(허위 DANGER), 신규(클램프+중앙값) 방식은 같은
프레임에서 -2.68m/s로 주변 추세와 자연스럽게 이어짐(스냅 억제 확인).
단, 이는 로직 단위 합성검증이며 **실제 acados MPC 파이프라인/실차
로그로는 아직 미검증**.

**전달**: `0001-long_mpc-dRel-vision-closing-rate-frac_rate.patch`를
`/mnt/user-data/outputs/`에 생성, `git am` 안내와 함께 전달함(아래 참고).

## 다음 세션(또는 다음 메시지)에서 이어갈 것
1. 사용자가 `git am`으로 패치를 로컬(`c:\dev\ryu`)에 적용 후 실차 드라이브.
2. 신규 로그로 **원거리 반응 지연 개선 여부** 검증 (25차에서 확인된
   "물리적으로 TTC 문턱 못 넘어 개입 늦음" 패턴이 완화됐는지), 및 곡선
   구간(vturn) 구간에서 노이즈성 DANGER 오탐이 사라졌는지 확인.
3. "반응 개시 지연" 정량 지표 함수 toolkit에 추가 검토 (25차에서 식별된
   미해결 gap — TTC caution 문턱 통과 시점 대비 실제 a_target 하강 개시
   시점 지연을 측정하는 함수 없음).
4. 검증 통과 후 → 2번(옆차선 차량 락온 순간 급감속, 25차에서 대기 중이던
   항목) 착수.

## 이전 (25차) — 참고용, 위 26차로 방향 결정 완료


## 25차 계속 — 영상 8개 리뷰 완료, 다음 액션 사용자 결정 대기

사용자가 화면녹화 영상 8개(`260821_110103`~`260821_115950`, 각
약 60초, 파일명 시각은 영상 시작 시점의 표시 시각으로 추정)를
업로드. 원본 rlog/zip은 이번 세션엔 없어(이전 세션 산출물인
`evidence/route_summaries_260821/*.json` 요약만 참조 가능),
**영상 자체의 CarrotWeb 오버레이(1.Accel 그래프: Y=a_ego,
G=a_target, O=a_out + 리드박스 dRel/리드속도 표시)를 직접 판독**해
분석 진행.

**라우트 매칭** (FINDINGS.md 24차 route5~8 시간대 기록 기준):
- route5(`83e6b133f5`, 10:53~11:12, 고속도로) ← 110103/110242/
  110525/110821 4개 클립
- route6(`866476e5c3`, 11:13~11:32, 고속도로) ← 112042/112534/
  112816 3개 클립
- route8(`203f99d429`, 11:53~12:12, 고속도로+약간감속) ← 115950
  1개 클립
- (route7 11:33~11:52 구간 클립 없음)

**영상 판독 결과**: 8개 클립 마지막 15~22초 구간 다수 프레임 확인.
관찰된 패턴은 두 갈래로 갈림 —
1. 원거리(60~105m) 선행차 접근 시 a_target이 한동안 0 근처~완만한
   음수만 유지되다가(예: dRel 97m/리드속도 97km/h, closing
   ~5m/s, TTC 추정 18s+ 구간에서 a_target -0.06~-0.18 정도) 이후
   서서히 큰 감속으로 전환 — **22~24차에서 이미 확정한 "TTC 캐션
   문턱(6.0s)이 원거리에서 물리적으로 안 넘어가는" 구조와 정성적으로
   합치**. 사용자가 "감속을 안 한다"고 느끼는 지점은 실제로는
   "물리적으로 TTC가 아직 캐션 문턱을 안 넘어 개입이 늦게 시작"하는
   현상으로 보임(105m/2818차 24차 프레임 검증과 같은 메커니즘).
2. 근접(30~50m대) 상황에선 a_target이 뚜렷하게 -1.3~-1.5 급으로
   확실히 반응(예: 110242 클립 마지막, SUV 근접 시 -1.4대 감속 확인)
   — 즉 "아예 반응 안 함"은 아니고, **반응 시작 시점이 늦다**는
   쪽에 더 가까운 증거.

**24차 로그 통계와의 간극**: route5/6/8 3개 다 harsh_brake/
turn_speed_violation 등 "이산적 급제동/위반" 지표는 0건(클린)으로
집계됐었음 — 이는 **급브레이크가 없었다는 것만 확인할 뿐, "더
일찍 감속했어야 하는데 늦게 반응했다"는 이번 체감 문제를 애초에
탐지하도록 설계된 지표가 아님**. 즉 기존 배치분석 도구가 이번
증상을 못 잡아낸 게 아니라 애초에 이 증상용 지표가 없었던 것 —
**신규 발견**: "반응 개시 지연"을 정량화할 지표(예: TTC가 caution
문턱을 넘은 시점 대비 실제 a_target 하강 개시 시점의 지연(lag)을
직접 측정하는 함수)가 toolkit에 없음. 다음 세션 후보로 추가.

**결론 및 다음 액션**: 22~23차에 이미 설계됐던 대안 3개(1.TTC
문턱 완화 6.0→10~12s, 2.closing-rate 절대값 게이트 -5.5~-6.0m/s,
4.`_vision_dRel_rate`를 `v_lead`에 직접 반영) 중 어느 것을 적용할지
**사용자 결정 필요** — 이번 25차 영상 증거가 "원거리 반응 지연"
패턴을 재확인해줬으므로 착수 조건은 충분. 단 23차 결론대로 곡선
노이즈 취약성 때문에 **곡선 노이즈 필터링(`curve_lead_dRel_jump_
consistency`/`curve_noise_summary_refined`, devnotes에 구현은
있으나 `ryu` 코드 미반영) 선행 여부도 함께 결정 필요**.

**이미 파악된 근본원인(22~23차, 재확인 완료, 코드 미변경)**:
a) `LEAD_ACQ_TTC_CAUTION=6.0s` 문턱이 원거리(dRel≈85~120m)에서
   물리적으로 도달 불가 — 카메라가 접근율을 정확히 감지해도
   거리가 멀면 TTC=dRel/rate 계산값이 문턱을 못 넘어 무시됨.
b) 레이더 락온 순간 vRel 불연속 점프(재현 2건 모두 -8.0~-8.4m/s
   로 유사값 점프) — 단안 카메라 깊이추정이 곡선/원거리에서
   낙관적으로 보고.

2. **[대기 중] 옆차선 차량 락온 순간 급감속** — 아직 상세 논의
   전, 사용자가 "그 외 몇 개 더 있지만 1번부터"라고 해서 순서상
   대기. 1번(위) 방향 결정 및 착수 완료 후 진행 예정.

## 다음 세션(또는 다음 메시지)에서 이어갈 것
1. 사용자가 1)TTC 문턱 완화 / 2)closing-rate 게이트 / 4)vision_
   dRel_rate 직접반영 / 곡선노이즈필터 선행 중 방향을 정하면 →
   패치 설계 → 구현 → `git format-patch` → `C:\dev\patch\` 전달 →
   `git am` 안내.
2. "반응 개시 지연" 정량 지표 함수 toolkit에 추가 검토(위 참고).
3. 방향 결정/패치 완료 후 2번(옆차선 락온 급감속) 착수.

## 다음 세션 우선 과제 (25차와 별개, 참고용, 순서 밀림)
1. 고속도로 급접근(harsh) 케이스 실측 표본 확보 — 24차까지 확보된
   b403d52 검증은 전부 "온건한 접근" 케이스뿐, 급접근 시나리오는
   미확보. (이번 25차의 영상 제보가 바로 이 급접근 표본이 될 가능성
   높음.)
2. route3(`dda0d533ce`)의 `vision_radar_crossover
   count_highway_est=0`이 route_summary.py 버그(route4에서 발견+
   수정) 영향인지 재확인(낮은 우선순위).
3. `source_pair_flicker` 관련 문서에서 경쟁 소스를 5종에서 최소
   7종(+bump/gas)으로 반영 필요.

## 다음 세션 시작 시
이 WIP.md에 "25차 착수" 섹션이 있으면 무조건 그 지점(영상 업로드
대기)부터 이어감. 사용자가 아직 영상을 안 올렸다면 다시 요청.
