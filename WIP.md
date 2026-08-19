# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

- 저장 시각: 2026-08-20 (사용자 "체크포인트 저장" 요청)
- HEAD (c3-ms-dev): `f7b154638cf2` — 이번 세션 코드 변경 없음 (관찰/분석만)

## 이번 세션에서 완료된 것 (이미 push됨, 재작업 불필요)
- 라우트 `260819-1`(x20seg, 25.6km/1200s, ADAS 활성 97.3%) 실주행 로그
  분석 완료.
- FINDINGS.md / PARAMS_REGISTRY.md / LAST_ANALYZED.md 갱신 후
  push_via_api.py로 push 완료.
  커밋: https://github.com/ryujmin97/ryu-devnotes/commit/2b39fe6cc34ef62a2c6f2fe5294add3d49f200b8
- 주요 발견 요약 (상세는 FINDINGS.md 참고):
  1. `LEAD_ACQ_LOSS_GRACE_TIME(0.5s)` 초과 사례 6~7건 신규 확보 (누적
     11~12건, 유실시간 최대 2.46s). 정차열(vEgo=0.0) 중 dRel 8~12.5m
     감소 재포착 신규 패턴 발견 — 리드 대체(다른 차량으로 전환)
     의심.
  2. `speed_n_sources` min() 히스테리시스 부재로 인한 src/desiredSpeed
     플리커가 국도뿐 아니라 73~113km/h 고속 커브 구간 전반에서 재현
     (A→B→A 패턴 49건, 총 전환 164건 중).
  3. harsh brake / turn violation / steering oscillation / cut-in —
     전부 클린 (특이사항 없음).
- 코드 패치 없음 — 이번 세션은 순수 관찰/분석 세션.

## 진행 중이던 코드 작업
없음. (패치 구현/적용 작업은 이번 세션에서 시작 안 함)

## 다음 세션에서 이어갈 후보 (아직 착수 안 함)
1. **정차열 리드 대체 가설 검증**: 라우트 260819-1의 `--2`/`--3` 세그
   (t=205~278s 부근) dashcam(qcamera.ts) 프레임과 동기화해 실제로
   대기열 내 다른 차량으로 재포착 대상이 바뀌는지 시각 확인 필요.
2. **src flicker 실제 영향 정량화**: seg4~8/11~12/18~19의 vturn↔road/
   model/route 플리커 클러스터 구간에서 desiredSpeed 왕복폭과 실제
   aEgo/저크 반영 여부(하류 슬루 리미터 흡수량) 미분석 — 다음
   세션에서 정량화.
3. (기존 on-the-horizon 항목들 — PROJECT_INSTRUCTIONS.md/README.md
   참고) LEAD_ACQ_RAMP_TIME=5.0s, LEAD_ACQ_TTC_DANGER=2.5s 검증용
   고속 근접 리드 lock-on 로그 여전히 필요.
   CarrotWeb 로그탭 UI 버그(Drive 전송 중 화면 교차/정체)도 미해결.

## 다음 세션 시작 시
이 WIP.md가 존재하면 위 "다음 세션에서 이어갈 후보" 중 사용자가
지정하는 항목부터 진행. 착수/해소되면 해당 항목을 이 파일에서
제거하거나 완료 표시.
