#!/bin/bash
# radard 크래시(sccFallback capnp 스키마 위반) 긴급 수정 + 커밋 + push
# 기기(C3X) SSH 터미널에서 실행. REPO 경로가 다르면 아래 변수를 먼저 수정하세요.
set -e
REPO="/data/openpilot"
FILE="$REPO/selfdrive/controls/radard.py"

if [ ! -f "$FILE" ]; then
  echo "!! $FILE 을 찾을 수 없습니다. REPO 경로를 확인해주세요."
  exit 1
fi

cd "$REPO"

echo "== 현재 브랜치/원격 확인 =="
git branch --show-current
git remote -v

cp "$FILE" "$FILE.bak_$(date +%s)"

python3 << 'PYEOF'
import re
path = "/data/openpilot/selfdrive/controls/radard.py"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

src = src.replace(
    "def get_RadarState(self, model_prob: float = 0.0, vision_y_rel=0.0, scc_fallback: bool = False):",
    "def get_RadarState(self, model_prob: float = 0.0, vision_y_rel=0.0):"
)
src = re.sub(
    r'\n\s*# 37차: track_scc\(단일점 SCC 폴백, 차로내 위치 무검증 채택\) 유래인지 표시\.\n'
    r'\s*# True면 RadarD\.update\(\)에서 LeadBlend 우회\(즉시 반영\)를 하지 않고\n'
    r'\s*# cutout/danger-passthrough 로직을 계속 태운다\.\n'
    r'\s*"sccFallback": bool\(scc_fallback\),\n',
    '\n',
    src
)
src = src.replace(
    "lead_one_raw, self.radar_detected = self.get_lead(sm['carState'], md, alive_tracks, 0, leads_v3[0], model_v_ego, low_speed_override=False)\n      if lead_one_raw.get('radar') and not lead_one_raw.get('sccFallback'):",
    "lead_one_raw, self.radar_detected, lead_one_scc_fallback = self.get_lead(sm['carState'], md, alive_tracks, 0, leads_v3[0], model_v_ego, low_speed_override=False)\n      if lead_one_raw.get('radar') and not lead_one_scc_fallback:"
)
src = src.replace(
    "self.radar_state.leadTwo, _ = self.get_lead(sm['carState'], md, alive_tracks, 1, leads_v3[1], model_v_ego, low_speed_override=False)",
    "self.radar_state.leadTwo, _, _ = self.get_lead(sm['carState'], md, alive_tracks, 1, leads_v3[1], model_v_ego, low_speed_override=False)"
)
src = src.replace(
    "lead_dict = track.get_RadarState(lead_msg.prob, self.vision_tracks[0].yRel, scc_fallback=used_scc_fallback)",
    "lead_dict = track.get_RadarState(lead_msg.prob, self.vision_tracks[0].yRel)"
)
src = src.replace(
    "    return lead_dict, radar\n",
    "    return lead_dict, radar, used_scc_fallback\n"
)

if src == orig:
    print("!! 아무것도 바뀌지 않았습니다 -- 파일이 예상과 다를 수 있습니다. 수동 확인 필요, 중단합니다.")
    raise SystemExit(1)

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print(">> radard.py 수정 완료.")

import ast
ast.parse(open(path).read())
print(">> 문법(ast) 검증 통과.")
PYEOF

echo "== diff 미리보기 =="
git diff -- selfdrive/controls/radard.py

echo ""
echo "== 커밋 + push =="
git add selfdrive/controls/radard.py
git commit -m "radard: sccFallback 딕셔너리 키로 인한 radard 크래시 긴급 수정 (37차 후속)"
git push

echo ""
echo ">> 완료. 이제 재부팅해서 radard 정상 기동 확인하세요."
