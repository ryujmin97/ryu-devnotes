#!/usr/bin/env python3
"""
lookahead horizon 가설(ii) 직접 검증용 replay 스크립트 (2026-08-23, 53차 신규).

52차까지 누적된 근거: route2/route4에서 vturn_decel_rate(1.2m/s^2) 대비
실측 aEgo가 100~288%까지 반응하는데도 목표속도(vTurnSpeed)를 못 따라잡는
사례가 다수(75%/57%) 확인됨 -> "감속률 자체가 부족"이 아니라
"carrot_man.vturn_speed()가 급조임 커브를 충분히 일찍(=먼 시점에) 감지
못해 뒤늦게 반응"하는 쪽 가설(ii)에 무게가 실림. 그러나 지금까지의 검증은
전부 extract_log.py CSV의 vTurnSpeed(=필터 통과 후 최종 출력)만 봐온 것이라,
"모델이 애초에 그 지점을 lookahead 안에서 보고는 있었는데 저역통과
필터(vturn_decel_rc=0.15s)가 늦춘 것"과 "애초에 lookahead_horizon_s(8.0s)
윈도 안에 그 급조임 지점 자체가 아직 안 들어와 있었던 것"을 구분할 수 없었음.

이 스크립트는 modelV2 원본(orientationRate.z/velocity.x/position.x)을
rlog에서 직접 읽어, carrot_man.py의 vturn_speed()와 동일한 물리공식으로
"필터 적용 전(raw) argmin 지점"을 프레임 단위로 재현한다. 이러면:
  - raw_kph가 이미 오래전부터(예: 6~8초 전부터) 낮게 나왔는데 filtered_kph만
    저역통과 때문에 늦게 따라간 것이라면 -> 문제는 필터(decel_rc)에 있음.
  - raw_kph 자체가 실제 이벤트 직전까지 높게 유지되다가 급락한 것이라면
    -> 문제는 lookahead_horizon_s(또는 모델이 그 거리의 곡률을 정확히
    예측 못 하는 것)에 있음 -> 가설(ii) 직접 확증.

주의(한계):
  - carrot_man은 20Hz 자체 틱으로 sm['modelV2']를 매 틱 재사용(sample&hold)
    하지만, 이 스크립트는 modelV2 이벤트 자체(대략 20Hz 발행)를 한 틱으로
    취급한다 -- 완전히 동일한 타이밍은 아니나 근사로 충분하다고 판단(49차와
    동일 전제).
  - low-pass 필터의 dt는 실제 코드처럼 고정 1/20초를 사용한다(이벤트 간
    실제 시간차를 쓰지 않음 -- 코드 자체가 고정값을 쓰기 때문에 그대로 재현).
  - AutoCurveSpeedFactor/AutoCurveSpeedAggressiveness는 사용자 실제 런타임
    파라미터 값이 devnotes에 기록되어 있지 않아 코드 기본값(120/100,
    즉 1.2/1.0)을 기본으로 쓴다. 실제 값이 다르면 --factor/--aggr로 override.
  - curv_direction(부호) 로직도 참고용으로 재현하지만, 이 분석의 핵심은
    크기(속도 제약값) 쪽이라 부호 자체의 정확도는 2차적이다.

입력: route_dir (세그먼트 폴더들의 상위 폴더, 각 세그먼트에 rlog.zst)
출력: CSV (t, seg, raw_kph, filtered_kph_replica, apex_pos_m, apex_t_s,
      apex_lat_a_source_rate, curv_direction_replica)
      + (옵션) t_lo/t_hi 지정 시 그 구간만 stdout에도 표 출력

사용:
    python3 replay_lookahead_v1.py /home/claude/work/route4 \
        /home/claude/work/route4_lookahead.csv --repo /home/claude/ryu

    # 특정 이벤트 전후 8초 확대 확인 (예: route4 idx10 이벤트가 t=12345.6이면)
    python3 replay_lookahead_v1.py /home/claude/work/route4 \
        /home/claude/work/route4_lookahead.csv --repo /home/claude/ryu \
        --print-window 12337.6 12346.6

    # AutoCurveSpeedFactor/Aggressiveness가 기본값(120/100)이 아니면:
    python3 replay_lookahead_v1.py ... --factor 1.5 --aggr 1.2
"""
import argparse
import csv
import math
import os
import sys

import numpy as np

from decode_rlog import iter_events

# --- carrot_man.py vturn_speed()에서 그대로 가져온 상수 (2026-08-23 기준,
#     HEAD f94a7d2). 코드가 바뀌면 이 값들도 같이 동기화할 것. ---
TARGET_LAT_A = 1.6  # m/s^2
IDX_N = 33


def index_function(idx, max_val=192.0, max_idx=32):
    # selfdrive/modeld/constants.py의 index_function과 동일
    return max_val * ((idx / max_idx) ** 2)


T_IDXS = np.array([index_function(i, max_val=10.0) for i in range(IDX_N)])


def compute_vturn_frame(orientation_rate_raw, velocity_raw, position_raw,
                         factor, aggr, horizon_s, decel_rate, safe_time):
    """vturn_speed()의 필터-전 부분(argmin 계산까지)을 그대로 재현.

    반환: (raw_required_speed_kph, apex_pos_m, apex_t_s, curv_direction, ok)
    ok=False면 유효 포인트가 없어 계산 불가(250.0 기본값 상황).
    """
    orientation_rate = np.asarray(orientation_rate_raw, dtype=np.float64) * factor
    velocity = np.asarray(velocity_raw, dtype=np.float64)
    position = np.asarray(position_raw, dtype=np.float64)

    n = min(len(orientation_rate), len(velocity), len(position))
    if n == 0:
        return 250.0, float("nan"), float("nan"), 1.0, False
    orientation_rate = orientation_rate[:n]
    velocity = velocity[:n]
    position = position[:n]

    valid = np.isfinite(orientation_rate) & np.isfinite(velocity) & np.isfinite(position)
    orientation_rate = orientation_rate[valid]
    velocity = velocity[valid]
    position = position[valid]
    if len(orientation_rate) == 0:
        return 250.0, float("nan"), float("nan"), 1.0, False

    n_pts = min(len(orientation_rate), IDX_N)
    t_idxs = T_IDXS[:n_pts]
    within_horizon = int(np.count_nonzero(t_idxs <= horizon_s))
    lookahead_steps = max(5, min(n_pts, within_horizon))

    lookahead_rate = orientation_rate[:lookahead_steps]
    lookahead_vel = velocity[:lookahead_steps]
    lookahead_pos = np.maximum(position[:lookahead_steps], 0.0)
    lookahead_t = t_idxs[:lookahead_steps]

    adjusted_target_lat_a = TARGET_LAT_A * aggr
    point_lat_acc = np.abs(lookahead_rate) * np.abs(lookahead_vel)
    point_curve = point_lat_acc / np.maximum(lookahead_vel, 0.1) ** 2
    point_target_speed = np.where(
        point_curve > 1e-8,
        np.clip((adjusted_target_lat_a / np.maximum(point_curve, 1e-8)) ** 0.5 * 3.6, 5.0, 250.0),
        250.0,
    )

    safe_speed_mps = point_target_speed / 3.6
    safe_dist = safe_speed_mps * safe_time
    decel_dist = np.maximum(lookahead_pos - safe_dist, 0.0)
    required_speed_mps = np.sqrt(np.maximum(safe_speed_mps ** 2 + 2 * decel_rate * decel_dist, 0.0))
    required_speed_kph = np.clip(required_speed_mps * 3.6, 5.0, 250.0)

    apex_idx = int(np.argmin(required_speed_kph))
    turn_speed = float(required_speed_kph[apex_idx])
    apex_pos = float(lookahead_pos[apex_idx])
    apex_t = float(lookahead_t[apex_idx])

    if point_curve[apex_idx] > 1e-8:
        curv_direction = float(np.sign(lookahead_rate[apex_idx]))
    else:
        weights = np.clip(1.0 - 0.55 * (lookahead_t / max(horizon_s, 0.1)), 0.45, 1.0)
        curv_direction = float(np.sign(np.sum(lookahead_rate * weights)))
    if curv_direction == 0:
        curv_direction = float(np.sign(orientation_rate[0])) if orientation_rate[0] != 0 else 1.0

    return turn_speed, apex_pos, apex_t, curv_direction, True


def apply_lowpass(prev_speed, raw_speed, decel_rc, accel_rc, dt=1.0 / 20.0):
    if not math.isfinite(prev_speed):
        return raw_speed
    rc = decel_rc if raw_speed < prev_speed else accel_rc
    alpha = dt / (rc + dt)
    return prev_speed + (raw_speed - prev_speed) * alpha


def discover_segments(route_dir):
    segs = []
    for name in sorted(os.listdir(route_dir)):
        seg_dir = os.path.join(route_dir, name)
        rlog_path = os.path.join(seg_dir, "rlog.zst")
        if os.path.isdir(seg_dir) and os.path.exists(rlog_path):
            segs.append((name, rlog_path))
    return segs


def process_route(route_dir, repo_dir, max_mb, factor, aggr, horizon_s,
                   decel_rate, safe_time, decel_rc, accel_rc):
    segs = discover_segments(route_dir)
    if not segs:
        print(f"WARNING: {route_dir}에서 rlog.zst를 찾지 못함", file=sys.stderr)
        return []

    rows = []
    vturn_last_speed = float("nan")
    for seg_name, rlog_path in segs:
        for evt in iter_events(rlog_path, repo_dir=repo_dir, max_output_mb=max_mb):
            if evt.which() != "modelV2":
                continue
            t = evt.logMonoTime / 1e9
            md = evt.modelV2
            raw_kph, apex_pos, apex_t, curv_dir, ok = compute_vturn_frame(
                md.orientationRate.z, md.velocity.x, md.position.x,
                factor=factor, aggr=aggr, horizon_s=horizon_s,
                decel_rate=decel_rate, safe_time=safe_time,
            )
            if not ok:
                filtered = vturn_last_speed
            else:
                filtered = apply_lowpass(vturn_last_speed, raw_kph, decel_rc, accel_rc)
                vturn_last_speed = filtered
            rows.append({
                "t": f"{t:.3f}",
                "seg": seg_name,
                "raw_kph": f"{raw_kph:.3f}" if ok else "",
                "filtered_kph_replica": f"{filtered:.3f}" if math.isfinite(filtered) else "",
                "apex_pos_m": f"{apex_pos:.2f}" if ok else "",
                "apex_t_s": f"{apex_t:.3f}" if ok else "",
                "curv_direction_replica": f"{curv_dir:.0f}" if ok else "",
            })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("route_dir")
    ap.add_argument("out_csv")
    ap.add_argument("--repo", default="/home/claude/ryu")
    ap.add_argument("--max-mb", type=int, default=400)
    ap.add_argument("--factor", type=float, default=1.2, help="AutoCurveSpeedFactor*0.01 (기본값=코드 기본 120*0.01)")
    ap.add_argument("--aggr", type=float, default=1.0, help="AutoCurveSpeedAggressiveness*0.01 (기본값=코드 기본 100*0.01)")
    ap.add_argument("--horizon-s", type=float, default=8.0, help="vturn_lookahead_horizon_s (PARAMS_REGISTRY 확인된 최신값)")
    ap.add_argument("--decel-rate", type=float, default=1.2, help="vturn_decel_rate (m/s^2)")
    ap.add_argument("--safe-time", type=float, default=1.0, help="vturn_safe_time (s)")
    ap.add_argument("--decel-rc", type=float, default=0.15, help="vturn_decel_rc (s)")
    ap.add_argument("--accel-rc", type=float, default=0.15, help="vturn_accel_rc (s)")
    ap.add_argument("--print-window", nargs=2, type=float, metavar=("T_LO", "T_HI"),
                     help="지정 시 이 시간 구간만 stdout에 표로 추가 출력")
    args = ap.parse_args()

    rows = process_route(
        args.route_dir, args.repo, args.max_mb,
        factor=args.factor, aggr=args.aggr, horizon_s=args.horizon_s,
        decel_rate=args.decel_rate, safe_time=args.safe_time,
        decel_rc=args.decel_rc, accel_rc=args.accel_rc,
    )

    if not rows:
        print("추출된 modelV2 프레임이 없습니다.", file=sys.stderr)
        sys.exit(1)

    fieldnames = ["t", "seg", "raw_kph", "filtered_kph_replica", "apex_pos_m", "apex_t_s", "curv_direction_replica"]
    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} modelV2 프레임 -> {args.out_csv}")

    if args.print_window:
        t_lo, t_hi = args.print_window
        print(f"\n--- t={t_lo:.2f}~{t_hi:.2f} 구간 (raw vs filtered) ---")
        print(f"{'t':>12} {'raw_kph':>9} {'filtered':>9} {'apex_pos_m':>11} {'apex_t_s':>9}")
        for r in rows:
            t = float(r["t"])
            if t_lo <= t <= t_hi:
                print(f"{r['t']:>12} {r['raw_kph']:>9} {r['filtered_kph_replica']:>9} "
                      f"{r['apex_pos_m']:>11} {r['apex_t_s']:>9}")


if __name__ == "__main__":
    main()
