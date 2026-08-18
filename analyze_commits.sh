#!/usr/bin/env bash
# 최신 커밋 분석 자동화.
# LAST_ANALYZED.md에 기록된 지점 이후의 커밋만 뽑아서
# 목록 + 핵심 파일(longitudinal/radar/carrot) diff까지 한 번에 출력.
#
# 사용:
#   bash analyze_commits.sh <repo_dir> <branch> [since_commit]
#
# since_commit을 생략하면 LAST_ANALYZED.md에서 해당 브랜치의
# last_analyzed_commit을 자동으로 찾아서 씀 (파일이 repo_dir 상위 또는
# 프로젝트 폴더에 있다고 가정, --last-file로 경로 지정 가능).
#
# 예:
#   bash analyze_commits.sh /home/claude/ryu c3-ms-dev
#   bash analyze_commits.sh /home/claude/ryu c3-ms-dev 8dbed620887b

set -euo pipefail

REPO_DIR="${1:?repo_dir 필요}"
BRANCH="${2:?branch 필요}"
SINCE="${3:-}"
LAST_FILE="${LAST_ANALYZED_FILE:-/mnt/project/LAST_ANALYZED.md}"

# 관심 파일: 종방향/레이더/커롯 로직 위주. 필요하면 여기 추가.
WATCH_FILES=(
  "selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py"
  "selfdrive/controls/radard.py"
  "selfdrive/carrot/carrot_functions.py"
  "selfdrive/carrot/carrot_man.py"
  "selfdrive/carrot/carrot_serv.py"
)

cd "$REPO_DIR"
git fetch origin "$BRANCH" --quiet || true
git checkout "$BRANCH" --quiet 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH" --quiet

if [ -z "$SINCE" ] && [ -f "$LAST_FILE" ]; then
  SINCE=$(awk -v b="## $BRANCH" '
    $0==b {found=1; next}
    found && /^## / {found=0}
    found && /last_analyzed_commit:/ {
      match($0, /`([a-f0-9]+)`/, arr); print arr[1]; exit
    }
  ' "$LAST_FILE" 2>/dev/null || true)
fi

echo "=== branch: $BRANCH ==="
echo "=== since: ${SINCE:-<repo 시작부터, LAST_ANALYZED.md에 기록 없음>} ==="
echo

RANGE="HEAD"
if [ -n "$SINCE" ]; then
  RANGE="${SINCE}..HEAD"
fi

N=$(git rev-list --count "$RANGE" 2>/dev/null || echo 0)
if [ "$N" = "0" ]; then
  echo "새 커밋 없음. 현재 HEAD: $(git rev-parse --short HEAD)"
  exit 0
fi

echo "--- 커밋 목록 ($N개) ---"
git log --oneline "$RANGE"
echo

echo "--- 관심 파일 변경 diff (신규 커밋 범위 내) ---"
for f in "${WATCH_FILES[@]}"; do
  if git log --oneline "$RANGE" -- "$f" | grep -q .; then
    echo "### $f"
    git log -p "$RANGE" -- "$f"
    echo
  fi
done

echo "--- 그 외 변경된 파일 (관심 파일 목록에 없는 것들) ---"
git diff --stat "$RANGE" -- . $(printf ':(exclude)%s ' "${WATCH_FILES[@]}")

echo
echo "현재 HEAD: $(git rev-parse --short HEAD) (분석 끝나면 LAST_ANALYZED.md 갱신할 것)"
