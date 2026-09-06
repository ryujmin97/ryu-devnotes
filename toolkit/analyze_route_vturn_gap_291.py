#!/usr/bin/env python3
"""
[291차 신규] "route가 vturn보다 작은 값으로 arbitration에서 이긴" 경우를
찾아 그 폭(gap)을 정량화하고, gap이 route 쪽의 어떤 계산 단계(커브
목표속도 자체 vs 접근 감속 스케줄)에서 주로 발생하는지 분류한다.

배경: carrot_serv.py::update_navi()의 speed_n_sources는
    vturn 후보 = max(abs(vTurnSpeed), AutoCurveSpeedLowerLimit)
    route 후보 = route_speed (carrot_man.py::carrot_navi_route()가
                 반환한 out_speed, 역시 AutoCurveSpeedLowerLimit 바닥 적용)
둘 다 min()으로 경쟁한다(TurnSpeedControlMode in [1,2]/[2,3,4]에서 동시
참가). src=='route'인 프레임 중 vturn 후보보다 route 후보가 낮았던
(=route가 vturn을 누르고 이긴) 프레임만 골라 그 격차를 분석한다.

사용:
    python3 analyze_route_vturn_gap_291.py route1.csv route2.csv ... \
        [--lower-limit 20.0] [--min-gap 1.0] [--merge-tol 1.0] [--json out.json]

--lower-limit: AutoCurveSpeedLowerLimit 실제 설정값(kph). params_backup의
    값을 그대로 넣는다(기본 20.0 -- 이번 세션 업로드 params_backup-6.json
    실측값).
--min-gap: 이 이상 벌어진 경우만 "route가 vturn을 눌렀다"로 집계
    (부동소수/반올림 잡음 배제).
"""
import argparse
import csv
import json
import sys


def to_float(v, default=None):
    try:
        if v in (None, "", "None"):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def analyze_file(path, lower_limit, min_gap, vturn_active_thresh):
    rows = load_rows(path)
    episodes = []
    cur = None
    all_gaps = []
    all_vego = []
    n_route_total = 0
    active_gaps = []       # vturn도 같은 커브를 인지 중인(raw < thresh) 부분집합
    active_frames = []

    for r in rows:
        src = r.get("src")
        if src != "route":
            if cur is not None:
                episodes.append(cur)
                cur = None
            continue
        n_route_total += 1
        desired = to_float(r.get("desiredSpeed"))
        vturn_raw = to_float(r.get("vTurnSpeed"))
        v_ego = to_float(r.get("vEgo"))
        if desired is None or vturn_raw is None:
            if cur is not None:
                episodes.append(cur)
                cur = None
            continue
        vturn_cand = max(abs(vturn_raw), lower_limit)
        gap = vturn_cand - desired  # >0 이면 route가 vturn보다 작아서 이김
        v_ego_kph = v_ego * 3.6 if v_ego is not None else None

        if gap >= min_gap:
            frame = {
                "t": to_float(r.get("t")),
                "desiredSpeed": desired,
                "vTurnSpeed_raw": vturn_raw,
                "vturn_candidate": vturn_cand,
                "gap": gap,
                "v_ego_kph": v_ego_kph,
                "routeApexDist": to_float(r.get("routeApexDist")),
                "routeApexSpeed": to_float(r.get("routeApexSpeed")),
                "routeOutSpeed": to_float(r.get("routeOutSpeed")),
            }
            all_gaps.append(gap)
            if v_ego_kph is not None:
                all_vego.append(v_ego_kph)
            if abs(vturn_raw) < vturn_active_thresh:
                active_gaps.append(gap)
                active_frames.append(frame)
            if cur is None:
                cur = {"file": path, "start_t": frame["t"], "frames": []}
            cur["frames"].append(frame)
        else:
            if cur is not None:
                episodes.append(cur)
                cur = None
    if cur is not None:
        episodes.append(cur)

    # 요약
    ep_summaries = []
    for ep in episodes:
        fr = ep["frames"]
        gaps = [f["gap"] for f in fr]
        vegos = [f["v_ego_kph"] for f in fr if f["v_ego_kph"] is not None]
        apex_dists = [f["routeApexDist"] for f in fr if f["routeApexDist"] is not None]
        ep_summaries.append({
            "file": ep["file"],
            "start_t": ep["start_t"],
            "end_t": fr[-1]["t"],
            "duration_s": (fr[-1]["t"] - ep["start_t"]) if fr[-1]["t"] is not None and ep["start_t"] is not None else None,
            "n_frames": len(fr),
            "gap_max": max(gaps),
            "gap_mean": sum(gaps) / len(gaps),
            "vego_min_kph": min(vegos) if vegos else None,
            "vego_max_kph": max(vegos) if vegos else None,
            "apex_dist_at_max_gap": apex_dists[gaps.index(max(gaps))] if apex_dists and len(apex_dists) == len(gaps) else None,
        })

    return {
        "file": path,
        "n_route_frames_total": n_route_total,
        "n_route_wins_over_vturn_frames": len(all_gaps),
        "pct_of_route_frames": (100.0 * len(all_gaps) / n_route_total) if n_route_total else 0.0,
        "gap_mean": (sum(all_gaps) / len(all_gaps)) if all_gaps else None,
        "gap_max": max(all_gaps) if all_gaps else None,
        "gap_p90": sorted(all_gaps)[int(0.9 * (len(all_gaps) - 1))] if all_gaps else None,
        "vego_mean_kph": (sum(all_vego) / len(all_vego)) if all_vego else None,
        "n_episodes": len(ep_summaries),
        "episodes": ep_summaries,
        "n_active_both_frames": len(active_gaps),
        "active_gap_mean": (sum(active_gaps) / len(active_gaps)) if active_gaps else None,
        "active_gap_p90": sorted(active_gaps)[int(0.9 * (len(active_gaps) - 1))] if active_gaps else None,
        "active_gap_max": max(active_gaps) if active_gaps else None,
        "active_frames_sample": active_frames,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--lower-limit", type=float, default=20.0,
                     help="AutoCurveSpeedLowerLimit 실측 설정값(kph), 기본 20.0")
    ap.add_argument("--min-gap", type=float, default=1.0,
                     help="이 이상 벌어진 경우만 집계(기본 1.0kph)")
    ap.add_argument("--vturn-active-thresh", type=float, default=200.0,
                     help="abs(vTurnSpeed raw) < 이 값일 때만 \"vturn도 같은 "
                          "커브를 실제로 인지 중\"으로 보고 별도 집계 "
                          "(기본 200 -- vturn이 직선으로 보고 있으면 raw가 "
                          "~250 근처로 saturate됨, carrot_man.py V_CURVE_LOOKUP "
                          "외삽 특성)")
    ap.add_argument("--json", default=None)
    ap.add_argument("--top", type=int, default=15,
                     help="gap 큰 순으로 상위 몇 개 에피소드를 출력할지(기본 15)")
    args = ap.parse_args()

    results = []
    for path in args.csvs:
        res = analyze_file(path, args.lower_limit, args.min_gap, args.vturn_active_thresh)
        results.append(res)
        print(f"=== {path} ===")
        print(f"  route 프레임 총 {res['n_route_frames_total']}건 중 "
              f"vturn을 gap>={args.min_gap}kph로 이긴 프레임 "
              f"{res['n_route_wins_over_vturn_frames']}건 "
              f"({res['pct_of_route_frames']:.1f}%)")
        if res["gap_mean"] is not None:
            print(f"  gap(전체, vturn=직선무제한 상태 포함): mean={res['gap_mean']:.1f}kph, "
                  f"p90={res['gap_p90']:.1f}kph, max={res['gap_max']:.1f}kph")
            print(f"  vEgo mean(해당 프레임): {res['vego_mean_kph']:.1f}kph")
        print(f"  >> vturn도 같은 커브를 실측 인지 중(|vTurnSpeed raw|<{args.vturn_active_thresh})인 "
              f"부분집합: {res['n_active_both_frames']}건")
        if res["active_gap_mean"] is not None:
            print(f"     gap(진짜 불일치): mean={res['active_gap_mean']:.1f}kph, "
                  f"p90={res['active_gap_p90']:.1f}kph, max={res['active_gap_max']:.1f}kph")
        print(f"  에피소드(연속구간) 수: {res['n_episodes']}")

    all_eps = []
    for res in results:
        all_eps.extend(res["episodes"])
    all_eps.sort(key=lambda e: e["gap_max"], reverse=True)
    print(f"\n=== gap_max 상위 {args.top}개 에피소드 (전체 파일 통합) ===")
    for ep in all_eps[:args.top]:
        print(f"  {ep['file']} t={ep['start_t']:.2f}~{ep['end_t']:.2f} "
              f"({ep['duration_s']:.2f}s, {ep['n_frames']}프레임) "
              f"gap_max={ep['gap_max']:.1f} gap_mean={ep['gap_mean']:.1f} "
              f"vEgo={ep['vego_min_kph']:.1f}~{ep['vego_max_kph']:.1f}kph "
              f"apex_dist@max={ep['apex_dist_at_max_gap']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 저장: {args.json}")


if __name__ == "__main__":
    main()
