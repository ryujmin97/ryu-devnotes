# 모바일(Termux) 작업 절차

이 문서는 스마트폰 + Termux 환경에서 devnotes/ryu 결과물을 받아 push하는 절차를 정의한다.
PC(PowerShell/Windows) 절차와는 완전히 별개이며, 두 절차를 섞지 않는다.

## 사전 준비 (최초 1회)
termux-setup-storage
ls ~/storage/downloads/

## 파일 수신 후 반영 절차
1. 다운로드 -> /storage/emulated/0/Download 에 저장됨
2. cd ~/ryu-devnotes && cp ~/storage/downloads/WIP.md ./WIP.md (실제 파일명으로 교체)
3. git status (변경사항 잡히는지 확인)
4. git add -A && git commit -m "N차: 요약" && git push
5. push 성공 후: rm ~/storage/downloads/WIP.md

## 코드 패치(ryu) 수신 시
cd ~/ryu
git pull origin c3-ms-dev
cp ~/storage/downloads/0001-xxx.patch ./0001-xxx.patch
git am 0001-xxx.patch
git push origin c3-ms-dev
rm ~/storage/downloads/0001-xxx.patch

## 주의사항
- git status가 clean이면 cp가 반영 안 된 것 -> 원인 확인 전엔 다운로드 파일 삭제 금지
- push 전엔 항상 git pull/fetch로 원격에 모르는 커밋 있는지 먼저 확인

