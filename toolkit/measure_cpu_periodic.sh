#!/data/data/com.termux/files/usr/bash
# measure_cpu_periodic.sh (372차 신규)
#
# 목적: 콤마 디바이스의 CPU load/사용률/온도/최상위 프로세스를 SSH로
#       주기적으로 수집해 CSV로 누적한다. 353/354차 이후 "CPU% 정량
#       실측"이 온도계 기준 관찰치만 남아있던 항목을 메꾸기 위한 도구.
#
# 전제(§28): 부팅 직후 수치는 워밍업으로 오염되어 baseline 비교에 부적합.
#           반드시 "부팅 후 충분히 안정화된 상태"에서 여러 회 반복 측정해
#           추세/변동폭을 확보한 뒤 해석할 것 (단발 측정으로 원인 단정 금지).
#
# 사용법:
#   ./measure_cpu_periodic.sh <comma_ip> <interval_sec> <count> [output_csv]
#
# 예:
#   ./measure_cpu_periodic.sh 10.165.186.171 60 20
#   (60초 간격으로 20회, 약 20분간 수집)
#
# 출력 CSV 컬럼:
#   timestamp,uptime_field,load1,load5,load15,cpu_us,cpu_sy,cpu_id,
#   top_proc,top_proc_cpu,temp_max_c
#
# 한계:
#   - top -b -n1 출력이 정확히 7줄 헤더 + 프로세스 목록(swap 라인 포함)
#     형태임을 전제로 8번째 줄을 "최상위 프로세스"로 파싱한다. 콤마
#     펌웨어/커널 버전에 따라 헤더 줄 수가 다르면 top_proc/top_proc_cpu
#     컬럼이 어긋날 수 있으니 최초 1회는 CSV를 육안 검증할 것.
#   - uptime_field는 "up 13 min" 같은 짧은 형식만 안전하게 파싱된다.
#     "up 1 day, 2:34" 형식처럼 콤마가 포함되면 컬럼이 밀릴 수 있음
#     (장시간 연속측정 용도가 아니라 부팅 직후~안정화 구간 관찰용이라
#     현재는 허용, 필요 시 후속 세션에서 개선).
#   - GNU grep -P(PCRE) 의존 없이 grep -E/sed/awk만 사용해 Termux
#     기본 환경에서 추가 패키지 설치 없이 동작하도록 작성.

set -euo pipefail

HOST="${1:?사용법: measure_cpu_periodic.sh <comma_ip> <interval_sec> <count> [output_csv]}"
INTERVAL="${2:-60}"
COUNT="${3:-20}"
OUT="${4:-$HOME/cpu_periodic_$(date +%Y%m%d_%H%M%S).csv}"

echo "timestamp,uptime_field,load1,load5,load15,cpu_us,cpu_sy,cpu_id,top_proc,top_proc_cpu,temp_max_c" > "$OUT"

for i in $(seq 1 "$COUNT"); do
  ts=$(date +%Y-%m-%dT%H:%M:%S)

  remote_out=$(ssh "comma@${HOST}" '
    TOP1=$(top -b -n1)
    echo "UPLINE|$(echo "$TOP1" | sed -n "1p")"
    echo "CPULINE|$(echo "$TOP1" | sed -n "3p")"
    echo "PROCLINE|$(echo "$TOP1" | awk "NR==8")"
    echo "TEMPMAX|$(cat /sys/devices/virtual/thermal/thermal_zone*/temp 2>/dev/null | sort -n | tail -1)"
  ' 2>/dev/null || echo "SSH_FAIL|1")

  if echo "$remote_out" | grep -q '^SSH_FAIL|'; then
    echo "[$i/$COUNT] $ts SSH 접속 실패 -- 건너뜀" >&2
    echo "${ts},SSH_FAIL,,,,,,,,,," >> "$OUT"
    [ "$i" -lt "$COUNT" ] && sleep "$INTERVAL"
    continue
  fi

  upline=$(echo "$remote_out"   | grep '^UPLINE|'   | cut -d'|' -f2-)
  cpuline=$(echo "$remote_out"  | grep '^CPULINE|'  | cut -d'|' -f2-)
  procline=$(echo "$remote_out" | grep '^PROCLINE|' | cut -d'|' -f2-)
  tempmax_raw=$(echo "$remote_out" | grep '^TEMPMAX|' | cut -d'|' -f2-)

  uptime_field=$(echo "$upline" | sed -n 's/.*up //p' | cut -d',' -f1 | sed 's/^ *//;s/ *$//')

  load_all=$(echo "$upline" | sed -n 's/.*load average: //p')
  load1=$(echo "$load_all" | cut -d',' -f1 | tr -d ' ')
  load5=$(echo "$load_all" | cut -d',' -f2 | tr -d ' ')
  load15=$(echo "$load_all" | cut -d',' -f3 | tr -d ' ')

  cpu_us=$(echo "$cpuline" | grep -oE '[0-9.]+ us' | awk '{print $1}')
  cpu_sy=$(echo "$cpuline" | grep -oE '[0-9.]+ sy' | awk '{print $1}')
  cpu_id=$(echo "$cpuline" | grep -oE '[0-9.]+ id' | awk '{print $1}')

  top_proc=$(echo "$procline" | awk '{print $NF}')
  top_proc_cpu=$(echo "$procline" | awk '{print $9}')

  temp_max_c=""
  if [ -n "$tempmax_raw" ]; then
    temp_max_c=$(awk -v t="$tempmax_raw" 'BEGIN{printf "%.1f", t/1000}')
  fi

  echo "${ts},${uptime_field},${load1},${load5},${load15},${cpu_us},${cpu_sy},${cpu_id},${top_proc},${top_proc_cpu},${temp_max_c}" >> "$OUT"
  echo "[$i/$COUNT] $ts up=${uptime_field} load1=${load1} top=${top_proc}(${top_proc_cpu}%) temp=${temp_max_c}C"

  if [ "$i" -lt "$COUNT" ]; then
    sleep "$INTERVAL"
  fi
done

echo "완료: $OUT"
echo "(§23: 이 CSV는 대용량이 아니면 재사용 가치 판단 후 devnotes에 직접 커밋하지 말고 work/에 보관 또는 Drive 업로드 권장)"
