# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

- 저장 시각: 2026-08-21 (24차, 사용자 "저장" 요청 — a4b5550 HEAD
  대량 배치 로그 분석(15개 zip, 하루치) 중간 지점 체크포인트.
  9/15 라우트(실질 처리 필요 라우트 기준) 완료, 6개 남음.)

## 24차 — a4b5550 HEAD 첫 실주행 로그 대량 배치(15개 zip) 분석 — 진행 중

### 완료된 라우트 (FINDINGS.md 반영 + push 완료)
| 순번 | route_id | 시각 | 길이 | 상태 |
|---|---|---|---|---|
| 1 | `c8fef594d3` (x18seg) | 06:29 | 18분 | **완전 중복**(20차/21차 기존 분석과 이벤트 일치) — 스킵 |
| 2 | `8417c66e7e` (x3seg) | 06:47 | 2분 | ADAS 비활성 저속 이동 — 스킵 |
| 3 | `dda0d533ce` (x20seg) | 10:13 | 20분 | 시내, 클린 + refined danger 2건 |
| 4 | `b1820329bd` (x20seg) | 10:33 | 20분 | 고속도로, **route_summary.py 버그 발견+수정**(vision_radar_crossover highway 필드명 오류, `v_ego_kmh`→`highway`) |
| 5 | `83e6b133f5` (x20seg) | 10:53 | 20분 | 고속도로, **b403d52 조기감속 최초 프레임단위 실측 확인**(레이더 락온 1초 전 이미 감속 시작) |
| 6 | `866476e5c3` (x20seg) | 11:13 | 20분 | 고속도로, 클린, 오탐성 크로스오버 무반응 재확인 |
| 7 | `1723e8b850` (x20seg) | 11:33 | 20분 | 고속도로, 클린 |
| 8 | `203f99d429` (x20seg) | 11:53 | 20분 | 고속도로+저속차 추종, refined danger 3건 = 정상 추종(오탐 아님) |
| 9 | `280302e8ed` (x20seg) | 12:15 | 20분 | 고속도로, 클린 |
| 10 | `f3db6ca89d` (x20seg) | 12:35 | 20분 | 시내+고속 혼합, **source_pair 우세 역전**(model<->vturn 101건이 road<->vturn 49건 처음으로 앞섬) |

### 아직 처리 안 한 라우트 (5개, 다음 세션에서 순서대로 이어갈 것)
1. `20260821_125548_000002ea--d45a15f8fc_x20seg.zip` (12:55, 20분)
2. `20260821_131548_000002eb--7ffb3e693c_x20seg.zip` (13:15, 20분)
3. `20260821_133548_000002ec--3f3884d185_x17seg.zip` (13:35, 17분)
4. `20260821_140107_000002ed--6d6e114aa3_x20seg.zip` (14:01, 20분)
5. `20260821_142017_000002ee--54c822209b.zip` (14:20, 1세그만, ~2분 추정)

원본 업로드 파일들은 `/mnt/user-data/uploads/`에 그대로 남아있음(이번
세션 업로드분, 세션 넘어가면 재업로드 필요할 수 있음 — 다음 세션에서
파일 접근 안 되면 사용자에게 재업로드 요청).

### 처리 방식 (재현용)
```bash
cd /home/claude/work && mkdir routeN && cd routeN
unzip -q /mnt/user-data/uploads/<zip>
cd /home/claude
python3 devnotes/toolkit/extract_log.py /home/claude/work/routeN /home/claude/work/routeN.csv --repo /home/claude/ryu
cd /home/claude/devnotes/toolkit
python3 route_summary.py /home/claude/work/routeN.csv --label "..." > /home/claude/work/routeN_summary.json
# 결과 확인 -> 이상 이벤트 있으면 CSV에서 프레임 단위 추가 대조
# -> FINDINGS.md에 라우트별 섹션 추가, evidence/route_summaries_260821/에 json 복사
# -> push_via_api.py로 즉시 push (라우트 1개당 커밋 1개)
```
raw route.csv/압축해제 폴더는 각 라우트 처리 직후 삭제(개인 주행 데이터
미커밋 방침), route_summary.json만 evidence/에 보존.

### 지금까지 종합 관찰 (5개 남았으므로 최종 결론은 전체 완료 후)
- **종방향 안전 지표(harsh_brake/turn_speed_violation/ttc_danger, 전부
  ADAS 관여 기준) 9개 실주행 라우트 전부 0건** — a4b5550 HEAD 상태
  매우 안정적.
- **b403d52(vision closing-rate) 최초 프레임단위 실측 검증 완료**
  (route5) — 6차 원 제보 증상과 반대로, vision-only 상태에서 이미
  선제 감속 확인. 이 결과는 FINDINGS.md route5 섹션에 상세 기록됨,
  **PARAMS_REGISTRY.md의 VISION_CLOSING_RATE_TAU 항목도 이 실측
  결과로 갱신 필요**(다음 세션에서 반영, 이번 체크포인트에서는
  시간 관계상 FINDINGS.md만 갱신하고 PARAMS_REGISTRY.md는 아직
  미반영 — 잊지 말 것).
- curve_noise_refined 억제율이 라우트마다 62.5%~100%로 변동 — route8
  케이스(3건)는 오탐이 아니라 진짜 저속 추종으로 확인되어, refined
  로직이 실제 위험 상황도 잘 잡아내고 있다는 긍정적 신호로 해석.
- source_pair 우세 쌍이 도로 상황에 따라 달라짐 재확인(고속도로는
  road<->vturn 압도적, 시내+고속 혼합은 model<->vturn 역전) — 20차
  계속 관찰과 일치, road/route/model 각각 별도 히스테리시스 설계
  필요성 뒷받침하는 근거 계속 축적 중.

## 다음 세션에서 이어갈 것 (24차, 최우선)
1. **남은 5개 라우트 순서대로 분석 + push** (위 목록 순서 그대로).
2. 전체 라우트 완료 후 **종합 요약 섹션을 FINDINGS.md에 추가**
   (하루치 전체 통계: 총 주행거리/시간, 안전 이벤트 총계, b403d52
   검증 결과 종합, source_pair 우세 쌍 도로 유형별 패턴 정리) +
   `LAST_ANALYZED.md` 최종 갱신.
3. **PARAMS_REGISTRY.md에 route5 b403d52 실측 검증 결과 반영**
   (VISION_CLOSING_RATE_TAU 항목 — 아직 미반영, 잊지 말 것).
4. route3의 `vision_radar_crossover count_highway_est=0`이 이번에
   발견된 버그(수정 전 결과) 영향인지 재확인 필요 여부 검토(route3는
   시내 위주라 실제로도 낮았을 가능성 높지만 완전히 배제 안 됨,
   FINDINGS.md route4 섹션에 이미 메모됨).

## 이전 세션들 요약 (24차 이전, 이미 push됨) — 아래 기록은 보존용
- 21차까지: would_trigger_ttc_danger 개선 설계+검증(표본 5건),
  9~23차 vturn↔model 게이팅/vision closing-rate/model_turn_speed 추세
  게이팅 등 다수 패치 실차 적용+검증 완료. 상세는 FINDINGS.md 각
  세션 섹션 참고.

## 다음 세션 시작 시
이 WIP.md가 존재하면 "24차 — 아직 처리 안 한 라우트" 목록부터
순서대로 이어감. 처리 완료된 라우트는 목록에서 제거하고 "완료된
라우트" 표에 추가. 전체 완료되면 이 WIP.md의 24차 섹션 전체를
"완료, 재작업 불필요"로 표시하고 다음 체크포인트에서 정리.
