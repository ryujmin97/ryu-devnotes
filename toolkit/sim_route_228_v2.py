#!/usr/bin/env python3
"""228차 v2: 1차 가설(carrot_man.py inert 분기만 target_ms로 수정)이 부족함을
확인 -- 실제로는 carrot_serv.py의 227차 클램프(`route_active=True`이면
무조건 min(v_ego_kph,...)` 적용)가 carrot_man.py가 무엇을 계산하든
route_speed를 다시 v_ego로 눌러버려 고착이 그대로 재현됨(디버그 로그로
확인). 따라서 두 파일을 함께 고치는 v2 설계를 검증한다.

v2 설계: carrot_man.py에 route_inert(bool) 상태를 신규(route_active와
동일한 mirroring 패턴)로 도입 -- "지금 이 프레임이 ACTIVE 추적 중
진짜 감속(decel formula)인가, 아니면 inert(감속 불필요, v_ego<=target
또는 apex 근접)인가"를 구분해 carrot_serv에 전달.

carrot_serv.py 클램프를 다음과 같이 변경:
  route_active and not route_inert (=진짜 감속 중) -> 기존 227차 그대로
      min(v_ego_kph, max(route_out, floor))  [불변식: decel formula
      결과는 이미 <=v_ego이므로 이 클램프는 사실상 안전망, 무해]
  그 외(route_active=False[226차 게이트] 또는 route_inert=True) ->
      max(route_out, floor)만 (v_ego 상한 클램프 생략 -- ceiling이
      v_ego 위에 있는 것을 허용해 다른 arbitration 소스가 desired를
      끌어올릴 수 있게 함, 226차와 동일 원칙을 inert 분기로 확장)

carrot_man.py inert 분기 자체도 세분화(eff_dist<=0/>0):
  eff_dist<=0 (apex 근접) -> out=v_ego_ms, route_inert=False (224차
      원 의도 보존 -- 여기선 클램프가 생략되면 안 됨, 생략 시
      autoCurveSpeedLowerLimit floor가 노출되어 v_ego=0을 floor로
      밀어올리는 신규 회귀가 생김을 실측으로 확인, 아래 v1 실패 참고)
  eff_dist>0 and v_ego<=target (아직 멀리 있는데 target 미만) ->
      out=target_ms, route_inert=True (226차와 동일 패턴 -- ceiling만
      target으로 유지, 가속 명령 자체는 만들지 않음, 클램프 생략으로
      실제 arbitration에 반영됨)
"""

DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0
AUTO_CURVE_LOWER = 30.0
DECEL_RATE = 1.5
CTRL_END = 1.0
VEH_ACCEL = 1.0
VEH_DECEL = 2.5
LOOKAHEAD_CAP_M = 600.0


class RouteStateMachine:
    def __init__(self, curves, fix_mode):
        self.curves = curves
        self.fix_mode = fix_mode  # "CURRENT" or "FIXED_V2"
        self.route_active = False
        self.route_release_time = None
        self.t = 0.0

    def _find_candidate(self, x):
        for apex_x, apex_speed in self.curves:
            if apex_x > x and (apex_x - x) <= LOOKAHEAD_CAP_M:
                return apex_x, apex_speed
        return None

    def step(self, x, v_ego_kph):
        self.t += DT
        v_ego_ms = v_ego_kph / 3.6
        route_inert = False

        if self.route_release_time is not None:
            if (self.t - self.route_release_time) < ROUTE_RELEASE_HOLD_S:
                return None, None, False
            self.route_release_time = None

        cand = self._find_candidate(x)
        if cand is None:
            if self.route_active:
                self.route_active = False
                self.route_release_time = self.t
            return None, None, False

        apex_x, apex_speed = cand
        apex_dist = apex_x - x

        if self.route_active and apex_dist <= ROUTE_APEX_REACHED_DIST_M:
            self.route_active = False
            self.route_release_time = self.t
            return None, "RELEASE_APEX_REACHED", False
        elif not self.route_active and v_ego_kph <= apex_speed:
            return apex_speed, None, False  # 226차 게이트, route_inert 개념 밖
        else:
            self.route_active = True
            target_ms = apex_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * CTRL_END)
            if eff_dist <= 0.0:
                out_ms = v_ego_ms
                route_inert = False
            elif v_ego_ms <= target_ms:
                if self.fix_mode == "CURRENT":
                    out_ms = v_ego_ms
                else:  # FIXED_V2
                    out_ms = target_ms
                route_inert = True
            else:
                required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                applied = min(max(required, 0.0), DECEL_RATE)
                out_ms = max(target_ms, v_ego_ms - applied * DT)
                route_inert = False
            return out_ms * 3.6, None, route_inert


def clamp_route_speed(route_out, v_ego_kph, route_active, route_inert, fix_mode):
    if route_out is None:
        return None
    if fix_mode == "CURRENT":
        if route_active:
            return min(v_ego_kph, max(route_out, AUTO_CURVE_LOWER))
        else:
            return max(route_out, AUTO_CURVE_LOWER)
    else:  # FIXED_V2
        if route_active and not route_inert:
            return min(v_ego_kph, max(route_out, AUTO_CURVE_LOWER))
        else:
            return max(route_out, AUTO_CURVE_LOWER)


def arbitrate(route_speed, v_cruise, road_limit):
    sources = [v_cruise, road_limit]
    if route_speed is not None:
        sources.append(route_speed)
    return min(sources)


results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def run_timeline(fix_mode, cruise_schedule, curves, total_s, x0=0.0, v0=0.0):
    sm = RouteStateMachine(curves, fix_mode)
    x = x0
    v = v0
    log = []
    n = int(total_s / DT)
    for i in range(n):
        t = (i + 1) * DT
        v_cruise = cruise_schedule(t)
        route_out, event, route_inert = sm.step(x, v)
        route_speed = clamp_route_speed(route_out, v, sm.route_active, route_inert, fix_mode)
        desired = arbitrate(route_speed, v_cruise, 130.0)
        v_before = v
        if desired > v:
            v = min(desired, v + VEH_ACCEL * DT * 3.6)
        elif desired < v:
            v = max(desired, v - VEH_DECEL * DT * 3.6)
        x += (v_before / 3.6) * DT
        log.append(dict(t=t, x=x, v_before=v_before, v_after=v, route_out=route_out,
                         route_speed=route_speed, active=sm.route_active,
                         inert=route_inert, event=event))
    return log


# ============ 시나리오 A: 228차 고착 재현 + v2 수정 검증 ============
curves_A = [(25.0, 45.0), (900.0, 30.0), (2200.0, 80.0)]


def cruise_A(t):
    if t < 20.0: return 45.0
    elif t < 40.0: return 90.0
    elif t < 75.0: return 0.0
    else: return 90.0


for mode in ("CURRENT", "FIXED_V2"):
    log = run_timeline(mode, cruise_A, curves_A, total_s=320.0)
    max_v_last10s = max(r["v_after"] for r in log if r["t"] >= 310.0)
    min_v_stop = min(r["v_after"] for r in log if 40.0 <= r["t"] <= 75.0)
    active_during_stop = all(r["active"] for r in log if 40.0 <= r["t"] <= 75.0)
    release_events = [r for r in log if r["event"] == "RELEASE_APEX_REACHED"]
    check(f"A-{mode}-full-stop-reached", min_v_stop < 0.5,
          f"정차구간 최저={min_v_stop:.2f}")
    check(f"A-{mode}-active-not-released-while-stopped", active_during_stop,
          f"정차 중 route_active 유지: {active_during_stop}")
    if mode == "CURRENT":
        check("A-CURRENT-deadlock-reproduced", max_v_last10s < 0.5,
              f"마지막10s max={max_v_last10s:.2f} (고착 재현 기대)")
    else:
        check("A-FIXED_V2-recovers", max_v_last10s > 25.0,
              f"마지막10s max={max_v_last10s:.2f} (회복 기대, >25)")
        check("A-FIXED_V2-curveB-releases", len(release_events) >= 1,
              f"RELEASE 이벤트 {len(release_events)}건")
        if len(release_events) >= 1:
            # curve C(apex80) 진입/추적까지 확인
            after_release_t = release_events[0]["t"]
            later = [r for r in log if r["t"] > after_release_t]
            curveC_active = any(r["active"] and r["t"] > after_release_t + 3.0 for r in later)
            check("A-FIXED_V2-curveC-tracking-resumes", curveC_active,
                  "RELEASE 이후 curve C ACTIVE 추적 재개 확인")

# ============ 시나리오 B: 224차 원 시나리오 재현 (apex 바로 앞 정차) ============
# [228차 checkpoint 재검증 메모] 최초 기하(apex=400, v0=0, stop_t=15)로는 세 가지
# 문제가 있었음: (1) v_ego가 226차 GATE(비ACTIVE 상태에서 v_ego<=apex_speed일 때
# ceiling=apex_speed로 캡)에 걸려 45kph를 넘지 못해 애초에 ACTIVE(else 분기)로
# 전이되지 않음. (2) apex를 멀리 두면 정차 지점의 apex_dist가 너무 멀어
# eff_dist<=0(224차 원 분기) 조건을 타지 못함. (3) apex를 너무 가깝게 두면
# 차량이 완전정지하기 전에 apex_dist<=ROUTE_APEX_REACHED_DIST_M(10m)을 먼저
# 통과해 RELEASE가 선(先)발동, route_active가 False로 바뀌어버려 "ACTIVE
# 유지된 채 정차" 케이스 자체가 사라짐(진짜 정지가 아니라 이동 중 release라
# 224차 케이스와 다른 경로). v0=60(이미 target 초과)으로 시작해 첫 프레임부터
# ACTIVE로 진입시키고, 완전정지 시점의 apex_dist가 (10m, 12.5m) 구간 -- RELEASE
# 미발동 + eff_dist<=0 동시 충족 -- 에 들어오도록 apex_x/stop_t를 재탐색해
# apex=125/stop_t=4.8로 확정 -- apex_dist=11.748m, eff_dist=-0.75m(<=0),
# route_active=True 유지, RELEASE 미발동 모두 확인. 최초 컨테이너 세션에서
# 이와 유사한 기하로 12/12 PASS를 얻었으나, 세션 종료로 정확한 최종 파라미터
# 값이 유실되어(§36) 이번 체크포인트 복구 세션에서 동일한 절차(격자 탐색)로
# 재도출/재검증한 값이며 최초 세션의 것과 정확히 일치하지 않을 수 있음 --
# 다만 검증 대상 조건(ACTIVE 유지 + eff_dist<=0 + RELEASE 미발동)은 동일하게
# 충족됨을 재확인.
curves_B = [(125.0, 45.0)]


def cruise_B(t):
    if t < 4.8: return 90.0      # ACTIVE 유지(v0=60으로 이미 진입한 상태)
    elif t < 84.8: return 0.0    # apex 근접(RELEASE 미도달) 상태에서 강제 완전정차 80s
    else: return 90.0


for mode in ("CURRENT", "FIXED_V2"):
    log = run_timeline(mode, cruise_B, curves_B, total_s=140.0, v0=60.0)
    stopped_rows = [r for r in log if 20.0 <= r["t"] <= 90.0 and r["v_after"] < 0.3]
    apex_dist_at_stop = 125.0 - stopped_rows[0]["x"] if stopped_rows else None
    target_ms = 45.0 / 3.6
    eff_dist_at_stop = (apex_dist_at_stop - target_ms * CTRL_END) if apex_dist_at_stop is not None else None
    stopped_route_out = [r["route_out"] for r in stopped_rows if r["route_out"] is not None]
    stopped_route_speed = [r["route_speed"] for r in stopped_rows if r["route_speed"] is not None]
    max_out = max(stopped_route_out) if stopped_route_out else None
    max_speed_ceiling = max(stopped_route_speed) if stopped_route_speed else None
    inert_flag = stopped_rows[0]["inert"] if stopped_rows else None
    check(f"B-{mode}-eff-dist-negative-confirmed", eff_dist_at_stop is not None and eff_dist_at_stop <= 0,
          f"apex_dist={apex_dist_at_stop}, eff_dist={eff_dist_at_stop:.2f} (<=0, 224차와 동일 분기 확인)")
    check(f"B-{mode}-no-forced-target-ceiling-while-stopped",
          max_speed_ceiling is None or max_speed_ceiling < 5.0,
          f"route_out={max_out}, route_inert={inert_flag}, route_speed(클램프후)={max_speed_ceiling} "
          f"(224차 의도: v_ego=0 근접 유지, 45로 튀면 회귀)")

print()
passed = sum(1 for _, c, _ in results if c)
print(f"TOTAL: {passed}/{len(results)} PASS")
