#!/usr/bin/env python3
"""
130차: 129차(교차로 접근 route 사전감속 "계단형 고정") 실측 재현 확대판.

93차 `sim_route_margin_regression_scan.py`는 고정 3초 간격 스냅샷에서
margin=0 vs margin=25의 out_speed_now/min_speed 차이만 비교해 "조기개입
자체는 설계대로 동작"만 확인했음(93차 결과: min_speed 불변, 역전 0건).
이 스크립트는 그 결과를 재확인하되, **실제 계단형 급락이 관측된 정확한
시각(t=2182.70~2182.75, Δ-25kph) 주변을 0.05s(20Hz) 간격으로 슬라이딩
스냅샷**해 `backward_dp_margin()`의 out_speed_now(=현재 위치 목표속도,
carrotMan desiredSpeed로 이어지는 값)가 **연속적으로 변하는지 아니면
프레임 간 불연속으로 점프하는지**를 직접 확인한다 — "감속 스케줄이
당겨진다"(93차가 검증한 것)와 "그 스케줄 자체가 위치/시간에 대해
불연속"(129차가 실제로 불만을 제기한 것)은 다른 질문이며, 93차
스크립트는 후자를 검증하지 않았다.

추가로, 129차가 제안한 대안(사용자 제안 "과속카메라처럼 연속적으로
감속" = `carrot_serv.py calculate_current_speed()`가 이미 쓰는 sqrt
운동학 커브 방식)을 route DP 출력에 적용했을 때 동일 시간대에서
out_speed_now(t)가 매끄러워지는지 비교 시뮬레이션도 포함한다(코드
미반영, 순수 로직 비교).

사용:
  python3 sim_route_step_drop_repro.py <route.csv> \
      --t-center 2182.72 --window 3.0 --accel 0.70 --margin 25.0
"""
import argparse
import math
import sys

import numpy as np

sys.path.append("/home/claude/devnotes/toolkit")
from analysis_helpers import load_csv  # noqa: E402
from sim_route_curvature_sample import (  # noqa: E402
    reconstruct_path, resample_10m, compute_curvatures_speeds,
)
from sim_route_margin_regression_scan import backward_dp_margin  # noqa: E402


def out_speed_now_at(rows, t0, lookahead_s, accel_limit, margin_kph, sample=4):
  """t0 시점 스냅샷에서 backward_dp_margin 실행, out_speeds[0](현재
  위치 목표속도)만 반환. 93차 run_snapshot_margin과 동일 절차, 반환값만
  단순화."""
  pts = reconstruct_path(rows, t_start=t0, t_end=t0 + lookahead_s)
  if len(pts) < 20:
    return None
  xy = [(p['x'], p['y']) for p in pts]
  v_ego_kph = pts[0]['vEgo'] * 3.6
  try:
    resampled = resample_10m(xy)
  except Exception:
    return None
  curvatures, speeds, distances = compute_curvatures_speeds(resampled, sample)
  if not speeds:
    return None
  out = backward_dp_margin(speeds, distances, v_ego_kph, accel_limit, margin_kph=margin_kph)
  return out[0], v_ego_kph, distances[0] if distances else None


def backward_dp_smooth_ramp(speeds, distances, v_ego_kph, accel_limit, margin_kph, distance_interval=10.0,
                             vturn_safe_time=2.0):
  """129차 사용자 제안(연속 sqrt 감속) 근사 -- calculate_current_speed()가
  쓰는 '남은 거리 기반 sqrt 운동학 감속 곡선' 철학을 backward_dp 출력에
  사후 적용한 근사 버전. 실제 코드(calculate_current_speed)를 그대로
  옮긴 것은 아니고, "각 지점의 out_speed는 그 지점으로부터 다음
  감속목표점까지 남은 거리로 물리적으로 감속 가능한 한도 내에서만 낮아질
  수 있다"는 동일 원리를 v = sqrt(v_prev^2 - 2*a*d)로 재구성해 out_speeds
  배열에 앞->뒤 방향 forward pass로 한번 더 적용한다.
  (원본 backward_dp_margin은 뒤->앞으로 "미리 감속을 당기는" 스케줄만
  계산 -- 이 함수는 그 결과에 "실제로 그 지점에서 물리적으로 도달
  가능한 최대속도" 상한을 forward pass로 한번 더 씌워, 목표속도 자체가
  위치에 대해 매끄러운 sqrt 곡선을 그리도록 강제한다.)
  """
  base = backward_dp_margin(speeds, distances, v_ego_kph, accel_limit,
                             distance_interval=distance_interval,
                             vturn_safe_time=vturn_safe_time, margin_kph=margin_kph)
  smoothed = list(base)
  accel_ms2 = accel_limit
  for i in range(1, len(smoothed)):
    remaining_m = distance_interval
    v_prev_ms = smoothed[i - 1] / 3.6
    if base[i] < smoothed[i - 1]:
      max_decel_reachable = math.sqrt(max(0.0, v_prev_ms ** 2 - 2 * accel_ms2 * remaining_m)) * 3.6
      smoothed[i] = max(base[i], min(smoothed[i - 1], max_decel_reachable))
    else:
      smoothed[i] = base[i]
  return smoothed


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('csv_path')
  ap.add_argument('--t-center', type=float, default=2182.72,
                   help='급락이 관측된 시각(129차 실측: t=2182.70~2182.75)')
  ap.add_argument('--window', type=float, default=3.0, help='t_center 앞뒤로 이만큼(초) 스캔')
  ap.add_argument('--fine-step', type=float, default=0.05, help='슬라이딩 스텝(초), 기본 20Hz')
  ap.add_argument('--lookahead', type=float, default=45.0)
  ap.add_argument('--accel', type=float, default=0.70)
  ap.add_argument('--margin', type=float, default=25.0)
  args = ap.parse_args()

  rows = load_csv(args.csv_path)

  print(f"=== out_speed_now(t) 슬라이딩 재구성 (margin={args.margin}kph, "
        f"t={args.t_center - args.window:.2f}~{args.t_center + args.window:.2f}, "
        f"step={args.fine_step}s) ===")
  print(f"{'t':>10} {'vEgo(kph)':>10} {'out_speed_now':>14} {'d(out)/dt*step':>16}")

  t0 = args.t_center - args.window
  prev_out = None
  max_step_drop = 0.0
  max_step_drop_t = None
  results = []
  while t0 <= args.t_center + args.window:
    res = out_speed_now_at(rows, t0, args.lookahead, args.accel, args.margin)
    if res is None:
      t0 += args.fine_step
      continue
    out_now, v_ego_kph, d0 = res
    diff_str = ""
    if prev_out is not None:
      d = out_now - prev_out
      diff_str = f"{d:+.2f}"
      if -d > max_step_drop:
        max_step_drop = -d
        max_step_drop_t = t0
    results.append((t0, v_ego_kph, out_now))
    print(f"{t0:10.2f} {v_ego_kph:10.1f} {out_now:14.1f} {diff_str:>16}")
    prev_out = out_now
    t0 += args.fine_step

  print(f"\n최대 프레임간 급락: {max_step_drop:.2f}kph @ t={max_step_drop_t}")
  print("(참고) 129차 실측: t=2182.70->2182.75 desiredSpeed 86->61 (Δ-25.0)")

  print("\n=== 실측 desiredSpeed(t) 대조 (CSV 원본, src=route 구간만) ===")
  window_rows = [r for r in rows
                 if args.t_center - args.window <= float(r['t']) <= args.t_center + args.window]
  prev_ds = None
  for r in window_rows:
    t = float(r['t'])
    ds = float(r['desiredSpeed']) if r['desiredSpeed'] else None
    if ds is None:
      continue
    if prev_ds is not None and abs(ds - prev_ds) > 5.0:
      print(f"  t={t:.2f} desiredSpeed(실측)={ds:.1f} (직전대비 {ds - prev_ds:+.1f}) src={r['src']}")
    prev_ds = ds

  print("\n=== 129차 사용자 제안(연속 sqrt 감속) 근사 비교, t_center 시점 단일 스냅샷 ===")
  pts = reconstruct_path(rows, t_start=args.t_center, t_end=args.t_center + args.lookahead)
  if len(pts) >= 20:
    xy = [(p['x'], p['y']) for p in pts]
    v_ego_kph = pts[0]['vEgo'] * 3.6
    resampled = resample_10m(xy)
    curvatures, speeds, distances = compute_curvatures_speeds(resampled, 4)
    if speeds:
      base = backward_dp_margin(speeds, distances, v_ego_kph, args.accel, margin_kph=args.margin)
      smooth = backward_dp_smooth_ramp(speeds, distances, v_ego_kph, args.accel, margin_kph=args.margin)
      max_step_base = max((base[i - 1] - base[i] for i in range(1, len(base))), default=0.0)
      max_step_smooth = max((smooth[i - 1] - smooth[i] for i in range(1, len(smooth))), default=0.0)
      print(f"  현재 로직(margin={args.margin}) 최대 10m-스텝간 낙차: {max_step_base:.2f}kph")
      print(f"  smooth-ramp 근사 최대 10m-스텝간 낙차: {max_step_smooth:.2f}kph")
      print(f"  out_speed_now: base={base[0]:.1f} vs smooth={smooth[0]:.1f}")
      print(f"  min(out_speeds): base={min(base):.1f} vs smooth={min(smooth):.1f} "
            f"(목표 정점값 자체는 동일해야 함 -- 설계의도 검증)")
  else:
    print("  (lookahead 부족, 스킵)")


if __name__ == '__main__':
  main()
