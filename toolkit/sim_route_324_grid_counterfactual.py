#!/usr/bin/env python3
"""324차: 10m/5m/2.5m grid counterfactual -- 322-D stateful reproduction 확장.

목적: 323차 계측(`routeOrphanRawPath`, cereal @70)으로 확보한 **실제 orphan
발생 프레임의 원본(resample_10m_np 이전) relative_coords**를 이용해,
"10m sampling 때문에 실제 curve geometry가 사라져서 orphan/cluster/apex가
불안정해지는가?"를 실측으로 검증한다. 321차가 남긴 "orphan 국소 5m/2.5m
재샘플" 실험 설계(macro/fine chord 물리적 고정: 10m=sample4/fine1,
5m=sample8/fine2, 2.5m=sample16/fine4)를 합성 데이터가 아닌 실 corpus에
적용한다.

**설계 원칙(사용자 지시, 324차 확정)**:
1. 기존 322-D stateful reproduction(10m production exact reproduction)을
   그대로 보존한다 -- `recompute_grid()`는 sample/sample_fine/distance_interval을
   3021차 방식대로 파라미터화했을 뿐, sample=4/fine=1/interval=10.0 기본값으로
   호출하면 322d의 `recompute_full()`과 100% 동일한 로직(§27, 이번 세션
   자체 회귀검증으로 확인 -- 아래 `--validate` 참고).
2. 입력부만 raw geometry로 확장한다: `routeOrphanSingletonCount>0`인
   프레임(=routeOrphanRawPath가 채워진 프레임)에서만, naviPaths(이미 10m
   리샘플된 production 결과) 대신 raw `relative_coords`를 5m/2.5m로
   재샘플(`resample_10m_np`와 동일 알고리즘, distance_interval만 다름)한
   결과를 사용한다.
3. **중요한 근사(한계, §28에 명시)**: orphan이 아닌 프레임(대다수)에는
   raw geometry가 없다(323차 트리거 설계가 `orphan_count>0` 단일조건이므로
   -- WIP.md 323차 항목 참고). 이런 프레임에서는 5m/2.5m 조건도 10m
   production 결과(clusters/orphans/distances/speeds)를 그대로 재사용한다.
   즉 "그리드가 orphan 프레임 자체의 즉각적 candidate/cluster 판정에 주는
   영향"만 실측이고, "orphan이 아니었던 프레임이 더 촘촘한 그리드에서도
   여전히 orphan이 아니었을 것"은 검증이 아니라 가정이다. 이 가정이
   깨지는 경우(그리드 변경으로 새로운 orphan이 생기는 경우)는 이 스크립트
   범위 밖 -- 그런 일이 실제로 있는지는 별도 신규 계측(orphan이 아닌
   프레임의 raw geometry 계측) 없이는 확인 불가.
4. 3개(10m/5m/2.5m) 상태 트래커(`ContinuityState`/`ProvisionalTracker`)를
   전체 20Hz 프레임 시퀀스에 걸쳐 **동시에, 매 프레임 스텝**시킨다(스킵
   프레임 리셋 규칙도 322d와 동일하게 3개 트래커에 동일 적용) -- 이래야
   locked_dist의 시간 감쇠(`predicted = locked_dist - v_ego*dt`)가 세 조건
   모두에서 동일한 실시간 기준으로 진행되어 "그리드 차이"만 격리된다.

**의존**: `sim_route_322d_stateful_replay.py`(ContinuityState/
ProvisionalTracker/confidence_from_streak/parse_navi_paths/
route_find_clusters/calculate_curvature/상수 전체, §21 재사용,
import로 그대로 가져옴). `extract_log.py`(323차 갱신판, --with-navi-paths)로
뽑은 CSV(`routeOrphanRawPath` 컬럼 필요).

사용:
  python3 sim_route_324_grid_counterfactual.py <CSV> --validate
  python3 sim_route_324_grid_counterfactual.py <CSV> --out-episodes ep.csv
"""
import argparse
import csv
import sys

import numpy as np

from sim_route_322d_stateful_replay import (
    ContinuityState, ProvisionalTracker, confidence_from_streak,
    parse_navi_paths, route_find_clusters, calculate_curvature, recompute_full,
    V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS, ROUTE_CURVE_NEGLIGIBLE_THRESHOLD,
    ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M, ROUTE_SPEED_LOOP_DT,
    ROUTE_ACTIVE_RELEASE_MARGIN_RATIO, ROUTE_RELEASE_DIST_M,
    MAP_TURN_SPEED_FACTOR, AUTONAVI_SPEED_CTRL_END, AUTONAVI_SPEED_DECEL_RATE,
)

# [324차 params_backup-1.json 재확인, x18seg corpus] -- x17seg(322차)와 동일값
# (MapTurnSpeedFactor=110/AutoNaviSpeedCtrlEnd=8/AutoNaviSpeedDecelRate=90/
# TurnSpeedControlMode=2), 별도 상수 재정의 없이 322d의 값을 그대로 재사용
# 가능함을 이번 세션에서 재확인(§26, corpus 바뀔 때마다 재확인 원칙).

GRID_CONFIGS = {
    "10m": dict(sample=4, sample_fine=1, interval=10.0),
    "5m":  dict(sample=8, sample_fine=2, interval=5.0),
    "2.5m": dict(sample=16, sample_fine=4, interval=2.5),
}


def resample_arclen(points_xy, distance_interval):
    """carrot_man.py::resample_10m_np()와 100% 동일 알고리즘, interval만 매개변수화.
    (§27 -- 로직 자체는 원본 그대로, 상수만 외부에서 주입)"""
    pts = np.asarray(points_xy, dtype=np.float64)
    if len(pts) < 2:
        return [tuple(p) for p in pts]
    seg_vec = np.diff(pts, axis=0)
    seg_len = np.hypot(seg_vec[:, 0], seg_vec[:, 1])
    cum_len = np.concatenate(([0.0], np.cumsum(seg_len)))
    total_len = cum_len[-1]
    if total_len <= 0:
        return [tuple(pts[0])]
    n_samples = int(total_len // distance_interval) + 1
    sample_d = np.arange(n_samples, dtype=np.float64) * distance_interval
    sample_d = sample_d[sample_d <= total_len]
    idx = np.searchsorted(cum_len, sample_d, side="right") - 1
    idx = np.clip(idx, 0, len(seg_len) - 1)
    seg_start_len = cum_len[idx]
    seg_total_len = seg_len[idx]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(seg_total_len > 0, (sample_d - seg_start_len) / seg_total_len, 0.0)
    p_start = pts[idx]
    p_end = pts[idx + 1]
    out_xy = p_start + (p_end - p_start) * t[:, None]
    return [tuple(p) for p in out_xy]


def recompute_grid(resampled_points, road_limit_speed, sample, sample_fine, distance_interval,
                    map_turn_speed_factor=MAP_TURN_SPEED_FACTOR):
    """322d recompute_full()의 파라미터화판(§27, sample/sample_fine/distance_interval
    이외 로직 0% 변경). sample=4/sample_fine=1/interval=10.0으로 호출하면
    recompute_full()과 완전히 동일한 결과를 내야 한다(--validate로 회귀검증)."""
    curvatures, distances, speeds, fine_triggered = [], [], [], []
    if len(resampled_points) >= sample * 2 + 1:
        distance = -distance_interval
        macro_abs_curv = []
        for i in range(len(resampled_points) - sample * 2):
            distance += distance_interval
            p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
            curvature = calculate_curvature(p1, p2, p3)
            curvatures.append(curvature)
            macro_abs_curv.append(abs(curvature))
            distances.append(distance)

        macro_speeds_arr = np.interp(macro_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
        macro_speeds_arr = macro_speeds_arr * map_turn_speed_factor
        for i in range(len(curvatures)):
            speed = macro_speeds_arr[i]
            if macro_abs_curv[i] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                speed = max(speed, road_limit_speed)
            speeds.append(speed)

        fine_triggered = [False] * len(speeds)
        if sample_fine and sample_fine < sample and len(resampled_points) >= sample_fine * 2 + 1:
            n_fine = min(len(distances), len(resampled_points) - sample_fine * 2)
            if n_fine > 0:
                fine_curvatures, fine_abs_curv = [], []
                for i in range(n_fine):
                    p1, p2, p3 = resampled_points[i], resampled_points[i + sample_fine], resampled_points[i + sample_fine * 2]
                    f_curvature = calculate_curvature(p1, p2, p3)
                    fine_curvatures.append(f_curvature)
                    fine_abs_curv.append(abs(f_curvature))
                fine_speeds_arr = np.interp(fine_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
                fine_speeds_arr = fine_speeds_arr * map_turn_speed_factor
                for j in range(n_fine):
                    f_curv = fine_curvatures[j]
                    f_speed = fine_speeds_arr[j]
                    if fine_abs_curv[j] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                        f_speed = max(f_speed, road_limit_speed)
                    if f_speed < speeds[j]:
                        speeds[j] = f_speed
                        curvatures[j] = f_curv
                        fine_triggered[j] = True

    candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed]
    all_clusters = route_find_clusters(candidates, distances, 1, ROUTE_CLUSTER_MAX_GAP_M)
    clusters = [c for c in all_clusters if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
    orphans = [c for c in all_clusters if len(c) < ROUTE_CLUSTER_MIN_POINTS]
    return candidates, clusters, orphans, distances, speeds, fine_triggered


def parse_raw_path(s):
    """routeOrphanRawPath("x,y;x,y;...", 거리필드 없음) 파싱."""
    pts = []
    if not s:
        return pts
    for tok in s.split(';'):
        tok = tok.strip()
        if not tok:
            continue
        x, y = tok.split(',')
        pts.append((float(x), float(y)))
    return pts


def validate_against_322d(rows, limit_print=10):
    """recompute_grid(sample=4,fine=1,interval=10.0)이 recompute_full()과
    100% 동일한지 회귀검증 + routeOrphanRawPath를 10.0m로 재샘플한 결과가
    같은 프레임의 naviPaths(production 10m 결과)와 일치하는지 검증(raw
    round-trip 정합성 확인)."""
    mismatch_recompute = 0
    orphan_frames = 0
    raw_roundtrip_checked = 0
    raw_roundtrip_mismatch = 0
    shown = 0

    for row in rows:
        pts_navi, _ = parse_navi_paths(row["naviPaths"])
        road_limit_speed = float(row["nRoadLimitSpeed"]) if row["nRoadLimitSpeed"] else 300.0

        if len(pts_navi) >= 9:
            c1 = recompute_full(pts_navi, road_limit_speed)
            c2 = recompute_grid(pts_navi, road_limit_speed, sample=4, sample_fine=1, distance_interval=10.0)
            # tuple 비교(candidates/clusters/orphans/distances/speeds/fine_triggered)
            same = (c1[0] == c2[0] and c1[1] == c2[1] and c1[2] == c2[2]
                    and all(abs(a - b) < 1e-9 for a, b in zip(c1[3], c2[3]))
                    and all(abs(a - b) < 1e-9 for a, b in zip(c1[4], c2[4]))
                    and c1[5] == c2[5])
            if not same:
                mismatch_recompute += 1
                if shown < limit_print:
                    print(f"  [recompute mismatch] seg={row['seg']} t={row['t']}")
                    shown += 1

        oc = row.get("routeOrphanSingletonCount", "")
        try:
            oc_val = int(float(oc)) if oc else 0
        except ValueError:
            oc_val = 0
        if oc_val > 0:
            orphan_frames += 1
            raw_pts = parse_raw_path(row.get("routeOrphanRawPath", ""))
            if not raw_pts:
                continue
            raw_roundtrip_checked += 1
            resampled_10 = resample_arclen(raw_pts, 10.0)
            # naviPaths(production)와 좌표 개수/값 비교(부동소수점 .2f 반올림 오차 허용)
            if len(resampled_10) != len(pts_navi):
                raw_roundtrip_mismatch += 1
                continue
            for (rx, ry), (nx, ny) in zip(resampled_10, pts_navi):
                if abs(rx - nx) > 0.02 or abs(ry - ny) > 0.02:
                    raw_roundtrip_mismatch += 1
                    break

    print("=== validate ===")
    print(f"recompute_grid(4,1,10.0) vs recompute_full() mismatch: {mismatch_recompute} "
          f"(0이어야 함 -- §27 무변경 회귀검증)")
    print(f"orphan frames: {orphan_frames}, raw_path checked: {raw_roundtrip_checked}")
    print(f"raw->10m resample vs production naviPaths mismatch: {raw_roundtrip_mismatch} "
          f"(0에 가까워야 함 -- .2f 반올림 잔차만 허용)")


class GridReplayState:
    def __init__(self, name, cfg):
        self.name = name
        self.cfg = cfg
        self.continuity = ContinuityState()
        self.provisional = ProvisionalTracker()
        self.route_active = False

    def reset(self):
        self.continuity.reset()
        self.provisional.reset()
        self.route_active = False

    def step(self, clusters, orphans, distances, speeds, v_ego_ms, v_ego_kph, road_limit_speed):
        apex_idx, apex_dist, apex_speed, apex_mode, apex_streak = self.continuity.step(
            clusters, distances, speeds, v_ego_ms)
        prov_active, prov_dist, prov_speed, prov_streak, prov_err, prov_promoted = self.provisional.step(
            orphans, distances, speeds, v_ego_ms)

        if apex_mode == "none" or apex_speed is None:
            pub_apex_dist, pub_apex_speed = 0.0, 0.0
            if self.route_active:
                self.route_active = False
        else:
            pub_apex_dist, pub_apex_speed = apex_dist, apex_speed
            if self.route_active:
                apex_passed_or_lost = apex_mode in ("passed", "lost", "new")
                speed_reached = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
                dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
                if apex_passed_or_lost or speed_reached or dist_reached:
                    self.route_active = False
            else:
                apex_confidence = confidence_from_streak(apex_streak)
                eff_apex_speed = apex_confidence * apex_speed + (1.0 - apex_confidence) * v_ego_kph
                target_ms = eff_apex_speed / 3.6
                eff_dist = max(0.0, apex_dist - target_ms * AUTONAVI_SPEED_CTRL_END)
                if v_ego_ms <= target_ms:
                    pass
                elif eff_dist <= 0:
                    pass
                else:
                    required_decel_mss = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                    if required_decel_mss >= AUTONAVI_SPEED_DECEL_RATE:
                        self.route_active = True

        return dict(
            cluster_count=len(clusters), orphan_count=len(orphans),
            apex_mode=apex_mode, apex_dist=pub_apex_dist, apex_speed=pub_apex_speed,
            apex_streak=apex_streak, route_active=self.route_active,
        )


def run_grid_counterfactual(rows):
    states = {name: GridReplayState(name, cfg) for name, cfg in GRID_CONFIGS.items()}
    per_frame = []  # list of dict per grid, aligned by frame index

    for row in rows:
        t = row["t"]
        seg = row["seg"]
        pts_navi, _ = parse_navi_paths(row["naviPaths"])
        v_ego_ms = float(row["vEgo"]) if row["vEgo"] else 0.0
        v_ego_kph = v_ego_ms * 3.6
        road_limit_speed = float(row["nRoadLimitSpeed"]) if row["nRoadLimitSpeed"] else 300.0

        full_block = len(pts_navi) >= 9  # production 게이트 조건(그리드 무관, naviPaths 길이 기준)

        oc = row.get("routeOrphanSingletonCount", "")
        try:
            oc_val = int(float(oc)) if oc else 0
        except ValueError:
            oc_val = 0
        raw_pts = parse_raw_path(row.get("routeOrphanRawPath", "")) if oc_val > 0 else []
        is_orphan_frame = oc_val > 0 and len(raw_pts) > 0

        frame_result = dict(t=t, seg=seg, is_orphan_frame=is_orphan_frame, full_block=full_block)

        if not full_block:
            for st in states.values():
                if pts_navi:
                    if st.route_active:
                        st.reset()
                else:
                    st.reset()
                frame_result[st.name] = dict(cluster_count=0, orphan_count=0, apex_mode="",
                                              apex_dist=0.0, apex_speed=0.0, apex_streak=0,
                                              route_active=st.route_active)
        else:
            # baseline 10m: 항상 naviPaths(production) 그대로 -- 322-D와 동일
            base_candidates, base_clusters, base_orphans, base_distances, base_speeds, _ = recompute_full(
                pts_navi, road_limit_speed)

            for name, cfg in GRID_CONFIGS.items():
                st = states[name]
                if name == "10m":
                    clusters, orphans, distances, speeds = base_clusters, base_orphans, base_distances, base_speeds
                elif is_orphan_frame:
                    resampled = resample_arclen(raw_pts, cfg["interval"])
                    _, clusters, orphans, distances, speeds, _ = recompute_grid(
                        resampled, road_limit_speed, cfg["sample"], cfg["sample_fine"], cfg["interval"])
                else:
                    # 근사(§28 한계 3): raw geometry 없는 비-orphan 프레임은 10m 결과 재사용
                    clusters, orphans, distances, speeds = base_clusters, base_orphans, base_distances, base_speeds

                frame_result[name] = st.step(clusters, orphans, distances, speeds,
                                              v_ego_ms, v_ego_kph, road_limit_speed)

        per_frame.append(frame_result)

    return per_frame


def group_orphan_episodes(per_frame, gap_s=1.0):
    """orphan 프레임(raw geometry 존재)만 대상으로 319차와 동일 기준(seg 내
    연속 orphan 프레임 dt<=gap_s)으로 에피소드 그룹화."""
    orphan_rows = [r for r in per_frame if r["is_orphan_frame"]]
    episodes = []
    cur = None
    prev_seg, prev_t = None, None
    for r in orphan_rows:
        t = float(r["t"])
        new_ep = (cur is None or r["seg"] != prev_seg or (t - prev_t) > gap_s)
        if new_ep:
            if cur is not None:
                episodes.append(cur)
            cur = {"seg": r["seg"], "t0": t, "t1": t, "frames": [r]}
        else:
            cur["t1"] = t
            cur["frames"].append(r)
        prev_seg, prev_t = r["seg"], t
    if cur is not None:
        episodes.append(cur)
    return episodes


def summarize_episodes(episodes):
    print(f"\n=== orphan 에피소드: {len(episodes)}건 ===\n")
    header = f"{'ep':>4} {'seg':>4} {'dur(s)':>7} {'n':>4} | {'10m maxCl':>10} {'5m maxCl':>9} {'2.5m maxCl':>10} | {'10m orph_end':>13} {'5m orph_end':>12} {'2.5m orph_end':>13} | 판정"
    print(header)
    print("-" * len(header))

    promoted_5m_only = 0
    promoted_2p5m_only = 0
    promoted_both = 0
    promoted_none = 0
    route_active_diverge_episodes = 0

    for i, ep in enumerate(episodes):
        frames = ep["frames"]
        dur = ep["t1"] - ep["t0"]
        max_cl = {name: max(f[name]["cluster_count"] for f in frames) for name in GRID_CONFIGS}
        orph_end = {name: frames[-1][name]["orphan_count"] for name in GRID_CONFIGS}

        improved_5m = max_cl["5m"] > max_cl["10m"]
        improved_2p5m = max_cl["2.5m"] > max_cl["10m"]
        if improved_5m and improved_2p5m:
            promoted_both += 1
            verdict = "5m+2.5m 모두 cluster 승격"
        elif improved_5m and not improved_2p5m:
            promoted_5m_only += 1
            verdict = "5m에서 cluster 승격"
        elif improved_2p5m and not improved_5m:
            promoted_2p5m_only += 1
            verdict = "2.5m에서만 cluster 승격"
        else:
            promoted_none += 1
            verdict = "승격 없음(그리드 무관 orphan)"

        ra_10 = [f["10m"]["route_active"] for f in frames]
        ra_5 = [f["5m"]["route_active"] for f in frames]
        ra_25 = [f["2.5m"]["route_active"] for f in frames]
        if ra_10 != ra_5 or ra_10 != ra_25:
            route_active_diverge_episodes += 1
            verdict += " [route_active 상이]"

        print(f"{i:>4} {ep['seg']:>4} {dur:>7.2f} {len(frames):>4} | "
              f"{max_cl['10m']:>10} {max_cl['5m']:>9} {max_cl['2.5m']:>10} | "
              f"{orph_end['10m']:>13} {orph_end['5m']:>12} {orph_end['2.5m']:>13} | {verdict}")

    print()
    print(f"[집계] 5m+2.5m 모두 승격: {promoted_both}  5m만: {promoted_5m_only}  "
          f"2.5m만: {promoted_2p5m_only}  승격없음: {promoted_none}  "
          f"(전체 {len(episodes)}건)")
    print(f"[집계] route_active 시퀀스가 그리드 간 달랐던 에피소드: "
          f"{route_active_diverge_episodes} / {len(episodes)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--validate", action="store_true",
                     help="recompute_grid 회귀검증 + raw round-trip 정합성만 확인하고 종료")
    ap.add_argument("--out-episodes", default=None, help="에피소드별 요약 CSV 저장 경로")
    args = ap.parse_args()

    with open(args.csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"loaded {len(rows)} rows from {args.csv_path}")

    if args.validate:
        validate_against_322d(rows)
        return

    per_frame = run_grid_counterfactual(rows)
    episodes = group_orphan_episodes(per_frame)
    summarize_episodes(episodes)

    if args.out_episodes:
        with open(args.out_episodes, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ep", "seg", "t0", "t1", "dur_s", "n_frames",
                        "maxCl_10m", "maxCl_5m", "maxCl_2p5m",
                        "orphEnd_10m", "orphEnd_5m", "orphEnd_2p5m",
                        "route_active_diverge"])
            for i, ep in enumerate(episodes):
                frames = ep["frames"]
                max_cl = {name: max(fr[name]["cluster_count"] for fr in frames) for name in GRID_CONFIGS}
                orph_end = {name: frames[-1][name]["orphan_count"] for name in GRID_CONFIGS}
                ra_10 = [fr["10m"]["route_active"] for fr in frames]
                ra_5 = [fr["5m"]["route_active"] for fr in frames]
                ra_25 = [fr["2.5m"]["route_active"] for fr in frames]
                diverge = (ra_10 != ra_5 or ra_10 != ra_25)
                w.writerow([i, ep["seg"], ep["t0"], ep["t1"], ep["t1"] - ep["t0"], len(frames),
                            max_cl["10m"], max_cl["5m"], max_cl["2.5m"],
                            orph_end["10m"], orph_end["5m"], orph_end["2.5m"], diverge])
        print(f"\nwrote episode summary to {args.out_episodes}")


if __name__ == "__main__":
    main()
