#!/usr/bin/env python3
"""
로그 타임스탬프(t, extract_log.py CSV의 't'와 동일 축)를 라우트 내
세그먼트들과 대조해 "이 t가 실제로 어느 세그먼트의 유효 시간 범위 안에
있는지"부터 검증한 뒤, 맞는 세그먼트에서 qcamera 프레임을 자동으로
추출한다.

왜 필요한가 (extract_dashcam_frames.py와의 차이):
- extract_dashcam_frames.py는 세그먼트 폴더 하나를 직접 지정받는다 --
  즉 "이 t가 어느 세그먼트 것인지"는 사용자/호출자가 미리 알아야 한다
  (지금까지는 route.csv를 읽고 seg 컬럼으로 시간 범위를 수동 대조하는
  식으로 매번 처리했음, 42차 세션 참고).
- 이 스크립트는 route_dir(여러 세그먼트) 전체를 스캔해 각 세그먼트의
  실제 유효 시간 범위(qRoadEncodeIdx 이벤트 t의 min/max)를 자동으로
  구축하고, target time마다 올바른 세그먼트를 자동 매칭한다.
- 세그먼트 경계를 벗어난 t(세그먼트 사이 gap에 들어가거나 range 밖)나
  매칭 오차가 큰 프레임은 조용히 넘어가지 않고 OUT_OF_RANGE/WARN으로
  명시적으로 리포트한다 -- "틀린 프레임으로 결론 내리는" 실수 방지가
  핵심 목적.

전제: extract_dashcam_frames.py와 동일 (각 세그먼트 폴더에 qcamera.ts +
rlog.zst/qlog.zst, ryu 레포 clone).

CLI 사용 예:
    python3 verify_and_extract_frames.py \\
        /home/claude/work/routeB \\
        --repo /home/claude/ryu \\
        --times 1895.6,1896.2,1896.5,1896.85,1897.6 \\
        --out-dir /home/claude/work/frames/eventB_seg10_auto \\
        --context 1

    출력:
    - <out-dir>/manifest.json: extract_dashcam_frames.py와 동일 포맷 +
      "segment"(자동 매칭된 세그먼트명) 필드 추가
    - <out-dir>/verify_report.json: target별 검증 결과(status/segment/
      matched_t/diff_s)
    - stdout에 사람이 읽기 쉬운 요약 표 출력

파이썬에서 직접 쓰는 예:
    from verify_and_extract_frames import verify_and_extract
    report, manifest = verify_and_extract(
        "/home/claude/work/routeB", "/home/claude/ryu",
        [1895.6, 1896.85], "/home/claude/work/frames/out",
    )
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_dashcam_frames import (  # noqa: E402
    find_segment_files,
    build_frame_time_index,
    nearest_frame_for_time,
    extract_frame,
)

STATUS_OK = "OK"
STATUS_WARN = "WARN_LARGE_DIFF"
STATUS_OUT_OF_RANGE = "OUT_OF_RANGE"
STATUS_NO_INDEX = "NO_ENCODE_INDEX"


def discover_segments(route_dir):
    """route_dir 아래에서 qcamera.ts + (rlog.zst 또는 qlog.zst)가 둘 다 있는
    세그먼트 폴더를 이름순(=extract_log.py와 동일한 정렬 기준, 폴더명이
    타임스탬프 접두라 이름순=시간순)으로 리턴."""
    segs = []
    for d in sorted(os.listdir(route_dir)):
        seg_dir = os.path.join(route_dir, d)
        if not os.path.isdir(seg_dir):
            continue
        has_cam = os.path.exists(os.path.join(seg_dir, "qcamera.ts"))
        has_log = os.path.exists(os.path.join(seg_dir, "rlog.zst")) or os.path.exists(
            os.path.join(seg_dir, "qlog.zst")
        )
        if has_cam and has_log:
            segs.append(seg_dir)
    return segs


def build_route_time_index(route_dir, repo_dir):
    """route_dir의 모든 세그먼트에 대해 build_frame_time_index()를 호출,
    세그먼트별 (t_min, t_max, index)를 리턴한다.
    리턴: [{"segment_dir", "segment_name", "t_min", "t_max", "index"}, ...]
    (segment_dir 이름순 정렬 유지, t_min 기준이 아님 -- 폴더명 순서를
    신뢰, 로그가 밀린 경우를 대비해 세그먼트 자체 정렬은 건드리지 않음)
    """
    route_index = []
    for seg_dir in discover_segments(route_dir):
        _, log_path = find_segment_files(seg_dir)
        idx = build_frame_time_index(log_path, repo_dir)
        if not idx:
            route_index.append({
                "segment_dir": seg_dir,
                "segment_name": os.path.basename(seg_dir),
                "t_min": None,
                "t_max": None,
                "index": [],
            })
            continue
        route_index.append({
            "segment_dir": seg_dir,
            "segment_name": os.path.basename(seg_dir),
            "t_min": idx[0]["t"],
            "t_max": idx[-1]["t"],
            "index": idx,
        })
    return route_index


def resolve_segment_for_time(route_index, target_t):
    """target_t를 포함하는 세그먼트를 찾는다.
    리턴: (seg_entry_or_None, status)
    - 범위 안에 드는 세그먼트가 있으면 (그 entry, "IN_RANGE")
    - 없으면, t_min/t_max가 있는 세그먼트 중 가장 가까운 것을
      (entry, "NEAREST_OUT_OF_RANGE")로 리턴 (참고용 -- 호출자가
      warn_diff_s로 최종 OK/WARN/OUT_OF_RANGE 판정)
    - 유효 세그먼트가 하나도 없으면 (None, "NO_SEGMENTS")
    """
    valid = [s for s in route_index if s["t_min"] is not None]
    if not valid:
        return None, "NO_SEGMENTS"

    for s in valid:
        if s["t_min"] <= target_t <= s["t_max"]:
            return s, "IN_RANGE"

    def dist(s):
        if target_t < s["t_min"]:
            return s["t_min"] - target_t
        return target_t - s["t_max"]

    nearest = min(valid, key=dist)
    return nearest, "NEAREST_OUT_OF_RANGE"


def verify_and_extract(route_dir, repo_dir, target_times, out_dir,
                        context=0, warn_diff_s=0.15, out_of_range_gap_s=2.0,
                        label_prefix=""):
    """
    핵심 함수. route_dir 전체를 스캔해 target_times 각각을 올바른
    세그먼트에 자동 매칭하고 프레임을 추출한다.

    out_of_range_gap_s: target_t가 가장 가까운 세그먼트의 범위 밖이더라도
    이 값(기본 2.0s) 이내면 "세그먼트 경계 바로 바깥" 정도로 보고
    NEAREST_OUT_OF_RANGE 세그먼트에서 그대로 추출 시도(경고만 남김).
    이 값을 넘으면 아예 OUT_OF_RANGE로 판정해 추출을 건너뛴다 --
    엉뚱한 세그먼트의 아무 프레임이나 뽑아 잘못된 결론으로 이어지는
    것을 막기 위함.

    리턴: (report: list[dict], manifest: list[dict])
    report 각 항목: {target_t, status, segment, matched_t, diff_s}
    manifest는 extract_dashcam_frames.extract_frames_for_times()와
    동일 포맷 + "segment" 필드.
    """
    os.makedirs(out_dir, exist_ok=True)
    route_index = build_route_time_index(route_dir, repo_dir)

    report = []
    manifest = []

    for target_t in target_times:
        seg_entry, resolve_status = resolve_segment_for_time(route_index, target_t)

        if resolve_status == "NO_SEGMENTS":
            report.append({
                "target_t": target_t, "status": STATUS_NO_INDEX,
                "segment": None, "matched_t": None, "diff_s": None,
            })
            print(f"WARNING: t={target_t} — route_dir 전체에 유효한 "
                  f"qRoadEncodeIdx 인덱스가 있는 세그먼트가 하나도 없음",
                  file=sys.stderr)
            continue

        if resolve_status == "NEAREST_OUT_OF_RANGE":
            gap = (seg_entry["t_min"] - target_t if target_t < seg_entry["t_min"]
                   else target_t - seg_entry["t_max"])
            if gap > out_of_range_gap_s:
                report.append({
                    "target_t": target_t, "status": STATUS_OUT_OF_RANGE,
                    "segment": seg_entry["segment_name"], "matched_t": None,
                    "diff_s": gap,
                })
                print(f"WARNING: t={target_t} — 가장 가까운 세그먼트"
                      f"({seg_entry['segment_name']})의 유효범위"
                      f"[{seg_entry['t_min']:.2f},{seg_entry['t_max']:.2f}]"
                      f"에서 {gap:.2f}s 벗어남(허용 {out_of_range_gap_s}s) — "
                      f"이 라우트에 해당 시각 로그 자체가 없는 것으로 보임, "
                      f"추출 건너뜀", file=sys.stderr)
                continue
            print(f"WARNING: t={target_t} — 세그먼트 {seg_entry['segment_name']} "
                  f"범위 바로 바깥({gap:.2f}s 초과), 경계 인접으로 보고 추출 시도",
                  file=sys.stderr)

        entry, diff = nearest_frame_for_time(seg_entry["index"], target_t)
        status = STATUS_OK if diff <= warn_diff_s else STATUS_WARN
        if status == STATUS_WARN:
            print(f"WARNING: t={target_t} — 매칭 오차 {diff:.3f}s > "
                  f"{warn_diff_s}s (세그먼트 {seg_entry['segment_name']})",
                  file=sys.stderr)

        report.append({
            "target_t": target_t, "status": status,
            "segment": seg_entry["segment_name"],
            "matched_t": entry["t"], "diff_s": diff,
        })

        qcam, _ = find_segment_files(seg_entry["segment_dir"])
        center_seg_id = entry["segmentId"]
        for off in range(-context, context + 1):
            seg_id = center_seg_id + off
            if seg_id < 0:
                continue
            fname = f"{label_prefix}t{target_t:.2f}_off{off:+d}_seg{seg_id}.jpg"
            out_path = os.path.join(out_dir, fname)
            try:
                extract_frame(qcam, seg_id, out_path)
            except RuntimeError as e:
                print(f"WARNING: {e}", file=sys.stderr)
                continue
            manifest.append({
                "target_t": target_t,
                "offset": off,
                "segment": seg_entry["segment_name"],
                "segmentId": seg_id,
                "matched_t": entry["t"] if off == 0 else None,
                "time_diff_s": diff if off == 0 else None,
                "frameId": entry["frameId"] if off == 0 else None,
                "file": out_path,
            })

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "verify_report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n=== 타임스탬프 검증 결과 ===")
    print(f"{'target_t':>12} {'status':<22} {'segment':<45} {'matched_t':>12} {'diff_s':>8}")
    for r in report:
        seg = r["segment"] or "-"
        mt = f"{r['matched_t']:.3f}" if r["matched_t"] is not None else "-"
        df = f"{r['diff_s']:.3f}" if r["diff_s"] is not None else "-"
        print(f"{r['target_t']:>12.3f} {r['status']:<22} {seg:<45} {mt:>12} {df:>8}")
    ok_n = sum(1 for r in report if r["status"] == STATUS_OK)
    print(f"\n{ok_n}/{len(report)} OK, {len(manifest)}개 프레임 추출 완료 -> {out_dir}")

    return report, manifest


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("route_dir", help="세그먼트 폴더 여러 개를 담은 라우트 상위 폴더")
    ap.add_argument("--repo", default="/home/claude/ryu")
    ap.add_argument(
        "--times", required=True, help="쉼표구분 타겟 시각들 (초, CSV 't'축과 동일)"
    )
    ap.add_argument("--out-dir", required=True)
    ap.add_argument(
        "--context", type=int, default=0, help="타겟 프레임 앞뒤로 몇 장씩 더 뽑을지"
    )
    ap.add_argument(
        "--warn-diff-s", type=float, default=0.15,
        help="매칭 오차 경고 임계값(초). 기본 0.15s (~qcamera 3프레임)",
    )
    ap.add_argument(
        "--out-of-range-gap-s", type=float, default=2.0,
        help="가장 가까운 세그먼트 범위에서 이만큼(초) 이상 벗어나면 "
             "OUT_OF_RANGE로 판정하고 추출을 건너뜀 (기본 2.0s)",
    )
    ap.add_argument("--label-prefix", default="")
    args = ap.parse_args()

    target_times = [float(x) for x in args.times.split(",")]
    report, manifest = verify_and_extract(
        args.route_dir, args.repo, target_times, args.out_dir,
        context=args.context, warn_diff_s=args.warn_diff_s,
        out_of_range_gap_s=args.out_of_range_gap_s,
        label_prefix=args.label_prefix,
    )
    if any(r["status"] in (STATUS_OUT_OF_RANGE, STATUS_NO_INDEX) for r in report):
        sys.exit(1)


if __name__ == "__main__":
    main()
