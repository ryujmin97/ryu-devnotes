## 63차 계속7 (체크포인트 — 2단계 완료: dPath/yRel 연속성 확인, 인접차선 오검출 가설 사실상 기각)

**2단계 완료**: seg14 vision-only 구간(t=921.0~925.35, 레이더 락온 전)
동안 `leadDPath`/`leadYRel` 연속성을 dRel 점프와 대조.

**핵심 결과**:
- `leadDPath` range: **-0.486m ~ +0.024m** (구간 전체) — 인접차로 판정
  기준(37차 `SCC_FALLBACK_DPATH_GATE=2.0m`/60차 A `VISION_TRACK_
  TENTATIVE_DPATH_ABS_GATE=1.75m`)보다 훨씬 작은 값. 시종일관 자차
  차로 중심 부근에 위치 — 옆차로 물체가 섞여 들어온 흔적 없음.
- 프레임간 최대 `dPath` 변화량: **0.156m**. 반면 같은 구간 프레임간
  최대 `dRel` 변화량은 **11.54m**(t=924.047, 53.05→41.51m). **dRel이
  11.5m 튀는 순간에도 dPath는 거의 안 움직임** — "다른 물체로
  전환(트랙 스왑)"이라면 dPath도 함께 크게 튀어야 하는데 그렇지
  않음.

**결론(잠정, 신뢰도 높음)**: 63차 계속4에서 세운 "트랙 전환(인접차로
오검출/스왑)" 가설은 **사실상 기각**. seg14의 반복 discontinuity는
**동일한 하나의 물체(자차 차로 내 실제 선행차)에 대한 vision 거리
(depth) 추정 자체의 불안정/노이즈**로 재확정됨 — 이는 63차 계속3의
원래 관찰(leadVRel은 -0.8~-3.2m/s로 온건한데 raw dRel 미분만 -230m/s급)
과 정합적이며, 그 원인이 트랙 스왑이 아니라 **단일 물체의 depth
추정 노이즈 자체**임을 이번에 dPath로 명확히 뒷받침.

**부가 발견(신규, 중요) — 사용자 제보와 정합**: 같은 구간 `leadVLead`/
`vRel`/`aLeadK`를 보면, **레이더 락온 순간(t=925.351)** `leadVRel`이
음수(-2.1, closing)에서 **양수(+3.2~+4.3, opening)로 급반전**하고
`aLeadK`도 +2.2까지 치솟음 — **선행차가 실제로 자차보다 빠르게
가속해 멀어지기 시작하는 순간과 정확히 일치**(사용자가 제공한
"끼어드는 차량이 내차보다 가속" 정보와 부합). 단, **급감속(aEgo 최저
-4.29m/s², t=925.148)은 이 가속 이탈이 레이더로 확인되기 *직전*,
아직 vision 단독 단계에서 이미 발생** — 즉 시스템은 "곧 가속해서
멀어질 차"를 vision 단계의 노이즈성 급접근 신호 때문에 미리 과잉
제동한 셈. 이 두 현상(vision 노이즈로 인한 과잉제동 + 직후 실제
가속이탈 확인)은 서로 다른 시점의 별개 현상이며, 방안 설계 시
혼동하지 않아야 함.

**다음(3단계, 최우선)**: qcamera 프레임으로 t=923.0~925.35 구간을
시각 대조 — (a) 이 구간 화면상으로도 선행차가 실제로 그렇게 급격히
접근하는 것처럼 보이는지(노이즈 vs 실제 접근 재확인), (b) 락온 직후
가속 이탈이 영상으로도 확인되는지(사용자 제보 최종 검증).

**세션 종료 아님 — 중단지점 저장.**

## 63차 계속6 (체크포인트 — 1단계 완료: seg14 신규 컬럼 추출, radarTrackId 확인)

**1단계 완료**: 사용자가 재업로드한 원본 zip에서 seg14만 분리 →
신규 `extract_log.py`(dPath/yRel/aLeadK/radarTrackId 포함판)로 재추출
(`/home/claude/work/route63b/seg14.csv`, 1200행, commit `4ea63c3`).
discontinuity 구간(t=921~926) 프레임 단위 확인 완료.

**radarTrackId 확인 결과 — 예상과 다름, 중요**: t=918~930 구간에서
`leadRadarTrackId`는 `-1`(vision-only, 미정의) 또는 `0`(레이더 락온 후)
단 두 값만 존재. **레이더 락온 전(vision-only, t<925.351) 구간 내내
`-1` 고정** — 즉 이 필드는 vision 단계 내에서의 "트랙 전환"(다른 물체로
넘어감) 자체를 구분할 수 있는 필드가 아님(radard.py가 vision track에
개별 ID를 부여하지 않고 vision-only인 동안은 항상 -1로 채움). **63차
계속4에서 세운 "radarTrackId 변화로 트랙 스왑 여부 확인" 계획은 이
필드로는 직접 검증 불가능함이 확인됨** — 대신 dPath/yRel의 연속성으로
간접 판단해야 함(다음 단계).

**세션 종료 아님 — 중단지점 저장, 바로 2단계(dPath/yRel 연속성 분석)로 이어감.**

## 63차 계속5 (체크포인트 — 원본 zip 재업로드 확인, 토큰절약 위해 분석은 다음으로 미룸)

**배경**: 63차 계속4에서 요청한 r1-3/r1-14 원본 데이터셋을 사용자가
재업로드함(`drive-download-20260824T072553Z-1-001.zip`, 61차 당시와
동일한 16세그 전체 셋 — route1 `a2141d7786` seg1/3/6/9/12/14/15/17/19
(9세그) + route2 `6f02a46c8a` seg1~7(7세그), 각 세그에 qcamera.ts+
rlog.zst+qlog.zst+화면녹화 clip 포함). **seg14 폴더에 "cutin 급감속_
택시" clip 존재 확인** — 63차 계속3/4에서 다루던 바로 그 r1-14 이벤트의
원본으로 사용 가능. 사용자가 토큰 절약을 위해 지금은 분석하지 말고
중간 저장만 요청.

**다음 세션(또는 다음 메시지) 최우선 — 압축 안 풀고 바로 여기서 시작**:
1. zip은 `/mnt/user-data/uploads/drive-download-20260824T072553Z-1-001.zip`
   에 그대로 있음(이번 세션에서 목록만 확인, 압축 해제/추출 안 함).
2. seg14(`20260824_155128_00000317--a2141d7786--14`) 먼저 `extract_log.py`
   (신규 dPath/leadYRel/leadALeadK/leadRadarTrackId 컬럼 포함판, 63차
   계속4에 push 완료)로 추출 → t=923.10~923.50 부근(같은 route 재현이면
   유사 시각대) discontinuity 구간에서 `leadRadarTrackId` 변화 여부 확인
   → 트랙 전환 가설(63차 계속4) 검증.
3. seg14 qcamera.ts로 해당 구간 프레임 대조(`verify_and_extract_frames.py`)
   — 사용자가 말한 "끼어드는 차량이 내차보다 가속" 상황이 영상으로도
   보이는지 확인.
4. 트랙 전환 확정되면 방안 E 설계(63차 계속4 "다음" 4번 참고) 착수.
5. seg14 외 나머지 15세그(특히 r1-3=seg3)도 필요시 같은 절차로 재검증
   가능(61차 당시와 동일 데이터셋이므로 61차 qcamera 대조 결과와 대조 가능).

**코드/devnotes 변경 없음(이번 메시지는 상태 저장만)**.

**세션 종료 아님 — 중단지점 저장.**

## 63차 계속4 (체크포인트 — dPath/radarTrackId 컬럼 추가 완료, 사용자 신규 정보로 가설 갱신, 원본 rlog 재업로드 대기)

**배경**: 63차 계속3의 최우선 과제(1번, dPath 컬럼 추가)를 이번 세션에서
착수. 동시에 사용자가 **"로그에서 끼어드는 차량이 내차보다 가속되는
상황"**이라는 신규 정보를 제공 — seg14(t=923.10~923.50, 7회 연속
discontinuity) 이벤트가 인접차선 오검출이 아니라 **실제 cut-in 이벤트이고,
끼어든 차량이 자차보다 빠르게 가속해 멀어지는 상황**이었을 가능성을 시사.

**조치**: `extract_log.py`에 `leadDPath`/`leadYRel`/`leadALeadK`/
`leadRadarTrackId`(RadarState.LeadData 필드) 4개 컬럼 신규 추가.
`py_compile` 통과. README.md/CHANGELOG.md 동기화 완료.

**가설 갱신(중요, 미확정)**: 사용자 정보가 맞다면 seg14의 반복
closing/opening 패턴은 다음처럼 재해석 가능 —
1. cut-in 차량이 진입하는 순간 기존에 추적 중이던(더 먼) 리드와 새
   cut-in 차량 사이에서 트랙이 왔다갔다 흔들리며(radarTrackId 전환)
   dRel이 요동쳤을 가능성. 순수 vision 노이즈(단일 물체의 추정 오차)
   보다 **트랙 스왑(다른 물체로의 전환)**이 원인일 가능성이 높아짐.
2. 이후 "가속해 멀어짐"이 사실이면, discontinuity 종료 후 실제
   dRel이 다시 벌어지는(opening) 것 자체는 정상 물리 현상 — 문제는
   그 직전 트랙 전환 구간에서 `_vision_dRel_rate`가 오염되는 것.
3. 이는 63차 계속3에서 발견한 **"aEgo 최저치 시점에 PATCHED=UNPATCHED=
   1.0으로 완전 동일"** 현상과도 부합: 트랙 전환으로 오염된 값이 방안
   C/D의 타이머 리셋과 무관하게(`_lead_acq_timer`만 리셋, `_vision_
   dRel_rate` 자체는 안 건드림 — 방안C) 또는 리셋해도 즉시 재유입
   (방안D) 계속 살아남는 것과 일치.

**아직 확정 불가 — radarTrackId 실측 필요**: 위는 사용자 정보 기반
추정이며, 이번 세션엔 원본 rlog가 없어(컨테이너 재시작으로 유실,
`/mnt/user-data/uploads/` 비어있음) 검증 못함. **다음(최우선)**:
1. r1-14(route `a2141d7786` seg14, 가능하면 qcamera 포함) 원본 rlog
   재업로드 요청 → 새 컬럼(`extract_log.py`)으로 재추출.
2. t=923.10~923.50 구간에서 `leadRadarTrackId`가 실제로 바뀌는지
   확인 — 바뀌면 "트랙 전환" 가설 확정, 안 바뀌면 단일 물체 vision
   노이즈 가설(기존 63차 계속3 잠정 결론) 쪽으로 복귀.
3. `leadDPath`로 cut-in 전/중/후 궤적이 차로 안으로 들어오는 패턴과
   일치하는지 시각적으로도 확인(사용자 "가속 이탈" 설명과 정합성).
4. 트랙 전환 확정 시 **방안 E 설계 방향 구체화**: `radarTrackId` 변화
   자체를 discontinuity 트리거 조건에 추가(현재 `DREL_DISCONTINUITY_
   DROP_THRESH`는 dRel 절대 변화량만 봄 — trackId 변화를 직접 감지하면
   더 정확하고 조기에 잡을 수 있음). danger override는 여전히 무관하게
   유지.

**코드 변경**: `devnotes/toolkit/extract_log.py`/`README.md`/
`CHANGELOG.md`만 변경. **ryu 코드는 여전히 미변경**(방안D는 63차
계속3에서 이미 폐기, 방안E는 트랙 전환 확정 전까지 설계 보류).

**세션 종료 아님 — 중단지점 저장.**

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

## 63차 계속3 (방안 D 구현·재생검증 완료 — 방안 D는 폐기, 방안 E/dPath 확인이 신규 최우선)

**배경**: 63차 체크포인트2에서 설계했던 방안D(discontinuity 트리거 시
`_vision_dRel_rate`/`_vision_dRel_rate_window`도 함께 리셋)를 실제
구현하고 seg3/seg14로 재생검증(`work/route63/replay_drel_
discontinuity_d.py` 신규 — 이전 스크립트는 저장 전 세션 중단으로
유실, 동일 로직으로 재작성).

**핵심 결과**:
- seg3: 방안D 추가효과 없음(방안C만으로 이미 충분, 기존 결론 유지).
- seg14: **방안D도 사실상 무효** — discontinuity가 1회가 아니라
  t=923.10~923.50 사이 7회 연속 재트리거됨. 리셋해도 그 직후 다시
  큰(-30m/s 클램프) raw_rate가 연속 유입돼 median 필터가 즉시
  재수렴, discontinuity 종료 0.55초 후(t=924.047)엔 이미 UNPATCHED/
  PATCHED_C와 같은 프레임에 frac_rate=1.0 재포화. aEgo 최저치
  (t=925.148) 시점엔 방안D도 완전히 동일값(1.0).

**[신규 발견] raw dRel 신뢰성 자체가 의심스러움**: 이 구간 dRel
변화량이 프레임당 최대 -230m/s(물리적으로 불가능)에 달하고 방향이
반복적으로 뒤집힘(closing→opening→closing...). qcamera 프레임 육안
비교(t=923.10/923.30/924.00)로는 차량이 이 구간 동안 뚜렷이 가까워
지는 것처럼 안 보임(단, 저해상도라 결정적이진 않음 — 보조 정황).
leadVRel(모델 자체 추정)은 -0.8~-3.2m/s로 훨씬 온건해 raw dRel
미분과 크게 괴리. **인접차선 오검출(dPath 미확인 상태)이거나 vision
dRel 추정 자체의 노이즈/불안정 중 하나로 추정, 미확정.**

**다음(최우선, 갱신)**:
1. **extract_log.py에 dPath 컬럼 추가** — 이 구간이 인접차선 차량
   오검출인지부터 먼저 확인(원인 특정 없이 완화 로직부터 만들면
   잘못된 방향으로 갈 위험).
2. dPath로 인접차선 오검출 아닌 걸로 확인되면 **방안 E**(반복
   재트리거 시 frac_rate 성분 일시 무력화/상한) 설계 착수 — danger
   override는 항상 무관하게 유지되도록 신중히 설계.
3. **방안D는 폐기/우선순위 하향** — 더 이상 이 방향으로 시간 쓰지
   않음.
4. 실차 검증(사용자) 시: r1-3류는 방안C로 개선 체감 가능성 높음,
   r1-14류는 방안C/D 어느 쪽으로도 무개선일 가능성 높다는 점 미리
   인지.

**코드 변경 없음(ryu 미변경)**. `work/route63/replay_drel_
discontinuity_d.py` 신규(toolkit 미편입, 방안 미확정 상태 스크래치
유지). `work/route63/frames_seg14/`, `frames_seg14b/`(qcamera 프레임,
커밋 안 함).

**세션 종료 아님 — 중단지점 저장.**
