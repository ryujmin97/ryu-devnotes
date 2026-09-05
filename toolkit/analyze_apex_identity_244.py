#!/usr/bin/env python3
"""
analyze_apex_identity_244.py (244cha sinkyu, toolkit hupbo daesang)

mokjeog: routeApexIdx flicker-ga "dongil mulriieog apex-ui index pyohyeon-man
heundeullineun geot"(Position-Identity munje, CASE A)inji, "silje hubo
jache-ga bakkuineun geot"(CASE B)inji, geurigo geu jung-gan(CASE C, dist-neun
keuge byeonhaji-man idx gwangyega teugihan gyeongu)inji-reul gijon 232cha
sillo(gate eobsneun sunsu stage0 build)-ui routeApexIdx/Dist/Speed +
routeCandidate0~2Idx/Dist/Speed telemetry-man-euro pandeonghanda.

CASE jeong-ui (frame i-1 -> i):
  CASE_A: |d_idx| >= IDX_JUMP_THRESH  AND  |d_dist| <= DIST_STABLE_M
                                       AND |d_speed| <= SPEED_STABLE_KPH
          -> idx-man tuim, dongil mulriieog apex-ro chujeong (position-identity
             munje-ui jikjeobjeog jeunggeo)
  CASE_B: |d_idx| >= IDX_JUMP_THRESH  AND  (dist EODO speed-do keuge byeonham)
          -> silje hubo(mulriieog wichi)-ui jeonhwan, dansun index munje anim
  CASE_C: |d_idx| < IDX_JUMP_THRESH   AND  |d_dist| >= DIST_JUMP_M
          -> idx-neun geoui dongil-hae boinya, geori gyesan/path matching-i
             heundeullineun teugi-han gyeongu (vehicle position uncertainty,
             route distance jae-gyesan deung uisim)
  (wi 3gaji-e sokhaji anhneun frame-eun UNCLASSIFIED-ro nama)

candidate0~2 gyocha-hwagin: routeApexIdx(=candidate0Idx-wa dongil, 223cha
apex seontaeg-i hangsang candidates[0])-ga bakkuil ttae, jikjeon frame-ui
candidate0/1/2 jung eoneu geosi hyeonjae frame-ui candidate0-wa dist gijun
gakkaunji(<= MATCH_DIST_M)-reul hwagin -- "candidates[] naebu-eseo sunwi-man
bakkuin geosinji"-reul jikjeob boyeojunda.

ju-ui: routeCandidateCount/Candidate0~2-neun stage0(road_limit_speed
pilteo)만 jeog-yong-doen candidates list-eseo ppoban-da(223/196cha gujo).
242cha ROUTE_SEVERITY_GATE_RATIO(0.90) gate-neun 237cha-e chuga-doen
stage1-ini, i seuseuripteu-ga bunseoghaneun log(device build 232cha,
check_device_build.py-ro hwagindoem)-eneun stage1 gate jache-ga
eobseumeuro **gate hyogwa-wa wanjeonhi bunlidoen** sunsu identity bunseog-i
doenda(byeol-do t taeging pilyo eobsi).

sayongbeob:
    python3 analyze_apex_identity_244.py <csv_path> [--near-dist 15]
                                          [--idx-jump 1] [--dist-stable 15]
                                          [--speed-stable 3] [--dist-jump 40]
                                          [--match-dist 15]
"""
import argparse
import csv
from collections import Counter


def load_active_rows(csv_path):
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        idx = r.get("routeApexIdx", "")
        if idx in ("", "-1", None):
            continue
        try:
            out.append({
                "t": float(r["t"]),
                "idx": int(float(idx)),
                "dist": float(r["routeApexDist"]),
                "speed": float(r["routeApexSpeed"]),
                "out_speed": float(r.get("routeOutSpeed", 0.0) or 0.0),
                "cand_count": int(float(r.get("routeCandidateCount", 0) or 0)),
                "c0_idx": int(float(r.get("routeCandidate0Idx", -1) or -1)),
                "c0_dist": float(r.get("routeCandidate0Dist", 0.0) or 0.0),
                "c0_speed": float(r.get("routeCandidate0Speed", 0.0) or 0.0),
                "c1_idx": int(float(r.get("routeCandidate1Idx", -1) or -1)),
                "c1_dist": float(r.get("routeCandidate1Dist", 0.0) or 0.0),
                "c1_speed": float(r.get("routeCandidate1Speed", 0.0) or 0.0),
                "c2_idx": int(float(r.get("routeCandidate2Idx", -1) or -1)),
                "c2_dist": float(r.get("routeCandidate2Dist", 0.0) or 0.0),
                "c2_speed": float(r.get("routeCandidate2Speed", 0.0) or 0.0),
            })
        except (ValueError, TypeError):
            continue
    return out


def classify_transitions(rows, idx_jump_thresh=1, dist_stable_m=15.0,
                          speed_stable_kph=3.0, dist_jump_m=40.0):
    """frame-frame jeonhwan-eul CASE A/B/C/UNCLASSIFIED-ro bunlyu."""
    events = []
    for i in range(1, len(rows)):
        r0, r1 = rows[i - 1], rows[i]
        d_idx = r1["idx"] - r0["idx"]
        d_dist = r1["dist"] - r0["dist"]
        d_speed = r1["speed"] - r0["speed"]

        idx_jumped = abs(d_idx) >= idx_jump_thresh
        dist_stable = abs(d_dist) <= dist_stable_m
        speed_stable = abs(d_speed) <= speed_stable_kph
        dist_jumped = abs(d_dist) >= dist_jump_m

        if d_idx == 0:
            case = "SAME_IDX"
        elif idx_jumped and dist_stable and speed_stable:
            case = "CASE_A"
        elif idx_jumped and (not dist_stable or not speed_stable):
            case = "CASE_B"
        elif (not idx_jumped) and dist_jumped:
            case = "CASE_C"
        else:
            case = "UNCLASSIFIED"

        events.append({
            "t": r1["t"], "case": case,
            "d_idx": d_idx, "d_dist": d_dist, "d_speed": d_speed,
            "r0": r0, "r1": r1,
        })
    return events


def candidate_reidentify(events, match_dist_m=15.0):
    """CASE_B/UNCLASSIFIED frame-e daehae, jikjeon frame-ui candidate0/1/2
    jung hana-ga hyeonjae candidate0-wa dist gijun gakkaunji hwagin.
    -> candidates[] naeb-e "dongil mulriieog apex-ga sunwi-man milryeonan"
       gyeongu-reul CASE_A-wa byeoldo-ro chujeoghae naenda(idx jeongui-man
       bogo-neun mot japneun chuga jeungeo)."""
    reidentified = []
    for e in events:
        if e["case"] not in ("CASE_B", "UNCLASSIFIED"):
            continue
        r0, r1 = e["r0"], e["r1"]
        c1_target_dist = r1["c0_dist"]
        prev_candidates = [
            (r0["c0_idx"], r0["c0_dist"]),
            (r0["c1_idx"], r0["c1_dist"]),
            (r0["c2_idx"], r0["c2_dist"]),
        ]
        best = None
        for idx, dist in prev_candidates:
            if idx == -1:
                continue
            d = abs(dist - c1_target_dist)
            if d <= match_dist_m and (best is None or d < best[1]):
                best = (idx, d)
        if best is not None:
            reidentified.append({
                "t": e["t"], "case": e["case"],
                "prev_candidates": prev_candidates,
                "matched_prev_idx": best[0], "match_dist_diff": best[1],
            })
    return reidentified


def summarize(rows, events, reident, args):
    total = len(events)
    counts = Counter(e["case"] for e in events)
    print(f"[load] apex-active frame: {len(rows)} (t={rows[0]['t']:.2f}~{rows[-1]['t']:.2f})")
    print(f"[transitions] frame-frame jeon-i chongsu: {total}")
    print()
    print("=== CASE bunpo ===")
    for case in ("SAME_IDX", "CASE_A", "CASE_B", "CASE_C", "UNCLASSIFIED"):
        n = counts.get(case, 0)
        pct = n / total * 100 if total else 0.0
        print(f"  {case:14s}: {n:5d} ({pct:5.1f}%)")

    idx_changed = total - counts.get("SAME_IDX", 0)
    print()
    print(f"[idx flicker rate] idx byeonhwa frame: {idx_changed}/{total} = "
          f"{idx_changed/total*100 if total else 0:.1f}%")
    if idx_changed:
        case_a_of_changed = counts.get("CASE_A", 0) / idx_changed * 100
        case_b_of_changed = counts.get("CASE_B", 0) / idx_changed * 100
        print(f"  -> idx byeonhwa jung CASE_A(position-identity uisim) biyul: {case_a_of_changed:.1f}%")
        print(f"  -> idx byeonhwa jung CASE_B(silje hubo jeonhwan) biyul: {case_b_of_changed:.1f}%")

    print()
    print(f"=== candidate jae-sikbyeol (CASE_B/UNCLASSIFIED daesang, match_dist={args.match_dist}m) ===")
    print(f"  daesang frame: {sum(1 for e in events if e['case'] in ('CASE_B','UNCLASSIFIED'))}")
    print(f"  jae-sikbyeol seong-gong(jikjeon candidate1/2 jung hana-ga hyeonjae c0-wa gakkaum): {len(reident)}")
    if reident:
        print(f"  -> i geongeon-eun 'candidates[] naebu sunwi-man bakkuim'euro chujeong "
              f"gani -- sillo CASE_A-e gakkaun seong-gyeog")

    print()
    print("=== CASE_A sangwi 10geon (idx-man tuim, dongil apex uisim) ===")
    case_a_events = [e for e in events if e["case"] == "CASE_A"]
    for e in case_a_events[:10]:
        r0, r1 = e["r0"], e["r1"]
        print(f"  t={e['t']:.3f}  idx {r0['idx']:3d}->{r1['idx']:3d}  "
              f"dist {r0['dist']:6.1f}->{r1['dist']:6.1f}  "
              f"speed {r0['speed']:5.1f}->{r1['speed']:5.1f}")
    if len(case_a_events) > 10:
        print(f"  ... (chong {len(case_a_events)}geon)")

    print()
    print("=== CASE_B sangwi 10geon (silje hubo jeonhwan) ===")
    case_b_events = [e for e in events if e["case"] == "CASE_B"]
    for e in case_b_events[:10]:
        r0, r1 = e["r0"], e["r1"]
        print(f"  t={e['t']:.3f}  idx {r0['idx']:3d}->{r1['idx']:3d}  "
              f"dist {r0['dist']:6.1f}->{r1['dist']:6.1f}  "
              f"speed {r0['speed']:5.1f}->{r1['speed']:5.1f}  "
              f"cand_count {r0['cand_count']}->{r1['cand_count']}")
    if len(case_b_events) > 10:
        print(f"  ... (chong {len(case_b_events)}geon)")

    print()
    print("=== CASE_C sangwi 10geon (idx geoui dongil, dist bijeongsang) ===")
    case_c_events = [e for e in events if e["case"] == "CASE_C"]
    for e in case_c_events[:10]:
        r0, r1 = e["r0"], e["r1"]
        print(f"  t={e['t']:.3f}  idx {r0['idx']:3d}->{r1['idx']:3d}  "
              f"dist {r0['dist']:6.1f}->{r1['dist']:6.1f}  "
              f"speed {r0['speed']:5.1f}->{r1['speed']:5.1f}")
    if len(case_c_events) > 10:
        print(f"  ... (chong {len(case_c_events)}geon)")

    # tunnel gugan(t~2210-2215) jung-jeom bogo
    tunnel = [e for e in events if 2200.0 <= e["t"] <= 2230.0]
    if tunnel:
        print()
        print(f"=== tunnel gugan(t=2200~2230) jibjung bunseog ({len(tunnel)}geon jeon-i) ===")
        tc = Counter(e["case"] for e in tunnel)
        for case in ("SAME_IDX", "CASE_A", "CASE_B", "CASE_C", "UNCLASSIFIED"):
            print(f"  {case:14s}: {tc.get(case, 0)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--idx-jump", type=int, default=1,
                     help="i sangsu isang idx cha-i-myeon 'idx tuim'euro pandan (gibon 1)")
    ap.add_argument("--dist-stable", type=float, default=15.0,
                     help="i m ihawa cha-i-myeon dist 'anjeong'euro pandan (gibon 15m)")
    ap.add_argument("--speed-stable", type=float, default=3.0,
                     help="i kph ihawa cha-i-myeon speed 'anjeong'euro pandan (gibon 3kph)")
    ap.add_argument("--dist-jump", type=float, default=40.0,
                     help="i m isang cha-i-myeon dist 'tuim'euro pandan (gibon 40m)")
    ap.add_argument("--match-dist", type=float, default=15.0,
                     help="candidate jae-sikbyeol si dist maeching heoyongchi (gibon 15m)")
    args = ap.parse_args()

    rows = load_active_rows(args.csv_path)
    if len(rows) < 2:
        print("hwaseonghwa-doen apex-active frame-i bujokhamnida.")
        return

    events = classify_transitions(
        rows, idx_jump_thresh=args.idx_jump, dist_stable_m=args.dist_stable,
        speed_stable_kph=args.speed_stable, dist_jump_m=args.dist_jump,
    )
    reident = candidate_reidentify(events, match_dist_m=args.match_dist)
    summarize(rows, events, reident, args)


if __name__ == "__main__":
    main()
