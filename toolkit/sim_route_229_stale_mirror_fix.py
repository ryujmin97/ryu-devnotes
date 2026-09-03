#!/usr/bin/env python3
"""229차: carrot_man.py::carrot_navi_route()의 조기 return(mode 0/1 전환,
navi 비활성)이 함수 말미의 유일한 carrot_serv mirror 지점(228차 패치 기준
1039/1045행)을 건너뛰어, self.route_active/route_inert(carrot_man 측)는
즉시 False로 갱신되는데 self.carrot_serv.route_active/route_inert(carrot_serv
측, 별개 객체)는 직전 프레임 값에 stale하게 고정될 수 있던 문제를 재현하고,
229차 수정(두 조기 return 지점에 mirror 2줄씩 추가)이 이를 해소하는지
검증한다.

배경: ChatGPT가 228차(5fa0254) 코드리뷰에서 지적한 항목을 Claude가 실제
GitHub 코드를 직접 읽어 확인(WIP.md 229차 참고) -- carrot_serv.py::
update_navi()는 route_speed(반환값)가 None이면 클램프 블록 전체를 스킵하므로
"현재는" 이 stale 값이 실제로 읽히지 않지만(즉시 차량 거동 영향 없음),
향후 다른 로직이 이 두 필드를 참조하면 회귀 소지가 있어 최소 변경으로 수정.

모델링: carrot_man 쪽 상태(self.route_active/route_inert)와 carrot_serv
쪽 상태(self.carrot_serv_route_active/route_inert, 별개 속성)를 명시적으로
분리해, "두 객체 간 미러링 누락"이라는 버그의 본질을 재현한다(기존
sim_route_228_edge_cases_AJ.py는 단일 객체라 이 버그 클래스를 애초에
표현할 수 없었음).

실차 검증: 미실시. 합성 시나리오(단순 상태기계) 시뮬레이션만 수행.
"""

DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0
LOOKAHEAD_CAP_M = 600.0

results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


class RouteSimBase:
    """carrot_man/carrot_serv 상태를 분리 모델링. MIRROR_ON_EARLY_RETURN
    클래스 변수로 229차 수정 적용 여부를 스위치한다."""

    MIRROR_ON_EARLY_RETURN = False  # 하위 클래스가 override

    def __init__(self, curves):
        self.curves = curves
        # carrot_man 측 상태
        self.route_active = False
        self.route_inert = False
        self.route_release_time = None
        # carrot_serv 측 상태(별개 객체 시뮬레이션) -- 함수 말미(정상 경로)
        # mirror만으로 갱신되는, 초기값은 carrot_man과 동일하게 시작
        self.serv_route_active = False
        self.serv_route_inert = False
        self.t = 0.0

    def _mirror_now(self):
        """함수 말미 mirror(228차부터 존재, 정상 종료 경로에서 항상 실행)."""
        self.serv_route_active = self.route_active
        self.serv_route_inert = self.route_inert

    def _find_candidate(self, x):
        for apex_x, apex_speed in self.curves:
            if apex_x > x and (apex_x - x) <= LOOKAHEAD_CAP_M:
                return apex_x, apex_speed
        return None

    def step(self, x, v_ego_kph, route_enabled=True):
        self.t += DT
        v_ego_ms = v_ego_kph / 3.6

        if not route_enabled:
            # mode 0/1 조기 return 지점 (carrot_man.py 650행 부근)
            self.route_active = False
            self.route_inert = False
            self.route_release_time = None
            if self.MIRROR_ON_EARLY_RETURN:
                self._mirror_now()
            return None, "MODE_OFF"  # <- 함수는 여기서 return, 말미 mirror 미실행

        if self.route_release_time is not None:
            if (self.t - self.route_release_time) < ROUTE_RELEASE_HOLD_S:
                return None, "HOLD"  # route_active/inert 변경 없는 return -> 안전(229차 범위 밖)
            self.route_release_time = None

        cand = self._find_candidate(x)
        if cand is None:
            released = False
            if self.route_active:
                self.route_active = False
                self.route_inert = False
                self.route_release_time = self.t
                released = True
            self._mirror_now()  # 정상 경로(함수 계속 진행 후 말미 도달) -- 항상 실행됨
            return None, ("RELEASE_NO_CANDIDATE" if released else "NO_CANDIDATE_INACTIVE")

        apex_x, apex_speed = cand
        apex_dist = apex_x - x

        if self.route_active and apex_dist <= ROUTE_APEX_REACHED_DIST_M:
            self.route_active = False
            self.route_inert = False
            self.route_release_time = self.t
            self._mirror_now()
            return None, "RELEASE_APEX_REACHED"
        elif not self.route_active and v_ego_kph <= apex_speed:
            self.route_inert = False
            self._mirror_now()
            return apex_speed, "GATE_CEILING"
        else:
            self.route_active = True
            target_ms = apex_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * 1.0)
            if eff_dist <= 0:
                out_ms = v_ego_ms
                self.route_inert = False
                branch = "EFF_DIST_LE_0"
            elif v_ego_ms <= target_ms:
                out_ms = target_ms
                self.route_inert = True
                branch = "FAR_INERT"
            else:
                required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                applied = min(max(required, 0.0), 1.5)
                out_ms = max(target_ms, v_ego_ms - applied * DT)
                self.route_inert = False
                branch = "DECEL_FORMULA"
            self._mirror_now()
            return out_ms * 3.6, branch

    def step_navi_inactive(self):
        """navi 비활성 조기 return 지점(carrot_man.py 686행 부근) 별도 모델링."""
        self.t += DT
        self.route_active = False
        self.route_inert = False
        if self.MIRROR_ON_EARLY_RETURN:
            self._mirror_now()
        return None, "NAVI_INACTIVE"  # <- 여기서도 함수는 return, 말미 mirror 미실행


class PreFix229Sim(RouteSimBase):
    """228차(5fa0254) 상태 그대로 -- 조기 return에 mirror 없음(버그 재현용)."""
    MIRROR_ON_EARLY_RETURN = False


class PostFix229Sim(RouteSimBase):
    """229차 패치 적용 후 -- 조기 return에도 mirror 추가(수정 검증용)."""
    MIRROR_ON_EARLY_RETURN = True


# ============================================================
# K. [버그 재현] ACTIVE+far-inert 상태에서 mode 0/1 전환 -> 수정 전에는
#    carrot_serv 측 route_active/route_inert가 stale True로 고정된다.
# ============================================================
sim = PreFix229Sim([(300.0, 50.0)])
sim.step(x=0.0, v_ego_kph=90.0)          # ACTIVE 진입(DECEL_FORMULA)
sim.step(x=10.0, v_ego_kph=50.0)         # far-inert 진입, mirror 실행됨(serv=True/True)
check("K-precondition-serv-was-true", sim.serv_route_active and sim.serv_route_inert,
      f"serv_active={sim.serv_route_active}, serv_inert={sim.serv_route_inert}")
out, branch = sim.step(x=20.0, v_ego_kph=50.0, route_enabled=False)  # mode 0/1 전환
check("K-carrot_man-side-resets-immediately", sim.route_active is False and sim.route_inert is False,
      f"route_active={sim.route_active}, route_inert={sim.route_inert}")
check("K-BUG-serv-side-stays-stale", sim.serv_route_active is True and sim.serv_route_inert is True,
      f"serv_active={sim.serv_route_active}, serv_inert={sim.serv_route_inert} "
      "(수정 전: carrot_man은 False인데 carrot_serv는 stale True로 남음 -- 버그 재현 성공)")

# ============================================================
# L. [수정 검증] 동일 시나리오, 229차 패치 적용 버전 -> carrot_serv도 즉시 False.
# ============================================================
sim2 = PostFix229Sim([(300.0, 50.0)])
sim2.step(x=0.0, v_ego_kph=90.0)
sim2.step(x=10.0, v_ego_kph=50.0)
check("L-precondition-serv-was-true", sim2.serv_route_active and sim2.serv_route_inert,
      f"serv_active={sim2.serv_route_active}, serv_inert={sim2.serv_route_inert}")
out2, branch2 = sim2.step(x=20.0, v_ego_kph=50.0, route_enabled=False)
check("L-carrot_man-side-resets", sim2.route_active is False and sim2.route_inert is False,
      f"route_active={sim2.route_active}, route_inert={sim2.route_inert}")
check("L-FIX-serv-side-resets-too", sim2.serv_route_active is False and sim2.serv_route_inert is False,
      f"serv_active={sim2.serv_route_active}, serv_inert={sim2.serv_route_inert} "
      "(수정 후: 조기 return에서도 즉시 mirror -- stale 해소 확인)")

# ============================================================
# M. [버그 재현, navi 비활성 경로] 동일 패턴을 686행 부근(navi_points_active
#    False)에도 적용해 재현.
# ============================================================
sim3 = PreFix229Sim([(300.0, 50.0)])
sim3.step(x=0.0, v_ego_kph=90.0)
sim3.step(x=10.0, v_ego_kph=50.0)
sim3.step_navi_inactive()
check("M-BUG-navi-inactive-path-also-stale", sim3.serv_route_active is True and sim3.serv_route_inert is True,
      f"serv_active={sim3.serv_route_active}, serv_inert={sim3.serv_route_inert} (navi 비활성 경로도 동일 버그)")

sim4 = PostFix229Sim([(300.0, 50.0)])
sim4.step(x=0.0, v_ego_kph=90.0)
sim4.step(x=10.0, v_ego_kph=50.0)
sim4.step_navi_inactive()
check("N-FIX-navi-inactive-path-resets", sim4.serv_route_active is False and sim4.serv_route_inert is False,
      f"serv_active={sim4.serv_route_active}, serv_inert={sim4.serv_route_inert}")

# ============================================================
# O. [무회귀] 정상 경로(candidate 소실 RELEASE, apex 도달 RELEASE, mode
#    유지 등)는 수정 전/후 동일하게 동작해야 한다(§27 최소 변경 -- 이
#    두 조기 return 외 다른 경로는 건드리지 않았으므로).
# ============================================================
for cls, label in [(PreFix229Sim, "PRE"), (PostFix229Sim, "POST")]:
    s = cls([(100.0, 20.0)])
    s.step(x=0.0, v_ego_kph=30.0)
    s.step(x=50.0, v_ego_kph=10.0)  # far-inert
    out, ev = s.step(x=150.0, v_ego_kph=10.0)  # candidate 소실 -> RELEASE (정상 경로, mirror 항상 실행)
    check(f"O-{label}-release-no-candidate-unaffected", ev == "RELEASE_NO_CANDIDATE" and s.serv_route_active is False,
          f"event={ev}, serv_active={s.serv_route_active}")

print()
n_pass = sum(1 for _, c, _ in results if c)
print(f"TOTAL: {n_pass}/{len(results)} PASS")
