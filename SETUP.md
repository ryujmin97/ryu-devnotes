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
0-2. **[63차 정책 변경] 새로 작성하는 검증/시뮬레이션 스크립트는
   검증 상태(합성검증뿐/실측검증 완료 등)와 무관하게 작성 즉시
   `toolkit/`에 커밋한다.** `work/`는 1회성 스캔/탐색용으로만 쓰고,
   재사용 가능한 검증 도구를 `work/`에만 남겨두지 않는다 — 컨테이너는
   세션마다 리셋되므로 `work/`에만 있으면 다음 세션(또는 리셋 시)에
   그대로 소실돼 같은 스크립트를 다시 작성하는 낭비가 생긴다(58차1번
   `test_visiontrack_gate.py`, 63차 `sim_drel_discontinuity.py` 총
   2회 반복된 후 이 원칙으로 변경). 절차: 스크립트 작성 →
   `toolkit/<name>.py`에 저장 → `toolkit/README.md`에 섹션 추가 →
   `toolkit/CHANGELOG.md`에 날짜/한줄요약 추가 → 세션 종료(또는
   체크포인트) 시 다른 변경 파일과 함께 push. (이전 원칙이었던
   "신뢰성 미검증 스크립트는 work/ 스크래치로 유지"는 폐기됨 —
   README/CHANGELOG에 검증 상태를 명시하는 것으로 대체.)
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
5-1. **과거에 추출한 CSV를 다시 쓸 일이 있으면(예: 회귀 재검증) 원본
   zip을 재추출하기 전에 먼저 Google Drive `ryu-devnotes-csv/` 폴더에
   같은 route의 CSV가 이미 올라가 있는지 `search_files`로 확인** — 있으면
   `download_file_content`로 바로 받아 쓴다(재추출 불필요). 없으면 평소대로
   추출. (74차, 아래 "CSV 보관(Google Drive)" 섹션 참고)

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

## CSV 보관 (Google Drive) — 74차 신규

`extract_log.py`로 뽑은 route CSV는 **레포(devnotes)에는 절대 커밋하지
않는다** — git 히스토리는 삭제 커밋으로도 blob이 영구히 남아 레포가
계속 비대해지므로, 레포엔 분석 결론(FINDINGS.md 등)만 남기고 원본 CSV는
레포 밖(Google Drive)에 둔다.

**전제**: 사용자 Google Drive 커넥터가 연결되어 있어야 함(연결 안 돼
있으면 `search_mcp_registry`로 확인 후 `suggest_connectors`로 연결
안내 — 없으면 이 섹션 스킵하고 기존처럼 `work/`에만 스크래치로 둠).

**전용 폴더**: `ryu-devnotes-csv` (Drive 루트, folderId
`16r-XIFcXXBvOV7tlpL_P0vxuMXmfwFSU`, 74차 세션에서 생성).

**업로드 시점**: 재사용 가치가 있는 CSV(예: 회귀검증에 쓴 route, 패치
전/후 비교용 baseline)를 추출한 세션 종료 시. 1회성 탐색용 CSV까지
전부 올릴 필요는 없음 — 판단 애매하면 올리는 쪽으로(Drive는 git과
달리 용량 부담이 크지 않음).

**파일명 규칙**: `<route_dir_이름>_<commit_short>.csv`
(예: `20260825_152959_0000031f--ea5bcc0566_f8e136e.csv` — route_dir 이름은
`extract_log.py`가 만든 meta.json의 `route_dir` 마지막 세그먼트 폴더명
prefix나 라우트 해시로 축약해도 됨, commit_short는 meta.json의
`commit_short`).

**업로드 방법**:
```
Google Drive:create_file
  title: "<파일명>.csv"
  textContent: <CSV 파일 전체 텍스트>
  contentMimeType: "text/csv"
  disableConversionToGoogleType: true   # 반드시 true -- 없으면 Google
                                         # Sheets로 변환되어 순수 CSV로
                                         # 못 받아옴
  parentId: "16r-XIFcXXBvOV7tlpL_P0vxuMXmfwFSU"
```
리턴된 `id`(fileId)를 `LAST_ANALYZED.md` 또는 `FINDINGS.md`의 해당
세션 기록에 `drive_csv: <fileId>` 형태로 남긴다(다음 세션이 재추출
없이 바로 다운로드할 수 있도록).

**다운로드 방법**:
```
Google Drive:download_file_content fileId=<위 fileId>
```
결과의 `content`는 base64 인코딩 — 디코딩하면 원본 CSV 텍스트.

**검색 방법**(fileId를 모를 때):
```
Google Drive:search_files query="name contains '<route_hash>'"
```

**보관 정책**: git과 달리 Drive는 삭제해도 진짜로 지워지고 용량 부담도
적으므로, 레포처럼 "삭제해도 히스토리에 남는" 문제가 없다. 다만
무한정 쌓아둘 필요는 없으니 — 같은 route를 재추출해 새 commit 기준
CSV를 올렸다면 **이전 commit 기준 CSV는 `trash_file`로 정리**해도
안전하다(단, 다른 커밋과의 회귀비교에 아직 쓰이는 중이면 보존).
이 정리는 선택사항이며 세션 종료 필수 절차는 아님.

**74차 검증 완료**: `create_file`(textContent+text/csv,
disableConversionToGoogleType=true) → `download_file_content` 왕복
테스트, base64 디코딩 결과 원본과 100% 일치 확인.

## 주의사항 (toolkit 관련, 기존과 동일)
- `decode_rlog.py`는 `cereal/log.capnp` 스키마를 `ryu` 레포에서 직접
  로드하므로 `ryu`를 먼저 clone해야 함.
- `zstandard.ZstdDecompressor().decompress()`는 `max_output_size` 명시 필요
  (기본 200MB, `extract_log.py --max-mb`로 조절).
- `capnp.remove_import_hook()`을 `capnp.load()` 이전에 반드시 호출.
- pip 설치 시 `--break-system-packages` 필요.
