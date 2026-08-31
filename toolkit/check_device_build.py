#!/usr/bin/env python3
"""
check_device_build.py (178차 신규)

목적: extract_log.py의 meta.json "repo commit"은 분석 컨테이너가 체크아웃한
repo 상태일 뿐, 디바이스가 실제로 실행한 빌드가 아니다(기존 "Patch workflow
discipline" 원칙 -- 여러 세션에서 이 구분을 놓쳐 "패치가 반영됐다"를 잘못
단정할 위험이 반복 지적됨).

이 스크립트는 rlog/qlog의 InitData capnp 이벤트를 직접 읽어 디바이스가
실제로 기록한 gitCommit/gitCommitDate/gitBranch/dirty를 뽑고, 로컬 ryu repo
히스토리와 대조해 그 커밋이 실제로 origin에 존재하는지, 특정 대상 커밋의
조상/후손인지까지 확인한다.

사용법:
    python3 check_device_build.py <route_dir> --repo /home/claude/ryu \
        [--compare-commit <hash_or_short>]

<route_dir>: extract_log.py와 동일하게 세그먼트 폴더들의 상위 폴더
             (예: 첫 segment의 첫 rlog.zst에서 InitData를 찾음.
              InitData는 보통 세그먼트 맨 앞부분에서 1회 발행됨)

출력: gitCommit/gitCommitDate/gitBranch/dirty 원본 값 +
      - 로컬 repo에 해당 commit이 존재하는지 (git cat-file -t)
      - --compare-commit 지정 시: 그 커밋의 조상인지(ancestor) 여부
      - dirty=True인 경우 경고: 워킹트리에 커밋 안 된 로컬 변경이 있었다는
        뜻이므로 "이 커밋 = 실제 실행 코드"라는 보장이 약함

주의: InitData는 매 세그먼트가 아니라 드라이브 시작 시 1회만 발행될 수
있음 -- 이 스크립트는 폴더 내 세그먼트를 순서대로 훑어 첫 InitData를
찾으면 즉시 반환한다. 여러 세그먼트를 검색해도 못 찾으면 "InitData 없음"
경고 출력(구버전 빌드이거나 세그먼트 자체가 드라이브 중간부터 시작하는
경우 발생 가능).
"""
import sys
import glob
import os
import subprocess
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_rlog import get_schema, iter_events  # noqa: E402


def find_init_data(route_dir, repo_dir, max_segments=5):
    segs = sorted(glob.glob(os.path.join(route_dir, "*", "rlog.zst")))
    if not segs:
        segs = sorted(glob.glob(os.path.join(route_dir, "*", "qlog.zst")))
    for seg in segs[:max_segments]:
        for evt in iter_events(seg, repo_dir):
            if evt.which() == "initData":
                return seg, evt.initData
    return None, None


def git(repo_dir, *args):
    r = subprocess.run(["git", "-C", repo_dir, *args],
                        capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_dir")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--compare-commit", default=None,
                     help="이 커밋의 조상/동일 커밋인지 확인 (예: 특정 패치 커밋 해시)")
    args = ap.parse_args()

    seg, init = find_init_data(args.route_dir, args.repo)
    if init is None:
        print("경고: InitData를 찾지 못함 (구버전 빌드 또는 세그먼트 누락 가능)")
        sys.exit(1)

    commit = str(init.gitCommit)
    commit_date = str(init.gitCommitDate)
    branch = str(init.gitBranch)
    dirty = bool(init.dirty)

    print(f"segment: {seg}")
    print(f"device gitCommit:     {commit}")
    print(f"device gitCommitDate: {commit_date}")
    print(f"device gitBranch:     {branch}")
    print(f"device dirty:         {dirty}")
    if dirty:
        print("  [경고] dirty=True -- 빌드 시점 워킹트리에 커밋 안 된 로컬 변경 "
              "존재. 이 gitCommit 해시만으로 '실제 실행 코드=이 커밋'이라고 "
              "단정할 수 없음.")

    rc, _, _ = git(args.repo, "cat-file", "-t", commit)
    if rc == 0:
        print(f"  -> 로컬 repo에 존재하는 커밋: OK")
        rc2, out2, _ = git(args.repo, "show", "-s",
                            "--format=%H %ai %s", commit)
        if rc2 == 0:
            print(f"     {out2}")
    else:
        print(f"  -> [주의] 로컬 repo(unshallow 포함)에 이 커밋 해시가 "
              f"존재하지 않음. origin 히스토리에 없는 커밋이거나, "
              f"이후 rebase/amend로 재작성됐거나, fetch 안 된 별도 브랜치일 "
              f"가능성. GitHub API/로컬에서 추가 확인 필요.")

    if args.compare_commit:
        rc3, _, _ = git(args.repo, "merge-base", "--is-ancestor",
                         commit, args.compare_commit)
        if rc3 == 0:
            print(f"  -> {commit[:12]} 는 {args.compare_commit} 의 조상: YES")
        else:
            print(f"  -> {commit[:12]} 는 {args.compare_commit} 의 조상: "
                  f"NO/확인불가 (둘 다 로컬에 존재해야 정확히 판정 가능)")


if __name__ == "__main__":
    main()
