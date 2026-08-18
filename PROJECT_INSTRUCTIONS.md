# Claude 프로젝트 지침 (Project Instructions / Custom Instructions)

아래 내용을 어느 계정이든 Claude 프로젝트(claude.ai) 생성 시
"프로젝트 지침" / "Custom instructions" 칸에 그대로 붙여넣으면 된다.
**파일 업로드가 아니라 텍스트 지침**이라 계정을 새로 만들거나 프로젝트를
새로 파도 이 텍스트 한 번만 붙여넣으면 동일한 워크플로우가 재현된다.
(devnotes 레포 자체가 SETUP.md/FINDINGS.md 등을 갖고 있으므로, 이 지침은
"세션 시작하면 devnotes부터 clone해서 그 안의 지시를 따르라"는 진입점
역할만 한다.)

---

## 붙여넣을 지침 (여기부터)

이 프로젝트는 openpilot 포크(`ryujmin97/ryu`, Genesis DH 2015/2016 대상)의
종방향 제어 로직 개선 작업이다. 주 요청 유형: 최신 커밋 분석, 실주행 로그
분석, 문제점/원인 파악, 대안 제시, 패치 적용.

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
- 세션 끝나면 devnotes 안의 해당 파일들을 갱신해서
  `/mnt/user-data/outputs/`에 만들어 전달 (push 권한 없음 -- 사람이
  로컬에서 commit/push)

코드 수정 요청 시: 패치 파일을 만들어 `/mnt/user-data/outputs/`에 두고,
적용용 PowerShell 명령어(`git am` 등)를 함께 제공한다. 직접 push하지
않는다 (권한 없음).

## 붙여넣을 지침 (여기까지)

---

## 계정별로 다르게 채워야 하는 부분 (있다면)
현재는 레포 URL이 public이라 별도 인증 없이 clone 가능. 만약 나중에
`ryu-devnotes`를 private으로 바꾸면, 이 지침 위쪽에 "GitHub PAT을
`~/.netrc`나 clone URL에 넣는 법" 같은 계정별 인증 절차를 한 문단 추가해야
한다 (지침 텍스트 자체는 계정마다 동일해도, PAT 값은 계정/세션마다 다를
수 있으므로 지침엔 "어디서 가져와서 어떻게 넣으라"는 절차만 적고 실제 값은
적지 않는 게 안전).
