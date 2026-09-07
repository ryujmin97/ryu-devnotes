#!/usr/bin/env python3
"""
sim_route_297_reacquire_gap_real_corpus.py (297차 신규)

목적
----
296차가 self-test(합성)만 완료하고 "corpus 확보 후"로 미뤄둔
sim_route_296_active_reacquire_gap.py::RouteStateMachine을 실측
route1~4 corpus(283~296차가 반복 분석해온 그 corpus, 2026-09-06
16:56~18:03, `extract_log.py --with-navi-paths`로 재추출)에 대해
실행한다.

296차 스크립트는 `--frames-json`으로 프레임 리스트(JSON)를 받는데,
그 포맷(candidates:[(dist,speed),...])은 stage0(클러스터링 이전)
전체 후보 배열이 필요하다. 이 어댑터가 CSV의 naviPaths 원시
폴리라인에서 매 프레임 그 배열을 직접 재구성해 296차 상태기계에
그대로 흘려보낸다.

핵심 발견(이 세션, 코드 대조로 확인) -- devnotes 기존 toolkit의
gap
------------------------------------------------------------------
`analysis_helpers.py::recompute_route_curvature_speed()`(147/158차)는
279차에 프로덕션(`carrot_man.py`)에 새로 도입된
`self.carrot_serv.mapTurnSpeedFactor` 곱셈을 반영하지 않는다.
그 함수를 그대로 쓰면 (특히 이 corpus처럼 실측
`MapTurnSpeedFactor=110%`인 경우) apex 목표속도가 실제 프로덕션보다
낮게(=더 가혹하게) 재구성되어, 이 스크립트가 재현하려는 continuity
상태기계 입력 자체가 왜곡된다.

이 스크립트는 `analysis_helpers.parse_navi_paths()`(변경 없음)로
폴리라인만 재사용하고, 곡률->속도 계산은 `carrot_man.py`
960~1066행(macro+fine, mapTurnSpeedFactor 곱셈 포함, floor
threshold=ROUTE_CURVE_NEGLIGIBLE_THRESHOLD=0.001)을 이 파일에
독립적으로 다시 이식한다(§27 -- 기존 devnotes 함수를 고치는 대신
결과가 다른 새 함수를 별도로 두어, 기존 함수를 쓰던 다른 68개
toolkit 스크립트의 동작에 영향을 주지 않음. 기존 함수 자체가 "고정
factor=1.0 가정" 하에서는 여전히 정확하므로 버그로 규정하지 않고
"279차 이후 프로덕션과의 gap"으로만 기록).

사용
----
    python3 sim_route_297_reacquire_gap_real_corpus.py \\
        --csv /home/claude/route_a3b3373495.csv \\
        --map-turn-speed-factor 1.10 \\
        --ctrl-end 8.0 --decel-rate 0.70

--map-turn-speed-factor/--ctrl-end/--decel-rate 기본값은 287/291차가
실측 확인한 이 corpus 촬영 당시 `params_backup-6.json` 값
(MapTurnSpeedFactor=110%, AutoNaviSpeedCtrlEnd=8초,
AutoNaviSpeedDecelRate=70=0.70m/s²)과 동일하게 맞춰 두었다.
"""
import argparse
import csv
import math
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths

from sim_route_296_active_reacquire_gap import RouteStateMachine

# ---- carrot_man.py 960~1066행에서 그대로 이식(HEAD d2f47d1=290차) ----
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360.,
                     1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
DISTANCE_INTERVAL = 10.0
MACRO_SAMPLE = 4
ROUTE_CURVATURE_FINE_SAMPLE = 1


def _calculate_curvature(p1, p2, p3):
    # carrot_man.py calculate_curvature()와 100% 동일.
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


def _interp(x, xp, fp):
    # np.interp와 동일 동작(정렬된 xp 가정, 단조 선형보간, 범위 밖은 clamp).
    if x <= xp[0]:
        return fp[0]
    if x >= xp[-1]:
        return fp[-1]
    for i in range(1, len(xp)):
        if x <= xp[i]:
            x0, x1 = xp[i - 1], xp[i]
            y0, y1 = fp[i - 1], fp[i]
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return fp[-1]


def recompute_route_speeds_with_factor(points, distances_unused, road_limit_speed,
                                        map_turn_speed_factor):
    """carrot_man.py 960~1066행(macro+fine, mapTurnSpeedFactor 곱셈
    포함)을 그대로 재현. `points`는 parse_navi_paths()가 반환한
    resampled 좌표 리스트(10m 간격, distance=-10.0부터 시작하는
    production의 resampled_points와 동일 포맷으로 이미 CSV에
    naviPaths로 저장돼 있음). 반환: [(distance, speed_cap), ...]
    (stage0 후보 배열, 클러스터링 이전).
    """
    n = len(points)
    if n < MACRO_SAMPLE * 2 + 1:
        return []

    distances = []
    macro_abs_curv = []
    curvatures = []
    distance = -10.0
    for i in range(n - MACRO_SAMPLE * 2):
        distance += DISTANCE_INTERVAL
        p1, p2, p3 = points[i], points[i + MACRO_SAMPLE], points[i + MACRO_SAMPLE * 2]
        curvature = _calculate_curvature(p1, p2, p3)
        curvatures.append(curvature)
        macro_abs_curv.append(abs(curvature))
        distances.append(distance)

    speeds = []
    for i in range(len(curvatures)):
        speed = _interp(macro_abs_curv[i], V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
        speed = speed * map_turn_speed_factor
        if macro_abs_curv[i] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
            speed = max(speed, road_limit_speed)
        speeds.append(speed)

    sample_fine = ROUTE_CURVATURE_FINE_SAMPLE
    if sample_fine and sample_fine < MACRO_SAMPLE and n >= sample_fine * 2 + 1:
        n_fine = min(len(distances), n - sample_fine * 2)
        if n_fine > 0:
            for j in range(n_fine):
                p1 = points[j]
                p2 = points[j + sample_fine]
                p3 = points[j + sample_fine * 2]
                f_curv = _calculate_curvature(p1, p2, p3)
                f_abs = abs(f_curv)
                f_speed = _interp(f_abs, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
                f_speed = f_speed * map_turn_speed_factor
                if f_abs < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                    f_speed = max(f_speed, road_limit_speed)
                if f_speed < speeds[j]:
                    speeds[j] = f_speed

    return list(zip(distances, speeds))


def build_frames(csv_path, map_turn_speed_factor):
    frames = []
    with open(csv_path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            navi = row.get("naviPaths", "")
            if not navi:
                continue
            try:
                v_ego = float(row["vEgo"])
                road_limit = float(row["nRoadLimitSpeed"])
                t = float(row["t"])
            except (ValueError, TypeError):
                continue
            if road_limit <= 0:
                continue
            points, distances = parse_navi_paths(navi)
            if not points:
                continue
            entries = recompute_route_speeds_with_factor(points, distances, road_limit,
                                                           map_turn_speed_factor)
            candidates = [(d, s) for d, s in entries if s < road_limit]
            frames.append({
                "t": t,
                "v_ego_ms": v_ego,
                "v_ego_kph": v_ego * 3.6,
                "candidates": candidates,
            })
    return frames


def run_route(csv_path, ctrl_end, decel_rate, map_turn_speed_factor):
    frames = build_frames(csv_path, map_turn_speed_factor)
    sm = RouteStateMachine()
    n_active_true = 0
    for f in frames:
        out_speed, mode, active = sm.step(
            f["t"], f["candidates"], f["v_ego_ms"], f["v_ego_kph"],
            ctrl_end, decel_rate)
        if active:
            n_active_true += 1
    return frames, sm, n_active_true


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--map-turn-speed-factor", type=float, default=1.10,
                     help="287/291차 실측 params_backup-6.json 기본값(110%%)")
    ap.add_argument("--ctrl-end", type=float, default=8.0,
                     help="287차 실측 AutoNaviSpeedCtrlEnd 기본값(8초)")
    ap.add_argument("--decel-rate", type=float, default=0.70,
                     help="287차 실측 AutoNaviSpeedDecelRate 기본값(0.70 m/s^2)")
    args = ap.parse_args()

    frames, sm, n_active = run_route(args.csv, args.ctrl_end, args.decel_rate,
                                      args.map_turn_speed_factor)
    print(f"csv={args.csv}")
    print(f"  프레임(naviPaths 있는 것만): {len(frames)}")
    print(f"  route_active=True로 관측된 프레임: {n_active}")
    print(f"  seamless forced-release 이벤트: {len(sm.events)}건")
    n_immediate = sum(1 for e in sm.events if e["immediate_reentry"])
    n_needs_decel = sum(1 for e in sm.events if e["new_apex_needs_decel"])
    print(f"    immediate_reentry=True: {n_immediate}건")
    print(f"    new_apex_needs_decel=True: {n_needs_decel}건 / {len(sm.events)}건")
    for e in sm.events:
        print(f"    t={e['t']:.2f} mode={e['mode']} new_dist={e['new_apex_dist']:.1f}"
              f" new_speed={e['new_apex_speed']:.1f} needs_decel="
              f"{e['new_apex_needs_decel']} immediate_reentry={e['immediate_reentry']}")


if __name__ == "__main__":
    main()
