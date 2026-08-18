# 새 세션 최초 1회 셋업 (계정 무관)

이 문서 하나로 어느 Claude 계정/세션에서든 동일하게 시작한다.
Claude 프로젝트 파일 업로드가 필요 없다 — 아래 두 줄이면 코드 +
분석 기록이 전부 최신 상태로 딸려온다.

```bash
# 0) 파이썬 의존성
pip install --break-system-packages -q pycapnp zstandard

# 1) 분석 노트/이슈 트래커 (가벼움, 텍스트 파일 몇 개)
cd /home/claude && git clone --depth 1 \
  https://github.com/ryujmin97/ryu-devnotes.git devnotes

# 2) 실제 코드 (커밋 히스토리 필요하므로 shallow 안 씀 -- depth 1은
#    "최신 커밋 분석" 요청 시 git log가 안 돼서 문제가 된다)
cd /home/claude && git clone --branch c3-ms-dev --single-branch --depth 200 \
  https://github.com/ryujmin97/ryu.git ryu

# 3) 작업 폴더 + toolkit 실행 권한
mkdir -p /home/claude/work
chmod +x /home/claude/devnotes/analyze_commits.sh
```

## 세션 시작 시 체크리스트
1. `/home/claude/devnotes/LAST_ANALYZED.md` 열어서 어디까지 분석했는지 확인
2. "최신 커밋 분석" 요청이면:
   ```bash
   bash /home/claude/devnotes/analyze_commits.sh /home/claude/ryu c3-ms-dev
   ```
   (LAST_ANALYZED.md 기록 이후 신규 커밋만 자동으로 뽑아줌)
3. "실주행 로그 분석" 요청이면:
   ```bash
   mkdir -p /home/claude/work/route && cd /home/claude/work/route
   unzip -q -o /mnt/user-data/uploads/<업로드파일>.zip
   cd /home/claude/devnotes/toolkit
   python3 extract_log.py /home/claude/work/route /home/claude/work/route.csv --repo /home/claude/ryu
   ```
4. `/home/claude/devnotes/PARAMS_REGISTRY.md`로 관련 튜닝 상수 현재값/검증상태 확인
5. `/home/claude/devnotes/FINDINGS.md`로 이미 알려진 이슈인지 먼저 확인
   (재발견/중복 분석 방지)

## 세션 종료 시 체크리스트
1. 새로 발견한 이슈/검증 결과 → `FINDINGS.md`에 추가
2. 튜닝 상수 값 변경/검증 완료 → `PARAMS_REGISTRY.md` 갱신
3. 커밋 분석을 했으면 → `LAST_ANALYZED.md`의 해당 브랜치 해시 갱신
4. 갱신된 파일들을 `/mnt/user-data/outputs/`에 만들어서 전달
   (Claude는 push 권한이 없음 -- Master가 로컬에서 commit + push)

## Master 로컬 반영 방법 (PowerShell)
```powershell
# devnotes 갱신 파일을 받으면 (예: FINDINGS.md, LAST_ANALYZED.md)
cd C:\dev\ryu-devnotes
# 다운로드한 파일을 이 폴더에 덮어쓰기 후:
git add -A
git commit -m "session: <한줄 요약>"
git push
```
코드 패치(`git am`)와 달리 devnotes는 단순 파일 덮어쓰기 + commit이라
더 간단하다.

## 커밋 추적 (로그 <-> 코드 상태 매칭)
`toolkit/extract_log.py`는 CSV를 만들 때 `--repo`로 지정한 저장소(`ryu`)의
현재 git commit 정보를 함께 기록한다:
- CSV의 각 row에 `commit`(short hash) 컬럼
- `<out.csv>.meta.json`에 commit hash/branch/commit 날짜·메시지/dirty
  여부/추출 시각/row 수

```python
from analysis_helpers import compare_runs_by_commit
result = compare_runs_by_commit([
    "/home/claude/work/route_before.csv",
    "/home/claude/work/route_after.csv",
])
```

## 주의사항 (toolkit 관련, 기존과 동일)
- `decode_rlog.py`는 `cereal/log.capnp` 스키마를 `ryu` 레포에서 직접
  로드하므로 `ryu`를 먼저 clone해야 함.
- `zstandard.ZstdDecompressor().decompress()`는 `max_output_size` 명시 필요
  (기본 200MB, `extract_log.py --max-mb`로 조절).
- `capnp.remove_import_hook()`을 `capnp.load()` 이전에 반드시 호출.
- pip 설치 시 `--break-system-packages` 필요.
