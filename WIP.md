# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

- 저장 시각: 2026-08-20 (6차, 코딩 세션 시작 직후 체크포인트)
- HEAD (c3-ms-dev): `f7b154638cf2` — **로컬 워킹 카피에서 1개 커밋
  `60286ff` 추가됨 (아직 GitHub `ryu`에 push 안 됨, patch 파일로 전달).**

## 이번 세션(6차)에서 완료된 것 — 비전-only 원거리 리드 closing-rate 패치
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
- **패치 구현 완료** (`long_mpc.py`, commit `60286ff`): dRel 프레임간
  미분 기반 독립 접근속도 추정(저역통과, TAU=1.0s) 신설 → vision-only +
  1초 이상 연속추적 시에만 기존 vRel-TTC와 min()으로 결합. 순수 floor라
  감속 완화 방향 작동 없음. VisionTrack.vRel 자체는 미변경(리스크 격리).
  문법 체크(`py_compile`) 통과.
- push 대상 devnotes: `FINDINGS.md`, `PARAMS_REGISTRY.md`, `WIP.md`.
- ryu 패치: `/mnt/user-data/outputs/0001-long_mpc-vision-only-closing-rate.patch`
  (git am 적용 필요, 아직 미적용/미push).

## 다음 세션에서 이어갈 것 (최우선)
1. **aEgo 실측 대조 (미완료)** — `VISION_RADAR_CROSSOVER.md` 최우선
   후보 5건 세그 폴더(260819-6 seg15/seg5, 260819-7 seg14/seg8,
   260819-5 seg34) 재업로드받아 패치 적용 전/후 aEgo 비교, 특히
   vision-only 구간에서 실제로 조기 감속이 시작되는지 확인.
2. 실차 검증: 디바이스에 patch 적용(`git am`) 후 유사 고속도로 원거리
   서행차 상황 재주행, VISION_CLOSING_RATE_TAU/MIN_TIME(둘 다 1.0s)
   튜닝 필요 여부 판단.
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
