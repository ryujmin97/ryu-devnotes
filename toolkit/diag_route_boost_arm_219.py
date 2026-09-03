#!/usr/bin/env python3
"""
219차 -- 199차 discontinuity boost가 t=1004~1030류 사례(WIP 218차가 "apex_speed
104->44로 튀었다 돌아오는 동안 liveRouteSpeed가 기본 램프율로만 25초+ 하강"으로
기술한 케이스)에서 왜 발동하지 않았는지 프레임별 진단.

기존 toolkit/sim_route_217_ceiling_vcruise_ab.py의 Branch 클래스(199차 boost
로직을 프로덕션과 100% 동일하게 이식, sanity check median|diff|=0.74kph로
신뢰도 확인됨)를 그대로 import해서 재사용한다(§21 -- 새 재구성 로직을
중복 작성하지 않음). 이 스크립트는 Branch.step() 호출 전/후로 진단값
(apex_delta_kph, boost_armed 상태, required_decel_mss)을 추가로 계산해
출력하는 관측 레이어만 얹는다.

**핵심 발견(219차)**: t=1004~1030 구간을 프레임 단위로 재생한 결과, 199차
게이트(ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH=15.0kph)는 이 구간 전체에서
단 한 번도 무장(armed)되지 않았다(armed_count=0). 원인은 apex_speed가 실제로는
"한 프레임에서 갑자기 15kph 이상 떨어지는" 불연속이 아니라, apexIdx가 매
프레임 인접 후보(10m 간격)로 계속 전환되면서 잘게 쪼개진 계단식 하강(구간 내
최대 단일 프레임 낙차 10.75kph, t=1005.38)으로 나타나기 때문 -- 199차 게이트는
"단일 프레임 급락"만 감지하도록 설계되어 있어 이런 "누적은 크지만 프레임당은
작은" 하강 패턴을 구조적으로 감지할 수 없다. 즉 "부스트가 발동했는데
무력화됐다"가 아니라 "애초에 이 케이스는 부스트의 감지 대상이 아니다"가
정확한 원인.

--decel-rate 옵션으로 218차 결정(0.70->1.00 m/s²)도 동일 케이스에 재적용해
비교 가능(개선은 있으나 제한적: 23.19s -> 20.04s, armed_count 여전히 0).

CSV 컬럼 요구: sim_route_217_ceiling_vcruise_ab.py와 동일(t, vEgo, vCruise,
naviPointsActive, routeApexIdx, routeApexDist, routeApexSpeed, routeOutSpeed,
ccPoseValid, positionDtSinceFix, liveRouteSpeed). naviPaths는 불필요(이 진단은
ceiling/candidate 재구성이 아니라 boost arm 로직만 보므로 raw_col=routeOutSpeed를
그대로 사용).

사용법:
  python3 diag_route_boost_arm_219.py [csv_path] [t0] [t1] [--decel-rate=1.0]
"""
import csv
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/claude/ryu-devnotes/toolkit")
import sim_route_217_ceiling_vcruise_ab as base_mod
from sim_route_217_ceiling_vcruise_ab import (
    Branch, ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH, ROUTE_VEGO_BOOST_MAX_MSS,
    load_rows, f
)


def run(csv_path, t0, t1, decel_rate, verbose=True):
    base_mod.AUTO_NAVI_SPEED_DECEL_RATE = decel_rate
    rows = load_rows(csv_path)
    br = Branch()
    if verbose:
        print(f"{'t':>8} {'idx':>4} {'apexD':>6} {'apexS':>7} {'d_apex':>7} {'armed':>6} "
              f"{'vEgo':>6} {'accel':>7} {'out':>7} {'live':>7}")
    max_abs_delta = 0.0
    max_delta_t = None
    armed_count = 0
    spike_t = None
    below50_t = None
    for r in rows:
        t = f(r, "t")
        active = r["naviPointsActive"] == "True"
        v_ego_ms = f(r, "vEgo")
        apex_dist = f(r, "routeApexDist")
        apex_speed = f(r, "routeApexSpeed")
        raw_col = f(r, "routeOutSpeed", 300.0)
        live_actual = f(r, "liveRouteSpeed", -1.0)
        apex_idx = int(float(r["routeApexIdx"])) if r["routeApexIdx"] not in ("", None) else -1
        cc_pose_valid = r.get("ccPoseValid", "") == "True"
        position_dt_since_fix = f(r, "positionDtSinceFix")

        if not active:
            br.reset()
            continue

        prev_apex = br.apex_speed_prev
        apex_delta = (prev_apex - apex_speed) if prev_apex is not None else None
        accel_kmh_before = decel_rate * 3.6

        out = br.step(raw_col, apex_dist, apex_speed, v_ego_ms, cc_pose_valid, position_dt_since_fix)
        accel_kmh_after = br.prev  # not directly available; recompute via boost_armed flag below
        accel_kmh = accel_kmh_before
        if br.boost_armed and apex_dist > 0:
            v_target_ms = apex_speed / 3.6
            if v_ego_ms > v_target_ms:
                req = (v_ego_ms ** 2 - v_target_ms ** 2) / (2.0 * apex_dist)
                if req > decel_rate:
                    accel_kmh = min(req, ROUTE_VEGO_BOOST_MAX_MSS) * 3.6

        if t0 <= t <= t1:
            if apex_delta is not None and abs(apex_delta) > max_abs_delta:
                max_abs_delta, max_delta_t = abs(apex_delta), t
            if br.boost_armed:
                armed_count += 1
            if out >= 100 and spike_t is None:
                spike_t = t
            if spike_t is not None and below50_t is None and out < 50.0:
                below50_t = t
            if verbose:
                print(f"{t:8.2f} {apex_idx:4d} {apex_dist:6.1f} {apex_speed:7.1f} "
                      f"{('%.1f' % apex_delta) if apex_delta is not None else '  n/a':>7} "
                      f"{str(br.boost_armed):>6} {v_ego_ms*3.6:6.1f} {accel_kmh:7.2f} "
                      f"{out:7.1f} {live_actual:7.1f}")

    print()
    print(f"=== decel_rate={decel_rate} m/s^2 요약 (t={t0}~{t1}) ===")
    print(f"구간 내 최대 |apex_delta|: {max_abs_delta:.2f}kph (t={max_delta_t}), "
          f"임계값={ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH}kph 초과 여부: "
          f"{max_abs_delta > ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH}")
    print(f"armed 프레임 수: {armed_count}")
    if spike_t and below50_t:
        print(f"스파이크(out>=100, t={spike_t:.2f}) -> out<50 도달(t={below50_t:.2f}): "
              f"{below50_t-spike_t:.2f}s 소요")


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/x18seg_215cha_route.csv"
    t0 = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
    t1 = float(sys.argv[3]) if len(sys.argv) > 3 else 1035.0
    decel_rate = 0.70
    for a in sys.argv[4:]:
        if a.startswith("--decel-rate="):
            decel_rate = float(a.split("=", 1)[1])
    run(csv_path, t0, t1, decel_rate)


if __name__ == "__main__":
    main()
