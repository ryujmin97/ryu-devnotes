# ryu-devnotes

`ryujmin97/ryu`(openpilot 포크, comma 기기에 실배포되는 코드) 개발을
위한 분석/이슈 트래커 저장소. **코드가 아니라 분석 산출물**만 들어있다 —
comma 기기에 이 레포가 pull될 일은 없고, Claude 세션(어느 계정에서든)
+ Master의 로컬 작업 양쪽에서 참조하는 "공유 메모리" 용도.

## 왜 `ryu` 본 레포에 안 넣고 분리했나
`ryu`는 기기에 실배포되는 코드라 커밋 이력 자체가 제품이다. 분석 노트나
튜닝 상수 트래커를 섞으면 배포 파이프라인에 불필요한 걸 신경 써야 하고,
용량도 커진다. 그래서 물리적으로 분리했다.

## 파일 구성
- `SETUP.md`      : 새 세션(어느 계정이든) 시작할 때 맨 처음 실행할 명령어
- `FINDINGS.md`   : 발견한 버그/이슈, 검증 상태 누적 기록
- `LAST_ANALYZED.md` : 브랜치별 "여기까지 분석했다" 커밋 해시 기록
- `PARAMS_REGISTRY.md` : 여러 파일에 흩어진 튜닝 상수 한곳에 정리
- `analyze_commits.sh` : LAST_ANALYZED.md 기준으로 신규 커밋만 뽑아
  핵심 파일 diff까지 자동 출력하는 스크립트
- `toolkit/` : rlog 디코딩 + CSV 추출 + 후처리 헬퍼 (구 Claude 프로젝트 파일,
  여기로 이전)

## 워크플로우
1. 세션 시작: `SETUP.md`대로 `ryu-devnotes` + `ryu`(코드) 둘 다 clone
2. `LAST_ANALYZED.md`로 어디까지 분석했는지 확인 → 신규 커밋만 검토
3. 로그 있으면 `toolkit/extract_log.py`로 CSV 추출 → `analysis_helpers.py`로 분석
4. 발견사항/검증결과는 `FINDINGS.md`에 추가, 상수 만졌으면 `PARAMS_REGISTRY.md` 갱신
5. 세션 끝날 때 `LAST_ANALYZED.md` 갱신
6. 코드 패치와 마찬가지로, Claude는 push 권한이 없으므로 갱신된 파일들을
   `/mnt/user-data/outputs/`에 만들어 전달 → Master가 로컬에서 commit + push

## 로컬 경로 (Master 기준)
- devnotes 로컬 clone: `C:\dev\ryu-devnotes`
- ryu(코드) 로컬 clone: `C:\dev\ryu`
- 패치 파일: `C:\dev\patch`
