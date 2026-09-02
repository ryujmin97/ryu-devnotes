#!/usr/bin/env python3
"""
203차 -- spike_proxy 무장(armed) + N프레임 연속 무신호 시 해제(disarm)하는
결합 설계의 N값별(3/5/8/10) 스윕.

armed=True 동안 hi=vEgo_kph, armed=False(정상)면 hi=math.inf(173차 원래 설계).

평가:
1) spike suppression: t=418.4~419.5 스파이크 구간에서 armed가 유지되는가
2) 브릿지: 스파이크(t~418.6) 이후 북대전IC 진입(t~450)까지 armed가 끊김없이
   유지되는가(끊기면 201차/202차가 밝힌 baseline 문제가 재발)
3) false recovery / recovery latency: 스파이크성 신호가 반복 발생하는 구간
   (t=291~314, t=382~393 -- 실제 도로 형태 미확인, 아래에서 라벨링 필요성 지적)
   에서 armed가 계속 재무장되어 정상 직진 가속을 막지는 않는가
"""
import csv
import math
import sys

ROUTE_MAX_SPEED_KPH = 150.0
ROAD_LIMIT_PROXY_KPH = 150.0


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


def compute_spike_proxy_series(rows):
    prev_apex_idx = None
    prev_raw = None
    series = []
    for r in rows:
        t = f(r, "t")
        active = r["naviPointsActive"] == "True"
        if not active:
            prev_apex_idx = None
            prev_raw = None
            series.append((t, False, False))
            continue
        apex_idx = int(float(r["routeApexIdx"])) if r["routeApexIdx"] not in ("", None) else -1
        raw_col = f(r, "routeOutSpeed", 300.0)
        idx_changed = (prev_apex_idx is not None and apex_idx != prev_apex_idx)
        raw_jump = (prev_raw is not None and (raw_col - prev_raw) > 20.0)
        spike = idx_changed and (raw_col >= ROAD_LIMIT_PROXY_KPH) and raw_jump
        series.append((t, True, spike))
        prev_apex_idx = apex_idx
        prev_raw = raw_col
    return series


def sweep(series, N):
    armed = False
    clean_count = 0
    timeline = []  # (t, armed)
    disarm_events = []
    arm_events = []
    for t, active, spike in series:
        if not active:
            armed = False
            clean_count = 0
            timeline.append((t, armed))
            continue
        if spike:
            if not armed:
                arm_events.append(t)
            armed = True
            clean_count = 0
        else:
            if armed:
                clean_count += 1
                if clean_count >= N:
                    armed = False
                    disarm_events.append(t)
                    clean_count = 0
        timeline.append((t, armed))
    return timeline, arm_events, disarm_events


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/199cha_8seg_route_extracted.csv"
    rows = load_rows(csv_path)
    series = compute_spike_proxy_series(rows)

    for N in [3, 5, 8, 10, 60, 92, 100, 120]:
        timeline, arm_events, disarm_events = sweep(series, N)
        print(f"\n===== N={N} (연속 {N}프레임={N*0.05:.2f}s 무신호 시 disarm) =====")
        print(f"arm 이벤트 수: {len(arm_events)}, disarm 이벤트 수: {len(disarm_events)}")

        # 1) t=418.4~419.5 스파이크 구간에서 armed 유지 여부
        seg1 = [(t, a) for t, a in timeline if 418.40 <= t <= 419.55]
        print(f"[스파이크구간 418.4~419.5] armed=True 비율: {sum(a for _,a in seg1)}/{len(seg1)}")

        # 2) 스파이크(418.6) ~ 북대전IC 진입(450) 브릿지 유지 여부
        bridge = [(t, a) for t, a in timeline if 418.60 <= t <= 450.0]
        armed_frac = sum(a for _, a in bridge) / len(bridge)
        first_disarm_in_bridge = next((t for t, a in bridge if not a), None)
        print(f"[브릿지 418.6~450.0] armed=True 비율: {armed_frac*100:.1f}%, "
              f"구간 내 최초 disarm 시각: {first_disarm_in_bridge}")

        # 3) 북대전IC 구간(450~498) armed 유지 여부(실제 감속 필요 구간이므로 유지돼야 함)
        seg3 = [(t, a) for t, a in timeline if 450.0 <= t <= 498.0]
        print(f"[북대전IC 450~498] armed=True 비율: {sum(a for _,a in seg3)}/{len(seg3)}")

        # 4) 반복 스파이크 구간(291~314, 382~393)에서 armed로 묶여있는 총 시간(초)
        for label, lo, hi in [("291~314(추정 직선/전환구간)", 291, 314), ("382~393(추정 직선/전환구간)", 382, 393)]:
            segX = [(t, a) for t, a in timeline if lo <= t <= hi]
            armed_time_s = sum(a for _, a in segX) * 0.05
            print(f"[{label}] armed 유지 총 시간: {armed_time_s:.2f}s / 구간길이 {hi-lo}s")


if __name__ == "__main__":
    main()
