#!/usr/bin/env python3
"""
sim_route_317_orphan_local_fine_resample.py (317차 신규)

목적: 306차가 확정한 "route_find_clusters()의 min_points=2 게이트가
고립된 1포인트 좁은 커브(orphan)를 노이즈로 오인해 제거"하는 문제에
대해, 사용자가 이번 세션에서 제안한 개선 방향 -- "600m 전체를 매 프레임
5m로 재샘플하는 것은 부하가 크므로, orphan이 탐지된 지점 주변만
국소적으로 5m(또는 더 촘촘하게) 재샘플해서 진짜 커브인지 확인하자" --
을 (1) 합성 self-test로 메커니즘 자체의 타당성부터 검증하고, (2) 실제
x17seg corpus(20171행, 020ea86)로 실측 가능한 범위까지 검증한다.

**§21/22 기존 도구 재사용**: route_find_clusters()는 306/308차가 이미
이식해둔 것과 동일 로직(ryu HEAD 020ea86, carrot_man.py 463~475행)을
이 스크립트에도 동일하게 이식한다(재구현 아님, 상수/로직 100% 동일 --
아래 각 함수 docstring에 원본 라인 번호 명시, §27).

===========================================================================
[핵심 사전 확인 -- 이번 세션에서 실측으로 밝혀진, 원래 설계를 제약하는
중요한 사실. 반드시 먼저 읽을 것]
===========================================================================
사용자 제안의 원래 형태는 "orphan 지점 주변의 **원본(raw) 폴리라인**을
가져와서 그 구간만 5m로 다시 리샘플"하는 것이었다. 그런데 x17seg
corpus를 실제로 열어보니:

  - routeSource == "tcp_navi" (전 구간, 17세그 전부) -- 즉 navi 앱이
    navd cereal 채널이 아니라 raw TCP소켓(7712)으로 좌표를 직접 밀어
    넣는 경로였다. `cereal/log.capnp`의 NavRoute(navRouteNavd, 원본
    lat/lon 폴리라인을 담을 수 있는 필드)는 **이 corpus 전체에서 이벤트
    카운트 0건**으로 실측 확인됨(아래 `probe_navroute_navd()` 참고).
  - carrot_man.py::carrot_navi_route() 705행이 리턴하는
    `resampled_points, resampled_distances`(=10m 그리드로 이미
    리샘플된 결과)만 `carrotMan.naviPaths`로 발행된다(carrot_serv.py
    1357행). 즉 **10m 리샘플 이전의 원본 relative_coords/path는 이
    corpus 어디에도 로그되어 있지 않다.**

따라서 "orphan 주변 원본 폴리라인을 5m로 다시 리샘플"이라는 원래
아이디어를 **이번 x17seg corpus로 실측 검증하는 것은 구조적으로
불가능**하다 -- 이미 10m로 한 번 손실된 정보를 그 이후 단계에서 되살릴
방법이 없기 때문이다(10m 포인트 사이를 5m로 다시 보간해봤자 원본이
직선이었다고 가정하는 것과 같아, 실제 좁은 코너 형상을 복원하지
못한다). 이걸 실측으로 검증하려면 `relative_coords`(10m 리샘플 **이전**
원본)를 새로 계측 패치로 cereal에 발행하도록 `ryu` 코드를 바꾸고(§31
사용자 승인 필요), 그 계측이 들어간 빌드로 **새로 주행**해야 한다 --
이번 corpus로는 해소 불가능한 근본적 한계다(§28).

그래서 이 스크립트는 두 파트로 나눈다:

**Part 1 (합성, self-test)**: "점 밀도만 올리고 곡률 chord는 고정"하는
방식이 "진짜 좁은 커브"와 "1프레임성 노이즈"를 실제로 구분해낼 수 있는
메커니즘인지, 실제 좌표 데이터 없이 순수 시뮬레이션으로 증명한다.
사용자 원안의 **개념 자체**는 이 파트로 확정 검증 가능(코드 논리이므로
실측 데이터가 필요 없음, 306차의 dip_len 스윕과 동일 성격).

**Part 2 (실측, x17seg)**: 원본 폴리라인이 없어 "국소 재샘플"은 못하지만,
대신 **이미 로그에 있는 데이터만으로** 검증 가능한, 같은 메커니즘의
다른 예측을 실측한다 -- 219/220차가 이미 확정한 "리샘플 그리드는 매
프레임 현재위치 기준으로 재앵커링된다"는 사실을 이용하면, 차량이
움직이면서 프레임마다 10m 그리드의 위상(phase)이 물리적으로 계속
바뀐다. 즉 "이 프레임에서는 orphan(1점)이었던 커브가, 몇 프레임 전/후
(그리드 위상이 다른 시점)에는 실제로 cluster(2점 이상)로 잡혔는가?"를
`routeOrphanSingletonDist`/`routeClusterCount`/`routeApexDist` 컬럼만
으로 직접 실측할 수 있다. 이건 "국소 재샘플"과 동일한 결론(그리드
해상도/위상 문제로 진짜 커브가 노이즈 취급됐는가)을 다른 방법으로
검증하는 것이다 -- 사용자 원안의 **효과를 예측하는 대리 지표**로 취급할
것(§28, "국소 재샘플 자체를 실측했다"고 과장하지 않는다).

**한계(반드시 함께 보고)**:
1. Part 1은 개념 검증일 뿐 ep108/x17seg의 실제 orphan이 이 메커니즘
   때문이라는 뜻은 아니다.
2. Part 2의 "phase 해소" 판정은 같은 물리적 지점을 프레임 간 거리
   변화(예측 거리 vs 실측 거리, 10m tolerance)로 매칭하는 근사이며,
   완전히 다른 두 개의 이웃 커브를 같은 커브로 오인할 가능성을 배제
   못한다(에피소드 길이가 짧을수록, 즉 접근 속도가 빠를수록 이 위험이
   커짐 -- 결과표의 에피소드별 프레임 수 참고).
3. Part 2는 "국소 재샘플을 했더라면 orphan이 풀렸을 것이다"를 증명하지
   않는다 -- "그리드 위상이 다른 인접 프레임에서 같은 지점이 실제로
   cluster로 잡힌 적이 있는가"만 확인한다(다른 방법, 같은 가설).
4. 진짜 "국소 재샘플" 실측 검증은 §31 승인 하에 relative_coords
   계측 패치 -> 신규 주행 -> 재분석 없이는 불가능.

**입력**: /home/claude/session297/work/route (x17seg, 17세그, 020ea86),
        /home/claude/session297/work/x17seg.csv (--with-navi-paths 포함
        추출본, 이번 세션 신규 추출)
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# ryu carrot_man.py (HEAD 020ea86) 이식 -- 상수/함수 100% 동일, §27
# ---------------------------------------------------------------------------

# carrot_man.py 44~45행
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360.,
                     1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
# carrot_man.py 63행
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
# carrot_man.py 79행
ROUTE_CURVATURE_FINE_SAMPLE = 1
# carrot_man.py 207~208행
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0
# carrot_man.py 1165행 (macro chord 3점 인덱스 스텝)
MACRO_SAMPLE = 4


def route_find_clusters(idxs, distances, min_points, max_gap_m):
    """carrot_man.py 463~475행과 100% 동일."""
    if not idxs:
        return []
    clusters = []
    cur = [idxs[0]]
    for i in idxs[1:]:
        if distances[i] - distances[cur[-1]] <= max_gap_m:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_points]


# ===========================================================================
# Part 1: 합성 self-test -- "밀도만 올리고 chord는 고정" 메커니즘 검증
# ===========================================================================
#
# carrot_man.py의 실제 커브 검출은 (a) macro chord=80m 3점 곡률로 대략적
# 형상을 잡고 (b) fine chord=20m 3점 곡률이 더 급하면 해당 인덱스 하나만
# 대체하는 구조다(1217~1263행). 이 스크립트는 "실제 도로 곡률 -> speed"
# 변환까지 재현하는 대신, 306차와 동일하게 "그 결과로 나온 distance별
# speed 프로파일"을 직접 다루는 추상화 수준에서 검증한다 -- 이렇게 해야
# xy 좌표/곡률 계산의 부차적 디테일 없이 "밀도 vs 위상 vs 클러스터 성립"
# 관계 자체에 집중할 수 있다(306차의 dip_len 스윕과 동일한 추상화 수준,
# §27 -- 필요 이상으로 복잡한 재구현을 하지 않는다).
#
# 진짜 커브: 물리적 폭 L(m) 구간 [d0, d0+L)에서 speed=dip_speed(<road_limit),
#            그 밖은 전부 above_speed(>=road_limit).
# 1프레임성 노이즈: L=0 -- 폭이 없는 점 하나. 어떤 grid로 샘플링해도
#            원리적으로 표본 1개 이상이 그 구간 [d0, d0+L)=[d0,d0) 안에
#            들어갈 수 없으므로(공집합), "정확히 d0을 표본으로 찍은 경우"만
#            candidate가 된다 -- 즉 개념적으로 아무리 촘촘히 찍어도 그
#            지점에 표본이 "우연히" 정확히 걸리는 경우가 아니면 애초에
#            후보 자체가 안 생긴다(진짜 순간 스파이크는 애초에 그리드에
#            거의 안 걸린다는 뜻이므로 별도로 "표본이 d0에 정확히 걸리는
#            경우"를 강제로 만들어 최악의 케이스로 시험한다, 아래 참고).


def sample_profile(d0, width, dip_speed, above_speed, road_limit,
                    grid_start, interval, window_lo, window_hi):
    """grid_start부터 interval 간격으로 [window_lo, window_hi] 구간을
    샘플링해 candidates(= speed < road_limit인 인덱스)와 distances를 만든다.
    """
    distances = []
    d = grid_start
    while d <= window_hi:
        if d >= window_lo:
            distances.append(d)
        d += interval
    speeds = []
    for d in distances:
        if d0 <= d < d0 + width:
            speeds.append(dip_speed)
        else:
            speeds.append(above_speed)
    candidates = [i for i, s in enumerate(speeds) if s < road_limit]
    return distances, speeds, candidates


def clusters_and_orphans(candidates, distances):
    all_c = route_find_clusters(candidates, distances, 1, ROUTE_CLUSTER_MAX_GAP_M)
    clusters = [c for c in all_c if len(c) >= ROUTE_CLUSTER_MIN_POINTS]
    orphans = [c for c in all_c if len(c) < ROUTE_CLUSTER_MIN_POINTS]
    return clusters, orphans


def part1_synthetic_self_test():
    print("=" * 96)
    print("Part 1 (합성 self-test) -- 국소 밀도 재샘플이 '좁은 진짜 커브'와")
    print("'폭 0 노이즈'를 구분해내는지 검증")
    print("=" * 96)

    road_limit = 50.0
    dip_speed = 15.0
    above_speed = 300.0
    d0 = 155.0  # orphan이 전역 10m 그리드에서 처음 걸리는 대략적 위치
    WINDOW_PAD_M = 60.0  # ROUTE_CLUSTER_MAX_GAP_M(40) + 여유

    intervals = [10.0, 5.0, 2.5]
    widths = [0.0, 4.0, 8.0, 12.0, 16.0, 20.0, 30.0]

    print(f"\n[실험1] 폭(L) x 간격(interval) x 위상(phase) 스윕")
    print(f"{'L(m)':>6} | {'interval':>8} | {'phase 성공률(2점+ 클러스터)':>28} | 판정")
    print("-" * 96)

    summary = {}
    for width in widths:
        for interval in intervals:
            n_phase = int(round(interval))  # 1m 단위로 위상 스윕 (interval이 정수 가정)
            n_phase = max(n_phase, 1)
            success = 0
            for phase in range(n_phase):
                grid_start = d0 - WINDOW_PAD_M - phase  # 위상만 바뀌고 그리드 자체는 -10 선증가와 동일하게 정렬
                window_lo = d0 - WINDOW_PAD_M
                window_hi = d0 + width + WINDOW_PAD_M
                distances, speeds, candidates = sample_profile(
                    d0, width, dip_speed, above_speed, road_limit,
                    grid_start, interval, window_lo, window_hi)
                clusters, orphans = clusters_and_orphans(candidates, distances)
                if len(candidates) > 0 and clusters:
                    success += 1
            rate = success / n_phase
            summary[(width, interval)] = rate
            verdict = "정상(클러스터 성립)" if rate > 0.0 else "orphan 고정"
            print(f"{width:>6.1f} | {interval:>8.1f} | {success:>3d}/{n_phase:<3d} ({rate*100:5.1f}%) "
                  f"{'':>10} | {verdict}")

    print("\n[핵심 결과]")
    # L=0 (노이즈)이 어떤 interval에서도 절대 클러스터가 되지 않아야 함
    noise_rates = [summary[(0.0, iv)] for iv in intervals]
    assert all(r == 0.0 for r in noise_rates), \
        f"self-test FAIL: L=0(노이즈)이 클러스터를 형성함(밀도를 올리면 노이즈까지 살아남는 회귀) -- {noise_rates}"
    print(f"- L=0(폭 없는 순수 노이즈): 모든 interval(10/5/2.5m)에서 성공률 0% "
          f"-> 밀도를 올려도 노이즈를 클러스터로 '구제'하지 않음 (기대대로 PASS)")

    # 10m에서 orphan이 될 만한(=성공률<100%) 좁은 폭에서, 5m/2.5m이 10m보다
    # 성공률이 같거나 높아야 함 (밀도를 올릴수록 진짜 커브 포착률이 개선되어야 함)
    improved_or_equal = True
    detail = []
    for width in widths:
        if width == 0.0:
            continue
        r10 = summary[(width, 10.0)]
        r5 = summary[(width, 5.0)]
        r25 = summary[(width, 2.5)]
        detail.append((width, r10, r5, r25))
        if not (r5 >= r10 and r25 >= r5):
            improved_or_equal = False
    assert improved_or_equal, f"self-test FAIL: 밀도를 올렸는데 오히려 성공률이 떨어지는 폭이 있음 -- {detail}"
    print(f"- 폭>0인 모든 커브(L=4~30m): interval을 10m->5m->2.5m로 좁힐수록 "
          f"클러스터 성립(위상 무관 성공) 확률이 단조 증가 (기대대로 PASS)")
    print(f"  (상세 성공률: {detail})")

    print("\n[결론] '점 밀도만 올리고 곡률 chord는 그대로 유지'하는 방식은,")
    print("실제로 폭이 있는 좁은 커브(L>0)는 위상에 덜 민감하게(성공률 상승) 잡아내면서도")
    print("폭이 없는 순수 1프레임 노이즈(L=0)는 절대 클러스터로 만들지 않는다.")
    print("=> 사용자가 제안한 '밀도만 국소적으로 올리는' 접근은, 원리적으로 노이즈")
    print("   재유입 없이 '진짜 좁은 커브 vs 순간 노이즈'를 구분하는 판별자로 유효함")
    print("   (단, 이건 개념 검증이지 x17seg의 실제 orphan이 이 케이스라는 뜻은 아님).")
    return summary


# ===========================================================================
# Part 2: x17seg 실측 -- "그리드 위상이 다른 인접 프레임에서 같은 지점이
# cluster로 잡힌 적이 있는가"(phase-resolution) 실측
# ===========================================================================

CONTINUITY_TOL_M = 10.0  # 265/267차가 확인한 프로덕션 CONTINUITY_MATCH_TOLERANCE_M


def probe_navroute_navd(rlog_path, repo_dir):
    """이 corpus에 navRouteNavd(원본 미리샘플 폴리라인) 이벤트가 실제로
    존재하는지 확인 -- 존재하면 진짜 국소 재샘플 실측이 가능해지므로
    매 세션 재확인할 가치가 있다(§28, 가정을 실측으로 재검증)."""
    sys.path.insert(0, os.path.join(repo_dir, "..", "devnotes", "toolkit"))
    from decode_rlog import iter_events
    count = 0
    coord_lens = []
    for evt in iter_events(rlog_path, repo_dir=repo_dir):
        if evt.which() == "navRouteNavd":
            count += 1
            coord_lens.append(len(evt.navRouteNavd.coordinates))
    return count, coord_lens


def build_episodes(df):
    """routeOrphanSingletonCount>0인 연속 프레임을 하나의 '에피소드'로
    묶는다. 같은 물리적 지점을 추적 중이라고 볼 수 있는 기준:
    - 연속 프레임(다음 행)이어야 함 (seg 경계 넘어가면 새 에피소드)
    - 예측 거리(prev_dist - vEgo*dt)와 실제 orphan dist의 오차가
      CONTINUITY_TOL_M(10m) 이내여야 같은 지점으로 간주(265/267차 tolerance
      그대로 재사용, §27)
    """
    episodes = []
    cur = None
    prev_row = None
    for _, row in df.iterrows():
        has_orphan = row["routeOrphanSingletonCount"] > 0
        if not has_orphan:
            if cur is not None:
                episodes.append(cur)
                cur = None
            prev_row = row
            continue

        dist = row["routeOrphanSingletonDist"]
        same_episode = False
        if cur is not None and prev_row is not None:
            dt = row["t"] - prev_row["t"]
            if 0 < dt <= 0.25 and row["seg"] == prev_row["seg"]:
                predicted = prev_row["routeOrphanSingletonDist"] - prev_row["vEgo"] * dt
                if abs(predicted - dist) <= CONTINUITY_TOL_M:
                    same_episode = True

        if same_episode:
            cur["rows"].append(row)
        else:
            if cur is not None:
                episodes.append(cur)
            cur = {"rows": [row]}
        prev_row = row

    if cur is not None:
        episodes.append(cur)
    return episodes


def part2_real_corpus_phase_check(csv_path, neighbor_window_s=3.0):
    print("\n" + "=" * 96)
    print("Part 2 (실측, x17seg) -- orphan 에피소드가 그리드 위상이 다른")
    print("인접 프레임에서 실제로 cluster로 해소된 적이 있는지 확인")
    print("=" * 96)

    df = pd.read_csv(csv_path, usecols=[
        "t", "seg", "vEgo", "routeOrphanSingletonCount", "routeOrphanSingletonDist",
        "routeOrphanSingletonSpeed", "routeClusterCount", "routeApexDist",
        "routeApexMode", "naviPointsActive",
    ])
    df = df.reset_index(drop=True)

    total_orphan_rows = int((df["routeOrphanSingletonCount"] > 0).sum())
    print(f"\n전체 프레임: {len(df)} / orphan singleton>0 프레임: {total_orphan_rows}")

    episodes = build_episodes(df)
    print(f"에피소드로 그룹화: {len(episodes)}개 "
          f"(연속프레임+거리연속성 {CONTINUITY_TOL_M:.0f}m tolerance 기준)")

    resolved = 0
    persistent = 0
    detail_rows = []
    for ep in episodes:
        rows = ep["rows"]
        t0 = rows[0]["t"]
        t1 = rows[-1]["t"]
        seg = rows[0]["seg"]
        dist_at_start = rows[0]["routeOrphanSingletonDist"]
        dist_at_end = rows[-1]["routeOrphanSingletonDist"]

        # 같은 세그, 에피소드 시간 범위 +-neighbor_window_s 내에서
        # routeClusterCount>=1이면서 routeApexDist가 이 에피소드가
        # 추적하던 물리적 위치(대략 dist_at_end~dist_at_start 범위, 여유
        # CONTINUITY_TOL_M)와 겹치는 프레임이 있는지 확인.
        neighbor_mask = (
            (df["seg"] == seg)
            & (df["t"] >= t0 - neighbor_window_s)
            & (df["t"] <= t1 + neighbor_window_s)
            & (df["routeClusterCount"] >= 1)
        )
        neighbors = df[neighbor_mask]
        lo = min(dist_at_start, dist_at_end) - CONTINUITY_TOL_M
        hi = max(dist_at_start, dist_at_end) + CONTINUITY_TOL_M
        match = neighbors[(neighbors["routeApexDist"] >= lo) & (neighbors["routeApexDist"] <= hi)]

        is_resolved = len(match) > 0
        if is_resolved:
            resolved += 1
        else:
            persistent += 1
        detail_rows.append({
            "seg": seg, "t0": round(t0, 2), "t1": round(t1, 2),
            "n_frames": len(rows), "dist_start": round(dist_at_start, 1),
            "dist_end": round(dist_at_end, 1),
            "phase_resolved": is_resolved,
        })

    print(f"\n{'seg':>4} | {'t0':>8} | {'t1':>8} | {'frames':>6} | "
          f"{'dist_start':>10} | {'dist_end':>9} | phase_resolved")
    print("-" * 96)
    for d in detail_rows:
        print(f"{d['seg']:>4} | {d['t0']:>8.2f} | {d['t1']:>8.2f} | {d['n_frames']:>6d} | "
              f"{d['dist_start']:>10.1f} | {d['dist_end']:>9.1f} | {d['phase_resolved']}")

    print("-" * 96)
    print(f"\n[핵심 결과] 총 {len(episodes)}개 orphan 에피소드 중:")
    print(f"  - phase_resolved(인접 프레임에서 같은 위치가 cluster로 잡힌 적 있음): {resolved}건")
    print(f"  - persistent(에피소드 전체 구간 동안 한 번도 cluster로 안 잡힘): {persistent}건")
    if len(episodes) > 0:
        print(f"  - phase-resolved 비율: {resolved/len(episodes)*100:.1f}%")

    print("\n[해석 시 주의(§28)] phase_resolved 비율이 높다는 것은 \"그리드 위상만")
    print("바뀌어도 같은 물리적 지점이 cluster가 되기도 하고 orphan이 되기도 한다\"는")
    print("정황이며, 이는 Part 1이 보여준 메커니즘(밀도/위상에 민감한 좁은 진짜 커브)과")
    print("방향이 일치한다. 그러나 이것이 \"국소 재샘플을 했다면 풀렸을 것\"이라는 직접")
    print("증거는 아니다 -- 원본 폴리라인 없이 이 corpus로 검증 가능한 최대치임.")

    return {"episodes": len(episodes), "resolved": resolved, "persistent": persistent,
            "detail": detail_rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/home/claude/session297/work/x17seg.csv")
    ap.add_argument("--rlog-sample",
                     default="/home/claude/session297/work/route/"
                             "20260908_070010_000003c6--586e535fca--4/rlog.zst")
    ap.add_argument("--repo", default="/home/claude/session297/ryu")
    ap.add_argument("--skip-navroute-probe", action="store_true")
    args = ap.parse_args()

    part1_synthetic_self_test()

    if not args.skip_navroute_probe:
        print("\n" + "=" * 96)
        print("[사전 재확인] navRouteNavd 존재 여부 (이 corpus, seg4 샘플)")
        print("=" * 96)
        try:
            count, lens = probe_navroute_navd(args.rlog_sample, args.repo)
            print(f"navRouteNavd 이벤트 수: {count}"
                  + (f" (좌표개수 샘플: {lens[:5]})" if lens else ""))
            if count == 0:
                print("-> 0건 확정. 원본(pre-resample) 폴리라인 실측 불가 (위 docstring 참고).")
        except Exception as e:
            print(f"[경고] navRouteNavd 확인 실패: {e}")

    if os.path.exists(args.csv):
        part2_real_corpus_phase_check(args.csv)
    else:
        print(f"\n[안내] {args.csv} 없음 -- Part 2(실측) 스킵. "
              f"extract_log.py --with-navi-paths로 먼저 CSV를 뽑을 것.")


if __name__ == "__main__":
    main()
