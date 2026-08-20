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





# ---------------------------------------------------------------------------
# 0) 비전(카메라) 인식 -> 레이더 확인 크로스오버 (2026-08-20, leadRadar/
#    leadModelProb 컬럼 추가 후 신규 작성)
# ---------------------------------------------------------------------------
def vision_to_radar_crossover(rows, min_gap_s=0.3, highway_v_ego=15.0):
    """
    "leadStatus=True 이면서 leadRadar=False (비전 모델만으로 리드 판정,
    아직 레이더 미확인) 상태"가 시작된 시점부터, 같은 리드가 이어지다가
    leadRadar=True 로 바뀌는(레이더 확인) 시점까지의 갭을 찾는다.

    사용자가 체감한 "카메라가 파란 박스로 먼저 잡았는데 감속은 레이더
    빨간 박스 뜰 때부터 시작되는 느낌"을 정량화하기 위한 함수 -- 이
    갭 동안 현재 코드가 실제로 얼마나 감속/미감속했는지는 aEgo 컬럼으로
    별도 대조해야 한다(이 함수는 갭 자체의 존재/길이/거리만 탐지).

    주의: leadRadar가 True/False로 프레임마다 흔들리는(레이더가 스팟성으로
    반짝이는) 경우가 있어, min_gap_s 이상 연속으로 leadRadar=False가
    유지된 경우만 "진짜 비전-only 구간"으로 센다(단발성 레이더 미스는
    제외). 리드가 leadStatus=False로 끊기면(새 리드) 그 크로스오버는
    미완결로 버린다.

    리턴: [{
        "seg", "t_vision_start", "t_radar_confirm", "gap_s",
        "dRel_at_vision_start", "dRel_at_radar_confirm", "dRel_closed_m",
        "vRel_at_vision_start", "vEgo_at_vision_start", "modelProb_at_vision_start",
        "highway": bool (vEgo_at_vision_start >= highway_v_ego 기준),
    }, ...]
    """
    events = []
    state = None  # {"t_start", "seg", "dRel0", "vRel0", "vEgo0", "prob0", "last_radar_false_t"}

    for r in rows:
        status = _b(r, "leadStatus") if r.get("leadStatus") != "" else False
        radar_raw = r.get("leadRadar", "")
        t = _f(r, "t")
        if t is None:
            continue

        if not status or radar_raw == "":
            # 리드 자체가 끊김 -> 진행 중이던 크로스오버는 폐기(리드 유지 전제가 깨짐)
            state = None
            continue

        is_radar = str(radar_raw).strip().lower() in ("1", "true", "t", "yes")

        if not is_radar:
            if state is None:
                state = {
                    "t_start": t, "seg": r.get("seg", ""),
                    "dRel0": _f(r, "leadDRel"), "vRel0": _f(r, "leadVRel"),
                    "vEgo0": _f(r, "vEgo"), "prob0": _f(r, "leadModelProb"),
                }
            # 비전-only 구간 계속 유지 중 -> 대기
        else:
            if state is not None and (t - state["t_start"]) >= min_gap_s:
                dRel_now = _f(r, "leadDRel")
                events.append({
                    "seg": state["seg"],
                    "t_vision_start": round(state["t_start"], 3),
                    "t_radar_confirm": round(t, 3),
                    "gap_s": round(t - state["t_start"], 3),
                    "dRel_at_vision_start": state["dRel0"],
                    "dRel_at_radar_confirm": dRel_now,
                    "dRel_closed_m": (
                        round(state["dRel0"] - dRel_now, 2)
                        if state["dRel0"] is not None and dRel_now is not None else None
                    ),
                    "vRel_at_vision_start": state["vRel0"],
                    "vEgo_at_vision_start": state["vEgo0"],
                    "modelProb_at_vision_start": state["prob0"],
                    "highway": (state["vEgo0"] or 0) >= highway_v_ego,
                })
            state = None  # 레이더 확인됐으니 이 크로스오버는 종료(다음 비전-only 구간은 새 이벤트)

    return events


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
# 4b) 커브 탈출 - 무가속 구간 스캔 v2 (260819-6 세션 오탐 대응 개선판)
# ---------------------------------------------------------------------------
def curve_exit_no_accel_scan_v2(rows, curvature_thresh=0.002, straight_thresh=0.0005,
                                 min_curve_duration_s=0.5, no_accel_window_s=2.0,
                                 accel_thresh=0.15, min_straight_hold_s=0.8,
                                 lead_exclude_dist_m=60.0):
    """
    curve_exit_no_accel_scan의 v1 대비 개선점 (260819-6 세션 오탐 분석 근거):
    1) leadStatus 필터: 커브 탈출 시점에 선행차가 잡혀있고 leadDRel이
       lead_exclude_dist_m 이내면 후보에서 제외 (감속이 선행차 추종 때문일
       가능성이 높음 -- v1에서 이 패턴으로 2건 오탐 확인됨).
    2) 직선 지속시간 강화: straight_thresh 진입 이후 min_straight_hold_s
       동안 계속 |curvature| < curvature_thresh(재상승 안 함)를 유지해야
       "진짜 탈출"로 인정. 유지 못하면(S자 연속커브 재진입) 후보에서 제외
       -- v1에서 이 패턴으로 1건 오탐 확인됨.

    리턴: v1과 동일 스키마 + "leadStatus_at_exit","leadDRel_at_exit" 추가.
    """
    n = len(rows)
    curv = [abs(_f(r, "desiredCurvature", 0.0) or 0.0) for r in rows]
    times = [_f(r, "t", 0.0) for r in rows]
    aEgo = [_f(r, "aEgo", 0.0) for r in rows]
    vEgo = [_f(r, "vEgo", 0.0) for r in rows]
    segs = [r.get("seg") for r in rows]
    lead = [_b(r, "leadStatus") for r in rows]
    dRel = [_f(r, "leadDRel") for r in rows]

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

                # -- 개선 1: leadStatus 필터
                if lead[i] and dRel[i] is not None and dRel[i] <= lead_exclude_dist_m:
                    i += 1
                    continue

                # -- 개선 2: 직선 지속시간 재확인 (재상승 여부)
                j0 = i
                hold_ok = True
                while j0 < n and segs[j0] == seg_exit and (times[j0] - t_exit) <= min_straight_hold_s:
                    if curv[j0] >= curvature_thresh:
                        hold_ok = False
                        break
                    j0 += 1
                if not hold_ok:
                    i += 1
                    continue

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
                        "leadStatus_at_exit": lead[i],
                        "leadDRel_at_exit": round(dRel[i], 1) if dRel[i] is not None else None,
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


# ---------------------------------------------------------------------------
# 12) 세그먼트 경계 leadStatus 아티팩트 탐지 (extract_log.py 구버전 CSV 감사용)
# ---------------------------------------------------------------------------
def segment_boundary_lead_loss_artifacts(rows, max_gap_s=0.06, tail_lookback_s=0.5):
    """
    extract_log.py 2026-08-21 수정 이전 버전으로 뽑은 CSV를 감사(audit)하는
    용도. 그 버전은 세그먼트가 바뀔 때마다 leadStatus를 무조건 False로
    리셋했기 때문에, 실제로는 리드가 계속 유지되고 있었는데도 새 세그먼트
    시작 시 첫 radarState 이벤트 전까지 가짜 "순간유실" row가 찍히는 구조적
    버그가 있었다 (PARAMS_REGISTRY.md LEAD_ACQ_LOSS_GRACE_TIME 항목,
    FINDINGS.md 22차 참고).

    새 버전(meta.json에 segment_state_carryover_fix=true)으로 뽑은 CSV에는
    이 아티팩트가 없으므로 이 함수를 돌릴 필요가 없다 -- load_meta()로
    먼저 확인할 것.

    판정 로직: 각 세그먼트 경계에서
      - 이전 세그먼트 마지막 row가 leadStatus=True 였고
      - 새 세그먼트 시작 시 leadStatus=False 인 row가 하나 이상 나온 뒤
        다시 leadStatus=True로 복귀하며
      - 그 복귀 시점까지의 dRel/vRel 변화가 리드가 실제로 사라졌다
        보기엔 비연속적(gap)이면
    "세그먼트 경계 아티팩트 의심"으로 표시. diff_from_boundary_s가
    0에 가까울수록(특히 <= max_gap_s) 아티팩트일 확률이 높다.

    리턴: [{
        "seg_from", "seg_to", "t_boundary_prev_true", "t_boundary_new_true",
        "false_span_s", "diff_from_boundary_s", "prev_dRel", "next_dRel",
        "suspected_artifact"(bool)
    }]
    실제 유실인지/아티팩트인지 최종 판단은 사람이 dRel 연속성 등을 보고
    한다 -- 이 함수는 "재검토 우선순위가 높은 후보"를 추려주는 용도.
    """
    # 세그먼트별로 순서를 유지한 채 그룹화
    seg_order = []
    seg_rows = {}
    for r in rows:
        seg = r.get("seg")
        if seg not in seg_rows:
            seg_rows[seg] = []
            seg_order.append(seg)
        seg_rows[seg].append(r)

    results = []
    for i in range(1, len(seg_order)):
        prev_seg, cur_seg = seg_order[i - 1], seg_order[i]
        prev_rows, cur_rows = seg_rows[prev_seg], seg_rows[cur_seg]
        if not prev_rows or not cur_rows:
            continue

        prev_last = prev_rows[-1]
        if not _b(prev_last, "leadStatus"):
            continue  # 이전 세그먼트 끝에 리드가 없었으면 경계 아티팩트 대상 아님

        t_boundary = _f(cur_rows[0], "t")
        prev_dRel = _f(prev_last, "leadDRel")

        # 새 세그먼트 시작부터 leadStatus=False가 이어지는 구간 찾기
        j = 0
        while j < len(cur_rows) and not _b(cur_rows[j], "leadStatus"):
            j += 1
        if j == 0:
            continue  # 바로 True로 시작 -> 아티팩트 없음
        if j >= len(cur_rows):
            continue  # 세그먼트 전체가 leadStatus=False -> 진짜 유실일 가능성이 높아 제외

        t_first_false = _f(cur_rows[0], "t")
        t_new_true = _f(cur_rows[j], "t")
        next_dRel = _f(cur_rows[j], "leadDRel")
        false_span_s = round(t_new_true - t_first_false, 3) if (t_new_true is not None and t_first_false is not None) else None
        diff_from_boundary_s = round(t_first_false - t_boundary, 3) if (t_first_false is not None and t_boundary is not None) else None

        suspected = diff_from_boundary_s is not None and abs(diff_from_boundary_s) <= max_gap_s

        results.append({
            "seg_from": prev_seg, "seg_to": cur_seg,
            "t_boundary_prev_true": round(_f(prev_last, "t"), 3) if _f(prev_last, "t") is not None else None,
            "t_boundary_new_true": round(t_new_true, 3) if t_new_true is not None else None,
            "false_span_s": false_span_s,
            "diff_from_boundary_s": diff_from_boundary_s,
            "prev_dRel": round(prev_dRel, 2) if prev_dRel is not None else None,
            "next_dRel": round(next_dRel, 2) if next_dRel is not None else None,
            "suspected_artifact": suspected,
        })
    return results


# ---------------------------------------------------------------------------
# 13) TTC(Time-To-Collision) 위험 구간 탐지
# ---------------------------------------------------------------------------
def ttc_danger_events(rows, ttc_thresh=2.5, min_closing_vrel=0.1, min_duration_s=0.0):
    """
    레이더 기반 raw TTC = leadDRel / (-leadVRel) (vRel<0, 즉 접근 중일 때만
    정의됨)가 ttc_thresh 이하로 내려가는 구간을 찾는다.
    LEAD_ACQ_TTC_DANGER(기본 2.5s) 등 위험 문턱 검증용 -- 실제 DANGER
    케이스가 로그에 있는지 여러 CSV를 일괄 스캔할 때 사용.

    min_closing_vrel(m/s): 이 값보다 느리게 접근하는 경우는 노이즈로 보고
    제외 (정지 상태에서 vRel이 미세하게 음수로 흔들리는 것 방지).

    리턴: [{"seg","t_start","t_end","duration","min_ttc","dRel_at_min_ttc",
            "vRel_at_min_ttc","vEgo_at_min_ttc"}]
    """
    n = len(rows)
    t = [_f(r, "t") for r in rows]
    lead = [_b(r, "leadStatus") for r in rows]
    dRel = [_f(r, "leadDRel") for r in rows]
    vRel = [_f(r, "leadVRel") for r in rows]
    vEgo = [_f(r, "vEgo") for r in rows]
    seg = [r.get("seg") for r in rows]

    events = []
    cur = None
    for i in range(n):
        ttc = None
        if lead[i] and dRel[i] is not None and vRel[i] is not None and vRel[i] <= -min_closing_vrel:
            ttc = dRel[i] / (-vRel[i])
        danger = ttc is not None and ttc <= ttc_thresh
        if danger:
            if cur is None:
                cur = {"seg": seg[i], "t_start": t[i], "t_end": t[i],
                       "min_ttc": ttc, "dRel_at_min_ttc": dRel[i],
                       "vRel_at_min_ttc": vRel[i], "vEgo_at_min_ttc": vEgo[i]}
            else:
                cur["t_end"] = t[i]
                if ttc < cur["min_ttc"]:
                    cur["min_ttc"] = ttc
                    cur["dRel_at_min_ttc"] = dRel[i]
                    cur["vRel_at_min_ttc"] = vRel[i]
                    cur["vEgo_at_min_ttc"] = vEgo[i]
        else:
            if cur is not None:
                events.append(cur)
                cur = None
    if cur is not None:
        events.append(cur)

    result = []
    for e in events:
        dur = e["t_end"] - e["t_start"]
        if dur >= min_duration_s:
            e["duration"] = round(dur, 2)
            e["min_ttc"] = round(e["min_ttc"], 2)
            if e["dRel_at_min_ttc"] is not None:
                e["dRel_at_min_ttc"] = round(e["dRel_at_min_ttc"], 2)
            if e["vRel_at_min_ttc"] is not None:
                e["vRel_at_min_ttc"] = round(e["vRel_at_min_ttc"], 2)
            if e["vEgo_at_min_ttc"] is not None:
                e["vEgo_at_min_ttc"] = round(e["vEgo_at_min_ttc"], 2)
            result.append(e)
    return result


def scan_routes_for_ttc_danger(csv_paths, ttc_thresh=2.5, min_closing_vrel=0.1):
    """
    여러 route.csv 경로를 한 번에 스캔해 ttc_danger_events()를 합쳐 리턴.
    "희귀 이벤트(고속 근접추종 TTC DANGER) 배치 스캐너" 용도 -- 지금까지
    한 건도 못 찾은 DANGER 케이스를 여러 라우트에 걸쳐 한 번에 찾을 때 사용.

    리턴: {"<csv_path>": [이벤트...], ...} + "_summary": {"n_routes","n_events_total"}
    """
    out = {}
    total = 0
    for path in csv_paths:
        rows = load_csv(path)
        events = ttc_danger_events(rows, ttc_thresh=ttc_thresh, min_closing_vrel=min_closing_vrel)
        out[path] = events
        total += len(events)
    out["_summary"] = {"n_routes": len(csv_paths), "n_events_total": total}
    return out


# ---------------------------------------------------------------------------
# 14) 패치 전/후 회귀 리포트
# ---------------------------------------------------------------------------
def _jerk_stats(rows):
    """운전자 개입 제외 후 aEgo의 프레임간 변화율(jerk, m/s^3) 통계."""
    clean = remove_driver_intervention(rows)
    t = [_f(r, "t") for r in clean]
    a = [_f(r, "aEgo") for r in clean]
    jerks = []
    for i in range(1, len(clean)):
        if t[i] is None or t[i - 1] is None or a[i] is None or a[i - 1] is None:
            continue
        dt = t[i] - t[i - 1]
        if 0 < dt < 1.0:  # 세그먼트 경계 등 비정상 dt 제외
            jerks.append((a[i] - a[i - 1]) / dt)
    if not jerks:
        return {"max_abs_jerk": None, "jerk_std": None, "n_samples": 0}
    mean_j = sum(jerks) / len(jerks)
    var = sum((j - mean_j) ** 2 for j in jerks) / len(jerks)
    return {
        "max_abs_jerk": round(max(abs(j) for j in jerks), 3),
        "jerk_std": round(var ** 0.5, 3),
        "n_samples": len(jerks),
    }


def _route_metrics(rows, src_pair=("vturn", "model"), ttc_thresh=2.5):
    """단일 라우트 CSV(rows)에 대한 회귀 리포트용 표준 지표 세트."""
    summary = trip_summary(rows)
    duration_min = summary.get("duration_s", 0) / 60.0 if summary else 0.0

    harsh = harsh_brake_events(rows)
    violations = turn_speed_violations(rows)
    transitions = source_transition_log(rows)
    pair_transitions = [
        tr for tr in transitions
        if {tr["from_src"], tr["to_src"]} == set(src_pair)
    ]
    ttc_events = ttc_danger_events(rows, ttc_thresh=ttc_thresh)
    jerk = _jerk_stats(rows)

    def _per_min(count):
        return round(count / duration_min, 2) if duration_min > 0 else None

    return {
        "duration_min": round(duration_min, 1),
        "distance_km": summary.get("distance_km"),
        "n_harsh_brake_events": len(harsh),
        "harsh_brake_per_min": _per_min(len(harsh)),
        "n_turn_speed_violations": len(violations),
        "turn_speed_violation_per_min": _per_min(len(violations)),
        "n_src_transitions_total": len(transitions),
        "src_transitions_total_per_min": _per_min(len(transitions)),
        f"n_src_flicker_{src_pair[0]}_{src_pair[1]}": len(pair_transitions),
        f"src_flicker_{src_pair[0]}_{src_pair[1]}_per_min": _per_min(len(pair_transitions)),
        "n_ttc_danger_events": len(ttc_events),
        "ttc_danger_events": ttc_events,  # 상세 내역, 표본 0건 확인 등에 필요
        "max_abs_jerk": jerk["max_abs_jerk"],
        "jerk_std": jerk["jerk_std"],
    }


def regression_report(rows_before, rows_after, before_label="before", after_label="after",
                       src_pair=("vturn", "model"), ttc_thresh=2.5):
    """
    패치 전/후 route CSV(rows_before/rows_after, load_csv() 결과)를 받아
    표준 지표(플리커율/harsh_brake율/turn_speed_violation율/TTC danger
    건수/jerk 통계)를 자동으로 계산 + diff. 세션마다 "회귀 없음"을 손으로
    세던 걸 대체하는 용도(17/19/23차 반복 패턴).

    비교 가능하도록 대부분 지표는 분당(per_min) 비율로 정규화한다
    (전/후 라우트 길이가 다를 수 있으므로 절대 건수만 비교하면 오해 소지).

    src_pair: 플리커 추적할 소스 쌍 (기본 vturn/model -- 지금까지 가장
    많이 검증된 쌍). 다른 쌍(road/route 등) 검증 시 인자로 바꿔서 재사용.

    리턴: {"before": {...}, "after": {...}, "delta_pct": {지표별 변화율(%)}}
    delta_pct는 양수 = after가 더 큼(악화 여부는 지표에 따라 사람이 판단
    -- 예: harsh_brake_per_min 증가는 나쁜 신호, 이건 함수가 자동 판단 안 함).
    """
    before = _route_metrics(rows_before, src_pair=src_pair, ttc_thresh=ttc_thresh)
    after = _route_metrics(rows_after, src_pair=src_pair, ttc_thresh=ttc_thresh)

    delta_pct = {}
    for key in before:
        bv, av = before.get(key), after.get(key)
        if isinstance(bv, (int, float)) and isinstance(av, (int, float)):
            if bv == 0:
                delta_pct[key] = None if av == 0 else float("inf")
            else:
                delta_pct[key] = round((av - bv) / abs(bv) * 100, 1)

    return {before_label: before, after_label: after, "delta_pct": delta_pct}


def regression_report_markdown(report, before_label="before", after_label="after"):
    """
    regression_report()의 리턴값을 FINDINGS.md/PARAMS_REGISTRY.md에 바로
    붙여넣기 좋은 마크다운 표로 변환. ttc_danger_events 상세 리스트는
    표에서 제외(건수만 표시) -- 필요하면 report[label]["ttc_danger_events"]
    를 따로 확인.
    """
    before = report[before_label]
    after = report[after_label]
    delta = report["delta_pct"]

    rows_order = [
        ("duration_min", "라우트 길이(분)"),
        ("distance_km", "거리(km)"),
        ("harsh_brake_per_min", "harsh_brake/분"),
        ("turn_speed_violation_per_min", "커브속도위반/분"),
        ("src_transitions_total_per_min", "소스전환(전체)/분"),
        (None, None),  # placeholder replaced below for pair-specific key
        ("n_ttc_danger_events", "TTC DANGER 건수"),
        ("max_abs_jerk", "최대|jerk| (m/s^3)"),
        ("jerk_std", "jerk 표준편차"),
    ]
    pair_key = next((k for k in before if k.startswith("src_flicker_") and k.endswith("_per_min")), None)
    if pair_key:
        rows_order[5] = (pair_key, f"{pair_key.replace('src_flicker_', '').replace('_per_min', '')} 플리커/분")

    lines = [f"| 지표 | {before_label} | {after_label} | 변화율 |", "|---|---|---|---|"]
    for key, label in rows_order:
        if key is None:
            continue
        bv, av, dv = before.get(key), after.get(key), delta.get(key)
        dv_str = "N/A" if dv is None else ("+inf" if dv == float("inf") else f"{dv:+.1f}%")
        lines.append(f"| {label} | {bv} | {av} | {dv_str} |")
    return "\n".join(lines)


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
