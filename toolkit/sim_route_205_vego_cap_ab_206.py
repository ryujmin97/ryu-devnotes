#!/usr/bin/env python3
"""
206차 -- 205차 패치(out_speed 상한을 고정 150 -> max(vEgo_kph, apex_speed)와
150 중 min으로 동적화) 검증 시뮬레이션.

202차/203차가 분석한 199차 8세그 문제 로그(북대전IC 진입 26초 전
t=418.42~423.18 apex_idx 슬라이딩 스파이크/고원)를 그대로 재생하되,
raw out_speed 클리핑 단계만 두 방식으로 병렬 계산한다.

  방식 OLD (202차, 205차 이전): out_speed = min(raw_col, 150.0)
  방식 NEW (205차, 현재 코드):  out_speed = min(raw_col, max(vEgo_kph, apex_speed), 150.0)

그 이후 단계(199차 boost, 132/172/173차 비대칭 램프limiter, 162/167차
position-uncertainty 게이트)는 실제 carrot_man.py L933~1038과 동일한
구조로 OLD/NEW 두 갈래에 각각 독립 적용한다(122차 각주와 달리 이번엔 상한
자체가 A/B 갈림길이므로, 하강측 boost도 각 갈래의 out_speed/거리로
독립 재계산 -- apex_dist/apex_speed 자체는 raw 클리핑과 무관하므로 공유).

CSV 컬럼 요구: t, vEgo, naviPointsActive, routeApexIdx, routeApexDist,
routeApexSpeed, routeOutSpeed, ccPoseValid, positionDtSinceFix,
src, desiredSpeed
"""
import csv
import math
import sys

ROUTE_MAX_SPEED_KPH = 150.0
ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH = 15.0
ROUTE_VEGO_BOOST_MAX_MSS = 3.0
ROUTE_POSITION_UNCERTAIN_DT_S = 3.0
AUTO_NAVI_SPEED_DECEL_RATE = 0.70  # 83차 실측 고정값 재사용 (autoNaviSpeedDecelRate)


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

    def step(self, raw_clipped, apex_dist, apex_speed, v_ego_kph, v_ego_ms,
             cc_pose_valid, position_dt_since_fix):
        out_speed = raw_clipped

        # 199차 boost: 하강 상한(accel_limit_kmh) 동적화
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

        # 172/173차 비대칭 램프리미터
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
                             apex_speed=apex_speed, v_ego_kph=v_ego_kph,
                             raw_col=raw_col, out_old=None, out_new=None))
            continue

        raw_old = min(raw_col, ROUTE_MAX_SPEED_KPH)
        raw_new = min(raw_col, max(v_ego_kph, apex_speed), ROUTE_MAX_SPEED_KPH)

        out_old = old.step(raw_old, apex_dist, apex_speed, v_ego_kph, v_ego_ms,
                            cc_pose_valid, position_dt_since_fix)
        out_new = new.step(raw_new, apex_dist, apex_speed, v_ego_kph, v_ego_ms,
                            cc_pose_valid, position_dt_since_fix)

        out.append(dict(t=t, active=True, apex_idx=apex_idx, apex_dist=apex_dist,
                         apex_speed=apex_speed, v_ego_kph=v_ego_kph, raw_col=raw_col,
                         out_old=out_old, out_new=out_new))
    return out


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/199cha_8seg_route_extracted.csv"
    rows = load_rows(csv_path)
    sim = simulate(rows)
    actual = {round(f(r, "t"), 3): (r["src"], f(r, "desiredSpeed")) for r in rows}

    print(f"총 프레임: {len(rows)}, 활성 프레임: {sum(1 for s in sim if s['active'])}")
    print()

    print("=== 스파이크/고원 구간 t=418.40~423.30 (OLD vs NEW) ===")
    print(f"{'t':>8} {'idx':>4} {'dist':>6} {'apexSpd':>8} {'vEgo':>6} {'raw':>7} {'OLD':>7} {'NEW':>7}")
    for s in sim:
        if s['active'] and 418.40 <= s['t'] <= 423.30:
            print(f"{s['t']:8.2f} {s['apex_idx']:4d} {s['apex_dist']:6.1f} {s['apex_speed']:8.1f} "
                  f"{s['v_ego_kph']:6.1f} {s['raw_col']:7.1f} {s['out_old']:7.1f} {s['out_new']:7.1f}")
    print()

    print("=== 북대전IC 구간 t=450.0~498.0 통계 (실제 apex 도달~통과 구간) ===")
    seg = [s for s in sim if s['active'] and 450.0 <= s['t'] <= 498.0]
    print(f"프레임 수: {len(seg)}")

    def stats(key):
        vals = [s[key] for s in seg]
        return sum(vals) / len(vals), max(vals), min(vals)

    for label, key in [("OLD(150고정)", "out_old"), ("NEW(205차 vEgo동적)", "out_new")]:
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
    print(f"would_bind OLD(150고정): {would_bind_old}/{n} ({100*would_bind_old/n:.1f}%)")
    print(f"would_bind NEW(205차):   {would_bind_new}/{n} ({100*would_bind_new/n:.1f}%)")
    print()

    # apex 도달 시점(202차 문서: t=450, apex_dist가 최소가 되는 지점 근방) 값 비교
    apex_arrival = min(seg, key=lambda s: s['apex_dist'] if s['apex_dist'] > 0 else 1e9)
    print(f"=== apex 최근접 프레임(t={apex_arrival['t']:.2f}, dist={apex_arrival['apex_dist']:.1f}) ===")
    print(f"apex_speed(목표)={apex_arrival['apex_speed']:.1f}  vEgo={apex_arrival['v_ego_kph']:.1f}  "
          f"OLD={apex_arrival['out_old']:.1f}  NEW={apex_arrival['out_new']:.1f}")
    print(f"목표 대비 격차: OLD={apex_arrival['out_old']-apex_arrival['apex_speed']:.1f}kph  "
          f"NEW={apex_arrival['out_new']-apex_arrival['apex_speed']:.1f}kph")
    print()

    # 스파이크 구간 최댓값 (raw 클리핑 직후, 램프 이전) 비교
    spike_seg = [s for s in sim if s['active'] and 418.40 <= s['t'] <= 423.30]
    max_old = max(s['out_old'] for s in spike_seg)
    max_new = max(s['out_new'] for s in spike_seg)
    print(f"=== 스파이크 구간(t=418.40~423.30) 내 OLD/NEW 최댓값 ===")
    print(f"OLD 최댓값: {max_old:.1f}   NEW 최댓값: {max_new:.1f}")


if __name__ == "__main__":
    main()
