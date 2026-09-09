#!/usr/bin/env python3
"""
sim_route_342_release_condition_removal.py (342차 초안, work/ 임시 -- 세션종료 전
toolkit/ 반영 여부 판단 필요, §22)
================================================================
목적: 341차/341차계속이 확정한 두 조건
  (1) ACTIVE 릴리즈 조건 speed_reached: v_ego_kph <= apex_speed * RELEASE_MARGIN_RATIO
  (2) STEP2/INERT 게이트의 v_ego_ms <= target_ms 얼리엑싯
을 제거했을 때 실차로그(000003d4--59a8ae5773, x20seg, 23,776행)에서
route_active flapping/거동이 어떻게 바뀌는지 관찰한다.

**주의(ANALYSIS_ONLY, ryu 코드 무변경)**: 이 스크립트는 diag_required_decel_341.py/
sim_route_273의 게이트 산식을 그대로 복사한 뒤 두 조건만 제거한 변형이다(§21 --
기존 로직 재사용, 변경 지점만 명시). carrot_man.py 실제 코드는 건드리지 않았다.
Master 승인 없이는 이 변형을 ryu에 반영하지 않는다(§27).

**(2) 제거 시 주석**: carrot_man.py L1723 `if eff_dist<=0 or v_ego_ms<=target_ms`의
OR 중 `eff_dist<=0`은 그대로 유지(0-division 가드), `v_ego_ms<=target_ms`만
제거한다. 이 경우 eff_dist>0이고 이미 v_ego_ms<target_ms(목표속도보다 이미 느림)인
프레임에서 required_decel_mss가 음수가 되고, 이를 `max(...,0.0)`으로 0에 클립하면
out_speed_ms=max(target_ms, v_ego_ms-0)=target_ms > v_ego_ms가 되어 **route가
현재 속도보다 높은 속도(=가속)를 명령**하게 된다 -- 이는 224/228차가 고쳤던
회귀(§4 "route는 vEgo를 초과 명령해서는 안 된다")와 동일한 패턴이므로 이 스크립트는
그 발생 빈도/크기를 별도로 계측한다(`accel_commanded` 플래그).

사용:
    python3 sim_route_342_release_condition_removal.py <csv> --summary
    python3 sim_route_342_release_condition_removal.py <csv> <t0> <t1>
"""
import csv
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim_route_273_active_gate_relax_sensitivity import (
    ContinuityApprox, confidence_from_streak, load_rows,
    CONFIDENCE_TAU_DEFAULT, CTRL_END_DEFAULT, DECEL_RATE_DEFAULT,
    CONTINUITY_TOL_DEFAULT, RELEASE_MARGIN_RATIO as _STALE_RELEASE_MARGIN_RATIO,
    RELEASE_DIST_M,
)

# [342차 발견] sim_route_273(273차 작성)의 RELEASE_MARGIN_RATIO=1.10은
# carrot_man.py 290차 변경(1.1->1.05, devnotes 290차) 이전 값으로 stale.
# diag_required_decel_341.py가 이 상수를 그대로 import해서 341차 결과가
# 실제 배포 코드(현재 HEAD 7b3dfec4, ROUTE_ACTIVE_RELEASE_MARGIN_RATIO=1.05)
# 와 다른 마진으로 계산됐을 가능성이 있다. 이 스크립트는 실제 코드값(1.05)을
# 사용한다 -- 아래에서 override.
RELEASE_MARGIN_RATIO = 1.05

ROUTE_SPEED_LOOP_DT = 0.05  # carrot_man.py ROUTE_SPEED_LOOP_DT와 동일(20Hz)


def load_src(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {float(r["t"]): r["src"] for r in rows}


def simulate(rows, decel_rate, tau, ctrl_end, continuity_tol,
             remove_speed_reached, remove_target_early_exit,
             remove_target_active=None, remove_target_inert=None):
    """
    remove_target_early_exit: 하위호환용 -- True면 ACTIVE/INERT 둘 다 제거.
    remove_target_active / remove_target_inert: 각각 단독 지정 시 이 값이
    remove_target_early_exit보다 우선한다(342차 후속 -- "릴리즈 조건에만
    국한"이라는 사용자 질문에 답하기 위해 ACTIVE-STEP2 분기와 INERT
    진입게이트 분기를 독립적으로 켜고 끌 수 있게 분리).
    """
    if remove_target_active is None:
        remove_target_active = remove_target_early_exit
    if remove_target_inert is None:
        remove_target_inert = remove_target_early_exit
    cont = ContinuityApprox(continuity_tol)
    route_active = False
    prev_t = None
    out = []
    for row in rows:
        t = row["t"]
        dt = (t - prev_t) if prev_t is not None else 0.05
        prev_t = t
        dt = max(0.001, min(dt, 0.5))

        apex_idx, apex_dist, apex_speed = row["apex_idx"], row["apex_dist"], row["apex_speed"]
        v_ego_ms = row["v_ego_ms"]
        v_ego_kph = v_ego_ms * 3.6
        streak = cont.step(dt, v_ego_ms, apex_idx, apex_dist, row["candidates"])

        was_active = route_active
        reason = None
        req_decel = None
        eff_apex_speed = None
        out_speed_kph = None
        accel_commanded = False  # (2) 제거로 인한 "route가 vEgo 초과 명령" 관측 플래그

        if apex_idx is None or apex_idx < 0 or apex_speed is None or apex_dist is None:
            route_active = False
            if was_active:
                reason = "no_apex"
        else:
            conf = confidence_from_streak(streak, tau)
            eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
            target_ms = eff_apex_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)

            if route_active:
                apex_reset = streak == 1
                dist_reached = apex_dist <= RELEASE_DIST_M
                if remove_speed_reached:
                    speed_reached = False  # (1) 제거
                else:
                    speed_reached = v_ego_kph <= apex_speed * RELEASE_MARGIN_RATIO
                if apex_reset or speed_reached or dist_reached:
                    route_active = False
                    reason = ("apex_reset" if apex_reset else
                              "speed_reached" if speed_reached else "dist_reached")
                else:
                    # STEP2 -- ACTIVE 상태에서의 target_ms 얼리엑싯.
                    # remove_target_active=True면 이 분기(§ACTIVE 전용)만
                    # 제거(eff_dist<=0 0-division 가드는 유지).
                    skip = (eff_dist <= 0) if remove_target_active else (eff_dist <= 0 or v_ego_ms <= target_ms)
                    if skip:
                        out_speed_ms = v_ego_ms
                    else:
                        req_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                        applied = min(max(req_decel, 0.0), decel_rate)
                        out_speed_ms = max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)
                    if out_speed_ms > v_ego_ms + 1e-9:
                        accel_commanded = True
                    out_speed_kph = out_speed_ms * 3.6
            else:
                # INERT 진입게이트의 target_ms 체크.
                # remove_target_inert=True면 이 분기(§INERT 전용)만 제거.
                cond1 = (v_ego_ms <= target_ms) if not remove_target_inert else False
                if cond1:
                    pass
                elif eff_dist <= 0:
                    pass
                else:
                    req_decel = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                    if req_decel >= decel_rate:
                        route_active = True

        out.append({
            "t": t, "route_active": route_active, "was_active": was_active,
            "reason": reason, "apex_idx": apex_idx, "apex_dist": apex_dist,
            "apex_speed": apex_speed, "v_ego_kph": v_ego_kph,
            "req_decel": req_decel, "eff_apex_speed": eff_apex_speed, "streak": streak,
            "out_speed_kph": out_speed_kph, "accel_commanded": accel_commanded,
        })
    return out


def run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window,
                 remove_speed_reached, remove_target_early_exit, label,
                 remove_target_active=None, remove_target_inert=None):
    from collections import Counter
    rows = load_rows(csv_path)
    sim = simulate(rows, decel_rate, tau, ctrl_end, continuity_tol,
                    remove_speed_reached, remove_target_early_exit,
                    remove_target_active, remove_target_inert)

    releases = [(i, s) for i, s in enumerate(sim) if s["was_active"] and not s["route_active"]]
    print(f"=== {label} ===")
    print(f"[전체] route_active True->False 릴리즈 이벤트: {len(releases)}건")
    print("  reason 분포:", dict(Counter(s["reason"] for _, s in releases)))

    flap = []
    for i, s in releases:
        t0 = s["t"]
        reentered = False
        for j in range(i + 1, len(sim)):
            if sim[j]["t"] - t0 > flap_window:
                break
            if sim[j]["route_active"]:
                reentered = True
                break
        if reentered:
            flap.append(s)
    print(f"[{flap_window}s 이내 재진입=flapping] {len(flap)}건")
    print("  reason 분포:", dict(Counter(s["reason"] for s in flap)))

    active_frames = sum(1 for s in sim if s["route_active"])
    print(f"[route_active 프레임 비율] {active_frames}/{len(sim)} ({100.0*active_frames/len(sim):.1f}%)")

    accel_frames = [s for s in sim if s["accel_commanded"]]
    print(f"[accel_commanded(=out_speed>v_ego, route가 가속 명령)] {len(accel_frames)}건")
    if accel_frames:
        max_gap = max(s["out_speed_kph"] - s["v_ego_kph"] for s in accel_frames)
        print(f"  최대 초과폭: {max_gap:.2f}kph")
        ts = [s["t"] for s in accel_frames]
        print(f"  최초/최후 발생 t: {ts[0]:.2f} / {ts[-1]:.2f}")
    print()
    return sim


def run_window(csv_path, t0, t1, decel_rate, tau, ctrl_end, continuity_tol,
               remove_speed_reached, remove_target_early_exit):
    rows = load_rows(csv_path)
    src_map = load_src(csv_path)
    sim = simulate(rows, decel_rate, tau, ctrl_end, continuity_tol,
                    remove_speed_reached, remove_target_early_exit)

    print(f"{'t':>9} {'src':>6} {'idx':>4} {'apexD':>7} {'apexS':>6} {'vEgo':>6} "
          f"{'outSpd':>7} {'streak':>6} {'active':>6} {'reason':>12} {'accel!':>6}")
    for s in sim:
        if t0 <= s["t"] <= t1:
            src_actual = src_map.get(s["t"], "?")
            out_spd = s["out_speed_kph"]
            print(f"{s['t']:9.2f} {src_actual:>6} "
                  f"{(s['apex_idx'] if s['apex_idx'] is not None else -1):4d} "
                  f"{(s['apex_dist'] if s['apex_dist'] is not None else float('nan')):7.1f} "
                  f"{(s['apex_speed'] if s['apex_speed'] is not None else float('nan')):6.1f} "
                  f"{s['v_ego_kph']:6.1f} "
                  f"{(out_spd if out_spd is not None else float('nan')):7.1f} "
                  f"{s['streak']:6d} {str(s['route_active']):>6} {str(s['reason']):>12} "
                  f"{'YES' if s['accel_commanded'] else '':>6}")


def main():
    csv_path = sys.argv[1]
    decel_rate = DECEL_RATE_DEFAULT
    tau = CONFIDENCE_TAU_DEFAULT
    ctrl_end = CTRL_END_DEFAULT
    continuity_tol = CONTINUITY_TOL_DEFAULT
    flap_window = 2.0
    summary_mode = "--summary" in sys.argv[2:]

    rest = [a for a in sys.argv[2:] if a != "--summary"]
    for a in list(rest):
        if a.startswith("--decel-rate="):
            decel_rate = float(a.split("=", 1)[1]); rest.remove(a)
        elif a.startswith("--tau="):
            tau = float(a.split("=", 1)[1]); rest.remove(a)
        elif a.startswith("--ctrl-end="):
            ctrl_end = float(a.split("=", 1)[1]); rest.remove(a)
        elif a.startswith("--continuity-tol="):
            continuity_tol = float(a.split("=", 1)[1]); rest.remove(a)
        elif a.startswith("--flap-window="):
            flap_window = float(a.split("=", 1)[1]); rest.remove(a)

    if summary_mode:
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window,
                    remove_speed_reached=False, remove_target_early_exit=False,
                    label="BASELINE (현재 코드, 341차와 동일)")
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window,
                    remove_speed_reached=True, remove_target_early_exit=False,
                    label="(1) speed_reached 제거만")
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window,
                    remove_speed_reached=False, remove_target_early_exit=True,
                    label="(2) v_ego_ms<=target_ms 제거만(ACTIVE+INERT 둘 다)")
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window,
                    remove_speed_reached=True, remove_target_early_exit=True,
                    label="(1)+(2) 두 조건 모두 제거")
        print("### 342차 후속 -- ACTIVE 전용 / INERT 전용 분리 ###\n")
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window,
                    remove_speed_reached=False, remove_target_early_exit=False,
                    remove_target_active=True, remove_target_inert=False,
                    label="(2a) target_ms 제거 -- ACTIVE STEP2만(INERT는 그대로), speed_reached 유지")
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window,
                    remove_speed_reached=True, remove_target_early_exit=False,
                    remove_target_active=True, remove_target_inert=False,
                    label="(2a)+(1) target_ms(ACTIVE만) + speed_reached 동시 제거")
        run_summary(csv_path, decel_rate, tau, ctrl_end, continuity_tol, flap_window,
                    remove_speed_reached=False, remove_target_early_exit=False,
                    remove_target_active=False, remove_target_inert=True,
                    label="(2b) target_ms 제거 -- INERT 진입게이트만(ACTIVE는 그대로), speed_reached 유지")
    else:
        t0 = float(rest[0])
        t1 = float(rest[1])
        run_window(csv_path, t0, t1, decel_rate, tau, ctrl_end, continuity_tol,
                   remove_speed_reached=True, remove_target_early_exit=True)


if __name__ == "__main__":
    main()
