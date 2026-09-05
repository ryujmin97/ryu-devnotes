# toolkit/ CHANGELOG

새 도구 추가/기존 도구 함수 추가·변경 시 날짜 + 한 줄 요약을 여기에
남긴다. `README.md`도 같이 갱신할 것.

## 2026-09-05 (244차, 체크포인트)
- `analyze_apex_identity_244.py`: 신규 -- `routeApexIdx` flicker의
  Position-Identity(CASE A) vs 실제 후보전환(CASE B) vs 거리이상(CASE C)
  판정. seg12-16(device build 232차, gate 없음)으로 실측: 전체 idx
  변화 286건 중 CASE_A 28건(9.8%)/CASE_B 258건(90.2%) -- position-identity
  가설은 소수 현상으로 확인. candidate 재식별(list 내부 순위교체)까지
  적용해도 CASE_B/미분류 258건 중 104건(40%)만 순위교체로 설명됨.
  터널 구간(t=2200~2230) 심층 확인 결과 road_limit_speed(100kph)
  바로 아래(79~99.8kph)의 다수 미약 후보가 600m 전역에 흩어져
  노이즈로 산발 승격/탈락하는 패턴 확인(FINDINGS.md 244차 CRITICAL).
  이 노이즈는 0.70 gate에서는 거의 전부 걸러지나(vEgo~100kph 기준
  0.70 threshold≈71kph) 현재 라이브 0.90 gate(threshold≈92kph)에서는
  일부(79~92kph대) 통과 -- 242차 0.70->0.90 변경이 이 터널 flicker를
  재유발할 가능성 신규 발견, 실차검증 우선순위에 반영 필요.

## 2026-09-05 (241차)
- `scan_route_vturn_handoff_ratio.py`: `--min-vego-kph` 옵션 추가(기본 0=미적용).
  confirmed&far-from-apex(n=14) 그룹을 vEgo 하한으로 추가 필터링해
  별도 리포트 -- 240차가 남긴 "표본 14건 분산 매우 큼(0.285~10.0)"
  문제를 저속(교차로/시내 회전 추정) 표본과 고속(하이웨이 커브 추정)
  표본으로 분리하기 위함. 기존 리포트(all/confirmed/far-from-apex)는
  옵션 미지정 시 출력 동일(하위호환).
- 신규 실행 없이 240차와 동일 11개 로그로 재실행, 재현성 확인(전체
  145/44/14 수치 240차와 완전 일치) 후 `--min-vego-kph 30` 추가 분석.
  상세는 FINDINGS.md 241차 참고.

## 2026-09-05 (240차)
- `scan_route_vturn_handoff_ratio.py`: 신규 -- route→vturn 실제 핸드오프
  시점의 apex_speed/vEgo 비율(handoff ratio) 실측 지시서(2026-09-05
  사용자 검증지시) 1~2번 대응. `build_speeds_distances()`(234/238차
  방식 재사용)로 naviPaths를 현재 곡률 로직으로 재구성(stage0, gate 없음)
  하고, 실측 src/vTurnSpeed로 route episode 종료 직후 vturn 전환 및
  2초 내 vTurnSpeed 수렴 여부를 확인해 "확인된 handoff"만 채택.
  **중요**: 이번 세션 업로드 11개 로그 전부가 223차(`ee1f5f8`, 2초 hold
  신설 커밋) **이전** 빌드(179차 후속2~221차, 전부 dirty=True)에서
  채록됨을 `check_device_build.py`로 확인 -- 지시서 4/5번(2초 hold 검증)은
  이 로그들로 원천적으로 검증 불가, 1~2번(ratio)도 severity gate가 아예
  없는 빌드의 "gate 없는 자연 전환" 데이터라 234~239차가 논의해온 것과는
  다른 성격의 표본. 상세는 FINDINGS.md 240차(CRITICAL) 참고.

## 2026-09-04 (234차 계속10)
- `sim_route_234_spatial_apex_continuity.py`: 계속9 정정(severity gate
  기준은 road_limit_speed가 아니라 v_ego_kph)을 정식 반영 -- stage1 계산을
  `gate_base * RATIO`에서 `v_ego_kph * RATIO`로 수정. stage0은 기존 배포
  코드 후보 필터(road_limit_speed 기준)로 무관하게 유지.
- route(seg12-16)를 `extract_log.py`(계속5에서 `nRoadLimitSpeed` 컬럼
  추가된 버전)로 재추출(`route_v3.csv`, 5999행, gate_source 전부
  `road_limit`) -- 정식 반영 스크립트로 재실행한 결과가 계속9의 즉석
  ad-hoc 스크립트 수치와 완전 일치(전체 172/60/16/3, 터널 81/0/0/0,
  IC gore 31/22/4/0, S커브 0/6/9/3) -- 재현성 확인.
- S커브 구간 잔여 stage3 점프 3건(t=2120.20/2120.46/2120.75) 위치 확인 --
  전부 continuity `held`->`new` 전환(miss_frames 초과로 lock 해제 후 원거리
  클러스터로 재진입) 패턴. 해당 구간 80/140/150m 대의 서로 다른 클러스터가
  수백ms 간격으로 번갈아 나타나는 것으로 보아, 단일 커브의 노이즈(터널
  패턴)라기보다 **여러 개의 실제 커브가 짧은 간격으로 연속된 진짜 S자
  도로 형상**일 가능성 -- dashcam 대조로 확정 필요(미완, 다음 세션).
  상세는 WIP.md 234차 계속10 참고.

## 2026-09-04 (234차 계속6)
- `sim_route_234_spatial_apex_continuity.py`: `gate_base_kph()` 신설,
  severity gate 기준을 vEgo 근사 대신 실측 `nRoadLimitSpeed`로 교체.
  재추출 CSV로 재실행 -- sanity check 24.4%->98.2% 대폭 개선(가정 a 해소).
  단, stage0/1 절대 점프 수 172/62건(vEgo 근사 97/60건과 다름), stage2/3
  추가 감소폭도 이전 추정(~95%)보다 작음(~23%, 62->55->48) -- **234차
  계속4/5의 ②③ 효과 크기 추정은 과대평가였을 가능성 있어 재검토 필요**.
  10/15/20m tolerance 재비교는 세 값 모두 matched=200, ambiguous 0%로
  동일 -- 10m 채택 결론은 유지. 잔여 48건 점프가 새 구간(t≈2108~2116)에
  집중 -- 다음 세션 dashcam 조사 대상. 상세는 README.md/WIP.md 234차
  계속6 참고.

## 2026-09-04 (234차 계속5)
- `extract_log.py`: `nRoadLimitSpeed` 컬럼 추가(순수 계측, 로직 변경 없음).
  234차 계속4의 가정(a)(road_limit_speed를 vEgo로 근사, 정합률 24.4%)를
  근본 해소하기 위한 사용자 지시 -- **재추출 필요, 기존 CSV엔 소급 안 됨**.
- `sim_route_234_spatial_apex_continuity.py`: `--continuity-tolerance <m>`
  옵션 추가 + ambiguous-match 계측(가정 (b) 검증용, 사용자 지시).
  동일 route(seg12-16)로 10/15/20m A/B/C 실행 -- 3건 모두 ambiguous 0%,
  flicker 억제(점프 3건)도 동일 -- 넓힐 이득 없어 보수적인 10m 잠정 채택
  권장(단일 route 결과, §26 확정 전 추가 검증 필요). 상세는 README.md/
  WIP.md 234차 계속5 참고.

## 2026-09-04 (234차 계속4)
- `sim_route_234_spatial_apex_continuity.py` 신규 -- ②spatial cluster/
  ③apex continuity 4단계(baseline/+30%gate/+spatial/+continuity) A/B.
  `analysis_helpers.recompute_route_curvature_speed()`로 naviPaths에서
  candidates 전체 배열 재구성(신규 rlog 판독 불필요). 터널 구간(t=2190~
  2225)은 +30%gate 단계에서 이미 전부 걸러짐(234차 계속2 결론과 일치).
  전체 로그 기준 프레임간 >40m 점프: 97(baseline)->60(+gate)->16(+spatial)
  ->3(+continuity). **미확정 가정 2건 있음(road_limit_speed 근사=vEgo,
  continuity 매칭 허용오차=15m 임의설정) -- 사용자 확인 전까지 결론 확정
  아님**, 상세는 README.md/WIP.md 234차 계속4 참고.

## 2026-09-04 (234차 계속3)
- `extract_log.py` FIELDNAMES/row 생성부에 `routeCandidateCount`/
  `routeCandidate0~2Idx/Dist/Speed` 10개 컬럼 추가. 204차에 capnp+
  carrot_serv.py에 이미 채워지고 있던 값인데 이 스크립트에서만 누락돼
  있었음(신규 rlog 판독 스크립트 불필요, 로직 변경 없음, 순수 계측 컬럼
  추가). 233차 실차 로그(route `0000039a--7b602ffb85`, seg12-16)로
  재추출 검증 -- 터널 flicker 구간(t≈2210~2215)에서 apex idx가 근거리
  (2~9)/원거리(44~50) 후보 사이를 매 프레임 오가는 것과 동시에
  `routeCandidateCount`가 0~2 사이로 계속 바뀌는 패턴을 실제로 확인,
  ②spatial cluster/③apex continuity 설계 검증에 필요한 데이터 확보.

## 2026-09-04 (229차)
- ChatGPT의 228차(5fa0254) 코드리뷰 지적사항(조기 return이 carrot_serv
  mirror를 건너뛰어 stale 값 남을 수 있음)을 Claude가 GitHub 실제 코드로
  직접 검증 후 사실로 확인, `carrot_man.py` 최소 수정(mode0/1·navi비활성
  두 조기 return 직전 mirror 2줄씩 추가) 패치 작성. `sim_route_229_stale_
  mirror_fix.py` 신규 추가 -- carrot_man/carrot_serv 상태를 별개 객체로
  분리 모델링해 버그 재현+수정검증+무회귀 10/10 PASS. 기존
  `sim_route_228_edge_cases_AJ.py` 44/44 PASS 재확인(무회귀). 독립 클론
  `git apply --check`+`git am`+`py_compile` 통과, byte-identical 확인.
  실차 검증은 미실시(현재 코드 경로상 즉시 영향 없는 예방적 수정으로 분석).
  상세는 FINDINGS.md/WIP.md "229차" 참고.

## 2026-09-04 (228차 계속)
- route_inert v2 실제 ryu 패치 적용 완료(`carrot_man.py`/`carrot_serv.py`,
  base `925a07a` -> `5fa0254`). `sim_route_228_edge_cases_AJ.py` 신규
  추가 -- 실제 patch diff의 3분기/클램프 조건을 그대로 재현해 사용자
  지정 A~J 10개 엣지케이스 개별 검증, 44/44 PASS. 독립 클론
  `git apply --check`+`git am`+`py_compile` 통과, push 후 `git ls-remote`로
  원격 반영 재확인. 실차 검증은 아직 미실시. 상세는 FINDINGS.md/WIP.md
  "228차 후속"/"228차 계속" 참고.

## 2026-09-04 (228차)
- `sim_route_228_v2.py` 신규 추가 -- 227차 클램프 적용 이후에도 남아있던
  결함 재발견: ACTIVE 추적 중 vEgo가 완전정지(0)까지 떨어지면 정차 원인
  해소 후에도 route_speed가 영구 고착되어 재가속 경로가 없음(자기참조적
  고착). carrot_man.py 단독 수정 가설은 carrot_serv.py의 227차 클램프가
  이를 다시 눌러버려 실패 -- 결함이 두 파일에 걸침을 확인. `route_inert`
  신규 상태(route_active와 동일 mirroring)를 도입해 ACTIVE 추적을
  "진짜 감속" vs "far-inert"로 구분하는 v2 설계로 12/12 PASS(고착 재현
  시나리오 즉시 회복 + curve 재추적 확인, 224차 원 시나리오 무회귀 확인).
  개발 과정에서 2차 버그(eff_dist<=0 구간까지 route_inert=True로 묶으면
  floor 노출로 신규 회귀)도 발견/수정. ryu 실제 코드 패치는 아직
  작성/적용 안 됨(§31 사용자 승인 대기). 상세는 FINDINGS.md/WIP.md
  228차 참고.
## 2026-09-04 (227차)
- `sim_route_227_ceiling_clamp_scope.py` 신규 추가 -- 226차의 ACTIVE 진입
  게이트 ceiling 분기(`out_speed=apex_speed`)와 `carrot_serv.py`의 225차 B
  vEgo 상한 클램프가 구분 없이 결합되어, vEgo가 apex_speed 미만인 동안
  route_speed/desired_speed가 매 프레임 vEgo에 고착 -> 가속 명령 원천
  봉쇄되는 회귀를 다중 프레임(최대 1200프레임) 시뮬레이션으로 재현/검증.
  5 CASE/7 체크 전부 PASS. PASS 확인 후 `carrot_serv.py`(`self.route_active`
  신규 저장 + L1143 클램프를 `route_active`일 때만 적용) +
  `carrot_man.py`(`carrot_navi_route()` 반환 직전 `self.carrot_serv.
  route_active` 동기화 1줄) 2파일 패치 적용, 독립 클론 `git apply --check`+
  `git am`+재컴파일 검증 완료. 상세는 FINDINGS.md/WIP.md "227차" 참고.

## 2026-09-04 (226차)
- `sim_route_226_active_gate_ceiling.py` 신규 추가 -- `carrot_navi_route()`
  ACTIVE 진입 게이트(`not route_active and v_ego_kph<=apex_speed` 분기,
  L896-902)가 `out_speed=None`을 반환하면 `carrot_serv.py::update_navi()`가
  route를 `speed_n_sources`에서 완전히 제외해 apex_speed ceiling 자체가
  사라지는 설계 갭(ChatGPT 225차 정적점검, vEgo=60/apex=80/vCruise=100 ->
  100까지 개방) 검증. GATE 분기만 OLD(None)/NEW(apex_speed) 대조,
  225차 A/B는 불변으로 고정. CASE1(핵심 재현)/CASE2(정상 감속 회귀
  없음)/CASE3(Stop&Go ceiling 유지)/CASE4(연속곡선 stale target
  없음)/CASE5(205/207차 회귀 -- apex flicker 스파이크 없음) 전체 PASS
  (24/24 체크). PASS 확인 후 `carrot_man.py` 1줄 패치(`out_speed=None`
  -> `out_speed=apex_speed`) 적용, 독립 클론 `git apply --check`+`git am`
  검증 완료. 상세는 FINDINGS.md/WIP.md "226차" 참고.

## 2026-09-03 (224차)
- `sim_route_224_ceiling_fix.py` 신규 추가 -- 223차 재설계 continuation
  분기의 "v_ego<=target일 때 out이 target으로 확정되어 route가 가속 목표
  처럼 동작"하는 버그(224차 실차로그: apex 40m 앞 80.8초 정지 중 out_speed가
  vEgo=0 대신 target(45~47kph) 유지) 수정 검증. OLD/NEW 대조 CASE1~5 +
  회귀 2건 전체 PASS. `carrot_man.py` 패치와 함께 전달.
- `sim_route_224_serv_floor_fix.py` 신규 추가 -- `carrot_serv.py::update_navi()`
  의 `autoCurveSpeedLowerLimit`(기본 30kph) 바닥값이 ceiling-fix된
  route_speed를 vEgo 위로 재상승시키는 2차 버그(같은 성격, 다른 파일) 발견
  및 수정 검증. `route_speed=min(v_ego_kph, max(route_speed, lower_limit))`
  로 상한 재적용, 바닥값의 기존 보호 목적은 vEgo 여유가 있을 때 그대로
  유지됨을 CASE3로 확인(회귀 없음). `carrot_serv.py` 패치와 함께 전달.

## 2026-09-03 (223차)
- `sim_route_223_state_machine_step5.py` 신규 추가 -- route 감속 전면 재설계
  (무상태 감속식 + route_active/route_release_time 2상태 상태기계)의 합성
  검증. CASE1/2/6/7/8/9/10/11/12/14 전부 PASS, 특히 222차가 발견한 정지→
  재출발 vEgo 초과 버그가 새 구조에서 재발 불가능함을 확인(CASE14). 독립
  재구현(실제 코드 import 아님) -- 실제 코드와의 diff 일치는 223차 계속4
  STEP6에서 별도 라인 단위 재검토. 상세는 FINDINGS.md/WIP.md "223차" 참고.

## 2026-09-03 (220차)
- `replay_route_apex_debounce_only_220.py` 신규 추가 -- "(A) apex_idx debounce만
  으로 199차 OLD 게이트가 충분한가"를 합성 모델이 아니라 route.csv의 raw
  routeApexIdx/Dist/Speed로 직접 재생해 검증(rolling-max(B)는 의도적 제외,
  (A) 단독 효과 분리). 추가로 같은 구간 vEgo/aEgo/brakePressed를 대조해
  "게이트 미작동 구간이 실제 급제동이 필요했던 구간인지"까지 함께 판정.
  x18seg CSV(commit 4514e97) t=990~1046 재생 결과: armed 여전히 0회(원인은
  "실패"가 아니라 debounce가 타겟을 매끈하게 만들어 불연속 자체가 사라짐),
  게다가 이 구간은 brakePressed=False/aEgo 최소 -1.79m/s^2로 실제 급제동
  신호 자체가 없었음을 확인 -- 219차의 "게이트 사각지대=문제" 결론에 대한
  반례. 상세는 FINDINGS.md/WIP.md "220차" 참고.

## 2026-09-03 (219차)
- `diag_route_boost_arm_219.py` 신규 추가 -- 199차 discontinuity boost가
  t=1004~1030류 사례에서 미작동한 원인을 프레임별로 진단. 기존
  `sim_route_217_ceiling_vcruise_ab.py`의 `Branch` 클래스를 그대로 재사용(§21),
  `apex_delta_kph`/`boost_armed`/`required_decel_mss` 관측 레이어만 추가.
  결과: 199차 게이트가 이 구간에서 armed 0회(최대 프레임간 낙차 10.75kph <
  임계값 15.0kph) -- "부스트 무력화"가 아니라 "게이트 감지 사각지대"임을 확정.
  `--decel-rate` 옵션으로 0.70/1.00 비교 가능(218차 결정 반영, 20.04s로 일부
  단축되나 armed는 여전히 0). 상세는 FINDINGS.md/WIP.md "219차" 참고.

## 2026-09-03 (217차 계속2)
- `sim_route_217_ceiling_vcruise_ab.py` 신규 추가 -- 217-2(out_speed ceiling
  상수항 150 고정 -> min(vCruise,150)) 실차로그 A/B 재검증. 215차 18세그
  CSV(commit 4514e97) 재사용, naviPaths에서 214차 B안 방식으로 candidates
  재구성(208차 방식 확장, 거리 포함). OLD 재구성이 recorded liveRouteSpeed와
  median|diff|=0.74kph로 근접(sanity check PASS). 결과 POSITIVE -- 상세는
  WIP.md "217차 계속2" 참고.

## 2026-09-03 (215차)
- `verify_apex_transition_215.py` 신규 추가 -- 214차 B안(route ceiling 거리인지화)
  패치 반영 후 첫 실차 로그(x18seg, commit 4514e97)에서 WIP 214차 계속3이
  합의한 4개 판정기준(1.해제 2.재가속 3.재감속 4.먼커브 비고정)을 apex1->apex2
  전환 이벤트 단위로 자동 채점. POSITIVE(아래 WIP 215차 참고). 179차 noise-point
  위험 실측용 apexIdx flicker 통계도 함께 산출.

## 2026-09-03 (214차)
- `sim_route_ceiling_distance_aware_214.py` 신규 추가 -- route ceiling
  (sharpest_candidate_speed)을 candidate별 calculate_current_speed()
  재사용(거리인지)으로 교체하는 B안 사전검증. 8/8 PASS. 사용자 확정 후
  carrot_man.py L994에 실제 코드 패치 완료(실차 검증 미실시).

## 2026-09-03 (213차)
- `sim_route_distance_offset_213.py` 신규 추가 -- 212차 A안(20m 하드플로어
  제거) 패치 로직을 격리 재현. distance 선증가 초기값 10.0->-10.0 변경 후
  index0 거리가 20.0 고정 -> 0.0 정상화, 접근 중 단조비증가 확인. 5/5 PASS.

## 2026-09-02 (209차)
- `analysis_helpers.py::lead_coast_to_zero_scan()` 신규 추가 -- 실차로그
  (20260902_181435_4e18e62932--12seg)에서 발견된 leadDRel 완만한 단조감소
  ->0.0 도달 직후 leadStatus False 전환 아티팩트 패턴 탐지.
  `curve_lead_dRel_jump_events`(급점프)와 구분되는 별개 패턴. 이번 로그
  기준 1건 탐지, 같은 dRel<1.0m 프레임 전수조사로 누락 없음 확인. 다른
  로그 대상 오탐 여부는 미검증(다음 과제).

## 2026-09-02 (206차)
- `sim_route_205_vego_cap_ab_206.py` 신규 추가 -- 205차 패치(out_speed
  상한 vEgo 동적화)를 202/203차 문제 로그(199차 8세그)로 A/B 재검증.
  결과 NEGATIVE: 핵심 스파이크/고원 구간(t=418.4~423.2, 북대전IC 접근
  t=423~498)에서 OLD/NEW 완전 동일 -- apex_idx 오선택이 raw뿐 아니라
  apex_speed도 함께 오염시켜 205차의 vEgo 하한이 작동하지 않음.

## 2026-09-01 (191차)
- `analysis_helpers.py::type3_curvature_blindspot_scan_v3()` 신규 추가 +
  `scan_type3_curvature_blindspot.py`에 `--v3`/`--stop-v-ego-thresh`/
  `--min-stop-duration` 플래그 추가. 190차 25분 전수스캔에서 새로 발견한
  오탐 유형(a) — 급정거/장기정차 후 xTurnInfo reset으로 naviPaths가
  "제약없음" 기본값으로 복귀하는 프레임들이, 정차 중에도 감긴 채 유지된
  steeringAngleDeg와 결합해 계속 후보를 생성/병합시켜 실제로는 route가
  정상 완주한 급선회(190차 4번/6번, t=1483.51~1534.01/50.5초,
  t=1940.76~1998.20/57.4초)를 긴 오탐 이벤트로 부풀리는 문제를 보완.
  v2 로직(1단계 median/2단계 low_cap)은 완전히 동일하게 유지하고, 3단계로
  vEgo<stop_v_ego_thresh(기본 0.3m/s=프로덕션 `LAUNCH_BYPASS_STOP_V_EGO`
  재사용) 프레임을 (1)후보 생성 자체에서 배제, (2)두 후보 사이
  min_stop_duration_s(기본 1.0초) 이상 정차가 끼어 있으면 merge_gap_s
  이내라도 강제로 이벤트 분리. 합성 데이터로 두 게이트 모두 의도대로
  동작함을 단위 테스트로 확인(정차 구간 포함 시 v2는 하나로 병합, v3는
  정차 전/후로 분리). **190차가 같이 발견한 오탐 유형(b)(190차 3번/5번,
  국지적 실제 커브가 far_window median에 희석되거나 low_cap_eval_start_m
  경계를 비껴가는 문제)는 이번에 다루지 않음** — 관련 파라미터가 이미
  187차 확정사례를 지키기 위해 튜닝된 값이라 실측 회귀 데이터 없이
  건드리면 기존 정탐을 깰 위험(§28). **8개 회귀 세트(187차 1건/188차
  신규 2건/190차 6건) 재실행 검증은 미실시 — routeA.csv/routeB.csv가
  190차 종료 시 미보관되어(§23) 원본 zip 재업로드 필요.** 기본 CLI
  동작(`--v2`/`--v3` 미지정)은 v1 그대로 — 회귀 없음. **ryu 프로덕션
  코드 변경 없음, 분석도구 전용 수정.**

## 2026-09-01 (188차)
- `analysis_helpers.py::type3_curvature_blindspot_scan_v2()` 신규 추가 +
  `scan_type3_curvature_blindspot.py`에 `--v2`/`--show-rejected`/
  `--low-cap-*` 플래그 추가. 187차 도구(v1)를 seg14/15(187차와 동일
  route)로 재실행하는 과정에서 발견: v1의 median 단독 판정이 "far_window
  안에 실제 짧은 커브가 있지만 앞뒤 긴 직선 때문에 median이 희석되는"
  경우(t=1352.76~1361.91 — 대시캠 확인 결과 일반 도로커브, naviPaths도
  실제 곡률(d=80~100m 구간 5km/h)을 담고 있었으나 median은 200km/h로
  나와 오탐)를 걸러내지 못함. v2는 1단계(median 후보 발굴, v1과 완전
  동일)는 그대로 두고, 2단계로 far_window 내 저속 지점의 연속길이
  (`low_cap_run_m`)/비율(`low_cap_ratio_thresh`)을 추가 검사해 오탐을
  분리. **개발 중 자체 회귀 실패 1건 발견/수정**: 2단계 저속판정에
  근접 경계 제외 없이 1차 구현했더니 187차 확정 이벤트 초반부
  (1365.71~1367.76)까지 오탐 제외되는 문제 발생 — 원인은
  `near_field_guard_m`(50m) 바로 다음 d=50~80m 구간에서도 187차 사례
  naviPaths가 순간적으로 저속을 보이는 별도의 근접노이즈 번짐 패턴
  (원인 미확정, FINDINGS.md 188차 NEEDS_INVESTIGATION). `low_cap_eval_
  start_m`(기본 80.0m) 파라미터로 2단계 판정에서만 이 구간을 제외해
  해결. 회귀테스트 3건(187차 기존 사례/신규 A/신규 B) 전부 기대대로
  통과 확인. **기본 CLI 동작(플래그 없이 실행)은 v1 그대로 — 회귀 없음.**
  **ryu 프로덕션 코드 변경 없음, 분석도구 전용 수정.**

## 2026-09-01 (187차)
- `analysis_helpers.py::type3_curvature_blindspot_scan()` 신규 추가 +
  `scan_type3_curvature_blindspot.py` 신규 CLI 도구. 152차가 확정한
  "유형3"(naviPaths 폴리라인 원본 좌표 자체에 급회전 형상 부재, chord
  샘플 간격 문제가 아니라 못 잡음)를 blinker 없이 자동 탐지 —
  152차 다음 단계 제안("blinker 기반 required_decel_gap_scan()은 유형3을
  체계적으로 누락")에 대응. steeringAngleDeg(실제 급조향 발생)를 ground
  truth로 사용해, naviPaths가 median 기준 사실상 직선(near_field_guard_m
  ~far_check_max_m 구간)인데도 lookahead_s 안에 실제 급조향이 온 시점을
  이벤트로 잡는다. **near_field_guard_m 설계 근거(187차 검증 중 발견)**:
  naviPaths 최근접(~0~40m) 점들은 ego 진입 앵커 전환 노이즈로 그 자체가
  스스로 튀는 경우가 있어(149/179차 근접노이즈 문제와 대칭되는 반대
  방향 함정), min()이 아닌 근접 제외+median으로 오탐 방지. 187차
  seg14/15(우회전 교차로 미탐지 실사례, t≈1370)로 검증 — 근접노이즈
  포함 min() 방식 1차 시도는 이 실제 사례를 놓쳤고(근접 앵커전환
  구간의 가짜 curvature 때문), near_field_guard/median 방식으로
  수정 후 정확히 해당 구간(t=1365.71~1376.56)을 이벤트로 포착함을
  확인. **ryu 프로덕션 코드 변경 없음, 분석 전용 신규 도구.**

## 2026-09-01 (183차)
- `sim_route_camera_style_decel.py`: `carrot_navi_route_camera_style_nearest_relative_gated_min_of_both()`
  신규 추가(ChatGPT 제안, 사용자 확인 하 프로토타입). 배경: 사용자가
  "180/181차 relative_gated(0.85) 게이트를 통째로 삭제하고 순수
  nearest로 되돌리자"고 제안했으나, 이는 179~181차가 실측 로그로 검증
  완료한 노이즈 차단 수정(FINDINGS.md 181차)을 되돌리는 것이라 기각.
  대신 relative_gated를 보존하면서, 이 게이트가 갖는 별도의 신규 edge
  case(1차=근접 완만한 진짜커브, 2차=원거리 훨씬 급한 진짜커브, apex가
  2차로 건너뛰어 1차 진입시 과속)를 "게이트 없는 nearest"와 "게이트
  통과 후보" 중 더 보수적인 camera-style 결과를 취하는 방식(min_of_both)
  으로 보정. 유닛테스트 6건 추가(기존 15/15 + 신규 6건 = 21/21 PASS) --
  179~181차 검증 두 건 회귀 없음 확인 + 신규 edge case 재현 및 해소
  확인 + 노이즈=sharpest 동시성 케이스에서 새로운 악화 없음(방어도 안
  됨, 기존 한계 유지) 확인. **ryu 프로덕션 코드 변경 없음, 실측 로그
  재검증 전까지는 시뮬레이션 전용.**

## 2026-08-31 (179차 후속2)
- `sim_route_camera_style_decel.py`: 179차 후속에서 제안만 됐던 대안 2개를
  구현하고 실함수 호출 유닛테스트로 확정(3건 추가, 15/15 PASS) —
  `carrot_navi_route_camera_style_nearest_relative_gated()`(윈도우 내
  sharpest 대비 상대 심각도 비율 게이트, 기본 0.85): **POSITIVE**, 검증2
  (curve1) 대응력 유지 + 검증1(잡음) 차단 동시 만족 확정. 채택 유력.
  `carrot_navi_route_camera_style_nearest_persistence_gated()`(인접
  연속지점 지속성 게이트): **NEGATIVE**, curve1이 fine-sample 특성상
  단일 지점에서만 threshold를 넘어 대응력이 깨짐 — 폐기.

## 2026-08-31 (179차 후속)
- `sim_route_camera_style_decel.py`: `carrot_navi_route_camera_style_nearest_severity_gated()`
  (도로제한속도 대비 비율 최소심각도 게이트 시도) + `noise_then_real_curve_curvature_fn()`
  (검증1 지오메트리 합성 재현) 신규 추가. 유닛테스트 2건 추가(12/12 PASS)로
  이 게이트 방향이 **작동하지 않음**을 확정(단일 비율로 curve1 유지 +
  noise 차단 동시 만족 불가 -- lookup 테이블 비선형성 때문에 noise가
  curve1보다 항상 더 "심각"하게 계산됨). 이 방향 폐기, 대안 제안만
  FINDINGS.md에 기록.

## 2026-08-31 (179차)
- `sim_route_camera_style_decel.py`: `carrot_navi_route_camera_style_nearest()`
  신규 추가(179차 apex 선택기준 "가장 가까운 지점" 오프라인 재현). 유닛테스트
  3건 추가(10/10 PASS) — 연속커브(2차가 살짝 더 급한 경우) 1차 무시 문제를
  nearest가 해소하면서도 2차 대응력은 희생하지 않음을 확정 검증.
- `replay_route_camera_style_vs_baseline.py`: `--apex-mode {sharpest,nearest,both}`
  옵션 추가(기본 sharpest, 기존 호환). `both`로 실측 로그에서 두 방식을
  나란히 비교 가능. route 00000374 재생 결과 FINDINGS.md 179차 기록.

## 2026-08-31 (178차)
- `check_device_build.py` 신규: rlog InitData에서 디바이스 실제
  gitCommit/gitCommitDate/gitBranch/dirty 추출 + 로컬 repo 존재여부/조상관계
  확인. 177차 패치 실차검증 시도 중 디바이스 gitCommit이 origin 히스토리에
  없고 dirty=True인 것을 발견해 작성.

- **2026-08-31 (166차)**: `sim_yaw_anchor_delta.py` 신규 — 165차 방안1
  (orientationNED 절대값 직접차분 앵커링, 적분 아님) 수식 자체의 정합성
  검증. 166차 실측(`ccYawDeg`/`ccYawRateZ`)으로 `CC.orientationNED`가
  나침반 관례(우회전=증가)임을 확인 후, 그 부호를 전제로 리셋무드리프트/
  wrap경계연속성(좌우 양방향)/162차 실측 정체사건 재현(Diff 오차 2.8e-14°
  vs baseline 오차 66.11°)/적분방식과의 교차검증(0.60° 이내) 5/5 PASS.
  ryu 패치 없음(설계 검증만, 사용자 승인 대기).

- **2026-08-31 (165차)**: `extract_log.py` — `ccYawDeg`/`ccYawRateZ`/`ccPoseValid`
  컬럼 추가(carControl.orientationNED[2] 나침반변환값 + calibrated
  angularVelocity[2] 원시값 + 유효성 — livePose 직접구독 대신 carrot_man이
  이미 구독 중인 carControl에서 추출, carrot_serv.py L729 기존 TODO가
  가리키던 바로 그 필드). 162차 근본원인(bearing 정체+직진외삽)의 방향1
  (헤딩보정) 설계 검증용 지상진실 확보 목적. 이 시점 이전 CSV엔 당연히
  없음, 재추출 필요.

- 2026-08-31 (161차) `replay_route_camera_style_vs_baseline.py` 신규:
  158차 `replay_route_apex_vs_baseline.py` 구조 재사용, 160차 camera-style
  알고리즘을 실측 CSV로 오프라인 재생 + liveRouteSpeed 대조. route156 실측
  검증 PASS(157차 stuck 버그 3곳 전부 정상 반응, 회귀없음). 같은 세션에
  naviPaths/TBT가 실제 급우회전을 전혀 감지 못하는 신규 이슈 발견(149차와
  다른 유형, FINDINGS.md 161차 참고).

- 2026-08-30 (158차계속/159차) `sim_route_apex_hysteresis.py` 신규:
  157차 무상태 apex 알고리즘에 대한 3상태(reset/engaged/disengaged)
  히스테리시스 대안, 단위테스트 4/4 PASS. `replay_route_apex_hysteresis_ab.py`
  신규: 같은 route156 실측 CSV로 157차(A) vs 히스테리시스(B) A/B 비교 —
  **결과 NEGATIVE**: B는 stuck 구간 3곳 중 2곳에서 무반응(disengaged
  고착), 프레임간 최대낙차 244.11km/h(A는 0.26km/h) — 램프리미터
  "제약해제 즉시통과" 규칙과 상호작용해 오히려 톱니 진동 유발. 히스테리시스
  방향 폐기, 157차 그대로 유지 결론. FINDINGS.md 159차 참고.
- 2026-08-30 (153차) `sim_route_near_stop_accel_boost.py`:
  `carrot_navi_route_dp_forced_decel()` 신규(152차 옵션1) — 151차가
  NEGATIVE 판정한 "accel_limit을 부스트해 같은 역방향 DP 재귀에 넣는"
  방식 대신, base DP를 그대로 돌린 뒤 근정지급 구간(min_idx까지)만 별도로
  "지금부터 등가속도로 감속하면 정확히 target 도달"하는 물리 공식(재귀/
  time_wait 완전 배제)으로 직접 덮어쓰는 방식. `simulate_approach()`에
  `apply_forced_decel` 파라미터 추가, 유닛테스트 시나리오 E~H 추가.
  **결과 POSITIVE**: 149차 근사조건(초과분 base 4.4kph→옵션1 0.0kph,
  151차 boost는 8.8kph로 악화), 149차 실측조건(5.3→0.0, boost 10.1),
  극단적 늦은 감지(50m, 클램프 1.2 m/s^2 적용, 1.3→0.0, boost 4.9) 3개
  조건 전부 개선 확인, 일반 커브 회귀 없음(diff=0) 확인. FINDINGS.md
  152차 계속2 참고. **ryu 패치는 아직 미작성(다음 단계).**
- 2026-08-30 (152차) `analysis_helpers.py::required_decel_gap_scan()`:
  `turn_confirm_deg`/`turn_confirm_window_s` 게이트 추가 — blinker onset이
  무관한 차선변경일 때 근정지급 커브 감지와 잘못 페어링되던 오탐 버그
  수정(seg10 실측에서 발견, gap_ratio=14.35 허위 이벤트 제거 확인).
- 2026-08-30 (149차) `extract_log.py`: `liveRouteSpeed` 컬럼 추가 —
  `carrotMan.szPosRoadName`의 "route=XX.X" 디버그 텍스트를 정규식으로
  파싱해 post-DP 최종 route_speed 실측값을 직접 추출(재현 시뮬레이션
  불필요). "우회전인데 route 미작동"(898edd0f96 seg16/17) 근본원인을
  이 필드로 확정(감속률 부족, 패치 결함 아님). 기본 추출에 항상 포함.

- 2026-08-30 (148차): `replay_route_full_pipeline.py` 신규(NEEDS_VALIDATION,
  절대수치 신뢰불가 — nRoadLimitSpeed 미기록으로 published 대비 평균오차
  98.7kph) — 147차 패치 실차 재검증(898edd0f96 seg10 재업로드분) 과정에서
  전체 파이프라인(역방향DP+램프리미터) 수치 재현 시도, 실패했으나 toolkit
  방침에 따라 보존. 실제 검증 결론은 기존 `recompute_route_curvature_speed`
  + 실측 직접대조로 도출(FINDINGS.md "148차" 참고).

- 2026-08-30 (147차 계속): `analysis_helpers.py::recompute_route_curvature_speed()`에
  `sample_fine` 파라미터 추가(carrot_man.py `ROUTE_CURVATURE_FINE_SAMPLE`
  패치와 동일 로직, 매크로/미세 샘플 중 더 급한 쪽 채택) — 검증도구를
  실제 패치와 일치시킴. `extract_log.py` 버그 수정: `--with-navi-paths`
  플래그와 무관하게 row dict가 항상 갖는 `naviPaths` 키가 FIELDNAMES에
  누락되어 DictWriter가 항상 크래시하던 문제, FIELDNAMES에 항상 포함
  하도록 수정. 상세는 README.md/FINDINGS.md "147차 계속" 참고.

- 2026-08-30 (145차): `extract_log.py` FIELDNAMES에 `lllProb`/`rllProb`/
  `lllStd`/`rllStd` 추가(modelV2.laneLineProbs[1]/[2],
  laneLineStds[1]/[2]) — AdjustLaneOffset 커브내측 자동보정의 게이트값
  `d_prob`을 CSV만으로 근사 재현하기 위함. 기존 컬럼/세그먼트 캐리오버
  로직 변경 없음(순수 추가, non-breaking).

- 2026-08-29 (131차): `sim_route_step_drop_repro.py` 신규(NEGATIVE) —
  129차 계단형 급락(Δ-25kph 단일프레임)을 desiredCurvature 재구성
  기반으로 재현 시도했으나 최대 1.84kph만 나와 재현 실패, 방법론
  한계 확인. `sim_route_lookahead_boundary_snap.py` 신규(SUCCESS) —
  `carrot_navi_route()` 실제 순수함수를 그대로 복제해 합성 GPS
  폴리라인으로 검증, "route_lookahead 윈도우 경계 진입 시 speeds[]에
  급커브가 이산적으로 출현" 가설(Hypothesis C)이 실측과 동일 규모
  (Δ-19.8kph 단일프레임)로 재현됨. 상세는 FINDINGS.md "131차" 참고.

- 2026-08-29 (125차): `extract_cutin_lists.py` 신규 — rlog에서
  `radarState.leadOne`/`leadsCutIn`/`leadsLeft`/`leadsRight`를 시간별로
  원본 그대로 추출(게이트 재구현 없음). r354 t≈296~299 컷인 재분석에서
  cutIn/left/right가 사건 내내 전부 비어있었음(옆차 yRel 최대 0.83m로
  `in_lane_prob` 계산상 "차로 안" 판정 유지) 확인 — "차선 폭 넓히기"
  제안이 이 사례엔 무력함을 입증. 124차의 TTC 계산(7초+)이 실제 위험
  구간(t=297.0 이후, dRel 5.3→1.8m, yRel 0→0.8m 급변, TTC 3.1초)을
  놓쳤던 것도 이번에 정정됨(상세는 FINDINGS.md "125차" 참고).

- 2026-08-29 (120차): `replay_lane_departure_gate.py` 신규 — 119차
  실제 패치(radard.py LANE_DEPARTURE 게이트)를 실차 route CSV
  4개(89996행)로 검증. PASS 5/FAIL 3 — `LeadBlend.update()`가 게이트의
  status=False 리셋을 자신의 구버전 `_is_cutout()`(2.0m 기준)으로
  재판정해 최대 0.6s(LEAD_LOST_GRACE_TIME) 무력화하는 구조적 버그
  발견(상세는 FINDINGS.md/WIP.md "120차" 참고, NEEDS_FIX).

- 2026-08-29 (119차): `sim_lane_departure_gate.py` 신규 — 118차
  제안 차선이탈 강제해제 게이트(THRESH/CONFIRM_S) 파라미터 후보
  합성 검증. 핵심 발견: 기존 2.0m 재사용 시 실측 이벤트(route1
  t=5915~5932) 최대 dPath가 -1.99m라 아예 트리거 안 됨, 1.75m로
  좁히면 자연해제 대비 2.25s 단축(근사치, route1.csv 미보유로 정밀
  replay 아님).

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

## 2026-08-29 (116차, sim_gap_open_damping.py 신규)
- 신규: `toolkit/sim_gap_open_damping.py` — 저속(<=40km/h)+gap_ratio>=1.5
  (기존 MARGIN_ACCEL_GATE_FULL 재사용)+앞차 강한가속 조건에서만 a_lead에
  상한(0.5 m/s^2)을 거는 신규 방안(LOW_SPEED_GAP_OPEN_*) 단위 검증.
  launch bypass 및 정상 출발 연장 구간 오탐 방지(45차 재발 방지) 포함
  6개 시나리오 전부 PASS. **경계 전이 시 a_lead 최대 1.5 m/s^2 단차
  발견 -- 완만화 필요 여부 NEEDS_VALIDATION.**
- 2026-08-29 (117차): sim_gap_open_damping.py에 완만화(rise-rate 블렌드)
  버전(`apply_gap_open_cap_smoothed`) 추가 -- 116차 F에서 발견된 하드클램프
  단차(1.5 m/s^2)를 39차와 동일 패턴(블렌드 weight 사이클당 변화폭 제한,
  양방향)으로 해소. 신규 시나리오 G(단차 0.075로 감소)/H(bypass 즉시
  우회)/I(정상상태 일치) 전부 PASS. long_mpc.py 실제 패치 적용 완료
  (LOW_SPEED_GAP_OPEN_*, LOW_SPEED_GAP_OPEN_WEIGHT_RISE_RATE 신규,
  patch 0001-117-gap-opening-a_lead-116-rise-rate.patch), git am 검증 통과.

## 2026-08-29 (130차, sim_lead_blend_far_jump_gate.py 신규 + radard.py 패치)
- 신규: `toolkit/sim_lead_blend_far_jump_gate.py` — 104차 Finding A
  (커브+레이더유실 시 vision-only 저신뢰 원거리 오판) 재현 및
  `LeadBlend` BIG_JUMP 신뢰도 게이트 패치 검증. 5개 시나리오 전부 PASS.
- 패치: `radard.py` `LeadBlend.update()` BIG_JUMP(>15m 안전방향)
  즉시-스냅 조건에 `LEAD_BLEND_BIG_JUMP_PROB_GATE(0.70)` 신뢰도 게이트
  추가 — radar=True 또는 고신뢰 vision(modelProb>=0.70)만 즉시 스냅,
  저신뢰 vision-only far jump는 기존 블렌딩(0.35s 시정수) 경로로.
  git am verify-am 브랜치 검증(base `b63063a`) + py_compile 통과,
  패치 `0001-130-LeadBlend-BIG_JUMP-104-Finding-A.patch` 전달.
  실차 검증 대기(FINDINGS.md 130차 참고).

## 132차
- `sim_route_boundary_ramp_limiter.py`(신규) — 131차 Hypothesis C 패치
  후보(carrot_navi_route() out_speed 프레임간 램프 리미터, 상한
  accel_limit_kmh*dt) 사전검증. curve_R 10~25m/accel 0.70~1.2 전
  조합 PASS(정상주행 구간 최대낙차가 이론 상한 이내로 억제).
  실제 패치 `0001-132-route_lookahead-Hypothesis-C-131-out_speed.patch`
  작성 -> verify-am(base 1cc2bf3) git am 성공 + py_compile 통과 + diff-0.
  실차 검증 대기(FINDINGS.md 132차 참고).

## 133차
- `extract_gps.py`(신규) — gpsLocation(1Hz) capnp 채널 추출을 재사용
  가능한 스크립트로 정식화(131차 인라인 작업 대체).
- `replay_route_ramp_limiter_direct.py`(신규, 주 검증도구) — 132차
  램프 리미터를 실측 desiredSpeed(route) 원본 시계열에 직접 사후적용.
  129차/131차 원본 route(306de77a28 seg15) 재업로드로 검증 -- 실측
  급락 2건(t=4.25 Δ-25, t=28.35 Δ-24) 모두 patched에서 초당
  accel_limit_kmh 상한 이내로 완화됨을 확인, PASS.
- `replay_route_boundary_ramp_limiter.py`(신규, 보조) — 실측 GPS
  트랙(1Hz)을 navi_points 프록시로 carrot_navi_route_core(131차) 재생.
  t=28.35 이벤트를 raw 66.6->37.9 단일프레임 스냅으로 독립 재현(Hypothesis
  C 실측 재확인), t=4.25는 lookahead 윈도우 한계로 재현 실패(방법론
  한계, 주 검증도구 결론에는 영향 없음).
- 134차: sim_boost_arm_priority.py 신규 — boost-arm 소스 4종(discontinuity/discontinuity_lc/handoff/low_speed_strong_decel) 덮어쓰기 우선순위 검증, 112차 가드 비대칭 발견분 long_mpc.py 패치와 함께 7/7 PASS
- 140차: sim_path_offset_laneless_curvature_source.py 신규 — controlsd.py의 curvature 소스 선택 분기(PathOffset 레인리스 반영 패치) 로직단위 검증, 6/6 PASS
- 141차: sim_path_offset_laneless_curvature_source.py 갱신(mpc_solution_valid 파라미터 추가) — mpcSolutionValid 체크(140차 리뷰 지적사항 보완) 8/8 PASS
- 144차: extract_log.py에 activeLaneLine 컬럼 추가(controlsState) — 140/141차 PathOffset 레인리스 패치 실차검증에 필요. data/routes/ba5f3d3273,898edd0f96,e996400f6e,144cha-combined 신규(사용자 실주행 로그 3개 x37seg, 연속주행 07:02~07:37 20.6km, 20260830 업로드, NEEDS_VALIDATION — 승인 후 삭제 예정)
- 146차: extract_log.py FIELDNAMES에 activeCarrot/xTurnInfo/xDistToTurn/xSpdType/xSpdDist/atcType/leftSec 추가 — route 카운트다운/회전(ATC) 사전감속 미작동 가설(xTurnInfo 이중소스 충돌) 정량검증용. active_kisa_count는 cereal 미발행이라 CSV 추출 불가함을 주석으로 명시
- 146차 계속: extract_log.py에 xSpdCountDown/xTurnCountDown 추가 후 원본 route(ba5f3d3273/898edd0f96/e996400f6e) 재추출로 정량검증 — xTurnInfo 이중소스 가설은 기각, 실제 원인은 AutoTurnControl=0/AutoNaviCountDownMode=0(둘 다 off) 확정. extract_gps.py로 정차구간 GPS 드리프트 확인해 가설 B(정차 중 route= 하락)도 정성지지
- 147차: extract_log.py에 `--with-navi-paths` 플래그 신규(기본 off, row당 최대 ~1200자라 기본 추출엔 미포함) — carrotMan.naviPaths(carrot_navi_route()가 곡률 계산에 실제 쓰는 로컬(x,y) 리샘플 폴리라인+거리, 이미 20Hz 발행 중이었음/ryu 코드 변경 없음) 컬럼 추출 지원. analysis_helpers.py에 `parse_navi_paths()`/`recompute_route_curvature_speed()`/`route_curvature_underestimate_scan()` 신규 — 89차/90차가 "raw navi_points 로그 부재로 직접검증 불가"라 미뤄뒀던 "route 곡률 과소평가가 chord 길이 문제인지 실제 지도 폴리라인 형상 문제인지"를 이제 실측 데이터로 직접 검증 가능. 합성 90도 코너로 단위테스트 PASS(코너 정점에서 curvature=0.03/speed_cap=20.5kph 정확히 포착 확인)
- 151차: analysis_helpers.py에 `required_decel_gap_scan()` 신규 — liveRouteSpeed(149차) 기반, 근정지급 코너(fine 곡률 첫 감지 시점~진입 시점) 구간의 필요감속률 vs 실측감속률 갭 스캔. route1617.csv 1건 검출(gap≈2.6kph/s).
- 151차: sim_route_near_stop_accel_boost.py 신규 — carrot_navi_route()의 역방향 accel-limited DP(`carrot_navi_route_dp()`) 독립 재현 + 149차/150차 설계 근정지급 부스트(`ROUTE_NEAR_STOP_TARGET_KPH`/`ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS`) on/off 비교. `simulate_approach()`로 단일 코너 접근을 132차 램프리미터(`sim_route_boundary_ramp_limiter.RampLimiterState` 재사용) 포함 다중프레임(20Hz) 시뮬레이션 — **결과 NEGATIVE(부스트가 오히려 초과분 악화), 배포 보류 권고**. 상세는 FINDINGS.md 151차 참고.

## 157차
- `sim_route_apex_redesign.py`(신규) — 사용자 제안 재설계("route는 다음
  apex(최대곡률)까지의 거리 하나로 사전감속을 결정, 통과 후 vturn에
  넘기고 다음 apex를 다시 찾는다") 시뮬레이션 검증. baseline(기존
  backward DP + 153차 근정지 후처리, curvature<0.02 플로어 포함
  재현) vs apex 재설계(단일 apex 거리기반 물리공식, 플로어 임계값
  0.001) 비교. 156차 재현 연속 굽이길(baseline 무반응 확인 vs apex
  정상 감속)/직선 회귀없음/147차류 단일커브(0.02 미만이면 baseline도
  플로어 버그로 무반응함을 재확인, apex는 정상)/152·153차 근정지
  재현(apex가 153차 forced-decel과 동등 성능) 4개 시나리오 7/7 PASS.

## 2026-08-30 (158차, 신규)
- `analysis_helpers.recompute_route_curvature_speed()`/
  `_route_curvature_single_pass()`에 `floor_threshold` 파라미터 추가
  (기본 0.02=하위호환, 157차 패치 재현 시 0.001 전달). 기존 호출부
  전부 영향 없음(스모크 테스트 확인).
- `replay_route_apex_vs_baseline.py` 신규 -- naviPaths 포함 "패치 적용
  이전" 실측 로그를 프레임 단위로 재생, 157차 apex 알고리즘 오프라인
  재현값을 실측 liveRouteSpeed(패치전 production, ground truth)와 비교.
  148차 replay_route_full_pipeline.py(신뢰불가, nRoadLimitSpeed 가정치
  필요)와 달리 절대오차 문제 없음. 156차가 준 실제 route 로그(2세그먼트,
  "route 작동안함 104에서 멈춤")로 검증: liveRouteSpeed가 104.0km/h로
  9.9~12.3초씩 3회 고정되는 실측 버그 구간에서, apex 오프라인 재계산은
  56.3~76.7km/h로 정상 반응(157차 패치가 실제 이 로그에서 문제를
  해결했을 것임을 실측 데이터로 확인). stuck 구간과 20초 이상 떨어진
  나머지 구간에서는 오탐(과잉감속) 0건. 프레임간 최대낙차 0.26km/h로
  132차 램프리미터도 정상 작동 확인(단, naviPaths 부족으로 윈도우가
  리셋되는 프레임에서는 production과 동일하게 램프 예외 발생 -- 버그
  아님).
- (2026-08-31, 160차 신규) sim_route_camera_style_decel.py 추가 — route 감속을
  과속카메라 calculate_current_speed()와 동일 공식으로 재구현(157차 accel_limit
  동적 부스트 폐기, safe_time 버퍼 신규), 연속 S자커브 apex 전환 시나리오 포함
  7/7 PASS. carrot_man.py 패치(0001-route-decel-reuse-camera-...)로 이어짐.
- (2026-08-31, 162차 신규) compare_navpos_vs_gps.py 추가 — carrotMan
  xPosLat/xPosLon/xPosAngle(데드레커닝 ego 추정위치, 20Hz) vs gpsLocation
  (실측, 1Hz) 이격 비교. 161차 "route가 우회전을 못 봄" 근본원인이
  carrot_navi_route() 곡률계산이 아니라 estimate_position() 데드레커닝의
  헤딩 정체(회전 중 11초간 296.0°로 고정, 최대 28m 위치오차)임을 확인.
  (컨테이너 리셋으로 최초 작성분 유실 → 재업로드 로그로 재작성+재검증,
  수치 완전 일치 확인.)
- (2026-08-31, 163차 신규) sim_route_position_uncertainty_gate.py 추가 —
  162차 근본원인 방향2(보수적 완화) 패치의 램프리미터 위치불확실성 게이트
  검증. carrot_man.py/carrot_serv.py 패치(0001-route-position-uncertainty-gate)로
  이어짐. 3/3 PASS(회귀없음/재현/하강허용), 157차 apex 재설계 기존 회귀
  테스트 7/7 재확인.
- (2026-08-31, 169차 계측) extract_log.py 컬럼 추가 — carrotMan.vpPosPointLatNavi/
  LonNavi, dtNaviPacketAge, positionDtSinceFix. 169차 코드리뷰에서 재발견한
  기존 "내부GPS 폴백" 타임아웃 판정(패킷 도착 기준)이 "내용정지" 실패모드를
  못 잡는 문제(NEEDS_INVESTIGATION)를 다음 실차 로그에서 CSV만으로 직접
  구분하기 위함. ryu 본체 패치(0001-add-navi-gps-telemetry-instrumentation)로
  cereal(custom.capnp)/carrot_serv.py에 4개 필드 신규 발행 필요 — 패치
  미적용 로그는 전부 0.0으로 찍힘(주의 필요, 크래시 아님).

## 173차
- `sim_route_boundary_ramp_limiter.py`: `RampLimiterState`에 `asymmetric_up`
  옵션(기본 False, 하위호환 유지) 추가 — 172차 원인A(132차 대칭 램프가
  160차 apex 재설계 "즉시 원복" 의도를 무력화) 패치 후보 사전검증.
  `run()`에 `--road-limit-speed-kph` 옵션도 추가.
## 175차
- `build_acados_long_mpc.sh` + `acados_stub_prelude.py`: 실제 acados 롱컨 솔버를
  이 컨테이너에서 코드젠+컴파일해 살아있는 LongitudinalMpc로 인스턴스화하는 절차 신규
  작성 (스크립트 단독 재실행으로 재현성 검증 완료). 174차 원인B(A_CHANGE_COST=200
  구조적 지연) acados 실솔버 재현검증의 선행 작업.
- 176차: `sim_acados_causeB_signflip.py` 신규 -- acados 실솔버 폐루프 시뮬레이션으로 174차
  원인B(A_CHANGE_COST=200 부호전환 지연) 가설 재현검증 SUCCESS (baseline 부호전환 1.5s vs
  완화값(20) 1.0s, 0.5s 차이). route raw zip 미보유로 실측 프레임 대신 FINDINGS.md 174차
  요약 특성 기반 통제된 합성 시나리오 사용(제약사항 README에 명시).
- 176차 계속: `sim_acados_causeB_real_replay.py` 신규 -- 사용자가 재업로드한 route
  `6310bba9b8` raw zip을 실측 프레임 단위로 acados 실솔버에 주입해 원인B 가설 재검증.
  closedloop 모드에서 baseline(200) vs 완화(20) 부호전환 0.45s 차이로 가설 방향 재확인.
  단, 시뮬레이션 절대 감속량이 실측보다 약함(원인 미해결, README에 명시) + t=832.51
  이후 실측은 운전자 수동제동 혼입 구간이라 비교 무효(t<832.51로 한정 필요).
- 177차: 원인B 패치 설계+구현 -- long_mpc.py에 리드없는 cruise 모드 route 감속률
  기반 a_change_cost 완화 게이트 신규(CRUISE_DECEL_RATE_RELAX_LOW/HIGH,
  CRUISE_DECEL_RELAX_A_CHANGE_COST, self.route_decel_rate EMA). `sim_causeB_patch_validate.py`
  신규 -- 패치 ON/OFF 비교, 부호전환 1.5s->1.25s(0.25s 단축), t=3.0s gap 9.19->7.99kph.
  HIGH 임계값 1.0->0.85 재조정(EMA 평활화로 정상상태 ~0.906 도달, 최초 설정으론 완전완화 미달성).
  PARAMS_REGISTRY.md 신규 등록(NEEDS_VALIDATION). git am 검증/실차 검증 아직.
- 180차: `replay_route_camera_style_vs_baseline.py`에 `--apex-mode relative_gated`
  (179차 후속2/180차 프로덕션 반영 게이트) + `both_relative`(nearest vs relative_gated
  비교) 신규 추가. `carrot_navi_route_camera_style_nearest_relative_gated` import 및
  A/B 비교 출력부 일반화(하드코딩된 sharpest/nearest → modes[0]/modes[1]). 합성
  스팟체크로 relative_gated가 sharpest와 동일 결과를 냄을 확인. **route 00000374
  실측 CSV 재확보 후 both_relative 실측 A/B 재검증은 아직 미착수(다음 세션 과제).**
- 182차: `check_navi_route_activity.py` 신규 -- navi_points_active 드롭아웃("route
  사전감속이 61초간 전혀 없었음", route=390.0 노출) 자동 진단. `naviPointsActive`
  =False 연속구간을 찾아 지속시간/드롭아웃 직전 route 소스(navd/tcp_raw/tcp_navi)/
  vEgo 범위를 리포트. `extract_log.py`에 `naviPointsActive`/`navdActive`/
  `dtRouteInactive`/`routeSource` 4컬럼 신규(carrotMan, 항상 포함). 이 필드들은
  `0001-navi-route-activity-instrumentation.patch`(182차, ryu 본체)로 실차 반영
  해야만 새 rlog에 찍힘 -- 패치 적용 전 로그는 `--fallback-naviPaths` 근사 모드로
  degrade(naviPaths 텍스트 비어있음 + liveRouteSpeed==390.0 휴리스틱, 원인규명은
  불가능하고 지속시간만 근사 추정). 사용자 실차 패치 반영 대기 중(NEEDS_VALIDATION).
## 203차
- `sim_route_hi_vego_anchor_203.py`: 신규 -- 202차 제안(상승측 hi 디바운스
  게이트) 1단계 검증. `hi=math.inf`(A, 현재) vs `hi=vEgo_kph`(B, 제안) A/B
  재현. 북대전IC would_bind A 37.1%->B 98.9%로 방향 확인. 스파이크가 단발이
  아니라 t=418.62~423.18(4.6초) 지속 고원임을 신규 발견 -- 진짜 apex 전환
  (t=423.23) 시점부터 raw 단조감소, 이후 hi 설정 무관해짐.
- `sim_route_hi_debounce_sweep_203.py`: 신규 -- N프레임 디바운스 스윕
  (N=3/5/8/10/60/92/100/120). N=92(4.6초)에서 disarm 시각이 진짜 커브 진입과
  정확히 일치(유효 신호 확인). 그러나 동일 신호가 정상 연속곡선 통과 후
  가속 구간(t=382~393, 실측 대조)에서도 반복 발생 -- armed 상태에서 route
  후보가 vEgo에 고정되어 실가속 억제 위험을 실측으로 확인. "apex_idx 급변"
  단독 신호로는 허위스파이크/정상 연속곡선 구분 불가 결론(FINDINGS.md 203차).
  코드화 보류, 사용자 방향 결정 대기.
## 221차
- `sim_route_ceiling_vego_221.py`: 신규 -- ceiling 기준항 vCruise(217차) ->
  vEgo(221차) 재교체를 사용자 설계문서 예시 2건 + 안전조건(무개입) 1건 +
  vEgo<=0 폴백 대조군으로 합성검증. 시나리오2(완만 원거리 후보 65kph 존재,
  vEgo=50/vCruise=70)에서 OLD=65(vEgo보다 빠르게 가라는 신호, 위반) vs
  NEW=50(vEgo로 정확히 눌림)으로 실제 분기 확인(4/4 assert PASS). 단일후보
  케이스(시나리오2b)는 mid항이 이미 vEgo로 지배해 OLD==NEW로 수렴함을
  대조군으로 별도 기록(ceiling 차이가 "항상" 드러나는 게 아님을 명시).
  실차로그 없음(§23, 미보관 정책 + 미업로드) -- 합성검증 한정, 실차 검증 미실시.
## 207차
- `sim_route_ceiling_sharpest_candidate_207.py`: 신규 -- 206차 NEGATIVE 원인
  (근접 trivial 후보가 원거리 진짜 급커브를 "고원" 구간 동안 가려 apex_speed까지
  오염시키는 문제)에 대응하는 설계(ceiling 항만 apex_speed -> sharpest_candidate_speed)를
  ryu 코드 반영 전 시나리오 기반으로 사전검증. 6/6 PASS(핵심 재현 시나리오 150->55,
  대조 시나리오 3종 diff-0). ryu 패치는 `0001-207-...patch`로 별도 전달, 실차 미검증.
## 208차
- `sim_route_207_ceiling_ab_208.py`: 신규 -- 207차(ceiling apex_speed ->
  sharpest_candidate_speed, `2b44b65` 현재 코드)를 199cha 8세그 실차로그로
  처음 실측 재검증(207차 사전검증은 합성 시나리오였음, NEEDS_VALIDATION 해소).
  이 로그엔 204차 candidate telemetry가 없어 naviPaths 원시 폴리라인에서
  `analysis_helpers.recompute_route_curvature_speed()`로 candidates를 직접
  재구성(macro sample=4 + fine sample=1, road_limit_speed=200.0 고정가정
  148/161차 기존 한계 재사용). 북대전IC 구간(t=450~498) would_bind
  37.1%(205차, 206차 NEGATIVE와 동일)->76.8~77.3%(207차)로 대폭 개선을 실측
  확인 -- 205차 단독으로 해결 못했던 202/203차 문제를 207차가 이 로그
  기준으로는 상당 부분 해소함(POSITIVE). 부수 발견: naviPaths 마지막
  리샘플 포인트가 드물게(0.4%, 28/7098프레임) 실제 유클리드 간격이 10m와
  불일치하는 경계 클램프 아티팩트를 만들어 허위 급커브(5.0kph)로 오판되는
  사례 1건 발견 -- 스크립트에 트림 보정 반영, 결과 영향은 미미(76.8% vs
  77.3%)함을 확인. 이 결과와 별개로 t=466~467 구간 실제 device 텔레메트리
  자체(routeApexSpeed)가 5.0을 기록해, sharpest_candidate가 미리 잡아낸
  5.0kph 후보가 아티팩트가 아니라 실재하는 급커브임을 교차검증함.
## 238차
- `replay_route_237_vs_baseline.py`: 신규 -- 237차 patch(`ROUTE_SEVERITY_GATE_RATIO=0.70`,
  carrot_man.py `fc98eaa`)를 실차 적용 전 158/224차 방식으로 desiredSpeed
  출력 시계열까지 A/B 재현. `sim_route_234_spatial_apex_continuity.py`
  (candidate 재구성)와 `replay_route_223_vs_baseline.py`의 `RouteSim223`
  (apex->out_speed 상태기계, 무변경 재사용)을 조합해, baseline(A, stage0만)
  vs patched(B, stage0+237차 stage1 gate) 각각 독립 인스턴스로 out_speed를
  계산. seg12-16 로그(5999행) 실측 결과: apex_dist 점프(>40m) 172건(A)->
  47건(B)로 감소(방향은 237차 checkpoint와 일치), out_speed 기준 vEgo+2kph
  초과 유지 구간(overshoot)이 A는 1건(t=2245.1~2248.5, max 99.4kph, apex_speed
  프레임간 노이즈가 route_active 상태에서 감쇠 없이 그대로 out_speed로
  노출된 것으로 확인 -- 237차 gate 도입 동기를 실제 out_speed 레벨에서도
  재확인) 발견된 반면 B는 0건. **중요 발견(신규)**: 실제 patch 코드는
  stage1을 stage0 결과 위에 순차 적용(nested, `candidates = [k for k in
  candidates if ...]`)하는데, 234차 `sim_route_234_...`의 stage1은 전체
  speeds 배열에 독립적으로 재적용(non-nested)하고 있어 두 방식이 다르다 --
  이 차이로 전체 stage1 건수가 234차 기록 60건과 47건(이 스크립트, nested/
  실코드 그대로)으로 갈렸다. 구간별 대조: 터널(81/0)·S커브(0/6)는 완전
  일치, IC gore만 22(234차, non-nested)->30건(이 스크립트, nested/실코드)
  으로 차이 -- **234차 toolkit 수치가 실제 배포 코드(nested)보다 낙관적
  이었을 가능성**, WIP.md 238차/FINDINGS.md 참고. 실차 검증은 여전히
  미실시(오프라인 재계산 한정, RouteSim223 단순화 한계는 스크립트 docstring
  한계 3번 참고).
## 224차
- `replay_route_223_vs_baseline.py`: 신규 -- 223차 재설계(무상태 감속식,
  carrot_man.py L840-922) 검증용. curve 후보 선택 로직이 223차에서도
  불변임을 이용해 naviPaths 재파싱 없이 로그의 routeApexIdx/Dist/Speed
  (193/194차 계측)를 그대로 입력으로 재사용, liveRouteSpeed(구코드 실측)
  vs new_out_speed(223차 오프라인 재계산)를 "vEgo+2kph 초과 유지 구간"
  기준으로 대조. 222차 로그(17세그, 0000038c--2cbdaca9d2)로 실측 검증 --
  222차 원 버그(정지->재출발 55kph 초과) FIX 확인 + 신규 발견 2건(apex
  전 정지 시 RELEASE 미작동/apexIdx flicker 무감쇠 노출). 상세는
  FINDINGS.md 224차 참고.
