#!/usr/bin/env python3
"""
109차 신규: 옵션1 patch(long_mpc.py, LANE_CHANGE_DISCONTINUITY_DANGER_
CONFIRM_S) 검증용. `replay_lane_change_discontinuity_gate.py`의
`LaneChangeGateReplay`(76차, duration_mode='full')를 상속해
'discontinuity_lc' 트리거에 한해서만 danger_active가
LANE_CHANGE_DISCONTINUITY_DANGER_CONFIRM_S(0.25s, long_mpc.py 실제
값과 동일하게 유지) 동안 연속으로 유지돼야 force_revert를 인정하도록
확장한다. 'handoff'는 기존과 동일(즉시 revert, 회귀 없음).

목적: PATCHED가 108차에서 확정한 force_revert 에피소드(discontinuity_lc
3건)에서 boost 유지 구간이 실제로 늘어나는지(=boost가 조기에 base로
꺼지지 않는지), 동시에 이 패치가 다른 트리거(순수 discontinuity,
handoff)나 진짜 위험(danger_active가 오래 지속되는 경우) 반응에는
영향이 없는지(회귀 없음) 확인.

사용:
    from patched_replay_v109 import PatchedLaneChangeGateReplay
    from scan_force_revert_episodes import scan_route  # UNPATCHED 참고용

    rep = PatchedLaneChangeGateReplay(lane_change_gate=True, duration_mode='full')
    # run() 함수로 라우트 전체 재생, force_revert 여부는
    # res['timer_active'] and res['force_revert'] and res['a_change_cost'] < 300.0
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay_lane_change_discontinuity_gate import (  # noqa: E402
    LaneChangeGateReplay, RADAR_HANDOFF_JERK_BOOST_RELEASE_RATE,
)
from replay_boost_duration import DISCONTINUITY_JERK_COST_BOOST  # noqa: E402

# long_mpc.py 실제 값과 반드시 동일하게 유지 (109차 패치)
LANE_CHANGE_DISCONTINUITY_DANGER_CONFIRM_S = 0.25


class PatchedLaneChangeGateReplay(LaneChangeGateReplay):
  """LaneChangeGateReplay(76차, full모드) + 109차 옵션1(discontinuity_lc
  전용 danger confirm-hold)."""

  def __init__(self, lane_change_gate, duration_mode='full'):
    assert duration_mode == 'full', "109차 패치는 discontinuity_lc(full모드) 전용"
    super().__init__(lane_change_gate, duration_mode=duration_mode)
    self._lc_danger_confirm_timer = 0.0

  def step(self, dt, lead_status, dRel, vRel, a_lead, radar_locked, v_ego, cruise_enabled,
            blinker_active):
    # 부모 step()의 트리거/타이머 갱신 로직은 그대로 재사용하되, force_revert
    # 판정부만 오버라이드해야 하므로 부모 step()을 통째로 복붙하지 않고
    # -- 트리거 소스는 부모가 이미 계산해두므로(self._trigger_source),
    # 여기서는 danger_active만 부모 결과에서 받아 confirm 로직을 얹는다.
    res = super().step(dt, lead_status, dRel, vRel, a_lead, radar_locked, v_ego,
                        cruise_enabled, blinker_active)

    if self._trigger_source == 'discontinuity_lc':
      if res['danger_active']:
        self._lc_danger_confirm_timer += dt
      else:
        self._lc_danger_confirm_timer = 0.0
      lc_danger_confirmed = self._lc_danger_confirm_timer >= LANE_CHANGE_DISCONTINUITY_DANGER_CONFIRM_S
    else:
      lc_danger_confirmed = False
      self._lc_danger_confirm_timer = 0.0

    # 부모 step()은 이미 danger_active 즉시 반영해서 a_change_cost/
    # _release_value를 계산해버렸으므로, discontinuity_lc이고 danger_active가
    # 아직 confirm 안 된 경우에만 boost 값으로 재계산한다.
    if (self._trigger_source == 'discontinuity_lc' and res['danger_active']
        and not lc_danger_confirmed and self._timer > 0.0):
      a_change_cost = DISCONTINUITY_JERK_COST_BOOST
      self._release_value = DISCONTINUITY_JERK_COST_BOOST
      force_revert = False
    else:
      a_change_cost = res['a_change_cost']
      force_revert = res['danger_active'] if self._trigger_source != 'discontinuity_lc' else lc_danger_confirmed

    res = dict(res)
    res['a_change_cost'] = a_change_cost
    res['force_revert'] = force_revert
    res['lc_danger_confirm_timer'] = self._lc_danger_confirm_timer
    return res


def scan_route_patched(route_id, rows, force_revert_cost_thresh=300.0):
    """scan_force_revert_episodes.scan_route()와 동일한 인터페이스,
    PatchedLaneChangeGateReplay 사용."""
    clean_rows = [r for r in rows
                  if r.get("vEgo", "") not in ("", None)
                  and r.get("aEgo", "") not in ("", None)]
    clean_rows = sorted(clean_rows, key=lambda r: float(r["t"]))

    rep = PatchedLaneChangeGateReplay(lane_change_gate=True, duration_mode='full')
    episodes = []
    cur = None
    prev_t = None

    def _b(v):
        return v in ('True', '1', 'true')

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
        is_fr = (res['timer_active'] and res.get('force_revert', res['danger_active'])
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
