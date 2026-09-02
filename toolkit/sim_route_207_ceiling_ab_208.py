#!/usr/bin/env python3
"""
208차 -- 207차 패치(out_speed 상한(ceiling) 항 apex_speed -> sharpest_candidate_speed
교체) 실차로그 A/B 재검증. 207차 사전검증(sim_route_ceiling_sharpest_candidate_207.py)은
206차 WIP 기록 수치로 재구성한 합성 시나리오였고(NEEDS_VALIDATION), 이번이 199cha
8세그 원본 로그로 하는 첫 실측 재현이다(206차와 동일한 로그/방법론, ceiling 분기만
205차->207차로 교체).

  방식 OLD (205차, 206차가 NEGATIVE로 확인한 버전):
      out_speed = min(raw_col, max(vEgo_kph, apex_speed), 150.0)
  방식 NEW (207차, 현재 코드):
      out_speed = min(raw_col, max(vEgo_kph, sharpest_candidate_speed), 150.0)
      sharpest_candidate_speed = min(speeds[k] for k in candidates) if candidates else apex_speed

apex_dist/apex_speed/raw_col(routeOutSpeed)은 199cha 8세그 CSV에 이미 실측 텔레메트리로
들어있다(193/194차). 그러나 candidates 리스트(도로제한속도 미만인 모든 후보의 speed)는
이 로그에 없다(204차 계측 이전 로그) -- naviPaths 원시 폴리라인 컬럼(147차 계측)에서
carrot_man.py와 동일한 3점 곡률(macro sample=4 + fine sample=1, ROUTE_CURVATURE_FINE_SAMPLE)
계산을 재현해(analysis_helpers.recompute_route_curvature_speed) candidates를 직접
재구성한다.

**알려진 한계(148/161차 기존 한계와 동일)**: nRoadLimitSpeed(실제 도로제한속도)는
CSV에 기록되지 않아 오프라인 재현에서는 고정값 200.0을 가정한다(recompute_route_
curvature_speed의 기본값과 동일 관행). 실제 도로제한이 200보다 낮으면 candidates
집합이 실제보다 넓게(더 보수적으로) 잡힐 수 있다 -- 이 스크립트는 apex_dist/apex_speed
자체는 CSV 실측값을 그대로 쓰고, candidates 재구성에만 이 가정을 적용한다.

CSV 컬럼 요구: t, vEgo, naviPointsActive, routeApexIdx, routeApexDist,
routeApexSpeed, routeOutSpeed, ccPoseValid, positionDtSinceFix, src, desiredSpeed,
naviPaths(--with-navi-paths로 추출 필요)
"""
import csv
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analysis_helpers import parse_navi_paths, recompute_route_curvature_speed

ROUTE_MAX_SPEED_KPH = 150.0
ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH = 15.0
ROUTE_VEGO_BOOST_MAX_MSS = 3.0
ROUTE_POSITION_UNCERTAIN_DT_S = 3.0
AUTO_NAVI_SPEED_DECEL_RATE = 0.70
ASSUMED_ROAD_LIMIT_KPH = 200.0  # 148/161차 기존 오프라인 한계와 동일 가정
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001  # 157차 패치 값(carrot_man.py와 동일)


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


def sharpest_candidate_speed_for_row(navi_paths_str, apex_speed):
    """naviPaths 원시 폴리라인에서 carrot_man.py L839 candidates(=speed <
    도로제한속도인 전체 지점)를 재구성하고 그중 최솟값(sharpest)을 반환.
    파싱 실패/포인트 부족 시 apex_speed로 폴백(179차 폴백 경로와 동일).

    [208차, 실측 중 발견한 재현 아티팩트 보정] naviPaths의 마지막 포인트는
    resample_10m_np()가 실제 경로 길이보다 요청 거리(route_lookahead_m)가
    더 길 때 물리적으로 균등하지 않은 위치로 클램프하는 경우가 있음(라벨
    거리는 정확히 10m 간격이지만 실제 x,y 유클리드 간격은 그렇지 않음--
    t=437.98 실측: 마지막 두 점 간 실제 간격 6.55m인데 y가 -1.22->-5.15로
    급변, 3점 곡률 스텐실이 이를 반경 20m 미만의 급커브로 오판(speed=5.0)).
    이 스크립트는 재현 목적상 마지막 1개 포인트를 드롭하고 재계산해 이
    경계 아티팩트를 제거한다(전체 로그 스캔 결과 실제 유클리드 간격이
    7~13m 범위를 벗어나는 프레임은 7,098개 중 28개/0.4%뿐이나, 문제
    구간에서 24초 이상 연속 재현돼 영향이 누적됨 -- 상세는 WIP.md 208차).
    """
    points, distances = parse_navi_paths(navi_paths_str)
    if len(points) < 4 * 2 + 1 + 1:  # sample*2+1 + 경계 트림 1개
        return apex_speed, 0
    points, distances = points[:-1], distances[:-1]
    entries = recompute_route_curvature_speed(
        points, distances, sample=4, sample_fine=1,
        road_limit_speed=ASSUMED_ROAD_LIMIT_KPH,
        floor_threshold=ROUTE_CURVE_NEGLIGIBLE_THRESHOLD,
    )
    candidates = [spd for (_, _, spd) in entries if spd < ASSUMED_ROAD_LIMIT_KPH]
    if not candidates:
        return apex_speed, 0
    return min(candidates), len(candidates)


class Branch:
    """OLD/NEW 각 갈래가 독립적으로 갖는 상태(_route_speed_prev류)."""
    def __init__(self):
        self.prev = None
        self.apex_speed_prev = None
        self.boost_armed = False
        self.boost_armed_speed = None

    def reset(self):
        self.prev = None
        self.apex_speed_prev = None
        self.boost_armed = False
        self.boost_armed_speed = None

    def step(self, raw_clipped, apex_dist, apex_speed, v_ego_ms,
             cc_pose_valid, position_dt_since_fix):
        out_speed = raw_clipped

        accel_limit_kmh = AUTO_NAVI_SPEED_DECEL_RATE * 3.6
        if self.apex_speed_prev is None:
            pass
        else:
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
    n_candidate_recompute = 0
    for r in rows:
        t = f(r, "t")
        active = r["naviPointsActive"] == "True"
        v_ego_ms = f(r, "vEgo")
        v_ego_kph = v_ego_ms * 3.6
        apex_idx = int(float(r["routeApexIdx"])) if r["routeApexIdx"] not in ("", None) else -1
        apex_dist = f(r, "routeApexDist")
        apex_speed = f(r, "routeApexSpeed")
        raw_col = f(r, "routeOutSpeed", 300.0)
        cc_pose_valid = r.get("ccPoseValid", "") == "True"
        position_dt_since_fix = f(r, "positionDtSinceFix")

        if not active:
            old.reset()
            new.reset()
            out.append(dict(t=t, active=False, apex_idx=apex_idx, apex_dist=apex_dist,
                             apex_speed=apex_speed, v_ego_kph=v_ego_kph, raw_col=raw_col,
                             sharpest=None, n_cand=0, out_old=None, out_new=None))
            continue

        sharpest, n_cand = sharpest_candidate_speed_for_row(r.get("naviPaths", ""), apex_speed)
        n_candidate_recompute += 1

        raw_old = min(raw_col, max(v_ego_kph, apex_speed), ROUTE_MAX_SPEED_KPH)
        raw_new = min(raw_col, max(v_ego_kph, sharpest), ROUTE_MAX_SPEED_KPH)

        out_old = old.step(raw_old, apex_dist, apex_speed, v_ego_ms,
                            cc_pose_valid, position_dt_since_fix)
        out_new = new.step(raw_new, apex_dist, apex_speed, v_ego_ms,
                            cc_pose_valid, position_dt_since_fix)

        out.append(dict(t=t, active=True, apex_idx=apex_idx, apex_dist=apex_dist,
                         apex_speed=apex_speed, v_ego_kph=v_ego_kph, raw_col=raw_col,
                         sharpest=sharpest, n_cand=n_cand, out_old=out_old, out_new=out_new))
    return out, n_candidate_recompute


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/199cha_8seg_route_extracted.csv"
    rows = load_rows(csv_path)
    sim, n_recompute = simulate(rows)
    actual = {round(f(r, "t"), 3): (r["src"], f(r, "desiredSpeed")) for r in rows}

    print(f"총 프레임: {len(rows)}, 활성 프레임: {sum(1 for s in sim if s['active'])}, "
          f"candidates 재계산 프레임: {n_recompute}")
    print()

    print("=== 스파이크/고원 구간 t=418.40~423.30 (OLD=205차 vs NEW=207차) ===")
    print(f"{'t':>8} {'idx':>4} {'dist':>6} {'apexSpd':>8} {'sharp':>7} {'nCand':>5} "
          f"{'vEgo':>6} {'raw':>7} {'OLD':>7} {'NEW':>7}")
    for s in sim:
        if s['active'] and 418.40 <= s['t'] <= 423.30:
            print(f"{s['t']:8.2f} {s['apex_idx']:4d} {s['apex_dist']:6.1f} {s['apex_speed']:8.1f} "
                  f"{s['sharpest']:7.1f} {s['n_cand']:5d} {s['v_ego_kph']:6.1f} {s['raw_col']:7.1f} "
                  f"{s['out_old']:7.1f} {s['out_new']:7.1f}")
    print()

    print("=== 북대전IC 구간 t=450.0~498.0 통계 (실제 apex 도달~통과 구간) ===")
    seg = [s for s in sim if s['active'] and 450.0 <= s['t'] <= 498.0]
    print(f"프레임 수: {len(seg)}")

    def stats(key):
        vals = [s[key] for s in seg]
        return sum(vals) / len(vals), max(vals), min(vals)

    for label, key in [("OLD(205차)", "out_old"), ("NEW(207차 sharpest)", "out_new")]:
        avg, mx, mn = stats(key)
        print(f"{label}: 평균={avg:.1f} 최대={mx:.1f} 최소={mn:.1f}")
    avg_ego, mx_ego, mn_ego = stats("v_ego_kph")
    print(f"실제 vEgo: 평균={avg_ego:.1f} 최대={mx_ego:.1f} 최소={mn_ego:.1f}")
    avg_apex, mx_apex, mn_apex = stats("apex_speed")
    print(f"routeApexSpeed(실제목표): 평균={avg_apex:.1f} 최대={mx_apex:.1f} 최소={mn_apex:.1f}")
    print()

    would_bind_old = would_bind_new = 0
    for s in seg:
        key = round(s['t'], 3)
        if key in actual:
            _, actual_spd = actual[key]
            if s['out_old'] <= actual_spd + 1e-6:
                would_bind_old += 1
            if s['out_new'] <= actual_spd + 1e-6:
                would_bind_new += 1
    n = len(seg)
    print(f"would_bind OLD(205차):        {would_bind_old}/{n} ({100*would_bind_old/n:.1f}%)")
    print(f"would_bind NEW(207차 sharpest): {would_bind_new}/{n} ({100*would_bind_new/n:.1f}%)")
    print()

    apex_arrival = min(seg, key=lambda s: s['apex_dist'] if s['apex_dist'] > 0 else 1e9)
    print(f"=== apex 최근접 프레임(t={apex_arrival['t']:.2f}, dist={apex_arrival['apex_dist']:.1f}) ===")
    print(f"apex_speed(목표)={apex_arrival['apex_speed']:.1f}  vEgo={apex_arrival['v_ego_kph']:.1f}  "
          f"OLD={apex_arrival['out_old']:.1f}  NEW={apex_arrival['out_new']:.1f}")
    print(f"목표 대비 격차: OLD={apex_arrival['out_old']-apex_arrival['apex_speed']:.1f}kph  "
          f"NEW={apex_arrival['out_new']-apex_arrival['apex_speed']:.1f}kph")
    print()

    spike_seg = [s for s in sim if s['active'] and 418.40 <= s['t'] <= 423.30]
    max_old = max(s['out_old'] for s in spike_seg)
    max_new = max(s['out_new'] for s in spike_seg)
    min_sharp = min(s['sharpest'] for s in spike_seg)
    max_ncand = max(s['n_cand'] for s in spike_seg)
    print("=== 스파이크 구간(t=418.40~423.30) 내 OLD/NEW 최댓값 ===")
    print(f"OLD(205차) 최댓값: {max_old:.1f}   NEW(207차) 최댓값: {max_new:.1f}")
    print(f"이 구간 sharpest_candidate_speed 최솟값: {min_sharp:.1f}   "
          f"candidates 개수 최댓값: {max_ncand}")
    print()

    # 전체 로그 스캔: OLD != NEW인 프레임 수 (206차와 동일 형식의 요약)
    diff_frames = [s for s in sim if s['active'] and abs(s['out_old'] - s['out_new']) > 1e-6]
    print(f"=== 전체 로그(활성 {sum(1 for s in sim if s['active'])}프레임) 중 OLD!=NEW 프레임: "
          f"{len(diff_frames)}개 ===")
    if diff_frames:
        biggest = max(diff_frames, key=lambda s: abs(s['out_old'] - s['out_new']))
        print(f"최대 격차 프레임: t={biggest['t']:.2f}  OLD={biggest['out_old']:.1f}  "
              f"NEW={biggest['out_new']:.1f}  (Δ={biggest['out_old']-biggest['out_new']:.1f})")


if __name__ == "__main__":
    main()
