#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
long_mpc.py update()의 vision-only dRel closing-rate 계산 블록
(discontinuity 감지 -> 클램프+중앙값 필터 -> 방안E ref_rate 클램프 ->
vision_rate_for_lead0 유예판정)을 **재구현하지 않고**, 실제 파일에서
그 블록을 문자 그대로 잘라내 exec()으로 재생 클래스에 편입한 뒤,
extract_log.py로 뽑은 CSV(leadDRel/leadVLead/leadRadar/leadStatus/
leftBlinker/rightBlinker/vEgo 컬럼 필요)로 프레임 단위 재생한다.

목적: "로직단위 시뮬레이션(손으로 재구현한 스크립트)"과 "실제
long_mpc.py에 통합된 코드"가 완전히 같은 동작을 하는지 최종 대조하는
용도(63차 계속9/10의 sim_e.py류 검증 이후, 63차 계속10 (b)에서 최초
도입). 코드 블록을 손으로 옮겨 적지 않으므로, 이 스크립트 자체가
future-proof하게 재사용 가능 -- 블록 경계는 하드코딩된 줄번호가 아니라
마커 문자열(BLOCK_START_MARKER/BLOCK_END_MARKER)로 찾는다. 단, long_mpc.py
의 update() 시그니처/블록 구조 자체가 크게 바뀌면(예: 마커 문자열이
지워지거나 옮겨지면) 다시 확인 필요 -- 스크립트가 마커를 못 찾으면
AssertionError로 바로 알려준다(조용히 잘못된 범위로 진행하지 않음).

사용:
    python3 replay_vision_rate_integrated.py <csv_path> <seg_name> [<seg_name2> ...] \
        [--repo /home/claude/ryu] [--out /home/claude/work/replay_result.pkl]

CLI로 직접 실행하면 각 seg의 frac_rate 궤적을 계산해 요약(최대값/시각)
을 출력하고, 상세 프레임 데이터는 pickle로 저장한다(다른 스크립트에서
로드해 그래프/표 작성 가능).

주의: 이 스크립트가 다루는 건 vision_rate_for_lead0 산출까지다(그 값이
process_lead()에 실제로 넘어가는 최종 신호이므로 그 이후 MPC solve
자체는 검증 범위 밖 -- acados 컴파일 의존성 때문에 이 컨테이너에서는
애초에 실행 불가, 기존 세션들과 동일한 한계).
"""
import argparse
import collections
import csv
import pickle
import re
import sys

import numpy as np

DEFAULT_REPO = "/home/claude/ryu"
LONG_MPC_REL_PATH = "selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py"

# update() 블록에서 vision_rate_for_lead0 계산까지 필요한 상수들 --
# 새 상수가 추가되면 이 목록에 이름만 추가하면 됨(값은 항상 파일에서
# 직접 파싱, 수기 입력 없음).
CONST_NAMES = [
    "LEAD_ACQ_CONFIRM_TIME", "LEAD_ACQ_LOSS_GRACE_TIME",
    "VISION_CLOSING_RATE_TAU", "VISION_CLOSING_RATE_MIN_TIME",
    "VISION_CLOSING_RATE_MAX_PLAUSIBLE", "VISION_CLOSING_RATE_MEDIAN_WINDOW",
    "VISION_CLOSING_RATE_GATE_CAUTION", "VISION_CLOSING_RATE_GATE_DANGER",
    "VISION_RATE_REF_MARGIN",
    "NEW_LEAD_VLEAD_CORRECTION_SUPPRESS_S", "LANE_CHANGE_VLEAD_CORRECTION_HOLD_S",
    "DREL_DISCONTINUITY_DROP_THRESH", "DREL_DISCONTINUITY_WINDOW_N",
]
INT_CONST_NAMES = ("VISION_CLOSING_RATE_MEDIAN_WINDOW", "DREL_DISCONTINUITY_WINDOW_N")

# 블록 시작/끝 마커 -- 실제 파일 안에 이 리터럴 문자열이 정확히 있어야 함.
# 시작: def update() 선언부. 끝: process_lead() 실제 MPC 호출 직전까지만 필요.
BLOCK_START_MARKER = "  def update(self, carrot, reset_state, radarstate, v_cruise, x, v, a, j, personality=log.LongitudinalPersonality.standard,"
BLOCK_END_MARKER = "    lead_xv_0, lead_v_0 = self.process_lead("


def load_constants(long_mpc_path):
    with open(long_mpc_path, "r", encoding="utf-8") as f:
        text = f.read()
    consts = {}
    for name in CONST_NAMES:
        m = re.search(rf"^{name}\s*=\s*(-?[0-9.]+)", text, re.MULTILINE)
        assert m, f"const not found in {long_mpc_path}: {name}"
        val = float(m.group(1))
        if name in INT_CONST_NAMES:
            val = int(val)
        consts[name] = val
    return consts


def extract_update_block(long_mpc_path):
    with open(long_mpc_path, "r", encoding="utf-8") as f:
        text = f.read()
    start = text.index(BLOCK_START_MARKER)
    end = text.index(BLOCK_END_MARKER, start)
    assert end > start, "BLOCK_END_MARKER가 BLOCK_START_MARKER보다 앞에서 발견됨 - 마커 재확인 필요"
    raw_block = text[start:end]
    n_lines = raw_block.count("\n") + 1
    return raw_block, n_lines


def build_replay_class(long_mpc_path):
    """실제 long_mpc.py에서 상수 + update() 블록을 그대로 잘라와 재생용
    LongMpcReplay 클래스를 exec()으로 생성해 리턴한다(재구현 없음)."""
    consts = load_constants(long_mpc_path)
    raw_block, n_lines = extract_update_block(long_mpc_path)

    # 시그니처 첫 두 줄(def update(...), lane_change_blinker_active=False):)
    # 제거 -- carrot/x/v/a/j/personality는 이 검증 범위에서 안 씀.
    body_lines = raw_block.splitlines(keepends=True)
    # 첫 줄이 BLOCK_START_MARKER 자체(시그니처 1행), 다음 줄이 시그니처 2행
    # (기본값 파라미터 줄) -- 둘 다 제거.
    body_lines = body_lines[2:]
    body = "".join(body_lines)
    # 클래스 메서드 4-space 본문 들여쓰기(원본 스타일) -> 우리 하네스는
    # 표준 4-space 클래스/8-space 메서드본문 스타일이므로 앞에 공백 4칸 추가.
    body = "".join(("    " + line if line.strip() else line) for line in body.splitlines(keepends=True))

    harness_src = f'''
class LongMpcReplay:
    def __init__(self):
        self.dt = 0.05
        self.x0 = [0.0, 0.0, 0.0]
        self._launch_bypass_active = False
        self._lead_absent_timer = 0.0
        self._lead_present_run_timer = 0.0
        self._lead_acq_ramp_started = False
        self._lead_acq_timer = 0.0
        self._vision_dRel_prev = None
        self._vision_dRel_rate = 0.0
        self._vision_dRel_rate_window = collections.deque(maxlen={consts["VISION_CLOSING_RATE_MEDIAN_WINDOW"]})
        self._dRel_raw_history = collections.deque(maxlen={consts["DREL_DISCONTINUITY_WINDOW_N"]})
        self._lane_change_vlead_hold_timer = 0.0
        self.j_lead = 0.0
        self.status = False

    def update_rate_only(self, carrot, radarstate, personality=None, lane_change_blinker_active=False):
{body}
        return vision_rate_for_lead0
'''
    g = {"np": np, "collections": collections}
    for name in CONST_NAMES:
        g[name] = consts[name]
    exec(harness_src, g)
    return g["LongMpcReplay"], consts, n_lines


def vision_dRel_rate_frac(vision_rate, radar, acq_timer, consts):
    """frac_rate = clip((GATE_CAUTION - rate)/(GATE_CAUTION-GATE_DANGER),0,1),
    단 radar 락온 중이거나 VISION_CLOSING_RATE_MIN_TIME 미만이면 0.
    실제 long_mpc.py 977~997줄 공식 그대로(수기 값 대신 파일에서 로드된
    상수 사용)."""
    caution = consts["VISION_CLOSING_RATE_GATE_CAUTION"]
    danger = consts["VISION_CLOSING_RATE_GATE_DANGER"]
    min_time = consts["VISION_CLOSING_RATE_MIN_TIME"]
    if (not radar) and acq_timer >= min_time:
        return float(np.clip((caution - vision_rate) / (caution - danger), 0.0, 1.0))
    return 0.0


class Lead:
    __slots__ = ("status", "dRel", "vLead", "radar", "vRel", "aLeadK", "jLead")
    def __init__(self, status, dRel, vLead, radar):
        self.status, self.dRel, self.vLead, self.radar = status, dRel, vLead, radar
        self.vRel = 0.0
        self.aLeadK = 0.0
        self.jLead = 0.0


class RadarState:
    def __init__(self, leadOne):
        self.leadOne = leadOne
        self.leadTwo = Lead(False, 0.0, 0.0, False)


class CarrotMock:
    # vision_rate_for_lead0 산출까지만 필요한 범위에선 t_follow 자체가
    # 이후 재사용되지 않음(코드 확인 완료) -- 호출만 하고 반환값은 버려짐.
    def get_T_FOLLOW(self, personality, v_ego, a_ego):
        return 1.5


def _b(s):
    return str(s).strip().lower() in ("true", "1", "1.0")


def replay_seg(LongMpcReplay, consts, csv_path, seg_name):
    """CSV 한 세그를 재생, (t, dRel, vLead, radar, status, vision_dRel_rate,
    vision_rate_for_lead0, acq_timer, frac_rate) 튜플 리스트 리턴."""
    mpc = LongMpcReplay()
    carrot = CarrotMock()
    rows_out = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["seg"] != seg_name:
                continue
            t = float(row["t"])
            v_ego = float(row["vEgo"])
            lead_status = _b(row["leadStatus"])
            lead_radar = _b(row["leadRadar"]) if lead_status else False
            dRel = float(row["leadDRel"]) if row["leadDRel"] != "" else 0.0
            vLead = float(row["leadVLead"]) if row["leadVLead"] != "" else 0.0
            lb_active = _b(row.get("leftBlinker", "")) or _b(row.get("rightBlinker", ""))

            mpc.x0[1] = v_ego
            lead = Lead(lead_status, dRel, vLead, lead_radar)
            rs = RadarState(lead)
            vision_rate = mpc.update_rate_only(carrot, rs, personality=0, lane_change_blinker_active=lb_active)
            fr = vision_dRel_rate_frac(mpc._vision_dRel_rate, lead_radar, mpc._lead_acq_timer, consts)
            rows_out.append((t, dRel, vLead, lead_radar, lead_status,
                              mpc._vision_dRel_rate, vision_rate, mpc._lead_acq_timer, fr))
    return rows_out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path")
    ap.add_argument("seg_names", nargs="+")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--out", default=None, help="결과 pickle 저장 경로 (기본: csv 옆에 .replay.pkl)")
    args = ap.parse_args()

    long_mpc_path = f"{args.repo}/{LONG_MPC_REL_PATH}"
    LongMpcReplay, consts, n_lines = build_replay_class(long_mpc_path)
    print(f"[블록 추출 완료] {long_mpc_path} (마커 기준 {n_lines}줄, 문자 그대로)", file=sys.stderr)
    print(f"[상수, 파일에서 파싱] {consts}", file=sys.stderr)

    out_path = args.out or (args.csv_path + ".replay.pkl")
    results = {}
    for seg in args.seg_names:
        rows = replay_seg(LongMpcReplay, consts, args.csv_path, seg)
        if not rows:
            print(f"[경고] seg '{seg}': CSV에서 매칭되는 행이 없음", file=sys.stderr)
            continue
        max_fr = max(r[8] for r in rows)
        max_fr_t = next(r[0] for r in rows if r[8] == max_fr)
        print(f"=== {seg}: {len(rows)}행, 최대 frac_rate={max_fr:.3f} (t={max_fr_t:.3f}) ===")
        results[seg] = rows

    with open(out_path, "wb") as f:
        pickle.dump(results, f)
    print(f"결과 저장: {out_path}")


if __name__ == "__main__":
    main()
