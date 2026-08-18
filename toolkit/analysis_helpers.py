#!/usr/bin/env python3
"""
extract_log.py로 뽑은 route.csv를 후처리하는 함수 모음.

컬럼 참고 (extract_log.py FIELDNAMES):
    t, seg,
    vEgo, aEgo, brakePressed, gasPressed, cruiseEnabled, vCruise,
    steeringAngleDeg, desiredCurvature,
    leadStatus, leadDRel, leadVRel, leadVLead,
    src, desiredSpeed, vTurnSpeed

모든 함수는 csv.DictReader가 만든 dict의 list(rows)를 입력으로 받는다.
숫자 필드는 문자열로 들어오므로 각 함수 내부에서 float() 변환한다.
"""
import csv
import json
import os


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_meta(csv_path):
    """
    extract_log.py가 생성한 <csv_path>.meta.json을 읽어 dict로 리턴.
    파일이 없으면(구버전 CSV 등) None.
    """
    meta_path = csv_path + ".meta.json"
    if not os.path.exists(meta_path):
        return None
    with open(meta_path) as f:
        return json.load(f)


def compare_runs_by_commit(csv_paths):
    """
    여러 route.csv (각기 다른 세션/커밋에서 뽑힌 로그)를 받아,
    trip_summary()를 커밋별로 나란히 비교할 수 있게 정리.
    csv_paths: [path1, path2, ...]

    리턴: [{"csv","commit","branch","commit_date","summary": trip_summary결과}, ...]
    meta.json이 없는 csv는 commit="unknown"으로 표시.
    """
    results = []
    for path in csv_paths:
        rows = load_csv(path)
        meta = load_meta(path)
        results.append({
            "csv": path,
            "commit": (meta or {}).get("commit_short", "unknown"),
            "branch": (meta or {}).get("branch"),
            "commit_date": (meta or {}).get("commit_date"),
            "summary": trip_summary(rows),
        })
    return results





def _f(row, key, default=None):
    v = row.get(key, "")
    if v == "" or v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _b(row, key):
    v = row.get(key, "")
    return str(v).strip().lower() in ("1", "true", "t", "yes")


# ---------------------------------------------------------------------------
# 1) 운전자 개입 구간 제거
# ---------------------------------------------------------------------------
def remove_driver_intervention(rows, gas_thresh=0.0, keep_margin_s=0.0):
    """
    brakePressed / gasPressed가 True인 프레임(및 그 앞뒤 keep_margin_s초)을
    제외한 rows를 리턴. cruiseEnabled가 False인 구간도 함께 제외.

    운전자가 개입한 순간 주변은 openpilot의 자체 판단이 아니므로,
    감속/커브 분석 등에서 노이즈가 된다.
    """
    n = len(rows)
    drop = [False] * n
    for i, r in enumerate(rows):
        intervened = _b(r, "brakePressed") or _b(r, "gasPressed") or not _b(r, "cruiseEnabled")
        if intervened:
            drop[i] = True

    if keep_margin_s > 0:
        times = [_f(r, "t", 0.0) for r in rows]
        drop_idx = [i for i, d in enumerate(drop) if d]
        for i in drop_idx:
            t0 = times[i]
            for j in range(max(0, i - 50), min(n, i + 50)):
                if abs(times[j] - t0) <= keep_margin_s:
                    drop[j] = True

    return [r for r, d in zip(rows, drop) if not d]


# ---------------------------------------------------------------------------
# 2) 감속 블록 탐지
# ---------------------------------------------------------------------------
def clean_decel_blocks(rows, decel_thresh=-0.5, min_duration_s=0.5, gap_merge_s=0.3):
    """
    aEgo <= decel_thresh 가 min_duration_s 이상 지속되는 구간들을 찾아 리턴.
    gap_merge_s 이내로 붙어 있는 블록은 하나로 합침.

    리턴: [{"seg", "t_start", "t_end", "duration", "min_aEgo", "v_start", "v_end"}]
    """
    blocks = []
    cur = None
    for r in rows:
        a = _f(r, "aEgo")
        t = _f(r, "t")
        v = _f(r, "vEgo")
        seg = r.get("seg")
        if a is None or t is None:
            continue
        if a <= decel_thresh:
            if cur is None:
                cur = {"seg": seg, "t_start": t, "t_end": t, "min_aEgo": a,
                       "v_start": v, "v_end": v}
            else:
                cur["t_end"] = t
                cur["v_end"] = v
                cur["min_aEgo"] = min(cur["min_aEgo"], a)
        else:
            if cur is not None:
                blocks.append(cur)
                cur = None
    if cur is not None:
        blocks.append(cur)

    # 짧은 gap으로 나뉜 블록 병합 (같은 세그먼트 내에서만)
    merged = []
    for b in blocks:
        if merged and merged[-1]["seg"] == b["seg"] and (b["t_start"] - merged[-1]["t_end"]) <= gap_merge_s:
            merged[-1]["t_end"] = b["t_end"]
            merged[-1]["v_end"] = b["v_end"]
            merged[-1]["min_aEgo"] = min(merged[-1]["min_aEgo"], b["min_aEgo"])
        else:
            merged.append(b)

    result = []
    for b in merged:
        dur = b["t_end"] - b["t_start"]
        if dur >= min_duration_s:
            b["duration"] = round(dur, 2)
            result.append(b)
    return result


# ---------------------------------------------------------------------------
# 3) 선행차 유무 판정 (구간 단위 요약)
# ---------------------------------------------------------------------------
def lead_presence_segments(rows, min_duration_s=0.5):
    """
    leadStatus가 True/False로 바뀌는 지점 기준으로 구간을 나눠 리턴.
    리턴: [{"seg", "t_start", "t_end", "duration", "lead", "min_dRel", "max_dRel"}]
    """
    segments = []
    cur = None
    for r in rows:
        t = _f(r, "t")
        seg = r.get("seg")
        lead = _b(r, "leadStatus")
        dRel = _f(r, "leadDRel")
        if t is None:
            continue
        if cur is None or cur["lead"] != lead or cur["seg"] != seg:
            if cur is not None:
                segments.append(cur)
            cur = {"seg": seg, "t_start": t, "t_end": t, "lead": lead,
                   "min_dRel": dRel, "max_dRel": dRel}
        else:
            cur["t_end"] = t
            if dRel is not None:
                cur["min_dRel"] = dRel if cur["min_dRel"] is None else min(cur["min_dRel"], dRel)
                cur["max_dRel"] = dRel if cur["max_dRel"] is None else max(cur["max_dRel"], dRel)
    if cur is not None:
        segments.append(cur)

    result = []
    for s in segments:
        dur = s["t_end"] - s["t_start"]
        if dur >= min_duration_s:
            s["duration"] = round(dur, 2)
            result.append(s)
    return result


# ---------------------------------------------------------------------------
# 4) 커브 탈출 - 무가속 구간 스캔
# ---------------------------------------------------------------------------
def curve_exit_no_accel_scan(rows, curvature_thresh=0.002, straight_thresh=0.0005,
                              min_curve_duration_s=0.5, no_accel_window_s=2.0,
                              accel_thresh=0.15):
    """
    desiredCurvature가 curvature_thresh 이상인 커브 구간이 끝나고
    (|curvature| < straight_thresh, 즉 직선 구간 진입) 이후
    no_accel_window_s 동안 aEgo가 accel_thresh를 못 넘긴 (가속하지 않은) 케이스를 찾는다.

    커브를 빠져나왔는데도 재가속이 지연/누락되는 상황을 감지하기 위한 용도.

    리턴: [{"seg", "t_curve_end", "t_window_end", "max_aEgo_in_window", "vEgo_at_exit"}]
    """
    n = len(rows)
    curv = [abs(_f(r, "desiredCurvature", 0.0) or 0.0) for r in rows]
    times = [_f(r, "t", 0.0) for r in rows]
    aEgo = [_f(r, "aEgo", 0.0) for r in rows]
    vEgo = [_f(r, "vEgo", 0.0) for r in rows]
    segs = [r.get("seg") for r in rows]

    results = []
    in_curve = False
    curve_start_t = None
    i = 0
    while i < n:
        c = curv[i]
        if not in_curve and c >= curvature_thresh:
            in_curve = True
            curve_start_t = times[i]
        elif in_curve and c < straight_thresh:
            curve_dur = times[i] - curve_start_t
            in_curve = False
            if curve_dur >= min_curve_duration_s:
                t_exit = times[i]
                seg_exit = segs[i]
                j = i
                max_a = aEgo[i] if aEgo[i] is not None else 0.0
                t_window_end = t_exit
                while j < n and segs[j] == seg_exit and (times[j] - t_exit) <= no_accel_window_s:
                    if aEgo[j] is not None:
                        max_a = max(max_a, aEgo[j])
                    t_window_end = times[j]
                    j += 1
                if max_a < accel_thresh:
                    results.append({
                        "seg": seg_exit,
                        "t_curve_end": round(t_exit, 2),
                        "t_window_end": round(t_window_end, 2),
                        "max_aEgo_in_window": round(max_a, 3),
                        "vEgo_at_exit": round(vEgo[i], 2) if vEgo[i] is not None else None,
                    })
        i += 1
    return results


# ---------------------------------------------------------------------------
# 5) 목표속도 추종 오차 분석
# ---------------------------------------------------------------------------
def speed_tracking_error(rows, target_field="desiredSpeed", window_s=1.0):
    """
    vEgo와 target_field(기본 desiredSpeed, 필요시 vCruise) 간의 오차를
    프레임별로 계산하고, window_s 구간별 평균/최대 오차를 요약해 리턴.

    리턴: {"frames": [{"t","seg","vEgo","target","error"}...],
           "summary": [{"seg","t_start","t_end","mean_abs_error","max_abs_error"}...]}
    """
    frames = []
    for r in rows:
        v = _f(r, "vEgo")
        tgt = _f(r, target_field)
        t = _f(r, "t")
        if v is None or tgt is None or t is None:
            continue
        frames.append({"t": t, "seg": r.get("seg"), "vEgo": v, "target": tgt, "error": v - tgt})

    summary = []
    cur = None
    for f in frames:
        if cur is None or f["seg"] != cur["seg"] or (f["t"] - cur["t_start"]) > window_s:
            if cur is not None:
                cur["mean_abs_error"] = round(cur["_sum_abs"] / cur["_n"], 3)
                cur["max_abs_error"] = round(cur["_max_abs"], 3)
                del cur["_sum_abs"], cur["_n"], cur["_max_abs"]
                summary.append(cur)
            cur = {"seg": f["seg"], "t_start": f["t"], "t_end": f["t"],
                   "_sum_abs": 0.0, "_n": 0, "_max_abs": 0.0}
        cur["t_end"] = f["t"]
        cur["_sum_abs"] += abs(f["error"])
        cur["_n"] += 1
        cur["_max_abs"] = max(cur["_max_abs"], abs(f["error"]))
    if cur is not None and cur["_n"] > 0:
        cur["mean_abs_error"] = round(cur["_sum_abs"] / cur["_n"], 3)
        cur["max_abs_error"] = round(cur["_max_abs"], 3)
        del cur["_sum_abs"], cur["_n"], cur["_max_abs"]
        summary.append(cur)

    return {"frames": frames, "summary": summary}


# ---------------------------------------------------------------------------
# 6) 커브 진입 시 권장속도(vTurnSpeed) 초과 탐지
# ---------------------------------------------------------------------------
def turn_speed_violations(rows, margin=0.5, min_duration_s=0.3):
    """
    vEgo > vTurnSpeed + margin (m/s) 인 구간을 찾는다.
    vTurnSpeed가 비어있는(0 또는 미제공) 프레임은 건너뜀.

    리턴: [{"seg","t_start","t_end","duration","max_over","vEgo_peak","vTurnSpeed_at_peak"}]
    """
    n = len(rows)
    t = [_f(r, "t") for r in rows]
    v = [_f(r, "vEgo") for r in rows]
    vt = [_f(r, "vTurnSpeed") for r in rows]
    seg = [r.get("seg") for r in rows]

    blocks = []
    cur = None
    for i in range(n):
        if t[i] is None or v[i] is None or vt[i] is None or vt[i] <= 0:
            over = False
        else:
            over = v[i] > vt[i] + margin
        if over:
            if cur is None:
                cur = {"seg": seg[i], "t_start": t[i], "t_end": t[i],
                       "max_over": v[i] - vt[i], "vEgo_peak": v[i], "vTurnSpeed_at_peak": vt[i]}
            else:
                cur["t_end"] = t[i]
                if (v[i] - vt[i]) > cur["max_over"]:
                    cur["max_over"] = v[i] - vt[i]
                    cur["vEgo_peak"] = v[i]
                    cur["vTurnSpeed_at_peak"] = vt[i]
        else:
            if cur is not None:
                blocks.append(cur)
                cur = None
    if cur is not None:
        blocks.append(cur)

    result = []
    for b in blocks:
        dur = b["t_end"] - b["t_start"]
        if dur >= min_duration_s:
            b["duration"] = round(dur, 2)
            b["max_over"] = round(b["max_over"], 2)
            result.append(b)
    return result


# ---------------------------------------------------------------------------
# 7) desiredSource(src) 전환 이력
# ---------------------------------------------------------------------------
def source_transition_log(rows):
    """
    'src' 필드가 바뀌는 시점을 순서대로 기록.
    어떤 로직(cruise/lead/turn 등)이 언제 감속/가속 판단을 주도했는지 추적용.

    리턴: [{"seg","t","from_src","to_src","vEgo","desiredSpeed"}]
    """
    transitions = []
    prev_src = None
    for r in rows:
        src = r.get("src")
        t = _f(r, "t")
        if src is None or t is None:
            continue
        if prev_src is not None and src != prev_src:
            transitions.append({
                "seg": r.get("seg"), "t": t,
                "from_src": prev_src, "to_src": src,
                "vEgo": _f(r, "vEgo"), "desiredSpeed": _f(r, "desiredSpeed"),
            })
        prev_src = src
    return transitions


# ---------------------------------------------------------------------------
# 8) 크루즈 on/off 이벤트
# ---------------------------------------------------------------------------
def cruise_engage_disengage_events(rows):
    """
    cruiseEnabled가 False<->True로 토글되는 시점을 기록하고,
    그 직전 프레임의 상태(속도/선행차/조향각)를 함께 남긴다.
    특히 disengage 원인 분석에 유용.

    리턴: [{"seg","t","event"("engage"|"disengage"),"vEgo","leadStatus",
            "steeringAngleDeg","brakePressed","gasPressed"}]
    """
    events = []
    prev_enabled = None
    for r in rows:
        enabled = _b(r, "cruiseEnabled")
        t = _f(r, "t")
        if t is None:
            continue
        if prev_enabled is not None and enabled != prev_enabled:
            events.append({
                "seg": r.get("seg"), "t": t,
                "event": "engage" if enabled else "disengage",
                "vEgo": _f(r, "vEgo"),
                "leadStatus": _b(r, "leadStatus"),
                "steeringAngleDeg": _f(r, "steeringAngleDeg"),
                "brakePressed": _b(r, "brakePressed"),
                "gasPressed": _b(r, "gasPressed"),
            })
        prev_enabled = enabled
    return events


# ---------------------------------------------------------------------------
# 9) 급브레이크 이벤트 (운전자 개입성 급감속만 분리)
# ---------------------------------------------------------------------------
def harsh_brake_events(rows, accel_drop_thresh=-0.8, window_s=0.5):
    """
    brakePressed=True 이면서, window_s 이내에 aEgo가 accel_drop_thresh
    이하로 급격히 떨어지는 순간들을 이벤트로 기록.
    clean_decel_blocks(시스템 감속 포함 전체)와 달리, 운전자가 직접
    브레이크를 밟은 급감속만 골라내기 위한 함수.

    리턴: [{"seg","t","aEgo","vEgo"}]
    """
    events = []
    n = len(rows)
    for i, r in enumerate(rows):
        if not _b(r, "brakePressed"):
            continue
        a = _f(r, "aEgo")
        if a is None or a > accel_drop_thresh:
            continue
        t = _f(r, "t")
        # 같은 급감속 구간 내 중복 이벤트 방지: 직전 이벤트와 window_s 이내면 skip
        if events and events[-1]["seg"] == r.get("seg") and (t - events[-1]["t"]) < window_s:
            continue
        events.append({"seg": r.get("seg"), "t": t, "aEgo": a, "vEgo": _f(r, "vEgo")})
    return events


# ---------------------------------------------------------------------------
# 10) 선행차 끼어들기(cut-in) 감지
# ---------------------------------------------------------------------------
def lead_cut_in_detector(rows, close_dist_m=20.0):
    """
    leadStatus가 False -> True 로 바뀌는 순간, 새로 잡힌 선행차의 leadDRel이
    처음부터 close_dist_m 이내인 경우 (즉 먼 거리에서 서서히 잡힌 게 아니라
    이미 가까운 상태로 갑자기 나타난 경우) cut-in 후보로 기록.

    리턴: [{"seg","t","leadDRel","leadVRel","vEgo"}]
    """
    events = []
    prev_lead = None
    for r in rows:
        lead = _b(r, "leadStatus")
        t = _f(r, "t")
        if t is None:
            continue
        if prev_lead is False and lead is True:
            dRel = _f(r, "leadDRel")
            if dRel is not None and dRel <= close_dist_m:
                events.append({
                    "seg": r.get("seg"), "t": t,
                    "leadDRel": dRel, "leadVRel": _f(r, "leadVRel"),
                    "vEgo": _f(r, "vEgo"),
                })
        prev_lead = lead
    return events


# ---------------------------------------------------------------------------
# 11) 전체 구간 요약 통계
# ---------------------------------------------------------------------------
def trip_summary(rows):
    """
    라우트 전체에 대한 한 눈에 보는 요약.
    다른 분석 함수들(clean_decel_blocks, harsh_brake_events,
    cruise_engage_disengage_events)의 결과를 취합해서 리턴.

    거리(km)는 vEgo(m/s)를 프레임 간 dt로 적분해 근사.
    """
    n = len(rows)
    if n == 0:
        return {}

    times = [_f(r, "t") for r in rows]
    speeds = [_f(r, "vEgo", 0.0) or 0.0 for r in rows]
    enabled_cnt = sum(1 for r in rows if _b(r, "cruiseEnabled"))
    brake_cnt = sum(1 for r in rows if _b(r, "brakePressed"))
    gas_cnt = sum(1 for r in rows if _b(r, "gasPressed"))

    dist_m = 0.0
    for i in range(1, n):
        if times[i] is None or times[i - 1] is None:
            continue
        dt = times[i] - times[i - 1]
        if 0 < dt < 1.0:  # 세그먼트 경계 등 비정상 dt 제외
            dist_m += speeds[i] * dt

    valid_times = [t for t in times if t is not None]
    duration_s = (valid_times[-1] - valid_times[0]) if len(valid_times) >= 2 else 0.0

    decels = clean_decel_blocks(rows)
    harsh_brakes = harsh_brake_events(rows)
    cruise_events = cruise_engage_disengage_events(rows)
    disengages = [e for e in cruise_events if e["event"] == "disengage"]

    return {
        "n_frames": n,
        "duration_s": round(duration_s, 1),
        "distance_km": round(dist_m / 1000, 2),
        "avg_speed_kmh": round((dist_m / duration_s) * 3.6, 1) if duration_s > 0 else 0,
        "cruise_enabled_ratio": round(enabled_cnt / n, 3),
        "brake_pressed_ratio": round(brake_cnt / n, 3),
        "gas_pressed_ratio": round(gas_cnt / n, 3),
        "n_decel_blocks": len(decels),
        "n_harsh_brake_events": len(harsh_brakes),
        "n_cruise_disengage_events": len(disengages),
    }


# ---------------------------------------------------------------------------
# 12) 조향 진동/오버슈트 감지
# ---------------------------------------------------------------------------
def steering_oscillation_detector(rows, min_reversals=3, window_s=2.0, angle_delta_thresh=3.0):
    """
    steeringAngleDeg의 부호가 window_s 안에서 min_reversals회 이상
    반전(좌->우->좌...)되는 구간을 조향 진동 후보로 탐지.
    angle_delta_thresh(deg) 미만의 미세한 변화는 반전으로 안 침 (노이즈 방지).

    리턴: [{"seg","t_start","t_end","n_reversals","max_abs_angle"}]
    """
    n = len(rows)
    t = [_f(r, "t") for r in rows]
    ang = [_f(r, "steeringAngleDeg") for r in rows]
    seg = [r.get("seg") for r in rows]

    # 방향 전환 지점 찾기
    reversal_idx = []
    last_dir = 0
    last_extreme = None
    for i in range(1, n):
        if ang[i] is None or ang[i - 1] is None or t[i] is None:
            continue
        delta = ang[i] - ang[i - 1]
        if abs(delta) < angle_delta_thresh / 10.0:  # 너무 미세한 변화 무시
            continue
        d = 1 if delta > 0 else -1
        if last_dir != 0 and d != last_dir and last_extreme is not None:
            if abs(ang[i - 1] - last_extreme) >= angle_delta_thresh:
                reversal_idx.append(i - 1)
                last_extreme = ang[i - 1]
        elif last_extreme is None:
            last_extreme = ang[i - 1]
        last_dir = d

    # window_s 안에 min_reversals 이상 몰려있는 구간을 블록으로 묶음
    blocks = []
    i = 0
    m = len(reversal_idx)
    while i < m:
        j = i
        while j + 1 < m and t[reversal_idx[j + 1]] - t[reversal_idx[i]] <= window_s:
            j += 1
        count = j - i + 1
        if count >= min_reversals:
            idxs = reversal_idx[i:j + 1]
            max_abs = max(abs(ang[k]) for k in idxs)
            blocks.append({
                "seg": seg[idxs[0]],
                "t_start": round(t[idxs[0]], 2),
                "t_end": round(t[idxs[-1]], 2),
                "n_reversals": count,
                "max_abs_angle": round(max_abs, 1),
            })
            i = j + 1
        else:
            i += 1
    return blocks


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python3 analysis_helpers.py <route.csv>")
        sys.exit(1)
    rows = load_csv(sys.argv[1])
    print(f"loaded {len(rows)} rows")
    clean = remove_driver_intervention(rows)
    print(f"after removing driver intervention: {len(clean)} rows")
    decels = clean_decel_blocks(clean)
    print(f"decel blocks: {len(decels)}")
    for b in decels[:5]:
        print(" ", b)
    print()
    print("trip summary:", trip_summary(rows))
