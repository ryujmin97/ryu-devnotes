#!/usr/bin/env python3
"""310차: 307차 shadow tracker(routeProvisional*) 최초 실차 로그 분석.

307차는 min_points=2 게이트가 고립된(orphan) 1포인트 후보를 노이즈로
오인해 제거할 수 있다는 가설(306차, ep108)을 실차로 검증하기 위해
production 로직과 완전히 분리된 shadow tracker를 계측만 해두었다
(PROVISIONAL_PROMOTE_STREAK=3, NEEDS_VALIDATION). 이 스크립트는 020ea86
(307차) 반영이 확인된 첫 실차 로그(x17seg, 17개 세그먼트)에서 그 값을
검증한다.

방법:
  routeProvisionalActive/Streak/Dist/Speed/MatchError, routeApexMode,
  routeClusterCount, routeOrphanSingletonCount 컬럼을 시간순으로 훑으며
  "provisional episode"를 재구성한다. 한 episode = streak가 1에서
  시작해 연속으로 증가하다(계속 매칭) 리셋되는 구간 하나(같은 orphan
  후보를 계속 추적한 연속 구간). streak가 이전 값보다 커지지 않고
  1로 재시작하면 새 episode로 취급한다(다른 물리적 후보로 hand-off).

  각 episode에 대해 다음을 함께 기록해 "이 orphan이 실제로 production
  apex가 없던 공백을 메웠을 후보였는지"를 1차 필터링한다:
    - max_streak (PROVISIONAL_PROMOTE_STREAK=3 승격 여부)
    - 동시 구간의 routeApexMode 최빈값/집합 -- 'none'/'lost'가 섞여
      있으면 그 프레임엔 production이 apex가 없었다는 뜻(design A가
      개입했다면 차이가 났을 후보). 전부 'matched'/'held'/'passed'면
      이미 클러스터 경로로 apex가 잡혀 있어 orphan 승격이 redundant.
    - 동시 구간 routeClusterCount 최소값(0이면 그 프레임엔 정상
      클러스터가 전혀 없었다는 뜻).

  이 스크립트는 순수 관측/집계이며 ryu 코드를 전혀 수정하지 않는다.
  "실제 커브였는가"는 로그만으로 확정할 수 없으므로(§28), 승격 후보
  중 apex_mode 공백이 겹치는 상위 사례는 qcamera 육안 대조를 다음
  단계로 권장한다(콘솔 출력에 프레임 시각 목록 제공).

사용:
    python3 sim_route_310_provisional_streak_real_corpus.py <route.csv>
      [--promote-streak 3] [--check-cruise] [--cluster-gap-s 5.0]

[313차 추가] --check-cruise / --cluster-gap-s:
  311/312차가 대화식 python 후처리로 확인한 두 가지를 스크립트 정식
  옵션으로 편입한다(§21 -- 로직 재구현 아님, 두 세션에서 검증된 방식
  그대로 옮김).
    --check-cruise: 근접+이동중(gap_overlap) episode 각각에 대해 구간
      전체의 cruiseEnabled 값 집합을 계산해 True(전체 개입)/False(전체
      수동)/mixed(구간 중 전환)로 분류하고, True만 별도로 "ADAS engaged"
      상위 목록으로 출력한다. cruiseEnabled=False 구간은 apex 공백이
      실제 차량 거동에 영향을 주지 못하므로(311차 발견) 우선순위에서
      낮춘다.
    --cluster-gap-s (기본 5.0): ADAS engaged episode들을 같은 seg 내에서
      시간 gap이 이 값 이하면 같은 물리적 위치로 묶는다(312차 발견 --
      routeProvisionalStreak가 하나의 커브 접근 중 여러 번 끊겨 episode
      수가 실제 물리적 위치 수보다 부풀려짐). 클러스터링 결과는
      "episode 건수"가 아니라 "물리적 위치 건수"로 요약 출력된다.
"""
import argparse
import csv
import sys
from collections import Counter


def load_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r)


def to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def to_bool(v):
    return str(v).strip().lower() in ("true", "1")


def build_episodes(rows):
    """연속 provisional streak 구간을 episode로 재구성.

    반환: list of dict(start_t, end_t, n_frames, max_streak, promoted,
    apex_modes(Counter), min_cluster_count, dist, speed, max_match_error)
    """
    episodes = []
    cur = None
    prev_streak = 0

    for row in rows:
        active = to_bool(row.get("routeProvisionalActive", ""))
        streak = to_int(row.get("routeProvisionalStreak", "0"))
        t = to_float(row.get("t", "0"))
        mode = row.get("routeApexMode", "")
        cluster_count = to_int(row.get("routeClusterCount", "0"))
        dist = to_float(row.get("routeProvisionalDist", "0"))
        speed = to_float(row.get("routeProvisionalSpeed", "0"))
        match_err = to_float(row.get("routeProvisionalMatchError", "0"))
        cruise = to_bool(row.get("cruiseEnabled", ""))

        if not active or streak <= 0:
            if cur is not None:
                episodes.append(cur)
                cur = None
            prev_streak = 0
            continue

        # streak가 이전보다 커지지 않고(재시작=1 포함) hand-off된 경우
        # 새 episode로 취급.
        if cur is None or streak <= prev_streak:
            if cur is not None:
                episodes.append(cur)
            cur = {
                "start_t": t, "end_t": t, "n_frames": 0, "max_streak": 0,
                "apex_modes": Counter(), "min_cluster_count": cluster_count,
                "dist_first": dist, "dist_last": dist,
                "speed_first": speed, "speed_last": speed,
                "max_match_error": 0.0, "seg": row.get("seg", ""),
                "vegos": [], "cruise_states": set(),
            }

        cur["end_t"] = t
        cur["n_frames"] += 1
        cur["max_streak"] = max(cur["max_streak"], streak)
        cur["apex_modes"][mode] += 1
        cur["min_cluster_count"] = min(cur["min_cluster_count"], cluster_count)
        cur["dist_last"] = dist
        cur["speed_last"] = speed
        cur["max_match_error"] = max(cur["max_match_error"], match_err)
        cur.setdefault("vegos", []).append(to_float(row.get("vEgo", "0")))
        cur.setdefault("cruise_states", set()).add(cruise)
        prev_streak = streak

    if cur is not None:
        episodes.append(cur)
    return episodes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--promote-streak", type=int, default=3,
                     help="PROVISIONAL_PROMOTE_STREAK 비교 기준(기본 3, carrot_man.py 현재값과 동일)")
    ap.add_argument("--near-threshold-m", type=float, default=150.0,
                     help="[310차 계속 수정] 이 값 미만 거리만 '근접(진짜 커브 후보)'로 분류. "
                          "이 값 이상은 naviPaths lookahead 끝단(약 500m) 아티팩트 의심 버킷("
                          "'원거리') 으로 분리한다. 최초 310차 콘솔 출력에서는 이 분류가 수동이라 "
                          "500~430m 원거리 사례를 근접으로 잘못 인용하는 사고가 있었음(정정: "
                          "FINDINGS.md 310차 참고) -- 이후 항상 스크립트가 자동 분류하도록 고정.")
    ap.add_argument("--moving-min-vego", type=float, default=3.0,
                     help="[310차 계속 수정] episode 평균 vEgo(m/s)가 이 값 미만이면 '정차 중 "
                          "고립후보 유지'로 자명하게 분류해 상위 목록에서 제외(예: 신호대기, "
                          "정체). vEgo≈0이면 predicted≈locked_dist라 streak가 무의미하게 커지는 "
                          "게 당연한 결과이므로 이런 케이스가 streak 상위 랭킹을 왜곡하지 않게 "
                          "한다.")
    ap.add_argument("--check-cruise", action="store_true",
                     help="[313차 신규] 근접+이동중 episode를 cruiseEnabled 구간 전체 값으로 "
                          "True(ADAS 개입)/False(운전자 수동)/mixed(전환)로 분류해 별도 출력한다. "
                          "311차 발견 -- cruiseEnabled=False 구간은 apex 공백이 실제 차량 거동에 "
                          "영향을 주지 못하므로 우선순위에서 낮춘다.")
    ap.add_argument("--cluster-gap-s", type=float, default=5.0,
                     help="[313차 신규] --check-cruise와 함께 사용. ADAS engaged episode들을 "
                          "같은 seg 내 시간 gap이 이 값(초) 이하면 같은 물리적 위치로 묶는다(312차 "
                          "발견 -- routeProvisionalStreak가 하나의 커브 접근 중 여러 번 끊겨 "
                          "episode 수가 실제 물리적 위치 수보다 부풀려짐).")
    args = ap.parse_args()

    rows = load_rows(args.csv_path)
    if not rows or "routeProvisionalActive" not in rows[0]:
        print(f"[SKIP] {args.csv_path}: routeProvisional* 컬럼 없음 "
              f"(020ea86 이전 로그이거나 extract_log.py 미갱신 버전으로 추출됨)")
        sys.exit(1)

    episodes = build_episodes(rows)
    print(f"총 provisional episode 수: {len(episodes)}")

    streak_hist = Counter(e["max_streak"] for e in episodes)
    print("\nmax_streak 분포:")
    for k in sorted(streak_hist):
        print(f"  streak={k}: {streak_hist[k]}건")

    promoted = [e for e in episodes if e["max_streak"] >= args.promote_streak]
    print(f"\n승격 기준(streak>={args.promote_streak}) 도달 episode: {len(promoted)}/{len(episodes)}건")

    # apex_mode 공백(none/lost)이 섞인 episode = production이 이 구간에
    # apex를 전혀 못 잡고 있었을 가능성 -- design A 개입 시 차이가 났을
    # 진짜 후보.
    for e in promoted:
        e["avg_vego"] = sum(e.get("vegos", [0.0])) / max(1, len(e.get("vegos", [1])))
        e["gap"] = e["apex_modes"].get("none", 0) + e["apex_modes"].get("lost", 0)

    gap_overlap = [e for e in promoted if e["gap"] > 0]
    redundant = [e for e in promoted if e not in gap_overlap]

    print(f"  - 그중 production apex_mode가 none/lost로 겹친 구간(공백 후보): {len(gap_overlap)}건")
    print(f"  - 그중 production이 이미 matched/held/passed였던 구간(redundant): {len(redundant)}건")

    # [310차 계속 수정] 근접/원거리, 이동/정차를 스크립트가 자동으로
    # 나눈다. 최초 310차 세션에서 이 분류를 수동으로 하다가 500~430m
    # (원거리, lookahead 끝단 부근) 사례를 근접 진짜 커브 후보로 잘못
    # 인용한 사고가 있었음(FINDINGS.md 310차 정정 참고) -- 재발 방지.
    def is_near(e):
        return max(e["dist_first"], e["dist_last"]) < args.near_threshold_m

    def is_moving(e):
        return e["avg_vego"] >= args.moving_min_vego

    near_moving = [e for e in gap_overlap if is_near(e) and is_moving(e)]
    near_stationary = [e for e in gap_overlap if is_near(e) and not is_moving(e)]
    far_moving = [e for e in gap_overlap if not is_near(e) and is_moving(e)]
    far_stationary = [e for e in gap_overlap if not is_near(e) and not is_moving(e)]

    print(f"\n[4분면 분류] (근접 임계값={args.near_threshold_m}m, 이동 임계값 avg_vEgo>="
          f"{args.moving_min_vego}m/s)")
    print(f"  근접+이동중(진짜 커브 후보, 최우선 qcamera 대조 대상): {len(near_moving)}건")
    print(f"  근접+정차중(신호대기 등 자명, 낮은 우선순위): {len(near_stationary)}건")
    print(f"  원거리+이동중(lookahead 끝단 아티팩트 의심, 코드 레벨 확인 필요): {len(far_moving)}건")
    print(f"  원거리+정차중(자명한 비이슈): {len(far_stationary)}건")

    if near_moving:
        print("\n[근접+이동중 상세] (qcamera 육안 대조 최우선 권장 목록)")
        for e in sorted(near_moving, key=lambda x: -x["max_streak"])[:20]:
            modes = dict(e["apex_modes"])
            print(f"  seg={e.get('seg','?')} t={e['start_t']:.2f}~{e['end_t']:.2f}s "
                  f"max_streak={e['max_streak']} n_frames={e['n_frames']} "
                  f"avg_vEgo={e['avg_vego']:.1f}m/s "
                  f"dist={e['dist_first']:.1f}->{e['dist_last']:.1f}m "
                  f"speed={e['speed_first']:.1f}->{e['speed_last']:.1f}km/h "
                  f"min_cluster_count={e['min_cluster_count']} "
                  f"max_match_error={e['max_match_error']:.2f}m "
                  f"apex_modes={modes}")

    if far_moving:
        print("\n[원거리+이동중 상세] (lookahead 끝단 아티팩트 의심 -- qcamera로 확정 불가 영역, "
              "코드 레벨 조사 우선)")
        for e in sorted(far_moving, key=lambda x: -x["max_streak"])[:15]:
            modes = dict(e["apex_modes"])
            print(f"  seg={e.get('seg','?')} t={e['start_t']:.2f}~{e['end_t']:.2f}s "
                  f"max_streak={e['max_streak']} avg_vEgo={e['avg_vego']:.1f}m/s "
                  f"dist={e['dist_first']:.1f}->{e['dist_last']:.1f}m apex_modes={modes}")

    if args.check_cruise and near_moving:
        # [313차 신규, 311/312차 대화식 로직 편입 -- §21] cruiseEnabled
        # 구간 전체 값으로 분류.
        def cruise_label(e):
            states = e.get("cruise_states", set())
            if states == {True}:
                return "True"
            if states == {False}:
                return "False"
            return "mixed"

        for e in near_moving:
            e["cruise_label"] = cruise_label(e)

        cruise_true = [e for e in near_moving if e["cruise_label"] == "True"]
        cruise_false = [e for e in near_moving if e["cruise_label"] == "False"]
        cruise_mixed = [e for e in near_moving if e["cruise_label"] == "mixed"]

        print(f"\n[--check-cruise] 근접+이동중 {len(near_moving)}건의 cruiseEnabled 구간 분류:")
        print(f"  cruiseEnabled=True(ADAS 개입, 실제 의미있는 후보): {len(cruise_true)}건")
        print(f"  cruiseEnabled=False(운전자 수동조작, apex 공백 무해): {len(cruise_false)}건")
        print(f"  mixed(구간 중 전환): {len(cruise_mixed)}건")

        # [313차 신규, 312차 발견 편입] 같은 seg 내에서 시간 gap이
        # --cluster-gap-s 이하인 ADAS engaged episode들을 하나의 물리적
        # 위치로 묶는다. episode 수가 아니라 물리적 위치 수를 본다.
        by_seg = {}
        for e in sorted(cruise_true, key=lambda x: x["start_t"]):
            by_seg.setdefault(e.get("seg", ""), []).append(e)

        locations = []
        for seg, seg_episodes in by_seg.items():
            cur_loc = None
            for e in seg_episodes:
                if cur_loc is None or e["start_t"] - cur_loc["end_t"] > args.cluster_gap_s:
                    if cur_loc is not None:
                        locations.append(cur_loc)
                    cur_loc = {"seg": seg, "start_t": e["start_t"], "end_t": e["end_t"],
                               "episodes": [e]}
                else:
                    cur_loc["end_t"] = max(cur_loc["end_t"], e["end_t"])
                    cur_loc["episodes"].append(e)
            if cur_loc is not None:
                locations.append(cur_loc)

        print(f"\n[위치 군집화] (gap<={args.cluster_gap_s}s 기준) ADAS engaged "
              f"{len(cruise_true)}건 episode -> 물리적 위치 {len(locations)}곳:")
        for loc in sorted(locations, key=lambda x: -len(x["episodes"])):
            print(f"  seg={loc['seg']} t={loc['start_t']:.2f}~{loc['end_t']:.2f}s "
                  f"episode {len(loc['episodes'])}건")

    # 최근접 orphan 존재 빈도(전체 프레임 대비) -- 참고용
    total_frames = len(rows)
    orphan_frames = sum(1 for r in rows if to_int(r.get("routeOrphanSingletonCount", "0")) > 0)
    print(f"\n전체 {total_frames}프레임 중 orphan(고립 후보) 존재 프레임: "
          f"{orphan_frames}건 ({100*orphan_frames/total_frames:.2f}%)")


if __name__ == "__main__":
    main()
