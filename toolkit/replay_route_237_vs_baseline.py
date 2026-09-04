#!/usr/bin/env python3
"""
replay_route_237_vs_baseline.py (238차, 신규)

목적: 237차 patch(`ROUTE_SEVERITY_GATE_RATIO=0.70` severity gate,
carrot_man.py fc98eaa)를 실제 device에 적용하기 전, "158/224차 방식"의
A/B replay로 desiredSpeed(route out_speed) 출력 시계열까지 오프라인
재현해 대조한다. 237차 WIP.md의 미확인 사항("candidate 레벨 카운트만
검증했고 실제 desiredSpeed 시계열까지는 안 함") 해소가 목적.

구성 -- 두 단계를 조합:
  (1) candidate/apex 선택 -- sim_route_234_spatial_apex_continuity.py
      (234차 계속4~10, 237차에 재확인)와 동일한 방식으로 naviPaths를
      recompute_route_curvature_speed()로 재구성해 매 프레임 후보 배열을
      만든다.
        baseline(A) = stage0만 (speeds[k] < nRoadLimitSpeed) -- 232차
                      HEAD(현재 device에 실제 올라가 있는 코드, 197차 WIP
                      기준 게이트 없음)와 동일
        patched(B)  = stage0 + stage1(237차 patch 그대로: speeds[k] <
                      max(v_ego_kph,1.0) * ROUTE_SEVERITY_GATE_RATIO)
  (2) apex -> out_speed 상태기계 -- replay_route_223_vs_baseline.py
      (224차)의 RouteSim223을 그대로(무변경) 재사용한다. 237차 patch는
      candidates 구성부(위 (1))만 건드렸고 apex 도달 이후 route_active/
      route_release_time 상태기계 및 감속식(carrot_man.py L947~)은 전혀
      바꾸지 않았으므로(diff 참고, WIP.md 237차) 이 하류 로직은 A/B가
      완전히 동일 -- 각기 독립된 RouteSim223 인스턴스에 (1)에서 만든
      서로 다른 apex_idx/apex_dist/apex_speed 스트림을 흘려보내
      out_speed를 각각 계산한다.

한계(반드시 인지, replay_route_223_vs_baseline.py와 동일 계열):
1. turnSpeedControlMode가 로그에 프레임별로 없어 --assume-mode-on(기본
   True)으로 전 구간 가정.
2. autoNaviSpeedDecelRate/autoNaviSpeedCtrlEnd는 device Params값이라
   로그에 없음 -- --decel-rate(기본 1.00)/--ctrl-end(기본 7.0) CLI로 가정.
3. RouteSim223 자체가 205~228차의 ceiling/boost/route_inert 등 후속
   로직을 포함하지 않는 단순화 버전(224차 "MIXED" 결과 참고) -- 절대값
   보다는 "게이트 도입으로 apex 후보/out_speed가 어떻게 달라지는가"라는
   구조적 비교에 우선 쓸 것.
4. build_speeds_distances()의 floor_threshold 처리에 쓰는
   road_limit_speed=200.0은 실제 nRoadLimitSpeed가 아니라 "곡률이
   negligible일 때 사실상 무제한임을 표시하는 placeholder"다(234차
   계속6 관례 그대로) -- 실제 stage0 게이트 비교는 이 값이 아니라 매
   프레임 CSV의 실측 nRoadLimitSpeed로 별도 수행한다.

입력: extract_log.py --with-navi-paths 출력 CSV (t, vEgo, nRoadLimitSpeed,
      naviPaths, liveRouteSpeed 컬럼 필수)
출력: stdout 요약(stage0->stage1 후보 감소량 재확인, out_speed 시계열
      overshoot 구간 A/B 대조, apex 점프(flicker) 건수 A/B 대조,
      프레임간 최대낙차) + --json 프레임별 덤프

사용:
  python3 replay_route_237_vs_baseline.py <route.csv> \\
      [--decel-rate 1.00] [--ctrl-end 7.0] [--assume-mode-on] \\
      [--start-t T0] [--end-t T1] [--json out.json]
"""
import argparse
import csv
import json
import sys

sys.path.insert(0, ".")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0

MACRO_SAMPLE = 4
FINE_SAMPLE = 1                    # ROUTE_CURVATURE_FINE_SAMPLE, 147차
FLOOR_THRESHOLD = 0.001            # ROUTE_CURVE_NEGLIGIBLE_THRESHOLD, 157차 패치, 232/237차 HEAD와 동일
ROUTE_SEVERITY_GATE_RATIO = 0.70   # 237차 patch(carrot_man.py fc98eaa)와 동일
APEX_JUMP_GAP_M = 40.0             # 234차/237차와 동일 flicker 지표 기준


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_speeds_distances(navi_paths_str):
    """234차 계속4 build_speeds_distances()와 동일(placeholder floor=200.0,
    한계 4번 참고) -- 232/237차 HEAD의 macro+fine merge 로직 재현."""
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
    return [k for k in range(len(speeds)) if speeds[k] < threshold]


def select_apex(dists, speeds, road_limit_kph, v_ego_kph, apply_severity_gate):
    """carrot_man.py L879-897(237차 HEAD)의 candidates 구성부를 그대로
    옮긴 것. apply_severity_gate=False면 stage0(232차, road_limit_speed
    필터만)까지, True면 stage0+stage1(237차, vEgo*0.70 gate 추가)까지."""
    c0 = gate_candidates(speeds, road_limit_kph)
    if apply_severity_gate:
        gate_base = max(v_ego_kph, 1.0) * ROUTE_SEVERITY_GATE_RATIO
        c1 = [k for k in c0 if speeds[k] < gate_base]
    else:
        c1 = c0
    if not c1:
        return None, None, None
    idx = c1[0]
    return idx, dists[idx], speeds[idx]


class RouteSim223:
    """replay_route_223_vs_baseline.py(224차)의 RouteSim223과 100% 동일
    (무변경 재사용) -- carrot_man.py::carrot_navi_route() apex 도달 이후
    route_active/route_release_time 상태기계 + 감속식(L947~, 237차에서도
    미변경 구간). A/B 두 인스턴스에 서로 다른 apex 스트림을 흘려보낸다."""

    def __init__(self, decel_rate_mss, ctrl_end_s, assume_mode_on=True):
        self.route_active = False
        self.route_release_time = None
        self.decel_rate_mss = decel_rate_mss
        self.ctrl_end_s = ctrl_end_s
        self.assume_mode_on = assume_mode_on

    def step(self, t, v_ego_kph, apex_idx, apex_dist, apex_speed_kph):
        route_enabled = self.assume_mode_on
        if not route_enabled:
            self.route_active = False
            self.route_release_time = None
            return None

        if self.route_release_time is not None:
            if (t - self.route_release_time) < ROUTE_RELEASE_HOLD_S:
                return None
            self.route_release_time = None

        candidates_empty = (apex_idx is None or int(apex_idx) < 0)
        if candidates_empty:
            if self.route_active:
                self.route_active = False
                self.route_release_time = t
            return None

        v_ego_ms = v_ego_kph / 3.6
        if self.route_active and apex_dist <= ROUTE_APEX_REACHED_DIST_M:
            self.route_active = False
            self.route_release_time = t
            return None
        if not self.route_active and v_ego_kph <= apex_speed_kph:
            return None

        self.route_active = True
        target_ms = apex_speed_kph / 3.6
        eff_dist = max(0.0, apex_dist - target_ms * self.ctrl_end_s)
        if v_ego_ms <= target_ms or eff_dist <= 0:
            required_decel_mss = 0.0
        else:
            required_decel_mss = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
        applied_decel_mss = min(max(required_decel_mss, 0.0), self.decel_rate_mss)
        out_speed_ms = max(target_ms, v_ego_ms - applied_decel_mss * ROUTE_SPEED_LOOP_DT)
        return out_speed_ms * 3.6


def replay(rows, decel_rate_mss, ctrl_end_s, assume_mode_on=True):
    sim_a = RouteSim223(decel_rate_mss, ctrl_end_s, assume_mode_on)  # baseline(232차, gate 없음)
    sim_b = RouteSim223(decel_rate_mss, ctrl_end_s, assume_mode_on)  # patched(237차, 0.70 gate)
    out = []
    for row in rows:
        t = float(row["t"])
        v_ego_kph = float(row["vEgo"]) * 3.6
        try:
            road_limit_kph = float(row.get("nRoadLimitSpeed", "") or 0.0)
        except ValueError:
            road_limit_kph = 0.0
        if road_limit_kph <= 0:
            road_limit_kph = v_ego_kph  # 구버전 CSV 폴백(234차 계속6 gate_base_kph 관례)

        dists, speeds = build_speeds_distances(row.get("naviPaths", ""))

        if not speeds:
            apex_a = (None, None, None)
            apex_b = (None, None, None)
        else:
            apex_a = select_apex(dists, speeds, road_limit_kph, v_ego_kph, apply_severity_gate=False)
            apex_b = select_apex(dists, speeds, road_limit_kph, v_ego_kph, apply_severity_gate=True)

        out_a = sim_a.step(t, v_ego_kph, apex_a[0], apex_a[1], apex_a[2])
        out_b = sim_b.step(t, v_ego_kph, apex_b[0], apex_b[1], apex_b[2])

        live = float(row.get("liveRouteSpeed", "nan") or "nan")

        out.append({
            "t": t, "v_ego_kph": v_ego_kph, "road_limit_kph": road_limit_kph,
            "apex_a_idx": apex_a[0], "apex_a_dist": apex_a[1], "apex_a_speed": apex_a[2],
            "apex_b_idx": apex_b[0], "apex_b_dist": apex_b[1], "apex_b_speed": apex_b[2],
            "live_route_speed": live,
            "out_a_speed": out_a, "out_b_speed": out_b,
            "route_active_a": sim_a.route_active, "route_active_b": sim_b.route_active,
        })
    return out


def find_overshoot_segments(result, margin_kph=2.0, min_len_s=1.0, field="live_route_speed"):
    """{field}가 vEgo보다 margin_kph 이상 큰(=제약이 무력화된) 구간 탐지.
    replay_route_223_vs_baseline.py와 동일 지표."""
    segs = []
    active = False
    start_i = None
    for i, r in enumerate(result):
        val = r[field]
        over = (val is not None) and (val > r["v_ego_kph"] + margin_kph)
        if over and not active:
            active = True
            start_i = i
        elif not over and active:
            active = False
            length = result[i - 1]["t"] - result[start_i]["t"]
            if length >= min_len_s:
                segs.append((start_i, i - 1, length))
    if active:
        length = result[-1]["t"] - result[start_i]["t"]
        if length >= min_len_s:
            segs.append((start_i, len(result) - 1, length))
    return segs


def summarize_segment(result, s, e, field, label):
    window = result[s:e + 1]
    vals = [r[field] for r in window if r[field] is not None]
    max_excess = max((r[field] - r["v_ego_kph"] for r in window if r[field] is not None), default=0.0)
    print(f"  [{label}] t={result[s]['t']:.1f}~{result[e]['t']:.1f} "
          f"({result[e]['t']-result[s]['t']:.1f}s), "
          f"{field} max={max(vals) if vals else float('nan'):.1f}kph, "
          f"vEgo 초과폭 최대={max_excess:.1f}kph")


def jump_count(result, key, gap_thresh_m=APEX_JUMP_GAP_M):
    """프레임간 apex_dist 낙차(절대값)가 gap_thresh_m를 넘는 '점프' 횟수
    (234차/237차와 동일 flicker 지표 -- stage0(A)->stage1(B) 감소 재확인용)."""
    jumps = 0
    for i in range(1, len(result)):
        a, b = result[i - 1][key], result[i][key]
        if a is not None and b is not None and abs(a - b) > gap_thresh_m:
            jumps += 1
    return jumps


def active_frames(result, key):
    return sum(1 for r in result if r[key] is not None)


def max_frame_drop(result, key):
    max_drop = 0.0
    for i in range(1, len(result)):
        a, b = result[i - 1][key], result[i][key]
        if a is not None and b is not None:
            max_drop = max(max_drop, a - b)
    return max_drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--decel-rate", type=float, default=1.00,
                     help="autoNaviSpeedDecelRate 가정치 m/s^2 (기본 1.00, PARAMS_REGISTRY 218차계속)")
    ap.add_argument("--ctrl-end", type=float, default=7.0,
                     help="autoNaviSpeedCtrlEnd(safe_time) 가정치 초 (기본 7.0)")
    ap.add_argument("--assume-mode-on", action="store_true", default=True)
    ap.add_argument("--no-assume-mode-on", dest="assume_mode_on", action="store_false")
    ap.add_argument("--start-t", type=float, default=None)
    ap.add_argument("--end-t", type=float, default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    if args.start_t is not None:
        rows = [r for r in rows if float(r["t"]) >= args.start_t]
    if args.end_t is not None:
        rows = [r for r in rows if float(r["t"]) <= args.end_t]
    if not rows:
        print("no rows in range", file=sys.stderr)
        sys.exit(1)

    result = replay(rows, args.decel_rate, args.ctrl_end, args.assume_mode_on)

    print(f"=== 총 {len(rows)} rows, t={rows[0]['t']}~{rows[-1]['t']} "
          f"(decel_rate={args.decel_rate}, ctrl_end={args.ctrl_end}, "
          f"assume_mode_on={args.assume_mode_on}) ===\n")

    print("=== [1단계] candidate 레벨 재확인 (237차 checkpoint stage0->stage1 수치와 대조) ===")
    a_active = active_frames(result, "apex_a_idx")
    b_active = active_frames(result, "apex_b_idx")
    a_jumps = jump_count(result, "apex_a_dist")
    b_jumps = jump_count(result, "apex_b_dist")
    print(f"  baseline(A, stage0)  : apex 존재 프레임={a_active}/{len(result)}, "
          f"apex_dist 점프(>{APEX_JUMP_GAP_M:.0f}m)={a_jumps}건")
    print(f"  patched(B, stage0+1) : apex 존재 프레임={b_active}/{len(result)}, "
          f"apex_dist 점프(>{APEX_JUMP_GAP_M:.0f}m)={b_jumps}건")
    print()

    print("=== [2단계] out_speed 시계열 -- vEgo+2kph 초과 유지 구간(overshoot) ===")
    live_segs = find_overshoot_segments(result, field="live_route_speed")
    a_segs = find_overshoot_segments(result, field="out_a_speed")
    b_segs = find_overshoot_segments(result, field="out_b_speed")

    print(f"--- [실측 ground truth, device 현재 코드] liveRouteSpeed: {len(live_segs)}건 ---")
    for (s, e, length) in live_segs:
        summarize_segment(result, s, e, "live_route_speed", "실측")
    print(f"\n--- [baseline(A) 오프라인 재계산] out_a_speed: {len(a_segs)}건 ---")
    for (s, e, length) in a_segs:
        summarize_segment(result, s, e, "out_a_speed", "A=baseline")
    print(f"\n--- [patched(B) 오프라인 재계산] out_b_speed: {len(b_segs)}건 ---")
    for (s, e, length) in b_segs:
        summarize_segment(result, s, e, "out_b_speed", "B=patched(237차)")
    print()

    a_drop = max_frame_drop(result, "out_a_speed")
    b_drop = max_frame_drop(result, "out_b_speed")
    theory_max = args.decel_rate * 3.6 * ROUTE_SPEED_LOOP_DT
    print(f"=== 프레임간 최대낙차(저크 체크, 이론상한={theory_max:.2f} km/h/frame) ===")
    print(f"  A(baseline) 최대낙차 = {a_drop:.2f} km/h")
    print(f"  B(patched)  최대낙차 = {b_drop:.2f} km/h")
    print()

    if b_jumps < a_jumps:
        print(f">>> 판정: apex 점프(flicker) {a_jumps}건 -> {b_jumps}건으로 감소 "
              f"(237차 checkpoint 방향과 일치).")
    elif b_jumps == a_jumps:
        print(">>> 판정: apex 점프 건수 변화 없음 -- 이 구간(범위)에서는 gate 효과 미미.")
    else:
        print(f">>> 판정: apex 점프가 오히려 {a_jumps}건 -> {b_jumps}건으로 증가 -- 추가 조사 필요.")

    if a_drop > theory_max + 0.05 or b_drop > theory_max + 0.05:
        print(">>> 주의: 프레임간 낙차가 이론상한을 초과하는 지점이 있음(A 또는 B) -- "
              "RouteSim223 단순화(한계 3번, ceiling/route_inert 미포함) 영향일 수 있으므로 "
              "실차 적용 전 별도 확인 필요.")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=1)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
