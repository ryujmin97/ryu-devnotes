# Route 감속 로직 재설계 지침

## 1. 기본 목적
Route는 미래의 커브/Apex를 미리 탐지하여 **필요한 시점부터 선행 감속**한다.
Apex가 멀다는 이유로 현재 주행속도를 제한하거나 정상적인 가속을 방해하지 않는다.

## 2. Apex 탐색
- 전방 Route에서 다음 감속 대상 Apex를 계산한다.
- Apex 발견과 Route 개입은 분리한다.
- Apex 선택은 기존 프로젝트의 검증된 spatial clustering + apex continuity 메커니즘을 우선 재사용한다.
- 단, 기존 Severity Gate는 사용하지 않는다. Gate 제거 후 apex 선택/continuity가 독립적으로 성립하는지 시뮬레이션으로 검증한다.

## 3. 감속 시작 조건 — INERT에서만 검사
현재 `vEgo`, Apex 목표속도, Apex까지 거리, 고정 감속률을 이용하여 감속 시작점을 계산한다.
- **INERT 상태에서만 감속 시작 조건을 검사한다.**
- 아직 감속할 필요가 없음 → `ROUTE INERT`
- 지금부터 감속해야 함 → `ROUTE ACTIVE`
- ACTIVE 상태에서는 §3의 진입조건을 다시 검사하지 않는다.

## 4. ACTIVE Apex anchor
ACTIVE 진입 시점에 선택된 Apex를 **1회 확정**한다.
- 위치/지오메트리 anchor를 저장한다.
- ACTIVE 중에는 `candidates[0]`을 다시 검색하여 다른 Apex로 갈아타지 않는다.
- 이후 매 프레임 anchor까지의 남은 거리만 재계산한다.
- 따라서 ACTIVE의 검사 대상 Apex는 프레임마다 변경되지 않는다.

## 5. Route 해제 조건 — ACTIVE에서만 검사
ACTIVE 상태에서만 다음을 검사한다.
- `vEgo ≤ 목표속도 × 1.1` → RELEASE
- **Apex 통과** → RELEASE

Apex 통과는 확정된 anchor까지의 남은 거리가 `0m 이하`가 되는 순간으로 판정한다(필요 시 차량 전방 윈도우 이탈도 동일한 종료 조건으로 취급).
INERT 상태에서는 §5 해제조건을 검사하지 않는다.

## 6. Route 감속
ACTIVE에서는 현재 `vEgo`를 기준으로 목표속도까지 선행 감속한다.
- `vEgo`를 반드시 사용한다.
- Route가 현재속도보다 높은 속도를 명령해서는 안 된다.
- 고정된 Route 감속률을 기준으로 한다.
- INERT에서는 Route가 제어에 개입하지 않는다.

## 7. RELEASE 후 2초 Gate
Route RELEASE 후 **2초 동안 Route 재개입을 금지한다.**
목적은 동일 Apex 재검출과 ACTIVE ↔ RELEASE 반복을 방지하는 것이다.

## 8. 다음 Apex 반복
2초 Gate가 끝나면 전방 Route를 다시 탐색하여 다음 유효 Apex를 계산하고 동일한 과정을 반복한다.

`Apex 탐색 → INERT → 감속 시작점 진입 → ACTIVE → (110% 도달 또는 Apex 통과) → RELEASE → 2초 Gate → 다음 Apex 탐색`

## 9. 기존 코드 정리 원칙
이번 재설계에서는 기존 Route 코드를 무조건 보존하지 않는다.
- `ROUTE_SEVERITY_GATE_RATIO` → 즉시 삭제
- 기존 `route_inert`의 target 고정 출력 구조 → 삭제
- 기존 ACTIVE 진입/감속 구조 → 폐기 후 재작성
- 새 설계와 충돌하는 로직 → 삭제
- 새 설계와 무관하거나 실제 동작하지 않는 코드 → 사용자에게 보고 후 삭제
- 필요한 기능만 새 상태머신에 맞춰 재구성한다.

## 10. 검증 우선 원칙
`carrot_man.py`를 바로 패치하지 않는다.
먼저 새 설계대로 시뮬레이션한다.
최소 검증 대상은 246차 CRITICAL(150~500m 원거리 apex 자기참조 고착), 239차 self-elimination 사례, Severity Gate 제거 후 터널 apex flicker 사례다.
시뮬레이션 결과에서 발견된 문제는 설계에 반영한 뒤 최종 패치한다.

## 11. 최우선 원칙
**Apex를 아는 것과 Route가 감속하는 것은 다르다.**
Route는 미래를 미리 보되, 감속이 필요한 시점까지는 차량의 정상적인 가속을 방해하지 않는다.
이번 설계지침을 기존 코드보다 우선한다.
