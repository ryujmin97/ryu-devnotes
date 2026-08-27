"""
rlog.zst / qlog.zst -> capnp Event 이터레이터.

핵심 주의사항 (다 겪었던 함정들):
- capnp.remove_import_hook()을 capnp.load() 이전에 반드시 호출.
- zstandard 압축 해제는 max_output_size를 명시해야 함 (기본 zstd 프레임에는
  압축 해제 크기가 안 들어있는 경우가 있어, 안 주면 예외 발생 가능).
- BytesIO보다 임시 파일에 써서 읽는 편이 capnp의 멀티 메시지 스트림 파싱에
  더 안정적.
- 2026-08-26 수정: 드라이브 종료 시점(전원 차단/segment 강제 종료 등)에
  걸린 마지막 세그먼트는 rlog.zst 파일 자체가 잘려 기록된 경우가 있음.
  이 경우 one-shot decompress()가 "did not decompress full frame"으로
  실패하지만, stream_reader로 읽으면 잘린 지점까지의 유효 데이터는 정상
  회수 가능(zstd 프레임 경계 문제일 뿐 내용 자체는 유효). one-shot 실패
  시 스트리밍 폴백을 자동 시도하고, 이 경우 stderr에 경고를 남긴다
  (마지막 세그먼트 끝부분 일부 row 유실 가능성 있음을 알리기 위함).
"""
import io
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
        raw = f.read()
    try:
        data = dctx.decompress(raw, max_output_size=max_output_mb * 1024 * 1024)
    except zstandard.ZstdError as e:
        # 잘린 파일(마지막 세그먼트 등) 폴백: 스트리밍으로 가능한 만큼 회수
        print(f"[decode_rlog] WARNING: one-shot decompress 실패({e}), "
              f"stream_reader 폴백 시도: {path}", file=sys.stderr)
        chunks = []
        reader = dctx.stream_reader(io.BytesIO(raw), read_across_frames=True)
        try:
            while True:
                chunk = reader.read(1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
        except Exception as e2:
            print(f"[decode_rlog] WARNING: 스트리밍도 {len(b''.join(chunks))} "
                  f"bytes에서 중단됨({e2}): {path}", file=sys.stderr)
        data = b"".join(chunks)
        if not data:
            raise

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
