# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

- 저장 시각: 2026-08-21 (24차 계속, a4b5550 HEAD 대량 배치 로그
  분석(15개 zip, 하루치) — 실질 처리 필요 라우트 12/15 완료,
  3개는 이번 세션에 업로드되지 않아 미분석 상태로 대기.)

## 24차 — a4b5550 HEAD 첫 실주행 로그 대량 배치(15개 zip) 분석 — 거의 완료

### 완료된 라우트 (FINDINGS.md 반영 완료, push 대기 중)
| 순번 | route_id | 시각 | 길이 | 상태 |
|---|---|---|---|---|
| 1 | `c8fef594d3` (x18seg) | 06:29 | 18분 | **완전 중복**(20차/21차 기존 분석과 이벤트 일치) — 스킵 |
| 2 | `8417c66e7e` (x3seg) | 06:47 | 2분 | ADAS 비활성 저속 이동 — 스킵 |
| 3 | `dda0d533ce` (x20seg) | 10:13 | 20분 | 시내, 클린 + refined danger 2건 |
| 4 | `b1820329bd` (x20seg) | 10:33 | 20분 | 고속도로, route_summary.py 버그 발견+수정 |
| 5 | `83e6b133f5` (x20seg) | 10:53 | 20분 | 고속도로, **b403d52 조기감속 최초 프레임단위 실측 확인** |
| 6 | `866476e5c3` (x20seg) | 11:13 | 20분 | 고속도로, 클린, 오탐성 크로스오버 무반응 재확인 |
| 7 | `1723e8b850` (x20seg) | 11:33 | 20분 | 고속도로, 클린 |
| 8 | `203f99d429` (x20seg) | 11:53 | 20분 | 고속도로+저속차 추종, refined danger 3건 = 정상 추종 |
| 9 | `280302e8ed` (x20seg) | 12:15 | 20분 | 고속도로, 클린 |
| 10 | `f3db6ca89d` (x20seg) | 12:35 | 20분 | 시내+고속 혼합, **source_pair 우세 역전**(model<->vturn > road<->vturn) |
| 11 | `3f3884d185` (x17seg) | 13:35 | 16.8분 | 시내 위주, 클린(종방향), curve_noise refined 8건(진짜 접근 확인), source_pair model≈road 동률 |
| 12 | `54c822209b` (1seg) | 14:20 | 9.8초 | ADAS 비활성 극단문 — 스킵 |

### 아직 처리 못함 (3개, 이번 세션에 업로드 안 됨 — 재업로드 필요)
1. `20260821_125548_000002ea--d45a15f8fc_x20seg.zip` (12:55, 20분)
2. `20260821_131548_000002eb--7ffb3e693c_x20seg.zip` (13:15, 20분)
3. `20260821_140107_000002ed--6d6e114aa3_x20seg.zip` (14:01, 20분)

**다음 세션에서 사용자에게 위 3개 zip 재업로드를 먼저 요청할 것.**
업로드되면 route13/14/15로 이어서 동일한 처리 방식(아래) 적용 후,
FINDINGS.md에 "24차 최종 완료" 종합 섹션 추가하고 이 WIP.md의 24차
항목 전체 제거.

### 처리 방식 (재현용)
```bash
cd /home/claude/work && mkdir routeN && cd routeN
unzip -q /mnt/user-data/uploads/<zip>
cd /home/claude
python3 devnotes/toolkit/extract_log.py /home/claude/work/routeN /home/claude/work/routeN.csv --repo /home/claude/ryu
cd /home/claude/devnotes/toolkit
python3 route_summary.py /home/claude/work/routeN.csv --label "..." > /home/claude/work/routeN_summary.json
# 결과 확인 -> 이상 이벤트 있으면 CSV에서 프레임 단위 추가 대조
# -> FINDINGS.md에 라우트별 섹션 추가, evidence/route_summaries_260821/에
#    route_e<hex접미사>_<routeid>.json 이름으로 복사 (예: 000002ea -> route_ea_...)
# -> push_via_api.py로 즉시 push (라우트 1개당 커밋 1개, 또는 모아서 일괄)
```
raw route.csv/압축해제 폴더는 각 라우트 처리 직후 삭제(개인 주행 데이터
미커밋 방침), route_summary.json만 evidence/에 보존.

### 종합 관찰 (12/15 라우트 기준, 최종 결론은 나머지 3개 완료 후)
- **종방향 안전 지표(harsh_brake/turn_speed_violation/ttc_danger, 전부
  ADAS 관여 기준) 10개 실질 라우트 전부 0건** — a4b5550 HEAD 상태
  매우 안정적.
- **b403d52(vision closing-rate) 최초 프레임단위 실측 검증 완료**
  (route5) — PARAMS_REGISTRY.md VISION_CLOSING_RATE_TAU 항목 갱신
  완료(이번 세션 반영함, 이전 체크포인트의 "미반영" 이슈 해소).
- curve_noise_refined 억제율이 라우트 유형에 따라 분화(고속도로
  87.5~100% vs 저속추종/시내혼합 55.6~62.5%) — 낮은 케이스들 프레임
  대조 결과 전부 오탐 아닌 정상 위험 포착으로 확인.
- source_pair 우세 쌍이 도로 상황에 따라 달라짐 계속 재확인(고속도로는
  road<->vturn 압도적, 시내+고속 혼합은 model<->vturn 역전 또는 동률).

## 다음 세션에서 이어갈 것 (24차 마무리, 최우선)
1. **사용자에게 남은 3개 zip 재업로드 요청** (위 목록).
2. 3개 라우트 순서대로 분석 + push.
3. 전체 라우트(15개) 완료 후 **최종 종합 요약을 FINDINGS.md에 추가**
   (하루치 전체 통계) + `LAST_ANALYZED.md` 최종 갱신(현재는 "12/15
   완료, 3개 미완료" 상태로 기록됨 — 완료 후 갱신 필요).
4. route3의 `vision_radar_crossover count_highway_est=0`이 버그 영향
   인지 재확인 필요 여부 검토(낮은 우선순위, FINDINGS.md route4
   섹션에 메모됨).

## 이전 세션들 요약 (24차 이전, 이미 push됨) — 아래 기록은 보존용
- 21차까지: would_trigger_ttc_danger 개선 설계+검증(표본 5건),
  9~23차 vturn↔model 게이팅/vision closing-rate/model_turn_speed 추세
  게이팅 등 다수 패치 실차 적용+검증 완료. 상세는 FINDINGS.md 각
  세션 섹션 참고.

## 다음 세션 시작 시
이 WIP.md가 존재하면 "다음 세션에서 이어갈 것" 목록부터 순서대로
이어감(1번: 재업로드 요청이 최우선). 나머지 3개 라우트 처리 완료되면
이 WIP.md의 24차 섹션 전체를 삭제하고 다음 체크포인트에서 정리.
