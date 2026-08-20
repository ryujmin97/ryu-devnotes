# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

- 저장 시각: 2026-08-20 (17차, 정상 zip 재업로드로 16차 재검증 +
  vision-only closing-rate 크로스체크(`b403d52`) 최초 실측 검증
  완료, 코드 변경 없음.

## 17차 갱신 — 16차 재검증 + b403d52(비전 클로징레이트) 첫 실측
- 16차의 zip 손상 이슈 해소(정상본 재업로드, 19세그 전체) — 13차
  model 게이팅 vturn↔model 플리커 감소가 63~69%로 더 뚜렷하게
  재확인됨.
- **신규**: 사용자가 "카메라 인식 시부터 감속 시작하도록 반영한
  패치도 분석 필요"라고 요청 — 이건 6차에서 이미 작성/적용된
  `b403d52`(long_mpc vision-only closing-rate 크로스체크) 패치를
  가리킴, 신규 커밋 아님(git fetch로 원격에 새 커밋 없음 확인).
  이번이 그 패치의 **실차 적용 후 첫 실측 검증** — closing 크로스오버
  6건 전부 레이더 확인 순간 aEgo 급변 없이 매끈하게 이어짐 확인,
  패치 의도대로 동작 중인 것으로 보임.
- 상세는 FINDINGS.md "[VALIDATED] 재업로드... 17차" 참고.

## 다음 세션에서 이어갈 것 (17차 갱신 최우선)
1. **260819-6 seg15급 초장거리(7~8초/90m대, modelProb 0.5대) 극단
   사례 재확보** — b403d52 검증에서 아직 이 등급은 재현 못함. 고속도로
   위주로 먼 거리 서행/정지차가 나오는 구간 재주행 로그 필요.
2. **장시간 정속 커브 구간 로그 확보** — 13차 model 게이팅의 남은
   한계, 고속도로/국도 완만한 커브가 길게 이어지는 구간 필요.
3. road/route 등 나머지 min() 히스테리시스 쌍 설계 착수(여전히 미해결).
4. screenrecord clip 롤오버 패치(`591f219`) 실측 — 화면녹화 켜둔 채
   20분+ 주행 형태로 별도 확인 필요.
5. opening/flat 크로스오버(비전 먼저 인식했지만 위험하지 않은 케이스)
   에서 b403d52 패치가 불필요 개입 안 하는지 — 6차부터 이어지는 과제,
   여전히 미확인.

## 16차 갱신 — 패치 후 첫 실주행 로그로 model 게이팅 부분 검증
- route `4fe653914c`(9분)/`a5f42c2218`(16분), 둘 다 HEAD `591f219`
  (13차+14/15차 패치 모두 반영) 상태에서 기록된 첫 실주행 로그.
- **업로드 zip 2개 모두 중간 구간 손상**(zstd CRC 불일치) — route1
  세그5~14, route2 세그7~9 유실. 손상분 제외한 정상 구간만 분석,
  재분석 필요하면 해당 구간 재업로드 요청.
- vturn↔model 전환 빈도가 패치 전 베이스라인(7.0/min) 대비 약
  57~60% 감소(2.78~3.0/min) 확인 — 패치 의도대로 작동 중인 것으로
  보임. turn_speed_violation 0건, ADAS 활성 중 harsh_brake 사실상
  0건 유지, 신규 이슈 없음.
- **아직 미검증으로 남은 것**: (1) 장시간 정속 커브 부작용(13차
  알려진 한계) — 이번 로그가 시내 위주라 검증 못 함, 고속도로 장거리
  완만한 커브 로그 필요. (2) road↔vturn/route↔vturn 등 model 외
  나머지 쌍 히스테리시스 — 이번 로그에서도 여전히 빈번히 재현,
  미해결 그대로.
- 상세는 FINDINGS.md "[VALIDATED, 부분 확인] model_turn_speed 추세
  게이팅... 16차" 참고.

## 다음 세션에서 이어갈 것 (16차 갱신 최우선)
1. **장시간 정속 커브 구간 로그 확보** — 고속도로/국도 완만한 커브가
   길게 이어지는 구간 실주행 로그(줌 재업로드 또는 신규 주행)로
   model 조기 배제 부작용 여부 마저 확인.
2. road/route 등 나머지 min() 히스테리시스 쌍 설계 착수(여전히 별도
   과제로 대기, PARAMS_REGISTRY.md 참고).
3. screenrecord clip 롤오버 패치(`591f219`) 실측 — 이번 dashcam
   로그로는 검증 불가(별도 기능), 화면녹화 켜둔 채 20분+ 주행 형태로
   따로 확인 필요.

- 저장 시각: 2026-08-20 (15차, screenrecord clip 롤오버/타임스탬프
  패치 — **실차 `git am` 적용 + push 완료 확인**, commit `591f219`
  (`119b101..591f219`). 실측 검증만 남음.

## 15차 갱신 — screenrecord clip 롤오버/타임스탬프 패치 실차 적용 확인
- 14차에서 작성한 패치를 사용자가 실차에서 `git am` 적용 + `git push`
  완료 확인 (원격 커밋 `591f219`, 원격 fetch로 diff 동일 재확인).
  코드 변경 없음(devnotes 동기화만).
- 상세는 FINDINGS.md "[PATCH_APPLIED, NEEDS_VALIDATION] screenrecord
  clip(commit `0f7575f`) ... 15차 실차 적용 확인" 참고.

## 다음 세션(또는 이 세션 재개)에서 이어갈 것 (15차, 최우선 — 실측만 남음)
1. **screenrecord clip 패치 실측** — 화면녹화 켜둔 채 20분+ 주행 시
   자동 롤오버에서 clip이 더 이상 생성되지 않는지, 정지 버튼으로는
   여전히 정상 생성되는지, 가능하면 토글 연타로 `_clip_2.mp4` 폴백
   동작 확인.
2. **13차(model 게이팅) 실측 검증** — 위 13차 섹션 항목 그대로
   (플리커 감소 + 진입 전 사전감속 정상 작동 + 장시간 정속 커브
   부작용 확인).
3. atc/road/route 등 나머지 min() 히스테리시스 쌍은 여전히 미해결
   (PARAMS_REGISTRY.md 참고).

- 저장 시각: 2026-08-20 (14차 갱신, screenrecord clip 버그 2건 —
  **패치 작성 + `git am` 시뮬레이션 검증 완료, 실차 적용 대기**)

## 14차 갱신 — screenrecord clip 버그 2건 패치 완료 (실차 적용 대기)
- 문제 1(20분 자동 롤오버에서도 clip 반복 생성)/문제 2(초 단위
  타임스탬프 충돌) 모두 설계 합의대로 구현 완료.
- **구현**: `stop_locked(bool auto_rollover = false)` 시그니처 변경,
  롤오버 호출부만 `stop_locked(true)`로 clip 추출 스킵.
  `extract_trailing_clip()`에 `stat()` 충돌 체크 + `_clip_2`,
  `_clip_3`... 접미사 폴백 추가(정상 케이스는 기존과 동일).
- 컨테이너 ryu 클론에서 커밋 생성(base `119b101`, HEAD 반영), 별도
  임시 브랜치에서 `git am` 적용 시뮬레이션 통과 확인.
- **패치 파일**: `/mnt/user-data/outputs/0001-screenrecord-clip-rollover-fix.patch`
  (`git format-patch` 형식). **실차 미적용** — 사용자 `git am` 적용
  대기.
- 상세 근거/구현 diff는 FINDINGS.md "[PATCH_WRITTEN, NEEDS_VALIDATION]
  screenrecord clip(commit `0f7575f`) ... 14차 패치 작성" 참고.

## 다음 세션(또는 이 세션 재개)에서 이어갈 것 (14차, 최우선)
1. **실차 `git am` 적용 + push 대기** — 위 패치 파일.
2. 적용 후 실측: (a) 화면녹화 켜둔 채 20분+ 주행 시 자동 롤오버에서
   clip이 더 이상 생성되지 않는지, (b) 정지 버튼으로는 여전히 정상
   생성되는지, (c) 토글 연타로 같은 초에 정지가 겹치는 상황 재현이
   가능하면 `_clip_2.mp4` 폴백이 실제로 동작하는지 확인.
3. 10차(screenrecord clip 원 기능)/13차(model 게이팅) 실측 검증도
   여전히 별도 트랙으로 대기 중(아래 각 섹션 참고).

## [이전 기록] 14차 설계 합의 시점 메모 (패치 작성 완료로 해소, 보존용)
- 합의된 방향(위 "14차 갱신"에 그대로 구현됨): stop_locked에
  auto_rollover 플래그 추가, 타임스탬프 해상도는 초 단위 유지 +
  stat() 충돌 체크로 접미사 부여(분 단위 대안은 기각).

- 저장 시각: 2026-08-20 (13차, 사용자 "저장" 요청 — **model 게이팅
  재설계 패치 실차 `git am` 적용 + push 완료 확인**, commit `119b101`
  (`0f7575f..119b101`). 실측 검증만 남음.

## 13차 갱신 — model 게이팅 desiredCurvature -> model_turn_speed 추세 재설계 (패치 완료, 실차 적용 확인)
- 이 패치는 12차(직전 세션)에서 이미 설계/작성됐으나 그 세션이
  WIP.md 갱신 전에 끝나 여기 반영이 누락되어 있었음(FINDINGS.md/
  PARAMS_REGISTRY.md/LAST_ANALYZED.md에는 12차 기록이 이미 있었음 —
  WIP.md만 유실). 이번 세션에서 사용자가 실차 적용 결과를 보고,
  devnotes 전체를 최신 상태로 동기화.
- **배경**: 9차(아래 옛 섹션 참고)에서 도입한 `desiredCurvature`
  (현재 곡률) 기반 model 게이팅이, 커브 진입 직전 직선 구간에서
  model의 사전감속(lookahead) 기여까지 억제할 위험이 있다는 게
  11차 코드 재검토로 확인됨(FINDINGS.md `[RISK_IDENTIFIED]` 참고).
- **재설계**: `desiredCurvature` 대신 `model_turn_speed` 자기 자신의
  추세(최근 hold_sec 동안 노이즈 허용폭(0.3km/h)을 넘는 감소가
  한 번도 없었는지)로 "트레일링(커브를 이미 빠져나와 복귀 중)"만
  판별해 배제. 커브 접근 중 사전감속 시도(=하강 중)는 단 한 프레임의
  유의미한 하강만 있어도 즉시 카운터 리셋되어 배제되지 않음(비대칭
  설계 유지). 상수: `model_turn_speed_noise_tol`(0.3km/h),
  `model_turn_straight_hold_sec`(0.6s, 기존값 유지) — `carrot_serv.py`.
- **패치 파일**: `/mnt/user-data/outputs/0001-carrot_serv-model-desiredCurvature-model_turn_speed.patch`.
  **실차 `git am` 적용 + push 완료** (commit `119b101`, `C:\dev\ryu`).
- **알려진 한계(실측 필요)**: 장시간 정속 커브(model_turn_speed가 낮은
  값에서 정체)에서 model이 조기 배제되지 않는지 — vturn/route가 동일
  커브를 이미 커버하므로 위험은 낮다고 판단하나 실측 필요.
- 상세 근거/구현 diff는 FINDINGS.md "[PATCH_APPLIED, NEEDS_VALIDATION]
  model 게이팅을 desiredCurvature -> model_turn_speed 추세 기반으로
  재설계" 참고.

## 다음 세션(또는 이 세션 재개)에서 이어갈 것 (13차, 신규 최우선)
1. **model_turn_speed 추세 게이팅 실측 검증** — 유사 구간(국도 완만한
   커브 연속, 260819-4 세션 model↔vturn 우세 구간) 재주행,
   `source_transition_log`로 vturn↔model 플리커 감소 확인 + 커브
   진입 직전 model 사전감속이 더 이상 억제되지 않는지(9차 패치 대비
   개선 확인) 함께 확인.
2. **장시간 정속 커브 부작용 확인** — model_turn_speed가 낮은 값에서
   오래 정체되는 구간(고속 완만한 커브 장거리)에서 model이 조기
   배제되는지, 그 경우 vturn/route가 대신 적절한 값을 주고 있는지.
3. 10차(screenrecord clip)는 아래 섹션대로 여전히 실측 검증 대기,
   9차 옛 항목(desiredCurvature 기반)은 13차로 완전히 대체됨 —
   아래 9차 섹션은 기록 보존용으로만 남기고 "다음 세션 이어갈 것"
   에서는 제거.

- 저장 시각: 2026-08-20 (10차 갱신, screenrecord "정지 시 마지막 1분
  clip 자동 생성" — **실차 `git am` 적용 + push 완료 확인**, commit
  `0f7575f` (`2226db7..0f7575f`). 실측 검증만 남음.

## 10차 갱신 — screenrecord 정지 시 마지막 1분 clip 자동 생성 (패치 완료, 실차 적용 대기)
- 최초 설계(링버퍼, 아래 "10차 최초 설계" 참고)는 사용자가 더 간단한
  대안으로 대체: **"정지 버튼 누르면 기존처럼 메인 mp4가 정상
  종료되고, 그 직후 해당 파일에서 마지막 1분만 잘라 별도 clip으로
  생성"** — 메모리/구현 복잡도 모두 낮음.
- **구현**: `screenrecorder.cc::stop_locked()`에서 `closeEncoder()`로
  메인 mp4가 finalize된 직후, 그 경로를 `ffmpeg -y -sseof -60 -i
  <원본> -c copy <clip>` (QProcess::startDetached, non-blocking,
  fire-and-forget)로 백그라운드 실행해 마지막 ~60초를 stream copy로
  추출. `OmxEncoder::get_last_video_path()` 신설(finalize된 파일 경로
  조회용).
  - clip 파일명: `<YYMMDD_HHMMSS>_clip.mp4` (정지 시각 기준, `_clip`
    접미사) — 목록에서 구분 용이.
  - 저장 위치: 메인과 같은 폴더(`/data/media/0/videos`) → carrotweb
    로그탭 화면녹화 목록에 자동으로 같이 뜸.
  - 녹화 길이가 1분 미만이어도 항상 clip 생성(전체 길이만큼 잘림,
    스킵 안 함) — 사용자 요청대로 구분 용이 우선.
  - `-c copy`(재인코딩 없음)라 실제 클립 길이는 키프레임 간격 때문에
    정확히 60.000초가 아니라 약 60.0~60.8초 범위(고지 완료).
  - ffmpeg 실패(바이너리 없음/원본 파일 문제)해도 메인 녹화 파일에는
    영향 없음(독립 프로세스, fire-and-forget).
- **검증**: 컨테이너 `ryu` 클론에서 실제 커밋 생성(base `2226db7`,
  로컬 커밋 해시는 세션마다 재현 시 달라질 수 있음 — 패치 내용은
  동일) → `git format-patch -1`로 추출 → 임시 브랜치에서 `git am`
  적용 시뮬레이션 통과 확인. C++ 컴파일 자체는 컨테이너에 빌드
  툴체인이 없어 불가 — 코드 리뷰 + `git apply --check`/`git am`
  검증까지만.
- **패치 파일**: `/mnt/user-data/outputs/0001-screenrecord-1-clip.patch`
  (`git format-patch` 형식). **실차 `git am` 적용 + push 완료**
  (commit `0f7575f`, `C:\dev\ryu`).
- ⚠️ **직전 세션 유실 이력**: 이 패치는 실제로 한 번 더 앞서 작성된
  적이 있으나(동일 diff, 커밋 해시만 다름) 그 세션이 devnotes push
  전에 종료되어 WIP.md/PARAMS_REGISTRY.md에 반영이 안 된 채 유실됨.
  이번 세션에서 대화 내용에 남아있던 전체 diff를 그대로 재현하고
  다시 검증해 이 항목으로 정리함. **앞으로는 코드 커밋 직후 바로
  devnotes push까지 한 번에 끝내는 것을 우선한다** (검증만 하고 push를
  미루지 않기).

## 다음 세션(또는 이 세션 재개)에서 이어갈 것 (10차, 최우선 — 남은 건 실측뿐)
1. 실차 검증: 녹화 정지 → 메인 mp4 정상 생성 확인 → 같은 폴더에
   `<시각>_clip.mp4`가 뒤이어 생기는지, 길이가 대략 60~61초인지,
   1분 미만 녹화에서도 정상 생성되는지 확인.
2. ffmpeg 디바이스 내 실제 경로/버전 확인(PATH 상 `ffmpeg`로 바로
   실행 가능한지, 안 되면 절대경로로 수정 필요할 수 있음 — 미확인).

## 10차 최초 설계 (참고용, 위 ffmpeg 방식으로 대체됨 — 채택 안 함)
- 최초 검토안: 링버퍼 방식 — `handle_out_buf`에서 최근 ~65초 h264
  패킷(인코딩된 상태로 ~15MB, raw RGBA는 ~4.8GB라 불가)을 별도
  링버퍼에 같이 저장, 트리거 시 두 번째 `AVFormatContext`로 mux.
  트리거 채널 후보로 `annotated_camera.cc`의 기존 `carrotCmd ==
  "RECORD"` 커맨드 채널에 `"CLIP"` 추가하는 방식도 검토했었음.
  → 사용자가 "정지 버튼 + 사후 ffmpeg 추출"이 더 간단하다고 판단해
  이 방식은 폐기, 채택 안 함. (트리거가 이벤트가 아니라 "정지" 하나로
  단순화됨.)

- 저장 시각: 2026-08-20 (9차, vturn↔model 플리커 게이팅 패치 실차 적용
  + push 완료 확인 — `git am` commit `2226db7`)
- HEAD (c3-ms-dev): **`2226db7`** — `1fca82f..2226db7` push 완료
  확인됨(원격 fetch로 재확인). 코드 변경은 완결, 실측 검증만 남음.

## 9차 완료분 — vturn↔model 플리커: model 후보 desiredCurvature 게이팅 (실차 적용 + push 완료)
- 사용자 요청: "desiredCurvature가 일정 시간 이상 직선을 유지하면 model
  후보를 min()에서 일시 배제(또는 하한선) — vturn/route가 이미 갖고
  있는 '회전 종료' 판단 근거를 model에도 공유하는 방식으로 가자."
- 기존 근거: FINDINGS.md의 "src/desiredSpeed 플리커 — vturn↔road/model/
  route 전환에서 대규모 재현" (x20seg, A→B→A 49건) + 260819-4 세션
  집계(우세 쌍 model↔vturn 140건).
- 구현: `carrot_serv.py`에 `model_turn_straight_thresh`(0.002,
  desiredCurvature 임계값) / `model_turn_straight_hold_sec`(0.6s) /
  `model_turn_straight_count`(연속 직선 프레임 카운터, 20Hz 기준) 신설.
  `sm['modelV2'].action.desiredCurvature`가 hold_sec 이상 연속으로
  threshold 미만이면 그 프레임의 "model" 후보를 `speed_n_sources`에서
  완전 배제(하한선 아님). 곡률이 threshold를 다시 넘으면 카운터
  즉시 리셋 → model 후보 지연 없이 복귀(비대칭 설계, 커브 진입 반응은
  안 늦춤).
- `py_compile` 통과. **실차 적용 + push 완료** (`git am`, commit
  `2226db7`).
- 커밋 이력 보존 방식으로 재작성: 컨테이너 ryu 클론에서 실제 커밋
  생성(`ab703fb`, base `1fca82f`) 후 `git format-patch -1`로 재추출
  (기존에 `git diff`로만 뽑았던 1차 시도는 커밋 없는 순수 diff라 폐기 —
  사용자 지적으로 항상 커밋 이력이 남도록 수정). `git am` 적용
  시뮬레이션(임시 브랜치)으로 검증 완료, `py_compile` 재확인.
- 패치 파일: `/mnt/user-data/outputs/model_turn_straight_gate.patch`
  (`git format-patch` 형식). 사용자가 `git am` 1차 시도로 이미
  적용+push 완료(`2226db7`). 이후 실수로 동일 패치 재적용 시도가
  실패했으나(이미 적용된 상태라 정상적인 실패, `git am --abort`로
  정리 안내) push 자체는 1차 적용분으로 정상 반영됨.

## [SUPERSEDED, 13차로 대체됨] 9차 시점 "다음 세션에서 이어갈 것" — 기록 보존용, 재작업 불필요
> 아래 1~2번은 desiredCurvature 기반 게이팅(9차, `2226db7`) 검증
> 계획이었으나, 그 게이팅 자체가 11차 코드 재검토로 위험 확인되어
> 12~13차에서 model_turn_speed 추세 기반으로 완전히 대체됨. 실측
> 검증은 위 "13차, 신규 최우선" 섹션 항목으로 이어감.
1. ~~model_turn_straight_gate 실측 검증~~ → 13차 패치로 대체, 검증
   대상 자체가 바뀜.
2. ~~S자 커브 부작용 확인~~ → 13차 재설계로 해당 위험 자체가 제거됨
   (사전감속 억제 위험), 대신 "장시간 정속 커브" 새 한계로 재검토 필요.
3. **atc/road/route 등 나머지 쌍은 여전히 미해결** — 이번 패치는
   vturn↔model 쌍만 다룸. 전체 min() 히스테리시스 재설계는 별도
   과제로 유지(PARAMS_REGISTRY.md 참고). (이 항목만 유효, 계속 유지)

## 8차 완료분 — vturn 지평선 2단계 확대 4.5s → 6.5s → 8.0s (모두 push 완료)
- 사용자 요청(7차): "곡선 진입 전 사전 감속시간이 부족해서 충분히
  감속이 안된 상태에서 곡선에 진입 → 급감속" → `vturn_lookahead_
  horizon_s`를 2초 늘려서 해결 요청.
- **기존 근거**: `[INVESTIGATING] 조여드는 커브 중간에 vturn 감속 진행
  중 운전자 브레이크 개입` (260819-7 seg6, 표본 1건) — 곡률이 8.6초에
  걸쳐 서서히 증가하는 커브에서 vturn 감속률 자체는 매끈했지만 aEgo
  -3.41m/s² 도달 직후 운전자가 추가 브레이크 개입, 이때도 곡률은 계속
  증가 중이었음.
- **코드 원인**: `carrot_man.py` vturn_speed()가 모델 예측 궤적 중
  `vturn_lookahead_horizon_s`(기존 4.5s) 이내 지점만 보고 그중 가장
  엄격한 필요속도를 취함 → 정점까지 걸리는 시간이 지평선보다 긴
  커브에서는 접근 중 정점이 뒤늦게 지평선 안으로 들어오는 순간
  필요속도가 급락 → 물리공식(v_i²=v_f²+2ad) 자체는 정확해도 "그 순간
  보이는 거리"가 짧아 감속 시작이 늦어지는 구조적 문제.
- **1차 패치**(`carrot_man.py`, commit `4c15987`, push 완료
  `b403d52..4c15987`): `vturn_lookahead_horizon_s` 4.5s → 6.5s.
- **2차 패치**(`carrot_man.py`, commit `1fca82f`, push 완료
  `4c15987..1fca82f`): 사용자가 1차 push 확인 직후 근거 사례(조임
  지속시간 8.6s)에 더 가깝게 맞추기 위해 6.5s → 8.0s로 재확대 요청,
  적용 완료.
- 사용자 질문에 답변(2차 시): `vturn_lookahead_horizon_s`는 "감속에
  걸리는 시간"이 아니라 "커브 후보를 몇 초 앞까지 스캔할지" 지평선이고,
  방지턱과 동일한 거리기반 서서히-감속(v_i²=v_f²+2ad) 프로파일 자체는
  `vturn_decel_rate`(1.2 m/s²)/`vturn_safe_time`(1.0s)이 담당한다는 점을
  구분해서 설명함. 두 패치 모두 지평선(스캔 범위)만 변경, 감속
  프로파일은 미변경.
- 두 패치 모두 문법 체크(`py_compile`) 통과.
- devnotes push: FINDINGS.md/PARAMS_REGISTRY.md/WIP.md의 커밋 해시
  표기를 `4c15987`→`1fca82f` 최신 상태로 갱신 완료.

## 다음 세션에서 이어갈 것 (8차 갱신, 최우선 — 여전히 미해소)
1. **vturn 지평선 실차 검증** (1차 6.5s, 2차 8.0s 모두 미검증) — 패치
   적용 후 유사 조여드는 커브 구간 재주행, aEgo 프로파일 및 운전자
   개입 여부 확인.
2. **8.0s < 8.6s 한계 재확인** — 근소한 차이(0.6s)만 남음. 검증 결과
   부족하면 추가 미세 조정 또는 vturn_decel_rate/vturn_safe_time 조정
   검토(우선순위 낮음).
3. 지평선 확대 부작용 확인 — 지평선이 4.5s→8.0s로 거의 2배 늘어난 만큼,
   완만한 국도 커브 연속 구간에서 기존 `speed_n_sources` vturn↔road/
   model/route 플리커 이슈와의 상호작용 및 원거리 모델 예측 신뢰도
   이슈를 이전보다 더 주의 깊게 관찰.

## 지난 세션(6차)에서 이어갈 것
- 사용자 요청: "고속도로에서 카메라(파란박스)가 멀리 서행 앞차를 인식한
  시점부터는 감속 없다가 레이더(빨간박스) 인식 순간부터 감속 시작되는
  느낌 — 카메라 인식 시점부터 서서히 감속하는 코딩" (WIP 5차에 이미
  올라와 있던 최우선 후보 #1과 동일 트랙).
- 신규 로그 업로드 없이(사용자가 증상만 재기술) 기존 `VISION_RADAR_
  CROSSOVER.md` 분석(8개 zip, highway crossover 65건, 특히 260819-6
  seg15/seg5의 modelProb 0.54~0.56 · 7~8초 지속 · 90m+ 좁혀짐 사례)과
  코드 레벨 원인 분석으로 진행.
- **코드 원인 확정**: `radard.py` VisionTrack.update()가 modelProb<0.97
  구간(원거리 거의 항상)에서 vRel을 모델 예측치 그대로 사용 →
  `long_mpc.py`의 LEAD_ACQ_TTC_* 램프가 이 편향된 vRel로 TTC를 계산하므로
  실제 위험이 가려져 개입 못 함. LEAD_ACQ 로직 자체는 "source 무관"하게
  이미 vision/radar 동일 적용되지만, **입력값(vRel) 품질이 소스별로
  다른 게 진짜 원인**이었음.
- **패치 구현 + 실차 적용 완료** (`long_mpc.py`, commit `b403d52`): dRel
  프레임간 미분 기반 독립 접근속도 추정(저역통과, TAU=1.0s) 신설 →
  vision-only + 0.5초 이상 연속추적 시에만 기존 vRel-TTC와 min()으로
  결합 (MIN_TIME 최초 1.0s → 사용자 피드백으로 0.5s 단축, TAU는 유지).
  순수 floor라 감속 완화 방향 작동 없음. VisionTrack.vRel 자체는
  미변경(리스크 격리). 문법 체크(`py_compile`) 통과 후 사용자가 실차에서
  `git am` 적용 + `git push` 완료 확인(`f7b1546..b403d52`).
- push 완료: devnotes(`FINDINGS.md`, `PARAMS_REGISTRY.md`,
  `LAST_ANALYZED.md`, `WIP.md`) + ryu(`b403d52`) 양쪽 모두 반영됨.

## 6차 항목 — 다음 세션에서 이어갈 것 (아직 미해소)
1. **aEgo 실측 대조 (미완료, patch는 이미 `b403d52`로 실차 적용됨)** —
   `VISION_RADAR_CROSSOVER.md` 최우선 후보 5건 세그 폴더(260819-6
   seg15/seg5, 260819-7 seg14/seg8, 260819-5 seg34) 재업로드받아 (이
   세그들은 패치 이전 시점 로그이므로) 패치 적용 전/후 aEgo 비교, 특히
   vision-only 구간에서 실제로 조기 감속이 시작되는지 확인.
2. **패치 적용 이후(`b403d52` 이후) 신규 실주행 로그로 직접 검증** —
   유사 고속도로 원거리 서행차 상황을 재주행한 새 로그가 있으면, 위 1번의
   "적용 전 로그 재해석"보다 이쪽이 더 확실한 근거. VISION_CLOSING_RATE_
   TAU(1.0s)/MIN_TIME(0.5s, 이번 세션에 1.0s→0.5s 단축됨) 추가 튜닝
   필요 여부 판단.
3. opening/flat 크로스오버 케이스(65건 중 63%)에서 이 패치가 불필요
   개입 안 하는지 확인 — 설계상 dRel 미분이 양수면 자동 제외되지만
   실측 미확인.

## 지난 세션들 요약 (이미 push됨, 재작업 불필요)

## 이번 세션(4차)에서 완료된 것
- **정차열 리드 대체 가설 — dashcam 영상 검증 완료, 가설 수정됨**
  (우선순위 1 항목 해소).
  - 사용자가 route 260819-1의 `--2`, `--3` 세그(qcamera.ts + rlog.zst)를
    업로드 → `extract_dashcam_frames.py`로 대상 4개 이벤트
    (`--2`: t=205.53/207.99, 208.69/210.48; `--3`: t=263.84/264.63,
    277.33/277.83) 전부 프레임 매칭(오차 1~12ms) 및 육안 확인 완료.
  - **결과: "정차열"이 아니라 "교차로 정차 중 횡단교통 오탐지"로 가설
    수정.** 4건 전부 동일한 대형 교차로 정지신호 대기 장면 — 내 차로
    전방은 비어 있고, 그 너머 교차로를 버스/트럭/승용차가 가로지르며
    통과. 기존에 가정한 "동일 차로 정차 대기열 내 리드 전환"이 아니라
    빈 교차로에서 횡단 차량을 일시적으로 리드로 오탐지하는 패턴으로
    보는 게 프레임 증거와 부합.
  - FINDINGS.md 해당 항목(L393-429, `[NEEDS_VALIDATION] ... 신규
    패턴`) 아래에 `[VALIDATED, 가설 수정]` 서브섹션 추가 완료.
  - 비교 이미지 4장(`compare_seg2_event1/2.jpg`,
    `compare_seg3_event1/2.jpg`, 각 수십KB) `devnotes/evidence/`에
    추가 — 원본 qcamera.ts/rlog.zst는 미커밋(개인 주행 영상, 방침
    유지).
  - push 대상: `FINDINGS.md`, `evidence/compare_seg2_event1.jpg`,
    `evidence/compare_seg2_event2.jpg`, `evidence/compare_seg3_event1.jpg`,
    `evidence/compare_seg3_event2.jpg`, `WIP.md`.

## 지난 세션들 요약 (이미 push됨, 재작업 불필요)
- 1~3차(WIP 히스토리): route 260819-1 x20seg 분석, LEAD_ACQ_LOSS_GRACE_TIME
  초과사례 확보, src flicker 대규모 재현, `extract_dashcam_frames.py`
  작성+스모크 테스트.
- 8~9차(LAST_ANALYZED.md 히스토리, 별도 트랙): route8a/8b(260819-7/8)
  분석 — harsh_brake/turn_speed_violation/steering_oscillation/cut-in
  전부 0건, LEAD_ACQ_LOSS_GRACE_TIME 초장기 유실(최대 222.85s)은 고속도로
  선행차 부재로 무해 판단, MAX_SEGMENTS_PER_ROUTE 관련 참고 관찰(정확히
  40세그 후 boot 변경, 캡 발동 여부 미확정). 상세는 LAST_ANALYZED.md /
  FINDINGS.md 참고.

## 진행 중이던 코드 작업
없음 (ryu 코드 변경 없음, devnotes 문서/증거 이미지만 갱신).

## 이번 세션(5차)에서 완료된 것 — 비전→레이더 크로스오버 분석 (신규 트랙)
- 사용자 요청: "고속도로에서 카메라가 멀리 서행 앞차를 먼저 인식(파란
  박스)했는데 감속은 레이더 확인(빨간 박스) 시점부터 시작되는 느낌 —
  향후 이 패치를 재업로드 없이 요청할 수 있게 8개 zip 전체를 분석해
  push해달라"는 요청 처리.
- `toolkit/extract_log.py`에 `leadRadar`/`leadModelProb` 컬럼 추가
  (radarState.leadOne.radar/modelProb), `toolkit/analysis_helpers.py`에
  `vision_to_radar_crossover()` 함수 신규 작성.
- **260819-1~8 전체(8개 zip, x20세그 내외 × 8 = 160세그 안팎) 스캔
  완료**, 매 zip 분석 완료 즉시 push(토큰/컨텍스트 절약 목적).
  결과: `VISION_RADAR_CROSSOVER.md` + `evidence/crossover/
  crossover_260819-{1..8}.json` + `crossover_ALL_summary.json`.
  (원본 route.csv는 매 zip 처리 직후 삭제, 커밋 안 함 — 이벤트 요약
  JSON만 남김, 방침 유지.)
- 종합: crossover 108건 중 highway(≥54km/h) 65건. 갭 중앙값 2.0s,
  최대 10.45s. dRel 변화는 closing 24건/flat 15건/opening 26건으로
  혼재 — `leadRadar=False`만으로는 "위험한 접근" 판별 불충분, closing
  rate 게이팅 필요함을 확인.
- **최우선 후보 5건 확정** (다음 단계 aEgo 대조용, 상세는
  VISION_RADAR_CROSSOVER.md "8개 전체 종합" 참고):
  1. 260819-6 seg15 (갭 7.80s, 94.6m 좁혀짐)
  2. 260819-6 seg5 (갭 7.00s, 91.9m 좁혀짐)
  3. 260819-7 seg14 (갭 2.26s, 71.5m 좁혀짐, closing rate 최대)
  4. 260819-7 seg8 (갭 1.70s, 59.0m 좁혀짐)
  5. 260819-5 seg34 (갭 2.25s, 51.1m 좁혀짐)

## 다음 세션에서 이어갈 후보 (우선순위 순, 5차 시점 — 1번은 6차에서
## 코드까지 진행됨. 상세는 위 "6차" 섹션 참고, 이 목록은 기록용 유지)
1. **[6차에서 코드 구현 완료, aEgo 실측 대조는 여전히 미완료]
   비전→레이더 크로스오버 aEgo 대조 (최우선, 새 트랙)**: 위 5건
   세그 폴더명이 이미 `VISION_RADAR_CROSSOVER.md`(및 highway 65건
   전체는 `evidence/crossover/highway_events_seg_lookup.md`)에 있으므로,
   **zip 전체가 아니라 해당 세그 폴더 1~5개만** 재업로드 받아 그
   구간 aEgo를 프레임 단위로 확인 → "비전-only 구간 동안 실제로
   감속을 안 하고 있었는지" 확정. 확정되면 long_mpc.py의
   `LEAD_ACQ_*`가 `radar=False` 상태에서 이미 반응하는지 코드
   확인 → "vision-only + closing rate 게이팅" 선제 감속 패치 설계.
2. **"교차로 빈 lead 오탐지" 근본원인 조사**: 정차 중 빈 교차로
   지오메트리에서 횡단 차량을 리드로 오탐지하는 패턴(4차 체크포인트
   확인) — long_mpc.py/LeadBlend에서 정차(vEgo≈0) + 실제 리드 부재
   상황을 구분해 게이팅할 수 있는지 검토. 아직 코드 조사 미착수.
3. **src flicker 실제 영향 정량화**: seg4~8/11~12/18~19의 vturn↔road/
   model/route 플리커 클러스터 구간에서 desiredSpeed 왕복폭과 실제
   aEgo/저크 반영 여부(하류 슬루 리미터 흡수량) 미분석.
4. **MAX_SEGMENTS_PER_ROUTE 관찰 검증**: route `f7e0bb3abd`가 정확히
   40세그먼트에서 boot 변경과 함께 종료된 것이 캡 발동인지 우연한
   재부팅 겹침인지 코드 레벨 확인 필요 (패치 이전 시점 로그라 미검증).
5. (기존 on-the-horizon 항목) LEAD_ACQ_RAMP_TIME=5.0s,
   LEAD_ACQ_TTC_DANGER=2.5s 검증용 고속 근접 리드 lock-on 로그 여전히
   필요. CarrotWeb 로그탭 UI 버그도 미해결.

## 다음 세션 시작 시
이 WIP.md가 존재하면 위 "다음 세션에서 이어갈 후보" 중 사용자가
지정하는 항목부터 진행. 착수/해소되면 해당 항목을 이 파일에서
제거하거나 완료 표시.
