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
0. **`/home/claude/devnotes/WIP.md` 존재 여부부터 확인.** 있으면 이전
   세션이 한도/중단 등으로 끝까지 못 마친 작업이 있다는 뜻 — 그 내용부터
   사용자에게 요약해서 알리고, 이어서 할지 확인 후 이어간다. 없으면
   평소대로 진행.
0-1. **로그 분석/시뮬레이션/새 스크립트 작성이 필요한 요청이면
   `toolkit/README.md`부터 읽는다.** 이미 있는 도구로 되는지 먼저
   확인 후, 없을 때만 새로 작성한다 — 중복 스크립트 생성 방지.
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
3-1. **새 toolkit 스크립트를 만들었거나 기존 스크립트에 함수를
   추가/변경했으면** → `toolkit/README.md`에 섹션 추가/갱신 +
   `toolkit/CHANGELOG.md`에 날짜/한줄요약 추가.
4. **GH_TOKEN 자동 push (있으면 우선):**
   ```bash
   export GH_TOKEN="<지침 상단 값>"
   python3 /home/claude/devnotes/toolkit/push_via_api.py \
       --message "session: <한줄 요약>" \
       FINDINGS.md=/home/claude/devnotes/FINDINGS.md \
       LAST_ANALYZED.md=/home/claude/devnotes/LAST_ANALYZED.md \
       PARAMS_REGISTRY.md=/home/claude/devnotes/PARAMS_REGISTRY.md
   ```
   (3-1에서 toolkit 파일이 바뀌었으면 그 파일들도 같은 방식으로
   `toolkit/README.md=/home/claude/devnotes/toolkit/README.md` 형태로
   인자에 추가) 실제로 바뀐 파일만 인자로 넘긴다. 성공 시 출력되는
   커밋 SHA/URL을 사용자에게 보여준다. 토큰 값은 어떤 경우에도
   출력하지 않는다.
5. **GH_TOKEN 없거나 4번 실패 시 (폴백):** 갱신된 파일들을
   `/mnt/user-data/outputs/`에 만들어서 전달 (Master가 로컬에서
   commit + push, 아래 PowerShell 섹션 참고)

## 코딩 작업 중 체크포인트 (세션 정상 종료가 아닌 "중단 지점 저장")
Claude는 현재 세션의 5시간 사용량 잔여 %를 조회할 수 없다. 그래서
"한도 도달을 감지해서 멈추기 전에 저장"은 불가능 -- 대신 아래 트리거
발생 시 작업을 끝내지 말고 바로 체크포인트한다:
1. 사용자가 "체크포인트" / "저장" / "여기까지" 요청
2. 패치 하나의 구현/검증이 한 단계 완료된 시점
3. 대화가 비정상적으로 길어져 한도 임박 가능성이 있다고 판단될 때

체크포인트 절차:
1. 진행 상황(완료 단계 / 다음 단계 / 관련 로그 분석 상태 / 코드 diff
   요약)을 `/home/claude/devnotes/WIP.md`에 기록 (없으면 생성)
2. `/mnt/user-data/outputs/`에 `WIP.md` 생성 → present_files 전달
3. 코드 변경분이 있으면 현재 상태 그대로 patch 파일도 같이 생성
   (`git am` 적용 안내 포함, WIP 단계라도 patch화)
4. 위의 "세션 종료 시 체크리스트" 1~4번도 함께 수행 (FINDINGS 등)
5. 사용자에게 "세션 종료"가 아니라 "중단 지점 저장"임을 명확히 알림

다음 세션은 `WIP.md`가 있으면 그 지점부터 이어받고, 완료되면
WIP.md에서 해당 항목을 제거하거나 완료 표시한다.

## Master 로컬 반영 방법 (PowerShell) — GH_TOKEN 없을 때 폴백
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
