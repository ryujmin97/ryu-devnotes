#!/usr/bin/env python3
"""
108차 신규: replay_lane_change_discontinuity_gate.py의 LaneChangeGateReplay
(duration_mode='full', 75-76차, 현재 long_mpc.py의 discontinuity_lc 소스와
100% 동일 로직)를 여러 라우트에 대해 "라우트 전체를 한 번에 연속 재생"
방식으로 돌려 force_revert(=danger_active인데도 timer_active라서
a_change_cost가 boost 값 밑으로 못 내려간, 즉 boost가 여전히 안전측
danger 반응을 막고 있을 뻔한 프레임) 에피소드를 자동 탐지/그룹핑한다.

**왜 이 도구가 필요했는가 (108차 발견)**: 클러스터 구간만 잘라
warm-start로 재생하면 상태머신이 매번 리셋돼 pad_s에 따라 결과가
달라지는 아티팩트가 생긴다 -- 반드시 라우트 전체를 시간순으로 한 번에
연속 재생해야 한다. 또한 트리거 소스별로 실제 hard-hold 시간이 다르므로
(discontinuity=1.0s, handoff/discontinuity_lc=4.0s) 이 구분을 하지
않는 재현 도구(폐기된 flicker_cluster_boost_replay.py)는 허위 severe
사례를 만들어낸다 -- 반드시 LaneChangeGateReplay를 그대로 써야 한다.

force_revert 정의: timer_active(boost 타이머 아직 살아있음) AND
danger_active(TTC 등으로 진짜 위험 판정) AND a_change_cost < 300.0
(boost 값 500 밑으로 떨어짐 = 게이트가 danger에 밀려 boost가 무력화된
순간). 연속된 force_revert 프레임을 하나의 에피소드로 묶는다.

사용:
    from scan_force_revert_episodes import scan_many_routes
    eps = scan_many_routes(route_rows_map)  # {route_id: rows}

route_rows_map의 rows는 analysis_helpers.load_csv() 또는
data_routes.load_route()가 반환하는 list(dict) 그대로 사용 가능.
vEgo/aEgo가 빈 문자열인 행(세그먼트 경계 등)은 자동 필터링한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay_lane_change_discontinuity_gate import LaneChangeGateReplay  # noqa: E402


def _b(v):
    return v in ('True', '1', 'true')


def scan_route(route_id, rows, force_revert_cost_thresh=300.0):
    """단일 라우트를 시간순 연속 재생해 force_revert 에피소드 리스트를 반환.

    반환: [{"route_id","trigger_source","blinker_active_at_start",
            "lane_change_active","t_start","t_end","duration_s",
            "min_aEgo","n_frames"}, ...]
    """
    clean_rows = [r for r in rows
                  if r.get("vEgo", "") not in ("", None)
                  and r.get("aEgo", "") not in ("", None)]
    clean_rows = sorted(clean_rows, key=lambda r: float(r["t"]))

    rep = LaneChangeGateReplay(lane_change_gate=True, duration_mode='full')
    episodes = []
    cur = None
    prev_t = None

    for r in clean_rows:
        t = float(r['t'])
        dt = (t - prev_t) if prev_t is not None else 0.05
        prev_t = t
        lead_status = _b(r['leadStatus'])
        dRel = float(r['leadDRel']) if r['leadDRel'] not in ('', None) else 0.0
        vRel = float(r['leadVRel']) if r['leadVRel'] not in ('', None) else 0.0
        a_lead = float(r['leadALeadK']) if r.get('leadALeadK') not in ('', None) else 0.0
        radar_locked = _b(r['leadRadar'])
        v_ego = float(r['vEgo'])
        cruise_enabled = _b(r['cruiseEnabled'])
        aEgo = float(r['aEgo'])
        blinker = _b(r.get('leftBlinker')) or _b(r.get('rightBlinker'))

        res = rep.step(dt, lead_status, dRel, vRel, a_lead, radar_locked, v_ego,
                        cruise_enabled, blinker)
        is_fr = (res['timer_active'] and res['danger_active']
                 and res['a_change_cost'] < force_revert_cost_thresh)

        if is_fr:
            if cur is None:
                cur = dict(route_id=route_id, t_start=t, t_end=t,
                           trigger_source=res['trigger_source'], min_aEgo=aEgo,
                           blinker_active_at_start=blinker,
                           lane_change_active=res['lane_change_active'], n_frames=1)
            else:
                cur['t_end'] = t
                cur['min_aEgo'] = min(cur['min_aEgo'], aEgo)
                cur['n_frames'] += 1
        else:
            if cur is not None:
                cur['duration_s'] = cur['t_end'] - cur['t_start']
                episodes.append(cur)
                cur = None

    if cur is not None:
        cur['duration_s'] = cur['t_end'] - cur['t_start']
        episodes.append(cur)

    return episodes


def scan_many_routes(route_rows_map, force_revert_cost_thresh=300.0):
    """route_rows_map: {route_id: rows} -> 전체 라우트의 force_revert
    에피소드를 하나의 리스트로 합쳐 반환 (min_aEgo 오름차순 정렬은 호출부에서)."""
    all_eps = []
    for route_id, rows in route_rows_map.items():
        all_eps.extend(scan_route(route_id, rows, force_revert_cost_thresh))
    return all_eps


if __name__ == '__main__':
    # 간단한 단독 실행 예시: data_routes에 등록된 라우트 중 인자로 준 것만 스캔
    import argparse
    from data_routes import load_route

    ap = argparse.ArgumentParser()
    ap.add_argument('devnotes_dir')
    ap.add_argument('route_ids', nargs='+')
    args = ap.parse_args()

    route_rows_map = {}
    for rid in args.route_ids:
        rows, meta = load_route(args.devnotes_dir, rid)
        route_rows_map[rid] = rows

    eps = scan_many_routes(route_rows_map)
    print(f"총 라우트 수: {len(route_rows_map)} / force_revert 에피소드: {len(eps)}")
    for e in sorted(eps, key=lambda x: x['min_aEgo']):
        print(f"{e['route_id']:14} src={e['trigger_source']:16} "
              f"blinker={e['blinker_active_at_start']!s:6} "
              f"t={e['t_start']:.2f}~{e['t_end']:.2f} dur={e['duration_s']:.2f}s "
              f"min_aEgo={e['min_aEgo']:.2f}")
