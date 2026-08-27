#!/usr/bin/env python3
"""라우트 CSV 하나를 표준 분석 스위트로 훑어 JSON 요약을 출력.
사용: python3 route_summary.py <route.csv> [--label LABEL]
"""
import sys, json, argparse
sys.path.insert(0, "/home/claude/devnotes/toolkit")
from analysis_helpers import (
    load_csv, load_meta, trip_summary, harsh_brake_events,
    turn_speed_violations, steering_oscillation_detector,
    lead_cut_in_detector, segment_boundary_lead_loss_artifacts,
    all_source_pairs_flicker_summary, ttc_danger_events,
    curve_noise_summary_refined, vision_to_radar_crossover,
    remove_driver_intervention,
)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    meta = load_meta(args.csv_path)

    out = {"label": args.label, "meta": meta, "n_rows": len(rows)}

    out["trip_summary"] = trip_summary(rows)

    adas_rows = remove_driver_intervention(rows)
    out["n_rows_adas"] = len(adas_rows)

    hb = harsh_brake_events(adas_rows)
    out["harsh_brake_events"] = {"count": len(hb), "events": hb[:20]}

    tsv = turn_speed_violations(adas_rows)
    out["turn_speed_violations"] = {"count": len(tsv), "events": tsv[:20]}

    osc = steering_oscillation_detector(rows)
    out["steering_oscillation"] = {"count": len(osc), "events": osc[:10]}

    ci = lead_cut_in_detector(rows)
    out["cut_in"] = {"count": len(ci), "events": ci[:20]}

    if meta.get("segment_state_carryover_fix"):
        out["segment_boundary_artifacts"] = {"skipped": "신버전 CSV, 아티팩트 없음"}
    else:
        sba = segment_boundary_lead_loss_artifacts(rows)
        out["segment_boundary_artifacts"] = {"count": len(sba), "events": sba[:20]}

    pairs = all_source_pairs_flicker_summary(rows, min_count=3)
    out["source_pair_flicker"] = pairs

    ttcd = ttc_danger_events(rows)
    ttcd_adas = [e for e in ttcd if e.get("cruiseEnabled") in (True, "True")]
    out["ttc_danger"] = {"count_total": len(ttcd), "count_adas": len(ttcd_adas), "events": ttcd[:20]}

    try:
        cns = curve_noise_summary_refined(rows)
        out["curve_noise_refined"] = cns
    except Exception as e:
        out["curve_noise_refined"] = {"error": str(e)}

    try:
        vrc = vision_to_radar_crossover(rows)
        highway = [e for e in vrc if e.get("highway")]
        out["vision_radar_crossover"] = {"count_total": len(vrc), "count_highway_est": len(highway), "events": vrc[:15]}
    except Exception as e:
        out["vision_radar_crossover"] = {"error": str(e)}

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))

if __name__ == "__main__":
    main()
