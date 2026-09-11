# CURRENT_STATUS.md

이 파일은 `ryu`/`ryu-devnotes`의 **현재 상태 스냅샷**이다. WIP.md처럼
회차별 누적 이력을 담지 않고, 매 세션 종료 시점의 "지금 어디까지 왔고
무엇이 남았는지"만 최신 상태로 덮어쓴다(WIP.md/FINDINGS.md와 달리
append-only 원칙 적용 안 함 -- 항상 최신 1개 스냅샷만 유지).

새 세션(Claude/ChatGPT 무관)은 WIP.md 최신 회차를 읽기 전에 이 파일을
먼저 확인해 전체 그림을 빠르게 파악할 것.

**[369차 갱신 시 발견]** 이 파일이 363차 종료 시점에서 364~368차(5개
세션) 동안 갱신되지 않았던 것을 369차에서 재정비했다. 그 사이 WIP.md는
정상적으로 누적됐으므로 실제 작업 연속성에는 문제가 없었으나, 앞으로도
매 세션 종료 시 이 파일을 갱신할 것.

---

## 코드 상태 (2026-09-12, 371차 종료 시점)

**Repository**: `ryujmin97/ryu`
**Branch**: `c3-ms-dev`
**HEAD (GitHub 기준, fresh clone으로 371차 직접 확인)**: `d5b34bb6b358`
(367차 계속4, GitHub 저장소 자체는 아직 무변경 -- 371차 패치는 파일로만
전달됨, 사용자 적용/커밋/push 대기). 패치 적용 시 반영될 변경: L1807
(INERT, `v_ego_ms<=target_ms`)에 `ROUTE_L1807_HOLD_FRAMES=4`(0.20s)
시간기반 디바운스 히스테리시스 추가(370차 Master 결정 B3 구현,
`_route_apply_l1807_hold()` 신규 메서드, 게이트 산식 자체는 무변경).
패치 파일: `0001-371-carrot_man.py-L1807-hold-4-0.20s.patch`(git-am
호환, 별도 clone에 적용 재현 완료).

**Repository**: `ryujmin97/ryu-devnotes`
**Branch**: `main`
**HEAD (fresh clone으로 371차 직접 확인)**: `e1a9f05`(370차 완료
시점)까지 push 완료 확인. 이번(371차) devnotes 갱신(WIP/FINDINGS/
이 파일)은 이 세션 종료 후 push 대기 중.

---

## ⏳ 371차 완료 -- `carrot_man.py` L1807 hold=4(0.20s) 히스테리시스 실제 코드 패치 작성, 사용자 적용 대기

370차가 남긴 "다음 작업 1"(L1807 hold=4 실제 코드 패치 작성)을 최소변경
(§27)으로 구현: 신규 상수 `ROUTE_L1807_HOLD_FRAMES=4`, `__init__`
상태 3개, 신규 메서드 `_route_apply_l1807_hold()` 추가, L1807 조건의
raw bool을 이 메서드를 거친 확정값으로 교체하는 삽입 지점 한 곳만
변경(나머지 게이트 산식 무변경). 이 알고리즘이 370차 오프라인 검증에
쓰인 `toolkit/diag_required_decel_341.py`의 `apply_hold()`와 완전히
동일한지 None 섞인 랜덤 시퀀스 200개로 대조 -> **200/200 일치**.
`py_compile` 통과, 별도 fresh clone에 `git apply --check`+`git am`으로
patch 적용 재현도 충돌 없이 완료.

**주의**: 이번 검증은 (a) 알고리즘 동등성(합성 시퀀스), (b) 문법/patch
적용성까지이며, **이 패치가 적용된 실제 `carrot_man.py`로 370차
corpus(`22ebbb245d`)를 재생(replay)해 218건->0건을 직접 재현하지는
않았다** -- 알고리즘이 같다는 것과 실제 재생 결과가 같다는 것은 별개
확인. 341차 원 corpus(x20seg) 기준 반응지연 부작용도 미검증(§29 실차
검증 아님). 상세: WIP.md 371차/FINDINGS.md 370차 보강분 참고.

**다음 세션 최우선**: (1) 패치 적용 후 `carrot_man.py`로 370차
corpus 재생 -> 218건->0건 직접 재확인, (2) 341차 원 corpus(x20seg)로
반응지연 부작용 검증.

---

## ⏳ 369차 완료 -- 368차 251건 플래핑의 실제 근본원인 코드 위치 정정 (L1832 ACTIVE 게이트 아님, L1807 INERT 비교가 원인)

368차 "다음 작업 1"(`diag_required_decel_341.py` 정식 적용)을 동일
route(`22ebbb245d`)에 실행한 결과 **릴리즈 이벤트 0건** -- 341차 원
corpus(x20seg)와 달리 이 corpus는 ACTIVE 상태(`route_active=True`)에
**한 번도 진입하지 않음**을 확인(3,296프레임 중 ACTIVE 진입게이트
`required_decel_mss`가 평가된 프레임 0건). 원인: corpus `apexDist`
최대 140m인데 실측 vEgo(~90~100kph)에서 `target_ms *
autoNaviSpeedCtrlEnd(7.0)`이 통상 150~200m라 `eff_dist`가 항상
0으로 클램프되거나 그 전에 `v_ego<=target`(L1807, INERT 분기)이
먼저 걸림 -- 즉 368차가 지목했던 "L1832 ACTIVE 진입 게이트"는 이
corpus에는 전혀 관여하지 않는다. 실제 관여 코드는 **L1807**
(`if v_ego_ms <= target_ms:`, 히스테리시스 없는 단순 비교)이며,
grid 경계 apex_speed 스파이크가 이 조건을 1프레임만 참으로 만들어
route를 arbitration에서 순간 제외시키는 것이 251건 플래핑의 실제
메커니즘. `carrot_serv.py` L1260 교차확인으로 `src=='route'` 선택
자체는 `route_active` 내부 플래그와 무관한 순수 arbitration 결과임도
확인. 코드 수정 없음(설계 방향 Master 결정 대기). 상세: WIP.md/
FINDINGS.md 369차 참고.

**다음 세션 최우선**: L1807(INERT `v_ego<=target`)에 히스테리시스를
추가할지/어떻게 설계할지 Master 결정. L1832(ACTIVE 게이트) 히스테리시스
설계는 이번 근거리 corpus 근거로는 불필요할 수 있음 -- 별도로 341차
원 corpus(x20seg, 원거리) 기준 재검토.

---

## ✅ 368차 완료 -- 341차 확정 메커니즘, 신규 실차 제보 route(`22ebbb245d`)에서 251건 규모 재확인 (근본원인 코드 위치는 369차에서 정정됨, 위 참고)

341차가 x20seg(직선, 46건)에서 확정한 "grid 경계 apex_speed 스파이크
-> route 1프레임 드롭아웃/블립" 패턴이 신규 route(곡선구간, 251건 =
135 드롭아웃+116 블립, 98~99% grid 전환 동시발생)에서 훨씬 조밀하게
재현됨을 실측 확인. `ryu` 코드 변경 없음. 상세: WIP.md/FINDINGS.md
368차 참고. **369차에서 근본원인 코드 위치가 L1832(ACTIVE)가 아니라
L1807(INERT)임이 밝혀졌으므로, 이 항목의 "근본원인" 부분은 369차
기록을 우선 참고할 것.**

---

## ⏳ 367차 계속4 완료 -- `route_curvature_macro_fine()` 원거리 fine 대체 억제 게이트(150m) 코드 반영, 실차 검증 대기

367차 계속3이 확보한 anchor 2건(apexDist=210m, 검증된 오탐)과 오염
확인된 진짜 커브 2건(apexDist=50m/120m) 근거로 `ROUTE_FINE_OVERRIDE_
MIN_DIST_M=150.0` 상수+게이트를 `carrot_man.py`에 반영, 패치 검증
완료(§6/§7 전체 PASS). **표본 4건뿐이라 NEEDS_VALIDATION**, offline
replay 스윕은 사용자 결정으로 생략. **실차 검증: 미실시 -- 다음
세션 최우선**(362차 원 문제 해소 여부 + 원거리 실제 급커브 대응 지연
부작용 여부 동시 확인 필요). 패치: `0001-367-4-route_curvature_macro_
fine-150m-fine.patch`(base `bd21c7e4a87f`). 상세: WIP.md/FINDINGS.md
367차 계속4 참고.

---

## 362~367차 요약 (곡률 게이트 계열 -- ISOLATION/150m 게이트로 수렴)

362차가 발견한 "고속도로 완만한 커브 과감속"(fine 10m 서브샘플이
macro 40m보다 낮으면 인접 정합성 확인 없이 무조건 채택하는 구조적
결함) 문제에 대해 363차(크기-비율 게이트, 기각) -> 364차(지속성
게이트 PERSIST, 기각) -> 365차(heading ISOLATION 게이트, 유망) ->
366차(정탐 대리필터 교차검증, precision 92.2%->25kph로 100%) ->
367차/367차계속(corpus 확대, R<13m 급커브에서 ISOLATION 생존율 급락
반례 발견) -> 367차계속3/4(anchor 기반 거리 임계값 150m 도출, 코드
반영)로 이어짐. **현재 `ryu`에 반영된 것은 150m 거리 게이트뿐**
(ISOLATION 게이트는 설계 검증 단계, 코드 미반영). 상세는 각 회차
WIP.md/FINDINGS.md 참고.

---

## ✅ 361차 완료 -- 358차/359차 실차 검증 (신규 실차 로그, 20세그/20분)

- **359차(300m 캡 오버런/경로반전) -- 실차 검증 완료, 재발 없음 확인**.
- **358차(carrotMan 0Hz staleness E') -- 정상 부팅/주행 확인, fallback
  자체 트리거는 미검증**(로그에 fallback 발동 상황 자체가 없었음).

상세: WIP.md 361차 참고.

---

## ✅ 357차 완료 -- 356차 보안 발견 후속 처리

- ZMQ 7710 무인증 원격명령실행 -- 핸들러 제거, 패치전달+실차검증 완료.
- `carrotweb`(7000) 무인증 상태 -- Master가 위험 수용 확인(핫스팟
  전용 사용), 코드 미수정.
- `send_routes()` 도달불가 분기 -- dead code 제거, 패치전달 완료
  (실차 검증 미실시, 기능 영향 없는 순수 정리).

상세: WIP.md/FINDINGS.md 356차/357차 참고.

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
