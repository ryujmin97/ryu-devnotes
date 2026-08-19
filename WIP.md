# WIP — 중단 지점 (체크포인트, 세션 종료 아님)

- 저장 시각: 2026-08-20 (3차, 사용자 "저장" 요청)
- HEAD (c3-ms-dev): `f7b154638cf2` — ryu 코드 변경 없음. devnotes
  `toolkit/extract_dashcam_frames.py`는 2차 체크포인트 이후 파일 자체
  변경 없음 (실데이터 검증만 이번에 완료, 코드 수정 아님).

## 이번 세션(3차)에서 완료된 것 — 코드 변경 없어 push 대상 아님
- **`extract_dashcam_frames.py` 실데이터 검증 완료**: 사용자가 테스트로
  올려준 세그(segmentNum=35, t=2155.67~2215.57s, route 260819-1의 뒷부분
  세그로 추정 — FINDINGS.md의 `--2`/`--3`(t≈205~278s) 이벤트와는 다른
  세그)로 기능 검증:
  - `qRoadEncodeIdx` 1200 프레임 전부 인덱싱 확인
  - target_t 3건 매칭 오차 10~27ms (경고 임계 0.15s 대비 충분히 정밀)
  - ffmpeg 프레임 추출 정상 (실제 도로 장면 육안 확인 — 신호등/선행차량/
    표지판 선명)
  - `make_side_by_side()` 라벨 합성도 정상
  - → **스크립트 자체는 실증 완료. 정차열 리드 대체 가설 검증은 아직
    실제 대상 세그(`--2`/`--3`) 미확보로 미착수.**
- **세션 간 원본 업로드 관련 방침 확정** (사용자 질문에 대한 답):
  프로젝트 파일 업로드를 안 쓰는 구조라 `/mnt/user-data/uploads`는
  대화(채팅창) 종료 시 소실 — 새 세션마다 원본 rlog/qcamera 재업로드
  필요함을 확인. 용량 절감을 위해: **대시캠 프레임 검증처럼 영상 확인이
  필요한 항목은, 결과로 나온 비교 이미지(jpg, 수십KB)를 devnotes에
  커밋해두고 원본은 재업로드하지 않는 방식으로 진행하기로 함.** 원본
  로그 자체(rlog/qcamera, 수 MB~수십 MB)는 개인 주행 영상이라
  퍼블릭 devnotes에 커밋하지 않음 — 검증에 필요한 최소 결과물만 남김.

## 지난 세션(2차)에서 완료된 것 (이미 push됨, 재작업 불필요)
- **`devnotes/toolkit/extract_dashcam_frames.py` 신규 작성** — 정차열
  리드 대체 가설 검증용 dashcam(qcamera.ts) 프레임 추출/동기화 스크립트.
  - `cereal/log.capnp`의 `qRoadEncodeIdx`(EncodeIndex) 이벤트를 이용:
    `logMonoTime`(=extract_log.py CSV의 `t`와 동일 시간축)과 `segmentId`
    (세그먼트 내 qcamera.ts presentation-order 인덱스)를 매칭해 `t*fps`
    근사가 아니라 정밀 프레임 매칭.
  - 주요 함수: `build_frame_time_index()`, `nearest_frame_for_time()`
    (매칭오차 0.15s 초과 시 경고), `extract_frames_for_times()`
    (manifest.json 생성), `make_side_by_side()` (전/후 프레임 라벨 붙여
    합성, PIL).
  - 커밋: https://github.com/ryujmin97/ryu-devnotes/commit/5e511b8bef22d51f294bad4e9880c70ef195da8c

## 지난 세션(1차)에서 완료된 것 (이미 push됨, 재작업 불필요)
- 라우트 `260819-1`(x20seg, 25.6km/1200s, ADAS 활성 97.3%) 실주행 로그
  분석 완료.
- FINDINGS.md / PARAMS_REGISTRY.md / LAST_ANALYZED.md 갱신 후
  push_via_api.py로 push 완료.
  커밋: https://github.com/ryujmin97/ryu-devnotes/commit/2b39fe6cc34ef62a2c6f2fe5294add3d49f200b8
- 주요 발견 요약 (상세는 FINDINGS.md 참고):
  1. `LEAD_ACQ_LOSS_GRACE_TIME(0.5s)` 초과 사례 6~7건 신규 확보 (누적
     11~12건, 유실시간 최대 2.46s). 정차열(vEgo=0.0) 중 dRel 8~12.5m
     감소 재포착 신규 패턴 발견 — 리드 대체(다른 차량으로 전환)
     의심.
  2. `speed_n_sources` min() 히스테리시스 부재로 인한 src/desiredSpeed
     플리커가 국도뿐 아니라 73~113km/h 고속 커브 구간 전반에서 재현
     (A→B→A 패턴 49건, 총 전환 164건 중).
  3. harsh brake / turn violation / steering oscillation / cut-in —
     전부 클린 (특이사항 없음).
- 코드 패치 없음 — 이번 세션은 순수 관찰/분석 세션.

## 진행 중이던 코드 작업
없음 (ryu 코드 변경 없음). devnotes/toolkit 스크립트 작성은 완료,
실데이터 검증만 남음.

## 다음 세션(또는 이어서)에서 착수할 것 — 우선순위 1
**정차열 리드 대체 가설 검증 — 실행 대기 중.**
- 준비 완료: `extract_dashcam_frames.py` 작성 + **실데이터 검증까지 완료**
  (다른 세그로 스모크 테스트, 매칭 오차 10~27ms 확인 — 3차 체크포인트
  참고). 로직은 신뢰 가능, 이제 대상 세그만 있으면 바로 실행 가능.
- 필요: 사용자가 라우트 260819-1의 `--2`(및 가능하면 `--1`,`--3`,`--4`)
  세그먼트를 `qcamera.ts` + `rlog.zst` 포함해서 업로드하기로 함
  (아직 미업로드 — 매 세션 재업로드 필요함을 확인/합의함, 3차 체크포인트
  참고).
- 업로드되면 바로 실행할 커맨드 (타겟 시각은 FINDINGS.md L399-407 표):
  ```bash
  cd /home/claude/devnotes/toolkit
  python3 extract_dashcam_frames.py \
      /home/claude/work/route/--2 \
      --repo /home/claude/ryu \
      --times 205.53,207.99,208.69,210.48 \
      --out-dir /home/claude/work/frames \
      --context 2
  # --3 세그(263.84,264.63,277.33,277.83)도 동일하게, --3 폴더로 별도 실행
  ```
- 이후 `make_side_by_side()`로 유실 직전/재포착 직후 프레임 비교 이미지
  생성 → 육안으로 같은 차량인지 확인 → 결과를 FINDINGS.md 해당 항목
  ([NEEDS_VALIDATION] 정차열 리드 대체, L393-429)에 추가.
- rlog.zst가 아니라 qlog.zst만 오면 qRoadEncodeIdx 커버리지가 낮아
  매칭 오차 커질 수 있음 — 스크립트가 경고 출력하니 확인.

## 다음 세션에서 이어갈 후보 (순위 2 이하, 아직 착수 안 함)
1. **src flicker 실제 영향 정량화**: seg4~8/11~12/18~19의 vturn↔road/
   model/route 플리커 클러스터 구간에서 desiredSpeed 왕복폭과 실제
   aEgo/저크 반영 여부(하류 슬루 리미터 흡수량) 미분석 — 다음
   세션에서 정량화.
2. (기존 on-the-horizon 항목들 — PROJECT_INSTRUCTIONS.md/README.md
   참고) LEAD_ACQ_RAMP_TIME=5.0s, LEAD_ACQ_TTC_DANGER=2.5s 검증용
   고속 근접 리드 lock-on 로그 여전히 필요.
   CarrotWeb 로그탭 UI 버그(Drive 전송 중 화면 교차/정체)도 미해결.

## 다음 세션 시작 시
이 WIP.md가 존재하면 위 "다음 세션에서 이어갈 후보" 중 사용자가
지정하는 항목부터 진행. 착수/해소되면 해당 항목을 이 파일에서
제거하거나 완료 표시.
