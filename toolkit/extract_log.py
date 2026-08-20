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
]


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


def process_segment(rlog_path, seg_name, repo_dir, max_mb, commit_short=""):
    last_cs = {}
    last_ctrl = {"desiredCurvature": None}
    last_lead = {"leadStatus": False, "leadDRel": "", "leadVRel": "", "leadVLead": "",
                 "leadRadar": "", "leadModelProb": ""}
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
            }
        elif w == "controlsState":
            last_ctrl = {"desiredCurvature": evt.controlsState.desiredCurvature}
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
                **last_cs, **last_ctrl, **last_lead,
                "src": str(cm.desiredSource), "desiredSpeed": cm.desiredSpeed, "vTurnSpeed": cm.vTurnSpeed,
            })
    return rows


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
    for seg in seg_dirs:
        rlog_path = os.path.join(args.route_dir, seg, "rlog.zst")
        rows = process_segment(rlog_path, seg, args.repo, args.max_mb,
                                commit_short=git_info["commit_short"] or "")
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
    }
    meta_path = args.out_csv + ".meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Wrote metadata to {meta_path}")


if __name__ == "__main__":
    main()
