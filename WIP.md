# WIP — 중단 지점 체크포인트

세션 정상 종료가 아니라 사용자 요청으로 여기서 저장한 중단 지점.
다음 세션(다른 계정 포함)은 여기부터 이어받는다.

---

## 완료된 것 (2026-08-20)
- 라우트 260819-2 (x20seg, 10.29km/1199.9s) 실주행 로그 전체 분석 완료.
  HEAD f7b154638cf2 (신규 커밋 없음, 코드 변경도 없음 — 순수 분석만).
- 발견 2건 FINDINGS.md/PARAMS_REGISTRY.md/LAST_ANALYZED.md에 기록하고
  push 완료 (커밋 0f48cf3de1d39e84b7c269e0deca4248f2763bcd):
  1. `extract_log.py`가 세그먼트 파일 전환마다 `last_lead`를 강제로
     False 리셋하는 버그 확인 (root cause 코드로 특정 완료, 260819-2의
     순간유실 16건 전부 세그먼트 경계와 diff=0.000s로 정확히 일치 —
     실제 리드유실 아닌 추출 아티팩트). LEAD_ACQ_LOSS_GRACE_TIME 관련
     과거 누적 증거 신뢰도에 영향 — PARAMS_REGISTRY "재검토 필요"로
     하향 조정함.
  2. seg24 t=1505.78~1507.88: 고속(112km/h) 순항 중 새 리드 포착 직후
     leadDRel은 연속인데 leadVRel/leadVLead만 한 프레임 만에 불연속
     점프(-4.6→-26.2m/s). 시스템 감속(-4.61m/s²)이 TTC DANGER(2.5s)
     문턱을 못 넘긴 채 이어지다 운전자 급브레이크(-7.46m/s²) 개입으로
     연결됨. LeadBlend 게이트가 dRel 점프만 감지해 이런 vRel-only
     불연속은 놓칠 수 있다는 가설 — 표본 1건, NEEDS_VALIDATION.

## 다음 단계 (아직 미착수 — 방향 결정만 하고 코드 작업 전 중단)
사용자에게 4가지 선택지를 제시했고, "일단 체크포인트만 저장"을 선택함.
다음 세션 시작 시 아래 중 무엇을 할지 다시 물어볼 것:
1. `extract_log.py` 세그먼트 경계 버그 패치
   (제안된 수정 방향: `process_segment()` 시작 시 `last_lead`를 매번
   False로 초기화하지 말고, 이전 세그먼트 처리 종료 시점 값을
   다음 세그먼트 호출로 carry-forward)
2. seg24 급감속 이벤트를 dashcam 영상으로 교차검증
   (실제로 그 시점에 느린 선행차/정체가 있었는지 vs 오탐 트랙전환인지
   확인 필요 — 사용자가 원본 dashcam mp4를 아직 안 올림, 260819-2.zip은
   rlog만 포함)
3. LeadBlend에 vRel-only 불연속 감지 게이트 추가 검토
   (현재 CLOSER_JUMP_DIST/BIG_JUMP_DIST는 dRel 점프만 봄 — vRel/vLead
   불연속만 있고 dRel은 연속인 케이스 대응 로직 설계 필요, 아직 설계
   착수 안 함)

## 참고 — 코드 diff 상태
이번 세션 코드 변경 없음. 위 1번(extract_log.py 패치)은 아직 코드
작성 전, 방향만 제안된 상태.
