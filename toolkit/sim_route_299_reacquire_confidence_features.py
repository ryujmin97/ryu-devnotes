#!/usr/bin/env python3
"""
sim_route_299_reacquire_confidence_features.py (299차 신규)

목적
----
298차 qcamera 육안 대조(`evidence/route_297_seamless_release_qcamera/
classification.md`)로 15건의 "seamless forced-release" 이벤트에
"실제 커브"(7건)/"불분명"(3건)/"커브 없음"(5건) 정답 라벨이 이미 붙어
있다. 이 스크립트는 그 15건에 대해, ACTIVE 유지/RELEASE 판정에 실제로
쓸 수 있는 **candidate 신뢰도 진단 지표**를 코드 레벨에서 추가로
계산해, 어떤 지표가 정답 라벨과 상관관계가 있는지(=판별에 쓸모가
있는지) 수치로 확인한다.

296/297차의 `RouteStateMachine`/`ContinuityState`/`route_find_clusters`
판정 로직 자체는 **전혀 수정하지 않고 그대로 재사용**한다(§27) -- 이
스크립트는 그 위에 순수 진단용 관찰(observer)만 추가한다. 즉
`sm.step()`이 호출되기 전/후 상태를 옆에서 읽기만 하고, 상태기계
내부로 어떤 값도 되먹임하지 않는다.

추가하는 4개 진단 지표(모두 §28 -- 코드/산식으로 재계산, 추측 아님)
------------------------------------------------------------------
1. `cluster_size`: 새로 매칭된 apex를 이룬 원시 candidate 점 개수
   (`route_find_clusters()`가 만든 cluster의 길이). 실제 커브는 곡률이
   일정 구간에 걸쳐 유지되므로 연속된 여러 점이 함께 클러스터를
   이루기 쉽고, 노이즈는 `ROUTE_CLUSTER_MIN_POINTS=2`(최소치) 근처에
   머물 것이라는 가설.
2. `speed_margin_ratio`: `new_apex_speed / road_limit_speed`. 1.0에
   가까울수록(=도로제한속도에서 거의 안 깎인 미세한 감속) 279차
   `ROUTE_CURVE_NEGLIGIBLE_THRESHOLD` 근처의 미세 곡률(=노이즈에 가까운
   신호)일 가능성이 높고, 작을수록(=제한속도 대비 크게 깎임) 실제
   급커브일 가능성이 높다는 가설(179차 relative severity gating과
   같은 방향의 지표).
3. `persistence_frames_before` / `persistence_seconds_before`: 이번에
   새로 잠긴 apex 위치가 이 프레임에 "갑자기 나타난" 것인지, 아니면
   그 이전 여러 프레임에서도 (아직 continuity 매칭 tolerance 밖이라
   추적되진 않았지만) 비슷한 위치에 계속 candidate로 잡혀왔는지를
   센다. 이벤트 프레임에서 뒤로 최대 3.0초 동안, 매 과거 프레임마다
   "새 apex 위치가 그 시점에 있었을 것으로 예상되는 위치"(등속 가정
   역투영, `new_apex_dist + v_ego_ms*(t_event - t_i)`)에서
   `CONTINUITY_MATCH_TOLERANCE_M` 이내에 실제 candidate cluster가
   있었는지 확인, 이벤트 프레임에서부터 연속으로 몇 프레임/몇 초
   지속됐는지 계산. 실제 물리적 커브는 GPS/맵 매칭이 매 프레임 거의
   동일한 위치를 가리키므로 지속성이 높고, 순간적 맵 후보 노이즈는
   1~2프레임짜리 blip으로 그칠 것이라는 가설.
4. `distance_jump_m`: 직전에 추적하던 apex가 끊어지는 순간의
   예측위치(`old_locked_dist - v_ego_ms*dt`)와 새로 매칭된 apex
   거리의 차이. 작을수록(=거의 같은 자리) "원래 있던 커브의 연속
   추적 실패 후 재탐색"에 가깝고, 클수록 "전혀 다른 위치의 새 신호"에
   가깝다는 가설.

주의(§28/§29): 이 스크립트는 위 4개 지표를 **계산만** 한다. 어떤
임계값도 아직 정하지 않았고, `carrot_man.py`에 반영된 것도 없다.
15건이라는 표본 크기 자체가 통계적으로 작다는 점(298차 WIP에도 명시)도
그대로 유지 -- 이 결과는 "다음에 무엇을 코드로 시도해볼 가치가
있는지"를 좁히는 용도로만 쓴다.

사용
----
    python3 sim_route_299_reacquire_confidence_features.py \\
        --csv-dir /home/claude/corpus_csv \\
        --classification evidence/route_297_seamless_release_qcamera/classification.md
"""
import argparse
import csv
import math
import os
import re
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths

from sim_route_296_active_reacquire_gap import (
    RouteStateMachine, route_find_clusters, ROUTE_CLUSTER_MIN_POINTS,
    ROUTE_CLUSTER_MAX_GAP_M, CONTINUITY_MATCH_TOLERANCE_M, ROUTE_SPEED_LOOP_DT,
)

# ---- carrot_man.py 960~1066행 이식 (297차와 동일, 여기서는 curvature도
# 함께 반환하도록 반환 튜플만 확장 -- 산식 자체는 297차와 100% 동일) ----
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360.,
                     1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
DISTANCE_INTERVAL = 10.0
MACRO_SAMPLE = 4
ROUTE_CURVATURE_FINE_SAMPLE = 1

PERSISTENCE_WINDOW_S = 3.0


def _calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


def _interp(x, xp, fp):
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


def recompute_with_curvature(points, road_limit_speed, map_turn_speed_factor):
    """297차 recompute_route_speeds_with_factor()와 100% 동일 산식이되,
    반환 튜플에 curvature(macro, fine-merge 후 최종 채택된 쪽)를 추가.
    반환: [(distance, speed_cap, curvature_abs), ...]"""
    n = len(points)
    if n < MACRO_SAMPLE * 2 + 1:
        return []

    distances, macro_abs_curv, curvatures = [], [], []
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

    final_abs_curv = list(macro_abs_curv)

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
                    final_abs_curv[j] = f_abs

    return list(zip(distances, speeds, final_abs_curv))


def build_frames(csv_path, map_turn_speed_factor):
    """297차 build_frames()와 동일하되 candidates에 curvature(3번째
    원소)를 함께 담고, road_limit_speed도 프레임에 보존한다."""
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
            candidates = [(d, s, c) for d, s, c in entries if s < road_limit]
            frames.append({
                "t": t, "v_ego_ms": v_ego, "v_ego_kph": v_ego * 3.6,
                "road_limit_speed": road_limit, "candidates": candidates,
            })
    return frames


def run_route_with_features(csv_path, ctrl_end, decel_rate, map_turn_speed_factor):
    frames = build_frames(csv_path, map_turn_speed_factor)
    sm = RouteStateMachine()

    # 진단용 프레임 히스토리: (t, v_ego_ms, clusters=[(center_dist, size)])
    history = []
    enriched = []  # sm.events와 순서 대응하는 진단 지표 dict 리스트

    for fr in frames:
        distances = [c[0] for c in fr["candidates"]]
        speeds = [c[1] for c in fr["candidates"]]
        idxs = list(range(len(fr["candidates"])))
        clusters_this_frame = route_find_clusters(idxs, distances,
                                                    ROUTE_CLUSTER_MIN_POINTS,
                                                    ROUTE_CLUSTER_MAX_GAP_M)
        cluster_summaries = [(distances[c[0]], len(c)) for c in clusters_this_frame]

        prev_locked_dist = sm.continuity.locked_dist
        n_events_before = len(sm.events)

        # ContinuityState/RouteStateMachine은 (dist,speed) 튜플만
        # 인덱싱해서 쓰므로 3-tuple(dist,speed,curvature)을 그대로
        # 넘겨도 판정 로직에는 영향 없음(§27 -- 로직 무변경 확인).
        sm.step(fr["t"], fr["candidates"], fr["v_ego_ms"], fr["v_ego_kph"],
                ctrl_end, decel_rate)

        if len(sm.events) > n_events_before:
            ev = sm.events[-1]
            new_dist = ev["new_apex_dist"]

            # 1) cluster_size: 이번 프레임 클러스터 중 new_dist를 만든
            # 클러스터를 찾는다(첫 점 거리 == new_dist로 유일 식별 가능,
            # ContinuityState가 clusters[0]/matched cluster의 첫 점을
            # locked_dist로 쓰기 때문).
            cluster_size = None
            curvature_at_match = None
            for c in clusters_this_frame:
                if abs(distances[c[0]] - new_dist) < 1e-6:
                    cluster_size = len(c)
                    curvature_at_match = fr["candidates"][c[0]][2]
                    break

            # 2) speed_margin_ratio
            speed_margin_ratio = (ev["new_apex_speed"] / fr["road_limit_speed"]
                                   if fr["road_limit_speed"] > 0 else None)

            # 3) persistence: 과거 히스토리를 시간 역순으로 훑으며,
            # 매 과거 프레임 시점에 new_dist가 있었을 것으로 예상되는
            # 위치(등속 역투영) 근처에 클러스터가 있었는지 연속으로 확인.
            persistence_frames = 0
            persistence_seconds = 0.0
            t_event = fr["t"]
            v_event = fr["v_ego_ms"]
            for (t_i, v_i, clusters_i) in reversed(history):
                if t_event - t_i > PERSISTENCE_WINDOW_S:
                    break
                predicted_at_i = new_dist + v_event * (t_event - t_i)
                hit = any(abs(cd - predicted_at_i) <= CONTINUITY_MATCH_TOLERANCE_M
                          for (cd, _sz) in clusters_i)
                if not hit:
                    break
                persistence_frames += 1
                persistence_seconds = t_event - t_i

            # 4) distance_jump_m
            distance_jump_m = None
            if prev_locked_dist is not None:
                predicted_break_pos = prev_locked_dist - v_event * ROUTE_SPEED_LOOP_DT
                distance_jump_m = abs(new_dist - predicted_break_pos)

            enriched.append({
                "t": ev["t"], "mode": ev["mode"],
                "new_apex_dist": new_dist, "new_apex_speed": ev["new_apex_speed"],
                "new_apex_needs_decel": ev["new_apex_needs_decel"],
                "cluster_size": cluster_size,
                "curvature_at_match": curvature_at_match,
                "road_limit_speed": fr["road_limit_speed"],
                "speed_margin_ratio": speed_margin_ratio,
                "persistence_frames_before": persistence_frames,
                "persistence_seconds_before": round(persistence_seconds, 3),
                "distance_jump_m": (round(distance_jump_m, 2)
                                     if distance_jump_m is not None else None),
            })

        history.append((fr["t"], fr["v_ego_ms"], cluster_summaries))
        # 메모리/시간 절약: PERSISTENCE_WINDOW_S보다 오래된 히스토리는
        # 굳이 들고 있을 필요 없음(다음 이벤트가 그 이상 과거를 보지
        # 않으므로) -- 매 프레임 arbitrary하게 긴 리스트를 스캔하지
        # 않도록 정리.
        cutoff = fr["t"] - PERSISTENCE_WINDOW_S
        while history and history[0][0] < cutoff:
            history.pop(0)

    return frames, sm, enriched


# 298차 classification.md의 route별 t(초)를 키로 삼아 정답 라벨을
# 붙인다. 파일 파싱은 표 형식이 고정돼 있다는 전제(§28 -- 매직넘버
# 대신 파일에서 직접 읽음).
_LABEL_MAP = {
    "실제 커브": "real_curve", "커브 없음": "no_curve",
    "불분명": "unclear", "약한 커브": "weak_curve",
}


def load_ground_truth(classification_path):
    """`| # | route | t | dist(m) | apex_speed(kph) | 판정 | 비고 |`
    형식의 마크다운 표를 파싱해 {(route_prefix_or_full, round(t,2)): label}
    로 반환. route 컬럼은 297/298차 표기 그대로(파일 전체 이름) 사용."""
    gt = {}
    with open(classification_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 6 or not cols[0].isdigit():
                continue
            route, t_str, judgment = cols[1], cols[2], cols[5]
            label = "unknown"
            for kr, en in _LABEL_MAP.items():
                if kr in judgment:
                    label = en
                    break
            try:
                t_val = round(float(t_str), 2)
            except ValueError:
                continue
            gt[(route, t_val)] = label
    return gt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", required=True,
                     help="route_<id>.csv 4개가 있는 디렉토리")
    ap.add_argument("--classification",
                     default="evidence/route_297_seamless_release_qcamera/classification.md")
    ap.add_argument("--map-turn-speed-factor", type=float, default=1.10)
    ap.add_argument("--ctrl-end", type=float, default=8.0)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    args = ap.parse_args()

    gt = load_ground_truth(args.classification)
    print(f"정답 라벨 {len(gt)}건 로드: {args.classification}")

    route_ids = ["a3b3373495", "01742d6c1c", "c8d2619479", "bf794c0073"]
    all_rows = []
    for rid in route_ids:
        csv_path = os.path.join(args.csv_dir, f"route_{rid}.csv")
        if not os.path.exists(csv_path):
            print(f"  (스킵: {csv_path} 없음)")
            continue
        frames, sm, enriched = run_route_with_features(
            csv_path, args.ctrl_end, args.decel_rate, args.map_turn_speed_factor)
        print(f"\n=== {rid}: 프레임 {len(frames)}, 이벤트 {len(sm.events)}건 ===")
        for e in enriched:
            key = (rid, round(e["t"], 2))
            label = gt.get(key, "unknown")
            e["route"] = rid
            e["label"] = label
            all_rows.append(e)
            print(f"  t={e['t']:.2f} label={label:10s} mode={e['mode']:6s}"
                  f" dist={e['new_apex_dist']:.1f} speed={e['new_apex_speed']:.1f}"
                  f" margin={e['speed_margin_ratio']:.3f}"
                  f" cluster={e['cluster_size']}"
                  f" persist={e['persistence_frames_before']}f/"
                  f"{e['persistence_seconds_before']}s"
                  f" jump={e['distance_jump_m']}")

    # ---- 그룹별 집계(real_curve+weak_curve vs no_curve) ----
    def _bucket(label):
        if label in ("real_curve", "weak_curve"):
            return "real"
        if label == "no_curve":
            return "noise"
        return None  # unclear/unknown은 집계 제외

    print("\n=== 지표별 그룹 평균 (real=실제 커브+약한 커브 / noise=커브 없음) ===")
    for feat in ("cluster_size", "speed_margin_ratio",
                 "persistence_frames_before", "persistence_seconds_before",
                 "distance_jump_m"):
        real_vals = [r[feat] for r in all_rows
                     if _bucket(r["label"]) == "real" and r[feat] is not None]
        noise_vals = [r[feat] for r in all_rows
                      if _bucket(r["label"]) == "noise" and r[feat] is not None]
        rm = sum(real_vals) / len(real_vals) if real_vals else float("nan")
        nm = sum(noise_vals) / len(noise_vals) if noise_vals else float("nan")
        print(f"  {feat:28s} real(n={len(real_vals)})={rm:.3f}"
              f"  noise(n={len(noise_vals)})={nm:.3f}"
              f"  real값={['%.2f'%v for v in real_vals]}"
              f"  noise값={['%.2f'%v for v in noise_vals]}")

    if not all_rows or all(r["label"] == "unknown" for r in all_rows):
        print("\n경고: 정답 라벨이 하나도 매칭되지 않음 -- classification.md"
              " 파싱 또는 t 매칭 로직을 점검할 것(§33, 임의로 진행하지 않음).")


if __name__ == "__main__":
    main()
