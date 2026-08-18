# Claude 프로젝트 지침 (Project Instructions / Custom Instructions)

아래 내용을 어느 계정이든 Claude 프로젝트(claude.ai) 생성 시
"프로젝트 지침" / "Custom instructions" 칸에 그대로 붙여넣으면 된다.
**파일 업로드가 아니라 텍스트 지침**이라 계정을 새로 만들거나 프로젝트를
새로 파도 이 텍스트 한 번만 붙여넣으면 동일한 워크플로우가 재현된다.

---

## 붙여넣을 지침 (여기부터)

이 프로젝트는 openpilot 포크(`ryujmin97/ryu`, Genesis DH 2015/2016 대상)의
종방향 제어 로직 개선 작업이다. 주 요청 유형: 최신 커밋 분석, 실주행 로그
분석, 문제점/원인 파악, 대안 제시, 패치 적용.

**중요: 이 프로젝트는 파일 업로드(프로젝트 파일)를 쓰지 않는다.** 분석
기록/이슈 트래커/툴킷은 전부 GitHub 공개 레포 `ryujmin97/ryu-devnotes`에
있고, 세션마다 clone해서 쓴다. 세션이 끝나도 사람이 그 레포에 push해두면
다음 세션(같은 계정이든 다른 계정이든)이 항상 최신 상태를 이어받는다.

**세션을 시작하면 다른 어떤 작업보다 먼저 아래를 실행한다:**

```bash
pip install --break-system-packages -q pycapnp zstandard
cd /home/claude
git clone --depth 1 https://github.com/ryujmin97/ryu-devnotes.git devnotes
git clone --branch c3-ms-dev --single-branch --depth 200 https://github.com/ryujmin97/ryu.git ryu
mkdir -p /home/claude/work
chmod +x /home/claude/devnotes/analyze_commits.sh
```

그 다음 `/home/claude/devnotes/SETUP.md`를 읽고 그 안에 적힌 세션
시작/종료 체크리스트를 그대로 따른다. 특히:
- `LAST_ANALYZED.md`로 이미 분석한 커밋 범위를 확인하고 그 이후만 검토
- `FINDINGS.md`로 이미 알려진 이슈인지 먼저 확인 (중복 분석 방지)
- `PARAMS_REGISTRY.md`로 관련 튜닝 상수 현황 파악
- 로그 분석은 `devnotes/toolkit/`의 스크립트 사용

**세션 종료 시 (반드시):**
1. `FINDINGS.md` / `LAST_ANALYZED.md` / `PARAMS_REGISTRY.md` 중 이번
   세션에서 내용이 바뀐 파일들을 실제로 갱신한다 (devnotes 클론 안의
   파일을 직접 수정).
2. 갱신된 파일들을 `/mnt/user-data/outputs/`에 만들어 present_files로
   전달한다. Claude는 GitHub push 권한이 없으므로 여기서 끝낸다 — 절대
   "완료했다"고만 말하고 파일을 안 만들면 안 된다.
3. 전달할 때 아래 PowerShell 안내를 같이 준다 (매번 반복):
   ```powershell
   # 다운로드한 갱신 파일들을 C:\dev\ryu-devnotes 에 덮어쓴 뒤
   cd C:\dev\ryu-devnotes
   git add -A
   git commit -m "session: <한줄 요약>"
   git push
   ```
4. 코드(패치) 변경이 있었던 세션이면 `ryu` 레포용 패치 파일도 별도로
   만들어 `/mnt/user-data/outputs/`에 두고, `git am` 적용 명령어를 같이
   제공한다 (devnotes와 완전히 별개 절차 — 섞지 않는다).

이 절차를 따르면 어느 계정에서 세션을 열든, 사람이 push만 해두면 다음
세션이 프로젝트 파일 업로드 없이 항상 최신 상태(FINDINGS/LAST_ANALYZED/
PARAMS_REGISTRY/toolkit)를 자동으로 이어받는다.

## 붙여넣을 지침 (여기까지)

---

## 계정별로 다르게 채워야 하는 부분 (있다면)
현재는 레포 URL이 public이라 별도 인증 없이 clone 가능. private으로
바뀌면 인증 절차를 이 지침 위쪽에 추가해야 한다.
