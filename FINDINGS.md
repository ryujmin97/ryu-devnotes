# FINDINGS — 이슈 / 검증 상태 누적 기록

세션이 끝나도 남아야 하는 것만 여기 기록한다. 대화 내용 전체를 옮기지 말고,
"무엇을 발견했고, 지금 상태가 뭔지"만 짧게. 새 세션 시작할 때 이 파일을
먼저 훑으면 이미 끝난 걸 다시 분석하지 않아도 된다.

각 항목 형식:
```
## [상태] 제목 (발견일, 관련 커밋/파일)
- 증상:
- 원인:
- 조치: (수정됨 / 검토중 / 보류)
- 근거 로그: (있으면 라우트명 + 타임스탬프)
```
상태 태그: `[FIXED]` 수정 완료 / `[INVESTIGATING]` 원인 분석 중 /
`[NEEDS_VALIDATION]` 코드는 있으나 실도로 검증 필요 / `[WONTFIX]` 보류

---

## [FIXED] radard KjException 크래시 — dPath numpy.float64 캐스팅 누락 (2026-08-17, 커밋 2c34855)
- 증상: EnableRadarTracks<3 (Genesis DH 기본) 순수 비전 리드 경로에서 radard가
  KjException으로 죽음 → radarState dead → soft disable → engage 해제.
- 원인: `VisionTrack.get_lead()`에서 `self.dPath`가 numpy 타입 그대로 capnp
  구조체에 대입됨. `Track.get_RadarState()`류는 이미 float() 캐스팅돼 있었는데
  이 함수만 누락.
- 조치: FIXED. float() 캐스팅 추가.
- 근거 로그: t=140.78 radard exitCode=1, t=141.23~144.23 soft disable→disable.

## [FIXED] t_follow 이중 apply_t_follow 호출로 0에 수렴 (2026-08-17, 커밋 a12d729)
- 증상: 차선변경 중 longitudinalPlan.tFollow가 0.005~0.09까지 붕괴, 옆차선
  선행차와 위험하게 근접.
- 원인: `get_T_FOLLOW()`와 `dynamic_t_follow()`가 각자 내부에서
  `apply_t_follow()`(증가방향 레이트리미터)를 호출 → 차선변경으로 줄어든 값이
  다음 사이클 리미터 기준선이 되어 재귀적으로 계속 축소.
- 조치: FIXED. 두 함수는 raw 값만 반환, `long_mpc.update()`에서 최종 확정된
  t_follow에 대해 apply_t_follow()를 정확히 1회만 호출하도록 정리.
- 근거 로그: 시뮬레이션 재현 — OLD 로직 0.5초만에 0.00215로 수렴, 관측값과 일치.

## [FIXED] vturn 슬루 리미터 min/max 반전 (2026-08-16, 커밋 ab156ea)
- 증상: 커브 감속(vTurnSpeed)이 "변화율 상한"이 아니라 "최소 변화량 강제"로
  동작 → 20Hz 루프에서 프레임당 -10%/+8% 복리 누적, 1초 안에 -88%/+366%까지
  튈 수 있는 상태. vTurnSpeed는 크루즈 목표속도 결정(min())에 직접 쓰임.
- 원인: 슬루 제한 코드의 min()/max() 방향이 반대로 작성됨.
- 조치: FIXED. 동시에 "탈출 후 2초 고정 지연 가속회복" 상태머신도 제거하고
  1차 저역통과 필터(감속 rc=0.25s, 가속 rc=0.6s)로 교체 — 이 상태머신이
  오히려 "커브 빠져나오고도 한참 안 밟는" 현상의 직접 원인이었음.
- 참고: 이전에 있었던 "persistent state machine (apex/exit lock-in, freeze
  재획득)" 방식은 같은 날 안에 폐기되고 lookahead 기반 벡터화 방식으로
  대체됨. 과거 세션 요약에 그 상태머신이 언급돼 있다면 이미 구버전 설명임.

## [NEEDS_VALIDATION] LEAD_ACQ_RAMP_TIME=5.0s / LEAD_ACQ_TTC_DANGER=2.5s (2026-08-17~)
- 목적: 리드 최초 인식 시 관측치가 부정확한 구간(비전/레이더 무관)에 대한
  선제적 감속 하한선. TTC 실시간 재계산으로 경과시간 램프가 못 잡는 급접근
  케이스 보완.
- 상태: 코드는 완결(min() 기반 floor, 안전방향으로만 작동 확인됨). 실도로
  파라미터 자체(RAMP_TIME 5.0s가 적정한지, TTC 임계값 2.5s/6.0s가 적정한지)
  검증 아직 부족.
- 2026-08-18 로그 분석 (x9seg, 522초 시내주행) 결과:
  - 리드 인식 이벤트 13건 중 cruiseEnabled=True(로직이 실제 작동 가능한
    조건)는 8건. 그중 TTC가 DANGER(2.5s) 아래로 내려간 케이스 0건.
  - 가장 근접했던 케이스(seg8 t=556.22, ttc_min=3.62s)도 원인은 route
    기반 감속으로 보이며 aEgo 반응은 매끈함(튐 없음).
  - 얼핏 "위험 케이스"로 보였던 seg6(t=436.95, vRel=-7.49m/s)는 실제로는
    리드가 0.6초 만에 사라지고(LOSS_GRACE_TIME 넘어 리셋) 이후 급감속은
    vturn(커브)+운전자 브레이크가 원인 — LEAD_ACQ와 무관한 이벤트였음.
  - 진짜 위험 TTC(0.98s, seg12 t=808.20)는 cruiseEnabled=False(운전자 수동
    브레이크 중)라 ACC 로직 검증에 못 씀.
  - 이 로그로는 검증 불가. 고속도로 순항 중 크루즈 켠 채로 리드가
    가깝게/빠르게 나타나서 계속 락온 유지되는 로그 필요.
- **2026-08-18 로그 분석 (x12seg, 722초/3.78km, "가속 지연/설정속도 미달"
  체감 불만 제보 주행) — 처음으로 조건에 맞는 사례 확보:**
  - seg10 t=657.39: leadStatus 유지 상태에서 leadDRel이 **한 프레임(dt=0.05s)
    만에 75.1m→12.2m로 점프**(radard LeadBlend closer_jump/big_jump 게이트
    발동 조건). vEgo 57.1km/h, vCruise 70km/h, leadVRel -0.9m/s(TTC 약 13.6s,
    DANGER 아님) — 고속 순항 중 갑자기 가까운 리드가 나타난 사례.
  - 반응: 이후 약 6초간 aEgo가 -0.3~-0.98 사이에서 **매끈하게** 눌리며
    vEgo 57.1→45.0km/h로 감속. 급브레이크성 스파이크 없음.
  - **결론: LEAD_ACQ_RAMP_TIME=5.0s 로직이 실제로 "급조작 없이 선제감속"
    의도대로 동작한 첫 실사례.** 표본 1건이라 추가 검증 필요하지만
    긍정적 데이터포인트. 이 사례로 RAMP_TIME 5.0s 자체가 너무 길다/짧다는
    판단은 아직 어려움(감속 총량이 크지 않아 상한 근처까지 안 감).
  - 참고: seg2 t=211.85~216.05 (leadDRel 62.5m→7m, vRel -7~-11m/s 지속,
    aEgo 최대 -2.7)는 physically 일관된 급정지 선행차 추종 상황 —
    급감속이지만 **버그 아님**, 정상 ACC 동작으로 확인.
  - **[NEEDS_VALIDATION 신규] 비전 리드 트래킹 노이즈 발생 빈도**: 같은
    leadStatus 유지 구간에서 leadDRel이 프레임당(≤0.3s) 8m 이상 튀는
    이벤트가 12분 주행 중 46건(~15초당 1회) 관측됨. 대부분은 감속으로
    이어지지 않았으나(예: t=327.16, 647.04 등은 오히려 가속 지속),
    EnableRadarTracks<3 비전 폴백 구조와 일치하는 증상. 컨트롤에 미치는
    영향은 크지 않아 보이나 LeadBlend 게이트 발동 빈도 자체가 높다는 점은
    추가 로그로 누적 확인 필요.
  - **사용자 체감 불만("지연 출발/설정속도 미달")의 주 원인은 버그보다는
    커브/교차로 밀집 구간 특성으로 추정**: cruiseEnabled 구간의 13.1%가
    desiredSource=vturn(커브 감속캡)이었고, vCruise는 62~90km/h로 계속
    설정돼 있었는데 실속도는 20~55km/h대에 머묾. 회전이 잦은 도로에
    고속 크루즈를 걸어둔 상황과 일치 — 로직상 정상 동작으로 판단되나,
    vTurnSpeed 캡 자체가 체감상 과도하게 보수적인지는 추가 검토 여지 있음.
    (참고: 운전자 gas override 비율도 cruiseEnabled 구간의 4.3%로 다소
    높음 — 체감 불만과 일치하는 정황.)

## [FIXED] CarrotWeb Drive 전송 진행률이 번갈아 뜨다가 (1/1) 0%에서 멈춘 뒤 타임아웃 (2026-08-18, 미적용 상태였던 커밋 8dbed62 기준 / 수정 커밋: fix-gdrive-upload-race 브랜치 f72e68a, 패치 파일로 전달)
- 증상: 로그탭에서 라우트 2개 선택 후 "Drive 전송" 시 상태 줄이
  "업로드 중(2/2)... 82%"와 "업로드 중(1/1)... 0% (Google Drive 연결
  확인 중...)" 사이를 번갈아 표시. (2/2) 쪽이 100% 완료돼 사라진 뒤에도
  화면은 (1/1) 0% 상태에 멈춰 있다가, 한참 후 "업로드 실패(1/1): Drive
  업로드 실패(네트워크/타임아웃): Timeout on reading data from socket"로
  실패 표시됨. (스크린샷 3장으로 재현 순서 확인, 실제 rlog 로그 분석은
  아님 — UI/서버 코드 리뷰로 원인 특정)
- 원인 (두 가지가 겹침):
  1. `logs.js`의 `btnDashcamUploadSelected`/`btnScreenrecordUploadSelected`
     버튼에 업로드 중 비활성화 로직이 없고 `uploadSelectedFiles()`에도
     재진입 가드가 없었음. 이전 업로드(예: 라우트 1개짜리, total=1)가
     아직 안 끝난 상태(특히 핸드셰이크 단계에서 응답이 느려 0%에 멈춰
     보일 때)에서 사용자가 다시 선택/전송하면(예: 전체선택 후 재전송,
     total=2) 두 번째 독립된 업로드 루프가 새로 시작됨. 두 루프 모두
     같은 `#logsStatus` DOM 한 줄을 `el.textContent = message`로 그냥
     덮어쓰기 때문에, 두 루프의 폴링 주기(500ms)가 엇갈리며 서로의
     메시지를 번갈아 지우는 것처럼 보임 — "번갈아 뜸"의 정체.
  2. `gdrive.py`의 `upload_file_resumable()`이 토큰 갱신(`_get_access_token`)
     / 폴더 조회·생성(`_ensure_folder`) / resumable 세션 여는 POST까지
     전부 청크 업로드용 `aiohttp.ClientSession(timeout=_UPLOAD_TIMEOUT)`
     (`sock_read=300s`)을 그대로 물려받아 사용했음. 이 세 요청은 원래
     1~2초짜리 작은 JSON 왕복인데, 기기 쪽 네트워크가 일시적으로
     끊기거나 응답이 늦으면 프론트에는 "Google Drive 연결 확인 중..."
     0%로 최대 5분간 아무 진행도 없이 멈춘 것처럼 보이다가 뒤늦게
     `Timeout on reading data from socket`으로 실패. 사용자 입장에서는
     "멈춘 것 같다"고 느끼고 재시도(버튼 재클릭)하게 되는 유인이 되어
     1번 문제와 맞물림.
- 조치: FIXED (코드 완결, 실기기 검증은 아직).
  - `logs.js`: `logsState.gdrive.uploading` 재진입 가드 추가 + 업로드
    중 두 업로드 버튼 모두 disabled 처리, `try/finally`로 확실히 해제.
  - `gdrive.py`: 핸드셰이크 전용 `_HANDSHAKE_TIMEOUT`(total=20s,
    sock_connect=10s, sock_read=15s)을 신설해 토큰갱신/폴더조회·생성/
    resumable 세션 오픈 요청에 개별 적용. 실제 청크 PUT 루프는 기존
    관대한 타임아웃(`_UPLOAD_TIMEOUT`, sock_read=300s) 그대로 유지
    (느린 회선에서도 대용량 전송이 끝까지 가야 하므로).
- 검증 필요: 실기기에서 (a) 업로드 중 버튼 재클릭 시 토스트만 뜨고
  두 번째 루프가 안 생기는지, (b) 의도적으로 네트워크를 끊은 상태에서
  Drive 전송 시 20초 내외로 빨리 실패 메시지가 뜨는지 확인.
- 근거 로그: 없음 (사용자 제공 스크린샷 3장 기반 코드 리뷰. rlog 분석
  대상 아님).

## [NEEDS_VALIDATION] LeadBlend closer_jump(8m)/big_jump(15m) 게이트, CUTOUT_* (2026-08-16, 커밋 084a5b8)
- 상태: route1/route2 특정 이벤트로 검증됨(closer_jump: route1 seg13 t=794s,
  big_jump: route1 t=1388~1390s / route2 t=825~827s). 표본이 각 1건씩이라
  추가 로그로 재현성 확인하면 좋음.

## [NEEDS_VALIDATION] LEAD_ACQ_LOSS_GRACE_TIME(0.5s)가 실측 레이더/비전 플리커 유실시간보다 짧을 가능성 (2026-08-19, x11seg 라우트, HEAD 366009153812)
- 근거: 원본 12436프레임에서 `lead_presence_segments(min_duration_s=0.5)`로
  뽑은 1초 미만 lead-lost 구간 4건 전부, 실측 유실시간(마지막 True 프레임
  ~다음 True 프레임)이 0.5s를 초과함:

  | seg | t 구간 | vEgo | dRel 전→후 | 실측 유실시간 |
  |---|---|---|---|---|
  | --2 | 203.41→204.11 | ~9 m/s (주행) | 44.9~45.2 → 47.2~47.4m (연속적, 같은 리드로 보임) | ~0.70s |
  | --6 | 424.56→425.51 | ~0.07 m/s (거의 정지) | 21.1→15.2m (튐) | ~0.95s |
  | --8/--9 경계 | 595.11→596.11 | ~18.3 m/s (고속) | 78.7→93.4m (등속 가정 시 예상 ~81m와 12m 이상 불일치) | ~1.00s |
  | --9 | 649.66→650.61 | ~7 m/s | 35.2m 근처 유지 | ~0.90s |

- 해석: 4건 모두 `LEAD_ACQ_LOSS_GRACE_TIME=0.5s`를 초과 — lead acquisition
  램프의 debounce가 실주행 중 레이더 플리커로 인해 의도보다 자주
  리셋(재확인 대기 `LEAD_ACQ_CONFIRM_TIME=0.2s`부터 다시 카운트)될 여지가
  있음을 시사하는 첫 정량적 근거. `EnableRadarTracks < 3` 상태라 비전
  폴백 의존도가 높은 것과 맞물려 있을 수 있음.
- 특기사항: 595~596s 구간(고속 주행 중)은 유실 전후 dRel 변화가 등속
  가정과 12m 이상 어긋남 — 같은 리드의 노이즈가 아니라 근거리 리드
  소실 + 원거리 리드 재포착(컷아웃 유사 상황)일 가능성도 있어 LEAD_ACQ
  단독 이슈로 단정하기는 이름. dashcam(mp4) 동기화로 실제 장면 확인은
  아직 안 함.
- 표본: 이번 1개 라우트, 4건. 그레이스 타임 조정 전 추가 라우트로
  재현성 확인 필요.
- 근거 로그: `20260819_062438_000002c9--63f3712592` (x11seg, HEAD
  366009153812, dirty=False)

## [VALIDATED] x16seg 라우트 종방향 전구간 클린 — harsh brake 전부 운전자 개입 (2026-08-19, HEAD 366009153812)
- 16.44km / 955s (19093 프레임) 전체에서 `harsh_brake_events` 15건 발생했으나
  전부 해당 프레임에서 `cruiseEnabled=False` 확인됨. 두 클러스터
  (t=3242~3244 교차로 정지신호 앞 정지, t=3381~3396 도심 구간·오토바이
  통행) 모두 dashcam 프레임으로 확인한 결과 신호대기/도심 저속 구간에서
  운전자가 먼저 disengage 후 수동 제동한 것 — ADAS가 활성 상태에서
  급제동을 유발한 사례는 이번 라우트에 0건.
- cruise_engage_disengage_events 2건(disengage) 모두 위 두 지점과 일치,
  재인게이지 1건(t=3284.8)도 정상적인 재출발.
- 근거 로그: `20260819_114324_000002cb--6ef53b224d` (x16seg)

## [VALIDATED] 근거리 컷인 유사 이벤트 매끈한 반응 (2026-08-19, x16seg t=2516.9~2519)
- t=2516.93~2517.18 (0.25s, 0.5s 미만이라 lead_presence_segments엔
  안 잡힘) 순간 leadStatus 유실 후 재포착 시 dRel이 12.1m→4.7m로
  점프, leadVRel도 -0.5→+3.4로 튐 (근접 차량 재포착/컷인 유사 패턴).
  이후 aEgo가 -0.2→-0.8 m/s²까지 약 2초에 걸쳐 매끄럽게 램프,
  harsh_brake_events에 잡히지 않음. lead_cut_in_detector가 이 지점을
  검출은 했지만 컨트롤 반응 자체는 튀지 않은 양호 사례.
- 근거 로그: 위와 동일.

## [NEEDS_VALIDATION] carrot_serv.py speed_n_sources min() 선택에 히스테리시스 없음 — src/desiredSpeed 잦은 플리커 (2026-08-19, x16seg)
- 코드: `desired_speed, source = min(speed_n_sources, key=lambda x: x[0])`
  (carrot_serv.py) — 매 프레임 후보(atc/road/vturn/route/model 등) 중
  최솟값을 그대로 채택. 후보값들이 서로 근접해 있으면 프레임 노이즈만
  으로도 `source`(및 `desiredSpeed` 그 자체)가 프레임 단위로 왕복.
- 실측: 전체 85건의 src 전환 중 1초 이내 4건 이상 몰린 "플리커 클러스터"
  5곳 확인 (t=3144.4~3145.8 10건/1.4s, t=3206.4~3206.8 4건/0.4s,
  t=3223.4~3225.2 5건/1.8s, t=3236.2~3236.9 5건/0.7s, t=3404.4~3407.2
  6건/2.8s). 대부분 완만한 커브가 이어지는 국도 구간(curvature
  0.0005~0.0007, 거의 직선에 가까움)에서 road/route/vturn 캡값이
  171~200 사이로 서로 근접할 때 발생. 예: t=3146.88 desiredSpeed=171
  → t=3147.68 194 (0.8s만에 23km/h 왕복).
- 실제 영향: 이번 라우트에서는 aEgo 변동폭이 -0.03~-0.47 m/s² 수준으로
  작아 체감 저크는 미미함 (하류 슬루 리미터가 상당 부분 흡수하는 것으로
  보임). 다만 후보값 간 격차가 더 벌어지는 상황에서는 `desiredSpeed`
  자체가 소스 라벨과 함께 튀어 체감 저크로 이어질 수 있어 구조적
  리스크로 기록. 최소값 선택에 짧은 dwell-time/hysteresis(예: N프레임
  연속 우세해야 전환)를 추가하는 방안 검토 여지 있음.
- 근거 로그: 위와 동일 (`source_transition_log` 결과 기반).

## [VALIDATED] 정지 선행차 추종 감속 — 클린 케이스 (2026-08-19, x11seg 라우트)
- t=597~606s: 리드 정지(`leadVLead`→0 근처)에 맞춰 17.5→1.4 m/s까지
  8.9초 동안 매끈하게 감속(min_aEgo=-2.53 m/s²), `leadStatus=True` 끊김
  없이 `src=route`가 처음부터 끝까지 감속을 주도. lead acquisition
  램프나 LeadBlend가 별도 개입할 필요 없는 이상적 케이스 — 정지 리드
  처리가 최소한 이런 클린한 시나리오에서는 잘 동작함을 보여주는
  긍정적 사례로 기록.
- 근거 로그: 위와 동일.
