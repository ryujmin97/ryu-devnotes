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
2. **GH_TOKEN이 이 지침 상단에 채워져 있으면 자동 push (우선 방식):**
   ```bash
   export GH_TOKEN="<지침 상단의 GH_TOKEN 값>"
   python3 /home/claude/devnotes/toolkit/push_via_api.py \
       --message "session: <한줄 요약>" \
       FINDINGS.md=/home/claude/devnotes/FINDINGS.md \
       LAST_ANALYZED.md=/home/claude/devnotes/LAST_ANALYZED.md \
       PARAMS_REGISTRY.md=/home/claude/devnotes/PARAMS_REGISTRY.md
   ```
   (실제로 바뀐 파일만 인자로 넘긴다.) 성공하면 출력된 커밋 SHA와
   커밋 URL을 사용자에게 보여준다. **토큰 값 자체는 절대 stdout에
   출력/echo/로그하지 않는다** — push_via_api.py는 에러 메시지에서도
   토큰을 마스킹하도록 되어 있지만, Claude도 별도로 토큰을 print하는
   커맨드를 실행하지 않는다. 이 방식이 성공하면 3번(수동 절차)은
   생략한다.
3. **GH_TOKEN이 비어있거나 push_via_api.py가 실패하면 (수동 방식):**
   갱신된 파일들을 `/mnt/user-data/outputs/`에 만들어 present_files로
   전달한다. 절대 "완료했다"고만 말하고 파일을 안 만들면 안 된다.
   전달할 때 아래 PowerShell 안내를 같이 준다:
   ```powershell
   # 다운로드한 갱신 파일들을 C:\dev\ryu-devnotes 에 덮어쓴 뒤
   cd C:\dev\ryu-devnotes
   git add -A
   git commit -m "session: <한줄 요약>"
   git push
   ```
4. 코드(패치) 변경이 있었던 세션이면 `ryu` 레포용 패치 파일은
   (GH_TOKEN 유무와 무관하게) 항상 `/mnt/user-data/outputs/`에 별도로
   만들고 `git am` 적용 명령어를 같이 제공한다 — `ryu`는
   `push_via_api.py` 대상이 아니며 devnotes와 완전히 별개 절차다
   (섞지 않는다).

**보안 참고:** GH_TOKEN은 이 저장소 1개, Contents Read/write 권한만 갖는
fine-grained PAT를 전제로 한다. 만료 기간은 짧게 유지하고, 이 지침
텍스트가 포함된 화면을 캡처/공유할 때는 GH_TOKEN 줄을 반드시 가린다.

이 절차를 따르면 어느 계정에서 세션을 열든, 사람이 push만 해두면 다음
세션이 프로젝트 파일 업로드 없이 항상 최신 상태(FINDINGS/LAST_ANALYZED/
PARAMS_REGISTRY/toolkit)를 자동으로 이어받는다.

**코딩 작업 중 체크포인트 (세션 한도 대비, 다른 계정에서 이어받기 위함):**

Claude는 지금 세션의 5시간 사용량 잔여치를 조회할 방법이 없다 (계정
사용량 표시줄은 Claude 쪽에 노출되지 않음). 그래서 "한도 임박을 감지해서
멈추기 전에 저장"은 할 수 없고, 대신 아래 트리거가 발생하면 작업을
끝내지 말고 그 시점까지의 진행 상황을 즉시 체크포인트한다:
1. 사용자가 "체크포인트" / "저장" / "여기까지" 등으로 명시 요청
2. 패치 하나의 구현/검증이 한 단계 완료된 시점 (다음 단계로 넘어가기 전)
3. 대화가 비정상적으로 길어져 세션 한도 임박 가능성이 있다고 판단될 때
   (예: long_conversation_reminder류의 내부 신호를 받았을 때)

체크포인트 시 수행할 것:
- 현재까지의 코드 diff/패치 상태, 완료된 단계, 미완료 다음 단계, 관련
  로그 분석 진행 상황을 `devnotes/WIP.md`에 기록 (없으면 새로 생성,
  있으면 갱신 — 이전 WIP 내용은 완료 표시하고 남겨두거나 정리)
- GH_TOKEN이 있으면 `push_via_api.py`로 `WIP.md`(+ 이번 세션에서 바뀐
  다른 devnotes 파일)를 바로 push. 없으면 `/mnt/user-data/outputs/`에
  `WIP.md` 생성 → present_files 전달 + PowerShell 안내 (평소 종료
  절차의 2/3번과 동일한 분기)
- 코드 변경분이 있으면 지금까지의 작업을 patch 파일로도 만들어
  `/mnt/user-data/outputs/`에 같이 둔다 (완성 여부와 무관하게 WIP 상태
  그대로 patch화 — `git am` 적용 안내 포함, `ryu`는 항상 수동 patch만)
- "세션 종료"가 아니라 "중단 지점 저장"이라는 걸 사용자에게 분명히 알린다

다음 세션(다른 계정 포함)은 SETUP.md 체크리스트에서 `devnotes/WIP.md`
존재 여부를 가장 먼저 확인하고, 있으면 그 지점부터 이어간다. 이어받은
후 WIP 항목이 해소되면 WIP.md에서 제거(또는 완료 표시)한다.

## 붙여넣을 지침 (여기까지)

---

## 계정별로 다르게 채워야 하는 부분 (있다면)
현재는 레포 URL이 public이라 별도 인증 없이 clone 가능. private으로
바뀌면 인증 절차를 이 지침 위쪽에 추가해야 한다.
