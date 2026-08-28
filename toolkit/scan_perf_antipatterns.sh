#!/usr/bin/env bash
# 실시간 루프 파일들에서 CPU/메모리 관련 정적 안티패턴을 grep으로 스캔.
# 101차 이후(carrot_man __init__ 크래시 수정) "전체코드 CPU/메모리 재점검"
# 요청에서 사용한 패턴 모음. 매번 손으로 다시 짜지 말고 이 스크립트 재사용.
#
# 주의: 이건 "의심 위치 찾기" 도구다. 매치된다고 전부 문제인 건 아니고,
# 각 매치는 반드시 컨텍스트(호출 빈도, 게이트 조건, bounded 여부)를
# 직접 읽고 판단해야 한다 -- 오탐(예: 이미 deque(maxlen=...)로 bounded된
# .append(), 이미 readParams 카운트다운으로 캐싱된 .get() 등)이 흔하다.
#
# 사용:
#   bash scan_perf_antipatterns.sh <repo_dir> [추가 파일들...]
#   (파일 인자 없으면 아래 DEFAULT_TARGETS 사용)

set -euo pipefail

REPO_DIR="${1:?repo_dir 필요}"
shift || true

DEFAULT_TARGETS=(
  "selfdrive/carrot/carrot_man.py"
  "selfdrive/carrot/carrot_functions.py"
  "selfdrive/carrot/carrot_serv.py"
  "selfdrive/carrot/carrot_controls.py"
  "selfdrive/carrot/carrot_server.py"
  "selfdrive/controls/controlsd.py"
  "selfdrive/controls/radard.py"
  "selfdrive/controls/plannerd.py"
  "selfdrive/controls/lib/longitudinal_planner.py"
  "selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py"
  "selfdrive/car/cruise.py"
)

TARGETS=("${@:-${DEFAULT_TARGETS[@]}}")

cd "$REPO_DIR"

echo "===== 대상 파일 크기 ====="
for f in "${TARGETS[@]}"; do
  [ -f "$f" ] && wc -l "$f"
done

echo ""
echo "===== deepcopy (dict/object면 .copy()로 대체 가능한지 확인) ====="
grep -n "deepcopy" "${TARGETS[@]}" || echo "(없음)"

echo ""
echo "===== Params() 인스턴스 신규 생성 (self.params 재사용 가능한지 확인) ====="
grep -n "= Params(\|Params()\.get" "${TARGETS[@]}" || echo "(없음)"

echo ""
echo "===== .params.get* 호출 (readParams 카운트다운 캐싱 게이트 안에 있는지 확인) ====="
grep -n "\.params\.get\|\.params_memory\.get" "${TARGETS[@]}" || echo "(없음)"

echo ""
echo "===== print( 호출 (핫루프 매 프레임 실행되는지, f-string 포맷팅 비용 확인) ====="
grep -n "print(" "${TARGETS[@]}" | grep -v "^\s*#" || echo "(없음)"

echo ""
echo "===== re.compile (모듈 레벨이 아니라 함수 내부인지 확인) ====="
grep -n "re\.compile\|import re$" "${TARGETS[@]}" || echo "(없음)"

echo ""
echo "===== threading.Thread( / subprocess. (반복 호출 루프 안인지, 1회성인지 확인) ====="
grep -n "threading\.Thread\|subprocess\." "${TARGETS[@]}" || echo "(없음)"

echo ""
echo "===== .append( (deque(maxlen=..)로 bounded인지, 주기적으로 []/clear()되는지 확인) ====="
grep -n "\.append(" "${TARGETS[@]}" || echo "(없음)"

echo ""
echo "===== self.xxx = {} / dict[key]= 누적 캐시 패턴 (eviction 없이 계속 자라는지 확인) ====="
grep -n "self\.\w\+\s*=\s*{}\s*$" "${TARGETS[@]}" || echo "(없음)"

echo ""
echo "===== for ... in range(len( 비벡터화 순회 (numpy 벡터화 가능한지 확인) ====="
grep -n "for .* in range(len(" "${TARGETS[@]}" || echo "(없음)"

echo ""
echo "(스캔 완료 -- 각 매치는 반드시 sed -n 'N,Mp' <file>로 컨텍스트 확인 후 판단할 것)"
