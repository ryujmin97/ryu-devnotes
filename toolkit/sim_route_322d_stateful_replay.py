#!/usr/bin/env python3
"""322-D: 전체구간 stateful apex replay -- production vs offline 대조.

322차(1단계, stateless)가 확정한 recompute() 블록(candidate/cluster/
orphan)을 그대로 재사용하고, 여기에 carrot_man.py의
_route_cluster_continuity_step()/_route_provisional_singleton_step()을
그대로 이식한 상태 추적기를 추가해 x17seg 전체 20171행을 시간순으로
재생한다. 목표: routeApexMode/Dist/Speed/ClusterCount/OrphanCount/
Provisional*를 production 로그와 프레임 단위로 대조.

**핵심 전제(carrot_man.py 코드 추적으로 확정, 반드시 이 순서로 재현해야
production과 동일):**

1. candidate/cluster/orphan/continuity 블록 전체는 매 프레임(20Hz,
   ROUTE_SPEED_LOOP_DT=0.05 고정 -- 실측 dt 아님) `if path:` 안의
   `if len(resampled_points) >= sample*2+1(=9):` 조건을 통과했을 때만
   실행된다(carrot_man.py 1146/1166행).
2. naviPaths가 CSV에 존재하더라도(=path가 비어있지 않음) 포인트 수가
   9개 미만이면 이 블록은 스킵된다 -- x17seg corpus 실측: naviPaths
   있는 19860프레임 중 1340프레임이 이 케이스(9개 미만).
3. 블록이 스킵되면:
   - naviPaths가 아예 비어있는 경우(path 자체가 없음, `else:` 분기,
     carrot_man.py 1574~1594행) **또는** navi_points 자체가 비활성인
     경우(1046~1080행, **무조건** 리셋) -- route_active/continuity
     lock을 **무조건** 리셋한다.
   - naviPaths는 있지만 포인트 부족(`elif self.route_active:` 분기,
     1559~1573행) -- **route_active가 True였을 때만** 리셋한다. False였다면
     continuity lock 상태는 이번 프레임에 전혀 손대지 않고(다음 실행
     프레임까지) 그대로 유지된다(x17seg에는 case (naviPaths 완전
     공백)이 로그 최초 311프레임 -- t<556.99s, 잠금 이전 -- 에만
     존재하므로 사실상 항상 이 case로 들어온다).
   - 두 경우 모두 이번 프레임 발행 텔레메트리(routeApexMode 등)는
     함수 진입부 sentinel(""/0/False, carrot_man.py 971~998행)로
     남는다 -- continuity 내부 lock이 살아있어도 "이번 프레임 발행값"은
     항상 sentinel.
4. 따라서 route_active(ACTIVE/INERT)의 정확한 추적이 "스킵 프레임에서
   리셋하는가"를 결정하는 데 필요 -- 257차 거리게이트(INERT 진입) +
   247차 RELEASE 3-OR 조건을 그대로 이식(1428~1549행). 이번 322-D의
   관심사는 continuity telemetry 자체이지 route_active/out_speed
   정합성이 아니지만, route_active를 잘못 추적하면 스킵 프레임에서
   리셋 여부 판단이 틀려 이후 continuity 상태 전체가 어긋난다.

**의존**: 322차 recompute() 로직(sim_route_322_single_frame_check.py)을
distances/speeds/clusters/orphans까지 반환하도록 확장 재사용(§21/§27,
후보 판정 로직 자체는 완전히 동일, 반환값만 늘림).
"""
import argparse
import csv
import math

import numpy as np

# ---- carrot_man.py에서 그대로 이식한 상수(값/의미 모두 동일, 302차/322차 corpus 실측값) ----
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
ROUTE_CURVATURE_FINE_SAMPLE = 1
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
ROUTE_SPEED_LOOP_DT = 0.05
CONTINUITY_MATCH_TOLERANCE_M = 20.0
ROUTE_APEX_MISS_TOLERANCE_FRAMES = 6
PROVISIONAL_PROMOTE_STREAK = 3
ROUTE_ACTIVE_RELEASE_MARGIN_RATIO = 1.05
ROUTE_RELEASE_DIST_M = 10.0
CONFIDENCE_TAU = 6.3

# [322차/params_backup.json 재확인, x17seg corpus 전용 -- 다른 corpus 재사용 금지]
MAP_TURN_SPEED_FACTOR = 1.10          # MapTurnSpeedFactor=110 * 0.01
AUTONAVI_SPEED_CTRL_END = 8.0         # AutoNaviSpeedCtrlEnd=8 (그대로 float)
AUTONAVI_SPEED_DECEL_RATE = 0.90      # AutoNaviSpeedDecelRate=90 * 0.01
# turnSpeedControlMode=2 (params_backup.json) -- route_enabled = mode in [2,3]는
# 이 corpus 전체에서 항상 True. carrot_man.py의 "if not route_enabled" 리셋
# 분기는 이번 replay 대상 구간(t>=556.99s)에서 발동할 수 없다(별도 구현 안 함,
# 발동 조건 자체가 성립하지 않음을 위 gap 분석으로 확인 -- 아래 --check-mode-const
# 로 재검증 가능).


def calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0
    return cross_product / (len_v1 * len_v2 * len_v1)


def route_find_clusters(idxs, distances, min_points, max_gap_m):
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


def parse_navi_paths(s):
    pts = []
    dists = []
    if not s:
        return pts, dists
    for tok in s.split(';'):
        tok = tok.strip()
        if not tok:
            continue
        x, y, d = tok.split(',')
        pts.append((float(x), float(y)))
        dists.append(float(d))
    return pts, dists


def recompute_full(resampled_points, road_limit_speed, map_turn_speed_factor=MAP_TURN_SPEED_FACTOR):
    """carrot_man.py 1160~1372행 재구현. 322차 recompute()와 후보판정 로직은
    완전히 동일(§27 무변경) -- clusters/orphans/distances/speeds/fine_triggered까지
    반환하도록 확장(continuity/provisional step에 필요)."""
    sample = 4
    curvatures, distances, speeds, fine_triggered = [], [], [], []

    if len(resampled_points) >= sample * 2 + 1:
        distance = -10.0
        macro_abs_curv = []
        for i in range(len(resampled_points) - sample * 2):
            distance += 10.0
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
        sample_fine = ROUTE_CURVATURE_FINE_SAMPLE
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


def confidence_from_streak(streak, tau=CONFIDENCE_TAU):
    if streak <= 1:
        return 0.0
    return 1.0 - math.exp(-(streak - 1) / tau)


class ContinuityState:
    """carrot_man.py::_route_cluster_continuity_step() 그대로 이식."""
    def __init__(self):
        self.locked_dist = None
        self.locked_speed = None
        self.miss_frames = 0
        self.streak = 0

    def reset(self):
        self.locked_dist = None
        self.locked_speed = None
        self.miss_frames = 0
        self.streak = 0

    def step(self, clusters, distances, speeds, v_ego_ms, dt=ROUTE_SPEED_LOOP_DT):
        predicted = (self.locked_dist - v_ego_ms * dt) if self.locked_dist is not None else None
        matched = None
        if predicted is not None and predicted > 0 and clusters:
            best, best_err = None, None
            for c in clusters:
                idx = c[0]
                err = abs(distances[idx] - predicted)
                if best_err is None or err < best_err:
                    best, best_err = idx, err
            if best_err is not None and best_err <= CONTINUITY_MATCH_TOLERANCE_M:
                matched = best

        if matched is not None:
            self.locked_dist = distances[matched]
            self.locked_speed = speeds[matched]
            self.miss_frames = 0
            self.streak += 1
            return matched, self.locked_dist, self.locked_speed, "matched", self.streak

        reset_reason = None
        if self.locked_dist is not None:
            if predicted is not None and predicted <= 0:
                reset_reason = "passed"
            else:
                self.miss_frames += 1
                if self.miss_frames < ROUTE_APEX_MISS_TOLERANCE_FRAMES and predicted is not None and predicted > 0:
                    self.locked_dist = predicted
                    return -1, predicted, self.locked_speed, "held", self.streak
                reset_reason = "lost"
            self.locked_dist = None
            self.locked_speed = None
            self.miss_frames = 0

        if clusters:
            idx = clusters[0][0]
            self.locked_dist = distances[idx]
            self.locked_speed = speeds[idx]
            self.miss_frames = 0
            self.streak = 1
            return idx, distances[idx], speeds[idx], (reset_reason or "new"), self.streak

        self.streak = 0
        return -1, None, None, (reset_reason or "none"), self.streak


class ProvisionalTracker:
    """carrot_man.py::_route_provisional_singleton_step() 그대로 이식."""
    def __init__(self):
        self.locked_dist = None
        self.locked_speed = None
        self.streak = 0

    def reset(self):
        self.locked_dist = None
        self.locked_speed = None
        self.streak = 0

    def step(self, orphans, distances, speeds, v_ego_ms, dt=ROUTE_SPEED_LOOP_DT):
        predicted = (self.locked_dist - v_ego_ms * dt) if self.locked_dist is not None else None
        matched = None
        if predicted is not None and predicted > 0 and orphans:
            best, best_err = None, None
            for c in orphans:
                idx = c[0]
                err = abs(distances[idx] - predicted)
                if best_err is None or err < best_err:
                    best, best_err = idx, err
            if best_err is not None and best_err <= CONTINUITY_MATCH_TOLERANCE_M:
                matched = (best, best_err)

        if matched is not None:
            idx, err = matched
            self.locked_dist = distances[idx]
            self.locked_speed = speeds[idx]
            self.streak += 1
            promoted = self.streak >= PROVISIONAL_PROMOTE_STREAK
            return True, self.locked_dist, self.locked_speed, self.streak, err, promoted

        self.locked_dist = None
        self.locked_speed = None
        self.streak = 0
        if orphans:
            idx = orphans[0][0]
            self.locked_dist = distances[idx]
            self.locked_speed = speeds[idx]
            self.streak = 1
            return True, distances[idx], speeds[idx], 1, 0.0, (1 >= PROVISIONAL_PROMOTE_STREAK)
        return False, 0.0, 0.0, 0, 0.0, False


def replay(rows):
    continuity = ContinuityState()
    provisional = ProvisionalTracker()
    route_active = False

    results = []  # per-frame dict for comparison

    for row in rows:
        t = row["t"]
        seg = row["seg"]
        pts, dists_ignored = parse_navi_paths(row["naviPaths"])
        v_ego_ms = float(row["vEgo"]) if row["vEgo"] else 0.0
        v_ego_kph = v_ego_ms * 3.6
        road_limit_speed = float(row["nRoadLimitSpeed"]) if row["nRoadLimitSpeed"] else 300.0

        full_block = len(pts) >= 9  # sample*2+1

        if full_block:
            candidates, clusters, orphans, distances, speeds, fine_triggered = recompute_full(pts, road_limit_speed)
            apex_idx, apex_dist, apex_speed, apex_mode, apex_streak = continuity.step(
                clusters, distances, speeds, v_ego_ms)
            prov_active, prov_dist, prov_speed, prov_streak, prov_err, prov_promoted = provisional.step(
                orphans, distances, speeds, v_ego_ms)

            apex_fine_triggered = bool(fine_triggered[apex_idx]) if apex_idx != -1 else False

            # --- publish rule (carrot_man.py 1402~1426행) ---
            if apex_mode == "none" or apex_speed is None:
                pub_apex_idx, pub_apex_dist, pub_apex_speed = -1, 0.0, 0.0
                if route_active:
                    route_active = False
            else:
                pub_apex_idx, pub_apex_dist, pub_apex_speed = apex_idx, apex_dist, apex_speed
                if route_active:
                    apex_passed_or_lost = apex_mode in ("passed", "lost", "new")
                    speed_reached = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
                    dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
                    if apex_passed_or_lost or speed_reached or dist_reached:
                        route_active = False
                    # else: stays ACTIVE (out_speed 계산은 322-D 범위 밖 -- 텔레메트리
                    # 비교 대상 아님, route_active 추적 목적만)
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
                            route_active = True

            orphan_count = len(orphans)
            orphan_dist = distances[orphans[0][0]] if orphans else 0.0
            orphan_speed = speeds[orphans[0][0]] if orphans else 0.0

            results.append(dict(
                t=t, seg=seg, skipped=False,
                cluster_count=len(clusters), apex_mode=apex_mode,
                apex_dist=pub_apex_dist, apex_speed=pub_apex_speed,
                apex_fine_triggered=apex_fine_triggered,
                orphan_count=orphan_count, orphan_dist=orphan_dist, orphan_speed=orphan_speed,
                prov_active=prov_active, prov_dist=prov_dist, prov_speed=prov_speed,
                prov_streak=prov_streak, prov_err=prov_err, prov_promoted=prov_promoted,
                route_active=route_active,
                n_pts=len(pts),
            ))
        else:
            # 블록 스킵 -- 발행 텔레메트리는 항상 sentinel
            if pts:
                # naviPaths 있으나 9개 미만: route_active였을 때만 리셋(§ elif 분기)
                if route_active:
                    route_active = False
                    continuity.reset()
                    provisional.reset()
                # else: 아무것도 안 함(lock 그대로 유지, 다음 실행 프레임까지)
            else:
                # naviPaths 완전 공백: 무조건 리셋
                route_active = False
                continuity.reset()
                provisional.reset()

            results.append(dict(
                t=t, seg=seg, skipped=True,
                cluster_count=0, apex_mode="",
                apex_dist=0.0, apex_speed=0.0, apex_fine_triggered=False,
                orphan_count=0, orphan_dist=0.0, orphan_speed=0.0,
                prov_active=False, prov_dist=0.0, prov_speed=0.0,
                prov_streak=0, prov_err=0.0, prov_promoted=False,
                route_active=route_active,
                n_pts=len(pts),
            ))

    return results


def to_bool(s):
    return str(s).strip().lower() in ("true", "1")


def to_float(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def to_int(s, default=0):
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


def compare(rows, results):
    mismatches = []
    field_mismatch_counts = {}
    for row, res in zip(rows, results):
        logged = dict(
            cluster_count=to_int(row.get("routeClusterCount")),
            apex_mode=row.get("routeApexMode") or "",
            apex_dist=to_float(row.get("routeApexDist")),
            apex_speed=to_float(row.get("routeApexSpeed")),
            apex_fine_triggered=to_bool(row.get("routeApexFineTriggered")),
            orphan_count=to_int(row.get("routeOrphanSingletonCount")),
            orphan_dist=to_float(row.get("routeOrphanSingletonDist")),
            orphan_speed=to_float(row.get("routeOrphanSingletonSpeed")),
            prov_active=to_bool(row.get("routeProvisionalActive")),
            prov_dist=to_float(row.get("routeProvisionalDist")),
            prov_speed=to_float(row.get("routeProvisionalSpeed")),
            prov_streak=to_int(row.get("routeProvisionalStreak")),
            prov_err=to_float(row.get("routeProvisionalMatchError")),
            prov_promoted=to_bool(row.get("routeProvisionalPromoted")),
        )
        diffs = []
        # mode/count/bool: exact match required
        for k in ("cluster_count", "apex_mode", "apex_fine_triggered", "orphan_count",
                  "prov_active", "prov_streak", "prov_promoted"):
            if logged[k] != res[k]:
                diffs.append(k)
        # numeric: small tolerance (rounding), flagged separately with magnitude
        for k in ("apex_dist", "apex_speed", "orphan_dist", "orphan_speed", "prov_dist", "prov_speed", "prov_err"):
            if abs(logged[k] - res[k]) > 0.05:
                diffs.append(k)

        if diffs:
            mismatches.append((row["t"], row["seg"], diffs, logged, res))
            for d in diffs:
                field_mismatch_counts[d] = field_mismatch_counts.get(d, 0) + 1

    return mismatches, field_mismatch_counts


def classify_mode_mismatches(rows, mismatches):
    """apex_mode 불일치 프레임을 2가지 이미 설명된 원인으로 자동 분류한다.

    A(클러스터 경계): 이 프레임 전후 2초 이내에 cluster_count 자체가
      logged와 다른(=322차와 동일한 naviPaths .2f 좌표 양자화 경계) 프레임이
      있음 -- 그 stateless 불일치가 continuity 매칭 대상을 바꿔 mode 전이가
      production 대비 정확히 1프레임 앞/뒤로 밀린 것.
    B(zero-crossing 경계): apex_mode가 'matched'<->'passed' 사이에서만
      갈리고 logged/offline 양쪽 모두 apex_dist=0.00 -- predicted<=0
      판정이 부동소수점 등호 경계에 걸린 경우(특히 vEgo가 0에 근접해
      정지 상태로 한 후보 위에 여러 프레임 머무를 때 흔함).
    """
    import bisect
    cluster_mismatch_ts = sorted(float(t) for t, seg, diffs, l, r in mismatches if 'cluster_count' in diffs)
    mode_mismatches = [(t, seg, diffs, l, r) for t, seg, diffs, l, r in mismatches if 'apex_mode' in diffs]

    cat_a, cat_b, unclassified = [], [], []
    for t, seg, diffs, logged, res in mode_mismatches:
        tt = float(t)
        i = bisect.bisect_left(cluster_mismatch_ts, tt)
        near_cluster = any(0 <= j < len(cluster_mismatch_ts) and abs(cluster_mismatch_ts[j] - tt) <= 2.0
                            for j in (i - 1, i))
        if near_cluster:
            cat_a.append((t, seg, logged, res))
        elif {logged['apex_mode'], res['apex_mode']} <= {'matched', 'passed'} and \
                abs(logged['apex_dist']) < 0.01 and abs(res['apex_dist']) < 0.01:
            cat_b.append((t, seg, logged, res))
        else:
            unclassified.append((t, seg, logged, res))
    return cat_a, cat_b, unclassified


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--limit-print", type=int, default=30)
    ap.add_argument("--classify", action="store_true",
                     help="apex_mode 불일치를 A(cluster 경계)/B(zero-crossing 경계)로 자동 분류")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv_path)))
    print(f"total rows: {len(rows)}")

    results = replay(rows)
    mismatches, field_counts = compare(rows, results)

    n_full = sum(1 for r in results if not r["skipped"])
    n_skip = sum(1 for r in results if r["skipped"])
    print(f"full-block frames: {n_full}  skipped frames: {n_skip}")
    print(f"total mismatched frames: {len(mismatches)} / {len(rows)} ({100.0*len(mismatches)/len(rows):.3f}%)")
    print("mismatch field breakdown:", field_counts)

    if args.classify:
        cat_a, cat_b, unclassified = classify_mode_mismatches(rows, mismatches)
        n_mode = sum(1 for m in mismatches if 'apex_mode' in m[2])
        print(f"\n--- apex_mode mismatch classification ({n_mode} total) ---")
        print(f"A (cluster-count 경계, naviPaths .2f 양자화 -- 322차와 동일 원인): {len(cat_a)}")
        print(f"B (predicted<=0 zero-crossing 부동소수점 경계): {len(cat_b)}")
        print(f"미분류(추가 조사 필요): {len(unclassified)}")
        for t, seg, logged, res in unclassified:
            print(f"  UNCLASSIFIED t={t} seg={seg} logged={logged['apex_mode']} off={res['apex_mode']} "
                  f"logged_dist={logged['apex_dist']:.2f} off_dist={res['apex_dist']:.2f}")
        return

    print(f"\n--- first {args.limit_print} mismatches ---")
    for t, seg, diffs, logged, res in mismatches[:args.limit_print]:
        print(f"t={t} seg={seg} diffs={diffs}")
        for d in diffs:
            print(f"    {d}: logged={logged[d]!r}  offline={res[d]!r}")


if __name__ == "__main__":
    main()
