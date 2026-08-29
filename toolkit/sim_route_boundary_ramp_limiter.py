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
    def __init__(self):
        self.prev_out = None

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
            hi = self.prev_out + max_step
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
    accel_limit_kmh = args.accel * 3.6

    prev_unpatched = None
    max_drop_unpatched = 0.0
    max_drop_patched = 0.0
    max_drop_t_unpatched = None
    max_drop_t_patched = None
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
    print(f"{'t':>7} {'dist_to_curve':>14} {'unpatched':>10} {'d(unp)':>8} {'patched':>9} {'d(pat)':>8}")

    while ego_y < args.straight_before_curve_m + 50:
        lon = lon0
        lat = lat0 + ego_y / m_per_deg_lat
        current_position = (lon, lat)
        out_speed_raw, navi_points_start_index, n_speeds, far_dist = carrot_navi_route_core(
            coords, navi_points_start_index, current_position, heading_deg=0.0,
            v_ego_kph=args.v_ego_kph, accel_limit=args.accel)
        out_speed_patched = limiter.apply(out_speed_raw, accel_limit_kmh, args.dt)

        dist_to_curve = args.straight_before_curve_m - ego_y
        d_unp_str = d_pat_str = ""
        if prev_unpatched is not None:
            d_unp = out_speed_raw - prev_unpatched[0]
            d_pat = out_speed_patched - prev_unpatched[1]
            d_unp_str, d_pat_str = f"{d_unp:+.2f}", f"{d_pat:+.2f}"
            if -d_unp > max_drop_unpatched:
                max_drop_unpatched, max_drop_t_unpatched = -d_unp, t
            if -d_pat > max_drop_patched:
                max_drop_patched, max_drop_t_patched = -d_pat, t
            is_sentinel_transition = (out_speed_raw >= 299.999) or (prev_unpatched[0] >= 299.999)
            if not is_sentinel_transition:
                if -d_unp > max_drop_unpatched_steady:
                    max_drop_unpatched_steady = -d_unp
                if -d_pat > max_drop_patched_steady:
                    max_drop_patched_steady, max_drop_t_steady = -d_pat, t

        if abs(dist_to_curve) < 400 or (prev_unpatched is not None and abs(out_speed_raw - prev_unpatched[0]) > 3.0):
            print(f"{t:7.2f} {dist_to_curve:14.1f} {out_speed_raw:10.1f} {d_unp_str:>8} "
                  f"{out_speed_patched:9.1f} {d_pat_str:>8}")

        prev_unpatched = (out_speed_raw, out_speed_patched)
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
    args = ap.parse_args()
    run(args)


if __name__ == '__main__':
    main()
