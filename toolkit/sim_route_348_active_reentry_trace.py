#!/usr/bin/env python3
"""
sim_route_348_active_reentry_trace.py (348차 신규)

목적
----
347차가 이월한 "다음 작업" 3번 -- 강제 RELEASE=lost 7건(x19seg 6+x10seg 1)이
실제 route_active 재진입까지 이어지는지 개별 사례 트레이스(301차 방식,
346차가 이월한 것과 동일 과제, 표본 7건으로 확대) -- 를 수행한다.

301차(`sim_route_301_lost_boundary_trace.py`)는 lost 발생 -> B(새 apex)
재획득 -> continuity 유지(matched/held) 생존시간까지는 이미 추적했지만,
"그 B가 실제로 route_active를 다시 True로 만들었는가"(INERT->ACTIVE 게이트
재통과)는 보지 않았다(301차 docstring에 명시된 범위 밖). `ActualLayer`
(300차, `sim_route_300_release_boundary_counterfactual.py`)는 이미
매 프레임 `route_active` bool을 갖고 `step()`이 `(out_speed, route_active)`를
반환하므로, 이 스크립트는 그 값을 프레임별로 그대로 기록만 하면 된다
(§27 -- ActualLayer.step()의 산식/분기는 한 글자도 바꾸지 않음, 관측
레이어만 얇게 추가).

방법
----
1. 301차의 `build_stream`(continuity 재생, 무변경 import)으로 스트림 생성.
2. `ActualLayer`(300차, 무변경 import)를 스트림 전체에 재생하되, 이번에는
   `actual.events`(강제 RELEASE 이벤트)뿐 아니라 매 프레임의 `route_active`
   값도 별도 리스트에 기록한다(300/301차는 이 궤적 자체를 저장하지 않았음
   -- 이 스크립트의 유일한 신규 관측 지점).
3. 301차의 `trace_lost_events`를 그대로 재사용해 7건의 A->LOST->B 정보
   (B_survive_seconds/frames 등)를 얻는다.
4. 각 강제 RELEASE=lost 이벤트 프레임 i(이 프레임에서 `route_active`가
   False로 막 전환됨, ActualLayer.step() 그 프레임 자체 반환값)부터
   스트림 끝까지 `route_active` 궤적을 스캔해, **다시 True로 바뀌는 첫
   프레임**(재진입)을 찾는다. 재진입 시점의 apex_dist/apex_speed/mode/
   cluster_size와, 그 재진입이 301차가 이미 추적한 "B"(같은 프레임에
   즉시 재획득된 apex) 자체에 의한 것인지, B가 먼저 continuity를
   잃은 뒤 그 다음(C 이상)에 의한 것인지를 구분해 기록한다.
5. 재진입을 못 찾으면(스트림 끝까지 route_active=False 유지) `None`으로
   보고한다 -- 추측하지 않음(§28).

**하지 않는 것**: qcamera 대조, confidence 게이트 설계, `carrot_man.py`
패치. ANALYSIS_ONLY, `ryu` 코드 무변경(§29).

사용
----
    python3 sim_route_348_active_reentry_trace.py \\
        --csv /home/claude/work/x19seg_348.csv \\
        --map-turn-speed-factor 1.10 --ctrl-end 8.0 --decel-rate 0.70
"""
import argparse
import sys

sys.path.insert(0, ".")

from sim_route_301_lost_boundary_trace import build_stream, trace_lost_events
from sim_route_300_release_boundary_counterfactual import ActualLayer


def replay_with_active_trace(stream, ctrl_end, decel_rate):
    """ActualLayer.step()을 그대로 호출하되(§27 -- 무변경), 매 프레임의
    route_active 값을 별도로 기록한다(300/301차는 이 궤적 자체를 저장하지
    않았음 -- 이번 스크립트의 유일한 신규 관측 지점)."""
    actual = ActualLayer()
    route_active_trace = []
    for fr in stream:
        out_speed, route_active = actual.step(
            fr["t"], fr["apex_idx"], fr["apex_dist"], fr["apex_speed"],
            fr["mode"], fr["streak"], fr["v_ego_ms"], fr["v_ego_kph"],
            ctrl_end, decel_rate)
        route_active_trace.append(route_active)
    return actual, route_active_trace


def trace_reentry(stream, route_active_trace, lost_events, max_search_s):
    """lost_events(301차 trace_lost_events 출력) 각각에 대해, 해당 프레임
    이후 route_active가 다시 True로 바뀌는 첫 프레임을 찾는다."""
    t_index = {round(row["t"], 2): i for i, row in enumerate(stream)}
    out = []
    for ev in lost_events:
        i = t_index.get(ev["t"])
        if i is None:
            continue
        reentry = None
        for j in range(i + 1, len(stream)):
            if stream[j]["t"] - stream[i]["t"] > max_search_s:
                break
            if route_active_trace[j] and not route_active_trace[j - 1]:
                reentry = j
                break
        row = dict(ev)
        if reentry is None:
            row["reentry_found"] = False
            row["reentry_t"] = None
            row["reentry_gap_seconds"] = None
            row["reentry_gap_frames"] = None
            row["reentry_apex_dist"] = None
            row["reentry_apex_speed"] = None
            row["reentry_mode"] = None
            row["reentry_within_B_survival"] = None
        else:
            rrow = stream[reentry]
            row["reentry_found"] = True
            row["reentry_t"] = round(rrow["t"], 2)
            row["reentry_gap_seconds"] = round(rrow["t"] - stream[i]["t"], 2)
            row["reentry_gap_frames"] = reentry - i
            row["reentry_apex_dist"] = (round(rrow["apex_dist"], 1)
                                         if rrow["apex_dist"] is not None else None)
            row["reentry_apex_speed"] = (round(rrow["apex_speed"], 1)
                                          if rrow["apex_speed"] is not None else None)
            row["reentry_mode"] = rrow["mode"]
            # B(=이번 lost 프레임에 즉시 재획득된 apex)가 재진입 시점까지
            # continuity를 끊김없이 유지했는지(같은 apex) 여부 -- 301차
            # B_survive_frames 범위 안에 재진입이 들어오면 "같은 B",
            # 벗어나면 B도 한 번 더 끊긴 뒤(C 이상) 재진입한 것으로 판단.
            row["reentry_within_B_survival"] = (
                ev["B_dist_m"] is not None
                and row["reentry_gap_frames"] <= ev["B_survive_frames"] + 1
            )
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--map-turn-speed-factor", type=float, default=1.10)
    ap.add_argument("--ctrl-end", type=float, default=8.0)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--persistence-horizon", type=float, default=5.0,
                     help="301차와 동일 -- B 생존 관찰 창(초)")
    ap.add_argument("--reentry-search-horizon", type=float, default=60.0,
                     help="route_active 재진입을 찾을 최대 탐색 시간(초)")
    args = ap.parse_args()

    stream = build_stream(args.csv, args.map_turn_speed_factor)

    # (1) 301차 방식 그대로: 강제 RELEASE 이벤트 탐지 + A->LOST->B 정보.
    #     여기서는 actual.events만 쓰고 route_active 궤적은 버림(1회차 재생).
    actual_for_events = ActualLayer()
    for fr in stream:
        actual_for_events.step(fr["t"], fr["apex_idx"], fr["apex_dist"],
                                fr["apex_speed"], fr["mode"], fr["streak"],
                                fr["v_ego_ms"], fr["v_ego_kph"],
                                args.ctrl_end, args.decel_rate)
    lost_events = trace_lost_events(stream, actual_for_events.events,
                                     args.persistence_horizon)

    # (2) route_active 궤적을 기록하는 2회차 재생(동일 스트림, 동일 파라미터
    #     -> ActualLayer는 결정론적이므로 actual.events는 (1)과 100% 동일해야
    #     함, 아래에서 assert로 확인).
    actual2, route_active_trace = replay_with_active_trace(
        stream, args.ctrl_end, args.decel_rate)
    assert len(actual2.events) == len(actual_for_events.events), (
        "재생 비결정성 감지 -- ActualLayer가 순수 함수가 아님(버그 가능성)")

    reentry_rows = trace_reentry(stream, route_active_trace, lost_events,
                                  args.reentry_search_horizon)

    print(f"=== 강제 RELEASE=lost {len(lost_events)}건 개별 재진입 트레이스 "
          f"({args.csv}) ===\n")
    for r in reentry_rows:
        print(f"t={r['t']:.2f}  A_last(t={r['A_last_matched_t']}, "
              f"dist={r['A_last_dist_m']}m, speed={r['A_last_speed_kph']}km/h, "
              f"gap={r['gap_seconds_A_to_LOST']}s)")
        print(f"  -> B(dist={r['B_dist_m']}, speed={r['B_speed_kph']}, "
              f"cluster={r['B_cluster_size']}/{r['B_n_clusters_total_this_frame']}) "
              f"survive={r['B_survive_seconds']}s/{r['B_survive_frames']}f"
              f"{'(+)' if r['B_survived_full_horizon'] else ''}")
        if r["reentry_found"]:
            same_b = "같은 B 유지 중 재진입" if r["reentry_within_B_survival"] \
                else "B도 끊긴 뒤 재진입(신규 apex 추정)"
            print(f"  -> route_active 재진입: t={r['reentry_t']} "
                  f"(+{r['reentry_gap_seconds']}s/{r['reentry_gap_frames']}f), "
                  f"재진입시 apex_dist={r['reentry_apex_dist']}, "
                  f"apex_speed={r['reentry_apex_speed']}, mode={r['reentry_mode']} "
                  f"[{same_b}]")
        else:
            print(f"  -> route_active 재진입: 없음 "
                  f"(탐색범위 {args.reentry_search_horizon}s 내 미재진입)")
        print()

    n_reentry = sum(1 for r in reentry_rows if r["reentry_found"])
    n_same_b = sum(1 for r in reentry_rows
                   if r["reentry_found"] and r["reentry_within_B_survival"])
    print(f"=== 요약: {len(reentry_rows)}건 중 route_active 재진입 "
          f"{n_reentry}건 (탐색범위 {args.reentry_search_horizon}s) ===")
    if n_reentry:
        print(f"  그 중 같은 B 유지 중 재진입: {n_same_b}건, "
              f"B도 끊긴 뒤(신규 apex) 재진입: {n_reentry - n_same_b}건")


if __name__ == "__main__":
    main()
