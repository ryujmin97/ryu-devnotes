#!/usr/bin/env python3
"""
verify_route_release_hold_283_real_log.py (283차 신규)

목적: 282차(`ROUTE_RELEASE_HOLD_S` 2.0->0.0) 패치 반영 후 실차 로그로
"RELEASE 직후 candidate 재검출로 인한 ENGAGE/RELEASE 진동(가감속 반복)"
발생 여부(253차가 우려했던 케이스, 282차 WIP "다음 작업" (b) 항목)를
검증한다. 281차 `sim_route_281_release_hold_ab.py`(합성 시나리오)와 달리
이 스크립트는 `extract_log.py` 실측 CSV를 입력으로 받는다.

방법:
1. `src=='route'`(carrotMan arbitration에서 route가 실제로 desiredSpeed를
   결정한 프레임)를 ACTIVE 프록시로 사용한다. `routeApexIdx!=-1`를 프록시로
   쓰면 min() 산식 자체의 프레임 단위 후보 재탐색 잡음(기존에 이미 알려진
   "min() arbitration has no hysteresis" 이슈, ROUTE_RELEASE_HOLD_S와 무관)
   까지 전부 "재-ACTIVE"로 잡혀 과다검출되므로 사용하지 않는다(283차에서
   직접 비교 확인 -- WIP.md 283차 참고).
2. `src=='route'` 연속 구간(run)을 `--merge-tol`(기본 1.0s) 이내 gap은
   같은 "에피소드"로 병합한다 -- 이 병합 없이 raw run 단위로 보면 동일
   커브를 감속하며 접근하는 도중에도(§ 위 1번 이유) 초 단위 미만의 run이
   반복 발생해 "재-ACTIVE 빈도"가 실제보다 부풀려진다.
3. 에피소드 간 gap이 `--hold-s`(기본 2.0, 구 hold값) 미만인 경우를
   "hold=2.0이었다면 발생하지 않았을 재-ACTIVE"로 표시하고, 각 전이
   구간(이전 에피소드 종료 -0.5s ~ 새 에피소드 시작 +1.0s)의 aEgo
   min/max/range를 계산해 "가감속 반복(pump)" 여부를 정성 판단할 수 있게
   출력한다. aEgo가 짧은 구간 안에서 뚜렷한 양의 스파이크(재가속) 직후
   뚜렷한 음의 스파이크(재감속)를 동시에 보이면 pump 의심 -- 이 스크립트는
   자동 판정을 내리지 않고 후보만 나열한다(§28, 추측만으로 원인 확정 금지).

283차 실측 결과(4개 route, 16:56~18:03 연속 주행, 80145행): gap<2.0s
재-ACTIVE 11건 전부 저속(vEgo 9~11m/s) 근접 apex_dist(10~50m) 구간의
교차로/저속 회전 상황이었고, aEgo range는 최대 1.79 m/s²로 정상 주행
변동 범위 내(뚜렷한 pump 시그니처 없음). 상세: WIP.md 283차.

**한계**:
- ACTIVE 프록시가 `src=='route'`이므로, route가 이겼다가 다른 소스(vturn/
  section/gas 등)에 밀렸다가 다시 route가 이기는 경우도 전부 "에피소드
  경계"로 잡힌다 -- 실제 `self.route_active`/`route_release_time` 내부
  상태와 100% 동일하지는 않다(코드 내부 상태를 직접 로깅하지 않는 한
  외부에서 완전히 재현 불가, 179차 이후 반복되는 한계와 동일 성격).
- S커브 등 "같은 물리적 위치"를 여러 주행에서 비교하려면 GPS/naviPaths
  기반 위치 매칭이 별도로 필요 -- 이 스크립트는 시간축 통계만 제공한다.
- 실차 검증이지만 "운전자 체감"(승차감 등 주관적 지표)은 대변하지 않는다.

사용:
    python3 verify_route_release_hold_283_real_log.py route1.csv route2.csv ... \
        [--merge-tol 1.0] [--hold-s 2.0]

여러 route CSV를 시간순으로 이어붙여 하나의 연속 주행으로 취급한다(같은
boot 세션 내 route ID만 바뀌는 경우 -- 283차 실측 사례처럼 t가 route
경계에서 이어지는지 먼저 확인할 것, 이어지지 않으면 별도 실행 권장).
"""
import sys
import argparse
import pandas as pd
import numpy as np


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--merge-tol", type=float, default=1.0,
                     help="같은 에피소드로 병합할 최대 gap(s), 기본 1.0")
    ap.add_argument("--hold-s", type=float, default=2.0,
                     help="비교 기준 구 hold값(s), 기본 2.0")
    ap.add_argument("--out-prefix", default="route_release_verify")
    args = ap.parse_args()

    df = load_concat(args.csvs)
    t = df["t"].values
    aEgo = df["aEgo"].values
    vEgo = df["vEgo"].values
    apexDist = df["routeApexDist"].values
    is_route = (df["src"].values == "route")

    runs = find_runs(is_route)
    if not runs:
        print("route src 구간이 전혀 없습니다.")
        sys.exit(1)

    episodes = merge_runs(runs, t, args.merge_tol)
    print(f"raw runs: {len(runs)}  ->  merged episodes(tol={args.merge_tol}s): {len(episodes)}")

    rows = []
    for i, (s, e) in enumerate(episodes):
        gap_before = (t[s] - t[episodes[i - 1][1] - 1]) if i > 0 else None
        rows.append({
            "ep": i, "t_start": t[s], "t_end": t[e - 1],
            "dur": t[e - 1] - t[s], "gap_before": gap_before,
            "apex_dist_start": apexDist[s],
            "vEgo_start_kph": vEgo[s] * 3.6,
        })
    edf = pd.DataFrame(rows)
    edf.to_csv(f"{args.out_prefix}_episodes.csv", index=False)

    close = edf[(edf.gap_before.notna()) & (edf.gap_before < args.hold_s)].copy()
    print(f"\ngap_before < {args.hold_s}s (구 hold였다면 불가능했을 재-ACTIVE): {len(close)}건")

    pump_rows = []
    for _, row in close.iterrows():
        ep = int(row.ep)
        t_prev_end = edf.iloc[ep - 1]["t_end"]
        t_start = row.t_start
        mask = (t >= t_prev_end - 0.5) & (t <= t_start + 1.0)
        a_win = aEgo[mask]
        pump_rows.append({
            "ep": ep, "gap_before": row.gap_before, "t_start": t_start,
            "apex_dist_start": row.apex_dist_start,
            "vEgo_start_kph": row.vEgo_start_kph,
            "a_min": a_win.min(), "a_max": a_win.max(),
            "a_range": a_win.max() - a_win.min(),
            "possible_pump": bool((a_win > 0.3).any() and (a_win < -0.5).any()),
        })
    pdf = pd.DataFrame(pump_rows)
    if len(pdf):
        pdf.to_csv(f"{args.out_prefix}_close_gap_aego.csv", index=False)
        print(pdf.to_string())
        n_pump = pdf["possible_pump"].sum()
        print(f"\npossible_pump 후보(양+음 스파이크 동시 검출): {n_pump}건 "
              f"-- 반드시 해당 구간 qcamera로 육안 재확인 후 결론 내릴 것(§28).")
    else:
        print("(해당 없음)")


if __name__ == "__main__":
    main()
