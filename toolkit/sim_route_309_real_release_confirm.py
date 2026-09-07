#!/usr/bin/env python3
"""
sim_route_309_real_release_confirm.py (309차 신규)

목적: 308차가 단순화된 valid->invalid 전이 스캔으로 찾은 "594건 cutoff /
448건 lost_with_candidates_present(100% orphan)"이, **실제 production
설정(ROUTE_ACTIVE_RELEASE_MARGIN_RATIO=1.10)에서 진짜로 몇 건의 ACTIVE
RELEASE(episode 종료)를 유발했는지**를 확정한다. 308차 스크립트 자신의
docstring이 이미 명시한 한계("289차의 엄격한 6프레임 지속 기준을 안 쓰는
단순화 버전이라 정확한 RELEASE 건수는 과대계수 가능성 있음")를 이번
세션에서 실제로 해소한다.

**중요 정정(§24/26, WIP/FINDINGS 309차 참고)**: 293/294/306/307/308차가
인용해온 "continuity 에피소드 39건 중 ep108이 유일한 lost_with_
candidates_present"라는 수치는, `sim_route_292_continuity_root_cause.py`를
**기본 인자(--old-ratio 1.10 --new-ratio 1.05)로 실행했을 때의 `cause_new`
컬럼**(=마진을 1.05로 낮췄다고 가정한 what-if 결과)을 그대로 썼기 때문에
나온 숫자다. 실제 production 마진(1.10)에서 289차 `cause_old`가 진짜로
"apex_lost_or_new(continuity)"로 판정한 에피소드는 **11건**뿐이며(전체
110건 중), 39건 중 나머지 28건은 "마진을 1.05로 낮췄다면 continuity로
끝났을 것"이라는 가상의 에피소드다. ep108 자체는 이 11건에도 포함되므로
(마진 변경과 무관하게 원래도 continuity였음) 306~308차의 ep108 관련
결론 자체는 바뀌지 않지만, **분모는 "1/39"가 아니라 "1/11"이 맞다.**

**이 스크립트가 하는 일(§21 -- 289/292차 함수 재사용, 재구현 아님)**:
1. `sim_route_289_margin_ab_real_log.py`와 동일한 방식으로 `src=='route'`
   run을 병합해 실제 에피소드 목록을 만들고, 각 에피소드 종료 프레임에서
   `classify_cause()`(289차 원본, old_ratio=1.10)로 **실제 production
   판정**을 재현한다.
2. `cause_old`가 "apex_lost_or_new(continuity)"인 에피소드만 추출해
   `sim_route_292_continuity_root_cause.py::classify_continuity_episode()`
   (292차 원본, 그대로 재사용)로 세부원인(passed/dist_reached_during_hold/
   lost_with_candidates_present/lost_no_candidate)을 판정한다.
3. 각 에피소드의 실제 종료 프레임(`t_end_old`)에서 raw apexSpeed 값을
   직접 조회해, 0이 아닌 채로 종료 판정이 난 경우(= `src`가 route에서
   떠난 시점과 apexSpeed가 실제로 0이 되는 시점이 어긋나는 경우)를
   `possible_fragmentation` 플래그로 표시한다 -- 이런 경우
   `classify_continuity_episode()`의 lookahead가 **다른(더 뒤의, 어쩌면
   무관한) 에피소드의 종료를 잘못 귀속시킬 위험**이 있다(309차에서
   ep=99가 실제로 이런 사례였음이 lookahead를 넓혀 확인됨 -- ep99와
   ep100 사이 gap이 1.10s로 `--merge-tol`(1.0s) 경계를 살짝 넘어 병합되지
   않았을 뿐, 실질적으로 같은 물리적 candidate의 파편일 가능성이 큼).

**한계(§28)**:
- `possible_fragmentation` 플래그는 근사 탐지다 -- held 상태에서도 원래
  apex_speed가 몇 프레임 더 유효하게 남는 것은 정상(292차 docstring 4번
  항목)이므로, 플래그가 켜졌다고 전부 오분류인 것은 아니다. 최종 판단은
  qcamera 육안 대조 또는 `--merge-tol`을 조정한 재실행으로 확인 필요.
- 289차와 동일하게 candidate가 실제로 다른 물리적 커브로 전환됐는데
  값이 우연히 비슷한 경우까지는 구분 못함.

사용:
    python3 sim_route_309_real_release_confirm.py route1.csv route2.csv ... \\
        [--merge-tol 1.0] [--old-ratio 1.10] [--dist-m 10.0] \\
        [--out-prefix sim309_real_release]
"""
import argparse
import sys

import numpy as np
import pandas as pd

# 289/292차 원본 함수 재사용(§21) -- 같은 폴더의 기존 스크립트를 모듈로 import
from sim_route_289_margin_ab_real_log import (
    find_runs, merge_runs, classify_cause, load_concat as load_concat_289,
)
from sim_route_292_continuity_root_cause import classify_continuity_episode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_csvs", nargs="+")
    ap.add_argument("--merge-tol", type=float, default=1.0)
    ap.add_argument("--old-ratio", type=float, default=1.10)
    ap.add_argument("--dist-m", type=float, default=10.0)
    ap.add_argument("--dt", type=float, default=0.05)
    ap.add_argument("--miss-tolerance", type=int, default=6)
    ap.add_argument("--out-prefix", default="sim309_real_release")
    args = ap.parse_args()

    df = load_concat_289(args.route_csvs)
    t = df["t"].values
    vEgo = df["vEgo"].values
    apexDist = df["routeApexDist"].values
    apexSpeed = df["routeApexSpeed"].values
    is_route = (df["src"].values == "route")

    runs = find_runs(is_route)
    episodes = merge_runs(runs, t, args.merge_tol)
    print(f"raw runs: {len(runs)}  ->  merged episodes(tol={args.merge_tol}s): {len(episodes)}")

    rows = []
    for i, (s, e) in enumerate(episodes):
        last = e
        if last >= len(df):
            continue
        cause_old = classify_cause(vEgo[last] * 3.6, apexSpeed[last], apexDist[last],
                                    args.old_ratio, args.dist_m)
        rows.append({"ep": i, "s": s, "e": e, "t_start": t[s], "t_end_old": t[last],
                     "cause_old": cause_old})
    odf = pd.DataFrame(rows)
    print(f"\n실제 production(margin={args.old_ratio}) 원인 분포 (전체 {len(odf)}건):")
    print(odf["cause_old"].value_counts().to_string())

    cont = odf[odf["cause_old"] == "apex_lost_or_new(continuity)"].copy()
    print(f"\n실제 continuity 에피소드: {len(cont)}건 -- 세부원인 재분류 시작")

    sub_rows = []
    for _, ep in cont.iterrows():
        r = classify_continuity_episode(df, ep["t_start"], ep["t_end_old"],
                                         args.dt, args.dist_m)
        r["ep"] = ep["ep"]
        r["t_start"] = ep["t_start"]
        r["t_end_old"] = ep["t_end_old"]
        # possible_fragmentation: t_end_old(src가 route를 떠난 시점)부터
        # 실제 cutoff_t(진짜 0-crossing)까지 걸린 시간이 실제 production
        # miss-tolerance 윈도(ROUTE_APEX_MISS_TOLERANCE_FRAMES*dt, 기본
        # 6*0.05=0.3s)보다 크면 의심 -- held 상태에서 값이 몇 프레임
        # decaying하는 것(정상, 292차 docstring 4번)의 정상 범위를 넘어선
        # 경우다. UNRESOLVED(cutoff_t 없음)도 동일하게 플래그.
        cutoff_t = r.get("cutoff_t")
        gap = (cutoff_t - ep["t_end_old"]) if cutoff_t is not None and not np.isnan(cutoff_t) else None
        r["gap_end_to_cutoff_s"] = gap
        r["possible_fragmentation"] = bool(gap is None or gap > args.miss_tolerance * args.dt)
        sub_rows.append(r)
    rdf = pd.DataFrame(sub_rows)
    rdf.to_csv(f"{args.out_prefix}_breakdown.csv", index=False)

    print("\n세부원인 분포 (실제 production margin 기준):")
    print(rdf["sub_cause"].value_counts().to_string())

    n_frag = rdf["possible_fragmentation"].sum()
    print(f"\npossible_fragmentation 플래그(t_end_old->실제 cutoff_t 간격이 "
          f"miss-tolerance 윈도 {args.miss_tolerance * args.dt:.2f}s 초과, "
          f"§28 -- 최종판단 아님, qcamera 대조 권장): {n_frag}/{len(rdf)}건")

    lwcp = rdf[rdf["sub_cause"].str.startswith("lost_with_candidates_present")]
    print(f"\n=== 핵심 결과 ===")
    print(f"실제 production margin={args.old_ratio} 기준 lost_with_candidates_present "
          f"(orphan 후보): {len(lwcp)}건 / continuity {len(cont)}건 / 전체 에피소드 {len(odf)}건")
    for _, row in lwcp.iterrows():
        print(f"  ep={row['ep']}  cutoff_t={row['cutoff_t']:.2f}s  "
              f"candidateCount={row['candidate_count_at_cutoff']}  "
              f"last_valid_dist={row['last_valid_dist_m']:.1f}m")

    print(f"\n(참고) toolkit/sim_route_292_continuity_root_cause.py를 기본 인자로 "
          f"돌리면 --new-ratio(기본 1.05) what-if로 continuity 에피소드가 39건까지 "
          f"늘어나 보이는데, 이는 마진을 낮췄다고 가정한 가상 시나리오다 -- 실제 "
          f"production 수치는 이 스크립트의 {len(cont)}건이다(309차 정정, WIP/"
          f"FINDINGS 참고).")


if __name__ == "__main__":
    main()
