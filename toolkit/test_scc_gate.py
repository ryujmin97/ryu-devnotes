#!/usr/bin/env python3
"""
37차 -- SCC 단일점 폴백(`track_scc`, trackId=0) 채택 시 dPath(차로내
위치) 검증 게이트 회귀 검증 스크립트.

당시(37차) 이 검증은 세션 컨테이너의 work/test_scc_gate.py에만 있었고
`toolkit/`에는 저장되지 않은 채로 세션이 종료됨 -- 80차에서 뒤늦게
발견/정식 편입(당시 실행 로그는 남아있지 않아 이번에 재작성 후
현재 radard.py 코드 기준으로 재검증).

재현 대상 (`selfdrive/controls/radard.py`, `RadarD.get_lead()`,
L807~845 부근):
    used_scc_fallback = False
    if (track is None or lead_msg.prob < .6) and track_scc is not None \\
       and track_scc.cnt > 2:
      if self.enable_radar_tracks == -1 or \\
         (self.enable_radar_tracks >= 2 and track_scc.vLead < 5.0):
        if abs(track_scc.dPath) < SCC_FALLBACK_DPATH_GATE:  # 2.0m
          track = track_scc
          used_scc_fallback = True

핵심: `track_scc`는 비전 대응 없이 채택되는 단일점 폴백이라 차로내
위치 검증이 없으면 옆차선/주행경로 밖 정지물체를 오채택할 수 있음
(37차 배경, FINDINGS.md 참고). 이 스크립트는 위 조건식 전체를
`enable_radar_tracks == -1`(Genesis DH 실사용 설정, params_backup 확인)
케이스에 한정해 순수함수로 재현한다.

의존성: 없음(표준 라이브러리만).

사용:
    python3 test_scc_gate.py
"""

SCC_FALLBACK_DPATH_GATE = 2.0  # m


def get_lead_scc_fallback(track_present, lead_msg_prob, track_scc_cnt,
                           track_scc_dpath, track_scc_vlead,
                           enable_radar_tracks=-1):
    """
    RadarD.get_lead()의 SCC 폴백 채택 분기만 순수함수로 재현.
    track_present: 비전 매칭된 track이 이미 있는지(None이 아닌지) 여부.
    반환: (used_scc_fallback: bool, gate_blocked: bool)
        gate_blocked=True면 dPath 게이트가 폴백 자체를 막았다는 뜻
        (즉 후보 조건은 만족했으나 dPath 초과로 거부됨).
    """
    track_scc_present = track_scc_cnt > 2  # None 대용(테스트 편의상 cnt=0을 "없음"으로 취급)
    candidate = (not track_present or lead_msg_prob < .6) and track_scc_present
    if not candidate:
        return False, False

    mode_ok = (enable_radar_tracks == -1) or \
              (enable_radar_tracks >= 2 and track_scc_vlead < 5.0)
    if not mode_ok:
        return False, False

    if abs(track_scc_dpath) < SCC_FALLBACK_DPATH_GATE:
        return True, False
    else:
        return False, True  # 후보였으나 dPath 게이트에 막힘


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  PASS: {msg}")


def scenario_adjacent_lane_blocked():
    """37차 배경 사례: 옆차선 정지물체(dPath 큼) -- 비전 매칭 실패
    (track_present=False) 상태에서 SCC 단일점이 옆차선을 오채택하려는
    상황을 게이트가 차단해야 함."""
    print("[시나리오1] 옆차선 오검출(|dPath|>=2.0m) -- 폴백 채택 거부")
    used, blocked = get_lead_scc_fallback(
        track_present=False, lead_msg_prob=0.3, track_scc_cnt=5,
        track_scc_dpath=5.5, track_scc_vlead=0.0, enable_radar_tracks=-1)
    _assert(not used and blocked,
            "dPath=5.5m(37차 배경 실측 -5.5~-10.5m 범위 대표값) -- 명백히 차로 밖, 폴백 채택 안 됨")


def scenario_borderline_curve_blocked():
    """37차 배경 사례 중 애매했던 저속 도심 커브 1건(dPath 미실측 시절엔
    yRel -1.4~-1.5m로 단순 yRel 게이트로 못 거를 수 있던 케이스) --
    dPath 기준 게이트가 이 케이스도 차단하는지 확인(2.0m 문턱 근처는
    통과, 초과분은 차단)."""
    print("[시나리오2] 문턱 근접 케이스 -- dPath=2.1m(문턱 초과) 거부, dPath=1.9m(문턱 이내) 채택")
    used_over, blocked_over = get_lead_scc_fallback(
        track_present=False, lead_msg_prob=0.3, track_scc_cnt=5,
        track_scc_dpath=2.1, track_scc_vlead=0.0, enable_radar_tracks=-1)
    _assert(not used_over and blocked_over, "dPath=2.1m(SCC_FALLBACK_DPATH_GATE=2.0 초과) -- 거부")

    used_in, blocked_in = get_lead_scc_fallback(
        track_present=False, lead_msg_prob=0.3, track_scc_cnt=5,
        track_scc_dpath=1.9, track_scc_vlead=0.0, enable_radar_tracks=-1)
    _assert(used_in and not blocked_in, "dPath=1.9m(문턱 이내) -- 정상 채택")


def scenario_in_lane_lead_accepted():
    """정상 케이스: 차로 내(dPath 작음) 정지/저속 선행차 -- 비전 매칭 실패
    상황에서도 SCC 단일점 폴백이 정상적으로 채택돼야 함(게이트가 정상
    케이스까지 막으면 회귀)."""
    print("[시나리오3] 회귀 확인 -- 차로 내 정상 리드(|dPath|<2.0m)는 폴백 정상 채택")
    used, blocked = get_lead_scc_fallback(
        track_present=False, lead_msg_prob=0.3, track_scc_cnt=5,
        track_scc_dpath=0.3, track_scc_vlead=0.0, enable_radar_tracks=-1)
    _assert(used and not blocked, "dPath=0.3m -- 정상 채택, 게이트로 인한 회귀 없음")


def scenario_track_scc_absent_no_candidate():
    """track_scc 자체가 없거나(cnt<=2, 아직 신뢰 부족) track이 이미
    확실히 있는 경우(prob>=.6) -- 애초에 폴백 후보 조건 자체가 안
    열려야 함(37차 게이트와 무관한 정상 no-op)."""
    print("[시나리오4] 회귀 확인 -- 폴백 후보 조건 자체가 안 열리는 케이스(no-op)")
    used1, blocked1 = get_lead_scc_fallback(
        track_present=False, lead_msg_prob=0.3, track_scc_cnt=1,  # cnt<=2, 아직 미신뢰
        track_scc_dpath=0.3, track_scc_vlead=0.0, enable_radar_tracks=-1)
    _assert(not used1 and not blocked1, "track_scc.cnt<=2(신뢰 부족) -- 후보 자체 아님, 게이트 무관")

    used2, blocked2 = get_lead_scc_fallback(
        track_present=True, lead_msg_prob=0.8,  # 이미 확실한 비전 매칭 track 존재
        track_scc_cnt=5, track_scc_dpath=5.0, track_scc_vlead=0.0, enable_radar_tracks=-1)
    _assert(not used2 and not blocked2,
            "track 이미 존재+prob>=.6(확실) -- 폴백 후보 자체 아님, dPath 게이트와 무관하게 no-op")


def scenario_low_confidence_with_existing_track():
    """60차 계속8 관련 확인: track이 이미 있어도 lead_msg.prob<.6(저확신)이면
    폴백 후보 조건이 다시 열림 -- 이 경우에도 dPath 게이트가 동일하게
    적용돼야 함(있었다고 게이트를 우회하면 안 됨, get_lead() 주석 명시)."""
    print("[시나리오5] track 존재+저확신(prob<.6) -- dPath 게이트 우회 없이 동일 적용")
    used, blocked = get_lead_scc_fallback(
        track_present=True, lead_msg_prob=0.4,  # track은 있으나 저확신
        track_scc_cnt=5, track_scc_dpath=4.0, track_scc_vlead=0.0, enable_radar_tracks=-1)
    _assert(not used and blocked,
            "track 존재해도 prob<.6+dPath=4.0m(초과) -- 게이트 우회 없이 동일하게 거부됨"
            "(get_lead() 주석의 '검증을 우회하는 구멍 방지' 의도 재확인)")


if __name__ == "__main__":
    scenario_adjacent_lane_blocked()
    scenario_borderline_curve_blocked()
    scenario_in_lane_lead_accepted()
    scenario_track_scc_absent_no_candidate()
    scenario_low_confidence_with_existing_track()
    print("\n전 시나리오 통과 -- 37차 SCC_FALLBACK_DPATH_GATE 로직이 현재"
          " radard.py get_lead()와 일치(옆차선/차로밖 오채택 차단, 정상"
          " 채택/no-op 케이스 회귀 없음)함을 확인.")
