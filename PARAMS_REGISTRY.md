# PARAMS_REGISTRY — 튜닝 상수 레지스트리

여러 파일에 흩어진 튜닝 상수를 한곳에서 추적. 값이 바뀌면 이 표도 같이
갱신. "검증상태" 컬럼이 NEEDS_VALIDATION인 항목은 로그 분석 요청 시
우선순위로 챙길 것.

## selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| MARGIN_ACCEL_GATE_FULL / NONE | 1.5 / 1.0 | 여유거리 클수록 aLead 흔들림 무시 (dRel/desired_distance 비율 기준) | **한계 확인(38차)** — desired_distance가 고속에서 커지는 탓에 TTC 15s대 안전 구간에서도 이 비율만으론 weight=1(무감쇠) 고정되는 경우 확인. 아래 LEAD_ACCEL_TTC_GATE_*와 min() 결합으로 보완 시도(패치 작성, 미적용). 이 상수 자체(1.5/1.0)는 여전히 NEEDS_VALIDATION |
| LEAD_ACCEL_TTC_GATE_FULL / NONE | 12.0s / 6.0s | (38차 신규) TTC 기반 aLead damping 게이트, MARGIN_ACCEL_GATE와 min()으로 결합 | NEEDS_VALIDATION (2026-08-22, 38차 신규 도입 — 로직 단위 검증만 완료. **39차: 저속 구간에서 이 게이트 자체는 정상 동작하나, dRel이 작아 TTC가 급격히 붕괴하면서 weight가 순간적으로 튀는 부작용 발견 → LEAD_ACCEL_WEIGHT_RISE_RATE로 보완(아래 항목).** **41차: 신규 실차 로그(HEAD `c31ddca`)에서 안전지표 전부 0건, 사용자 체감 양호 — 회귀 징후 없음. 단 이 게이트가 직접 개입한 프레임을 특정 검증하진 못함.** 실차 acados 파이프라인 상세 승차감 검증은 여전히 미완. FINDINGS.md 38차/39차/41차 참고) |
| LEAD_ACCEL_WEIGHT_RISE_RATE | 1.0 (1/s) | (39차 신규) 위 TTC/거리 게이트의 결합 weight가 "감쇠 풀리는 방향(상승)"으로 바뀔 때 사이클당 변화폭 제한(0→1 최소 1초). TTC<=LEAD_ACQ_TTC_DANGER(2.5s)인 실제위험 시엔 우회, 즉시 weight=1.0 | NEEDS_VALIDATION (2026-08-22, 39차 신규 도입 — 저속 로그 수치 시뮬레이션(rlog 재파싱 기반)으로 peak |aLead| 완화 확인. **패치 적용/push 완료(origin/c3-ms-dev HEAD `52668ec`)**, acados MPC 파이프라인 재실행/실차 검증은 아직 안 됨. **41차: 신규 로그(HEAD `c31ddca`)에서 저속 급정지 느낌 재발 징후 없음(harsh_brake 0건, 사용자 체감 양호)이나 이 패치가 실제로 개입한 프레임을 직접 특정하진 않음 — 간접 확인 수준.** **45차: bypass 활성 중(아래 LAUNCH_BYPASS_*)엔 이 rise-rate 제한도 함께 우회하도록 변경 — 정차→출발 구간에서만 적용되는 예외라 39차 원 목적(저속 TTC 붕괴형 급정지 방지)엔 영향 없음.** FINDINGS.md 39차/41차/45차 참고) |
| LAUNCH_BYPASS_STOP_V_EGO / EXIT_V_EGO | 0.3 m/s / 5.0 m/s | (45차 신규) 정차→출발 구간에서 LEAD_ACCEL_TTC_GATE_*(38차)를 완전 우회하고 dist_w(MARGIN_ACCEL_GATE)만으로 aLead damping을 결정. v_ego<STOP에서 정차 판정(bypass arm), v_ego>=EXIT에서 출발 완료 판정(38/39차 로직 복귀) | NEEDS_VALIDATION (2026-08-22, 45차 신규 도입 — "정지 후 출발 가속 약화"(ttc_accel_weight의 closing<=0.1→weight=0 분기가 launch 구간의 v_ego<=v_lead와 겹쳐 aLeadK를 통째로 지우는 부작용) 근본원인 대응. `work/test_launch_bypass.py` 합성 시나리오 4종(정차중 출발/bypass 중 exit 전환/고속 잡음 회귀/저속 danger cut-in 회귀)으로 로직 단위 검증 완료 — exit 순간 w가 즉시 하강할 수 있음(rise-rate 미적용, 기존 "감쇠 방향은 즉시 반영" 컨벤션과 일치, 의도된 동작)을 확인. 실차 acados 파이프라인/실주행 재현 검증은 아직 없음. `git am` temp branch 검증(base `c31ddca`) + py_compile 통과. FINDINGS.md 45차 참고) |
| LOW_SPEED_GAP_OPEN_V_EGO_GATE / A_LEAD_THRESH / ACCEL_CAP / MARGIN_RATIO | 40/3.6 m/s(~40km/h) / 1.0 m/s² / 0.5 m/s² / 1.5(=MARGIN_ACCEL_GATE_FULL 재사용) | (117차 신규, 6님 제보 대응) 저속+이미 desired_distance보다 충분히 벌어진(gap_ratio) 상태에서 앞차가 강하게 멀어질 때만 a_lead에 상한을 건다. margin_accel_weight()/ttc_accel_weight()는 둘 다 위험(closing) 방향 감쇠만 있고 멀어지는 방향엔 damping이 없어 a_lead가 그대로 MPC에 반영되던 것이 원인. launch bypass 중엔 게이트 자체가 닫힘(45차 재발 방지) | NEEDS_VALIDATION (2026-08-29, 116차 설계+합성검증(A~E) 전부 PASS, 117차 patch 적용/push 완료(commit 예정, 아래 WEIGHT_RISE_RATE 항목 참고). 실측 로그(lowspeed_a/b/c 등) replay 검증 아직 없음. FINDINGS.md 116/117차 참고) |
| LOW_SPEED_GAP_OPEN_WEIGHT_RISE_RATE | 1.0 (1/s) | (117차 신규) 위 캡을 하드클램프 대신 블렌드 weight(0=무캡~1=완전캡)로 적용하고, 그 weight의 사이클당 변화폭을 제한(0<->1 최소 1초, 진입/해제 양방향 모두). 39차(LEAD_ACCEL_WEIGHT_RISE_RATE)와 동일 패턴이나 그쪽은 rising(위험해지는) 방향만 제한한 반면 이쪽은 "위험 신호"가 아니라 "가속 상한"이라 켜질 때/꺼질 때 둘 다 완만화가 필요해 양방향 제한. launch bypass 중엔 이 rise-rate 제한도 즉시 우회(cap_w=0 강제, 45차와 동일 defense-in-depth 원칙) | NEEDS_VALIDATION (2026-08-29, 117차 신규 도입 — 116차 F에서 발견된 하드클램프 단차(최대 1.5 m/s²)가 `toolkit/sim_gap_open_damping.py` 시나리오 G에서 0.075 m/s²/cycle로 감소함을 확인(95% 감소, 이론상 RISE_RATE×dt×discontinuity와 일치). 시나리오 H(bypass 중 완만화 즉시 우회)/I(정착 후 하드클램프와 동일 정상상태 도달) 포함 신규 9개 시나리오 전부 PASS. `git am` temp branch 검증(base `8a7baa0`) diff 0 + py_compile 통과. 실측 로그 replay/실차 검증은 아직 없음. FINDINGS.md 117차 참고) |
| LEAD_ACQ_RAMP_TIME | 5.0s | 리드 인식 후 선제감속 하한선 도달 시간 | NEEDS_VALIDATION (2026-08-18 x12seg 로그에서 첫 적합 사례 확보, seg10 t=657.39 — 매끈한 감속으로 긍정적. 표본 1건, 추가 검증 필요) |
| LEAD_ACQ_MIN_V_EGO | 3.0 m/s | 이 속도 미만 미적용 | - |
| LEAD_ACQ_CONFIRM_TIME | 0.2s | 블립 무시, 램프 시작 조건 | - |
| LEAD_ACQ_LOSS_GRACE_TIME | 0.5s | 순간유실 허용 시간 | **재검토 필요, 감사 도구 준비됨(2026-08-21)** (2026-08-20, 260819-2 분석 중 extract_log.py가 세그먼트 경계마다 leadStatus를 인위적으로 False 리셋하는 도구 버그 확인 — 해당 라우트 순간유실 16건 전부 세그먼트 경계와 diff=0.000s로 정확히 일치, 실제 유실 아닌 추출 아티팩트. 과거 누적 증거(x11seg 4건+x16seg 1건+x20seg(260819-1) 6~7건)도 세그먼트 경계 여부 재대조 필요 — 특히 0.3s 이하 짧은 유실은 아티팩트 의심, 1s+ 긴 유실은 실사례 가능성 유지. **2026-08-21: 근본 원인 수정 완료** — `extract_log.py`가 이제 세그먼트 간 leadStatus 상태를 이어받아 신규 추출분엔 이 아티팩트가 없음(`meta.json.segment_state_carryover_fix=true`로 확인 가능). 과거 CSV 재대조용으로 `analysis_helpers.segment_boundary_lead_loss_artifacts()` 추가됨 — 다음 로그 분석 세션에서 이 함수로 x11/x16/x20seg 재대조 실행 예정, 아직 미실행. 상세는 FINDINGS.md 참고) |
| LEAD_ACQ_TTC_DANGER | 2.5s | TTC 이하면 frac=1.0 즉시 | NEEDS_VALIDATION |
| LEAD_ACQ_TTC_CAUTION | 6.0s | TTC 이상이면 TTC 성분 미개입 | NEEDS_VALIDATION |
| VISION_CLOSING_RATE_TAU | 1.0s | vision-only dRel 미분 접근속도 저역통과 시정수 | PARTIALLY_VALIDATED, **알려진 한계 2건(23차), 곡선 노이즈 탐지 도구 준비됨(2026-08-21)** (2026-08-20 신규 도입, 17차 첫 실측(closing 크로스오버 6건 매끈), 22차 원거리 TTC 캐션 문턱 구조적 한계 확인(개선안 3가지 제안, `a4b5550`로 3번 적용). **23차: 개선안 3번(grace 수정) 실차 첫 검증 — grace 로직 자체는 정상 동작(14건 blip-preserved 확인, 회귀 없음). 단 22차가 겨냥한 정확한 증상(vision 과소평가→레이더 락온 급감속)의 재현 사례가 이번 로그엔 없어 "패치가 실제로 그 증상을 줄였는지"는 미확인. 신규 발견: 곡선(`src=vturn`) 구간에서 dRel이 여러 물체 사이를 널뛰며 이 TAU 필터에 노이즈성 DANGER급 rate를 유발할 수 있음(routeB seg12 t=815/817, dRel_closed 전체는 양수인데 순간 rate가 -12~-25로 튐, 레이더 락온 후 실제로는 vRel+4.4~+6.1로 멀어지는 중이었음) — 이번엔 실제 aEgo 반응 없었으나 원인 미확인(운 좋게 무해했을 가능성). FINDINGS.md 23차 참고, 1/2/4번안 설계 전 곡선 노이즈 필터링 선행 검토 필요**. **2026-08-21: 선행검토용 도구 `analysis_helpers.curve_lead_dRel_jump_events()`/`curve_noise_summary()` 추가됨(toolkit/CHANGELOG.md 참고), 합성 데이터로 검증 완료. 실제 routeA/routeB 및 향후 로그로 발생 빈도 측정은 다음 로그 분석 세션에서 — 아직 미실행.** **24차(2026-08-21): route5(고속도로, HEAD `a4b5550`)에서 프레임 단위 최초 실측 검증 완료 — seg6 t=2817.53~2819.53(가장 큰 폭 접근, dRel_closed 41.4m/1.99s) 대조 결과, `leadRadar=False`(vision-only) 상태이던 t=2818.53부터 aEgo가 이미 감속 시작(-0.90→-1.31→-1.08), `leadRadar=True`로 전환되는 t=2819.53보다 **1초 먼저** 선제 감속 확인. 이후 레이더 락온 전후 감속 전환도 매끄러움(-0.94~-1.45 범위, 단절 없음, 최대 감속 약 -1.45m/s² 온건). 6차 원 제보 증상("카메라 인식 시점엔 감속 없다가 레이더 락온 순간 급감속")과 **정반대 결과** — 현재 TAU=1.0s/MIN_TIME=0.5s 설정이 의도대로 유효 작동 중인 것으로 판단. 이후 route4~11(고속도로 6개 + 시내혼합 2개, 총 10개 라우트) crossover 이벤트 다수의 오탐성 크로스오버(노이즈성 dRel 스냅)도 확인했으나 전부 시스템 무반응(aEgo 정상 범위 유지) — 과잉반응 없음 재확인. 근거: FINDINGS.md 24차 route5/route4/route6 섹션. VALIDATED로 상태 상향 검토 가능하나, 여전히 표본이 "온건한 접근" 케이스 위주이고 급접근(harsh) 케이스의 실측은 아직 없어 PARTIALLY_VALIDATED 유지 권장.**) |
| VISION_CLOSING_RATE_MIN_TIME | **0.5s** (정정, 최초 1.0s에서 단축) | 이 시간 이상 연속추적 후에만 dRel 미분 TTC 신뢰 | VALIDATED (2026-08-20, 사용자 피드백으로 1.0s→0.5s 단축. 22차: leadStatus 짧은 깜빡임마다 무조건 리셋되는 부작용 발견, 개선안 3번(grace 적용) 제안. **23차: 개선안 3번 실차(`a4b5550`) 첫 실측 — routeA 1건/routeB 13건 blip-preserved 이벤트 확인, grace 이내에선 리셋 안 되고 값 유지하며 이어서 누적되는 것 정상 동작 확인, 회귀 없음. 이 파라미터 자체(0.5s 문턱)의 적절성 재검토는 불필요 — 리셋 버그가 진짜 원인이었고 이제 해소됨.** FINDINGS.md 22차/23차 참고**) |
| VISION_CLOSING_RATE_MAX_PLAUSIBLE | 30.0 m/s | raw_rate 클램프 상한(접근 방향만) | VALIDATED (2026-08-21, 26차 신설, 합성검증. **36차(2026-08-22): 실차 acados MPC 파이프라인에서 frac_rate 게이트가 정상 활성화됨을 실측 확인(카메라인식/정치차량 로그) — 클램프 자체가 게이트 계산 경로 안에 있어 함께 검증된 것으로 간주, VALIDATED로 상향.** 근거: FINDINGS.md 36차) |
| VISION_CLOSING_RATE_MEDIAN_WINDOW | 3 frames | 클램프된 rate의 중앙값 필터 윈도우 | VALIDATED (2026-08-21, 26차 신설, 합성검증. **36차: 위와 동일 사유로 VALIDATED 상향** — 실차 로그에서 raw dRel/vRel이 프레임 단위로 크게 튀는데도(카메라인식 route 다수 구간) frac_rate 출력 자체는 매끈하게 이어져 중앙값 필터가 실제로 스냅 노이즈를 억제하고 있는 것으로 관찰됨. 근거: FINDINGS.md 36차) |
| VISION_CLOSING_RATE_GATE_CAUTION | **-2.2 m/s** (26차 최초 -5.5 → 30/31차 재설계로 확정) | filt rate 절대값 게이트, 이 값 이상이면 frac_rate=0 | VALIDATED (2026-08-21. 26차 최초값(-5.5, LEAD_ACQ_TTC_*와 동일 재사용)은 28차 세그7/세그12 실측 대조로 과보수 확정(실측 피크 -3.2~-3.5m/s가 CAUTION보다 낮아 전혀 미발동). 30차 -2.2로 잠정 하향, 31차 6개 세그(3개 라우트) 재검증으로 강하게 뒷받침. 32차 곡선 오탐 검증 결과 이 문턱 자체가 새 오탐 리스크를 만들지 않음 확인. 33차: 사용자 로컬 커밋(`8114a46`, c3-ms-dev) 완료. 36차(2026-08-22): 실차 첫 실측 검증 성공 — 정치차량 route에서 82m/vRel -6.5~-7.9m/s 원거리 급접근 시 frac_rate가 레이더 락온보다 훨씬 이전에 0.826→1.0 도달, 이후 harsh_brake/운전자개입 없이 완전정지까지 매끈하게 감속. 카메라인식 route 4세그 중 2세그에서 max_frac_rate=1.000 추가 확인. **41차(2026-08-22, HEAD `c31ddca`): 신규 로그 4개 급접근 이벤트 전부 게이트가 레이더 락온보다 0.7~4.2초 이전에 활성화 재확인, 3/4건은 실제 aEgo도 vision-only 단계부터 점진 반영. 1건(route B seg10)은 vision raw vRel이 실제 dRel 변화와 불일치하는 노이즈성 프레임 때문에 게이트는 켜졌으나 실제 반영이 약했다가 락온 후 몰리는 잔여 패턴 확인 — 22/23차 vision 폐색비 과소평가 이슈의 연장, 표본 1건.** 근거: FINDINGS.md 28/30/31/32/36/41차) |
| VISION_CLOSING_RATE_GATE_DANGER | **-5.0 m/s** (26차 최초 -10.0 → 30/31차 재설계로 확정) | filt rate 절대값 게이트, 이 값 이하면 frac_rate=1.0 | VALIDATED (위 GATE_CAUTION과 동일 이력/상태 — 36차 실측 검증 완료, 근거 동일) |
| VISION_RATE_REF_MARGIN | **5.0 m/s** (63차 계속9 설계, 구현 착수) | 방안E: `ref_rate=-(vEgo-leadVLead)` 기준 `plausible_min=ref_rate-MARGIN`을 raw_rate 클램프 하한에 추가 | **NEEDS_VALIDATION (2026-08-24, 63차 계속10 정정)** — 직전 REJECTED 판단 철회. seg3(r1-3) 재생검증에서 관찰된 "PATCHED_E가 frac_rate를 0.209로 억제"는 리스크가 아니라 **의도된 동작임을 확인**: seg3의 raw dRel 극단값은 트랙전환 인공 점프였고, `leadVLead`(ref_rate)는 이 구간 내내 실제로 안전(opening 직전)했음 — 레이더 락온 후 실측 vRel +3.2~+7m/s(opening)로 확정, "끼어든 차가 더 빨랐다"는 사용자 요구사항과 정합. 방안E는 정확히 이 "raw dRel은 튀지만 leadVLead는 안전을 가리키는" 상황을 걸러내도록 설계됐고 seg3에서 그 역할을 제대로 수행함. "안전장치가 보완대상 신호에 종속되는 모순" 비판은 58차1번(leadVLead가 위험을 과소평가하는 반대 실패모드)의 프레임을 잘못 적용한 것이었음. margin 로직상 leadVLead가 실제 위험을 가리킬 땐 ref_rate도 함께 낮아져 raw_rate를 거의 그대로 통과시키므로 진짜 위험 억제 방향은 아님. **다음: `long_mpc.py` 실제 구현 → git am 검증 → 패치 전달.** 근거: FINDINGS.md 63차 계속10/63차 계속10 정정 |
| process_lead() vision_dRel_rate → v_lead 직접 보정 (신규 파라미터 아님, 로직 확장) | vision-only + `_lead_acq_timer>=VISION_CLOSING_RATE_MIN_TIME`일 때, 측정된 `v_ego+_vision_dRel_rate`가 `lead.vLead`보다 위험(작음)하면 그 값을 v_lead로 채택(min, 안전측만) | (58차 1번) NEEDS_VALIDATION — "카메라 인식 감속이 레이더 대비 약함" 개선 요청 대응. 기존엔 `_vision_dRel_rate`가 frac_rate로 MPC obstacle-distance 하한(floor)만 조였고 MPC가 실제 extrapolate에 쓰는 v_lead 자체는 보정 안 됐던 것을 수정. 합성검증(work/test_visiontrack_gate.py 확장): v_lead 24.0→19.0m/s 보정 시 t=4s MPC 예측 lead거리 196m→176m로 좁혀짐 확인. `git am` 적용(사용자 로컬 `C:\dev\ryu`, origin/c3-ms-dev `f94a7d2..e17e078`) + push 완료. 실차 검증 대기 — 원거리 vision-only 접근 시 감속 개시가 빨라지는지, 정상 추종 상황 회귀(불필요 조임) 없는지 확인 필요. FINDINGS.md 58차 참고 |
| LOW_SPEED_STRONG_DECEL_V_EGO_GATE / A_LEAD_THRESH | 30km/h(≈8.33m/s) / -1.8 m/s² | (58차 2번) 저속(v_ego<=게이트) + 앞차 실측 감속(a_lead<=문턱) 동시 성립 시 TTC 위치·rise-rate 제한과 무관하게 danger override와 동일하게 즉시 weight=1.0(무감쇠). 정체구간 "붕끗"(급가속→급감속 반전) 대응 — TTC 6~12s 램프 구간에서 감쇠 누적 후 몰아서 반영되는 패턴을 저속+강한감속 조합으로 좁혀서 원천 차단 | NEEDS_VALIDATION (2026-08-23, 58차 2번 계속4 신규 도입. `sim_low_speed_decel.py` 합성검증 4건 PASS — 게이트 밖(고속) diff=0 확인(A), 실측 이벤트(route `a3a55cb808` seg12, min TTC 4.45s) 근사 재현으로 unpatched 감쇠→몰림 패턴/patched 즉시무감쇠 대비 확인(B), 저속+완만감속(threshold 미달) 오탐 없음 diff=0 확인(C), 게이트 경계 전이 예외 없음 확인(D). `git am` verify-am 브랜치 검증(base `e17e078`) + py_compile 통과, **push 완료 (`e17e078..a35a39f`)**. **실차 acados MPC 파이프라인 검증은 아직 없음.** FINDINGS.md 58차 2번 계속4 참고) |

| NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S | 1.5s | (60차 계속2 신규) 리드 신규등록 후 이 시간(`_lead_acq_timer` 기준) 이내엔 58차1 v_lead 직접보정을 유예(패치 이전처럼 `lead.vLead` 그대로 사용) — cutin류 catch-up 구간 커버 목적 | NEEDS_VALIDATION (2026-08-24, 60차 원 분석의 cutin 사례 타이밍(등록~오염관측 0.45~1.44s)을 근거로 설계 추정치. 실측 재검증 안 됨 — cutin 원본 로그(--5) 재확보 시 우선 확인) |
| LANE_CHANGE_VLEAD_CORRECTION_HOLD_S | 1.0s | (60차 계속2 신규) `leftBlinker`/`rightBlinker` 활성 중 + 종료 후 이 시간 동안 58차1 v_lead 직접보정을 유예 — 차선변경 중 dRel 흔들림 구간 커버 목적. `longitudinal_planner.py`가 `sm['carState']`에서 blinker를 읽어 `mpc.update()`에 `lane_change_blinker_active`로 전달 | NEEDS_VALIDATION (2026-08-24, 60차 계속2 신규 도입. route `ee004b2c19--12`(차선변경 3번째 사례) CSV로 게이트 로직만 재현 검증 — 문제구간(t=816.98~817.44) 전체 `suppressed=True` 확인. `git am` verify-am 브랜치 검증(base `1ac07de`) + py_compile 통과, **패치 전달, 아직 적용/push 전**. 실차 acados 파이프라인 검증 없음, 정상추종 회귀검증도 필요. FINDINGS.md 60차 계속 참고) |

| DISCONTINUITY_JERK_COST_BOOST_S / _BOOST | 1.0s / 500.0 | (66차 방안G 신규) discontinuity 트리거(61차 방안C와 동일 감지, `_lead_acq_timer` 리셋과 같은 프레임) 후 이 시간 동안 `a_change_cost`(MPC 저크비용)를 500으로 override(평시 최대 200보다 큼) — 목표거리는 그대로 두고 도달 속도만 완만하게. `process_lead()`의 danger override(ttc<=2.5s)/58차2번 low_speed_strong_lead_decel 또는 25/26/33차 proactive floor(frac_time/frac_ttc/frac_rate>0) 중 하나라도 성립하면 즉시 무시하고 기존 j_lead 기반 식으로 복귀 | **[재확정, 73차, 2026-08-26] duration_S 자체는 병목이 아님으로 판명 — 진짜 원인은 `frac<=0.0` 게이트.** `toolkit/replay_boost_duration.py`(신규)로 route1(`ea5bcc0566`)/route2(`a5b1ce4e42`) 실측 재생: boost_s를 1.0→2.0→2.5→3.0s로 늘려도 위험구간(aEgo<=-1.5) 내 실제 boost 적용시간은 두 이벤트 모두 여전히 0.00초(0.0%) — timer는 boost_s에 비례해 활성화되지만 그 전부가 frac_ttc>0(radar 락온 직후 closing이 지속되며 TTC가 CAUTION 6.0s 밑으로 곧 진입) 게이트에 걸려 base_a_change_cost로 강등됨. **72차의 "duration 부족" 결론은 정정 — boost와 frac_ttc floor가 상호배타(if/else) 구조인 게 근본 문제.** NEEDS_VALIDATION(다음 방향 3안 중 결정 대기, FINDINGS.md 73차 참고) | NEEDS_VALIDATION (2026-08-25, 66차 신규 도입. `sim_jerk_boost.py` 합성검증 5건 PASS — 정상부스트/danger동시발생 억제/frac동시발생 억제/discontinuity 미발생 시 회귀없음(diff=0)/부스트 도중 danger 신규발생 즉시해제 전부 확인. `git am` verify-am-66 브랜치 검증(base `e6a00aea`) + py_compile 통과, 패치 전달 완료. 실차 acados MPC 파이프라인 검증은 아직 없음. FINDINGS.md 66차 참고) |

| CRUISE_DECEL_RATE_RELAX_LOW / _HIGH | 0.3 / 0.85 m/s² | (177차 신규, 원인B 대응) 리드없는 cruise 모드(`self.source=='cruise'`)에서 route 목표속도(v_cruise) 하강률(EMA, `self.route_decel_rate`)이 LOW~HIGH 구간을 지나며 `base_a_change_cost`를 200→20(`CRUISE_DECEL_RELAX_A_CHANGE_COST`)까지 선형완화 — 176차가 검증한 "가속->감속 부호전환 구조적 지연" 가설에 대한 직접 대응. j_lead 기반 기존 리드케이스 interp(`[0.3, 2.0]->[200,20]`)와 동일 패턴을 route 아날로그로 구현 | NEEDS_VALIDATION (2026-08-31, 177차 신규 도입. `sim_causeB_patch_validate.py`(신규) 합성 시나리오(174차 요약 특성 재사용, v_ego 57.5kph 시작/target 57.9→48.1kph 3초 램프/leadStatus=False) 검증 — 부호전환 1.5s(패치 OFF)→1.25s(패치 ON), t=3.0s gap 9.19→7.99kph(-13%) 개선 확인. **HIGH=1.0으로 최초 설계했으나 EMA(0.1/0.9) 평활화된 route_decel_rate 정상상태가 ~0.906까지만 도달해 완전완화(20) 미달성(개선폭 0.2s에 그침) 발견 → 0.85로 하향해 재검증, 개선폭 0.25s로 소폭 상승.** 176차 실측/합성이 보여준 baseline vs A_CHANGE_COST=20 상수 고정 간 차이(0.45~0.5s)에는 못 미침 — EMA 평활화 자체가 의도적 지연(노이즈성 route 흔들림에 즉각 반응해 스냅백을 유발하지 않기 위함)이라 구조적으로 발생하는 트레이드오프. **다음: EMA 계수(현재 0.1/0.9, j_lead와 동일하게 재사용)를 route 전용으로 더 빠르게(예: 0.2/0.8) 튜닝할지, 또는 현재 개선폭을 실차에서 먼저 확인할지 결정 필요.** 실측 프레임(route `6310bba9b8`) 재검증은 zip 재업로드 필요(캐싱 안 됨, 176차 계속 정책과 동일). `git am` 검증/실차 검증 모두 아직. FINDINGS.md/WIP.md 177차 참고) |
| CRUISE_DECEL_RELAX_A_CHANGE_COST | 20.0 | (177차 신규) 위 완화 게이트의 최대 완화값 — 리드 케이스 최솟값과 동일하게 맞춰 일관성 유지(임의로 더 낮추지 않음) | NEEDS_VALIDATION (위 항목과 동일 근거) |

## selfdrive/controls/radard.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| VISION_TRACK_TENTATIVE_PROB_GATE | 0.35 | (58차3번 A) 이 이상이면 tentative(예비) 후보 카운트 시작 | NEEDS_VALIDATION (2026-08-23, 신규 도입 — "정지차량_미인식" 실사례(8초간 leadModelProb<0.5로 트랙 미등록) 대응. 로직단위 합성검증(sim_vision_track_ab.py A-1/A-2/A-3) PASS. 실차 검증 없음 — 특히 오탐지(존재하지 않는 리드 조기등록) 위험 확인 필요. FINDINGS.md 58차3번 참고) |
| VISION_TRACK_TENTATIVE_CNT_GATE | 10 (0.5s@20Hz) | (58차3번 A) tentative 상태가 이만큼 연속 유지되면 정식등록(prob>.5 문턱 우회) | NEEDS_VALIDATION (위와 동일 이력) |
| VISION_TRACK_TENTATIVE_DREL_JITTER | 8.0m | (58차3번 A) tentative 추적 중 dRel이 이 이상 튀면 다른 물체로 판단, tentative_cnt 리셋 | NEEDS_VALIDATION (위와 동일 이력) |
| VISION_TRACK_SAFETY_MIN_CNT | 2 | (58차3번 B) prob<VISION_TRACK_PROB_GATE(0.70) 구간에서 dRel 실측 이력이 이 프레임 이상 쌓이면, 실측기반 vLead가 모델예측보다 위험할 때만 min() 안전측 보정 적용 | NEEDS_VALIDATION (2026-08-23, 신규 도입 — 58차1번 v_lead 안전클램프와 동일 원칙 재사용. sim_vision_track_ab.py B-1(실사례 근사 재현)/B-2(정상상황 무간섭) PASS. 실차 검증 없음. FINDINGS.md 58차3번 참고) |
| LEAD_BLEND_TTC_DANGER | 2.5s | TTC 이하 즉시 반영 | FIXED (route1/2 검증됨) |
| LEAD_BLEND_DANGER_HOLD | 0.3s | 위험 판정 후 스무딩 우회 유지 시간 | - |
| LEAD_BLEND_SAFE_DIST_TIME | 0.35s | 안전방향 블렌딩 시정수 | - |
| LEAD_BLEND_CLOSER_JUMP_DIST | 8.0m | 이 이상 급접근 점프 시 즉시 반영 | 검증됨 (route1 seg13 t=794s, 표본 1건) |
| LEAD_BLEND_BIG_JUMP_DIST | 15.0m | 이 이상 안전방향 점프는 즉시 스냅(단, 130차부터 신뢰도 게이트 통과시에만) | 검증됨 (route1 t=1388~1390s / route2 t=825~827s, 표본 1건씩) |
| LEAD_BLEND_BIG_JUMP_PROB_GATE | 0.70 (130차 신규, VISION_TRACK_PROB_GATE와 동일값 재사용) | BIG_JUMP 즉시-스냅을 `radar=True` 또는 `modelProb>=`이 값일 때만 허용 — 저신뢰 vision-only far jump는 블렌딩(0.35s 시정수) 경로로 완화. 104차 Finding A(커브 중 레이더 유실 → vision 저신뢰 원거리 오판, 84~89m로 근접 실물체를 원거리 오판) 대응 | NEEDS_VALIDATION (2026-08-29, 130차 신규 도입. `sim_lead_blend_far_jump_gate.py` 합성검증 5건 PASS — 104차 재현(첫프레임 점프 55.4m→8.0m 감소)/고신뢰vision 회귀없음/레이더교차검증 회귀없음/closer_jump 반응지연없음/정상추종 완전동일 전부 확인. `git am` verify-am 브랜치 검증(base `b63063a`) + py_compile 통과, 패치 전달 완료. **실차 acados MPC 파이프라인 검증은 아직 없음**(동일 커브+레이더유실 재현 로그 미확보). FINDINGS.md 130차 참고) |
| LEAD_LOST_GRACE_TIME | 0.6s | 리드 순간유실 홀드 시간 | - |
| CUTOUT_DPATH_THRESH | 2.0m | 컷아웃 판정 dPath 임계값 | NEEDS_VALIDATION |
| CUTOUT_VREL_GATE | -0.5 m/s | 컷아웃 판정 vRel 게이트 | NEEDS_VALIDATION |
| SCC_FALLBACK_DPATH_GATE | 2.0m | `get_lead()`에서 `track_scc`(SCC 단일점, trackId=0) 채택 전 dPath(차선중심 대비, 곡률/차선폭 보정 포함) 기준 차로내 위치 게이트. 넘으면 폴백 미채택 — 옆차선/경로이탈 오탐 4건 근본원인 대응(37차). yRel 대신 dPath 채택 이유는 FINDINGS.md 37차 항목 참고 | PATCH_APPLIED(c3-ms-dev `21effa1`/c3-ms-test `b5a1209`), 로직 단위 합성검증(7케이스) 통과, 실차 미검증. CUTOUT_DPATH_THRESH와 동일값(2.0) 채택 — 별도 상수로 관리, 값 연동 아님 |
| sccFallback 플래그 (RadarD.get_lead 3-tuple 반환값, `used_scc_fallback`) | bool | track_scc 유래 채택인지 표시. True면 `RadarD.update()`에서 `radar=True`라도 LeadBlend 우회 안 함(cutout/danger-passthrough 계속 적용) | **[URGENT FIX 완료] 원래 dict 키(`sccFallback`)였으나 capnp LeadData 스키마에 없어 매 사이클 크래시(radard 프로세스 실행 불가) 유발 확인 — `f67a834`에서 dict 키 제거하고 `get_lead()` 3-tuple 반환의 파이썬 로컬 변수로 분리, 로직은 동일 유지. FINDINGS.md 해당 항목 참고. PATCH_APPLIED(로컬, patch 전달 대기), 실차 미검증** |
| (해결됨, 참고) radar=True → LeadBlend 전면 우회 | `RadarD.update()` line ~680 | ~~구 조건 `lead_one_raw.get('radar')`~~ → **패치 후**: `lead_one_raw.get('radar') and not lead_one_scc_fallback`(로컬 변수, dict 키 아님 — 위 항목 참고). track_scc 폴백 리드만 LeadBlend를 계속 타도록 분리 완료(37차 계속 3, capnp 크래시 수정 후 f67a834) | PATCH_APPLIED(patch 전달 대기), 실차 미검증 |
| VISION_TRACK_PROB_GATE / VISION_TRACK_CNT_GATE | 0.70 / 10 (기존 0.97 / 20) | `VisionTrack.update()`에서 실측 dRel미분 기반 vRel 추정 경로(레이더와 동일 방식) 진입 조건. 기존 0.97 게이트가 원거리 실측 prob 분포(0.5~0.8대 흔함)에서 거의 항상 걸려 이 경로가 사실상 죽어있던 문제 대응(56/57차 qcamera 대조로 반복 확인된 "카메라 미감속" 패턴의 root cause 중 하나) | (58차 1번) NEEDS_VALIDATION — 합성검증(work/test_visiontrack_gate.py)으로 게이트 진입 빈도 증가는 확인했으나, alpha=0.02(저역통과 시정수 2.5초) + model_weight 블렌딩 특성상 이 변경 단독으로는 개선 효과가 제한적임을 확인(같은 세션 시뮬레이션 결과). 실효는 long_mpc.py의 v_lead 직접 보정(위 항목)이 더 큼 — 이 변경은 보조적/방향성 일치 개선으로 유지. `git am` 적용 + push 완료(origin/c3-ms-dev `e17e078`). 실차 검증 대기 |

## selfdrive/carrot/carrot_functions.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| lcAggressiveMaxTime | 8.0s | 차선변경 중 좁은 tFollow 유지 안전상한 (runaway guard) | FIXED/검증됨 (route1 422→0건, route2 363→0건) |
| tFollowLaneChangeHoldTime | 1.0s | 차선변경 종료 후 좁은 tFollow 고정 유지 | - |
| tFollowLaneChangeBlendTime | 1.5s | 이후 정상값으로 복귀하는 시간 | - |

## selfdrive/carrot/carrot_serv.py

| 상수/구조 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| speed_n_sources min() 선택 | 히스테리시스는 여전히 없음. **model 후보만** model_turn_speed 추세 기반 게이팅 적용(아래 두 행, 13차 재설계) | atc/road/vturn/route/model 등 후보 중 크루즈 목표속도 소스 선택 | NEEDS_VALIDATION — 나머지 쌍(atc/road/route) (2026-08-19 x16seg + 2026-08-20 x20seg(260819-1) 로그: 국도 완만한 커브뿐 아니라 73~113km/h 고속 커브 구간 전반에서 vturn↔road/model/route 재현, x20seg에서 A→B→A 플리커 49건 확인, 우세 쌍 vturn↔model. **16차(2026-08-20): 패치 후 실주행 로그에서 vturn↔model 플리커는 유의미하게 감소(아래 행 참고)했으나, road↔vturn/route↔vturn은 여전히 비슷하거나 더 큰 빈도로 재현 — model 쌍 외에는 여전히 미해결.** **20차(2026-08-21, 신규 로그 260821): `all_source_pairs_flicker_summary()`(도구 4/5)로 처음 전체 쌍을 자동 스캔 — 이 로그에선 오히려 road<->vturn(107건, 5.94/min)이 model<->vturn(70건, 3.89/min)보다 더 우세, route<->vturn(47건) 뒤이음. road<->route(34건, 1.89/min)도 이번이 최초 정량화. 우세 쌍은 로그마다 달라질 수 있음이 확인됐으며, road/route 관련 쌍은 여전히 히스테리시스 완전 미적용 상태.** FINDINGS.md 참고) |
| model_turn_straight_thresh | (12차, `7cdc20b`로 제거됨) | desiredCurvature 기준 게이팅 — 진입 전 사전감속 억제 위험으로 폐기 | SUPERSEDED (2026-08-20, model_turn_speed 추세 기반으로 대체, 아래 항목 참고) |
| model_turn_speed_noise_tol | 0.3 km/h | [REPLACED, 50차] `model_turn_speed_min_recent`+`model_turn_recover_margin` 방식으로 대체됨(아래 항목 참고). 값 자체는 더 이상 코드에 없음 | REPLACED (2026-08-23, 50차 — 프레임 노이즈에 과민하게 반응해 접근구간에서도 트레일링 오탐 유발, 실측으로 확인) |
| model_turn_straight_hold_sec | 0.6s | 이 시간 이상 연속 "회복 유지"(아래 min_recent+margin 기준)여야 "트레일링"으로 보고 model 후보를 min()에서 배제 | PARTIALLY_VALIDATED — 값(0.6s) 자체는 유지, **판정 기준만 50차에서 min_recent+margin으로 재설계**(아래 항목 참고). 새 로직 자체는 아직 실차 미검증. |
| `model_turn_speed_min_recent` + `model_turn_recover_margin=3.0km/h` [NEW, 50차] | 3.0 km/h | 트레일링 판정 기준선. 최근 확인된 model_turn_speed 최저점(min_recent) 대비 이 폭 이상 지속 회복돼야 트레일링으로 확정(carrot_serv.py, 50차 커밋 `74e8e90`) | **NEEDS_VALIDATION (2026-08-23, 50차)**: route1(203f99d429 seg8) 재현 시뮬레이션으로 apex 사전감속 여유시간이 3초 미만→20초+로 확대됨을 확인(work/replay_vturn2.py 기반 스크래치). **단 같은 로그 전수 스캔 결과 전체 프레임의 98.8%에서 model이 min() 후보로 참여 — 진짜 평탄한 직선 고속도로에서도 이 비율이 유지되는지 검증 로그 부재로 미확인. 실차 테스트 시 직선 구간 불필요 감속 여부 최우선 확인 필요.** 실차 미검증. |
| model 후보 게이트 `abs(vturn_speed) < 120` | [REMOVED, 50차] | model_turn_speed를 min() 후보에 넣을지 여부의 추가 조건이었음(carrot_serv.py L1051, 13차 `119b101`에서 model↔vturn 플리커 감소 목적으로 도입) | **REMOVED (2026-08-23, 50차, 커밋 `74e8e90`)** — 46차에서 NEEDS_VALIDATION으로 지목됐던 위험(vturn 원시값이 원거리에서 극도로 불안정(-249~249 관측)해 model의 안정적 조기신호를 반복 차단)이 route1(203f99d429 seg8) 로그로 재확인됨에 따라 제거. 트레일링 판정(위 항목)이 자체적으로 진입/이탈을 구분하므로 vturn 절대값 게이트는 더 이상 필요 없다고 판단. **실차 미검증, 직선구간 오탐 위험 최우선 확인 필요.** |

## selfdrive/carrot/carrot_man.py

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| vturn_lookahead_horizon_s | **8.0s** (정정, 4.5s→6.5s→8.0s 2단계 확대) | 커브 조기감속 예측구간 | **[NEEDS_VALIDATION, 52차, 2026-08-23 갱신] 21차 "overspeed 0건" 결론은 완전히 폐기됨.** 51차 단위버그 수정판으로 재스캔한 결과: route1(203f99d429) 1건/route2(f3db6ca89d 전체20세그) 16건(over 4.2~18.1kph)/route4(d45a15f8fc 전체20세그) 24건(1건은 운전자개입 제외, 23건 순수ADAS, over 2.2~15.1kph)/route9(280302e8ed) 0건 — route마다 편차 크지만 연속커브/고속도로 커브 구간에서 재현성 있는 문제로 확정. **핵심**: route2 16건 중 12건(75%)·route4 23건 중 13건(57%)이 실측 aEgo가 이미 `vturn_decel_rate`(1.2m/s²) 대비 100~288%로 반응 중인데도 못 따라잡음 — 감속 파라미터 자체보다 **lookahead horizon이 급조임을 충분히 일찍 못 잡아 뒤늦게 발견**하는 쪽 원인 가설(ii)에 무게. apex-vs-gap 재분류(route2 11/16건)에서도 최대초과 시점이 조향각 정점보다 0.3~1.75초 먼저 발생 — "정점에서만 못 따라감"이 아니라 "진입 중 이미 벌어짐"과 일치. route4 idx10 1건(over=13.3kph, aEgo_min=-3.45m/s²=설계값 288%)은 이례적으로 강해 개별 확인 필요. 상세는 FINDINGS.md 51/52차 참고. **다음 단계: raw required_speed(필터 전) lookahead 재현 검증 필요.** |
| vturn_decel_rc | **0.15s** (정정, 기존 0.25s는 구버전 값) | 감속 저역통과 시정수(모델 노이즈 제거용, 감속 프로파일 자체는 물리공식이 결정) | 검증됨(2026-08-20, 260819-7 세션 코드 직접 확인 — a94a58b 커밋에서 물리공식 기반으로 재설계되며 값도 변경됨, 기존 표는 ab156ea 시점 값이라 최신화) |
| vturn_accel_rc | **0.15s** (정정, 기존 0.6s는 구버전 값) | 가속복귀 저역통과 시정수 | 검증됨(상동, 260819-7 세션 정정) |
| TARGET_LAT_A | 1.6 m/s^2 | 목표 횡가속도 기준(autoCurveSpeedAggressiveness로 배율 적용) | - |
| vturn_safe_time | **2.0s** (81차, 기존 1.0s에서 상향) | 목표속도 여유 도달 시간(방지턱 AutoNaviSpeedBumpTime과 동일 기본값에서 출발) | NEEDS_VALIDATION (2026-08-26, 81차 — 계산상 목표속도가 정점에 지정돼도 실제 차량 속도가 아직 못 따라와 체감상 빠르다는 사용자 제보. vturn_decel_rc/accel_rc(0.15s)는 시정수가 작아 필터 자체가 큰 지연 요인은 아니라고 판단, 1.0s 버퍼가 실제 acados MPC+차량 감속 응답 램프업 시간 대비 부족했을 가능성이 유력 후보 — 2.0s로 상향해 `c3-ms-curv` 브랜치에서 실차검증. 문제 있으면 브랜치 롤백 가능하도록 c3-ms-dev와 분리) |
| vturn_decel_rate | 1.2 m/s² | 방지턱 물리공식 기반 커브 감속률(AutoNaviSpeedDecelRate=120 동일값) | PARTIALLY_VALIDATED (2026-08-20, 21차: route1/route2 고속 vturn 블록에서 저크 없는 매끈한 감속 다수 확인, 급조임 상황(260819-7 seg6 표본과 유사한 케이스)은 이번 로그에 없어 원 의문점 자체는 미해소 — FINDINGS.md 21차 참고) |
| `AutoNaviSpeedDecelRate` [사용자 UI 설정값, 83차 신규] | **사용자 실측 70**(=0.70 m/s², 기본값 120=1.20보다 낮춤) | `carrot_navi_route()`(route 커브 진입측 감속)의 `accel_limit`으로 직접 사용. 필요거리=`(v_ego²-target²)/(2×accel_limit)` — 값을 낮출수록 더 이르게·완만하게 감속 시작(UI 툴팁: "Lower number, slows down from a greater distance") | [84차 조치완료, NEEDS_VALIDATION] 300m 고정 캡이었던 시절엔 100→60km/h 시 0.70에서 이미 ≈303m로 상한 초과 우려가 있었으나, **84차에서 캡 자체를 동적화(300~500m)해 이 문제를 완화** — 아래 `route_lookahead_dynamic_cap` 행 참고. 단 accel_limit 자체의 "낮출수록 항상 좋다"가 아닌 성질(감속폭에 따라 최적값이 갈림)은 여전히 유효. **[중요] route 전용 파라미터 아님** — 과속카메라 감속(`sdi_speed`)/TBT 회전 감속(`atc_desired`)/도로제한속도 감속과 전부 공유(`carrot_serv.py` L847/L983/L994), 조정 시 넷 다 동시에 영향받음. |
| `ROUTE_NEAR_STOP_TARGET_KPH` / `ROUTE_ACCEL_LIMIT_BOOST_MAX_MSS` [149/150차 설계, `carrot_man.py`, 로컬에만 존재/origin 미반영] | 15.0 kph / 1.2 m/s² (vturn_decel_rate 재사용) | 근정지급 코너(lookahead 윈도우 내 최소 target_speed가 이 값 이하) 한정으로 `carrot_navi_route()`의 `accel_limit`을 필요치까지 부스트(상한 1.2) | **[151차, 배포 보류 권고]** `toolkit/sim_route_near_stop_accel_boost.py`로 132차 램프리미터 포함 다중프레임 시뮬레이션 검증 결과 **NEGATIVE** — accel_limit을 올리면 DP가 "나중에 더 세게 감속 가능"이라 판단해 현재 시점 감속 시작을 오히려 늦추는데, 132차 램프리미터는 실시간(dt) 기준으로만 부스트를 적용해 따라잡지 못함. 149차 근사조건(280m)에서 부스트 후 초과속도가 4.4→8.8kph로 악화 확인. 91차/129차/131차/132차가 막으려던 "지연된 급감속" 패턴을 재도입하는 것으로 판단 — **현재 형태로 ryu에 push하지 않음.** 대안(감속시작시점 계산과 감속스텝 계산의 accel_limit 분리 / route_lookahead_m 상한 확장 / 코드변경 없이 종결) 미결정, FINDINGS.md 151차 참고. |
| `route_lookahead_dynamic_cap` [84차 신규, 85차 max_m 500->600 상향] | `min_m=300.0`/`max_m=600.0`(85차, 기존 500.0)/`assumed_target_kph=30.0` | `carrot_man.py compute_route_lookahead_distance()` — `carrot_navi_route()`의 `get_path_after_distance()` 호출 시 fetch할 거리(구 300m 고정값)를 `(v_ego²-target²)/(2×accel_limit)`로 계산 후 [min_m,max_m]로 clip. `assumed_target_kph`는 실제 커브 목표속도가 아니라 캡 크기 산정용 가정값(이 함수 호출 시점엔 실제 곡률 기반 목표속도를 아직 모름). 저속(<=60km/h 부근)은 accel_limit 무관 항상 min_m(기존 300m와 동일, 회귀 없음). | NEEDS_VALIDATION (2026-08-26, 85차 갱신) — 84차가 max_m=500m로 도입했으나 "120→60km/h 풀커버는 accel=0.70 기준 이론상 ≈595m 필요, 500m는 절충값"이라는 84차 자체 지적에 따라 85차에서 600m로 상향(≈595m 이론치를 온전히 커버). `toolkit/sim_route_dynamic_cap.py` 600m 기준 재검증 — 사용자 실측 accel=0.70 기준 110km/h+에서 ceil(600m) 도달, 저속 floor(300m) 유지, 단조성, 예외 안전폴백 4건 전부 PASS. `git am` verify-am-85(base `2a91c3f`) diff 0 + `py_compile` 통과. 실차 반응 여전히 미확인 — 600m가 실제로 충분한지, assumed_target_kph=30.0이 적절한지 튜닝 여지 있음. |

## selfdrive/carrot/server/gdrive.py (CarrotWeb Drive 업로드)

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| _HANDSHAKE_TIMEOUT | total=20s / sock_connect=10s / sock_read=15s | 토큰갱신·폴더조회생성·resumable세션오픈 전용 타임아웃(청크 PUT의 관대한 타임아웃과 분리) | NEEDS_VALIDATION (2026-08-18 신설, 실기기 네트워크 끊김 재현 검증 필요) |
| _UPLOAD_TIMEOUT | total=1800s / sock_connect=30s / sock_read=300s | 실제 파일 청크(8MB) PUT 전송용 (핸드셰이크 요청에는 더 이상 안 씀) | 기존값 유지 |
| UPLOAD_CHUNK_SIZE | 8MB | resumable 업로드 청크 크기 | - |

## system/loggerd/logger.cc

| 상수 | 현재값 | 용도 | 검증상태 |
|---|---|---|---|
| MAX_SEGMENTS_PER_ROUTE | 20 (기존 40) | 라우트당 최대 세그먼트 개수, 도달 시 새 라우트로 회전 (라우트당 최대 길이: 세그먼트 1개=1분 기준 약 20분, 기존 40분) | NEEDS_VALIDATION (2026-08-20, 260819-5 로그에서 route `ba55f880d1`가 seg0~39까지 40개 단위로 이어진 걸 실기기 미반영으로 오판했다가 정정 — 해당 로그(8/19 12:41~13:00)가 패치 커밋 f7b154638cf2(8/20 00:57)보다 이전이라 40개 동작이 정상. 진짜 검증은 패치 커밋 이후 기록된 로그로 다시 필요. 상세: FINDINGS.md [WONTFIX](정정 기록)) |

## 비전 리드 트래킹 노이즈 (신규 관찰, 특정 상수 아님)
| (신규 이슈, 상수 아님) dRel-vRel 지속적 곡선 드리프트 불일치 | (미설계) N프레임 dRel 변화량 vs vRel 적분값 괴리 임계 | frac_rate 게이트가 지속적 곡선(글리치 아닌 매끈한 드리프트)에서 오탐 — 기존 baseline 문턱에서도 이미 재현 | NEEDS_VALIDATION (2026-08-21, 32차, `203f99d429--8`에서 최초 실측: 2.7초간 dRel 93→38.6m 감소인데 vRel은 -1.7~-3.4m/s뿐 — 6~10배 괴리. 문턱 재설계와 무관한 별도 결함, 원인 미확인(대시캠 대조 필요), 수정 설계도 미실시. FINDINGS.md 32차 참고) |

| 항목 | 관찰값 | 용도 | 검증상태 |
|---|---|---|---|
| leadDRel 프레임당(≤0.3s) 급점프(≥8m) 발생빈도 | ~46건/722s (약 15초당 1회) | LeadBlend closer_jump/big_jump 게이트 발동 빈도 추정 | NEEDS_VALIDATION (2026-08-18 x12seg, 컨트롤 영향은 대부분 미미했으나 누적 확인 필요) |

---
- 2026-08-20: 260819-2 로그 분석 — LEAD_ACQ_LOSS_GRACE_TIME 근거였던 순간유실
  사례 중 상당수가 extract_log.py 세그먼트 경계 아티팩트로 확인돼
  "재검토 필요"로 하향/보류 조정 (상세: FINDINGS.md)
- 2026-08-20: 260819-3 로그(route3a+3b) 분석 — extract_log.py 세그먼트
  경계 아티팩트 버그 13건 추가 재확인(값 변경 없음, "재검토 필요"
  상태 유지). harsh_brake/turn_speed_violation 계속 클린 재확인.
- 2026-08-20: 260819-5 로그(route5a+5b) 분석 — MAX_SEGMENTS_PER_ROUTE
  실기기 미반영 "반증"으로 처음 기록했다가 정정: 로그가 패치 커밋보다
  이전 시점이라 40개 동작이 정상이었음(오판, 상세 FINDINGS.md). 검증
  상태는 NEEDS_VALIDATION 그대로(패치 이후 로그로 재확인 필요).
  LEAD_ACQ_LOSS_GRACE_TIME real 유실 route5b 다수 확인됐으나 전부
  cruiseEnabled=False라 표본 부적합 처리. 비전 원거리 리드 노이즈
  패턴 재확인(값 변경 없음).
  저속 리드 대체 패턴 극단 사례(36m 점프) 추가 확보했으나 해당 구간
  cruiseEnabled=False라 제어 영향 없음(상세: FINDINGS.md)
- 2026-08-20: 260819-4 로그(route3b 연속분, seg5~24) 분석 — 이번
  라우트는 경계 아티팩트가 8건 중 1건뿐이라 실사례 비중(7/8)이 높음,
  0.5s 초과 실유실 5건 확보(0.6~1.6s) — "재검토 필요"이지만 실사례
  존재 자체는 재확인됨. LeadBlend CLOSER_JUMP_DIST/BIG_JUMP_DIST
  게이트 관련: 게이트 임계값을 초과하는 대형 dRel/vRel 점프 26건이
  이번엔 전부 무해하게 해소(급제동 없음) — vRel-only 불연속이 항상
  위험으로 이어지진 않는다는 반례 데이터 추가(상세: FINDINGS.md)
- 2026-08-20: 260819-6 로그(route6a+6b) 분석 — LEAD_ACQ_LOSS_GRACE_TIME
  6~36초짜리 긴 유실 신규 발견(기존 최대 2.46s 대비 훨씬 김)했으나
  개별 대조 결과 전부 무해(개활도로 선행차 소실/저속 코너 시야이탈)
  — 상태 NEEDS_VALIDATION 유지, 시급성 낮음으로만 기록. 별건: 사용자
  제기 "커브 탈출 후 재가속 지연" 가설 검증 시도 — `curve_exit_no_accel_scan`
  기본 임계값이 시내/연속커브 도로에서 오탐(선행차 추종 정차/S자
  재진입을 커브탈출로 오판) 다수 발생해 이번 로그로는 가설 확증/반증
  둘 다 못함. 도구 개선 방향(leadStatus 필터, 직선 지속시간 조건)
  제안만 하고 코드 작업은 미착수(상세: FINDINGS.md)
- 2026-08-20: 260819-7 로그(고속도로 위주, 32.7km/1319.9s) 분석 —
  `curve_exit_no_accel_scan_v2` 신설(leadStatus 필터+직선유지 조건),
  4건→3건으로 감소했으나 남은 1건도 프레임 대조 결과 3번째 오탐 패턴
  (vCruiseCluster 캡으로 이미 목표속도 근처라 가속 여지가 애초에 없었던
  경우)으로 판명 — 가설 검증 여전히 미완료, v3 개선 방향(목표속도 여유폭
  필터) 제안. vturn_decel_rc/accel_rc 값 정정(0.25/0.6→0.15/0.15,
  코드 직접 확인). vturn_decel_rate=1.2m/s²/vturn_safe_time=1.0s 신규
  등록. 그 외: harsh_brake 12건 중 11건 disengage 인접(운전자 개입) 확인,
  1건은 진행 중인 vturn 감속 커브 도중 개입한 새 패턴(표본 1건,
  INVESTIGATING). turn_speed_violation 0건. LEAD_ACQ_LOSS_GRACE_TIME
  0.5s 초과 6건 모두 고속 개활도로/완만한 커브 상황 무해 재확인. 상세는
  FINDINGS.md 참고.

갱신 이력:
- 2026-08-18: 최초 작성 (c3-ms-dev HEAD 8dbed620887b 기준)
- 2026-08-18: x12seg 로그 분석 반영 (LEAD_ACQ_RAMP_TIME 첫 검증 사례,
  비전 리드 트래킹 노이즈 빈도 신규 관찰 항목 추가)
- 2026-08-18: CarrotWeb gdrive._HANDSHAKE_TIMEOUT 신설 (Drive 업로드
  진행률 번갈아 뜨는 버그 수정 관련, FINDINGS.md 참고)
- 2026-08-19: LEAD_ACQ_LOSS_GRACE_TIME NEEDS_VALIDATION으로 갱신
  (x11seg 로그 실측 플리커 4건 근거, FINDINGS.md 참고)
- 2026-08-20: system/loggerd/logger.cc MAX_SEGMENTS_PER_ROUTE 40 -> 20
  신설 (carrotweb 로그탭 라우트 세그먼트 수 축소 요청, FINDINGS.md 참고)
- 2026-08-20: 260819-8 로그 분석 — 값 변경 없음. LEAD_ACQ_LOSS_GRACE_TIME/
  MAX_SEGMENTS_PER_ROUTE 둘 다 NEEDS_VALIDATION 유지(고속도로 라우트에서
  긴 유실 다수 확인됐으나 전부 무해 재확인, MAX_SEGMENTS_PER_ROUTE는
  route ID 종료가 캡 발동인지 재부팅 우연인지 불명확한 참고 관찰만
  추가). 상세는 FINDINGS.md 참고.
- 2026-08-20 (신규 세션): VISION_CLOSING_RATE_TAU/MIN_TIME 신설 —
  vision-only 원거리 리드 closing-rate 크로스체크 패치(commit
  `b403d52`, 실차 `git am` + push 완료). 8개 zip 크로스오버
  분석(VISION_RADAR_CROSSOVER.md) 최우선 후보 5건 + 사용자 실주행
  체감 보고("카메라 인식 시점부터 감속 없다가 레이더 확인 순간부터
  감속") 기반 설계. aEgo 실측 대조는 아직 미완료 — 다음 세션에서 최우선
  후보 5건 세그 재업로드받아 검증 필요(FINDINGS.md 신규 항목 참고).
  같은 세션 내 사용자 피드백으로 MIN_TIME 1.0s→0.5s 단축(반응 지연이
  길다는 판단, TAU=1.0s는 유지).
- 2026-08-20 (7차): vturn_lookahead_horizon_s 4.5s→6.5s 확대(commit
  `4c15987`, ryu `c3-ms-dev` push 완료 `b403d52..4c15987`). "곡선 진입
  전 사전감속 부족으로 곡선 내 급감속" 사용자 보고 + 기존
  [INVESTIGATING] 260819-7 seg6 사례(조임 8.6s) 근거.
- 2026-08-20 (8차, 같은 트랙 이어감): 1차 push(`4c15987`) 확인 직후
  사용자가 6.5s→8.0s 재확대 요청(근거 사례 조임 8.6s에 더 근접하게).
  patch(`1fca82f`, push 완료). `vturn_lookahead_horizon_s`가
  "감속 소요시간"이 아니라 "커브 후보 스캔 지평선"이며, 방지턱과 동일한
  거리기반 서서히-감속 프로파일은 `vturn_decel_rate`/`vturn_safe_time`
  담당이라는 점 사용자에게 설명. 실차 검증 미완료 — 다음 세션 최우선.
- 2026-08-20 (10차): screenrecord "정지 시 마지막 1분 clip 자동 생성"
  기능 신규 (튜닝 상수 아님, 상수 없음 — clip 길이는 코드에 하드코딩
  `-sseof -60`). 실차 `git am` + push 완료(commit `0f7575f`,
  `2226db7..0f7575f`). 실측 검증(clip 생성 여부/길이/ffmpeg 경로)은
  아직 남음. 상세는 WIP.md 참고.
- 2026-08-25 (72차, 방안 I): `RADAR_HANDOFF_VREL_JUMP_THRESH=3.0` m/s
  신규(`long_mpc.py`) — 레이더 락온 전환(False->True) 엣지 프레임에서
  직전 프레임 vRel 대비 이 이상 접근방향으로 튀면 방안G(66/67차)
  저크부스트 재사용 arm. 실차 재현 사례(route1 t=690.05, vRel
  -3.6->-10.8m/s=7.2m/s 점프)를 확실히 잡도록 여유있게 설정한 설계
  추정치 — NEEDS_VALIDATION, 실차 반응 보고 튜닝 필요. patch
  `0001-72-I-vRel-G.patch` 전달 완료, base `0c137f2`.
- 2026-08-26 (81차, route 500m TBT 게이트 제거): `carrot_serv.py`의
  `speed_n_sources` 결합부 — `TurnSpeedControlMode==2`에서
  `-500<xDistToTurn<500`(TBT 회전지점 근접) 게이트가 있어야만
  route_speed가 min() 후보에 참가하던 것을 제거, mode 2도 mode 3/4처럼
  항상 참가하도록 통일(단 vturn 참가 조건([1,2] 분기)은 그대로 유지 —
  mode 2에서 vturn+route 둘 다 항상 경쟁하는 구조로 변경). 근거: TBT
  안내가 없는 일반 도로 굽이길에서 route_speed가 계산은 되고도 후보에서
  빠지던 사각지대(81차 코드리딩으로 신규 식별). **리스크**: 내비 GPS
  폴리라인 곡률 계산이 vturn(비전모델) 대비 노이즈에 취약할 수 있어,
  게이트 해제 후 직선/완만 구간에서 오탐(불필요 감속) 가능성 —
  NEEDS_VALIDATION, `c3-ms-curv` 브랜치에서 실차검증 (문제 시 브랜치
  롤백으로 c3-ms-dev 즉시 복귀 가능하도록 분리).
- 2026-08-26 (87차): `VISION_TRACK_GHOST_TIMEOUT_S=3.0` 신규
  (`radard.py`, `VisionTrack`) — 60차 계속6(B안)이 남긴 사각지대 수정:
  tentative_cnt 래치가 prob 영구 소실 시에도 못 풀리던 버그(실차 재현:
  파란 박스 120초 유지, 급감속 유발). prob<TENTATIVE_PROB_GATE(0.35)
  연속 유지시간이 이 값을 넘으면 tentative_cnt 강제 리셋. 순수 로직
  시뮬레이션 3개 시나리오 PASS(고스트 해제/실제 리드 회귀없음/시야이탈
  정상해제), patch 전달 완료(`0001-87-...patch`, base `284457f`).
  NEEDS_VALIDATION — 실차 반응 보고 튜닝 필요(너무 짧으면 실제 리드
  일시 가림에서 조기리셋 가능, 너무 길면 팬텀 지속시간 증가).

## ROUTE_ENTRY_MARGIN_KPH (91차, NEEDS_VALIDATION)
- 위치: `selfdrive/carrot/carrot_man.py`, `carrot_navi_route()`
- 값: 25.0 (km/h)
- 목적: route 역방향 DP의 감속 전환 시점 time_delay 계산에서 target_speed를
  이 값만큼 낮게 취급 — route가 vturn보다 사전감속을 더 일찍 시작하도록.
  최종 채택 target_speed(정점 목표값) 자체는 불변, 반영 타이밍만 조정.
- 근거: 시뮬레이션(devnotes work, bc4301a25d 캐시) — 커브A에서 vturn 실제
  전환보다 3.76초 먼저 개입, 직선 154초/커브B 오탐 0건. 20/30 사이 사용자
  확정값.
- 실차 검증: 미실시(NEEDS_VALIDATION).

## ROUTE_SPEED_LOOP_DT (132차, NEEDS_VALIDATION)
- 위치: `selfdrive/carrot/carrot_man.py`, `carrot_navi_route()`
- 값: 0.05 (초, 20Hz) — `broadcast_version_info()`의 `Ratekeeper(20)`과
  일치시킨 값. 별도 튜닝 대상 아님(루프 주기 그 자체).
- 목적: 131차 Hypothesis C(route_lookahead 윈도우 경계 진입 시 curvature
  이산적 출현 -> out_speed 단일프레임 급락) 완화용 프레임간 램프 리미터의
  주기값. 상한 계산식: `accel_limit_kmh(=AutoNaviSpeedDecelRate*3.6) * ROUTE_SPEED_LOOP_DT`.
  새 튜닝 상수 없이 기존 `AutoNaviSpeedDecelRate`를 재사용.
- 근거: `toolkit/sim_route_boundary_ramp_limiter.py`(132차) 사전검증 —
  curve_R 10~25m/accel 0.70~1.2 전 조합 PASS.
- 실차 검증: 미실시(NEEDS_VALIDATION) — 129차와 동일/유사 교차로 재주행
  필요.

## ROUTE_CURVATURE_FINE_SAMPLE (147차 계속, NEEDS_VALIDATION)
- 위치: `selfdrive/carrot/carrot_man.py`, `carrot_navi_route()`
- 값: 1 (=10m chord, 리샘플 네이티브 해상도). 기존 매크로 `sample=4`
  (40m chord)는 상수화하지 않고 그대로 리터럴 유지 — 이 값만 신규.
- 목적: 89/90차가 의심했던 "route 곡률 chord=40m 단독 샘플링이 좁은
  코너를 평활화해 놓친다"는 가설을 실측 naviPaths(147차)로 확정.
  기존 sample=4 매크로 계산은 그대로 두고, 같은 위치에서 이 값(fine
  sample)으로 한 번 더 3점 곡률을 계산해 더 급한(speed_cap이 더 낮은)
  쪽만 채택(merge, 대체 아님) — 매크로의 직선구간 오탐방지 특성은
  유지.
- 근거: `898edd0f96` seg10 실측(--with-navi-paths) — 40m chord 단독:
  실제 R≈27m(steer -49.9°) 커브를 R≈110m로 평활화, 0.02 임계값 미도달
  → nRoadLimitSpeed(무제한) 클램프. 10m chord(=1): 같은 지점
  R≈27m/speed_cap 10.1km/h로 정상 포착. 같은 로그 직선구간(122포인트,
  steer≈0)에서 fine sample 적용해도 max|curvature|=0.0146으로 임계값
  미도달 — 오탐 없음. FINDINGS.md 147차 계속 참고.
- 실차 검증: 미실시(NEEDS_VALIDATION) — 이번 패치가 적용된 코드로
  실주행 재현 및, 특히 다른 route(고속도로/GPS노이즈 큰 구간)에서
  fine sample의 오탐률 확인이 다음 세션 우선순위.
