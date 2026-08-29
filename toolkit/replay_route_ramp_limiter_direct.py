#!/usr/bin/env python3
"""
133차: 132차 램프 리미터 패치를 실측 desiredSpeed(route) 원본 시계열에
직접 사후 적용(post-hoc)하는 가장 신뢰도 높은 검증.

replay_route_boundary_ramp_limiter.py(같은 세션, GPS 프록시로 
carrot_navi_route_core를 재구성)와의 차이: 그 스크립트는 navi_points를
차량 실주행 GPS 트랙으로 근사해서 "왜"(어떤 메커니즘으로) 급락이
발생하는지까지 재현하려 했으나, 그 근사 자체의 오차(GPS 1Hz 프록시가
실제 navi 폴리라인과 다를 수 있음, lookahead 윈도우가 특정 시점에
route 끝에 도달 못하는 등)로 129차가 보고한 3건의 급락 중 일부는
재현되지 않았다(1차 t=4.25 미재현).

이 스크립트는 그런 "왜"를 따지지 않는다 -- 132차 패치는 원인이 무엇이든
(Hypothesis C 윈도우 경계 스냅이든, 91차 margin_kph 스케줄이든, 다른
무엇이든) `carrot_navi_route()`가 반환하는 **최종 out_speed 값**에만
사후로 프레임간 상한을 거는 구조다. 따라서 로그에 실제로 기록된
desiredSpeed(src=='route') 원본 시계열을 그대로 raw_out_speed 시퀀스로
간주하고 `RampLimiterState`를 순서대로 통과시키면, "이 패치가 실제
이 주행 중에 있었다면 desiredSpeed(route)가 정확히 어떻게 나왔을지"를
어떤 재구성/근사 오차도 없이(로직 자체는 실제 패치 코드와 동일 함수)
직접 답할 수 있다.

주의: desiredSpeed 컬럼은 src와 무관하게 매 프레임 기록되지만, 실제
carrot_navi_route()는 src=='route'일 때만 그 값이 route 계산 결과다.
src가 vturn/gas 등으로 바뀌면 desiredSpeed는 다른 소스의 값을 반영하므로
리미터를 그 프레임까지 이어서 적용하면 안 된다(route가 아닌 값에
route용 램프를 걸면 의미 없음). 이 스크립트는 **src=='route'인 프레임만
추려서** 그 부분수열에만 리미터를 적용한다(연속된 route 구간 내에서는
직전 route 프레임과의 실제 시간간격 dt를 그대로 사용, route 구간이
끊겼다 다시 시작하면 리미터 상태를 리셋 -- 실제 코드도 route 비활성/
재활성 시 리셋되는 것과 동일 원칙, WIP.md 132차 참고).

사용:
  python3 replay_route_ramp_limiter_direct.py <route.csv> [--accel 0.70]
"""
import argparse
import csv

from sim_route_boundary_ramp_limiter import RampLimiterState


def run(route_csv, accel):
    rows = []
    with open(route_csv) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    t0 = float(rows[0]['t'])

    accel_limit_kmh = accel * 3.6
    limiter = RampLimiterState()
    prev_t_in_route_run = None

    out = []
    for row in rows:
        t = float(row['t']) - t0
        src = row['src']
        ds = row['desiredSpeed']
        ds = float(ds) if ds not in ('', None) else None
        vturn = row['vTurnSpeed']
        vturn = float(vturn) if vturn not in ('', None) else None
        steer = row['steeringAngleDeg']
        steer = float(steer) if steer not in ('', None) else None
        vego_kph = float(row['vEgo']) * 3.6

        if src == 'route' and ds is not None:
            if prev_t_in_route_run is None:
                dt = 0.05
            else:
                dt = max(1e-3, t - prev_t_in_route_run)
            patched = limiter.apply(ds, accel_limit_kmh, dt)
            prev_t_in_route_run = t
        else:
            # route가 아닌 프레임: 리미터 상태 리셋(다음 route 재진입 시
            # 첫 프레임은 즉시 통과) -- 132차 패치의 "route 비활성 시
            # prev_out=None 리셋"과 동일 원칙.
            limiter.prev_out = None
            prev_t_in_route_run = None
            patched = ds

        out.append({'t': t, 'src': src, 'vego_kph': vego_kph, 'steer': steer,
                     'recorded_desSpd': ds, 'patched_desSpd': patched, 'vTurn': vturn})

    print(f"=== 실측 desiredSpeed(route) 원본에 132차 램프 리미터 직접 사후적용 "
          f"(route={route_csv}, accel={accel}) ===")
    print(f"{'t':>7} {'vEgo':>6} {'steer':>7} {'src':>6} "
          f"{'recorded':>8} {'patched':>8} {'d(rec)':>7} {'d(pat)':>7} {'vTurn':>7}")

    prev_rec = prev_pat = None
    prev_t_for_rate = None
    max_drop_rec, max_drop_rec_t = 0.0, None
    max_drop_pat, max_drop_pat_t = 0.0, None
    # [133차] 실제 로그는 dt가 정확히 0.05s로 균일하지 않다(프레임 드랍 등으로
    # 0.02~0.08s 폭 존재 확인됨) -- 고정 dt 가정 대신 프레임별 실제 dt로
    # "낙차율(kph/s)"을 계산해 accel_limit_kmh(초당 물리 상한) 자체와 비교한다.
    max_rate_pat, max_rate_pat_t = 0.0, None
    for r in out:
        d_rec_str = d_pat_str = ""
        # [133차] route가 비활성이었다가 재진입하는 첫 프레임(prev_rec is None)은
        # 리미터가 설계상 즉시 통과(reset)시키는 경계 -- 132차 패치 자체의 정상
        # 동작이지 "프레임간 낙차 위반"이 아니므로 지표 집계에서 제외한다
        # (다른 검증 스크립트의 300 센티널 제외와 동일 원칙).
        if r['src'] == 'route' and r['recorded_desSpd'] is not None and prev_rec is not None:
            d_rec = r['recorded_desSpd'] - prev_rec
            d_pat = r['patched_desSpd'] - prev_pat
            d_rec_str, d_pat_str = f"{d_rec:+.1f}", f"{d_pat:+.1f}"
            if -d_rec > max_drop_rec:
                max_drop_rec, max_drop_rec_t = -d_rec, r['t']
            if -d_pat > max_drop_pat:
                max_drop_pat, max_drop_pat_t = -d_pat, r['t']
            dt_actual = max(1e-3, r['t'] - prev_t_for_rate) if prev_t_for_rate is not None else 0.05
            rate_pat = -d_pat / dt_actual
            if rate_pat > max_rate_pat:
                max_rate_pat, max_rate_pat_t = rate_pat, r['t']
        if r['src'] == 'route' and r['recorded_desSpd'] is not None:
            prev_t_for_rate = r['t']
        else:
            prev_t_for_rate = None
        interesting = (
            (d_rec_str and abs(float(d_rec_str)) > 3.0) or
            (r['steer'] is not None and abs(r['steer']) > 60) or
            any(abs(r['t'] - tc) < 0.35 for tc in (4.25, 28.35, 43.70))
        )
        if interesting:
            rec_s = f"{r['recorded_desSpd']:.0f}" if r['recorded_desSpd'] is not None else "-"
            pat_s = f"{r['patched_desSpd']:.0f}" if r['patched_desSpd'] is not None else "-"
            vt_s = f"{r['vTurn']:.0f}" if r['vTurn'] is not None else "-"
            steer_s = f"{r['steer']:.1f}" if r['steer'] is not None else "-"
            reset_mark = " <-route재진입(리셋)" if (r['src'] == 'route' and prev_rec is None) else ""
            print(f"{r['t']:7.2f} {r['vego_kph']:6.1f} {steer_s:>7} {r['src']:>6} "
                  f"{rec_s:>8} {pat_s:>8} {d_rec_str:>7} {d_pat_str:>7} {vt_s:>7}{reset_mark}")
        if r['src'] == 'route' and r['recorded_desSpd'] is not None:
            prev_rec, prev_pat = r['recorded_desSpd'], r['patched_desSpd']
        else:
            prev_rec = prev_pat = None

    theoretical_max_step_nominal = accel_limit_kmh * 0.05
    print(f"\n[recorded 원본] 최대 프레임간 낙차: {max_drop_rec:.2f}kph @ t={max_drop_rec_t}")
    print(f"[patched]        최대 프레임간 낙차: {max_drop_pat:.2f}kph @ t={max_drop_pat_t} "
          f"(참고: 명목 20Hz 기준 상한 {theoretical_max_step_nominal:.2f}kph -- 실제 로그는 "
          f"dt가 정확히 0.05s로 균일하지 않아 이 값을 그대로 넘을 수 있음, 아래 낙차율로 재판정)")
    print(f"[patched] 최대 낙차율(kph/s, 프레임별 실제 dt 기준): {max_rate_pat:.3f} @ t={max_rate_pat_t}")
    print(f"물리 상한(accel_limit_kmh, 초당): {accel_limit_kmh:.2f}kph/s")
    ok = max_rate_pat <= accel_limit_kmh + 1e-3
    print("=> PASS: 실측 원본 시계열 기준으로도 patched 낙차율이 accel_limit_kmh 이내로 억제됨"
          if ok else "=> FAIL: 낙차율이 accel_limit_kmh 초과 -- 로직 재검토 필요")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('route_csv')
    ap.add_argument('--accel', type=float, default=0.70)
    args = ap.parse_args()
    run(args.route_csv, args.accel)


if __name__ == '__main__':
    main()
