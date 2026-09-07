#!/usr/bin/env python3
"""
sim_route_300_release_boundary_counterfactual.py (300차 신규)

목적
----
299차까지 "새 candidate(B)의 진위를 판별하는 단일 임계값 게이트"
방향은 표본(n=15)으로는 근거 부족이라는 결론이 나왔다(FINDINGS.md
299차). 이번 세션(ChatGPT 제안, 사용자 검토 지시)은 그 대신 아래
질문 하나만 먼저 답한다(§28 -- 원인 확정 전에 증상/재현조건부터):

    "1217행 `apex_passed_or_lost = apex_mode in ('passed','lost','new')`에
    의한 강제 RELEASE가, 실제로(counterfactual 대비) 손실/이득을
    만들었는가?"

두 가지를 동시에 재생한다:
  (A) **실제 프로덕션 동작**: 296/297차 `RouteStateMachine`을 그대로
      재사용(§27, 무수정) -- passed/lost/new에서 무조건 RELEASE.
  (B) **counterfactual(가상)**: 동일한 continuity 스트림 위에서
      `apex_passed_or_lost` 항만 제거한(=speed_reached/dist_reached만
      RELEASE 사유로 남긴) 가상의 판정 레이어. continuity 자체
      (`ContinuityState`, `route_find_clusters`)는 (A)와 물리적으로
      동일 객체를 공유한다 -- continuity는애초에 `route_active`를
      파라미터로 받지 않으므로(735~808행, `route_active`와 무관하게
      항상 동일하게 진행) 두 판정 레이어가 같은 입력을 보장받는다
      (§27 -- 판정 로직과 관측 로직을 분리한 299차와 동일 원칙,
      여기서는 "판정 로직 자체를 변형한 가상 레이어"를 별도 클래스로
      분리해 실제 코드(A)에는 어떤 영향도 주지 않음).

(A)의 강제 RELEASE 이벤트가 발생한 각 프레임에서 그 이후 최대
`--horizon`초 동안 (A)/(B) 두 트랙의 `out_speed`/`route_active`
궤적을 나란히 기록해 다음을 계산한다:
  - `actual_gap_frames`/`actual_gap_seconds`: (A)가 RELEASE 후 다시
    route_active=True로 돌아오기까지 걸린 프레임/시간(윈도우 내
    복귀 못하면 None).
  - `cf_min_speed_kph`/`cf_max_decel_from_current`: (B)가 그 윈도우
    동안 실제로 명령했을 최저 속도 / 이벤트 프레임 vEgo 대비 최대
    감속 요구량 -- "만약 강제 RELEASE가 없었다면 어느 정도까지
    깎였을까"의 실측치.
  - `outcome`: 두 트랙 비교로 아래 표(사용자 제시안)에 대응하는
    관측 결과만 기록한다(§28 -- 여기서 게이트/임계값을 만들지
    않는다, 관측만).

298차 qcamera 정답 라벨(`classification.md`)과 결합해 real/noise
그룹별로 나눠 출력한다.

**하지 않는 것(사용자/ChatGPT 확정, 이번 세션 범위 밖)**:
- confidence 임계값/게이트 설계, decel_rate 변경, RELEASE_HOLD 복원,
  0.9 마진 변경 -- 전부 보류. 이 스크립트는 관측 전용이며 `ryu` 코드는
  건드리지 않는다(ANALYSIS_ONLY).

사용
----
    python3 sim_route_300_release_boundary_counterfactual.py \\
        --csv-dir /path/to/route_csvs \\
        --classification evidence/route_297_seamless_release_qcamera/classification.md \\
        --horizon 5.0
"""
import argparse
import csv
import math
import os
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths

from sim_route_296_active_reacquire_gap import (
    ContinuityState, route_find_clusters, confidence_from_streak,
    ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M,
    ROUTE_ACTIVE_RELEASE_MARGIN_RATIO, ROUTE_RELEASE_DIST_M,
    ROUTE_SPEED_LOOP_DT,
)
from sim_route_299_reacquire_confidence_features import (
    recompute_with_curvature, load_ground_truth, _LABEL_MAP,
)

PERSISTENCE_WINDOW_S = 3.0


# ---------------------------------------------------------------------
# (A) 실제 프로덕션과 동일한 판정 레이어 -- carrot_navi_route()
# 1174~1324행(290차) 그대로. sim_route_296/297의 RouteStateMachine과
# 로직 100% 동일하되, 이 파일에서는 continuity를 (B)와 공유해야 하므로
# ContinuityState를 외부에서 주입받는 얇은 래퍼로 다시 둔다(§27 --
# 산식 자체는 한 글자도 바꾸지 않음, 296차 클래스 복붙 대신 import해
# 재사용하고 싶었으나 continuity 공유 구조상 얇은 판정 레이어만
# 분리했다).
# ---------------------------------------------------------------------
class ActualLayer:
    def __init__(self):
        self.route_active = False
        self.events = []  # 강제 RELEASE(=passed/lost/new) 이벤트

    def step(self, t, apex_idx, apex_dist, apex_speed, mode, streak,
              v_ego_ms, v_ego_kph, ctrl_end, decel_rate):
        was_active = self.route_active
        forced_release = False
        if mode == "none" or apex_speed is None:
            if self.route_active:
                self.route_active = False
            out_speed = None
        else:
            if self.route_active:
                apex_passed_or_lost = mode in ("passed", "lost", "new")
                speed_reached = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
                dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
                if apex_passed_or_lost or speed_reached or dist_reached:
                    self.route_active = False
                    out_speed = None
                    if apex_passed_or_lost and not speed_reached and not dist_reached:
                        forced_release = True
                else:
                    out_speed = _active_decel_out(apex_dist, apex_speed, streak,
                                                   v_ego_ms, v_ego_kph, ctrl_end,
                                                   decel_rate) * 3.6
            else:
                would_active, required_decel = _inert_gate(
                    apex_speed, apex_dist, streak, v_ego_ms, v_ego_kph,
                    ctrl_end, decel_rate)
                conf = confidence_from_streak(streak)
                eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
                target_ms = eff_apex_speed / 3.6
                if v_ego_ms <= target_ms:
                    out_speed = None
                elif would_active:
                    self.route_active = True
                    applied = min(max(required_decel, 0.0), decel_rate)
                    out_speed = max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT) * 3.6
                else:
                    eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)
                    out_speed = v_ego_kph if eff_dist <= 0 else None
        if was_active and forced_release:
            self.events.append({"t": t, "mode": mode, "new_apex_dist": apex_dist,
                                 "new_apex_speed": apex_speed})
        return out_speed, self.route_active


# ---------------------------------------------------------------------
# (B) counterfactual 판정 레이어 -- `apex_passed_or_lost`를 RELEASE
# 사유에서 제거(=speed_reached/dist_reached만 남김). 새로 잠긴 apex를
# "이미 ACTIVE인 채로" 계속 소비한다(= 사용자/ChatGPT가 말하는
# "seamless switch" 가설의 최소 구현 -- 신뢰도 게이트는 추가하지
# 않음, 순수하게 "강제 RELEASE 조건 제거"의 효과만 분리 관측).
# ---------------------------------------------------------------------
class CounterfactualLayer:
    def __init__(self):
        self.route_active = False

    def step(self, t, apex_idx, apex_dist, apex_speed, mode, streak,
              v_ego_ms, v_ego_kph, ctrl_end, decel_rate):
        if mode == "none" or apex_speed is None:
            self.route_active = False
            return None, self.route_active
        if not self.route_active:
            # counterfactual도 최초 진입 게이트(INERT)는 그대로 통과해야
            # 한다 -- "강제 RELEASE만 없앤다"는 가설이지 "게이트 자체를
            # 없앤다"는 가설이 아니므로(§27, 최소 변경 원칙을 가상
            # 레이어에도 동일 적용).
            would_active, required_decel = _inert_gate(
                apex_speed, apex_dist, streak, v_ego_ms, v_ego_kph,
                ctrl_end, decel_rate)
            conf = confidence_from_streak(streak)
            eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
            target_ms = eff_apex_speed / 3.6
            if v_ego_ms <= target_ms:
                return None, self.route_active
            if would_active:
                self.route_active = True
                applied = min(max(required_decel, 0.0), decel_rate)
                return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT) * 3.6, True
            eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)
            return (v_ego_kph if eff_dist <= 0 else None), self.route_active
        # ACTIVE 유지 중: speed_reached/dist_reached만 RELEASE 사유로 남김.
        speed_reached = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
        dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
        if speed_reached or dist_reached:
            self.route_active = False
            return None, self.route_active
        out_ms = _active_decel_out(apex_dist, apex_speed, streak, v_ego_ms,
                                    v_ego_kph, ctrl_end, decel_rate)
        return out_ms * 3.6, self.route_active


def _active_decel_out(apex_dist, apex_speed, streak, v_ego_ms, v_ego_kph,
                       ctrl_end, decel_rate):
    # carrot_man.py 1251~1260행(266차 confidence blend 포함) 그대로.
    conf = confidence_from_streak(streak)
    eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
    target_ms = eff_apex_speed / 3.6
    eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)
    if eff_dist <= 0 or v_ego_ms <= target_ms:
        return v_ego_ms
    required = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
    applied = min(max(required, 0.0), decel_rate)
    return max(target_ms, v_ego_ms - applied * ROUTE_SPEED_LOOP_DT)


def _inert_gate(apex_speed, apex_dist, streak, v_ego_ms, v_ego_kph, ctrl_end, decel_rate):
    # carrot_navi_route() else(INERT) 분기, 1283~1324행과 동일 산식.
    conf = confidence_from_streak(streak)
    eff_apex_speed = conf * apex_speed + (1.0 - conf) * v_ego_kph
    target_ms = eff_apex_speed / 3.6
    eff_dist = max(0.0, apex_dist - target_ms * ctrl_end)
    if v_ego_ms <= target_ms or eff_dist <= 0:
        return False, None
    required_decel_mss = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
    return required_decel_mss >= decel_rate, required_decel_mss


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
            entries = recompute_with_curvature(points, road_limit, map_turn_speed_factor)
            candidates = [(d, s) for d, s, _c in entries if s < road_limit]
            frames.append({"t": t, "v_ego_ms": v_ego, "v_ego_kph": v_ego * 3.6,
                            "candidates": candidates})
    return frames


def run_route(csv_path, ctrl_end, decel_rate, map_turn_speed_factor, horizon_s):
    frames = build_frames(csv_path, map_turn_speed_factor)
    continuity = ContinuityState()
    actual = ActualLayer()
    cf = CounterfactualLayer()

    # 전체 프레임을 한 번에 continuity까지 미리 계산해두고(공유 스트림),
    # 그 다음 두 판정 레이어를 독립적으로 그 위에 재생한다 -- 이렇게
    # 하면 이벤트 이후 최대 horizon초 구간을 손쉽게 슬라이스해서 두
    # 번째 재생(비교용)도 가능하다.
    stream = []
    for fr in frames:
        distances = [c[0] for c in fr["candidates"]]
        speeds = [c[1] for c in fr["candidates"]]
        idxs = list(range(len(fr["candidates"])))
        clusters = route_find_clusters(idxs, distances, ROUTE_CLUSTER_MIN_POINTS,
                                        ROUTE_CLUSTER_MAX_GAP_M)
        apex_idx, apex_dist, apex_speed, mode, streak = continuity.step(
            clusters, distances, speeds, fr["v_ego_ms"])
        stream.append({**fr, "apex_idx": apex_idx, "apex_dist": apex_dist,
                        "apex_speed": apex_speed, "mode": mode, "streak": streak})

    actual_track = []
    for fr in stream:
        prev_active = actual.route_active
        out, active = actual.step(fr["t"], fr["apex_idx"], fr["apex_dist"],
                                   fr["apex_speed"], fr["mode"], fr["streak"],
                                   fr["v_ego_ms"], fr["v_ego_kph"], ctrl_end, decel_rate)
        actual_track.append({"t": fr["t"], "out_speed": out, "active": active})

    cf_track = []
    for fr in stream:
        out, active = cf.step(fr["t"], fr["apex_idx"], fr["apex_dist"],
                               fr["apex_speed"], fr["mode"], fr["streak"],
                               fr["v_ego_ms"], fr["v_ego_kph"], ctrl_end, decel_rate)
        cf_track.append({"t": fr["t"], "out_speed": out, "active": active})

    # ---- 이벤트별 counterfactual 비교(§28, 관측만) ----
    results = []
    for ev in actual.events:
        t0 = ev["t"]
        # A: 실제 트랙에서 RELEASE 이후 재진입까지 걸린 시간
        gap_frames, gap_seconds = None, None
        for i, row in enumerate(actual_track):
            if row["t"] <= t0:
                continue
            if row["t"] - t0 > horizon_s:
                break
            if row["active"]:
                gap_frames = i - next(j for j, r in enumerate(actual_track) if r["t"] == t0)
                gap_seconds = round(row["t"] - t0, 2)
                break
        # B: counterfactual 트랙에서 같은 구간의 최저 속도/최대 감속량
        v0 = next(fr["v_ego_kph"] for fr in stream if fr["t"] == t0)
        cf_speeds = [row["out_speed"] for row in cf_track
                     if t0 <= row["t"] <= t0 + horizon_s and row["out_speed"] is not None]
        cf_min_speed = min(cf_speeds) if cf_speeds else None
        cf_max_decel_kph = (v0 - cf_min_speed) if cf_min_speed is not None else None
        # 실제 트랙 동일 구간 최저 속도(active일 때만 의미있는 감속 명령)
        actual_speeds = [row["out_speed"] for row in actual_track
                          if t0 <= row["t"] <= t0 + horizon_s and row["out_speed"] is not None]
        actual_min_speed = min(actual_speeds) if actual_speeds else None

        results.append({
            "t": round(t0, 2), "mode": ev["mode"],
            "new_apex_dist": round(ev["new_apex_dist"], 1),
            "new_apex_speed": round(ev["new_apex_speed"], 1),
            "v_ego_kph_at_event": round(v0, 1),
            "actual_gap_seconds": gap_seconds,
            "actual_min_speed_kph_in_window": (round(actual_min_speed, 1)
                                                if actual_min_speed is not None else None),
            "cf_min_speed_kph_in_window": (round(cf_min_speed, 1)
                                            if cf_min_speed is not None else None),
            "cf_max_decel_kph_from_event_speed": (round(cf_max_decel_kph, 1)
                                                   if cf_max_decel_kph is not None else None),
        })
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", required=True)
    ap.add_argument("--classification",
                     default="evidence/route_297_seamless_release_qcamera/classification.md")
    ap.add_argument("--map-turn-speed-factor", type=float, default=1.10)
    ap.add_argument("--ctrl-end", type=float, default=8.0)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--horizon", type=float, default=5.0,
                     help="이벤트 이후 counterfactual을 비교할 시간 창(초)")
    args = ap.parse_args()

    gt = load_ground_truth(args.classification)
    route_ids = ["a3b3373495", "01742d6c1c", "c8d2619479", "bf794c0073"]

    all_rows = []
    for rid in route_ids:
        csv_path = os.path.join(args.csv_dir, f"route_{rid}.csv")
        if not os.path.exists(csv_path):
            print(f"(스킵: {csv_path} 없음)")
            continue
        rows = run_route(csv_path, args.ctrl_end, args.decel_rate,
                          args.map_turn_speed_factor, args.horizon)
        print(f"\n=== {rid}: 강제 RELEASE 이벤트 {len(rows)}건 ===")
        for r in rows:
            key = (rid, round(r["t"], 2))
            label = gt.get(key, "unknown")
            r["route"] = rid
            r["label"] = label
            all_rows.append(r)
            print(f"  t={r['t']:.2f} label={label:10s} mode={r['mode']:6s}"
                  f" v0={r['v_ego_kph_at_event']}"
                  f" actual_gap={r['actual_gap_seconds']}s"
                  f" actual_min={r['actual_min_speed_kph_in_window']}"
                  f" cf_min={r['cf_min_speed_kph_in_window']}"
                  f" cf_max_decel={r['cf_max_decel_kph_from_event_speed']}")

    def _bucket(label):
        if label in ("real_curve", "weak_curve"):
            return "real"
        if label == "no_curve":
            return "noise"
        return None

    print(f"\n=== 요약(horizon={args.horizon}s) ===")
    for bucket_name in ("real", "noise"):
        rows_b = [r for r in all_rows if _bucket(r["label"]) == bucket_name]
        n = len(rows_b)
        n_no_reentry = sum(1 for r in rows_b if r["actual_gap_seconds"] is None)
        cf_decels = [r["cf_max_decel_kph_from_event_speed"] for r in rows_b
                     if r["cf_max_decel_kph_from_event_speed"] is not None]
        avg_cf_decel = sum(cf_decels) / len(cf_decels) if cf_decels else float("nan")
        gaps = [r["actual_gap_seconds"] for r in rows_b if r["actual_gap_seconds"] is not None]
        avg_gap = sum(gaps) / len(gaps) if gaps else float("nan")
        print(f"  {bucket_name}(n={n}): 실제 RELEASE 후 {args.horizon}s 내 미재진입"
              f"={n_no_reentry}/{n}, 재진입까지 평균 {avg_gap:.2f}s(n={len(gaps)}),"
              f" counterfactual 평균 최대감속={avg_cf_decel:.1f}kph(n={len(cf_decels)})")


if __name__ == "__main__":
    main()
