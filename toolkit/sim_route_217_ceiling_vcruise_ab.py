#!/usr/bin/env python3
"""
217차 -- out_speed ceiling 상수항(ROUTE_MAX_SPEED_KPH=150 고정) -> min(vCruise,150)
전환(217-2)의 실차로그 A/B 재검증.

215차 18세그 CSV(commit 4514e97, 214차 B안 HEAD에서 추출)를 그대로 사용한다.
이 로그엔 204차 candidate telemetry가 없으므로(위 커밋 시점엔 CSV 컬럼에
routeCandidate0~2가 없음) naviPaths 원시 폴리라인에서 208차와 동일한 방식으로
candidates(거리,speed)를 재구성하고, 214차 B안(calculate_current_speed 재사용,
거리인지화)으로 sharpest_candidate_speed를 계산한다 -- 이 부분은 217차가
건드리지 않은 항이므로 OLD/NEW 양쪽에 동일하게 적용해 ceiling 상수항 교체
효과만 분리한다.

  OLD (로그 실제 촬영 당시 코드, 211~214차):
      ceiling_const = ROUTE_MAX_SPEED_KPH = 150.0
  NEW (217차):
      ceiling_const = min(vCruise, 150.0) if vCruise > 0 else 150.0

out_speed = min(raw_col, max(vEgo_kph, sharpest_B), ceiling_const)
이후 172/173차 비대칭 램프(하강만 제한, 상승 무제한)를 OLD/NEW 동일 로직으로
독립 적용(각자 별도 _route_speed_prev 상태 보유).

raw_col(routeOutSpeed)/apex_dist/apex_speed는 CSV 실측 텔레메트리를 그대로
사용(라인 880-891, apex 단독 물리계산 -- ceiling/ramp 이전 값이라 217차와 무관).

**한계**: nRoadLimitSpeed 미기록으로 오프라인 재현은 200.0 고정 가정
(148/161/207/208차 기존 관행과 동일). OLD 브랜치가 recorded liveRouteSpeed와
얼마나 일치하는지를 sanity check로 함께 출력(재구성 오차 규모 확인용).

CSV 컬럼 요구: t, vEgo, vCruise, naviPointsActive, routeApexIdx, routeApexDist,
routeApexSpeed, routeOutSpeed, ccPoseValid, positionDtSinceFix, liveRouteSpeed,
naviPaths(--with-navi-paths로 추출 필요)
"""
import csv
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/claude/ryu-devnotes/toolkit")
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

ROUTE_MAX_SPEED_KPH = 150.0
ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH = 15.0
ROUTE_VEGO_BOOST_MAX_MSS = 3.0
ROUTE_POSITION_UNCERTAIN_DT_S = 3.0
AUTO_NAVI_SPEED_DECEL_RATE = 0.70
AUTO_NAVI_SPEED_CTRL_END = 7.0
ASSUMED_ROAD_LIMIT_KPH = 200.0
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001


def load_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def f(row, key, default=0.0):
    v = row.get(key, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def calculate_current_speed(left_dist, safe_speed_kph, safe_time, safe_decel_rate):
    safe_speed = safe_speed_kph / 3.6
    safe_dist = safe_speed * safe_time
    decel_dist = left_dist - safe_dist
    if decel_dist <= 0:
        return safe_speed_kph
    temp = safe_speed ** 2 + 2 * safe_decel_rate * decel_dist
    speed_mps = math.sqrt(temp) if temp >= 0 else safe_speed
    return max(safe_speed_kph, min(250, speed_mps * 3.6))


def sharpest_candidate_speed_B_for_row(navi_paths_str, apex_speed):
    """214차 B안 재구성: naviPaths -> candidates(dist,speed) -> 각각
    calculate_current_speed() 적용 후 min. 208차 sharpest_candidate_speed_for_row와
    동일한 파싱/트림/가정을 쓰되, 거리도 함께 반환한다(B안은 거리가 필요)."""
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < 4 * 2 + 1 + 1:
        return apex_speed, 0
    points, distances = points[:-1], distances[:-1]
    entries = recompute_route_curvature_speed(
        points, distances, sample=4, sample_fine=1,
        road_limit_speed=ASSUMED_ROAD_LIMIT_KPH,
        floor_threshold=ROUTE_CURVE_NEGLIGIBLE_THRESHOLD,
    )
    candidates = [(dist, spd) for (dist, _, spd) in entries if spd < ASSUMED_ROAD_LIMIT_KPH]
    if not candidates:
        return apex_speed, 0
    sharpest_B = min(
        calculate_current_speed(dist, spd, AUTO_NAVI_SPEED_CTRL_END, AUTO_NAVI_SPEED_DECEL_RATE)
        for (dist, spd) in candidates
    )
    return sharpest_B, len(candidates)


class Branch:
    def __init__(self):
        self.prev = None
        self.apex_speed_prev = None
        self.boost_armed = False
        self.boost_armed_speed = None

    def reset(self):
        self.__init__()

    def step(self, raw_clipped, apex_dist, apex_speed, v_ego_ms,
              cc_pose_valid, position_dt_since_fix):
        out_speed = raw_clipped
        accel_limit_kmh = AUTO_NAVI_SPEED_DECEL_RATE * 3.6
        if self.apex_speed_prev is not None:
            apex_delta_kph = self.apex_speed_prev - apex_speed
            if apex_delta_kph > ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH:
                self.boost_armed = True
                self.boost_armed_speed = apex_speed
            elif self.boost_armed:
                if abs(apex_speed - self.boost_armed_speed) > ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH:
                    self.boost_armed = False
                    self.boost_armed_speed = None
        self.apex_speed_prev = apex_speed

        if self.boost_armed and apex_dist > 0:
            v_target_ms = apex_speed / 3.6
            if v_ego_ms > v_target_ms:
                required_decel_mss = (v_ego_ms ** 2 - v_target_ms ** 2) / (2.0 * apex_dist)
                if required_decel_mss > AUTO_NAVI_SPEED_DECEL_RATE:
                    boosted_mss = min(required_decel_mss, ROUTE_VEGO_BOOST_MAX_MSS)
                    accel_limit_kmh = boosted_mss * 3.6

        if self.prev is not None:
            max_step_kmh = accel_limit_kmh * ROUTE_SPEED_LOOP_DT
            lo = self.prev - max_step_kmh
            hi = math.inf
            if (position_dt_since_fix > ROUTE_POSITION_UNCERTAIN_DT_S
                    and not cc_pose_valid):
                hi = self.prev
            out_speed = min(max(out_speed, lo), hi)
        self.prev = out_speed
        return out_speed


def simulate(rows):
    old = Branch()
    new = Branch()
    out = []
    for r in rows:
        t = f(r, "t")
        active = r["naviPointsActive"] == "True"
        v_ego_ms = f(r, "vEgo")
        v_ego_kph = v_ego_ms * 3.6
        v_cruise_kph = f(r, "vCruise")
        apex_idx = int(float(r["routeApexIdx"])) if r["routeApexIdx"] not in ("", None) else -1
        apex_dist = f(r, "routeApexDist")
        apex_speed = f(r, "routeApexSpeed")
        raw_col = f(r, "routeOutSpeed", 300.0)
        live_actual = f(r, "liveRouteSpeed", -1.0)
        cc_pose_valid = r.get("ccPoseValid", "") == "True"
        position_dt_since_fix = f(r, "positionDtSinceFix")

        if not active:
            old.reset()
            new.reset()
            out.append(dict(t=t, active=False, apex_idx=apex_idx, apex_dist=apex_dist,
                             apex_speed=apex_speed, v_ego_kph=v_ego_kph, v_cruise_kph=v_cruise_kph,
                             raw_col=raw_col, sharpest=None, n_cand=0,
                             out_old=None, out_new=None, live_actual=live_actual))
            continue

        sharpest_B, n_cand = sharpest_candidate_speed_B_for_row(r.get("naviPaths", ""), apex_speed)

        old_ceiling_const = ROUTE_MAX_SPEED_KPH
        new_ceiling_const = min(v_cruise_kph, ROUTE_MAX_SPEED_KPH) if v_cruise_kph > 0 else ROUTE_MAX_SPEED_KPH

        raw_old = min(raw_col, max(v_ego_kph, sharpest_B), old_ceiling_const)
        raw_new = min(raw_col, max(v_ego_kph, sharpest_B), new_ceiling_const)

        out_old = old.step(raw_old, apex_dist, apex_speed, v_ego_ms, cc_pose_valid, position_dt_since_fix)
        out_new = new.step(raw_new, apex_dist, apex_speed, v_ego_ms, cc_pose_valid, position_dt_since_fix)

        out.append(dict(t=t, active=True, apex_idx=apex_idx, apex_dist=apex_dist,
                         apex_speed=apex_speed, v_ego_kph=v_ego_kph, v_cruise_kph=v_cruise_kph,
                         raw_col=raw_col, sharpest=sharpest_B, n_cand=n_cand,
                         out_old=out_old, out_new=out_new, live_actual=live_actual))
    return out


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/x18seg_215cha_route.csv"
    rows = load_rows(csv_path)
    sim = simulate(rows)
    active = [s for s in sim if s['active']]
    print(f"총 프레임: {len(rows)}, 활성 프레임: {len(active)}")
    print()

    # 0) sanity check: OLD 재구성이 실제 recorded liveRouteSpeed와 얼마나 일치하는지
    diffs = [abs(s['out_old'] - s['live_actual']) for s in active if s['live_actual'] >= 0]
    diffs.sort()
    n = len(diffs)
    print("=== sanity check: OLD(재구성) vs 실제 liveRouteSpeed(recorded) ===")
    print(f"n={n}  median|diff|={diffs[n//2]:.2f}  p90|diff|={diffs[int(n*0.9)]:.2f}  max|diff|={diffs[-1]:.2f}")
    print()

    # 1) t=375.5 부근(WIP 217차가 지목한 vCruise=55 고정 스파이크 구간) 상세
    print("=== t=370.0~385.0 상세 (150 클램프 스파이크로 지목된 구간) ===")
    print(f"{'t':>8} {'vCru':>5} {'idx':>4} {'apexD':>6} {'apexS':>6} {'sharp':>6} "
          f"{'vEgo':>6} {'raw':>7} {'OLD':>7} {'NEW':>7} {'actual':>7}")
    for s in active:
        if 370.0 <= s['t'] <= 385.0:
            print(f"{s['t']:8.2f} {s['v_cruise_kph']:5.1f} {s['apex_idx']:4d} {s['apex_dist']:6.1f} "
                  f"{s['apex_speed']:6.1f} {s['sharpest']:6.1f} {s['v_ego_kph']:6.1f} {s['raw_col']:7.1f} "
                  f"{s['out_old']:7.1f} {s['out_new']:7.1f} {s['live_actual']:7.1f}")
    print()

    # 2) 전체 로그: OLD가 150 근접(>=145) 클램프된 프레임 수, 그 프레임들에서 NEW는 얼마나 낮아지는지
    clamp_frames = [s for s in active if s['out_old'] >= 145.0]
    print(f"=== 전체 활성 {len(active)}프레임 중 OLD>=145(150 클램프 근접) 프레임: {len(clamp_frames)}개 ===")
    if clamp_frames:
        deltas = [s['out_old'] - s['out_new'] for s in clamp_frames]
        print(f"이 프레임들에서 NEW가 낮춘 폭: 평균={sum(deltas)/len(deltas):.1f}kph "
              f"최대={max(deltas):.1f}kph 최소={min(deltas):.1f}kph")
        vcru_at_clamp = [s['v_cruise_kph'] for s in clamp_frames]
        print(f"이 프레임들의 vCruise: 평균={sum(vcru_at_clamp)/len(vcru_at_clamp):.1f} "
              f"최대={max(vcru_at_clamp):.1f} 최소={min(vcru_at_clamp):.1f}")
    print()

    # 3) 램프 하강 구간 길이 비교: OLD/NEW 각각 150(or vCruise) 근접에서 실제 목표(apex_speed)까지
    #    내려오는 데 걸린 시간(연속 클램프 구간 단위)
    print("=== 150 스파이크 -> 정상수렴까지 걸린 시간(연속 클램프 에피소드별) ===")
    episodes = []
    cur = None
    for s in active:
        clamped = s['out_old'] >= 145.0
        if clamped and cur is None:
            cur = {'t0': s['t'], 't1': s['t']}
        elif clamped:
            cur['t1'] = s['t']
        elif cur is not None:
            episodes.append(cur)
            cur = None
    if cur is not None:
        episodes.append(cur)
    for e in episodes:
        dur = e['t1'] - e['t0']
        print(f"  t={e['t0']:.2f}~{e['t1']:.2f} (연속 {dur:.2f}s)")
    print(f"에피소드 수: {len(episodes)}")
    print()

    # 4) 전체 스캔: OLD != NEW 프레임 수/비율
    diff_frames = [s for s in active if abs(s['out_old'] - s['out_new']) > 1e-6]
    print(f"=== 전체 활성 {len(active)}프레임 중 OLD!=NEW 프레임: {len(diff_frames)}개 "
          f"({100*len(diff_frames)/len(active):.1f}%) ===")
    if diff_frames:
        biggest = max(diff_frames, key=lambda s: abs(s['out_old'] - s['out_new']))
        print(f"최대 격차 프레임: t={biggest['t']:.2f}  vCruise={biggest['v_cruise_kph']:.1f}  "
              f"OLD={biggest['out_old']:.1f}  NEW={biggest['out_new']:.1f}  "
              f"(Δ={biggest['out_old']-biggest['out_new']:.1f})")
    avg_old = sum(s['out_old'] for s in active) / len(active)
    avg_new = sum(s['out_new'] for s in active) / len(active)
    print(f"전체 평균: OLD={avg_old:.1f}  NEW={avg_new:.1f}")


if __name__ == "__main__":
    main()
