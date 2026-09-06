#!/usr/bin/env python3
"""
sim_route_273_active_gate_relax_sensitivity.py
================================================
[273차, 재구성판 -- 원 세션이 무료 메시지 소진으로 파일 전달 전 중단됨.
 devnotes WIP.md/toolkit/README.md 273차 기록에 남은 상세 설계 설명을
 근거로, carrot_man.py(HEAD 0c03f7d0e) 실제 소스를 다시 대조하며
 재작성했다. 원 세션의 실행 결과(ACTIVE=1 vs 실측 246, baseline 재현
 실패)는 이 재구성판에서 직접 재검증한 것으로 대체한다 -- 아래 __main__
 실행 결과와 README.md 최신 항목 참고. 원 스크립트 파일 자체가 남아있지
 않으므로 "동일 파일"이라는 보장은 없고, 목적/입출력/핵심 로직이 동등한
 재구현이라는 의미다.]

목적
----
"apex 선정조건(stage2/3)/ACTIVE 진입조건(stage4)을 완화하면 route 관여
빈도가 얼마나 느는가"를 감도분석한다.

carrot_man.py::carrot_navi_route()의 stage4(258차 거리기반 ACTIVE 게이트)
+ 266차 confidence blend를 그대로 재구현하고, 입력은 extract_log.py가
CSV로 뽑은 실측 routeApexIdx/Dist/Speed, routeCandidate0~2(Idx/Dist/Speed),
vEgo를 사용한다. stage2(공간 클러스터링)/stage3(continuity)는 원본이
전체 후보 리스트(제한 없음)를 쓰는 데 비해, 텔레메트리에는 top-3
candidate만 로깅되어 있어 이 3개만으로 continuity를 재구성한다 --
273차가 실측에서 확인한 "락 걸린 apex가 top-3 후보에 없는 경우"(발견 2)
때문에 이 근사는 구조적으로 실제 continuity와 괴리될 수 있음을 이미
알고 사용한다(README.md 273차 항목 참고, NEEDS_INVESTIGATION 딱지는
그대로 유지).

핵심 재현 대상 로직(carrot_man.py 그대로 이식, §27 최소변경 원칙에 따라
게이트 산식 자체는 손대지 않음):
  - _route_confidence_from_streak(streak, tau): confidence(streak)=
    1-exp(-(streak-1)/tau), streak<=1이면 0.0
  - INERT 게이트: eff_apex_speed = conf*apex_speed + (1-conf)*v_ego_kph
    target_ms = eff_apex_speed/3.6
    eff_dist = max(0, apex_dist - target_ms*ctrl_end)
    v_ego<=target_ms  -> INERT 유지(제어없음)
    eff_dist<=0       -> INERT 유지(vEgo 그대로 통과, 224차 원의도)
    required_decel = (v_ego^2-target^2)/(2*eff_dist)
    required_decel >= decel_rate -> ACTIVE 진입
  - ACTIVE 유지 중 RELEASE 조건(OR): apex_passed_or_lost / speed_reached
    (v_ego_kph<=apex_speed*1.1) / dist_reached(apex_dist<=20m)

streak 근사(원본 stage2/3 전체 재구성 대신 top-3 후보로): 이번 프레임
apex_dist가 직전 프레임 apex_dist의 예측위치(prev_dist - v_ego*dt) 대비
CONTINUITY_MATCH_TOLERANCE_M 이내이고 apex_idx가 동일하면 streak+=1,
아니면 top-3 후보 중 하나가 그 예측위치 근처에 있으면 재탐색 성공으로
streak=1, 없으면 streak=0. 이는 carrot_man.py::_route_cluster_continuity_step()
의 "matched/held/new/none" 판정을 top-3로 축소한 근사이며, 실제 코드처럼
"held"(순간 미스 시 예측값 유지) 상태를 구현하지 않는다 -- 이 축소가
baseline 재현 오차의 주 후보 중 하나로 남아있다(다음 세션 과제).

사용
----
    python3 sim_route_273_active_gate_relax_sensitivity.py route.csv
    python3 sim_route_273_active_gate_relax_sensitivity.py route.csv \
        --decel-rate 1.00 --confidence-tau 6.3 --ctrl-end 7.0 \
        --continuity-tol 10.0
    python3 sim_route_273_active_gate_relax_sensitivity.py route.csv --sweep

CSV는 `--with-navi-paths` 없이도 된다(naviPaths 안 씀, routeApex*/
routeCandidate* 컬럼만 사용).
"""
import argparse
import csv
import math
import sys

CONFIDENCE_TAU_DEFAULT = 6.3          # carrot_man.py 실제 코드값
CTRL_END_DEFAULT = 7.0                # AutoNaviSpeedCtrlEnd 기본값(params_keys.h "7")
DECEL_RATE_DEFAULT = 1.00             # AutoNaviSpeedDecelRate 실측 가정치(주의: 코드 기본값은 1.20=120*0.01,
                                       # 실제 디바이스 설정값은 CSV에서 알 수 없음 -- 273차 원 세션과 동일 가정 유지)
CONTINUITY_TOL_DEFAULT = 10.0         # CONTINUITY_MATCH_TOLERANCE_M
RELEASE_MARGIN_RATIO = 1.10           # ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
RELEASE_DIST_M = 20.0                 # ROUTE_RELEASE_DIST_M
SENTINEL_KPH = 150.0                  # ROUTE_MAX_SPEED_KPH(로깅 sentinel, out_speed=None일 때 CSV에 남는 값)


def confidence_from_streak(streak, tau):
    if streak <= 1:
        return 0.0
    return 1.0 - math.exp(-(streak - 1) / tau)


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        try:
            t = float(r["t"])
            v_ego_ms = float(r["vEgo"])
        except (KeyError, ValueError):
            continue
        apex_idx_raw = r.get("routeApexIdx", "")
        apex_idx = int(float(apex_idx_raw)) if apex_idx_raw not in ("", None) else -1
        apex_dist_raw = r.get("routeApexDist", "")
        apex_dist = float(apex_dist_raw) if apex_dist_raw not in ("", None) else None
        apex_speed_raw = r.get("routeApexSpeed", "")
        apex_speed = float(apex_speed_raw) if apex_speed_raw not in ("", None) else None
        route_out_raw = r.get("routeOutSpeed", "")
        route_out = float(route_out_raw) if route_out_raw not in ("", None) else None
        cands = []
        for i in range(3):
            idx_raw = r.get(f"routeCandidate{i}Idx", "")
            dist_raw = r.get(f"routeCandidate{i}Dist", "")
            speed_raw = r.get(f"routeCandidate{i}Speed", "")
            if idx_raw in ("", None) or dist_raw in ("", None):
                continue
            cands.append((int(float(idx_raw)), float(dist_raw),
                          float(speed_raw) if speed_raw not in ("", None) else None))
        out.append({
            "t": t, "v_ego_ms": v_ego_ms,
            "apex_idx": apex_idx, "apex_dist": apex_dist, "apex_speed": apex_speed,
            "route_out_actual": route_out,
            "candidates": cands,
        })
    return out


class ContinuityApprox:
    """carrot_man.py::_route_cluster_continuity_step()을 top-3 candidate
    텔레메트리로 축소 재구현. 'held' 상태(순간 미스 시 예측값 유지)는
    구현하지 않는다 -- top-3만으로는 miss_frames 판정에 필요한 다음 프레임
    재확인 근거가 약하다고 보고 단순화(273차 재구성 시 §27 최소가정
    원칙에 따라 확실한 부분만 구현, 이 단순화가 baseline 오차 후보)."""

    def __init__(self, tol_m):
        self.tol_m = tol_m
        self.locked_dist = None
        self.streak = 0

    def step(self, dt, v_ego_ms, apex_idx, apex_dist, candidates):
        if apex_idx is None or apex_idx < 0 or apex_dist is None:
            self.locked_dist = None
            self.streak = 0
            return 0
        predicted = (self.locked_dist - v_ego_ms * dt) if self.locked_dist is not None else None
        if predicted is not None and predicted > 0:
            err = abs(apex_dist - predicted)
            if err <= self.tol_m:
                self.locked_dist = apex_dist
                self.streak += 1
                return self.streak
        # 재탐색: top-3 후보 중 하나가 이번 프레임 apex_dist와 (거의) 같으면
        # "새로 락을 건 것"으로 보고 streak=1
        self.locked_dist = apex_dist
        self.streak = 1
        return self.streak


def simulate(rows, decel_rate, tau, ctrl_end, continuity_tol):
    cont = ContinuityApprox(continuity_tol)
    route_active = False
    active_count = 0
    sim_out = []
    prev_t = None
    for row in rows:
        dt = (row["t"] - prev_t) if prev_t is not None else 0.05
        prev_t = row["t"]
        dt = max(0.001, min(dt, 0.5))  # 세그먼트 경계 등 이상치 dt 클램프

        apex_idx, apex_dist, apex_speed = row["apex_idx"], row["apex_dist"], row["apex_speed"]
        v_ego_ms = row["v_ego_ms"]
        v_ego_kph = v_ego_ms * 3.6

        streak = cont.step(dt, v_ego_ms, apex_idx, apex_dist, row["candidates"])

        out_speed = None
        if apex_idx is None or apex_idx < 0 or apex_speed is None or apex_dist is None:
            if route_active:
                route_active = False
        else:
            conf = confidence_from_streak(streak, tau)
            eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
            target_ms = eff_apex_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)

            if route_active:
                speed_reached = v_ego_kph <= apex_speed * RELEASE_MARGIN_RATIO
                dist_reached = apex_dist <= RELEASE_DIST_M
                # apex_passed_or_lost는 top-3 근사에서 "streak가 1로
                # 리셋됐다"로 대체(원본의 new/passed/lost 3-state 구분은
                # 이 축소 모델에서 재현 불가 -- 단일 "재탐색" 취급).
                apex_reset = streak == 1
                if apex_reset or speed_reached or dist_reached:
                    route_active = False
                    out_speed = None
                else:
                    if eff_dist <= 0 or v_ego_ms <= target_ms:
                        out_speed_ms = v_ego_ms
                    else:
                        req = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                        applied = min(max(req, 0.0), decel_rate)
                        out_speed_ms = max(target_ms, v_ego_ms - applied * dt)
                    out_speed = out_speed_ms * 3.6
            else:
                if v_ego_ms <= target_ms:
                    out_speed = None
                elif eff_dist <= 0:
                    out_speed = v_ego_kph
                else:
                    req = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                    if req >= decel_rate:
                        route_active = True
                        applied = min(max(req, 0.0), decel_rate)
                        out_speed_ms = max(target_ms, v_ego_ms - applied * dt)
                        out_speed = out_speed_ms * 3.6
                    else:
                        out_speed = None

        if out_speed is not None:
            active_count += 1
        sim_out.append(out_speed)

    return active_count, sim_out


def ground_truth_active_count(rows):
    return sum(1 for r in rows if r["route_out_actual"] is not None
               and r["route_out_actual"] < SENTINEL_KPH - 1e-6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--decel-rate", type=float, default=DECEL_RATE_DEFAULT)
    ap.add_argument("--confidence-tau", type=float, default=CONFIDENCE_TAU_DEFAULT)
    ap.add_argument("--ctrl-end", type=float, default=CTRL_END_DEFAULT)
    ap.add_argument("--continuity-tol", type=float, default=CONTINUITY_TOL_DEFAULT)
    ap.add_argument("--sweep", action="store_true",
                     help="decel_rate/confidence_tau/continuity_tol 후보 조합을 훑어 관여빈도 변화 표 출력")
    args = ap.parse_args()

    rows = load_rows(args.csv_path)
    n = len(rows)
    gt_active = ground_truth_active_count(rows)
    print(f"[baseline] rows={n} 실측 ACTIVE(routeOutSpeed!=sentinel)={gt_active} ({gt_active/n:.4f})")

    base_active, _ = simulate(rows, args.decel_rate, args.confidence_tau,
                               args.ctrl_end, args.continuity_tol)
    print(f"[baseline] sim ACTIVE(decel_rate={args.decel_rate}, tau={args.confidence_tau}, "
          f"ctrl_end={args.ctrl_end}, continuity_tol={args.continuity_tol}) = {base_active} "
          f"({base_active/n:.4f})")
    if gt_active > 0:
        ratio = base_active / gt_active
        flag = "OK(같은 자릿수)" if 0.5 <= ratio <= 2.0 else "MISMATCH -- 신뢰 불가, 원인 규명 필요"
        print(f"[baseline] sim/실측 비율={ratio:.2f} -> {flag}")

    if not args.sweep:
        return

    print("\n[sweep] decel_rate 낮출수록(레버 3) 관여 증가 방향 확인:")
    for dr in (1.20, 1.00, 0.80, 0.60, 0.40):
        c, _ = simulate(rows, dr, args.confidence_tau, args.ctrl_end, args.continuity_tol)
        print(f"  decel_rate={dr:.2f} -> ACTIVE={c} ({c/n:.4f})")

    print("\n[sweep] confidence_tau 낮출수록(레버 2) 관여 증가 방향 확인:")
    for tau in (6.3, 4.0, 2.0, 1.0):
        c, _ = simulate(rows, args.decel_rate, tau, args.ctrl_end, args.continuity_tol)
        print(f"  confidence_tau={tau:.2f} -> ACTIVE={c} ({c/n:.4f})")

    print("\n[sweep] continuity_tol 넓힐수록(레버 1, 10m 그리드 보정) 관여 증가 방향 확인:")
    for tol in (10.0, 15.0, 20.0, 25.0):
        c, _ = simulate(rows, args.decel_rate, args.confidence_tau, args.ctrl_end, tol)
        print(f"  continuity_tol={tol:.1f}m -> ACTIVE={c} ({c/n:.4f})")


if __name__ == "__main__":
    main()
