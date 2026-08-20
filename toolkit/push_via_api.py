#!/usr/bin/env python3
"""
GH_TOKEN 환경변수를 이용해 GitHub API로 ryu-devnotes 저장소에 직접
파일을 커밋/push하는 스크립트.

- 토큰은 반드시 환경변수 GH_TOKEN 으로만 받는다 (하드코딩 금지, 인자로도 받지 않음).
- 어떤 경우에도 토큰 값 자체를 stdout/stderr에 출력하지 않는다 (에러 메시지 포함).
- fine-grained PAT (해당 repo 1개, Contents Read/write 권한)를 전제로 한다.

**Git Trees API 사용 (2026-08-21부터)**: 파일이 몇 개든 항상 커밋 1개로
묶는다. 이전 버전(Contents API PUT 반복)은 파일마다 별도 커밋이 생겨
히스토리가 지저분해지는 문제가 있었음 — blob 생성 → tree 생성(base_tree
사용, 나머지 파일은 그대로 유지) → commit 생성 → ref 갱신 순서로 처리.

사용법:
    export GH_TOKEN="..."
    python3 push_via_api.py --message "커밋 메시지" \\
        FINDINGS.md=/home/claude/devnotes/FINDINGS.md \\
        LAST_ANALYZED.md=/home/claude/devnotes/LAST_ANALYZED.md

    좌변 = 저장소 내 경로 (repo root 기준)
    우변 = 로컬 파일 경로 (push할 실제 내용)
"""

import argparse
import base64
import os
import sys

import requests

OWNER = "ryujmin97"
REPO = "ryu-devnotes"
BRANCH = "main"
API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"


def mask_errors(func):
    """토큰이 예외 메시지/응답 본문에 실수로 섞여도 출력 전에 마스킹."""

    def wrapper(*args, **kwargs):
        token = os.environ.get("GH_TOKEN", "")
        try:
            return func(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            if token:
                msg = msg.replace(token, "***MASKED***")
            print(f"[push_via_api] 오류: {msg}", file=sys.stderr)
            sys.exit(1)

    return wrapper


def get_session(token):
    s = requests.Session()
    s.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return s


@mask_errors
def push_files(message, mappings):
    token = os.environ.get("GH_TOKEN")
    if not token:
        print(
            "[push_via_api] GH_TOKEN 환경변수가 비어있음 → 자동 push 생략, "
            "수동 절차(outputs + PowerShell)로 폴백하세요.",
            file=sys.stderr,
        )
        sys.exit(2)

    session = get_session(token)

    for remote_path, local_path in mappings:
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"로컬 파일 없음: {local_path}")

    # 1) 현재 브랜치 ref -> 최신 커밋 sha -> 그 커밋의 base tree sha
    ref_resp = session.get(f"{API_BASE}/git/ref/heads/{BRANCH}")
    ref_resp.raise_for_status()
    latest_commit_sha = ref_resp.json()["object"]["sha"]

    commit_resp = session.get(f"{API_BASE}/git/commits/{latest_commit_sha}")
    commit_resp.raise_for_status()
    base_tree_sha = commit_resp.json()["tree"]["sha"]

    # 2) 파일마다 blob 생성
    tree_entries = []
    for remote_path, local_path in mappings:
        with open(local_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode("ascii")

        blob_resp = session.post(
            f"{API_BASE}/git/blobs",
            json={"content": content_b64, "encoding": "base64"},
        )
        if blob_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"{remote_path} blob 생성 실패 (HTTP {blob_resp.status_code}): "
                f"{blob_resp.text[:300]}"
            )
        blob_sha = blob_resp.json()["sha"]
        tree_entries.append(
            {
                "path": remote_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha,
            }
        )

    # 3) base_tree 위에 새 tree 생성 (나머지 파일은 그대로 유지됨)
    tree_resp = session.post(
        f"{API_BASE}/git/trees",
        json={"base_tree": base_tree_sha, "tree": tree_entries},
    )
    if tree_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"tree 생성 실패 (HTTP {tree_resp.status_code}): "
            f"{tree_resp.text[:300]}"
        )
    new_tree_sha = tree_resp.json()["sha"]

    # 4) 커밋 1개 생성 (파일 개수와 무관)
    new_commit_resp = session.post(
        f"{API_BASE}/git/commits",
        json={
            "message": message,
            "tree": new_tree_sha,
            "parents": [latest_commit_sha],
        },
    )
    if new_commit_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"commit 생성 실패 (HTTP {new_commit_resp.status_code}): "
            f"{new_commit_resp.text[:300]}"
        )
    new_commit = new_commit_resp.json()
    new_commit_sha = new_commit["sha"]
    new_commit_url = new_commit["html_url"]

    # 5) 브랜치 ref를 새 커밋으로 이동
    update_ref_resp = session.patch(
        f"{API_BASE}/git/refs/heads/{BRANCH}",
        json={"sha": new_commit_sha},
    )
    if update_ref_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"ref 업데이트 실패 (HTTP {update_ref_resp.status_code}): "
            f"{update_ref_resp.text[:300]}"
        )

    for remote_path, _ in mappings:
        print(f"[push_via_api] {remote_path} 업데이트 완료")
    print(f"[push_via_api] 최종 커밋 SHA: {new_commit_sha}")
    print(f"[push_via_api] 커밋 URL: {new_commit_url}")


def parse_mapping(raw):
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"'{raw}' 형식이 잘못됨. remote_path=local_path 형태여야 함"
        )
    remote_path, local_path = raw.split("=", 1)
    return remote_path, local_path


def main():
    parser = argparse.ArgumentParser(description="ryu-devnotes 자동 push")
    parser.add_argument("--message", required=True, help="커밋 메시지")
    parser.add_argument(
        "mappings",
        nargs="+",
        type=parse_mapping,
        help="remote_path=local_path 형식, 여러 개 지정 가능",
    )
    args = parser.parse_args()
    push_files(args.message, args.mappings)


if __name__ == "__main__":
    main()
