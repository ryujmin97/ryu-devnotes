#!/usr/bin/env python3
"""
data/routes/ 아래 저장된 gzip CSV 라우트 캐시를 불러오는 헬퍼.

목적: 로그 업로드 zip을 매 세션 다시 unzip + extract_log.py 하지 않고,
이미 추출해 devnotes/data/routes/<route_id>/route.csv.gz 로 커밋해둔
라우트를 바로 analysis_helpers.load_csv()와 동일한 list[dict] 형태로
불러온다. 상세 구조/등록 라우트 목록은 data/routes/README.md 참고.

사용법:
    from data_routes import load_route, list_routes

    rows, meta = load_route("/home/claude/devnotes", "ea5bcc0566")
    for r in list_routes("/home/claude/devnotes"):
        print(r)
"""

import csv
import gzip
import json
import os
import shutil
import tempfile


def list_routes(devnotes_dir):
    """data/routes/ 아래 등록된 route_id 목록 반환."""
    routes_dir = os.path.join(devnotes_dir, "data", "routes")
    if not os.path.isdir(routes_dir):
        return []
    return sorted(
        d
        for d in os.listdir(routes_dir)
        if os.path.isdir(os.path.join(routes_dir, d))
        and os.path.isfile(os.path.join(routes_dir, d, "route.csv.gz"))
    )


def load_route_meta(devnotes_dir, route_id):
    """meta.json만 읽어 dict로 반환 (CSV 전체를 풀지 않고 빠르게 확인할 때)."""
    meta_path = os.path.join(devnotes_dir, "data", "routes", route_id, "meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_route(devnotes_dir, route_id):
    """
    route.csv.gz를 임시 파일로 풀어 analysis_helpers.load_csv()와 동일한
    list[dict] 형태로 반환. 반환: (rows, meta)
    rows의 각 필드는 CSV 원본 그대로 문자열(analysis_helpers 함수들이
    기대하는 형식과 동일 — 숫자 변환은 호출부 책임).
    """
    route_dir = os.path.join(devnotes_dir, "data", "routes", route_id)
    gz_path = os.path.join(route_dir, "route.csv.gz")
    if not os.path.isfile(gz_path):
        raise FileNotFoundError(
            f"route.csv.gz 없음: {gz_path} (data/routes/README.md의 등록 라우트 목록 확인)"
        )

    meta = load_route_meta(devnotes_dir, route_id)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    os.close(tmp_fd)
    try:
        with gzip.open(gz_path, "rb") as src, open(tmp_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        with open(tmp_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    finally:
        os.remove(tmp_path)

    return rows, meta


if __name__ == "__main__":
    import sys

    devnotes_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/devnotes"
    for rid in list_routes(devnotes_dir):
        m = load_route_meta(devnotes_dir, rid)
        print(
            f"{rid}: {m.get('n_rows')} rows, {m.get('n_segments')} segs, "
            f"commit {m.get('commit_short')} ({m.get('commit_subject')})"
        )
