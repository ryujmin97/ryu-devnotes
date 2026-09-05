#!/usr/bin/env python3
"""
sim_route_260_gyesok_spatial_curvature_consistency.py (260차 계속, 신규)

목적: 260차가 발견한 문제("curvature_consistency 신호가 현재 정의(시간축
track별 부호 최빈값)로는 판별력이 없음 -- streak==1인 절대다수 트랙에서
표본 1개로 자명하게 1.0이 나오는 통계적 아티팩트")를 해소하기 위해,
같은 신호를 **시간축(여러 프레임에 걸친 추적)이 아니라 공간축(그 프레임
naviPaths 폴리라인 안에서 후보 지점 주변 이웃 샘플)** 기준으로 재정의하고
실측으로 판별력을 재검증한다.

**재정의 근거**: 260차 원래 정의는 persistence 신호(추적 지속 프레임 수)와
사실상 같은 축(시간)을 재는 것이어서 중복이었다. Master가 원한 것은
"이 후보가 GPS 노이즈로 인한 고립된 스파이크인지, 실제로 연속된 커브
형상의 일부인지"이므로, 그 판정은 **그 순간의 폴리라인 형상만으로도
즉시(1프레임째부터) 계산 가능**해야 하고, track이 여러 프레임 살아남을
때까지 기다릴 필요가 없다. 이게 persistence와 명확히 다른 축이 되는
지점이기도 하다.

**새 정의**: 후보 지점(cluster 대표점) 기준 ±WINDOW_M(기본 40m, 기존
ROUTE_CLUSTER_MAX_GAP_M과 동일 스케일) 범위 안의 전체 재구성 곡률
배열(recompute_route_curvature_speed, fine sample=1 = 10m 간격) 포인트 중:
  - support = 이웃 포인트 중 curvature가 FLOOR_THRESHOLD(0.001, 157차 기준)를
    넘는(=유의미한 커브로 취급되는) 포인트 개수 (후보 자신 제외)
  - consistency = 그 중 후보와 curvature 부호가 같은 포인트의 비율
    (support==0이면 정의상 0.0 -- "주변에 아무 커브도 없이 혼자 튀는
    지점"은 최저 신뢰도로 처리, 기존처럼 1.0으로 처리하지 않음(§ 핵심 수정))

이 정의는 프레임 1개만으로 계산되므로 persistence(다중 프레임 필요)와
직교하는 신호가 된다 -- 두 신호가 서로 다른 것을 재는지 상관관계로 확인.

재사용: sim_route_260_confidence_signals.py의 gate_base_kph/gate_candidates/
find_clusters/build_dist_curv_speed 전부 동일 재사용(§21, 파일명 길어
아래에 인라인 복사 -- 원본 import 시 순환 의존 없음, 로직 diff 없음
명시적 표시).

사용:
    python3 sim_route_260_gyesok_spatial_curvature_consistency.py <route.csv> \
        --window 2108 2112 --label ic_gore \
        --window 2116 2122.2 --label s_curve
    (인자 없이 실행하면 251차가 확정한 터널/IC gore/S커브 3구간 + 전체 실행)
"""
import argparse
import csv
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

MACRO_SAMPLE = 4
FINE_SAMPLE = 1
FLOOR_THRESHOLD = 0.001  # 157차 패치(ROUTE_CURVE_NEGLIGIBLE_THRESHOLD), 현재 HEAD와 동일
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
WINDOW_M = 40.0  # 신규 spatial consistency 윈도우 -- ROUTE_CLUSTER_MAX_GAP_M과 동일 스케일로 통일(§27 최소변경, 새 상수 남발 방지)

DEFAULT_WINDOWS = [
    (2190.0, 2225.0, "tunnel"),
    (2108.0, 2112.0, "ic_gore"),
    (2116.0, 2122.2, "s_curve"),
]


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_dist_curv_speed(navi_paths_str):
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < FINE_SAMPLE * 2 + 1:
        return [], [], []
    merged = recompute_route_curvature_speed(
        points, distances, sample=MACRO_SAMPLE, sample_fine=FINE_SAMPLE,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD,
    )
    if not merged:
        return [], [], []
    return [m[0] for m in merged], [m[1] for m in merged], [m[2] for m in merged]


def gate_base_kph(row, v_ego_kph):
    raw = row.get("nRoadLimitSpeed", "")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0 else v_ego_kph


def gate_candidates(speeds, threshold):
    return [k for k in range(len(speeds)) if speeds[k] <= threshold]


def find_clusters(idxs, dists, min_points, max_gap_m):
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


def spatial_consistency(idx, dists, curvs, window_m=WINDOW_M):
    """공간축 재정의(260차 계속): idx 지점 기준 ±window_m 이웃 포인트 중
    유의미한 곡률(FLOOR_THRESHOLD 초과)을 가진 포인트들의 부호 일치율.
    support(이웃 유의미 포인트 개수)==0이면 consistency=0.0(고립 스파이크,
    최저신뢰) -- 기존 정의의 "표본 1개=자명한 1.0" 문제를 여기서 직접 해소."""
    target = curvs[idx]
    target_sign = 1 if target > 0 else (-1 if target < 0 else 0)
    d0 = dists[idx]
    support = 0
    agree = 0
    for j, (d, c) in enumerate(zip(dists, curvs)):
        if j == idx:
            continue
        if abs(d - d0) > window_m:
            continue
        if abs(c) < FLOOR_THRESHOLD:
            continue
        support += 1
        sign = 1 if c > 0 else (-1 if c < 0 else 0)
        if sign == target_sign:
            agree += 1
    if support == 0:
        return 0.0, 0
    return agree / support, support


def replay(rows):
    """프레임별로 매칭된 (frame, cluster) 각각에 대해 새 spatial_consistency
    신호와 기존(260차) persistence(단순화판, track 없이 이번 프레임 클러스터
    개수만으로 대략 재현 불가하므로 이 스크립트는 spatial_consistency +
    support만 계측하고, persistence와의 상관관계 비교는 별도로 두 CSV를
    조인해 확인한다 -- 아래 main()의 correlation 절 참고)."""
    out = []
    for row in rows:
        t = float(row["t"])
        if not row.get("vEgo"):
            continue
        v_ego_ms = float(row["vEgo"])
        v_ego_kph = v_ego_ms * 3.6

        dists, curvs, speeds = build_dist_curv_speed(row.get("naviPaths", ""))
        if not speeds:
            continue

        gate_base = gate_base_kph(row, v_ego_kph)
        c0 = gate_candidates(speeds, gate_base)
        clusters = find_clusters(c0, dists, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        if not clusters:
            continue

        for c in clusters:
            idx = c[0]
            consistency, support = spatial_consistency(idx, dists, curvs)
            out.append({
                "t": t,
                "dist": dists[idx],
                "consistency": consistency,
                "support": support,
                "cluster_size": len(c),
            })
    return out


def summarize_window(records, lo, hi, label):
    w = [r for r in records if lo <= r["t"] <= hi]
    print(f"\n=== {label} (t={lo}~{hi}, {len(w)} (frame,cluster) 레코드) ===")
    if not w:
        print("  (매칭된 클러스터 없음)")
        return

    def stats(name, arr):
        arr_sorted = sorted(arr)
        n = len(arr_sorted)
        mean = sum(arr_sorted) / n
        p50 = arr_sorted[n // 2]
        print(f"  {name}: mean={mean:.3f} median={p50:.3f} "
              f"min={arr_sorted[0]:.3f} max={arr_sorted[-1]:.3f}")

    stats("spatial_consistency(0~1)", [r["consistency"] for r in w])
    stats("support(이웃 유의미 포인트 수)", [r["support"] for r in w])

    zero_support = sum(1 for r in w if r["support"] == 0)
    print(f"  support==0(고립 스파이크, consistency 자동 0.0) 비율: "
          f"{100*zero_support/len(w):.1f}% ({zero_support}/{len(w)})")

    high_conf = sum(1 for r in w if r["support"] >= 2 and r["consistency"] >= 0.8)
    print(f"  고신뢰(support>=2 & consistency>=0.8) 비율: "
          f"{100*high_conf/len(w):.1f}% ({high_conf}/{len(w)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--window", type=float, nargs=2, action="append", default=None)
    ap.add_argument("--label", action="append", default=None)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    if not rows:
        print("no rows", file=sys.stderr)
        sys.exit(1)

    records = replay(rows)
    print(f"=== 전체 {len(rows)}행 처리, (frame,cluster) 매칭 레코드 {len(records)}건 ===")

    # 전체 corpus 기준 support==0(고립 스파이크) 비율 -- 기존 정의가 놓쳤던
    # "표본부족으로 자명한 1.0" 케이스가 실제로 전체의 몇 %였는지 정량화
    zero_support_all = sum(1 for r in records if r["support"] == 0)
    print(f"=== 전체 기준 support==0 비율: "
          f"{100*zero_support_all/len(records):.1f}% "
          f"({zero_support_all}/{len(records)}) -- 이 비율만큼 기존 정의가 "
          f"근거 없이 1.0을 보고했던 것으로 추정 ===")

    if args.window:
        labels = args.label or [f"win{i}" for i in range(len(args.window))]
        for (lo, hi), label in zip(args.window, labels):
            summarize_window(records, lo, hi, label)
    else:
        for lo, hi, label in DEFAULT_WINDOWS:
            summarize_window(records, lo, hi, label)


if __name__ == "__main__":
    main()
