#!/usr/bin/env python3
"""
scan_consecutive_curve_pairs.py (286차 신규)

목적: 235차가 확정했던 실제 S커브 corpus(`0000039a--7b602ffb85` seg12-16)가
현재 레포/Drive에 미보관 상태(§23)라, 283/284/285차가 쓰던 다른 corpus
(route1~4: a3b3373495/01742d6c1c/c8d2619479/bf794c0073)에서 "S커브와
유사한 패턴"(방향이 반대인 커브 두 개가 짧은 간격으로 연속)을 대신
탐색하기 위한 범용 스캐너. 특정 route에 종속되지 않음 -- 임의의
extract_log.py CSV에 대해 동작한다.

방법:
1. `curve_apex_vs_gap_delta()`(analysis_helpers.py, 46차)와 동일한
   |steeringAngleDeg| entry/exit 임계값 방식으로 커브 이벤트를 분리한다
   (entry_thresh=5.0, exit_thresh=3.0, 기본값도 동일 -- 기존 도구와의
   일관성 유지, §21).
2. 연속된 두 이벤트(i, i+1)에 대해:
   - gap = entry_t[i+1] - exit_t[i]  (커브1 이탈 ~ 커브2 진입 간격)
   - sign_flip = apex_steer[i]와 apex_steer[i+1]의 부호가 반대인가
     (좌->우 또는 우->좌 전환 -- 235차 S커브의 정의적 특징)
3. `--max-gap`(기본 2.0s) 이하이고 sign_flip=True인 쌍만 "S커브 후보"로
   보고한다. gap 오름차순 정렬.
4. 각 후보에 대해 "두 번째 커브 반응성" 평가용 부가 지표를 계산한다:
   - 커브2 진입~apex 구간의 src 분포(route/vturn/section/gas 등 승자 비율)
   - 커브2 apex 시점 전후 desiredSpeed와 vEgo(kph)의 차이(초과/미달)
   - 커브2 apex 시점 전후 aEgo range (pump 여부 정성 판단용, 283차와
     동일 관례)

한계:
- steeringAngleDeg 기반 근사이므로 실제 route apex 선정 로직(곡률/
  naviPaths 기반)과 100% 일치하지 않는다 -- "물리적으로 조향각이 반대로
  꺾인 두 커브"를 찾는 것이지, route 알고리즘이 실제로 apex 2개를 어떻게
  처리했는지는 4번 부가 지표로 별도 확인해야 한다.
- 235차가 확정한 실제 S커브(t=2116~2122.2, 간격 250~290ms)와 물리적으로
  같은 위치를 찾는 것이 아니라, "유사한 성격의 패턴"을 다른 corpus에서
  찾는 것이다 -- 위치 재식별(GPS/naviPaths 매칭)의 대체가 아니라 보완.
- entry_thresh=5.0deg 미만의 완만한 S자(예: 차선 내 미세 곡선)는 잡히지
  않는다.

사용:
    python3 scan_consecutive_curve_pairs.py route1.csv route2.csv ... \\
        [--entry-thresh 5.0] [--exit-thresh 3.0] [--min-event-rows 3] \\
        [--max-gap 2.0] [--top 10]

여러 route CSV를 순서대로 이어붙여 하나의 연속 주행으로 취급한다
(동일 boot 세션 내 route ID만 바뀌는 경우 -- t가 route 경계에서 이어지는지
먼저 확인할 것, verify_route_release_hold_283_real_log.py의 load_concat과
동일 관례).
"""
import argparse
import sys

import pandas as pd
import numpy as np


def _f(row, key, default=None):
    v = row.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_concat(paths):
    dfs = []
    for p in paths:
        df = pd.read_csv(p, low_memory=False)
        df["_srcfile"] = p
        dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)
    df = df.sort_values("t").reset_index(drop=True)
    return df


def segment_curve_events(df, entry_thresh, exit_thresh, min_event_rows):
    """steeringAngleDeg 기반 커브 이벤트 분리. curve_apex_vs_gap_delta()와
    동일 방식(entry/exit 히스테리시스 임계값)."""
    steer = df["steeringAngleDeg"].astype(float).abs().to_numpy()
    t = df["t"].astype(float).to_numpy()

    events = []
    in_curve = False
    start_i = None
    for i in range(len(df)):
        s = steer[i]
        if np.isnan(s):
            continue
        if not in_curve and s >= entry_thresh:
            in_curve = True
            start_i = i
        elif in_curve and s < exit_thresh:
            in_curve = False
            if i - start_i >= min_event_rows:
                events.append((start_i, i - 1))
            start_i = None
    if in_curve and start_i is not None and (len(df) - 1 - start_i) >= min_event_rows:
        events.append((start_i, len(df) - 1))

    out = []
    for (i0, i1) in events:
        sub = df.iloc[i0:i1 + 1]
        raw_steer = sub["steeringAngleDeg"].astype(float)
        apex_pos = raw_steer.abs().idxmax()
        out.append({
            "i0": i0, "i1": i1,
            "entry_t": float(df["t"].iloc[i0]),
            "exit_t": float(df["t"].iloc[i1]),
            "apex_t": float(df["t"].loc[apex_pos]),
            "apex_steer": float(raw_steer.loc[apex_pos]),
            "seg": df["seg"].iloc[i0] if "seg" in df.columns else "",
        })
    return out


def evaluate_second_curve(df, ev2, window_before_s=1.0, window_after_s=1.0):
    """커브2 구간 전후로 src 분포 / desiredSpeed vs vEgo 차이 / aEgo range."""
    t = df["t"].astype(float)
    mask = (t >= ev2["entry_t"] - window_before_s) & (t <= ev2["exit_t"] + window_after_s)
    win = df[mask]
    if win.empty:
        return {}

    src_counts = win["src"].value_counts().to_dict() if "src" in win.columns else {}

    ds = pd.to_numeric(win.get("desiredSpeed"), errors="coerce")
    vego_kph = pd.to_numeric(win.get("vEgo"), errors="coerce") * 3.6
    diff = vego_kph - ds
    max_over = float(diff.max()) if diff.notna().any() else None  # 양수=초과

    aego = pd.to_numeric(win.get("aEgo"), errors="coerce")
    a_min = float(aego.min()) if aego.notna().any() else None
    a_max = float(aego.max()) if aego.notna().any() else None
    a_range = (a_max - a_min) if (a_min is not None and a_max is not None) else None

    route_frac = None
    if src_counts:
        total = sum(src_counts.values())
        route_frac = src_counts.get("route", 0) / total if total else None

    return {
        "src_counts": src_counts,
        "route_frac": route_frac,
        "max_vego_minus_desired_kph": max_over,
        "aEgo_min": a_min,
        "aEgo_max": a_max,
        "aEgo_range": a_range,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("routes", nargs="+")
    ap.add_argument("--entry-thresh", type=float, default=5.0)
    ap.add_argument("--exit-thresh", type=float, default=3.0)
    ap.add_argument("--min-event-rows", type=int, default=3)
    ap.add_argument("--max-gap", type=float, default=2.0,
                     help="커브1 exit ~ 커브2 entry 간격 상한(초). 이 이하이고 "
                          "부호가 반대인 쌍만 S커브 후보로 보고.")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    df = load_concat(args.routes)
    events = segment_curve_events(df, args.entry_thresh, args.exit_thresh,
                                   args.min_event_rows)
    print(f"curve events found: {len(events)}")

    candidates = []
    for i in range(len(events) - 1):
        e1, e2 = events[i], events[i + 1]
        gap = e2["entry_t"] - e1["exit_t"]
        if gap < 0:
            continue
        sign_flip = (e1["apex_steer"] * e2["apex_steer"]) < 0
        if gap <= args.max_gap and sign_flip:
            candidates.append((gap, e1, e2))

    candidates.sort(key=lambda x: x[0])
    print(f"S-curve candidates (gap<={args.max_gap}s, sign flip): {len(candidates)}\n")

    for rank, (gap, e1, e2) in enumerate(candidates[:args.top]):
        metrics = evaluate_second_curve(df, e2)
        print(f"--- candidate #{rank+1} ---")
        print(f"  curve1: apex_t={e1['apex_t']:.3f} steer={e1['apex_steer']:.1f}deg "
              f"seg={e1['seg']}")
        print(f"  curve2: apex_t={e2['apex_t']:.3f} steer={e2['apex_steer']:.1f}deg "
              f"seg={e2['seg']}")
        print(f"  gap(curve1 exit -> curve2 entry) = {gap:.3f}s")
        if metrics:
            print(f"  curve2 window src distribution: {metrics['src_counts']}")
            print(f"  curve2 window route_frac: {metrics['route_frac']}")
            print(f"  curve2 window max(vEgo_kph - desiredSpeed): "
                  f"{metrics['max_vego_minus_desired_kph']}")
            print(f"  curve2 window aEgo range: {metrics['aEgo_range']} "
                  f"(min={metrics['aEgo_min']}, max={metrics['aEgo_max']})")
        print()

    if not candidates:
        print("조건을 만족하는 S커브 후보 없음 (--max-gap 늘리거나 "
              "--entry-thresh 낮춰서 재시도 고려).")


if __name__ == "__main__":
    main()
