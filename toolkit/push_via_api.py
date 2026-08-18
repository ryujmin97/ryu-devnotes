#!/usr/bin/env python3
"""
GH_TOKEN 환경변수를 이용해 GitHub Contents API로 ryu-devnotes 저장소에
직접 파일을 커밋/push하는 스크립트.

- 토큰은 반드시 환경변수 GH_TOKEN 으로만 받는다 (하드코딩 금지, 인자로도 받지 않음).
- 어떤 경우에도 토큰 값 자체를 stdout/stderr에 출력하지 않는다 (에러 메시지 포함).
- fine-grained PAT (해당 repo 1개, Contents Read/write 권한)를 전제로 한다.

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
API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}/contents"


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
    last_commit_sha = None
    last_commit_url = None

    for remote_path, local_path in mappings:
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"로컬 파일 없음: {local_path}")

        with open(local_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode("ascii")

        url = f"{API_BASE}/{remote_path}"

        # 기존 파일 sha 조회 (없으면 신규 생성)
        get_resp = session.get(url, params={"ref": BRANCH})
        sha = None
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")
        elif get_resp.status_code not in (404,):
            get_resp.raise_for_status()

        payload = {
            "message": message,
            "content": content_b64,
            "branch": BRANCH,
        }
        if sha:
            payload["sha"] = sha

        put_resp = session.put(url, json=payload)
        if put_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"{remote_path} push 실패 (HTTP {put_resp.status_code}): "
                f"{put_resp.text[:300]}"
            )

        data = put_resp.json()
        last_commit_sha = data.get("commit", {}).get("sha")
        last_commit_url = data.get("commit", {}).get("html_url")
        print(f"[push_via_api] {remote_path} 업데이트 완료")

    if last_commit_sha:
        print(f"[push_via_api] 최종 커밋 SHA: {last_commit_sha}")
        print(f"[push_via_api] 커밋 URL: {last_commit_url}")


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
