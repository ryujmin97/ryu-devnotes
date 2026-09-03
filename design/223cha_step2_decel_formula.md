# 223차 STEP2 — 신규 vEgo 기반 감속식 설계 (코드 수정 없음)

Base commit: 7519a3a91df530ee6667183759b6c94afa8ae287 (221차 HEAD, STEP1과 동일, 변경 없음 확인됨)
대상: selfdrive/carrot/carrot_man.py `carrot_navi_route()` 내 raw out_speed 계산부
전제: STEP1 F항 사용자 결정 3건 반영 완료
  1. 203차 vs 223차 → 223차(전면 재설계) 확정
  2. relative-severity 게이트 → 부활 안 함 (candidates[0] 그대로 유지)
  3. ROUTE_MAX_SPEED_KPH=150 → ceiling/sentinel 모두 최종 삭제, 단 대체 반환값은 STEP3(arbitration 확인)에서 확정
실차 검증: 미실시 (이번 세션은 수식 설계만, 코드/시뮬레이션 미착수)

---

## 1. 기존 공식이 왜 안 되는가 (§8 근거 재확인)

기존 `calculate_current_speed(left_dist, safe_speed_kph, safe_time, safe_decel_rate)`:

```
safe_dist  = safe_speed * safe_time
decel_dist = left_dist - safe_dist
out = sqrt(safe_speed^2 + 2*safe_decel_rate*decel_dist)   # decel_dist>0일 때
```

이 식은 **vEgo를 입력받지 않는다.** "target과 거리만으로, 지금 이 거리에서 낼 수 있는
최대 허용속도"를 계산하는 카메라(sdi_speed)식 ceiling 공식이다.

문제는 이 공식이 `safe_decel_rate`(=`autoNaviSpeedDecelRate`)에 대해 **항상 증가함수**라는
점이다 (distance 고정 시 ∂out/∂decel > 0). 즉 사용자가 "더 적극적으로 감속해라"는 의미로
decel_rate를 높이면, 이 공식은 오히려 "더 늦게까지 빨리 가도 된다"고 허용속도를 올려버린다
— 205~221차에 걸쳐 vEgo ceiling/sharpest_candidate/vCruise ceiling 패치가 계속 추가된
근본 원인이 바로 이 역방향 민감도다. §8은 이 함수형(sqrt(target²+2·decel·dist)) 자체의
재사용을 금지 — ceiling 항이든 raw 항이든, vEgo로 감싸서 clamp하는 방식으로 우회해도
"거리 고정 시 decel 증가 → out 증가"라는 역방향 민감도 자체는 사라지지 않으므로 우회
불가 (검증 4번에서 반례로 직접 확인).

---

## 2. 신규 설계: "필요 감속도" 기반 실시간 피드백 공식

### 2.1 핵심 아이디어

매 프레임(20Hz), **지금 이 순간의 실제 vEgo**와 **지금 이 순간의 apex까지 남은 거리**만
가지고 "지금부터 등감속으로 감속하면 apex에서 정확히 target에 도달하기 위해 필요한
감속도"를 역산한다. 이 필요 감속도를 `autoNaviSpeedDecelRate`(편의상 comfort cap)로
상한을 씌운 뒤, 그 값만큼 **이번 프레임 동안 vEgo에서 한 스텝만** 깎아 출력한다.

이전 프레임의 route 출력값(=`_route_speed_prev`류)은 전혀 쓰지 않는다 — 매 프레임 입력은
`carState.vEgo`(실측값)와 현재 apex_dist/apex_speed(매 프레임 새로 계산되는 값)뿐이다.

### 2.2 이산시간 수식

```
v_ego_ms   = carState.vEgo                                   # 실측, m/s
target_ms  = apex_speed_kph / 3.6
eff_dist   = max(0.0, apex_dist - target_ms * safe_time)      # safe_time = autoNaviSpeedCtrlEnd 그대로 재사용
                                                                # (§27 최소변경 -- 파라미터 의미 보존, 도착 전 target
                                                                #  안정화 여유시간)

if v_ego_ms <= target_ms or eff_dist <= 0:
    required_decel_mss = 0.0        # 이미 target 이하로 주행 중이거나 apex 도달 -- 개입 불필요
else:
    required_decel_mss = (v_ego_ms**2 - target_ms**2) / (2.0 * eff_dist)

applied_decel_mss = clamp(required_decel_mss, 0.0, autoNaviSpeedDecelRate)   # comfort cap, 음수 방지

out_speed_ms  = max(target_ms, v_ego_ms - applied_decel_mss * ROUTE_SPEED_LOOP_DT)
out_speed_kph = out_speed_ms * 3.6
```

(`ROUTE_SPEED_LOOP_DT`는 132차가 이미 도입한 기존 상수 재사용, 20Hz=0.05s)

### 2.3 §9 불변식(가속 금지) 증명

`applied_decel_mss >= 0` 이 항상 보장되므로 (clamp 하한 0):

```
out_speed_ms = max(target_ms, v_ego_ms - applied_decel_mss*dt) <= v_ego_ms   (∵ applied_decel_mss*dt >= 0)
```

**매 프레임 out_speed <= vEgo가 수식 구조 자체로 보장된다** (조건 분기나 별도 ceiling
항 없이). 이는 이전 ceiling들(vEgo ceiling, sharpest_candidate ceiling, 150 ceiling)이
사후적으로 clamp해서 만들던 것과 달리, 애초에 "vEgo에서 빼는" 구조라 위반이 원천 불가능.

**→ 222차가 발견한 `liveRouteSpeed > vEgo` 현상(정지 후 재출발+커브, §20 CASE 14)은
이 구조에서 수학적으로 재발할 수 없다.** (39건 중 11건, 218차 기록) 이것이 §8이 요구하는
"완전히 다른 공식"으로 판단하는 핵심 근거.

### 2.4 §8 민감도 역전 검증 (decel_rate 증가 → out 감소 방향인지)

`eff_dist`가 이미 필요 제동거리보다 충분히 여유 있는 정상 구간(`required_decel_mss <
autoNaviSpeedDecelRate`)에서는 `applied_decel_mss = required_decel_mss`로, decel_rate
파라미터 자체가 출력에 전혀 영향을 주지 않는다(자연스러운 등감속 곡선을 그대로 따름).

decel_rate가 실제로 개입하는 것은 **부족한 경우** (`required_decel_mss >
autoNaviSpeedDecelRate`, 즉 커브가 갑자기 튀어나오거나 앞 프레임 지연 등으로 필요
감속도가 comfort cap을 넘는 경우)뿐이며, 이때:

```
out_speed_ms = v_ego_ms - autoNaviSpeedDecelRate * dt
```

decel_rate를 올리면 `applied_decel_mss`가 커지므로 **out_speed는 내려간다** (기존
공식과 정반대 방향, 사용자가 "더 적극적으로 감속"을 의도했을 때 기대하는 방향과 일치).
→ 기존 공식의 반대 방향 민감도 문제가 구조적으로 해소됨.

### 2.5 §7 요구사항(현재속도에서 시작) 충족 확인

ACTIVE 진입 순간(vEgo=80, target=50 가정)의 첫 프레임: eff_dist가 크므로
required_decel_mss가 작게 나옴 → out_speed ≈ vEgo(80에 가까운 값)로 시작 →
apex 접근하며 eff_dist가 줄어들수록 required_decel_mss가 자연히 커지며 등감속 곡선을
따라 target으로 수렴. "현재 속도(vEgo)에서 시작해서 target까지 내려간다"는 요구사항을
그대로 만족.

### 2.6 상태(state) 최소성 재확인 (§17)

이 공식은 프레임 간 어떤 route 전용 내부 상태도 요구하지 않는다 — 입력은 매 프레임
(1) `carState.vEgo`(실측, 이미 존재), (2) `apex_dist`/`apex_speed`(이번 STEP1에서
KEEP 확정된 candidates[0] 로직이 매 프레임 새로 계산, 이미 존재)뿐이다.
`_route_speed_prev`, boost armed, ceiling state 등 §15/§17이 삭제 지시한 항목은
이 공식에 애초에 등장하지 않는다(우회 보존이 아니라 구조적으로 불필요해짐).

---

## 3. Edge Case

| 상황 | 처리 |
|---|---|
| `apex_dist <= 0` (apex 도달/통과) | 공식 진입 전에 §10 RELEASE 상태전이가 먼저 처리 (STEP4에서 상태기계에 구현) — 공식 자체는 방어적으로 `eff_dist<=0 → required_decel=0 → out=target` 처리해 0-division 방지 |
| `vEgo <= target` (ACTIVE 진입 후 다른 요인으로 vEgo가 먼저 target 밑으로 내려간 경우, 예: 선행차 감속) | `required_decel_mss=0` → route는 개입하지 않고 out=vEgo로 사실상 무해(inert) — §6 ACTIVE 게이트는 유지하되 apex 도달까지는 그대로 두고, apex에서 정상 RELEASE(§10) |
| `eff_dist` 계산에서 `safe_time`이 너무 커서(비정상 파라미터) `eff_dist`가 자주 0이 되는 경우 | `max(0.0, ...)`로 이미 방어됨, 이 경우 사실상 target 근접까지 개입 없다가 마지막에 급하게 잡히는 형태가 될 수 있음 — STEP5 시뮬레이션에서 실제 `autoNaviSpeedCtrlEnd` 파라미터값으로 A/B 확인 필요 |

---

## 4. STEP2 결론

- 신규 감속식 확정. §7/§8/§9 요구사항 수식으로 증명 완료 (코드/시뮬레이션 미실시,
  이번은 설계 문서 단계).
- 이 식은 완전히 새로운 함수형이며(입력에 vEgo 실측값 포함, 상태 없음, decel_rate에
  대한 민감도 방향이 기존과 반대), §8이 금지한 `sqrt(target²+2·decel·dist)` 공식과
  다른 식이다. 단, "등감속 물리(v²=v₀²-2ad)" 자체는 동일 물리법칙이므로 완전히 새로운
  물리를 발명한 것은 아니고, **어떤 값을 입력으로 삼아 어떤 값을 역산하는지**가 반대로
  바뀐 것(과거: target+거리→허용 상한 속도 정산 / 신규: vEgo+거리+target→필요 감속도
  역산 후 1스텝만 적용)임을 명시.

## 5. 다음 단계 (STEP3 착수 조건)

- STEP3: `carrot_navi_route()` → `liveRouteSpeed` → `speed_n_sources` →
  `min()` → 최종 제어까지 arbitration 전체 흐름 확인 (carrot_serv.py 1090~1120줄
  주변, 이번 세션에서 일부만 훑음).
- STEP3에서 함께 결정할 것: STEP1 F-3 (`ROUTE_MAX_SPEED_KPH=150` sentinel 최종
  대체값 — route 비활성 시 arbitration에서 이 소스를 아예 제외할지, 다른 sentinel을
  쓸지).
- STEP2는 순수 설계 문서이며 코드 변경 없음 — 사용자 검토/승인 후 STEP3 진행.
