#!/usr/bin/env python3
"""
87차: VisionTrack tentative 래치가 prob 영구 소실 시 못 풀리는 버그 검증 +
GHOST_TIMEOUT 패치 효과/회귀 시뮬레이션.

radard.py의 capnp/cereal 의존성을 피하기 위해 update() 로직 중
tentative_cnt/register_ok/ghost_low_prob_time 계산 부분만 순수 파이썬으로
재현한다(dRel/vRel 등 하류 계산은 이번 검증과 무관해 생략).
"""

TENTATIVE_PROB_GATE = 0.35
TENTATIVE_CNT_GATE = 10
GHOST_TIMEOUT_S = 3.0
RADAR_TS = 0.05  # 20Hz


class Sim:
    def __init__(self, ghost_timeout_enabled: bool):
        self.tentative_cnt = 0
        self.ghost_low_prob_time = 0.0
        self.ghost_timeout_enabled = ghost_timeout_enabled
        self.register_ok_log = []

    def step(self, prob: float):
        # tentative 카운트 적립 (dPath/jitter 게이트는 이번 시나리오와 무관해
        # 항상 통과한다고 가정 -- 목적은 prob 게이트/타임아웃 로직 검증)
        if TENTATIVE_PROB_GATE <= prob <= 0.5:
            self.tentative_cnt += 1

        if self.ghost_timeout_enabled:
            if prob < TENTATIVE_PROB_GATE:
                self.ghost_low_prob_time += RADAR_TS
            else:
                self.ghost_low_prob_time = 0.0
            if self.ghost_low_prob_time >= GHOST_TIMEOUT_S:
                self.tentative_cnt = 0

        register_ok = (prob > 0.5) or (self.tentative_cnt >= TENTATIVE_CNT_GATE)
        self.register_ok_log.append(register_ok)
        return register_ok


def run(prob_seq, ghost_timeout_enabled):
    sim = Sim(ghost_timeout_enabled)
    for p in prob_seq:
        sim.step(p)
    return sim.register_ok_log


def scenario_ghost():
    """실차 재현: 0.5s간 tentative 문턱(0.35~0.5) 스침 -> 이후 120초간 prob 거의 0"""
    seq = [0.40] * 10          # 0.5s tentative 적립 -> tentative_cnt=10 래치
    seq += [0.01] * int(120 / RADAR_TS)  # 120초간 완전 소실
    return seq


def scenario_real_flicker():
    """B안이 보호하려던 진짜 리드: prob가 0.0x~0.5 사이를 노이즈처럼 넓게
    출렁이되, 한 번에 GHOST_TIMEOUT(3.0s)만큼 연속으로 0.35 밑에 머물지는
    않음(최대 연속 저하 구간 1.5s)."""
    import random
    random.seed(42)
    seq = []
    t = 0.0
    total = 60.0
    while t < total:
        # 1.0~1.5s는 tentative/정상 대역, 0.5~1.5s는 낮은 대역(0.35 밑, 최대 1.5s)
        high_dur = random.uniform(1.0, 1.5)
        for _ in range(int(high_dur / RADAR_TS)):
            seq.append(random.uniform(0.2, 0.6))
        low_dur = random.uniform(0.3, 1.5)  # GHOST_TIMEOUT(3.0s) 미만으로 제한
        for _ in range(int(low_dur / RADAR_TS)):
            seq.append(random.uniform(0.0, 0.34))
        t += high_dur + low_dur
    return seq


def scenario_real_lead_leaves():
    """실제 리드가 등록된 후 시야를 완전히 벗어나 prob가 영구적으로 0으로
    떨어지는 정상적인 상황(원래도 결국 트랙이 사라져야 정상)."""
    seq = [0.40] * 10           # 등록
    seq += [0.0] * int(10 / RADAR_TS)  # 10초간 완전 소실(리드가 시야 이탈)
    return seq


def summarize(name, seq, log_before, log_after):
    def first_false_after_latch(log):
        # tentative_cnt>=10에 도달한 시점(10프레임째, index 9) 이후 첫 False 인덱스
        for i in range(9, len(log)):
            if not log[i]:
                return i
        return None

    def true_ratio_tail(log, tail_frac=0.3):
        n = int(len(log) * tail_frac)
        tail = log[-n:] if n > 0 else log
        return sum(tail) / len(tail) if tail else 0.0

    print(f"\n=== {name} (총 {len(seq)}프레임, {len(seq)*RADAR_TS:.1f}s) ===")
    print(f"  [패치 전] register_ok 끝까지 유지? {'YES(래치 고착)' if all(log_before[9:]) else 'NO'}"
          f" | 마지막 30% 구간 True 비율: {true_ratio_tail(log_before):.2f}")
    idx = first_false_after_latch(log_after)
    if idx is None:
        print(f"  [패치 후] register_ok 끝까지 유지? YES (타임아웃 미도달)"
              f" | 마지막 30% 구간 True 비율: {true_ratio_tail(log_after):.2f}")
    else:
        print(f"  [패치 후] 래치 해제 시점: t={idx*RADAR_TS:.2f}s (프레임 {idx})"
              f" | 마지막 30% 구간 True 비율: {true_ratio_tail(log_after):.2f}")


if __name__ == "__main__":
    scenarios = {
        "1) 고스트 트랙(120s 영구소실)": scenario_ghost(),
        "2) 실제 리드 prob 노이즈성 출렁임(B안 보호 대상, 회귀 확인용)": scenario_real_flicker(),
        "3) 실제 리드가 시야를 벗어나 영구 소실(10s)": scenario_real_lead_leaves(),
    }

    all_pass = True
    for name, seq in scenarios.items():
        log_before = run(seq, ghost_timeout_enabled=False)
        log_after = run(seq, ghost_timeout_enabled=True)
        summarize(name, seq, log_before, log_after)

        if name.startswith("1)"):
            # 패치 전: 래치 고착(회귀 재현) / 패치 후: 반드시 풀려야 함(3~4초 내)
            ok_before = all(log_before[9:])
            idx = next((i for i in range(9, len(log_after)) if not log_after[i]), None)
            ok_after = idx is not None and (idx * RADAR_TS) <= (GHOST_TIMEOUT_S + 0.5)
            print(f"  판정: 패치전 래치고착 재현={ok_before}, 패치후 {GHOST_TIMEOUT_S}s 근처 해제={ok_after}")
            all_pass &= ok_before and ok_after
        elif name.startswith("2)"):
            # 회귀 없어야 함: 패치 전/후 register_ok 시퀀스가 완전히 동일해야 함
            # (진짜 리드의 짧은 출렁임은 타임아웃에 걸리지 않아야 함)
            identical = (log_before == log_after)
            true_ratio_before = sum(log_before[9:]) / len(log_before[9:])
            true_ratio_after = sum(log_after[9:]) / len(log_after[9:])
            print(f"  판정: 패치전/후 register_ok 시퀀스 완전동일(회귀없음)={identical}"
                  f" (True비율 전={true_ratio_before:.3f}, 후={true_ratio_after:.3f})")
            all_pass &= identical
        elif name.startswith("3)"):
            idx = next((i for i in range(9, len(log_after)) if not log_after[i]), None)
            ok_after = idx is not None and (idx * RADAR_TS) <= (GHOST_TIMEOUT_S + 0.5)
            ok_before = all(log_before[9:])  # 패치 전엔 10초 내내 고착(기존 버그)
            print(f"  판정: 패치전 10초 내내 고착(기존 버그 재현)={ok_before}, 패치후 정상 해제={ok_after}")
            all_pass &= ok_after

    print(f"\n{'='*60}\n전체 판정: {'PASS' if all_pass else 'FAIL'}")
