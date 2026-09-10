# CURRENT_STATUS.md

이 파일은 `ryu`/`ryu-devnotes`의 **현재 상태 스냅샷**이다. WIP.md처럼
회차별 누적 이력을 담지 않고, 매 세션 종료 시점의 "지금 어디까지 왔고
무엇이 남았는지"만 최신 상태로 덮어쓴다(WIP.md/FINDINGS.md와 달리
append-only 원칙 적용 안 함 -- 항상 최신 1개 스냅샷만 유지).

새 세션(Claude/ChatGPT 무관)은 WIP.md 최신 회차를 읽기 전에 이 파일을
먼저 확인해 전체 그림을 빠르게 파악할 것.

---

## 코드 상태 (2026-09-10, 347차 종료 시점)

**Repository**: `ryujmin97/ryu`
**Branch**: `c3-ms-dev`
**HEAD**: `da7ab36f` (343차 -- ACTIVE 릴리즈 OR-조건에서 `speed_reached`
삭제, `v_ego_ms<=target_ms`는 유지)

**Repository**: `ryujmin97/ryu-devnotes`
**Branch**: `main`
**HEAD**: `95b87349` (346차 devnotes 기록) -- **344차 patch가 push
됐는지 여전히 미확인**, **347차 patch도 아직 push 대기 중**(둘 다
아래 "미확인/대기중" 참고)

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
WIP.md/FINDINGS.md 347차 참고. **이 corpus들은 343차 패치 이전
채록이므로 아래 1번(343차 실차검증)에는 사용 불가** -- 별개 과제임에
주의.

---

## 미확인/대기 중인 것 (다음 세션 최우선 확인 사항)

1. **343차 패치가 실제로 사용자 로컬에 적용/push/디바이스 재빌드까지
   완료됐는지** -- 344차가 발견한 문제의 원인. 다음 세션 시작 시 가장
   먼저 확인할 것. 347차가 검증에 쓴 x19/x6/x10/x16seg는 343차보다
   훨씬 이전(823943a6, 329차) 채록이라 **이 항목의 답이 될 수 없음**
   (혼동 방지를 위해 명시).
2. **344차 devnotes patch(`0001-344cha-devnotes.patch`)가 push
   됐는지** -- 이 patch는 `WIP.md`/`FINDINGS.md`/
   `toolkit/verify_release_variant_344.py`/`toolkit/README.md`/
   `toolkit/CHANGELOG.md`를 포함하며, 독립 클론에서
   `git apply --check` -> `git am` -> `py_compile` 검증까지 완료된
   상태로 전달됨(base `c2a17cd7`). push 여부 미확인.
3. **347차 devnotes patch(`0001-347cha-devnotes.patch`)가 push
   됐는지** -- `WIP.md`/`FINDINGS.md`/`CURRENT_STATUS.md`를 포함(신규
   toolkit 스크립트 없음, 기존 346차 스크립트 재사용만). push 여부
   미확인.
4. 343차 패치 반영 확인 후, 동일/유사 리드차량 서행 상황을 재주행하여
   시나리오① release 소멸 여부 직접 재확인 필요.
5. (신규 이월, 347차) 강제 RELEASE=lost 발생 7건(x19seg 6+x10seg 1)이
   실제 route_active 재진입까지 이어지는지 개별 사례 트레이스(301차
   방식) 필요.

---

## 그 외 이월 항목 (userMemories/WIP 기준, 우선순위 낮음)

- `mapTurnSpeedFactor=1.10` 보정을 `analysis_helpers.py::recompute_route_curvature_speed()`에
  반영 후 297차 파이프라인 재실행
- `routeProvisional*`/`routeOrphanSingleton*` 실차 로그로
  `PROVISIONAL_PROMOTE_STREAK`(현재 3, observation-only) 값 확정
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

---

*최종 갱신: 347차 (Claude). 다음 세션은 이 파일을 먼저 읽고,
WIP.md 최신 회차(347차)로 상세 맥락을 보충할 것.*
