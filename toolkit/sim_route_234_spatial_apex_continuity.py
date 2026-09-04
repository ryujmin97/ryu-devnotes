#!/usr/bin/env python3
"""
sim_route_234_spatial_apex_continuity.py (234차 계속4, 신규)

목적: 234차 설계안 B(spatial cluster stability)/C(apex continuity)를
233/234차 실측 CSV(`extract_log.py --with-navi-paths`)로 4단계 A/B 재현한다.
  0=baseline(기존 코드, 232차 HEAD)
  1=+30% severity gate(234차 계속2 확정, ROUTE_SEVERITY_GATE_RATIO=0.70)
  2=+spatial cluster(설계안 B, ROUTE_CLUSTER_MIN_POINTS=2, gap<=40m)
  3=+apex continuity(설계안 C, 예측거리 매칭, ROUTE_APEX_MISS_TOLERANCE_FRAMES=3)

재사용: candidates 전체 배열은 `analysis_helpers.recompute_route_curvature_speed()`
(148차, 이미 replay_route_apex_hysteresis_ab.py 등에서 프로덕션 재현 신뢰도
검증됨)로 naviPaths에서 그대로 재구성한다 -- 신규 rlog 판독 불필요(234차
계속3의 "candidates 전체 배열이 CSV에 없다"는 이전 우려는, 이 방식으로
naviPaths만으로 매 프레임 전체 후보를 재구성할 수 있으므로 실질적으로 해소됨.
routeCandidate0~2 텔레메트리 컬럼은 이 재구성이 실제 232차 코드와 정합하는지
sanity-check하는 데만 사용).

**중요 -- 미확정 가정 2건(사용자 확인 필요, 아래 결과에 그대로 영향)**:
  (a) severity gate 기준값: 원래 설계(234차 지시서 §3 원문)는
      `speeds[k] <= road_limit_speed * RATIO`였으나 road_limit_speed
      (`nRoadLimitSpeed`, 맵 제한속도)가 CSV에 없어 234차 계속에서 이미
      `vEgo_kph` 기준으로 근사 검증했다(WIP.md 234차 계속 §160줄).
      이 스크립트도 동일 근사(`speeds[k] <= vEgo_kph * ratio`)를 그대로
      이어받는다 -- road_limit_speed 실측 컬럼이 추가되기 전까지는 정식
      A항목(target/road_limit 비율) 자체를 재현할 수 없다는 한계가 여전함.
  (b) apex continuity 매칭 허용오차(예측거리와 실측 후보 거리 차이 허용폭)는
      234차 지시서 §3 원문에 수치가 명시되지 않아 CONTINUITY_MATCH_TOLERANCE_M
      =15.0(리샘플 10m 간격의 1.5배)으로 **이 세션에서 자체 설정**했다.
      이 값이 너무 좁으면(엄격) continuity가 거의 안 걸리고, 너무 넓으면
      서로 다른 물리적 지점을 같은 apex로 오판할 수 있음 -- 사용자 확인 후
      §26(PARAMS_REGISTRY) 등록 필요.

사용:
    python3 sim_route_234_spatial_apex_continuity.py <route.csv> [--window 2190 2225]
"""
import argparse
import csv
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

MACRO_SAMPLE = 4
FINE_SAMPLE = 1
FLOOR_THRESHOLD = 0.001  # 157차 패치(ROUTE_CURVE_NEGLIGIBLE_THRESHOLD) 재현, 232차 HEAD와 동일
ROUTE_SEVERITY_GATE_RATIO = 0.70          # 234차 계속2 확정
ROUTE_CLUSTER_MIN_POINTS = 2              # 234차 사용자 확정 조건 1
ROUTE_CLUSTER_MAX_GAP_M = 40.0            # 설계안 B 원문
ROUTE_APEX_MISS_TOLERANCE_FRAMES = 3      # 234차 사용자 확정 조건 2 (~150ms)
CONTINUITY_MATCH_TOLERANCE_M = 15.0       # (b) 가정 -- 234차 계속5, --continuity-tolerance로 재설정 가능


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_speeds_distances(navi_paths_str):
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < FINE_SAMPLE * 2 + 1:
        return [], []
    merged = recompute_route_curvature_speed(
        points, distances, sample=MACRO_SAMPLE, sample_fine=FINE_SAMPLE,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD,
    )
    if not merged:
        return [], []
    return [m[0] for m in merged], [m[2] for m in merged]


def gate_candidates(speeds, threshold):
    return [k for k in range(len(speeds)) if speeds[k] <= threshold]


def gate_base_kph(row, v_ego_kph):
    """234차 계속6: 실측 nRoadLimitSpeed(맵 제한속도)가 있으면 그것을,
    없으면(구버전 CSV) 기존 vEgo_kph 근사(가정 a)로 폴백. 반환값:
    (gate_base_kph, source) -- source는 'road_limit'|'vego_fallback'."""
    raw = row.get("nRoadLimitSpeed", "")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = 0.0
    if v > 0:
        return v, "road_limit"
    return v_ego_kph, "vego_fallback"


def find_clusters(idxs, dists, min_points, max_gap_m):
    """idxs: 오름차순(거리) 후보 인덱스. 인접 gap<=max_gap_m인 런으로 묶는다."""
    if not idxs:
        return []
    clusters = []
    cur = [idxs[0]]
    for i in idxs[1:]:
        if dists[i] - dists[cur[-1]] <= max_gap_m:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_points]


class ContinuityState:
    """설계안 C: 예측거리 매칭. locked apex를 프레임간 v_ego*dt로 예측이동시켜
    실측 후보와 매칭되면 계속 추적, miss_frames<TOLERANCE는 예측값으로 hold,
    초과 시에만 재탐색."""

    def __init__(self):
        self.locked_dist = None
        self.locked_speed = None
        self.miss_frames = 0
        self.last_ambiguous = False

    def step(self, clusters, dists, speeds, v_ego_ms, dt):
        predicted = (self.locked_dist - v_ego_ms * dt) if self.locked_dist is not None else None

        # 이번 프레임 클러스터들 중 predicted와 가장 가까운 후보 탐색
        matched = None
        ambiguous = False
        if predicted is not None and predicted > 0 and clusters:
            best = None
            best_err = None
            within_tol = 0
            for c in clusters:
                idx = c[0]
                err = abs(dists[idx] - predicted)
                if err <= CONTINUITY_MATCH_TOLERANCE_M:
                    within_tol += 1
                if best_err is None or err < best_err:
                    best, best_err = idx, err
            if best_err is not None and best_err <= CONTINUITY_MATCH_TOLERANCE_M:
                matched = best
                # (b) 허용오차 자체 위험도 계측: 서로 다른 물리적 지점(cluster)이
                # 둘 이상 동시에 tolerance 안에 들어오면, 이 tolerance가 서로
                # 다른 지점을 같은 apex로 오판할 수 있다는 뜻(폭이 넓을수록 증가
                # 예상) -- 234차 계속5, 사용자 지시 10/15/20m A/B/C 비교용.
                ambiguous = within_tol >= 2
        self.last_ambiguous = ambiguous

        if matched is not None:
            self.locked_dist = dists[matched]
            self.locked_speed = speeds[matched]
            self.miss_frames = 0
            return matched, self.locked_dist, self.locked_speed, "matched"

        if self.locked_dist is not None:
            self.miss_frames += 1
            if self.miss_frames < ROUTE_APEX_MISS_TOLERANCE_FRAMES and predicted is not None and predicted > 0:
                # hold: 예측값으로 유지(실제 idx 없음 -- dist/speed만 hold)
                self.locked_dist = predicted
                return None, predicted, self.locked_speed, "held"
            # tolerance 초과 -- lock 해제, 아래에서 새로 탐색
            self.locked_dist = None
            self.locked_speed = None
            self.miss_frames = 0

        # lock 없음(최초 진입 또는 방금 해제) -- 가장 가까운 클러스터로 신규 진입
        if clusters:
            idx = clusters[0][0]
            self.locked_dist = dists[idx]
            self.locked_speed = speeds[idx]
            self.miss_frames = 0
            return idx, dists[idx], speeds[idx], "new"
        return None, None, None, "none"


def replay(rows):
    cont = ContinuityState()
    out = []
    prev_t = None
    for row in rows:
        t = float(row["t"])
        dt = (t - prev_t) if prev_t is not None else 0.05
        dt = max(0.001, min(dt, 0.5))
        prev_t = t
        v_ego_ms = float(row["vEgo"])
        v_ego_kph = v_ego_ms * 3.6

        dists, speeds = build_speeds_distances(row.get("naviPaths", ""))
        rec = {"t": t, "v_ego_kph": v_ego_kph,
               "published_apex_idx": row.get("routeApexIdx", ""),
               "published_apex_dist": row.get("routeApexDist", ""),
               "published_apex_speed": row.get("routeApexSpeed", ""),
               "published_candidate_count": row.get("routeCandidateCount", "")}
        if not speeds:
            for stage in ("s0", "s1", "s2", "s3"):
                rec[f"{stage}_idx"] = None
                rec[f"{stage}_dist"] = None
                rec[f"{stage}_speed"] = None
            rec["s3_ambiguous"] = False
            rec["gate_source"] = "n/a"
            cont.locked_dist = None
            cont.locked_speed = None
            cont.miss_frames = 0
            cont.last_ambiguous = False
            out.append(rec)
            continue

        # stage0: baseline -- 234차 계속6, 실측 nRoadLimitSpeed 있으면 사용(가정 a 해소),
        # 없으면(구버전 CSV) vEgo_kph 근사로 폴백
        gate_base, gate_src = gate_base_kph(row, v_ego_kph)
        rec["gate_source"] = gate_src
        c0 = gate_candidates(speeds, gate_base)
        i0 = c0[0] if c0 else None

        # stage1: +30% gate
        c1 = gate_candidates(speeds, gate_base * ROUTE_SEVERITY_GATE_RATIO)
        i1 = c1[0] if c1 else None

        # stage2: +spatial cluster
        clusters2 = find_clusters(c1, dists, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        i2 = clusters2[0][0] if clusters2 else None

        # stage3: +apex continuity (stage2 클러스터 기반)
        i3, d3, sp3, mode3 = cont.step(clusters2, dists, speeds, v_ego_ms, dt)
        rec["s3_ambiguous"] = cont.last_ambiguous

        rec["s0_idx"], rec["s0_dist"], rec["s0_speed"] = i0, (dists[i0] if i0 is not None else None), (speeds[i0] if i0 is not None else None)
        rec["s1_idx"], rec["s1_dist"], rec["s1_speed"] = i1, (dists[i1] if i1 is not None else None), (speeds[i1] if i1 is not None else None)
        rec["s2_idx"], rec["s2_dist"], rec["s2_speed"] = i2, (dists[i2] if i2 is not None else None), (speeds[i2] if i2 is not None else None)
        rec["s3_idx"], rec["s3_dist"], rec["s3_speed"] = i3, d3, sp3
        rec["s3_mode"] = mode3
        out.append(rec)
    return out


def jump_count(result, key, gap_thresh_m=40.0):
    """프레임간 dist 낙차(절대값)가 gap_thresh_m를 넘는 '점프' 횟수
    (근거리<->원거리 후보 교대 = flicker의 직접 지표)."""
    jumps = 0
    for i in range(1, len(result)):
        a, b = result[i - 1][key], result[i][key]
        if a is not None and b is not None and abs(a - b) > gap_thresh_m:
            jumps += 1
    return jumps


def active_frames(result, key):
    return sum(1 for r in result if r[key] is not None)


def sanity_check(result):
    """s0(=proxy baseline)가 실측 published apex와 얼마나 일치하는지
    (재현 신뢰도, 148차 방식과 동일 취지). vEgo 근사(가정 a) 탓에 완전
    일치는 기대하지 않음 -- 대략적 정합성만 확인."""
    matches = total = 0
    for r in result:
        pub_idx = r["published_apex_idx"]
        if pub_idx in ("", None):
            continue
        try:
            pub_idx = int(pub_idx)
        except ValueError:
            continue
        if pub_idx < 0:
            continue
        total += 1
        if r["s0_idx"] is not None and abs(r["s0_dist"] - float(r["published_apex_dist"])) <= 15.0:
            matches += 1
    return matches, total


def summarize(result, window=None):
    if window:
        lo, hi = window
        w = [r for r in result if lo <= r["t"] <= hi]
        label = f"윈도우 t={lo}~{hi} ({len(w)} rows)"
    else:
        w = result
        label = f"전체 ({len(w)} rows)"

    print(f"\n=== {label} ===")
    for stage, key in (("0 baseline(vEgo 근사)", "s0_dist"),
                        ("1 +30%gate", "s1_dist"),
                        ("2 +spatial cluster", "s2_dist"),
                        ("3 +continuity", "s3_dist")):
        active = active_frames(w, key)
        jumps = jump_count(w, key)
        print(f"  stage{stage}: active={active}/{len(w)} frames, "
              f">40m 프레임간 점프={jumps}건")

    ambiguous_count = sum(1 for r in w if r.get("s3_ambiguous"))
    matched_count = sum(1 for r in w if r.get("s3_mode") == "matched")
    rate = (100 * ambiguous_count / matched_count) if matched_count else 0.0
    print(f"  stage3 continuity tolerance={CONTINUITY_MATCH_TOLERANCE_M:.0f}m: "
          f"ambiguous matched frames={ambiguous_count}/{matched_count} "
          f"({rate:.1f}%) -- tolerance 안에 후보 2개 이상 동시 존재(오판 위험)")

    if window:
        s3_modes = {}
        for r in w:
            s3_modes[r.get("s3_mode")] = s3_modes.get(r.get("s3_mode"), 0) + 1
        print(f"  stage3 mode 분포: {s3_modes}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--window", type=float, nargs=2, default=[2190.0, 2225.0],
                     help="터널 flicker 구간(233/234차 재현 대상)")
    ap.add_argument("--continuity-tolerance", type=float, default=15.0,
                     help="234차 계속5: apex continuity 매칭 허용오차(m). "
                          "10/15/20 A/B/C 비교용으로 추가(사용자 지시)")
    args = ap.parse_args()

    global CONTINUITY_MATCH_TOLERANCE_M
    CONTINUITY_MATCH_TOLERANCE_M = args.continuity_tolerance

    rows = load_csv(args.csv_path)
    if not rows:
        print("no rows", file=sys.stderr)
        sys.exit(1)

    result = replay(rows)

    src_counts = {}
    for r in result:
        src_counts[r.get("gate_source")] = src_counts.get(r.get("gate_source"), 0) + 1
    print(f"=== gate_source 분포: {src_counts} (road_limit=실측 nRoadLimitSpeed 사용, "
          f"vego_fallback=구버전 CSV 폴백, n/a=naviPaths 없음) ===")

    matches, total = sanity_check(result)
    print(f"=== sanity check: s0 vs 실측 published apex_dist(±15m) 정합 "
          f"{matches}/{total} ({100*matches/total:.1f}%) ===")

    summarize(result, window=None)
    summarize(result, window=tuple(args.window))


if __name__ == "__main__":
    main()
