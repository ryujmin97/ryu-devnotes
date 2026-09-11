# CURRENT_STATUS.md

이 파일은 `ryu`/`ryu-devnotes`의 **현재 상태 스냅샷**이다. WIP.md처럼
회차별 누적 이력을 담지 않고, 매 세션 종료 시점의 "지금 어디까지 왔고
무엇이 남았는지"만 최신 상태로 덮어쓴다(WIP.md/FINDINGS.md와 달리
append-only 원칙 적용 안 함 -- 항상 최신 1개 스냅샷만 유지).

새 세션(Claude/ChatGPT 무관)은 WIP.md 최신 회차를 읽기 전에 이 파일을
먼저 확인해 전체 그림을 빠르게 파악할 것.

---

## 코드 상태 (2026-09-11, 363차 종료 시점)

**Repository**: `ryujmin97/ryu`
**Branch**: `c3-ms-dev`
**HEAD (GitHub 기준, fresh clone으로 이번 세션 직접 확인)**: `bd21c7e`
(359차, `get_path_after_distance()` 300m 캡 오버런/경로반전 버그 수정).
**358차/359차 패치 모두 push 완료 확인**(360차가 push 사고 복구 완료).
362차/363차는 `ryu` 코드 변경 없음(analysis-only, offline replay만).

**Repository**: `ryujmin97/ryu-devnotes`
**Branch**: `main`
**HEAD (fresh clone으로 이번 세션 직접 확인)**: `b4f5b4b`(362차 계속2,
게이트 설계 확정 체크포인트)까지 push 완료 확인. 이번(363차) devnotes
갱신(WIP/FINDINGS/이 파일/toolkit)은 이 세션 종료 후 push 대기 중.

---

## ⏳ 363차 완료 -- 362차 계속2 "크기-비율 게이트"(RATIO) 회귀검증, 재설계 필요로 판정

362차 계속2가 남긴 미확정 항목(`RATIO` 값)을 대체 corpus(`0000039a--
7b602ffb85` seg12-16, R≈20~35m급 실제 급커브)로 회귀검증. 결과:
RATIO=0.3/0.5 둘 다 실제 급커브 검출을 광범위하게 파괴함을 실측 확인
(R<30m 급커브 1,140프레임 기준 생존율 각각 7%/1%) -- **RATIO 단독
크기-비율 게이트는 채택 불가**. 362차 원 문제(고속도로 완만한 커브
과감속)는 여전히 미해결, 게이트 설계 자체의 재검토가 다음 세션 과제.
상세: WIP.md/FINDINGS.md 363차. 코드 패치 없음, 실차 검증 해당 없음
(게이트가 `ryu`에 반영된 적 없음).

---

## ✅ 361차 완료 -- 358차/359차 실차 검증 (신규 실차 로그, 20세그/20분)

사용자가 업로드한 신규 실차 로그(route `000003ea--90dc575e96`,
2026-09-11 14:04~14:23, 최고 112km/h)로 두 미검증 패치를 검증:

- **device gitCommit=`bd21c7e4a87f`**(359차, `ryu` HEAD와 완전 일치)
  확인 -- 이 로그는 358차+359차 패치가 모두 반영된 최신 빌드에서 채록됨.
- **359차(300m 캡 오버런/경로반전) -- 실차 검증 완료, 재발 없음 확인**:
  `routePathLen==3`(617건) 전부 `apexDist=0`/`apexSpeed=0`(정상 INERT),
  버그 시그니처(경로반전+대폭 요동)는 전체 로그에서 미관측. 직선
  고속도로 구간 route 개입 5개 클러스터 전부 정상적 단조 접근 패턴.
- **358차(carrotMan 0Hz staleness E') -- 정상 부팅/주행 확인, fallback
  자체 트리거는 미검증**: `carrotMan` 발행 gap이 20분 내내 안정
  (max 0.0887s, `sleep(1)` 예외 경로 0건) -- fallback이 발동할
  상황 자체가 이 로그에 없었으므로 "정상 동작에 지장 없음"은 확인됐으나
  "fallback 코드가 실제로 올바르게 동작하는지"는 여전히 별도 검증 필요.

상세: WIP.md 361차 참고.

---

## ⏳ 359차 -- route lookahead 300m 캡 오버런/경로반전 버그 -- 코드 구현+검증 완료, 실차 반영 대기

직선 고속도로에서 `routeApexDist`/`routeApexSpeed`가 프레임마다 급격히
요동하는 증상의 근본원인을 확정: `carrot_man.py::get_path_after_distance()`가
첫 세그먼트를 300m 캡 체크 없이 무조건 추가하는 버그로, 첫 세그먼트
자체가 이미 300m를 넘으면(직선 구간 raw waypoint 간격이 넓을 때) 경로가
국소적으로 반전됨. 첫 세그먼트도 나머지와 동일한 캡 로직을 적용하는
최소변경(§27)으로 수정, `sim_route_359_lookahead_overrun.py`(신규)로
버그재현/회귀방지 두 시나리오 모두 PASS 확인. 패치 검증(§6/§7:
throwaway clone -> `git apply --check` -> `git am` -> `py_compile` ->
byte-identical diff) 완료. **실차 검증: 미실시.**

상세: WIP.md/FINDINGS.md 359차 참고.

**다음 세션 최우선**: 358차 -> 359차 순서로 패치 적용/push 후, 실차에서
(a) 358차 fallback 정상 동작(정상 부팅 최우선), (b) 직선 고속도로
구간 route 오개입/요동 해소 두 가지를 함께 확인.

---

## ⏳ 358차~358차 계속3 진행 상황 -- `carrotMan` 0Hz staleness 보호(E') -- 코드 구현 완료, 실차 반영 대기

356차가 발견한 "`alive['carrotMan']`가 구조적으로 상시 True"(0Hz 등록
+ 실제 20Hz 발행 불일치) 문제에 대해 E'(소비처 5곳 `recv_time` 기반
로컬 staleness 체크, capnp 필드 추가 불필요)로 설계 확정 후, 358차
계속3에서 실제 코드 구현 및 패치 생성/검증까지 완료:

- `controls/controlsd.py`(L191 `vTurnSpeed`/L264 `desiredSpeed`),
  `controls/lib/lateral_planner.py`(L101 `vTurnSpeed`),
  `car/cruise.py`(L291), `selfdrived.py`(L251),
  `carrot_functions.py`(L442) 5개 파일 수정.
- `CARROT_MAN_STALE_S = 1.5`(provisional, 사용자 결정) -- 파일별 로컬
  상수, 공유 helper 모듈 신설 없음.
- `desiredSpeed` capnp 기본값 0 부팅 직후 latent 위험도 이번 fallback
  으로 함께 해소.
- 패치 파일: `0001-358cha-carrotman-E-prime-5-consumers.patch`
  (base `40ed6d9`). §6 절차(throwaway clone -> `git apply --check` ->
  `git am` -> `py_compile`) 전부 통과 확인.
- **실차 검증: 미실시** -- 사용자가 패치 적용/push 후 다음 세션
  최우선으로 확인 필요(정상 부팅 여부가 최우선).

**남은 것**:
1. 사용자 패치 적용 -> push -> 실차 재부팅/주행으로 정상 동작 확인
2. `CARROT_MAN_STALE_S=1.5`는 provisional -- 실제 `sleep(1)` 발현
   corpus 확보 후 재평가(폐기 대상 아님)
3. B/C/D안(`broadcast_version_info()` try 격리 등, E'와 병행 가능한
   별개 개선)은 이번에 다루지 않음, 보류 유지

상세: WIP.md 358차/358차 계속/358차 계속2/358차 계속3, FINDINGS.md
358차(6번 항목) 참고.

---

## ✅ 357차 완료 -- 356차 보안 발견 후속 처리

1. **[해결+실차검증 완료]** ZMQ 7710 `echo_cmd`/`tmux_send` 무인증 원격
   명령실행 -- CarrotMan/APM 앱 미사용 확인(Master), caller 부재
   확정 -> `carrot_man.py`(`c39d81f`)에서 핸들러 제거, 패치전달 완료.
   **실차 검증: 완료(357차 계속)** -- 재부팅 포함 실차에서 `carrot_man`
   정상 기동 확인(Master 보고). 이 항목은 완전히 종결.
2. **[Master 확인, 위험 수용]** `carrotweb`(port 7000, 실사용 중)의
   `/api/*`/`/ws/terminal` 전체가 무인증 상태(임의 쉘 실행/reboot/
   git·pip 실행/Params 변경 가능, `always_run`으로 상시 기동)임을
   357차에서 신규 발견. Master가 잔여 리스크(집 와이파이 연결 중에도
   포트 상시 개방)까지 설명 들은 뒤 "핫스팟에서만 접속, 집에서는 작업
   안 함"을 근거로 **문제없음으로 최종 확인 -> 코드 미수정**(FINDINGS.md
   357차 참고). 향후 네트워크 사용 패턴이 바뀌면 재검토 필요.
4. **[해결, 357차 계속2]** `send_routes()` 도달불가 분기 -- route
   activation 자체는 정상(356차 확정 유지). 원격 HEAD 재확인 결과
   `active_carrot` 승격은 이 분기와 무관한 별도 SDI 채널(UDP 7706,
   `carrot_serv.update()`)이 전담함을 신규 확인 -> corpus 검증 없이
   dead code 제거 진행(코드 결론만으로 충분 판단, 사용자 승인).
   `carrot_man.py`에서 `if not from_navd:` 블록 제거, 패치전달 완료.
   **실차 검증: 미실시**(기능 영향 없는 순수 정리라 우선순위 낮음).
5. 20Hz 메인루프(`broadcast_version_info`) 전체가 단일 try-except --
   예외 1건 발생 시 최대 1초 갱신 중단. 구조 개선 논의 필요.
6. `vturn_speed()` alive 조건이 AND -- `carState`/`modelV2` 둘 다
   죽어야만 스킵. 조건식 의도 재검증 필요(크래시 위험은 없음).
7. `server/core.py:1945` NameError 유발 가능 버그(aiohttp 미임포트) --
   대시보드 웹소켓 전용, 제어로직 무관, 경미.

상세: WIP.md/FINDINGS.md 356차 참고.

---

## 이전 코드 상태 요약 (2026-09-10, 355차 종료 시점 기준)

354차가 사용자의
로컬 적용/push 완료를 fresh clone으로 직접 확인했고, 이번 355차 세션
시작 시 fresh clone으로 재확인 -- 이 섹션이 이전까지 "패치 미적용
(`da7ab36f`)"로 표기돼 있던 것은 354차 확인 이후 갱신 누락된 stale
기록이었음(§33, 이번에 정정).

**Repository**: `ryujmin97/ryu-devnotes`
**Branch**: `main`
**HEAD**: `f0eba025` (354차 devnotes 기록, 이번 355차 세션 시작 시
fresh clone으로 확인). 355차 devnotes(이 파일 포함 WIP 갱신)는 이 세션
종료 후 push 대기 중.

---

## 지금 진행 중인 핵심 이슈: route ACTIVE 릴리즈 조건 튜닝

### 배경 (341~342차)
직선구간에서 route가 짧게 켜졌다 꺼지는 flapping 현상의 원인을 실측
로그로 추적 -- ACTIVE 릴리즈 OR-조건 중 `speed_reached`
(`v_ego_kph<=apex_speed*1.05`)가 전체 flapping의 61.1%를 차지함을
확인. `speed_reached`+`v_ego_ms<=target_ms` 동시 제거 시 route가 vEgo
초과 속도(가속)를 오명령하는 위험한 회귀가 재현됨을 what-if
시뮬레이션으로 확인.

### 원인 국소화 (342차 계속)
가속 오명령 위험은 `v_ego_ms<=target_ms`가 있는 두 지점(ACTIVE STEP2
분기 / INERT 진입게이트) 중 **ACTIVE STEP2 분기 하나**에서만 발생.
INERT 진입게이트는 건드려도 이 로그 기준 무변화(사실상 dead branch).

### 코드 반영 (343차, 완료)
`carrot_man.py` ACTIVE 릴리즈 OR-조건에서 `speed_reached`만 삭제
(`v_ego_ms<=target_ms`는 그대로 유지)하는 패치를 사용자 승인 하에
`ryu`에 실제 적용, HEAD `da7ab36f`. what-if 시뮬레이션 기준 릴리즈
47->35건, flapping 33->21건 감소 확인했으나, route_active 개입 비율은
3.2%->6.2%로 증가하는 트레이드오프 있음. **실차 검증: 미실시**로 종료.

### 사용자 질문 + 실측 검증 (344차, 완료) -- ⚠️ 중요 발견 포함
사용자가 "① 앞차 서행/신호로 속도<목표속도인 상황",
"② 좌회전 apex에서 신호대기 정지한 상황"에서 route release 여부를
질문 -> 코드 분석으로 답변 후, 재업로드 실측 로그로 검증.

**⚠️ 핵심 발견**: `check_device_build.py`(git 메타데이터)와
`verify_release_variant_344.py`(텔레메트리 재생, 신규 toolkit
스크립트) 두 독립적 방법 모두, 이번에 검증에 쓰인 로그가 **343차
패치 적용 이전 코드**(device gitCommit=`7b3dfec4`=336차, dirty=True)로
기록됐음을 확인. 즉 343차 패치가 아직 실제 디바이스에 반영되지 않은
것으로 보임.

- 시나리오① 실측 확인됨(t=1294.2s/1297.1s, speed_reached 단독으로
  release) -- 341/342차 flapping 메커니즘의 실제 발현 사례. 다만
  343차 패치 적용 후 이 release가 실제로 사라지는지는 **아직
  미확인**(구코드 로그였으므로).
- 시나리오② 실측 확인됨(t≈1406~1530s, apex_dist=0.0 고정 상태로
  100초 정지, dist_reached 상시 충족 -> release 유지) -- 기존
  "322차 계속, 원인 B"의 부동소수점 zero-crossing flicker와 동일
  현상, 새로운 문제 아님.

### 다른 corpus로 "강제 RELEASE=lost" 빈도 재확인 (346~347차, 완료)

346차가 x20seg 1개 corpus로 확인한 "강제 RELEASE=lost는 corpus마다
발생 여부가 갈린다"는 가설을, 347차가 사용자 재업로드분 x19/x6/x10/
x16seg(335~339차가 이미 분석했던 2026-09-09 채록 로그, 343차 패치
이전) 4개로 추가 검증. 결과: 6개 corpus 중 발생 3개(route1~4/x19seg
6건/x10seg 1건) : 미발생 3개(x20seg/x6seg/x16seg)로 corpus-의존성
가설이 보강됨. continuity 설계 전제("lost는 apex_dist>0 상태에서만
발생")는 5개 corpus 합계 401건 전부(100%)에서 예외 없이 성립. 상세는
WIP.md/FINDINGS.md 347차 참고. 이 corpus들은 343차 패치 이전
채록이므로 위 343차 실차검증에는 사용 불가 -- 별개 과제임에 주의.

### 강제 RELEASE=lost 7건 개별 route_active 재진입 트레이스 (348차, 완료)

347차가 이월한 과제 -- x19seg 6건+x10seg 1건 전부를
`sim_route_348_active_reentry_trace.py`(신규)로 개별 트레이스. **결론:
route_active 재진입은 7/7건 전부 결국 발생하나(무제한 탐색 기준),
0/7건에서 그 재진입이 즉시 재획득된 B가 살아있는 동안 일어나지 않음**
-- B는 매번 0.3~5.0s만 생존한 뒤 다시 끊기고, 그 후 0.9~95.5s 뒤에야
(대부분 원래보다 큰 apex_dist를 가진) 별도의 apex가 게이트를 통과함.
즉 "lost된 그 목표가 곧 회복된다"는 낙관적 해석은 확인되지 않았고,
재진입은 항상 "다음(별개의) 커브"에 의한 것으로 보임(간접 추론, 349차가
직접 검증). 상세는 WIP.md/FINDINGS.md 348차 참고.

### 348차 결론(재진입=별개 커브)의 qcamera 직접 검증 (349차, 완료)

348차가 간접 추론(gap 시간 + apex_dist 값)으로 남겼던 결론을 gap이
가장 긴 2건(x19seg 6번째=+95.49s, x10seg=+72.95s)에 대해 qcamera
프레임+GPS 직선거리로 직접 확인. x19seg는 아파트단지 도로 -> 가드레일
+산 배경 도로(GPS 621.6m), x10seg는 콘 구간 -> 좌회전 대형 신호교차로
(GPS 104.9m)로, 두 사례 모두 물리적으로 완전히 다른 장소임을 확인 --
"재진입은 그 apex의 회복이 아니라 다음 apex에 의한 것"이 직접 증거로
확정됨(기존 결론 변경 없음, 근거 보강). 나머지 gap 짧은 5건은 이번에
다루지 않음. **⚠️ 세션 중 컨테이너 재시작으로 원본 zip/추출 프레임/
합성 비교 이미지 2장이 유실**되어 이 patch에는 이미지 없이 텍스트
기록만 포함됨(§16, 필요 시 동일 corpus로 재현 가능, 재현성은 이미
2회 확인됨). 상세는 WIP.md/FINDINGS.md 349차 참고.

---

## 미확인/대기 중인 것 (다음 세션 최우선 확인 사항)

1. ~~343차 패치가 실제로 사용자 로컬에 적용/push/디바이스 재빌드까지
   완료됐는지~~ -- **350차에서 확인**: 신규 실차로그(2026-09-10 12:20
   채록, x15seg)의 device gitCommit이 343차 HEAD(`da7ab36f`)와 정확히
   일치하고, 소스 코드 직접 확인으로도 `speed_reached` 삭제가 반영되어
   있음을 재확인 -- 343차 패치는 반영된 것으로 판단. 단 **dirty=True는
   이번에도 존재**(원인 미상, 사용자 확인 필요, 아래 참고).
   `verify_release_variant_344.py`가 여전히 16건의 "speed_reached
   단독 종료"를 검출했으나, qcamera 프레임 대조 결과 커브/선행차 접근
   구간과 일치해 프록시 스크립트의 기존 한계(arbitration 오분류)로
   재해석함(잠정 결론, WIP.md 350차 참고).
   ~~**[350차 계속에서 진전]** 업스트림 미설정 가설, 다음 세션 최우선
   확인 필요~~ -- **351차에서 해결**: 기기 확인 결과 `@{u}`는
   `origin/c3-ms-dev`로 정상 설정돼 있어 350차 가설은 기각됨. 실제
   원인은 fork 내장 언어 전환 스크립트(`launch_chffrplus.sh`)가
   `LANG=main_ko`일 때 `events.py`를 매 부팅 시 `events_ko.py`로 강제
   교체하기 때문 -- git에 커밋 안 된 이 교체가 `git diff-index`에
   정직하게 잡히는 **정상 동작**임이 확정됨(번역 `.ts` 12개 diff도
   동일 계열). `ryu` 코드 수정 불필요. 178차 이후 반복된 dirty=True
   미스터리 전체가 이걸로 설명 가능. 상세: FINDINGS.md/WIP.md "351차"
   참고.
2. ~~344차 devnotes patch(`0001-344cha-devnotes.patch`)가 push
   됐는지~~ -- **350차 계속2에서 확인**: fresh clone으로 `WIP.md`/
   `FINDINGS.md`의 344차 항목, `toolkit/verify_release_variant_344.py`
   파일 실존, `toolkit/README.md`/`toolkit/CHANGELOG.md`의 344차 등록
   전부 직접 확인 -- push 완료 확정(사용자 확인 불필요, GitHub 직접
   조회로 해결).
3. ~~348차 결론 qcamera 직접 검증~~ -- **349차 완료** (gap이 긴 2건
   기준, 나머지 5건은 미실시로 남음, 우선순위 낮음).
4. 343차 패치 반영 확인 후, 동일/유사 리드차량 서행 상황을 재주행하여
   시나리오① release 소멸 여부 직접 재확인 필요 -- **350차에서 부분
   시도**: 신규 로그에 유사 교차로+선행차 케이스(t=155.65)가 있었으나
   지속시간이 1프레임(0.15s)로 매우 짧아 341/342차가 지적한 3초+
   flapping과 규모가 달라 정량 비교는 미실시. 완전한 재확인은 아직
   남음.
5. **[363차 신규]** 362차 원 문제(고속도로 완만한 커브 route 과감속)
   수정안 재설계 -- RATIO 단독 크기-비율 게이트는 363차 회귀검증에서
   채택 불가로 판정(R<30m 실제 급커브 생존율 7%/1%). 절대 곡률 임계값
   병행/시간지속성 조건 등 대안 설계 방향을 사용자와 논의 후 진행
   필요. 상세: WIP.md/FINDINGS.md 363차.

---

## CPU 부하 정리 (345차 발견, 352차 재검증, 353차 1차 패치, 354차 실차검증)

345차가 발견한 CPU 후보 6개를 352차가 현재 코드(343차 HEAD)와 전수 대조.
353차가 ①/②의 일부를 패치(§31 검증 완료). **354차: 사용자가 353차 패치
단독 적용 후 실차에서 CPU 온도 68~69도 -> 약 62도 하락 확인**(정량 CPU%/ms
실측은 여전히 미실시, 온도계 기준 관찰치).

1. ✅🔧 **`carrot_serv.py::update_params()`** -- **[353차 패치, 354차 실차검증 완료]**
   `carrot_man.py::_refresh_cached_params()`(99/100차)와 동일한 카운트다운
   캐시 패턴 적용, 18개 Params 읽기(MapTurnSpeedFactor 포함)를 20Hz 매프레임
   -> 5s(100프레임)에 1회로 전환. 패치 검증(§31) 완료. **354차: CPU 온도
   68~69도 -> 약 62도 하락 확인(실차, 단독 적용 조건)**. 정량 CPU%/ms
   실측 및 5s 캐시 지연 체감 영향 확인은 아직 남음.
   - ⚠️ 패치 중 발견: `MapTurnSpeedFactor`를 "죽은 값"이라 서술한 `[210차]`
     주석이 stale이었음 확인(`carrot_man.py` route 곡률 계산 2곳에서 실사용
     중) -- 삭제 대신 주석만 정정, 캐시 대상에 포함(FINDINGS.md 353차 참고).
2. **`make_send_message()`(Version/IsOnroad) + `gethostbyname()`** -- 3개
   하위 항목으로 분리:
   - ✅🔧 `IsOnroad`: **[353차 패치, 354차 실차검증 완료]** 이미 존재하던
     `self._is_onroad_cached`(99/100차)를 안 쓰고 중복 raw read 하던 것을
     캐시 재사용으로 교체.
   - ✅🔧 `Version`: **[353차 패치, 354차 실차검증 완료]**
     `_refresh_cached_params()`에 5s 캐시 신규 추가(`self._version_cached`).
   - 🔴 `gethostbyname()`: **[353차 명시적 보류]** `ip_address != self.ip_address`
     비교 기반 IP 변경감지/`remote_addr` 리셋 로직과 연결돼 있어, 캐싱 시
     이 감지 로직이 무력화될 부수효과 우려 -- 별도 세션에서 검토 필요.
   - 게이팅 자체(`frame%20==0 or remote_addr is not None`)는 352차 재분류대로
     내비 앱 연결 중 사실상 20Hz 유지, 이번엔 변경 안 함.
3. 🟡 orphan raw-path 문자열화(`relative_coords` 전체 join) -- 조건부(orphan
   존재 시만) 확인, 낮은 우선순위 유지(345/352/353차 일관).
4. 🟢 `route_local_curve_merge()`의 `any()` 선형탐색, `broadcast_version_info()`
   초기화 순서 문제(353차 확인: 이 함수 자체가 20Hz 메인루프이며 "race"는
   스레드 시작 시점 1회성 문제로, 반복 CPU 부하 아님) -- 우선순위 낮음/관찰 대상.
5. ✅ route 곡률 계산부(`np.interp` macro/fine 배치처리) -- 이미 Phase 1
   최적화 적용 확인, backlog 제외.

**355차: 5s 캐시 지연으로 인한 route 감속/커브 속도 반응성 체감 저하
여부 -- 사용자 직접 재주행, 체감상 이상 없음으로 확인 완료**(정성적/
주관적 확인, 정량 데이터 기반 검증은 아님, §29 원칙에 따라 구분 명시).

**다음 작업**: (선택) 정량 CPU%/ms 실측(C3 `top`/`htop` 또는 모니터링
스크립트) -- 여전히 미실시. `gethostbyname()` 캐싱 여부는 별도 세션에서
사용자 결정 후 진행.

---

## 그 외 이월 항목 (userMemories/WIP 기준, 우선순위 낮음)

- `mapTurnSpeedFactor=1.10` 보정을 `analysis_helpers.py::recompute_route_curvature_speed()`에
  반영 후 297차 파이프라인 재실행
- `routeProvisional*`/`routeOrphanSingleton*` 실차 로그로
  `PROVISIONAL_PROMOTE_STREAK`(현재 3, observation-only) 값 확정.
  **[352차 확인] 이 항목은 폐기 대상이 아님** -- 334차 미스터리는 340차에서
  `routeLocalResampleUsed` 계측으로 인과 확정됐고, 338차는 production
  실사례 6건(qcamera 확인)까지 찾아냈던 조사임. FINDINGS.md 340차가 남긴
  "클램프 코드수정 여부는 Master 확인 후 결정"이 아직 사용자 미결정
  상태로 남아있음(다른 AI(ChatGPT)가 제안한 "완전 폐기"안을 352차에서 반려).
- ep=99 에피소드 파편화(`--merge-tol=1.0s` 임계값이 ~1.10s
  `gas`-source 우선순위 핸드오프로 분리된 파편을 병합 못함) 해결
- `ContinuityApprox`에 `miss_frames` 기반 hold state 추가 후 baseline
  ratio 재검토
- `extract_log.py`에 `horizontalAccuracy` 컬럼 추가 (295차에서 이미
  FIELDNAMES에는 추가됨 -- 실측 검증 필요 여부 재확인)
- 좌회전 apex(344차 시나리오②)의 물리적 위치와 실제 정지선 간 거리
  qcamera 대조 (미실시)
- 132차 ramp limiter, 166차 heading freeze fix -- 둘 다 실차
  재주행 검증 대기(`NEEDS_VALIDATION`)
- CPU 개선후보 중 `gethostbyname()` 캐싱, orphan raw-path/`any()` 선형탐색
  -- 353차에서 명시적으로 보류(위 "CPU 부하 정리" 섹션 참고), ①/②
  일부(update_params/IsOnroad/Version)는 353차에서 패치 완료(실측 대기)

---

*최종 갱신: 361차 (Claude). 358차/359차 패치 모두 push 완료 확인(360차
복구), 신규 실차 로그(20세그/20분)로 두 항목 실차 검증: 359차(300m 캡
오버런/경로반전)는 **재발 없음 확인**, 358차(carrotMan staleness E')는
**정상 부팅/주행 확인**하되 **fallback 자체가 실제로 트리거되는
상황은 이 로그에 없어 그 코드 경로 자체의 정합성은 여전히 미검증**.
다음 세션 최우선: (1) 358차 fallback이 실제로 발동하는 corpus 확보
방안 검토, (2) 357차 계속2가 남긴 이월 후보(20Hz 메인루프 try-except
구조 / vturn_speed alive AND 조건 / server/core.py NameError, CPU
정량 실측)와 `CARROT_MAN_STALE_S` 재평가, (3) 직선 고속도로
apexSpeed 미세 진동(341차 계열, 이번 361차에서 재확인만 하고 근본원인
조사는 안 함) 우선순위를 사용자와 결정. WIP.md 최신 회차("361차")로
상세 맥락 보충.*
