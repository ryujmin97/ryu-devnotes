# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

현재 진행 중인 중단 작업 없음. 24차(15개 zip 하루치 실주행 로그
배치 분석)는 2026-08-21에 완전히 완료되어 이 파일에서 제거됨 —
상세 내용은 FINDINGS.md "24차" 관련 섹션들, LAST_ANALYZED.md
c3-ms-dev 최신 항목 참고.

## 다음 세션 우선 과제 (WIP는 아니지만 참고용)
1. 고속도로 급접근(harsh) 케이스 실측 표본 확보 — 지금까지 확보된
   b403d52 검증은 전부 "온건한 접근" 케이스뿐, 급접근 시나리오는
   미확보.
2. route3(`dda0d533ce`)의 `vision_radar_crossover
   count_highway_est=0`이 route_summary.py 버그(route4에서 발견+
   수정) 영향인지 재확인(낮은 우선순위, route3 자체가 시내 위주라
   실제로도 낮았을 가능성 높음).
3. `source_pair_flicker` 관련 문서(FINDINGS/PARAMS_REGISTRY 등)에서
   경쟁 소스를 기존 5종(road/route/model/vturn/cam)이 아닌 최소
   7종(+bump/gas)으로 반영 필요.

## 다음 세션 시작 시
이 WIP.md에 진행 중인 작업이 없으면 평소 SETUP.md 체크리스트대로
LAST_ANALYZED.md → FINDINGS.md → PARAMS_REGISTRY.md 순서로 확인 후
사용자 요청에 따라 진행.
