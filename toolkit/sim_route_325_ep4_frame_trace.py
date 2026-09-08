#!/usr/bin/env python3
"""325차: ep4(route_active grid 상이, 10m/5m/2.5m) 프레임 단위 원인 추적.

목적: 324차가 발견한 "route_active 시퀀스가 grid 간 상이한 2건" 중 가장 큰
사례(ep4, seg--4, ~60초 에피소드 -- 10m은 전체 구간 route_active 단 한 번도
True 안 됨, 5m 28프레임/2.5m 195프레임 발동)에 대해, 정확히 어느 프레임에서
`required_decel_mss` 임계 통과가 grid 간 갈리는지 3-way(10m/5m/2.5m) 동시
stateful replay로 프레임 단위 추적한다.

**설계 원칙(§27)**: 324차 `GridReplayState`/`recompute_grid`/grid 정의를
그대로 재사용(import). 로직은 전혀 바꾸지 않고, `GridReplayState.step()`이
내부적으로만 계산하고 버리던 진단 필드(required_decel_mss, target_ms,
eff_dist, apex_confidence, continuity/provisional 내부 locked_dist/streak)를
반환값에 추가로 노출하는 서브클래스만 새로 만든다(연산 결과 자체는
100% 동일 -- 필요시 --validate-parity로 324차 대비 회귀검증).

사용:
  python3 sim_route_325_ep4_frame_trace.py <CSV> --seg <seg_substr> \
      --t0 <t0> --t1 <t1> [--pad-s 5] [--out-csv trace.csv]
  python3 sim_route_325_ep4_frame_trace.py <CSV> --validate-parity
      (324차 summarize_episodes 결과와 route_active/cluster_count 등
      핵심 산출물이 100% 동일한지 회귀검증)
"""
import argparse
import csv

from sim_route_322d_stateful_replay import (
    ContinuityState, ProvisionalTracker, confidence_from_streak,
    parse_navi_paths, recompute_full,
    ROUTE_SPEED_LOOP_DT, ROUTE_ACTIVE_RELEASE_MARGIN_RATIO, ROUTE_RELEASE_DIST_M,
    AUTONAVI_SPEED_CTRL_END, AUTONAVI_SPEED_DECEL_RATE,
)
from sim_route_324_grid_counterfactual import (
    GRID_CONFIGS, recompute_grid, resample_arclen, parse_raw_path,
    group_orphan_episodes, summarize_episodes,
)


class DiagGridReplayState:
    """324차 GridReplayState와 연산 로직 100% 동일(§27) -- step()이 내부
    중간값(required_decel_mss 등)을 버리지 않고 반환값에 추가로 포함시키는
    점만 다르다. route_active 판정 분기 자체는 한 글자도 바꾸지 않음."""

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

        diag = dict(
            required_decel_mss=None, target_kph=None, eff_dist=None,
            apex_confidence=None, speed_reached=None, dist_reached=None,
            apex_passed_or_lost=None, decision="",
        )

        if apex_mode == "none" or apex_speed is None:
            pub_apex_dist, pub_apex_speed = 0.0, 0.0
            if self.route_active:
                self.route_active = False
                diag["decision"] = "release(apex_lost)"
        else:
            pub_apex_dist, pub_apex_speed = apex_dist, apex_speed
            if self.route_active:
                apex_passed_or_lost = apex_mode in ("passed", "lost", "new")
                speed_reached = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
                dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
                diag.update(apex_passed_or_lost=apex_passed_or_lost,
                            speed_reached=speed_reached, dist_reached=dist_reached)
                if apex_passed_or_lost or speed_reached or dist_reached:
                    self.route_active = False
                    diag["decision"] = "release"
                else:
                    diag["decision"] = "hold_active"
            else:
                apex_confidence = confidence_from_streak(apex_streak)
                eff_apex_speed = apex_confidence * apex_speed + (1.0 - apex_confidence) * v_ego_kph
                target_ms = eff_apex_speed / 3.6
                eff_dist = max(0.0, apex_dist - target_ms * AUTONAVI_SPEED_CTRL_END)
                diag.update(apex_confidence=apex_confidence, target_kph=eff_apex_speed, eff_dist=eff_dist)
                if v_ego_ms <= target_ms:
                    diag["decision"] = "skip(v_ego<=target)"
                elif eff_dist <= 0:
                    diag["decision"] = "skip(eff_dist<=0)"
                else:
                    required_decel_mss = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
                    diag["required_decel_mss"] = required_decel_mss
                    if required_decel_mss >= AUTONAVI_SPEED_DECEL_RATE:
                        self.route_active = True
                        diag["decision"] = "ACTIVATE"
                    else:
                        diag["decision"] = "below_threshold"

        result = dict(
            cluster_count=len(clusters), orphan_count=len(orphans),
            apex_idx=apex_idx, apex_mode=apex_mode, apex_dist=pub_apex_dist,
            apex_speed=pub_apex_speed, apex_streak=apex_streak,
            continuity_locked_dist=self.continuity.locked_dist,
            prov_active=prov_active, prov_streak=prov_streak,
            prov_promoted=prov_promoted, prov_locked_dist=self.provisional.locked_dist,
            route_active=self.route_active,
        )
        result.update(diag)
        return result


def run(rows, seg_filter=None, t0=None, t1=None, pad_s=5.0):
    """324차 run_grid_counterfactual()과 100% 동일한 시퀀싱(전체 20Hz 프레임을
    스킵 없이 순서대로 스텝, full_block/orphan 판정 동일) -- 다만 매 프레임
    DiagGridReplayState를 써서 진단 필드를 함께 기록하고, 지정된 seg/시간
    윈도우에 해당하는 프레임만 trace 리스트에 담아 반환한다(윈도우 밖 프레임도
    상태는 반드시 스텝시켜야 함 -- 그래야 locked_dist 시간감쇠/streak 누적이
    정확함)."""
    states = {name: DiagGridReplayState(name, cfg) for name, cfg in GRID_CONFIGS.items()}
    trace = []
    all_frames = []  # 324차 summarize_episodes parity 검증용(is_orphan_frame 등)

    for row in rows:
        t = float(row["t"])
        seg = row["seg"]
        pts_navi, _ = parse_navi_paths(row["naviPaths"])
        v_ego_ms = float(row["vEgo"]) if row["vEgo"] else 0.0
        v_ego_kph = v_ego_ms * 3.6
        road_limit_speed = float(row["nRoadLimitSpeed"]) if row["nRoadLimitSpeed"] else 300.0

        full_block = len(pts_navi) >= 9

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
                    clusters, orphans, distances, speeds = base_clusters, base_orphans, base_distances, base_speeds

                frame_result[name] = st.step(clusters, orphans, distances, speeds,
                                              v_ego_ms, v_ego_kph, road_limit_speed)

        all_frames.append(frame_result)

        if seg_filter and seg_filter in seg and t0 is not None and t1 is not None:
            if (t0 - pad_s) <= t <= (t1 + pad_s):
                trace.append(frame_result)

    return trace, all_frames


def print_trace(trace):
    prev_ra = {"10m": None, "5m": None, "2.5m": None}
    for fr in trace:
        ra = {name: fr[name]["route_active"] for name in GRID_CONFIGS}
        diverge = len(set(ra.values())) > 1
        changed = any(ra[n] != prev_ra[n] for n in GRID_CONFIGS if prev_ra[n] is not None)
        marker = ""
        if changed:
            marker = " <<< route_active 전환"
        if diverge:
            marker += " [DIVERGE]"
        if marker:
            print(f"\nt={fr['t']:.3f} seg={fr['seg']} orphan_frame={fr['is_orphan_frame']}{marker}")
            for name in GRID_CONFIGS:
                g = fr[name]
                rd = g.get("required_decel_mss")
                rd_s = f"{rd:.3f}" if rd is not None else "-"
                print(f"  [{name:>5}] cl={g['cluster_count']} orph={g['orphan_count']} "
                      f"apex_mode={g['apex_mode']:>7} apex_dist={g.get('apex_dist', 0):.1f} "
                      f"apex_speed={g.get('apex_speed', 0):.1f} apex_streak={g.get('apex_streak', 0)} "
                      f"prov_streak={g.get('prov_streak', 0)} prov_promoted={g.get('prov_promoted', False)} "
                      f"req_decel={rd_s} decision={g.get('decision', ''):>18} "
                      f"route_active={g['route_active']}")
        prev_ra = ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--seg", default=None, help="seg 이름에 포함될 부분문자열(예: --4)")
    ap.add_argument("--t0", type=float, default=None)
    ap.add_argument("--t1", type=float, default=None)
    ap.add_argument("--pad-s", type=float, default=5.0)
    ap.add_argument("--out-csv", default=None)
    ap.add_argument("--validate-parity", action="store_true",
                     help="324차 summarize_episodes() 결과와 전체 corpus route_active/cluster_count 비교(회귀검증)")
    args = ap.parse_args()

    with open(args.csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"loaded {len(rows)} rows from {args.csv_path}")

    if args.validate_parity:
        _, all_frames = run(rows)
        episodes = group_orphan_episodes(all_frames)
        summarize_episodes(episodes)
        return

    trace, _ = run(rows, seg_filter=args.seg, t0=args.t0, t1=args.t1, pad_s=args.pad_s)
    print(f"\n{len(trace)}개 프레임이 trace 윈도우에 해당(seg~={args.seg}, "
          f"t=[{args.t0}-{args.pad_s}, {args.t1}+{args.pad_s}])")
    print_trace(trace)

    if args.out_csv:
        cols = ["t", "seg", "is_orphan_frame"]
        for name in GRID_CONFIGS:
            for k in ["cluster_count", "orphan_count", "apex_mode", "apex_idx", "apex_dist",
                      "apex_speed", "apex_streak", "prov_streak", "prov_promoted",
                      "required_decel_mss", "decision", "route_active"]:
                cols.append(f"{name}_{k}")
        with open(args.out_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for fr in trace:
                row = [fr["t"], fr["seg"], fr["is_orphan_frame"]]
                for name in GRID_CONFIGS:
                    g = fr[name]
                    for k in ["cluster_count", "orphan_count", "apex_mode", "apex_idx", "apex_dist",
                              "apex_speed", "apex_streak", "prov_streak", "prov_promoted",
                              "required_decel_mss", "decision", "route_active"]:
                        row.append(g.get(k, ""))
                w.writerow(row)
        print(f"\nwrote frame trace to {args.out_csv}")


if __name__ == "__main__":
    main()
