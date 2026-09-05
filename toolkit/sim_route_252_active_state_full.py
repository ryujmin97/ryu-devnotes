#!/usr/bin/env python3
"""
sim_route_252_active_state_full.py (253차 세션, 신규 -- NEEDS_VALIDATION)

목적: design doc 247cha_route_inert_active_redesign.md §11 검증계획 5번
("246차 원거리 apex freeze, 239차 self-elimination 재현 케이스도 새
상태머신에서 해소되는지 확인")을 위해, 252차가 carrot_man.py/
carrot_serv.py에 실제로 반영한 INERT/ACTIVE 래치 상태머신 전체(§3~§5,
_route_cluster_continuity_step 포함)를 carrot_man.py에서 그대로 이식해
실측 dashcam 로그(extract_log.py --with-navi-paths CSV) 위에서 프레임
단위로 재생한다.

sim_route_234_spatial_apex_continuity.py(234차/247차/251차)는 stage2/3
(클러스터링+continuity)만 검증했고 apex identity 안정성(jump_count)만
측정했다 -- ACTIVE 진입/해제, §4/§5의 감속식/해제조건, 246차 freeze가
실제로 해소되는지는 검증 범위 밖이었다. 이 스크립트는 그 상위 레이어까지
포함해 carrot_navi_route()의 관련 분기(§8 severity gate 삭제 이후 상태)를
1:1로 재현한다.

**한계(§28 명시)**:
1. candidate/apex 산출은 naviPaths(carrotMan 발행, 20Hz)로 재구성한
   근사치다 -- 실제 코드와 동일한 3점 곡률/lookup 공식을 쓰지만, 실측
   당시의 부동소수 반올림/GPS 잡음까지 완전히 동일하다고 단정하지 않는다.
2. autoNaviSpeedCtrlEnd(safe_time)/autoNaviSpeedDecelRate는 CSV에 없어
   PARAMS_REGISTRY.md 등록값(safe_time=2.2s, decel=0.70 m/s²)을 고정
   가정으로 사용한다 -- 실제 실차 파라미터와 다르면 감속 프로파일의
   정량값은 달라질 수 있다(정성적 freeze/oscillation 유무 판정에는
   영향이 제한적일 것으로 추정되나 확정 아님).
3. 이 스크립트가 재현하는 것은 "이번 실측 로그의 실제 위치/속도 궤적에
   새 상태머신을 대입했을 때의 출력"이지, 새 상태머신이 실제 차량을
   운전했을 때의 vEgo 궤적(피드백 루프)은 아니다 -- open-loop 재생.
4. 실차 검증 아님(§29). 오프라인 시뮬레이션 한정.

사용:
    python3 sim_route_252_active_state_full.py route.csv \
        [--safe-time 2.2] [--decel-rate 0.70] [--release-margin 1.1] \
        [--continuity-tolerance 10.0] [--far-dist-m 150] \
        [--cruise-gap-kph 15] [--ceiling-track-kph 2.0] [--min-duration-s 2.0]

출력: (a) 실측 CSV의 src/routeOutSpeed 기준 far-apex-freeze episode
(scan_route_far_apex_accel_freeze.py와 동일 탐지식) vs (b) 이 스크립트가
새 상태머신으로 재계산한 out_speed 기준 동일 탐지식 결과를 나란히 비교.
종료 코드는 항상 0(순수 리포트 도구).
"""
import argparse
import csv
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

MACRO_SAMPLE = 4
FINE_SAMPLE = 1
FLOOR_THRESHOLD = 0.001  # ROUTE_CURVE_NEGLIGIBLE_THRESHOLD, 157차 패치 재현(232차 HEAD 이후 동일)
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
ROUTE_APEX_MISS_TOLERANCE_FRAMES = 3
ROUTE_SPEED_LOOP_DT = 0.05


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_candidates(navi_paths_str, road_limit_speed):
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < FINE_SAMPLE * 2 + 1:
        return [], []
    merged = recompute_route_curvature_speed(
        points, distances, sample=MACRO_SAMPLE, sample_fine=FINE_SAMPLE,
        road_limit_speed=road_limit_speed, floor_threshold=FLOOR_THRESHOLD,
    )
    if not merged:
        return [], []
    dists = [m[0] for m in merged]
    speeds = [m[2] for m in merged]
    return dists, speeds


def route_find_clusters(idxs, distances, min_points, max_gap_m):
    # carrot_man.py::route_find_clusters() 1:1 이식
    if not idxs:
        return []
    clusters = []
    cur = [idxs[0]]
    for i in idxs[1:]:
        if distances[i] - distances[cur[-1]] <= max_gap_m:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_points]


class Sim252:
    """carrot_man.py CarrotMan의 route_active/_route_cluster_* 상태 +
    carrot_navi_route() 중 severity-gate-삭제 이후 분기(§8/251차/252차
    HEAD, carrot_man.py L640-1149 참고)를 1:1 이식."""

    def __init__(self, safe_time, decel_rate, release_margin, continuity_tolerance_m):
        self.route_active = False
        self._route_cluster_locked_dist = None
        self._route_cluster_locked_speed = None
        self._route_cluster_miss_frames = 0
        self.safe_time = safe_time
        self.decel_rate = decel_rate
        self.release_margin = release_margin
        self.continuity_tolerance_m = continuity_tolerance_m
        # [253차 수정 -- 최초 포팅 누락분] design doc §6 "해제 후 2초 Gate" /
        # carrot_man.py carrot_navi_route() 상단
        # "if self.route_release_time is not None: ... return"과 동일한
        # RELEASE 직후 hold-off 타이머. 이게 없으면 RELEASE 다음 프레임에
        # 바로 재탐색+재진입이 가능해져, apex_mode가 프레임마다 흔들리는
        # 구간에서 실제 코드에는 없는 인위적 ENGAGE/RELEASE 진동이
        # 시뮬레이션에서만 발생한다(최초 버전 자가 검증 중 발견 -- §28).
        self.route_release_t = None
        self.t = 0.0
        self.ROUTE_RELEASE_HOLD_S = 2.0

    def _continuity_step(self, clusters, distances, speeds, v_ego_ms):
        dt = ROUTE_SPEED_LOOP_DT
        predicted = (self._route_cluster_locked_dist - v_ego_ms * dt) \
            if self._route_cluster_locked_dist is not None else None

        matched = None
        if predicted is not None and predicted > 0 and clusters:
            best, best_err = None, None
            for c in clusters:
                idx = c[0]
                err = abs(distances[idx] - predicted)
                if best_err is None or err < best_err:
                    best, best_err = idx, err
            if best_err is not None and best_err <= self.continuity_tolerance_m:
                matched = best

        if matched is not None:
            self._route_cluster_locked_dist = distances[matched]
            self._route_cluster_locked_speed = speeds[matched]
            self._route_cluster_miss_frames = 0
            return matched, self._route_cluster_locked_dist, self._route_cluster_locked_speed, "matched"

        if self._route_cluster_locked_dist is not None:
            self._route_cluster_miss_frames += 1
            if (self._route_cluster_miss_frames < ROUTE_APEX_MISS_TOLERANCE_FRAMES
                    and predicted is not None and predicted > 0):
                self._route_cluster_locked_dist = predicted
                return -1, predicted, self._route_cluster_locked_speed, "held"
            self._route_cluster_locked_dist = None
            self._route_cluster_locked_speed = None
            self._route_cluster_miss_frames = 0

        if clusters:
            idx = clusters[0][0]
            self._route_cluster_locked_dist = distances[idx]
            self._route_cluster_locked_speed = speeds[idx]
            self._route_cluster_miss_frames = 0
            return idx, distances[idx], speeds[idx], "new"

        return -1, None, None, "none"

    def step(self, v_ego_ms, road_limit_speed_kph, distances, speeds, t_abs=None):
        # [253차] hold-off 타이머는 실제 코드처럼 wall-clock(monotonic)
        # 기준이어야 하므로, 프레임 카운트*고정dt 누적 대신 CSV의 실측
        # 절대시각(t_abs, extract_log.py 출력)을 그대로 사용한다 --
        # 세그먼트 경계 등으로 프레임 간격이 20Hz(0.05s)에서 벗어나는
        # 구간에서도 2초 hold 판정이 실측 시간과 어긋나지 않도록.
        self.t = t_abs if t_abs is not None else (self.t + ROUTE_SPEED_LOOP_DT)
        if self.route_release_t is not None:
            if (self.t - self.route_release_t) < self.ROUTE_RELEASE_HOLD_S:
                return None, -1, 0.0, 0.0
            self.route_release_t = None

        v_ego_kph = v_ego_ms * 3.6
        candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed_kph]
        clusters = route_find_clusters(candidates, distances,
                                        ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        apex_idx, apex_dist, apex_speed, apex_mode = self._continuity_step(
            clusters, distances, speeds, v_ego_ms)

        if apex_mode == "none":
            if self.route_active:
                self.route_active = False
                self.route_release_t = self.t
            return None, -1, 0.0, 0.0

        if self.route_active:
            apex_passed_or_lost = apex_mode == "new"
            speed_reached = v_ego_kph <= apex_speed * self.release_margin
            if apex_passed_or_lost or speed_reached:
                self.route_active = False
                self.route_release_t = self.t
                out_speed = None
            else:
                out_speed = self._decel_step(v_ego_ms, apex_dist, apex_speed)
        else:
            target_ms = apex_speed / 3.6
            eff_dist = max(0.0, apex_dist - target_ms * self.safe_time)
            if eff_dist <= 0:
                out_speed = v_ego_kph
            elif v_ego_ms > target_ms:
                self.route_active = True
                out_speed = self._decel_step(v_ego_ms, apex_dist, apex_speed)
            else:
                out_speed = apex_speed
        return out_speed, apex_idx, apex_dist, apex_speed

    def on_missing_navi_data(self, t_abs):
        # carrot_navi_route()의 "resampled_points 부족" 분기(즉시 해제,
        # hold 없음, 132차 원칙)를 근사. naviPaths가 비어 candidate 산출
        # 자체가 불가능한 프레임(§28 한계 1번)에 대응.
        self.t = t_abs
        if self.route_active:
            self.route_active = False
        self._route_cluster_locked_dist = None
        self._route_cluster_locked_speed = None
        self._route_cluster_miss_frames = 0

    def _decel_step(self, v_ego_ms, apex_dist, apex_speed):
        target_ms = apex_speed / 3.6
        eff_dist = max(0.0, apex_dist - target_ms * self.safe_time)
        if eff_dist <= 0 or v_ego_ms <= target_ms:
            out_speed_ms = v_ego_ms
        else:
            required_decel_mss = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            applied_decel_mss = min(max(required_decel_mss, 0.0), self.decel_rate)
            out_speed_ms = max(target_ms, v_ego_ms - applied_decel_mss * ROUTE_SPEED_LOOP_DT)
        return out_speed_ms * 3.6


def replay(rows, safe_time, decel_rate, release_margin, continuity_tolerance_m):
    sim = Sim252(safe_time, decel_rate, release_margin, continuity_tolerance_m)
    out = []
    for row in rows:
        try:
            v_ego_ms = float(row["vEgo"])
            road_limit = float(row.get("nRoadLimitSpeed") or 50.0)
        except (TypeError, ValueError):
            out.append(dict(row, sim_out_speed="", sim_src=""))
            continue
        dists, speeds = build_candidates(row.get("naviPaths", ""), road_limit)
        if not dists:
            sim.on_missing_navi_data(float(row["t"]))
            out.append(dict(row, sim_out_speed="", sim_src=""))
            continue
        out_speed, apex_idx, apex_dist, apex_speed = sim.step(
            v_ego_ms, road_limit, dists, speeds, t_abs=float(row["t"]))
        newrow = dict(row)
        newrow["sim_out_speed"] = "" if out_speed is None else f"{out_speed:.2f}"
        newrow["sim_src"] = "route" if out_speed is not None else ""
        newrow["sim_apex_dist"] = f"{apex_dist:.1f}" if apex_idx != -1 or out_speed is not None else ""
        out.append(newrow)
    return out


def scan_freeze(rows, src_key, out_speed_key, far_dist_m, cruise_gap_kph, ceiling_track_kph, min_duration_s,
                 apex_dist_key="routeApexDist"):
    episodes = []
    cur = None
    for row in rows:
        try:
            t = float(row["t"])
            v_ego_kph = float(row["vEgo"]) * 3.6
            v_cruise = float(row["vCruise"])
            out_speed = float(row[out_speed_key]) if row.get(out_speed_key) not in (None, "") else None
            apex_dist = float(row[apex_dist_key]) if row.get(apex_dist_key) not in (None, "") else None
        except (TypeError, ValueError):
            out_speed, apex_dist = None, None
        cond = (row.get(src_key) == "route" and apex_dist is not None and apex_dist > far_dist_m
                and (v_cruise - v_ego_kph) > cruise_gap_kph
                and out_speed is not None and abs(out_speed - v_ego_kph) < ceiling_track_kph)
        if cond:
            if cur is None:
                cur = {"start": t, "end": t}
            else:
                cur["end"] = t
        else:
            if cur is not None:
                if cur["end"] - cur["start"] >= min_duration_s:
                    episodes.append(cur)
                cur = None
    if cur is not None and cur["end"] - cur["start"] >= min_duration_s:
        episodes.append(cur)
    return episodes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--safe-time", type=float, default=2.2)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--release-margin", type=float, default=1.1)
    ap.add_argument("--continuity-tolerance", type=float, default=10.0)
    ap.add_argument("--far-dist-m", type=float, default=150.0)
    ap.add_argument("--cruise-gap-kph", type=float, default=15.0)
    ap.add_argument("--ceiling-track-kph", type=float, default=2.0)
    ap.add_argument("--min-duration-s", type=float, default=2.0)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    print(f"loaded {len(rows)} rows from {args.csv_path}")

    sim_rows = replay(rows, args.safe_time, args.decel_rate, args.release_margin, args.continuity_tolerance)

    real_ep = scan_freeze(rows, "src", "routeOutSpeed", args.far_dist_m, args.cruise_gap_kph,
                           args.ceiling_track_kph, args.min_duration_s, apex_dist_key="routeApexDist")
    sim_ep = scan_freeze(sim_rows, "sim_src", "sim_out_speed", args.far_dist_m, args.cruise_gap_kph,
                          args.ceiling_track_kph, args.min_duration_s, apex_dist_key="sim_apex_dist")

    print(f"\n=== 실측(CSV routeOutSpeed/src 기준) far-apex-freeze episodes: {len(real_ep)} ===")
    for e in real_ep:
        print(f"  t={e['start']:.1f}-{e['end']:.1f} (dur={e['end']-e['start']:.2f}s)")

    print(f"\n=== 시뮬레이션(252차 INERT/ACTIVE 상태머신 재생) far-apex-freeze episodes: {len(sim_ep)} ===")
    for e in sim_ep:
        print(f"  t={e['start']:.1f}-{e['end']:.1f} (dur={e['end']-e['start']:.2f}s)")

    print(f"\n요약: 실측 {len(real_ep)}건 -> 시뮬레이션(252차 상태머신) {len(sim_ep)}건")
    print("주의: 이 비교는 open-loop 재생(§28/스크립트 docstring 한계 4번) -- "
          "실측 궤적을 그대로 새 로직에 대입한 결과이지 실제 피드백 루프 재현이 아님.")


if __name__ == "__main__":
    main()
