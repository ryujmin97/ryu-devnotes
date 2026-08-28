#!/usr/bin/env python3
"""111차 신규: 대시캠 화면녹화 클립(_clip.mp4)이 어느 route CSV 구간(t범위)에
대응하는지 매칭하는 도구.

배경: carrotweb HUD 시계는 시:분만 표시(초 단위 없음) + screenrecorder.cc가
파일명에 남기는 타임스탬프는 클립 "저장(종료)" 시각이라 클립 시작 시각과
초 단위 어긋남이 있음(19차/62차 계열에서 이미 알려진 문제, `_clip.mp4` 실제
길이 참고). 따라서 파일명 시:분 매칭만으로는 route CSV의 정확한 t를 특정할
수 없다 -- 실측(110차/111차)으로 최대 ~50초까지 벗어나는 사례 확인.

해법: 파일명 매칭 대신 **물리적 특징(blinker 클러스터 + 급감속 강도)의
순서/상대 간격**으로 매칭한다.
1. `analysis_helpers`류로 route CSV의 blinker(좌/우) 활성 클러스터 전부 추출.
2. 각 클러스터 구간의 min_aEgo(급감속 강도)를 계산.
3. 여러 클립이 있을 경우, 파일명 시각차(초)와 후보 클러스터 쌍의 시간차(t초)를
   비교 -- 오차 ±10초 이내면 강한 매칭 후보로 채택(저장 지연/버퍼링 감안).
4. 시각적 교차검증(권장, 필수는 아님): 후보 클러스터 시각 부근의 route
   qcamera.ts에서 프레임 추출 -> 클립 프레임과 배경/차량 대조.

**주의**: 이 도구는 "언제(t) 어떤 이벤트가 일어났는가"를 특정하는 것이지,
화면에 보이는 a_ego/a_target/a_out 그래프 자체를 재현하지 않는다(그건 실제
MPC 솔버 재실행이 필요 -- 별도 작업).

사용 예:
    from match_dashcam_clip_to_route import find_blinker_clusters, match_clips

    rows = load_route_csv(...)
    clusters = find_blinker_clusters(rows)  # [(t_start,t_end,min_aEgo,min_aEgo_t), ...]
    matches = match_clips(clusters, clip_filename_seconds=[113702, 113848],
                           tolerance_s=10)
"""


def find_blinker_clusters(rows, gap_merge_s=0.0):
    """route CSV rows(list of dict, 't'/'leftBlinker'/'rightBlinker'/'aEgo' 문자열
    필드 포함)에서 blinker 활성 구간을 클러스터링하고, 각 구간 +8초 이내의
    min_aEgo/해당 시각을 함께 반환한다.
    반환: [{"t_start", "t_end", "min_aEgo", "min_aEgo_t"}, ...] (시간순)
    """
    def _b(v):
        return v in ("True", "1", "true", True, 1)

    rows_sorted = sorted(rows, key=lambda r: float(r["t"]))
    clusters = []
    cur = None
    for r in rows_sorted:
        t = float(r["t"])
        active = _b(r.get("leftBlinker")) or _b(r.get("rightBlinker"))
        if active:
            if cur is None:
                cur = [t, t]
            else:
                cur[1] = t
        else:
            if cur is not None:
                clusters.append(tuple(cur))
                cur = None
    if cur is not None:
        clusters.append(tuple(cur))

    out = []
    for t_start, t_end in clusters:
        window = [r for r in rows_sorted
                  if t_start - 3 <= float(r["t"]) <= t_end + 8]
        if not window:
            continue
        min_row = min(window, key=lambda r: float(r["aEgo"]))
        out.append({
            "t_start": t_start, "t_end": t_end,
            "min_aEgo": float(min_row["aEgo"]),
            "min_aEgo_t": float(min_row["t"]),
        })
    return out


def match_clips(clusters, clip_filename_seconds, tolerance_s=10,
                 min_aEgo_thresh=-1.5):
    """clip_filename_seconds: 클립 파일명에서 뽑은 HHMMSS(정수, 시각순 정렬)
    리스트. 클러스터 중 min_aEgo가 min_aEgo_thresh보다 작은(=유의미한 급감속)
    것들만 후보로 추리고, 후보 쌍의 시간차(t)와 파일명 시각차(초)를 비교해
    tolerance_s 이내면 순서대로 매칭한다.
    반환: [(clip_index, cluster_dict, delta_s_error), ...] 또는 매칭 실패 시 []
    주의: 클립이 3개 이상이면 조합 폭발 -- 2~3개 클립 전용, 그 이상은 수동 검토.
    """
    def hhmmss_to_s(v):
        h, m, s = v // 10000, (v // 100) % 100, v % 100
        return h * 3600 + m * 60 + s

    candidates = sorted(
        [c for c in clusters if c["min_aEgo"] < min_aEgo_thresh],
        key=lambda c: c["min_aEgo_t"])

    if len(clip_filename_seconds) < 2 or len(candidates) < len(clip_filename_seconds):
        return []

    file_gaps = [hhmmss_to_s(clip_filename_seconds[i + 1]) - hhmmss_to_s(clip_filename_seconds[i])
                 for i in range(len(clip_filename_seconds) - 1)]

    # 후보 중 연속된 len(clips)개 조합을 슬라이딩하며 시간차 오차 검사
    n = len(clip_filename_seconds)
    best = None
    for start_idx in range(len(candidates) - n + 1):
        window = candidates[start_idx:start_idx + n]
        cand_gaps = [window[i + 1]["min_aEgo_t"] - window[i]["min_aEgo_t"]
                     for i in range(n - 1)]
        err = sum(abs(cg - fg) for cg, fg in zip(cand_gaps, file_gaps))
        if best is None or err < best[0]:
            best = (err, window)

    if best is None or best[0] > tolerance_s * (n - 1):
        return []

    return [(i, c, None) for i, c in enumerate(best[1])]
