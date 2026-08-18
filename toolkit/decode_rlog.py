"""
rlog.zst / qlog.zst -> capnp Event 이터레이터.

핵심 주의사항 (다 겪었던 함정들):
- capnp.remove_import_hook()을 capnp.load() 이전에 반드시 호출.
- zstandard 압축 해제는 max_output_size를 명시해야 함 (기본 zstd 프레임에는
  압축 해제 크기가 안 들어있는 경우가 있어, 안 주면 예외 발생 가능).
- BytesIO보다 임시 파일에 써서 읽는 편이 capnp의 멀티 메시지 스트림 파싱에
  더 안정적.
"""
import os
import sys

import capnp

capnp.remove_import_hook()
import zstandard  # noqa: E402


def _load_schema(repo_dir: str):
    cereal_dir = os.path.join(repo_dir, "cereal")
    log_capnp_path = os.path.join(cereal_dir, "log.capnp")
    if not os.path.exists(log_capnp_path):
        raise FileNotFoundError(
            f"log.capnp not found at {log_capnp_path}. "
            f"레포를 먼저 clone하세요 (SETUP.md 참고)."
        )
    # cereal 내부 capnp 파일들이 서로를 상대경로로 import하므로,
    # import_path에 cereal_dir 자체를 넣어줘야 함.
    return capnp.load(log_capnp_path, imports=[cereal_dir, repo_dir])


_SCHEMA_CACHE = {}


def get_schema(repo_dir: str = "/home/claude/ryu"):
    if repo_dir not in _SCHEMA_CACHE:
        _SCHEMA_CACHE[repo_dir] = _load_schema(repo_dir)
    return _SCHEMA_CACHE[repo_dir]


def iter_events(path: str, repo_dir: str = "/home/claude/ryu", max_output_mb: int = 400):
    """Yield capnp Event objects from a single rlog.zst/qlog.zst file."""
    log_capnp = get_schema(repo_dir)

    dctx = zstandard.ZstdDecompressor()
    with open(path, "rb") as f:
        data = dctx.decompress(f.read(), max_output_size=max_output_mb * 1024 * 1024)

    tmp_path = f"/tmp/_seg_{os.getpid()}.bin"
    with open(tmp_path, "wb") as f:
        f.write(data)
    try:
        with open(tmp_path, "rb") as f:
            yield from log_capnp.Event.read_multiple(f)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    # 간단한 자체 테스트: 첫 이벤트 종류 몇 개만 출력
    if len(sys.argv) < 2:
        print("usage: python3 decode_rlog.py <rlog.zst> [repo_dir]")
        sys.exit(1)
    repo = sys.argv[2] if len(sys.argv) > 2 else "/home/claude/ryu"
    n = 0
    for evt in iter_events(sys.argv[1], repo_dir=repo):
        print(evt.which())
        n += 1
        if n >= 20:
            break
