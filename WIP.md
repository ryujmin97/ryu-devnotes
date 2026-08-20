# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

- 저장 시각: 2026-08-20 (4차, 사용자 "체크포인트에 요구했던 qcamera
  관련 작업하고, 저장" 요청)
- HEAD (c3-ms-dev): `f7b154638cf2` — ryu 코드 변경 없음. devnotes만 갱신.

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

## 다음 세션에서 이어갈 후보 (우선순위 순)
1. **"교차로 빈 lead 오탐지" 근본원인 조사**: 이번에 확인된 패턴이
   `LEAD_ACQ_LOSS_GRACE_TIME` 조정만으로 해결될 문제가 아니라,
   정차 중 빈 교차로 지오메트리에서의 lead qualification/게이팅
   상위 로직 이슈일 가능성 있음 — long_mpc.py/LeadBlend 쪽에서
   정차(vEgo≈0) + 전방 실제 리드 부재(교차로) 상황을 구분해서
   게이팅할 수 있는지 검토 필요. 아직 코드 조사 미착수.
2. **src flicker 실제 영향 정량화**: seg4~8/11~12/18~19의 vturn↔road/
   model/route 플리커 클러스터 구간에서 desiredSpeed 왕복폭과 실제
   aEgo/저크 반영 여부(하류 슬루 리미터 흡수량) 미분석.
3. **MAX_SEGMENTS_PER_ROUTE 관찰 검증**: route `f7e0bb3abd`가 정확히
   40세그먼트에서 boot 변경과 함께 종료된 것이 캡 발동인지 우연한
   재부팅 겹침인지 코드 레벨 확인 필요 (패치 이전 시점 로그라 미검증).
4. (기존 on-the-horizon 항목) LEAD_ACQ_RAMP_TIME=5.0s,
   LEAD_ACQ_TTC_DANGER=2.5s 검증용 고속 근접 리드 lock-on 로그 여전히
   필요. CarrotWeb 로그탭 UI 버그도 미해결.

## 다음 세션 시작 시
이 WIP.md가 존재하면 위 "다음 세션에서 이어갈 후보" 중 사용자가
지정하는 항목부터 진행. 착수/해소되면 해당 항목을 이 파일에서
제거하거나 완료 표시.
