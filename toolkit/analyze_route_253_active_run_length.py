#!/usr/bin/env python3
"""
analyze_route_253_active_run_length.py (253차 세션, 신규 -- NEEDS_VALIDATION)

목적: 239차 CRITICAL(self-elimination 진동)이 새 INERT/ACTIVE 상태머신에서
수치적으로도 해소됐는지 확인하기 위한 route-active "run"(연속 구간) 개수
비교. 253차 세션 전반부(컨테이너 초기화로 유실)에서 RELEASE-hold 버그가
있던 초기 버전 스크립트로 1차 실행했을 때, route_ac 로그에서 실측 61건
대비 시뮬 163건의 짧은 run이 관측됐다(WIP.md 253차 항목 "미완료" 참고).
이 스크립트는 그 관측을 sim_route_252_active_state_full.py의 수정본
(2초 RELEASE hold 포함)으로 재실행해, 비정상적 run 분절이 버그였는지
실제 상태머신 특성이었는지 판별한다.

이 스크립트는 기존 toolkit(§21)을 수정하지 않고, sim_route_252_active_state_
full.py의 replay()/Sim252를 그대로 import해 재사용한다(§21/§27 -- 로직
중복 작성 금지).

**한계(§28)**:
1. "run"은 실측은 CSV `src`=="route" 연속 구간, 시뮬은 replay() 출력의
   `sim_src`=="route" 연속 구간으로 정의한다. 실측 `src`는 desiredSpeed
   arbitration의 최종 승자 소스라 route 외 다른 승자(vturn/cruise 등)로
   전환되면 run이 끊긴다 -- 시뮬은 route 후보 유무/ACTIVE 상태만 반영하고
   다른 소스와의 arbitration은 재현하지 않으므로, 두 run 정의는 완전히
   동일한 신호가 아니다(정성적/거시적 비교 목적, §28 명시).
2. open-loop 재생 한계는 sim_route_252_active_state_full.py와 동일.
3. 실차 검증 아님(§29).

사용:
    python3 analyze_route_253_active_run_length.py route.csv \
        [--safe-time 2.2] [--decel-rate 0.70] [--release-margin 1.1] \
        [--continuity-tolerance 10.0] [--short-run-s 2.0]

출력: 실측/시뮬 각각의 run 개수, run별 길이(초) 분포, --short-run-s 미만
"short run" 개수 비교.
"""
import argparse
import csv
import statistics
import sys

from sim_route_252_active_state_full import replay, load_csv


def find_runs(rows, key, t_key="t"):
    runs = []
    cur_start = None
    prev_t = None
    for row in rows:
        active = row.get(key) == "route"
        try:
            t = float(row[t_key])
        except (TypeError, ValueError):
            continue
        if active:
            if cur_start is None:
                cur_start = t
            prev_t = t
        else:
            if cur_start is not None:
                runs.append((cur_start, prev_t))
                cur_start = None
    if cur_start is not None:
        runs.append((cur_start, prev_t))
    return runs


def summarize(name, runs, short_run_s):
    durations = [end - start for start, end in runs if end is not None]
    short = [d for d in durations if d < short_run_s]
    print(f"\n=== {name}: {len(runs)}건 ===")
    if durations:
        print(f"  길이(초) min={min(durations):.2f} median={statistics.median(durations):.2f} "
              f"max={max(durations):.2f}")
    print(f"  {short_run_s}s 미만 short-run: {len(short)}건")
    return len(runs), len(short)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--safe-time", type=float, default=2.2)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--release-margin", type=float, default=1.1)
    ap.add_argument("--continuity-tolerance", type=float, default=10.0)
    ap.add_argument("--short-run-s", type=float, default=2.0)
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    print(f"loaded {len(rows)} rows from {args.csv_path}")

    sim_rows = replay(rows, args.safe_time, args.decel_rate, args.release_margin,
                       args.continuity_tolerance)

    real_runs = find_runs(rows, "src")
    sim_runs = find_runs(sim_rows, "sim_src")

    real_n, real_short = summarize("실측(CSV src==route)", real_runs, args.short_run_s)
    sim_n, sim_short = summarize("시뮬레이션(252차 상태머신, RELEASE-hold 수정본)", sim_runs,
                                  args.short_run_s)

    print(f"\n요약: run 개수 실측 {real_n}건 -> 시뮬 {sim_n}건 "
          f"(short-run<{args.short_run_s}s 기준 실측 {real_short}건 -> 시뮬 {sim_short}건)")
    print("주의: run 정의 차이(한계 1번, docstring 참고) 및 open-loop 재생 한계로 "
          "완전 동일 신호 비교가 아님 -- 자릿수 단위의 비정상적 분절 여부 판별 목적.")


if __name__ == "__main__":
    main()
