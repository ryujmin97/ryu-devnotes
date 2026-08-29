#!/usr/bin/env python3
"""
rlog.zst에서 radarState 메시지의 leadOne / leadsCutIn / leadsLeft / leadsRight
리스트를 시간별로 그대로 뽑는다 (radard.py compute_leads()가 실제로 산출한
최종 리스트 자체를 관찰 -- 게이트/hysteresis를 재구현하지 않고 코드가 그
순간 실제로 무엇을 "왼쪽/오른쪽/컷인 후보"로 봤는지 원본 그대로 확인).

배경: extract_log.py는 최종 선택된 leadOne(leadDPath/leadYRel 등)만 CSV로
뽑는다. 그러나 "인접 차선에서 끼어드는 차량이 실제로 cutin_list/left_list/
right_list에 언제부터 후보로 잡혔는지, in_lane_prob_future 게이트를
언제 통과했는지"를 보려면 leadsCutIn/leadsLeft/leadsRight 원본 리스트가
필요함 -- 125차, 컷인_이거는_차선_폭을_넓게(133212) 정밀분석 계기로 작성.

핵심 설계: radard.py의 in_lane_prob/cut_in_count/lane_line_available
게이트 로직을 별도로 재구현하지 않는다. leadsCutIn/leadsLeft/leadsRight는
이미 실제 코드가 그 게이트들을 전부 통과시킨 뒤 publish한 최종 결과이므로,
그대로 읽기만 하면 "코드가 실제로 그 순간 뭘 봤는지"를 리터럴하게 알 수 있음
(재구현 시 발생할 수 있는 로직 drift 위험 자체가 없음).

입력: route_dir(세그먼트 폴더들의 상위 폴더, 각 폴더에 rlog.zst 포함)
      또는 단일 세그먼트 폴더(rlog.zst 직접 포함) 둘 다 지원.
출력: stdout에 시간창 내 이벤트를 사람이 읽기 좋은 표로 출력.
      --json 지정 시 <out.jsonl>에 전체 라우트 프레임을 한 줄씩 JSON으로 저장
      (leadOne dict + leadsCutIn/leadsLeft/leadsRight 리스트 전체 보존,
      후속 스크립트에서 재사용 가능).

사용:
    python3 extract_cutin_lists.py <route_dir_or_seg_dir> \
        --repo /home/claude/ryu --t-lo 294 --t-hi 300
    # 전체 라우트를 JSONL로 저장(후속 분석용):
    python3 extract_cutin_lists.py <route_dir> --repo /home/claude/ryu \
        --json /home/claude/work/cutin_lists.jsonl
"""
import argparse
import json
import os
import sys

from decode_rlog import iter_events


def _lead_to_dict(ld):
    """LeadData capnp reader -> plain dict (status=False면 나머지 필드는 의미 없음)."""
    return {
        "status": bool(ld.status),
        "dRel": float(ld.dRel),
        "yRel": float(ld.yRel),
        "dPath": float(ld.dPath),
        "vRel": float(ld.vRel),
        "vLead": float(ld.vLead),
        "vLeadK": float(ld.vLeadK),
        "aLeadK": float(ld.aLeadK),
        "modelProb": float(ld.modelProb),
        "radar": bool(ld.radar),
        "radarTrackId": int(ld.radarTrackId),
    }


def discover_segments(path):
    """path가 세그먼트 하나(rlog.zst 직접 포함)면 [path], route_dir(여러
    세그먼트 하위폴더)면 이름순 정렬된 세그먼트 폴더 리스트를 리턴."""
    if os.path.exists(os.path.join(path, "rlog.zst")):
        return [path]
    segs = []
    for d in sorted(os.listdir(path)):
        full = os.path.join(path, d)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, "rlog.zst")):
            segs.append(full)
    return segs


def process_route(path, repo_dir, max_mb=400):
    """제너레이터: 라우트 전체를 순회하며 프레임별 dict를 yield.

    각 프레임(dict)은 radarState 이벤트(있으면) + 가장 최근 modelV2의
    laneLineProbs[1]/[2](lane_line_available 근사 확인용, 참고용 -- 실제
    게이트는 radard.py 내부에서 이미 적용된 뒤라 이 값은 "왜 그런
    판정이 나왔는지" 설명 보조용일 뿐 재현에 쓰이지 않음)를 담는다.
    carState.vEgo/brakePressed도 참고용으로 같이 캐리한다.
    """
    segs = discover_segments(path)
    if not segs:
        raise FileNotFoundError(f"세그먼트를 찾을 수 없음: {path}")

    last_lane_probs = (None, None)
    last_v_ego = None
    last_brake = None

    for seg_dir in segs:
        seg_name = os.path.basename(seg_dir.rstrip("/"))
        rlog_path = os.path.join(seg_dir, "rlog.zst")
        for evt in iter_events(rlog_path, repo_dir=repo_dir, max_output_mb=max_mb):
            w = evt.which()
            t = evt.logMonoTime / 1e9
            if w == "carState":
                cs = evt.carState
                last_v_ego = float(cs.vEgo)
                last_brake = bool(cs.brakePressed)
            elif w == "modelV2":
                probs = evt.modelV2.laneLineProbs
                if len(probs) >= 3:
                    last_lane_probs = (float(probs[1]), float(probs[2]))
            elif w == "radarState":
                rs = evt.radarState
                yield {
                    "t": t,
                    "seg": seg_name,
                    "vEgo": last_v_ego,
                    "brakePressed": last_brake,
                    "laneLineProb_left": last_lane_probs[0],
                    "laneLineProb_right": last_lane_probs[1],
                    "leadOne": _lead_to_dict(rs.leadOne),
                    "leadsCutIn": [_lead_to_dict(ld) for ld in rs.leadsCutIn],
                    "leadsLeft": [_lead_to_dict(ld) for ld in rs.leadsLeft],
                    "leadsRight": [_lead_to_dict(ld) for ld in rs.leadsRight],
                }


def _fmt_lead(ld):
    if not ld["status"]:
        return "status=False"
    return (f"dRel={ld['dRel']:.2f} dPath={ld['dPath']:.2f} yRel={ld['yRel']:.2f} "
            f"vRel={ld['vRel']:.2f} vLead={ld['vLead']:.2f} radar={ld['radar']} "
            f"trackId={ld['radarTrackId']} prob={ld['modelProb']:.2f}")


def print_window(path, repo_dir, t_lo=None, t_hi=None, max_mb=400):
    n_printed = 0
    for fr in process_route(path, repo_dir, max_mb=max_mb):
        if t_lo is not None and fr["t"] < t_lo:
            continue
        if t_hi is not None and fr["t"] > t_hi:
            break
        n_printed += 1
        cutin_str = "; ".join(_fmt_lead(ld) for ld in fr["leadsCutIn"]) or "(없음)"
        left_str = "; ".join(_fmt_lead(ld) for ld in fr["leadsLeft"][:3]) or "(없음)"
        right_str = "; ".join(_fmt_lead(ld) for ld in fr["leadsRight"][:3]) or "(없음)"
        print(f"t={fr['t']:.3f} seg={fr['seg']} vEgo={fr['vEgo']:.2f} "
              f"brake={fr['brakePressed']} laneProbs=({fr['laneLineProb_left']},{fr['laneLineProb_right']})")
        print(f"  leadOne : {_fmt_lead(fr['leadOne'])}")
        print(f"  cutIn(n={len(fr['leadsCutIn'])}) : {cutin_str}")
        print(f"  left(n={len(fr['leadsLeft'])})   : {left_str}")
        print(f"  right(n={len(fr['leadsRight'])}) : {right_str}")
    if n_printed == 0:
        print("(해당 시간창에 radarState 이벤트 없음 -- t 범위/세그먼트 확인)", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_or_seg_dir")
    ap.add_argument("--repo", default="/home/claude/ryu")
    ap.add_argument("--max-mb", type=int, default=400)
    ap.add_argument("--t-lo", type=float, default=None)
    ap.add_argument("--t-hi", type=float, default=None)
    ap.add_argument("--json", default=None, help="지정 시 전체 라우트를 JSONL로 저장")
    args = ap.parse_args()

    if args.json:
        n = 0
        with open(args.json, "w") as f:
            for fr in process_route(args.route_or_seg_dir, args.repo, max_mb=args.max_mb):
                f.write(json.dumps(fr) + "\n")
                n += 1
        print(f"{n} rows -> {args.json}")
    else:
        print_window(args.route_or_seg_dir, args.repo, args.t_lo, args.t_hi, args.max_mb)


if __name__ == "__main__":
    main()
