# FINDINGS — 이슈 / 검증 상태 누적 기록

세션이 끝나도 남아야 하는 것만 여기 기록한다. 대화 내용 전체를 옮기지 말고,
"무엇을 발견했고, 지금 상태가 뭔지"만 짧게. 새 세션 시작할 때 이 파일을
먼저 훑으면 이미 끝난 걸 다시 분석하지 않아도 된다.

각 항목 형식:
```
## [상태] 제목 (발견일, 관련 커밋/파일)
- 증상:
- 원인:
- 조치: (수정됨 / 검토중 / 보류)
- 근거 로그: (있으면 라우트명 + 타임스탬프)
```
상태 태그: `[FIXED]` 수정 완료 / `[INVESTIGATING]` 원인 분석 중 /
`[NEEDS_VALIDATION]` 코드는 있으나 실도로 검증 필요 / `[WONTFIX]` 보류

---

## [FIXED] radard KjException 크래시 — dPath numpy.float64 캐스팅 누락 (2026-08-17, 커밋 2c34855)
- 증상: EnableRadarTracks<3 (Genesis DH 기본) 순수 비전 리드 경로에서 radard가
  KjException으로 죽음 → radarState dead → soft disable → engage 해제.
- 원인: `VisionTrack.get_lead()`에서 `self.dPath`가 numpy 타입 그대로 capnp
  구조체에 대입됨. `Track.get_RadarState()`류는 이미 float() 캐스팅돼 있었는데
  이 함수만 누락.
- 조치: FIXED. float() 캐스팅 추가.
- 근거 로그: t=140.78 radard exitCode=1, t=141.23~144.23 soft disable→disable.

## [FIXED] t_follow 이중 apply_t_follow 호출로 0에 수렴 (2026-08-17, 커밋 a12d729)
- 증상: 차선변경 중 longitudinalPlan.tFollow가 0.005~0.09까지 붕괴, 옆차선
  선행차와 위험하게 근접.
- 원인: `get_T_FOLLOW()`와 `dynamic_t_follow()`가 각자 내부에서
  `apply_t_follow()`(증가방향 레이트리미터)를 호출 → 차선변경으로 줄어든 값이
  다음 사이클 리미터 기준선이 되어 재귀적으로 계속 축소.
- 조치: FIXED. 두 함수는 raw 값만 반환, `long_mpc.update()`에서 최종 확정된
  t_follow에 대해 apply_t_follow()를 정확히 1회만 호출하도록 정리.
- 근거 로그: 시뮬레이션 재현 — OLD 로직 0.5초만에 0.00215로 수렴, 관측값과 일치.

## [FIXED] vturn 슬루 리미터 min/max 반전 (2026-08-16, 커밋 ab156ea)
- 증상: 커브 감속(vTurnSpeed)이 "변화율 상한"이 아니라 "최소 변화량 강제"로
  동작 → 20Hz 루프에서 프레임당 -10%/+8% 복리 누적, 1초 안에 -88%/+366%까지
  튈 수 있는 상태. vTurnSpeed는 크루즈 목표속도 결정(min())에 직접 쓰임.
- 원인: 슬루 제한 코드의 min()/max() 방향이 반대로 작성됨.
- 조치: FIXED. 동시에 "탈출 후 2초 고정 지연 가속회복" 상태머신도 제거하고
  1차 저역통과 필터(감속 rc=0.25s, 가속 rc=0.6s)로 교체 — 이 상태머신이
  오히려 "커브 빠져나오고도 한참 안 밟는" 현상의 직접 원인이었음.
- 참고: 이전에 있었던 "persistent state machine (apex/exit lock-in, freeze
  재획득)" 방식은 같은 날 안에 폐기되고 lookahead 기반 벡터화 방식으로
  대체됨. 과거 세션 요약에 그 상태머신이 언급돼 있다면 이미 구버전 설명임.

## [NEEDS_VALIDATION] LEAD_ACQ_RAMP_TIME=5.0s / LEAD_ACQ_TTC_DANGER=2.5s (2026-08-17~)
- 목적: 리드 최초 인식 시 관측치가 부정확한 구간(비전/레이더 무관)에 대한
  선제적 감속 하한선. TTC 실시간 재계산으로 경과시간 램프가 못 잡는 급접근
  케이스 보완.
- 상태: 코드는 완결(min() 기반 floor, 안전방향으로만 작동 확인됨). 실도로
  파라미터 자체(RAMP_TIME 5.0s가 적정한지, TTC 임계값 2.5s/6.0s가 적정한지)
  검증 아직 부족.
- 2026-08-18 로그 분석 (x9seg, 522초 시내주행) 결과:
  - 리드 인식 이벤트 13건 중 cruiseEnabled=True(로직이 실제 작동 가능한
    조건)는 8건. 그중 TTC가 DANGER(2.5s) 아래로 내려간 케이스 0건.
  - 가장 근접했던 케이스(seg8 t=556.22, ttc_min=3.62s)도 원인은 route
    기반 감속으로 보이며 aEgo 반응은 매끈함(튐 없음).
  - 얼핏 "위험 케이스"로 보였던 seg6(t=436.95, vRel=-7.49m/s)는 실제로는
    리드가 0.6초 만에 사라지고(LOSS_GRACE_TIME 넘어 리셋) 이후 급감속은
    vturn(커브)+운전자 브레이크가 원인 — LEAD_ACQ와 무관한 이벤트였음.
  - 진짜 위험 TTC(0.98s, seg12 t=808.20)는 cruiseEnabled=False(운전자 수동
    브레이크 중)라 ACC 로직 검증에 못 씀.
  - **결론: 이 로그로는 검증 불가.** 고속도로 순항 중 크루즈 켠 채로 리드가
    가깝게/빠르게 나타나서 계속 락온 유지되는 로그 필요.

## [NEEDS_VALIDATION] LeadBlend closer_jump(8m)/big_jump(15m) 게이트, CUTOUT_* (2026-08-16, 커밋 084a5b8)
- 상태: route1/route2 특정 이벤트로 검증됨(closer_jump: route1 seg13 t=794s,
  big_jump: route1 t=1388~1390s / route2 t=825~827s). 표본이 각 1건씩이라
  추가 로그로 재현성 확인하면 좋음.
