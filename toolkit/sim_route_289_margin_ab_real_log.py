#!/usr/bin/env python3
"""
sim_route_289_margin_ab_real_log.py (289차 신규)

목적: 사용자 요청("route가 너무 짧게 작동하다 릴리즈된다 -- 릴리즈 마진을
1.1 -> 1.05로 낮추면 어떻게 되는지 보고 싶다")에 답하기 위해,
`ROUTE_ACTIVE_RELEASE_MARGIN_RATIO`를 --new-ratio(기본 1.05)로 바꿨을
때 288차가 분석한 실측 route1~4 로그에서 RELEASE 시점이 어떻게 바뀔지
what-if 시뮬레이션한다. ryu 코드는 변경하지 않는다(§27/§28 -- 시뮬레이션
선행 원칙).

**방법(§21: 288차 `analyze_route_release_trigger_288.py`의 run탐지/
episode 병합 로직을 그대로 재사용)**:
1. `src=='route'` 에피소드를 288차와 동일하게 병합(gap<--merge-tol)해
   "기존(margin=1.1) 실측 에피소드" 목록을 만든다.
2. margin이 RELEASE 원인에 관여한 에피소드(`speed_reached`/
   `speed+dist_both`)에 대해서만, 에피소드 시작 프레임부터 전체 연속
   프레임(원본 df, `src` 무관 -- routeApexDist/Speed는 carrot_serv.py가
   후보를 추적하는 한 매 프레임 발행되므로 route가 arbitration에서 잠시
   져도 값이 이어짐)을 앞으로 순회하며, apex 후보 값(apex_speed/
   apex_dist)이 0/NaN으로 비는 프레임은 `ROUTE_APEX_MISS_TOLERANCE_FRAMES`
   (=6, 실제 코드 상수, carrot_man.py 211행)만큼 직전 유효값으로
   forward-fill한다 -- 이 허용치를 넘는 연속 결측만 "continuity 소실"로
   판정한다(정확히 실제 코드의 miss-tolerance 게이트와 동일 원칙 재사용).
3. 매 프레임 `v_ego_kph <= apex_speed_filled * new_ratio`(margin) 또는
   `apex_dist_filled <= ROUTE_RELEASE_DIST_M`(거리)이 최초로 성립하는
   지점을 "새 RELEASE 시점"으로 기록한다. margin이 아닌 원인(거리 단독/
   continuity 소실)으로 끝난 에피소드는 margin 값 변경의 영향을 받지
   않으므로 시뮬레이션에서 제외하고 원본 그대로 둔다.
4. 새 RELEASE 시점이 원래 "다음 에피소드"의 시작 시각을 넘어서면 두
   에피소드가 하나로 합쳐지는 것으로 보고 병합한다(연쇄 병합 가능,
   flicker train이 통째로 하나의 긴 ACTIVE로 흡수되는 경우 포함).
5. 병합 후의 새 에피소드 집합에 288차와 동일한 flicker-train 탐지
   (gap<3.0s, 3회 이상 연속)를 다시 적용해 train 개수 변화를 비교한다.

**한계(정직하게 명시, §28)**:
- INERT->ACTIVE 재진입 게이트(confidence blend, 257차)는 이 시뮬레이션
  대상이 아니다 -- margin은 RELEASE(ACTIVE->INERT)에만 영향을 주므로
  에피소드 시작 시각은 원본 그대로 두고 끝 시각만 다시 계산한다. 즉 이
  시뮬레이션은 288차가 발견한 "재진입 게이트-margin 불일치" flicker의
  근본 원인(원인 3가지 대안 a/b/c) 자체를 바꾸는 것이 아니라, 그 중
  아무 것도 손대지 않고 "margin 값만" 낮췄을 때의 순수 효과만 본다.
- apex_speed/apex_dist는 실제 `self.route_active` 내부 상태를 직접
  로깅한 값이 아니라 carrot_serv.py가 매 프레임 발행하는 후보 추적값의
  프록시다(283/288차와 동일 한계). candidate가 실제로 다른 물리적
  커브로 전환됐는데도 값이 우연히 비슷해 continuity로 오판될 가능성은
  배제하지 못한다.
- forward-fill 6프레임 허용치는 실제 `ROUTE_APEX_MISS_TOLERANCE_FRAMES`
  상수를 그대로 가져온 것이나, 코드의 다른 상태(streak/confidence)까지
  완전히 재현하지는 않는다.

사용:
    python3 sim_route_289_margin_ab_real_log.py route1.csv route2.csv ... \\
        [--merge-tol 1.0] [--old-ratio 1.10] [--new-ratio 1.05] \\
        [--dist-m 10.0] [--miss-tolerance 6] [--out-prefix sim289_margin]
"""
import sys
import argparse
import pandas as pd
import numpy as np

ROUTE_RELEASE_DIST_M = 10.0
ROUTE_APEX_MISS_TOLERANCE_FRAMES = 6


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


def classify_cause(v_ego_kph, apex_speed, apex_dist, ratio, dist_m):
    # 288차 버그 수정 반영(§21 -- analyze_route_release_trigger_288.py와
    # 동일 수정): apex_speed==0을 continuity로 조기 확정하지 않는다.
    # apex_dist<=dist_m이 그대로 성립하면 dist_reached로 분류하는 것이
    # 원 실측 분류(WIP/FINDINGS 288차 기록)와 일치한다.
    margin_ok = v_ego_kph <= apex_speed * ratio
    dist_ok = apex_dist <= dist_m
    if margin_ok and dist_ok:
        return "speed+dist_both"
    if margin_ok:
        return "speed_reached(margin)"
    if dist_ok:
        return "dist_reached(10m)"
    return "apex_lost_or_new(continuity)"


def simulate_new_release(df, s, old_ratio, new_ratio, dist_m, miss_tol, horizon_frames=2000):
    """s: 에피소드 시작 인덱스. 앞으로 순회하며 new_ratio 기준 RELEASE
    프레임을 찾는다. (new_release_idx, cause, hit_horizon) 반환."""
    t = df["t"].values
    vEgo = df["vEgo"].values
    apexSpeed = df["routeApexSpeed"].values
    apexDist = df["routeApexDist"].values

    last_speed = apexSpeed[s]
    last_dist = apexDist[s]
    miss = 0
    n = len(df)
    end = min(s + horizon_frames, n)
    for idx in range(s, end):
        raw_speed = apexSpeed[idx]
        raw_dist = apexDist[idx]
        if raw_speed and raw_speed > 0.0 and not np.isnan(raw_speed):
            last_speed = raw_speed
            last_dist = raw_dist
            miss = 0
        else:
            miss += 1
            if miss > miss_tol:
                return idx, "apex_lost_or_new(continuity)", False

        v_ego_kph = vEgo[idx] * 3.6
        margin_ok = v_ego_kph <= last_speed * new_ratio
        dist_ok = last_dist <= dist_m
        if margin_ok or dist_ok:
            cause = "speed+dist_both" if (margin_ok and dist_ok) else (
                "speed_reached(margin)" if margin_ok else "dist_reached(10m)")
            return idx, cause, False
    return end - 1, "horizon_exceeded", True


def find_trains(edf, train_gap, train_min):
    edf = edf.copy()
    edf["gap_before"] = edf["gap_before"].fillna(999.0)
    edf["is_margin"] = edf["cause"].str.contains("speed_reached", na=False)
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
    ap.add_argument("--merge-tol", type=float, default=1.0)
    ap.add_argument("--old-ratio", type=float, default=1.10)
    ap.add_argument("--new-ratio", type=float, default=1.05)
    ap.add_argument("--dist-m", type=float, default=ROUTE_RELEASE_DIST_M)
    ap.add_argument("--miss-tolerance", type=int, default=ROUTE_APEX_MISS_TOLERANCE_FRAMES)
    ap.add_argument("--train-gap", type=float, default=3.0)
    ap.add_argument("--train-min", type=int, default=3)
    ap.add_argument("--out-prefix", default="sim289_margin")
    args = ap.parse_args()

    df = load_concat(args.csvs)
    t = df["t"].values
    vEgo = df["vEgo"].values
    apexDist = df["routeApexDist"].values
    apexSpeed = df["routeApexSpeed"].values
    is_route = (df["src"].values == "route")

    runs = find_runs(is_route)
    episodes = merge_runs(runs, t, args.merge_tol)
    print(f"raw runs: {len(runs)}  ->  merged episodes(tol={args.merge_tol}s): {len(episodes)}")

    old_rows = []
    for i, (s, e) in enumerate(episodes):
        # RELEASE 판정 프레임은 e-1(에피소드 안쪽 마지막)이 아니라 e(바로
        # 다음 프레임) -- 288차 버그 수정과 동일 이유(위 classify_cause
        # 주석 참고).
        last = e
        if last >= len(df):
            continue  # 로그 끝 절단, 판별 불가(288차와 동일 처리)
        gap_before = (t[s] - t[episodes[i - 1][1] - 1]) if i > 0 else None
        cause_old = classify_cause(vEgo[last] * 3.6, apexSpeed[last], apexDist[last],
                                    args.old_ratio, args.dist_m)
        old_rows.append({"ep": i, "s": s, "e": e, "t_start": t[s], "t_end": t[last],
                          "cause_old": cause_old, "gap_before": gap_before})
    odf = pd.DataFrame(old_rows)

    print(f"\n기존(margin={args.old_ratio}) 원인 분포:")
    print(odf["cause_old"].value_counts().to_string())

    # margin이 원인에 관여한 에피소드만 새 ratio로 재시뮬레이션
    margin_mask = odf["cause_old"].str.contains("speed_reached")
    sim_rows = []
    for _, row in odf.iterrows():
        if not margin_mask.loc[row.name]:
            sim_rows.append({"ep": row.ep, "t_start": row.t_start,
                              "t_end_old": row.t_end, "t_end_new": row.t_end,
                              "cause_new": row.cause_old, "changed": False,
                              "horizon_exceeded": False})
            continue
        new_idx, cause_new, hit_horizon = simulate_new_release(
            df, row.s, args.old_ratio, args.new_ratio, args.dist_m, args.miss_tolerance)
        t_end_new = t[new_idx]
        sim_rows.append({"ep": row.ep, "t_start": row.t_start,
                          "t_end_old": row.t_end, "t_end_new": t_end_new,
                          "cause_new": cause_new,
                          "changed": t_end_new > row.t_end + 1e-6,
                          "horizon_exceeded": hit_horizon})
    sdf = pd.DataFrame(sim_rows)
    sdf.to_csv(f"{args.out_prefix}_per_episode.csv", index=False)

    n_changed = sdf["changed"].sum()
    added = (sdf.loc[sdf["changed"], "t_end_new"] - sdf.loc[sdf["changed"], "t_end_old"])
    print(f"\nmargin={args.new_ratio}로 낮췄을 때 지속시간이 늘어나는 에피소드: "
          f"{n_changed}/{len(sdf)}건")
    if n_changed:
        print(f"  연장 시간: 평균 {added.mean():.2f}s, 최대 {added.max():.2f}s, "
              f"합계 {added.sum():.1f}s")
    n_horizon = sdf["horizon_exceeded"].sum()
    if n_horizon:
        print(f"  주의: {n_horizon}건은 --horizon-frames 내에 새 RELEASE 조건을 "
              f"못 찾음(비정상적으로 긴 연장 후보 -- 개별 확인 필요)")

    # 새 에피소드 종료시각 기준으로 다음 에피소드와 겹치면 병합
    new_episodes = []
    cur_start = sdf.iloc[0]["t_start"]
    cur_end = sdf.iloc[0]["t_end_new"]
    cur_cause = sdf.iloc[0]["cause_new"]
    for i in range(1, len(sdf)):
        row = sdf.iloc[i]
        if row["t_start"] < cur_end + args.merge_tol:
            # 다음 에피소드 시작이 새 종료시각보다 앞서면(또는 merge_tol 이내) 병합
            cur_end = max(cur_end, row["t_end_new"])
            cur_cause = row["cause_new"]
        else:
            new_episodes.append({"t_start": cur_start, "t_end": cur_end, "cause": cur_cause})
            cur_start, cur_end, cur_cause = row["t_start"], row["t_end_new"], row["cause_new"]
    new_episodes.append({"t_start": cur_start, "t_end": cur_end, "cause": cur_cause})
    ndf = pd.DataFrame(new_episodes)
    ndf["gap_before"] = ndf["t_start"] - ndf["t_end"].shift(1)
    ndf["dur"] = ndf["t_end"] - ndf["t_start"]
    ndf.to_csv(f"{args.out_prefix}_new_episodes.csv", index=False)

    print(f"\n에피소드 개수: 기존 {len(odf)}건 -> margin={args.new_ratio} 적용 후 "
          f"{len(ndf)}건 (병합으로 {len(odf) - len(ndf)}건 감소)")
    print(f"평균 ACTIVE 지속시간: 기존 {(odf.t_end - odf.t_start).mean():.2f}s -> "
          f"신규 {ndf['dur'].mean():.2f}s")

    old_trains = find_trains(odf.rename(columns={"cause_old": "cause"}), args.train_gap, args.train_min)
    new_trains = find_trains(ndf, args.train_gap, args.train_min)
    print(f"\nflicker train(gap<{args.train_gap}s, {args.train_min}회 이상 연속): "
          f"기존 margin={args.old_ratio} {len(old_trains)}건 -> "
          f"margin={args.new_ratio} {len(new_trains)}건")
    for tr in new_trains:
        sub = ndf.loc[tr]
        print(f"  t={sub.t_start.min():.1f}~{sub.t_end.max():.1f}s ({len(tr)}episodes)")


if __name__ == "__main__":
    main()
