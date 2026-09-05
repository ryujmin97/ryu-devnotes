#!/usr/bin/env python3
"""
sim_route_260_gyesok2_crossscale_curvature_consistency.py (260차 계속2, 신규)

목적: 260차 계속(공간축 sign-consistency, ±40m 이웃 부호 일치율) 시도가
S자형 실제 도로 구간(부호가 자연스럽게 반전되는 정상 형상)에서 오히려
낮은 값을 줄 위험이 확인되어(60~90m 구간이 음->양으로 반전하는 실측 사례,
아래 "계속 시도 기록" 참고) 다른 축으로 재설계한다.

**재정의**: 기존 프로덕션 로직(147/158차, `recompute_route_curvature_speed`의
macro/fine merge)이 이미 "같은 지점을 두 개의 서로 다른 chord 길이(macro=
40m, fine=10m)로 각각 계산해서 더 급한(=speed_cap이 낮은) 쪽을 채택"하는
구조를 갖고 있다는 데 착안 -- **이 두 스케일이 같은 지점에서 서로 동의
(부호 일치)하는지를 그대로 confidence 신호로 재사용**한다.

  - 실제 커브(연속된 도로 형상)는 chord를 40m로 넓혀도 방향(부호)이
    유지된다 -- 아래 실측(t=2109.9, IC gore)에서 fine 60~90m 구간
    (부호 -,-,+,+)과 macro 40~110m 구간(부호 -,-,-,-,+,+,+,+)이 동일
    지점에서 동일 부호로 일치함을 확인(계속 시도 기록 참고).
  - GPS 노이즈로 인한 국소 스파이크는 chord를 넓히면(=여러 원시 포인트를
    평균하는 효과) 대개 상쇄되어 부호가 반대로 나오거나 거의 0이 된다.

**신호 정의** (프레임 1개만으로 즉시 계산 가능 -- 시간축 아님, 260차
원래 문제였던 "표본부족 자명한 1.0"과 무관):
  agree(0/1)      = sign(macro_curv_at_same_dist) == sign(fine_curv_at_idx)
                    (단, 둘 중 하나라도 FLOOR_THRESHOLD 미만이면 "판정불가"
                    로 별도 표시 -- 강제로 0/1 부여하지 않음)
  magnitude_ratio = |macro_curv| / |fine_curv| (0~1+, 1에 가까울수록
                    스케일 불변 -- 진짜 급커브일수록 macro에서도 거의
                    안 줄어듦)

**계속 시도 기록(공간축 sign-consistency, 폐기)**: ±40m 이웃 부호 일치율로
정의했을 때 IC gore/S커브 양쪽 다 100% 고신뢰로 나왔으나, 원시 곡률 배열을
직접 열어보니 S자형 구간(예: t=2109.9, dist 60~90m에서 부호가 -,-,+,+로
자연 반전)이 존재해 이 정의가 "정상적인 방향 전환"과 "노이즈로 인한 부호
뒤집힘"을 구분하지 못할 위험이 확인됨(이번 corpus에서는 우연히 후보
윈도우가 반전 경계를 피해가 100%로 나왔을 뿐, 재현성 보장 안 됨) -- 폐기
사유로 devnotes에 남김(§24 유사 정의).

사용:
    python3 sim_route_260_gyesok2_crossscale_curvature_consistency.py <route.csv> \
        --window 2108 2112 --label ic_gore --window 2116 2122.2 --label s_curve
"""
import argparse
import csv
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

FLOOR_THRESHOLD = 0.001  # 157차 패치(ROUTE_CURVE_NEGLIGIBLE_THRESHOLD), 현재 HEAD와 동일
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0

DEFAULT_WINDOWS = [
    (2190.0, 2225.0, "tunnel"),
    (2108.0, 2112.0, "ic_gore"),
    (2116.0, 2122.2, "s_curve"),
]


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_fine_and_macro(navi_paths_str):
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < 2 * 2 + 1:
        return None
    fine = recompute_route_curvature_speed(
        points, distances, sample=1, sample_fine=None,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD)
    macro = recompute_route_curvature_speed(
        points, distances, sample=4, sample_fine=None,
        road_limit_speed=200.0, floor_threshold=FLOOR_THRESHOLD)
    if not fine or not macro:
        return None
    return fine, macro


def nearest_macro(macro, dist):
    return min(macro, key=lambda m: abs(m[0] - dist))


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


def cross_scale_consistency(idx, fine_dists, fine_curvs, macro):
    fine_curv = fine_curvs[idx]
    m_dist, macro_curv, _ = nearest_macro(macro, fine_dists[idx])
    if abs(fine_curv) < FLOOR_THRESHOLD or abs(macro_curv) < FLOOR_THRESHOLD:
        return None, None  # 판정불가(둘 중 하나가 이미 무의미한 크기)
    fine_sign = 1 if fine_curv > 0 else -1
    macro_sign = 1 if macro_curv > 0 else -1
    agree = 1 if fine_sign == macro_sign else 0
    ratio = min(abs(macro_curv) / abs(fine_curv), 2.0)  # 2.0에서 클램프(이상치 방지)
    return agree, ratio


def replay(rows):
    out = []
    for row in rows:
        t = float(row["t"])
        if not row.get("vEgo"):
            continue
        v_ego_ms = float(row["vEgo"])
        v_ego_kph = v_ego_ms * 3.6

        navi = row.get("naviPaths", "")
        built = build_fine_and_macro(navi)
        if not built:
            continue
        fine, macro = built
        fine_dists = [m[0] for m in fine]
        fine_curvs = [m[1] for m in fine]
        fine_speeds = [m[2] for m in fine]

        gate_base = gate_base_kph(row, v_ego_kph)
        c0 = gate_candidates(fine_speeds, gate_base)
        clusters = find_clusters(c0, fine_dists, ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        if not clusters:
            continue

        for c in clusters:
            idx = c[0]
            agree, ratio = cross_scale_consistency(idx, fine_dists, fine_curvs, macro)
            out.append({
                "t": t,
                "dist": fine_dists[idx],
                "agree": agree,
                "ratio": ratio,
            })
    return out


def summarize_window(records, lo, hi, label):
    w = [r for r in records if lo <= r["t"] <= hi]
    print(f"\n=== {label} (t={lo}~{hi}, {len(w)} (frame,cluster) 레코드) ===")
    if not w:
        print("  (매칭된 클러스터 없음)")
        return

    judged = [r for r in w if r["agree"] is not None]
    unjudged = len(w) - len(judged)
    print(f"  판정불가(둘 중 하나 FLOOR_THRESHOLD 미만): {unjudged}/{len(w)} "
          f"({100*unjudged/len(w):.1f}%)")
    if judged:
        agree_rate = sum(r["agree"] for r in judged) / len(judged)
        ratios = sorted(r["ratio"] for r in judged)
        n = len(ratios)
        print(f"  cross_scale_agree 비율: {100*agree_rate:.1f}% ({sum(r['agree'] for r in judged)}/{len(judged)})")
        print(f"  magnitude_ratio(macro/fine, 0~2 클램프): "
              f"mean={sum(ratios)/n:.3f} median={ratios[n//2]:.3f} "
              f"min={ratios[0]:.3f} max={ratios[-1]:.3f}")


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

    judged_all = [r for r in records if r["agree"] is not None]
    if judged_all:
        agree_rate_all = sum(r["agree"] for r in judged_all) / len(judged_all)
        print(f"=== 전체 기준 cross_scale_agree 비율: {100*agree_rate_all:.1f}% "
              f"({len(judged_all)}/{len(records)}건 판정 가능) ===")

    if args.window:
        labels = args.label or [f"win{i}" for i in range(len(args.window))]
        for (lo, hi), label in zip(args.window, labels):
            summarize_window(records, lo, hi, label)
    else:
        for lo, hi, label in DEFAULT_WINDOWS:
            summarize_window(records, lo, hi, label)


if __name__ == "__main__":
    main()
