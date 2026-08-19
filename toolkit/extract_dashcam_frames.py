#!/usr/bin/env python3
"""
qcamera.ts(대시캠) 프레임을 rlog의 qRoadEncodeIdx 이벤트와 동기화해 추출한다.
"정차열 리드 대체 가설" 등, dRel 이벤트 시각(t)에 실제로 화면에 뭐가 찍혀
있었는지 확인할 때 쓴다.

핵심 아이디어:
- cereal/log.capnp의 EncodeIndex(qRoadEncodeIdx 필드)는 프레임마다
  {frameId, segmentId(세그먼트 내 camera 파일 안 presentation-order 인덱스),
  segmentNum, timestampSof/Eof}를 실어 나른다.
- 이 이벤트의 logMonoTime(evt.logMonoTime/1e9)은 extract_log.py가 CSV 't'
  컬럼에 쓰는 것과 완전히 같은 시간축이다. 따라서 FINDINGS.md에 적힌
  유실/재포착 타임스탬프(t)를 이 인덱스로 바로 찾을 수 있다.
- segmentId를 ffmpeg select=eq(n\\,segmentId) 필터에 넘기면 해당 프레임을
  정확히 뽑아낼 수 있다. 단순히 (t - seg시작) * fps로 계산하는 것보다
  안전하다 (프레임 드롭이 있어도 segmentId가 파일 내 실제 위치를 그대로
  반영하기 때문).

전제:
- segment_dir에 qcamera.ts + rlog.zst (없으면 qlog.zst, 커버리지 낮음
  경고 후 사용)가 있어야 한다.
- ryu 레포가 clone되어 있어야 한다 (cereal/log.capnp 스키마 로드용).

CLI 사용 예:
    python3 extract_dashcam_frames.py \\
        /home/claude/work/route/<세그먼트폴더> \\
        --repo /home/claude/ryu \\
        --times 205.53,207.99,208.69,210.48 \\
        --out-dir /home/claude/work/frames \\
        --context 2

    각 target time마다: 가장 가까운 프레임 1장 + 전후 --context장씩 추출하고
    <out-dir>/manifest.json에 (target_t, matched_t, time_diff_s, segmentId,
    file) 기록을 남긴다.

파이썬에서 직접 쓰는 예 (event 쌍 비교, 라벨 붙여서 나란히 합성):
    from extract_dashcam_frames import extract_frames_for_times, make_side_by_side
    manifest = extract_frames_for_times(seg_dir, repo, [205.53, 207.99], out_dir)
    make_side_by_side(
        [manifest[0]["file"], manifest[1]["file"]],
        ["t=205.53 (유실 직전, dRel=46.4m)", "t=207.99 (재포착, dRel=38.8m)"],
        out_dir + "/compare_seg2_event1.jpg",
    )
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_rlog import iter_events  # noqa: E402

QCAMERA_FIELD = "qRoadEncodeIdx"


def find_segment_files(segment_dir):
    """segment_dir 안에서 qcamera.ts와 로그 파일(rlog.zst 우선, 없으면 qlog.zst)을 찾는다."""
    qcam = os.path.join(segment_dir, "qcamera.ts")
    if not os.path.exists(qcam):
        raise FileNotFoundError(f"qcamera.ts not found in {segment_dir}")

    rlog = os.path.join(segment_dir, "rlog.zst")
    qlog = os.path.join(segment_dir, "qlog.zst")
    if os.path.exists(rlog):
        log_path = rlog
    elif os.path.exists(qlog):
        log_path = qlog
        print(
            f"WARNING: rlog.zst 없음, qlog.zst로 대체함 (qRoadEncodeIdx 커버리지가 "
            f"더 낮을 수 있어 매칭 오차가 커질 수 있음): {qlog}",
            file=sys.stderr,
        )
    else:
        raise FileNotFoundError(f"rlog.zst / qlog.zst 둘 다 없음: {segment_dir}")
    return qcam, log_path


def build_frame_time_index(log_path, repo_dir, encode_field=QCAMERA_FIELD):
    """
    log 파일을 순회하며 encode_field(기본 qRoadEncodeIdx) 이벤트를 모아
    [{"t", "frameId", "segmentId", "segmentNum"}, ...] (t 기준 정렬)로 리턴.
    t는 extract_log.py CSV의 't'와 동일 시간축(logMonoTime/1e9).
    """
    entries = []
    for evt in iter_events(log_path, repo_dir=repo_dir):
        if evt.which() != encode_field:
            continue
        idx = getattr(evt, encode_field)
        entries.append({
            "t": evt.logMonoTime / 1e9,
            "frameId": idx.frameId,
            "segmentId": idx.segmentId,
            "segmentNum": idx.segmentNum,
        })
    entries.sort(key=lambda e: e["t"])
    if not entries:
        print(
            f"WARNING: {log_path}에서 {encode_field} 이벤트를 하나도 못 찾음 "
            f"(로그에 인코드 인덱스가 없거나 필드명이 다를 수 있음)",
            file=sys.stderr,
        )
    return entries


def nearest_frame_for_time(index, target_t):
    """index(build_frame_time_index 결과)에서 target_t에 가장 가까운 엔트리를 리턴.
    (entry, abs_diff_seconds) 튜플. index가 비어있으면 (None, None)."""
    if not index:
        return None, None
    best = min(index, key=lambda e: abs(e["t"] - target_t))
    return best, abs(best["t"] - target_t)


def extract_frame(qcamera_path, frame_number, out_path):
    """
    ffmpeg select 필터로 qcamera.ts에서 정확히 frame_number번째(0-based,
    presentation order = EncodeIndex.segmentId) 프레임 한 장을 out_path(jpg)로 추출.
    """
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", qcamera_path,
        "-vf", f"select=eq(n\\,{frame_number})",
        "-vsync", "0", "-frames:v", "1",
        out_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(
            f"ffmpeg 프레임 추출 실패 (frame={frame_number}): {r.stderr.strip()}"
        )
    return out_path


def extract_frames_for_times(segment_dir, repo_dir, target_times, out_dir,
                              context=0, label_prefix="", warn_diff_s=0.15):
    """
    target_times: [초 단위 float, ...] (extract_log.py CSV의 't'와 같은 축).
    각 시각마다 가장 가까운 프레임 1장(off=0) + 앞뒤로 context장씩(off!=0) 추가 추출.
    manifest(list of dict)를 리턴하고 <out_dir>/manifest.json으로도 저장한다.
    seg 경계를 벗어나 매칭 오차가 warn_diff_s(기본 0.15s, qcamera ~20fps 기준
    3프레임 정도)를 넘으면 stderr에 경고를 남긴다 (조용히 넘어가지 않음 —
    잘못된 프레임으로 결론 내리는 걸 방지).
    """
    os.makedirs(out_dir, exist_ok=True)
    qcam, log_path = find_segment_files(segment_dir)
    index = build_frame_time_index(log_path, repo_dir)
    if not index:
        raise RuntimeError(
            f"{log_path}에 qRoadEncodeIdx 이벤트가 없어 프레임 동기화 불가. "
            f"rlog.zst(qlog 아님)가 맞는지, 세그먼트 폴더가 맞는지 확인 필요."
        )

    manifest = []
    for target_t in target_times:
        entry, diff = nearest_frame_for_time(index, target_t)
        if diff is not None and diff > warn_diff_s:
            print(
                f"WARNING: t={target_t}에 가장 가까운 프레임이 {diff:.3f}s 떨어져 "
                f"있음 (허용치 {warn_diff_s}s 초과) — 세그먼트 경계를 벗어났거나 "
                f"target_t가 이 세그먼트 것이 아닐 수 있음",
                file=sys.stderr,
            )

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
                "segmentId": seg_id,
                "matched_t": entry["t"] if off == 0 else None,
                "time_diff_s": diff if off == 0 else None,
                "frameId": entry["frameId"] if off == 0 else None,
                "file": out_path,
            })

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(manifest)} frames + manifest to {out_dir}")
    return manifest


def make_side_by_side(image_paths, labels, out_path, max_width=1600):
    """
    PIL로 여러 프레임을 가로로 나란히 붙이고 상단에 라벨(예: 시각/dRel)을 찍는다.
    유실 직전 vs 재포착 직후 프레임을 나란히 놓고 "같은 차량인지" 육안 비교할 때 사용.
    """
    from PIL import Image, ImageDraw, ImageFont

    imgs = [Image.open(p) for p in image_paths]
    label_h = 36
    total_w = sum(im.width for im in imgs)
    max_h = max(im.height for im in imgs) + label_h
    canvas = Image.new("RGB", (total_w, max_h), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22
        )
    except OSError:
        font = ImageFont.load_default()

    x = 0
    for im, label in zip(imgs, labels):
        canvas.paste(im, (x, label_h))
        draw.text((x + 8, 6), label, fill=(255, 255, 0), font=font)
        x += im.width

    if canvas.width > max_width:
        scale = max_width / canvas.width
        canvas = canvas.resize((max_width, int(canvas.height * scale)))
    canvas.save(out_path, quality=90)
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("segment_dir", help="qcamera.ts + rlog.zst가 있는 세그먼트 폴더")
    ap.add_argument("--repo", default="/home/claude/ryu")
    ap.add_argument(
        "--times", required=True, help="쉼표구분 타겟 시각들 (초, CSV 't'축과 동일)"
    )
    ap.add_argument("--out-dir", required=True)
    ap.add_argument(
        "--context", type=int, default=0, help="타겟 프레임 앞뒤로 몇 장씩 더 뽑을지"
    )
    ap.add_argument("--label-prefix", default="")
    ap.add_argument(
        "--warn-diff-s", type=float, default=0.15,
        help="매칭 오차 경고 임계값(초). 기본 0.15s (~qcamera 3프레임)",
    )
    args = ap.parse_args()

    target_times = [float(x) for x in args.times.split(",")]
    extract_frames_for_times(
        args.segment_dir,
        args.repo,
        target_times,
        args.out_dir,
        context=args.context,
        label_prefix=args.label_prefix,
        warn_diff_s=args.warn_diff_s,
    )


if __name__ == "__main__":
    main()
