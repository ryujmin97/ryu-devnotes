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
    vEgo, aEgo, brakePressed, gasPressed, cruiseEnabled, vCruise,
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
import os
import subprocess
import sys
from datetime import datetime, timezone

from decode_rlog import iter_events

FIELDNAMES = [
    "t", "seg", "commit",
    "vEgo", "aEgo", "brakePressed", "gasPressed", "cruiseEnabled", "vCruise",
    "steeringAngleDeg", "desiredCurvature",
    "leadStatus", "leadDRel", "leadVRel", "leadVLead",
    "leadRadar", "leadModelProb",
    "src", "desiredSpeed", "vTurnSpeed",
    "leftBlinker", "rightBlinker",
    "laneChangeState", "laneChangeDirection",
]
# 2026-08-22 추가: 차선변경 발생 여부를 CSV만으로 판별하기 위해
# carState.leftBlinker/rightBlinker(운전자 의도)와
# lateralPlan.laneChangeState/laneChangeDirection(실제 궤적 계획 상태:
# off/preLaneChange/laneChangeStarting/laneChangeFinishing)을 추가.
# dRel 급점프가 "vision 노이즈"인지 "ego 차선변경으로 인한 리드 타겟
# 스왑"인지 구분할 근거 없이는 오판할 수 있음 (FINDINGS.md 42차 재검토
# 계기, B seg10 이벤트에서 사용자가 차선변경 가능성 제기).


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
                     carry_cs=None, carry_ctrl=None, carry_lead=None, carry_lat=None):
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
    last_ctrl = dict(carry_ctrl) if carry_ctrl is not None else {"desiredCurvature": None}
    last_lead = dict(carry_lead) if carry_lead is not None else {
        "leadStatus": False, "leadDRel": "", "leadVRel": "", "leadVLead": "",
        "leadRadar": "", "leadModelProb": "",
    }
    last_lat = dict(carry_lat) if carry_lat is not None else {
        "laneChangeState": "", "laneChangeDirection": "",
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
                "steeringAngleDeg": cs.steeringAngleDeg,
                "leftBlinker": cs.leftBlinker, "rightBlinker": cs.rightBlinker,
            }
        elif w == "controlsState":
            last_ctrl = {"desiredCurvature": evt.controlsState.desiredCurvature}
        elif w == "lateralPlan":
            lp = evt.lateralPlan
            last_lat = {
                "laneChangeState": str(lp.laneChangeState),
                "laneChangeDirection": str(lp.laneChangeDirection),
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
                }
            else:
                last_lead = {"leadStatus": False, "leadDRel": "", "leadVRel": "", "leadVLead": "",
                             "leadRadar": "", "leadModelProb": ""}
        elif w == "carrotMan":
            cm = evt.carrotMan
            rows.append({
                "t": t, "seg": seg_name, "commit": commit_short,
                **last_cs, **last_ctrl, **last_lead, **last_lat,
                "src": str(cm.desiredSource), "desiredSpeed": cm.desiredSpeed, "vTurnSpeed": cm.vTurnSpeed,
            })
    return rows, last_cs, last_ctrl, last_lead, last_lat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_dir")
    ap.add_argument("out_csv")
    ap.add_argument("--repo", default="/home/claude/ryu")
    ap.add_argument("--max-mb", type=int, default=400)
    args = ap.parse_args()

    git_info = get_repo_git_info(args.repo)
    if git_info["commit_short"]:
        print(f"repo commit: {git_info['commit_short']} ({git_info['branch']}) "
              f"dirty={git_info['dirty']}")

    seg_dirs = sorted(
        d for d in os.listdir(args.route_dir)
        if os.path.isdir(os.path.join(args.route_dir, d))
        and os.path.exists(os.path.join(args.route_dir, d, "rlog.zst"))
    )
    if not seg_dirs:
        print(f"no segment dirs with rlog.zst found under {args.route_dir}", file=sys.stderr)
        sys.exit(1)

    all_rows = []
    carry_cs, carry_ctrl, carry_lead, carry_lat = None, None, None, None
    for seg in seg_dirs:
        rlog_path = os.path.join(args.route_dir, seg, "rlog.zst")
        rows, carry_cs, carry_ctrl, carry_lead, carry_lat = process_segment(
            rlog_path, seg, args.repo, args.max_mb,
            commit_short=git_info["commit_short"] or "",
            carry_cs=carry_cs, carry_ctrl=carry_ctrl, carry_lead=carry_lead, carry_lat=carry_lat,
        )
        all_rows.extend(rows)
        print(f"done {seg}: {len(rows)} rows ({len(all_rows)} total)")

    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, restval="")
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
