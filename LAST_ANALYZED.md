# LAST_ANALYZED — 브랜치별 마지막 커밋 분석 지점

새 세션에서 "최신 커밋 분석"을 요청받으면, 여기 기록된 커밋 이후만
`git log <기록된 해시>..HEAD`로 훑는다. 매번 최근 30개를 처음부터
다시 보지 않기 위함.

분석을 마칠 때마다 이 파일을 갱신한다 (해시 + 날짜 + 한줄 메모).

---

## c3-ms-dev
- last_analyzed_commit: `366009153812`
- date: 2026-08-19
- note: 8dbed620887b 이후 신규 커밋 1개(3660091, CarrotWeb gdrive 재진입/
  핸드셰이크 타임아웃) 확인했으나 이미 FINDINGS.md에 기록된 이슈라 재분석
  생략. 대신 x11seg 실주행 로그 분석 수행 — LEAD_ACQ_LOSS_GRACE_TIME
  NEEDS_VALIDATION 갱신, 정지 리드 추종 클린 케이스 기록. 상세는
  FINDINGS.md/PARAMS_REGISTRY.md 참고.
  같은 날 x16seg(16.44km/955s) 라우트 추가 분석 — 종방향 harsh brake
  15건 전부 운전자 개입(cruiseEnabled=False) 확인해 ADAS 활성구간
  급제동 0건, 근접 컷인 유사 이벤트 매끈한 반응 확인, carrot_serv.py
  speed_n_sources min() 히스테리시스 부재로 인한 src/desiredSpeed
  플리커 신규 발견, LEAD_ACQ_LOSS_GRACE_TIME 5번째 초과 샘플 확보.
  코드 변경 없음(관찰/분석만).

## c3-ms
- last_analyzed_commit: (아직 분석 안 함)
- date: -
- note: -

## c3-atune
- last_analyzed_commit: (아직 분석 안 함)
- date: -
- note: -
