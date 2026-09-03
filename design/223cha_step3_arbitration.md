# 223차 STEP3 — arbitration 전체 흐름 확인 (코드 수정 없음)

Base commit: 7519a3a91df530ee6667183759b6c94afa8ae287 (STEP1/STEP2와 동일)
대상: selfdrive/carrot/carrot_man.py `broadcast_version_info()` + carrot_serv.py `update_navi()`
실차 검증: 미실시 (정적 코드 리딩만)

---

## 1. 확인된 실제 흐름 (§19 요구사항)

```
carrot_man.py:582
  coords, distances, route_speed = self.carrot_navi_route()
      -- route_speed = carrot_navi_route()의 out_speed 반환값 그 자체
         (STEP2가 교체 대상으로 지목한 raw 계산 결과, self._route_out_speed/
          self.carrot_serv.route_out_speed 텔레메트리와 동일 값)

carrot_man.py:598
  self.carrot_serv.update_navi(..., route_speed, ...)

carrot_serv.py:983 update_navi(...) 내부:
  1118: route_speed = max(route_speed, self.autoCurveSpeedLowerLimit)   # 바닥값만 적용
  1119: if self.turnSpeedControlMode in [2, 3, 4]:
  1126:     speed_n_sources.append((route_speed, "route"))
  1165: desired_speed, source = min(speed_n_sources, key=lambda x: x[0])
```

`atc`/`atc2`/카메라(`sdi_speed`)/`road`(제한속도)/`vturn`(mode 1,2)/`route`(mode 2,3,4)/
`model` 전부 동일하게 `speed_n_sources` 리스트에 후보로 들어가 **단순 min() 하나로**
최종 `desired_speed`가 결정된다. Route에 대한 별도 가중치/우선순위 로직 없음 —
"가장 낮은 값이 이긴다"는 단일 규칙.

**mapTurnSpeedFactor 곱셈**: 210차에서 이미 완전히 제거됨(주석으로 확인, 재확인 완료) —
현재 코드에 남아있지 않음, 재도입 우려 없음.

## 2. §19 "route source가 이전 값을 붙잡는 현상" 여부

`route_speed`는 매 프레임 `carrot_navi_route()`의 반환값을 **그대로** 넘겨받는 구조라,
`update_navi()`/arbitration 레이어 자체에는 캐싱이나 지연이 없다. STEP2 이전 버전에서
실제로 "값이 지연되어 붙잡히는" 문제가 있었다면, 그 원인은 arbitration이 아니라
**`carrot_navi_route()` 내부의 `_route_speed_prev` 램프리미터**(STEP1에서 DELETE
확정, STEP2 신규 감속식으로 대체)였다 — arbitration 레이어 자체는 무죄로 확인됨.

## 3. Mode 0/1에서 route 계산이 여전히 매 프레임 도는 문제 (STEP1 A항 재확인)

STEP1에서 이미 지적한 대로, `carrot_navi_route()`는 mode를 전혀 보지 않고 항상 curve
search/apex 계산을 수행한다. arbitration 쪽(`update_navi()` 1119줄)은 mode에 따라
결과를 **채택만 안 할 뿐**, 계산 자체의 낭비(및 mode 0/1에서도 route telemetry가
계속 채워지는 것)는 막지 못한다 — design doc §3이 요구하는 `carrot_navi_route()`
진입부 mode 게이트가 STEP4에서 반드시 필요함을 재확인.

## 4. STEP1 F-3 (150 sentinel) 최종 결론

기존 구조: route 비활성(또는 유효 포인트 부족) 시 `carrot_navi_route()`가
`ROUTE_MAX_SPEED_KPH`(150)를 반환 → `update_navi()`는 mode만 보고 **무조건**
`speed_n_sources`에 `(150, "route")`를 추가 → `min()` 특성상 다른 소스(vturn/road/atc
등)가 항상 150보다 낮으므로 실질적 영향은 없음(안전) — 그러나 이는 "150이 우연히
다른 소스보다 항상 커서 무해한 것"이지 구조적으로 안전이 보장된 것은 아니다(다른
소스가 전부 150을 넘는 비정상 상황을 배제할 근거가 없음).

**제안(STEP4에서 구현)**: 150 sentinel을 완전히 없애고, design doc §2/§3의
`route_active` 개념을 그대로 arbitration 게이트에 사용한다.

```
# carrot_navi_route() 반환값 변경: 비활성/직선(감속 불필요) 시 route_speed = None
# update_navi() 변경:
if self.turnSpeedControlMode in [2, 3] and route_speed is not None:
    speed_n_sources.append((route_speed, "route"))
```

이러면 "150이라는 매직넘버가 다른 소스보다 항상 큰가"를 신경 쓸 필요 자체가 없어짐
— route가 비활성이면 애초에 min() 후보에 들어가지 않는다(§19가 우려한 "이전 값을
붙잡는 현상"이 구조적으로 원천 봉쇄됨).

**cereal(msg.carrotMan.routeOutSpeed) 텔레메트리는 별도 처리 필요** — capnp float
필드는 None을 못 담으므로, 로깅용 sentinel은 그대로 유지하되(예: 150 그대로 재사용,
"비활성 표시"라는 의미만 남기고 arbitration 입력과는 완전히 분리) 값 자체가
arbitration에 다시 흘러들어가지 않도록 두 값을 코드상 명확히 분리한다(현재도
`self._route_out_speed`(텔레메트리)와 `carrot_navi_route()` 반환값(제어입력)이
이미 별개 변수이므로, 반환값만 None으로 바꾸고 텔레메트리 변수는 그대로 150 유지하면
충돌 없음 -- 사용자가 STEP1 F-3에서 질문한 "sentinel 완전 제거 vs 다른 방식 대체"의
답은 "제어입력은 None(그래서 애초에 sentinel 불필요), 로깅표시는 150 유지"로 정리).

## 5. STEP4 착수 전 확정 사항 요약

| 항목 | 결론 |
|---|---|
| arbitration 구조 | min(speed_n_sources) 그대로 유지, route 항목 append 조건만 변경 |
| mapTurnSpeedFactor | 이미 삭제됨(210차), 재검토 불필요 |
| route 계산 자체 mode 게이트 | STEP4에서 `carrot_navi_route()` 진입부에 신규 추가 |
| route_active → arbitration 연결 | `route_speed=None` 반환 시 append 생략 (신규) |
| cereal 텔레메트리 150 sentinel | 로깅 전용으로만 유지, 제어 경로와 분리 |

STEP3 완료. 코드 변경 없음. 사용자 승인 후 STEP4(실제 코드 수정) 착수 예정.
