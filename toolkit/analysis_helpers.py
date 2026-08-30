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
# 4c) 커브 탈출 - 무가속 구간 스캔 v3 (260819-7 세션 vCruiseCluster 캡 오탐 대응)
# ---------------------------------------------------------------------------
def curve_exit_no_accel_scan_v3(rows, curvature_thresh=0.002, straight_thresh=0.0005,
                                 min_curve_duration_s=0.5, no_accel_window_s=2.0,
                                 accel_thresh=0.15, min_straight_hold_s=0.8,
                                 lead_exclude_dist_m=60.0, cap_margin_thresh_kph=5.0):
    """
    curve_exit_no_accel_scan_v2 대비 개선점 (260819-7 세션, FINDINGS.md
    "[INVESTIGATING] curve_exit_no_accel_scan v1의 3번째 오탐 패턴" 항목 근거):

    3) vCruiseCluster 캡 여유폭 필터: 탈출 시점의
       min(vCruiseCluster, desiredSpeed) - vEgo(kph 환산) 여유폭이
       cap_margin_thresh_kph 미만이면, vTurnSpeed/desiredSpeed 자체가
       이미 회복됐어도 controlsd.py `desired_kph = min(CS.vCruiseCluster,
       carrotMan.desiredSpeed)` 캡 때문에 애초에 가속할 여지가 거의 없는
       정상 상황이므로 후보에서 제외한다.

       주의: 반드시 "vCruiseCluster" 필드를 써야 함 -- "vCruise"는 이름은
       비슷하지만 controlsd.py가 실제로 캡에 쓰는 값이 아닌 별개 필드
       (extract_log.py 47차 참고). vCruiseCluster가 로그에 없는(구버전
       CSV) row는 이 필터를 건너뛰고 v2와 동일하게 처리한다(캡 오탐
       제외를 못하므로 과탐 방향으로만 치우침 -- 안전 쪽 fallback).

    리턴: v2와 동일 스키마 + "vCruiseCluster_at_exit", "cap_margin_kph_at_exit" 추가.
    (margin 계산이 불가능했던 row는 두 필드 모두 None.)
    """
    n = len(rows)
    curv = [abs(_f(r, "desiredCurvature", 0.0) or 0.0) for r in rows]
    times = [_f(r, "t", 0.0) for r in rows]
    aEgo = [_f(r, "aEgo", 0.0) for r in rows]
    vEgo = [_f(r, "vEgo", 0.0) for r in rows]
    segs = [r.get("seg") for r in rows]
    lead = [_b(r, "leadStatus") for r in rows]
    dRel = [_f(r, "leadDRel") for r in rows]
    vCruiseCluster = [_f(r, "vCruiseCluster") for r in rows]
    desiredSpeed = [_f(r, "desiredSpeed") for r in rows]

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

                # -- 개선 1 (v2): leadStatus 필터
                if lead[i] and dRel[i] is not None and dRel[i] <= lead_exclude_dist_m:
                    i += 1
                    continue

                # -- 개선 2 (v2): 직선 지속시간 재확인 (재상승 여부)
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

                # -- 개선 3 (v3, 신규): vCruiseCluster 캡 여유폭 필터
                vcc = vCruiseCluster[i]
                dspd = desiredSpeed[i]
                cap_margin = None
                if vcc is not None and dspd is not None and vEgo[i] is not None:
                    target_kph = min(vcc, dspd)
                    cap_margin = target_kph - (vEgo[i] * 3.6)
                    if cap_margin < cap_margin_thresh_kph:
                        i += 1
                        continue
                # vcc/dspd 중 하나라도 없으면(구버전 CSV) 필터 스킵 -- v2와
                # 동일하게 처리(안전 쪽 fallback, 위 docstring 참고).

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
                        "vCruiseCluster_at_exit": round(vcc, 1) if vcc is not None else None,
                        "cap_margin_kph_at_exit": round(cap_margin, 1) if cap_margin is not None else None,
                    })
        i += 1
    return results


def curve_exit_no_accel_scan_v4(rows, curvature_thresh=0.002, straight_thresh=0.0005,
                                 min_curve_duration_s=0.5, no_accel_window_s=2.0,
                                 accel_thresh=0.15, min_straight_hold_s=0.8,
                                 lead_exclude_dist_m=60.0, cap_margin_thresh_kph=6.5,
                                 min_vego_at_exit_mps=1.0):
    """
    curve_exit_no_accel_scan_v3 대비 개선점 (2026-08-23, 48차, route6/7/8
    실전 검증 근거 — FINDINGS.md "48차" 항목 참고):

    4) vEgo 최소속도 필터: `vEgo_at_exit`가 `min_vego_at_exit_mps` 미만이면
       (사실상 정차) 곡률 임계값이 우연히 넘은 경우를 배제한다. 정차 중
       조향각/곡률 계산이 튀는 건 "커브"가 아니므로 애초에 v3 스캐너의
       대상이 아니다 (48차 route7 seg18 t=1176.94, vEgo≈0 오탐으로 신규
       발견).

    5) `cap_margin_thresh_kph` 기본값을 5.0 -> 6.5로 상향. 48차에서
       route7 seg12(t=833.54, margin=6.0)/seg14(t=949.09, margin=5.8)
       두 근접 후보를 CSV 원본(vTurnSpeed/src 필드)으로 직접 대조한 결과,
       **두 건 모두 vTurnSpeed 자체는 이미 완전히 해제(각각 -201/-187,
       즉 200km/h 안팎으로 사실상 무제한)된 상태였고, desiredSpeed를
       최종 제한하는 건 오직 vCruiseCluster(운전자 설정 순항속도) 캡
       뿐**이었음이 확인됨 — 즉 vturn_speed()의 lookahead/필터 로직과는
       처음부터 무관한, 순수 "여유폭이 작아서 완만히만 가속하는" 정상
       상황. 문턱 5.0은 이런 경계 사례(5.8~6.0)를 걸러내기엔 살짝
       빡빡했던 것으로 판단, 6.5로 상향해 route7의 두 근접 후보를 v4
       단계에서 정식 제외한다.

    이 두 변경을 적용한 결과 route6(ADAS 미관여 제외)/7/8 3개 route
    전부 0건으로 수렴함(48차 실측 확인, FINDINGS.md 참고).

    리턴: v3와 동일 스키마.
    """
    n = len(rows)
    curv = [abs(_f(r, "desiredCurvature", 0.0) or 0.0) for r in rows]
    times = [_f(r, "t", 0.0) for r in rows]
    aEgo = [_f(r, "aEgo", 0.0) for r in rows]
    vEgo = [_f(r, "vEgo", 0.0) for r in rows]
    segs = [r.get("seg") for r in rows]
    lead = [_b(r, "leadStatus") for r in rows]
    dRel = [_f(r, "leadDRel") for r in rows]
    vCruiseCluster = [_f(r, "vCruiseCluster") for r in rows]
    desiredSpeed = [_f(r, "desiredSpeed") for r in rows]

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

                # -- v4 신규: 정차(사실상 vEgo=0) 상태 배제
                if vEgo[i] is None or vEgo[i] < min_vego_at_exit_mps:
                    i += 1
                    continue

                # -- v2: leadStatus 필터
                if lead[i] and dRel[i] is not None and dRel[i] <= lead_exclude_dist_m:
                    i += 1
                    continue

                # -- v2: 직선 지속시간 재확인 (재상승 여부)
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

                # -- v3, v4에서 문턱만 상향(5.0 -> 6.5): vCruiseCluster 캡 여유폭 필터
                vcc = vCruiseCluster[i]
                dspd = desiredSpeed[i]
                cap_margin = None
                if vcc is not None and dspd is not None and vEgo[i] is not None:
                    target_kph = min(vcc, dspd)
                    cap_margin = target_kph - (vEgo[i] * 3.6)
                    if cap_margin < cap_margin_thresh_kph:
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
                        "vCruiseCluster_at_exit": round(vcc, 1) if vcc is not None else None,
                        "cap_margin_kph_at_exit": round(cap_margin, 1) if cap_margin is not None else None,
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

    **단위 주의(2026-08-23, 51차 버그 수정)**: CSV의 vEgo는 m/s
    (carState 원본 그대로), desiredSpeed/vTurnSpeed/vCruise는 km/h
    (carrotMan 메시지 원본, int(...)로 로깅됨) — 서로 단위가 다르다.
    이 함수는 내부적으로 vEgo를 *3.6 해서 km/h로 맞춘 뒤 비교한다.
    error/target/frames의 "vEgo"/"error"는 모두 km/h 기준.
    (구버전은 vEgo(m/s)를 변환 없이 비교해 오차값이 사실상 무의미했음
    — turn_speed_violations()도 동일 버그로 함께 수정, PARAMS_REGISTRY
    /FINDINGS.md 51차 항목 참고.)

    리턴: {"frames": [{"t","seg","vEgo","target","error"}...],
           "summary": [{"seg","t_start","t_end","mean_abs_error","max_abs_error"}...]}
    ("vEgo"/"error"는 km/h 단위)
    """
    frames = []
    for r in rows:
        v = _f(r, "vEgo")
        tgt = _f(r, target_field)
        t = _f(r, "t")
        if v is None or tgt is None or t is None:
            continue
        v_kph = v * 3.6
        frames.append({"t": t, "seg": r.get("seg"), "vEgo": v_kph, "target": tgt, "error": v_kph - tgt})

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
def turn_speed_violations(rows, margin=2.0, min_duration_s=0.3):
    """
    vEgo > vTurnSpeed + margin (km/h) 인 구간을 찾는다.
    vTurnSpeed가 비어있는(0 또는 미제공) 프레임은 건너뜀.

    **단위 버그 수정(2026-08-23, 51차)**: 구버전은 vEgo(m/s)를 변환 없이
    vTurnSpeed(km/h)와 직접 비교해 사실상 항상 미발동(false negative)
    상태였음 — vEgo가 km/h로 환산해도 vTurnSpeed보다 낮은 정상 상황에서도
    m/s 값 자체는 항상 vTurnSpeed(km/h, 보통 30~250대)보다 작아 조건식이
    거의 발동 불가능한 구조였다. 이 버전은 vEgo를 *3.6 km/h로 환산 후
    비교한다. margin도 기존 0.5(단위 불명확)에서 2.0 km/h로 재정의
    (turn_speed_violations()를 참조하던 route_summary.py 등 과거 결과는
    재검증 필요 — PARAMS_REGISTRY.md/FINDINGS.md 51차 항목 참고).

    리턴: [{"seg","t_start","t_end","duration","max_over","vEgo_peak","vTurnSpeed_at_peak"}]
    (vEgo_peak은 km/h 단위로 리턴됨 — 구버전은 m/s였음)
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
            v_kph = None
        else:
            v_kph = v[i] * 3.6
            over = v_kph > abs(vt[i]) + margin
        if over:
            if cur is None:
                cur = {"seg": seg[i], "t_start": t[i], "t_end": t[i],
                       "max_over": v_kph - abs(vt[i]), "vEgo_peak": v_kph, "vTurnSpeed_at_peak": vt[i]}
            else:
                cur["t_end"] = t[i]
                if (v_kph - abs(vt[i])) > cur["max_over"]:
                    cur["max_over"] = v_kph - abs(vt[i])
                    cur["vEgo_peak"] = v_kph
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


def source_target_violations(rows, src_name, target_field="desiredSpeed", margin=2.0, min_duration_s=0.3):
    """
    turn_speed_violations()의 일반화 버전. vTurnSpeed 고정이 아니라
    임의의 desiredSource(src_name)가 선택돼 있는 구간에서 vEgo가
    target_field(기본 desiredSpeed, km/h) + margin(km/h)을 초과하는 블록을 찾는다.

    예: route(내비 경로) 감속 후보의 실제 준수 여부를 보려면
        source_target_violations(rows, "route")

    **단위 주의**: CSV의 vEgo는 m/s, desiredSpeed/vTurnSpeed는 km/h —
    이 함수는 내부적으로 vEgo를 *3.6 해서 km/h로 맞춰 비교한다
    (turn_speed_violations()와 동일한 51차 단위 수정 적용, 처음부터
    올바른 단위로 작성됨).
    src_name이 아닌 프레임, target_field가 비어있거나(<=0) 프레임은 건너뜀
    (해당 구간에서는 위반 판정을 하지 않고 블록을 끊는다 — turn_speed_violations와
    동일한 규칙).

    리턴: [{"seg","t_start","t_end","duration","max_over","vEgo_peak","target_at_peak"}]
    (vEgo_peak은 km/h 단위)
    """
    n = len(rows)
    t = [_f(r, "t") for r in rows]
    v = [_f(r, "vEgo") for r in rows]
    tgt = [_f(r, target_field) for r in rows]
    src = [r.get("src") for r in rows]
    seg = [r.get("seg") for r in rows]

    blocks = []
    cur = None
    for i in range(n):
        active = src[i] == src_name
        if not active or t[i] is None or v[i] is None or tgt[i] is None or tgt[i] <= 0:
            over = False
            v_kph = None
        else:
            v_kph = v[i] * 3.6
            over = v_kph > tgt[i] + margin
        if over:
            if cur is None:
                cur = {"seg": seg[i], "t_start": t[i], "t_end": t[i],
                       "max_over": v_kph - tgt[i], "vEgo_peak": v_kph, "target_at_peak": tgt[i]}
            else:
                cur["t_end"] = t[i]
                if (v_kph - tgt[i]) > cur["max_over"]:
                    cur["max_over"] = v_kph - tgt[i]
                    cur["vEgo_peak"] = v_kph
                    cur["target_at_peak"] = tgt[i]
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


def route_target_jump_events(rows, jump_thresh_kph=8.0, max_dt_s=0.5):
    """
    src=='route'(내비 경로 감속 후보) 구간에서 desiredSpeed(=이 구간에서는
    route_speed 산출값과 동일)가 짧은 시간 안에 큰 폭으로 튀는 지점을 찾는다.
    carrot_navi_route()의 역순 시간지연(time_delay/time_wait) 스무딩이
    매 프레임 재계산되며 GPS 경로점/곡률 추정 노이즈로 불연속을 만드는지
    확인하는 용도(vturn 쪽의 curve_noise_summary_refined()에 대응하는
    route 버전).

    연속 두 프레임이 같은 seg 내에서 dt<=max_dt_s이고
    |Δ desiredSpeed| >= jump_thresh_kph 이면 이벤트로 기록.
    src가 route가 아닌 프레임을 만나면 연속성이 끊긴 것으로 보고 리셋.

    리턴: [{"seg","t","dt","d_desiredSpeed","before","after"}]
    """
    events = []
    prev = None
    for r in rows:
        if r.get("src") != "route":
            prev = None
            continue
        t = _f(r, "t")
        v = _f(r, "desiredSpeed")
        seg = r.get("seg")
        if t is None or v is None:
            prev = None
            continue
        if prev is not None and prev["seg"] == seg:
            dt = t - prev["t"]
            dv = v - prev["v"]
            if 0 < dt <= max_dt_s and abs(dv) >= jump_thresh_kph:
                events.append({
                    "seg": seg, "t": round(t, 2), "dt": round(dt, 2),
                    "d_desiredSpeed": round(dv, 2),
                    "before": round(prev["v"], 1), "after": round(v, 1),
                })
        prev = {"t": t, "v": v, "seg": seg}
    return events


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
# 7-1) min() 소스 선택 히스테리시스 — 임의의 두 소스 쌍 플리커 정량화 (범용 스캐너)
# ---------------------------------------------------------------------------
def source_pair_flicker_stats(rows, src_a, src_b, transitions=None):
    """
    src_a<->src_b 두 소스 사이의 전환만 골라 플리커를 정량화.

    지금까지(9~20차) vturn<->model/road/route 등 특정 쌍의 플리커 건수를
    세션마다 손으로 골라 세었던 걸 대체하는 범용 함수 — 임의의 두 소스명을
    넣으면 동일한 지표를 계산해준다. transitions를 미리 계산해뒀으면
    (예: all_source_pairs_flicker_summary에서 재사용) 넘겨서 재계산을 피할 수 있음.

    "A->B->A 왕복"은 해당 쌍 내에서 연속된 두 전환이 정확히 역방향일 때만
    카운트한다 (즉 그 사이에 제3의 소스가 끼면 왕복으로 안 침 — 진짜 진동만
    잡기 위함). dwell(체류 시간)은 그 쌍에 속한 연속 전환들 사이의 시간차.

    리턴: {
        "pair": "A<->B",
        "transition_count": int,   # A->B + B->A 전체
        "round_trip_count": int,   # A->B->A 또는 B->A->B (연속, 사이에 다른 src 없음)
        "route_duration_min": float or None,
        "rate_per_min": float or None,   # transition_count / route_duration_min
        "dwell_stats": {"min","median","max","n"} or None,  # 초 단위
        "events": [...]  # source_transition_log 형식 그대로, 이 쌍만 필터링
    }
    """
    if transitions is None:
        transitions = source_transition_log(rows)

    pair_set = {src_a, src_b}
    relevant = [t for t in transitions if {t["from_src"], t["to_src"]} == pair_set]

    round_trip_count = 0
    dwells = []
    for i in range(len(relevant) - 1):
        cur, nxt = relevant[i], relevant[i + 1]
        dt = nxt["t"] - cur["t"]
        dwells.append(dt)
        # 정확히 역방향 전환이 곧바로 이어지면 왕복(A->B->A)으로 카운트
        if cur["from_src"] == nxt["to_src"] and cur["to_src"] == nxt["from_src"]:
            round_trip_count += 1

    ts = [_f(r, "t") for r in rows if _f(r, "t") is not None]
    duration_min = (max(ts) - min(ts)) / 60.0 if ts else None

    dwell_stats = None
    if dwells:
        sd = sorted(dwells)
        n = len(sd)
        dwell_stats = {
            "min": round(sd[0], 2),
            "median": round(sd[n // 2], 2),
            "max": round(sd[-1], 2),
            "n": n,
        }

    return {
        "pair": f"{src_a}<->{src_b}",
        "transition_count": len(relevant),
        "round_trip_count": round_trip_count,
        "route_duration_min": round(duration_min, 2) if duration_min is not None else None,
        "rate_per_min": (
            round(len(relevant) / duration_min, 2)
            if duration_min and duration_min > 0 else None
        ),
        "dwell_stats": dwell_stats,
        "events": relevant,
    }


def all_source_pairs_flicker_summary(rows, min_count=3):
    """
    rows에 등장하는 모든 src 값에 대해 가능한 모든 쌍(A<->B)의 플리커를
    자동 스캔해 건수 내림차순으로 정렬해 리턴. "우세 쌍이 뭔지" 세션마다
    수동으로 찾던 과정(예: 260819-4 세션의 model<->vturn 140건 수동 집계)을
    자동화 — road<->route 등 이제껏 따로 집계된 적 없는 쌍도 여기서 함께 나온다.

    min_count: 이 건수 미만인 쌍은 결과에서 제외(노이즈성 1~2건 전환 제거용).

    리턴: [source_pair_flicker_stats(...), ...] (transition_count 내림차순),
          각 항목의 "events" 키는 용량 절약을 위해 제거하고 대신 전체를
          별도로 얻고 싶으면 source_pair_flicker_stats()를 그 쌍에 대해
          직접 재호출.
    """
    transitions = source_transition_log(rows)
    srcs = set()
    for t in transitions:
        srcs.add(t["from_src"])
        srcs.add(t["to_src"])
    srcs = sorted(srcs)

    results = []
    for i in range(len(srcs)):
        for j in range(i + 1, len(srcs)):
            stats = source_pair_flicker_stats(rows, srcs[i], srcs[j], transitions=transitions)
            if stats["transition_count"] >= min_count:
                stats = dict(stats)
                stats.pop("events", None)
                results.append(stats)

    results.sort(key=lambda s: s["transition_count"], reverse=True)
    return results


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
def congestion_stop_launch_lurch_scan(rows, stop_v_ego=0.3, congestion_window_s=60.0,
                                       congestion_stop_count_thresh=2,
                                       ttc_danger_thresh=2.5, min_closing_vrel=0.1,
                                       congestion_min_closing_for_danger=3.0,
                                       post_jerk_window_s=1.5):
    """
    (2026-08-23, 58차 2번 신규) "정체구간 붕끗" 근본원인 가설 검증용 스캐너.
    58차 2번 WIP 설계를 그대로 로그 위에서 재현:

    1. "정체(congestion)" 상태 추적 -- 최근 congestion_window_s초 이내
       v_ego가 stop_v_ego 밑으로 새로 진입(정차)한 횟수가
       congestion_stop_count_thresh 이상이면 congestion_active=True.
    2. congestion_active 구간에서 TTC(=dRel/-vRel) <= ttc_danger_thresh인
       기존 danger override 발동 시점(LEAD_ACQ_TTC_DANGER, 기존 로직)을
       찾되, 그중 실제 closing 속도(|vRel|)가
       congestion_min_closing_for_danger 미만인 "완만한 접근"만 후보로
       추림 -- 이게 바로 58차 2번이 "오판"으로 규정한 케이스(설계상
       패치 후엔 danger override가 억제되어야 할 대상).
       |vRel| >= congestion_min_closing_for_danger는 "진짜 위험"으로
       간주해 후보에서 제외(설계 원칙: 안전 설계는 그대로 유지).
    3. 각 후보 시점 이후 post_jerk_window_s 이내 aEgo 최대 낙폭(가장
       음의 방향 변화)을 "체감 붕끗 강도"로 같이 리포트.

    입력: extract_log.py CSV rows.
    리턴: [{"seg","t","dRel","vRel","ttc","vEgo","stop_count_in_window",
            "post_min_aEgo","post_aEgo_drop"}]

    한계: LAUNCH_BYPASS_STOP_V_EGO(0.3)와 stop_v_ego 기본값을 맞췄으나,
    congestion_window_s/stop_count_thresh/min_closing_for_danger는
    아직 코드에 반영된 실제 상수가 아니라 이 스캔 전용 추정치 --
    실제 패치 상수값은 이 분석 결과를 참고해 별도로 정할 것.
    """
    n = len(rows)
    t = [_f(r, "t") for r in rows]
    vEgo = [_f(r, "vEgo") for r in rows]
    lead = [_b(r, "leadStatus") for r in rows]
    dRel = [_f(r, "leadDRel") for r in rows]
    vRel = [_f(r, "leadVRel") for r in rows]
    aEgo = [_f(r, "aEgo") for r in rows]
    seg = [r.get("seg") for r in rows]
    ce = [_b(r, "cruiseEnabled") for r in rows]

    stop_events_t = []  # 정차 진입 시각들
    prev_above = True
    candidates = []
    cur_danger = None

    for i in range(n):
        if t[i] is None:
            continue
        if vEgo[i] is not None:
            below = vEgo[i] < stop_v_ego
            if below and prev_above:
                stop_events_t.append(t[i])
            prev_above = not below

        # 최근 window 이내 정차 횟수
        stop_events_t = [st for st in stop_events_t if t[i] - st <= congestion_window_s]
        congestion_active = len(stop_events_t) >= congestion_stop_count_thresh

        ttc = None
        if lead[i] and dRel[i] is not None and vRel[i] is not None and vRel[i] <= -min_closing_vrel:
            ttc = dRel[i] / (-vRel[i])
        danger = ttc is not None and ttc <= ttc_danger_thresh

        if danger and congestion_active:
            if cur_danger is None:
                cur_danger = {"seg": seg[i], "t_start": t[i], "t_end": t[i],
                               "min_ttc": ttc, "dRel": dRel[i], "vRel": vRel[i],
                               "vEgo": vEgo[i], "cruiseEnabled": ce[i],
                               "stop_count_in_window": len(stop_events_t),
                               "max_abs_vRel": abs(vRel[i])}
            else:
                cur_danger["t_end"] = t[i]
                cur_danger["max_abs_vRel"] = max(cur_danger["max_abs_vRel"], abs(vRel[i]))
                if ttc < cur_danger["min_ttc"]:
                    cur_danger["min_ttc"] = ttc
                    cur_danger["dRel"] = dRel[i]
                    cur_danger["vRel"] = vRel[i]
                    cur_danger["vEgo"] = vEgo[i]
        else:
            if cur_danger is not None:
                candidates.append(cur_danger)
                cur_danger = None
    if cur_danger is not None:
        candidates.append(cur_danger)

    # "완만한 접근"만 필터 + 사후 aEgo 낙폭 계산
    results = []
    for c in candidates:
        # 이벤트 전체(danger 지속구간)에서 한 번이라도 실제 위험급
        # closing(max_abs_vRel)이 있었으면 "진짜 위험"으로 보고 제외 --
        # 완만한 접근만으로 danger override가 튄 순수 후보만 남김.
        if c["max_abs_vRel"] >= congestion_min_closing_for_danger:
            continue
        t0 = c["t_start"]
        pre_a = None
        min_a = None
        for i in range(n):
            if t[i] is None or aEgo[i] is None:
                continue
            if t0 - 0.3 <= t[i] < t0:
                pre_a = aEgo[i]
            if t0 <= t[i] <= t0 + post_jerk_window_s:
                if min_a is None or aEgo[i] < min_a:
                    min_a = aEgo[i]
        drop = None
        if pre_a is not None and min_a is not None:
            drop = round(pre_a - min_a, 3)
        results.append({
            "seg": c["seg"], "t": round(c["t_start"], 2),
            "duration_s": round(c["t_end"] - c["t_start"], 2),
            "dRel": round(c["dRel"], 2) if c["dRel"] is not None else None,
            "vRel": round(c["vRel"], 2) if c["vRel"] is not None else None,
            "ttc": round(c["min_ttc"], 2),
            "vEgo": round(c["vEgo"], 2) if c["vEgo"] is not None else None,
            "cruiseEnabled": c["cruiseEnabled"],
            "stop_count_in_window": c["stop_count_in_window"],
            "post_min_aEgo": round(min_a, 3) if min_a is not None else None,
            "post_aEgo_drop": drop,
        })
    return results


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


# ---------------------------------------------------------------------------
# 15) 곡선(vturn) 구간 leadDRel 급점프 노이즈 탐지
# ---------------------------------------------------------------------------
def curve_lead_dRel_jump_events(rows, jump_thresh_m=8.0, max_dt_s=0.35,
                                 curve_src_values=("vturn",), ttc_danger_thresh=2.5):
    """
    23차(2026-08-21)에서 발견된 패턴 탐지용: 곡선 구간(`src`가
    curve_src_values, 기본 "vturn")에서 모델이 서로 다른 물체(차선/
    구조물/실제 다른 차량)를 순간순간 리드로 오인해 leadDRel이 프레임
    간 큰 폭(예: 60m→32m→29m)으로 튀는 현상. 이게 vision closing-rate
    필터(`VISION_CLOSING_RATE_TAU`, sim_vision_rate.py 참고)에 노이즈성
    DANGER 스파이크를 유발할 수 있음 -- 개선안 1/2/4번 설계 전 선행검토용.

    max_dt_s: 이 시간 이내의 연속 프레임 쌍만 비교(세그먼트 경계 등
    비정상 dt 제외, extract_log.py 2026-08-21 수정 이후 CSV 권장).

    리턴: [{"seg","t","dRel_prev","dRel_now","jump_m","dt_s",
            "implied_rate_mps","vEgo","would_trigger_ttc_danger"}]
    implied_rate_mps = jump_m / dt_s (프레임 간 급점프를 순간
    접근/이탈 속도로 환산한 값 -- 실제 vRel이 아니라 dRel 미분
    노이즈의 크기를 가늠하기 위한 참고치).
    would_trigger_ttc_danger: dRel_now/implied_rate_mps로 계산한 TTC가
    ttc_danger_thresh 이하인지 (실제로 DANGER 문턱을 넘길 만한
    노이즈인지 1차 필터링용).
    """
    n = len(rows)
    t = [_f(r, "t") for r in rows]
    src = [r.get("src") for r in rows]
    dRel = [_f(r, "leadDRel") for r in rows]
    lead = [_b(r, "leadStatus") for r in rows]
    vEgo = [_f(r, "vEgo") for r in rows]
    seg = [r.get("seg") for r in rows]

    events = []
    for i in range(1, n):
        if src[i] not in curve_src_values:
            continue
        if not (lead[i] and lead[i - 1]):
            continue
        if t[i] is None or t[i - 1] is None or dRel[i] is None or dRel[i - 1] is None:
            continue
        dt = t[i] - t[i - 1]
        if not (0 < dt <= max_dt_s):
            continue
        jump = dRel[i] - dRel[i - 1]
        if abs(jump) < jump_thresh_m:
            continue
        implied_rate = jump / dt
        ttc = None
        would_danger = False
        if implied_rate < 0 and dRel[i] > 0:
            ttc = dRel[i] / (-implied_rate)
            would_danger = ttc <= ttc_danger_thresh
        events.append({
            "seg": seg[i], "t": round(t[i], 2),
            "dRel_prev": round(dRel[i - 1], 2), "dRel_now": round(dRel[i], 2),
            "jump_m": round(jump, 2), "dt_s": round(dt, 3),
            "implied_rate_mps": round(implied_rate, 2),
            "vEgo": round(vEgo[i], 2) if vEgo[i] is not None else None,
            "would_trigger_ttc_danger": would_danger,
        })
    return events


def curve_noise_summary(rows, jump_thresh_m=8.0, max_dt_s=0.35,
                         curve_src_values=("vturn",), ttc_danger_thresh=2.5):
    """
    curve_lead_dRel_jump_events()를 요약 통계로 압축.
    "곡선 구간에서 이 노이즈가 실제로 얼마나 자주 DANGER 문턱을
    넘길 만한 크기로 발생하는가"를 한눈에 보는 용도.

    리턴: {"n_curve_frames","n_jump_events","n_would_trigger_danger",
           "jump_events_per_min_in_curve", "events"(상세 리스트)}
    """
    events = curve_lead_dRel_jump_events(
        rows, jump_thresh_m=jump_thresh_m, max_dt_s=max_dt_s,
        curve_src_values=curve_src_values, ttc_danger_thresh=ttc_danger_thresh,
    )
    n_curve_frames = sum(1 for r in rows if r.get("src") in curve_src_values)
    # 곡선 구간 체류 시간(초) 근사: 프레임 수 * 평균 dt 대신, 실제 t 스팬으로 추정
    curve_rows = [r for r in rows if r.get("src") in curve_src_values]
    curve_times = [_f(r, "t") for r in curve_rows if _f(r, "t") is not None]
    curve_duration_min = 0.0
    if len(curve_times) >= 2:
        # 연속 구간이 아닐 수 있으므로 dt<1.0인 구간만 누적
        curve_times_sorted = sorted(curve_times)
        for i in range(1, len(curve_times_sorted)):
            dt = curve_times_sorted[i] - curve_times_sorted[i - 1]
            if 0 < dt < 1.0:
                curve_duration_min += dt / 60.0

    n_danger = sum(1 for e in events if e["would_trigger_ttc_danger"])
    return {
        "n_curve_frames": n_curve_frames,
        "curve_duration_min": round(curve_duration_min, 2),
        "n_jump_events": len(events),
        "n_would_trigger_danger": n_danger,
        "jump_events_per_min_in_curve": (
            round(len(events) / curve_duration_min, 2) if curve_duration_min > 0 else None
        ),
        "events": events,
    }


def curve_lead_dRel_jump_consistency(rows, jump_thresh_m=8.0, max_dt_s=0.35,
                                      curve_src_values=("vturn",), ttc_danger_thresh=2.5,
                                      consistency_window_s=1.5, monotonic_frac_thresh=0.6,
                                      revert_frac_thresh=0.5):
    """
    21차(2026-08-21) seg6/seg12 dashcam 시각 검증 결과를 근거로 설계된
    `curve_lead_dRel_jump_events()`의 후속 개선. 단일 프레임 점프만
    보는 `would_trigger_ttc_danger`는 "노이즈성 플리커"와 "진짜 접근"을
    구분 못 함(23차/20차에서 확인된 한계) -- 이 함수는 점프 이후
    consistency_window_s초 동안의 dRel/leadVRel 추이를 추가로 봐서
    구분을 시도한다.

    21차 시각 증거로 확인된 두 패턴:
    - **노이즈(seg6)**: 곡선 가장자리 버스/정차차량이 리드 후보로
      순간 혼입 -> 큰 폭 점프 직후 짧게(약 0.1~0.3s) 비슷한 크기로
      반대 방향 재점프가 발생하며 원래 값 근처로 복귀하는 "플리커".
    - **진짜 접근(seg12 t=797.79)**: 레이더 락온 직후 짧은 정착
      구간(~0.3~0.4s) 동안은 오히려 vRel이 잠깐 양수로 흔들리는
      노이즈가 있었지만, 그 이후 지속적으로 dRel이 줄고 vRel도
      음수로 수렴 -- 짧은 윈도우(0.6s)로는 이 정착 지연 때문에 오히려
      "일관성 없음"으로 오판되는 것을 실측으로 확인함(윈도우를 1.5s로
      늘려야 정착 구간을 지나 진짜 추세가 드러남).

    판정 로직 (이벤트 인덱스 i, 점프 방향 sign(jump_m)):
    - window: t[i] ~ t[i]+consistency_window_s 구간의 동일 세그먼트 프레임들.
    - reverted: window 내에 jump_m과 반대 부호이고 크기가
      abs(jump_m)*revert_frac_thresh 이상인 "복귀성 재점프"가 있으면 True
      (플리커의 강한 신호).
    - monotonic_frac: window 내 연속 프레임 dRel 변화 중 jump_m과 같은
      부호인 비율.
    - vrel_consistent: window 내 leadVRel 평균의 부호가 jump_m 부호와
      일치하는지(jump_m<0, 즉 접근이면 평균 vRel<0 기대).
    - physically_consistent = (not reverted) and monotonic_frac >=
      monotonic_frac_thresh and vrel_consistent is True
    - refined_would_trigger_danger = would_trigger_ttc_danger and
      physically_consistent

    **알려진 한계 (21차 시점, 다음 세션 검증 필요)**:
    - 파라미터(window=1.5s, monotonic_frac_thresh=0.6)는 seg6 노이즈
      4건 + seg12 t=797.79 진짜위험 1건, 총 5건의 시각 검증 사례로만
      튜닝됨 -- 표본이 작음. 더 많은 시각 검증 사례로 재확인 필요.
    - 같은 로그의 seg12 t=800.05(브레이크등 점등 육안 확인, 진짜
      감속 반응으로 추정되나 이 케이스는 아직 시각 미검증) 같은
      "리드 재획득/후보 전환이 섞인" 복잡한 케이스는 현재 파라미터로
      여전히 놓침(refined=False) -- 리드 재획득(dRel 급증 후 재추적)
      패턴은 별도 처리가 필요할 수 있음.

    리턴: curve_lead_dRel_jump_events()와 동일한 dict 리스트에 아래 키 추가:
      "reverted", "monotonic_frac", "vrel_consistent",
      "physically_consistent", "refined_would_trigger_danger"
    """
    events = curve_lead_dRel_jump_events(
        rows, jump_thresh_m=jump_thresh_m, max_dt_s=max_dt_s,
        curve_src_values=curve_src_values, ttc_danger_thresh=ttc_danger_thresh,
    )
    if not events:
        return events

    t = [_f(r, "t") for r in rows]
    dRel = [_f(r, "leadDRel") for r in rows]
    vRel = [_f(r, "leadVRel") for r in rows]
    seg = [r.get("seg") for r in rows]

    for ev in events:
        i = None
        for idx in range(len(rows)):
            if seg[idx] == ev["seg"] and t[idx] is not None and abs(t[idx] - ev["t"]) < 0.005:
                i = idx
                break
        if i is None:
            ev.update({"reverted": None, "monotonic_frac": None,
                       "vrel_consistent": None, "physically_consistent": None,
                       "refined_would_trigger_danger": ev["would_trigger_ttc_danger"]})
            continue

        jump_sign = 1 if ev["jump_m"] > 0 else -1
        window_end_t = t[i] + consistency_window_s
        window_idx = [i]
        j = i + 1
        while j < len(rows) and t[j] is not None and t[j] <= window_end_t and seg[j] == ev["seg"]:
            window_idx.append(j)
            j += 1

        reverted = False
        same_sign_diffs = 0
        total_diffs = 0
        for k in range(1, len(window_idx)):
            a, b = window_idx[k - 1], window_idx[k]
            if dRel[a] is None or dRel[b] is None:
                continue
            d = dRel[b] - dRel[a]
            total_diffs += 1
            if d * jump_sign > 0:
                same_sign_diffs += 1
            if d * jump_sign < 0 and abs(d) >= abs(ev["jump_m"]) * revert_frac_thresh:
                reverted = True

        monotonic_frac = (same_sign_diffs / total_diffs) if total_diffs > 0 else None

        vrel_vals = [vRel[k] for k in window_idx if vRel[k] is not None]
        vrel_consistent = None
        if vrel_vals:
            avg_vrel = sum(vrel_vals) / len(vrel_vals)
            vrel_consistent = (avg_vrel * jump_sign) > 0

        physically_consistent = (
            not reverted
            and monotonic_frac is not None and monotonic_frac >= monotonic_frac_thresh
            and vrel_consistent is True
        )
        ev.update({
            "reverted": reverted,
            "monotonic_frac": round(monotonic_frac, 2) if monotonic_frac is not None else None,
            "vrel_consistent": vrel_consistent,
            "physically_consistent": physically_consistent,
            "refined_would_trigger_danger": bool(ev["would_trigger_ttc_danger"] and physically_consistent),
        })
    return events


def curve_noise_summary_refined(rows, jump_thresh_m=8.0, max_dt_s=0.35,
                                 curve_src_values=("vturn",), ttc_danger_thresh=2.5,
                                 consistency_window_s=1.5, monotonic_frac_thresh=0.6,
                                 revert_frac_thresh=0.5):
    """
    curve_noise_summary()의 refined 버전. 21차에서 추가한
    `curve_lead_dRel_jump_consistency()`를 사용해 raw
    would_trigger_ttc_danger 건수 대비 refined_would_trigger_danger
    (물리적 일관성 체크 통과) 건수를 비교한다 -- "이 개선이 실제로
    얼마나 노이즈를 걸러내는지" 한눈에 보는 용도.

    리턴: curve_noise_summary()와 동일한 키 + "n_refined_danger"
    (물리적 일관성까지 통과한 건수), "noise_suppression_rate"
    (1 - n_refined_danger/n_would_trigger_danger, raw danger 대비
    억제 비율).
    """
    events = curve_lead_dRel_jump_consistency(
        rows, jump_thresh_m=jump_thresh_m, max_dt_s=max_dt_s,
        curve_src_values=curve_src_values, ttc_danger_thresh=ttc_danger_thresh,
        consistency_window_s=consistency_window_s,
        monotonic_frac_thresh=monotonic_frac_thresh,
        revert_frac_thresh=revert_frac_thresh,
    )
    n_curve_frames = sum(1 for r in rows if r.get("src") in curve_src_values)
    curve_rows = [r for r in rows if r.get("src") in curve_src_values]
    curve_times = [_f(r, "t") for r in curve_rows if _f(r, "t") is not None]
    curve_duration_min = 0.0
    if len(curve_times) >= 2:
        curve_times_sorted = sorted(curve_times)
        for i in range(1, len(curve_times_sorted)):
            dt = curve_times_sorted[i] - curve_times_sorted[i - 1]
            if 0 < dt < 1.0:
                curve_duration_min += dt / 60.0

    n_danger = sum(1 for e in events if e["would_trigger_ttc_danger"])
    n_refined = sum(1 for e in events if e["refined_would_trigger_danger"])
    return {
        "n_curve_frames": n_curve_frames,
        "curve_duration_min": round(curve_duration_min, 2),
        "n_jump_events": len(events),
        "n_would_trigger_danger": n_danger,
        "n_refined_danger": n_refined,
        "noise_suppression_rate": (
            round(1 - n_refined / n_danger, 3) if n_danger > 0 else None
        ),
        "jump_events_per_min_in_curve": (
            round(len(events) / curve_duration_min, 2) if curve_duration_min > 0 else None
        ),
        "events": events,
    }


def dRel_jump_ego_maneuver_overlap(rows, events=None, blinker_window_s=1.0,
                                    curvature_reversal_window_s=1.0,
                                    curvature_reversal_thresh=0.0005,
                                    **jump_kwargs):
    """
    44차(2026-08-22)에서 발견된 실수 재발 방지용: `curve_lead_dRel_jump_events()`가
    찾아낸 dRel 급점프 각각이 "vision 깊이 오추정 노이즈"가 아니라 ego
    자신의 실제 측방 기동(방향지시등 on / desiredCurvature 부호 반전 /
    lateralPlan.laneChangeState 활성)과 겹치는지 자동으로 플래그한다.

    배경: route B seg10 t=1895.6 이벤트(FINDINGS.md 44차)가 42차에서
    "커브 vision 노이즈"로 오판됐던 근본 원인은, 당시 CSV에 blinker/
    laneChangeState 컬럼 자체가 없어 "이 점프가 ego의 실제 조향/신호와
    겹치는지"를 검증할 수단이 없었기 때문. 43차에서 `extract_log.py`에
    해당 컬럼을 추가했지만, 매번 사람이 CSV를 눈으로 대조해야 한다면
    같은 실수가 반복될 수 있음 -- 이 함수가 그 대조를 자동화한다.

    각 이벤트 발생 시각(t) 기준:
    - blinker_on: 전후 blinker_window_s초 내 leftBlinker 또는
      rightBlinker가 True인 프레임이 하나라도 있는지.
    - laneChangeState_active: 같은 창 내 laneChangeState가 "off"/빈값이
      아닌 프레임이 있는지 (openpilot 자체 LCA가 개입했는지).
    - curvature_reversal: 전후 curvature_reversal_window_s초 내
      desiredCurvature 부호가 반전되고 그 진폭(max-min)이
      curvature_reversal_thresh를 넘는지 -- 단순 편측 커브 주행에서는
      나오지 않는 S자형 조향 패턴 근사 탐지.
    - likely_ego_maneuver: 위 세 가지 중 하나라도 True.

    **주의**: `likely_ego_maneuver=True`라고 해서 "이 dRel 점프는 안전과
    무관하다"는 뜻이 아니다 -- 44차 결론대로 ego 기동 중에도 실제 리드
    차량과의 거리/위험은 여전히 유효할 수 있다. 이 함수는 "vision 노이즈"
    라는 성급한 결론을 막기 위한 1차 스크리닝 용도로만 쓸 것.

    rows: extract_log.py 2026-08-22(43차) 이후 버전으로 뽑은 CSV만 지원
    (leftBlinker/rightBlinker/laneChangeState 컬럼 필요). 구버전 CSV면
    모든 이벤트의 blinker_on/laneChangeState_active가 항상 False로
    나오므로, 그 결과만으로 "노이즈 확정"하지 말고 CSV 버전부터 확인할 것.

    리턴: curve_lead_dRel_jump_events()와 동일한 이벤트 리스트에
    "blinker_on"/"laneChangeState_active"/"curvature_reversal"/
    "likely_ego_maneuver" 키를 추가해서 반환.
    """
    if events is None:
        events = curve_lead_dRel_jump_events(rows, **jump_kwargs)
    if not events:
        return events

    t = [_f(r, "t") for r in rows]
    curv = [_f(r, "desiredCurvature") for r in rows]
    lblk = [_b(r, "leftBlinker") for r in rows]
    rblk = [_b(r, "rightBlinker") for r in rows]
    lcs = [r.get("laneChangeState") for r in rows]

    for e in events:
        et = e["t"]

        idxs_b = [i for i in range(len(rows))
                  if t[i] is not None and abs(t[i] - et) <= blinker_window_s]
        blinker_on = any((lblk[i] or rblk[i]) for i in idxs_b)
        lc_active = any(lcs[i] not in (None, "", "off") for i in idxs_b)

        idxs_c = [i for i in range(len(rows))
                  if t[i] is not None and abs(t[i] - et) <= curvature_reversal_window_s]
        curv_vals = [curv[i] for i in idxs_c if curv[i] is not None]
        curvature_reversal = False
        if len(curv_vals) >= 2:
            cmin, cmax = min(curv_vals), max(curv_vals)
            if cmin < 0 < cmax and (cmax - cmin) >= curvature_reversal_thresh:
                curvature_reversal = True

        e["blinker_on"] = blinker_on
        e["laneChangeState_active"] = lc_active
        e["curvature_reversal"] = curvature_reversal
        e["likely_ego_maneuver"] = blinker_on or lc_active or curvature_reversal

    return events


def curve_apex_vs_gap_delta(rows, entry_thresh=5.0, exit_thresh=3.0,
                             unrestricted_ds=180.0, min_event_rows=3):
    """
    (2026-08-22, 46차 계속) 커브 이벤트별로 "실제 조향각 정점(apex) 시점"과
    "vEgo(kph)-desiredSpeed 최대 초과폭(max gap) 발생 시점"의 시간차를
    계산 -- "정점 감속 부족"이 실제로는 apex 이전(사전감속 구간 후반)에서
    이미 벌어진 문제의 연장인지, 진짜 apex에서 못 따라간 것인지 구분하는
    용도. route2(f3db6ca89d) 32건 분석에서 79%가 gap이 apex보다 평균
    1.26초 먼저 발생하는 것으로 확인(FINDINGS.md "route2 32건 커브
    이벤트 재분류" 참고).

    이벤트 분리: |steeringAngleDeg| >= entry_thresh 진입 / < exit_thresh
    이탈. min_event_rows 미만인 짧은 잡음성 이벤트는 제외.
    desiredSpeed >= unrestricted_ds(기본 180, 사실상 무제한)인 프레임은
    gap 계산에서 제외(직선 구간이 이벤트에 섞여 들어온 경우 방지).

    리턴: 이벤트별 dict 리스트. 각 dict:
      entry_t, exit_t, apex_t, apex_steer,
      max_gap(양수=초과, 음수=미달), gap_t, gap_ds, gap_vego,
      delta_gap_minus_apex(음수=gap이 apex보다 먼저 발생)
    max_gap 계산 가능한 유효 프레임이 없는 이벤트(전 구간
    desiredSpeed>=unrestricted_ds)는 결과에서 제외됨.

    참고: route1(고속도로 단일커브)처럼 이벤트 자체가 드문 도로에서는
    잡음성 조향(차선변경 등)이 entry_thresh를 넘어 이벤트로 잡히고
    max_gap이 크게 음수로 나오는 경우가 많음 -- 호출부에서
    `max_gap > 0`으로 먼저 필터링해 "실제 초과 사례"만 볼 것.
    """
    events = []
    in_curve = False
    cur = []
    for r in rows:
        steer = abs(_f(r, "steeringAngleDeg", 0.0))
        if not in_curve and steer >= entry_thresh:
            in_curve = True
            cur = [r]
        elif in_curve:
            cur.append(r)
            if steer < exit_thresh:
                in_curve = False
                if len(cur) >= min_event_rows:
                    events.append(cur)
                cur = []
    if in_curve and len(cur) >= min_event_rows:
        events.append(cur)

    results = []
    for ev in events:
        apex_row = max(ev, key=lambda r: abs(_f(r, "steeringAngleDeg", 0.0)))
        apex_t = _f(apex_row, "t")
        apex_steer = _f(apex_row, "steeringAngleDeg")

        gap_candidates = []
        for r in ev:
            ds = _f(r, "desiredSpeed")
            vego = _f(r, "vEgo")
            if ds is None or vego is None or ds <= 0 or ds >= unrestricted_ds:
                continue
            vego_kph = vego * 3.6
            gap_candidates.append((vego_kph - ds, _f(r, "t"), ds, vego_kph))
        if not gap_candidates:
            continue
        max_gap, gap_t, gap_ds, gap_vego = max(gap_candidates, key=lambda x: x[0])

        results.append({
            "entry_t": _f(ev[0], "t"),
            "exit_t": _f(ev[-1], "t"),
            "apex_t": apex_t,
            "apex_steer": apex_steer,
            "max_gap": max_gap,
            "gap_t": gap_t,
            "gap_ds": gap_ds,
            "gap_vego": gap_vego,
            "delta_gap_minus_apex": gap_t - apex_t,
            "seg": ev[0].get("seg", ""),
        })
    return results


def vturn_release_lag_scan(rows, entry_thresh=5.0, exit_thresh=3.0,
                            min_event_rows=3, curvature_release_hold_s=0.3,
                            vturn_rise_thresh_kph=1.5, vturn_rise_hold_s=0.3,
                            search_window_s=8.0):
    """
    (2026-08-23, 49차) `vturn_speed()`(carrot_man.py) 설계상 apex(조향각
    정점) 통과 즉시 argmin 후보가 전방으로 넘어가며 제약이 풀리기
    시작하는 구조인지, 아니면 실제 vTurnSpeed 출력이 눈에 띄게 오르기
    시작하는 시점까지 체감될 만한 지연(주로 vturn_accel_rc 저역통과
    스무딩)이 있는지를 CSV만으로 근사 측정한다.

    주의(중요, 근사치): vturn_speed() 내부의 필터-전 required_speed_kph
    (매 지점 물리공식 결과, argmin 이전 값)는 modelV2.orientationRate/
    velocity/position raw 배열에서만 계산 가능하고 CSV엔 없음 -- CSV엔
    필터-후 최종 출력 vTurnSpeed만 있다. 이 함수는 그 대신
    steeringAngleDeg(실제 조향각, 곡률 진행의 관측 가능한 proxy)의
    apex를 "구조적으로 release가 시작돼야 하는 시점"의 근사치로 쓴다.
    즉 "argmin 전환 시각" 자체를 직접 재현하는 게 아니라, "곡률이
    실제로 완화되기 시작한 시각" 대비 "vTurnSpeed가 실제로 오르기
    시작한 시각"의 지연을 잰다 -- accel_rc 스무딩 체감 지연을 보는
    용도로는 충분하지만, argmin 구조 자체의 정확한 전환 시점 검증은
    아니다(그러려면 modelV2 raw 재현이 필요, 별도 과제).

    이벤트 분리는 `curve_apex_vs_gap_delta()`와 동일한
    entry_thresh/exit_thresh 방식(|steeringAngleDeg| 기준).

    각 이벤트에 대해:
    1. apex_t: |steeringAngleDeg| 최댓값 시각 (곡률 완화가 구조적으로
       시작될 수 있는 가장 이른 시점의 근사 하한).
    2. curvature_release_t: apex_t 이후, |steeringAngleDeg|가
       curvature_release_hold_s 동안 연속 비증가(재상승 없이 감소/유지)
       하기 시작하는 첫 시각. 아직 못 찾으면 이벤트 제외.
    3. vturn_rise_t: apex_t 이후 search_window_s 이내에서, 곡선 진행
       방향과 무관하게 abs(vTurnSpeed)가 vturn_rise_thresh_kph 이상
       상승한 뒤 vturn_rise_hold_s 동안 다시 그 이하로 안 떨어지는
       첫 시각(=필터 출력이 "실제로, 계속" 오르기 시작하는 시점).
       못 찾으면 이벤트 제외(=이 구간에선 vTurnSpeed가 아예 안 올랐다는
       뜻이므로 lag 계산이 무의미).
    4. lag_s = vturn_rise_t - curvature_release_t (양수=곡률 완화보다
       vTurnSpeed 상승이 늦음, 음수=먼저/동시 상승 -- 부호 반전은
       근사 오차이거나 다른 제약(vCruiseCluster 등)이 개입했을 가능성).

    리턴: 이벤트별 dict 리스트 (apex_t, curvature_release_t, vturn_rise_t,
    lag_s, seg, apex_steer). curvature_release_t나 vturn_rise_t를 못 찾은
    이벤트는 결과에서 제외.
    """
    events = []
    in_curve = False
    cur = []
    for r in rows:
        steer = abs(_f(r, "steeringAngleDeg", 0.0))
        if not in_curve and steer >= entry_thresh:
            in_curve = True
            cur = [r]
        elif in_curve:
            cur.append(r)
            if steer < exit_thresh:
                in_curve = False
                if len(cur) >= min_event_rows:
                    events.append(cur)
                cur = []
    if in_curve and len(cur) >= min_event_rows:
        events.append(cur)

    results = []
    for ev in events:
        apex_idx = max(range(len(ev)), key=lambda i: abs(_f(ev[i], "steeringAngleDeg", 0.0)))
        apex_row = ev[apex_idx]
        apex_t = _f(apex_row, "t")
        apex_steer = _f(apex_row, "steeringAngleDeg")

        # curvature_release_t: apex 이후 |steeringAngleDeg|가
        # curvature_release_hold_s 동안 연속 비증가 시작하는 첫 시각.
        post_apex = ev[apex_idx:]
        release_t = None
        for i in range(len(post_apex) - 1):
            t0 = _f(post_apex[i], "t")
            if t0 is None:
                continue
            ok = True
            peak = abs(_f(post_apex[i], "steeringAngleDeg", 0.0))
            for j in range(i, len(post_apex)):
                tj = _f(post_apex[j], "t")
                if tj is None:
                    continue
                if tj - t0 > curvature_release_hold_s:
                    break
                sj = abs(_f(post_apex[j], "steeringAngleDeg", 0.0))
                if sj > peak + 0.05:  # 0.05deg 노이즈 허용
                    ok = False
                    break
                peak = min(peak, sj) if sj < peak else peak
            if ok:
                release_t = t0
                break
        if release_t is None:
            continue

        # vturn_rise_t: apex 이후 search_window_s 내에서 abs(vTurnSpeed)가
        # vturn_rise_thresh_kph 이상 오른 뒤 vturn_rise_hold_s 동안
        # 유지되는 첫 시각.
        base_vturn = abs(_f(apex_row, "vTurnSpeed", 0.0))
        rise_t = None
        for i in range(len(post_apex)):
            ti = _f(post_apex[i], "t")
            if ti is None or ti - apex_t > search_window_s:
                break
            vi = abs(_f(post_apex[i], "vTurnSpeed", 0.0))
            if vi - base_vturn >= vturn_rise_thresh_kph:
                held = True
                for k in range(i, len(post_apex)):
                    tk = _f(post_apex[k], "t")
                    if tk is None:
                        continue
                    if tk - ti > vturn_rise_hold_s:
                        break
                    vk = abs(_f(post_apex[k], "vTurnSpeed", 0.0))
                    if vk - base_vturn < vturn_rise_thresh_kph * 0.5:
                        held = False
                        break
                if held:
                    rise_t = ti
                    break
        if rise_t is None:
            continue

        results.append({
            "apex_t": apex_t,
            "apex_steer": apex_steer,
            "curvature_release_t": release_t,
            "vturn_rise_t": rise_t,
            "lag_s": rise_t - release_t,
            "seg": ev[0].get("seg", ""),
        })
    return results


def radar_source_flicker_scan(rows, min_flips=3, window_s=2.0,
                                blinker_window_s=1.0, jump_thresh_m=8.0,
                                ttc_danger_thresh=2.5):
    """
    107차: 106차(WIP/FINDINGS)가 남긴 "차선변경 중 leadRadar 핸드오프 반복 급감속"의
    정량화용. 106차는 leadRadarTrackId 컬럼이 없어 화면녹화 육안대조에만 의존했으나,
    이미 63차 계속3에서 해당 컬럼이 추가돼 있었음이 107차에서 재확인됨 -- 다만 이
    차량(SCC 단일점 레이더, 코너레이더 없음)에서는 leadRadar=True인 프레임의
    leadRadarTrackId가 항상 0으로 고정(캐시된 12개 라우트 전수 확인)이라 트랙ID
    자체는 변별력이 없음. 대신 leadRadar(True/False) 값이 얼마나 자주 뒤집히는지와
    그게 blinker 활성 구간과 겹치는지를 직접 정량화한다.

    방법:
    - leadStatus=True로 이어지는 연속 구간(run) 안에서 leadRadar 값이 이전 프레임
      대비 바뀌는 시점(엣지)을 전부 찾는다.
    - 각 엣지를 기준으로 앞뒤 window_s초 안에 다른 엣지가 min_flips개 이상 모여
      있으면 "플리커 클러스터"로 묶는다(같은 클러스터에 속하는 엣지들은 중복
      집계하지 않고 클러스터 단위로 1건 카운트).
    - 클러스터별로: 지속시간(첫~마지막 엣지), 엣지 수, blinker_window_s 안에
      leftBlinker/rightBlinker가 한 번이라도 True였는지, 클러스터 구간 내 최대
      |dRel jump|(프레임간, jump_thresh_m 이상만) 및 그 순간 would_trigger_ttc_danger
      (curve_lead_dRel_jump_events와 동일 계산식, 단 src 필터 없음 -- 이 현상은
      src(vturn 등)와 무관하게 발생하므로 curve_lead_dRel_jump_events를 그대로
      재사용하지 않고 여기서 독립 계산).

    리턴: {"n_clusters", "n_clusters_with_blinker", "clusters"(상세 리스트),
           "n_leadRadar_edges_total"}
    각 cluster dict: {"t_start","t_end","duration_s","n_edges","seg",
                       "blinker_overlap","max_abs_jump_m","would_trigger_ttc_danger",
                       "vEgo_at_start"}

    주의: min_flips=3 기본값은 106차 사례3(1.85초/4회+)을 기준으로 잡은 보수적
    문턱 -- mild 사례(사례1, 2초/3회)는 걸리지만 정상적인 1회성 핸드오프는
    걸리지 않도록. 필요시 완화(min_flips=2)해서 재실행 권장.
    """
    n = len(rows)
    t = [_f(r, "t") for r in rows]
    lead = [_b(r, "leadStatus") for r in rows]
    radar = [_b(r, "leadRadar") for r in rows]
    dRel = [_f(r, "leadDRel") for r in rows]
    vEgo = [_f(r, "vEgo") for r in rows]
    lblk = [_b(r, "leftBlinker") for r in rows]
    rblk = [_b(r, "rightBlinker") for r in rows]
    seg = [r.get("seg") for r in rows]

    edges = []
    for i in range(1, n):
        if not (lead[i] and lead[i - 1]):
            continue
        if t[i] is None or t[i - 1] is None:
            continue
        if radar[i] != radar[i - 1]:
            edges.append(i)

    clusters = []
    used = [False] * len(edges)
    for k, i in enumerate(edges):
        if used[k]:
            continue
        et = t[i]
        group_idx = [k]
        for k2, i2 in enumerate(edges):
            if k2 == k or used[k2]:
                continue
            if t[i2] is not None and abs(t[i2] - et) <= window_s:
                group_idx.append(k2)
        if len(group_idx) < min_flips:
            continue
        for k2 in group_idx:
            used[k2] = True

        group_rows = [edges[k2] for k2 in group_idx]
        t_start = min(t[i2] for i2 in group_rows)
        t_end = max(t[i2] for i2 in group_rows)

        blk_idxs = [j for j in range(n)
                    if t[j] is not None and t_start - blinker_window_s <= t[j] <= t_end + blinker_window_s]
        blinker_overlap = any((lblk[j] or rblk[j]) for j in blk_idxs)

        max_jump = 0.0
        would_danger = False
        span_idxs = [j for j in range(n) if t[j] is not None and t_start - 0.1 <= t[j] <= t_end + 0.1]
        for j in span_idxs:
            if j == 0 or not (lead[j] and lead[j - 1]):
                continue
            if t[j] is None or t[j - 1] is None or dRel[j] is None or dRel[j - 1] is None:
                continue
            dt = t[j] - t[j - 1]
            if not (0 < dt <= 0.35):
                continue
            jump = dRel[j] - dRel[j - 1]
            if abs(jump) < jump_thresh_m:
                continue
            if abs(jump) > max_jump:
                max_jump = abs(jump)
            implied_rate = jump / dt
            if implied_rate < 0 and dRel[j] > 0:
                ttc = dRel[j] / (-implied_rate)
                if ttc <= ttc_danger_thresh:
                    would_danger = True

        i0 = group_rows[0]
        clusters.append({
            "t_start": round(t_start, 2),
            "t_end": round(t_end, 2),
            "duration_s": round(t_end - t_start, 2),
            "n_edges": len(group_idx),
            "seg": seg[i0],
            "blinker_overlap": blinker_overlap,
            "max_abs_jump_m": round(max_jump, 2),
            "would_trigger_ttc_danger": would_danger,
            "vEgo_at_start": round(vEgo[i0], 2) if vEgo[i0] is not None else None,
        })

    clusters.sort(key=lambda c: c["t_start"])
    return {
        "n_clusters": len(clusters),
        "n_clusters_with_blinker": sum(1 for c in clusters if c["blinker_overlap"]),
        "n_leadRadar_edges_total": len(edges),
        "clusters": clusters,
    }


# ===========================================================================
# 147차: carrotMan.naviPaths(carrot_navi_route()가 곡률 계산에 실제로 쓰는
# 로컬(x,y) 리샘플 폴리라인+거리) 파싱 및 route 곡률/목표속도 재계산.
#
# 배경: 89차/90차가 "route가 특정 커브의 실제 조임 정도를 과소평가하는
# 이유가 chord 길이(sample=4, 40m 간격)인지 실제 GPS 폴리라인 형상
# 자체인지 확인하려면 raw navi_points를 로그에 계측해야 한다"고 제안했으나
# (raw navi_points가 로그에 없어 직접검증 불가로 NEEDS_VALIDATION 유지),
# 147차에서 코드 재확인 결과 **이미 carrot_serv.py가 이 데이터를
# `naviPaths` 필드로 20Hz 발행 중**이었음이 드러남(ryu 코드 변경 불필요,
# extract_log.py --with-navi-paths 로 추출만 하면 됨).
# calculate_curvature()/V_CURVE_LOOKUP_BP/VALS는 90차 sim_route_curvature_sample.py
# 이식본과 100% 동일(carrot_man.py 원본 상수 그대로).
# ===========================================================================

_ROUTE_V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265.,
                            1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
_ROUTE_V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]


def parse_navi_paths(navi_paths_str):
    """carrotMan.naviPaths 텍스트("x1,y1,d1;x2,y2,d2;...")를
    [(x, y), ...], [d1, d2, ...] 튜플로 파싱. 빈 문자열/파싱 실패 시 ([], [])."""
    if not navi_paths_str:
        return [], []
    points, distances = [], []
    for chunk in navi_paths_str.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(",")
        if len(parts) != 3:
            continue
        try:
            x, y, d = float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            continue
        points.append((x, y))
        distances.append(d)
    return points, distances


def _route_calculate_curvature(p1, p2, p3):
    """carrot_man.py calculate_curvature()와 100% 동일(회전/이동 불변)."""
    import math
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


def _route_curvature_single_pass(points, distances, sample, road_limit_speed, floor_threshold=0.02):
    """sample 간격(=sample*10m chord) 3점 곡률 1회 계산. 내부 헬퍼.
    floor_threshold(158차 추가): curvature < floor_threshold일 때
    speed를 road_limit_speed로 되돌리는 플로어 임계값. 기본 0.02는
    157차 이전 프로덕션(버그 포함) 동작과 동일 -- 157차 패치 재현 시
    ROUTE_CURVE_NEGLIGIBLE_THRESHOLD=0.001을 넘겨서 호출할 것."""
    import numpy as np
    out = []
    if len(points) < sample * 2 + 1:
        return out
    for i in range(len(points) - sample * 2):
        p1, p2, p3 = points[i], points[i + sample], points[i + sample * 2]
        curvature = _route_calculate_curvature(p1, p2, p3)
        speed = float(np.interp(abs(curvature), _ROUTE_V_CURVE_LOOKUP_BP, _ROUTE_V_CRUVE_LOOKUP_VALS))
        if abs(curvature) < floor_threshold:
            speed = max(speed, road_limit_speed)
        dist = distances[i + sample] if i + sample < len(distances) else distances[-1]
        out.append((dist, curvature, speed))
    return out


def recompute_route_curvature_speed(points, distances, sample=4, sample_fine=None,
                                     road_limit_speed=200.0, floor_threshold=0.02):
    """parse_navi_paths()로 얻은 실측 폴리라인에 carrot_navi_route()와
    동일한 3점 곡률(샘플 간격 = sample*10m) + V_CURVE_LOOKUP을 적용해
    지점별 (distance, curvature, speed_cap) 리스트를 반환한다.
    (역방향 DP/시간지연 스무딩은 별도 -- 이 함수는 "곡률이 실제로 이
    지점에서 얼마나 급하게 잡혔는지"만 순수 재현. 89차/90차가 의심한
    "route가 이 지점의 곡률 자체를 과소평가했는가"를 직접 확인하는 용도.)

    sample_fine (147차 신규): 지정하면 매크로 sample(기본 4, 40m chord)은
    그대로 유지한 채, 같은 폴리라인에 sample_fine(예: 1 = 10m chord)로
    한 번 더 3점 곡률을 계산해 같은 위치(거리)에서 더 급한(=speed_cap이
    더 낮은) 쪽을 채택한 리스트를 반환한다(merge). carrot_man.py의
    ROUTE_CURVATURE_FINE_SAMPLE 패치와 동일 로직 -- 검증 도구가 실제
    프로덕션 패치와 항상 일치하도록 함. 147차 실측: 40m chord 단독으로는
    반경 27m급 급커브를 반경 110m급으로 평활화해 0.02 임계값 아래로
    숨기는 것을 실측 naviPaths로 확인(FINDINGS.md 147차 참고).
    sample_fine=None(기본)이면 기존과 동일하게 매크로 단독 결과만 반환.

    floor_threshold (158차 추가): macro/fine 양쪽 계산에 동일하게 적용.
    기본 0.02 = 157차 패치 이전(버그) 재현, 0.001 =
    ROUTE_CURVE_NEGLIGIBLE_THRESHOLD(157차 패치) 재현.
    """
    macro = _route_curvature_single_pass(points, distances, sample, road_limit_speed, floor_threshold)
    if not sample_fine:
        return macro
    fine = _route_curvature_single_pass(points, distances, sample_fine, road_limit_speed, floor_threshold)
    if not fine:
        return macro
    if not macro:
        return fine

    macro_dists = [m[0] for m in macro]

    def _nearest_macro(dist):
        # 이진탐색 없이 선형 탐색해도 충분히 짧은 리스트(row당 최대 수십개)
        best = min(macro, key=lambda m: abs(m[0] - dist))
        return best

    merged = []
    for dist, curv_fine, speed_fine in fine:
        m_dist, curv_macro, speed_macro = _nearest_macro(dist)
        if speed_fine <= speed_macro:
            merged.append((dist, curv_fine, speed_fine))
        else:
            merged.append((dist, curv_macro, speed_macro))
    return merged


def route_curvature_underestimate_scan(rows, min_gap_kph=15.0):
    """naviPaths 컬럼이 있는 CSV(extract_log.py --with-navi-paths)에서,
    실제 발행된 route desiredSpeed(src=="route" 구간)와
    recompute_route_curvature_speed()로 그 시점 실측 폴리라인에서 직접
    재계산한 최소 speed_cap을 비교. 재계산 최소값이 발행값보다
    min_gap_kph 이상 낮다면 -- 즉 "실제 폴리라인 형상만으로도 이미
    이만큼 낮췄어야 했는데 실제로는 그러지 않았다"는 뜻이면, chord
    길이(sample) 문제가 아니라 다른 로직(역방향DP의 time_delay/margin
    스케줄링, 또는 폴리라인 자체가 애초에 완만하게 들어옴)이 원인임을
    시사. 반대로 재계산 최소값도 발행값과 비슷하게 높다면(=폴리라인
    자체가 이미 완만함), 89/90차가 의심한 "지도 데이터의 코너 형상
    자체가 뭉툭함" 가설을 직접 뒷받침.
    행마다 naviPaths가 채워져 있어야 하므로 --with-navi-paths로 뽑은
    CSV에서만 유의미한 결과가 나온다(빈 값 행은 건너뜀).
    """
    results = []
    for r in rows:
        naq = r.get("naviPaths", "")
        if not naq:
            continue
        if r.get("src", "") != "route":
            continue
        try:
            published = float(r.get("desiredSpeed", ""))
        except (TypeError, ValueError):
            continue
        points, distances = parse_navi_paths(naq)
        recomputed = recompute_route_curvature_speed(points, distances)
        if not recomputed:
            continue
        min_dist, min_curv, min_speed = min(recomputed, key=lambda x: x[2])
        gap = published - min_speed
        if gap >= min_gap_kph:
            results.append({
                "t": r.get("t"),
                "published_desiredSpeed": round(published, 1),
                "recomputed_min_speed": round(min_speed, 1),
                "recomputed_min_speed_dist_m": round(min_dist, 1),
                "recomputed_min_curvature": round(min_curv, 5),
                "gap_kph": round(gap, 1),
            })
    return results


def required_decel_gap_scan(rows, near_stop_target_kph=15.0, detection_search_s=40.0,
                             min_regression_points=5, turn_confirm_deg=15.0,
                             turn_confirm_window_s=8.0):
    """(2026-08-30, 150차 신규) 149차가 898edd0f96 seg16/17 rightBlinker
    이벤트 1건에서 수작업으로 계산했던 "fine 곡률 최초 감지 시점부터
    실제 회전 진입까지, liveRouteSpeed 실측 감속률이 필요감속률 대비
    얼마나 부족한가"를 여러 이벤트에 자동 적용하는 전수 스캐너.
    --with-navi-paths로 뽑은 CSV(naviPaths/liveRouteSpeed 컬럼 필수) 전용.

    **이벤트 식별**: leftBlinker/rightBlinker가 False->True로 바뀌는
    시점(t_arrive)을 "실제 회전 진입(교차로 도달)" 시점의 근사 프록시로
    삼는다(149차 사례와 동일 패턴). steeringAngleDeg 단독 기반(비교차로
    급커브) 탐지는 미지원 -- 아래 한계 참고.

    각 이벤트에서:
    1. t_arrive에서 과거 방향으로 최대 detection_search_s초까지 프레임을
       하나씩 훑으며(naviPaths가 있는 프레임마다
       recompute_route_curvature_speed(sample=4, sample_fine=1) 재계산)
       fine 최소 speed_cap이 **처음으로** near_stop_target_kph 이하로
       내려가는 가장 이른(=t_arrive에서 가장 먼) 프레임을 "최초 감지
       시점"(t_detect)으로 채택 -- 149차의 수작업 절차(fine이 처음
       target을 잡아낸 시점)를 그대로 자동화. detection_search_s 안에
       그런 프레임이 전혀 없으면(=애초에 조기감지가 안 됐거나 코너가
       근정지급이 아님) 이벤트 skip.
    2. t_detect ~ t_arrive 구간에서 liveRouteSpeed가 숫자로 파싱되는
       (=carrotMan.szPosRoadName에 "route=" 텍스트가 실제로 발행된)
       행만 모아 (t, liveRouteSpeed) 최소자승 선형회귀 기울기를
       actual_decel_kphps(감속=양수 부호로 반전)로 채택. 표본이
       min_regression_points 미만이면 이벤트 skip(회귀 신뢰불가).
    3. required_decel_kphps = (routeSpeed_detect_kph - target_speed_kph) /
       (t_arrive - t_detect) -- 149차와 동일하게 "감지 시점부터 실제
       회전 진입까지 걸린 실측 경과시간"을 그대로 분모로 쓴다(거리/속도
       근사가 아니라 실제 타임스탬프 차이라 물리적으로 더 정확함).
       **주의(중요)**: 시작 속도로 vEgo가 아니라 감지 시점의
       liveRouteSpeed(=route 자신의 내부 스케줄 값)를 쓴다 -- vEgo는
       이미 cam/vturn 등 다른 소스에 의해 낮게 눌려있는 경우가 많아(이
       route/vturn 예시에서도 t_detect 시점 vEgo=52kph인데
       liveRouteSpeed=109kph로 거의 2배 차이), vEgo를 쓰면 "route
       자신이 그 시점부터 target까지 실제로 얼마나 감속해야 했는가"를
       과소평가하게 된다(150차 최초 구현 시 vEgo를 썼다가 이 괴리로
       required<actual이라는 149차와 모순된 결과가 나와 수정됨).
       liveRouteSpeed가 t_detect 시점에 숫자로 파싱 안 되면(빈 문자열)
       그 프레임 기준 가장 가까운 유효 liveRouteSpeed 값으로 대체하고,
       그마저 없으면 이벤트 skip.
    4. gap_kphps = required_decel_kphps - actual_decel_kphps,
       gap_ratio = required_decel_kphps / actual_decel_kphps
       (actual_decel_kphps <= 0.05 kph/s면 division 방지를 위해
       gap_ratio=None 처리, gap_kphps는 계산).

    반환: 이벤트 dict list, gap_ratio 내림차순(비교 불가 항목은 뒤로) 정렬.
    각 dict: t_arrive, t_detect, blinker_side, route_speed_detect_kph
    (=t_detect 시점 liveRouteSpeed, vEgo 아님), target_speed_kph,
    detect_lead_time_s(=t_arrive-t_detect), required_decel_kphps,
    actual_decel_kphps, gap_kphps, gap_ratio, n_regression_points.

    **한계**:
    - blinker 미점등 회전(비교차로 급커브, 로터리 등)은 탐지 못함 --
      steeringAngleDeg 기반 확장은 미작성(다음 세션 과제).
    - t_arrive(blinker onset)는 "실제 회전 진입"의 근사 프록시일 뿐 --
      운전자/내비 안내가 blinker를 교차로 도달 몇 초 전에 켜는지는
      상황마다 다르므로, 특히 blinker가 아주 늦게(교차로 코앞에서)
      켜지는 경우 required_decel_kphps가 과대평가될 수 있음.
    - naviPaths가 매 프레임 존재하지 않으면(예: route 비활성 구간) 그
      구간은 감지 시도 자체가 스킵됨 -- t_detect가 실제보다 늦게(더
      가까운 시점으로) 채택될 수 있음.
    - 결과값은 1차 스크리닝용 -- accel_limit 튜닝처럼 안전에 직결되는
      결정 전엔 149차처럼 개별 이벤트를 수작업으로도 재검증할 것.
    - 같은 t_arrive 부근에 같은 방향 blinker가 짧게 여러 번 켜졌다
      꺼지는 경우(차선변경 취소 후 재점등 등) 이벤트가 중복 카운트될
      수 있음 -- 중복 제거 로직 없음.

    turn_confirm_deg/turn_confirm_window_s (2026-08-30, 152차 신규,
    버그수정): 초기 버전은 t_detect에서 감지한 "먼 곳의 근정지급 커브"와
    t_arrive의 blinker onset이 같은 물리적 지점이라고 무조건 가정했으나,
    898edd0f96 seg10 실측 검증에서 blinker가 4초 만에 꺼지고 steer가
    0deg 근처에 머문 채 liveRouteSpeed가 계속 상승하는 "무관한 차선변경
    blinker"가 근정지급 커브 감지와 우연히 시간상 이어져 허위 이벤트로
    잡히는 사례 발견(gap_ratio=14.35로 진짜 이벤트보다도 커서 그대로
    뒀으면 최우선순위로 오판될 뻔함). t_arrive 이후 turn_confirm_window_s
    (기본 8초) 이내에 steeringAngleDeg 절대값이 turn_confirm_deg(기본
    15도) 이상인 프레임이 한 번이라도 있어야 "실제 회전이 뒤따랐다"고
    보고 이벤트를 채택한다. 이 조건이 없으면 이벤트는 조용히 스킵됨
    (반환값에 제외 사유는 남지 않음 -- 필요시 디버깅용 별도 로깅 추가
    가능).
    """
    events = []
    prev_left = prev_right = False
    for i, r in enumerate(rows):
        left = _b(r, "leftBlinker")
        right = _b(r, "rightBlinker")
        if left and not prev_left:
            events.append((i, "left"))
        if right and not prev_right:
            events.append((i, "right"))
        prev_left, prev_right = left, right

    results = []
    for idx, side in events:
        try:
            t_arrive = float(rows[idx].get("t"))
        except (TypeError, ValueError):
            continue

        # 1) t_arrive에서 과거로 훑으며 fine target이 처음(=가장 이른 시점) 근정지급으로
        #    내려가는 프레임을 찾는다. "가장 이른" 프레임을 얻기 위해 조건을 만족하는
        #    동안 계속 갱신하며 더 먼 과거로 이동한다.
        detect_idx = None
        target_speed_kph = None
        j = idx
        while j >= 0:
            try:
                tj = float(rows[j].get("t"))
            except (TypeError, ValueError):
                j -= 1
                continue
            if t_arrive - tj > detection_search_s:
                break
            naq = rows[j].get("naviPaths", "")
            if naq:
                points, distances = parse_navi_paths(naq)
                recomputed = recompute_route_curvature_speed(points, distances, sample=4, sample_fine=1)
                if recomputed:
                    _, _, min_speed = min(recomputed, key=lambda x: x[2])
                    if min_speed <= near_stop_target_kph:
                        detect_idx = j
                        target_speed_kph = min_speed
            j -= 1
        if detect_idx is None:
            continue  # 이 이벤트는 근정지급 조기감지 자체가 없었음 -- 스캔 대상 아님

        t_detect = float(rows[detect_idx].get("t"))
        detect_lead_time_s = t_arrive - t_detect
        if detect_lead_time_s <= 0:
            continue

        # 152차 신규: t_arrive 이후 실제 회전이 뒤따르는지 확인 (차선변경 등
        # 무관한 blinker와 근정지급 커브 감지가 우연히 시간상 인접해 오탐되는
        # 것 방지 -- seg10 실측 사례 참고)
        turn_confirmed = False
        k = idx
        while k < len(rows):
            try:
                tk = float(rows[k].get("t"))
            except (TypeError, ValueError):
                k += 1
                continue
            if tk - t_arrive > turn_confirm_window_s:
                break
            try:
                steer_abs = abs(float(rows[k].get("steeringAngleDeg", 0) or 0))
            except (TypeError, ValueError):
                steer_abs = 0.0
            if steer_abs >= turn_confirm_deg:
                turn_confirmed = True
                break
            k += 1
        if not turn_confirmed:
            continue

        # detect_idx 시점의 liveRouteSpeed(=route 자신의 스케줄 값, vEgo 아님) --
        # 빈 문자열이면 가까운 유효값으로 폴백(전후 탐색, 최대 detection_search_s 범위 내)
        def _nearest_live_route_speed(center_idx):
            lrs = rows[center_idx].get("liveRouteSpeed", "")
            if lrs:
                try:
                    return float(lrs)
                except ValueError:
                    pass
            for delta in range(1, 40):
                for cand in (center_idx - delta, center_idx + delta):
                    if 0 <= cand < len(rows):
                        v = rows[cand].get("liveRouteSpeed", "")
                        if v:
                            try:
                                return float(v)
                            except ValueError:
                                continue
            return None

        v_detect_kph = _nearest_live_route_speed(detect_idx)
        if v_detect_kph is None:
            continue

        # 2) t_detect~t_arrive 구간 liveRouteSpeed 선형회귀
        reg_pts = []
        for k in range(detect_idx, idx + 1):
            lrs = rows[k].get("liveRouteSpeed", "")
            if lrs:
                try:
                    tk = float(rows[k].get("t"))
                    reg_pts.append((tk, float(lrs)))
                except ValueError:
                    pass
        if len(reg_pts) < min_regression_points:
            continue

        ts = [p[0] for p in reg_pts]
        vs = [p[1] for p in reg_pts]
        n = len(ts)
        t_mean = sum(ts) / n
        v_mean = sum(vs) / n
        num = sum((t - t_mean) * (v - v_mean) for t, v in zip(ts, vs))
        den = sum((t - t_mean) ** 2 for t in ts)
        slope_kphps = (num / den) if den else 0.0
        actual_decel_kphps = -slope_kphps  # 감속(속도 감소)=양수로 부호 반전

        required_decel_kphps = (v_detect_kph - target_speed_kph) / detect_lead_time_s
        gap_kphps = required_decel_kphps - actual_decel_kphps
        gap_ratio = (required_decel_kphps / actual_decel_kphps) if actual_decel_kphps > 0.05 else None

        results.append({
            "t_arrive": round(t_arrive, 2),
            "t_detect": round(t_detect, 2),
            "blinker_side": side,
            "route_speed_detect_kph": round(v_detect_kph, 1),
            "target_speed_kph": round(target_speed_kph, 1),
            "detect_lead_time_s": round(detect_lead_time_s, 2),
            "required_decel_kphps": round(required_decel_kphps, 2),
            "actual_decel_kphps": round(actual_decel_kphps, 2),
            "gap_kphps": round(gap_kphps, 2),
            "gap_ratio": round(gap_ratio, 2) if gap_ratio is not None else None,
            "n_regression_points": n,
        })

    results.sort(key=lambda x: (x["gap_ratio"] is None, -(x["gap_ratio"] or 0)))
    return results


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
