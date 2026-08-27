#!/usr/bin/env python3
"""
5개 항목 종합분석 프레임워크 (55/56차부터 반복 사용).

항목:
1) 카메라 인식 시 감속 (vision_to_radar_crossover, analysis_helpers 기존 함수 재사용)
2) 정지 앞차 감속 (stopped_lead_decel_events, 신규 — leadStatus and |leadVLead|<1.0m/s 지속구간)
3) 정지 후 재출발 (launch_after_stop_events, 신규 — vEgo 0.3m/s -> 5.0m/s 도달 구간,
   45차 LAUNCH_BYPASS_STOP_V_EGO/EXIT_V_EGO 상수와 동일 값)
4) 레이더 락온 상태 추종 중 저크 (radar_lockon_jerk_events, 신규 — 0.3s 이동평균 aEgo
   기준 |jerk|>=3.0 m/s^3, leadRadar=True 프레임만)
5) 곡선구간 감속 (turn_speed_violations, analysis_helpers 기존 함수 재사용)

55차에서 처음 작성됐으나 work/ 스크래치에만 있어 컨테이너 리셋으로 2회(56차/86차)
유실됨 — 이번에 devnotes/toolkit/에 정식 편입해 재발 방지.

사용법:
    from five_item_scan import run_five_item_scan
    result = run_five_item_scan(rows)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from analysis_helpers import vision_to_radar_crossover, turn_speed_violations, _f, _b


def stopped_lead_decel_events(rows, v_lead_thresh=1.0, min_duration_s=1.0):
    """leadStatus and |leadVLead|<thresh 지속구간을 이벤트로 묶어 반환."""
    events = []
    cur = None
    for row in rows:
        status = _b(row, "leadStatus")
        v_lead = _f(row, "leadVLead")
        t = _f(row, "t")
        stopped = status and v_lead is not None and abs(v_lead) < v_lead_thresh
        if stopped:
            if cur is None:
                cur = {"start_t": t, "rows": [row]}
            else:
                cur["rows"].append(row)
        else:
            if cur is not None:
                if cur["rows"][-1] is not None:
                    dur = _f(cur["rows"][-1], "t") - cur["start_t"]
                    if dur >= min_duration_s:
                        events.append(_summarize_stopped(cur))
                cur = None
    if cur is not None:
        dur = _f(cur["rows"][-1], "t") - cur["start_t"]
        if dur >= min_duration_s:
            events.append(_summarize_stopped(cur))
    return events


def _summarize_stopped(cur):
    rs = cur["rows"]
    aegos = [_f(r, "aEgo") for r in rs if _f(r, "aEgo") is not None]
    return {
        "start_t": cur["start_t"],
        "end_t": _f(rs[-1], "t"),
        "duration_s": _f(rs[-1], "t") - cur["start_t"],
        "vEgo_start": _f(rs[0], "vEgo"),
        "vEgo_end": _f(rs[-1], "vEgo"),
        "dRel_start": _f(rs[0], "leadDRel"),
        "aEgo_min": min(aegos) if aegos else None,
        "seg": rs[0].get("seg"),
    }


def launch_after_stop_events(rows, stop_v_ego=0.3, exit_v_ego=5.0):
    """vEgo<stop_v_ego 진입 -> exit_v_ego 도달까지를 재출발 이벤트로 묶어 반환."""
    events = []
    state = "normal"  # normal -> stopped -> launching
    cur = None
    for row in rows:
        v = _f(row, "vEgo")
        t = _f(row, "t")
        if v is None or t is None:
            continue
        if state == "normal":
            if v < stop_v_ego:
                state = "stopped"
        elif state == "stopped":
            if v >= stop_v_ego:
                state = "launching"
                cur = {"start_t": t, "rows": [row]}
        elif state == "launching":
            cur["rows"].append(row)
            if v >= exit_v_ego:
                events.append(_summarize_launch(cur))
                state = "normal"
                cur = None
            elif v < stop_v_ego:
                # 재정차, 취소
                state = "stopped"
                cur = None
    return events


def _summarize_launch(cur):
    rs = cur["rows"]
    aegos = [_f(r, "aEgo") for r in rs if _f(r, "aEgo") is not None]
    gas = [_f(r, "gasPressed") for r in rs if r.get("gasPressed") not in (None, "")]
    gas_ratio = (sum(1 for g in gas if g) / len(gas)) if gas else 0.0
    return {
        "start_t": cur["start_t"],
        "end_t": _f(rs[-1], "t"),
        "duration_s": _f(rs[-1], "t") - cur["start_t"],
        "aEgo_max": max(aegos) if aegos else None,
        "aEgo_avg": (sum(aegos) / len(aegos)) if aegos else None,
        "driver_gas_ratio": gas_ratio,
        "seg": rs[0].get("seg"),
    }


def radar_lockon_jerk_events(rows, jerk_thresh=3.0, smooth_window_s=0.3):
    """0.3s 이동평균 aEgo 기준 |jerk|>=thresh, leadRadar=True 프레임만."""
    # 이동평균 aEgo 계산 (단순 슬라이딩 윈도우, 20Hz 가정)
    n = len(rows)
    ts = [_f(r, "t") for r in rows]
    aegos = [_f(r, "aEgo") for r in rows]
    smoothed = [None] * n
    for i in range(n):
        if ts[i] is None:
            continue
        lo = ts[i] - smooth_window_s / 2
        hi = ts[i] + smooth_window_s / 2
        vals = []
        j = i
        while j >= 0 and ts[j] is not None and ts[j] >= lo:
            if aegos[j] is not None:
                vals.append(aegos[j])
            j -= 1
        j = i + 1
        while j < n and ts[j] is not None and ts[j] <= hi:
            if aegos[j] is not None:
                vals.append(aegos[j])
            j += 1
        if vals:
            smoothed[i] = sum(vals) / len(vals)

    events = []
    for i in range(1, n):
        if smoothed[i] is None or smoothed[i - 1] is None:
            continue
        if ts[i] is None or ts[i - 1] is None:
            continue
        dt = ts[i] - ts[i - 1]
        if dt <= 0:
            continue
        jerk = (smoothed[i] - smoothed[i - 1]) / dt
        if abs(jerk) >= jerk_thresh and _b(rows[i], "leadRadar"):
            events.append({
                "t": ts[i],
                "jerk": jerk,
                "leadVRel": _f(rows[i], "leadVRel"),
                "leadDRel": _f(rows[i], "leadDRel"),
                "aEgo": aegos[i],
                "seg": rows[i].get("seg"),
            })
    return events


def run_five_item_scan(rows):
    """5개 항목 전부 실행, dict로 반환."""
    return {
        "1_vision_to_radar_crossover": vision_to_radar_crossover(rows),
        "2_stopped_lead_decel": stopped_lead_decel_events(rows),
        "3_launch_after_stop": launch_after_stop_events(rows),
        "4_radar_lockon_jerk": radar_lockon_jerk_events(rows),
        "5_turn_speed_violations": turn_speed_violations(rows),
    }


if __name__ == "__main__":
    import csv as csvmod

    if len(sys.argv) < 2:
        print("usage: five_item_scan.py <csv_path>")
        sys.exit(1)
    path = sys.argv[1]
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csvmod.DictReader(f))
    result = run_five_item_scan(rows)
    for k, v in result.items():
        print(f"{k}: {len(v)}건")
