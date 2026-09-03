"""
replay_route_223_vs_baseline.py (224차 예정, 신규)

목적: extract_log.py로 뽑은 "223차 패치 적용 이전" 실측 로그를 프레임(20Hz)
단위로 재생해, 223차 신규 route 상태기계(무상태 감속식 + route_active/
route_release_time, WIP.md 223차 계속4 / sim_route_223_state_machine_step5.py
RouteSim과 동일 로직을 carrot_man.py L840-922 실제 코드에서 그대로 옮김)가
그 실제 상황에서 어떻게 반응했을지 오프라인으로 계산하고, CSV에 이미 기록된
liveRouteSpeed(패치 적용 전 실제 production이 낸 route_speed, 구 램프리미터/
ceiling까지 통과한 실측 ground truth)와 나란히 비교한다.

핵심 전제(158차 replay_route_apex_vs_baseline.py와 다른 점): 223차는 curve
탐색/후보 선정 로직(candidates[0], 179/196차 방식) 자체를 변경하지 않았다
(STEP1 KEEP 확정, carrot_man.py L842-845 주석 참고). 따라서 naviPaths를
재파싱해 apex를 재계산할 필요가 없다 -- 패치 이전 로그에 이미 기록된
routeApexIdx/routeApexDist/routeApexSpeed(193/194차 계측, cereal 발행)를
그대로 새 알고리즘의 입력(apex_dist, apex_speed)으로 재사용할 수 있다.
이는 재현이 아니라 실측 중간값 재사용이므로 148차가 겪은 "미기록 파라미터를
가정치로 대체해야 하는" 신뢰도 문제가 없다.

주의(한계, 반드시 인지):
1. turnSpeedControlMode(mode)는 프레임별로 로그에 기록되지 않는다. 이
   스크립트는 --assume-mode-on(기본 True)일 때 전 구간 mode in [2,3]로
   가정한다. 223차는 mode 0/1에서 즉시 리턴하지만 구코드(221차 이전)는
   mode를 전혀 참조하지 않고 apex를 항상 계산했으므로(STEP1 A항), 로그의
   routeApexIdx!=-1 자체는 mode 상태를 알려주지 않는다. 이 가정이 깨지는
   구간(실제로는 mode 0/1이었는데 이 스크립트가 mode on으로 가정해 개입을
   생성)이 있다면 그 구간의 비교는 무효 -- 사용자가 실제 주행 중 mode를
   변경한 적이 없는 로그(예: route 기능 전용 테스트 드라이브)에서만 전체
   구간 비교가 유효하다.
2. autoNaviSpeedDecelRate/autoNaviSpeedCtrlEnd(safe_time)는 디바이스 Params
   값이라 로그에 없다 -- --decel-rate(기본 1.00, PARAMS_REGISTRY.md 218차
   계속 실측 현재값)/--ctrl-end(기본 7.0, WIP.md 222차 시점 "7->10 미결"
   상태이므로 원래값 7 사용) CLI 인자로 받는다. 실제 로그 캡처 시점 값과
   다르면 사용자가 맞춰서 지정할 것.
3. routeApexIdx==-1은 "이 프레임 candidates 없음(직선) 또는 리샘플 포인트
   부족"을 뜻하는데 old/new 코드 둘 다 이 두 경우를 구분하지 않고 동일하게
   처리(candidates_empty로 취급)하므로 이 스크립트도 구분하지 않는다.

절대값보다는 "패치 전 vEgo를 크게 초과 유지하던 구간(222차 실측 버그)에서
패치 후 알고리즘이 vEgo를 넘지 않는가"라는 구조적 판정에 우선 쓸 것.

입력: extract_log.py 출력 CSV (t, vEgo, liveRouteSpeed, routeApexIdx,
      routeApexDist, routeApexSpeed 컬럼 필수 -- naviPaths 불필요)
출력: stdout 요약(vEgo 초과 구간 탐지 -- 패치전/후 대조) + --json 프레임별 덤프

사용:
  python3 replay_route_223_vs_baseline.py <route.csv> \\
      [--decel-rate 1.00] [--ctrl-end 7.0] [--assume-mode-on] \\
      [--start-t T0] [--end-t T1] [--json out.json]
"""
import argparse
import csv
import json
import sys

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_REACHED_DIST_M = 10.0
ROUTE_RELEASE_HOLD_S = 2.0


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class RouteSim223:
    """carrot_man.py::carrot_navi_route() L840-922의 223차 상태기계를
    그대로 옮긴 것 -- monotonic 시계 대신 로그의 t(초)를 그대로 사용."""

    def __init__(self, decel_rate_mss, ctrl_end_s, assume_mode_on=True):
        self.route_active = False
        self.route_release_time = None
        self.decel_rate_mss = decel_rate_mss
        self.ctrl_end_s = ctrl_end_s
        self.assume_mode_on = assume_mode_on

    def step(self, t, v_ego_kph, apex_idx, apex_dist, apex_speed_kph):
        route_enabled = self.assume_mode_on  # 한계 1번 참고
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
    sim = RouteSim223(decel_rate_mss, ctrl_end_s, assume_mode_on)
    out = []
    for row in rows:
        t = float(row["t"])
        v_ego_kph = float(row["vEgo"]) * 3.6
        apex_idx_raw = row.get("routeApexIdx", "-1")
        apex_idx = int(float(apex_idx_raw)) if apex_idx_raw not in ("", None) else -1
        apex_dist = float(row.get("routeApexDist", 0.0) or 0.0)
        apex_speed = float(row.get("routeApexSpeed", 0.0) or 0.0)
        live = float(row.get("liveRouteSpeed", "nan") or "nan")

        new_out = sim.step(t, v_ego_kph, apex_idx, apex_dist, apex_speed)
        out.append({
            "t": t, "v_ego_kph": v_ego_kph,
            "apex_idx": apex_idx, "apex_dist": apex_dist, "apex_speed": apex_speed,
            "live_route_speed": live,
            "new_out_speed": new_out,
            "route_active": sim.route_active,
        })
    return out


def find_overshoot_segments(result, margin_kph=2.0, min_len_s=1.0, field="live_route_speed"):
    """{field}가 vEgo보다 margin_kph 이상 큰(=제약이 무력화된) 구간 탐지.
    222차가 실측한 정지->재출발 전이구간 버그와 동일 지표."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--decel-rate", type=float, default=1.00,
                     help="autoNaviSpeedDecelRate 실측값 m/s^2 (기본 1.00, PARAMS_REGISTRY 218차계속)")
    ap.add_argument("--ctrl-end", type=float, default=7.0,
                     help="autoNaviSpeedCtrlEnd(safe_time) 초 (기본 7.0, 222차 시점 원래값)")
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

    old_segs = find_overshoot_segments(result, field="live_route_speed")
    new_segs = find_overshoot_segments(result, field="new_out_speed")

    print(f"=== [패치 전 실측] liveRouteSpeed가 vEgo+2kph 초과 유지 구간: {len(old_segs)}건 ===")
    for (s, e, length) in old_segs:
        summarize_segment(result, s, e, "live_route_speed", "구코드 실측")
    print()

    print(f"=== [223차 오프라인 재계산] new_out_speed가 vEgo+2kph 초과 유지 구간: {len(new_segs)}건 ===")
    for (s, e, length) in new_segs:
        summarize_segment(result, s, e, "new_out_speed", "223차 재계산")
    print()

    if old_segs and not new_segs:
        print(">>> 판정: 222차가 실측한 vEgo 초과 구간이 223차 재계산에서는 재현되지 않음 "
              "(버그 해소 시사, 단 위 한계 1/2/3 인지 필요).")
    elif old_segs and new_segs:
        print(">>> 판정: 223차 재계산에서도 vEgo 초과 구간이 남아 있음 -- 추가 조사 필요.")
    else:
        print(">>> 판정: 이 구간(들)에는 패치 전 vEgo 초과 구간 자체가 없음(비교 대상 없음).")

    # 프레임간 최대 낙차(저크 체크) -- new_out_speed 기준
    max_drop = 0.0
    for i in range(1, len(result)):
        a, b = result[i - 1]["new_out_speed"], result[i]["new_out_speed"]
        if a is not None and b is not None:
            max_drop = max(max_drop, a - b)
    print(f"\n=== 223차 재계산 프레임간 최대 낙차: {max_drop:.2f} km/h "
          f"(이론상한={args.decel_rate*3.6*ROUTE_SPEED_LOOP_DT:.2f} km/h/frame) ===")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=1)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
