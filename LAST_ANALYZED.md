# LAST_ANALYZED — 브랜치별 마지막 커밋 분석 지점

새 세션에서 "최신 커밋 분석"을 요청받으면, 여기 기록된 커밋 이후만
`git log <기록된 해시>..HEAD`로 훑는다. 매번 최근 30개를 처음부터
다시 보지 않기 위함.

분석을 마칠 때마다 이 파일을 갱신한다 (해시 + 날짜 + 한줄 메모).

---

## c3-ms-dev
- last_analyzed_commit (35차): `dfa2f4f` (HEAD, 신규 커밋 2개 —
  `c1e79ed`(screenrecord clip 60s->20s) + 자체 해시로 재커밋된
  carrotweb Clip 필터 버튼 커밋. 둘 다 `git am`으로 컨텍스트 충돌
  없이 적용, `git push origin c3-ms-dev` 완료 확인(`8114a46..dfa2f4f`).
  같은 두 patch가 `c3-ms-test`에도 충돌 없이 적용되어 push 완료
  (`725d19f..e9000b3`) — 코드 분석 대상 아님(우리가 만든 UI/설정
  패치), 참고용 기록만.
- date: 2026-08-22 (35차)
- note: (35차) 실차 검증 남음 — clip 실제 길이 20초대 확인, carrotweb
  "Clip만" 필터 버튼 동작 확인. 상세는 FINDINGS.md/WIP.md 35차 참고.

## c3-ms-dev
- last_analyzed_commit (33차): `8114a46` (HEAD, 신규 커밋 2개 —
  `c53c2fd`(26차 patch 실제 반영: 곡선 노이즈 클램프+중앙값 필터 +
  VISION_CLOSING_RATE 절대값 게이트 신설, 구문턱 -5.5/-10.0으로
  origin 최초 push) + `8114a46`(33차: 문턱을 30/31차 확정값
  -2.2/-5.0으로 재설계). 둘 다 사용자가 로컬(`c:\dev\ryu`)에서
  커밋 후 이번 세션에서 `git push origin c3-ms-dev` 완료 확인
  (`a4b5550..8114a46`, fetch로 diff 최종 상태
  GATE_CAUTION=-2.2/GATE_DANGER=-5.0 재확인).
- date: 2026-08-21 (33차)
- note: (33차) 32차에서 사용자 확인 대기였던 두 갈래 중 (a) 문턱
  재설계 진행 확정 → 컨테이너가 origin 새 clone이라 26차 로컬
  커밋(5cc0900, 미push 상태였음)이 없어 devnotes 기록으로 역설계
  재구성한 2단계 커밋(26차 재현 + 문턱 델타)으로 패치 생성 →
  전달한 delta patch는 `git am` 컨텍스트 불일치로 실패(예상된
  리스크) → PowerShell 정규식 치환으로 수동 반영 → 사용자가 실제
  커밋(`c53c2fd`/`8114a46`)까지 완료 후 push. **VISION_CLOSING_RATE_
  GATE_CAUTION/DANGER, MAX_PLAUSIBLE, MEDIAN_WINDOW 4개 신규 상수
  PARAMS_REGISTRY.md에 PARTIALLY_VALIDATED로 추가.** (b) "지속적
  곡선 dRel-vRel 불일치 드리프트" 결함은 이번 세션 범위 밖, 다음
  세션 과제로 유지(FINDINGS.md 32차 참고). **다음 최우선**: 신규
  로그로 이 게이트가 실제 acados MPC 파이프라인에서 원거리 반응
  지연을 개선하는지 첫 실측 검증 — 지금까지는 전부
  `sim_frac_rate.py` 시뮬레이션 기반.

## c3-ms-dev
- last_analyzed_commit (20차 계속): `a4b5550` (HEAD, 신규 커밋 없음 —
  20차 계속은 toolkit 도구 1~4/5 첫 실전 실행 세션)
- date: 2026-08-21 (20차 계속)
- note: (20차 계속) 신규 로그(`c8fef594d3`, 18분, 18세그)로 도구
  1~4/5를 실제 route CSV에 처음 돌려봄. **1/5**: 세그먼트 경계
  아티팩트 0건 확인(수정 정상 동작). **3/5**: 곡선 노이즈 21건 중
  대부분(seg6 등)은 aEgo 무변화로 무해 확인됐으나, seg12 t=798은
  물리적으로 일관된 진짜 리드 접근으로 확인 — would_trigger 휴리스틱이
  노이즈/진짜위험을 구분 못 함, 다중 프레임 체크 보강 필요.
  **4/5(신규 도구 첫 실행)**: `all_source_pairs_flicker_summary()`로
  전체 쌍 자동 스캔 — road<->vturn(107건)이 model<->vturn(70건)보다
  우세, road<->route(34건)도 최초 정량화. cut-in 5건/ttc_danger 5건
  전부 cruiseEnabled=False라 무해. 상세는 FINDINGS.md 20차 계속 참고.

## c3-ms-dev
- last_analyzed_commit (23차): `a4b5550` (HEAD, 신규 커밋 없음 —
  23차는 22차-2 패치의 실차 첫 실측 검증 세션)
- date: 2026-08-21 (23차)
- note: (23차) routeA(`8417c66e7e`, 20분)/routeB(`c8fef594d3`,
  36분) 신규 로그로 개선안 3번(vision closing-rate grace) 실차
  검증. **grace 로직 정상 동작 확인**(14건 blip-preserved,
  `toolkit/sim_vision_rate.py` 재현 시뮬레이터로 검증, devnotes에
  편입). 단 22차가 겨냥한 정확한 증상(카메라 인식→레이더 락온
  급감속)의 재현 사례는 이번 로그에 없어 "패치가 실제로 증상을
  줄이는지"는 아직 직접 검증 못함. **신규 발견**: 곡선(`src=vturn`)
  구간에서 vision dRel이 여러 물체 사이를 널뛰며 노이즈성 DANGER
  TTC를 유발할 수 있음(routeB seg12 t=815/817) — 1/2/4번안(TTC
  문턱 완화/closing-rate 게이트/MPC에 직접 주입) 설계 전 이 노이즈
  필터링을 먼저 검토해야 함. 별개로 seg12 t=798 급감속은 곡선
  구간 레이더 타깃 전환 이슈로 재분류(vision closing-rate 크로스
  체크와 무관). 상세는 FINDINGS.md 23차 참고.

## c3-ms-dev
- last_analyzed_commit (24차 최종): `a4b5550` (HEAD, 신규 커밋 없음
  — 24차는 하루치 실주행 로그 15개 zip 대량 배치 분석 세션, 이번
  갱신으로 24차 완전 종료)
- date: 2026-08-21 (24차 최종)
- note: (24차 최종) 22~23차 vision closing-rate grace 버그 수정
  적용 후 첫 하루치(06:29~14:20, 약 7.9시간 구간, 총 주행 약
  230km) 실주행 로그 15개 zip **전체 처리 완료**(실질 분석 13개,
  ADAS 미관여 스킵 2개). **종방향 안전 지표(harsh_brake/turn_speed_
  violation/ttc_danger, ADAS 관여 기준) 13개 실질 라우트 전부
  0건** — a4b5550 HEAD가 고속도로/시내/극심한 정체 전 도로유형에
  걸쳐 종방향 안전 회귀 없음 최종 확인. **b403d52(vision
  closing-rate) 프레임단위 실측 검증 완료**(route5, PARAMS_REGISTRY.md
  갱신 완료) — 6차 원 제보 증상과 정반대 결과. 신규 source 라벨
  2건(`bump`=APN 과속방지턱, `gas`=가속페달 오버라이드) 관찰 —
  둘 다 기존 코드의 정상 동작, 이번 배치에서 처음 로그에 등장했을
  뿐. source_pair 우세 쌍의 도로유형 의존성(고속도로=road<->vturn
  압도, 시내혼합=역전/동률, 정체=재우세하나 다변화)이 15개 라우트
  전체에 걸쳐 일관되게 확인 — 도로유형별 분기 설계 필요성 최종
  뒷받침. 상세는 FINDINGS.md 24차 최종 종합 참고. **다음 우선
  과제**: 고속도로 급접근(harsh) 케이스 표본 미확보(b403d52 "온건한
  접근" 검증에 그침), route3 highway 판별 버그 영향 재확인(낮은
  우선순위).

## c3-ms-dev (구버전 기록)
- last_analyzed_commit: `a4b5550` (HEAD, 22차-2에서 작성한 vision
  closing-rate leadStatus grace 버그 수정 패치를 사용자가 실차에서
  `git am` 적용 + `git push` 완료 확인 — `1f9f852..a4b5550`, 원격
  fetch로 diff 동일 재확인. 개선안 3번 완전 반영.)
- date: 2026-08-20 (22차-3)
- note: (22차-3, 코드 변경 없음, devnotes 갱신만) 22차-2에서 작성한
  로컬 커밋 `34227e9`(base `1f9f852`)가 사용자 실차에서 그대로
  `git am`+`git push`로 반영됨(원격 `a4b5550`). 원격 fetch 후 로컬
  커밋과 diff 없음(내용 완전 동일) 확인. **실측 검증은 다음
  세션 과제로 유지** — route1/route2와 유사하게 leadStatus가
  짧게 깜빡이는 vision-only 구간이 있는 신규 로그로,
  `_vision_dRel_rate`가 grace 이내에서 리셋되지 않고 유지되는지
  + 카메라 인식→레이더 락온 급감속 재현 빈도가 줄었는지 확인 필요.
  개선안 1/2번(TTC 캐션 문턱 완화 / closing-rate 절대값 게이트) 대신
  "레이더 락온 시 취급을 vision_dRel_rate 수렴 후에도 동일 적용"
  (`process_lead()`의 `lead.vLead`에 보정값 주입) 방향은 여전히
  설계 단계, 코드 미착수.

## c3-ms-dev (구버전 기록)
- last_analyzed_commit (22차-2, 코드 작성): `34227e9` (로컬 커밋,
  base `1f9f852`. **실차 미적용** — patch 파일
  `/mnt/user-data/outputs/0001-long_mpc-vision-closing-rate-leadStatus.patch`
  전달, 사용자 `git am` 적용 대기.)
- note: (22차-2) 사용자가 22차에서 제안한 개선안 3번(leadStatus 짧은
  깜빡임에 `_vision_dRel_rate` 리셋 안 하고 LEAD_ACQ_LOSS_GRACE_TIME
  grace 적용)을 "무조건 적용" 지시 → `long_mpc.py` L529-577 재작성
  완료. 기존 코드가 ramp bookkeeping의 grace 로직(L517-524)과 별개로
  vision closing-rate 블록(L534-543)에서 leadStatus=False 프레임마다
  무조건 리셋해 grace를 무력화하던 걸 확인, radar 락온/grace 초과
  진짜 유실/grace 이내 blip 3갈래로 분기하도록 수정. `py_compile`
  통과. 개선안 1/2번(TTC 캐션 문턱 완화, closing-rate 절대값 게이트)은
  사용자가 "좀더 생각해보라"며 보류, 대신 "레이더 인식 시 로직을
  그대로 적용하면 안 되나" 제안 → `process_lead()`가 `lead.vLead`
  (절대속도)를 그대로 MPC 예측에 쓴다는 걸 확인, radard.py가
  레이더 락온 시 "이미 안정적인 실측값이므로 그대로 사용"하는 것과
  같은 취급을 vision_dRel_rate 수렴 후에도 적용(= MPC 예측 자체에
  보정된 v_lead를 반영, 현재는 TTC floor로만 간접 사용 중)하는 4번안
  아이디어로 재구성해 다음 세션에 상세 설계 제안 예정 — **코드 미착수**.

- last_analyzed_commit (22차 기록): `1f9f852` (HEAD, 신규 커밋 없음 —
  22차도 코드 분석이 아니라 route1/route2(21차와 동일 로그, dashcam
  zip 재업로드) 재스캔 + 영상 프레임 대조)
- date: 2026-08-20 (22차)
- note: (22차) 사용자 재제보 "카메라 인식→레이더 락온 순간 급감속"
  패턴을 `vision_to_radar_crossover(highway_v_ego=0.0)`로 저속 포함
  재스캔 + radar_confirm 전후 aEgo 프로파일 자동 대조 → route2 seg5
  t=1647.00(고속 100km/h대 커브, aEgo 0→-2.28 m/s²/1.8s)과 route1
  seg9 t=1077.81(시내 68km/h, 완만한 버전) 2건 재현 확인, 둘 다
  레이더 락온 순간 vRel이 -8.0/-8.4m/s로 유사하게 점프. **원인 확정**:
  `b403d52`의 dRel 미분 추정치 자체는 실제값에 근접하지만, 원거리
  (63~120m)에서는 TTC=dRel/rate가 물리적으로 LEAD_ACQ_TTC_CAUTION
  (6.0s)을 못 넘어 무시됨(구조적 한계) + `leadStatus` 짧은 깜빡임마다
  `_vision_dRel_rate`가 리셋되는 부작용도 신규 확인. 개선안 3가지
  제안(캐션 문턱 완화/closing-rate 절대값 게이트/리셋에 grace 적용) —
  **사용자 결정 대기, 코드 미작성**. `extract_dashcam_frames.py`로
  route2 t=1644.75/1646.95/1648.36 프레임 확보, `evidence/
  vision_radar_ttc_limit/`에 3장 저장. 상세는 FINDINGS.md/
  PARAMS_REGISTRY.md 22차 참고.

- last_analyzed_commit: `1f9f852` (HEAD, 20차 CarrotWeb 로그탭
  새로고침 버튼 패치 실차 `git am`+push로 반영 확인 —
  `7b4a160..1f9f852`. 커밋 분석 트랙과는 별개, UI 기능 추가.)
- date: 2026-08-20 (20차)
- note: (21차, 별도 트랙 — 실주행 로그 분석) HEAD `1f9f852` 기준,
  어제 세션에서 적용된 커브/vturn 관련 패치들(vturn_lookahead_horizon_s
  8.0s, vturn_decel_rate/safe_time 물리공식, model 게이팅) 첫 실주행
  로그 2개 라우트(route1 `a5f42c2218`, route2 `4fe653914c`, 각
  x19seg/19.0분) 분석 완료 — 종방향 전부 클린(harsh_brake ADAS중
  0/0, turn_speed_violation 0/0), route2에서 100km/h대 고속 vturn
  감속 실측 최초 확보(저크 없이 매끈). 상세는 FINDINGS.md 21차 참고,
  PARAMS_REGISTRY.md vturn_lookahead_horizon_s/vturn_decel_rate
  PARTIALLY_VALIDATED로 격상.
- note: (19차) 18차에서 사용자가 제보한 "정지 버튼 -> ui 크래시 의심"
  이슈, 실차 `/data/log/swaglog.0000000915`로 원인 확정: 크래시가
  아니라 `Watchdog timeout for ui (exitcode None) restarting` —
  `stop_locked()`(UI 메인 스레드)가 직접 호출하는
  `extract_trailing_clip()`의 `QProcess::startDetached("ffmpeg", ...)`
  가 posix_spawn/vfork 기반이라 exec 완료까지 UI 메인 스레드를
  블로킹, watchdog(5s) 초과로 SIGKILL+재시작. `extract_trailing_clip()`
  호출을 `std::thread(...).detach()`로 분리하는 패치를 사용자가
  실차에서 `git am` 적용 + `git push` 완료 확인(원격 커밋 `7b4a160`).
  **실측 검증까지 같은 세션에서 완료**: swaglog watchdog 로그 0건,
  `_clip.mp4` 2건 정상 생성, 정지 버튼 화면 즉각 반응(스플래시 재현
  안 됨) — 3항목 전부 통과로 이슈 완전히 해소. 상세는 FINDINGS.md
  "[VALIDATED]"/WIP.md 19차 참고.

- last_analyzed_commit (17차 기록): `591f219` (HEAD, 신규 커밋 없음 — 17차도 코드
  분석이 아니라 실주행 로그 재검증)
- date: 2026-08-20 (17차)
- note: (17차) 16차에서 손상됐던 zip 2개를 사용자가 정상본으로
  재업로드(같은 두 라우트, 이번엔 19세그 전체) — 16차 수치를
  대체하는 최종 재검증 + **vision-only closing-rate 크로스체크
  (commit `b403d52`, 6차 패치) 최초 실측 검증** 수행. (1) 13차
  model 게이팅: vturn↔model 플리커 2.16~2.58/min, 베이스라인
  대비 63~69% 감소로 재확인(16차 추정보다 뚜렷). (2) b403d52:
  highway 크로스오버(비전 먼저 인식→레이더 확인) 이벤트 자체는
  여전히 발생(route1 11건/route2 4건)하나, closing 상황(dRel_closed
  >5m) 6건 전부 레이더 확인 순간 급격한 aEgo 불연속 없이 매끈하게
  감속 이어짐 확인 — "카메라 인식 시부터 감속 시작" 의도대로 동작
  중인 것으로 보임. 단 260819-6 seg15급 초장거리(7~8초/90m대) 극단
  사례는 이번 로그에 재현되지 않아 그 등급 재검증은 못함. 코드 변경
  없음. 상세는 FINDINGS.md/PARAMS_REGISTRY.md 17차 참고.

- last_analyzed_commit (16차 기록): `591f219` (HEAD, 신규 커밋 없음 — 16차는 코드
  분석이 아니라 패치 후 첫 실주행 로그 분석, **zip 손상으로 17차에서 재검증됨**)
- date: 2026-08-20 (16차)
- note: (16차) 사용자가 dashcam zip 2개(route `4fe653914c` 15:56~16:14,
  route `a5f42c2218` 15:37~15:55, 둘 다 extract_log.py 메타로 repo
  HEAD `591f219`/patch 커밋 이후 기록 확인)를 업로드 — "이번에 패치된
  내용 위주로 분석" 요청. 두 zip 모두 중간 구간 손상(zstd CRC 불일치,
  route1은 세그5~14, route2는 세그7~9 유실)되어 손상분 제외한 정상
  구간만(9분/16분) 분석. 핵심 결과: 13차 model_turn_speed 게이팅
  패치(`119b101`) 반영 후 vturn↔model 플리커가 베이스라인 대비
  약 57~60% 감소(7.0/min → 2.78~3.0/min), turn_speed_violation 0건,
  ADAS 활성 중 harsh_brake 사실상 0건(1/62) 유지. road↔vturn/
  route↔vturn 등 나머지 쌍은 여전히 미해결 재확인. 장시간 정속 커브
  케이스(13차 알려진 한계)는 이번 로그(시내 위주)로 미검증. 코드 변경
  없음. 상세는 FINDINGS.md/PARAMS_REGISTRY.md 16차 참고.

- last_analyzed_commit (15차 기록): `591f219` (HEAD, 15차에서 `git am`+push로 반영
  확인 — `119b101..591f219`, 14차에서 작성한 screenrecord clip
  롤오버/타임스탬프 충돌 패치)
- date: 2026-08-20
- note: (15차, 코드 변경 없음, devnotes 갱신만) 14차에서 작성한
  screenrecord clip 패치(`stop_locked(auto_rollover)` 플래그 +
  `extract_trailing_clip()` stat() 충돌 체크)를 사용자가 실차에서
  `git am` 적용 + `git push` 완료 확인(원격 커밋 `591f219`, 원격
  fetch로 diff 동일 재확인). 실측 검증(20분+ 주행 시 롤오버에서 clip
  미생성 확인, 정지 버튼 clip은 정상 생성 확인)은 다음 세션 과제로
  유지.

- last_analyzed_commit (13차 기록): `119b101` (HEAD, 13차에서 `git am`+push로 반영
  확인 — `0f7575f..119b101`, 12차에서 작성한 model 게이팅 재설계 패치.
  screenrecord clip(2번 위험, 10차 WIP)은 이번에도 미착수)
- date: 2026-08-20
- note: (13차, 사용자 "저장" 체크포인트 요청) 12차에서 작성한
  model_turn_speed 추세 기반 게이팅 패치를 사용자가 실차에서 `git am`
  적용 + `git push` 완료 확인(원격 커밋 `119b101`, 로컬 재현 커밋
  `7cdc20b`와 diff 내용 동일). 코드 변경 없음(이번 세션은 devnotes
  갱신만). 실측 검증(장시간 정속 커브에서 model 조기 배제 여부)은
  다음 세션 최우선 과제로 유지.

- last_analyzed_commit (12차 기록): `0f7575f` (HEAD 기준 동일, 로컬 신규 커밋 `7cdc20b`는
  아직 실차 미적용 — git am 대기 중이라 HEAD로 취급하지 않음)
- note: (12차, 같은 세션 이어감) 11차에서 발견한 위험 2건 중 model
  게이팅 건에 대해 사용자가 개선 방향 1번(model_turn_speed 자체 추세
  기반) 채택 지시 → 패치 작성 완료(`7cdc20b`, base `0f7575f`).
  `desiredCurvature`(현재 곡률) 기준 게이팅을 제거하고, model_turn_speed
  값 자체가 hold_sec(0.6s) 동안 노이즈 허용폭(0.3km/h)을 넘는 감소
  없이 유지/반등할 때만 "트레일링"으로 판단해 배제하도록 재설계.
  `py_compile` 통과, `git am` 적용 시뮬레이션 통과. **실차 미적용** —
  패치 파일 `/mnt/user-data/outputs/0001-carrot_serv-model-desiredCurvature-model_turn_speed.patch`
  전달, 사용자 `git am` 적용 대기. screenrecord clip 건(2번 위험)은
  이번 세션에서 미착수, 다음 세션 후보로 유지.

- last_analyzed_commit (11차 기록): `0f7575f`
- note: (11차, 코드 리뷰 세션) `1fca82f..0f7575f` 신규 커밋 2개(`2226db7`
  model_turn_straight_gate, `0f7575f` screenrecord clip) 전체 diff
  재검토. 코드 변경 없음(리뷰만) — 두 커밋 모두 이미 실차 적용+push
  완료된 상태에서, 로직 재검토로 기존에 기록 안 됐던 위험 2건을 새로
  발견해 FINDINGS.md에 `[RISK_IDENTIFIED, NEEDS_VALIDATION]`로 추가:
  1. `2226db7`의 desiredCurvature 게이팅이 "커브 진입 전 model
     사전감속"까지 억제할 수 있음(현재값 vs 예측값 혼동).
  2. `0f7575f`의 clip 추출이 20분 자동 세그먼트 롤오버에서도 반복
     실행됨(정지 버튼 전용이 아님).

- last_analyzed_commit (10차 이전 기록): `1fca82f`
- note: `1fca82f` = 8차 세션에서 만든 vturn_lookahead_horizon_s
  6.5s→8.0s 패치(로컬 커밋 `c4e3093`)가 `git am`+`git push`로 반영된
  커밋 (`4c15987..1fca82f`). 1차(4.5s→6.5s, `4c15987`)에 이은 2단계
  확대. 신규 분석 대상 아님(우리가 만든 패치), 참고용 기록만.
- note: 8dbed620887b 이후 신규 커밋 1개(3660091, CarrotWeb gdrive 재진입/
  핸드셰이크 타임아웃) 확인했으나 이미 FINDINGS.md에 기록된 이슈라 재분석
  생략. 대신 x11seg 실주행 로그 분석 수행 — LEAD_ACQ_LOSS_GRACE_TIME
  NEEDS_VALIDATION 갱신, 정지 리드 추종 클린 케이스 기록. 상세는
  FINDINGS.md/PARAMS_REGISTRY.md 참고.
  같은 날 x16seg(16.44km/955s) 라우트 추가 분석 — 종방향 harsh brake
  15건 전부 운전자 개입(cruiseEnabled=False) 확인해 ADAS 활성구간
  급제동 0건, 근접 컷인 유사 이벤트 매끈한 반응 확인, carrot_serv.py
  speed_n_sources min() 히스테리시스 부재로 인한 src/desiredSpeed
  플리커 신규 발견, LEAD_ACQ_LOSS_GRACE_TIME 5번째 초과 샘플 확보.
  코드 변경 없음(관찰/분석만).
  2026-08-20: f7b1546(system/loggerd MAX_SEGMENTS_PER_ROUTE 40->20,
  carrotweb 로그탭 라우트당 세그먼트 수 축소 요청 대응) master가 patch
  적용 + push 완료, HEAD 반영. 실기기 검증(라우트 20개 단위 분할 확인,
  carrotweb 로그탭 표시 확인)은 아직 NEEDS_VALIDATION — FINDINGS.md
  참고.
  2026-08-20 (같은 날, 2차): 신규 커밋 없음(HEAD f7b154638cf2 그대로) —
  라우트 260819-1(x20seg, 25.6km/1200s) 실주행 로그 분석 수행. 코드
  변경 없음(관찰/분석만). 주요 발견 2건: (1) LEAD_ACQ_LOSS_GRACE_TIME
  0.5s 초과 사례 6~7건 신규 확보(유실시간 최대 2.46s로 확대) + 정차열
  중 dRel 8~12.5m 감소 재포착 신규 패턴(리드 대체 의심). (2)
  speed_n_sources 플리커가 국도뿐 아니라 고속 커브 전반에서 재현
  (A→B→A 패턴 49건). harsh brake/turn violation/steering
  oscillation/cut-in은 전부 클린. 상세는 FINDINGS.md/PARAMS_REGISTRY.md
  참고.

  2026-08-20 (3차): 라우트 260819-2(x20seg, 10.29km/1199.9s, 시내/정체
  위주, avg 30.9km/h) 실주행 로그 분석. 코드 변경 없음(관찰/분석만).
  주요 발견 2건: (1) extract_log.py가 세그먼트 파일마다 leadStatus를
  False로 강제 초기화하는 버그 확인 — 순간유실 16건 전부 세그먼트 경계와
  타임스탬프 완전 일치(diff=0.000s), 실제 리드 유실 아닌 도구 아티팩트.
  LEAD_ACQ_LOSS_GRACE_TIME 관련 과거 누적 증거 재검토 필요 (PARAMS_REGISTRY
  하향 조정). (2) seg24 t=1505.78~1507.88: 고속(112km/h) 순항 중 새 리드
  포착 후 leadDRel은 연속인데 leadVRel/leadVLead만 한 프레임 만에 불연속
  점프(-4.6→-26.2m/s) — 시스템 감속(-4.61m/s²까지 매끈히 상승)이 운전자
  급브레이크(-7.46m/s²) 개입으로 이어짐. TTC가 DANGER(2.5s) 문턱을 못
  넘은 채 반응 강도가 유지된 점, LeadBlend 게이트가 dRel 점프만 감지해
  이런 vRel-only 불연속을 놓칠 수 있는 점 신규 확인 — NEEDS_VALIDATION.
  그 외: harsh_brake 45건 전부 운전자 브레이크 개입 중(cruiseEnabled 무관),
  turn_speed_violation 0건, steering oscillation 0건, cut-in 12건 전부
  저속(<7m/s) 정체구간, speed_n_sources 플리커 330건(기존 이슈 재확인,
  신규 아님). 상세는 FINDINGS.md/PARAMS_REGISTRY.md 참고.

  2026-08-20 (4차): 신규 커밋 없음(HEAD f7b154638cf2 그대로) — 라우트
  260819-3 분석. zip 안에 route ID가 다른 두 부팅 세션이 섞여있어
  route3a(6ef53b224d, x15seg, 15.58km/894.9s)/route3b(ba55f880d1,
  x5seg, 3.53km/301.5s)로 분리 추출. 코드 변경 없음(관찰/분석만).
  harsh_brake ADAS 활성 중 0건 계속 재확인, turn_speed_violation 0건.
  extract_log.py 세그먼트 경계 아티팩트 13건 추가 재확인(패치 미적용
  상태 그대로). 저속 리드 대체 패턴 36m 점프 극단 사례 확보했으나
  해당 구간 cruiseEnabled=False(운전자 수동 주차)라 제어 영향 없음.
  steering_oscillation_detector 오탐 2건 유형 확인(급커브 단일 S자
  조향 vs 운전자 수동 조작) — 탐지기 개선 여지 기록. 상세는
  FINDINGS.md/PARAMS_REGISTRY.md 참고.

  2026-08-20 (5차): 신규 커밋 없음(HEAD f7b154638cf2 그대로) — 라우트
  260819-4(x20seg, route ID `ba55f880d1` seg5~24, 19.0km/1200.2s,
  route3b의 직접 연속분) 분석. 코드 변경 없음(관찰/분석만).
  harsh_brake 22건 전부 단일 정차 이벤트(disengage/re-engage로 교차
  검증) — ADAS 활성 중 급제동 0건 5개 라우트 연속 재확인.
  turn_speed_violation/cut-in/steering_oscillation 전부 0건.
  LEAD_ACQ_LOSS_GRACE_TIME: 단기 유실 8건 중 세그먼트 경계 아티팩트는
  1건뿐, 나머지 7건은 진짜 유실(0.5s 초과 5건 포함) — 재검토 판단에
  실사례 비중 근거 추가. 신규 관찰: dRel/vRel 대형 불연속 점프 26건이
  LeadBlend 게이트 임계값을 훨씬 초과함에도 급제동 없이 무해하게
  해소(260819-2 seg24의 문제 사례와 대조되는 반례). 상세는
  FINDINGS.md/PARAMS_REGISTRY.md 참고.

  2026-08-20 (6차, 260819-5): 신규 커밋 없음(HEAD f7b154638cf2 그대로) —
  라우트 260819-5 분석. route5a(`ba55f880d1` seg25~39, x15seg,
  route3b/260819-4 직접 연속분)+route5b(신규 `dc8bdc7d4d` seg0~4,
  x5seg). 코드 변경 없음(관찰/분석만). route `ba55f880d1`가
  seg0(260819-3)~seg39(260819-5)까지 끊김 없이 40개 세그먼트로 이어진
  걸 보고 MAX_SEGMENTS_PER_ROUTE=20 패치 실기기 미반영 반증으로 처음
  판단했으나, **정정**: 로그 시각(8/19 12:41~13:00)이 패치 커밋
  f7b154638cf2(8/20 00:57)보다 이전이라 40개 동작이 정상이었음(오판,
  FINDINGS.md [WONTFIX] 정정 기록 — 진짜 검증은 패치 이후 로그로
  다시 필요). 그 외: harsh_brake ADAS 활성 중 0건 7개 라우트
  연속 재확인, turn_speed_violation 0건, LEAD_ACQ_LOSS_GRACE_TIME
  route5a real 1건(무해 해소), route5b는 real 유실 다수 확인됐으나
  전부 cruiseEnabled=False 구간이라 표본 부적합. dRel/vRel 원거리
  요동 노이즈 재확인. 상세는 FINDINGS.md 참고.

  2026-08-20 (7차, 260819-6): 신규 커밋 없음(HEAD f7b154638cf2 그대로) —
  라우트 260819-6 분석. route6a(`dc8bdc7d4d` seg5~22, x18seg, route5b
  직접 연속분, 8.57km/1043.2s)+route6b(신규 `f7e0bb3abd` seg0~1,
  x2seg, 0.4km/121.6s). 코드 변경 없음(관찰/분석만). **주 목적: 사용자가
  제기한 "커브 탈출 후 재가속 지연" 가설을 `curve_exit_no_accel_scan`
  으로 검증 시도했으나, 후보로 뽑힌 이벤트를 프레임 단위로 대조한
  결과 전부 오탐(선행차 추종 정차 감속 또는 S자 연속커브 재진입을
  "커브 탈출"로 오판)으로 확인 — 가설을 확증도 반증도 못함. 스캔
  도구에 leadStatus 필터/직선 지속시간 조건 추가하는 개선 방향
  제안(코드 미착수).** 그 외: harsh_brake ADAS 활성 중 0건 8개 라우트
  연속 재확인, turn_speed_violation 0건. LEAD_ACQ_LOSS_GRACE_TIME
  스캔에서 6~36초짜리 긴 유실 다수 신규 발견했으나 개별 대조 결과
  전부 무해(개활도로 선행차 소실 또는 저속 코너 시야이탈, vturn이
  코너 중엔 이미 저속 유지 중이라 리스크 없음) — PARAMS_REGISTRY
  판단 변경 없음. MAX_SEGMENTS_PER_ROUTE 검증용 로그(패치 커밋 이후
  기록분)는 이번에도 미확보(로그 시각이 패치보다 이전). 상세는
  FINDINGS.md 참고.

  2026-08-20 (8차, 260819-7): 신규 커밋 없음(HEAD f7b154638cf2 그대로) —
  라우트 260819-7 분석. route `f7e0bb3abd` seg2~23(x22seg, route6b의
  직접 연속분, 32.73km/1319.9s, avg 89.3km/h — 이번 로그부터 처음으로
  고속도로 위주 구간 확보). 코드 변경 없음(관찰/분석만, 단
  `toolkit/analysis_helpers.py`에 `curve_exit_no_accel_scan_v2` 함수
  추가는 완료). **주 목적: "커브 탈출 후 재가속 지연" 가설 재검증.**
  v2(leadStatus 필터+직선유지 조건) 스캔으로 오탐 1건 추가 배제했으나,
  남은 후보를 프레임 대조한 결과 3번째 오탐 패턴(vCruiseCluster 캡으로
  이미 목표속도 근접, 가속할 여지 자체가 없었던 상황) 신규 확인 — 가설은
  이번에도 확증/반증 못함, v3 개선 방향(목표속도 여유폭 필터) 제안.
  부가: 커브 진입 중(아직 안 끝난 상태) vturn 감속이 진행 중인데 운전자가
  브레이크로 개입한 신규 패턴 1건 발견(표본 1건, INVESTIGATING) — 곡률
  조임 속도 대비 vturn_decel_rate/lookahead가 충분한지 의문 제기.
  코드 리딩 중 PARAMS_REGISTRY의 vturn_decel_rc/accel_rc 값이 구버전
  기록(0.25/0.6)이라 현재 코드(0.15/0.15, a94a58b 재설계 반영)와
  불일치함을 확인해 정정. 그 외: harsh_brake 12건 중 11건은 기존 패턴과
  동일(disengage 인접), 1건은 위 신규 패턴. turn_speed_violation 0건,
  steering_oscillation 0건. LEAD_ACQ_LOSS_GRACE_TIME 0.5s 초과 6건
  전부 고속 개활도로/완만한 커브 상황 무해 재확인. 상세는 FINDINGS.md/
  PARAMS_REGISTRY.md 참고.

  2026-08-20 (9차, 260819-8, 사용자 "체크포인트" 요청): 신규 커밋
  없음(HEAD f7b154638cf2 그대로) — 라우트 260819-8 분석. route8a
  (`f7e0bb3abd` seg24~39, x16seg, 260819-7 직접 연속분, 27.27km/959.9s,
  avg 102.3km/h) + route8b(신규 `da28883b75` seg0~4, x5seg,
  5.93km/272.0s, 시내 저속 혼합). 코드 변경 없음(관찰/분석만).
  **route8a는 harsh_brake/turn_speed_violation/steering_oscillation/
  cut-in/curve_exit_v2 전부 0건 — 지금까지 중 처음으로 전 카테고리
  클린한 순수 고속도로 라우트.** 커브 콘텐츠 자체가 거의 없어(curvature
  threshold 초과 39/19145 프레임) 커브 관련 가설 2건(탈출 후 재가속
  지연/진입 중 과소감속) 모두 이번 세션엔 진전 없음. route8b harsh_brake
  16건은 disengage 직후 저속 정차 감속으로 기존 패턴과 동일(신규 아님).
  LEAD_ACQ_LOSS_GRACE_TIME: route8a에서 기존 최대(2.46s)를 크게 넘는
  긴 유실(최대 222.85s) 다수 확인했으나 harsh_brake 등 다른 지표가
  전부 0건이라 고속도로 선행차 부재로 판단, 무해. MAX_SEGMENTS_PER_ROUTE
  관련 참고 관찰 추가(route `f7e0bb3abd`가 정확히 40세그먼트 후 boot
  변경과 함께 종료 — 캡 발동인지 우연한 재부팅 겹침인지 로그만으론
  구분 불가, 여전히 패치 이전 시점이라 미검증). 상세는 FINDINGS.md
  참고. **사용자 요청으로 이번 세션은 여기서 체크포인트 저장** —
  WIP.md 참고.

  2026-08-20 (6차): 신규 커밋 1개 — `b403d52` (long_mpc.py, vision-only
  원거리 리드 closing-rate 크로스체크, VISION_CLOSING_RATE_TAU=1.0s/
  MIN_TIME=0.5s 신설). 사용자가 실차 `git am` + push 완료 확인
  (`f7b1546..b403d52`). 코드 상세는 FINDINGS.md "[PATCH_APPLIED,
  NEEDS_VALIDATION] 비전-only 원거리 리드 closing-rate 크로스체크"
  참고. **aEgo 실측 대조는 아직 미완료 — 다음 세션 최우선 과제.**

## c3-ms
- last_analyzed_commit: (아직 분석 안 함)
- date: -
- note: -

## c3-atune
- last_analyzed_commit: (아직 분석 안 함)
- date: -
- note: -
