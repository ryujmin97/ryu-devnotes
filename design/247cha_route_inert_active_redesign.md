# 247차 Route 감속 로직 재설계 — INERT/ACTIVE 래치 상태머신 (확정안)

**작성**: Claude, 247차 (사용자+지선생 대화 기반 정리, 코드 변경 없음)
**배경**: 지선생이 "Route 감속 로직 재설계 지침" 최초안을 제시, 대화를 통해
§3/§5 검사 분리(래치 구조), §5 종료조건 OR 분리(vEgo≤target×1.1 / Apex 통과),
severity gate 즉시삭제까지 확정. 이 문서는 그 확정 내용 + Claude가 대화 중
발견한 apex anchor 문제(Q1)와 그 해법(234차 continuity 재사용안)까지 합쳐
하나의 문서로 정리한 것.

---

## 1. 기본 목적

Route는 미래의 커브/Apex를 미리 탐지하여 필요한 시점부터 선행 감속한다.
Apex가 멀다는 이유로 현재 주행속도를 제한하거나 정상적인 가속을 방해하지 않는다.

## 2. Apex 탐색

- 전방 Route에서 다음 감속 대상 Apex를 계산한다.
- Apex 발견과 Route 개입은 분리한다. Apex를 발견했다고 즉시 감속하지 않는다.
- (247차 신규 결정사항, §8 참고) Apex 탐색 자체도 기존 `candidates[0]`
  무상태 재선택 방식이 아니라, 234차 계속4~10에서 이미 설계·부분검증된
  **공간 클러스터링 + 예측거리 매칭 continuity 추적**을 재사용한다.

## 3. 감속 시작 조건 — INERT에서만 검사

현재 `vEgo`, Apex 목표속도, Apex까지 거리, 고정 감속률을 이용하여 감속
시작점을 계산한다.

- INERT 상태에서만 감속 시작 조건을 검사한다.
- 아직 감속할 필요가 없음 → `ROUTE INERT`
- 지금부터 감속해야 함 → `ROUTE ACTIVE`
- ACTIVE 상태에서는 §3의 진입조건을 다시 검사하지 않는다.

## 4. Route 감속 — ACTIVE

ACTIVE 상태에서는 현재 `vEgo`를 기준으로 목표속도까지 선행 감속한다.

- `vEgo`를 반드시 사용한다(매 프레임 실측값, 확정 (A) — 운전자가 가속하면
  ceiling도 함께 오르고, 오른 vEgo 기준으로 다시 계산되는 것이 정상 동작).
- Route가 현재속도보다 높은 속도를 명령해서는 안 된다.
- 고정된 Route 감속률을 기준으로 한다.

## 5. Route 해제 조건 — ACTIVE에서만 검사, 둘 중 하나(OR)

- `vEgo ≤ 목표속도 × 1.1`
- Apex를 통과함

INERT 상태에서는 §5의 해제조건을 검사하지 않는다.

```text
ACTIVE
 ├─ vEgo ≤ target × 1.1 → RELEASE
 └─ Apex 통과            → RELEASE
```

## 6. 해제 후 2초 Gate

RELEASE 후 2초간 Route 재개입을 금지한다. 목적: 동일 Apex 재검출 방지,
ACTIVE↔RELEASE 반복 방지, 불필요한 감속 진동 방지.

## 7. 다음 Apex 반복

2초 Gate가 끝나면 전방 Route를 다시 탐색하여 다음 유효 Apex를 계산하고
동일한 과정을 반복한다.

```text
Apex 탐색 → INERT(§3 검사) → 조건만족 → ACTIVE(§5 검사)
   → (110% 도달 또는 Apex 통과) → RELEASE → 2초 Gate → 다음 Apex 탐색
```

## 8. 기존 코드 정리 원칙 (지선생 확정)

- `ROUTE_SEVERITY_GATE_RATIO` → **즉시 삭제**(시뮬레이션 결과와 무관하게 확정).
- 기존 `route_inert`(228차 v2)의 target 고정 출력 구조 → **삭제**. 이 구조가
  246차 CRITICAL(원거리 apex 가속억제 freeze)의 직접 원인으로 추정됨
  (`carrot_man.py` L1097-1111 `v_ego_ms<=target_ms` 분기 + `carrot_serv.py`
  L1187-1188 클램프 분기 조합). 새 래치 구조에서는 이 서브스테이트 자체가
  불필요 — ACTIVE는 항상 vEgo 기준 실시간 계산, INERT는 아예 미개입(None)이라
  "target에 자기참조적으로 고정"되는 코드 경로가 존재하지 않게 됨.
- 기존 ACTIVE 진입/감속 구조(223/224/228차 3분기: eff_dist≤0 / far-inert /
  실감속) → **폐기 후 재작성**.
- `ROUTE_APEX_REACHED_DIST_M=10.0` 기반 거리조기해제 분기 → §5 "Apex 통과"
  조건으로 대체(아래 §9 참고, 정확한 판정 기준은 continuity 추적의
  `predicted_dist≤0` 시점).
- `_route_candidate_lost_frames` / `ROUTE_RELEASE_CONFIRM_FRAMES=8`(245차
  debounce) → **불필요해질 가능성 높음**. §9 원칙(INERT/ACTIVE 각자 다른
  조건만 검사)과 §11의 continuity 3프레임 hold가 같은 문제(candidate 순간
  소실)를 이미 커버하므로 중복. 시뮬레이션에서 재검증 후 최종 삭제 확정.
- `carrot_serv.py::update_navi()`의 `route_active and not route_inert` 분기
  클램프 → **단순화 후보**. ACTIVE가 구조적으로 항상 vEgo 이하만 출력하고
  INERT는 None으로 배제되면, `min(v_ego_kph, ...)` 클램프 자체가 불필요해질
  가능성. `autoCurveSpeedLowerLimit` floor만 남기는 방향으로 재검토.
- 새 설계와 무관하거나 실제 동작하지 않는 코드 → 사용자에게 보고 후 삭제.
- 판단 기준은 "기존에 있었으니 유지"가 아니라 **새 설계에 필요한가**.

## 9. 핵심 상태 원칙

INERT와 ACTIVE는 검사해야 할 조건이 다르다.

- `INERT` → §3 감속 시작 조건만 검사
- `ACTIVE` → §5 해제 조건만 검사
- `RELEASE` → 2초 Gate
- Gate 종료 → 새 Apex 탐색

한 상태에서 다른 상태의 조건을 섞어서 검사하지 않는다. (239차
self-elimination 리밋사이클의 재발 방지 원리 — 매 프레임 진입조건을
vEgo로 재평가하는 게이트 구조 자체가 진동의 원인이었음.)

## 10. Apex Anchor 문제와 해법 (247차 대화 중 신규 발견)

**문제(Q1)**: §5 "Apex 통과" 판정과 §9 "ACTIVE는 같은 apex를 계속 추적"
전제가 성립하려면, ACTIVE 중 apex_dist/apex_speed가 매 프레임 `candidates[0]`
무상태 재선택이 아니라 **동일 물리적 지점을 계속 가리키는 값**이어야 한다.
244차 실측(CASE_A 9.8% vs CASE_B 90.2%)에 따르면 현재 방식은 프레임마다
실제로 다른 후보로 전환되는 경우가 대부분 — 이 상태로는 "그 apex를
지나쳤다"는 판정 자체가 성립하지 않는다.

**해법**: 234차 계속4~10이 이미 설계·부분검증한 메커니즘을 재사용한다
(`toolkit/sim_route_234_spatial_apex_continuity.py`).

- **공간 클러스터링**(stage2): 인접 후보끼리 gap≤`ROUTE_CLUSTER_MAX_GAP_M`
  (40m)이면 하나의 클러스터로 묶어(`ROUTE_CLUSTER_MIN_POINTS=2` 이상),
  단발성 노이즈 후보 하나만으로 apex가 성립하지 않도록 한다.
- **예측거리 매칭 continuity**(stage3): locked apex를 `vEgo×dt`로 매 프레임
  예측 이동시키고, 이번 프레임 클러스터 중 예측위치와
  `CONTINUITY_MATCH_TOLERANCE_M`(잠정 10m, §12 참고) 이내로 매칭되면 계속
  추적. 매칭 실패해도 `ROUTE_APEX_MISS_TOLERANCE_FRAMES`(3프레임,
  ~150ms)까지는 예측값으로 hold, 초과 시에만 lock 해제 후 재탐색.
- 이 `locked_dist`가 곧 새 설계의 apex anchor다. **"Apex 통과"는
  `predicted_dist = locked_dist - vEgo×dt`가 0 이하가 되는 시점**으로
  정의한다 — 명확한 기준이 생긴다(Q1 해결).
- 노이즈로 인한 순간 미스는 3프레임 hold가 흡수하므로, INERT/ACTIVE
  각자 다른 조건만 본다는 §9 원칙이 실제로 안전하게 성립한다(Q2도 부수 해결).

## 11. 검증 필요 사항 (아직 미해결 — §28 원칙, 추측만으로 확정 안 함)

234차 실측(172→60→16→3건, 터널 81→0→0→0)은 전부 **stage1(severity gate)이
이미 적용된 상태 위에서** stage2/3를 쌓은 결과다. 터널 81건은 stage1
단독으로 이미 0건이 되어, stage2/3(클러스터링+continuity)가 그 구간에서
추가로 증명한 바가 없다.

이번 재설계는 §8에 따라 severity gate를 **완전히 삭제**하므로,
**"gate 없이 클러스터링+continuity만으로 터널급 노이즈를 억제할 수 있는가"는
아직 한 번도 검증되지 않은 질문이다.** 이것이 다음 세션(247차 계속)의
1순위 검증 항목이다.

**검증 계획(제안, 지선생/사용자 확인 후 착수)**:
1. `sim_route_234_spatial_apex_continuity.py`에 stage1(gate) 건너뛰고
   stage0→stage2→stage3로 직행하는 옵션 추가(§21, 기존 도구 확장).
2. 244차/234차와 동일 로그(seg12-16, 터널/IC gore/S커브 3구간 corpus)로
   "gate 없는 stage2/3" 재실행, 터널 구간 flicker 억제 여부 확인.
3. 통과 시 이 continuity 메커니즘을 새 INERT/ACTIVE 상태머신의 apex 추적
   레이어로 정식 채택.
4. 실패 시(터널에서 flicker 재발) 클러스터링/continuity 파라미터를
   gate 없는 조건에 맞게 재조정하거나 지선생께 재보고.
5. 그 외 246차(원거리 apex freeze), 239차(self-elimination) 재현 케이스도
   같은 시뮬레이션 틀에서 새 상태머신이 실제로 해소하는지 함께 확인.

## 12. 미확정 파라미터 (§26 PARAMS_REGISTRY 등록 전 재검증 필요)

- `CONTINUITY_MATCH_TOLERANCE_M`: 234차 계속5에서 10/15/20m 비교했으나
  단일 route에서 차이가 없어 "10m 잠정 채택"으로만 남음. 다른 corpus로
  추가 검증 권장(특히 두 커브가 실제로 인접한 구간처럼 ambiguous 매칭이
  나올 만한 로그).
- `ROUTE_CLUSTER_MIN_POINTS=2` / `ROUTE_CLUSTER_MAX_GAP_M=40.0`: 설계안
  원문 채택값, 별도 A/B 없음.
- `ROUTE_APEX_MISS_TOLERANCE_FRAMES=3`: 234차 사용자 확정값, 재사용.

## 13. 핵심 한 줄

Route는 Apex를 미리 알되, 감속할 때가 아니면 절대 개입하지 않는다. 감속을
시작한 뒤에는 `목표속도×1.1` 도달 또는 Apex 통과(동일 물리적 지점을
continuity로 계속 추적해 그 지점을 지나쳤다고 확정한 시점) 중 하나가
발생하면 종료하고, 2초 후 다음 Apex를 다시 계산한다. 상태가 다르면
검사하는 조건도 다르다 — 절대 섞지 않는다.
