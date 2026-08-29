## 131차 (체크포인트 — 원인가설 SUCCESS 재현, 코드 미수정, 실차검증 필요) — 129차 route "계단형 급락" 진짜 원인: route_lookahead 윈도우 경계 진입 이산적 불연속(Hypothesis C)

사용자가 route `306de77a28` seg15 재업로드("패치 적용전에 시뮬레이션
하자")로 129차 후속 진행. 상세는 FINDINGS.md "131차" 항목 참고.

**핵심 결과 요약**:
1. rlog 전수조사로 실제 navi 폴리라인이 어떤 로그 채널에도 없음을
   확인(navRoute count=0, navInstructionCarrot은 좌표 없음).
2. `sim_route_step_drop_repro.py`(신규, NEGATIVE): desiredCurvature
   재구성 방식으로는 실측 Δ-25kph 단일프레임 급락을 재현 못 함
   (최대 1.84kph) — 129차의 margin_kph 가설이 계단형 자체의 원인은
   아님을 시사, 방법론 한계도 확인.
3. `sim_route_lookahead_boundary_snap.py`(신규, **SUCCESS**):
   `carrot_man.py`(1cc2bf3) 실제 순수함수를 그대로 복제, 합성 GPS
   폴리라인(직선+원호)으로 검증 — "route_lookahead 윈도우 경계를
   넘어 급커브가 curvature 배열에 이산적으로 출현, 역방향DP가 그
   프레임에 즉시 전체 재계산"하는 메커니즘이 실측과 동일 규모/형태
   (Δ-19.8kph, 단일 20Hz 프레임)로 재현됨.
4. `ryu` 코드는 미수정 — devnotes(FINDINGS/WIP/toolkit README+
   CHANGELOG)만 갱신, 신규 스크립트 2개 toolkit에 저장.

**다음 세션**: (1) 실제 교차로 좌표로 합성 폴리라인 정밀화, (2)
윈도우 경계 완충(저역통과/램프 리미터) 패치 방향 설계, (3)
margin_kph=0/25 대조로 91차 패치의 기여도 확인 후 패치 설계 착수.

---

## 130차 (완료 — 원인확정+구현+합성검증+패치전달 완료, 실차검증 대기) — 104차 Finding A(커브+레이더유실 vision 원거리 오판) `LeadBlend` BIG_JUMP 신뢰도 게이트 패치

**요청**: "이어서 계속, A로 진행하자" — 104차 Finding A(오탐, 25회차간
NEEDS_VALIDATION 방치)를 이어서 진행.

**진행**:
1. devnotes 부트스트랩(129차 확인) + FINDINGS.md 104차 Finding A 재확인.
2. 새 실차 로그 없음 → 코드 정적분석으로 원인 규명: `radard.py`
   `LeadBlend.update()`의 BIG_JUMP(15m) 즉시-스냅 로직이 신뢰도
   (radar/modelProb) 검증 없이 항상 적용되던 것을 확인 — 104차 관찰
   (레이더 유실 후 vision 저신뢰 84~89m 즉시 반영)과 정확히 일치.
3. 패치 설계: `LEAD_BLEND_BIG_JUMP_PROB_GATE=0.70` 신설, 즉시-스냅을
   `radar=True` 또는 `modelProb>=GATE`로 한정. `radard.py` 직접 수정.
4. `toolkit/sim_lead_blend_far_jump_gate.py`(신규) 5개 시나리오 합성
   검증 전부 PASS(104차 재현/고신뢰vision 회귀없음/레이더교차검증
   회귀없음/closer_jump 반응지연없음/정상추종 완전동일).
5. `git format-patch` → `verify-am` 브랜치 검증(base `b63063a`,
   `git am` 적용 + `py_compile`) 통과.
6. devnotes 갱신: FINDINGS.md(104차 Finding A 상태 갱신 + 130차 신규
   섹션), PARAMS_REGISTRY.md(`LEAD_BLEND_BIG_JUMP_PROB_GATE` 등록),
   toolkit/README.md + CHANGELOG.md.

**결과물**:
- 패치: `0001-130-LeadBlend-BIG_JUMP-104-Finding-A.patch`
  (radard.py, `git am` 검증 완료, 로컬 적용/push는 사용자 몫)
- devnotes: WIP.md/FINDINGS.md/PARAMS_REGISTRY.md/toolkit/README.md/
  toolkit/CHANGELOG.md/toolkit/sim_lead_blend_far_jump_gate.py

**다음 세션**:
- 실차 acados MPC 파이프라인 검증(동일 커브+레이더유실 재현 로그 필요
  — 104차 원본 route는 대용량 정책상 컨테이너 미보관, 재확보 필요)
- 진짜 far-jump(다른 차량으로 전환되는 정상 케이스)에서 0.35s 블렌딩
  지연이 체감 문제 없는지 실차 확인
- GATE=0.70이 과보수적인지, 필요시 VisionTrack 레벨(더 상류)에서
  플로시빌리티 게이트를 추가할지 재검토
- Finding B(반응 둔감, route/vturn 속도 목표 우선순위 문제)는 104차
  이후 아직 착수 안 됨 — 다음 우선순위 후보

---

## 129차 (체크포인트 — 원인분석 완료, 구현방향 미결정, 코드 변경 없음) — 교차로 route 사전감속 계단형 고정 원인분석

**요청**: 교차로(좌/우회전) 접근 시 route 사전감속이 너무 일찍 최저속도(30km/h)로
고정돼 서행이 길다 — 과속카메라처럼 연속감속(70→65→...→30)으로 바꾸고 싶다.

**진행**: route `306de77a28` seg15 실차로그 업로드(rlog+대시캠클립) →
extract_log.py 추출 → desiredSpeed/src/vTurnSpeed/steeringAngleDeg 20Hz
시계열 분석 → desiredSpeed 계단형 급락 2건(Δ24~25kph, 0.05초 이내,
steer 직진 수준일 때 발생) 확인 → carrot_man.py::carrot_navi_route()
91차 ROUTE_ENTRY_MARGIN_KPH 마진 로직 코드 재검토 → 구조적 원인 가설 수립
(v_ego_kph를 거리 무관하게 전역 사용 → time_delay 과다산정 → 장거리
"고정값 정체" 발생). 상세 근거/수치는 FINDINGS.md "129차" 참고.

**상태**: NEEDS_VALIDATION — 가설 수준, 시뮬레이션 재현 미실시. 코드 변경 없음.

**다음**: (1) 사용자에게 대안 A(margin 로직 거리보정)/B(calculate_current_speed
스타일로 재구현)/C(margin_kph 완화) 중 방향 확인, (2) 실제 device 펌웨어
커밋 확인(추출 CSV의 commit=b63063a5fe89는 로컬 repo HEAD일 뿐 실측
아님 — 115차 학습 재적용 필요), (3) 방향 확정 후 sim_route_margin_regression_scan.py
확장 재검증 → 패치.

---

## 128차 계속2 (완료 — scons 컴파일 검증 완료) — (a) 클린 컴파일 확인, (b) 실질 검증 불필요함을 확인

**scons 검증 진행** (127차계속과 동일 apt+uv+scons 방식):

**(a) 검증 결과 — 클린**: `carrot.o`(폰트 자동축소 패치 포함) 컴파일 시 에러/경고 0건. 링크까지
정상 진행(별도 무관 이슈로 최종 링크만 미완주, 아래 참고).

**(b) 관련 추가 발견 — omx_encoder.h include 자체는 검증 대상이 아니었음**:
- 헤더 include 추가 후 `omx_encoder.cc` 컴파일 시도 → `AVCodecContext` 에러는 사라졌으나 대신
  `av_free_packet`(ffmpeg 3.1+에서 제거), `av_register_all`(ffmpeg 4.0+에서 제거),
  `avcodec_find_encoder`가 `const AVCodec*` 반환(ffmpeg 5.0+) 등 **훨씬 오래된 ffmpeg API에 맞춰진
  코드가 최신 ffmpeg 6.1.1과 3중으로 안 맞는** 사실을 발견.
- 원인 추적: `selfdrive/ui/SConscript`의 `is_running_on_wsl2()`가 `/proc/version`에 "WSL2" 또는
  "Ubuntu" 문자열이 있으면 **`omx_encoder.cc`/`screenrecorder.cc`를 빌드에서 통째로 제외**함.
  사용자의 실제 개발 환경(Windows PC, WSL2)에서는 이 조건이 걸려 애초에 이 파일이 빌드되지 않음.
  샌드박스 커널 버전 문자열(`6.18.44-fc-v22`)만 이 패턴에 안 걸려서 예외적으로 컴파일이 시도된 것.
- **결론**: omx_encoder.h/cc의 ffmpeg API 불일치는 실제 개발 환경에서 마주칠 일이 없는 샌드박스
  전용 허상 이슈. 128차(b) include 패치는 안전한 방어적 수정으로 유지하되, 3중 API 불일치를
  전부 고치는 건 불필요한 범위 확장이라 진행하지 않음(전역 수정 지양 원칙).
- 검증을 위해 샌드박스에서만 `is_running_on_wsl2()`를 강제 True로 임시 패치해 실제 WSL2 환경과
  동일하게 해당 파일들을 빌드에서 제외한 뒤 재컴파일 → `carrot.o` 포함 전체 정상 컴파일 확인.
  이 임시 패치는 검증 후 즉시 원복(커밋 대상 아님).

**최종 링크 미완주 (무관 이슈, 참고용)**: `libQMapLibre.so`가 요구하는 ICU 66 심볼
(`ubidi_*_66`, `u_shapeArabic_66` 등) 미해결로 링크 실패. 지도 서드파티 prebuilt 바이너리와
샌드박스 ICU 버전 불일치 — 127차계속의 avcodec 이슈와 같은 성격의 환경 문제, 코드 무관.

**빌드 부산물 정리**: scons 실행 중 `lupdate`가 번역 파일(`*.ts`) 11개를 자동 재생성함 —
패치와 무관한 빌드 부산물이라 `git checkout`으로 원복, 커밋 안 함.

**최종 커밋 상태**: `03482e6`(a), `6a3b61b`(b) — 원격 대비 이 2개 파일 diff만 존재, 클린.

---

## 128차 계속 (완료 — 패치 2건 전달 + scons 검증 완료, 위 128차계속2 참고) — TBT HUD 폰트 자동축소 + omx_encoder.h avcodec.h include

**요청**: 사용자 승인 — (a) 폰트 자동 축소 패치 작성, (b) 헤더 include 1줄 추가 패치 작성.

**(a) 패치** (`0001-128-tbt-hud-bottom-text-font-shrink.patch`, 커밋 `03482e6`, base `b63063a`):
- `drawTurnInfoHud()` 하단 안내텍스트(szSdiDescr/szPosRoadName) 구간에 `fit_bottom_text_size` 람다 추가.
- 가용 폭 = `TBT_BOX_W - 40`(420px). `nvgTextBounds`로 폰트 30부터 측정, 초과 시 2px씩 축소해 20까지 시도.
- 20까지 축소해도 넘치면 20 유지(잘림 감수) — 완전한 말줄임/2줄 배치는 이번엔 적용 안 함(범위 최소화).

**(b) 패치** (`0002-128-omx-encoder-avcodec-include.patch`, 커밋 `6a3b61b`, base `03482e6`):
- `omx_encoder.h`의 `extern "C"` 블록에 `#include <libavcodec/avcodec.h>` 1줄 추가 (avformat.h include 위).
- ryu 자체 버그 아님(원본 openpilot 구조), 실차 빌드 영향 없을 가능성 높으나 안전한 명시적 include로 방어.

**검증 상태**:
- ✅ 두 패치 모두 클린 클론(base 위)에 순차 적용 가능(`03482e6` → `6a3b61b`), git format-patch로 개별 생성.
- ✅ carrot.cc 중괄호 균형: 수정 전 483/482(기존 불균형 1, 문자열 리터럴 기인 추정) → 수정 후 485/484(불균형 그대로 1 유지, 내가 추가한 람다 블록은 대칭) — 구조적 깨짐 없음 확인.
- ❌ **scons 컴파일 검증 미실시** — 이번 세션에서 시도 안 함. 다음 세션에서 127차계속과 동일 방식(apt 패키지 수동설치 + scons -j1 selfdrive/ui/)으로 진행 가능.
- ❌ 실차 반영 전 폰트 축소 결과 실측 필요(nvg 실제 렌더링 폭이 목업 추정치와 다를 수 있음).

**상세**: `FINDINGS.md` 128차 항목(분석 근거) 참고.

**다음**: scons 컴파일 검증 → 실차 반영 → (a) 실제 렌더링에서 여전히 잘리면 말줄임/2줄 배치로 추가 보완 검토.

---

## 127차 계속 (완료 — scons 컴파일 검증 완료, unused-private-field 버그 발견+수정 패치 전달) — TurnInfoDrawer::icon_size 제거

**상태**: 127차에서 보류했던 scons 컴파일 검증 진행. 사용자 파일 업로드 없이
샌드박스에서 `tools/install_ubuntu_dependencies.sh` 패키지 목록 수동 설치
(apt) + `uv sync --frozen --extra docs --extra testing --extra dev`
(metadrive-simulator 포함된 `tools` extra는 해시 불일치로 실패하여 제외,
UI 빌드엔 불필요) + `scons -j1 selfdrive/ui/` 로 실제 컴파일 시도.

**환경 이슈 1 (빌드와 무관, 우회만 함)**: 샌드박스가 1코어라 `SConstruct`의
`SetOption('num_jobs', int(os.cpu_count()/2))`가 0을 넘겨 즉시 크래시.
로컬 테스트용으로만 `max(1, ...)` 가드를 임시로 넣어 우회했고, 검증 후
`SConstruct`는 원본으로 복구함(커밋/패치 대상 아님, 실차/일반 PC에선
발생 안 하는 문제로 판단).

**핵심 발견 — 127차 패치의 실제 컴파일 버그**: `carrot.o` 컴파일 시
`selfdrive/ui/carrot.cc:963: error: private field 'icon_size' is not used
[-Werror,-Wunused-private-field]`. 127차 패치가 `TurnInfoDrawer` 클래스
내부에서 아이콘 크기를 기존 `icon_size`(256) 대신 새 상수
`TBT_ICON_SIZE`(140)로 교체하면서, 클래스 멤버로 남아있던 `icon_size`
선언 자체를 지우지 않아 죽은 코드가 됨 → 이 레포의 `-Werror` 빌드 설정상
100% 컴파일 실패. (주의: `carrot.cc` 안에 동명의 `icon_size`가 다른
클래스에 3곳 더 있으나 전부 별개 클래스에서 실제로 사용 중 — 그쪽은
정상, `TurnInfoDrawer`만의 문제였음.)

**조치**: `TurnInfoDrawer` 클래스의 미사용 `int icon_size = 256;` 멤버
선언 1줄 제거. 제거 후 `selfdrive/ui/carrot.o` 정상 컴파일 확인
(`0002-127-scons-unused-private-field-TurnInfoDrawer-icon_s.patch`,
127차 커밋 `0ad61ea` 위에 적용).

**전체 바이너리 링크는 별도 무관 이슈로 미완주 — 참고용**: `main.o` 컴파일
단계에서 `selfdrive/ui/qt/screenrecorder/omx_encoder.h:70: error: unknown
type name 'AVCodecContext'` 발생. 이건 127차 패치와 전혀 무관한 화면
녹화(OMX, comma 3 하드웨어 전용) 서브시스템 헤더 문제로, 이 파일이
`libavformat/avformat.h`만 include하고 `libavcodec/avcodec.h`를 직접
include하지 않는데, 샌드박스에 설치된 Ubuntu 24.04 기본 ffmpeg
6.1.1이 예전처럼 avformat.h에서 avcodec.h를 전이 include 해주지 않아
발생. **이 문제는 이번 세션에서 손대지 않음** — TBT HUD 패치 검증
범위 밖이고, 실차/기존 빌드 환경(다른 ffmpeg 버전 또는 별도 헤더 경로)
에서는 애초에 발생하지 않았을 가능성이 높음(그렇지 않았다면 이전
회차들의 정상 빌드 자체가 불가능했을 것). 다음에 전체 링크까지
검증하려면 이 헤더 문제를 별도로 먼저 봐야 함 — 사용자가 필요하다고
판단하면 별도 세션에서 조사 제안.

**결론**: `selfdrive/ui` 타겟의 **컴파일 유닛 레벨**(carrot.o) 검증은
완료 — 패치 적용 후 반드시 `0002` fix 패치까지 같이 적용해야 컴파일됨.
전체 바이너리 링크/실행 검증은 무관 이슈로 인해 이번 세션에서 미완주.

---

## 127차 (체크포인트 — UI 경로안내창(TBT HUD) 폭 축소 패치 전달, scons 컴파일 검증은 다음 세션으로 이월) — drawTurnInfoHud 790px→460px

**요청**: 우측하단 경로안내창(TurnInfoDrawer::drawTurnInfoHud, `selfdrive/ui/carrot.cc`)
크기를 줄여달라는 요청. 사용자가 스크린샷에 노란 박스로 목표 크기를 표시.

**분석**: 스크린샷(1152x648, fb 스케일 0.6배율=1920x1080 추정) 픽셀 역산 결과
목표 박스 크기는 대략 폭 425~460px / 높이 300px 내외. 기존 박스는 폭 790px,
높이 300px — **높이는 실측치와 거의 동일, 폭만 지배적으로 줄이면 됨**을 확인.

**패치 내용** (`0001-127-TBT-HUD-790px-460px.patch`, 커밋 14d9a6b, base 21adb2c):
- `TBT_BOX_W`(460)/`TBT_BOX_H`(300)/`TBT_ICON_SIZE`(140) 상수화 — 이후 미세조정 시
  이 3개 값만 변경하면 됨
- 회전/분기 아이콘 256px→140px 축소
- "도착: X분(HH:MM)" / "X.Xkm"을 기존 대각선 배치(좁은 폭에서 텍스트 잘림 위험)에서
  세로 2줄 배치로 변경, 폰트 40~50 → 30~32로 축소
- 신호과속(szSdiDescr)/도로명(szPosRoadName) 텍스트: 좌측 정렬 + 폰트 30으로 축소
  (기존은 tbt_x+200 기준이라 좁아진 폭에서 우측 클리핑 우려 있었음)
- 우측 정렬 기준(화면 우측 여백 10px)은 기존과 동일 유지

**검증 상태 (중요 — 다음 세션 필수 확인 사항)**:
- ✅ 클린 클론(base 21adb2c, c3-ms-dev)에 `git am` 정상 적용 확인
- ✅ 원본 대비 중괄호/괄호 개수 균형 동일 (구조적 깨짐 없음)
- ❌ **scons 컴파일 검증 미실시** — 이번 세션 샌드박스에선 시도 안 함(사용자가
  "검증은 다음 세션"으로 명시적 보류 결정). 조사 결과 `ryu`는 cereal/opendbc가
  git submodule 아닌 vendored 구조라 서브모듈 초기화 불필요, `tools/ubuntu_setup.sh`
  + `SConstruct`로 PC 네이티브 빌드 경로 존재. 샌드박스 네트워크 허용 도메인에
  `archive.ubuntu.com`/`security.ubuntu.com`/`github.com`이 이미 포함돼 있어
  **다음 세션에서 사용자 파일 제공 없이 apt-get + scons로 실제 컴파일 시도 가능**함을
  확인함. 다음 세션 시작하면 이 방식으로 `selfdrive/ui` 타겟 빌드 검증부터 진행.
- 실차 반영 전 반드시 PC/실차 빌드로 레이아웃 시각 확인 필요 (겹침/클리핑 없는지)

**다음 세션 우선순위**:
1. `tools/install_ubuntu_dependencies.sh` 기반 의존성 설치 시도 → `scons` selfdrive/ui 빌드
2. 빌드 성공 시 실제 화면 스크린샷으로 레이아웃 재검토(특히 도착정보 텍스트 폭 초과 여부)
3. 실차 검증 후 문제 없으면 devnotes에 완료 처리(## 127차 계속 or 완료로 갱신)

---

## 126차 계속 (완료 — 컷인 전용 로직 구조적 한계 확인, 사용자 결정으로 컷인 관련 검토 전체 보류) — SCC 단일점 하드웨어에서 leadsCutIn 로직 자체가 거의 발동 불가능함을 확인

**상태**: 126차 이후 사용자가 "컷인 판단 로직이 별도로 있나" 질문 →
`compute_leads()`의 `cut_in_count`/`leadCutIn`/`_pick_lead_one_from_state`
3단계 전용 로직(차선폭/`in_lane_prob`와는 별개) 확인해 답변. 이어서
**사용자가 "컷인관련 검토는 보류"로 결정** — 다음 세션은 이 주제를
먼저 꺼내지 말고, 사용자가 다시 요청할 때까지 대기.

**핵심 신규 발견(125/126차보다 한 단계 더 근본적인 원인)**:
컷인 전용 로직은 `tracks.values()`(RadarD가 관리하는 **레이더** 트랙
딕셔너리)만 순회 — `self.vision_tracks`(비전 전용)는 애초에 순회
대상이 아님. 이 차량은 37차가 이미 확인한 대로 코너레이더 없는 SCC
단일점이라 `tracks`에 동시에 존재하는 레이더 포인트가 사실상 1개뿐
(`trackId` 항상 0). 즉 "leadOne 후보"와 "옆에서 컷인 중인 후보"가
동시에 별도 레이더 트랙으로 존재해야 이 로직이 작동하는데, 하드웨어가
구조적으로 그 두 번째 트랙을 만들어내지 못함. **125/126차의
leadsCutIn n=0은 "차선폭 임계값 미스매치"뿐 아니라, 이 하드웨어
구성(SCC 단일점 + 코너레이더 미장착)에서는 컷인 전용 로직 자체가
정상 주행 중 거의 발동할 수 없는 구조라는 게 근본 원인.** 코너레이더가
실제 장착되고 `EnableCornerRadar`가 켜져야 `tracks`에 다중 포인트가
생겨 이 로직이 의미를 가질 가능성이 큼.

**사용자 결정에 따른 처리**: 컷인 판정/차선폭/discontinuity 조인트
게이트 등 컷인 계열 코딩 방향은 전부 **보류 상태로 유지**. 코드 변경
없음. 다음 세션에서 사용자가 이 주제를 다시 꺼내기 전까지는 재검토
시작하지 않음.

## 126차 (완료 — 신규 route 포터컷인 스크린샷 분석 완료, 코드 미수정) — 위험 아님 확인 + "차선 폭 넓히기" 2번째 무력함 재확인, 램프합류 신규 관찰

**상태**: 사용자가 신규 zip(`820cae021b` seg17/18) + 스크린샷(13:46,
dRel 45.6→37.3, 우측차로 포터 컷인 추정) 업로드, "차선 폭 기준 넓히는
방향이 맞는지" 재검토 요청. 125차와 동일 주제 두 번째 독립 실측.
상세는 FINDINGS.md "126차" 참고.

**핵심 결과**:
1. t=1107.00~1107.66 매칭 확인(45.5→37.4m 급락, 레이더 재락온).
   급락폭 4.1m(<94차 15.0m 임계값, 미스파이어 없음 정상), 구간 최소
   TTC 7.08초, harsh_brake 0건(brakePressed 시종 False, aEgo -0.7부터
   선제 감속 중이었음) — **위험 아니었음**.
2. `extract_cutin_lists.py` 재생 결과 이번에도 `leadsCutIn`/`leadsLeft`/
   `leadsRight` 전 구간 n=0 — leadOne이 prob 0.82~0.98로 tentative
   게이트를 거칠 필요 없이 처음부터 정식 등록돼 있었기 때문.
   **"차선 폭 넓히기"는 125차에 이어 이번에도 무력함 확인.**
3. **신규 관찰**: qcamera 프레임 대조 결과 이 구간은 평범한 다차로
   직선도로가 아니라 고속도로 출구램프→지방도 1차로 합류 지점이었음.
   yRel이 -3→-6.8→0으로 크게 출렁이는 궤적은 일반 커브 dPath 노이즈
   (118/119차 기록 ±0.3~0.9m)보다 훨씬 커서, 램프 합류의 기하학적
   수렴으로 보는 게 더 합리적 — "균일 차로 폭 인접차선 컷인"을
   전제로 한 차선폭 상수 튜닝 자체가 이런 합류부엔 안 맞을 수 있음.

**다음 세션 필요 — 코딩 방향, 현재까지 결론**:
1. `lane_half_width`/`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE` 수정은
   2건 표본 모두 "게이트 미개입+위험아님"이라 근거 부족 — **보류 권장**.
2. 94차 discontinuity 조인트 게이트 확장안(125차 제안)은 이번 사례
   (4.1m, 임계값 미만)로는 검증 불가 — 더 큰 낙폭 실사례 필요.
3. 램프/인터체인지 합류부의 큰 폭 yRel 변동 패턴은 이번이 첫 관찰 —
   코드 수정 근거는 아직 아니나, 유사 사례 나오면 축적 가치 있음.

원본 zip/route_new.csv는 work/에만 있어 컨테이너 리셋 시 소실 —
재검증 필요 시 재업로드 필요.

## 125차 (체크포인트 — 124차 TTC 결론 정정, "차선 폭 넓히기" 제안 기각, 코딩방향 미결정으로 중단) — 133212 재정밀분석, SCC 단일점 레이더 타겟 스위칭 신규 확인

**상태**: 사용자가 route354 seg3(133212 사건) rlog/qcamera zip 재업로드.
"물리적으로 충돌위험 있었다, 차선 폭 넓혀서 일찍 감지하고 감속시켜달라"는
요청에 원본 rlog를 `liveTracks`/`radarState`/`modelV2` 레벨까지 직접
재생하여 재정밀분석. 신규 스크립트 `extract_cutin_lists.py` 작성해
toolkit 편입. 상세는 FINDINGS.md "125차" 참고.

**핵심 결과**:
1. **124차의 TTC 계산(7초+, 저위험) 철회 — 사용자 판단이 맞았음.**
   124차는 t=296.5~296.9(레이더 재락온 스냅, yRel≈0)만 보고 결론냈는데,
   그 직후 t=297.0부터 dRel 5.3→3.8→1.8m + yRel 0→0.6~0.8m로 동시
   급변하는 훨씬 급격한 2차 사건이 있었음(124차가 관찰 구간을 거기까지
   확장하지 않아 놓침). 브레이크 개입 시점(t=297.419) 실측 TTC ≈ 3.1초.
2. **"차선 폭 넓히기" 제안은 이 사례엔 무력함을 실측으로 확인.**
   `radard.py`의 실제 `leadsCutIn`/`leadsLeft`/`leadsRight` 리스트를
   원본 그대로 재생한 결과 사건 전체 구간에서 전부 n=0(단 한 번도
   후보로 잡힌 적 없음) — 옆차 yRel 최대 0.83m가 `in_lane_prob` 계산상
   "여전히 차로 안"으로 분류돼 애초에 "차로 밖 후보" 게이트가 개입한
   적이 없었음. lane_half_width 계열 임계값을 넓혀도 이미 발동 안 하는
   게이트를 더 관대하게 만들 뿐이라 효과 없음.
3. **신규 메커니즘 확인 — SCC 단일점 레이더의 "타겟 스위칭".**
   `modelV2.leadsV3[0]`(비전 단독)은 이 구간 내내 매끄럽게 감소하는
   별개의 물체 하나를 계속 추적 중이었음(y≈0 유지, 급변 없음). 반면
   레이더는 재락온 시 더 가깝고 옆으로 치우친 다른 물체로 갈아탄 것으로
   보임 — 이 차량은 코너레이더 없는 SCC 단일점이라 `radarTrackId`가
   항상 0 고정(107차 확인 사항)이라, **124차가 근거로 삼았던 "trackId
   불변=동일 물체" 추론 자체가 이 하드웨어에서 성립하지 않음**을
   재확인.

**다음 세션 필요 — 코딩 방향 미결정, 아래 순서로 검토 제안**:
1. `DREL_DISCONTINUITY_DROP_THRESH`를 dRel 단독이 아니라 dRel 급락 +
   dPath/yRel 동시 급증(=타겟 스위칭 의심 신호)을 보는 조인트 게이트로
   확장 + radar_locked 프레임에서도 적용 검토(기존엔 비전단독 구간만
   검사, 63차/94차가 발견한 사각지대와 연결됨)
2. 표본 1건뿐이므로 다른 라우트(정상 컷인/차로변경/재락온 상황)로
   오탐률 검증 필요
3. "차선 폭" 계열 상수(`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE` 등)
   자체의 원래 목적 기준 튜닝 가치는 이번 분석과 별개로 여전히 미검토

원본 zip(route354 seg3)은 컨테이너 리셋 시 소실 — 다음 세션에서
이어가려면 재업로드 필요할 수 있음. route354/356 다른 세그먼트(r354.csv/
r356.csv, 124차가 쓰던 CSV)도 마찬가지로 미보유.

## 124차 (체크포인트 — 컷인 5클립 전수분석 완료, 코딩방향 미결정으로 중단) — 123차 원인가설 2건 모두 고해상도 재검증으로 기각, 새 메커니즘 발견

**상태**: 컨테이너 재시작 후 route354/356 zip 재업로드받아 CSV
재추출 완료. 사용자 요청("컷인상황만 정밀분석하고 코딩방향
정하자")에 따라 남은 컷인 클립 4개(141434/133149/134659/141833)
전부 분석. 상세는 FINDINGS.md "124차" 참고.

**핵심 결과**:
1. 컷인 클립 5개 중 진짜 문제 사례는 **1건뿐**(133212=133149,
   동일사건). 141434는 운전자 본인 수동 차선변경(컷인 아님),
   134659/141833은 정상 처리.
2. **123차가 제시했던 원인가설 2건(`VISION_TRACK_TENTATIVE_
   DPATH_ABS_GATE`, `DREL_DISCONTINUITY_DROP_THRESH`) 모두
   0.05초 단위 재검증으로 기각됨** — 실제 메커니즘은 "동일
   trackId=0가 2프레임(~0.1s) 레이더를 잠깐 놓쳤다가 재락온하며
   거리값을 5.5m로 스냅 보정"하는 것으로, 두 상수 모두 이 상황을
   다루지 않음(신규등록 게이트도 아니고, discontinuity 로직은
   radar_locked 프레임에서 오히려 히스토리를 초기화함).
3. 이 구간 `vRel`은 -0.5~-1.1m/s로 물리적 위험도는 낮았음(TTC 7초
   이상) — 운전자 브레이크 개입이 "화면상 숫자가 갑자기 반토막
   나는 것에 대한 반사 반응"이었을 가능성이 시스템 결함보다 큼.
4. `sim_drel_discontinuity.py`(기존 toolkit 재사용) threshold=8.0
   시뮬레이션 결과 여전히 미탐지 확인. 6.0대로 낮추는 안도 검토했으나
   r354/r356 전체에서 6~15m 낙폭 이벤트 134건 확인되어 오탐 급증
   리스크로 보류.

**다음 세션 필요 — 코딩 방향 미결정, 4가지 옵션 중 선택 필요**:
1. 레이더 재락온 급보정(동일 trackId, 거리값 스냅) 대응 로직 신규 설계
2. 물리적 위험도 낮았을 가능성 있으니 코드수정 보류, 사례 추가 수집 후 재판단
3. 그래도 `VISION_TRACK_TENTATIVE_DPATH_ABS_GATE`/
   `DREL_DISCONTINUITY_DROP_THRESH`는 각자 원래 목적에서 튜닝 가치
   있을 수 있으니 (이번 사례와 무관하게) 별개로 검토
4. 원본 rlog 정밀분석 확장(dPath/yRel 등 추가 필드로 "왜 2프레임간
   레이더가 놓쳤는지" 근본원인 재탐색)

route354/356 CSV(r354.csv, r356.csv)는 work/에 있으나 컨테이너
리셋 시 소실 — 다음 세션에서 이어가려면 zip 재업로드 필요할 수 있음.

## 123차 (체크포인트 — 세번째 검증 중단, 컨테이너 리셋으로 미완료) — 컷아웃 2건 검증 완료 + 컷인 차선폭 가설 코드근거 발견, 나머지 5클립 미착수

**상태**: 세션 중간에 컨테이너가 리셋되어 route CSV(r354~357) 소실.
분석 결과는 대화 기록에서 복구해 FINDINGS.md에 기록 완료(상세는
FINDINGS.md "123차" 참고). 이 문단은 다음 세션 재개용 요약.

**완료된 것**:
- 컷아웃_135527(r355 t≈1666~1696), 컷아웃_141322(r356 t≈2760~2774)
  둘 다 매끈하게 처리됨 확인. 단 119차 LANE_DEPARTURE 게이트가
  실제로 발동한 케이스는 아니었음(자연 prob 감쇠/target-switch로
  해소).
- 컷인_이거는_차선_폭을_넓게_133212 → r354 t≈296~302 매칭, 정밀분석
  완료. 원인 후보 특정: `radard.py` L420
  `VISION_TRACK_TENTATIVE_DPATH_ABS_GATE=1.75` (컷인 중인 차량의
  tentative 등록을 dPath 큰 동안 배제하는 구조) + 보조적으로
  `long_mpc.py`의 `DREL_DISCONTINUITY_DROP_THRESH=15.0`(6.66m급
  완만한 dRel 급락은 미탐지). 사용자 가설("컷인은 차선폭 기준을
  넓혀야") 지지하는 코드 구조 확인. **둘 다 코드 미수정, 설계
  제안 단계.**

**다음 세션에서 할 일**:
1. route354~357 zip **재업로드 필요**(work/ 소실) → 재추출
2. 컷인_141434(r356) 매칭/분석 이어서 진행 (시작만 하고 중단됨)
3. 복합 클립 3건(컷아웃_컷인_133149 / 컷인_컷아웃_134659 /
   컷인_컷아웃_141833) 미착수 — 분석 시작
4. 5개 클립 결과 종합 후, `VISION_TRACK_TENTATIVE_DPATH_ABS_GATE`
   상향 조정안(예: 1.75→2.0~2.3m대) 시뮬레이션 검증 스크립트 필요
   여부 판단 — 새로 만들기 전 toolkit/README.md에서 dPath/컷인
   관련 기존 sim 스크립트(`sim_lane_departure_gate.py` 등) 재사용
   가능성부터 확인할 것
5. 최종 결론 나오면 사용자 승인 하에 코드 패치 진행

## 122차 (완료 — 두번째 검증: 저속구간 가감속 실차 재검증 + 119차 최신패치 재확인, 코드 변경 없음) — route356 저속 stop-and-go 3건 전부 클린

**배경**: 사용자가 신규 실차 route356(20260829_140924, x20seg, 20분,
commit `21adb2c013f4`=119차 반영 상태) + "저속_가감속" 라벨 화면녹화
클립 3개(141048/141556/142300) 업로드, "저속구간 가감속 상황 분석 +
로그 자세히 분석 + 최신 패치(119차) 잘 적용됐는지 검증" 요청. 121차가
"다음 세션 필요"로 남긴 route356 항목의 이어서 진행.

**클립-route 매칭**: 121차의 "파일명 대비 항상 +52초"가 고정 상수가
아님을 이번에 재확인 — 이번 세션 클립들은 offset이 +30.6s/+31.5s/
+13.5s로 클립마다 편차 있음(스크린레코더 저장지연이 매번 다름을
시사, match_dashcam_clip_to_route.py의 blinker 클러스터 매칭은 이번
클립들이 차선변경이 아니라 저속 정체 시나리오라 blinker 활성이 없어
적용 불가 — 대신 HUD 오버레이 수치(dRel/vEgo/aEgo)를 route CSV와
소수점 단위로 직접 대조 + qcamera 프레임 3건 전부 시각 재확인으로
매칭 확정):
- Clip1(141048) → r356 t≈2592.9 (seg1, dRel=8.3m/vEgo≈5km/h 정밀
  일치 + qcamera 프레임 시각 일치 확인)
- Clip2(141556) → r356 t≈2901.8 (seg7, dRel=6.4m/vEgo≈3km/h/
  aEgo≈-0.90 일치 + qcamera 프레임 시각 일치 확인)
- Clip3(142300) → r356 t≈3307.8 (seg13, dRel=4.5m/vEgo=0 정지 +
  qcamera 프레임 시각 일치 확인, 화명동/그랜저 313노1030 배경 동일)

**119차 최신패치(빨간박스 LANE_DEPARTURE 강제해제 게이트) 검증**:
`replay_lane_departure_gate.py`(120차 도구 재사용)로 route356 전체
23999행 스캔 — 후보 2건(t=2547.35/t=3418.60) **전부 PASS**, 120차가
발견했던 LeadBlend 무력화 버그 미재현. 단 두 이벤트 모두 3개 클립
구간 밖(저속 가감속 자체와 직접 연관 없는 별개 지점)이라 "119차가
정상 동작 중"이라는 방향성 재확인 정도로만 기록, 이번 세션의 저속
가감속 분석 자체와는 독립적 결과.

**저속 가감속 3개 구간 상세 분석 결과 — 전부 클린**:
- harsh_brake_events(급감속 -0.8 이하) 3개 구간 전부 0건 (route356
  전체 30건 중 clip 구간에 겹치는 사례 없음 — clip1/2/3 근접
  harsh_brake 이벤트는 각각 clip 시작 전/후 별도 지점)
- ttc_danger_events 3개 구간 전부 0건
- congestion_stop_launch_lurch_scan(58차 2번, "정체 붕끗") route356
  전체 스캔 0건
- dRel≥6m discontinuity 이벤트 3개 구간 전부 0건, leadStatus 전환도
  0건(추적 안정)
- Clip1(t=2592~2622): 정체 크리핑, vEgo 0~11.3km/h 반복, min
  aEgo=-0.53(경미) — 튐 없이 완만한 정지/재출발 반복
- Clip2(t=2901~2931): vEgo 10.2→1.7km/h 감속 후 재가속, min
  aEgo=-1.75(112차 LOW_SPEED_STRONG_DECEL 문턱 -2.5 미도달, 게이트
  미발동이 적절) — leadALeadK/leadDRel과 aEgo 반응이 시간축상
  자연스럽게 동조(계단식 튐 없음), 신호과속 카메라(55km/h 구간)
  경고 HUD와 겹치나 ADAS 종방향 로직과는 무관한 별도 표시
- Clip3(t=3307~3337): 완전정지, min aEgo=-0.90, dRel 4.5m로 안정적
  유지, 정차 중 흔들림 없음

**결론**: commit `21adb2c`(119차) 상태에서 저속구간 가감속이 3개
사례 전부 매끈하게 처리됨 — 112차(LOW_SPEED_STRONG_DECEL threshold
-2.5)/116·117차(gap-open damping)/94차(discontinuity 리셋)의 실차
동작이 이번 저속 시나리오에서도 회귀 없이 유지되는 것으로 판단.
119차 LANE_DEPARTURE 게이트도 이 route의 다른 지점(클립 무관)에서
정상 PASS 재확인.

**다음 세션 필요**:
1. route357(121차가 "미추출"로 남긴 나머지 구간) 필요시 이어서 확인.
2. 이번엔 clip당 확인용 qcamera 프레임 1장씩만 추출(매칭 검증
   목적) — 클립 전체 30초 구간의 프레임 단위 정밀 대조는 미실시,
   필요시 다음 세션 과제.
3. 119차 게이트 후보 2건(t=2547.35/t=3418.60)은 이번 클립과 무관한
   지점이라 상세 프레임 대조는 안 함 — 필요시 다음 세션에서 검토.

**CSV 산출물**: `r356.csv`(23999행) 레포 미커밋(대용량 정책),
`work/`에만 존재 — 컨테이너 리셋 시 소실.

## 121차 (완료 — 76/94차 방안D discontinuity 리셋 실차 재검증, 코드 변경 없음) — "차선변경 중 급감속" 재발 없음 확인

**배경**: 사용자가 신규 실차 4개 route(354~357) + "내차 차선변경"
클립 4개 업로드, "차선변경시 옆차선 앞차 반응 정상인지 / 예전
급감속이 없어진 게 맞는지" 검증 요청.

**작업**:
1. `extract_log.py`로 route354(22797행)/route355(24000행) 추출
   (커밋 `21adb2c013f4`=119차 반영 상태, route356/357은 클립이
   매칭 안 돼 이번엔 미추출).
2. `match_dashcam_clip_to_route.py` 원리(blinker 클러스터 상대간격
   대조)로 클립 4개 전부 정밀 매칭(오차 <1.5s) — 파일명 대비 항상
   **+52초** 오프셋 확인(111차 "최대~50초" 추정과 사실상 동일값,
   이번에 정밀 재확인).
3. 신규 스캔 스크립트(1회성, 미저장 — 아래 "다음 세션" 참고)로
   dRel≥6m 순간점프(discontinuity) 이벤트 route354/355 전체
   151건 자동 탐지 + 각 이벤트 후 3초 min_aEgo 계산.
4. 4개 클립 이벤트 + 미매칭 강감속 1건(t=827.81~831.45, min_aEgo
   -2.703) 상세 분석. 상세 근거는 FINDINGS.md "121차" 참고.

**핵심 결론**:
- 4개 클립 전부 min_aEgo -0.32~-1.01 범위(경미~온건) — 구버그가
  보고했던 "-2.75까지 급강하" 재현 안 됨. 76차/94차(방안D) discontinuity
  트리거 시 `_vision_dRel_rate`/`window` 리셋이 실주행에서 의도대로
  작동 중인 것으로 판단(간접 확인, 내부 필터 상태 직접 재현은 아님).
- 미매칭 강감속 1건(-2.70)은 **버그 재현이 아니라 정상 반응**으로
  판정 — 레이더가 직접 측정한 vRel=-6.3m/s(vision 미분값 아님)에
  대한 매끄럽고 비례적인 감속, TTC≈4.8s 기준 과도하지 않음.
- route354/355 전수 스캔에서 차선변경 인접 강감속(-2.0 이하) 사례는
  극소수이고, 차선변경 무관 일반주행에서도 유사 강도 감속이 유사
  빈도로 나타나 — 차선변경 특이적 버그가 아니라 정상 ACC 추종 반응.

**사용자 체감("예전 급감속 없어진 듯")과 정량 데이터 일치 확인.**

**다음 세션 필요**:
1. 이번에 짠 discontinuity 자동스캔 스크립트는 1회성 인라인 코드로만
   실행하고 toolkit에 편입 안 함(스크립트 지속성 정책 위반 — 다음
   세션에서 `toolkit/scan_lead_discontinuities.py`로 정식 편입 필요,
   재사용 가치 높음).
2. route356/357(14:09:24~14:34, 미추출) — 남은 구간 차선변경
   이벤트 확인 필요시 이어서 진행.
3. 내부 필터 상태(`_vision_dRel_rate` 등) 직접 재현하는 실측 CSV
   기반 replay 스크립트 부재 — 이번 결론은 aEgo 관측치 기반 간접
   확인이므로, 더 확실한 인과 확인이 필요하면 신규 replay 도구 작성
   검토.
4. 120차가 남긴 "LeadBlend가 LANE_DEPARTURE 게이트 리셋 무력화"
   버그(radard.py 미수정 상태)는 이번 세션과 별개 트랙으로 그대로
   남아있음 — 다음 세션에서 이어서 처리 필요(아래 120차 기록 참고).

**아직 안 한 것**: qcamera 프레임 직접 대조 미실시(CSV 정량분석만).
route356/357 CSV 미추출.

**CSV 산출물**: `r354.csv`(22797행), `r355.csv`(24000행) 레포
미커밋(대용량 정책), `work/`에만 존재 — 컨테이너 리셋 시 소실.

## 120차 (체크포인트 — 119차 패치 실차검증 완료, 부분 무력화 버그 발견, 코드 미수정) — LeadBlend가 LANE_DEPARTURE 게이트 리셋을 다시 덮어씀

**배경**: 사용자가 119차 패치(`21adb2c`) 적용 후 실차 주행(4개 route
zip, 13:30:24~14:34 연속 64분 + CarrotWeb 화면녹화 클립 19개) 업로드,
"패치적용 잘 됐는지" 검증 요청.

**작업**:
1. `extract_log.py`로 4개 route 전체 CSV 추출(89996행, 전부 commit
   `21adb2c`=119차 반영 상태에서 추출 확인 — 단, 이 커밋해시는 "분석
   당시 로컬 repo 상태"일 뿐 "로그 녹화 당시 기기 펌웨어"를 보증하는
   값은 아님에 유의, 실제 검증은 아래 replay 결과로 함).
2. 화면녹화 클립 19개 파일명(유니코드 이스케이프 디코딩 필요했음,
   `#Uxxxx` 형식) 전부 확인 — 시나리오 라벨: 내차 차선변경(패치검증용
   포함)/컷인/컷아웃/저속 가감속/유령파란박스/교차로 조기감속 등.
3. **신규 `replay_lane_departure_gate.py`(toolkit 편입)**: 119차
   게이트 로직을 CSV 위에서 그대로 복제해 "예측 발동 시각"을 계산하고
   실제 leadStatus 전환과 대조하는 검증 도구 작성(119차 WIP.md가
   "다음 세션 필요"로 남겨둔 항목).
4. 4개 route 전체 스캔 결과: 후보 9건 중 PASS 5건/FAIL 3건(자세한
   내용/근본원인은 FINDINGS.md "120차" 참고). **핵심**: 119차 게이트가
   완전히 "죽은" 게 아니라, `LeadBlend.update()`가 게이트의 상태리셋을
   다시 가로채 최대 0.6초 지연시키거나(경우에 따라 완전 무력화) 하는
   부분적 실패 — 118/119차가 원래 잡으려던 "outer 로직이 내부
   상태리셋을 무력화" 버그 클래스가 LeadBlend를 매개로 재발.
5. "내차 차선변경 패치적용여부 검증" 등 ego 차선변경 클립 구간은
   dPath 스파이크가 매번 0.5초 미만이라 게이트 미발동 — 정상
   차선변경 중 오탐(리드 오손실) 없음 확인(긍정적 부수 결과).

**다음 세션 필요**:
1. get_lead() 게이트 발동 시 `self.lead_blend.prev/miss_cnt/
   danger_hold_cnt`도 함께 리셋하는 패치 설계+작성 (RadarD.update()
   빨간박스 케이스, L859~860과 동일 패턴 참고).
2. 위 패치를 `replay_lane_departure_gate.py`에 PATCHED 버전으로
   추가해 이번 실측 FAIL 3건이 해소되는지 재검증.
3. 검증 통과 후 실제 `git format-patch` 작성 -> 사용자 `git am`
   적용 -> 재실차검증(같은 시나리오로 재주행 권장).

**아직 안 한 것**: 코드(radard.py) 수정 없음(원인 확정만). 화면녹화
클립 19개는 시간대 스캔 위주로만 활용, 개별 프레임 육안 확인은 안 함
(토큰 예산 고려, 필요시 다음 세션에 특정 클립만 선별해서 진행).

**CSV 산출물**: `route354~357.csv`(총 89996행) 레포 미커밋(대용량
정책), `work/`에만 존재 — 컨테이너 리셋 시 소실, 재분석 필요하면
원본 zip 재업로드 필요.

## 119차 계속 (완료 — 패치 작성+`git am` 재적용 검증+전달 완료, 사용자 확인 대기) — `radard.py`에 LANE_DEPARTURE 게이트(1.75m/0.5s) 실제 반영, `0001-lane-departure-gate.patch`

**작업**: 아래 119차(파라미터 합성검증) 직후, 사용자가 "패치작업"
요청 → 검증 없이 route1 실측 replay는 아직 안 됐지만("잠정치"로
명시하고) 사용자 지시에 따라 바로 패치 작성으로 진행.

**변경 내용** (`selfdrive/controls/radard.py`, base
`76c985c`=117차):
1. 상수 3개 신규 추가 (L42~ 부근): `LANE_DEPARTURE_DPATH_THRESH=1.75`,
   `LANE_DEPARTURE_CONFIRM_S=0.5`,
   `LANE_DEPARTURE_VREL_GATE=CUTOUT_VREL_GATE`(-0.5). 각 상수 옆에
   118차 원인/119차 검증 근거를 주석으로 남김.
2. `RadarD.__init__()`에 `self._lane_departure_cnt = {0: 0.0, 1: 0.0}`
   디바운스 카운터 추가.
3. `RadarD.get_lead()` 내 `lead_dict` 확정 직후(corner_radar 보정
   이후, `low_speed_override` 이전)에 게이트 삽입 — **index==0
   (leadOne)에만 적용**, leadTwo는 118차 미결정 3번(cut-in 감지 등
   용도 상이) 그대로 보류. `lead_dict['status']`가 True이고
   `|dPath|>1.75` 이고 `vRel>-0.5`(강접근 아님)인 프레임이
   `DT_MDL` 단위로 누적돼 0.5초 이상 지속되면
   `lead_dict={'status': False}; radar=False`로 강제 전환. 이
   경로는 radar-lock(빨간박스) 상태를 포함해 `lead_dict`가 어느
   경로로 확정됐든 매 프레임 재평가되므로, 118차가 확인한
   "`lead_one_raw.get('radar') and not lead_one_scc_fallback`일
   때 `LeadBlend.update()` 자체가 스킵되는" 우회 문제를 구조적으로
   해결.

**capnp 스키마 안전성**: `lead_dict`는 기존에도 매 경로에서 이미
`dict`로 재구성되던 값이고, 이번 변경은 메시지 필드 신규 접근/신규
쓰기 없이 기존 `lead_dict`/`radar` 로컬 변수 값만 조건부로 덮어씀
— capnp 스키마 변경 없음(40차류 크래시 리스크 없음, key_learnings
원칙 확인).

**검증**:
- `python3 -m py_compile selfdrive/controls/radard.py` → OK
- `git format-patch -1 HEAD` → `0001-lane-departure-gate.patch`
  생성 → 별도 브랜치(`verify-am`, base `76c985c`)에서 `git am`
  재적용 → 성공, `py_compile` 재확인 OK.

**아직 안 된 것 (사용자 확인 전 명시적으로 남김)**:
- 1.75m/0.5s는 **근사 재현(route1.csv 실측 replay 아님) 기반
  잠정치** — 119차(합성검증)에서 이미 밝힌 한계 그대로 유지. 실측
  replay, 정상주행 로그 전수 스캔(오탐율 실측 확인)은 아직 안 함.
- 실차 검증 전무(패치만 작성됨, 사용자가 로컬에서 `git am` 적용 후
  실주행/replay로 확인 필요).
- leadTwo 적용 여부 미결정 그대로.

**다음 세션**: 사용자가 이 패치를 적용/실차 검증 또는 route1 원본
확보 후 정밀 replay 재요청 시 그에 맞춰 진행. `radar_state.leadOne`
쪽 downstream(long_mpc.py 등)에 이번 변경으로 인한 부작용 없는지도
필요시 다음 세션에 재확인.

## 119차 (체크포인트 — 118차 제안 LANE_DEPARTURE 게이트 파라미터 후보 합성검증, 코드 미반영) — 사용자 제안 THRESH=1.75m/CONFIRM_S=0.5s를 `sim_lane_departure_gate.py`(신규, toolkit 편입)로 검증

**배경**: 118차에서 제안한 "빨간 박스(검증된 레이더락) 상태에서도
적용되는 차선이탈 강제해제 게이트" 설계의 미결정 사항 중 1번(임계값)에
대해, 사용자가 `CUTOUT_DPATH_THRESH`(2.0m)보다 좁힌 **1.75m**를
1차 후보로 제안, `LANE_DEPARTURE_CONFIRM_S`(0.5s, 118차 기본값)와
조합해서 검증 요청.

**작업**: `toolkit/sim_lane_departure_gate.py` 신규 작성(118차 제안
로직을 문자 그대로 재현, `_is_cutout()` 상수 대조). 4개 시나리오로
2.00m/1.75m/2.30m(118차가 언급한 "보수적" 대안) 3개 후보 비교.
route1.csv 원본이 이 세션에 없어(캐시/업로드 모두 없음) 실측 프레임
replay는 불가 — 118차 WIP.md 기록 수치(t=5915.03 dPath≈0.2m →
t=5931.02 dPath=-1.97m → t=5932.53 자연해제, -1.98~-1.99 정체)만으로
만든 **근사** 프로파일 사용.

**핵심 발견**:
1. **2.0m 그대로 재사용(118차 기본안)은 이 실측 이벤트에 전혀
   트리거 안 됨** — dPath 최대치가 -1.97~-1.99m로 2.0m 문턱을 한
   번도 못 넘기 때문. 즉 "기존 컷아웃 철학 그대로 재사용" 옵션은
   사용자가 실제로 보고한 이 사례에는 무력함이 정량 확인됨.
2. 1.75m/confirm_s=0.5 조합은 근사 재현 기준 t≈15.25s(원본 환산
   t≈5930.28) 시점에 강제해제 트리거 → 자연해제(17.50s 소요)
   대비 **약 2.25초 단축**.
3. 2.30m(118차가 언급한 "더 보수적" 대안)도 이 이벤트에서는
   트리거 안 됨(2.0m보다도 더 못 미침 — 애초에 최대 dPath가
   2.0m 미만이므로 당연한 결과).
4. 정상 커브 dPath 노이즈(118차 기록 실측 스윙 ±0.3~0.9m 기반
   200회 몬테카를로) 기준 1.75m/2.0m/2.30m 모두 오탐 0건. 단, 이
   노이즈 모델은 118차가 관찰한 사례 1건의 범위에만 근거 —
   더 급한 커브의 정상 dPath 거동은 대표 못 할 수 있음(한계로
   toolkit/README.md에 명시).
5. 단일 프레임 스파이크(디바운스 확인)·강접근 중 dPath 초과
   (danger override 우선순위 확인) 두 시나리오 모두 3개 후보 전부
   정상(PASS) — confirm_s=0.5s 디바운스와 vRel 게이트는 임계값
   선택과 무관하게 잘 작동.

**결론(잠정, 실측 replay 전)**: 사용자가 제안한 1.75m 방향이 118차
데이터 기준으로는 타당함 — 오히려 2.0m 그대로는 이 이벤트를 못
잡는다는 점이 이번에 새로 드러난 더 중요한 사실. 다만 이 결론은
근사 프로파일 + 노이즈 모델 표본 1건에 기반하므로, 118차가 이미
제안했던 다음 단계(실측 replay)로 확인 전까지는 "확정"이 아니라
"1.75m가 유력 후보"로 취급.

**미결정/다음 세션 필요 사항**:
1. route1(`ce1f43d848`) 원본 rlog 확보 후
   `replay_lane_departure_gate.py`(신규 예정, toolkit 미보유)로
   정밀 replay — 근사가 아닌 실제 프레임 단위로 1.75m/0.5s 조합의
   조기해제 시점·단축량 재확인 필요.
2. 정상 커브 dPath 노이즈 표본을 118차 사례 1건에서 늘리기 —
   route1/route2 전체(또는 추가 정상주행 로그)에서 "차선이탈
   아닌데 dPath가 1.5m 이상 튄" 구간이 있는지 전수 스캔해서 1.75m
   문턱의 실제 오탐 위험을 노이즈 모델이 아닌 실측으로 확인.
3. 위 1~2번 결과에 따라 1.75m 최종 확정 또는 재조정 후
   `radard.py` 실제 패치 작성 → `git format-patch` → 사용자
   `git am` 적용.
4. leadTwo(index=1) 적용 여부(118차 미결정 3번)는 아직 미논의.

**아직 못한 것**: 코드(`radard.py`) 미변경(118차와 동일하게 설계/
파라미터 검증 단계). route1 실측 replay 미실시(원본 미보유).

## 118차 (체크포인트 — "앞차 컷아웃/차선이탈 시 레이더 락온 미해제→출발지연" 원인 확정, 코드 설계 제안, 패치는 사용자 확인 대기) — get_lead()가 검증된 레이더 락(red box)을 발행할 때 LeadBlend의 dPath 컷아웃 로직이 완전히 우회됨을 확인

**배경**: 사용자 제보 — "앞차가 차선을 이탈하였는데도 레이더 락온이 안
풀림. 그로인해 내차의 출발이 늦음. 앞차의 차선이탈이 확실하다고
판단되면 락온해제 방법 코딩 논의". 업로드(`앞차_컷아웃.Zip`): CarrotWeb
화면녹화 클립 2개(`_clip.mp4`, 각 ~30초, HUD 오버레이 포함) + route
rlog 2세트(route1: `ce1f43d848` x20seg, 12:16:14~12:36:14 / route2:
`bc5b8243eb` x5seg, 12:36:14~12:40:01). 커밋 `76c985ca86f5`(117차 반영).

**분석 절차**:
1. `extract_log.py`로 route1/route2 CSV 추출(`leadDPath`/`leadYRel`
   컬럼 이미 포함 — 88차 이전과 달리 별도 스크립트 불필요했음).
2. 클립 파일명 시각(12:19:25 / 12:37:48) 직접 매칭 시도 — 111차가 이미
   경고한 "HUD 시:분 표시 + screenrecorder 저장시각 어긋남(최대
   ~50초)" 문제로 단순 오프셋 매칭은 신뢰 불가 확인(실제로 route1 원본
   위치와 어긋남). `match_dashcam_clip_to_route.py`(111차)는 **클립
   2개 이상이 같은 라우트 안에 있어야** 상대시간차로 매칭 가능한데, 이번
   두 클립은 서로 다른 라우트(route1 1개/route2 1개)에 각각 1개씩이라
   이 도구를 직접 적용 불가 — **한계로 기록, 다음에 같은 라우트 내
   클립 2개+인 경우에만 이 도구 사용**.
3. 대안으로 클립 자체(HUD 오버레이 포함 화면녹화)를 1fps로 프레임
   추출해 직접 육안 분석 — CarrotWeb HUD가 dRel/lead box(적=레이더락,
   청=비전전용)/a_ego·a_target 그래프/vEgo/vCruise를 전부 표시하므로
   qcamera+rlog 없이도 이 자체로 1차 증거로 유효.
4. **clip2(12:37대) 프레임 분석**: t=6~8s 구간에서 흰색 SUV 리드가
   빨간 박스(레이더 락, dRel 16.4~16.9m)로 계속 추적되다가, 도로가
   좌회전 커브인데 SUV는 우측(교차로/갈림길 방향)으로 진행 — 명백한
   차선/경로 이탈 장면 확인. t=8s 프레임에서 이미 박스가 사라짐(자연
   해제된 것으로 보임 — 이 특정 사례는 결과적으로 큰 지연 없이
   해제됨, "Signal slowing" 텍스트로 봐서 이후 감속은 신호/커브
   속도제어 쪽 원인일 가능성).
5. 클립1(12:19대)도 유사하게 확인했으나 파일명-route 매핑 불확실성
   때문에 route1 CSV 전체를 스캔하는 쪽으로 전환(아래 6번).
6. **route1.csv 전체 스캔(신규, 아래 "신규 분석 코드" 참고)**:
   `leadStatus=True & leadRadar=True`(레이더 락 유지 중)인 동안
   `|leadDPath|>1.8m`가 0.8초 이상 지속되는 구간을 탐지 → 2건 발견.
   그중 **t=5915.03~5932.53(약 17.5초) 이벤트**를 상세 확인:
   - dPath가 t=5915(약 0.2m)부터 점진적으로 커져 t=5931.02에 처음
     **-1.97m**(CUTOUT_DPATH_THRESH=2.0m에 근접) 도달, 이후
     **-1.98~-1.99m 부근에서 정체된 채 leadStatus=True가 계속
     유지**되다가, t=5932.53에서야 leadStatus가 자연스럽게 False로
     전환(레이더 자체가 아니라 **비전 모델(leadsV3[0])이 스스로
     prob를 낮춰서** 발생한 것으로 추정 — 이 프레임까지 radard 내부
     어떤 코드도 dPath 기준 능동적 해제를 시도하지 않음).
   - **dPath가 사실상의 문턱(2.0m)에 도달한 t=5931.02부터 실제
     해제(t=5932.53)까지 약 1.5초 공백** — 이 구간 동안 레이더는
     계속 이 차량을 "내 앞의 유효 리드"로 유지. 다행히 이 특정
     사례는 vEgo가 이미 7.8→8.6km/h로 계속 가속 중이었어서(완전
     정차 후 재출발 상황은 아니었음) 체감 영향이 제한적이었으나,
     **동일 메커니즘이 정차 직후(launch) 상황에서 발생하면 사용자가
     보고한 "출발 지연"으로 직결**됨(원리적으로 dRel이 작고 aLead가
     0 근처로 유지되는 정차 상황일수록 해제가 늦어질 위험이 더 큼 —
     당장 두 클립에서 완전 정차→재출발 국면의 dPath 지연 사례를
     정확히 못 잡았으나 원인 코드 구조 자체가 확인됨).

**근본 원인 확정 (코드 리딩, `radard.py`)**:
- `LeadBlend._is_cutout()`(L659~662, `CUTOUT_DPATH_THRESH=2.0m`
  기준)은 **이미 46차/37차 때부터 존재하는 정상 설계**이지만,
  **`RadarD.update()`(L826~838)를 보면 `lead_one_raw.get('radar') and
  not lead_one_scc_fallback`(비전-레이더 교차검증된 안정적 락, 즉
  "빨간 박스" 상태)일 때는 `LeadBlend.update()` 호출 자체를 완전히
  건너뛰고 `lead_one_raw`를 그대로 `radar_state.leadOne`에
  발행**한다(주석에 "이미 안정적인 실측값이므로 블렌딩 지연 없이
  그대로 사용"이라고 명시돼 있음 — 파란박스→비전 전용/sccFallback
  경로로 떨어질 때만 `LeadBlend.update()`가 호출되고, 그때 비로소
  `_is_cutout()`이 평가됨).
- 즉 **CUTOUT_DPATH_THRESH 로직은 "락이 이미 풀렸거나 불안정한
  경우"에만 작동하고, 정작 가장 흔한 상태("빨간 박스", 전체 추적
  시간의 74~82%로 코드 주석에 명시)에서는 dPath가 아무리 커져도
  아무 검사 없이 그대로 통과**된다. 사용자가 겪은 "차선을 확실히
  벗어났는데도 락온이 안 풀림"은 바로 이 우회 경로가 원인 — 비전
  모델이 스스로 그 차량에 대한 confidence를 떨어뜨리기 전까지는
  (또는 레이더 트랙 자체가 물리적으로 사라지기 전까지는) 아무 것도
  능동적으로 락을 풀지 않는다.

**신규 분석 코드 (toolkit 미편입, 1회성 스캔 — 재사용 시 정식 편입 필요)**:
- `/home/claude/work` 내 임시 스크립트로 `leadStatus/leadRadar/
  leadDPath` 열을 이용해 "락 유지 중 dPath 지속 초과" 구간을 찾음.
  간단한 로직이라 아직 toolkit에 정식 편입하지 않음 — **다음 세션에
  이 패턴 재사용 필요해지면 `toolkit/scan_locked_lane_departure.py`
  정도로 정식 편입 검토** (지금은 1회성이라 보류, README 신규 도구
  체크리스트 미적용 상태임을 명시).

**제안하는 코드 설계 (아직 미구현, 사용자 확인 필요)**:
`radard.py` `get_lead()` 내, `track`이 선택돼 `lead_dict =
track.get_RadarState(...)`가 만들어진 직후(L899~901 부근)에 **"검증된
락 상태에서도 적용되는" 사전 차선이탈 감지 게이트**를 추가하는 방향
제안:
```python
LANE_DEPARTURE_DPATH_THRESH = CUTOUT_DPATH_THRESH  # 2.0m, 기존 컷아웃
                                                     # 철학 재사용
LANE_DEPARTURE_CONFIRM_S = 0.5  # s, 단일 프레임 노이즈(곡선구간 dPath
                                 # 진동, 실측상 정상차량도 ±0.3~0.9m
                                 # 흔들림 있음)로 오탐 방지
LANE_DEPARTURE_VREL_GATE = CUTOUT_VREL_GATE  # -0.5 m/s, 강하게
                                               # 접근중인 물체는 그대로 유지
                                               # (danger override와 철학 일치)
```
`RadarD.__init__()`에 `self._lane_departure_cnt = {0: 0, 1: 0}` 같은
인덱스별 디바운스 카운터 추가 → `get_lead()`에서 `lead_dict['status']`
True이고 위 조건 만족 시 `DT_MDL` 단위로 누적, `LANE_DEPARTURE_CONFIRM_S`
이상 지속되면 `lead_dict = {'status': False}; radar = False`로 강제
전환. **이렇게 하면 "빨간 박스 우회 경로"에서도 적용되고, 기존
LeadBlend 경로(파란박스/sccFallback)의 `_is_cutout()`과는 독립적으로
공존** — 강제로 status를 꺼주면 이후 자연스럽게 다음 사이클에
`match_vision_to_track`가 다른(또는 없는) 리드를 재평가하게 됨.

**미결정/사용자 확인 필요 사항**:
1. 임계값을 기존 `CUTOUT_DPATH_THRESH`(2.0m) 그대로 재사용할지, 아니면
   "이미 락이 걸린 상태에서의 해제"는 더 보수적으로(예: 2.3~2.5m)
   잡을지 — 오탐(정상 차로내 차량을 커브 등에서 성급히 놓침) vs
   미탐(사용자가 겪은 지연) 트레이드오프.
2. `LANE_DEPARTURE_CONFIRM_S` 0.5s가 적절한지 — 실측 이벤트(위
   t=5931.02~5932.53)에서 dPath가 문턱을 넘은 뒤 최종 자연해제까지
   실제 약 1.5초였으므로, confirm 0.5s면 이 사례에서 **약 1초를
   앞당길 수 있었을 것**으로 추정(정량 replay 검증 필요, 아직 안 함).
3. 이 로직을 leadOne뿐 아니라 leadTwo(index=1)에도 동일 적용할지 —
   leadTwo는 cut-in 감지용으로 쓰이는 등 용도가 달라 신중 검토 필요.
4. **다음 세션 진행 순서 제안**(분석 우선 원칙): (a) 이번 발견을
   `sim_*.py`류 합성 시나리오로 순수함수 검증 → (b) 가능하면
   `replay_*.py`류로 route1 t=5915~5932 실측 재생 재현(정량적으로
   "confirm 0.5s였다면 몇 초 앞당겨졌을지" 확인) → (c) 사용자 확정 후
   실제 `radard.py` 패치 작성.

**아직 못한 것**:
- 완전 정차→재출발(launch) 상황에서의 "차선이탈+락온지속" 사례를 이번
  두 클립에서 프레임 단위로 정확히 특정하지 못함(클립-route 매핑
  불확실성 때문 — 위 2번 참고). route1/route2 CSV에는 이번 발견한
  route1 t=5915 사례 1건 외 유사 패턴이 더 있을 수 있으나 전수조사는
  아직 안 함(2건만 발견, min_dur=0.8s/threshold=1.8m 조건에서).
- 코드 미변경 (설계 제안 단계, 사용자 확인 대기).
## 117차 (완료 — 116차 F 단차 대응 방향 확정+구현+검증+패치전달 완료) — 캡 진입/해제 완만화(rise-rate 블렌드) 추가, long_mpc.py patch 적용

**결정**: 116차 미결정사항 1번("F 단차를 그대로 두고 실측 replay부터
할지 vs 완만화를 먼저 추가할지") — 사용자가 **완만화 우선 확정**.
"캡 진입/해제를 `LEAD_ACCEL_WEIGHT_RISE_RATE`처럼 사이클당 변화폭을
제한하는 방식으로 바꿔서 단차 자체를 줄인다"는 방향으로, 39차와 동일
패턴(블렌드 weight rise-rate 제한) 재사용해 진행.

**구현**: `long_mpc.py` `process_lead()`에 `LOW_SPEED_GAP_OPEN_*` 상수
(게이트 조건은 116차 설계 그대로) + `LOW_SPEED_GAP_OPEN_WEIGHT_RISE_RATE`
(1.0/s, 신규) 추가. 캡을 하드클램프하지 않고 블렌드 weight(`cap_w`)를
두어 `a_lead*(1-cap_w) + min(a_lead,CAP)*cap_w`로 적용, cap_w는 목표
(gate on=1.0/off=0.0)를 향해 사이클당 `RISE_RATE*dt`만큼만 이동(진입/
해제 양방향). launch bypass 중엔 이 rise-rate도 즉시 우회해 cap_w=0.0
강제(45차 defense-in-depth). 상태(`_gap_open_cap_weight_prev`)는
`_lead_accel_weight_prev`와 동일하게 리드 소실 시 0.0(안전측)으로 리셋.
39차와 차이점: 39차는 rising(위험 풀림) 방향만 제한하지만 이 방안은
"위험 신호"가 아니라 "가속 상한"이라 양방향 모두 완만화 필요.

**합성검증**: `toolkit/sim_gap_open_damping.py`에 완만화 버전
(`apply_gap_open_cap_smoothed`) + 신규 시나리오 G/H/I 추가(기존 A~F는
하드클램프 버전 비교기준으로 보존). **G**: 116차 F와 동일 경계 왕복
재실행 — 사이클당 최대 a_lead 변화폭 1.500→**0.075 m/s²**(95% 감소,
이론값 `RISE_RATE*dt*discontinuity`=1.0*0.05*1.5=0.075와 정확히 일치).
**H**: cap_w가 중간값(0.5)으로 램프 중일 때 bypass 활성화 시 같은
프레임에 즉시 cap_w=0.0 강제 확인. **I**: 게이트 5s 유지 시 하드클램프
버전과 동일 정상상태(a_lead=0.5, cap_w=1.0) 도달 확인(지연만 있고
결과는 동일). 기존 A~E도 회귀 없음. **9개 시나리오 전부 PASS.**

**패치 검증**: 로컬 커밋(`7529bfd`, base `8a7baa0`) → `git format-patch`
→ 별도 temp branch(`verify-tmp`)에 `git am` 적용 → diff 0 + `py_compile`
통과(파일이 원래부터 UTF-8 BOM 시작이라 기본 encoding으론 ast.parse
실패 — `utf-8-sig`로 정상 확인, 기존 파일 특성이지 이번 패치 문제
아님). 패치 파일: `0001-117-gap-opening-a_lead-116-rise-rate.patch`.

**devnotes 갱신**: FINDINGS.md(117차 항목 신규)/PARAMS_REGISTRY.md
(LOW_SPEED_GAP_OPEN_* 2개 행 신규)/toolkit/README.md(sim_gap_open_damping.py
섹션 117차 갱신)/toolkit/CHANGELOG.md(117차 한줄 요약) 전부 완료.

**남은 것 (다음 세션 우선순위)**:
1. 실측 로그(115차 기존 lowspeed_a/b/c 등 4개 라우트)로 게이트 발동/
   오탐 여부 replay 검증 — 아직 실행 안 함
2. `ACCEL_CAP=0.5`/`A_LEAD_THRESH=1.0`/`WEIGHT_RISE_RATE=1.0` 전부 감으로
   잡은 값 — 실측 기반 튜닝 필요
3. 실차 체감 검증 전무

## 116차 (체크포인트 — 신규 방안 "저속 gap-opening a_lead 캡" 설계+합성검증 완료, 실측 replay 전 결정 대기) — LOW_SPEED_GAP_OPEN_* 6개 시나리오 전PASS, 경계전이 단차(1.5 m/s^2) 발견

**배경**: 6님 제보 — "저속(30~40km/h 이하)에서 앞차가 멀어질 때 자차가
너무 급하게 재가속하면, 이후 앞차가 다시 정지/감속할 때 자차가 급하게
반응하게 되는 것 아니냐"는 신규 가설. 기존 방안I/C/58차(전부 "앞차 감속에
어떻게 반응할까")와 달리, **"앞차가 멀어질 때 자차 가속을 어떻게 완만하게
할지"**를 다루는 첫 방안.

**코드 리딩 결과 (기존 로직 실태)**:
1. `dynamic_t_follow()`(jLead 기반 t_follow/jerk 보정)는 `DynamicTFollow`
   파라미터 기본값 0 → 완전 비활성. 사용자 실제 params_backup 확인 결과도
   `DynamicTFollow:"0"`, `EnableSpeedTF:"0"`, `JLeadFactor3:"0"` 전부
   비활성 확정 — 원인은 이쪽이 아님.
2. `long_mpc.py`의 lead accel damping(`dist_w`/`ttc_w`)은 위험(closing)
   방향 감쇠만 존재 — 앞차가 멀어지는(v_lead>v_ego) 방향엔 damping
   자체가 없어 `a_lead`가 감쇠 없이 그대로 MPC 타깃에 반영됨 (핵심 원인
   지점으로 특정).
3. `get_carrot_accel()`은 순수 속도기반 가속 상한이라 lead/gap 상태 무관.

**방향 A(DynamicTFollow 파라미터 활성화) vs 방향 B(long_mpc 레벨 신규
게이트) 비교 검토 → 방향 B 채택**: A는 jLead 신호가 toolkit CSV에
미수집(cereal엔 존재, extract_log.py 미추출)이라 검증 인프라 신설 필요 +
전역 스위치라 부작용 범위가 넓음. B는 기존 신호(aLeadK/vRel/dRel)로 즉시
replay 검증 가능 + 저속+gap-opening으로 영향범위 국한.

**설계 (`long_mpc.py` 삽입 위치: `dist_w`/`ttc_w` 계산부 인접)**:
```
LOW_SPEED_GAP_OPEN_V_EGO_GATE = 40.0 / 3.6       # ~40km/h (6님 확인값)
LOW_SPEED_GAP_OPEN_A_LEAD_THRESH = 1.0           # m/s^2
LOW_SPEED_GAP_OPEN_ACCEL_CAP = 0.5               # m/s^2
gap_ratio = x_lead / desired_distance             # desired_distance<=1.0이면 스킵
apply = (v_ego <= GATE and a_lead >= THRESH
         and not self._launch_bypass_active
         and gap_ratio >= MARGIN_ACCEL_GATE_FULL)  # 1.5, 기존 dist_w 경계 재사용
if apply: a_lead = min(a_lead, ACCEL_CAP)
```
**"정지 후 출발 가속 약화"(45차) 재발 방지가 핵심 설계 포인트**: (1)
`_launch_bypass_active` 구간 명시적 제외, (2) gap_ratio가 낮은(아직
desired_distance 이내로 정상 추종 중) 구간은 게이트 자체가 안 열림 →
정상 출발이 "너무 천천히" 되는 오탐을 구조적으로 차단.

**합성검증 (`toolkit/sim_gap_open_damping.py`, 신규, 6개 시나리오 전부
PASS)**: A(고속 회귀 diff=0)/B(launch bypass 중 캡 미적용,
defense-in-depth)/C(bypass 해제 후 18~40km/h 정상 출발 연장 구간 캡
미적용 — 오탐방지 핵심 검증)/D(이벤트 재현, gap_ratio>=1.5+강한가속
지속 시 a_lead가 0.5로 정상 클램프)/E(완만가속 오탐방지 diff=0)/
**F(gap_ratio 1.5 경계 전이 — 예외 없이 즉시 토글되나, 캡 진입 순간
a_lead에 최대 1.5 m/s^2 단차(하드클램프, 완만화 없음) 발생 발견 —
방안I류 jerk 완만화 병행 필요 여부는 NEEDS_VALIDATION)**.

**미결정 사항 (다음 세션 시작 시 최우선 확인)**:
1. F에서 발견된 경계전이 단차(1.5 m/s^2)를 그대로 두고 실측 replay부터
   할지, 아니면 완만화(rise-rate류)를 먼저 추가한 뒤 replay할지 — 방향
   미확정 상태로 세션 종료됨
2. `LOW_SPEED_GAP_OPEN_ACCEL_CAP=0.5`/`A_LEAD_THRESH=1.0`/
   `MARGIN_RATIO=1.5(재사용)` 전부 실측 로그 없이 감으로 잡은 값 —
   기존 4개 실측 라우트(lowspeed_a/b/c 등, 115차 참고)로 replay 검증
   필요
3. ryu 코드(long_mpc.py) 자체는 아직 미수정 — 방향 확정 후 patch 생성

## 115차 (체크포인트 — pre-112차(b67c291) 실측 로그 4건 분석, 112차 threshold 실측검증) — SMOOTH 완전PASS/ROUTE_A 부분개선/ROUTE_B 저속게이트무관 진짜급감속

**입력**: 사용자 업로드 zip 2건 → 라우트 4건으로 분리·추출.
- `smooth(1028)`: 08/28 10:28, 1세그, "10시28분28초 전후 감속분석 급감없이
  부드러움" — 비교군(양성 사례)
- `lowspeed_a`: 08/27 11:26, 2세그 — 저속(14.3km/h) 근접추종 정차 직전
- `lowspeed_b`: 08/27 12:06, 3세그 — 저속게이트 무관 구간(t≈4349) +
  메인 급감속(t≈4376, vEgo 33.5km/h, min aEgo **-4.02**)
- `lowspeed_c`: 08/27 12:21, 3세그 — 완만한 감속(min aEgo -2.18)

**중요, 최우선 확인사항**: `extract_log.py` meta.json의 `commit` 필드는
로컬 clone 시점 repo HEAD(112차, `8a7baa0`)일 뿐 **실제 드라이브 당시
device 펌웨어와 무관**. **사용자가 실제 펌웨어 커밋을 확인**:
`b67c2912a2d34b983f2c25fed9ec21547b9ea331`("Merge c3-ms-curv into
c3-ms-dev (81,82,84,85,87,91차 통합)", 2026-08-27 10:23 KST) — 즉 이
4개 라우트는 **94/98/100/101/109/112차 전부 미반영 상태**에서 캡처됨.
(향후 실측 로그 업로드 시 항상 "정확히 몇 차 펌웨어인지" 먼저 확인할 것
— meta.json만으로는 알 수 없음, 이번처럼 사용자에게 물어야 함.)

**[용어 정정, 중요]** 4개 로그 전부 **112차 패치 미적용(commit
b67c291) 상태의 실주행 로그** — 이 로그의 raw 값에 112차 patch 로직을
`replay_low_speed_strong_decel.py`로 **오프라인 재생(replay)**한
것이지, 패치가 실제로 device에서 구동된 결과를 관측한 게 아님. 아래
"PASS"/"완전히 제거함" 등은 전부 이 재생 시뮬레이션 기준.

**작업**: 기존 `toolkit/replay_low_speed_strong_decel.py`(112차 계속
산출물, 이제까지 ROUTE1 캐시에만 적용됐던 도구)를 이번 신규 4라우트에
그대로 재사용해 112차 threshold 패치(-1.8→-2.5)가 적용됐다면 어떻게
판정됐을지를 오프라인으로 재현. 신규 스크립트 작성 없음(README 우선
확인 원칙 준수).

**핵심 발견**:
1. **smooth(1028): 재생 시뮬레이션상 완전 PASS.** 구threshold(-1.8)
   기준 26프레임(1.247s 조기구간) 발동 **예상**되던 게 신threshold
   (-2.5)에서는 0프레임 예상 — 112차 patch 로직을 대입하면 이 라우트의
   저속게이트 오탐이 완전히 사라지는 것으로 재현됨.
2. **lowspeed_a(14.3km/h): 부분 개선.** 구 16프레임(조기 0.900s)/신
   9프레임(조기 0.700s) — 완전 제거는 아니고 조기발동 구간만 축소.
   다만 이 구간 실측 leadALeadK가 자연스럽게 -2.96까지 도달하는 **진짜
   지속 감속**이라(112차 계열 replay가 112차 원 케이스에서 이미 확인한
   패턴과 동일), threshold를 더 낮춰도 완전 제거는 물리적으로 어려울
   가능성.
3. **lowspeed_b: 2개 별개 이벤트.**
   - t≈4349~4351(25→20km/h): 저속게이트 대상 구간, leadALeadK
     -2.6~-2.7 도달. 구 발동/신 일부발동(8프레임) — a와 유사 패턴.
   - t≈4373~4377(**메인 이벤트**, vEgo 33.5~44km/h): **저속게이트
     자체가 적용 안 되는 범위(LOW_SPEED_STRONG_DECEL_V_EGO_GATE=
     30km/h 이상)**. dRel 34→18m, leadVRel +1.3→**-7.0m/s**로 2.5초간
     연속적·물리적으로 일관되게 변화(점프/불연속 없음, leadRadar 유지,
     차선변경 없음) — **노이즈나 버그가 아니라 선행차량의 실제 강한
     감속에 대한 정상적 연속 추종 반응**으로 판단됨. min aEgo -4.02가
     승차감상 과했는지는 별개 문제 — 대시캠(`260827_120658_clip.mp4`)
     대조 필요(다음 세션 후보).
4. **lowspeed_c: 저속게이트 완전 무관.** 구/신 threshold 전부 0프레임
   발동 — 이 라우트의 완만한 감속(min aEgo -2.18)은 margin/ttc weight
   자연수렴 경로로 진행된 것으로 보이며, 112차 패치와 무관.
5. **harsh_brake_events() 기본 파라미터(accel_drop_thresh=-0.8,
   window_s=0.5)로는 4라우트 전부 0건** — 실제 이벤트들이 1.5~3초에
   걸친 점진적 변화라 짧은 창 기반 탐지 로직 자체가 안 걸림(참고용
   기록, 함수 개선은 아직 미착수).

**다음 세션(사용자 확인 필요)**:
1. lowspeed_b 메인 이벤트(t≈4376) 대시캠 프레임 대조 — 실제 앞차
   급제동이 맞는지, 체감상 -4.0m/s²가 과했는지.
2. lowspeed_a/b의 저속게이트 "부분개선"(완전제거 아님) 결과를 112차
   FINDINGS.md 결론에 반영할지(신threshold로도 여전히 0.7~1.0s 조기
   구간 존재).
3. lowspeed_c처럼 저속게이트 무관 완만 감속 케이스의 "체감 급감" 원인은
   이번 분석으로 못 밝힘 — 근접추종 갭 오실레이션(seg7 미해결 패턴)
   연관 가능성, 필요 시 별도 분석.
4. 114차 체크포인트(판별지표 재설계/113차 유실 백업 확인)는 여전히
   미결 — 이번 115차와 별개로 계속 대기 중.

**이번 세션 변경 파일**: `devnotes`: `WIP.md`/`FINDINGS.md`/
`LAST_ANALYZED.md`(115차 기록 추가, 스크립트 신규 작성 없음).
`ryu`: 변경 없음.

## 115차 계속 (체크포인트 — lowspeed_a/b부수 "완전제거" 방향 심층분석, 코드 변경 없음) — threshold만 올리는 건 위험, 메커니즘(즉시점프→빠른램프) 교체 제안

**요청**: lowspeed_a/lowspeed_b부수(부분개선에 그친 두 사례)를 집중분석해
완전 제거 가능하도록 전면 재검토.

**[핵심 신규 발견] TTC 궤적을 보면 두 사례가 서로 다른 성격** — 지난
115차 기록은 각 이벤트의 "최저 leadALeadK 시점" 단일 프레임의 TTC만
봤는데(a: 5.66s, b부수: 5.28s), **신threshold(-2.5) 발동구간 전체의
TTC 궤적**을 다시 뽑아보면:
- **lowspeed_a**: 발동구간(t=1939.17~1939.62) 동안 TTC가 **6.86s →
  4.18s**까지 급격히 떨어짐(0.45초 만에). closing속도(v_ego-v_lead)도
  1.59→2.35m/s로 계속 증가 중 — 즉 "느긋한 완만감속"이 아니라 **TTC가
  실제로 danger(2.5s) 쪽으로 빠르게 다가가는 중인 이벤트**.
- **lowspeed_b부수**: 발동구간(t=4349.38~4350.32) 동안 TTC는
  12.93s → 5.1~5.4s대에서 멈춤(더 안 내려감) — a보다 훨씬 여유로움.

**[위험 신호] threshold만 올려서 "완전 제거"하면 원래 이 기능을
정당화한 사례(58차2번, route `a3a55cb808` seg12, 실측 min TTC=4.45s)
자체를 못 잡을 가능성이 큼.** `sim_low_speed_decel.py`의
`scenario_B_event_reproduction()`을 코드로 확인해보니, 이 시나리오는
**a_lead를 `LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH` 상수 자체를 그대로
가져다 쓰는 구조**(주석: "실측 근사치 -1.5~-2.0")라 **threshold를
올리면 시나리오도 같이 올라가 버려서 항상 자동으로 PASS함 — 즉 이
합성검증은 "threshold를 얼마로 올려도 무조건 통과"하는 동어반복이라
threshold 인상의 안전성 근거로 쓸 수 없음(중요, 지금까지 이 맹점이
인지되지 않았던 것으로 보임).** a3a55cb808의 진짜 실측 leadALeadK
값은 CSV가 로컬/레포에 없어(memory 캐시목록엔 있으나 실물 파일
미보유 — Google Drive 보관 정책) 이번 세션에 직접 대조 불가.
**lowspeed_a의 TTC 4.18s는 이 원 사례(4.45s)보다 오히려 더
급박한 축에 속함** — 만약 a3a55cb808의 실측 aLeadK가 -1.5~-2.0
근처라면, lowspeed_a(-2.96)를 안 잡는 threshold는 a3a55cb808도
당연히 안 잡는다는 뜻은 아니지만(서로 다른 축), **"aLeadK만 보는
현재 설계로 a를 걸러내려면 threshold를 매우 크게(-3.0 이상) 올려야
하고, 그 경우 저속+완만 aLeadK+급격 TTC하강 조합의 다른 미래 사례를
놓칠 위험이 있음**.

**제안 방향(코드 변경 전, 사용자 확인 필요) — threshold 조정이 아니라
반응 메커니즘 교체**:
1. **문제의 진짜 원인 재정의**: 사용자가 "harsh"하게 느끼는 건
   aLeadK가 threshold를 넘는다는 사실 자체가 아니라, **넘는 순간
   weight가 rise-rate 없이 즉시 0.x→1.0으로 스텝(계단)으로 튀는
   구조** 때문일 가능성이 높음(112차계속2가 이미 제안했던 옵션2와
   동일 방향, 이번에 TTC 데이터로 뒷받침).
2. **즉시 w=1.0 대신 "빠른 고정램프"로 교체**: 저속게이트 조건 성립
   시에도 danger override처럼 즉시 1.0이 아니라, 평소 rise-rate
   (1.0/s)보다 훨씬 빠른 전용 rise-rate(예: 3.0/s, 튜닝 대상)로 상승.
   **개략 계산**(현재 실측 데이터 기준 추정):
   - lowspeed_a: 발동시점 w_base≈0.150 → 3.0/s 램프면 1.0 도달까지
     약 0.28s. baseline 자연수렴(0.7s 후)보다는 여전히 0.42s 빠름
     — 즉 "TTC가 4.18s까지 떨어지는 급박한 구간에서 baseline보다
     느리게 반응하는" 회귀는 없음.
   - lowspeed_b부수: 발동시점 w_base≈0.000 → 3.0/s 램프면 약 0.33s
     소요. baseline(1.0s 후 수렴)보다 0.67s 빠름 — 마찬가지로 이점
     유지.
   - 정확한 rise-rate 값은 감(느낌)이 아니라 `sim_low_speed_decel.py`
     확장(현재 tautology인 시나리오B를 실측 고정값으로 앵커링해
     재작성) + 4개 신규 라우트 replay로 튜닝해야 함 — 이번 세션은
     방향 스케치까지만, 코드/정확한 상수는 다음 승인 후.
3. **(옵션, 추가 안전장치)** TTC가 진짜 danger 근접(예: <=4.0~4.5s
   근처)로 떨어지는 프레임에서는 기존처럼 즉시 1.0 유지(danger
   override와 사실상 동급 취급), TTC가 그보다 여유로운 상태에서만
   램프 적용 — 이러면 lowspeed_a의 후반부(TTC 4.18~4.28s 프레임)는
   여전히 즉시 반응, 전반부(TTC 6.86~5.0s대)와 lowspeed_b부수 전체는
   램프로 완화. 다만 게이트가 2단이 되어 복잡도가 늘어나는 트레이드오프
   있음 — 단순 3.0/s 고정램프 하나로 충분한지 다음 세션 sim에서 먼저
   확인 후 필요시에만 추가.

**사용자 확인/결정 필요**:
1. 이 방향(threshold 유지, 반응 메커니즘을 즉시점프→빠른램프로 교체)
   으로 진행할지, 아니면 그래도 threshold를 추가로 올려서 이 두 사례
   자체를 아예 게이트 밖으로 뺄지(단, 이 경우 a3a55cb808급 사례의
   미래 재발 위험을 감수한다는 의미임을 인지 필요).
2. **a3a55cb808 seg12 원본 CSV(또는 zip) 재확보 가능한지** — 이
   feature 전체를 정당화한 앵커 사례의 실측 aLeadK를 직접 확인해야
   threshold 관련 논의(1번)를 제대로 할 수 있음. 없으면 이번 근사치
   (-1.5~-2.0)를 그대로 신뢰하고 진행.
3. 승인되면 다음 세션에서 `sim_low_speed_decel.py` 시나리오B를
   비-tautology 형태로 재작성(a_lead를 threshold와 별개의 고정
   실측값으로 앵커링) → 램프 rise-rate 후보값 스윕 → 4개 신규
   라우트+캐시 라우트 전체 회귀검증 → `long_mpc.py` 패치 순.

**코드 변경 없음(설계 방향 스케치만).**

## 114차 (체크포인트 — margin_accel_weight 포함 완전 재현 완료, [긴급] 113차 유실 확인, 사용자 확인 필요) — ROUTE1은 이미 해소됨/ROUTE2·3만 진짜 문제

**[긴급, 먼저 확인] 113차 devnotes 유실 발견**: 세션 시작 시 WIP.md 최상단이
"112차 계속2"였음(113차 항목 없음). 확인 결과 `toolkit/replay_rise_rate_
saturation.py`(113차가 만들었다고 FINDINGS.md에 기록된 신규 스크립트)가
**레포에 존재하지 않음** — `toolkit/README.md`/`CHANGELOG.md`에도 등록
안 됨. FINDINGS.md 113차 서술 텍스트만 살아남고 스크립트 파일 자체와
WIP.md 113차 항목은 컨테이너 리셋으로 유실된 것으로 추정(SETUP.md
"검증 스크립트는 항상 toolkit에 저장" 원칙이 있었음에도 이번엔
지켜지지 못함 — 원인 미상, 커밋 히스토리 자체가 이번 세션 시작 시
단일 "재작성" 커밋(`5d0c517`)으로 남아있어 세션 중간 리셋 시점 특정 불가).
**사용자 확인 필요**: 로컬에 `replay_rise_rate_saturation.py` 백업이
있는지 확인 요망(있다면 아래 114차 스크립트와 별개로 보존 권장).

**작업**: 113차가 미룬 과제("margin_accel_weight(dist_w)까지 포함한 완전
재현") 수행. 신규 `toolkit/replay_margin_accel_weight_full.py` 작성 —
`long_mpc.py`의 desired_distance 체인(`get_safe_obstacle_distance`/
`desired_follow_distance`/`carrot.get_T_FOLLOW`)을 **carrot_functions.py의
Params 기본값**(TFollowGap2=1.20/ComfortBrake=2.4/StopDistanceCarrot=5.5/
EnableSpeedTF=0/DynamicTFollow=0/MyDrivingMode=Normal)으로 대입해 재현.
`margin_accel_weight`/`ttc_accel_weight`뿐 아니라 **LOW_SPEED_STRONG_DECEL
게이트 + TTC danger override(둘 다 rise-rate 우회, w=1.0 즉시 적용)까지
포함** — 이 부분이 113차(유실) 스크립트에 빠져있었을 가능성이 높음(아래
핵심발견 참고, 직접 대조는 파일이 없어 불가).

**핵심 발견 (중요, 113차 결론 정정)**:
1. **ROUTE1 saturation: 0.951s(113차) → 0.250s(114차, danger override
   포함)로 대폭 감소.** 프레임별 대조 결과 t=1939.173(aLeadK=-2.76)에서
   `LOW_SPEED_STRONG_DECEL`(112차가 이미 -1.8→-2.5로 강화, 현재 origin에
   반영된 상태)이 정확히 발동해 saturation을 0.25s만에 끊어버림 —
   SMOOTH의 0.298s와 거의 동급. 113차의 0.951s는 112차계속2의
   "override 없는 baseline 자연수렴" 수치(다른 질문에 대한 답)를
   "현재 코드의 saturation"으로 잘못 표에 넣었을 가능성이 큼(스크립트가
   없어 직접 대조 불가, 추정).
   **→ ROUTE1은 이미 112차 패치로 사실상 해소된 것으로 재평가.**
2. **ROUTE2(0.999s)/ROUTE3(0.903s)는 113차와 거의 동일** — 두 라우트 다
   `LOW_SPEED_STRONG_DECEL`(v_ego>30km/h라 게이트 밖)/TTC danger(ttc>2.5s
   유지) 어느 override도 안 걸리고, rise-rate 클램프가 온전히 목표를
   뒤쫓는 과정을 그대로 거침 — **이 두 라우트가 실제 남은 문제.**
3. **margin_accel_weight(dist_w)는 4라우트 이벤트 구간 전부에서 1.000
   고정**(dRel/desired_distance ratio가 GATE_NONE 밑) — 즉 113차가
   우려한 "dist_w 근사 오차로 인한 과대평가"는 **이 4개 이벤트에 한해서는
   기우였음**(dist_w가 처음부터 아예 안 걸림, ttc_w/override만이
   유효했음). 다만 이는 이번 4개 사례에 국한된 관찰 — 고속/장거리 추종
   시나리오에서는 dist_w가 실제로 작동할 수 있음(38차 원 사례 참고),
   일반화 금지.
4. **[신규 경고, 판별지표 재검토 필요] SMOOTH 라우트 전체 스캔에서
   0.448s 에피소드 발견(t≈5794.13, 분석 대상이던 t≈5768.92/0.298s
   이벤트와는 별개 지점)** — 프레임 대조 결과 t=5794.573에서 dRel이
   23.28→11.70m, vLead가 6.19→13.75m/s로 순간 점프(track-switch/재획득
   아티팩트로 추정, radarTrackId 미확인)해 ttc_w가 인위적으로 치솟다
   끊긴 것으로 보임 — **진짜 위험 감속이 아닌데도 ROUTE1의 최대
   saturation(0.25s)보다 긴 0.448s를 기록**. 113차가 제안한 "SMOOTH
   최장 0.298s / harsh 최소 0.903s 사이 어디든 안전한 분리선"이라는
   전제가 114차 데이터로는 깨짐(SMOOTH 내부에 0.448s 노이즈성
   에피소드 존재, ROUTE1은 이제 0.25s로 SMOOTH보다 오히려 낮음) —
   **단순 threshold 하나로는 못 가른다.** 상세는 FINDINGS.md 참고.

**전체 라우트 threshold 스윕 결과(오탐률 확인, `scan_route_saturation_
episodes`)**: FINDINGS.md 114차 표 참고 — 요약하면 0.40s 문턱 기준
SMOOTH 1건/ROUTE1 0건/ROUTE2 4건/ROUTE3 2건 걸림. ROUTE1이 이제 전
threshold에서 0건이라(최대 0.25s) 애초에 "이 새 메커니즘이 필요한
사례" 목록에서 빠지는 셈 — **113차가 세웠던 "ROUTE1을 대표사례로
한 통합 트리거" 설계 전제 자체를 재검토해야 함.**

**다음 세션(사용자 확인 후 진행, 방향 미확정)**:
1. **판별지표 재설계**: 현재 "연속 saturation 시간" 단일 지표로는
   SMOOTH의 track-switch 노이즈(0.448s)를 못 거름 — radarTrackId
   불연속 체크(63차 방안C/D 자산 재사용 가능성)를 추가 게이트로
   결합할지 검토.
2. **ROUTE2/ROUTE3 전용 접근으로 축소할지 판단**: ROUTE1이 빠지므로
   "저속+고속 공통 일반화 트리거"보다 "고속 추종 중 rise-rate
   장시간(≈0.9s+) saturation" 좁은 시나리오로 범위를 좁히는 안 검토.
3. (계속) 문턱 스윕 추가 라우트 확보 — 이번 세션은 기존 4라우트
   재사용뿐, 신규 라우트 없음(사용자가 제공한 파일 2건 모두 기존
   112/113차 라우트의 재업로드였음).
4. 113차 유실 스크립트 백업 여부 사용자 확인.
5. 방향 확정 후 `long_mpc.py` 패치 구현.

**이번 세션 변경 파일**: `devnotes`: `toolkit/replay_margin_accel_weight_
full.py`(신규), `toolkit/README.md`, `toolkit/CHANGELOG.md`,
`FINDINGS.md`(114차), `LAST_ANALYZED.md`, 이 WIP.md 항목. `ryu` 코드
변경 없음(분석만).

CSV(`smooth.csv`/`r1.csv`/`r2.csv`/`r3.csv`)는 프로젝트 정책(레포 커밋
금지)에 따라 devnotes에 커밋하지 않음 — `/home/claude/work/`에만 존재,
컨테이너 리셋 시 소실. Google Drive 커넥터 미연결이라 이번 세션은
work/ 스크래치로만 둠 — **재사용 필요하면 다음 세션에서 원본 zip
재업로드 필요**(114차 스크립트만 있으면 재추출은 빠름).

---

## 112차 계속2 (체크포인트 — [중요 정정] replay 검증 결과 threshold 강화 효과 재정량화, 사용자 판단 필요) — "오탐 제거"가 아니라 "조기발동 46% 단축"

**작업**: 사용자가 라우트1 원본 CSV 재업로드 → `extract_log.py` 재추출
→ 신규 `toolkit/replay_low_speed_strong_decel.py`로 실측 replay 검증.

**핵심 발견**: 기존 112차의 "일상 제동에도 걸리는 오탐" 판정은 단일
시점(aLeadK=-2.07)만 본 불완전한 분석이었음. 실측 전체 궤적은 aLeadK가
최대 -2.96까지 악화되는 **진짜 지속적 감속 이벤트**였고, TTC도 같은
구간에서 6.85s→4.15s로 자연 하강해 **오버라이드 없이도 정상경로가
t=1939.873에 자연 수렴**했을 것으로 확인(baseline 시뮬레이션).
threshold 강화(-1.8→-2.5)의 실제 효과는 "조기발동 구간 0.754s→0.410s
(약 46%) 단축"이지 "오탐 제거"가 아님. 상세 수치는 FINDINGS.md 112차
계속2 참고.

**다음(사용자 확인 필요 — 3가지 방향 중 선택)**:
1. 현재 패치를 "부분 개선"으로 인정하고 그대로 실차검증 진행.
2. 오버라이드 전용 짧은 고정램프(예 0.2~0.3s) 절충안 추가 검토
   (기각된 "rise-rate 전체 되살리기"와는 다른 접근).
3. 이번 이벤트가 실제로 강한 감속이었으므로 현재 반응이 적절했을
   가능성도 열어두고 라우트2/3과 함께 실차검증에서 재평가.

**이번 세션 변경 파일**: `devnotes`: `toolkit/
replay_low_speed_strong_decel.py`(신규), `toolkit/README.md`,
`toolkit/CHANGELOG.md`, `FINDINGS.md`(112차 계속2), 이 WIP.md 항목.
`ryu` 코드 변경 없음(지난 회차 패치 그대로 유지, 되돌리지 않음 —
사용자 판단 전까지 보수적으로 현상 유지).

---

## 112차 계속 (체크포인트 — 라우트1 패치 구현+단위검증 완료, replay검증 보류) — LOW_SPEED_STRONG_DECEL threshold 강화 + jerk_boost 신규 소스 추가

**작업**: 112차(위 항목) 합의 방향대로 `long_mpc.py` 구현 완료:
1. `LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH`: -1.8 → -2.5.
2. `discontinuity_jerk_boost`에 신규 트리거 소스 `low_speed_strong_decel`
   추가 (handoff/discontinuity_lc와 동일한 hold 4.0s+release 100/s
   경로 재사용, danger 지속 중엔 base 유지·해제 후에만 완만화 — rise-rate
   되살리기 기각 결정과 정합).
3. `toolkit/sim_low_speed_decel.py` 확장: 시나리오 E/F/G 추가, 기존 B는
   threshold 상수 참조로 수정. **7/7 PASS**.

**보류(다음 세션 최우선)**: 라우트1 원본 CSV가 컨테이너에 없어(레포
미커밋 정책 + 컨테이너 리셋, Drive 미연결) replay 검증 불가 — 사용자가
라우트1 CSV 또는 원본 zip 재업로드 필요. 이후 순서:
1. `patched_replay` 계열로 라우트1 실측 replay 검증 (min_aEgo/지속시간
   패치 전후 비교).
2. `git format-patch`로 패치 파일 생성·전달.
3. 라우트2/3 a_change_cost boost 확장 여부는 라우트1 실차검증 결과
   보고 재논의(기존 합의 유지).

**이번 세션 변경 파일**: `ryu`: `selfdrive/controls/lib/
longitudinal_mpc_lib/long_mpc.py`. `devnotes`: `toolkit/
sim_low_speed_decel.py`, `toolkit/README.md`, `toolkit/CHANGELOG.md`,
`FINDINGS.md`(112차 계속 항목), 이 WIP.md 항목.

---

## 112차 (체크포인트 — 원인 확정, 패치 방향 논의 완료, 코드 변경 없음) — "저속주행중 앞차 서행/정지시 급감속" 제보 3라우트 분석, 라우트1 LOW_SPEED_STRONG_DECEL 게이트 오탐 확정

**요청**: 사용자가 "저속주행급감.Zip"(대시캠 클립 3건 + route 3건,
`00000336--4a688572c0`(seg10-11), `00000338--c60bf8189f`(seg9-11),
`00000339--ce1f43d848`(seg4-6)) 업로드, "저속주행시 앞차가 서행하거나
정지시 내차가 급하게 정지"하는 증상 제보 + 부드러운 정지 코딩 요청.

**작업**: extract_log.py로 3라우트 CSV 추출(commit `02e1f9355f42`,
c3-ms-dev) → 각 라우트 최저 aEgo 구간 확인 → `leadALeadK` 필드까지
포함해 재추출·시계열 분석(3건 모두 radar=True 실제 리드, danger
override TTC≤2.5s 문턱은 불침범 확인).

**결과 (라우트별 원인 상이 — 중요)**:
1. **라우트1(t≈1940, 최저 aEgo=-2.58, vEgo 14~20km/h)**: 명확한 버그.
   t=1938.97에 `aLeadK=-2.07`(vEgo=19.2km/h, <30km/h 게이트) 시점에
   `LOW_SPEED_STRONG_DECEL`(58차2번, `V_EGO_GATE=30km/h`/
   `A_LEAD_THRESH=-1.8m/s²`) 정확히 발동 확인 — 이 순간 `w=1.0` 즉시
   적용되며 `LEAD_ACCEL_WEIGHT_RISE_RATE` rise-rate 제한까지 완전
   우회. 약 0.7~1초 후 aEgo가 -0.5→-2.58까지 급락(t=1939.5~1940.07).
   전 구간 dRel 8~9m로 여유 있었음(실제 위험 아님). **58차2번의 원래
   목적(정체구간 재출현 붕끗 대응)과 무관하게, 평범한 일상 제동
   강도(-1.8m/s²)에도 걸리는 문턱이 너무 낮고 완충 없이 풀강도로
   튀는 것이 원인.**
2. **라우트2(t≈4376, 최저 aEgo=-4.02, vEgo 33~44km/h)/라우트3(t≈5221,
   최저 aEgo=-2.18, vEgo 30~39km/h)**: `LOW_SPEED_STRONG_DECEL` 게이트
   **미발동**(vEgo가 30km/h 초과 구간에서 리드 강한 감속 발생, 게이트
   조건 자체가 안 걸림). `ttc_accel_weight`/`margin_accel_weight` 정상
   경로로 w가 서서히 상승 — ego 응답(-4.02, -2.18)이 리드 실측 감속
   (aLeadK 최대 -4.2, -2.0)과 대체로 비례. **설계대로 동작한 정상
   케이스에 가까움**(다만 체감상 급하게 느껴질 순 있음, 도달 과정
   jerk 완충 메커니즘 자체가 없는 구조적 공백은 라우트1과 공통).

**사용자와 패치 방향 논의 완료**:
- 라우트1: (A) 임계값 강화(-1.8→약 -2.5, 3라우트 실측 기반 보정) +
  (B) `discontinuity_jerk_boost` 메커니즘(66~73차 기 검증, "목표는
  안 바꾸고 저크만 완화")을 신규 트리거 소스(`low_speed_strong_decel`)
  로 확장 — **rise-rate 제한 되살리기(원안 B)는 기각**: 이 분기가
  `lead0_danger_now`에 묶여 TTC-danger와 동급 취급되므로, 여기에
  rise-rate를 다시 걸면 58차 원래 취지(정체 붕끗에 늦지 않게 반응)를
  부분 무력화하는 셈이라 반대함.
- 라우트2/3: a_change_cost boost 확장 대상에 **포함**하기로 함(근본
  구조적 공백이 3라우트 공통이므로) — 단, 회귀 원인 추적을 위해
  **라우트1 먼저 분리 패치+검증, 그 다음 라우트2/3 패턴(TTC 경로 정상
  상승 케이스)에 boost 확장 여부를 실차검증 결과 보고 판단**하는
  순서로 진행 합의.

**다음(사용자 확정 대기)**:
1. 라우트1 패치 구현: `LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH` 값 조정
   + `low_speed_strong_decel`을 `discontinuity_jerk_boost` 트리거
   소스로 추가(hold 시간/release rate는 기존 방안G/I 값 재사용 여부
   검토 필요).
2. `sim_low_speed_decel.py` 재사용/확장해 patch 전/후 비교 검증
   (기존 시나리오 A~D + 이번 3라우트 실측 케이스 추가).
3. 라우트1 CSV로 replay 검증 → git format-patch → 사용자 전달.
4. 라우트2/3 a_change_cost boost 확장 여부는 라우트1 실차검증 후 재논의.

**코드 변경 없음(분석 + 방향 합의만, 이번 세션)**.

---

## 111차 (체크포인트 — 사용자 제보 클립 2건 분석 완료, 코드 변경 없음) — dashcam clip-route 시간매칭 신규 도구 + 패치 영향범위 확인

**요청**: 사용자가 대시캠 클립 2건(`_113702_clip.mp4`,`_113848_clip.mp4`)
업로드, "차선변경시 화면 가속도 그래프가 패치 후 어떻게 바뀌는지" 질문.

**작업**:
1. 파일명 시:분초 단순매칭 실패(최대 53~55초 편차) → 신규
   `toolkit/match_dashcam_clip_to_route.py` 작성(blinker 클러스터
   상대시간차+급감속강도 매칭). README/CHANGELOG 반영.
2. 클립1=106차 "중간" 사례(t≈2574-2578, discontinuity_lc 미발동 —
   패치 무관, 그래프 동일), 클립2=106차/108차 "심각" 사례(t≈2683-2687,
   109차/110차가 이미 검증한 그 force_revert 에피소드) 식별.
3. 클립2 구간 프레임단위 재생 비교 — 실제 차이는 t=2685.72~2685.92
   (0.19초)뿐, 진짜 위험이라 PATCHED도 0.35s만에 confirm돼 base로
   수렴 — 109차/110차 결론(min_aEgo 보존, 지속시간만 단축)과 정합.
4. FINDINGS.md 111차 항목 기록.

**한계**: 화면 `a_ego/a_target/a_out` 곡선 자체는 실제 MPC 솔버
재실행 없이는 재현 못함(프레임단위 jerk-cost 비교로 대체) — 사용자에게
고지 완료, 필요시 다음 세션 과제로 남을 수 있음.

**다음 세션 최우선**: (변경 없음, 이월)
- **실차 드라이브 검증**(유일하게 남은 109차 patch 검증 과제).
- (기존 이월) 91차 curve pre-decel 실차검증, 방안E/G 실차검증, 45차
  stop-to-launch bypass 미완성 구현.

**이번 세션 변경 파일**: `toolkit/match_dashcam_clip_to_route.py`(신규),
`toolkit/README.md`, `toolkit/CHANGELOG.md`, `FINDINGS.md`(111차),
이 WIP.md 항목. `ryu` 코드 변경 없음.

---

## 110차 (완료 — 109차 검증 공백 해소, 코드 변경 없음) — 947fbb7dc6/ad830211ff 재업로드 후 PATCHED 재검증

**요청**: 109차가 컨테이너 리셋으로 검증 못 한 두 사례(`947fbb7dc6`
최심각 사례, `ad830211ff` handoff 2건) 사용자가 재업로드.

**작업**:
1. 로그 폴더 타임스탬프(2026-08-27) vs 109차 패치 커밋 `02e1f93`
   author date(2026-08-28) 교차검증 — 로그가 패치 이전 raw 기록임을
   확인(replay 시뮬레이션 목적엔 문제 없음, 실차검증 대체 아님).
2. `extract_log.py`로 두 라우트 CSV 추출 (`work/csv_947fbb7dc6.csv`,
   `work/csv_ad830211ff.csv`, 레포 미커밋).
3. `scan_force_revert_episodes`(UNPATCHED)/`patched_replay_v109`
   (PATCHED) 나란히 실행, before/after 비교.
4. **결과**: `947fbb7dc6` 최심각 사례 — min_aEgo -3.40 그대로 보존,
   지속시간 0.457s→0.209s 단축(54%↓). `ad830211ff` handoff 2건 —
   PATCHED/UNPATCHED 프레임단위 완전 동일(영향 없음, 설계대로).
5. FINDINGS.md 110차 항목 기록.

**결론**: 109차 옵션1 patch의 로그 기반 replay 검증이 모두 완료됨
(108차 30라우트 + 109차 캐시 12라우트 + 이번 2건). 코드 변경 없음
(109차 패치 `b84eeb8` 그대로 유지).

**다음 세션 최우선**:
- **실차 드라이브 검증**(유일하게 남은 과제) — 차선변경 중 급감속
  완화 체감, 순수 discontinuity/handoff 반응 회귀 없음,
  `LANE_CHANGE_DISCONTINUITY_DANGER_CONFIRM_S=0.25s` 적정성 판단.
- (기존 이월) 91차 curve pre-decel 실차검증, 방안E/G 실차검증, 45차
  stop-to-launch bypass 미완성 구현.

**이번 세션 변경 파일**: `FINDINGS.md`(110차 항목), 이 WIP.md 항목.
`toolkit/`, `ryu` 코드 변경 없음.

---

## 109차 (완료 — 옵션1 patch 구현+시뮬레이션 검증, 실차검증 전) — discontinuity_lc danger confirm-hold, 패치전달 완료

**요청**: 108차 확정 근거로 옵션1 patch 구현 착수.

**작업**:
1. `long_mpc.py`(c3-ms-dev)에 `LANE_CHANGE_DISCONTINUITY_DANGER_
   CONFIRM_S=0.25s` 신규 상수 + `_lc_danger_confirm_timer` 상태 추가.
   `discontinuity_lc` 소스에 한해 danger_active가 0.25s 연속 유지돼야
   force_revert 인정하도록 게이트 로직 수정. `handoff`/순수
   `discontinuity`는 완전 그대로(분기 조건이 소스명으로 한정돼 구조적
   회귀 불가). 커밋 `b84eeb8`.
2. 신규 `toolkit/patched_replay_v109.py` 작성(`LaneChangeGateReplay`
   상속) — 캐시 12라우트 재생 검증: `a5b1ce4e42`의 discontinuity_lc
   2건 중 경미한 1건은 완전 흡수, 지속 사례 1건은 0.55s→0.35s로 단축
   (진짜 위험 반응은 보존). 나머지 라우트는 애초 이벤트 없음.
3. **검증 공백**: 108차의 가장 심한 사례(`947fbb7dc6`, aEgo -3.40)와
   `handoff` 2건(`ad830211ff`)은 원본 CSV가 컨테이너 리셋으로 소실돼
   이번 세션에서 재검증 못함 — **재업로드 필요**.
4. 패치 파일 전달(`0001-discontinuity-lc-danger-confirm-hold.patch`).

**다음 세션 최우선**:
- `947fbb7dc6`/`ad830211ff` 재업로드 후 패치 재검증(가장 중요 — 심각
  사례에 대한 검증이 아직 없는 상태).
- 실차 드라이브 검증(체감/회귀 체크, CONFIRM_S=0.25s 적정성 판단).
- (기존 이월) 91차 curve pre-decel 실차검증, 방안E/G 실차검증, 45차
  stop-to-launch bypass 미완성 구현.

## 108차 (완료 — 실주행 30라우트 확대검증 + 시뮬레이션 버그 2건 발견/수정, 코드변경 없음) — discontinuity_lc(차선변경 중) force_revert 필요조건 재확정, 옵션1 설계 근거 확정

**요청**: 사용자가 실주행 로그 18개(2.7GB, 92bb45496d/947fbb7dc6 원본
포함) 신규 업로드, 107차 계속(캐시 12라우트) 결론을 더 큰 표본으로
검증 후 설계 방안 제시 요청.

**작업**:
1. 18개 라우트 `extract_log.py`로 CSV 추출 (`/home/claude/work/csv/`,
   레포 미커밋 — 대용량 정책). 기존 캐시 12개+신규 18개=30개 라우트.
2. 1차 재검증 도구(`flicker_cluster_boost_replay.py`) 작성 중 버그 2건
   발견: (a) 클러스터 warm-start 재생 시 pad_s에 따라 결과가 달라지는
   아티팩트 → 라우트 전체 연속 재생으로 해결. (b) **트리거 소스별
   boost_s(discontinuity=1.0s vs handoff/discontinuity_lc=4.0s)를
   구분 안 해 허위 severe 사례 다수 발생** — 원시데이터 대조로 확인,
   이 도구는 폐기.
3. 기존 75-76차 도구 `replay_lane_change_discontinuity_gate.py`의
   `LaneChangeGateReplay(duration_mode='full')`(실제 코드와 100% 동일)
   기반으로 신규 `toolkit/scan_force_revert_episodes.py` 작성 —
   30라우트 전체 정확 재스캔.
4. **최종 결과: force_revert 5건** — `discontinuity_lc` 3건(전부
   blinker=True, 106차 원본 947fbb7dc6 -3.40 포함), `handoff` 2건
   (blinker=False, 저속 정상범위 -1.75~-1.81), 순수 `discontinuity`는
   0건. → 106차/107차 결론(차선변경이 force_revert 필요조건) 재확정.
5. FINDINGS.md 108차 항목 기록, toolkit README/CHANGELOG 갱신.

**사고 기록**: 108차 최초 작업분이 도구 호출 한도로 push 전 컨테이너
리셋돼 유실 → 다음 세션에서 이전 세션 결과를 그대로 재구성해 기록
(재계산 불가, 원본 CSV 18개도 소실). 상세는 FINDINGS.md 108차 "주의"
항목 참고.

**다음 세션 최우선**: 옵션1 patch 구현 착수 — `long_mpc.py`의
`_discontinuity_trigger_source == 'discontinuity_lc'`인 경우에 한해
danger_active confirm-hold(0.2~0.3s) 적용, `handoff`는 즉시 revert
유지. 실차 검증은 아직 없음(30라우트는 전부 로그 기반 replay 재현).

## 107차 계속 (체크포인트 — 정밀 재검증 완료, 코드 변경 없음) — replay_boost_duration.py로 51클러스터 정밀 재현, 106차 blinker 인과관계 확정

**107차 본편에서 제기한 재검토("차선변경 특유 아닐 수 있음") 우려를
같은 세션에서 정밀 재현으로 재검증.** `replay_boost_duration.py`(73차,
기존 도구, 현재 코드와 동일 설정 boost_s=4.0/release_rate=100.0/
split_gate=True)를 51개 플리커 클러스터 전체에 실행.

**결과**: boost force_revert(danger override로 boost가 정작 필요할 때
꺼지는 106차 패턴) 재현 **3건 전부 blinker_overlap=True, blinker무관
30건 중 재현 0건.** 1차 근사 스캔의 `would_trigger_ttc_danger`는
과대추정(노이즈)이었던 것으로 확인 — 정밀 재현이 훨씬 적은 수만
실제 위험으로 확정. **결론: 106차의 "차선변경(blinker)이 원인"이라는
인과관계는 정량적으로 뒷받침됨 — 표본편향 우려는 기각.**

다만 새로 찾은 3건의 실제 감속 강도는 경미~중간(min aEgo: +0.05,
-0.08, -1.18) — 106차 사례3(-3.78, severe)만큼 심각한 사례는 이번
12개 캐시 라우트엔 없었음. 메커니즘은 진짜지만 심각도는 상황(실제
접근 속도 등)에 좌우됨. 상세는 FINDINGS.md 107차 후반부 참고.

**결론적으로 패치 범위를 "차선변경/blinker 컨텍스트 한정"으로 좁히는
것이 타당함이 확인됨** — 107차 본편 초반에 사용자에게 제시했던
옵션1(권장, 플리커 감지 후에만 confirm-hold)/옵션2(단순, blinker 중
항상 confirm-hold) 중 하나로 패치 설계 재착수 가능한 상태.

**다음 세션(또는 이어서) 최우선**:
1. 옵션1 또는 옵션2 확정 후 `radard.py`(get_lead()~LeadBlend 사이)에
   confirm-hold 패치 구현.
2. 패치 후 캐시된 12개 라우트로 회귀검증(3개 force_revert 사례가
   해소되는지 + 다른 정상 케이스 회귀 없는지) — `replay_boost_duration.py`
   확장 또는 별도 스크립트로.
3. 92bb45496d/947fbb7dc6(106차 실사례, severe 포함) 재검증하려면
   사용자가 `내차_차선변경.Zip` 재업로드 필요(미캐싱, 소실 상태).

**이번 세션 변경 파일**: `FINDINGS.md`(107차 항목 후반부 추가), 이
WIP.md 항목. `toolkit/`, `ryu` 코드 변경 없음(이전 체크포인트와 동일).

---

## 107차 (체크포인트 — 106차 후속 패치설계 재검토, 코드 변경 없음) — leadRadar 플리커 정량화 도구 신규 + 106차 "차선변경 특유" 결론 재검토 필요성 발견

**배경**: 106차가 남긴 "leadRadar 핸드오프 반복 급감속" 원인을 바탕으로
사용자가 패치 설계/구현 진행을 요청. 안전critical 코드라 설계안(옵션1/
옵션2) 제시 후 사용자가 "초보설명 + 전면 재검토" 요청 → 원래 WIP
계획(트랙ID 컬럼 추가 후 정량화)으로 되돌아가기로 합의.

**중요 발견 1**: `leadRadarTrackId` 컬럼은 63차 계속3에서 이미
`extract_log.py`에 추가돼 있었음(106차가 "없음"으로 오판, 기존 도구
미확인). 다만 이 차량(SCC 단일점 레이더, 코너레이더 없음) 구조상
radar=True 프레임의 트랙ID가 항상 0 고정 — 트랙ID로는 애초에
"같은 물체 vs 다른 물체" 구분이 불가능함을 캐시 라우트 3건으로 확인.

**중요 발견 2 (106차 결론 재검토 필요)**: 트랙ID 대신 leadRadar
True/False 엣지 자체를 클러스터링하는 `radar_source_flicker_scan()`
신규 작성(toolkit/analysis_helpers.py, README/CHANGELOG 반영 완료).
캐시된 일반 주행 12개 라우트(72차 검증셋 2개 + 86차 검증셋 10개)
전체 스캔 결과 **총 51클러스터 중 blinker 겹침은 21건(41%)뿐, 59%는
blinker 무관** — 즉 leadRadar 반복토글+dRel점프 현상 자체는 차선변경에
국한된 게 아니라 이미 검증 끝난 일반 주행에서도 흔함. 106차가 확보한
3건은 화면녹화가 있어 검증 가능했던 표본에 불과했을 가능성 —
"차선변경이 원인"이라는 인과관계는 표본편향일 수 있음(아직 반증은
아님). 상세는 FINDINGS.md 107차 참고.

**보류된 것**: 옵션1/옵션2 패치(confirm-hold 방식)는 착수 안 함 —
위 재검토가 끝나기 전까지는 범위(차선변경 한정 vs 일반)조차 확정 안 됨.

**다음 세션 최우선**:
1. `replay_boost_duration.py`(73차, 이미 존재)를 51개 플리커 클러스터
   구간(특히 would_trigger_ttc_danger=True 22건 내외)에 실행 —
   "danger override가 boost를 강제복귀시키는" 106차 사례3 패턴이
   blinker 무관 구간에서도 실제로 재현되는지 확인. **아직 미실시**.
2. 재현 여부에 따라 패치 범위(차선변경 한정 vs leadRadar 플리커 일반)
   재확정 후 패치 설계 재착수.
3. 92bb45496d/947fbb7dc6(105/106차 실사례) 재검증하려면 사용자가
   `내차_차선변경.Zip` 재업로드 필요(devnotes에 미캐싱, 컨테이너
   리셋으로 소실).

**이번 세션 변경 파일**: `toolkit/analysis_helpers.py`(함수 추가),
`toolkit/README.md`, `toolkit/CHANGELOG.md`, `FINDINGS.md`, 이 WIP.md
항목. `ryu` 코드 변경 없음.

---

## 106차 (완료 — 105차 체크포인트 완결, 코드 변경 없음) — 차선변경 중 leadRadar 핸드오프 급감속 원인 확정 (92bb45496d/947fbb7dc6 재현)

**입력**: 105차와 동일 파일명(`내차_차선변경.Zip`) 재업로드 — 이번엔
260827 클립 2건에 대응하는 정정된 라우트(`947fbb7dc6`, seg0~3)가
포함되어 105차의 "매칭 불일치" 문제가 해소됨.

**시각 매핑**: 클립 파일명(폰 클럭) vs 라우트 폴더명(디바이스 클럭)
사이 **~23초 오프셋**을 실측 확인(qcamera 프레임 vs 클립 프레임
HUD 대조로 확정) — 클립 끝부분 1~2초가 실제 사건 시각과 일치.

**핵심 결론**: 방향지시등(blinker) 켜지는 차선변경 시도마다
`leadRadar` 플래그가 `True/False`로 반복 토글되며 매 토글마다
`leadDRel`이 물리적으로 불가능한 순간변화율로 점프(레이더 핸드오프
불연속, 73차/76차가 이미 다루는 패턴). 3개 독립 사례로 확인:
- 92bb45496d seg4 t=4758.22 (mild, aEgo -1.12) — 화면녹화 HUD로
  리드 트랙ID `99→102→104` 스위치 시각 확인(105차 "후보이벤트A" 원인 확정)
- 947fbb7dc6 seg1 t=2575.37 (중간, aEgo -2.4)
- 947fbb7dc6 seg3 t=2683.88~2685.73 (**severe**, 1.85초간 4회+ 토글
  후 TTC danger 트리거 min_ttc=1.55s, aEgo 최저 **-3.78**) — 사용자
  체감 "급감속"과 가장 부합하는 규모, **76차가 미검증으로 남긴
  "harsh braking 실사례" 최초 확보**

**중요 발견**: 73차/76차의 4.0s hard-hold + release-rate 완화
메커니즘은 이미 적용된 코드(`bc1bcb0f6ff0`)에서 작동 중이었으나,
severe 사례에서는 TTC danger override가 뜨는 순간 boost가 설계상
즉시 base로 강제복귀(`force_revert`) — 정작 가장 필요한 순간에
jerk 완화가 꺼지는 구조. 상세는 FINDINGS.md 106차 항목 참고.

**다음 세션 최우선**:
1. `extract_log.py`에 `leadTrackId`(cereal `trackId` 필드 존재 확인함)
   컬럼 추가 — 현재는 화면녹화 HUD 육안대조에만 의존해 트랙 스위치를
   확인 가능(화면녹화 없는 로그는 검증 불가), 정량화 필요.
2. severe 사례(947fbb7dc6 seg3)의 "안정적으로 보이는 -9.2m/s 접근"이
   진짜 위험인지 트랙 불안정 연장선인지 판단 — 트랙ID 컬럼 확보 후
   재검토.
3. 위 분석 기반으로 방안 설계 착수(danger override와 핸드오프 직후
   유예기간 상호작용 조정 등) — **아직 패치 없음, 설계 논의 필요**.

**이번 세션 산출물**: `/home/claude/work/route_92bb45496d.csv`,
`route_947fbb7dc6.csv`, `frames_qcam/`, `frames_clip/` — 전부 컨테이너
리셋 시 소실, 재현 필요시 원본 zip 재업로드 후 동일 커맨드로 재추출.
FINDINGS.md/WIP.md 변경(이 항목들)만 devnotes에 반영, `toolkit/` 변경
없음(기존 도구로 전부 처리 가능했음).

---

## 105차 (완료 — 106차에서 결론 확정) — 사용자 제보 "차선변경 중 급감속" 실차 로그 분석 (내차_차선변경.zip)

### 요청 배경
사용자가 화면녹화(clip.mp4) 3건 + qcamera/rlog/qlog 라우트 3건 + 20세그 zip 1건을
`내차_차선변경.Zip`으로 업로드. "차선변경시 변경하려는 차선의 앞차에 대해
급감속 발생" 재현 로그 분석 요청. **파일명이 cp437/cp949 깨짐 상태로 담겨있어
`zipfile` + `filename.encode('cp437').decode('cp949')` 재해석 후 정상 추출됨**
(주의: 향후 유사 업로드도 이 패턴 우선 시도).

### 업로드 파일 매핑 현황
- `내차 차선변경 급감속_260828_101139_clip.mp4` (30초) ↔ 라우트
  `92bb45496d` 세그3/4/5 (`20260828_101055`/`101155`/`101256`, 각 60초,
  총 180초 = wall 10:10:55~10:13:56) — **폴더명 시각대가 겹쳐 이 클립과
  대응되는 라우트로 확정**. `extract_log.py`로 3600행 CSV 추출 완료
  (`/home/claude/work/route_92bb45496d.csv`, commit `bc1bcb0f6ff0`
  `c3-ms-dev`, `segment_state_carryover_fix: true`).
- `내차 차선변경 급감속_260827_113702_clip.mp4`,
  `..._260827_113848_clip.mp4` (2건) ↔ 대응 라우트 **불일치 발견**.
  업로드된 `20260827_121614_00000339--ce1f43d848_x20seg.zip`(20세그)을
  열어 세그 폴더명 확인한 결과 이 라우트는 wall **12:16:14~12:36:14**
  구간만 포함 — 두 클립 시각(11:37:02, 11:38:48)과 **약 39~40분 차이**로
  전혀 겹치지 않음. 즉 **이 2건 클립에 대응하는 로그가 이번 업로드에
  없음** (디바이스 시계 오프셋 문제인지, 잘못된 라우트 업로드인지는
  미확인). → **다음 세션 시작 전 사용자에게 확인 필요**: (a) 올바른
  라우트를 다시 업로드하거나 (b) 이 두 클립 분석은 보류.

### 92bb45496d(260828_101139 클립) 분석 진행 상황 — 결론 미확정
- CSV에서 `laneChangeState`는 전 구간 `off`로만 찍힘(이 라우트에서는
  차선변경이 openpilot 자동 조향에 의한 것이 아니라 **운전자 수동
  차선변경**이었을 가능성 — `rightBlinker` True 구간 t=4713.5~4717.07
  (seg3), `leftBlinker` True 구간 t=4756.3~4759.87(seg4) 확인됨.
- **후보 이벤트 A (seg4, t≈4759.7~4760.0, wall≈10:12:34)**: `leftBlinker`
  꺼지는 시점 직후 `leadDRel`이 **18.4m → 58.8m로 한 프레임 만에 점프**,
  동시에 `leadVRel`이 **-1.3 → +5.5로 부호 반전**하며 `aEgo`가 이 구간
  전체 라우트 중 **최저치 -1.12 m/s²**(global min)까지 하락. 이 패턴은
  devnotes에 기록된 **비전→레이더 핸드오프 vRel 불연속(72~73차, 방안
  I/G 영역)과 매우 유사** — 좌측 차선변경 완료 직후 새 차선의 선행차를
  잘못/불안정하게 재포착하며 급감속했을 가능성이 있는 **유력 후보**.
- 다만 **이 이벤트(wall≈10:12:34)가 클립(10:11:09~10:11:39 추정) 시간대
  안에 실제로 포함되는지 아직 프레임 대조로 확정 못함** — 라우트
  폴더명 기준 시각과 화면녹화 파일명 시각이 정확히 일치한다는 보장이
  없어(디바이스 클럭 vs 폰 클럭 오차 가능), `extract_dashcam_frames.py`로
  qcamera 프레임을 여러 후보 시각(seg3 t=4661/4664/4667/4670/4673/4676,
  4679/4684/4690/4700/4706/4712)에서 뽑아 클립 프레임(ffmpeg로 1초
  간격 추출, `/home/claude/work/frame_1s_*.png`)과 **도로 풍경(가드레일
  곡선, 방음벽, 선행 차량 위치)을 육안 대조 중이었으나 완료 전 체크포인트**.
- **참고로 확인된 사실(급감속과 무관, 오인 주의)**: seg3 구간 t≈4660~4691,
  t≈4691~4716에 vEgo가 95→81kph로 떨어지는 **완만한 감속 2회**가 있는데,
  이는 `desiredSpeed`가 200→88로 떨어지는 패턴과 정확히 일치 —
  **고정식 과속카메라(88kph 제한) 접근에 따른 정상 감속**이며 리드차량과
  무관(`leadStatus=False` 전 구간). 클립 초반 화면의 "과속(고정식) 88,
  504m" 배너와 일치하는 정상 동작이므로 "급감속 원인"에서 배제할 것.

### 남은 작업 (다음 세션 시작점)
1. qcamera 프레임 vs 클립 프레임 육안 대조 마무리 → 클립이 실제로
   담고 있는 route t 구간을 확정 (현재 유력 두 후보: (a) 초반 방음벽
   구간 t≈4660~4680대, (b) 후보이벤트A 부근 t≈4756~4762대 — 폴더명
   시각 계산상 클립은 (a)에 더 가깝지만 확정 아님).
2. 확정되면 `analysis_helpers.dRel_jump_ego_maneuver_overlap()` /
   `curve_lead_dRel_jump_events()`을 seg3+seg4 전체에 돌려 후보이벤트A
   외 추가 점프 이벤트 유무 스캔.
3. 후보이벤트A가 클립과 무관한 것으로 판명되면, 클립 구간 자체에서
   별도의 급감속 이벤트를 처음부터 재탐색.
4. 260827 클립 2건: 사용자에게 로그 매칭 불일치 안내 후 재업로드 요청.
5. 결론 확정 시 FINDINGS.md에 정식 기록 + 필요시 방안 설계(방안 I/C
   확장 검토).

### 이번 체크포인트 시점 산출물
- `/home/claude/work/route_92bb45496d.csv` (+`.meta.json`) — 컨테이너
  리셋 시 소실, 재사용 필요하면 다음 세션에서 동일 커맨드로 재추출
  (`extract_log.py /home/claude/work/route_92bb45496d ... --repo
  /home/claude/ryu`, 원본 세그 폴더는 업로드 zip 재해동 필요).
- 코드/devnotes 파일 변경 없음(이 WIP.md 항목 추가가 유일한 변경) —
  FINDINGS.md/PARAMS_REGISTRY.md/toolkit/ 변경 없음.
## 104차 (완료 — 분석만, 코드 변경 없음) — 오탐(A)/반응둔감(B) 제보 실차 로그 2건 분석

**입력**: dashcam zip 2건(seg10/seg11) + 화면녹화 mp4 1건, 제보 내용
"녹화영상보면 오탐 및 앞차에 반응 둔감".

**작업 순서**: 세션 시작(devnotes/ryu clone) → WIP.md 회차 확인(103차
확인) → 업로드 파일 확인 → toolkit/README.md에서 dashcam 분석 도구
확인 → zip 내용물 확인 → mp4 메타데이터 확인 → seg10/seg11 통합 route
폴더 구성 → `extract_log.py`로 CSV 추출 → meta.json으로 커밋 시점 확인
(101차 이후, 코드 변경 없는 순수 분석 세션으로 결정) → `analysis_helpers.py`
기존 함수(`five_item_scan`, TTC danger 탐지, harsh_brake 탐지 등)로
기본 스캔 → 위험/오탐 후보 구간 상세 로그 대조(t=683~689, t=726~731) →
조향각/곡률/트랙ID로 커브 여부 및 타겟 스위치 여부 확인 →
`extract_dashcam_frames.py`로 두 구간 핵심 시점 qcamera 프레임 추출/
확인(t=682/683.2/684.3/686.7/688.3, t=727.5/730.5/731.1) → FINDINGS.md
중복 확인(grep) → 104차 항목 작성.

**결과**: Finding A(오탐, NEEDS_VALIDATION)/Finding B(반응둔감 —
탐지오류 아닌 것으로 재분류) 2건을 FINDINGS.md에 기록. 상세는
FINDINGS.md "104차" 항목 참고. 코드 변경 없어 LAST_ANALYZED.md엔
분석 세션 기록만 추가(패치 없음).

**다음 세션**:
1. Finding A: 조향각 증가+레이더 유실 구간에서 vision-only 추정이
   원거리로 오판하는 사각지대 — 재현 로그 추가 확보 후 방안 설계 착수.
2. Finding B: 안정적 레이더 접근 중 desiredSpeed(route/vturn)가
   우선시돼 감속이 지연되는 우선순위 로직 문제 — `carrot_serv.py`
   min() 소스선택/`long_mpc.py` 리드 게이팅 교차점 코드리딩부터.
3. mp4 클립은 이번 두 사례 시각과 겹치지 않아 미활용 — 향후 제보 시
   클립 타임스탬프와 실제 이벤트 시각을 먼저 대조할 것.

---

## 103차 (완료 — WIP.md/LAST_ANALYZED.md 인코딩 손상 복구 + Downloads 처리 Copy→Move 절차 개정) — devnotes push 인코딩 사고 대응

**배경**: 102차 devnotes push 과정에서 rebase 충돌이 발생, Claude가
사용자에게 `(Get-Content WIP.md) | Where-Object {...} | Set-Content
WIP.md` 형태의 PowerShell 명령을 병합용으로 안내했음. Windows
PowerShell 5.1의 `Get-Content`/`Set-Content` 기본 인코딩이 UTF-8이
아니어서, 이 명령이 실행되며 WIP.md/LAST_ANALYZED.md 전체(100차
이상 누적된 한글 기록)의 비-ASCII 문자가 전부 `?`(리터럴 손실)로
깨진 채 커밋(`ac0ddbb`)되어 origin/main에 push됨.

**손상 확인**: 103차 세션 시작 시 devnotes fresh clone 후 바이트 단위
검사(`0x80` 이상 바이트 뒤에 오는 리터럴 `0x3F` 카운트)로 발견 —
WIP.md 12,931곳, LAST_ANALYZED.md 2,637곳 손상. `toolkit/*`(이번
merge에서 손대지 않은 파일)은 0곳으로 정상 — 손상 원인이 해당
PowerShell 명령 실행 범위와 정확히 일치함을 확인.

**복구**: 손상 이전 커밋 `495b8de`(101차까지, origin에 남아있던 정상
상태)의 WIP.md/LAST_ANALYZED.md를 기준으로 101차 이하 전체 이력을
바이트 단위로 완전 복구(디코딩/카운트 검증 완료, 의심 `?` 0~3건
수준으로 정상 범위). 그 위에 102차 신규 항목을 얹음:
- `LAST_ANALYZED.md` 102차 항목: 이 대화 이전 턴에 남아있던 원문
  전체를 그대로 사용 — **완전 복구**.
- `WIP.md` 102차 항목: 이 대화에 남아있던 원문은 앞부분(요청/범위/
  방법 문단)까지만 확보됨. 나머지(결과/산출물/다음 단계 문단)는
  `LAST_ANALYZED.md` 요약과 세션 맥락을 근거로 **재구성**했으며,
  항목 하단에 재구성 사실과 범위를 명시하는 편집 메모를 남겨둠 —
  원본과 100% 일치 보장 안 됨.

**재발 방지 규칙 신설** (`PROJECT_INSTRUCTIONS.md` 개정, 103차):
한글 등 비-ASCII 텍스트가 포함된 파일의 내용 편집/병합(git rebase
충돌 해결 포함)은 앞으로 사용자 PowerShell에서 직접 하지 않는다.
Claude가 컨테이너 안에서 완성된 파일을 만들어 다운로드시키고,
사용자는 그 파일을 이동(Move)만 하도록 절차 변경.

**추가 요청 처리**: "다운로드 폴더 → 레포"로 파일을 옮길 때 기존
`Copy-Item`(복사, Downloads에 파일이 계속 쌓임) 방식을 `Move-Item`
(이동, Downloads에서 제거됨) 방식으로 전면 교체 — `Copy-Latest`
함수를 `Move-Latest`로 개정하고 `PROJECT_INSTRUCTIONS.md`의 "작업
결과물 전달 원칙" 절에 반영.

**교훈**: (1) WIP.md 회차 표기 규칙에 "회차가 너무 길어지면 축약
고려 가능"이라는 문구가 있었지만, 이번 사고로 실제 위험은 파일
비대화가 아니라 **로컬 텍스트 처리 도구의 인코딩 불일치**였음 —
앞으로 devnotes 텍스트 파일에 대한 어떤 형태의 로컬 가공도 인코딩을
명시하지 않으면 위험하다는 점을 원칙으로 등록. (2) git 커밋은
스냅샷이므로, push되지 않은 로컬 전용 커밋(예: 리베이스 전
`56708a3`)은 원격에 흔적이 남지 않아 복구 근거가 될 수 없다 — 복구는
결국 **origin에 실제로 존재했던 마지막 정상 커밋**(`495b8de`)까지만
보장된다는 점 재확인.

**다음 단계**: 없음(devnotes 문서/기록 정정 세션, ryu 코드 변경 없음).

## 102차 (완료 — 전체코드 CPU/메모리 정적 재점검, 신규 이슈 없음 확인) — c3-ms-dev 최신본(101차 반영 `bc1bcb0`) 실시간 루프 파일 전수 재검토

**요청**: 101차(carrot_man 크래시 수정) 완료 후, "최신 c3-ms-dev 브랜치
전체코드를 면밀히 분석해서 CPU/메모리 점유율을 높이는 코드가 없는지"
재점검 요청.

**범위**: 실시간 루프가 도는 핵심 파일 8개 — `carrot_man.py`(20Hz),
`carrot_functions.py`, `carrot_serv.py`, `controlsd.py`(100Hz),
`radard.py`(20Hz), `longitudinal_planner.py`, `long_mpc.py`(MPC),
`cruise.py`. base `bc1bcb0`(101차 반영본).

**방법**: `toolkit/scan_perf_antipatterns.sh`(이번 세션 신규 작성,
toolkit 등록 완료) — deepcopy/미캐싱 Params.get/print/re.compile/
threading·subprocess/unbounded append/누적 dict/비벡터화 for-loop
grep 스캔 후, 매치 전부 컨텍스트(호출 빈도/캐싱 게이트/bounded 여부)
확인하며 8개 파일 전수 재검토.

**결과**: 새로운 성능 이슈 없음.
- Params I/O: 97~100차에 걸쳐 이미 캐싱(readParams 패턴)이 적용된
  상태 그대로 유지되고 있음을 재확인.
- deepcopy: 97차에 제거된 상태 유지, 재발 없음.
- 히스토리/버퍼류: 전부 `deque(maxlen=...)` 등으로 bounded 상태 확인.
- 스레드/subprocess 생성: 1회성 초기화 호출 외 루프 내 반복 생성 없음.
- 유일하게 남은 비벡터화 Python 루프인 `get_path_after_distance()`
  (haversine 기반 거리 계산, 20Hz 호출)는 증분 탐색 + lookahead 캡
  구조로 이미 실질적인 반복 상한이 있어, 즉시 조치가 필요한 문제는
  아니고 우선순위 낮은 벡터화 후보로만 기록.

**산출물**: `toolkit/scan_perf_antipatterns.sh` 신규 작성 및
`toolkit/README.md`/`toolkit/CHANGELOG.md` 등록 완료(재사용 가능).

**다음 단계**: 없음(코드 변경 없는 정적 재점검 세션). 101차 패치의
device 재부팅 검증은 이미 완료된 상태.

> ⚠️ 편집 메모(103차 세션 복구): 이 102차 항목은 devnotes 병합 과정에서
> Windows PowerShell `Get-Content | Set-Content` 명령이 기본 인코딩
> 문제로 한글을 깨뜨려 원본 텍스트 일부가 유실된 뒤, 같은 대화 내
> 이전 턴에 남아있던 원문 조각과 `LAST_ANALYZED.md` 102차 항목을
> 근거로 재구성한 버전이다. 상단 "요청/범위/방법" 문단은 원문 그대로
> 복구되었으나 "결과/산출물/다음 단계" 문단은 재구성분이므로, 세부
> 문구가 원본과 100% 일치하지 않을 수 있음.

## 101차 (완료 — 원인 확정+패치 적용+device 재부팅 검증까지 완료) — 100차 패치가 유발한 carrot_man __init__ AttributeError 크래시 원인 확정 및 수정

**배경**: 100차 패치(`eaee8b5`) 적용 후 device에서 carrot_man이
정상 기동하지 못하는 문제 발생. managerState에서
`carrot_man`이 `running=False, exitCode=1`로 수 초 간격 반복
재시작을 시도하다 실패(비정상 crash loop). 문제는 rlog/qlog
어디에도 carrot_man의 Python traceback이 전혀 남지 않았다는 점
— `logMessage`/`logCarrotMessage`를 전부 훑어도 관련 에러 로그
0건, stdout/stderr 캡처도 없음. 이는 크래시가 `cloudlog` 설정이
끝나기도 전, 즉 `__init__` 극초반에서 발생했음을 시사.

**원인 확정** (실제 코드 확인, 100차 패치본 `selfdrive/carrot/
carrot_man.py` 직접 분석): `__init__` 312번째 줄의
`self.carrot_curve_speed_params()` 호출이, 그 함수(1048번째 줄)가
참조하는 캐시 필드 `self._auto_curve_speed_factor`/
`self._auto_curve_speed_aggressiveness`보다 **먼저** 실행됨.
100차 패치가 이 캐시 필드 초기화 블록(`readParams` 포함)을
`__init__` 맨 끝(`self.is_metric = ...` 다음)에 새로 추가하면서,
이미 위쪽(312번째 줄)에 있던 `carrot_curve_speed_params()` 호출을
그 아래로 함께 옮기지 않은 게 원인. 결과적으로 `__init__` 도중
`AttributeError: 'CarrotMan' object has no attribute
'_auto_curve_speed_factor'`가 발생해 프로세스가 즉시 종료됨.
99차 이전(패치 전) 코드에서는 `carrot_curve_speed_params()`가
`self.params.get_*()`를 직접 호출했기 때문에 순서 의존성 자체가
없었음 — 100차의 캐싱 리팩터링이 새로 만들어낸 순서 버그.

**수정** (base `eaee8b5`, c3-ms-dev HEAD/100차 반영본, 로컬 커밋
`6bbccca`): 캐시 필드 초기화 블록(주석 포함 4줄:
`readParams`/`_is_onroad_cached`/`_auto_curve_speed_factor`/
`_auto_curve_speed_aggressiveness`)을 `__init__` 맨 끝에서
`self.carrot_curve_speed_params()` 호출 직전(`curvatureFilter`
설정 직후)으로 이동. 로직/캐시값/재조회 주기 등 100차의 실제
동작은 전혀 변경하지 않고 **초기화 순서만** 바로잡음. 이동한
블록에는 101차 원인 설명 주석 추가.

**검증**: `python3 -c "import ast; ast.parse(...)"` 문법 검증
통과. `git diff`로 이동만 있고 로직/값 변경 없음을 확인.
capnp/msgq 의존성 때문에 컨테이너에서 `long_mpc`류와 마찬가지로
실제 `CarrotMan()` 인스턴스화(런타임) 테스트는 불가 — **디바이스
부팅으로만 크래시 해소를 최종 확인 가능** (`PARAMS_REGISTRY.md`
"정적 크래시 검증" 원칙 참고).

**패치 전달**: `/mnt/user-data/outputs/0001-carrot-man-init-order-fix.patch`
(base `eaee8b5`, 즉 100차 반영본 위에 적용). `C:\dev\patch\`
(PC) 또는 Termux 환경이면 해당 위치에 저장 후 `git am` 적용.

**최종 검증 (device)**: 패치(`bc1bcb0`) 적용 후 device 재부팅 —
carrot_man crash loop 완전히 해소, 정상 기동 확인. 101차는 이걸로
완료.

**참고**: crash가 해소되어 carrot_man이 정상 기동하게 됐을 뿐,
100차 패치 자체(Params I/O 캐싱 + Shapely->numpy 벡터화)의 실제
주행 중 동작(체감/회귀 여부)은 아직 확인 전 — 100차 항목 "실차검증
대기" 상태는 별개로 그대로 이어짐(101차는 어디까지나 100차가
만든 크래시 버그만 해결한 것).

---

## 100차 (완료 — 구현+정적검증 완료, 실차검증 대기) — 99차 발견사항 전부 패치: carrot_man.py Params I/O 캐싱 + Shapely interpolate→numpy 벡터화 + 죽은코드 2건 제거

**배경**: 99차(정적 코드리뷰)가 찾은 3개 항목("패치구현" 사용자 확인 후)
전부 패치.

**구현** (base `6ab8ad6`, c3-ms-dev HEAD, 로컬 커밋 `8354ed6`):
1. `carrot_man.py` `__init__`에 `readParams`(카운트다운) +
   `_is_onroad_cached`/`_auto_curve_speed_factor`/
   `_auto_curve_speed_aggressiveness` 캐시 필드 추가, 신규 메서드
   `_refresh_cached_params()`(100프레임마다 재조회) 추가. 이 메서드를
   `broadcast_version_info()` 루프의 `self.sm.update(0)` 직후 매
   사이클 호출. `carrot_navi_route()`/`carrot_curve_speed_params()`는
   `self.params.get_*()` 직접호출 대신 캐시값 참조로 변경.
2. 신규 모듈함수 `resample_10m_np(points_xy, distance_interval)`
   (numpy 누적거리 배열 + 벡터화 선형보간) 추가, `carrot_navi_route()`
   내 `LineString(...)`+`while`+`.interpolate()` 블록을 이 함수
   호출 1줄로 교체. 최상단 `try: from shapely.geometry import
   LineString ... SHAPELY_AVAILABLE` 블록 및 `carrot_navi_route()`의
   `not SHAPELY_AVAILABLE` 가드 조건 제거(더 이상 shapely 불필요).
   `selfdrive/carrot/server/core.py`가 별도로 shapely를 쓰고 있어
   `pyproject.toml`의 `shapely` 의존성 자체는 손대지 않음.
3. `carrot_man.py:404`(`if False and self.navd_active:`),
   `controlsd.py:278`(`if False: # command` + `desire_map`) 죽은
   분기 삭제.

**사전검증** (`toolkit/verify_resample_np.py`, 100차 신규 — README/
CHANGELOG 등록 완료): 원본 Shapely 방식과 신규 numpy 방식을 랜덤
경로 20개 + 급커브 + 직선 + 경계조건(초단거리 2점, 길이가
distance_interval의 정확한 배수) + 600m급 긴 경로에 대해 좌표 비교 —
전부 PASS, 최대오차 1.2e-13m(부동소수점 오차 수준)로 100% 일치.

**적용검증**: `py_compile` 통과. 별도 클린 clone(`/home/claude/verify_apply`)
에서 `git reset --hard 6ab8ad6` 후 `git am
0001-carrot-man-perf-cleanup.patch` 충돌 없이 적용 확인, 적용 후
재컴파일도 통과.

**패치 전달**: `/mnt/user-data/outputs/0001-carrot-man-perf-cleanup.patch`
(base `6ab8ad6`). `C:\dev\patch\0001-carrot-man-perf-cleanup.patch`로
저장 후 `C:\dev\ryu`에서 `git am` 적용.

**실차검증 대기**: (a) `IsOnroad`/커브속도 계수(`AutoCurveSpeedFactor`/
`Aggressiveness`) 변경이 5s 지연 후 반영되는 것이 체감상 문제없는지,
(b) numpy 리샘플이 실제 GPS route(합성 데이터가 아닌 실주행 로그)에서도
곡률/out_speed 산출 결과가 기존과 동일한지 — 사전검증은 합성(랜덤+
수작업 케이스) 데이터 기준이었음, 실제 route 좌표로는 아직 재확인
안 함.

## 99차 (체크포인트 — 분석만 완료, 패치 미적용/사용자 결정 대기) — carrot_man.py 20Hz 루프 정적리뷰: Params I/O 미캐싱 2건 + Shapely interpolate 반복호출 + 죽은코드 2건 발견

**요청**: "코드 철저히 분석해서 다시 cpu 및 메모리 많이 차지하거나 불필요한
코드 찾아봐" — 97차/98차가 다루지 않은 범위(`carrot_man.py`) 위주 재검토.

**결과 요약** (상세는 FINDINGS.md 99차 참고):
1. `carrot_curve_speed_params()`/`carrot_navi_route()`가 20Hz 루프에서
   Params 3개(`AutoCurveSpeedFactor`,`AutoCurveSpeedAggressiveness`,
   `IsOnroad`)를 매 사이클 무캐싱 조회 — 97차와 동일 유형, `carrot_man.py`만
   누락돼 있었음.
2. `carrot_navi_route()`의 곡률 리샘플링이 Shapely `LineString.interpolate()`를
   20Hz × 최대 ~60회/사이클 반복호출 — GEOS가 매 호출마다 누적거리를
   처음부터 재탐색하므로 불필요한 재계산. numpy 벡터화로 대체 가능.
3. 죽은 코드 2건(`carrot_man.py:404`, `controlsd.py:278`의 `if False` 블록) —
   런타임 비용은 없으나 정리 대상.
4. 주석 435줄("5m 간격")과 실제 코드(`distance_interval=10.0`) 불일치 — 문서만
   정정 필요.

**아직 안 한 것**: 패치 구현 없음(97차와 동일하게 분석만). 사용자가
진행 원하면 100차에서 `carrot_functions.py`의 `params_count % 10` 캐싱
패턴 재사용 + `toolkit/sim_route_curvature_sample.py` 활용한 numpy 리샘플
회귀검증으로 패치 예정.

**base**: `6ab8ad6` (c3-ms-dev HEAD, 98차 패치 포함본), 코드 변경 없음(순수
리뷰), ryu 로컬 커밋 없음.

## 98차 (완료 — 구현+정적검증 완료, 실차검증 대기) — 97차 발견사항 전부 패치: Params I/O 캐싱 + compute_leads 내부함수 이동 + deepcopy 제거

**배경**: 97차(정적 코드리뷰)가 찾은 3개 항목을 사용자 확인 후 전부 패치.

**구현** (base `b67c291`, c3-ms-dev HEAD, 로컬 커밋 `05580ab`):
1. **Params I/O 캐싱** (`lateral_planner.py`의 `self.readParams` 카운터
   패턴 그대로 재사용):
   - `controlsd.py` `state_control()`(100Hz): `SteerRatioRate`/`CustomSR`/
     `UseLaneLineCurveSpeed`/`LatSmoothSec`/`SteerActuatorDelay`/
     `SpeedFromPCM`/`DisableDM` 7개 → 100프레임(~1s)마다 1회
   - `radard.py` `update()`(20Hz): `EnableRadarTracks`/`EnableCornerRadar`/
     `RadarLatFactor`/`RadarReactionFactor` 4개 → 100프레임(5s)마다 1회
   - `longitudinal_planner.py` `update()`(20Hz): `CommaLongAcc`/
     `LongActuatorDelay`/`VEgoStopping` 3개 → 100프레임(5s)마다 1회
2. **`compute_leads()` 내부함수 모듈레벨 이동**: `radard.py`의 `_ok()`/
   `_pick_two_with_gap()`(20Hz마다 재생성되던 클로저)를 모듈레벨
   `_lead_cand_ok()`/`_pick_two_with_gap()`으로 이동.
3. **`leadTwo` deepcopy→copy**: `get_RadarState()` 반환값이 float/bool/str만
   담긴 flat dict(중첩 가변객체 없음)임을 코드 확인 후 `.copy()`로 교체,
   `import copy` 제거.

**제어 로직/임계값 자체는 전혀 변경 없음** — 이번 패치는 순수 캐싱
리팩터. 부작용은 UI 파라미터 값 변경 시 반영 지연뿐(controlsd 최대~1s,
radard/longitudinal_planner 최대~5s) — 튜닝 중 즉각 반영을 기대하는
사용성과는 트레이드오프이나, `lateral_planner.py`/`carrot_functions.py`가
이미 이 트레이드오프를 채택 중이라 일관성 있음.

**검증**: `py_compile` 3파일 전부 통과. 로그 재생 시뮬레이션은 대상 아님
(제어값에 영향 없는 순수 I/O 캐싱이라 route 로그로 확인할 대상 자체가
없음 — behavior는 Params 반영 타이밍만 변함).

**전달**: `0001-98차-Params-IO-캐싱-compute_leads-이동-deepcopy제거.patch`
(base `b67c291`, 현재 origin `c3-ms-dev` HEAD 위에 바로 `git am` 가능).

**환경 변경 사항 (이번 세션부터)**: 사용자가 스마트폰 + Termux 환경으로
전환. 이후 devnotes/patch 로컬 저장 경로 및 push 절차는 PowerShell이
아닌 Termux(bash) 명령어로 안내.

**다음(최우선)**: 실차 드라이브 검증 —
1. UI에서 튜닝 파라미터(예: `LatSmoothSec`, `TFollowGap1` 등 캐싱 대상)
   변경 시 반영이 체감상 느려지지 않는지 (controlsd 최대 1s, 나머지 최대
   5s 지연은 설계상 허용 범위이나 실사용 체감 확인 필요).
2. 캐싱 전/후 조향·종방향 제어 동작 회귀 없는지 (특히 `SpeedFromPCM`/
   `DisableDM`처럼 안전 관련 파라미터가 지연 캐싱으로 인해 위험 상황에서
   불리하게 작동하지 않는지 — 단, 두 파라미터 모두 차량 설정값 성격이라
   주행 중 실시간 변경 대상이 아님을 확인함, 위험도 낮음).
3. 97차/98차는 로그분석 범위 밖 — `LAST_ANALYZED.md` 갱신 대상 아님.

## 97차 (완료 — 정적 코드리뷰만, 코드 변경 없음) — c3-ms-dev 전체 불필요코드/CPU부하 점검

**요청**: c3-ms-dev 최신(`b67c291`) 코드 전체를 대상으로 (1) 불필요한
코드 존재 여부, (2) comma 기기 구동 시 CPU 연산을 과다 소모하는 코드
존재 여부 점검. 로그분석/실차검증 아님 — 순수 정적 리뷰.

**결과 (상세는 FINDINGS.md 97차 항목 참고)**:
- **핵심 발견**: `controlsd.py` `state_control()`(100Hz 루프) 내
  rate-limit 없는 `Params.get_*()` 호출 10건 — 초당 최대 1000회
  불필요한 파라미터 I/O 가능성. `radard.py`(20Hz, 4건),
  `longitudinal_planner.py`(20Hz, 3건)에도 동일 패턴 있음.
- **대조**: `lateral_planner.py`/`carrot_functions.py`는 이미
  프레임 카운터로 분산 캐싱하는 올바른 패턴을 구현해뒀음 — 위
  3개 파일만 이 패턴이 빠져 일관성 없음.
- **부수 발견**: `radard.py` `compute_leads()` 내부함수 2개가
  20Hz마다 재생성(오버헤드), `leadTwo`의 불필요한 `deepcopy`
  (flat dict라 `.copy()`로 충분), `controlsd.py`의
  `smooth_value()` 내부함수도 100Hz마다 재생성.
- **불필요 코드 자체는 발견 안 됨**: 긴 주석 블록들은 문서화 주석,
  `frogpilot`은 `fleet_manager`로 실제 사용 중(죽은 코드 아님).

**다음 단계 (미정, 사용자 확인 필요)**:
1. 위 발견에 대한 패치 작성 여부 — 요청 시 진행
   (`state_control()`/`radard.update()`/`longitudinal_planner.update()`에
   `carrot_functions.py` 스타일 카운터 캐싱 적용 + `compute_leads()`
   내부함수 클래스레벨 이동 + `deepcopy`→`.copy()` 교체)
2. 패치화하면 실차 검증 항목: (a) 파라미터 UI에서 값 변경 시
   반영 지연이 체감되지 않는지(캐싱 주기 설계 확인), (b) 기존
   동작 회귀 없는지(zero-regression)
3. 이 항목은 로그분석 범위 밖이라 `LAST_ANALYZED.md` 갱신 대상 아님

## 96차 (완료 — 교차검토만, 코드 변경 없음) — c3-ms-curv 병합분(87차)과 94차 로직 상호작용 검토

- 95차 병합 직후 요청으로 진행: 병합된 81/82/84/85/87/91차와 94차가
  코드 레벨로 겹치는 지점이 있는지 확인.
- 81/82/84/85/91차(route/vturn/lookahead, carrot_man.py/carrot_serv.py)는
  94차(long_mpc.py)와 완전 독립 — 상호작용 없음.
- 87차(radard.py, VisionTrack 고스트 래치 수정)만 94차(discontinuity
  리셋)와 로직상 겹침 확인: 94차의 discontinuity 판정 조건
  (`lead_one_status_now and not radarstate.leadOne.radar`, 비전 단독
  상태에서만 평가)이 87차가 다루는 고스트 tentative 트랙과 정확히
  같은 조건 공간. 87차는 고스트의 dRel 노이즈가 94차를 스퓨리어스하게
  발동시킬 수 있는 노출시간을 최대 120초 → 최대 3초로 축소(보완관계),
  단 그 ≤3초 구간 안에서는 여전히 94차가 반응할 수 있는 잔여 갭 존재.
- 상세 근거/코드 인용은 FINDINGS.md 95차 항목 참고. **코드 변경 없음,
  관찰 대상으로만 기록.**
- **다음 세션 확인사항**: 실주행 로그에서 "커브/애매한 물체 스침 직후
  3초 이내 급감속 후 정상 복귀" 패턴 관찰되면 이 항목과 연결해서 확인.

## 95차 (완료 — c3-ms-curv → c3-ms-dev 병합 완료, 원격 푸시 확인 대기) — 81/82/84/85/87/91차 통합

- merge-base: `2d5174e` (79차)
- 병합 전 c3-ms-dev 단독 커밋: `6981b5d` (94차, 방안D 리셋)
- 병합 대상 c3-ms-curv 단독 커밋(오래된 순): `d7a647f`(81차a,b) `451a3b9`(82차) `2a91c3f`(84차) `284457f`(85차) `cf32b5d`(87차) `6d15391`(91차)
- 컨테이너 dry-run(`git merge --no-commit --no-ff`) 및 사용자 로컬 실제 병합(`ort` strategy) 둘 다 **충돌 없이 성공**
- 변경 파일: `selfdrive/carrot/carrot_man.py`, `selfdrive/carrot/carrot_serv.py`, `selfdrive/controls/radard.py` — 총 3 files changed, 120 insertions(+), 7 deletions(-)
- 사용자가 로컬에서 `git merge origin/c3-ms-curv -m "Merge c3-ms-curv into c3-ms-dev (81,82,84,85,87,91차 통합)"` 실행 완료, 이어서 `git push origin c3-ms-dev` 예정
- 이번 병합은 브랜치 병합(2-parent merge commit)이라 기존 `NNNN-xxx.patch`(git am용 단일 패치) 방식 대신 사용자 로컬 `git merge` 직접 실행으로 처리함
- **다음 세션 확인사항**: `git log --oneline -5 origin/c3-ms-dev`로 병합 커밋이 원격에 반영됐는지 확인, 이후 81/82/84/85/87/91차와 94차(방안D)가 한 브랜치에 공존하는 상태에서 실주행 검증 필요


**배경**: 사용자가 이전 세션(컨테이너 리셋으로 중단됨, `이전세션.txt`로 전달)에서
"내차_차선변경.zip"(차선변경 시 옆차선 앞차 인식 급감속) 분석 도중 63차 계속
FINDINGS.md 기록(r1-14 사각지대: 방안C가 `_lead_acq_timer`만 리셋하고
`frac_rate`/`frac_ttc`가 읽는 `_vision_dRel_rate`는 그대로 둬서, radar 락온이
급감속 종료 이후로 늦는 사례에서는 frac_rate가 discontinuity 트리거 이후에도
DANGER급으로 계속 유지되는 문제)를 재검토 — 63차 계속이 이미 제시했던 "방안D"
(discontinuity 트리거 시 `_vision_dRel_rate`/`_vision_dRel_rate_window`도 함께
리셋)를 이번 세션에서 실제 구현·검증까지 완료.

**구현** (`c3-ms-dev`, 로컬 커밋 `866e934`, base `2d5174e`(79차 HEAD)):
`long_mpc.py`의 discontinuity 트리거 블록(`_lead_acq_timer=0.0` 리셋 직후)에
`self._vision_dRel_rate=0.0`/`self._vision_dRel_rate_window.clear()`/
`self._vision_dRel_prev=None` 3줄 추가. 트리거 조건 자체(`DREL_DISCONTINUITY_*`
문턱)는 전혀 안 건드림 — discontinuity가 아예 안 걸리는 상황(정상 완만 접근)엔
구조적으로 개입 불가능.

**검증** (`toolkit/sim_drel_discontinuity_d.py` 신규, 4개 시나리오 전부 PASS):
1. r1-14류(radar 락온이 급감속 종료 이후로 지연) 재현 — UNPATCHED는 트리거
   프레임에서도, 그 이후 완만한 접근으로 바뀐 뒤에도 frac_rate=1.0(DANGER급)이
   계속 유지됨(저역통과 필터에 남은 급락 잔류 오염 때문). **PATCHED는 트리거
   프레임에서 즉시 frac_rate=0.000으로 리셋** — 63차 계속이 발견한 무효화 문제
   해소 확인.
2. 정상 완만 접근(discontinuity 없음) — PATCHED/UNPATCHED rate 완전 동일
   (diff=0.000000, 회귀 없음).
3. r1-3류(radar가 급락 직후 바로 락온) — 기존 코드가 락온 프레임에서 이미
   rate/window/prev를 무조건 리셋하는 별도 경로를 갖고 있어서, 락온 이후엔
   방안D 유무와 무관하게 두 버전이 완전히 동일(diff=0.000000) — 63차 계속이
   확인했던 "이 조합은 이미 효과 있음" 결론이 이번 패치로 깨지지 않음 확인.
4. danger override 독립성 — `process_lead()`의 `ttc_now`는 `_vision_dRel_rate`와
   코드상 완전히 분리된 변수라 이번 리셋과 무관하게 항상 즉시 반응(정적 확인).

`py_compile` 통과, 로컬 커밋 `866e934`(base `2d5174e`).

**전달**: `0001-94-방안D-discontinuity-vision_dRel_rate-window-리셋.patch`를
`/mnt/user-data/outputs/`에 전달(base `2d5174e`, 즉 현재 origin `c3-ms-dev`
HEAD 위에 바로 `git am` 가능).

**다음(최우선)**:
1. 사용자가 `C:\dev\ryu`에서 `git am` 적용 + `git push origin c3-ms-dev`.
2. **실차 드라이브 검증** — (a) 원 제보(차선변경 시 옆차선 앞차 인식 급감속,
   특히 radar 락온이 늦는 케이스)에서 실제로 완화되는지, (b) **회귀 검증
   필수** — r1-3류(radar 즉시 락온, 이미 검증된 조합)에서 체감 변화 없는지,
   진짜 위험(danger override, TTC<=2.5s)은 이 리셋과 무관하게 그대로
   즉시 반응하는지.
3. `이전세션.txt`에 언급된 3개 route(`00000329--d2a61d2a73`,
   `0000032b--4a32e2c0d3`, `0000032c--bc4301a25d`, 전부 commit `2d5174e`
   기록)로 이 패치 적용 전/후 `regression_report()` 정량 비교 검토 —
   원본 zip이 이번 세션엔 없어(이전세션.txt는 텍스트 로그만) 재분석하려면
   사용자 재업로드 필요.

## 93차 (완료 — 시뮬레이션 회귀검증만, 코드 변경 없음) — 91차(ROUTE_ENTRY_MARGIN_KPH) 국도 연속곡선 로그(baseline) 정식 회귀검증, **문제 없음**

**배경**: 92차가 "91차 적용후 로그"로 오분류했던 route(0000032d--c0e3054c4a,
seg13~19)를 사용자가 "91차 적용 이전 baseline"으로 재확인해줘서, 이번엔
실제 91차 로직(desiredCurvature 적분 재구성+역방향DP, margin 파라미터화)
그대로 이 로그 전체 구간에 재생해 정식 회귀검증 수행(92차는 baseline
로그의 turn_speed_violation/harsh_brake만 봤을 뿐 91차 로직 자체를
시뮬레이션한 게 아니었음 — 그 결론은 이미 92차에서 폐기됨).

**핵심 결과** (상세는 FINDINGS.md 93차 참고): 로그 전체(420초) 3초
간격 126개 스냅샷 스윕 —
1. 직선구간(무곡률) 오탐 0건.
2. 75/126건에서 조기개입 정상 확인, 이 구간들 **정점 목표값(min_speed)
   차이 평균/최대 0.00km/h** — 설계 의도(스케줄만 당김, 목표값 불변)
   정확히 확인.
3. 역전 버그(margin이 오히려 개입을 늦추는 경우) 0건.
4. turn_speed_violation/harsh_brake는 92차와 동일하게 전부 src=vturn
   기인, route/91차와 무관 재확인.

**결론**: 91차가 bc4301a25d(89/90/91차 원 검증 route) 외에 성격이 다른
route(국도 연속곡선)에서도 직선 오탐 없이 설계대로 동작함을 확인 —
89/90/91차 계열 첫 교차 route 검증.

**코드 변경**: `toolkit/sim_route_margin_regression_scan.py` 신규
(devnotes만, ryu 미변경).

**다음(최우선, 변경 없음 — 81/82/84/85/87/91차 전부 여전히 실차검증
대기 상태)**:
1. **실차 드라이브 검증** — 91차: (a) 커브 진입 시 route가 실제로
   vturn보다 먼저 개입하는 체감, (b) 직선/완만 구간 오탐 없는지(이번
   시뮬레이션상 0건이었으나 실제 GPS 노이즈는 다를 수 있음), (c) 커브B류
   (TBT 근접) 부작용 없는지.
2. 81차(vturn_safe_time 2.0s/TBT 500m 게이트 제거)/82차(원복측 대칭
   버퍼)/84차(동적 lookahead 캡 300~500m)/85차(캡 600m 상향)/87차
   (VisionTrack ghost timeout 3.0s) 전부 아직 실차 미검증 — 91차와
   함께 같은 드라이브에서 동시 확인 가능.

## 90차 (완료 — 시뮬레이션 검증만, 코드 변경 없음) — 89차 대안1(route 곡률 chord 축소) 검증, **효과 미미로 판정**

**배경**: 89차 곡선_고속도로램프2(같은 route bc4301a25d) 재업로드 →
89차가 제시한 개선 대안 4개 중 1번(`sample` 4->2/3, chord 40m->20~30m)을
검증하라는 지시.

**방법**: raw navi_points가 로그에 없어(navRoute capnp 미기록 확인)
`desiredCurvature` 시간적분으로 실주행 경로를 재구성, `carrot_man.py`
곡률+속도+역방향DP 로직을 그대로 복제(`toolkit/sim_route_curvature_sample.py`
신규)해 sample 2/3/4 비교.

**핵심 결과**: 정점 근처 최소 목표속도가 sample=4에서도 이미 78km/h
(vturn 실측 73km/h와 5km/h 차이)로 근접 — sample=2로 낮춰도 75.7km/h
(효과 ~2.5km/h뿐). 실제 로그의 route 최저값(121)-vturn 실측(73) 간
48km/h 갭에 비해 미미. raw navi_points 희소성(30/60/100m) 실험도
병행했으나 희소성이 sample 효과를 체계적으로 키우지 않고 오히려
노이즈성 스파이크(과대추정 방향)만 유발 — "성긴 raw 포인트+chord"
가설도 기각.

**결론**: 89차 대안1 단독으로는 관찰된 과소평가 갭을 설명/해소하기
부족. 진짜 원인은 chord 길이보다 실제 navi GPS 폴리라인 자체의 형상
정밀도(지도 데이터의 램프 표현) 쪽일 가능성이 커짐(NEEDS_VALIDATION,
raw navi_points 직접 로깅 없이는 확정 불가). 상세는 FINDINGS.md 90차
참고. **코드 변경 없음(시뮬레이션만).**

**다음(사용자 결정 대기)**:
1. **[신규 제안]** `carrot_man.py`에 raw navi_points/curvature 배열을
   디버그 계측 로깅하는 패치를 먼저 적용해 다음 로그에서 직접 검증
   (89/90차가 계속 가설 수준에 머무르는 근본 원인인 raw 데이터 부재
   해소).
2. 89차 대안2(route/vturn 괴리 기반 보정)/3(안전마진 휴리스틱) 순위
   재검토 — 1번 효과가 작아 순위 재조정 필요.
3. 커브B(t≈9259~9302, 급격한 램프+교차로)도 동일 방식 교차검증하면
   표본 2건으로 결론력 보강 가능.

## 89차 (완료 — 원인분석만, 코드 변경 없음) — 곡선_고속도로램프2, route 사전감속 과소평가 원인 규명 + 개선 대안 4개 제시

**배경**: 88차와 같은 route(`bc4301a25d`, `c3-ms-curv` 85차 HEAD `284457f`)의
seg12/13을 qcamera 포함 재업로드. 커브A(완만한 램프 진출로)/커브B(급격한
램프+교차로) 분석, 커브A 진입부 turn_speed_violation(16.73km/h/4.55초)
원인을 "route가 사전감속을 했는지" 질문에 답하며 규명.

**핵심 발견**: route가 t=9211.27부터 개입했으나 desiredSpeed를 200→121
km/h까지만 10초에 걸쳐 완만히 낮췄고, 그동안 vEgo는 계속 가속 중이라 실제
제동 효과가 전혀 없었음("서류상 사전감속"). t=9221.26에 vturn으로 전환되며
121→73km/h를 5초 만에 급락 — 이 급락이 overshoot의 직접 원인. **route가
산출한 최종 목표값(121) 자체가 vturn의 최종 요구치(73~77)보다 훨씬 높아
route가 이 커브의 조임을 과소평가했음이 CSV로 확인됨.**

**코드 레벨 원인 후보(NEEDS_VALIDATION)**: `carrot_navi_route()`의 곡률
계산이 3점을 40m 간격(`distance_interval=10.0 × sample=4`)으로 떼어
계산 — 반경 작은 램프 커브에서 순간곡률을 평활화(과소평가)할 가능성.
raw curvature/navi_points가 CSV에 없어 직접검증은 못함(가설).

**제시한 개선 대안 4개(사용자 결정 대기, 패치 미착수)**:
1. 곡률 샘플링 chord 축소(`sample` 4→2~3, 20~30m 간격) — 급커브 민감도↑,
   완만한 커브/직선 GPS 노이즈에 의한 오탐(불필요 감속) 회귀 리스크 있음,
   여러 커브로 A/B 검증 필요.
2. route가 산출한 목표값과 몇 초 뒤 vturn이 요구할 값 사이 괴리가 크면
   route 쪽에서 더 일찍 낮은 값으로 당기는 "격차 기반 보정" — vturn의
   lookahead 정보를 route DP 종점 조건에 반영하는 구조적 연동, 설계/검증
   비용 있음.
3. (저비용) 급조임 감지 시 목표속도에 안전마진(margin_kph)을 미리
   차감하는 휴리스틱 — 간단하지만 곡률 자체를 보정하는 게 아니라 임시방편.
4. (고비용, 구조적) route/vturn을 min() 승자독식 대신 두 소스의 구간별
   필요속도 프로파일을 물리적으로 병합해 재계산 — 근본적이나 리스크/작업량 큼.

우선순위/구현 여부는 사용자 결정 대기. 코드 변경 없음.

## 88차 (완료 — 분석만, 코드 변경 없음, **[정정] 브랜치 오판 수정**) — 곡선_고속도로_램프 실차 로그, c3-ms-curv(81/82차 반영, 87차 이전) route/vturn 결합 실측 확인

**[중요 정정]**: 최초 분석 시 세션시작 스크립트가 `ryu`를 항상 `c3-ms-dev` 브랜치로만
clone하기 때문에, `extract_log.py`의 `meta.json` commit 태그가 실제 로그가 기록된
브랜치와 무관하게 `c3-ms-dev` HEAD(`2d5174e`, 79차)로 찍혀 "81/82차 이전 baseline"
이라고 잘못 결론냄. **사용자 확인으로 실제로는 `c3-ms-curv` 브랜치, 87차(유령 파란박스
패치) 바로 이전 상태(=85차 HEAD `284457f`, 81/82/84/85차 전부 반영됨)임이 밝혀짐** —
`ryu` 저장소를 `git fetch origin c3-ms-curv` + `git checkout 284457f` 후 재추출해 확인
완료(재추출해도 CSV 수치 자체는 rlog 원본 데이터라 동일, `commit` 메타 태그만 정정됨).
**[프로세스 교훈]** 복수 브랜치(c3-ms-dev/c3-ms-curv)가 존재하는 현재 상태에서는
`meta.json`의 commit 태그를 곧이곧대로 신뢰하면 안 됨 — 분석 전 사용자에게 실제 주행
브랜치를 먼저 확인하거나, 여러 브랜치를 모두 fetch해 코드 내용(예: TBT 게이트 존재 여부)
으로 교차검증할 것. `SETUP.md`/세션시작 스크립트가 `c3-ms-dev`만 clone하는 구조를
바꾸지 않는 한 이 함정이 재발할 수 있음 — 다음 세션부터 유의.

**정정된 결론 (재분석)**: `284457f`(85차 HEAD) 기준 `carrot_serv.py`를 확인한 결과
81차 패치대로 **`turnSpeedControlMode in [2,3,4]`면 500m TBT게이트 없이 route가 항상
min() 후보에 참가**하는 코드가 이미 적용돼 있었음 — 즉 이전 결론("커브1에서 route가
게이트에 막혀 완전히 미참가")은 **틀림**. 실제로는:
- **커브1(t≈7170~7190.6, 우회전)**: route도 항상 후보로 경쟁했으나 412프레임 중 **24프레임
  (≈6%, t≈7177.8~7179.4 클러스터)에서만 route가 승리**, 나머지는 vturn이 더 엄격(낮은 값)해
  vturn이 대부분 담당. 게이트 배제가 아니라 **min() 경쟁에서 그때그때 진 것**.
- **커브2(t≈7193~7207.5, 좌회전)**: 290/290프레임(100%) route가 담당 — 이 구간은 route의
  GPS 폴리라인 기반 곡률 추정이 vturn(비전)보다 지속적으로 더 엄격했던 것으로 해석됨.
- 두 커브의 route 참가율 차이(6% vs 100%)는 TBT 게이트 때문이 아니라, **GPS 폴리라인
  곡률 계산이 커브마다 vturn 대비 얼마나 엄격하게 나오는지의 차이**로 재해석 필요 —
  프로젝트 온고잉 관심사인 "GPS 폴리라인 품질" 이슈와 연결될 수 있음(NEEDS_VALIDATION,
  route_speed 자체를 별도 로깅하지 않는 한 정확한 원인 특정은 어려움 — `extract_log.py`에
  route_speed/vturn 각각의 raw 후보값을 별도 컬럼으로 추가하는 계측 보강이 필요할 수 있음).

**나머지 관측(수치 자체는 최초 분석과 동일, 유효)**:
1. 최저 vEgo: 커브1 ≈84.2km/h(desiredSpeed≈89km/h, 최대감속 -0.95m/s²), 커브2 ≈81.9km/h
   (desiredSpeed≈84km/h, 최대감속 -0.94m/s²).
2. 탈출 후 회복: 커브1(vturn)은 3~4초 내 완전 해제(89→200km/h) — 82차 원복버퍼가 이미
   반영된 상태이므로 이게 82차 적용 후의 정상 속도. 커브2(route)는 계단식 급점프
   (84→129km/h, 약 1.6초) — DP 특성상 저역통과 없이 뛰는 정상 동작.
3. **src 하드-스위치 플리커**: 전체 로그 51회 전환 중 39회(76%)가 1초 이내 재전환 —
   81/82차 WIP "min() 하드-스위치 리뷰 필요" 미착수 항목이 실제로 빈번함을 재확인
   (결론 자체는 브랜치 오판과 무관하게 유효).
4. 안전지표: harsh_brake 0건, ttc_danger 0건. `turn_speed_violations` 2건(커브1 진입
   초입, overshoot 최대 5.11km/h, 0.5~0.66초) — 경미.

**코드 변경 없음(분석만).**

**다음(사용자 결정 대기)**:
1. route_speed(raw route 후보값) 자체를 CSV에 별도 컬럼으로 남기는 계측 보강 검토 —
   현재는 route가 이겼을 때(`src=='route'`)만 `desiredSpeed`로 값을 볼 수 있고, vturn이
   이기고 있을 때 route가 얼마나 근접했었는지는 알 수 없어 "왜 커브1에서 route가 6%만
   이겼는지"를 더 정밀하게 규명하기 어려움.
2. src 하드-스위치 플리커(76%) 완화 여부 — 여전히 저우선, 필요시 히스테리시스/블렌딩
   설계 검토.
3. `meta.json` 브랜치 오판 재발 방지 — 다음 세션부터 분석 착수 전 실제 주행 브랜치를
   사용자에게 확인하거나 코드 특징(게이트 존재 여부 등)으로 교차검증하는 절차 고려.

## 87차 (완료 — 원인분석+구현+시뮬레이션검증+패치전달 완료) — VisionTrack 팬텀(유령) 리드 트랙 영구고착 버그 수정

**배경**: 사용자가 화면 녹화(mp4)+route zip(`0000032d--c0e3054c4a`)을 업로드,
"패스 끝에 파란박스가 계속 표시되며 주행감이 이상해진다" 제보.

**원인 분석**(qcamera+CSV 대조, `c3-ms-curv` HEAD `284457f` 기준
`radard.py` `VisionTrack`): t=9793~9913(약120초) 내내 파란 박스(=
`radarState.leadOne`, UI 장식 아님)가 커브 바깥쪽 나무/가드레일 근처에
떠있는데 실제 앞차는 없음. `leadModelProb` 최대 0.095/최소 0.0003으로
정상등록(0.5)/예비등록(0.35) 문턱에 한참 못 미치는데도 `leadStatus=True`가
120초 유지됨. 근본원인: **60차 계속6(B안)의 사각지대** — `tentative_cnt`가
한번 `CNT_GATE`(10, 0.5s)에 도달해 `register_ok`가 래치되면, 이후 prob가
`TENTATIVE_PROB_GATE`(0.35) 밑으로 "영구적으로" 주저앉아도 기존 리셋
경로 3개(dPath 절대값 게이트/dRel jitter/dPath jitter)가 전부 prob가
[0.35,0.5] 구간 안에 있을 때만 평가되어 풀 방법이 없었음. 매 프레임
노이즈성 `dRel_candidate`를 실제 리드처럼 반영해 `desiredSpeed`/
`vTurnSpeed`를 흔들고 불필요한 급감속(t=9812~9814, aEgo -1.56) 유발
실측 확인.

**구현** (`c3-ms-curv` 브랜치, base `284457f`(85차 HEAD)): `radard.py`
`VisionTrack`에 `ghost_low_prob_time`(prob<`TENTATIVE_PROB_GATE` 연속
유지시간 누적, `self.radar_ts` 기반) 신규 필드 추가, `GHOST_TIMEOUT_S`
(3.0s) 초과 시 `tentative_cnt`를 강제로 0으로 리셋(다음 프레임
`register_ok` 재평가 시 자연스럽게 `self.reset()` 경로로 빠짐). 60차
B안 취지(짧은 prob 출렁임으로 진짜 리드를 오인 리셋하지 않음)는 그대로
보존 — "짧은 출렁임"과 "영구 소실"을 시간 길이(3.0s)로 구분.

**검증** (`work/sim_vision_track_ghost_timeout.py`, capnp 의존성 없는
순수 로직 재현): 3개 시나리오 전부 PASS —
1. 고스트(120s 영구소실): 패치 전 래치 고착 재현(끝까지 True), 패치 후
   t=3.5s에서 정상 해제.
2. 실제 리드 prob 노이즈성 출렁임(최대 연속저하 1.5s, GHOST_TIMEOUT 미만):
   패치 전/후 `register_ok` 시퀀스 **완전 동일**(회귀 없음 확인).
3. 실제 리드가 시야를 벗어나 영구 소실(10s): 패치 전 10초 내내 고착(기존
   버그), 패치 후 t=3.5s 정상 해제.
`py_compile` 통과, `verify_am_87`(base `284457f`)에서 `git am`+diff 0 확인.

**전달**: `0001-87-VisionTrack-tentative-GHOST_TIMEOUT_S-3.0s.patch`를
`/mnt/user-data/outputs/`에 전달(base `284457f`, `c3-ms-curv` 브랜치에
적용).

**신규 상수**: `VISION_TRACK_GHOST_TIMEOUT_S = 3.0` (NEEDS_VALIDATION,
실차 반응 보고 튜닝 필요 — 값이 너무 짧으면 실제 리드의 일시적 강한
가림/역광 등에서 조기 리셋 가능성, 너무 길면 팬텀 지속시간이 늘어남).

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`에서
`git remote set-branches --add origin c3-ms-curv`(로컬이 single-branch
클론이라 c3-ms-curv가 안 보이던 문제 해결) → `git fetch` → `git checkout -b
c3-ms-curv origin/c3-ms-curv` → `git am` 적용(로컬 커밋 `cf32b5d`) →
`git push origin c3-ms-curv` 완료. 컨테이너에서 `git fetch origin
c3-ms-curv:refs/remotes/origin/c3-ms-curv` 후 로컬 검증 커밋(`8d10c06`)과
diff 0(완전 동일) 재확인. origin `c3-ms-curv` HEAD: `284457f..cf32b5d`.

**다음(최우선)**:
1. ~~사용자 `git am` 적용 + push 확인.~~ → **완료**.
2. **실차 드라이브 검증** — (a) 이번에 재현된 것과 유사한 상황(커브
   진입부에서 짧게 애매한 물체 스침 후 대상 없음)에서 파란 박스가
   3~4초 내로 사라지는지, (b) 실제 리드(정지 앞차 등)를 놓치지 않고
   정상 추적하는지(회귀 확인), (c) 3.0s 타임아웃이 체감상 너무
   짧은지/긴지.
3. 86차에서 대기 중이던 ttc_danger 18건(route2 seg11 등) 개별 확인은
   이번 세션에서 미착수 — 다음 세션 이월.

## 86차 계속 (체크포인트 — CSV 재확보 + 5항목 스캔 완료, qcamera 대조 미실시) — c3-ms-curv 10개 route 종합분석

**배경**: 컨테이너 재시작으로 86차 원본 zip이 유실됐다가, 사용자가
Google Drive에 저장해둔 CSV zip(`ryu_c3-ms-curv_logs_20260826.zip`,
qcamera 미포함)을 재다운로드해 재업로드 — 10개 route 전부 재확보.

**작업**: `five_item_scan.py`(55/56차 로직 재현, 이번에 `toolkit/`
정식 편입) 신규 작성 → 10개 route 전체에 5항목(카메라인식감속/
정지앞차감속/정지후재출발/레이더락온저크/곡선구간감속) + 안전지표
(harsh_brake/ttc_danger/cutin) 일괄 스캔 완료. 10개 route를
`data/routes/<route_id>/`에 gzip 캐시로 등록(다음부터 재업로드 불필요).

**핵심 결과** (상세는 FINDINGS.md "86차" 항목 참고):\n- 곡선위반 72건 중 vturn 소스가 3149프레임, route 소스는 12프레임뿐 —\n  85차(route lookahead 600m)/82차(원복버퍼) 패치의 회귀가 아니라 기존\n  vturn apex 이슈 연장으로 잠정 판단(결론력 약함, route 소스만 걸러진\n  개별 확인 필요).\n- ttc_danger 18건 중 route2(0000032f) seg11 t=661.88(vEgo 8.68m/s,\n  dRel 28.6m, vRel -11.8m/s)이 상대적 고속 급접근 후보로 최우선.\n- route7 t=658.0~660.0에서 vision-only dRel 요동(74→68→56→61m) 후\n  vRel -14.9m/s까지 급격 심화, aEgo -2.7까지 감속 — 노이즈성 오탐인지\n  실제 cut-in인지 qcamera 없이 판정 불가.\n- radar_lockon_jerk의 leadVRel≈0 이상패턴이 126건(41차부터 이월된\n  저우선 항목, 표본 규모만 커짐 — 신규 격상은 안 함).\n\n**다음(최우선)**:\n1. qcamera 대조가 필요하면 원본 zip(rlog+qcamera 포함) 재확보 필요 —\n   이번 CSV-only 재다운로드로는 불가능. 사용자에게 재업로드 요청할지\n   결정.\n2. ttc_danger 18건(특히 route2 seg11, route10 9건 밀집) 개별 확인.\n3. 84/85차 이전(85차 이전 HEAD)에 이월돼 있던 실차검증 항목들\n   (84차/85차/82차 자체의 체감 확인 등)도 이 10개 route로 함께 확인\n   가능 여부 검토(meta.json commit이 `284457f`로 일치하므로 85차\n   이후 드라이브로 확정).\n\n## 86차 (완료 — 로그 추출만, 위 \"86차 계속\"에서 5항목 스캔으로 이어짐) — c3-ms-curv 실주행 로그 10개 route CSV 일괄 추출

**배경**: 사용자가 `c3-ms-curv` 브랜치(85차 HEAD `284457f`, route lookahead
600m 상향 반영된 상태)에서 실주행한 로그 10개 route를 한 번에 업로드
(00000329~00000332, 총 142세그, x1~x20seg 혼재). 분석용 CSV 추출 +
Google Drive 저장 요청.

**진행**: `extract_log.py`로 10개 route 전부 CSV 추출 완료(21599~24033
row, 총 ~152k row). 이번 세션은 **추출까지만 완료, 5항목 분석/qcamera
대조는 미착수** — 다음 세션에서 이어감.

**이슈 발견 및 수정**: `0000032e--8b55ac185d_x13seg`의 마지막 세그먼트
(12번) `rlog.zst`가 드라이브 종료 시점에 파일 자체가 잘려 기록됨(zstd
프레임 미완성) → 기존 `decode_rlog.py`가 전체 추출을 중단시킴. 스트리밍
폴백 추가해 해결(잘린 지점까지 유효 데이터 회수, 785 row). 정상 파일
회귀 테스트 통과. 상세는 `toolkit/CHANGELOG.md`/`README.md` 86차 항목
참고 — **이미 push됨(devnotes 전용 수정, ryu 코드 아님)**.

**Google Drive**: 폴더 `ryu_c3-ms-curv_logs_20260826` 생성 후 연결 완료.
단, **원본 CSV(7~8.4MB급) 자체는 Drive MCP 도구로 직접 업로드 불가능함을
확인** — 이 도구는 파일 전체 내용이 Claude 응답 텍스트를 통과해야
하는데, `view` 도구가 16,000자 초과 파일을 자동으로 중간 생략하는 구조라
MB급 파일은 컨텍스트에 온전히 못 들어옴(220KB짜리도 이미 잘림 확인).
→ **대안**: 10개 CSV+meta.json을 zip으로 묶어 `/mnt/user-data/outputs/`
전달(사용자가 직접 Drive 폴더로 드래그하는 방식 안내), 통합 메타 요약
(`ALL_ROUTES_META.json`, 2.4KB)만 Drive에 직접 업로드해둠. **향후
동일 요청 시 이 방식(zip 전달 + 사용자 수동 업로드) 그대로 사용할 것.**

**다음(최우선)**:
1. 사용자가 zip을 Drive 폴더로 옮겨 저장 완료했는지 확인(선택 사항).
2. 10개 route에 대해 5항목 분석 프레임워크(vision-to-radar crossover /
   stopped lead decel / launch-after-stop / radar lock-on jerk / curve
   speed violation) 적용, qcamera 프레임 대조 포함(5개 항목 전부 필수).
3. `sim_boost_window_extension.py`(72차, DISCONTINUITY_JERK_COST_BOOST_S
   1.0s→2.0/2.5/3.0s 커버리지) 관련 후속 검증도 이 로그로 가능한지 검토.
4. 85차/84차/82차/81차 등 여전히 실차검증 대기 중인 항목들, 이번 로그로
   함께 확인 가능 여부 검토(같은 `c3-ms-curv` 드라이브인지 먼저 확인 필요
   — meta.json commit이 `284457f`로 일치하므로 85차 이후 드라이브로 추정).

## 85차 (체크포인트 — 구현+검증+패치 전달 완료, `git am`/실차 적용 대기) — route lookahead 동적 캡 상한 500m -> 600m 상향

**배경**: 84차 PARAMS_REGISTRY.md 기록에서 "120->60km/h 풀커버는 accel=0.70
기준 이론상 ≈595m 필요, 500m는 절충값"이라 명시된 지점 — 사용자가 이번
세션에서 상한을 500m에서 600m로 올려 이 이론적 필요치(≈595m)를 온전히
커버하도록 결정.

**구현** (`c3-ms-curv` 브랜치, base `2a91c3f`(84차 HEAD)): `carrot_man.py`
`compute_route_lookahead_distance()`의 `max_m` 기본값 500.0->600.0,
주석 갱신(300~600m). 최소값(300m)/`assumed_target_kph`(30.0)/계산식은
그대로 — 상한값만 변경.

**검증** (`toolkit/sim_route_dynamic_cap.py`, 84차 원본을 600m 기준으로
갱신): 저속(<=50km/h) 전 accel_limit에서 floor(300m) 유지(회귀 없음) /
accel=0.70 기준 110km/h+에서 ceil(600m) 도달(기존 100km/h+에서 501.5m로
근접하던 것이 확실히 상한까지 확장됨) / accel_limit 낮을수록 더 낮은
속도부터 캡 확장(단조성 유지) / accel_limit=0·None 안전 폴백 — 4개
시나리오 전부 PASS. `git format-patch` → `verify-am-85`(base
`2a91c3f`)에서 `git am`+diff 0+`py_compile` 통과.

**전달**: `0001-85-route-lookahead-500m-600m.patch`를
`/mnt/user-data/outputs/`에 전달(base `2a91c3f`, `c3-ms-curv` 브랜치에
적용, 84차 패치 위에 적층).

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`에서 `git fetch`+
`git reset --hard origin/c3-ms-curv`(2a91c3f 동기화) 후 `git am` 적용 +
`git push origin c3-ms-curv` 완료. 컨테이너에서 `git fetch origin
c3-ms-curv:refs/remotes/origin/c3-ms-curv` 후 로컬 검증 커밋(`e608162`)과
diff 0(완전 동일) 재확인. origin `c3-ms-curv` HEAD: `2a91c3f..284457f`.

**다음(최우선)**:
1. ~~사용자가 `C:\dev\ryu`에서 `git checkout c3-ms-curv` + `git fetch`+
   `git reset --hard origin/c3-ms-curv`(2a91c3f 동기화) → `git am` 적용 →
   `git push origin c3-ms-curv`.~~ → **완료**.
2. **실차 드라이브 검증** — 600m 상한이 실제로 적용되는 고속 구간
   (accel=0.70 기준 110km/h+)에서 84차 대비 체감 차이(더 이른 감속
   개시) 확인, 저속/도심 구간 회귀 없는지(floor 300m 동일) 재확인.
3. 84차 항목(84차 자체의 실차검증)도 여전히 대기 중 — 85차와 함께 같은
   `c3-ms-curv` 드라이브에서 동시 확인 가능.

## 84차 (완료 — 구현+검증+패치 적용/push 완료) — route 커브 lookahead 300m 고정 캡 -> v_ego/accel_limit 기반 동적 캡(300~500m, 85차에서 600m로 추가 상향됨)

**배경**: 83차 NEEDS_VALIDATION(`AutoNaviSpeedDecelRate=0.70`가 고속+큰
감속폭 조합에서 300m 상한에 걸릴 수 있음)에 대한 조치. 300m 고정값 상향
대신 **v_ego/accel_limit 기반 동적 캡(300~500m)**으로 사용자 결정.

**구현** (`c3-ms-curv` 브랜치, base `451a3b9`(82차 HEAD) — **c3-ms-dev 아님**,
동일 함수(`carrot_navi_route`)를 81/82차가 이미 수정해둔 브랜치라 반드시 이
위에 적층): `carrot_man.py`에 `compute_route_lookahead_distance()` 신규
함수 추가 — `(v_ego²-target²)/(2*accel_limit)`을 300~500m로 clip,
`assumed_target_kph=30.0`은 캡 크기 산정 전용 가정값(실제 목표속도와 무관).
`get_path_after_distance(..., 300)` 하드코딩을 이 값으로 교체.

**검증** (`toolkit/sim_route_dynamic_cap.py`, 신규 정식 편입): 저속(<=50km/h)
전 accel_limit에서 floor(300m) 유지(회귀 없음) / 사용자 실측 accel=0.70
기준 100km/h+에서 ceil(500m) 도달 / accel_limit 낮을수록 더 낮은 속도부터
캡 확장(단조성) / accel_limit=0·None 안전 폴백 — 4개 시나리오 전부 PASS.
`git format-patch` → `verify-am-84`(base `451a3b9`)에서 `git am`+diff 0+
`py_compile` 통과.

**전달**: `0001-84-route-lookahead-300m-v_ego-accel_limit-300-500m.patch`를
`/mnt/user-data/outputs/`에 전달(base `451a3b9`, `c3-ms-curv` 브랜치에 적용).

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`에서 `git fetch`+
`git reset --hard origin/c3-ms-curv`(451a3b9 동기화) 후 `git am` 적용 +
`git push origin c3-ms-curv` 완료. 컨테이너에서 `git fetch origin
c3-ms-curv:refs/remotes/origin/c3-ms-curv` 후 로컬 검증 커밋(`c26fa91`)과
diff 0(완전 동일) 재확인. origin `c3-ms-curv` HEAD: `451a3b9..2a91c3f`.

**다음(최우선)**:
1. ~~사용자가 `C:\dev\ryu`에서 `git checkout c3-ms-curv` + `git fetch`+
   `git reset --hard origin/c3-ms-curv`(451a3b9 동기화) → `git am` 적용 →
   `git push origin c3-ms-curv`.~~ → **완료**.
2. **실차 드라이브 검증** — (a) 고속도로 순항 중 route 기반 커브 감속이
   더 이르게 시작되는지, (b) **회귀 검증 필수** — 저속/도심 구간 체감
   차이 없는지(floor 300m로 동일해야 함), 직선 구간 GPS 오차로 인한
   신규 오탐 없는지, (c) 연산 부하 체감(리샘플 포인트 최대 1.67배 증가).
3. `assumed_target_kph=30.0`/`max_m=500.0`는 설계 추정치 — 실차 반응
   보고 튜닝 필요.
4. 82차(vturn/route 원복측 대칭버퍼) 실차검증도 여전히 대기 중 — 84차와
   함께 같은 `c3-ms-curv` 드라이브에서 동시 확인 가능.

## 78차 (완료 — 분석만, 코드 변경 없음) — 77차와 동일 로그(x15seg)에서 discontinuity_lc 최초 실차 검증 완료

**배경**: 77차가 "이번 로그엔 laneChangeState가 전 구간 'off'라 76차
discontinuity_lc를 검증 못함"이라고 남긴 지점에서 이어감. laneChangeState는
계속 off였지만 leftBlinker/rightBlinker(운전자 수동 차선변경 추정)가
seg4/5/10/11에서 활성화된 걸 발견 → qcamera 프레임 대조로 4개 세그
전부 실제 차선변경 동작이 있었음을 영상으로 확정(신호와 조향 불일치
로깅 오류 의심을 기각).

**핵심 결과**: `long_mpc.py`의 `_dRel_raw_history` 5프레임 급락 판정
(`DREL_DISCONTINUITY_DROP_THRESH=15.0m`)+`lane_change_blinker_active`
분기 로직을 CSV로 직접 재현해 스캔 —
- **seg5 t=384.18**(rightBlinker 활성 중, vision-only 5프레임 47.79→
  25.45m, -22.34m): `discontinuity_lc` 소스로 정상 트리거, 4.0s
  hard-hold(RADAR_HANDOFF_JERK_BOOST_S) 부여됨을 코드 로직 재현으로
  최초 확인 — **76차 패치가 실제 차선변경 상황에서 트리거되는 것을
  이번에 처음으로 실측 확인.**
- **seg10 t=722.28**(leftBlinker 활성, -28.02m 급락): 동일하게
  `discontinuity_lc` 정상 트리거.
- 두 사례 모두 boost 윈도우(4초) 내 aEgo는 mild(seg5 min=-0.909,
  seg10은 오히려 가속 중 min=+0.081) — **harsh braking 자체가 없어
  boost의 "급감후 원복 완화" 효과 자체는 이번에도 정량 비교 못함**,
  단 오탐/부작용(불필요한 과잉반응) 없음은 확인(회귀 안전).
- seg4 t=368.63: blinker 꺼진 지 2.2초 후(1.0s hold 만료) → 소스
  `discontinuity`(일반)로 정상 분류, aEgo도 mild(가속중) — 소스 분기
  로직(blinker 활성/hold 여부에 따른 discontinuity vs discontinuity_lc)
  실제로 정확히 갈리는 것 확인.
- seg11: 차선변경은 확인됐으나 dRel 급락 패턴 자체가 없어(매끈한 lead
  전환) discontinuity 트리거 없음 — 정상.

**harsh_brake_events 49건 재확인**: 77차 FINDINGS 기록과 동일 클러스터
(seg1/seg5 t=421~425/seg13) — seg5 t=421~425 클러스터는 `src=vturn`+
`leadStatus=False`(리드 무관 곡선감속, 우회전 교차로 진입으로 추정)로
discontinuity_lc/차선변경과 완전히 무관함 재확인(77차 결론과 일치).

**결론**: 76차 목표(discontinuity_lc를 실제 차선변경 중 재현 검증)
**절반 달성** — 트리거 발동 자체와 소스 분기(discontinuity vs
discontinuity_lc)는 실측 확인됐고 회귀(오탐/부작용)도 없음. 단 "harsh
감속 상황에서 boost가 실제로 급감후 원복을 완화하는지"는 이번 로그에
그런 harsh 이벤트가 없어 여전히 미검증 — 다음은 discontinuity_lc가
harsh braking과 겹치는 차선변경 사례가 필요.

**코드 변경 없음**(분석 전용).

**다음 세션 최우선**:
1. discontinuity_lc 트리거 + harsh braking(aEgo<=-1.5 급)이 실제로
   겹치는 차선변경 로그 확보 시 boost 효과(급감후 원복 완화 여부)
   정량 검증.
2. (낮은 우선순위) steering_oscillation_detector 4건 개별 미조사 —
   필요시 조사.

## 77차 (세션 종료 — 분석만, 코드 변경 없음) — 76차 실차 로그 첫 검증(handoff 재확인, discontinuity_lc는 미검증)

76차 패치 커밋(`f3773b58`) 위에서 기록된 실주행 로그(x15seg,
895.8s/4.26km, 도심)+30초 화면녹화 클립 1개 분석.

**핵심**: 이번 로그엔 차선변경이 한 건도 없어(`laneChangeState` 전
구간 'off') 76차의 진짜 타깃(차선변경+discontinuity_lc)은 이번에도
검증 못함. 대신 고속도로 원거리(109m) vision→레이더 락온 handoff
사례(seg6 t=440~452)가 하나 잡혀서 73차 handoff 메커니즘(72차 방안I
+73차 duration 확장)이 실도로에서 다시 매끈하게 작동함을 재확인 —
락온 순간 vRel 불연속 점프(-12→-8.6m/s)에도 aEgo는 완전히 연속적으로
감속, TTC danger override도 충돌 없이 겹쳐 발동, harsh_brake(운전자
개입) 0건. turn_speed_violation 2건은 전부 운전자 수동주행 구간이라
ADAS 무관 확인(화면녹화 클립으로 앞차 정지 상황 직접 대조).

상세는 FINDINGS.md/LAST_ANALYZED.md "77차" 참고. 코드 변경 없음.

## 다음 세션 최우선
1. **차선변경이 포함된 실주행 로그 확보** → 76차 discontinuity_lc(4.0s
   hard+release-rate 100/s) 타깃 시나리오 직접 검증(아직 한 번도 실제
   차선변경 상황에서 재현 확인 못한 상태).
2. (낮은 우선순위) steering_oscillation_detector 4건 개별 미조사 —
   필요시 조사.

## 다음 세션 시작 시
이 WIP.md에 "77차" 섹션이 있으면 이 지점부터 이어감 — 특히 차선변경
포함 로그가 있는지부터 확인.

## 76차 계속2 (세션 종료 — 실차 적용/push 완료 확인) — discontinuity_lc 패치 반영

사용자가 `C:\dev\ryu`에서 `git am` 적용 + `git push origin c3-ms-dev`
완료(`f8e136e..f3773b5`). 원격 fetch로 로컬 검증 커밋(`f5c0e5c`)과 diff
없음 재확인(내용 완전 동일).

**다음 세션 최우선: 실차 드라이브 검증** — (a) 75차 원 제보(차선변경
시 급감후 원복) 실제 완화 여부, (b) **회귀 검증 필수** — danger
override(TTC<=2.5s) 정상 동작, 일반 cutin(discontinuity 비차선변경)/
handoff(레이더 락온) 두 기존 검증 조합 모두 지연 없는지, (c)
`discontinuity_lc`가 4.0s+release-rate로 오래 유지되는 특성상 차선변경이
짧게 여러 번 반복되는 상황(연속 차선변경)에서 boost가 과도하게 오래
걸리지 않는지 체감 확인.

## 76차 계속 (체크포인트 재개, 컨테이너 재시작 후 이어감) — 패치 생성/git am 검증/전달 완료

이전 세션이 코드 구현+시뮬레이션 검증까지 끝낸 상태에서 컨테이너가
재시작(세션 재시작)돼 로컬 ryu 커밋이 유실된 상태로 재개 — HEAD가
여전히 `f8e136e`(73차)임을 확인, 아래 76차 구현 내용을 long_mpc.py에
그대로 재적용 후 다음 단계 완료:

1. `git commit`(로컬 `f5c0e5c`, base `f8e136e`) → `git format-patch -1`
   → `verify-am-76` 임시 브랜치에서 `git am`(base `f8e136e`) 성공,
   패치 적용 후 diff 0(원본과 완전 동일) 확인, `py_compile` 통과.
2. `devnotes/toolkit/replay_lane_change_discontinuity_gate.py` 재실행 —
   이전 세션과 동일한 결과 재현 확인(route2 t=1472.401 최저점에서
   76차(full) a_change_cost=500 유지, 75차(gate_only)는 20으로 무력화됨
   재확인). route1 회귀 diff 402건 전부 소스=discontinuity_lc.
3. 패치 파일(`0001-76-discontinuity-73-handoff-duration-4.0s-release-ra.patch`)
   `/mnt/user-data/outputs/`에 전달 완료.

**다음(최우선)**: 사용자가 `C:\dev\ryu`에서 `git am` 적용 + `git push
origin c3-ms-dev` → **실차 드라이브 검증**(회귀 검증 필수 -- 일반
cutin/handoff 두 기존 검증 조합이 실차에서도 지연 없이 그대로
동작하는지, 차선변경 반복 시 boost가 과도하게 오래 유지되는 체감
없는지, 75차 원 제보(차선변경 시 급감후 원복) 실제 완화 여부).

## 76차 (최초 구현/검증 기록, 컨테이너 재시작 전) — discontinuity+차선변경 조합에 73차 handoff duration 해법(4.0s+100/s) 통합 적용

**배경**: 75차 계속2에서 방향(b)(차선변경 중 discontinuity 트리거도
handoff와 동일하게 frac 게이트 무관 완화) 구현·검증까지 마쳤으나,
검증 도중 신규 한계 발견 — hard-hold 자체가 여전히
`DISCONTINUITY_JERK_COST_BOOST_S`(1.0s)라서, 이 시나리오의 실제 aEgo
최저점(트리거 후 1.4~1.65초)이 hard-hold 소진 이후에 발생해 여전히
무력화됨(72~73차가 handoff에서 이미 겪은 "duration 자체가 짧음" 구조적
한계와 동일 패턴 재현). 사용자 요청: 73차가 handoff에 적용한 해법
(hard-hold 4.0s + release-rate 100/s)을 discontinuity+차선변경
조합에도 적용해 한 번에 처리.

**구현** (`long_mpc.py`, base `f8e136e`(73차 HEAD, 75차 패치는 아직
미적용 상태였음 — 이번에 75차 방향(b) + 76차 duration 확장을 함께
하나의 커밋으로 구현):
- discontinuity 트리거 지점(dRel 급락 감지)에서, 트리거 시점에
  차선변경 중(`lane_change_blinker_active` 또는 직전 프레임
  `_lane_change_vlead_hold_timer>0`)이면 소스 태그를 신규
  `'discontinuity_lc'`로 부여하고 `_discontinuity_jerk_boost_timer`를
  기존 1.0s(`DISCONTINUITY_JERK_COST_BOOST_S`) 대신 방안I과 동일한
  4.0s(`RADAR_HANDOFF_JERK_BOOST_S`)로 설정. 차선변경과 무관한 일반
  discontinuity는 소스 `'discontinuity'`로 기존 그대로(1.0s hard-hold).
- a_change_cost 적용부의 `is_handoff_source` 판정을
  `trigger_source in ('handoff', 'discontinuity_lc')`로 확장 —
  `'discontinuity_lc'`가 `'handoff'`와 완전히 동일한 코드경로(게이트
  frac 무관 + hard-hold 4.0s + release-rate 100/s 감쇠)를 타도록
  통합. 신규 상수 추가 없이 `RADAR_HANDOFF_JERK_BOOST_S/RATE` 재사용.
  일반 `'discontinuity'` 소스는 기존 분기(frac<=0.0 게이트 + 1.0s
  hard-cutoff) 완전히 그대로 — 회귀 없음.

**검증** (`toolkit/replay_lane_change_discontinuity_gate.py` 갱신 —
`duration_mode='gate_only'`(75차 원안)/`'full'`(76차, 신규) 옵션 추가,
release-rate 감쇠 로직도 실제 코드와 동일하게 재현):
- route2 t=1470.75 이벤트 재검증 — 75차(gate_only)는 최저점(t=1472.401,
  aEgo=-1.556)에서 hard-hold(1.0s, t=1471.75) 이미 소진돼
  a_change_cost=20(무감쇠에 가까움)으로 무력화 재확인. **76차(full)는
  hard-hold가 4.0s(t=1474.75까지)라 최저점 전체 구간에서
  a_change_cost=500(완전부스트) 유지 — 한계 해소 확인.**
- route1/route2 전체 스캔: full 모드 boost 프레임 수가 gate_only보다
  항상 크거나 같음(route1 730→1028, route2 184→479) — 커버리지 실제
  증가.
- **회귀 없음 확인**: route1/route2 전체에서 UNPATCHED 대비 diff
  프레임(402/409건)은 전부 소스=`'discontinuity_lc'`인 경우뿐 — 일반
  discontinuity(차선변경 무관)/handoff 소스는 diff 0건(완전 보존),
  danger_active 프레임 수도 전 구간 동일(회귀 없음).
- `py_compile` 통과.

**다음(최우선)**:
1. `git format-patch`로 커밋 생성 → `verify-am` 임시 브랜치에서 `git am`
   검증(base `f8e136e`) → `/mnt/user-data/outputs/`에 전달.
2. **실차 드라이브 검증** — (a) 차선변경 시 급감후 원복 현상이 이번엔
   실제로 완화되는지(75차 원 제보 재현), (b) **회귀 검증 필수** —
   danger override(TTC<=2.5s) 정상 동작, 일반 cutin(discontinuity
   비차선변경)/handoff(레이더 락온) 두 조합 모두 지연 없는지, (c)
   `discontinuity_lc`가 4.0s+release-rate로 오래 유지되는 특성상,
   차선변경이 짧게 여러 번 반복되는 상황(예: 연속 차선변경)에서 boost가
   과도하게 오래 걸리지 않는지 체감 확인.
3. route1 t=522~533(75차 3번, 핸드오프 구조적 한계, 3.20초 중 11%만
   커버)는 이번 76차 범위 밖(핸드오프 자체의 구조적 한계, discontinuity_lc
   경로와 무관) — 계속 이월.
4. route2 t=1541~1545(75차 원분석 2번째 사각지대 후보)는 이번 검증에서
   aEgo<=-1.5 위험구간 자체가 감지 안 됨(75차 계속2와 동일) — 필요시
   다른 기준/qcamera로 재확인.

**코드 변경**: `long_mpc.py`(ryu, 패치 전달 예정)/
`toolkit/replay_lane_change_discontinuity_gate.py`(devnotes,
`duration_mode` 옵션 추가)/`README.md`/`CHANGELOG.md`.

## 75차 계속2 (체크포인트 — 방향(b) 구현/검증/패치 전달 완료, 실차검증 대기, **신규 한계 발견**)

75차가 확정한 방향(b)(차선변경 중에 한정해 discontinuity 소스도 handoff와
동일하게 frac 게이트 무관 완화)를 `long_mpc.py`에 구현 완료(로컬 커밋
`e31f1e5`, base `f8e136e`) — 60차 계속2가 이미 배선해둔
`lane_change_blinker_active`/`_lane_change_vlead_hold_timer`를 그대로
재사용, 신규 배선 없음. `replay_lane_change_discontinuity_gate.py`(신규,
toolkit 편입)로 route1/route2 전체 회귀 스캔 + route2 t=1470.75 대상
이벤트 재검증 완료 — **회귀 없음 확인**(diff는 전부 차선변경 상황에서만
발생, 일반 cutin/기존 검증된 조합 완전 보존, danger_active 프레임 수
동일). 단 **[신규 발견, 미해결] hard-hold(1.0s) 구간 내에서는 boost
커버리지가 실제로 늘어나지만, 이 이벤트의 실제 aEgo<=-1.5 최저점은
트리거 후 1.4~1.65초(hard-hold 이미 소진)에 발생 — 72~73차 handoff에서
이미 봤던 "duration 자체가 짧음" 구조적 한계가 discontinuity+차선변경
조합에도 동일하게 재현됨.** 상세는 FINDINGS.md "75차 계속2" 참고.

**전달**: `0001-75-discontinuity-danger-b.patch`(base `f8e136e`) 전달,
`git am`+`py_compile` 검증 통과.

**다음(최우선, 다음 세션에서 이어감)**:
1. **실차 드라이브 검증** — (a) 이번 패치(frac 게이트 완화) 자체의
   체감 개선 여부, (b) **회귀 검증 필수** — danger override/일반 cutin
   정상 동작.
2. **[사용자 결정 대기]** duration 부족 한계 해소 여부 — 73차 handoff
   해법(4.0s+release-rate 100/s)을 discontinuity+차선변경 조합에도
   적용할지, 아니면 이번 패치만으로 실차 체감 먼저 확인할지.
3. route2 t=1541~1545(-1.5 문턱 미도달)는 다른 기준/qcamera로 재확인 필요.
4. route1 t=522~533(75차 3번, 구조적 한계)는 계속 이월.

## 75차 (체크포인트 — 코드 변경 없음, 분석만) — "차선변경 시 급감후 원복" 제보, 73차 패치와의 관계 분석

**배경**: 사용자가 스크린샷("차선을 변경합니다" 표시, dRel≈55m대, 1.Accel
그래프 하강)과 함께 "내차 차선변경 시 부드러울 때도 있고 급감후 원복하는
경우도 있다" 제보. 첨부 로그 2개(route1 `ea5bcc0566` x19seg/route2
`a5b1ce4e42` x7seg)는 **72~74차에서 이미 검증에 쓰인 그 두 라우트와
동일**(devnotes `data/routes/`에 캐시돼 있어 재추출 없이 그대로 재사용).

**분석 방법**: leftBlinker/rightBlinker/laneChangeState 활성 구간을
차선변경 이벤트로 탐지(route1 19건/route2 10건) → 각 이벤트 전후
aEgo 최저치 확인 → `replay_boost_duration.py`의 `BoostReplay`(73차
패치 로직 그대로 복제)로 UNPATCHED(1.0s hard)/PATCHED(73차, 4.0s+
release100/split_gate) 두 버전을 차선변경 구간에 재생, boost 적용
여부 대조.

**분류 결과** (harsh 판정: 구간 내 min_aEgo<=-1.0):
1. **73차 패치로 이미 개선된 사례 확인** — route2 t=1374~1381(핸드오프
   트리거, aEgo -3.16): UNPATCHED 시 위험구간(aEgo<=-1.0, 2.70초) 내
   boost 적용시간 0%였으나 **PATCHED는 100%(2.70/2.70초) 커버** —
   같은 날 이미 push된 패치(`f8e136e`)가 정확히 이 유형을 해결함.
   route1 t=363~369도 UNPATCHED 18%→PATCHED 56%로 개선.
2. **[신규 발견, 미해결] discontinuity(방안C/G) 소스는 frac 게이트에
   여전히 막혀 boost가 무효** — route2 t=1469~1472/t=1541~1545: 트리거는
   정상 발동하나(discontinuity 소스), PATCHED/UNPATCHED 둘 다 boost
   적용시간 0%. 원인: 73차의 `split_gate`는 **handoff 소스에만**
   frac 무관 게이트를 적용했고, discontinuity 소스는 기존
   `frac<=0.0` 게이트 그대로 유지(63차부터의 설계 원칙, 방안C/G
   실차검증 완료 조합 보호 목적) — 그런데 차선변경 시 새 차로 리드가
   dRel 급락으로 잡히는 순간 frac(TTC caution)도 함께 빠르게 올라가는
   경우가 많아, 결과적으로 이 시나리오에선 boost가 사실상 항상
   무력화됨. **73차가 커버한 건 "레이더 핸드오프"뿐, "차선변경 중
   비전 dRel 급락(discontinuity)"은 여전히 사각지대.**
3. **잔존 구조적 한계 재확인** — route1 t=522~533(핸드오프): 위험구간
   3.20초 중 PATCHED/UNPATCHED 둘 다 0.35초(11%)만 커버 — 트리거가
   위험구간 후반부에야 발동하는 74차부터 알려진 한계, 이번에도 동일.
4. **실제로는 버그가 아닌 정당한 급제동 확인** — route1 t=1015~1023
   (aEgo 최저 -4.01): qcamera 없이도 dRel/vRel 궤적으로 판단 가능 —
   차선변경 완료 시점(blinker on 1015.3) 직후 레이더가 짧게 놓쳤다가
   vision-only로 새 리드(71m)를 잡았는데, 이후 ~4초에 걸쳐 vRel이
   지속적으로 -13m/s대(물리적으로 일관, 단발 스냅 아님)로 유지되며
   TTC가 2.5s 미만까지 내려감 — **진짜 급접근(danger override 정상
   발동), 시스템이 의도대로 하드브레이크한 정탐**. 사용자 체감상
   "급감"으로 느껴질 수 있으나 코드 버그 아님.
5. route1 t=1061~1066/t=1131~1137: harsh 감속이지만 `leadStatus=False`
   (리드 자체가 없음) — 곡선(vturn) 관련으로 추정, 차선변경/리드
   메커니즘과 무관한 별개 이슈(우연히 blinker와 겹침).
6. route1 t=880~894, 대부분의 나머지 이벤트: 매끈한 점진적 근접
   추종(min_aEgo -2.3 정도까지 서서히) — 정상 동작, "급감후 원복"
   패턴 아님.

**결론**: "차선변경 시 부드러움 vs 급감후 원복"의 재현 가능한 원인
후보는 **2번(discontinuity 소스가 frac 게이트에 막혀 boost 무력화)**
로 좁혀짐 — 73차가 handoff 소스만 고쳤고 discontinuity 소스는 그대로
둔 것이 이번 차선변경 시나리오에서 사각지대로 남음. 나머지 harsh
사례들은 진짜 위험(4번) 또는 곡선 별개 이슈(5번)로 이번 제보와 직접
관련 없음.

**다음(사용자 확인 대기, 패치 미착수)**:
1. discontinuity 소스에도 split_gate(danger_active 단독 게이트)를
   적용할지 — 단 73차 계속 결정 당시 "discontinuity(방안C/G)는 이미
   실차검증 끝난 조합이라 회귀 리스크"로 명시적으로 보호 대상 밖에
   뒀던 것이므로, 전면 적용은 회귀 위험 재검토 필요. 대안: 차선변경
   중(blinker 활성+hold)에 한정해서만 discontinuity 소스도 frac 무관
   게이트로 완화(60차 계속2의 LANE_CHANGE_VLEAD_CORRECTION_HOLD_S와
   유사한 "시나리오 한정" 원칙 재사용) — 회귀 범위를 차선변경 상황으로
   좁히는 쪽이 사용자의 기존 선호(전역 킬스위치 거부, 시나리오 한정
   선호, 60차 계속2)와 일치.
2. 위 방향 확정되면 `replay_boost_duration.py`류로 route2 t=1469/1541
   재검증(boost 커버율이 실제로 늘어나는지) → 통과 시 `long_mpc.py`
   패치 설계.
3. route1 t=522~533 구조적 한계(3번)는 이번 세션 범위 밖, 기존 74차
   이월 항목("실차 정성적 체감 확인" 등)과 함께 계속 열어둠.

**코드 변경 없음(ryu). devnotes만 변경.**


**[갱신, 체크포인트] 사용자 영상 확인으로 2번 원인 확정 + 방향 (b) 채택**:
사용자가 스크린샷 시점 화면녹화를 직접 재확인 — 차선변경 진입 중
카메라가 먼저 "옆차로 앞앞차"(더 먼 차)를 리드로 인식했다가, 차로에
완전히 들어서면서 실제 "바로 앞차"(더 가까운 진짜 리드)로 **타겟이
전환**되는 순간 dRel이 급락한 것으로 확인 — 실제 접근이 아니라
방안C/G가 원래 겨냥한 "트랙 전환" 패턴이 차선변경 상황에서 발생한
사례임을 사용자가 직접 확인. discontinuity 트리거 자체는 정상(진짜
타겟 전환 감지)이나, 차선변경 중이라 TTC caution(frac)이 같이 뜨면서
완화 게이트가 막힘 — 75차 원 분석과 정확히 일치.

**방향 확정: (b) 차선변경 중(blinker 활성+hold)에만 한정해서
discontinuity 소스도 danger 무관 완화 게이트 적용.** 근거: 방안C/G의
기존 검증된 조합(일반 cutin 등)은 건드리지 않음, danger override
(TTC<=2.5s)는 항상 그대로 최우선 유지, 60차 계속2(LANE_CHANGE_
VLEAD_CORRECTION_HOLD_S)와 동일한 "시나리오 한정" 원칙 재사용.

**다음(최우선, 다음 세션에서 이어감)**:
1. 위 방향대로 게이트 조건 설계 — `_discontinuity_trigger_source`에
   'discontinuity'가 찍힌 경우라도, blinker 활성(+LANE_CHANGE 류
   hold) 중이면 handoff와 동일하게 danger_active만으로 게이트(frac
   무관)하도록 `long_mpc.py`의 boost 게이트 조건부(L1167~1172 부근,
   `is_handoff_source` 판정부)에 차선변경 조건 추가.
   `longitudinal_planner.py`가 이미 60차 계속2에서 blinker를
   `lane_change_blinker_active`로 mpc에 넘기고 있으므로 그 신호
   재사용 가능(중복 배선 불필요, 확인 후 재사용).
2. `replay_boost_duration.py`류로 route2 t=1469~1472/t=1541~1545
   재검증(boost 커버율이 실제로 늘어나는지, 일반 cutin 회귀 없는지)
   → 통과 시 `long_mpc.py` 패치 설계 → git am 검증 → 전달.
3. route1 t=522~533 구조적 한계(75차 3번)는 계속 별도 이월.

## 74차 — 73차 방안I 패치(f8e136e) 실차 전체 라우트 재생검증 완료, **정량 회귀 없음 확인**

**배경**: 73차에서 route1 seg10/route2 seg1 두 이벤트 구간만 검증했던
방안I 패치를, 사용자가 업로드한 route1(ea5bcc0566, x19seg, 11.06km)/
route2(a5b1ce4e42, x7seg, 4.30km) **전체 구간**에 대해 재생 검증(요청:
"이번 패치가 다른 로그상황에 어떤 영향을 미치는지도 검증").

**핵심 결과**(상세는 FINDINGS.md "74차" 참고):
- 트리거 검출 조건(discontinuity/handoff) patched=baseline 완전 동일
  (설계대로 — 패치는 hard-hold/release만 변경).
- danger_active(TTC<=2.5s)와 boost 동시발생 **0건**(route1/route2 모두,
  baseline/patched 모두) — danger override 회귀 없음 확정.
- boost 적용 프레임 비중 여전히 작음(route1 0.68%->3.80%, route2
  0.25%->1.73%).
- 위험구간(aEgo<=-1.5) 대비 boost 커버율 개선 확인(route1 2.7%->18.6%,
  route2 0.0%->68.4%) — 73차 설계 의도대로 작동.
- 기존 튜닝 대상 외 새 handoff 트리거 3건(route1) 개별 확인 — 전부
  고속 순항 중 원거리 레이더 재획득 vRel 노이즈로, 실제 급감속 없이
  무해하게 지나감(과도촉발 우려 기각).
- harsh_brake 이벤트(35+20건) 전수 확인 — boost와 무관, 대부분
  cruiseEnabled=False(운전자 개입/해제 인접)로 기존 학습 패턴과 일치.

**다음(최우선)**:
1. 정성적 승차감 체감(정량 회귀검증은 이번 세션에서 완료) — 실차
   드라이브 시 급감속 완화가 "체감되는지" 사용자 확인.
2. 방안C/G(discontinuity)+방안I(handoff) 이중 트리거 상황 승차감(로직상
   소스 전환은 확인됐으나 체감 미확인 — 73차에서 이월).
3. full_route_replay.py(전체 라우트 재생 스크립트) toolkit 정식 편입
   검토 — 향후 패치마다 "전체 라우트 회귀검증" 표준 절차화 가치 있음.

**코드 변경 없음.** route1.csv, route2.csv, full_route_replay.py
신규(스크래치, toolkit 미편입).

## 73차 계속4 — long_mpc.py 패치 작성/git am 검증/전달 완료, **적용/push 완료 확인, 실차 검증 대기**

**배경**: 73차 계속3의 결정(4.0s hard + 100/s release-rate, split_gate)대로
`long_mpc.py`에 실제 패치 구현.

**구현**(base `4fa4a44`, 로컬 커밋 `8402d8b`/verify-am 재현 `40bdb2d`):
- 신규 상수 `RADAR_HANDOFF_JERK_BOOST_S=4.0`/`RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE=100.0`
  (방안C/G의 기존 `DISCONTINUITY_JERK_COST_BOOST_S=1.0`과는 별개로 분리).
- `_discontinuity_trigger_source`('discontinuity'|'handoff') 신규 상태로
  트리거 소스 구분 — dRel discontinuity 트리거 지점(L901 부근)과 레이더
  핸드오프 vRel 불연속 트리거 지점(L933 부근) 각각에서 소스 태그 + 대응하는
  hard-hold 유지시간(1.0s vs 4.0s) 설정, 진행 중이던 반대쪽 release 값은 정리.
- `a_change_cost` 적용부(L1120대) 재작성: `is_handoff_source`로 분기 —
  **방안C/G는 완전히 기존 그대로**(hard-cutoff, `frac<=0.0` 게이트, 회귀 없음).
  **방안I은 danger_active만 게이트**(frac 무관, 73차 계속 결정), hard-hold
  종료 후 `_handoff_release_value`가 `RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE`
  (100/s)로 base까지 선형 감쇠, danger_active 뜨면 감쇠 중이라도 즉시 base로
  강제복귀.

**검증**:
- `py_compile` 통과, `git format-patch` → `verify-am-73` 임시 브랜치(base
  `4fa4a44`)에서 `git am` 컨텍스트 일치 확인.
- **`replay_boost_duration.py`로 패치와 동일 로직 재실행해 재확인** —
  route1(seg10, t=683~698) 68.6%, route2(seg1, t=1375~1388) 98.2% 커버
  (기존 baseline 1.0s hard는 둘 다 0%) — 73차 계속3 결정치(68.0/98.2%)와
  일치, 실측 검증 재확인 완료.

**전달**: `0001-73-handoff-boost-4.0s-release-rate-100.patch`를
`/mnt/user-data/outputs/`에 생성, `git am` 안내(base `4fa4a44`) 함께 전달.

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`에서 최초 `git am`
시도 시 로컬이 origin보다 2커밋 뒤처져(`e6a00ae`, 67차/72차 미반영)
컨텍스트 불일치로 실패 → `git fetch`+`git reset --hard origin/c3-ms-dev`
로 동기화 후 재적용 성공(`f8e136e`) + `git push origin c3-ms-dev` 완료
확인(`4fa4a44..f8e136e`).

**다음(최우선)**:
1. **실차 드라이브 검증** — (a) route1/route2류 재현 상황(정지앞차 레이더
   락온 시) 급감속 완화 체감 여부, (b) **회귀 검증 필수** — danger
   override(TTC<=2.5s) 정상 동작·지연 없는지, (c) 방안C/G(비전단독 dRel
   급락)는 이번 패치로 전혀 변경 없음(회귀 리스크 이론상 0, 그래도 재확인
   권장), (d) 방안C/G와 방안I 이중 트리거 시(예: route1처럼 discontinuity
   +handoff가 근접) 소스 전환이 부드럽게 처리되는지(새 트리거가 이전 진행
   중이던 release를 덮어씀 — 설계대로인지 체감 확인).
2. `RADAR_HANDOFF_JERK_BOOST_S=4.0`/`RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE
   =100.0`는 실측 커버율 기반 채택값이나 여전히 NEEDS_VALIDATION(실제
   acados MPC 반영 후 승차감 기준 재조정 여지 있음).
3. route1의 68.6%(구조적 한계, discontinuity+handoff 이중트리거로 8초
   가까이 위험구간 지속)는 이번 패치로도 완전 해소 안 됨 — 실차 체감으로
   추가 조치 필요성 재논의.

## [체크포인트, 세션 종료 아님] 73차 계속3 — boost_s 4~6.5s 스윗스팟 탐색 + release-rate 스크립트 버그 2건 수정, **4.0s+100/s 조합 채택 결정**

**배경**: 73차 계속2에서 남은 "boost_s를 더 올릴지" 질문에 답하기 위해
`replay_boost_duration.py`(split_gate 모드)로 boost_s 3.0~6.5s를 스캔.

**boost_s만 늘렸을 때(hard cutoff, split_gate)**:
- route1: 3.0s 19.2% → 4.0s 36.0% → 5.0s 52.0% → 6.0s 68.0% → 6.5s 76.0%
  (100% 도달 불가 — discontinuity(t=687.850)+handoff(t≈690.0) 이중
  트리거로 위험구간이 8초 가까이 이어지는 구조적 한계, 6.5s로도 한계).
- route2: 3.0s 44.2% → 4.0s 62.2% → 5.0s 81.1% → 6.0s 98.2% → 6.5s 100.9%.
- 게이트차단 전 구간 0.00s(회귀 없음). 단, 6~6.5s까지 밀면 "찰나성 완화"
  설계 취지에서 멀어지고 승차감상 "물러지는" 리스크 우려 제기 → duration
  단독 증가 대신 release-rate 완만화 병행 검토로 방향 전환.

**[중요] `replay_boost_duration.py` 버그 2건 발견·수정** (release-rate
옵션이 그동안 사실상 완전히 무효였음):
1. 감쇠 중 "즉시 base로 강제복귀" 판정이 split_gate의 방안I(handoff)
   frac 면제 예외를 반영 안 해서, 타이머 만료 직후 frac>0(핸드오프 직후
   거의 항상 즉시 발생)에 걸려 감쇠 시작도 못 하고 즉시 base로 꺼짐 —
   `force_revert` 변수로 분리해 split_gate+handoff 트리거는 danger_active만
   확인하도록 수정.
2. `self._release_value = max(base_cost, self._release_value -
   release_rate * dt)`에서 `release_rate`가 지역변수 미정의라 `self.
   release_rate` 대신 참조 시도 → `NameError`(1차 실행에선 예외가 case
   안 걸려 조용히 통과된 게 아니라 애초에 이 분기 자체가 버그1 때문에
   전혀 실행 안 돼서 안 걸렸던 것 — 버그1 수정 후 실행하면서 발견).
   `self.release_rate`로 수정.

**버그 수정 후 재검증 (route1/route2, split_gate 유지)**:
- 5.0s+300/s: 62.4%/92.8%, +200/s: 67.2%/98.2%, +150/s: 72.8%/100.9%.
- 4.0s+150/s: 56.8%/85.6%, **4.0s+100/s: 68.0%/98.2%**.

**결정**: **4.0s(hard) + 100/s(release-rate) 조합 채택.** 근거: 5.0s
hard 계열과 커버율이 거의 동급(68.0/98.2% vs 72.8/100.9%)이면서도,
\"완전부스트(500) 유지\" 구간을 4.0s로 더 짧게 가져가고 나머지는 완만한
꼬리로 커버하는 구조라 원래 방안G의 \"찰나성 완화\" 취지에 더 가까움 —
5~6초 내내 저크비용을 낮게 유지하는 것보다 승차감상 자연스러울 가능성.
route1이 68%로 미달(구조적 한계, 위 참고)인 점은 실차 검증으로 체감
확인 후 필요시 재논의하기로 함(무리하게 duration/release_rate를 더
극단화하지 않기로).

**다음(최우선)**:
1. 위 결정(방안I 트리거 전용 split_gate + boost_s 4.0s + release-rate
   100/s 완만화)대로 `long_mpc.py` 패치 설계 — 트리거 소스 구분용 상태
   신규 추가(`_discontinuity_jerk_boost_timer` 단일 타이머를 소스별로
   분리하거나 별도 bool 플래그 추가, `_trigger_source` 방식은
   `replay_boost_duration.py`에서 이미 검증됨) + release-rate 감쇠 로직
   신규 구현.
2. `replay_boost_duration.py`로 최종 파라미터(4.0s/100/s)로 다시 한 번
   route1/route2 재검증(패치 코드와 동일 로직인지 diff 확인) → `git am`
   검증 → 전달.
3. route1의 dRel discontinuity 트리거(t=687.850, 방안C/G 경로)는 이번에도
   split_gate 대상에서 제외(기존 게이트 유지) — 73차 계속 결정 재확인,
   변경 없음.

**코드 변경 없음(ryu 미변경). `toolkit/replay_boost_duration.py` 버그
수정(release-rate 옵션이 처음으로 정상 동작) — devnotes만 변경.**

## [체크포인트, 세션 종료 아님] 73차 계속2 — split_gate 검증 완료: 게이트차단 해소, duration과 결합해 커버율 실제 증가

**결과**: `replay_boost_duration.py`에 `split_gate` 옵션(방안I 트리거만
danger_active 단독 게이트) 구현·검증 완료 — route1 3.0s+split_gate
19.2%, route2 3.0s+split_gate 44.2% 커버(게이트차단 0.00s로 완전 해소).
danger_active 프레임 수 회귀 없음(baseline과 동일 확인). 상세는
FINDINGS.md 73차 계속 참고.

**다음(최우선)**:
1. boost_s를 3.0s보다 더 올릴지(4.0~5.0s 후보) — coverage가 아직
   100%에 못 미침(risk_dur 5.55~6.25초).
2. route1 dRel discontinuity 트리거(방안C/G 경로, t=687.850)도 이
   시나리오에선 split 대상에 포함할지 판단.
3. 방향 확정되면 `long_mpc.py` 패치 설계 — 트리거 소스 구분용 상태
   신규 추가(`_discontinuity_jerk_boost_timer` 단일 타이머를 소스별로
   분리하거나 별도 bool 플래그 추가) → `replay_boost_duration.py`로
   최종 재검증 → `git am` 검증 → 전달.

**코드 변경 없음(ryu 미변경). `toolkit/replay_boost_duration.py`
갱신(split_gate 옵션 추가).**

## [체크포인트, 세션 종료 아님] 73차 계속 — 방향 결정: **방안I 트리거 전용 게이트 분리(제한적 1번)**

**결정**: 3개 후보(FINDINGS.md 73차 참고) 중 **1번(frac 게이트 완화)을
방안I 트리거에만 한정** 적용하기로 확정. 근거:
- 2번(boost-frac 병존 재설계)은 a_change_cost 이분법 구조 자체를
  바꿔야 해 범위/리스크 큼.
- 1번을 **전면** 완화하면 방안C/G(dRel discontinuity, cutin/vision
  노이즈 대응)까지 함께 풀리는데, 이 조합(방안C/G + frac 게이트)은
  이미 실차검증까지 끝난 조합이라 회귀 리스크.
- **방안I(레이더 핸드오프)이 겨냥한 시나리오는 정의상 frac_ttc를
  즉시 끌어올림**(정지/서행 앞차의 진짜 상태가 락온 순간 확정되는
  것이지, 새로운 미확인 위험이 아님) — danger override(TTC<=2.5s)만
  살아있으면 안전망은 충분하다고 판단.
- 따라서 트리거 소스(dRel discontinuity vs 레이더 핸드오프)별로
  게이트를 분리: **방안I 트리거로 arm된 boost만 danger_active 단독
  게이트**(frac 무관), **방안C/G(dRel discontinuity) 트리거는 기존
  `frac<=0.0` 게이트 그대로 유지**.

**다음(이어서 진행)**: `replay_boost_duration.py`에 "방안I 전용 완화
게이트" 후보 추가 → route1/route2 재검증(커버리지가 실제로 늘어나는지,
danger override 회귀 없는지) → 통과 시 `long_mpc.py` 패치 설계
(트리거 소스를 구분하는 플래그 신규 필요 — 현재 `_discontinuity_jerk_
boost_timer`는 dRel discontinuity/레이더 핸드오프 두 트리거가 같은
타이머를 공유하므로, 소스 구분용 별도 상태 추가 검토).

## [체크포인트, 세션 종료 아님] 73차 — boost duration 연장 가설 재검증, **[방향전환] 원인은 duration이 아니라 frac<=0.0 게이트**

**배경**: 72차 계속4 "다음(최우선)" 1/2번대로 `data_routes.load_route()`
로 route1(`ea5bcc0566`)/route2(`a5b1ce4e42`) 불러와 boost 지속시간
후보(2.0/2.5/3.0s hard) + release-rate 완만화안(1.0s+300/s 또는
200/s 감쇠) 정량 비교 replay 스크립트(`toolkit/replay_boost_
duration.py`, 신규) 작성·실행.

**핵심 결과**: boost_s를 1.0→3.0s로 늘려도 위험구간(aEgo<=-1.5, 짧은
회복 blip 0.5s 이내 무시) 내 실제 boost 적용시간은 route1/route2 둘 다
**여전히 0.00초(0.0%)** — timer는 boost_s에 비례해 활성 시간이
늘어나지만(route2 기준 1.0s→0.45s/3.0s→2.45s), 그 활성 시간 전부가
`frac<=0.0` 게이트에 걸려 base_a_change_cost로 강등됨. 원인: radar
락온 직후 closing이 지속되며 TTC가 곧바로 `LEAD_ACQ_TTC_CAUTION=6.0s`
밑으로 진입해 frac_ttc>0이 거의 즉시 성립 — 이 시나리오(정지/서행
앞차 락온) 자체가 정의상 frac_ttc를 끌어올리는 상황이라 boost 게이트
`(timer>0 and not danger_active and frac<=0.0)`가 자기모순적으로
거의 항상 막힘. **72차의 "boost 1.0s가 짧아서 부족" 결론은 정정 —
duration 자체는 병목이 아니었음.** 상세는 FINDINGS.md 73차 참고.

route2에서 계산된 위험구간(t=1379.400~1384.950, 5.55초)이 72차 계속3의
수기 계산과 정확히 일치해 스크립트 재현 신뢰도도 확인됨.

**다음(최우선)**: 3개 방향 후보 중 사용자 결정 필요(순서 확정 대기):
1. boost 게이트에서 `frac<=0.0`을 완화(danger_active만으로 게이트,
   또는 frac 문턱을 낮은 양수로) — danger override(TTC<=2.5s)는
   별도로 항상 최우선 유지되므로 안전망 자체는 유지됨, 재검토 필요.
2. boost와 frac_ttc floor를 상호배타가 아니라 병존 가능하게 재설계.
3. "찰나성 노이즈 완화"(방안G/C)와 "몇 초 지속 진짜 급감속의 저크
   완만화"(방안I)를 같은 boost 메커니즘으로 묶은 구조 자체를 분리
   (frac gate 밖에서 동작하는 별도 경로).

방향 결정되면 → 해당 방향으로 게이트 조건 수정 →
`replay_boost_duration.py`로 재검증(boosted 시간이 실제로 늘어나는지
확인) → 통과 시 `long_mpc.py` 패치.

**코드 변경 없음(ryu 미변경). `toolkit/replay_boost_duration.py`
신규(정식 편입, 스크래치 아님).**

## [체크포인트, 세션 종료 아님] 72차 계속4 — `data/routes/` 구조 신설 완료(route1/route2 등록+push)

72차 계속3에서 쓴 두 라우트(route1 `ea5bcc0566` x19seg 22800행,
route2 `a5b1ce4e42` x7seg 7859행 — 둘 다 커밋 `4fa4a44b9311` 상태에서
추출, meta.json 확인 결과 이전 세션과 완전 동일 재현)를 gzip 압축해
`devnotes/data/routes/<route_id>/route.csv.gz`+`meta.json`으로 신규
저장. 로더 `toolkit/data_routes.py`(`load_route`/`list_routes`) 신규
작성 및 검증 완료(두 라우트 모두 load 성공, meta 일치 확인).
`data/routes/README.md`(등록 라우트 표 + 사용법 + 추가 절차),
`toolkit/README.md`/`CHANGELOG.md` 동기화 완료. 이 체크포인트와 함께
push.

**다음(최우선, 여전히 미착수)**: 아래 72차 계속3 항목 그대로 —
1. boost 지속시간 연장안(2.5~3.0s 후보) 또는 release-rate 완만화안 설계
2. `data_routes.load_route()`로 route1/route2 불러와 PATCHED vs
   UNPATCHED 정량 비교 replay 스크립트 작성(신규 재사용 가능 스크립트는
   toolkit/에 정식 편입)
3. 검증 통과 시 `long_mpc.py` 패치 → git am 검증 → 전달

---

## [체크포인트, 세션 종료 아님] 72차 계속3 — route2(x7seg) 교차검증 완료: boost 윈도우(1.0s) 구조적 부족 가설, **2개 라우트에서 재현 확인**

route2(`a5b1ce4e42`) seg1 t=1378.85 레이더 락온 이벤트(정지앞차,
vRel jump -5.11)에서 route1 seg10과 동일 패턴 재확인: boost 소진
(t=1379.85) 시점엔 아직 최악점 도달 전(aEgo=-2.229)이고, 실제 최대
감속(-3.157m/s²)은 boost 소진 1.36초 후(t=1381.207)에 발생. 전체 이벤트
aEgo<=-1.5 기준 5.55초 지속. 상세는 FINDINGS.md "72차 계속3" 참고.

**다음(최우선, 여전히 미착수 — 이번엔 착수 근거가 표본 2건으로 강화됨)**:
1. boost 지속시간 연장안(2.5~3.0s 후보, danger override는 여전히 우선)
   또는 release-rate 완만화안 설계
2. route1 seg10 + route2 seg1(위 두 사례) 기반 정식 replay 스크립트로
   PATCHED vs UNPATCHED 정량 비교 검증 (아직 스크립트화 안 됨)
3. 검증 통과 시 `long_mpc.py` 패치 작성 → git am 검증 → 전달

---

## [체크포인트, 세션 종료 아님] 72차 계속2 — 방안I 무력화 원인 재현/특정: **boost 윈도우(1.0s)가 실제 지속 급감속 이벤트에 비해 근본적으로 짧음**

**배경**: 직전 세션(대화록상 "방안I 트리거는 정상 작동하나 실제 저크완화
효과가 무효화됨"까지 격리검증 완료 후 FINDINGS 기록 직전에 중단)이
컨테이너 리셋으로 유실 — 이번 세션도 work/ 스크립트·CSV 전부 새로
시작, route2(x7seg) zip은 이번 세션엔 재업로드되지 않아 route1만 재확보.
사용자가 route1 zip(x19seg, `0000031f--ea5bcc0566`)만 재업로드해줘서,
72차 원 발견 구간(seg10, t≈683.8~697, "정지앞차 레이더락온시 급감")을
`extract_log.py`로 재추출 후 코드(`long_mpc.py` L823~1140, 현재
HEAD `4fa4a44` = 방안I 적용 상태) 그대로 프레임 단위 대조.

**실측 재확인(라이브 코드 대조, replay 스크립트 재작성 없이 직접 CSV
추적으로 검증 — 별도 재생스크립트는 다음 단계로 미룸)**:
- 레이더 락온 엣지 프레임 t=690.0027: vRel -3.957→-10.8m/s(-6.84m/s
  점프, `RADAR_HANDOFF_VREL_JUMP_THRESH=3.0` 정상 초과 → 방안I 트리거
  확인) / dRel은 99.8→91.8m으로 이 프레임 자체는 아직 멀어서
  `frac_ttc`(ttc_now≈91.8/10.8≈8.5s > CAUTION 6.0)=0, `frac_rate`도
  radar=True 전환이라 즉시 0, `_lead_acq_timer`도 이미 RAMP_TIME(5.0s)
  초과(t≈684.0부터 추적, 6s+ 경과)라 `frac_time`=0 → **frac=0,
  `_lead0_danger_active`=False(ttc_now 동일하게 8.5s대) → 부스트
  게이트(L1129~1131) 조건 정상 충족, 이 프레임에 실제로 boost 적용됨
  확인.**
- **그러나 실제 급감속은 이 순간 시작해 t≈691.0~695.0까지 4초 이상
  지속**(aEgo가 t=690대 -0.1 수준에서 t=693대 -2.0~-2.2까지 서서히
  악화, 정지앞차가 실제로 몇 초에 걸쳐 강하게 감속 중이었음
  — leadALeadK도 t=690.2부터 -0.5, -0.8, -1.0, -1.35(t=691.4피크)까지
  꾸준히 악화). **`DISCONTINUITY_JERK_COST_BOOST_S=1.0s` 부스트 윈도우는
  t≈691.0경 소진되는데, 그 시점이 바로 leadALeadK(=j_lead 근사)가
  가장 나빠지는 구간과 겹침 — 부스트가 꺼지자마자
  `base_a_change_cost = interp(abs(j_lead),[0.3,2.0],[A_CHANGE_COST=200,20])`
  식이 j_lead 급증으로 다시 낮은 값(≈20)까지 떨어져(=무감쇠에 가까운
  민감한 응답으로 복귀) 부스트 이전과 사실상 동일한 저크로 급감속이
  이어짐.**
- 부가 확인: 이 route1 seg10 케이스는 방안C(원본 discontinuity,
  vision-only dRel 원본값 5프레임창 급락)도 락온 이전 구간에서 별도로
  최소 1회 트리거됨(vision-only 구간 내 5샘플창 최대낙폭 20.25m,
  `DREL_DISCONTINUITY_DROP_THRESH=15.0` 초과) — 즉 이 케이스는 방안C
  경로와 방안I 경로 둘 다에서 부스트가 각각 arm되지만, **두 경로 모두
  같은 `_discontinuity_jerk_boost_timer`/같은 1.0s 윈도우를 공유**하고
  실제 위험은 그보다 훨씬 길게 지속되므로 결과는 동일(무력화).

**결론(원인 재확정, "방안C와의 상호작용 버그"가 아니라 "부스트 자체의
설계 전제 불일치"로 재해석)**: 직전 세션 요약에 남은 "방안I 트리거는
되는데 실제 효과가 무효화"라는 관찰은 이번 재현으로도 동일하게
확인되나, 원인은 방안C와의 직접적 상호작용(타이머 덮어쓰기 등)이라기
보다 — **방안G/C가 원래 겨냥한 시나리오(찰나의 vision dRel 노이즈/
cutin 스냅 → 곧 정상화)와 달리, 방안I이 새로 겨냥한 "레이더 락온이
드러내는 진짜 급감속"은 수 초 지속되는 이벤트라서, 1.0초짜리 부스트
윈도우 자체가 이 시나리오엔 구조적으로 부족**하다는 쪽이 더 정확한
설명으로 재정리됨. (단, 직전 세션이 "방안C 미개입 가정 시 방안I만
격리해도 무효화가 재현되는지"를 확인했다는 기록과 방향은 일치 —
방안C를 완전히 빼도 방안I 단독으로도 1.0s 윈도우 자체의 한계이므로
동일하게 무효화됨.)

**다음(최우선, 아직 미착수)**:
1. 위 가설을 `work/route72/route1.csv` 기반 정식 replay 스크립트로
   PATCHED(boost 1.0s 유지 vs 연장안) 비교 정량 검증 — 이번엔 시간
   제약으로 raw CSV 직접 대조까지만 하고 스크립트화는 다음 단계.
2. **방안 후보**: (a) boost 지속시간을 이 시나리오 한정 연장(예:
   2.5~3.0s, danger override는 여전히 무관하게 우선), 또는 (b) boost
   윈도우 소진 후에도 base_a_change_cost가 즉시 원상복귀하지 않도록
   a_change_cost 자체에 release-rate 제한(방안G 부스트 종료를 rise-rate
   limiter처럼 완만하게) 추가, 또는 (c) 애초에 "찰나성 노이즈 완화"와
   "진짜 급감속 초반 저크 완화"를 같은 타이머로 묶지 않고 후자 전용
   메커니즘 분리. 다음 세션에서 사용자와 방향 확정 필요.
3. route2(x7seg) 원본도 재업로드받아 71차에서 언급된 유사 사례(t≈1378.8)
   에도 동일 패턴(부스트 무력화)이 재현되는지 교차검증 필요 — 이번
   세션엔 route1만 확보됨.
4. 72차/WIP.md 기존 "다음(사용자 확인 대기)" 2/3번(mp4 나머지 클립
   매칭, 71차 이월 항목)은 여전히 미착수.

**코드 변경 없음(ryu 미변경, 재현/원인재확정만). `work/route72/route1.csv`
신규(스크래치, toolkit 미편입 — 방안 확정 전까지 유지 원칙 동일).**

## 72차 계속(방안 I) — 패치 적용/push 완료(`4fa4a44`), 실차 검증 대기

**배경**: 아래 "72차" 원 체크포인트가 컨테이너 리셋으로 중단됨 —
사용자가 작업 중이던 `long_mpc.py`(방안 I 구현이 이미 완료된 상태)를
새 세션에 업로드해줘서 그대로 이어받아 마무리.

**구현/검증/전달**: 상세는 FINDINGS.md "[PATCH_WRITTEN] 72차(방안 I)"
항목 참고. 요약: 레이더 False->True 전환 엣지 프레임에서 vRel 불연속
(`RADAR_HANDOFF_VREL_JUMP_THRESH=3.0m/s`)을 감지하면 기존 방안G
저크부스트를 재사용해 arm — danger override/proactive floor는 무관하게
항상 우선 유지. `git am` 검증(base `0c137f2`) + `py_compile` 통과.
`0001-72-I-vRel-G.patch` `/mnt/user-data/outputs/`에 전달 완료.

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`에서 `git fetch`+
`git reset --hard origin/c3-ms-dev` 동기화 후 `git am` 적용(diff --stat
42줄 추가로 예상과 일치 확인) + `git push origin c3-ms-dev` 완료
확인(`0c137f2..4fa4a44`).

**다음(최우선)**:
1. **실차 드라이브 검증** — (a) 이번 재현 상황(비전 낙관 6초+→레이더
   급락, route1류) 재현 시 급감속 완화 여부, (b) **회귀 검증 필수** —
   danger override(TTC<=2.5s) 정상 동작, 지연 없는지, (c) 방안G
   (비전단독 dRel 급락, 66/67차)와 이중 트리거 시 부작용 없는지.
2. (권장, 아직 미실시) route1 원본 rlog로 t=690.05 시퀀스에 방안 I
   로직을 추가한 재생 사전검증(방안C/G 때 했던 방식) — 이번엔 세션
   복구를 우선해 건너뜀, 실차 검증과 병행/대체 가능.
3. `RADAR_HANDOFF_VREL_JUMP_THRESH=3.0m/s`는 설계 추정치 — 실차 반응
   보고 튜닝 필요.
4. 72차 원 체크포인트의 "다음(사용자 확인 대기)" 2/3번(mp4 나머지
   클립 정밀 매칭, 71차 이월 항목 방안F/H·세그7 오실레이션)은 여전히
   미착수 — 방안 I 실차검증과 별개로 순서 재확인 필요.

## 72차 (완료 — 원인분석+방안I 구현으로 이어짐, 원 기록 보존) — 레이더 락온 급감속 실차 재현 + 원인 특정

**배경**: 사용자가 새 실차 로그 2개(route1 x19seg `0000031f--ea5bcc0566`,
route2 x7seg `00000320--a5b1ce4e42`, 둘 다 HEAD `0c137f28b456` 기준) +
화면녹화 mp4 3개(파일명에 증상 명시: "정지앞차_레이더락온시_급감_
서서히_감속_코딩_필요", "정지앞차_카메라락온_부드럽게_정지",
"정지앞차_카메라인식")를 업로드. 요청: 레이더 락온 시 급감속하는 경우가
있는데, 위험한 상황이 아니라면 서서히 목표속도까지 감속하도록 수정.

**mp4-로그 시각 매칭 방법**: mp4 파일명의 타임스탬프는 녹화 **종료**
시각(재생시간 역산 필요). route 세그먼트 폴더명 wall-clock과 CSV `t`
컬럼의 오프셋(delta = wall_sec - t, route1에서 상수 55663.85로 확인)을
구해 mp4 구간을 CSV `t` 범위로 역산 → qcamera 프레임(danger box 거리/
감속표시 값)으로 최종 교차검증. (다음 세션도 같은 방식 재사용 가능 —
delta는 route/부팅마다 다시 계산 필요, 상수 자체를 재사용하면 안 됨.)

**핵심 발견 (route1 t=683.85~696, "레이더락온시 급감" 클립과 일치
확인됨)**:
1. t=683.85~690.0(6.15초) 비전 단독 추적 구간 — modelProb 최대 0.93,
   `leadVLead` 12~16m/s로 안정적으로 보고(자차 17.9m/s와 큰 차이 없어
   "안전"으로 보임). dRel은 83~119m 사이 노이즈성 요동(인접 차로 트랙
   혼입 의심).
2. t=690.05 레이더 락온 순간 `leadVLead`가 7.1m/s로 급락, `vRel`이
   -3.6→-10.8m/s로 급변 — 실제로는 정체로 서행/정차 중이던 진짜
   선행차였음이 이 프레임에야 드러남.
3. 이후 1.5초 만에 aEgo 0→-2.1m/s²(사실상 A_CRUISE_MIN 근접)까지 급락,
   정지 직전까지 강제동. qcamera 프레임(t≈696, drel≈30m, red danger
   box)이 mp4 클립 마지막 프레임(-1.36/-1.64 표시)과 일치 확인.
4. route2 t=1378.8에도 동일 패턴(aEgo drop 2.92, 지금까지 최대) 1건
   추가 확인 — 재현성 있는 패턴으로 판단.

**원인 특정 (`long_mpc.py`)**:
- 방안G의 discontinuity 감지(L861~880)는 `not radarstate.leadOne.radar`
  (비전 단독 구간) 안에서만 동작하고, dRel 15m+ 급락만 트리거함.
  **레이더가 락온되는 그 프레임(L901 elif) 자체는 부기 리셋만 하고
  discontinuity 판정을 아예 하지 않음** — "비전→레이더 전환 시점의
  속도(vRel/vLead) 불연속"은 현재 코드의 사각지대.
- `LEAD_ACQ_RAMP_TIME=5.0s` 선제감속 floor도 구조적으로 무력화됨: 이
  리드가 비전으로 처음 잡힌 게 t≈684.05, 5초 램프 종료가 t≈689.05 —
  **진짜 위험이 드러난 t=690.05보다 1초 먼저 "안전 판정"으로 방어막이
  풀린 직후**에 위험이 드러남. 비전이 몇 초간 낙관적으로 유지되는
  케이스에서 구조적으로 반복 가능한 타이밍 문제로 판단.
- `VISION_RADAR_CROSSOVER.md`(8/19~20 로그 기반 사전 조사)에서 예상했던
  현상의 실차 재현 사례로 봐도 됨.

**제안한 수정 방향(사용자 확인 대기, 아직 미적용)**: 레이더 False→True
전환 프레임에서 새로 확정된 vRel/vLead가 직전 참고값(`_vision_dRel_rate`
등) 대비 일정 폭 이상 나쁜 쪽으로 튀면, 기존에 검증된
`_discontinuity_jerk_boost_timer`(방안G) 그대로 arm — TTC danger
override(2.5s 이하)는 그대로 유지해 진짜 위험엔 영향 없음, 도달
감속량은 그대로 두고 도달 속도(저크)만 완만화. 신규 상수 가칭
`RADAR_HANDOFF_VREL_JUMP_THRESH` 추가 제안.

**다음(사용자 확인 대기)**:
1. 위 수정 방향대로 패치 작성해도 될지 확인(임계값 포함).
2. mp4 3개 중 "카메라락온_부드럽게_정지"/"카메라인식" 클립은 아직
   개별 매칭 완료 안 됨(대략적 대조만 함, t=945~972 구간이 후보이나
   정확한 프레임 대조 미실시) — 필요시 다음 단계에서 마저 확인.
3. 71차 이월 항목(방안F/H, 저속근접 gap 오실레이션, `sim_jerk_boost.py`
   확인)은 이번 요청 처리 후 순서 재확인 필요.

**코드 변경 없음(분석 + 원인특정만, 패치는 사용자 확인 후 진행 예정).**

## 71차 (완료 — 분석/qcamera 대조만, 코드 변경 없음) — 최신 브랜치 실차 로그 2건 전체 분석, [신규] 장기 비전 진동 사례 발견

**배경**: HEAD `0c137f28b456`(67차 방안G) 기준 실차 로그 2개(route1 19세그
/1140s, route2 7세그/393s) 업로드받아 전체 분석 + qcamera 대조 수행.

**핵심 결과**:
1. harsh_brake 8개 독립사건 중 6건 운전자 직접개입(ADAS 무관), 2건만
   cruise 유지 중 발생(아래 2/3번).
2. TTC danger override 4건 중 3건 qcamera로 정탐 확인(정지/서행
   선행차, 곡선구간 브레이크등 켜진 차량), 1건은 운전자 수동정차라
   무관.
3. **[정정, 사용자 확인 — 버그 아님]** route1 seg4 t=356~368: 실제로는
   **자차 우회전 차선변경 + 변경 차로 혼잡**(rightBlinker=True가
   t=364.0부터 확인, 사용자 설명과 일치). t=356~364의 비전 dRel
   극심 진동은 혼잡 차로 내 여러 차량 사이를 트랙이 옮겨다닌 것으로
   재해석 — "discontinuity suppress가 실제 위험을 오래 억제" 가설
   기각. replay 검증 불필요.
4. 곡선 비전노이즈 억제율 route1 80.5%/route2 100%로 기존 패턴과
   일치, 새 이상 없음. turn_speed_violation 3건은 전부 저속
   `src=gas`(운전자 개입) 경계사례. congestion lurch 스캔 0건(58차2번
   회귀 없음).

상세는 FINDINGS.md "71차" 항목 참고.

**다음 세션 최우선**:
1. ~~route1 seg4(t=356~368) 원본 코드로 replay 검증~~ → **철회**(사용자
   확인 결과 버그 아님, 우회전 차선변경 상황).
2. 70차에서 이월된 항목(방안F/H 진행 여부, 세그7 후반 저속 근접 gap
   오실레이션 조사 착수 여부, `sim_jerk_boost.py` 실물 확인)이
   여전히 사용자 결정 대기 중.

**코드 변경 없음(분석/qcamera 대조만).**

## 70차 (완료 — devnotes 정정만, 코드 변경 없음) — [69차 정정] 방안 D~H 전체 경위 확정

**배경**: 사용자가 63~67차에 걸친 실제 세션 대화록을 제공해줘서, 69차가
"경위 불명/확정 불가"로 남겨뒀던 부분들을 전부 확정 기록으로 정정.
상세는 FINDINGS.md "70차 — [69차 정정] ..." 섹션 참고. 요약만 남김:

- **방안D**: 63차 계속3에서 명시적으로 기각/폐기 확정(seg14 7회 재트리거
  로 리셋이 무의미했고, seg14의 raw dRel 자체가 물리적으로 불가능한 값을
  보여 신호 자체가 의심스러웠음).
- **방안E**: 1차 교차검증에서 REJECTED 판정 났었으나(seg3에서 frac_rate
  억제를 리스크로 오판), 사용자가 원 의도("끼어드는 차가 더 빠르면
  레이더 락온 후처럼 정상주행 원함")를 정정 설명 → Claude가 재검토해
  그 억제가 정탐이었음을 확인 → REJECTED 철회, 채택 확정(e6a00ae).
- **방안F/G/H**: 방안E 실차검증(cutin 정상 처리 확인) 도중, 사용자가
  별도 이슈(차선변경 중 새 차로 앞차 인식 시 짧은 급감속의 체감 승차감)
  를 제기해 새로 파생된 스레드. vRel 부호 이진게이트 안은 실측으로
  기각, Claude가 3안(F=x_lead 블렌딩/G=discontinuity 직후 저크비용
  한시부스트/H=vRel 연속가중치) 제시, G를 "가장 가볍고 리스크 작음"으로
  우선 추천 → 66차 설계확정/67차 구현. **F/H는 명시적 기각이 아니라
  아직 미착수 상태로 후순위 대기 중**(69차가 "흔적없음, 확정불가"라고
  했던 것과 달리, 폐기가 아니라 "아직 안 한 것"임이 이번에 확정됨).
- **67차 [재생성]**: 69차 추측이 맞았음 — 컨테이너 리셋으로 패치 유실,
  FINDINGS.md의 "[66차, 방안G 구현]" 기록을 근거로 재구현. 단 그 근거
  기록 자체도 지금 devnotes엔 없어(재유실 추정) 66차 원본 설계 상세는
  여전히 복원 안 된 상태(코드 diff+대화록 재구성 수준까지만 복원됨).

**[신규, 미해결] 세그7 후반 "저속 근접 gap 오실레이션"**: 방안F/G/H
설계 논의 중 부수적으로 발견된 별개 패턴(discontinuity와 무관, 5~7m
근접 저속 추종 중 vRel 반복 진동으로 aEgo 재감속). 코드화 이전 단계
(발견만 됨) — 착수 여부 다음 세션에서 사용자 확인 필요.

**다음(사용자 결정 대기)**:
1. 방안F/H를 이어서 진행할지, G만으로 충분한지 — 66~67차 이후 실차
   검증 결과에 달려있음.
2. 저속 근접 gap 오실레이션(세그7 후반) 조사 착수 여부.
3. `toolkit/sim_jerk_boost.py` 실물 존재 확인(69차에서 이월, 아직 미확인).
4. 방안E/G 최종 acados 파이프라인 실차검증 — 최신 HEAD(`0c137f2`) 기준
   업데이트된 실차 로그 확보 시 진행.

**코드 변경 없음(devnotes 기록 정정만)**.

## 69차 (완료 — devnotes 역보완만, 코드 변경 없음) — 64~67차 devnotes 공백 채움

**배경**: 68차가 남긴 "devnotes 공백" 최우선 과제를 이번 세션에서
처리. `ryu` repo `git log`/`git show`로 `4ea63c3`(방안C, 61차) 이후
커밋을 직접 대조.

**정정(중요)**: 68차 메모의 "64~67차(방안 D/E/F/G) 4개 커밋"은 부정확
— 실제로는 **`e6a00ae`(63차 계속10, 방안E)와 `0c137f28b456`(67차,
방안G, 커밋메시지에 "[재생성]" 표기) 딱 2개 커밋뿐**. 방안D는 63차
계속 FINDINGS 제안(discontinuity 시 `_vision_dRel_rate` 직접 리셋)
그대로 구현된 흔적이 git log/코드 어디에도 없고, 방안F는 코드 주석
포함 완전히 흔적 없음 — 둘 다 실제 커밋으로 이어지지 않은 것으로
보임(경위 불명, 사용자 확인 필요).

**작업**: 두 커밋(`e6a00ae`/`0c137f28b456`)의 diff(코드 내 상세 설계
주석 포함)를 그대로 역추출해 FINDINGS.md에 신규 섹션 2개로 기록
(방안E: leadVLead 참고 closing rate 상대적 타당성 클램프 /
방안G: discontinuity 직후 a_change_cost 한시적 부스트). 두 항목 모두
PARAMS_REGISTRY.md엔 이미 NEEDS_VALIDATION으로 기록돼 있었음(devnotes
공백에도 PARAMS_REGISTRY만은 최신이었던 것으로 보임 — WIP.md/
FINDINGS.md만 push 누락됐던 것으로 추정, 62차 때와 유사한 패턴 재발).

**다음(최우선)**:
1. **방안D 폐기/방안E 채택 경위, 방안F 존재 여부** — git/코드만으론
   확정 불가, 사용자에게 직접 확인 필요.
2. `toolkit/sim_jerk_boost.py`(방안G 합성검증 스크립트로 코드 주석에
   언급됨) 실물 존재 여부 확인 — 이번 세션 컨테이너엔 미확인.
3. 방안E/G 둘 다 여전히 실차 미검증(NEEDS_VALIDATION) — 68차 분석
   로그도 방안C까지만 반영된 구브랜치였음이 확인돼, 방안E/G가 실제
   반영된 실차 로그는 devnotes에 아직 하나도 없음. 사용자가
   `c3-ms-dev` 최신 HEAD로 기기 업데이트 후 cutin(r1-3/r1-14류)
   재현 로그 확보 시 검증 착수.
4. 68차 원래 항목(seg7/seg11 분석, 버그 아님 판정)은 이미 완료 —
   아래 68차 섹션 그대로 유효, 추가 조치 불필요.

**코드 변경 없음(devnotes 기록 보완만)**.

## 68차 (완료 — 분석만, 코드 변경 없음) — "정체구간 앞차출발→정지 급정거" 제보 분석, 버그 아님 판정

**배경**: 사용자가 "정체구간에서 앞차 출발 후 따라가다 앞차 정지 시
내차 급정거" 증상 제보 (실제 기기는 58차까지만 적용된 구브랜치라고
명시) → route `0000031d--4ddb171bfb`(14세그) 업로드받아 seg7/seg11
qcamera 대조 분석.

**결과**: 둘 다 버그 아님.
- **seg11**: 정체 정지→출발→앞차 재감속→자차 재감속(-1.03m/s² 최저,
  저크 없음) 매끈한 정상 사례 — 58차2번(LOW_SPEED_STRONG_DECEL)이
  겨냥한 "붕끗" 없이 잘 동작.
- **seg7**: t=519.82 dRel 48m→18.6m 불연속 발견, 처음엔 61~66차류
  vision 오검출(트랙전환) 의심했으나 **qcamera 대조 결과 실제
  cut-in(흰색 세단이 인접차로에서 자차 차로로 끼어듦)으로 확정**.
  이후 aEgo -2.53m/s²(30km/h) 최저점도 qcamera로 **끼어든 차가
  교차로 적신호 앞 실제 급제동 중이었음** 확인 — 정당한 방어 반응.

**[신규, 경미] devnotes 공백 발견**: ryu repo git log상 64~67차(방안
D~G) 커밋이 존재하나 FINDINGS.md/WIP.md엔 63차 계속10(방안E)까지만
기록됨 — 62차 때와 유사한 push 누락 패턴 재발 추정.

**다음 세션 최우선**:
1. `git log` 기준 64~67차(방안 D/F/G 등) 커밋 내용을 FINDINGS.md/
   WIP.md/PARAMS_REGISTRY.md에 역보완 기록.
2. 이번 seg7류(cut-in+선행차 급제동) 자체는 버그가 아니므로 추가
   조치 불필요 — 단, 사용자가 실제 최신 브랜치(64~67차 적용)에서도
   동일 상황이 여전히 "체감상 급함"이라면 그건 별도 신규 제보로
   재접수.

상세는 FINDINGS.md "68차" 항목 참고.

## 63차 계속 (체크포인트2 — r1-3/r1-14 원본 rlog 재업로드받아 실측 재생 검증 완료, **중요 발견: 방안C 보호 공백**)

**배경**: 63차 체크포인트 직후 사용자가 r1-3/r1-14 원본 rlog(같은
16세그 로그, route `a2141d7786` seg3/seg14)를 재업로드 → 드디어 실측
재생 검증 진행.

**핵심 발견**: `long_mpc.py` 실제 코드를 그대로 복제한
`work/route63/replay_drel_discontinuity_real.py`로 PATCHED/UNPATCHED
비교 재생.
- **r1-3(seg3)**: discontinuity 정상 트리거(7프레임), aEgo 최저치 부근
  frac이 PATCHED 0.27~0.36 vs UNPATCHED 0.90~0.98 — **방안C 효과 확인**
  (radar가 이미 락온한 구간이라 frac_time 개선분이 그대로 드러남).
- **r1-14(seg14)**: discontinuity 정상 트리거(6프레임)했으나, aEgo
  최저치 부근 frac이 PATCHED=UNPATCHED=1.0으로 **완전히 동일 —
  방안C가 이 사례엔 사실상 무효**. 원인: radar 락온 전(vision-only
  지속)인 구간이라 `frac_rate`/`frac_ttc`가 여전히 활성인데, 이 둘은
  discontinuity suppression과 무관하게 `_vision_dRel_rate`를 직접
  읽음 — 방안C는 `_lead_acq_timer`만 리셋할 뿐 오염된 `_vision_dRel_
  rate` 자체는 그대로 둬서, 0.5초(`VISION_CLOSING_RATE_MIN_TIME`)만
  지나면 frac_rate가 다시 1.0으로 즉시 복귀함.

**의미**: 방안C(60차 계속 신규등록 게이트 재사용)는 "v_lead 직접보정"
경로만 보호하고 "frac_time/frac_ttc/frac_rate floor" 경로(25차/33차)는
애초에 보호 범위 밖이었음이 실측으로 처음 드러남. radar 락온이 빠른
케이스(r1-3류)는 우연히 frac_rate/ttc가 락온 즉시 0으로 리셋돼 보호
효과가 있었지만, 락온이 늦는 케이스(r1-14류)는 무방비.

**다음(최우선, 최상위로 격상)**:
1. **방안 D 설계 착수**: discontinuity 트리거 시 `_vision_dRel_rate=0.0`
   + `_vision_dRel_rate_window.clear()`도 함께 리셋 — frac_rate/frac_ttc
   경로까지 보호 확장. danger override(TTC<=2.5s, vRel 기반 직접경로)는
   무관하게 항상 살아있음을 재확인하며 설계.
2. 방안 D를 `replay_drel_discontinuity_real.py`에 추가해 seg3/14 둘 다
   frac이 낮아지는지 재생검증 먼저(패치 전 시뮬레이션 우선 원칙) →
   통과 시 패치 작성.
3. 실차 검증 시 r1-3류 vs r1-14류(radar 락온 지연 정도)를 구분해서
   관찰 필요 — 이 발견이 실차에서도 재현되는지 확인.

**세션 종료 아님 — 중단지점 저장.** 상세는 FINDINGS.md "[63차 계속,
중요] 방안 C 실측 재생 검증 완료" 항목 참고.

## 63차 (체크포인트 — 방안C 시뮬레이션 재검증만, 코드 변경 없음, 실차/원본로그 검증 대기)

**배경**: 62차의 "다음(최우선)" 항목 중 "최근 패치된 브랜치 시뮬레이션
검증" 요청 → 컨테이너 리셋으로 유실된 `work/sim_drel_discontinuity.py`
(방안 C 로직 단위 합성검증)를 재작성. 이번엔 실제 `long_mpc.py`
801~844줄 코드를 그대로 복사해 재현하는 방식으로 개선(이전엔 순수함수
재구현이라 코드-시뮬레이션 drift 리스크 있었음).

**결과**: 기존 4개 시나리오 + 신규 2개(신규등록 게이트와의 이중 트리거
부작용 확인/danger override 독립성 재확인) 총 6개 전부 PASS. 상세는
FINDINGS.md "[63차, 체크포인트] 방안 C 시뮬레이션 재검증" 항목 참고.

**한계(변함없음)**: r1-3/r1-14 원본 rlog가 이번 세션에도 없어, 여전히
"문서 기록 기반 근사 시뮬레이션"만 완료 — 실제 로그 재생 검증은 못함.

**다음(최우선)**:
1. r1-3/r1-14 원본 rlog(가능하면 qcamera 포함) 재업로드 → 실측 dRel
   시퀀스로 방안C 로직 직접 재생 검증.
2. 위가 어려우면 실차 드라이브 검증으로 바로 진행: (a) cutin 재현 시
   급감속 완화 여부, (b)(c)는 이번 세션 로직 검증으로 커버됨(회귀
   위험 낮음 확인) — 실측 확인만 남음.
3. `DREL_DISCONTINUITY_DROP_THRESH`/`WINDOW_N` 값 실차 반응 보고 튜닝
   여지 있음(설계 추정치 그대로).

**세션 종료 아님 — 중단지점 저장.**

## 62차 (체크포인트 — 유실된 61차 방안C 기록 복구, 패치 재검증 완료, 사용자 적용/push 여부 확인 대기)

**배경**: 새 세션 시작 시 사용자가 로컬 `C:\dev\ryu`의
`long_mpc.py`(방안C 코드 이미 반영된 상태)를 업로드 → devnotes를 fresh
clone해보니 61차 계속(방안C) 작업의 FINDINGS.md 기록이 origin에 없음을
발견(직전 세션이 push 없이 종료돼 유실됐던 것으로 추정).

**복구 조치**:
1. 업로드된 `long_mpc.py`를 컨테이너 `ryu` clone(origin HEAD `d6e334f`)에
   덮어써 로컬 커밋 재구성 → `py_compile` 통과, `git diff --stat`으로
   변경분이 43줄 추가(방안C 코드 그대로)임을 확인.
2. `git format-patch` → `verify-am-61c` 임시 브랜치(base `d6e334f`)에서
   `git am` 컨텍스트 일치 + `py_compile` 재확인 완료.
3. `0001-61-C-cutin-dRel-suppress.patch`를 `/mnt/user-data/outputs/`에
   재생성해 전달.
4. FINDINGS.md의 "[신규 발견 + 방안 C 구현 완료]" 항목을 그대로
   복구·재기록(복구 경위 문구 추가).

**[해결 완료]** 사용자가 `git fetch origin` + `git log --oneline -5
origin/c3-ms-dev` + `git log --oneline origin/c3-ms-dev..HEAD`로 직접
확인 — origin `c3-ms-dev` HEAD가 `4ea63c3`(방안C 커밋)이고 로컬 HEAD와
정확히 일치, 로컬에 미푸시 커밋도 없음(`origin/c3-ms-dev..HEAD` 빈
결과). **패치 적용 + push 완료 재확인됨.** LAST_ANALYZED.md 갱신 완료.

**다음(최우선)**: 61차 계속(방안C) FINDINGS.md 항목의 "다음(최우선)"
2~5번으로 진행:
1. 실차 검증: (a) r1-3/r1-14류 cutin 재현 시 급감속이 실제로 완화되는지,
   (b) **회귀 검증 필수** — 진짜 급접근(전방 차량 급브레이크 등)에서
   danger override가 지연 없이 그대로 작동하는지, (c) 신규등록
   게이트(60차 계속2)와 겹치는 케이스에서 이중 트리거로 인한 부작용
   없는지.
2. 가능하면 r1-3/r1-14 원본 rlog 재업로드받아 실측 dRel 시퀀스로 이번
   로직을 직접 재생 검증(현재는 문서 기록 기반 근사 시뮬레이션뿐).
3. `DREL_DISCONTINUITY_DROP_THRESH=15.0m`/`WINDOW_N=5` 값 자체는 설계
   추정치 — 실차 반응 보고 튜닝 필요.

## 61차 계속 (체크포인트3 — 나머지 13세그 중 11세그 qcamera 대조 완료, 이전 패치까지 포함 검증 완료)

체크포인트2 이후 사용자가 "이번 패치뿐 아니라 이전 패치도 검증, 나머지
증상 증상별 분석, qcamera 대조 필요" 요청 → 같은 16세그 로그(commit
`d6e334f`, 60차 계속8+60차 A/B 전부 반영)로 나머지 13세그 중 11세그
(route1 seg1/3/6/9/12/14/15/17/19, route2 seg2/4/6, route2 seg5는
저위험 생략)를 증상별로 qcamera 프레임 대조 완료. **전부 정탐(실제
차량/정체/신호대기 확인), 오탐 0건.** seg9(차선변경)는 blinker 구간
내내 aEgo 0 근처로 60차 A dPath게이트가 차선변경 오탐을 정상 차단함을
재확인. route2 seg4(정지앞차 카메라인식)는 58차1/60차A가 겨냥한 핵심
시나리오(신호대기 정지선행차 조기인식)가 정상 동작함을 확인. 상세는
FINDINGS.md 61차 계속 항목 참고.

**16세그 전체 결론(최종)**: 개별 qcamera 검증 14/16세그 완료, 오탐
0건. 유일한 이상신호는 seg1(옆차선 레이더 오탐, 오늘 패치와 무관한
별도 메커니즘, 체크포인트1에서 이미 규명). **오늘 검증한 2개 패치
(60차 계속8 외곽게이트 수정 + 60차 A/B tentative등록/dPath게이트)
모두 안전하게 동작 중, 회귀 없음.**

**남은 항목**:
1. route2 seg2 "체감 급감 vs 기록 aEgo 완만(-0.65)" 괴리 — 미세 저크
   스캔 필요(58차3 롤백 때 나온 가설과 동일 축), 저우선.
2. seg1 근본원인(SCC_FALLBACK_DPATH_GATE vLead<5.0 조건부 사각지대)
   패치 설계 — 사용자 논의 대기, 여전히 미착수.
3. route2 seg5 qcamera 미실시(저위험 생략) — 필요시 추가.
4. turn_speed_violation 3건 개별 미확인(체크포인트1부터 이월).

**세션은 계속 사용자와의 개선방향 논의 단계.**

## 61차 (진행중, 체크포인트1 — 오늘 패치 실차검증 로그 16세그 분석 시작)

**배경**: 60차 계속8(외곽게이트 fix, HEAD `d6e334f`) 적용 후 사용자가
실주행 로그 2개 부팅세션(route `a2141d7786` 9세그/`6f02a46c8a` 7세그,
총 16개 event-triggered 세그, 각 화면녹화 clip 제목=증상라벨)을 업로드
— "오늘 패치가 잘 적용됐는지 로그+영상 대조분석, 이후 개선방향 논의" 요청.
CSV 추출 확인 결과 `commit=d6e334f1ddb5`로 오늘 패치가 실제 반영된 상태에서
기록됐음 확인.

**진행 상황**: 16세그 개관(min_aEgo/cruise_ratio) 완료, 전체
harsh_brake(ADAS 활성중 0건 양쪽 route)/turn_speed_violation(1/2건) 스캔
완료. **seg1("옆차선 레이더 오탐 급감_이후 카메라인식") 상세 분석
완료** — qcamera 프레임 대조까지 마침, **오늘 패치(60차 A/B, VisionTrack
tentative 등록)와 무관한 별도 메커니즘(track_scc/37차 SCC_FALLBACK_
DPATH_GATE)의 사각지대로 추정**(NEEDS_VALIDATION, 상세는 FINDINGS.md
61차 항목 참고) — dPath 게이트가 `track_scc.vLead<5.0`(거의 정지한
물체) 조건에서만 작동해, 이번 사례(vLead≈9.6m/s)처럼 중속도 구간
레이더 단발 오탐은 게이트 보호 밖에 있을 가능성.

**seg3("옆차선 카메라 오탐 급감") 1차 분석**: dRel/vRel/aEgo 궤적이
매끄럽고 qcamera로도 실제 전방 차량 정지/서행이 보여 "오탐이 아니라
진짜 정체 추종"으로 보이나, 6프레임 샘플링(2~4초 간격)이라 확정 못함
— **다음 체크포인트에서 t=1503.75~1507 조밀 재확인 필요**.

**[갱신, 체크포인트2] seg3/4 연속성 확인 완료 + 16세그 자동 이상탐지 완료
+ 1차 종합판단 완료** — 상세는 FINDINGS.md 61차 체크포인트2 항목 참고.
핵심: seg3("옆차선 카메라 오탐")은 재확인 결과 seg4와 연속된 진짜
정지차량 추종 이벤트로 판단(오탐 근거 못 찾음, 저우선 재검증 여지만
남김). 16세그 전체 자동 스캔에서 체크포인트1의 seg1 1건만 뚜렷한
이상 신호, 나머지는 정상 노이즈 수준. **오늘 패치(60차 계속8)는 로그에
실제 반영 확인, ADAS 유발 harsh_brake 0건, 60차 A/B 핵심 타겟(정지앞차
인식)도 정상 동작 확인. seg1(옆차선 레이더 오탐)만 오늘 패치 범위
밖의 별도 메커니즘(track_scc SCC_FALLBACK_DPATH_GATE의 vLead<5.0 조건부
사각지대)으로 추정되는 신규 발견.**

**남은 항목(다음 세션 후보, 저우선 — 이번 세션 종합판단은 완료됨)**:
1. turn_speed_violation 3건 개별 미확인.
2. seg1 근본원인 확정용 dPath/trackId 확장 추출 스크립트 필요 →
   SCC_FALLBACK_DPATH_GATE의 vLead<5.0 조건 완화 패치 설계 논의.
3. 나머지 13세그(cutin/cutout/차선변경/정체정지출발/앞차카메라인식x6/
   cutout후지연출발) 개별 qcamera 정밀검증(자동스캔은 완료, 이상없음).

**이번 세션은 사용자와의 대화로 개선방향 논의 단계로 전환.**

## 60차 계속8 (체크포인트 — [URGENT, FIXED] 외곽게이트 버그 재발 수정/git am검증/전달 완료, 사용자 적용 대기)

**배경**: 사용자가 "이 패치가 컷인 상황에도 영향을 주나" 질문 → 컷인
경로(`compute_leads()`, 레이더 `Track.cut_in_count` 기반)는 `VisionTrack`
과 무관해 영향 없음을 확인하는 과정에서, `get_lead()` 외곽 함수가
`lead_msg.prob > .5`를 `VisionTrack.update()` 내부와 별개로 독립
재체크하고 있어 **60차 A(tentative 조기등록)가 실제 `radarState.leadOne`
출력엔 전혀 반영 안 되고 있던 것을 발견**.

**동일 버그 재발 확인**: 이건 58차3번 후속수정(`1145aea`)이 원래 고쳤던
버그와 정확히 같은 패턴(`elif ... lead_msg.prob > .5` 재체크가
tentative 승격을 무력화). 58차3번+후속수정 전체 롤백(`1ac07de`, radard.py
58차2번 시점 완전 원복)으로 이 수정도 같이 사라졌고, 60차 A가 tentative
로직을 재구현하며 외곽게이트 재반영을 빠뜨렸던 것 -- 즉 **현재
사용자 기기(`1a44491`)의 60차 A+B안은 내부 계산은 살아있지만 실제
출력엔 조기등록 효과가 전혀 없는 상태였을 가능성 높음.** 60차 계속5/6
시뮬레이션(9.2초 앞당김 등)은 VisionTrack 내부 로직만 순수함수 재현이라
이 외곽게이트 버그를 못 잡았음(중요 한계로 기록).

**조치**: `elif (track is None) and ready and (lead_msg.prob > .5):`를
`elif (track is None) and ready and self.vision_tracks[index].status:`로
교체(58차3번 후속수정과 동일 방식) -- `status`는 같은 tick에 이미
update() 끝난 최신 상태라 정식경로+tentative 조기등록 둘 다 자연히 포함.

**검증**: `git format-patch` -> `verify-am4` 임시 브랜치(base `1a44491`,
사용자 실제 로컬 HEAD를 이번 세션에서 origin fetch로 확보) `git am`
컨텍스트 일치 + `py_compile` 통과.

**전달**: `0001-60-8-get_lead-lead_msg.prob-vision_tracks-index-.sta.patch`
를 `/mnt/user-data/outputs/`에 생성, `git am` 안내와 함께 전달함(base
`1a44491`).

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`에서 `git am` 적용
(`Applying: 60차 계속8: get_lead() 외곽게이트 lead_msg.prob 중복체크 ->
vision_tracks[index].status로 교체`) + `git push origin c3-ms-dev` 완료.
origin `c3-ms-dev` HEAD: `1a44491..d6e334f`.

**다음(최우선)**:
1. ~~사용자가 `C:\dev\ryu`에서 `git am` 적용 + `git push origin c3-ms-dev`~~ → **완료**.
2. **실차 드라이브 검증 — 이 수정으로 60차 A(dPath게이트)+B안(prob리셋
   제거)이 처음으로 실제 동작**. 60차 계속7에서 안내했던 검증 항목
   그대로 유효(정지앞차/정체구간 조기인식, 옆차선/역광 오탐 회귀,
   산발적 tentative_cnt 누적 사각지대).
   **[60차 계속9 추가]** 정체구간에서 tentative 등록 직후 58차2
   저속강한감속게이트가 노이즈성으로 급하게 튀는 느낌이 있는지 추가
   관찰(로직단위 시뮬레이션으로 조합 리스크 발견, FINDINGS.md 60차
   계속9 항목 참고 — cutin/차선변경은 영향 없음 확인됨).
3. 이번처럼 "내부 로직 검증 PASS"와 "실제 출력 반영 여부"가 분리될 수
   있음이 두 번째로 확인됨(58차3번, 60차 A 둘 다) -- 앞으로 tentative/
   status 관련 신규 로직 추가 시, 외곽 게이트가 그 status를 실제로
   소비하는지 코드 리딩으로 매번 확인하는 걸 체크리스트화할 필요.

## 60차 계속7 (체크포인트 — B안 구현/`git am` 검증/전달 완료, 사용자 적용 대기) — A(tentative) prob 단독 리셋 제거

**구현**: `radard.py` `VisionTrack.update()`, 컨테이너 로컬 커밋 `82d39dc`
(base `a75c5cc`, 60차 A 위에 얹음). `elif self.prob < VISION_TRACK_
TENTATIVE_PROB_GATE: reset` 분기 제거 -- prob<0.35 프레임은 이제 아무
것도 안 하고(freeze) 넘어감, tentative_cnt/이력은 유지된 채 다음
tentative 구간 프레임에서 이어서 dRel/dPath jitter 판정. dPath 절대값
게이트/dRel·dPath jitter 게이트(진짜 "다른 물체로 전환" 신호)는 그대로.

**검증**: `git format-patch` -> `verify-am` 임시 브랜치(base `a75c5cc`)에서
`git am` 컨텍스트 일치 확인 + `py_compile` 통과.

**전달**: `0001-60-6-A-tentative-B-prob-0.35-tentative_cnt.patch`를
`/mnt/user-data/outputs/`에 생성, `git am` 안내와 함께 전달함(base
`a75c5cc`, 즉 사용자 로컬이 60차 A까지 적용된 상태여야 함 -- 이미
`d7c2b0d..a75c5cc` push 완료 확인된 상태이므로 그 위에 바로 적용 가능).

**시뮬레이션 근거**: 60차 계속5/6 항목(FINDINGS.md) 참고 -- 원 사례
(58차3번, a3a55cb808--10) 재등록 지연 8.1초->9.2초 앞당김, 옆차선
오탐 차단 회귀 PASS, 단발 노이즈(1프레임 유령객체) 오탐도 PASS.

**[갱신] push 완료 확인** — origin `c3-ms-dev` `a75c5cc..1a44491`.

**다음(최우선)**:
1. **실차 드라이브 검증** -- (a) 정지앞차/정체구간 조기인식이 실제로
   앞당겨지는지, (b) 옆차선/역광 상황 오탐 재발 여부(58차3번 seg2류),
   (c) **회귀 검증 필수** -- prob 하한 리셋 제거로 tentative_cnt가
   "오래 얼어붙은 채" 남아있다가 우연히 dRel/dPath가 맞아떨어지는
   먼 미래 프레임에서 리셋 없이 카운트가 이어지는 이론적 사각지대
   존재(0.5초 연속이 아니라 "산발적 10프레임"이 될 수 있음) -- 일반
   주행에서 예기치 않은 조기등록이 늘어나는지 특히 주의 관찰.
3. 통과 시 60차 A(옆차선 dPath 게이트)+B안(prob리셋 제거)이 최종
   확정, 다음 스레드(58차2번 실차검증 등 잔여 항목)로 복귀.

## 60차 계속6 (체크포인트 — 방향 결정 완료, 구현 착수 직전) — B안(prob 단독 리셋 제거) 채택

**배경**: 60차 계속5에서 발견한 "60차 A가 원 사례에 효과 0" 문제의
원인이 dPath 게이트가 아니라 `prob<0.35` 단독 리셋(노이즈성 prob
출렁임에도 카운트를 통째로 0으로 날림)임을 확인 → 두 가지 조치안을
원 사례 + 옆차선 오탐 회귀 + 단발 노이즈(유령객체) 오탐 3개 기준으로
비교 시뮬레이션.

**비교 결과**:
- A안(dPath in-lane이면 prob/cnt 무관 즉시등록): 원 사례 9.66초
  앞당김, 옆차선 차단 PASS, **단발 노이즈(1프레임 유령객체) 오탐 FAIL**
  — 58차3번 롤백 사유(체감 오탐/flicker)를 정면으로 키우는 방향이라 기각.
- **B안(prob<0.35 단독으로는 리셋 안 함, dRel/dPath jitter·dPath 절대값
  게이트만 리셋 사유로 유지, CNT_GATE=10 그대로) 채택**: 원 사례 9.20초
  앞당김(8.1초 지연 사실상 해소), 옆차선 차단 PASS, 단발 노이즈 오탐도
  PASS(0.5초 연속 요구가 그대로 유지되므로).

**사용자 결정**: B안으로 패치 진행. 상세 비교 수치는 FINDINGS.md
"60차 A ... 효과 0" 항목 뒤에 이어서 기록 예정(구현 완료 후 갱신).

**다음(이어서 진행)**: `radard.py` `VisionTrack.update()`의
`elif self.prob < VISION_TRACK_TENTATIVE_PROB_GATE: reset` 분기를
제거/완화하는 패치 구현 → `git am` 검증 → `C:\dev\patch\` 전달.

## 60차 계속5 (체크포인트 — 코드 변경 없음, 실측 시뮬레이션만) — 60차 A 원 사례 재현 검증: 효과 0 확인, 튜닝 방향 결정 대기

**배경**: 사용자가 60차 A(`a75c5cc`)를 58차3번을 촉발했던 원 사례
(route `a3a55cb808--10`, 정체구간 정지앞차 미인식, t=4301~4312) 로그로
직접 시뮬레이션 요청.

**작업**: `extract_modelv2_leads.py`(신규, work/ 스크래치)로 modelV2
leadsV3[0] 프레임(prob/dRel/dPath, Track.d_path와 동일 원리로 md.position
보간) 1200행 추출 → `a75c5cc`의 `VisionTrack.update()` tentative 분기를
순수함수로 재현해 재생.

**핵심 결과**: 이 원 사례에서 패치 전/후 재등록 시각 **완전 동일**
(0초 앞당김) — tentative 경로 발동 자체가 안 됨. 원인은 유실 9.7초
구간에서 `tentative_cnt`가 최대 3까지만 도달(`CNT_GATE=10` 필요),
리셋 3회 전부 `prob<0.35` 하한(dPath 게이트 아님)로 인한 것 — modelV2
prob가 이 구간에서 광범위하게 표류해 tentative_cnt가 쌓일 새가 없음.
상세는 FINDINGS.md "[NEEDS_VALIDATION] 60차 A ... 효과 0" 항목 참고.

**함의**: 합성검증 5건 PASS는 전부 이상적 시나리오였고, 원래 문제
사례로는 이번이 첫 실측 검증인데 CNT_GATE=10이 사실상 발동 불가 수준.
옆차선 오탐 차단(dPath 게이트) 효과는 별개로 유효할 가능성 있음.

**다음(사용자 결정 대기, 최우선)**:
1. `CNT_GATE` 하향(10→3~5) 시뮬레이션 재검증
2. `prob<0.35` 하드리셋을 decay 방식으로 변경 검토
3. `PROB_GATE` 하한(0.35) 자체 하향 검토(가장 공격적, 오탐 리스크 큼)
4. 또는 이 사례 개선은 보류하고 현재 패치(`a75c5cc`) 그대로 실차 검증
   진행(옆차선 오탐 차단 효과만 확인)

58차3번 롤백(실주행 체감 오탐) 전례가 있어 1~3번은 오탐 리스크 신중히
판단 필요. **코드 변경 없음, 세션 종료 아님.**

## 60차 계속4 — A(tentative 조기등록) 재설계 패치 적용/push 완료 (`a75c5cc`), 실차검증 대기

**배경**: 정지앞차 미인식 문제(58차3번 A)를 재시도. 58차3번+후속수정은
실주행 체감 오탐/불필요감속으로 롤백됐으나(FINDINGS.md 참고), 롤백
사유가 A(조기등록)/B(저확신구간 안전측 보정) 중 어느 쪽인지 확정 못한
상태였음 — 이번엔 **B는 제외하고 A만** 재시도, 원인 판별력을 위해
변수를 하나씩만 바꿈.

**설계/구현** (`radard.py` `VisionTrack`, 커밋 `172bb7a`, base `1ac07de`):
- 기존 58차3번 A의 dRel jitter(8m) 게이트만으론 dRel은 비슷하고 dPath만
  다른 옆차로 차량류를 못 걸렀을 가능성(58차3번 seg2 "역광+다차선
  인접차량 혼선" 사례가 이 허점이었을 것으로 추정) — dPath 게이트 2종
  추가:
  1. **절대값 게이트**(`VISION_TRACK_TENTATIVE_DPATH_ABS_GATE=1.75m`):
     `|dPath|`가 이 이상이면(차로 밖) tentative 후보 자체에서 배제.
     jitter 게이트(값의 *변화*만 감지)와 달리, 옆차로에서 **안정적으로
     유지**되는 물체까지 걸러내는 게 핵심(37차 SCC_FALLBACK_DPATH_GATE
     =2.0m와 동일 원리).
  2. **jitter 게이트**(`VISION_TRACK_TENTATIVE_DPATH_JITTER=1.5m`):
     프레임간 dPath 변화량 감시(다른 물체로 전환 감지), 기존 dRel
     jitter(8m)와 병행.
- `VISION_TRACK_TENTATIVE_MEDIAN_WINDOW=3` 프레임 경량 중앙값 필터를
  tentative dRel 판정에 추가 — 단일 프레임 스냅 노이즈로 jitter 게이트가
  불필요하게 리셋되는 것 방지. 정식 등록 후 dRel/vRel 계산엔 영향 없음.

**합성검증** (`devnotes/toolkit/sim_vision_track_a_dpath.py` 신규,
5개 시나리오 전부 PASS — `VisionTrack.update()`의 tentative 분기만
순수함수로 재현, 기존 세션들과 동일 방식):
- 정지앞차 조기등록 유지(회귀 없음 확인, 프레임9에서 등록)
- **옆차선 차량 승격 차단(핵심 신규)**: dRel은 정지앞차처럼 서서히
  감소하지만 dPath가 옆차로 수준(2.5m)으로 안정 유지되는 케이스 —
  1차 설계(dPath jitter 게이트만)에선 FAIL(승격 통과)이었으나, 절대값
  게이트 추가 후 200프레임간 등록 0회로 확실히 차단 확인.
- dPath 요동(다중 물체 혼선) 오인승격 방지
- 중앙값필터가 단일 프레임 스냅을 흡수(불필요한 리셋 방지) 확인
- 저prob(0.2, TENTATIVE_PROB_GATE 밑) 회귀 없음

**전달/적용**: `0002-60-A-tentative-dPath-jitter-dRel-B.patch`를
사용자 현재 HEAD(`d7c2b0d`, 60차 계속3의 v_lead 패치 적용 이후) 위에서
`git am` 검증 + `py_compile` 통과 확인 후 전달. **사용자가 `C:\dev\ryu`
에서 `git am` 적용 + `git push origin c3-ms-dev` 완료 확인** —
`d7c2b0d..a75c5cc`.

**다음(최우선, 실차)**:
1. 정지앞차 조기인식 실제로 앞당겨지는지 (58차3번 원 목적 달성 여부)
2. 옆차로/역광 상황에서 오탐 재발 여부 (58차3번 seg2류 재현 시 —
   이번엔 절대값 게이트로 차단됐어야 함, 실차로 재확인)
3. **회귀 검증**: 일반 주행에서 예기치 않은 변화 없는지
4. 통과 시 B(저확신구간 안전측 보정) 재도입 여부 논의 — 이번엔 A
   단독으로 오탐 없이 통과하는지부터 확인 후 결정

## 60차 계속3 — 패치 적용/push 완료 확인 (`d7c2b0d`), cutin(--5) 신규등록 게이트 컨테이너 재현 검증 완료

**적용 확인**: 사용자가 `C:\dev\ryu`에서 `git am 0001-60-58-1-v_lead.patch`
+ `git push origin c3-ms-dev` 완료. 원격 `c3-ms-dev` HEAD: `1ac07de..d7c2b0d`.

**cutin(--5) 게이트 시뮬레이션 검증** (컨테이너에서 route
`ee004b2c19--5` — 60차에서 이미 분석했던 그 route — CSV로 새 게이트
로직만 재현, 코드 변경 없음):
- t=408.136: 리드 신규 등록(prob=0.509 턱걸이), `_lead_acq_timer`=0 시작
- t=408.136~409.585(≈1.449s): vision-only(radar=False) 구간 — 60차에서
  확인한 dRel catch-up(65.7m→24.0m) 오염 구간과 정확히 일치. 전 구간
  `suppressed=True`(신규등록 게이트 1.5s 이내)로 58차1 v_lead 직접보정이
  억제됨 확인.
- t=409.637: 레이더 락온(dRel=11.6m), 이 시점 acq_timer=1.501s로 억제
  해제 — 단 락온 이후는 radar=True라 이 보정 자체가 적용 안 되는
  구간이라 무관.
- **결론**: 설계 시 추정한 `NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S=1.5s`가
  이 실제 로그의 vision-only 지속시간(1.449s)과 거의 정확히 일치 —
  신규등록 게이트가 이 cutin 사례의 취약구간 전체를 커버함을 확인.
- 참고: 이 route의 실측 `aEgo` 최저값(-2.75m/s², t=410.38)이 60차 원
  기록(-2.79)과 거의 일치 — **이 로그 자체는 패치 적용 전 상태에서
  녹화된 것**(문제 재현 로그, 이번 세션 시뮬레이션은 게이트 로직만
  코드 밖에서 재현 검증한 것이지 실제 패치 적용 후 재주행이 아님)임에
  유의. 실제 패치 적용 후 감속 완화 여부는 여전히 실차 재현 필요.

**다음(최우선, 실차)**:
1. cutin(--5류) 실제 재현 시 급감속 완화되는지 (패치 적용 후 재주행)
2. 차선변경(--12류) 실제 재현 시 급감속 완화되는지
3. **가장 중요 — 회귀 검증**: 정상 추종(비취약 상황, 신규등록 1.5s+
   경과 & 비차선변경)에서 58차1 원래 효과(원거리 반응 강화)가 그대로
   유지되는지, 불필요하게 조여지지 않는지
4. cutin(--5)/차선변경(--17) 원본 로그로 신규등록 게이트(1.5s)/hold(1.0s)
   값 자체의 실측 재조정 여지 계속 확인 (--5는 이번에 재확인했으나 다른
   표본도 있으면 추가 검증)

## 60차 계속2 — 58차1 v_lead 직접보정, 전역 스위치 대신 "취약 시나리오 한정 유예" 방식으로 재설계·패치 완료 (실차검증 대기)

**배경**: 사용자가 이전 체크포인트의 전역 킬스위치(`VLEAD_DIRECT_
CORRECTION_ENABLED`) 방식을 명시적으로 거부 — "58차1/2는 전반적으로
좋으니 그대로 두고, cutin/차선변경 상황에서만 패치 이전 로직이
적용되게" 요청. 전역 on/off가 아니라 **시나리오 한정 유예**로 재설계.

**설계**: 58차1의 `measured_v_lead` 보정 코드 자체는 그대로 두고,
`process_lead()`에 넘기는 `vision_dRel_rate` 인자를 아래 두 조건 중
하나라도 해당하면 `None`으로 전달(=패치 이전과 동일하게 `lead.vLead`
그대로 사용)하도록 `vision_rate_for_lead0` 계산부만 수정:
1. **신규 리드 등록 후 `NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S=1.5s`
   이내** (`_lead_acq_timer` 기준) — cutin류(--5) catch-up 구간 커버.
   60차 원 분석에서 등록~오염 관측 구간이 0.45~1.44s였으므로 1.5s면
   충분히 덮음(NEEDS_VALIDATION, 실측 재확인 시 조정 여지).
2. **차선변경 조작 중**(`leftBlinker`/`rightBlinker` 중 하나라도 True)
   **+ 종료 후 `LANE_CHANGE_VLEAD_CORRECTION_HOLD_S=1.0s` hold** —
   차선변경(--17/--12) 케이스 커버. blinker는 `longitudinal_planner.py`
   `update()`에서 `sm['carState']`로부터 뽑아 `mpc.update()`에 신규
   파라미터(`lane_change_blinker_active`)로 전달.
- 두 조건 모두 밖(정상 추종, 신규등록 1.5s 경과+비차선변경)에서는
  58차1이 패치 적용 당시와 100% 동일하게 작동 — frac_rate floor(26차
  원 로직)도 이 변경과 무관하게 그대로 유지.

**검증**: route `ee004b2c19--12`(이번 3번째 사례) CSV로 새 게이트
로직만 별도 재현(work/ 스크래치) — 문제 구간(t=816.98~817.44) 전체에서
`suppressed=True`(blinker 활성)로 정상 억제 확인. **cutin(--5)/차선변경
(--17) 두 원본 로그는 이번 세션에 없어(과거 세션 산출물, 컨테이너
로컬 미보존) 재검증 못함** — 신규등록 게이트(1.5s)는 60차 원 분석의
타이밍 기록으로 커버 가능성만 추정, 실측 재검증 필요.

**전달**: `0001-60-58-1-v_lead.patch`(base `1ac07de`) 생성,
`git am` 검증(temp branch) + `py_compile` 통과 확인 후 전달.

**다음 단계(최우선)**:
1. 실차 검증: (a) 이번 --12류 차선변경 재현 시 급감속 완화되는지,
   (b) cutin(--5)류 재현 가능하면 신규등록 게이트도 함께 확인,
   (c) **회귀 검증 필수** — 정상 추종(비차선변경, 신규등록 1.5s+
   경과) 상황에서 58차1 원래 효과(원거리 반응 강화)가 그대로
   유지되는지.
2. cutin(--5)/차선변경(--17) 원본 로그 재확보 시 이번 게이트 로직으로
   재시뮬레이션(신규등록 1.5s 게이트 실측 조정 여지 확인).
3. `LANE_CHANGE_VLEAD_CORRECTION_HOLD_S`/`NEW_LEAD_VLEAD_CORRECTION_
   SUPPRESS_S` 값 자체는 설계 추정치 — 실차 반응 보고 튜닝 필요.

## 60차 계속 (체크포인트 — 코드 변경 없음, 분석만) — 차선변경 급감속 3번째 사례 재현, 롤백 테스트 방안 안내

**배경**: 60차(cutin/cutout 급감속 NEEDS_VALIDATION, FINDINGS.md 60차
항목)에 이어, 사용자가 3번째 사례(`내차_차선변경.zip`, route
`ee004b2c19--12`, 자차 우측 차선변경 중 옆차선 택시는 멀어지는데
급감속 aEgo -1.82m/s²)를 제보. 분석 결과 60차와 동일한 메커니즘
(vision-only 구간의 다중 프레임 dRel catch-up이 58차1
`measured_v_lead` 직접 보정을 오염 → 락온 시점 dRel 스냅과 결합해
과잉감속) 3번째 독립 재현 확인. 상세는 FINDINGS.md "60차 계속" 항목
참고. **코드 변경 없음.**

**사용자 요청**: cutin(--5)/차선변경(--17/--12) 상황을 "패치 이전
단계"로 되돌려 58차1(v_lead 직접보정)이 진짜 원인인지 격리 테스트하는
방안 문의 — 대화창에서 직접 안내(git 브랜치 분리로 58차1만 격리,
58차2 저속 override는 유지하는 테스트 브랜치 방식 권고). 실제 브랜치
생성/패치 작업은 사용자 확인 후 다음 단계에서 진행.

**다음 단계**:
1. 사용자가 격리 테스트 방향(58차1만 되돌린 임시 브랜치) 확정하면
   패치 작성 → `C:\dev\patch\`에 전달.
2. 테스트 브랜치로 재드라이브, 동일 3개 route 상황 재현 시 감속 강도
   비교.
3. 개선 확인되면 정식 패치 설계(FINDINGS.md 60차 계속 "다음 단계"
   1/2번 참고) 착수.

## 59차 (체크포인트 — 코드 변경 없음, 설계 논의만) — 카메라 인식율 개선 방향 논의

**배경**: 58차3번(A+B) 롤백 이후 "카메라 인식율을 높이는 방법"을 사용자가
질문 → `radard.py VisionTrack`/`long_mpc.py` vision closing-rate 관련
코드를 다시 읽고 현재 구조(등록: prob>0.5 / 신뢰상승: cnt>=10 & prob>=0.70
전까지는 modelV2 예측치만 사용 / MPC 단: 클램프+중앙값+저역통과
closing-rate 게이트 + 58차1번 v_lead 직접보정) 설명 완료.

**58차3번 롤백 교훈을 반영한 개선 방향 3개 제안(코드 미착수, 사용자
결정 대기)**:
1. **신뢰도 전환을 이분법이 아니라 연속적으로** — 현재 cnt/prob 게이트가
   "모델예측 100% vs 실측블렌딩" 이분법(`VISION_TRACK_CNT_GATE`/
   `VISION_TRACK_PROB_GATE`)인데, 이걸 prob 상승에 비례해 서서히
   실측 dRel미분 비중을 늘리는 연속 가중치로 재설계.
2. **dPath(차선 대비 위치) 게이트를 VisionTrack 등록/신뢰상승 조건에
   포함** — 37차 옆차선 SCC 폴백 문제와 유사한 원리로, dPath가 급변하면
   (다른 물체로 전환 의심) 신뢰상승 리셋. 58차3번 A안이 seg2에서
   "역광+인접차량 혼선"으로 오탐한 사례를 구조적으로 줄이는 목적.
3. **VisionTrack 자체(radard.py)에도 경량 노이즈 필터 추가** — 현재
   클램프+중앙값 필터는 long_mpc.py에만 있고 radard.py dRel 미분엔
   없음. 등록 초기(cnt<10)에도 짧은 중앙값 필터를 넣어 조기등록
   재시도 시 스냅 노이즈 오탐 억제.

부가로 "체감 오탐 vs CSV 급감속(aEgo) 기준 오탐"의 정의 차이(58차3
WIP에 이미 기록된 가설)를 좁히기 위해, 다음 로그 분석 시 미세 저크까지
스캔 범위 확대 필요성도 재확인.

**다음(사용자 결정 대기, 최우선 후보 2개 중 택1)**:
(a) 위 1/2/3번 중 하나를 이번 세션에서 바로 설계·구현 착수, 또는
(b) 58차1,2번만 반영된 현재 baseline 실주행 재확인(WIP 58차3+후속수정
REVERTED 섹션에 이미 기록된 원래 다음 순서)부터 먼저 진행.

**세션 종료 아님 — 체크포인트 저장만.**


## 58차 3번+후속수정 REVERTED (2026-08-24) — 실주행 체감 오탐/불필요감속으로 롤백

사용자 실주행 피드백: "오탐이 많고 불필요한 감속이 체감됨" → 58차3번
(ff50b03, A 조기등록+B 안전측 보정) + 외곽게이트 후속수정(1145aea)을
전부 원복. `radard.py`가 58차2번(`a35a39f`) 시점과 완전히 동일한 상태로
복귀 확인(`git diff a35a39f origin/c3-ms-dev -- radard.py` 결과 empty).
push 완료: `1145aea..1ac07de`.

**바로 전 세션의 실차검증(FINDINGS.md "58차 3번+후속수정 실차검증"
항목)에서는 seg0 정탐(28초 정지앞차)/후속수정 실전파(690 row)를 영상+
수치로 확인했었으나, 사용자의 실제 체감 주행감은 오탐/불필요감속이
많았다는 상반된 피드백** — CSV 정량분석·특정 이벤트 단위 qcamera 대조로
잡힌 표본(3~4개 이벤트)이 전체 주행 체감을 대표하지 못했을 가능성.
다음에 A/B 재검토 시 이 괴리부터 짚고 갈 것: (1) 로그에 안 잡힌
tentative 등록/해제 flicker가 실제로는 훨씬 잦았을 수 있음(연속구간
묶기 로직이 과소집계했을 가능성), (2) "오탐"의 정의가 CSV 급감속
기준(aEgo)보다 사용자 체감(끊김/저크)에 더 민감할 수 있음 — 다음엔
급감속 임계값보다 낮은 미세한 accel jerk(rate of change)까지 스캔
필요.

**현재 상태(HEAD `1ac07de`)**: 58차1번(vision dRel미분 게이트완화+
long_mpc v_lead 보정)과 58차2번(저속+강한감속 danger override)만 유효.
A/B(tentative 조기등록/안전측 보정)는 코드베이스에서 완전히 제거됨.

**다음(최우선)**: 58차1,2번만 반영된 현재 상태로 먼저 주행감 재확인 →
문제없으면 그 상태를 새 기준선(baseline)으로 삼고, A/B는 설계 방향부터
재검토(재설계 시 tentative 승격 조건을 더 보수적으로: CNT_GATE 상향,
DREL_JITTER 하향, 또는 dPath/차선검증 추가 등 후보 검토).

## 58차 3번+후속수정 실차검증 완료 (2026-08-24 06:50 로그) — 부분 VALIDATED

14세그먼트 실차로그(commit `1145aea`)로 검증 완료. qcamera 대조까지
포함. 상세는 FINDINGS.md "58차 3번+후속수정 실차검증" 항목 참고.

**핵심 결과**:
- 외곽게이트 후속수정이 실로그에서도 동작 확인(690 row, 13개 구간)
- seg0 28초 정지앞차 이벤트 = qcamera로 정탐 확정 (단, cruise=False라
  제어 영향은 없었음 — 인지단만 검증)
- seg2에서 A가 cruise=True 중 신규발동한 유일 사례 발견 → dRel/vRel
  요동이 오탐이 아니라 "역광+다차선 인접차량 혼선"임을 qcamera로 규명
  (실제 감속엔 영향 없었음, vturn이 지배)
- seg4 실제 리드 감속 이벤트 = qcamera로 정상 확인, 운전자 브레이크는
  교차로 진입 때문으로 판단, 시스템 실패 아님

**다음 최우선**:
1. cruise 유지 중 A가 실제 accel/decel을 바꾸는 사례를 더 확보 (표본 1건뿐)
2. B(안전측 보정) 발동 사례 아직 못 찾음 — 추가 로그 필요
3. 다차선 인접차량 오인 리스크(seg2에서 확인) — `track_scc` lane
   validation 부재 findings와 통합해 별도 스캐너 설계 검토 필요

## 58차 3번 후속수정 (완료 — A 무력화 버그 수정 push 완료, 실차 재검증 대기) — 정지앞차 미인식

**배경**: 58차3번(A+B) push 직후, 사용자가 "오늘 커밋한 부분이 기기에러
안 나는지 검증해달라"고 요청 → 코드 재검토 진행.

**검증 결과**:
1. **크래시 위험 없음** — 신규 필드(`tentative_cnt`/`tentative_dRel_last`)는
   `get_lead()` 반환 dict(capnp 구조체로 대입되는 경로)에 전혀 안 들어감,
   40차 `sccFallback`류 크래시 재발 위험 없음 확인. `py_compile`/`git am`
   재검증(base `ff50b03`, 실제 원격 HEAD) 통과. 0-division 등 예외
   유발지점도 가드 있음 확인. (모듈 실제 import는 컨테이너에
   `msgq.ipc_pyx` 없어 완전한 파이프라인 검증은 이 환경에서 불가 — 기존
   세션들과 동일한 한계.)
2. **[FIXED, 긴급] A(조기등록) 무력화 버그 발견** — `get_lead()`(783번째줄,
   `RadarD.get_lead`, `VisionTrack.update()`를 감싸는 바깥 함수)의
   `elif (track is None) and ready and (lead_msg.prob > .5): lead_dict =
   self.vision_tracks[index].get_lead(md)` 이 `lead_msg.prob`를 **VisionTrack
   내부와 별개로 독립 재체크**하고 있었음. VisionTrack.update() 안에서 A로
   `status`가 tentative 조기승격돼도, 이 바깥 게이트가 여전히 prob>0.5만
   보고 막아버려서 **radarState.leadOne엔 A의 효과가 전혀 반영이 안 되는
   상태**였음(크래시는 아니고 A가 유명무실한 논리버그).

**조치**: 바깥 게이트를 `lead_msg.prob > .5` 중복체크 대신
`self.vision_tracks[index].status`(같은 tick에 이미 update() 끝난 최신
상태, 정식경로+A 조기등록 경로 둘 다 자연스럽게 포함)로 교체.

**검증**: `sim_vision_track_ab.py`에 `scenario_outer_gate_propagation`
신규 추가(총 7건 PASS) — 구게이트로는 A-1과 동일 시나리오(8초 정지앞차
재현)에서 lead_dict가 한 번도 노출 안 됨(None) / 신게이트로는 프레임9
(≈0.45s)에 노출 확인, A가 실제로 최종 출력까지 전파되는지까지 검증.

**전달 및 push 완료**: `0002-58-3-A-outer-gate-fix.patch`를
`/mnt/user-data/outputs/`에 생성, base `ff50b03`(원격 HEAD) 위에서
`git am` 검증 + `py_compile` 통과 확인 후 전달. 사용자가 `C:\dev\ryu`에서
`git am` 적용 + `git push origin c3-ms-dev` 완료 확인 — `ff50b03..1145aea`.
원격 fetch로 게이트가 `self.vision_tracks[index].status`로 반영됐음과
`py_compile` 통과를 재확인함.

**다음(최우선)**: 실차 드라이브 검증 — 이 후속수정으로 A(조기등록)가
처음으로 실제 동작하게 됨. 특히:
1. 오탐지 여부 — 복잡한 배경(터널 입구/표지판/그림자 등)에서 없는
   리드를 조기등록해 불필요 감속하는지
2. 이번 사례류(산길 정체 진입부) 재현 시 검출이 실제로 앞당겨지는지
3. B 보정이 정상 접근 상황에서 승차감을 해치지 않는지

## 58차 3번 (설계·구현·합성검증·패치 적용/push 완료, 실차검증 대기) — 정지앞차 미인식/과소반응 (A+B)

**배경**: 사용자가 산길 정체구간 정지앞차 미인식으로 브레이크 개입한
실제 사례(`정지차량_미인식.zip`+`260823_161743_clip.mp4`, route
`a3a55cb808` seg10, t=4301~4312) 제보. qcamera 10프레임 대조로 t=4302부터
이미 화면에 차량/정체군이 또렷이 보임을 확인.

**확인된 사실**:
1. t=4301.21~4309.30(8.1초) `leadStatus=False`인데도 vEgo 28.6->31.4m/s로
   계속 가속(순항목표 121km/h). 프레임상 t=4302부터 전방 차량 명백히 보임.
2. t=4309.30 최초 검출, `dRel=123.7m, leadModelProb=0.53`(0.5 턱걸이),
   `radar=False`(비전단독).
3. t=4309.30~4311.80 비전단독 구간 vLead 27->14m/s로 완만 감소로 보였으나,
   t=4311.85 레이더 락온 순간 14.1->4.88m/s로 실제값 급락(비전 낙관추정).

**원인 코드 특정** (`radard.py` `VisionTrack.update()`):
- (등록) `if self.prob > .5: ... else: self.reset()` — modelV2 prob이
  0.5를 못 넘으면 트랙 자체가 생성 안 됨(화면에 보여도 시스템엔 "없음").
- (신뢰) `if self.cnt<CNT_GATE or self.prob<PROB_GATE(0.70): vRel=
  lead_v_rel_pred`(모델예측 그대로, 실측 dRel미분 블렌딩 전혀 없음) —
  prob 0.5~0.70 구간은 100% 순수 모델예측에만 의존.

**사용자 결정**: A(등록문턱 완화)+B(저확신구간 안전측 보정) 동시 진행.

**구현** (`radard.py`, 로컬 커밋 `ccec041`, base `a35a39f`):
- 신규 상수: `VISION_TRACK_TENTATIVE_PROB_GATE=0.35`/
  `VISION_TRACK_TENTATIVE_CNT_GATE=10`(0.5s)/
  `VISION_TRACK_TENTATIVE_DREL_JITTER=8.0`/`VISION_TRACK_SAFETY_MIN_CNT=2`.
- **A**: prob가 0.35~0.5 구간에서 같은 위치(dRel jitter<=8m)로
  10프레임(0.5s) 연속 잡히면 `tentative_cnt` 누적 -> 정식문턱(0.5) 못
  넘어도 조기 등록(`register_ok`). dRel 튀면(다른 물체 추정) 즉시 리셋.
- **B**: prob<0.70(모델예측만 쓰는 구간)이라도 dRel 실측 이력 2프레임+
  쌓이면, 실측기반 vLead가 모델예측보다 더 위험(작음)할 때만 `min()`
  으로 안전측 보정 — 58차1번 v_lead 안전클램프와 동일 원칙(완화 방향
  없음, 모델이 맞을 땐 전혀 개입 안 함).

**합성검증** (`devnotes/toolkit/sim_vision_track_ab.py` 신규, 6개
시나리오 전부 PASS — VisionTrack.update() 핵심분기 순수함수 재현,
capnp 의존으로 radard.py 직접 import 불가라 기존 세션들과 동일 방식):
- A-1: prob=0.42 고정+안정적 접근 8초 -> 프레임9(≈0.45s)에 조기등록 확인.
- A-2: prob=0.2 고정(tentative문턱 밑) -> 200프레임간 미등록 유지(회귀 없음).
- A-3: prob=0.42지만 dRel 매프레임 요동(다른 물체 오인 재현) -> 승격 안 됨.
- B-1: 이번 실사례 근사 수치(dRel=123.7m, vEgo=31, 모델 27->14/실제
  27->4 근사) 재현 -> 모델예측보다 낮게(안전측) 보정되는 프레임 확인.
- B-2: 모델예측=실측 완전 일치(정상상황) -> 보정 개입 없음(오차 0).
- 고prob회귀: prob=0.85(기존 정상등록 경로) -> A/B 둘 다 미개입, 기존과
  동일 동작 유지.

**전달**: `0001-58-3-A-tentative-B.patch`를 `/mnt/user-data/outputs/`에
생성, `git am` verify(base `a35a39f`) + `py_compile` 통과 확인 후 전달.
**사용자가 `C:\dev\ryu`에서 `git am` 적용 + `git push origin c3-ms-dev`
완료 확인** — `a35a39f..ff50b03`.

**다음(최우선)**: 실차 드라이브 검증 — (1) 이번 사례류(산길 정체 진입부)
재현 시 검출이 실제로 앞당겨지는지, (2) A로 인한 오탐지(존재하지 않는
리드를 조기등록해 불필요 감속) 발생 여부 — 특히 시각적으로 복잡한
배경(터널 입구/표지판/그림자 등)에서 회귀 확인 필수, (3) B 보정이
정상 접근 상황에서 승차감을 해치지 않는지(합성검증상 무간섭 확인했으나
실제 노이즈 특성은 다를 수 있음).


## 58차 2번 계속4 (체크포인트 — 저속+강한감속 게이트 설계·구현·합성검증·패치 전달 완료, 실차검증 대기) — 정체구간 붕끗

**배경**: 직전 체크포인트("58차 2번 계속3", 아래)에서 원 가설(정체 중
danger override 오발동) 기각 후, 조치 후보 (a)GATE_NONE 상향 /
(b)앞차 실측 감속 크기 기반 보조 weight 경로 / (c)정체 한정 프레이밍
폐기 중 사용자와 논의해 **(b) 채택**, 이어서 "저속구간(정체) 한정,
그 외 구간엔 영향 없어야 함"이라는 사용자 요구로 범위를 더 좁혀
**v_ego 게이트(<=30km/h) + a_lead 문턱(<=-1.8m/s²)** 조합으로 설계
확정 → 구현 → 합성검증 → 패치 전달까지 완료.

**구현**: `long_mpc.py`에 `LOW_SPEED_STRONG_DECEL_V_EGO_GATE=30/3.6`
(m/s)/`LOW_SPEED_STRONG_DECEL_A_LEAD_THRESH=-1.8`(m/s²) 상수 추가.
`process_lead()`의 danger override 분기(`ttc_now <= LEAD_ACQ_TTC_
DANGER`)에 `or low_speed_strong_lead_decel`을 추가(`v_ego <= 게이트
and a_lead <= 문턱`) — 이 조건 성립 시 TTC 위치·rise-rate 제한과
무관하게 즉시 weight=1.0. 게이트 자체가 v_ego로 닫혀 있어 게이트 밖
(고속/일반 주행)에서는 새 분기가 원천적으로 안 열림 → patch 이전과
동작 100% 동일 보장.

**합성검증** (`devnotes/toolkit/sim_low_speed_decel.py`, 4개 시나리오
전부 PASS, `process_lead()`의 weight 계산부만 순수함수로 재현한
로직단위 검증 — 실제 acados MPC 미거침):
- A. 고속 회귀: v_ego=25m/s 고정, TTC 6~12s 램프 구간 왕복 + a_lead
  강/완만 번갈아도 patch 전/후 weight 시퀀스 diff=0.
- B. 이벤트 재현: 저속(0→28.8km/h 재가속) + a_lead=-1.8 지속, min
  TTC≈3.33s(danger 2.5s 미발동, 실측 4.45s와 정합)로 구성 — unpatched는
  초반 weight=0(감쇠)→rise-rate(1.0/s) 한계에 걸려 몰아서 반영되는
  패턴 재현, patched는 전 구간 weight=1.0 고정(감쇠 자체가 없어짐,
  danger override 경로가 아니라 저속게이트 경로로 도달 확인).
- C. 오탐 방지: 저속이지만 a_lead=-0.5(threshold 미달) — 게이트 미개방,
  patch 전/후 diff=0.
- D. 경계 전이: v_ego가 게이트값을 여러 번 넘나들어도 예외 없이 동작,
  게이트 열린 프레임 전부 즉시 w=1.0.

**커밋/패치**: `c3-ms-dev` **origin push 완료** (`e17e078..a35a39f`, 로컬
`git am` 적용 커밋 해시는 `a35a39f`로 재기록됨 — 내용은 컨테이너 커밋
`6440fe9`와 동일). `git format-patch` → `verify-am` 브랜치에서 `git am`+
`py_compile` 통과 확인 →
`0001-long_mpc-danger-override-58-2.patch` `/mnt/user-data/outputs/`
전달 완료(`git am` 안내 포함).

**다음(최우선)**: **실차 드라이브 검증 대기** — (1) 이번 붕끗 이벤트와
같은 저속 재가속+앞차감속 상황에서 급가속->급감속 반전이 사라지는지,
(2) 고속/일반 주행에서 회귀(불필요한 개입) 없는지 확인. 통과 시 58차
3번(정지앞차 반응 강화)으로 진행.


## 58차 2번 계속3 (체크포인트 — rlog 대조로 이벤트 정량 확인, **원 가설(danger override) 기각, 방향 재검토 필요**) — 정체구간 붕끗

사용자가 clip1/clip2와 같은 구간 rlog(route `a3a55cb808` seg11/12)를
제공 → clip2의 급감속 이벤트를 route time t=4420~4423(seg12)에서 정확히
특정. **핵심**: min TTC=4.45s로 danger override(≤2.5s) 문턱과 무관함을
확인 — 원 설계 가설(정체 중 danger override 오발동) 기각. 대신
`ttc_accel_weight()`의 GATE_NONE(6.0s)~GATE_FULL(12.0s) 램프 구간에서
앞차가 이미 강하게 감속 중(aLeadK 근사치 -1.5~-2.0m/s²대, ego 가속
중이던 시점부터)인데도 weight가 낮아 감쇠되다가, TTC가 6.0s를 넘는
순간 감쇠돼 있던 aLeadK가 1초 이내로 몰려 반영되며 붕끗 발생하는
패턴으로 재구성. dRel도 17~24m대로 "정체구간 짧은 dRel" 전제와 다름
— **정체구간 한정이 아니라 저속 추종 전반의 문제일 가능성.** 상세
수치/근거는 FINDINGS.md "58차 2번 계속3" 항목 참고. 코드 변경 없음.

**다음 최우선(사용자 방향 결정 대기, 코딩 착수 전)**: FINDINGS.md
"58차 2번 계속3 다음" 항목의 조치 후보 (a)GATE_NONE 상향 / (b)앞차
실측 감속 크기 기반 보조 weight 경로 / (c) 정체 한정 프레이밍 폐기
여부 등 결정 필요.


## 58차 2번 계속2 (체크포인트 — 화면녹화 영상 2건 제보, 정성적 일치 확인·정량 데이터 요청 대기) — 정체구간 붕끗

**배경**: 직전 체크포인트("58차 2번 계속", 아래)에서 로그 2개로는 "정체
중 danger override 오발동" 패턴을 확증 못해 사용자 추가 제보 대기
상태였음. 사용자가 화면녹화 clip 2개(`260823_161836_clip.mp4`/
`260823_161929_clip.mp4`, 각 ~30초, CarrotWeb 오버레이 포함)를 "붕끗이
명확한 영상"으로 업로드 → ffmpeg로 프레임 추출(seek 방식, 0.2~1초
간격)해 화면 판독으로 분석.

**clip2(161929) 상세 타임라인(정성적 판독, 초 단위는 영상 재생시각 기준)**:
- t=0~7s: 정차(속도 0, 정체 대기열)
- t=7~23s: 재출발 가속, 0→33km/h. 이 구간 내내 리드박스 dRel(빨간
  숫자)가 24m대→10m대까지 지속 감소(선행차와 계속 closing 유지 —
  정체 중 짧은 dRel 상황과 일치).
- **t≈23s 부근**: 화면 상단 "1.Accel (Y:a_ego, G:a_target, O:a_out)"
  그래프에서 세 선이 함께 급격히 위로 튀었다가 즉시 무너지는
  spike-crash 패턴 뚜렷이 관찰됨(0.2초 간격 프레임 다수로 재확인).
- t=23~29s: 실제 속도가 33→7km/h로 약 6초 만에 급감속(직전 재가속
  구간과 대비되는 급격한 반전).

**clip1(161836)**: 정체 접근 중 32→0km/h 감속 구간, 그래프에도 spike
패턴이 보이나 영상 시작(t=0) 이전 이벤트의 잔상일 가능성이 있어
독자적 확증으로는 보류(clip2만큼 명확한 대응관계는 아님).

**판단**: 영상에서 관찰된 "재출발 가속 중 dRel 지속 감소 → 급격한
accel spike-crash → 속도 급락" 패턴은 58차 2번 설계 가설(정체 중
짧은 dRel+지속 closing이 danger override(TTC<=2.5s)를 오발동시켜
rise-rate 제한까지 우회하고 즉시 weight=1.0으로 튐)과 **정성적으로
일치**. 단, 영상만으로는 (a) 정확한 TTC/aEgo/vRel 수치, (b) danger
override 플래그(실제로 그 경로였는지, 아니면 다른 메커니즘인지)를
확인할 수 없음 — 58차 2번 계속에서 이미 지적된 한계와 동일.

**다음(사용자 제보 대기, 최우선)**: 이 두 clip과 같은 주행의 rlog/
route(가능하면 qcamera 포함, 시각 16:18~16:19경) 재업로드 요청 —
clip2 t≈23s(재가속 후 급감속 시작 시점) 부근을 route 내에서 특정해
TTC/dRel/vRel/aEgo/danger override 발동 여부를 수치로 대조 확인할
것. 확증되면 58차 2번 구현(congestion 상태 추적 + danger override
closing 조건 추가) 착수. 코드 변경 없음(영상 분석만).


## 58차 2번 계속 (체크포인트 — 실차확인 로그 분석 착수, 구현 전 설계 검증 단계) — 정체구간 붕끗

**배경**: 58차 2번 설계(아래 원본 섹션)는 확정됐으나, 사용자가 구현
착수 전에 "정체구간_붕끽.zip"(실제 붕끗 발생 로그, qcamera 포함)을
업로드 → 실제 로그로 설계 전제(짧은 dRel + 완만한 closing → TTC
danger override 오발동)부터 검증하기로 함. 실차확인(패치 적용 후
검증)은 이후로 미루고, 지금은 "패치 이전 로그로 근본원인 자체를
실측 확인"하는 단계.

**로그**: 2개 route 업로드, route ID 다름 — 분리 추출.
- `route_98fe04a961`(3세그 0~2, 181.8s, avg 8.2km/h, cruise_ratio 71.9%)
- `route_a3a55cb808`(seg11~14 중 **seg14는 zstd 손상**(기존에도 알려진
  손상 파일) — seg11~13만 사용, 179.8s, avg 7.4km/h, cruise_ratio 93.1%)
- 둘 다 CSV 추출 완료(`/home/claude/work/congestion/route_*.csv`).

**1차 결과 (진행 중, 결론 아님)**:
1. 정차(v<0.3m/s) 진입 반복 횟수: route1 3회/route2 7회 — 두 route
   다 "정지-출발 반복" 정체 패턴 구조적으로 확인됨(설계 전제 1 충족).
2. `ttc_danger_events()`(TTC<=2.5s)로 danger override 발동 후보 스캔 —
   각 route 1건씩만 검출:
   - route1 t=60.40: dRel=6.52m, vRel=-2.79m/s, vEgo≈0 — **단, 이 구간은
     brakePressed=True 지속(운전자가 브레이크 밟고 정차 유지 중)이라
     cruiseEnabled 여부 미확인, ADAS 개입 여부 불명확. aEgo도 거의
     0으로 "붕끗" 징후 안 보임 — 이 이벤트가 사용자가 말한 증상과
     같은 건지 의심.**
   - route2 t=4316.31: dRel=11.60m, vRel=-4.70m/s, vEgo=6.46m/s(23km/h) —
     vRel이 -4.7m/s로 "완만한 closing"이라 보기엔 다소 큼(설계 문서의
     "완만한 closing" 전제와는 약간 어긋날 수 있음, qcamera 확인 필요).
3. 단순 jerk(|Δa_ego/Δt|>=1.5) 스캔은 route1 78건/route2 284건으로
   과다검출 — 대부분 정상적인 정지-출발/추종 가감속(src=vturn 등)이라
   섞여 있어 "붕끗" 특이 패턴만 못 걸러냄. **정체구간 한정 + TTC
   danger override 연관 필터 없이는 노이즈 지배적** → 범용 jerk
   스캔이 아니라 58차 2번 설계 그대로(정체 상태 추적 + danger override
   시점) 전용 스캐너가 필요함이 재확인됨.

**판단(갱신, (a) 완료)**: `congestion_stop_launch_lurch_scan()` 신규
구현·검증 완료(합성 시나리오 3건 통과, `analysis_helpers.py`/
README.md/CHANGELOG.md 동기화). 실제 두 route에 적용:
- 엄격 기준(window 60s, 정체판정 정차 2회 이상, 완만한 접근
  |vRel|<3.0m/s): **0건**(route1/route2 둘 다).
- 완화 기준(정차 1회만으로도 정체로 인정, window 90s): route1에서
  **1건**(t=60.40, 앞서 발견한 그 이벤트) — 그러나 **cruiseEnabled=
  False**(운전자가 브레이크 밟고 수동 정차 중, ADAS 종방향 제어 로직
  자체가 개입하지 않는 구간)로 확인, `post_aEgo_drop`도 0.001로
  사실상 무변화 — **ADAS danger override와 무관한 이벤트로 판정**.
  route2는 완화 기준으로도 0건.

**결론**: 이번에 업로드된 두 로그(각 ~3분, 정체구간)에서는 58차
2번이 겨냥한 "정체 중 danger override 오발동으로 인한 붕끗" 패턴의
ADAS 개입 사례를 확증하지 못함. qcamera 대조할 만한 명확한 후보가
없어 (b) 단계(영상 대조)는 보류 — **사용자에게 상황 보고 후 다음
방향 결정 필요**(예: 사용자가 실제 "붕끗"을 체감한 정확한 시각/구간
추가 제보, 또는 더 긴/다른 정체구간 로그 재업로드, 또는 파라미터를
더 완화해서 재스캔, 또는 danger override 외 다른 메커니즘 재검토).

**코드 변경**: `devnotes/toolkit/analysis_helpers.py`(신규 함수)/
`README.md`/`CHANGELOG.md`만 변경. **ryu 코드는 여전히 미변경**(2번
구현은 설계 확정 상태 그대로, 이번 로그로는 착수 판단 근거 부족).


## 58차 2번 (설계 확정, 구현 착수 전) — 정체구간 붕끗 완화

**증상**: 정체구간에서 앞차 정지-출발 반복 시 자차가 "붕끗"(급격히
반응했다 풀렸다) 느낌. 사용자 진단: "선행차 변화에 민감대응 코딩
영향, 정체구간 한정 별도 로직 필요."

**원인 확정**: `LAUNCH_BYPASS_STOP_V_EGO(0.3)/EXIT_V_EGO(5.0)`(45차)는
"정차→출발" 단발 이벤트만 상태로 관리 -- 재출발 중 v_ego가 5.0m/s를
잠깐 넘으면 즉시 38/39차 TTC 기반 로직(`ttc_accel_weight`)으로 복귀.
정체구간은 구조적으로 dRel(차간거리)이 짧아, 앞차의 정상적인 미세
감속에도 TTC=dRel/closing이 쉽게 LEAD_ACQ_TTC_DANGER(2.5s) 밑으로
떨어짐 -- 이 danger override는 rise-rate 제한(39차)까지 전부 우회하고
즉시 weight=1.0(무감쇠)로 튐. 정체구간의 정상적인 정지-출발 흐름을
"실제위험"으로 오판해 반응하는 것이 붕끗의 root cause로 판단.

**설계**: "정체(congestion)" 상태를 별도로 추적 -- 최근 시간창
(CONGESTION_WINDOW_S) 이내 정차(v_ego<STOP_V_EGO 진입) 횟수가
CONGESTION_STOP_COUNT_THRESH 이상이면 congestion_active=True.
정체 중엔 danger override 조건에 "TTC 짧음" 단독이 아니라 "실제
closing 속도도 유의미하게 큼"(CONGESTION_MIN_CLOSING_FOR_DANGER)을
추가로 요구 -- 정체 중 정상적인 짧은 dRel + 완만한 closing으로는
더 이상 즉시 무감쇠로 튀지 않고, 진짜 급접근(closing 큼)은 여전히
즉시 반응. congestion_active는 속도가 CONGESTION_EXIT_SPEED 이상을
CONGESTION_EXIT_SUSTAIN_S 이상 유지하면 해제(고속 정상주행 복귀 판단).

**안전 설계 원칙(중요)**: 정체 중이라고 반응을 무조건 죽이는 게 아니라
"TTC 단독 판정"에서 "TTC + closing 속도 동시 판정"으로 기준을
강화하는 것 -- 실제 급정지/cut-in처럼 closing 속도 자체가 큰 위험은
정체 중에도 그대로 즉시 반응.

**다음(같은 세션에서 이어서 구현)**: 위 설계대로 long_mpc.py에
congestion 상태 추적(deque 기반 정차 이력) + danger override 조건
수정 구현 → 합성검증 → patch 작성 → 사용자 전달.


## 58차 1번 (완료 — 패치 적용/push 완료, 실차 검증 대기) — 카메라 감속 강화
FINDINGS.md/PARAMS_REGISTRY.md/LAST_ANALYZED.md 58차 1번 항목 참고.
요약: `radard.py` VisionTrack 게이트 완화 + `long_mpc.py` v_lead 직접
보정(핵심) 2건 패치, 사용자 로컬 origin 동기화(30개+ 커밋 뒤처짐 발견,
reset --hard로 정리) 거쳐 `git am`+push 완료(`f94a7d2..e17e078`).
**다음 메시지 최우선**: 실차 검증 대기 중 — 사용자가 검증 결과
가져오면 확인 후 devnotes 갱신, 통과되면 58차 2번(정체구간 붕끽
완화)으로 진행. 58차 전체 순서는 아래 "58차" 섹션(순서 확정) 참고.


## 58차 — 사용자 지시 코딩 작업 순서 확정 (착수: 1번부터)
사용자가 4개 코딩 과제와 순서를 확정 지시함. **이 순서 그대로 진행,
임의 순서 변경 금지.**

1. **[착수 예정] 카메라(vision) 인식 감속이 레이더 대비 약함 — 레이더
   인식 수준으로 강화.** 현재 vision-only 상황(레이더 미락온)에서의
   감속 반응을 레이더 락온 시 반응 수준에 맞춰 강하게. 기존
   frac_rate 게이트(33차, GATE_CAUTION=-2.2/GATE_DANGER=-5.0)/TTC
   damping(38/39차)이 관련 로직 — 이번 요청이 이걸 완화하는 방향인지
   아니면 별도 경로(vision v_lead를 MPC에 더 직접 반영하는 25차
   "4번안"류) 추가인지는 코드 리딩 후 설계 확정 필요.
2. 정체구간(정지-출발-재정차 반복) 시 선행차 변화에 민감 반응해
   "붕끽" 느낌 — **정체구간 한정 별도 로직 적용 검토.** 45차 launch
   bypass(LAUNCH_BYPASS_STOP_V_EGO/EXIT_V_EGO)/39차 rise-rate와 관련
   가능성 — 정체구간(반복 정지-출발) 판정 방식부터 설계 필요.
3. 정지앞차에 대한 반응 강화 — 2번(정체구간 붕끽) 완화와 상충하지
   않는 범위에서 설계할 것(사용자가 "민감 반응 완화"와 "반응 강화"를
   동시에 요청 — 정체구간 vs 정지앞차 단일 이벤트를 구분해서
   접근해야 함, 혼동 주의).
4. 곡선구간 미리감속(사전감속) — 50차 model 게이트 재설계
   (abs(vturn_speed)<120 제거) 이후 미검증 상태였던 "직선 구간 오탐
   여부"와 함께, 사전감속 자체가 부족한지 재확인 후 진행.

**다음 세션(또는 다음 메시지) 최우선**: 1번부터 코드 리딩 → 설계 →
패치 작성 → 사용자 승인 → `C:\dev\patch\` 전달.


## 57차 — 56차 재업로드 dataset "qcamera영상도 대조분석" 요청 처리, 저각 역광 신규 후보 발견
56차와 동일 9개 route 재업로드받아(전체 재추출, `a3a55cb808` seg14
zstd 손상 재확인 후 제외) 저크 이상 패턴을 |jerk| 크기 기준 상위 6건
전부 qcamera 프레임 대조 완료(상세는 FINDINGS.md 57차 항목 참고).
**핵심 결과**: 1건은 56차까지의 "옆차선 대형차량 근접" 메커니즘과
일치 재확인. **3건(전부 `27b2980cda` route, 18:01~18:21 일몰 시간대)
은 저각 석양 역광/명암 급전환과 시각적으로 일치 — 신규 제3 메커니즘
후보(NEEDS_VALIDATION, 표본 3건뿐).** 1건은 원인 미상, 1건은 실제
감속이 타당한 정상 상황으로 배제. 코드 변경 없음(분석만).
**다음 세션(또는 다음 메시지) 최우선**:
1. 56차 WIP에서 이월된 "저크 이상 6건 코드리뷰"(옆차선 SCC 폴백
   dPath 게이트 잔존 여부, `radard.py get_lead()`/
   `Track.get_RadarState()`)는 여전히 미착수 — 계속 최우선 유지.
2. **[신규]** 저각 역광 가설 검증 — 다른 일출/일몰 시간대 로그
   확보 시 같은 패턴(vision 저크가 태양 방위각/고도와 상관되는지)
   재현 여부 확인. 표본이 늘면 `curve_lead_dRel_jump_consistency`류
   일관성 체크에 태양 역광 필터도 추가 검토.
3. `a3a55cb808` route 저크 105건(56차부터 대기) 원인 미검증, 계속
   저우선 유지.

- 저장 시각: 2026-08-23 (56차, 완료 — 코드 변경 없음, 분석만) 대량
  실주행 로그 9개 route(15:53~19:00 약 3시간, 189,336행, 각 1개
  boot session/10~20세그, `a3a55cb808`는 seg14 zstd 손상으로 seg0~13만
  사용) 업로드받아 55차와 동일 5개 항목 재분석 완료. `stopped_lead_
  decel_events`/`launch_after_stop_events`는 55차 work/ 스크래치가
  컨테이너 리셋으로 소실돼 devnotes 기록 기반으로 역재현
  (`work/five_item_scan.py`, toolkit 미편입).
  **핵심 결과**: 1)저반응 잔여패턴 뚜렷한 재현 없음(경계사례 1건뿐,
  저우선 유지). 2)정지앞차 26건 중 15건 순수ADAS 클린, 11건은
  운전자개입 혼합(개별검증 안함). 3)정지후 재출발 6건 전부
  driver_gas_ratio=0.0 매끈(45차 launch bypass 정상). **4)[중요,
  qcamera 대조 완료]** 55차 최우선이던 route1 seg18 저크 이상패턴
  (leadVRel≈0인데 큰 저크)이 4건 추가 재현(표본 2→6건). 3건
  (src=road/section)은 `verify_and_extract_frames.py`로 프레임
  대조한 결과 **저크 순간 전부 옆차선에 대형차량(SUV 2/탱크로리 1)이
  근접 밀착 주행 중이었음을 영상으로 확인** — 37차 "SCC 단일점
  락온이 옆차선 차량을 미검증 채택" 문제와 동일 메커니즘으로 추정
  (37차는 급감속 사례, 이번은 가속(+) 방향 저크라는 차이). 나머지
  1건(src=vturn)은 영상 확인 결과 진짜 커브 구간(옆차선 차량 없음)
  으로 완전 별개, 패턴에서 제외. 5)곡선
  위반 3건(표본 적음, 이번 로그가 커브 적은 시내 위주 추정), curve_exit
  0건(48차 결론 재확인). 안전지표(harsh_brake/ttc_danger) 전부 클린.
  상세는 FINDINGS.md 56차 항목 참고.
  **다음 세션(또는 다음 메시지) 최우선**:
  1. 4번 저크 이상 6건(55차 2건+56차 4건) **코드리뷰 착수** — "37차
     옆차선 SCC 폴백 문제가 37차 계속3 dPath 게이트 패치 적용 후에도
     가속 방향으로 잔존하는지" 중심으로 `radard.py get_lead()`/
     `Track.get_RadarState()` 재확인(위 FINDINGS.md 56차 "다음 세션
     최우선" 1번 참고).
  2. 51/54차 vturn apex lag 이슈는 이번 로그 표본이 적어 진전 없음,
     계속 열린 상태로 유지.
  3. `a3a55cb808` route 저크 105건(다른 route 대비 압도적) 원인
     미검증 — 저우선, 코드리뷰 이후 확인.


- 저장 시각: 2026-08-23 (55차, 체크포인트 — 코드 변경 없음, 분석만.
  사용자가 신규 로그 3개(route1=`a6e5df336a` x19seg/route2=`cf48b52c98`
  x20seg/route3=`7472041957` x3seg, HEAD `f94a7d2` 기준) 업로드해
  5개 항목(1.카메라인식 감속/2.정지앞차 감속/3.정지후 재출발/4.레이더
  락온 민감반응/5.곡선구간 감속) 순서대로 분석 요청 → 전부 완료,
  상세는 FINDINGS.md 55차 항목 참고. **route3 seg2는 rlog.zst zstd
  프레임 손상(녹화 중 절단 추정)으로 분석 제외(seg0/1만 사용).**
  요약: 1)frac_rate 게이트 정상 동작 재확인(52건 크로스오버 중 대부분
  레이더 락온 전 감속 개시), 저반응 잔여패턴 2건(41/42차류, 저우선).
  2)정지앞차 추종 5건 전부 클린. 3)정지후 재출발 3건 전부 매끈
  (45차 launch bypass 패치 정상 동작으로 추정). 4)레이더락온 저크
  36건 중 34건은 leadVRel 변화로 설명 가능, **예외 2건(route1 seg18,
  leadVRel≈0인데 큰 +저크)** 원인 미상 — 다음 세션 코드리뷰 우선 확인
  후보. 5)turn_speed_violations 23건(51/54차 vturn apex lag 이슈의
  연장, 신규 아님), curve_exit_no_accel_v4 3건(48차 결론과 동일하게
  vCruiseCluster 캡 문제, 버그 아님).
  **사용자가 "코딩검토는 분석이 다 완료된 이후"라고 명시 — 5개 항목
  분석은 이번 세션에서 완료됐으므로, 다음 메시지/세션에서 코드 리뷰
  단계로 전환 가능.**
  **다음 세션(또는 다음 메시지) 최우선**:
  1. route1 seg18 t=1195.102/1242.70 저크 이상 2건 — carrot_serv.py/
     long_mpc.py 코드 리딩으로 leadVRel 무관 저크의 원인(소스 전환?
     launch bypass exit? rise-rate 로직?) 특정.
  2. 4)에서 발견된 저반응 잔여패턴 2건(route1 seg2/route2 seg0)도
     41/42차처럼 qcamera 프레임 대조 검토(우선순위는 낮음).
  3. route2 harsh_brake 75건/cut-in 36건 운전자개입 여부 미검증 —
     정체구간 추정이나 확정 아님, 필요 시 개별 확인.
  4. 51/54차 turn_speed_violation(vturn apex lag) 이슈는 이번 로그로도
     재현됐으나 패치 방향은 여전히 미확정 상태(54차 WIP 그대로 유효) —
     사용자가 방향 결정 시 그쪽 스레드로 복귀.


- 저장 시각: 2026-08-23 (54차, 체크포인트 — 코드 변경 없음(ryu),
  분석 스크립트(work/ 스크래치)만 신규) route4(`d45a15f8fc`) 재업로드
  받아 53차 `replay_lookahead_v1.py`의 **실제 rlog 첫 검증 완료**.
  idx10 개별 정밀 대조 + 24건 전체 일반화 스캔(`work/lookahead_
  generalization_scan.py` 신규) 수행. **결론**: lookahead horizon
  가설(ii)이 지나친 단순화였음 확인 — raw(필터 이전) 신호 자체도
  이벤트 근접(수 초 전)까지는 하강 없음(이론상 8.0s horizon보다 훨씬
  늦게 감지, 원거리 modelV2 궤적/곡률 예측 신뢰도 문제로 추정) +
  filtered 최종출력은 raw보다 평균 2초+(18건 중 최대 8.6초) 추가로
  더 늦게 반응(RC 시정수 0.15s보다 훨씬 큰 누적지연 — 매 프레임
  갱신되는 argmin 목표를 계속 뒤쫓는 구조적 문제로 추정). (a)모델
  원거리 감지 vs (b)필터 누적지연, 둘 중 (b)가 개입 여지 크고 리스크
  낮은 후보로 판단되나 **패치 방향은 아직 미확정**. 상세는 FINDINGS.md
  54차 항목 참고.
  **[한계]** idx10 자체는 threshold 매칭 로직 이슈로 lag 자동계산
  nan(수동 대조로는 ~0.8s 확인) — 스크립트 정밀화 필요.
  **다음 세션 최우선**:
  1. **패치 방향 결정 필요(사용자와 협의)** — 필터 지연 완화((b)) 쪽에
     무게, 하지만 확정 아님. 방향 정해지면 시뮬레이션 → 패치 순서.
  2. `lookahead_generalization_scan.py` threshold 매칭 정밀화(idx10
     nan 해결) 후 toolkit 정식 편입 검토.
  3. route2 apex-vs-gap 미확정 5건 개별 재검증(route2 로그 재업로드
     대기, 계속 이월 중).


- 저장 시각: 2026-08-23 (53차, 체크포인트 — 코드 변경 없음(ryu),
  toolkit 신규 스크립트 작성+로직 단위 검증 완료) 52차 최우선 과제
  "lookahead horizon 가설 직접 검증용 replay 스크립트"를
  `toolkit/replay_lookahead_v1.py`로 작성 완료. `carrot_man.vturn_speed()`
  (HEAD `f94a7d2`)의 필터 적용 전(raw) argmin required_speed_kph를
  modelV2 원본(orientationRate.z/velocity.x/position.x)에서 직접
  재현하도록 구현 — `extract_log.py`의 `vTurnSpeed`(필터 후 최종값)만
  으로는 "필터가 늦춘 것"과 "lookahead_horizon_s(8.0s) 안에 애초에
  급조임 지점이 안 보였던 것"을 구분 못 했던 한계를 해소하는 게 목적.
  **검증**: 합성 시나리오 2건(원거리 급커브 raw_kph<100 확인/완전직선
  raw_kph>200 확인) + 저역통과 1스텝 방향성 검증 통과, cereal/log.capnp
  필드 경로(orientationRate.z/velocity.x/position.x = XYZTData) 직접 대조
  확인. toolkit/README.md/CHANGELOG.md 동기화 완료.
  **한계(다음 세션 확인 시 유의)**: modelV2 이벤트(~20Hz)를 carrot_man
  20Hz 틱 1개로 근사(완전히 같은 타이밍 아님, 49차와 동일 전제).
  AutoCurveSpeedFactor/Aggressiveness 사용자 실제 런타임값 미기록이라
  코드 기본값(1.2/1.0)을 기본 사용(--factor/--aggr로 override 가능).
  **다음 세션 최우선(변경 없음, 이번 세션이 그 첫 단계만 완료)**:
  1. **실제 rlog로 첫 검증** — route4(d45a15f8fc, idx10 포함) 또는 동급
     급조임 커브 raw route를 재업로드받아 `replay_lookahead_v1.py` 실행 →
     raw_kph가 실제 이벤트 몇 초 전부터 낮게 나오기 시작하는지 확인.
     raw_kph가 오래전부터 낮았는데 filtered만 늦었다면 -> 필터(decel_rc)
     원인. raw_kph 자체가 이벤트 직전까지 높다가 급락했다면 -> 가설(ii)
     (lookahead_horizon_s 부족 또는 모델의 원거리 곡률 예측 정확도 부족)
     직접 확증.
  2. route2 apex-vs-gap 미확정 5건 개별 재검증 (52차에서 이월).


- 저장 시각: 2026-08-23 (52차 계속2, 체크포인트3 — 코드 변경 없음,
  분석만) **[사고] 다른 계정 세션이 46차 시점 오래된 로컬본으로
  FINDINGS.md/WIP.md를 덮어씀(989줄 유실) → 이 컨테이너의 로컬 파일이
  cf3e9d4 상태 그대로 보존돼 있어 그대로 재push로 완전 복구함(커밋
  7198e9b). 이후 작업 재개.**
  route4 idx10(이례적으로 강한 감속 이벤트) 개별 확인 완료 —
  데이터 글리치 아니고 **진짜 극단적 급커브(desiredCurvature 최대
  0.052, route1의 약 18배)**로 확정. 시스템이 설계 감속률(1.2m/s²)의
  거의 3배(-3.45m/s²)까지 밟아가며 대응했지만 여전히 목표속도 못
  따라잡음 — lookahead horizon 가설(ii)이 4개 route 교차검증으로
  계속 강화되는 중.
  **다음 세션 최우선(변경 없음)**:
  1. lookahead horizon 가설 직접 검증용 replay 스크립트 작성 —
     modelV2 raw required_speed_kph를 오버슈트 8초 전부터 재현.
     이번 세션까지 근거 누적으로 최우선 격상.
  2. route2 apex-vs-gap 미확정 5건 개별 재검증.
  3. (완료) route4 idx10 qcamera 시각 검증 — 산간 급커브(관문 앞
     헤어핀) 영상으로 100% 확증, 데이터 이상 가능성 배제.

- 저장 시각: 2026-08-23 (52차 계속, 체크포인트2 — 코드 변경 없음,
  분석만) 52차 다음과제 3개 중 (1)(3) 완료.
  **(1) route2 apex-vs-gap 재분류**: 매칭 성공 11/16건에서 최대초과
  시점이 조향각 정점보다 0.3~1.75초 먼저 발생(46차 79%/1.26초 결론과
  일관) — "정점에서만 못 따라감"이 아니라 "진입중 이미 벌어짐" 쪽
  확정적. 5건은 인접 커브 매칭 오류로 미확정.
  **(3) route4(d45a15f8fc)/route9(280302e8ed) 전체 재업로드분 재스캔**:
  route4 **24건**(1건 운전자개입 제외, 23건 순수ADAS, over 2.2~15.1kph)
  — **47차 "v3=1건" 결론이 단위버그로 인한 false negative였음 확정**.
  route9는 0건(기존 클린 결론 유지). route4 23건 중 13건(57%)도
  route2(75%)와 유사하게 vturn_decel_rate(1.2m/s²) 100%+ 반응 중에도
  못 따라잡는 패턴 재현 — **단일 route 우연 아니라 일반적 패턴으로
  격상**. **[개별확인 필요]** route4 idx10(over=13.3kph, dur=6.6s,
  aEgo_min=-3.45m/s²=설계값288%/물리클램프173%) 이례적으로 강한 감속,
  다른 이벤트와 성격 다를 가능성 — 다음 세션 프레임 대조 우선순위.
  PARAMS_REGISTRY.md의 vturn_lookahead_horizon_s 행을 52차 결과로
  전면 갱신함(21차 "overspeed 0건" 결론 완전 폐기 명시).
  **(2, 미착수)**: lookahead horizon 가설 직접 검증(raw required_speed
  재현) — modelV2 raw가 CSV에 없어 별도 replay 스크립트 필요, 다음
  세션 최우선으로 이월.
  **다음 세션 최우선**:
  1. route4 idx10 개별 프레임/qcamera 대조(이례적 강한 감속 성격 규명)
  2. lookahead horizon 가설(ii) 직접 검증용 replay 스크립트
     (49차 replay_vturn2.py 재활용 검토) — modelV2 raw required_speed_kph
     궤적을 오버슈트 시작 8초 전부터 재현해 "이미 급조임을 반영하고
     있었는지" 확인
  3. route2 apex-vs-gap 미확정 5건 개별 재검증(±2s 매칭 정밀화 또는
     수동 대조)


- 저장 시각: 2026-08-23 (50차 계속, **push 완료 확인** — 사용자가
  `git am` 적용 + `git push origin c3-ms-dev` 완료, 원격 커밋
  `f94a7d2`(로컬 `74e8e90`과 내용 동일, 메타데이터만 차이) 확인.
  LAST_ANALYZED.md 갱신 완료.) 사용자가 route1(`203f99d429` seg8) 로그를
  재업로드하며 "사전거리 부족해 보인다" 제보 → 46차 NEEDS_VALIDATION
  항목(model 게이트 `abs(vturn_speed)<120`이 vturn 원거리 불안정
  구간에서 model의 조기신호를 차단) 재확인. 사용자가 "정점에서 실제
  목표속도 도달하게 코딩" 요청해 패치 착수·완료.
  **변경 내용**: (1) `abs(vturn_speed)<120` 게이트 제거, (2) 트레일링
  판정을 min_recent+recover_margin(3.0km/h) 방식으로 재설계(carrot_serv.py,
  로컬 커밋 `74e8e90`). 시뮬레이션 검증: route1 사전감속 여유시간
  3초 미만→20초+로 확대 확인. **[다음 세션 최우선] 같은 로그 전수
  스캔 결과 model 참여율 98.8% — 진짜 직선 고속도로 로그가 없어
  오탐(불필요 감속) 위험 미검증. 사용자가 이 패치 적용 후 실차
  드라이브하면, 특히 확실한 직선 구간에서 속도 제약이 부당하게
  걸리는지부터 확인할 것.** 패치는
  `0001-carrot_serv-model-min_recent-margin-abs-vturn_speed-.patch`
  로 전달, `C:\dev\patch\`에 저장 후 `git am` 안내 완료. 상세는
  FINDINGS.md/PARAMS_REGISTRY.md 50차 항목 참고.

- 저장 시각: 2026-08-23 (50차, 체크포인트 — 코드 변경 없음, 분석만)
  "곡선 사전감속 구간 부족" 신규 가설을 route2(f3db6ca89d) 15건
  실측으로 검증 → **가시거리 부족 가설 기각**(전부 여유 있음, 최대
  -107m). `replay_vturn2.py`(work/ scratch)로 modelV2 raw에서
  필터-전 required_speed_kph 재현해 신호 자체 지연 없음도 확인.
  부수적으로 CSV `vTurnSpeed`가 src=model 전환 후 음수로 보이는 현상은
  **버그 아님으로 확정**(carrot_man.py `turnSpeed * curv_direction`
  — 좌/우회전 방향 부호 인코딩, min() 승자 판단엔 무관, 분석 시
  `src` 컬럼 기준으로만 판단할 것). 상세는 FINDINGS.md 50차 항목.
  **다음(사용자 결정 대기)**: (a) 46차 발견 `abs(vturn_speed)<120`
  model 게이트 가설 재조사, (b) 고속도로 장거리 진입 로그로 horizon
  부족 가설 재검증, (c) 다른 스레드 전환.

- 저장 시각: 2026-08-23 (49차, 체크포인트 — 코드 변경 없음, 관찰만.
  48차가 "탈출 후 무가속" 스레드를 종결한 직후, 사용자가 프레이밍을
  바꾼 새 가설 2개 제기: (A) "탈출후"가 아니라 "탈출전(정점 직후,
  아직 완전 직선 아닌 시점)"부터 가속해야 하는 것 아니냐, (B) 과속
  방지턱처럼 최대 곡률 지점(apex)을 지나는 순간 속도 제약을 즉시
  원복하는 방식이 더 맞지 않냐. `vturn_speed()`(carrot_man.py L953)
  재확인 결과 **(A)/(B) 둘 다 이미 현재 설계 의도 자체임을 확인**:
  - lookahead 구간 내 모든 지점에 방지턱과 동일한 `v_i^2=v_f^2+2ad`
    공식을 벡터화 적용 후 `argmin`(가장 엄격한 지점)을 최종 제약으로
    삼는 구조라, "진입/탈출 이벤트"를 따로 판정하지 않음(주석에도
    명시: "커브를 빠져나오는 즉시 제약 해제").
  - `lookahead_pos = max(position, 0)`로 **자차 뒤(주행한) 지점은
    매 프레임 배제**되므로, apex를 통과하는 즉시 그 지점 자체가
    argmin 후보에서 사라지고 이후엔 곡률이 완화되는 전방 지점들만
    남아 required_speed가 자연히 상승 -> **정점 통과 즉시 해제
    시작**은 설계상 이미 그렇게 되어 있음(가설 B와 일치). 가속측만
    별도 저역통과(`vturn_accel_rc`)로 스무딩되는 구조라 "탈출 전부터
    서서히 풀림"(가설 A)도 물리적으로는 이미 가능한 형태.
  - **재프레이밍**: 그렇다면 48차까지 확정 못한 "체감상 가속 지연"은
    "아예 안 함" 문제가 아니라, argmin 전환 시점 대비 `vturn_accel_rc`
    스무딩이 체감상 얼마나 느린지(release rate 자체가 너무 완만한지)
    쪽으로 질문이 바뀔 가능성 제기. 아직 코드/로그로 검증 안 함.
  - **[갱신] `vturn_release_lag_scan()` 구현 완료, toolkit 편입 완료**
    (analysis_helpers.py/README.md/CHANGELOG.md 동기화). apex 이후
    "곡률 완화 시작 시각"(steeringAngleDeg proxy) vs "vTurnSpeed 실제
    상승 시작 시각" 사이 지연(lag_s)을 측정. 합성 시나리오 2건(지연
    1.2s 재현/무지연)으로 로직 검증 완료. **한계**: modelV2 raw
    (필터-전 required_speed_kph)는 CSV에 없어 steeringAngleDeg 근사
    proxy 사용 — argmin 전환 시각 자체의 정확한 재현은 아님.
  - **[남음, 최우선] 실제 로그 검증 미실시** — route7(`c8fef594d3`)/
    route8(`dda0d533ce`) raw CSV가 컨테이너 로컬 소실로 없음. **다음
    세션 시작할 것**: 사용자가 route7 또는 신규 고속도로 단일커브
    로그 재업로드 → `extract_log.py`로 CSV 추출 →
    `vturn_release_lag_scan()` 실행 → lag_s 분포 확인. 체감될 만큼
    (예: 0.5s+) 크면 `vturn_accel_rc` 하향 튜닝 검토, 작으면(즉시
    반응 구조 확인) "체감 지연"은 다른 원인(48차처럼 vCruiseCluster
    캡 등)일 가능성 재확인 — 48차 "버그 0건" 결론은 유효, 이건
    별도 축(release rate 자체의 튜닝 여지) 질문임에 유의.

- 저장 시각: 2026-08-23 (48차 계속, **"탈출 후 무가속" 조사 스레드
  사실상 종결**) — `vturn_speed()`(carrot_man.py) 코드 리딩 완료 +
  route7 근접 후보 2건(seg12/seg14)을 CSV 원본(`vTurnSpeed`/`src`)으로
  직접 대조. **두 건 모두 vTurnSpeed가 이미 완전히 해제(200km/h
  안팎)된 상태였고, 유일한 실질 제약은 vCruiseCluster(운전자 순항속도)
  캡뿐이었음 확정** — vturn 코드와는 처음부터 무관. `curve_exit_no_
  accel_scan_v4` 신규 구현(정차 오탐 배제 + cap_margin_thresh_kph
  5.0→6.5 상향) → route7/route8 둘 다 0건으로 수렴 확인.
  **결론: route1~8 누적 8개 route에서 "탈출 후 진짜 무가속" 버그
  확정 사례 0건, 근접 후보들도 vturn과 무관함이 확정됨 — 현재 코드에
  이 버그가 있다는 근거 없음. ryu 코드 변경 없음(toolkit 분석 함수만
  추가).** 이론적 사각지대(8초 lookahead 내 연속 커브 시 argmin이
  다음 커브로 넘어가는 경우)는 남아있으나 능동 스캔 우선순위는
  하향, 구체적 제보/영상이 나오면 재조사. 상세는 FINDINGS.md 48차
  계속 항목 참고.
  **다음 세션 시작할 것**: 이 스레드는 종결. 46차 WIP에 남아있던
  다른 열린 항목(2번 cam/road/vCruiseCluster 캡 가설 원 검증, 3번
  route3 steer 잔존값 규명) 중 하나로 전환하거나, 사용자가 새 제보를
  가져오면 그것부터.

- 저장 시각: 2026-08-23 (48차, 체크포인트 — 사용자가 신규 로그 3개
  (route6=`8417c66e7e` x3seg/route7=`c8fef594d3` x18seg/route8=
  `dda0d533ce` x20seg) 추가 업로드해 curve_exit_no_accel_scan v3
  검증 계속 진행) **route6은 cruise_enabled_ratio=0.0(ADAS 미관여)라
  분석 제외.** route7/route8에 v3를 `min_straight_hold_s`
  0.8/1.9/2.5/3.0 4개 값으로 반복 실행 — **hold값을 3배 이상 늘려도
  새 후보가 전혀 늘지 않음(47차 (a)안 판별력 없음을 실측 확인)**.
  route8은 전 hold값 0건. route7은 3건(hold≥2.5 기준) 중 1건은
  vEgo≈0 정차 상태 오탐으로 즉시 제외, 남은 2건(seg12 t=833.54/
  seg14 t=949.09)은 qcamera 프레임 대조까지 완료 — 둘 다
  cap_margin이 문턱(5.0kph) 바로 위(5.8~6.0kph)인 경계 사례로, 목표
  속도 여유폭 자체가 작아 완만한 가속(0.1m/s² 안팎)이 물리적으로
  타당한 정상 상황에 가까움(버그 아님 쪽으로 해석). **8개 route
  누적으로 "진짜 탈출 후 무가속 버그" 확정 사례 여전히 0건.**
  표준 안전지표(harsh_brake/ttc_danger 등)도 route7/8 둘 다 기존
  누적 패턴과 동일(저속 정차/교차로 상황)이라 신규 위험 없음 확인.
  **[신규, 경미] v3 사각지대 발견**: vEgo≈0(정차) 상태에서 곡률
  임계값을 우연히 넘는 케이스를 배제하는 로직이 없음 — v4 후보에
  `vEgo_at_exit` 최소 속도 조건 추가 필요.
  **다음(사용자 결정 대기)**: (c)안(증상 실재 여부 자체 재평가) 쪽으로
  무게를 옮길 것을 권고 — 8개 route 스캔에도 확정 사례 0건, 근접
  후보도 전부 "여유폭 작음"으로 설명 가능한 경계 사례였음. (a)안은
  이번 실측으로 우선순위 하향 권고. 계속 조사한다면 cap_margin_
  thresh_kph를 5.0→6.5~7.0로 살짝 올리는 시뮬레이션부터(패치 전
  시뮬레이션 우선 원칙). 상세는 FINDINGS.md 48차 항목 참고. 코드
  변경 없음(분석만).

- 저장 시각: 2026-08-23 (47차 계속, 체크포인트2 — 사용자가 대용량 로그
  2개(route4=`d45a15f8fc` 20세그/route5=`7ffb3e693c` 20세그, 각
  ~24000행) 추가 업로드해 v3 필터 실전 검증 진행) **v3(vCruiseCluster
  캡 필터) 실제 필터링 효과 최초 확인** — route4에서 v1=13건→v2=5건→
  **v3=1건**으로 감소, v2에서 남은 5건 중 4건이 vCruiseCluster 캡
  여유폭(<5kph, 2건은 심지어 음수 — desiredSpeed 자체가 vEgo보다 이미
  낮아 다음 커브 제약이 이미 겹친 상태)로 정상 필터링됨을 실증(route1/2/3
  때는 검증할 후보 자체가 없었던 것과 대비). route5는 v1=11건 전부 저속
  (3~15km/h, 교차로 추정)+leadStatus근접/S자재진입으로 v2 단계에서 이미
  걸러져 v3 검증 후보 없음(참고용).
  **[신규 발견, 중요] v3에 유일하게 남은 route4 seg6 t=10183.18 후보도
  실제로는 버그가 아니라 S자 커브(우→좌 반대방향 커브 즉시 재진입)로
  확인** — vTurnSpeed가 t=10181.98부터 부호 전환(+74→-73)되며 반대
  방향 커브 감속이 바로 이어짐. 곡률 절대값이 0.002 아래로 내려갔다가
  다시 올라가는 데 **약 1.9초** 걸렸는데, v2/v3 공통 필터
  `min_straight_hold_s=0.8초`가 이 케이스엔 너무 짧아서 "진짜 탈출"로
  오판함. **즉 v1→v2→v3 전부 통과한 후보도 여전히 오탐이었음 — 지금까지
  5개 route(1~5) 어디에서도 "탈출 후 진짜 무가속 버그" 확정 사례를
  찾지 못함.** 상세는 FINDINGS.md 47차 계속 항목 참고.
  **다음(사용자 결정 대기)**: (a) `min_straight_hold_s`를 1.9초 이상
  (예: 2.5~3.0초)으로 늘려 v4 후보 재설계, (b) 아니면 절대적 hold
  시간 대신 "곡률이 0을 향해 계속 감소 중인지(재상승 전조 감지)"
  방향성 체크로 필터 로직 자체를 바꾸는 방안 검토, (c) 5개 route
  전부 무후보로 끝났으므로 "탈출 후 가속지연" 증상 자체가 실재하는지
  회의적으로 재검토할 필요도 있음(46차 vturn_speed 코드리딩 결과와
  함께 재평가 권장). 코드 변경 없음(관찰/분석만, v3 자체는 47차 전반부
  구현 그대로 유지).

- 저장 시각: 2026-08-23 (47차, 체크포인트 — 46차 마지막 "2)cam/road/
  vCruiseCluster 캡 가설" 착수. **[중요 발견] route3(866476e5c3--18)의
  "vturn 이상함"과 미해결 steer 잔존값 미스터리가 둘 다 수동 차선변경
  (rightBlinker)으로 설명 가능함을 확인** — 사용자가 실차 화면녹화
  캡처(11:31경 "차선을 변경합니다" 표시, 우로 굽은 커브에서 우측
  차선변경)를 제보하며 "차선변경으로 곡선이 심해져 vturn이 튄 것 아니냐"
  가설 제기 → t=4784~4792 프레임 단위 재추적으로 확인: rightBlinker
  True(t=4785.03~4788.63) 구간과 desiredCurvature 급등(피크 0.00213)
  +vTurnSpeed 급락(129→103)이 거의 동시 발생, `laneChangeState`는 내내
  `off`(자동 차선변경 아닌 수동 차로이동으로 판단). 상세는 FINDINGS.md
  "[RESOLVED 가능성 높음] vturn 급감/조기해제와 steer 잔존값" 항목 참고.
  **표본 1건 기준, 확정 아님** — 다음 세션 후보로 `lane_change_curvature_
  artifact_scan` 검증 함수 추가 여부 검토(FINDINGS.md 다음 단계 참고).
  **[병행 작업] `curve_exit_no_accel_scan_v3` 구현 완료** —
  vCruiseCluster 캡 여유폭 필터(<5kph 제외) 추가, `extract_log.py`에도
  `vCruiseCluster` 컬럼 신규 추가(기존 `vCruise`와 별개 필드였음, 46차
  이전 CSV는 이 필드 없음 유의). route1/2/3 재실행: route1/3은 v1부터
  0건(세그 내 커브 미탈출, 기존 한계와 동일), route2는 v1=4건이 v2
  단계에서 전부 필터링(S자 연속커브 재진입)돼 v3 신규 필터까지 도달한
  후보가 없었음 — **v3 코드 자체는 문법/로직 검증 완료했으나 실제로
  뭔가를 걸러내는지는 이번 로그로 확인 못함.** 상세는 FINDINGS.md 47차
  항목(toolkit/CHANGELOG.md 47차 항목도 동기화) 참고.
  **다음(사용자 결정 대기)**: (a) v3 필터를 실제 검증할 수 있는 로그
  (고속도로 단일 커브, 탈출 시 vCruiseCluster 캡에 걸릴 만한 상황) 추가
  확보, (b) `lane_change_curvature_artifact_scan` 검증 함수 착수 여부,
  (c) 46차 원래 "2)cam/road/vCruiseCluster 캡 가설" 자체(탈출 후 가속
  지연이 vCruiseCluster 캡 때문인지)는 아직 별도 검증 필요 — 이번 47차
  발견은 그와는 다른 축(vturn 급변의 원인)임에 유의, 혼동하지 말 것.
  코드 변경 있음(`extract_log.py`/`analysis_helpers.py`), patch는
  ryu 절차대로 별도 전달 예정.

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

## 51차 — route 감속 실측 착수 중 turn_speed_violations() 단위버그 발견·수정, 토큰 예산으로 중간 체크포인트

**진행 상황**: vturn apex 조기화 아이디어는 사용자가 보류, "route 감속
코딩"으로 전환. route(내비 경로) 감속 실측 검증 착수 → f3db6ca89d(7세그,
seg6/7/15~19) 분석 완료. 상세는 FINDINGS.md 51차 참고.

**핵심 결과 요약**:
1. route overshoot 위반 0건이지만 이 표본은 route가 거의 안 눌린 케이스
   (결론력 약함) — route1(203f99d429 seg8, 이미 업로드됨, 급조임 커브)로
   재검증 필요.
2. route desiredSpeed 급점프 2건(0.1초 내 32km/h 하락) — 구조적 문제인지
   확인 필요.
3. **[중요] turn_speed_violations()/speed_tracking_error() 단위 불일치
   버그 발견·수정** — vEgo(m/s)를 km/h 필드와 변환 없이 비교하던 구조라
   과거 "위반 0건" 결론들이 대부분 false negative였을 가능성. 수정판으로
   f3db6ca89d 재스캔하니 vturn overshoot 14건 신규 발견(과거엔 안 잡혔음).

**코드 변경**: `devnotes/toolkit/analysis_helpers.py`만 변경(3개 함수:
`turn_speed_violations` 단위 수정, `speed_tracking_error` 단위 수정,
`source_target_violations`/`route_target_jump_events` 신규 추가).
`ryu` 패치 없음.

## 다음 세션(또는 다음 메시지)에서 이어갈 것
1. **최우선**: route1(203f99d429 seg8, 곡선.zip에 이미 있음)으로 route
   감속 재검증 — 급조임 커브에서 route가 실제로 binding하는지, overshoot
   없는지.
2. **최우선**: vturn overshoot 14건(버그 수정 후 재현) 개별 조사 —
   어느 지점, 왜 목표속도를 못 따라갔는지 프레임 단위 확인.
3. turn_speed_violations() 버그로 "0건" 결론 났던 과거 route들
   (24차 route4~11, 41차 route1/route2 등) 원본 로그 재확보되는 대로
   수정판 재스캔 — 안전 결론 자체가 뒤집힐 수 있는 사안이라 우선순위 높음.
4. route desiredSpeed 급점프 2건이 우연인지 구조적 문제인지 추가 표본으로 확인.

## 다음 세션 시작 시
이 WIP.md에 "51차" 섹션이 있으면 무조건 이 지점부터 이어감. 사용자가
"체크포인트"라고만 말하면 이 섹션 상태 그대로 유지, 추가 진행 있으면
새 섹션으로 덧붙임.

## 79차 (완료 — 원인분석+패치작성/검증 완료, 실차 적용/검증 대기) — 수동주행 중 첫 +RES 시 목표속도가 현재속도보다 낮게 설정되는 문제

**증상(사용자 제보)**: 시동 후 수동으로 60km/h로 주행 중 운전대 +RES(accelCruise)
버튼을 1회 누르면 목표속도가 33km/h로 설정되며 감속 발생 — 최소 1회 누를 때
현재 속도보다는 높게 설정되길 원함.

**원인 확정** (`selfdrive/car/cruise.py`, `VCruiseCarrot._update_cruise_buttons()`):
- `update_v_cruise()`에서 `CS.cruiseState.available`이 True이고 `pcmCruise`+
  `speed_from_pcm!=1`(Genesis DH 해당)이면, 매 프레임
  `self.v_cruise_kph = np.clip(v_cruise_kph, 30, self._cruise_speed_max)`로만
  처리됨 — 이 `v_cruise_kph`는 `CC.enabled=False`(크루즈 미인게이지, 즉 수동주행
  중)인 동안 버튼 로직에서 전혀 갱신되지 않고(아래 참고) 그대로 정체된 채
  30~161 사이로만 clip됨. **즉 수동주행 중엔 v_cruise_kph가 현재 차량속도를 전혀
  추종하지 않고, 이전 세션에서 남은 잔여값(이번 사례: 33)에 멈춰있음.**\n- `_update_cruise_buttons()`의 accelCruise 처리부에서
  `elif self._cruise_ready or not CC.enabled or CS.cruiseState.standstill or
  self.carrot_cruise_active:` 조건이 `not CC.enabled`(=수동주행 중 첫 인게이지)
  케이스까지 묶어서 **아무 것도 하지 않는(no-op, `if False:` 블록만 있음)**
  분기로 보내버림 — 그 결과 첫 +RES를 눌러도 위에서 정체돼 있던 33이 그대로
  크루즈 목표속도로 채택됨.
- **비교**: 바로 아래 decelCruise 처리부(L523)엔 이미 `elif not CC.enabled:
  v_cruise_kph = max(self.v_ego_kph_set, self._cruise_speed_min)`로 현재속도
  반영 로직이 있음 — **accelCruise만 이 처리가 빠져있던 비대칭 버그**로 확인.
  (참고: `d02bf5f6`(2026-03-23, "fix.. v_cruise init") 커밋이 `cruiseState.available`
  전환 시점(시동 직후 1프레임)만 `v_ego_kph_set`으로 초기화하도록 고쳤으나,
  "주행 중 CC 비활성 상태에서의 정체" 케이스는 다루지 않아 이번 버그가 계속
  남아있었음.)

**조치** (`selfdrive/car/cruise.py`, 로컬 커밋 `08ef23f`, base `f3773b58`(devnotes
LAST_ANALYZED 확인용 원격 HEAD)):
- accelCruise 분기에서 `not CC.enabled`를 기존 결합 조건에서 분리해 별도 `elif`로
  추가 — `self._cruise_ready`/`standstill`/`carrot_cruise_active`는 기존 동작(변경
  없음) 그대로 유지(우선순위도 decelCruise와 동일하게 이 세 조건을 먼저 검사).
  `not CC.enabled`인 경우엔 `math.ceil((v_ego_kph_set + 0.01) / unit) * unit`로
  현재 속도보다 **반드시 높게**(다음 단위 눈금으로 올림) 설정 — decelCruise가
  `max(v_ego_kph_set, min)`(현재속도와 같거나 높음)인 것과 달리, accelCruise는
  "+"버튼 의미를 살려 현재속도보다 확실히 높게 설정(사용자 요청 문구 "현재보다는
  높게"에 맞춤).

**검증** (`work/sim_res_button.py`, 로직 단위 순수함수 재현):
- 재현 시나리오(수동주행 vEgo=60km/h, v_cruise_kph 정체값=33, CC.enabled=False):
  구코드 33(버그 재현) → 신코드 61(현재속도+1kph 눈금, 개선 확인).
- 회귀 확인: `cruise_ready=True`/`standstill=True` 케이스는 구코드/신코드 결과
  동일(33, 변경 없음) — 취소 직후 등 기존 no-op 분기 동작 그대로 보존.
- `git format-patch` → `verify-am-79` 임시 브랜치(base `f3773b58`)에서 `git am`+
  `py_compile` 통과 확인.

**전달**: `0001-79-RES-accelCruise-v_cruise_kph.patch`를 `/mnt/user-data/outputs/`에
전달(base `f3773b58`, 즉 현재 origin `c3-ms-dev` HEAD 위에 바로 `git am` 가능).

**[갱신] 적용 완료 확인** — 사용자가 `C:\dev\ryu`를 origin에서 새로 clone(base
`f3773b58` 일치 확인) 후 `git am` 적용(로컬 `2d5174e`, diff --stat +9/-1로 예상과
일치) + `git push origin c3-ms-dev` 완료(push 결과 로그 미확인이라 `git fetch`+
`git log origin/c3-ms-dev -1` 재확인 요청함 — **push까지 완전히 확인 완료**(`git fetch`+`git log origin/c3-ms-dev -1`
결과 `2d5174e` 일치 확인됨). **다음은 실차 검증만 남음.**

**다음(최우선)**:
1. `C:\dev\ryu`에서 `git am` 적용 + `git push origin c3-ms-dev`.
2. **실차 드라이브 검증**: (a) 수동주행 중 첫 +RES 시 목표속도가 실제로 현재속도
   보다 높게(눈금 올림) 설정되는지, (b) **회귀 검증** — 크루즈 취소 직후
   재인게이지(`_cruise_ready`/`_v_cruise_kph_at_brake` 경로), 정차 후 출발
   (`standstill`), carrot 명령 인게이지(`carrot_cruise_active`) 등 기존
   인게이지 경로들이 이번 변경으로 영향받지 않는지, (c) decelCruise(−버튼)로
   첫 인게이지하는 경우(기존 로직 그대로, 변경 없음)와의 일관성 체감 확인.
3. `unit`(눈금 크기, `_cruise_speed_unit_basic`)이 사용자 설정에 따라 1보다
   크면 "현재속도+해당 눈금"까지 올라갈 수 있음(예: 눈금 5면 60→65) — 실차
   반응 보고 "몇 km/h 정도 위로 붙는게 적당한지" 튜닝 여지 있음(현재는 설계
   추정치, NEEDS_VALIDATION).

## 80차 계속 (완료) — toolkit 미편입 검증 스크립트 4개 소급 정식 편입

**배경**: 80차에서 "도구 먼저 찾기/새로 만들면 반드시 저장" 정책을
문서(`PROJECT_INSTRUCTIONS.md`/`toolkit/README.md`)에 강화한 직후,
사용자 요청으로 과거 세션에서 `work/`(컨테이너 스크래치)에만 작성되고
`toolkit/`엔 저장되지 않아 컨테이너 리셋으로 유실된 재사용 가치 높은
검증 스크립트들을 실제로 찾아 저장하는 작업 진행. WIP.md/FINDINGS.md
전체에서 "toolkit 미편입" 언급을 grep해 후보 추출 → 재사용 가치
(반복적으로 이월/재확인 필요했던 것) 기준으로 4개 선정.

**작업**: 아래 4개를 현재(80차 계속 시점) 코드 기준으로 재작성/신규
작성 후 `toolkit/`에 정식 편입, 전부 재검증 통과:
1. `sim_jerk_boost.py` — 66/67차 방안G `a_change_cost` boost
   ('discontinuity' 소스 전용) 합성검증. **69차부터 여러 세션에 걸쳐
   "실물 존재 확인 필요"로 이월만 되고 실제로는 한 번도 작성된 적
   없었음이 이번에 확인됨** — 코드 주석 언급뿐이었던 상태 해소.
2. `sim_res_button.py` — 79차 +RES accelCruise 버그 패치 검증(79차 세션
   work/에 있던 것 그대로 정식 편입, 로직 변경 없음).
3. `test_launch_bypass.py` — 45차 launch bypass 로직 검증(45차 세션
   work/에 있던 것 그대로 정식 편입, 로직 변경 없음).
4. `test_scc_gate.py` — 37차 SCC 단일점 폴백 dPath 게이트 검증(37차
   당시 실행 로그는 남아있지 않아 이번에 현재 `radard.py` 기준으로
   재작성).

**코드 변경**: 없음(`ryu` 미변경). `toolkit/`에 스크립트 4개 신규 +
`README.md`/`CHANGELOG.md` 갱신만.

**다음**: 이번에 편입 안 한 나머지 후보(`work/five_item_scan.py`,
`curve_gap_vs_apex_scan.py` 등)는 "편입 여부 판단 보류" 상태 그대로 —
방안 확정/재사용 가치가 더 명확해지면 다음 세션에서 재검토.

## 81차 계속 (체크포인트 — (a)(b) 적용/push 완료 확인, 실차 검증 대기)

**배경**: 사용자가 곡선_개념도.pdf/곡선_가감속_코딩.txt 업로드 — vturn/route
결합 설계 방향 제시. 코드 대조 결과 vturn 1/2번(기본곡선/연속곡선)은
이미 argmin+forward-only 구조로 구현돼 있음을 확인(설계 일치, 코드
변경 불필요). route 1번(현재속도 감안 조기감속)도 역방향 DP로 이미
구현됨 확인. **실제 조치가 필요한 두 지점만 특정**: (a) 공통사항
2)/3)(목표속도 도달 지연 체감) → `vturn_safe_time` 상향, (b) route
2번(500m 게이트 제거) → 아래 "81차" 원본 섹션에서 이미 식별한
`TurnSpeedControlMode==2`의 `-500<xDistToTurn<500` 게이트.

**사용자 지시**: 최신 `c3-ms-dev`(HEAD `2d5174e`, 79차) 베이스로
**`c3-ms-curv` 신규 브랜치** 생성 후 그 위에서 작업(실차 문제 시
c3-ms-dev로 즉시 롤백 가능하도록 분리). (a)는 2.0초로.

**구현** (`c3-ms-curv`, 로컬 커밋 `6344077`, base `2d5174e`):
- (a) `carrot_man.py`: `self.vturn_safe_time = 1.0` → `2.0`.
- (b) `carrot_serv.py`: `if self.turnSpeedControlMode == 2: if -500<xDistToTurn<500: append(route)` →
  `if self.turnSpeedControlMode in [2,3,4]: append(route)`로 단순화 —
  mode 2도 mode 3/4처럼 항상 route 참가. vturn 참가 조건(`[1,2]` 분기)은
  손대지 않아 mode 2에서 vturn+route 둘 다 항상 경쟁하는 구조가 됨(mode
  3/4는 기존대로 vturn 자체가 미참가 — vturn+route 동시경쟁은 mode
  2에서만 발생, 변경 없음).

**검증**: `py_compile` 통과. `git format-patch` → base `2d5174e` 위
`verify-am-81` 임시 브랜치에서 `git am` 적용 → 결과가 `c3-ms-curv`와
**diff 0(완전 동일)** 확인.

**전달**: `0001-81-a-b-vturn_safe_time-1.0s-2.0s-route-500m-TBT-mode.patch`를
`/mnt/user-data/outputs/`에 전달.

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`에서
`git checkout -b c3-ms-curv origin/c3-ms-dev` + `git am` 적용 +
`git push origin c3-ms-curv` 완료(신규 브랜치 최초 push, GitHub PR
링크 자동 안내됐으나 PR은 생성 안 함 — 브랜치만 사용). 컨테이너에서
`git fetch origin c3-ms-curv:refs/remotes/origin/c3-ms-curv` 후 로컬
검증 커밋(`6344077`)과 diff 0(완전 동일) 재확인 완료. origin
`c3-ms-curv` HEAD: `d7a647f`.

**[갱신] vturn_safe_time 영향범위 질의응답**: 사용자가 "(a)의 2초가
vturn 전체 로직(사전감속 시작/목표속도 도달/원복)을 균일하게 앞당기는
것인지" 질문 → 코드(`required_speed_mps = sqrt(safe_speed² + 2*decel_rate*
max(pos-safe_dist,0))`) 확인 결과 **사전감속 시작 지점과 목표속도 도달
시점만 영향받고(둘 다 safe_time만큼 더 일찍), 정점 통과 후 원복(재가속)
타이밍은 영향 없음**을 확인해 설명함. 원복 속도의 부드러움/타이밍은
별도 상수 `vturn_accel_rc`(0.15s 저역통과, 이번엔 미변경)가 담당 —
이번 patch 범위 밖. 실차 검증 시 원복 쪽 체감(답답함/급함)도 별도로
확인 필요하면 `vturn_accel_rc` 조정을 후속 항목으로 고려.

**다음(최우선)**:
1. ~~위 명령으로 `c3-ms-curv` 브랜치 생성+push~~ → **완료**. 기기에서
   `c3-ms-curv`로 전환 후 실차 드라이브 검증만 남음.
2. (a) 검증 포인트: 정점에서 실제 vEgo가 목표속도에 더 잘 맞춰
   도달하는지(2.0s가 과한지/부족한지 체감), 반대로 사전감속이 너무
   일찍 시작돼 답답한 느낌은 없는지.
3. (b) 검증 포인트: TBT 없는 일반 국도 굽이길에서 route가 이제 실제로
   개입하는지, **회귀 검증 필수** — 직선/완만 구간에서 GPS 폴리라인
   노이즈로 인한 오탐(불필요 감속) 없는지(가장 중요한 리스크).
4. 문제 발생 시 CarrotWeb pull UI로 `c3-ms-dev`(브랜치 미변경 원본)로
   즉시 롤백 가능 — 이게 이번에 브랜치를 분리한 목적.
5. 통과하면 `c3-ms-curv`를 `c3-ms-dev`에 merge할지, 계속 별도 브랜치로
   유지할지 사용자 결정 필요.

## 81차 (완료 — 설계검토/논의 단계, 위 "81차 계속"에서 구현으로 이어짐) — 곡선구간 가감속 vturn+route 결합 로직 설계 재검토 착수 (model 제외)

**배경**: 사용자가 "곡선구간 가감속 현재 vturn+route(네비경로)만 쓰고
model 가감속은 사용 안 함"이라고 문제제기 → 코드 확인 결과 `model`
후보(`desire_helper._make_model_turn_speed()`, `ModelTurnSpeedFactor`
기반) 자체는 `carrot_serv.py` min() 경쟁에 여전히 코드상 참가하도록
남아있으나(9~50차에 걸쳐 vturn↔model 플리커 대응/게이팅 재설계를 반복해온
이력 있음), **사용자가 설정(`ModelTurnSpeedFactor`)에서 model을 이미
꺼둔 상태**라고 확인해줌 → 이번 논의는 model을 제외하고 vturn(비젼)+route
(내비경로) 둘의 결합 로직만 재검토하기로 범위 확정.

**현재 아키텍처 정리** (`carrot_man.py`/`carrot_serv.py` 코드 리딩,
devnotes에 이 부분(TurnSpeedControlMode/±500m 게이트) 자체를 다룬
과거 세션 기록 없음 — 이번이 첫 정리):

1. **vturn** (`carrot_man.py vturn_speed()`): 비전모델 예측 궤적
   (~10s lookahead)에서 지점별 필요속도를 **순방향** 물리공식
   (`v_i²=v_f²+2ad`, `TARGET_LAT_A=1.6m/s²`)으로 계산, 가장 엄격한
   지점(apex) 채택. `TurnSpeedControlMode in [1,2]`면 항상 후보 참가.
   즉시 반응하지만 원거리 예측 불안정 이력 있음(50차, 부호까지 요동).

2. **route** (`carrot_man.py carrot_navi_route()`): 외부 내비 앱이
   보내는 GPS 폴리라인(`navi_points`)을 5m 간격 리샘플 → 3점 곡률
   (`calculate_curvature`) → **곡률→속도 룩업테이블**(`V_CURVE_LOOKUP_BP/
   VALS`, 경험적 테이블이지 물리공식 아님)로 지점별 속도 산출 →
   **역방향 DP**로 `autoNaviSpeedDecelRate` 감속한계 적용해 현재
   지점 속도로 역전파. 항상 전방 300m 전체로 계산됨.
   - **참가 게이트(`TurnSpeedControlMode==2`, 현재 사용자 설정값)**:
     `-500 < xDistToTurn < 500`(TBT 다음 회전지점과의 거리)일 때만
     min() 후보에 넣음. **[설계상 의문점, 이번에 처음 식별]** —
     `xDistToTurn`은 TBT 안내(교차로 좌/우회전 등) 이벤트까지의 거리인데,
     route_speed 자체는 그 지점 근처 곡률만 계산하는 게 아니라 항상
     전방 300m 폴리라인 전체(어떤 곡선이든)를 계산한다. 즉 **TBT
     안내가 없는 일반 도로 급커브(교차로 회전이 아닌 국도 굽이길 등)에서는
     route_speed가 계산은 되고도 게이트에 막혀 min() 후보에서 아예
     빠지고, vturn 단독으로만 대응**하게 되는 구조. mode 3/4는 이
     게이트 없이 항상 route 참가.

3. **결합**: `desired_speed, source = min(speed_n_sources, ...)` — 단순
   최소값 선택. vturn/route 둘 다 후보에 있으면 더 낮은(더 엄격한) 쪽이
   그대로 채택되고, 전환 시 부드러운 블렌딩 로직은 없음(다른 소스간
   플리커 문제가 9~50차에 걸쳐 반복 다뤄진 배경과 동일 구조).

**다음(설계 재검토 계속)**:
1. `-500<xDistToTurn<500` 게이트가 실제로 "TBT 없는 일반 커브에서
   route 미참가"를 유발하는지 실측 로그로 확인 필요(현재는 코드 리딩
   기반 추정, NEEDS_VALIDATION).
2. min() 단순선택 대신 소스 전환 시 블렌딩/히스테리시스가 필요한지
   (과거 vturn↔model 플리커 대응 사례를 vturn↔route에도 참고 적용할지)
   검토.
3. mode 2(현재 설정)를 mode 3(항상 route 참가)으로 바꾸는 대안의
   장단점 — route가 이르게 개입하면 좋을 수 있으나, 내비 GPS 폴리라인
   품질/오차가 낮은 도로에서 오히려 오탐 유발 가능성 고려 필요.

**[갱신] mode 3 오해 정정** — `TurnSpeedControlMode=3`은 "route 500m
게이트만 해제 + vturn 유지"가 아니라 **vturn을 완전히 끄고 route
단독으로 전환하는 모드**임을 코드로 재확인:
```python
if self.turnSpeedControlMode in [1,2]:
    speed_n_sources.append(vturn)   # mode 3은 [1,2] 밖 -> vturn 미참가
...
elif self.turnSpeedControlMode in [3, 4]:
    speed_n_sources.append(route)   # 게이트 없이 항상 참가
```
UI 설명(`"3: route(always)"`) 자체가 이 의미. 즉 "vturn+route 둘 다
항상 참전"이라는 목표 조합은 **현재 UI 설정만으로는 불가능** — mode 2의
`-500<xDistToTurn<500` 게이트만 제거하는 패치가 필요함(vturn 참가
조건은 손대지 않음). 대안으로 게이트를 "TBT 거리" 대신 다른 조건
(예: route_speed 자체가 유의미하게 낮을 때만 참가)으로 교체하는 방향도
논의 중 — 아직 패치 미작성, 방향 결정 대기.

## 82차 (체크포인트 — 구현+검증+패치 전달 완료, `git am`/실차 적용 대기) — vturn/route 원복(가속 재개)측 대칭 safe_time 버퍼, route측 심각한 버그 발견/수정

**배경**: 81차 계속에서 확인한 "vturn_safe_time은 진입측(사전감속 시작/목표속도
도달)에만 영향, 정점 통과 후 원복(재가속) 타이밍엔 무관"이라는 비대칭 구조에
대해, 사용자가 "가속 응답도 동일하게 지연이 있으니 원복측도 대칭 적용해야
한다"고 지적 → vturn/route 양쪽에 동일한 설계(진입과 같은 `vturn_safe_time`
버퍼를 원복측에도 대칭 적용) 승인 후 동시 구현.

**컨테이너 재시작으로 유실**: 이전 세션이 구현+디버깅 도중(특히 route측
검증 스크립트가 계속 diff=0을 보여 원인 규명 중) 컨테이너가 재시작됨.
이번 세션은 사용자가 로컬에서 편집 완료한 `carrot_man.py`를 업로드한 상태로
시작 — `origin/c3-ms-curv`(81차 HEAD `d7a647f`) 대비 diff 확인 결과 vturn/route
양쪽 모두 구현은 이미 로컬에 반영돼 있었으나 **커밋/patch화/devnotes 기록은
전혀 안 된 상태**였음(순수 파일 diff로만 존재).

**구현 및 검증**:

1. **`vturn_speed()` 원복측 대칭 buffer — 정상 작동 확인**:
   `accel_lead_dist = CS.vEgo * vturn_safe_time`만큼 lookahead position을
   앞당긴 가상의 2차 계산(`turnSpeed_recovery`)을 만들어, 상승추세
   (`turnSpeed > vturn_last_speed`)이고 recovery 값이 더 높을 때만 채택.
   `work/test_vturn_recovery_v2.py`(20Hz 프레임 시뮬레이션, 연속곡률
   프로파일 — 계단형 프로파일에서는 모델의 lookahead 배열이 정점 통과 즉시
   불연속으로 빠지는 특성상 buffer 효과가 안 보였으나, 실제 모델처럼
   연속적으로 완화되는 곡률 프로파일에서는) **100km/h 회복 시점이 0.7초/11m
   단축, 과도구간 turnSpeed 최대 +29km/h 우위** 확인 — 설계 의도대로 작동.
   접근(진입)측엔 전혀 영향 없음(로직이 완전히 분리된 블록, 회귀 없음).

2. **`carrot_navi_route()` 원복측 대칭 buffer — 심각한 버그 발견 후 수정**:
   최초 구현은 진입측 `time_delay`에도 `+ vturn_safe_time`을 동일하게
   더했는데, **`work/test_route_recovery2.py`(현실적 거리 스케일: 커브
   60m + 직후 직선 800m)로 재현한 결과 patched 출력이 baseline과
   소수점까지 100% 동일**함을 발견. 원인 규명(`work/` 내 debug trace):
   이 DP는 단일 스칼라 `time_wait`(누적 시간여유)로 감속/가속을 관리하는데,
   진입측에서 추가한 +2.0초의 debt가 **커브 구간(out_speed가 target에
   고정되어 클리핑되는 구간) 내내 그대로 보존**되다가, 원복 크레딧
   (`+= vturn_safe_time`, 동일 +2.0초)에서 **정확히 상쇄**되어 그 이후
   전체 구간의 `time_wait`/`out_speed`가 원본과 완전히 일치하게 되는
   구조적 문제였음(클리핑이 발생하지 않는 한 두 조정은 수학적으로 항상
   정확히 상쇄됨 — 커브가 매우 길어서 debt가 커브 안에서 다 소진되는
   극단적 케이스가 아닌 한 일반적인 커브에서는 100% 무효화).
   **수정**: 진입측(`time_delay`) 변경을 되돌려 순수 물리 도달시간
   계산으로 복원(기존 79/81차 동작 그대로), 원복측 크레딧만 유지.
   원복 판정 조건도 `route_prev_state=='decel'`(decel 트리거 직후 첫
   지점에 즉시 발동 — 커브 내부 정체구간에서도 조기 발동하는 문제 있었음)
   에서 `target_speed > next_out_speed and route_prev_state=='decel'`
   (실제로 target이 next_out을 넘어서는, 즉 커브를 물리적으로 빠져나가는
   지점)로 엄격화. 수정 후 재검증: baseline 대비 **회복구간에서 최대
   +6.9km/h 더 높은 out_speed**(더 빠른 회복) 확인, 커브 구간 내부에서는
   `elif` 조건(immediate vs strict) 어느 쪽을 써도 다운스트림 결과가
   동일함도 확인(둘 다 커브 내부에서 60kph를 넘기지 않음 — 회귀 없음).

3. **`py_compile` 통과, `git am` 검증**: 로컬 커밋(`a3f2880`, base
   `d7a647f`=81차 a/b) → `git format-patch -1` → `verify-am-82` 임시
   브랜치(base `d7a647f`)에서 `git am` 적용 → diff 0(완전 동일) 확인.

**전달**: `0001-82차-vturn-route-원복측-대칭버퍼-route버그수정.patch`를
`/mnt/user-data/outputs/`에 전달(base `d7a647f` = 현재 origin
`c3-ms-curv` HEAD 위에 바로 `git am` 가능).

**신규 상수 없음** — 진입측과 동일하게 `vturn_safe_time`(2.0s) 재사용.

**코드 변경**: `carrot_man.py`(ryu, `c3-ms-curv` 브랜치 대상, 패치 전달
완료)/`toolkit`(devnotes, 신규 검증스크립트는 아직 `work/`에만 있음 —
정식 편입 여부는 다음 세션 판단, 아래 참고).

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`(`c3-ms-curv` 브랜치)에서
`git am` 적용(로컬 diff --stat 예상과 일치) + `git push origin c3-ms-curv`
완료. 컨테이너에서 `git fetch origin c3-ms-curv:refs/remotes/origin/c3-ms-curv`
후 로컬 검증 커밋과 diff 0(완전 동일) 재확인 완료. origin `c3-ms-curv` HEAD:
`451a3b9`. **다음은 실차 검증만 남음.**

**다음(최우선)**:
1. **실차 드라이브 검증** — (a) vturn: 정점 통과 후 재가속이 더 자연스럽게
   느껴지는지(81차에서 지적된 "원복이 안 당겨지는" 문제 해소 여부),
   (b) route: 커브 빠져나온 후 회복이 더 빨라지는지, (c) **회귀 검증
   필수** — 진입(사전감속)측 체감이 이번 변경으로 전혀 달라지지 않았는지
   (vturn 진입/route 진입 로직 모두 미변경이어야 정상), 커브 구간 내부에서
   과속(target 초과) 없는지.
2. 검증용 스크립트 2개(`work/test_vturn_recovery_v2.py`,
   `work/test_route_recovery2.py`)는 재사용 가치가 높음(원복측 buffer
   회귀 검증에 반복 필요) — 아직 `toolkit/`에 미편입 상태, 다음 세션에서
   `toolkit/README.md` 정책대로 정식 편입 필요(80차 계속에서 강화한
   정책과 동일 적용 대상).
3. 문제 발생 시 CarrotWeb pull UI로 `c3-ms-dev`(브랜치 미변경 원본)로
   즉시 롤백 가능.

## 다음 세션 시작 시
이 WIP.md에 "82차" 섹션이 있으면 이 지점부터 이어감 — 특히 (1) `git am`/
실차 검증 결과 확인, (2) 위 검증 스크립트 2개 toolkit 편입 여부.

## 83차 (체크포인트 — 코드 변경 없음, 분석/설명만) — route 커브 사전감속 파라미터(`AutoNaviSpeedDecelRate`) 튜닝 관계 정리

**배경**: 82차(원복측 대칭버퍼) 실차검증 대기 중, 사용자가 별도로 "route
계산 로직으로 곡선 진입전 사전감속 시간을 늘릴 수 없나(속도에 따라 시간이
늘면 감속도가 낮아지나?)" 질문 → vturn류 신규 버퍼 추가(3안)는 사용자가
불채택, **`AutoNaviSpeedDecelRate` 파라미터 조정(2안)만 채택**해 설명.

**핵심 확인 사항**:
1. `carrot_navi_route()`(`carrot_man.py`)의 진입측 감속 계산은 이미
   `v_ego_kph`(매 프레임 실측 현재속도) 기반 물리공식
   (`필요거리=(v_ego²-target²)/(2×accel_limit)`, `accel_limit=
   self.carrot_serv.autoNaviSpeedDecelRate`)이라 **속도가 높을수록 필요
   감속시간/거리가 이미 자동으로 늘어남** — 별도 코드 변경 불필요.
2. `AutoNaviSpeedDecelRate`(UI: "SpeedCamDecelRatex0.01m/s^2", 범위
   10~200→0.10~2.00 m/s², 기본값 120=1.20)를 **낮추면** 더 이르게·완만하게
   감속 시작(UI 툴팁 "Lower number, slows down from a greater distance"와
   일치) — 기존 노출된 설정값으로 코드 변경 없이 바로 튜닝 가능.
3. **[중요, 신규 확인] 사용자 실제 `params_backup-1.json` 값**:
   `AutoNaviSpeedDecelRate=70`(=0.70 m/s², 기본 120보다 이미 상당히 낮춤),
   `AutoNaviSpeedCtrlEnd=9`, `TurnSpeedControlMode=2`,
   `ModelTurnSpeedFactor=20`, `AutoCurveSpeedFactor=90`,
   `AutoCurveSpeedAggressiveness=100` — 81/82차 작업 대상(`TurnSpeedControlMode=2`)과
   일치 확인.
4. **[중요, 신규 발견] 300m lookahead 상한(`get_path_after_distance(...,300)`)과의
   상호작용**: `accel_limit`을 낮출수록 필요거리가 늘어나 300m 상한을 쉽게
   초과함 — 예) 100→60km/h는 accel=0.70에서 이미 ≈303m로 상한 초과,
   accel=1.39 m/s²(UI 140)가 "120→60km/h를 정확히 300m에 맞추는" 이론적
   경계값(여유 없음, 실사용은 150~160 권장). 반대로 80→30km/h(큰 감속폭)는
   accel=0.70에서 ≈303m(초과), accel=0.80에서 ≈265m(여유 35m, 상한 이내)로
   — **감속폭이 클 때는 오히려 값을 살짝 올려야 300m 안에서 계산이 온전히
   끝나는** 경우도 있음을 구체적 수치로 확인. **사용자의 현재 실측값(0.70)은
   고속(100km/h대)+큰 감속폭 커브 조합에서 이미 300m 캡에 걸릴 수 있는
   경계 근처**임을 신규 확인(NEEDS_VALIDATION, 실차 재현 필요).
5. **[중요] `AutoNaviSpeedDecelRate`는 route 커브 전용이 아니라
   과속카메라 감속(`sdi_speed`, `carrot_serv.py` L983)/TBT 회전 감속
   (`atc_desired`, L847)/도로제한속도 기반 감속(L994)까지 전부 공유하는
   단일 파라미터** — 이 값을 조정하면 커브 감속만이 아니라 이 셋 전부
   동시에 완만해짐(경고 필요, route 전용으로 분리하려면 별도 코드 변경 필요).

**코드 변경 없음(설명/계산만, patch 없음).**

**다음(사용자 결정 대기)**:
1. 위 4번 발견(현재 설정 0.70이 고속+큰 감속폭 조합에서 300m 캡에 걸릴
   가능성)을 실제 고속도로 급조임 커브 로그로 재현 검증할지.
2. route 전용으로 감속률을 분리하고 싶다면 `accel_limit =
   self.carrot_serv.autoNaviSpeedDecelRate` 줄을 신규 상수로 분리하는
   패치 설계(사용자가 아직 불채택 의사 표명, 필요시 재논의).
3. 300m lookahead 캡 자체를 늘리는 방향(비용/회귀 검증 필요, 아직 논의만
   된 상태, 코드 미착수).

## 다음 세션 시작 시
이 WIP.md에 "83차" 섹션이 있으면 이 지점부터 이어감 — 특히 4번(300m 캡
경계 문제) 실차 재현 검증 여부.

## 91차 (완료 — 구현+검증+패치 전달 완료, `git am`/실차 적용 대기) — route 사전감속을 vturn보다 먼저 시작(ROUTE_ENTRY_MARGIN_KPH)

**배경**: 90차(대안1, chord 축소)가 효과 미미로 기각된 이후, 89차 대안3
("저비용, 급조임 감지 시 목표속도에 안전마진(margin_kph)을 미리 차감하는
휴리스틱")을 이번 세션에서 구현·검증까지 완료. 사용자 확인: "route의
목표속도가 vturn과 비슷한건 좋은소식 — route가 사전감속을 vturn보다 더
일찍 시작하게만 만들면 만족".

**설계**: `carrot_navi_route()`의 역방향 DP에서, 감속 전환 시점
(`target_speed < next_out_speed`)의 `time_delay`(=필요 소요시간) 계산에만
`target_speed - ROUTE_ENTRY_MARGIN_KPH`(마진 차감한 값)를 사용 — **최종
채택되는 target_speed 자체(`min(target_speed, max_allowed_speed)`)는 전혀
안 바뀜, 오직 "감속 스케줄을 얼마나 일찍부터 반영하기 시작할지"만 앞당김.**
정점(apex) 목표값이나 원복(82차)측 로직은 완전히 무관.

**검증** (`toolkit/sim_route_curvature_sample.py` 기반 DP 로직을 margin
파라미터 추가해 재현, `devnotes/data/routes/bc4301a25d` 캐시로 검증 —
raw zip 재업로드 불필요):
- **margin_kph 0/10/20/30 스윕**(3초 그리드) → 커브A(89/90차 대상 구간,
  완만한 램프)에서 margin이 클수록 조기바인딩(목표속도<현재속도로
  전환되는 시점) 시점이 앞당겨짐 확인.
- **커브B(급한 램프+교차로, 89차부터 미검증으로 남아있던 구간, t≈9255~9291)
  교차검증**: margin=30까지도 접근 구간(커브 진입 훨씬 전)에서 불필요한
  조기 트리거(오탐) 없음 확인 — 회귀 안전.
- **직선 154초 구간(bc4301a25d 내 t=8545~8699, steer<2°, 130km/h대 순항,
  새 로그 업로드 없이 같은 캐시 라우트에서 발견) 오탐 검증**: margin=0~30
  전 구간 오탐 0건 — margin 로직이 "감속 전환이 실제로 일어나는 지점"에만
  적용되는 구조라 곡률 자체가 없는 순수 직선에서는 구조적으로 개입 불가능함을
  확인(89차 대안1의 "직선 구간 GPS 노이즈 오탐" 우려와는 다른 축, 이번
  방식은 그 리스크가 원천적으로 낮음).
- 사용자가 margin_kph=25.0(20/30 사이 절충값) 확정 → 0.5초 그리드 정밀
  재확인: **t≈9217.5부터 조기바인딩(vturn 실제 전환 t=9221.26보다 3.76초
  먼저), 최종 목표값도 vturn 실측치(73~77)에 근접(78.1~78.2)**.

**구현** (`c3-ms-curv`, 로컬 커밋 `2f5c23e`, base `cf32b5d`(87차 HEAD)):
`carrot_man.py`에 `ROUTE_ENTRY_MARGIN_KPH=25.0` 신규 상수 추가, 역방향 DP
루프의 `time_delay` 계산부만 수정(1줄 로직 변경 + 상수 1개). `py_compile`
통과, `git format-patch` → `verify-am-91` 임시 브랜치(base `cf32b5d`)에서
`git am`+diff 0(완전 동일) 확인.

**전달**: `0001-91-route-ROUTE_ENTRY_MARGIN_KPH-25.0.patch`를
`/mnt/user-data/outputs/`에 전달(base `cf32b5d`, 즉 현재 origin
`c3-ms-curv` HEAD 위에 바로 `git am` 가능).

**[갱신] 적용/push 완료 확인** — 사용자가 `C:\dev\ryu`에서 `git fetch`+
`git reset --hard origin/c3-ms-curv`(cf32b5d 동기화) 후 `git am` 적용
(컨텍스트 충돌 없이 바로 성공) + `git push origin c3-ms-curv` 완료.
컨테이너에서 `git fetch origin c3-ms-curv:refs/remotes/origin/c3-ms-curv`
후 로컬 검증 커밋과 diff 0(완전 동일) 재확인 완료. origin `c3-ms-curv`
HEAD: `cf32b5d..6d15391`. **다음은 실차 검증만 남음.**

**다음(최우선)**:
1. ~~사용자가 `C:\dev\ryu`(`c3-ms-curv` 브랜치)에서 `git am` 적용 +
   `git push origin c3-ms-curv`~~ → **완료**.
2. **실차 드라이브 검증** — (a) 커브 진입 시 route가 실제로 vturn보다
   먼저 개입하는 느낌(사전감속이 더 일찍 시작)이 드는지, (b) **회귀 검증
   필수** — 직선/완만한 구간에서 불필요한 조기 감속(오탐) 없는지(시뮬레이션
   상 0건이었으나 실제 GPS 노이즈 특성은 다를 수 있음), (c) 커브B류(TBT
   근접, 이미 route가 지배적이던 급한 커브)에서도 부작용 없는지.
3. `ROUTE_ENTRY_MARGIN_KPH=25.0`은 시뮬레이션 기준 채택값 — 실차 반응
   보고 튜닝 여지 있음(NEEDS_VALIDATION).
4. 81/82/84/85/87차(모두 `c3-ms-curv`, 아직 실차검증 대기 중)도 이번
   패치와 함께 같은 드라이브에서 동시 확인 가능.

## 92차 (완료 — 실차 로그 분석, 코드 변경 없음, **[정정] 91차 검증 아님, 패치 적용 이전 베이스라인으로 재분류**) — 국도 연속곡선 로그, 91차(ROUTE_ENTRY_MARGIN_KPH) 실차검증은 여전히 미완료

**[중요 정정, 사용자 확인]**: 이 로그는 **91차 패치 적용 이전**에 기록됨
(88차와 동일 유형의 오판 — meta.json commit 태그가 컨테이너의 현재
체크아웃 상태를 반영할 뿐, 로그 기록 당시 실제 차량 빌드가 아님을
간과함). 아래 원래 분석 내용의 관측 자체(수치/이벤트)는 유효하지만,
**"91차로 인한 회귀 없음"이라는 귀속 결론은 근거 없음 — 폐기**.
실제로는:
- seg16(t≈10676) "route 6초 조기개입" 관측은 91차 마진 패치가 아니라
  **82/84/85차(원복측 대칭버퍼/동적 lookahead 캡)까지만 반영된 상태**에서
  이미 나타나던 기존 동작. 91차 효과 증거로 사용 불가.
- turn_speed_violation 5건/harsh_brake 1건이 전부 `src=vturn`이었다는
  관측(vturn apex-lag 이슈, route 무관)은 그 자체로는 유효한 관측이지만
  **91차 적용 전 상태의 참고자료(baseline)**로 재분류.
- **91차 실차검증 항목(a 조기개입 체감/b 직선 오탐 회귀/c 커브B류 부작용)은
  여전히 미완료 상태로 유지.**

**활용 가치**: 이번 로그는 동일 구간(`0000032d--c0e3054c4a`)을 91차 적용
후 재업로드하면 `regression_report()`(analysis_helpers.py)로 직접
전/후 비교(harsh_brake율/turn_speed_violation율/route↔vturn 플리커율
delta_pct)가 가능한 좋은 "before" 샘플. `data/routes/`에 캐시 등록
고려 가능(사용자 결정 대기, 아직 미등록).

**교훈 강화**: 88차 이후에도 "meta.json commit = 실제 빌드"로 오판하는
패턴이 재발함 — 로그 폴더명의 타임스탬프와 후보 커밋들의 author date를
**분석 착수 직후 곧바로 비교**하는 절차를 세션 루틴에 명시적으로
추가할 필요(SETUP.md 갱신 검토 대상, 아직 미반영).

---

**(아래는 정정 전 원래 분석 내용 — 관측치 자체는 유효, 귀속 결론만 폐기)**

## 92차 원본(귀속 오류) — 91차(ROUTE_ENTRY_MARGIN_KPH) 국도 연속곡선 실차검증, **문제 없음으로 판정**

**배경**: 91차 패치(`6d15391`) 실차 적용 후 사용자가 국도 연속곡선 구간
로그(`0000032d--c0e3054c4a`, x7seg 실수신, 5.85km/420s, 평균 50.2km/h)를
업로드 → 91차 "다음(최우선) 2번" 실차검증(a 조기개입 체감/b 직선 오탐
회귀/c 커브B류 부작용) 수행 지시.

**[주의, NEEDS_CONFIRMATION]**: `extract_log.py` meta.json은
`commit_short=6d153913582d`(91차, 컨테이너 현재 체크아웃 상태)로 찍혔으나,
로그 기록 시각(2026-08-26 18:05~18:11)이 91차 커밋 author date
(2026-08-27T07:16:03+09:00)보다 약 13시간 앞섬 — 88차와 같은 종류의
커밋태그-실제빌드 불일치 가능성 있음(단정 불가, 사용자 확인 필요).
분석 자체는 로그 데이터 자체(raw route/vturn 거동)에 근거해 진행,
아래 결론은 태그 신뢰 여부와 무관하게 유효.

**방법**: `extract_log.py`로 CSV 추출(8401행) → `five_item_scan.py` +
`turn_speed_violations`/`harsh_brake_events`/`ttc_danger_events`/
`lead_cut_in_detector`/`source_pair_flicker_stats`(route↔vturn) 실행,
turn_speed_violation 5건 전부에 대해 이벤트 시각의 `src` 필드를
개별 대조, 급조임 커브(seg16, t≈10676~10684) 구간 전체 row를 시계열로
직접 검토, 직선 구간(steeringAngleDeg<3°) 오탐 후보 전수 스캔.

**핵심 결과**:
- **turn_speed_violation 5건 전부 `src=vturn`** — route가 담당하던
  구간에서 발생한 위반 0건. 최대(12.74km/h/3.7s, t≈10529)도 vturn
  목표속도 자체의 급조임(60→39km/h)이 원인으로, 기존 vturn apex-lag
  이슈(89/90차 연장선)와 동일 계열, 91차 route 로직과 무관.
- **harsh_brake 1건(사실상 단일 이벤트, t≈10570~10572)도 `src=vturn`** —
  감소반경 커브(조향각 0°→29° 연속 증가) 중 vturn 목표가 계속 조여지며
  MPC가 따라잡는 상황. route 개입과 무관, 회귀 아님.
- **직선 오탐(91차 회귀검증 b) 0건**: steeringAngleDeg<3°이면서 route가
  vCruise 대비 5km/h 이상 낮은 desiredSpeed를 vEgo보다 낮게 유도한
  후보 전수 스캔 결과 0건 — 91차 시뮬레이션 예측(구조적으로 직선에서
  개입 불가)과 실측 일치.
- **긍정 사례 확인(91차 의도 a)**: seg16 t≈10676.27부터 route가
  200km/h 순항 상태에서 desiredSpeed를 200→94(6초 만에 완만히)로 미리
  낮추기 시작, 최종 커브 제한(`bump` src, 76~80km/h)까지 vEgo가 급감속
  없이 자연스럽게 근접 — 91차가 노린 "조기 개입" 패턴과 정확히 일치하는
  사례 실측 확인.
- 안전지표: ttc_danger_events 0건, cut_in 0건. vision→radar crossover
  1건/radar_lockon_jerk 1건은 정상범위(리드감지 서브시스템, 91차와 무관).
- route↔vturn 플리커: 102회 전환/7분(14.57회/분), dwell 중앙값 0.5s —
  절대치 비교용 사전(91차 이전) 베이스라인 로그가 없어 이번 패치로 인한
  증감 여부는 판단 불가(NEEDS_VALIDATION, 향후 동일 구간 A/B 필요시
  참고). 다만 flicker 자체가 89/90차 등에서 이미 다뤄온 기존 패턴과
  질적으로 다르지 않음(짧은 dwell 다수 — 기존 하드스위치 특성).

**결론**: 이번 국도 연속곡선 로그에서 91차 패치로 인한 새로운 문제(회귀)는
발견되지 않음. 관찰된 모든 turn_speed_violation/harsh_brake는 기존부터
알려진 vturn apex-lag 이슈로 귀속되며 route 쪽 원인 없음. 직선 오탐 0건으로
회귀 우려 해소. 조기개입 의도 동작도 최소 1개 구체 사례로 실측 확인됨.
**코드 변경 없음(분석만).**

**다음**:
1. 로그 기록시각-커밋일시 불일치건 사용자 확인(위 NEEDS_CONFIRMATION).
2. 91차 남은 항목 c(커브B류, TBT 근접 급커브에서의 부작용) — 이번
   로그가 저속 국도 위주라 고속 TBT 근접 커브 표본이 약함, 별도 로그
   필요시 재검증.
3. route↔vturn 플리커 절대 증감은 여전히 미확정 — 필요시 91차 적용
   직전 동일구간 로그 확보되면 `regression_report()`로 정량 비교 가능.
4. 81/82/84/85/87차 실차검증도 이번 로그로 함께 관찰 가능(별도 항목
   변화 없음, 특이사항 없음).
