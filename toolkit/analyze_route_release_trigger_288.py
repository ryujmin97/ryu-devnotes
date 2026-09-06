#!/usr/bin/env python3
"""
analyze_route_release_trigger_288.py (288차 신규)

목적: 사용자 질문("route가 작동하다가 릴리즈되는 순간의 원인이 릴리즈
마진 1.1(`ROUTE_ACTIVE_RELEASE_MARGIN_RATIO`) 때문인가?")에 답하기 위해,
`src=='route'` 에피소드가 끝나는(RELEASE되는) 프레임마다 carrot_man.py
`carrot_navi_route()`의 RELEASE 3-way OR 트리거 중 실제로 어느 조건이
충족돼 있었는지를 실측 텔레메트리로 역산 분류한다.

RELEASE 3조건(carrot_man.py, ACTIVE 분기, §283/288 WIP 참고):
    speed_reached: v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO(1.1)
    dist_reached : apex_dist <= ROUTE_RELEASE_DIST_M(10.0m)
    apex_lost_or_new: continuity 추적이 소실되었거나 다른 candidate로
                       전환됨(=RELEASE 직전 프레임 대비 routeApexIdx가
                       바뀌었거나 apex_speed가 0.0으로 꺼진 경우로 근사)

이 스크립트는 §21 원칙에 따라 `verify_route_release_hold_283_real_log.py`
(283차)의 run-찾기/에피소드 병합(gap<--merge-tol) 로직을 그대로 재사용하고,
그 위에 "RELEASE 원인 분류"와 "margin 트리거가 짧은 간격으로 연쇄되는
flicker train 탐지"(--trains) 기능만 신규로 얹는다 -- 동일 목적의 병합
로직을 새로 작성하지 않는다.

분류 규칙(각 에피소드의 마지막 route 프레임 값 기준):
    apex_speed == 0.0 또는 candidateCount == 0
        -> apex_lost_or_new(continuity)  (apex_speed 자체가 사라짐)
    아니면 margin_ok = (vEgo_kph <= apex_speed * MARGIN_RATIO)
         dist_ok   = (apexDist <= RELEASE_DIST_M)
    margin_ok and dist_ok   -> speed+dist_both
    margin_ok and not dist_ok -> speed_reached(margin1.1)
    dist_ok and not margin_ok -> dist_reached(10m)
    둘 다 아니면 -> apex_lost_or_new(continuity)  (남은 유일한 후보 -- OR
        3조건 중 하나는 반드시 성립했어야 RELEASE된 것이므로, margin/dist
        어느 쪽도 성립하지 않았다면 continuity 소실로 판정한다)

주의: 이 분류는 rlog 텔레메트리만으로 사후 역산한 근사치다(§28) --
carrot_man.py 내부 상태(streak/confidence blend 등)를 직접 로깅하지 않는
한 100% 정확한 재현은 아니다(283차 스크립트와 동일한 한계 성격).

--trains 옵션: gap_before < --train-gap(기본 3.0s)인 margin 관여
("speed_reached(margin1.1)" 또는 "speed+dist_both") 에피소드가
--train-min(기본 3)회 이상 연속되는 구간을 "flicker train" 후보로
출력한다 -- 288차가 t=313.9~325.6s 등 4개 구간에서 발견한 "INERT 재진입
게이트(confidence blend)와 RELEASE margin 판정(raw apex_speed)이 서로
다른 신뢰도 기준을 참조해 한 커브 접근 중 route가 수 회 반복
켜졌다꺼지는" 패턴을 자동 탐지하기 위함(상세 메커니즘: WIP.md/
FINDINGS.md 288차).

사용:
    python3 analyze_route_release_trigger_288.py route1.csv route2.csv ... \\
        [--merge-tol 1.0] [--trains] [--train-gap 3.0] [--train-min 3] \\
        [--out-prefix release_trigger_288]

여러 route CSV를 시간순으로 이어붙여 하나의 연속 주행으로 취급한다
(283차와 동일 관례).
"""
import sys
import argparse
import pandas as pd
import numpy as np

# carrot_man.py 상수(carrot_navi_route() ACTIVE 분기, 252차/223차 신규)
ROUTE_ACTIVE_RELEASE_MARGIN_RATIO = 1.1
ROUTE_RELEASE_DIST_M = 10.0


def load_concat(paths):
    dfs = []
    for p in paths:
        df = pd.read_csv(p, low_memory=False)
        df["__src_file"] = p
        dfs.append(df)
    full = pd.concat(dfs, ignore_index=True)
    full = full.sort_values("t").reset_index(drop=True)
    return full


def find_runs(is_active):
    prev = np.concatenate(([False], is_active[:-1]))
    starts = np.where(is_active & ~prev)[0]
    ends = np.where(~is_active & prev)[0]
    if is_active[-1]:
        ends = np.append(ends, len(is_active))
    return list(zip(starts, ends))


def merge_runs(runs, t, merge_tol):
    episodes = []
    cur_s, cur_e = runs[0]
    for (s, e) in runs[1:]:
        gap = t[s] - t[cur_e - 1]
        if gap < merge_tol:
            cur_e = e
        else:
            episodes.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    episodes.append((cur_s, cur_e))
    return episodes


def classify_cause(v_ego_kph, apex_speed, apex_dist, candidate_count):
    if apex_speed == 0.0 or (not np.isnan(candidate_count) and candidate_count == 0):
        return "apex_lost_or_new(continuity)", np.nan
    ratio = v_ego_kph / apex_speed if apex_speed else np.nan
    margin_ok = v_ego_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
    dist_ok = apex_dist <= ROUTE_RELEASE_DIST_M
    if margin_ok and dist_ok:
        return "speed+dist_both", ratio
    if margin_ok:
        return "speed_reached(margin1.1)", ratio
    if dist_ok:
        return "dist_reached(10m)", ratio
    return "apex_lost_or_new(continuity)", ratio


def find_trains(edf, train_gap, train_min):
    edf = edf.copy()
    edf["gap_before"] = edf["gap_before"].fillna(999.0)
    edf["is_margin"] = edf["cause"].str.contains("speed_reached")
    trains = []
    cur = []
    for i, row in edf.iterrows():
        if row["gap_before"] < train_gap and row["is_margin"]:
            if not cur:
                cur = [max(i - 1, 0), i]
            else:
                cur.append(i)
        else:
            if len(cur) >= train_min:
                trains.append(cur)
            cur = []
    if len(cur) >= train_min:
        trains.append(cur)
    return trains


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--merge-tol", type=float, default=1.0,
                     help="같은 에피소드로 병합할 최대 gap(s), 기본 1.0"
                          "(283차와 동일 기준)")
    ap.add_argument("--trains", action="store_true",
                     help="margin 트리거 flicker train 탐지 결과도 출력")
    ap.add_argument("--train-gap", type=float, default=3.0,
                     help="flicker train 판정용 최대 gap(s), 기본 3.0")
    ap.add_argument("--train-min", type=int, default=3,
                     help="flicker train 최소 연속 에피소드 수, 기본 3")
    ap.add_argument("--out-prefix", default="release_trigger_288")
    args = ap.parse_args()

    df = load_concat(args.csvs)
    t = df["t"].values
    vEgo = df["vEgo"].values
    apexDist = df["routeApexDist"].values
    apexSpeed = df["routeApexSpeed"].values
    candCount = (df["routeCandidateCount"].values
                 if "routeCandidateCount" in df.columns
                 else np.full(len(df), np.nan))
    is_route = (df["src"].values == "route")

    runs = find_runs(is_route)
    if not runs:
        print("route src 구간이 전혀 없습니다.")
        sys.exit(1)

    print(f"raw src=='route' runs: {len(runs)}", end="")
    episodes = merge_runs(runs, t, args.merge_tol)
    print(f"  ->  merged episodes(tol={args.merge_tol}s): {len(episodes)}")

    rows = []
    n_truncated = 0
    for i, (s, e) in enumerate(episodes):
        gap_before = (t[s] - t[episodes[i - 1][1] - 1]) if i > 0 else None
        last = e - 1
        if last == len(df) - 1 and i == len(episodes) - 1:
            # 로그 끝에서 절단된 마지막 에피소드는 실제 RELEASE 사유를
            # 판별할 수 없다(다음 프레임이 로그에 없음) -- 분류 제외.
            n_truncated += 1
            continue
        v_ego_kph = vEgo[last] * 3.6
        apex_speed = apexSpeed[last]
        apex_dist = apexDist[last]
        cand = candCount[last]
        cause, ratio = classify_cause(v_ego_kph, apex_speed, apex_dist, cand)
        rows.append({
            "t_release": t[last], "dur_active_s": t[last] - t[s],
            "vEgo_kph_at_release": v_ego_kph,
            "apexSpeed_at_release": apex_speed,
            "apexDist_at_release": apex_dist,
            "ratio_v_over_apexspeed": ratio,
            "candidateCount_at_release": cand,
            "cause": cause,
            "gap_before": gap_before,
        })

    edf = pd.DataFrame(rows)
    edf.to_csv(f"{args.out_prefix}_episodes.csv", index=False)

    print(f"\n분류 가능한 RELEASE 전이: {len(edf)}건 "
          f"(로그 끝 절단 제외 {n_truncated}건)\n")
    print(edf["cause"].value_counts().to_string())

    if args.trains:
        trains = find_trains(edf, args.train_gap, args.train_min)
        print(f"\nmargin 연쇄 flicker train(gap<{args.train_gap}s, "
              f"{args.train_min}회 이상 연속): {len(trains)}건")
        for tr in trains:
            sub = edf.loc[tr]
            print(f"  t={sub.t_release.min():.1f}~{sub.t_release.max():.1f}s "
                  f"({len(tr)}episodes), "
                  f"apexDist {sub.apexDist_at_release.max():.0f}->"
                  f"{sub.apexDist_at_release.min():.0f}m, "
                  f"vEgo {sub.vEgo_kph_at_release.max():.1f}->"
                  f"{sub.vEgo_kph_at_release.min():.1f}kph")


if __name__ == "__main__":
    main()
