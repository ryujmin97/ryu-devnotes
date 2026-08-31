#!/usr/bin/env python3
"""
132차(예정): 131차 Hypothesis C(윈도우 경계 진입 시 curvature 배열에
이산적으로 급커브가 출현 -> 역방향 DP가 그 프레임에 즉시 전체 재계산)에
대한 패치 후보 사전검증.

패치 아이디어: carrot_navi_route()의 최종 반환값 out_speed(=out_speeds[0])에
"물리적으로 이미 보장돼야 하는" 프레임간(20Hz, dt=0.05s) 변화 상한을 건다.
상한값은 accel_limit_kmh * dt -- 이미 사용자가 설정한 AutoNaviSpeedDecelRate
그대로 재사용(새 튜닝 상수 불필요). route_lookahead_m 자체가 "이 감속률로
정지/감속하기에 충분한 거리"를 목표로 동적 산정되므로(84차/85차), 이 리미터는
새로운 제약을 추가하는 게 아니라 "윈도우 경계 스냅이 없었다면 원래
성립했어야 할 불변식(프레임당 변화 <= accel_limit_kmh*dt)"을 최종 출력
지점에서 강제로 복원하는 것에 가깝다.

방향(증감) 모두 대칭 적용 -- 129차/131차가 보고한 "회전 종료 즉시 원복 스냅"
(원복측 계단)도 동일 메커니즘이므로 함께 완화된다.

리셋 규칙(중요, 안전 우선):
  - 경로 비활성/최초 활성화(prev_out=None): 리미터 미적용, 즉시 통과.
  - "제약 없음"(out_speed==300, 커브 데이터 없음/윈도우 내 포인트 부족):
    이 방향은 "제약 해제"(=허용 속도가 올라가는 안전한 방향)이므로 즉시
    통과시키고 상태를 리셋한다 -- 실제 제약이 있을 때만 램프를 걸어야
    커브 진입 직전 하드 브레이크 상황에서 "제약 완화인데 계속 낮게 묶여
    있는" 역설적 위험을 피할 수 있다.

이 스크립트는 sim_route_lookahead_boundary_snap.py의 순수함수를 그대로
재사용(carrot_navi_route_core)하고, 그 위에 패치 로직만 얇게 얹어
patched/unpatched를 나란히 비교한다. ryu 코드 자체는 아직 미수정 --
이 스크립트로 먼저 사전검증 후 실제 patch 파일을 작성한다.

사용:
  python3 sim_route_boundary_ramp_limiter.py --v-ego-kph 74 --curve-radius-m 17.3 --accel 0.70
  (반경 17.3m = 131차 정밀매칭에 쓰인 129차 실제 교차로 역산값)
"""
import argparse

from sim_route_lookahead_boundary_snap import (
    carrot_navi_route_core,
    compute_route_lookahead_distance,
    build_synthetic_route,
)


class RampLimiterState:
    # [173차] asymmetric_up 파라미터 추가 -- 기본값 False로 기존
    # 132차/133차 대칭 동작을 완전히 보존(replay_route_ramp_limiter_direct.py
    # 등 기존 스크립트가 인자 없이 그대로 호출하므로 하위호환 필수).
    # asymmetric_up=True일 때만 172차 원인A 패치 후보(증가/원복측 무제한)를
    # 시뮬레이션한다.
    def __init__(self, asymmetric_up=False):
        self.prev_out = None
        self.asymmetric_up = asymmetric_up

    def apply(self, raw_out_speed, accel_limit_kmh, dt):
        if raw_out_speed >= 299.999:
            # "제약 없음" 신호 -> 즉시 통과 + 상태 리셋 (완화 방향은 항상 즉시 허용)
            self.prev_out = None
            return raw_out_speed
        if self.prev_out is None:
            out = raw_out_speed
        else:
            max_step = accel_limit_kmh * dt
            lo = self.prev_out - max_step
            # [173차] 증가(원복) 방향 -- 160차 apex 재설계가 "apex 통과 즉시
            # 원복"을 의도했으므로, asymmetric_up 모드에서는 hi를 사실상
            # 무제한으로 둔다(하강측 lo는 그대로 유지 -- 감속 스케줄 보호는
            # 계속 필요).
            hi = float('inf') if self.asymmetric_up else self.prev_out + max_step
            out = min(max(raw_out_speed, lo), hi)
        self.prev_out = out
        return out


def run(args):
    coords, lon0, lat0, m_per_deg_lon, m_per_deg_lat = build_synthetic_route(
        args.straight_before_curve_m, args.curve_radius_m, args.curve_arc_deg)

    v_ego_ms = args.v_ego_kph / 3.6
    lookahead0 = compute_route_lookahead_distance(args.v_ego_kph, args.accel)
    start_offset_m = min(args.straight_before_curve_m - 5.0, lookahead0 + 250.0)
    ego_y = max(0.0, args.straight_before_curve_m - start_offset_m)

    navi_points_start_index = 0
    limiter = RampLimiterState()
    # [173차] 172차 원인A 패치 후보(증가측 무제한) 나란히 비교
    limiter_asym = RampLimiterState(asymmetric_up=True)
    accel_limit_kmh = args.accel * 3.6

    prev_unpatched = None
    max_drop_unpatched = 0.0
    max_drop_patched = 0.0
    max_drop_t_unpatched = None
    max_drop_t_patched = None
    max_rise_asym = 0.0
    max_rise_t_asym = None
    recovery_frames_patched = None
    recovery_frames_asym = None
    apex_passed_frame = None
    frame_idx = 0
    # [132차 사전검증] 300(제약없음 센티널) <-> 실제값 전환은 시뮬레이션
    # 하네스 자체의 경계 아티팩트(131차가 이미 "극단값 -- 원호 진입점이
    # 커브 시작이라 과장"/"윈도우가 커브를 완전히 지나며 사라짐"으로 문서화한
    # 것과 동일 성격)이지, 이 패치가 목표로 하는 "윈도우 경계 진입에 의한
    # 이산적 curvature 출현" 현상이 아니다. 두 종류를 구분해 별도로 집계한다.
    max_drop_unpatched_steady = 0.0
    max_drop_patched_steady = 0.0
    max_drop_t_steady = None
    t = 0.0

    print(f"=== 램프 리미터 패치 사전검증 (v_ego={args.v_ego_kph}kph, "
          f"curve_R={args.curve_radius_m}m, accel={args.accel}, dt={args.dt}s) ===")
    print(f"{'t':>7} {'dist_to_curve':>14} {'unpatched':>10} {'d(unp)':>8} {'patched':>9} {'d(pat)':>8} "
          f"{'asym(A)':>9} {'d(asym)':>8}")

    while ego_y < args.straight_before_curve_m + 50:
        lon = lon0
        lat = lat0 + ego_y / m_per_deg_lat
        current_position = (lon, lat)
        out_speed_raw, navi_points_start_index, n_speeds, far_dist = carrot_navi_route_core(
            coords, navi_points_start_index, current_position, heading_deg=0.0,
            v_ego_kph=args.v_ego_kph, accel_limit=args.accel,
            road_limit_speed_kph=args.road_limit_speed_kph)
        out_speed_patched = limiter.apply(out_speed_raw, accel_limit_kmh, args.dt)
        out_speed_asym = limiter_asym.apply(out_speed_raw, accel_limit_kmh, args.dt)

        dist_to_curve = args.straight_before_curve_m - ego_y

        # [173차] apex(커브 정점, dist_to_curve<=0으로 최초 전환되는 프레임)
        # 통과 후 "원복 완료까지 걸리는 프레임 수" 계측 -- 원인A가 실제로
        # 개선되는지(즉시 원복 vs 서서히 상승)를 시간 단위로 정량화.
        if apex_passed_frame is None and dist_to_curve <= 0:
            apex_passed_frame = frame_idx
        if apex_passed_frame is not None:
            if recovery_frames_patched is None and out_speed_patched >= out_speed_raw - 0.05:
                recovery_frames_patched = frame_idx - apex_passed_frame
            if recovery_frames_asym is None and out_speed_asym >= out_speed_raw - 0.05:
                recovery_frames_asym = frame_idx - apex_passed_frame

        d_unp_str = d_pat_str = d_asym_str = ""
        if prev_unpatched is not None:
            d_unp = out_speed_raw - prev_unpatched[0]
            d_pat = out_speed_patched - prev_unpatched[1]
            d_asym = out_speed_asym - prev_unpatched[2]
            d_unp_str, d_pat_str, d_asym_str = f"{d_unp:+.2f}", f"{d_pat:+.2f}", f"{d_asym:+.2f}"
            if -d_unp > max_drop_unpatched:
                max_drop_unpatched, max_drop_t_unpatched = -d_unp, t
            if -d_pat > max_drop_patched:
                max_drop_patched, max_drop_t_patched = -d_pat, t
            if d_asym > max_rise_asym:
                max_rise_asym, max_rise_t_asym = d_asym, t
            is_sentinel_transition = (out_speed_raw >= 299.999) or (prev_unpatched[0] >= 299.999)
            if not is_sentinel_transition:
                if -d_unp > max_drop_unpatched_steady:
                    max_drop_unpatched_steady = -d_unp
                if -d_pat > max_drop_patched_steady:
                    max_drop_patched_steady, max_drop_t_steady = -d_pat, t

        if abs(dist_to_curve) < 400 or (prev_unpatched is not None and abs(out_speed_raw - prev_unpatched[0]) > 3.0):
            print(f"{t:7.2f} {dist_to_curve:14.1f} {out_speed_raw:10.1f} {d_unp_str:>8} "
                  f"{out_speed_patched:9.1f} {d_pat_str:>8} {out_speed_asym:9.1f} {d_asym_str:>8}")

        prev_unpatched = (out_speed_raw, out_speed_patched, out_speed_asym)
        frame_idx += 1
        ego_y += v_ego_ms * args.dt
        t += args.dt

    theoretical_max_step = accel_limit_kmh * args.dt
    print(f"\n[전체(300 센티널 전환 포함)] 최대 프레임간 낙차: unpatched={max_drop_unpatched:.2f}kph, "
          f"patched={max_drop_patched:.2f}kph")
    print("  (300<->실제값 전환은 시뮬레이션 하네스 경계 아티팩트 -- 131차가 이미 문서화한 "
          "'원호 진입점 과장'/'윈도우가 커브를 완전히 지나며 소멸' 케이스와 동일 성격, "
          "실차에서 방금 route가 활성화된 순간에만 해당하고 이 패치의 대상이 아님)")
    print(f"\n[핵심 지표] 정상주행 중(300 센티널 제외) 최대 프레임간 낙차: "
          f"unpatched={max_drop_unpatched_steady:.2f}kph, patched={max_drop_patched_steady:.2f}kph "
          f"@ t={max_drop_t_steady}")
    print(f"이론상 patched 최대 허용 프레임당 낙차(accel_limit_kmh*dt) = {theoretical_max_step:.2f}kph")
    ok = max_drop_patched_steady <= theoretical_max_step + 1e-6
    print("=> PASS: 정상주행 구간에서 patched 낙차가 이론 상한 이내로 억제됨(Hypothesis C 완화 확인)"
          if ok else "=> FAIL: 이론 상한 초과 -- 로직 재검토 필요")

    # [173차, 172차 원인A 후보 검증] 증가측(asym) 최대 상승폭 -- 사실상
    # 무제한이므로 raw_out_speed의 순간 상승폭과 거의 같아야 정상(=원복이
    # 램프에 더 이상 묶이지 않음을 의미).
    print(f"\n[172차 원인A 후보] asym 모드 최대 프레임당 상승폭: {max_rise_asym:.2f}kph @ t={max_rise_t_asym} "
          f"(참고: patched 상한 = {theoretical_max_step:.2f}kph -- 이보다 크면 램프 해제 확인됨)")
    print(f"[172차 원인A 후보] apex 통과 후 원복 완료(raw 근접)까지 걸린 프레임 수: "
          f"patched(대칭, 현재코드)={recovery_frames_patched}프레임({(recovery_frames_patched or 0) * args.dt:.2f}s), "
          f"asym(후보A)={recovery_frames_asym}프레임({(recovery_frames_asym or 0) * args.dt:.2f}s)")
    asym_ok = (recovery_frames_asym is not None and recovery_frames_patched is not None
               and recovery_frames_asym <= recovery_frames_patched)
    print("=> PASS: asym 모드가 patched(대칭) 대비 원복을 지연시키지 않음(오히려 즉시/더 빠름)"
          if asym_ok else "=> FAIL: asym 모드가 오히려 원복을 지연 -- 로직 재검토 필요")
    # 감속측(lo)은 두 모드 동일해야 함(하강 상한은 손대지 않았으므로) --
    # steady 낙차 지표가 patched와 asym 사이에서 같은지는 위 max_drop_patched_steady
    # 계산에 asym이 포함돼 있지 않으므로, 필요시 별도 실행으로 대조 가능
    # (이번 검증 목적상 핵심은 상승측 완화이므로 별도 계측은 생략).
    return max_drop_unpatched_steady, max_drop_patched_steady, theoretical_max_step


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--v-ego-kph', type=float, default=74.0)
    ap.add_argument('--curve-radius-m', type=float, default=17.3,
                     help='129차/131차 정밀매칭 실측 반경(기본값)')
    ap.add_argument('--curve-arc-deg', type=float, default=90.0)
    ap.add_argument('--accel', type=float, default=0.70)
    ap.add_argument('--straight-before-curve-m', type=float, default=700.0)
    ap.add_argument('--dt', type=float, default=0.05)
    # [173차] 172차 실측(우회전 통과 후 30->48kph, 즉 300 무제약 센티널이
    # 아니라 "커브 이후 유한한 도로제한속도"로 수렴하는 실제 패턴) 재현용.
    # 기본값 300(기존 스크립트 동작 그대로 보존)이면 커브 직후 바로 무제약
    # 센티널로 튀어 132차 램프 자체가 즉시 리셋되므로, 원인A가 실측과 같은
    # "서서히 상승" 형태로 나타나지 않는다 -- 재현하려면 유한값 지정 필요.
    ap.add_argument('--road-limit-speed-kph', type=float, default=300.0,
                     help='커브 이후 직선 구간의 유효 목표속도(기본 300=무제약, 172차 재현엔 예: 48)')
    args = ap.parse_args()
    run(args)


if __name__ == '__main__':
    main()
