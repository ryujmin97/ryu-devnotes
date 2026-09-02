#!/usr/bin/env python3
"""
203차 -- hi=math.inf(방식A, 현재) vs hi=vEgo_kph(방식B) A/B 시뮬레이션.

carrot_man.py의 실제 램프 구조(150 cap 이후, 199차 boost 로직 포함)를
그대로 재구현하되, 상승측(hi) 규칙만 A/B 두 갈래로 나눠서 병렬 계산한다.

주의(데이터 한계): extract_log.py는 apex_idx/dist/speed(선택된 apex 1개)만
기록하고, carrot_navi_route() 내부의 전체 candidates 리스트는 텔레메트리에
없다. 따라서 "candidates_empty"는 이 CSV로 직접 관측 불가 -- 이번 8세그
로그에서는 apex_idx가 -1이 되는 프레임이 0건임을 실측 확인함(아래 출력).
대신 "apex_idx가 이전 프레임과 다르고 raw가 road_limit 근접(>=ROAD_LIMIT_PROXY_KPH)"을
스파이크 근사 신호로 사용한다. 이 근사는 202차가 발견한 실제 스파이크
(t=418.42~419.5, idx 0->15->14->13...)를 정확히 잡아내는지 아래에서 검증한다.
"""
import csv
import math
import sys

ROUTE_MAX_SPEED_KPH = 150.0
ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH = 15.0
ROUTE_VEGO_BOOST_MAX_MSS = 3.0
ROAD_LIMIT_PROXY_KPH = 150.0  # raw가 150 cap에 걸릴 정도면 "road_limit 근접"으로 간주


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


def simulate(rows):
    """
    각 프레임에 대해 raw(150 cap 적용), out_A(hi=inf), out_B(hi=vEgo),
    스파이크 근사신호(idx_changed_to_far_highspeed)를 계산해 리스트로 반환.
    두 방식 모두 199차 boost(하강측 accel_limit_kmh 동적화) 로직은 동일하게 공유
    -- 이 로직은 하강측에만 관여하므로 A/B 비교(상승측)와 독립적이다.
    """
    prev_A = None
    prev_B = None
    apex_speed_prev = None
    boost_armed = False
    boost_armed_speed = None
    prev_apex_idx = None
    prev_raw = None

    out = []
    for r in rows:
        t = f(r, "t")
        active = r["naviPointsActive"] == "True"
        v_ego_kph = f(r, "vEgo") * 3.6
        apex_idx = int(float(r["routeApexIdx"])) if r["routeApexIdx"] not in ("", None) else -1
        apex_dist = f(r, "routeApexDist")
        apex_speed = f(r, "routeApexSpeed")
        raw_col = f(r, "routeOutSpeed", 300.0)

        if not active:
            prev_A = None
            prev_B = None
            apex_speed_prev = None
            boost_armed = False
            boost_armed_speed = None
            prev_apex_idx = None
            prev_raw = None
            out.append(dict(t=t, active=False, v_ego_kph=v_ego_kph, apex_idx=apex_idx,
                             apex_dist=apex_dist, apex_speed=apex_speed, raw=None,
                             out_A=None, out_B=None, spike_proxy=False, boost_armed=False))
            continue

        # [202차] 150 상한
        raw = min(raw_col, ROUTE_MAX_SPEED_KPH)

        # [199차 v3] 하강측 부스트(boost) -- A/B 공통
        if apex_speed_prev is None:
            pass
        else:
            apex_delta_kph = apex_speed_prev - apex_speed
            if apex_delta_kph > ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH:
                boost_armed = True
                boost_armed_speed = apex_speed
            elif boost_armed:
                if abs(apex_speed - boost_armed_speed) > ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH:
                    boost_armed = False
                    boost_armed_speed = None
        apex_speed_prev = apex_speed

        accel_limit_kmh = self_base = 0.70 * 3.6  # AutoNaviSpeedDecelRate 실측값(83차) 고정 재사용
        if boost_armed and apex_dist > 0:
            required_decel_mss = (v_ego_kph / 3.6) ** 2 / (2 * max(apex_dist, 1e-3))
            # 목표속도가 v_ego보다 크면 필요감속 없음(음수) -> 0으로 클램프
            v_target_ms = apex_speed / 3.6
            v_ego_ms = v_ego_kph / 3.6
            if v_ego_ms > v_target_ms:
                required_decel_mss = (v_ego_ms ** 2 - v_target_ms ** 2) / (2 * max(apex_dist, 1e-3))
                boosted_mss = min(required_decel_mss, ROUTE_VEGO_BOOST_MAX_MSS)
                accel_limit_kmh = boosted_mss * 3.6

        # 스파이크 근사 신호: apex_idx가 바뀌었고, "150 cap 적용 전" 원시값
        # (raw_col == apex_speed, 197차 설계상 apex 지점 속도가 곧 out_speed)이
        # 급등. cap 이후 값(raw)으로 비교하면 150에서 클리핑돼 점프가
        # 지워지므로 반드시 raw_col(uncapped)로 판정해야 한다.
        idx_changed = (prev_apex_idx is not None and apex_idx != prev_apex_idx)
        raw_jump = (prev_raw is not None and (raw_col - prev_raw) > 20.0)
        spike_proxy = idx_changed and (raw_col >= ROAD_LIMIT_PROXY_KPH) and raw_jump

        # --- 방식 A: hi = math.inf (현재 코드) ---
        if prev_A is None:
            out_A = raw
        else:
            max_step = accel_limit_kmh * ROUTE_SPEED_LOOP_DT
            lo = prev_A - max_step
            hi = math.inf
            out_A = min(max(raw, lo), hi)
        prev_A = out_A

        # --- 방식 B: hi = vEgo_kph (203차 제안) ---
        if prev_B is None:
            out_B = raw
        else:
            max_step = accel_limit_kmh * ROUTE_SPEED_LOOP_DT
            lo = prev_B - max_step
            hi = v_ego_kph
            out_B = min(max(raw, lo), hi)
        prev_B = out_B

        prev_apex_idx = apex_idx
        prev_raw = raw_col

        out.append(dict(t=t, active=True, v_ego_kph=v_ego_kph, apex_idx=apex_idx,
                         apex_dist=apex_dist, apex_speed=apex_speed, raw=raw,
                         out_A=out_A, out_B=out_B, spike_proxy=spike_proxy,
                         boost_armed=boost_armed))
    return out


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/199cha_8seg_route_extracted.csv"
    rows = load_rows(csv_path)
    sim = simulate(rows)

    # actual 로그의 desiredSpeed/src (실측 arbitration 승자) -- would_bind 근사에 사용
    actual = [(f(r, "t"), r["src"], f(r, "desiredSpeed")) for r in rows]

    print(f"총 프레임: {len(rows)}, 활성 프레임: {sum(1 for s in sim if s['active'])}")
    empty_candidates = sum(1 for r in rows if r["naviPointsActive"] == "True" and r["routeApexIdx"] == "-1")
    print(f"활성 상태에서 apex_idx=-1(candidates 구조적 empty) 프레임: {empty_candidates}")
    print()

    # --- 1) t=418.4~419.5 스파이크 구간 ---
    print("=== 스파이크 구간 t=418.40~419.55 (A vs B, spike_proxy) ===")
    print(f"{'t':>8} {'idx':>4} {'dist':>6} {'apexSpd':>8} {'raw':>7} {'out_A':>7} {'out_B':>7} {'spike':>6} {'vEgo':>6}")
    for s in sim:
        if s['active'] and 418.40 <= s['t'] <= 419.55:
            print(f"{s['t']:8.2f} {s['apex_idx']:4d} {s['apex_dist']:6.1f} {s['apex_speed']:8.1f} "
                  f"{s['raw']:7.1f} {s['out_A']:7.1f} {s['out_B']:7.1f} {str(s['spike_proxy']):>6} {s['v_ego_kph']:6.1f}")
    print()

    # --- 2) 북대전IC 구간 t=450~498 통계 ---
    print("=== 북대전IC 구간 t=450.0~498.0 통계 ===")
    seg = [s for s in sim if s['active'] and 450.0 <= s['t'] <= 498.0]
    print(f"프레임 수: {len(seg)}")

    def stats(key):
        vals = [s[key] for s in seg]
        return sum(vals) / len(vals), max(vals), min(vals)

    for label, key in [("out_A", "out_A"), ("out_B", "out_B")]:
        avg, mx, mn = stats(key)
        print(f"{label}: 평균={avg:.1f} 최대={mx:.1f} 최소={mn:.1f}")
    avg_ego, mx_ego, mn_ego = stats("v_ego_kph")
    print(f"실제 vEgo: 평균={avg_ego:.1f} 최대={mx_ego:.1f} 최소={mn_ego:.1f}")
    avg_apex, mx_apex, mn_apex = stats("apex_speed")
    print(f"routeApexSpeed(실제목표): 평균={avg_apex:.1f} 최대={mx_apex:.1f} 최소={mn_apex:.1f}")

    # would_bind: route 후보(out_A/out_B)가 실제 arbitration 승자값(desiredSpeed_actual) 이하이면
    # route가 arbitration에서 이겼을 것으로 근사
    actual_map = {round(t, 3): (src, spd) for t, src, spd in actual}
    would_bind_A = would_bind_B = 0
    for s in seg:
        key = round(s['t'], 3)
        if key in actual_map:
            _, actual_spd = actual_map[key]
            if s['out_A'] <= actual_spd + 1e-6:
                would_bind_A += 1
            if s['out_B'] <= actual_spd + 1e-6:
                would_bind_B += 1
    n = len(seg)
    print(f"would_bind A(hi=inf): {would_bind_A}/{n} ({100*would_bind_A/n:.1f}%)")
    print(f"would_bind B(hi=vEgo): {would_bind_B}/{n} ({100*would_bind_B/n:.1f}%)")
    print()

    # --- 3) spike_proxy 신호가 실제 스파이크를 잡는지 검증 ---
    print("=== spike_proxy 신호 발생 프레임 (전체 8세그) ===")
    spike_frames = [s for s in sim if s['active'] and s['spike_proxy']]
    print(f"발생 횟수: {len(spike_frames)}")
    for s in spike_frames:
        print(f"  t={s['t']:.2f} idx={s['apex_idx']} raw={s['raw']:.1f}")


if __name__ == "__main__":
    main()
