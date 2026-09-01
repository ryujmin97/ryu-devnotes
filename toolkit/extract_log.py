#!/usr/bin/env python3
"""
라우트 폴더(세그먼트 여러 개, 각각 rlog.zst 포함)를 순회하며
자주 쓰는 필드들을 20Hz 기준 하나의 CSV로 뽑는다.

사용:
    python3 extract_log.py <route_dir> <out.csv> [--repo /home/claude/ryu] [--max-mb 400]

route_dir 예시 구조:
    route_dir/
      20260818_..._4/rlog.zst
      20260818_..._5/rlog.zst
      ...

CSV 컬럼:
    t, seg, commit,
    vEgo, aEgo, brakePressed, gasPressed, cruiseEnabled, vCruise, vCruiseCluster,
    steeringAngleDeg, desiredCurvature,
    leadStatus, leadDRel, leadVRel, leadVLead,
    src, desiredSpeed, vTurnSpeed

또한 <out.csv> 옆에 <out.csv>.meta.json 파일을 같이 생성한다.
여기에는 추출 당시의 repo commit hash / branch / commit 날짜·메시지,
route_dir, 추출 시각, 총 row 수가 기록된다.
이 값들로 "이 로그가 어느 코드 상태에서 뽑힌 건지"를 나중에도 추적할 수 있다.

2026-08-21 수정: 세그먼트 경계에서 carState/controlsState/leadStatus
상태를 이제 다음 세그먼트로 이어받는다 (이전에는 세그먼트마다
leadStatus=False로 강제 리셋되어, 실제로는 리드가 유지되고 있었는데도
새 세그먼트 시작 시 첫 radarState 이벤트 전까지 가짜 "순간유실" row가
찍히는 구조적 버그가 있었음 -- 세그먼트 경계와 diff=0.000s로 정확히
일치하는 leadStatus False 다수로 확인됨, FINDINGS.md 22차 참고). 이
버전으로 추출한 CSV는 meta.json에 `segment_state_carryover_fix: true`가
찍힌다 -- 과거 CSV(이 필드 없음)의 순간유실 이벤트는
`analysis_helpers.segment_boundary_lead_loss_artifacts()`로 먼저
아티팩트 여부를 걸러낼 것.
"""
import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from decode_rlog import iter_events

FIELDNAMES = [
    "t", "seg", "commit",
    "vEgo", "aEgo", "brakePressed", "gasPressed", "cruiseEnabled", "vCruise",
    "vCruiseCluster",
    "steeringAngleDeg", "desiredCurvature",
    "leadStatus", "leadDRel", "leadVRel", "leadVLead",
    "leadRadar", "leadModelProb",
    "leadDPath", "leadYRel", "leadALeadK", "leadRadarTrackId",
    "src", "desiredSpeed", "vTurnSpeed", "modelTurnSpeed",
    "leftBlinker", "rightBlinker",
    "laneChangeState", "laneChangeDirection",
    "activeLaneLine",
    "lllProb", "rllProb", "lllStd", "rllStd",
    "activeCarrot", "xTurnInfo", "xDistToTurn", "xSpdType", "xSpdDist",
    "atcType", "leftSec", "xSpdCountDown", "xTurnCountDown",
    "liveRouteSpeed",
    "ccYawDeg", "ccYawRateZ", "ccPoseValid",
    "vpPosPointLatNavi", "vpPosPointLonNavi", "dtNaviPacketAge", "positionDtSinceFix",
    "naviPointsActive", "navdActive", "dtRouteInactive", "routeSource",
    "routeApexIdx", "routeApexDist", "routeApexSpeed", "routeOutSpeed",
]
# 2026-09-02 추가(194차): carrotMan.routeApexIdx/routeApexDist/
# routeApexSpeed/routeOutSpeed -- 193차에서 추가했던 route apex 진단값이
# 실제로는 cereal(carrotMan)이 아니라 동반앱용 UDP JSON에만 채워지고
# rlog에는 전혀 기록되지 않던 설계 실수를 194차 패치로 바로잡은 뒤 추가한
# 컬럼(FINDINGS.md/WIP.md 193차/194차 참고). 이 계측은
# `cereal/custom.capnp`(routeApexIdx@38~routeOutSpeed@41)/carrot_man.py/
# carrot_serv.py 3곳을 함께 수정한 194차 패치 적용 이후 채록한 rlog에서만
# 값이 채워진다 -- **194차 이전 로그에는 capnp 기본값(0/0.0)만 나온다.**
# routeApexIdx=-1은 "해당 프레임에서 route apex 계산 자체가 스킵됨"(예:
# navi_points_active=False)을 의미하며 크래시나 데이터 없음과는 다르다.
# 2026-08-31 추가(182차 계측): carrotMan.naviPointsActive/navdActive/
# dtRouteInactive/routeSource -- "route 사전감속이 61초간 전혀 없었음"
# (FINDINGS.md 182차, route=390.0 기본값 노출)의 원인을 다음 실차 로그
# CSV만으로 직접 진단하기 위한 계측. naviPointsActive=False가 지속되는
# 동안(dtRouteInactive로 지속시간 직접 확인 가능) carrot_navi_route()는
# 곡률계산 자체를 스킵한다 -- 162/163차 게이트(positionDtSinceFix, "값은
# 들어오는데 위치추정이 부정확")와는 별개의 상위 단계 실패모드("애초에
# 폴리라인 수신 자체가 끊김"). routeSource는 마지막으로 route를 성공
# 수신한 경로(navd cereal/TCP 7709 raw/TCP 7712 handle_route)를 표시 --
# 드롭아웃 직전 어느 경로가 살아있었는지로 원인 후보를 좁히는 용도.
# 이 계측은 `0001-navi-route-activity-instrumentation.patch`(182차)로
# `ryu` 본체(cereal/custom.capnp, carrot_man.py, carrot_serv.py)에 실제
# 적용해야만 새 rlog에 찍힌다 -- **패치 적용 전 로그(과거 route)에는
# naviPointsActive=False, navdActive=False, dtRouteInactive=0.0,
# routeSource=""로 전부 capnp 기본값이 나옴(크래시 아님, "데이터 없음"과
# 동일 의미).**
# 2026-08-31 추가(169차 계측): carrotMan.vpPosPointLatNavi/LonNavi,
# dtNaviPacketAge, positionDtSinceFix -- "패킷단절 vs 내용정지" 구분용
# (FINDINGS.md 169차 NEEDS_INVESTIGATION). dtNaviPacketAge가 3.0을 넘으면
# "패킷단절"(navi 앱 신호 자체가 끊김), 3.0 미만인데 vpPosPointLatNavi/
# LonNavi가 여러 프레임 동안 값이 안 바뀌면 "내용정지"(패킷은 오지만
# 좌표가 그대로) -- 다음 실차 로그부터 이 둘을 CSV만으로 직접 구분
# 가능해짐. carrotMan.ccPoseValid(신규 cereal 필드)는 위 "carControl"
# 이벤트에서 이미 뽑는 ccPoseValid와 동일한 원본(len(orientationNED)>2)이라
# 중복 방지를 위해 CSV엔 추가하지 않음 -- 교차검증하려면 rlog에서 두
# 값이 항상 같은지 별도 확인할 것.
# 2026-08-31 추가(165차): carControl.orientationNED[2](라디안, calibrated
# NED 요/헤딩)를 나침반 표기(0~360도)로 변환한 ccYawDeg + carControl.
# angularVelocity[2](calibrated 요레이트, rad/s) 원시값 ccYawRateZ + 두 리스트가
# 실제로 채워져 있는지(calibrated_pose is not None일 때만 controlsd.py가
# 채움, 그 전엔 빈 List) 나타내는 ccPoseValid. **livePose를 직접 구독하지
# 않고 carControl에서 뽑는 이유**: carrot_serv.py L729의 기존 TODO 주석이
# 이미 "CC.orientationNED[2]를 이용하여" 보정하라고 명시해뒀고, controlsd.py
# L250-252(`CC.orientationNED = calibrated_pose.orientation.xyz.tolist()`,
# `CC.angularVelocity = calibrated_pose.angular_velocity.xyz.tolist()`)가
# 이미 캘리브레이션 보정까지 끝낸 값을 100Hz로 CarControl에 실어보내고
# 있음 -- carrot_man.py는 이미 'carControl'을 구독 중(L306)이라 신규
# SubMaster 서비스 추가 없이 기존 sm['carControl']에서 바로 꺼내 쓸 수 있음.
# (raw 'livePose' 구독 방식은 신규 서비스 추가 + 자체 캘리브레이션 처리가
# 필요해 더 무거움 -- 방향1 설계, FINDINGS.md 165차 참고).
# 목적: 162차가 확정한 근본원인(_update_gps()가 쓰는 bearing이 외부 GPS
# 정체 중 옛 헤딩으로 직진외삽)에 대한 방향1(헤딩보정) synthetic/실측
# 검증용 지상진실(ground truth) 확보. 프레임당 숫자 3개뿐이라 naviPaths처럼
# 별도 플래그 없이 기본 추출에 항상 포함.
# 2026-08-30 추가(149차): carrotMan.szPosRoadName -- carrot_serv.py
# L1100 `self.debugText += f"route={route_speed:.1f}"`가 이 필드에
# 그대로 실려 20Hz로 이미 발행되고 있었음(147차가 영상 오버레이를
# ffmpeg+육안 OCR로 초 단위로만 읽어야 했던 바로 그 값). route_speed는
# calculate_curvature()+V_CURVE_LOOKUP 순수 곡률값이 아니라 역방향
# 가속도제한 DP(entry margin/time_delay 스케줄링, carrot_man.py
# carrot_navi_route() 후반부)까지 통과한 **최종 값**이라, 148차까지
# recompute_route_curvature_speed()로는 재현이 원천적으로 불가능했던
# 부분(그 함수는 DP 이전 순수 곡률 재현만 함, README 명시)과 149차가
# `replay_route_full_pipeline.py`(148차, nRoadLimitSpeed 미기록으로
# 재현오차 98.7kph/신뢰불가 판정)로 시도했던 전체 파이프라인 수치
# 재현을 대체한다 -- 재현할 필요 없이 실측값을 직접 뽑으면 됨.
# "route=" 뒤 숫자만 정규식으로 파싱해 liveRouteSpeed 컬럼에 채운다.
# 파싱 실패(szPosRoadName에 "route="가 없는 프레임, 예: 132차 조건상
# 아예 계산 자체가 스킵된 경우)면 빈 문자열.
_ROUTE_SPEED_RE = re.compile(r"route=(-?\d+(?:\.\d+)?)")
# 2026-08-30 추가(147차): carrotMan.naviPaths -- carrot_navi_route()가
# 곡률 계산에 실제로 쓰는 로컬(x,y) 리샘플 폴리라인+거리를
# "x1,y1,d1;x2,y2,d2;..." 텍스트로 이미 20Hz 발행 중이었음(carrot_serv.py
# L1170-1172, coords_str). 89차/90차가 "raw navi_points가 로그에 없어
# 직접검증 불가"라며 신규 계측 패치를 제안했었는데, 사실은 새 패치 없이
# 이 필드만 뽑으면 됨 -- ryu 코드는 변경 없음, extract_log.py 쪽 누락이었음.
# 이 필드는 row당 최대 ~600m/10m=60개 점 * 약 15~20자 = 최대 ~1200자로
# 다른 컬럼들보다 훨씬 커서, 기본 추출에는 포함하지 않고
# --with-navi-paths 플래그를 줬을 때만 컬럼에 채워 넣는다(그 외엔 항상
# 빈 문자열) -- 일반 추출 CSV가 불필요하게 커지는 것을 방지.
# analysis_helpers.parse_navi_paths()/recompute_route_curvature_speed()로
# 파싱 및 carrot_man.py와 동일한 곡률/역방향DP 재계산 가능
# (calculate_curvature/V_CURVE_LOOKUP_BP/VALS는 90차 sim_route_curvature_sample.py
# 이식본을 그대로 재사용).
NAVI_PATHS_FIELD = "naviPaths"
# 2026-08-30 추가(146차, 정량검증 후 계속): carrotMan.activeCarrot/
# xTurnInfo/xDistToTurn/xSpdType/xSpdDist/atcType/leftSec/
# xSpdCountDown/xTurnCountDown -- "route 카운트다운/회전(ATC) 사전감속
# 미작동" 조사용. **정량검증 결과 원인은 "xTurnInfo 이중소스 충돌"이
# 아니라 AutoTurnControl=0(off, 기본값)/AutoNaviCountDownMode=0(off)
# 설정값 자체였음이 확정됨** — 최초 가설(코드분석만으로 세움)은 기각,
# FINDINGS.md 146차 계속 항목 참고. xSpdCountDown/xTurnCountDown은
# left_spd_sec/left_tbt_sec 원시 계산값(음성 카운트다운 게이트) 직접
# 확인용으로 재검증 과정에서 추가.
# 주의: carrot_serv.py 내부 변수 self.active_kisa_count(Waze 데이터
# 최근 수신 여부 판정에 쓰임)는 cereal(custom.capnp CarrotMan)에
# 발행되지 않아 CSV로 뽑을 수 없음 -- 이 변수가 필요하면 carrot_serv.py
# 자체에 임시 디버그 필드를 추가하거나 로그의 다른 프록시(atcType에
# " canceled"가 안 붙고 xTurnInfo가 반복적으로 -1로 튀는 패턴 등)로
# 간접 추정해야 함.
# 2026-08-30 추가(145차): modelV2.laneLineProbs[1]/[2] (left/right lane
# line 확신도, lane_planner_2.py parse_model()의 self.lll_prob/rll_prob과
# 동일 인덱스) + laneLineStds[1]/[2]. 145차에서 "AdjustLaneOffset(커브
# 안쪽 자동보정) 메커니즘이 d_prob>0일 때만 부분 반영된다"는 코드분석
# 가설을 실측 검증하려면 활성라인여부(activeLaneLine, 144차 추가)만으론
# 부족 -- lanefull_mode 진입 여부와 무관하게 always-on인 이 게이트값
# 자체가 CSV에 없어 d_prob=max(l_prob,r_prob)*std_mod 근사 계산이
# 불가능했음. get_d_path()의 l_std_mod/r_std_mod까지 정확히 재현하려면
# lllStd/rllStd도 필요해 함께 추가.
# 2026-08-30 추가(144차): controlsState.activeLaneLine
# (controlsd.py line360, `cs.activeLaneLine = self.lanefull_mode_enabled`) --
# 140차 PathOffset 레인리스 반영 패치의 실차검증에 필수. 이 필드 없이는
# desiredCurvature/steeringAngleDeg만으로 "지금 레인풀(차선기반)인지
# 레인리스(모델 직접출력)인지"를 CSV만으로 구분할 수 없어, 오프셋이
# 실제로 반영된 프레임인지 판별 불가능했음. True=레인풀(lanefull_mode_enabled),
# False=레인리스. PathOffset 원시값(Params) 자체는 cereal에 없어 여전히
# CSV로는 못 뽑음 -- 필요시 실차에서 carrot_settings.json/params 스냅샷을
# 별도로 받아야 함.
# 2026-08-25 추가(63차 계속3 이어서): RadarState.LeadData.dPath/yRel/
# aLeadK/radarTrackId -- seg14류 반복 discontinuity(raw dRel이 프레임당
# -230m/s급으로 튀며 closing/opening 반복)가 인접차선 오검출인지 실제
# cut-in(가속 이탈)인지 원인 판별을 dPath/radarTrackId 없이는 못 했음
# (63차 계속3 WIP 최우선 과제). radarTrackId는 트랙 전환(다른 물체로
# 넘어감) 자체를 직접 잡을 수 있어 dPath보다 더 결정적인 신호가 될 수 있음.
# 2026-08-22 추가(46차): modelV2.meta.modelTurnSpeed (carrot_serv.py의
# model_turn_speed 게이팅 후보 그 자체) -- 지금까지 CSV에 없어서
# "model 소스" 관련 분석 때 src=="model" 여부만 보고 실제 model_turn_speed
# 값 자체(200 미만 여부, vturn과의 상대적 크기)는 확인할 수 없었음.
# "곡선 진입전/정점/탈출 감속·가속" 분석을 위해 추가.
# 2026-08-22 추가: 차선변경 발생 여부를 CSV만으로 판별하기 위해
# carState.leftBlinker/rightBlinker(운전자 의도)와
# lateralPlan.laneChangeState/laneChangeDirection(실제 궤적 계획 상태:
# off/preLaneChange/laneChangeStarting/laneChangeFinishing)을 추가.
# dRel 급점프가 "vision 노이즈"인지 "ego 차선변경으로 인한 리드 타겟
# 스왑"인지 구분할 근거 없이는 오판할 수 있음 (FINDINGS.md 42차 재검토
# 계기, B seg10 이벤트에서 사용자가 차선변경 가능성 제기).
# 2026-08-23 추가(47차): carState.vCruiseCluster(controlsd.py line 214
# `min(CS.vCruiseCluster, desiredSpeed)`가 실제로 참조하는 필드) 신규
# 추가 -- 기존 "vCruise" 필드와는 별개의 값인데 이름이 비슷해 혼동
# 유발 가능성 있음. curve_exit_no_accel_scan_v3의 vCruiseCluster 캡
# 여유폭 필터는 반드시 이 필드를 써야 함(vCruise 아님).


def get_repo_git_info(repo_dir):
    """
    repo_dir의 현재 git 상태(commit hash, branch, commit 날짜/메시지, dirty 여부)를
    조회해 dict로 리턴. git 명령이 실패하면(레포 아님 등) 최대한 채워서 리턴하고
    실패한 필드는 None으로 남긴다. 이 값이 있어야 나중에 로그와 코드 상태를
    맞춰볼 수 있으므로, 조용히 넘어가지 않고 stderr에 경고를 남긴다.
    """
    info = {
        "commit": None, "commit_short": None, "branch": None,
        "commit_date": None, "commit_subject": None, "dirty": None,
        "repo_dir": repo_dir,
    }

    def _git(args):
        return subprocess.run(
            ["git", "-C", repo_dir] + args,
            capture_output=True, text=True, timeout=10,
        )

    try:
        r = _git(["rev-parse", "HEAD"])
        if r.returncode == 0:
            info["commit"] = r.stdout.strip()
            info["commit_short"] = info["commit"][:12]

        r = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        if r.returncode == 0:
            info["branch"] = r.stdout.strip()

        r = _git(["log", "-1", "--format=%cI|%s"])
        if r.returncode == 0 and "|" in r.stdout:
            date_part, subj_part = r.stdout.strip().split("|", 1)
            info["commit_date"] = date_part
            info["commit_subject"] = subj_part

        r = _git(["status", "--porcelain"])
        if r.returncode == 0:
            info["dirty"] = bool(r.stdout.strip())
    except (subprocess.SubprocessError, OSError) as e:
        print(f"WARNING: git info 조회 실패 ({repo_dir}): {e}", file=sys.stderr)

    if info["commit"] is None:
        print(
            f"WARNING: {repo_dir}에서 commit hash를 못 읽었습니다. "
            f"CSV의 commit 컬럼이 비게 되어 나중에 코드 상태 추적이 안 됩니다.",
            file=sys.stderr,
        )
    return info


def process_segment(rlog_path, seg_name, repo_dir, max_mb, commit_short="",
                     carry_cs=None, carry_ctrl=None, carry_lead=None, carry_lat=None,
                     carry_model=None, carry_pose=None, with_navi_paths=False):
    """
    carry_cs/carry_ctrl/carry_lead: 이전 세그먼트에서 넘어온 마지막 상태.
    None이면 이 세그먼트가 라우트의 첫 세그먼트라는 뜻으로 기본값 사용.

    2026-08-21 수정: 과거에는 세그먼트마다 last_lead를 무조건
    {"leadStatus": False, ...}로 리셋했음 -> 실제로는 리드가 계속
    잡혀 있었는데도 새 세그먼트 시작 시 첫 radarState 이벤트가 올
    때까지 leadStatus=False인 row가 몇 개 찍히는 구조적 아티팩트가
    발생했음 (세그먼트 경계와 diff=0.000s로 정확히 일치하는 "순간유실"
    다수 발견, FINDINGS.md 22차 참고). 이제 세그먼트 간 상태를 이어받아
    이 문제를 원천 차단한다. 리턴값도 (rows, 최종상태) 튜플로 변경.
    """
    last_cs = dict(carry_cs) if carry_cs is not None else {
        "leftBlinker": "", "rightBlinker": "",
    }
    last_ctrl = dict(carry_ctrl) if carry_ctrl is not None else {
        "desiredCurvature": None, "activeLaneLine": "",
    }
    last_lead = dict(carry_lead) if carry_lead is not None else {
        "leadStatus": False, "leadDRel": "", "leadVRel": "", "leadVLead": "",
        "leadRadar": "", "leadModelProb": "",
        "leadDPath": "", "leadYRel": "", "leadALeadK": "", "leadRadarTrackId": "",
    }
    last_lat = dict(carry_lat) if carry_lat is not None else {
        "laneChangeState": "", "laneChangeDirection": "",
    }
    last_model = dict(carry_model) if carry_model is not None else {
        "modelTurnSpeed": "",
        "lllProb": "", "rllProb": "", "lllStd": "", "rllStd": "",
    }
    last_pose = dict(carry_pose) if carry_pose is not None else {
        "ccYawDeg": "", "ccYawRateZ": "", "ccPoseValid": "",
    }
    rows = []
    for evt in iter_events(rlog_path, repo_dir=repo_dir, max_output_mb=max_mb):
        w = evt.which()
        t = evt.logMonoTime / 1e9
        if w == "carState":
            cs = evt.carState
            last_cs = {
                "vEgo": cs.vEgo, "aEgo": cs.aEgo,
                "brakePressed": cs.brakePressed, "gasPressed": cs.gasPressed,
                "cruiseEnabled": cs.cruiseState.enabled,
                "vCruise": cs.vCruise,
                "vCruiseCluster": cs.vCruiseCluster,
                "steeringAngleDeg": cs.steeringAngleDeg,
                "leftBlinker": cs.leftBlinker, "rightBlinker": cs.rightBlinker,
            }
        elif w == "controlsState":
            cst = evt.controlsState
            last_ctrl = {
                "desiredCurvature": cst.desiredCurvature,
                "activeLaneLine": cst.activeLaneLine,
            }
        elif w == "lateralPlan":
            lp = evt.lateralPlan
            last_lat = {
                "laneChangeState": str(lp.laneChangeState),
                "laneChangeDirection": str(lp.laneChangeDirection),
            }
        elif w == "modelV2":
            mv2 = evt.modelV2
            llp = mv2.laneLineProbs
            lls = mv2.laneLineStds
            last_model = {
                "modelTurnSpeed": mv2.meta.modelTurnSpeed,
                "lllProb": llp[1] if len(llp) > 2 else "",
                "rllProb": llp[2] if len(llp) > 2 else "",
                "lllStd": lls[1] if len(lls) > 2 else "",
                "rllStd": lls[2] if len(lls) > 2 else "",
            }
        elif w == "carControl":
            cc = evt.carControl
            ned = list(cc.orientationNED)
            avl = list(cc.angularVelocity)
            pose_valid = len(ned) > 2 and len(avl) > 2
            last_pose = {
                "ccYawDeg": ((math.degrees(ned[2]) + 360.0) % 360.0) if pose_valid else "",
                "ccYawRateZ": avl[2] if pose_valid else "",
                "ccPoseValid": pose_valid,
            }
        elif w == "radarState":
            lo = evt.radarState.leadOne
            if lo.status:
                # radar=False + status=True 는 "레이더 미확인, 비전(모델)만으로
                # 리드 판정" 상태 -- carrot LeadBlend/long_mpc가 참고하는
                # 것과 동일한 원시 신호. modelProb은 비전 모델의 리드 확신도.
                last_lead = {
                    "leadStatus": True, "leadDRel": lo.dRel, "leadVRel": lo.vRel, "leadVLead": lo.vLeadK,
                    "leadRadar": lo.radar, "leadModelProb": lo.modelProb,
                    "leadDPath": lo.dPath, "leadYRel": lo.yRel, "leadALeadK": lo.aLeadK,
                    "leadRadarTrackId": lo.radarTrackId,
                }
            else:
                last_lead = {"leadStatus": False, "leadDRel": "", "leadVRel": "", "leadVLead": "",
                             "leadRadar": "", "leadModelProb": "",
                             "leadDPath": "", "leadYRel": "", "leadALeadK": "", "leadRadarTrackId": ""}
        elif w == "carrotMan":
            cm = evt.carrotMan
            m = _ROUTE_SPEED_RE.search(str(cm.szPosRoadName))
            live_route_speed = m.group(1) if m else ""
            rows.append({
                "t": t, "seg": seg_name, "commit": commit_short,
                **last_cs, **last_ctrl, **last_lead, **last_lat, **last_model, **last_pose,
                "src": str(cm.desiredSource), "desiredSpeed": cm.desiredSpeed, "vTurnSpeed": cm.vTurnSpeed,
                "activeCarrot": cm.activeCarrot, "xTurnInfo": cm.xTurnInfo,
                "xDistToTurn": cm.xDistToTurn, "xSpdType": cm.xSpdType,
                "xSpdDist": cm.xSpdDist, "atcType": str(cm.atcType),
                "leftSec": cm.leftSec,
                "xSpdCountDown": cm.xSpdCountDown, "xTurnCountDown": cm.xTurnCountDown,
                "naviPaths": str(cm.naviPaths) if with_navi_paths else "",
                "liveRouteSpeed": live_route_speed,
                "vpPosPointLatNavi": cm.vpPosPointLatNavi,
                "vpPosPointLonNavi": cm.vpPosPointLonNavi,
                "dtNaviPacketAge": cm.dtNaviPacketAge,
                "positionDtSinceFix": cm.positionDtSinceFix,
                "naviPointsActive": cm.naviPointsActive,
                "navdActive": cm.navdActive,
                "dtRouteInactive": cm.dtRouteInactive,
                "routeSource": str(cm.routeSource),
                "routeApexIdx": cm.routeApexIdx,
                "routeApexDist": cm.routeApexDist,
                "routeApexSpeed": cm.routeApexSpeed,
                "routeOutSpeed": cm.routeOutSpeed,
            })
    return rows, last_cs, last_ctrl, last_lead, last_lat, last_model, last_pose


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_dir")
    ap.add_argument("out_csv")
    ap.add_argument("--repo", default="/home/claude/ryu")
    ap.add_argument("--max-mb", type=int, default=400)
    ap.add_argument("--with-navi-paths", action="store_true",
                     help="147차: carrotMan.naviPaths(로컬 리샘플 폴리라인+거리 텍스트, "
                          "route 곡률 검증용) 컬럼을 채운다. row당 최대 ~1200자로 "
                          "CSV가 크게 불어나므로 기본은 off -- route 커브 구간 조사 시에만 사용.")
    args = ap.parse_args()

    git_info = get_repo_git_info(args.repo)
    if git_info["commit_short"]:
        print(f"repo commit: {git_info['commit_short']} ({git_info['branch']}) "
              f"dirty={git_info['dirty']}")

    # 147차 버그 수정: process_segment()가 만드는 row dict는 플래그와
    # 무관하게 항상 "naviPaths" 키를 갖는다(플래그 off일 땐 값만 빈
    # 문자열). 이 키가 FIELDNAMES에 없으면 DictWriter(extrasaction 기본
    # "raise")가 플래그 사용 여부와 상관없이 "dict contains fields not
    # in fieldnames" ValueError로 항상 크래시한다 -- 그래서 조건부가
    # 아니라 항상 FIELDNAMES에 포함시켜야 한다(컬럼 자체는 항상 존재,
    # 값만 플래그에 따라 빈 문자열 or 실제 폴리라인).
    fieldnames = FIELDNAMES + [NAVI_PATHS_FIELD]

    seg_dirs = sorted(
        d for d in os.listdir(args.route_dir)
        if os.path.isdir(os.path.join(args.route_dir, d))
        and os.path.exists(os.path.join(args.route_dir, d, "rlog.zst"))
    )
    if not seg_dirs:
        print(f"no segment dirs with rlog.zst found under {args.route_dir}", file=sys.stderr)
        sys.exit(1)

    all_rows = []
    carry_cs, carry_ctrl, carry_lead, carry_lat, carry_model, carry_pose = None, None, None, None, None, None
    for seg in seg_dirs:
        rlog_path = os.path.join(args.route_dir, seg, "rlog.zst")
        rows, carry_cs, carry_ctrl, carry_lead, carry_lat, carry_model, carry_pose = process_segment(
            rlog_path, seg, args.repo, args.max_mb,
            commit_short=git_info["commit_short"] or "",
            carry_cs=carry_cs, carry_ctrl=carry_ctrl, carry_lead=carry_lead, carry_lat=carry_lat,
            carry_model=carry_model, carry_pose=carry_pose, with_navi_paths=args.with_navi_paths,
        )
        all_rows.extend(rows)
        print(f"done {seg}: {len(rows)} rows ({len(all_rows)} total)")

    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        w.writeheader()
        w.writerows(all_rows)
    print(f"Wrote {len(all_rows)} rows to {args.out_csv}")

    meta = {
        **git_info,
        "route_dir": os.path.abspath(args.route_dir),
        "out_csv": os.path.abspath(args.out_csv),
        "n_segments": len(seg_dirs),
        "n_rows": len(all_rows),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "segment_state_carryover_fix": True,
    }
    meta_path = args.out_csv + ".meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Wrote metadata to {meta_path}")


if __name__ == "__main__":
    main()
