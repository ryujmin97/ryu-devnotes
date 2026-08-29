#!/usr/bin/env python3
"""
133차: 129차/131차 실측 route(306de77a28 seg15) 로그로 132차 램프 리미터
패치를 사후 재검증.

배경: 131차는 navRoute/navInstructionCarrot 채널에 실제 navi 폴리라인
좌표가 없음을 확인했고(count=0), 그래서 합성 GPS 폴리라인으로만
Hypothesis C를 검증했다(sim_route_lookahead_boundary_snap.py). 이
스크립트는 다른 접근을 쓴다: navi 폴리라인 자체는 없지만, **차량이 실제로
주행한 GPS 궤적(gpsLocation 채널, 1Hz)**은 로그에 있다. 이 route는
"교차로 접근 route 사전감속" 시나리오이므로 차량은 사실상 nav route가
안내한 도로/교차로를 그대로 따라 주행했다 -- 즉 실제 주행 GPS 트랙이
navi_points의 매우 좋은 프록시가 된다(131차가 이미 검증에 썼던 "실제
회전 구간 desiredCurvature로 반경 역산"과 같은 논리의 연장).

방법:
1. `extract_log.py` CSV(20Hz: t, vEgo, desiredSpeed, vTurnSpeed, src,
   steeringAngleDeg)와 `extract_gps.py` CSV(1Hz: t, latitude, longitude,
   bearingDeg)를 로드.
2. GPS 포인트 60개(1Hz) 전체를 navi_points로 사용(전체 트랙이 이미
   "미래 경로"까지 포함하므로 현재 위치 이후 구간이 lookahead 윈도우
   역할을 정확히 함).
3. 20Hz 각 시각마다 GPS 트랙에서 position(t)/bearing(t)을 선형보간해
   current_position/heading_deg를 구하고, `carrot_navi_route_core`
   (131차, sim_route_lookahead_boundary_snap.py에서 import)를 그대로
   호출 -> raw_out_speed(unpatched 재현).
4. raw_out_speed에 132차 `RampLimiterState`(실제 patched 코드와 동일
   로직, dt는 실제 로그의 프레임간 간격을 그대로 사용 -- 20Hz지만
   완전히 균일하지 않음)를 적용 -> patched_out_speed.
5. 실측 desiredSpeed(src=='route') 컬럼, 그리고 vTurnSpeed 컬럼과
   나란히 비교 -- "패치가 실제로 이 주행에 있었다면 어떻게 반응했을지"
   + "vturn과의 교차/전환 구간에서 어떻게 상호작용하는지"를 동시에
   확인.

한계:
- 실제 navi 폴리라인이 아니라 차량 실주행 궤적을 대체 사용 -- 완전히
  동일한 lookahead 계산은 아닐 수 있음(차선 중앙 대비 GPS 노이즈,
  실제 route가 다른 차선/경로를 가리켰을 가능성 등). 그래도 131차가
  이미 이 방식(실측 GPS+desiredCurvature)으로 Hypothesis C를 정밀
  매칭했으므로 방법론적으로는 이미 검증된 접근.
- accel_limit(AutoNaviSpeedDecelRate)은 로그에 직접 기록되지 않아
  83차 실측 기본값(0.70 m/s^2)을 그대로 가정(--accel로 override 가능).
- carrot_navi_route_core는 "재구성한 raw out_speed"이지 로그의
  desiredSpeed(route) 원본과 100% 같은 코드경로가 아니므로(실 궤적
  프록시 오차 포함), unpatched 재구성값과 실측 desiredSpeed(route)가
  정확히 일치하지 않을 수 있음 -- 이 스크립트의 핵심 목적은 그 둘의
  일치도 자체가 아니라 "같은 raw 시퀀스에 램프 리미터를 걸었을 때
  vs 안 걸었을 때의 차이"이므로, 재구성된 unpatched를 기준선으로 삼아
  patched와 비교하는 것이 1차 목표.

사용:
  python3 replay_route_boundary_ramp_limiter.py \
      <route.csv> <gps.csv> [--accel 0.70]
"""
import argparse
import bisect
import csv

from sim_route_lookahead_boundary_snap import carrot_navi_route_core
from sim_route_boundary_ramp_limiter import RampLimiterState


def load_route_csv(path):
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    t0 = float(rows[0]['t'])
    out = []
    for row in rows:
        out.append({
            't': float(row['t']) - t0,
            'vEgo_kph': float(row['vEgo']) * 3.6,
            'desiredSpeed': float(row['desiredSpeed']) if row['desiredSpeed'] not in ('', None) else None,
            'vTurnSpeed': float(row['vTurnSpeed']) if row['vTurnSpeed'] not in ('', None) else None,
            'src': row['src'],
            'steer': float(row['steeringAngleDeg']) if row['steeringAngleDeg'] not in ('', None) else None,
        })
    return out, t0


def load_gps_csv(path, t0):
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            rows.append({
                't': float(row['t']) - t0,
                'lon': float(row['longitude']),
                'lat': float(row['latitude']),
                'bearing': float(row['bearingDeg']),
            })
    rows.sort(key=lambda r: r['t'])
    return rows


def interp_gps(gps_rows, t):
    ts = [r['t'] for r in gps_rows]
    if t <= ts[0]:
        return gps_rows[0]['lon'], gps_rows[0]['lat'], gps_rows[0]['bearing'], True
    if t >= ts[-1]:
        return gps_rows[-1]['lon'], gps_rows[-1]['lat'], gps_rows[-1]['bearing'], True
    i = bisect.bisect_right(ts, t) - 1
    t0_, t1_ = gps_rows[i]['t'], gps_rows[i + 1]['t']
    frac = 0.0 if t1_ == t0_ else (t - t0_) / (t1_ - t0_)
    lon = gps_rows[i]['lon'] + frac * (gps_rows[i + 1]['lon'] - gps_rows[i]['lon'])
    lat = gps_rows[i]['lat'] + frac * (gps_rows[i + 1]['lat'] - gps_rows[i]['lat'])
    bearing = gps_rows[i]['bearing'] + frac * (gps_rows[i + 1]['bearing'] - gps_rows[i]['bearing'])
    return lon, lat, bearing, False


def run(route_csv, gps_csv, accel):
    route_rows, t0 = load_route_csv(route_csv)
    gps_rows = load_gps_csv(gps_csv, t0)
    navi_points = [(r['lon'], r['lat']) for r in gps_rows]

    navi_points_start_index = 0
    limiter = RampLimiterState()
    prev_t = None

    print(f"=== 실측 로그 재생 (route={route_csv}, gps n={len(gps_rows)}, accel={accel}) ===")
    print(f"{'t':>7} {'vEgo':>6} {'steer':>7} {'src':>6} {'rec_desSpd':>10} "
          f"{'raw_recon':>9} {'patched':>8} {'vTurn':>7}")

    out_rows = []
    for r in route_rows:
        t = r['t']
        if t < gps_rows[0]['t'] or t > gps_rows[-1]['t']:
            continue
        lon, lat, bearing, clamped = interp_gps(gps_rows, t)
        raw_out, navi_points_start_index, n_speeds, far_dist = carrot_navi_route_core(
            navi_points, navi_points_start_index, (lon, lat), heading_deg=bearing,
            v_ego_kph=r['vEgo_kph'], accel_limit=accel)
        dt = 0.05 if prev_t is None else max(1e-3, t - prev_t)
        patched_out = limiter.apply(raw_out, accel * 3.6, dt)
        prev_t = t
        out_rows.append((t, r, raw_out, patched_out))

    # 급락/전환 구간만 출력: 실측 desiredSpeed 급락 지점(129차: t~4.25, ~28.35, ~43.70)
    # 및 vturn 교차(steer 90도 이상) 전후를 우선 표시
    prev_raw = None
    for (t, r, raw_out, patched_out) in out_rows:
        interesting = (
            (prev_raw is not None and abs(raw_out - prev_raw) > 3.0) or
            (r['steer'] is not None and abs(r['steer']) > 60) or
            any(abs(t - tc) < 0.3 for tc in (4.25, 28.35, 43.70))
        )
        if interesting:
            rec = f"{r['desiredSpeed']:.0f}" if r['desiredSpeed'] is not None else "-"
            vt = f"{r['vTurnSpeed']:.0f}" if r['vTurnSpeed'] is not None else "-"
            print(f"{t:7.2f} {r['vEgo_kph']:6.1f} {r['steer'] if r['steer'] is not None else 0:7.1f} "
                  f"{r['src']:>6} {rec:>10} {raw_out:9.1f} {patched_out:8.1f} {vt:>7}")
        prev_raw = raw_out

    # 요약: 재구성 raw 시퀀스 기준 최대 프레임간 낙차 vs patched
    max_drop_raw, max_drop_raw_t = 0.0, None
    max_drop_patched, max_drop_patched_t = 0.0, None
    prev_raw = prev_patched = None
    for (t, r, raw_out, patched_out) in out_rows:
        if prev_raw is not None:
            d_raw = raw_out - prev_raw
            d_pat = patched_out - prev_patched
            is_sentinel = raw_out >= 299.999 or prev_raw >= 299.999
            if not is_sentinel:
                if -d_raw > max_drop_raw:
                    max_drop_raw, max_drop_raw_t = -d_raw, t
                if -d_pat > max_drop_patched:
                    max_drop_patched, max_drop_patched_t = -d_pat, t
        prev_raw, prev_patched = raw_out, patched_out

    theoretical_max_step = accel * 3.6 * 0.05
    print(f"\n[재구성 unpatched] 최대 프레임간 낙차(300 센티널 제외): "
          f"{max_drop_raw:.2f}kph @ t={max_drop_raw_t}")
    print(f"[patched] 최대 프레임간 낙차(300 센티널 제외): "
          f"{max_drop_patched:.2f}kph @ t={max_drop_patched_t}")
    print(f"이론 상한(accel_limit_kmh*dt, dt~0.05s): {theoretical_max_step:.2f}kph")
    print(f"\n참고: 129차 실측(로그 원본 desiredSpeed 컬럼) 단일프레임 낙차 = "
          f"Δ-25.0(t=4.25), Δ-24.0(t=28.35), Δ-16.0(t=43.70)")

    ok = max_drop_patched <= theoretical_max_step + 1.0  # 실측 프록시 오차 감안 여유
    print("=> PASS: patched 낙차가 이론 상한 부근으로 억제됨" if ok
          else "=> 확인 필요: patched 낙차가 예상보다 큼 -- navi_points 프록시 오차 가능성 점검")
    return out_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('route_csv')
    ap.add_argument('gps_csv')
    ap.add_argument('--accel', type=float, default=0.70,
                     help='AutoNaviSpeedDecelRate 실측 기본값(83차), 로그에 직접 기록 안됨')
    args = ap.parse_args()
    run(args.route_csv, args.gps_csv, args.accel)


if __name__ == '__main__':
    main()
