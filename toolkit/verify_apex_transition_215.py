#!/usr/bin/env python3
"""
215cha: route apex 1cha->2cha jeonhwan(consecutive-curve apex transition)
sildo geomjeung script.

Mokjeog: 214cha B-an(sharpest_candidate_speed geori-injihwa) sildo patch(commit
4514e97) jeog-yong hu ilcha silju log(x18seg)eseo, WIP.md-e gilogdoen 4gae
pandeong gijun-eul jadong chaejeom handa.

Pandeong gijun (WIP.md 214cha gyesok3):
  1. 1cha apex tonggwa hu route jeyag-i sildaero haeje doeneunga
  2. haeje hu chalyang-i seoljeong sogdo-lo jaegasoghaneunga (=2cha apex-ga
     1cha boda deol geubhal ttae, out_after > apex1_speed)
  3. 2cha keobeu-ga pilyo gamsog geoli-e deul-eoss-eul ttae route gamsog-i
     dasi sijagdoeneunga (=2cha apex-ga 1cha boda deo geubhal ttae, out_after
     ga apex2_speed-e jeuggak geundeophaneunga)
  4. meon 2cha keobeu-ga hyeonjae chalyang-eul jeosog-e mukji anhneunga
     (=apex2_dist-ga keo-do out_after-ga apex2_speed-e mucho-jeog-eulo
     bindeoedji anhneunga)

Ipryeog: extract_log.py --with-navi-paths lo ppob-eun route.csv (routeApexIdx/
Dist/Speed, routeOutSpeed keollleom pilyo, 194cha chugalyeom)

Sayong:
    python3 verify_apex_transition_215.py <route.csv> [--near-dist 15.0]
        [--jump-dist 40.0] [--tol 0.5]
"""
import argparse
import csv
import sys


def load_active_rows(csv_path):
    """routeApexIdx != -1 in haengdeul-man t sun-eulo loading."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["routeApexIdx"] == "" or int(row["routeApexIdx"]) == -1:
                continue
            rows.append({
                "t": float(row["t"]),
                "vEgo": float(row["vEgo"]),
                "routeApexIdx": int(row["routeApexIdx"]),
                "routeApexDist": float(row["routeApexDist"]),
                "routeApexSpeed": float(row["routeApexSpeed"]),
                "routeOutSpeed": float(row["routeOutSpeed"]),
            })
    return rows


def find_transition_events(rows, near_dist=15.0, jump_dist=40.0):
    """apex geori-ga near_dist ihalo jeopgeunhan jigeob(1cha tonggwa) jigeub
    da-eum peuleim-eseo jump_dist isang geunjeungha-neun jigeom-eul 1cha->2cha
    jeonhwan ibenteu-lo tamji handa."""
    events = []
    for i in range(len(rows) - 1):
        r0, r1 = rows[i], rows[i + 1]
        if r0["routeApexDist"] <= near_dist:
            if (r1["routeApexDist"] - r0["routeApexDist"]) >= jump_dist:
                events.append((r0, r1))
    return events


def score_events(events, tol=0.5):
    """Design(gogseon_gagamsog_codeing.txt #5)e ttaleun pandeong:
    - apex2_speed >= apex1_speed - tol (2cha-ga deol geubham) -> release
      gidae: out_after > apex1_speed + tol
    - apex2_speed < apex1_speed - tol (2cha-ga deo geubham) -> jeuggak banyeong
      gidae: |out_after - apex2_speed| < 3.0
    """
    milder, sharper = [], []
    for r0, r1 in events:
        apex1_speed = r0["routeApexSpeed"]
        apex2_speed = r1["routeApexSpeed"]
        out_after = r1["routeOutSpeed"]
        entry = {
            "t": r0["t"], "apex1_speed": apex1_speed,
            "apex2_dist": r1["routeApexDist"], "apex2_speed": apex2_speed,
            "out_after": out_after,
        }
        if apex2_speed >= apex1_speed - tol:
            entry["released"] = out_after > apex1_speed + tol
            milder.append(entry)
        else:
            entry["immediate"] = abs(out_after - apex2_speed) < 3.0
            sharper.append(entry)
    return milder, sharper


def apex_idx_flicker_stats(rows):
    """apexIdx-ga peuleim-mada byeongyeongdoeneun bilyul mich geu ttae
    routeOutSpeed jeompeu keugi (179cha noise-point wiheom silche gwanchug)."""
    n_changed = 0
    out_diff_on_change = []
    out_diff_no_change = []
    for i in range(1, len(rows)):
        d_idx = rows[i]["routeApexIdx"] - rows[i - 1]["routeApexIdx"]
        d_out = abs(rows[i]["routeOutSpeed"] - rows[i - 1]["routeOutSpeed"])
        if d_idx != 0:
            n_changed += 1
            out_diff_on_change.append(d_out)
        else:
            out_diff_no_change.append(d_out)
    total = len(rows) - 1
    big_jumps_10 = sum(1 for i in range(1, len(rows))
                        if abs(rows[i]["routeOutSpeed"] - rows[i - 1]["routeOutSpeed"]) >= 10.0)
    return {
        "total_frames": total,
        "idx_change_frames": n_changed,
        "idx_change_pct": (n_changed / total * 100.0) if total else 0.0,
        "avg_out_diff_on_change": (sum(out_diff_on_change) / len(out_diff_on_change)) if out_diff_on_change else 0.0,
        "avg_out_diff_no_change": (sum(out_diff_no_change) / len(out_diff_no_change)) if out_diff_no_change else 0.0,
        "big_jump_ge10kph_frames": big_jumps_10,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--near-dist", type=float, default=15.0)
    ap.add_argument("--jump-dist", type=float, default=40.0)
    ap.add_argument("--tol", type=float, default=0.5)
    args = ap.parse_args()

    rows = load_active_rows(args.csv_path)
    print(f"[load] active(routeApexIdx!=-1) frames: {len(rows)}")

    events = find_transition_events(rows, args.near_dist, args.jump_dist)
    print(f"[detect] 1cha->2cha apex jeonhwan ibenteu: {len(events)}")

    milder, sharper = score_events(events, args.tol)

    print(f"\n=== gijun 1&2 (2cha-ga deol geubham -> release gidae) ===")
    print(f"haedang keiseu: {len(milder)}")
    if milder:
        n_ok = sum(1 for e in milder if e["released"])
        print(f"release gwanchug: {n_ok}/{len(milder)} = {n_ok/len(milder)*100:.1f}%")
        for e in milder:
            flag = "OK" if e["released"] else "FAIL"
            print(f"  [{flag}] t={e['t']:.2f} apex1={e['apex1_speed']:.1f} "
                  f"apex2_dist={e['apex2_dist']:.0f}m apex2={e['apex2_speed']:.1f} "
                  f"out_after={e['out_after']:.1f}")

    print(f"\n=== gijun 3 (2cha-ga deo geubham -> jeuggak banyeong gidae) ===")
    print(f"haedang keiseu: {len(sharper)}")
    if sharper:
        n_ok = sum(1 for e in sharper if e["immediate"])
        print(f"jeuggak banyeong gwanchug: {n_ok}/{len(sharper)} = {n_ok/len(sharper)*100:.1f}%")
        for e in sharper:
            flag = "OK" if e["immediate"] else "FAIL"
            print(f"  [{flag}] t={e['t']:.2f} apex1={e['apex1_speed']:.1f} "
                  f"apex2_dist={e['apex2_dist']:.0f}m apex2={e['apex2_speed']:.1f} "
                  f"out_after={e['out_after']:.1f}")

    print(f"\n=== gijun 4 (meon 2cha keobeu jeosog gojeong bangji, chamgo) ===")
    far_cases = [e for e in milder if e["apex2_dist"] >= 100.0]
    for e in far_cases:
        margin = e["out_after"] - e["apex2_speed"]
        print(f"  t={e['t']:.2f} apex2_dist={e['apex2_dist']:.0f}m apex2={e['apex2_speed']:.1f} "
              f"out_after={e['out_after']:.1f} (margin={margin:+.1f}kph)")

    print(f"\n=== apexIdx flicker tonggye (179cha noise-point wiheom silche gwanchug) ===")
    stats = apex_idx_flicker_stats(rows)
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
