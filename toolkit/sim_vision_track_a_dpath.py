#!/usr/bin/env python3
"""
60차: A(tentative 조기등록) 재설계 로직 단위 합성검증.

배경: 58차3번(A+B)이 실주행 체감 오탐/불필요감속으로 롤백됨(FINDINGS.md
"58차 3번+후속수정 REVERTED" 참고). 유일하게 잡힌 A 발동 사례(seg2)는
qcamera로 "역광+다차선 인접차량 혼선"으로 확인됐었음 -- 실제 감속엔
영향 없었다고 당시엔 판단했지만, dRel jitter(8m) 게이트만으론 dRel은
비슷하고 dPath(차선 대비 좌우 위치)만 다른 옆차선 차량류를 못 거를 수
있다는 가설로 이번 세션에서 dPath 안정성 게이트 + dRel 경량 중앙값
필터를 추가함(radard.py 실제 코드 참고). B(저확신구간 안전측 보정)는
이번엔 제외 -- 롤백 원인이 A/B 중 어느 쪽인지 불명확했으므로 변수를
하나씩만 바꿔 재검증.

radard.py는 cereal/capnp 컴파일 의존이라 컨테이너에서 직접 import 불가
-- VisionTrack.update()의 tentative 등록 분기만 순수 파이썬으로 재현해서
검증한다(기존 sim_vision_track_ab.py와 동일 관행).

radard.py 실제 코드와 반드시 동일하게 유지해야 하는 상수/로직:
- VISION_TRACK_TENTATIVE_PROB_GATE=0.35, VISION_TRACK_TENTATIVE_CNT_GATE=10
- VISION_TRACK_TENTATIVE_DREL_JITTER=8.0
- VISION_TRACK_TENTATIVE_DPATH_JITTER=1.5
- VISION_TRACK_TENTATIVE_DPATH_ABS_GATE=1.75
- VISION_TRACK_TENTATIVE_MEDIAN_WINDOW=3
"""
import statistics
from collections import deque

VISION_TRACK_TENTATIVE_PROB_GATE = 0.35
VISION_TRACK_TENTATIVE_CNT_GATE = 10
VISION_TRACK_TENTATIVE_DREL_JITTER = 8.0
VISION_TRACK_TENTATIVE_DPATH_JITTER = 1.5
VISION_TRACK_TENTATIVE_DPATH_ABS_GATE = 1.75
VISION_TRACK_TENTATIVE_MEDIAN_WINDOW = 3


class VT:
    """radard.py VisionTrack의 tentative 등록 분기만 재현. dPath는 실제
    코드처럼 md.position 보간이 아니라, 시나리오가 직접 넘기는 값을 그대로
    사용(보간 로직 자체는 이번 변경과 무관해 단순화)."""

    def __init__(self):
        self.tentative_cnt = 0
        self.tentative_dRel_last = 0.0
        self.tentative_dPath_last = 0.0
        self.tentative_dRel_hist: deque[float] = deque(maxlen=VISION_TRACK_TENTATIVE_MEDIAN_WINDOW)
        self.status = False  # register_ok 근사(정식문턱 prob>.5는 시나리오에서 안 씀)

    def update(self, prob, dRel_candidate, dPath_candidate):
        if VISION_TRACK_TENTATIVE_PROB_GATE <= prob <= 0.5:
            self.tentative_dRel_hist.append(dRel_candidate)
            dRel_filtered = statistics.median(self.tentative_dRel_hist)
            if abs(dPath_candidate) > VISION_TRACK_TENTATIVE_DPATH_ABS_GATE:
                # 차로 밖(옆차로 등) -- "안정적으로 유지"돼도 jitter 게이트로는
                # 못 걸러지므로 절대값 게이트로 원천 배제.
                self.tentative_cnt = 0
                self.tentative_dRel_hist.clear()
            else:
                if self.tentative_cnt > 0 and (
                    abs(dRel_filtered - self.tentative_dRel_last) > VISION_TRACK_TENTATIVE_DREL_JITTER or
                    abs(dPath_candidate - self.tentative_dPath_last) > VISION_TRACK_TENTATIVE_DPATH_JITTER
                ):
                    self.tentative_cnt = 0
                    self.tentative_dRel_hist.clear()
                    self.tentative_dRel_hist.append(dRel_candidate)
                    dRel_filtered = dRel_candidate
                self.tentative_cnt += 1
                self.tentative_dRel_last = dRel_filtered
                self.tentative_dPath_last = dPath_candidate
        elif prob < VISION_TRACK_TENTATIVE_PROB_GATE:
            self.tentative_cnt = 0
            self.tentative_dRel_hist.clear()

        register_ok = self.tentative_cnt >= VISION_TRACK_TENTATIVE_CNT_GATE
        self.status = register_ok
        return register_ok, self.tentative_cnt


def scenario_stopped_lead_still_promotes():
    """핵심 회귀 확인: 58차3번 원 목적(정지앞차 조기인식) 자체가 이번
    dPath 게이트 추가로 막히면 안 됨. 진짜 정지앞차(dPath 거의 고정,
    같은 차로) 8초 접근 시 여전히 조기 등록돼야 함."""
    vt = VT()
    dRel = 130.0
    dPath = 0.1  # 같은 차로, 살짝의 차선유지 노이즈만
    first_registered_frame = None
    for i in range(160):
        dRel -= 0.05
        dPath += 0.001 * (1 if i % 2 == 0 else -1)  # 미세한 노이즈만, 옆차선 수준 아님
        ok, tcnt = vt.update(prob=0.42, dRel_candidate=dRel, dPath_candidate=dPath)
        if ok and first_registered_frame is None:
            first_registered_frame = i
    result = first_registered_frame is not None and first_registered_frame <= 12
    print(f"[정지앞차 조기등록 유지] 최초 등록 프레임={first_registered_frame} (프레임10 근처 기대) -> {'PASS' if result else 'FAIL'}")
    return result


def scenario_side_lane_vehicle_blocked():
    """58차3번 seg2류 재현: 역광/인접차량 혼선으로 dRel은 정지앞차와
    비슷한 값을 유지하지만(같은 8m 이내), dPath는 옆차로 수준
    (|dPath|~2.5m)으로 뚜렷이 벗어나 있는 경우. dRel jitter 게이트만
    있던 58차3번 원안이라면 승격됐을 케이스 -- 이번 dPath 게이트로
    반드시 차단돼야 함."""
    vt = VT()
    dRel = 90.0
    dPath = 2.5  # 옆차로 수준 오프셋, 안정적으로 유지(dRel jitter만으론 못 거름)
    ever_registered = False
    for i in range(200):
        dRel -= 0.03  # dRel 자체는 서서히 접근하는 것처럼 보임(진짜처럼 위장)
        ok, tcnt = vt.update(prob=0.40, dRel_candidate=dRel, dPath_candidate=dPath)
        ever_registered = ever_registered or ok
    result = not ever_registered
    print(f"[옆차선 차량 승격 차단] 200프레임간 등록 여부={ever_registered} (False 기대) -> {'PASS' if result else 'FAIL'}")
    return result


def scenario_dpath_jitter_resets_like_drel():
    """dPath가 dRel처럼 튀는(다른 물체로 전환 추정) 경우도 리셋돼야 함 --
    dRel은 안정적인데 dPath만 왔다갔다 하는 극단 케이스로 게이트 독립
    동작 확인."""
    vt = VT()
    import random
    random.seed(1)
    dRel = 80.0
    ever_registered = False
    for i in range(200):
        dRel -= 0.02
        dPath = random.uniform(-3.0, 3.0)  # 매 프레임 좌우로 크게 요동(다중 물체 혼선 재현)
        ok, tcnt = vt.update(prob=0.42, dRel_candidate=dRel, dPath_candidate=dPath)
        ever_registered = ever_registered or ok
    result = not ever_registered
    print(f"[dPath 요동 오인승격 방지] 200프레임간 등록 여부={ever_registered} (False 기대) -> {'PASS' if result else 'FAIL'}")
    return result


def scenario_median_filter_absorbs_single_frame_snap():
    """dRel 경량 중앙값 필터 확인: 안정적으로 접근 중인 진짜 정지앞차인데
    단 1프레임만 스냅 노이즈(순간 10m 튐)가 섞여도, 3프레임 중앙값
    필터가 이를 흡수해 tentative_cnt가 불필요하게 리셋되지 않아야 함
    (필터 없으면 그 프레임에서 jitter>8m로 리셋됨)."""
    vt = VT()
    dRel = 100.0
    dPath = 0.0
    for i in range(30):
        dRel -= 0.05
        if i == 15:
            dRel_frame = dRel + 10.0  # 단일 프레임 스냅 노이즈
        else:
            dRel_frame = dRel
        ok, tcnt = vt.update(prob=0.42, dRel_candidate=dRel_frame, dPath_candidate=dPath)
    # 필터 덕분에 리셋 없이 30프레임 거의 다 카운트가 쌓여 있어야 함(약간의 흡수 지연은 허용)
    result = vt.tentative_cnt >= 25
    print(f"[중앙값필터 단일스냅 흡수] 최종 tentative_cnt={vt.tentative_cnt} (>=25 기대, 30프레임 중) -> {'PASS' if result else 'FAIL'}")
    return result


def scenario_low_prob_still_no_promotion():
    """회귀 확인: prob가 TENTATIVE_PROB_GATE(0.35) 밑이면 dPath/dRel이
    아무리 안정적이어도 여전히 승격 안 돼야 함(기존 58차3번 A-2와 동일
    성격, dPath 게이트 추가가 이 경로에 영향 주면 안 됨)."""
    vt = VT()
    dRel = 100.0
    ever_registered = False
    for i in range(200):
        dRel -= 0.05
        ok, tcnt = vt.update(prob=0.2, dRel_candidate=dRel, dPath_candidate=0.0)
        ever_registered = ever_registered or ok
    result = not ever_registered
    print(f"[저prob 미등록 회귀] 200프레임간 등록 여부={ever_registered} (False 기대) -> {'PASS' if result else 'FAIL'}")
    return result


if __name__ == "__main__":
    results = [
        scenario_stopped_lead_still_promotes(),
        scenario_side_lane_vehicle_blocked(),
        scenario_dpath_jitter_resets_like_drel(),
        scenario_median_filter_absorbs_single_frame_snap(),
        scenario_low_prob_still_no_promotion(),
    ]
    print(f"\n총 {len(results)}건 중 {sum(results)}건 PASS")
    assert all(results), "일부 시나리오 FAIL -- 코드 재검토 필요"
