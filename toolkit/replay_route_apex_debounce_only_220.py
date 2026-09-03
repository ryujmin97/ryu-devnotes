#!/usr/bin/env python3
"""
220차 -- "(A) apex_idx debounce만으로 199차 게이트(OLD, 직전 프레임 비교)가
충분한가"를 합성 모델이 아니라 실제 route.csv의 raw routeApexIdx/Dist/Speed
시퀀스로 직접 재생해 검증한다. rolling-max 게이트(B)는 이 스크립트에서
의도적으로 제외한다 -- (A) 단독 효과만 분리해서 보기 위함.

추가로, 같은 구간의 vEgo/aEgo/brakePressed를 함께 뽑아 "게이트가 armed 되지
않은 구간이 실제로 급제동/운전자개입이 필요했던 구간이었는지"를 대조한다.
219차는 게이트 작동 여부(armed count)만 확인했을 뿐 실제 주행 결과와는
대조하지 않았다 -- 이 스크립트는 그 공백을 메운다.

사용법:
    python3 replay_route_apex_debounce_only_220.py <route.csv> --t-start 990 --t-end 1046

route.csv는 extract_log.py로 뽑은 CSV(naviPaths 컬럼 불필요, routeApexIdx/
routeApexDist/routeApexSpeed/vEgo/aEgo/brakePressed/liveRouteSpeed 컬럼만
있으면 됨 -- --with-navi-paths 없이 뽑은 기본 CSV로도 동작).

carrot_man.py의 (A) debounce 로직(ROUTE_APEX_IDX_RELEASE_CONFIRM_FRAMES
프레임 확인, apex_dist 기준 강화/완화 판정)과 199차 OLD 게이트
(ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH 직전 프레임 비교)를 각각 그대로
재현한다 -- carrot_man.py를 import하지 않는 이유는 CarrotServ 등 런타임
의존성 없이 순수 로직만 격리 검증하기 위함(다른 sim_*.py들과 동일한 관례).
"""
import argparse
import csv

ROUTE_APEX_IDX_RELEASE_CONFIRM_FRAMES = 3
ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH = 15.0

# 219차/220차가 실제로 관측한 급제동 판정 기준(경험적 -- 필요시 조정).
HARD_BRAKE_AEGO_MSS = -2.5


def debounce_only(raw_idx, raw_dist, raw_speed, confirm_frames=ROUTE_APEX_IDX_RELEASE_CONFIRM_FRAMES):
    """carrot_man.py (A) 블록과 100% 동일 로직 -- apex_dist 기준으로
    강화방향(<=)은 즉시 채택, 완화방향(>)은 confirm_frames 연속 확인 후 채택.
    rolling-max(B)는 적용하지 않는다."""
    stable_idx = stable_dist = stable_speed = None
    pending_idx, pending_count = None, 0
    out_speed, out_release = [], []
    for rawi, rawd, raws in zip(raw_idx, raw_dist, raw_speed):
        release_confirmed = False
        if stable_idx is None or rawd <= stable_dist:
            stable_idx, stable_dist, stable_speed = rawi, rawd, raws
            pending_idx, pending_count = None, 0
        else:
            if pending_idx == rawi:
                pending_count += 1
            else:
                pending_idx, pending_count = rawi, 1
            if pending_count >= confirm_frames:
                stable_idx, stable_dist, stable_speed = rawi, rawd, raws
                pending_idx, pending_count = None, 0
                release_confirmed = True
        out_speed.append(stable_speed)
        out_release.append(release_confirmed)
    return out_speed, out_release


def old_gate(speed_seq, thresh=ROUTE_APEX_SPEED_DISCONTINUITY_THRESH_KPH):
    """199차 OLD 게이트(직전 프레임 대비 비교) -- carrot_man.py 패치 전과 동일."""
    prev = None
    armed = False
    armed_speed = None
    out = []
    for s in speed_seq:
        if prev is not None:
            delta = prev - s
            if delta > thresh:
                armed = True
                armed_speed = s
            elif armed and abs(s - armed_speed) > thresh:
                armed = False
        prev = s
        out.append(armed)
    return out


def load_window(csv_path, t_start, t_end):
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if t_start <= float(r["t"]) <= t_end]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--t-start", type=float, required=True)
    ap.add_argument("--t-end", type=float, required=True)
    ap.add_argument("--confirm-frames", type=int, default=ROUTE_APEX_IDX_RELEASE_CONFIRM_FRAMES)
    args = ap.parse_args()

    rows = load_window(args.csv_path, args.t_start, args.t_end)
    if not rows:
        print("해당 구간에 행이 없습니다.")
        return

    ts = [float(r["t"]) for r in rows]
    raw_idx = [int(r["routeApexIdx"]) for r in rows]
    raw_dist = [float(r["routeApexDist"]) for r in rows]
    raw_speed = [float(r["routeApexSpeed"]) for r in rows]
    vEgo_kph = [float(r["vEgo"]) * 3.6 for r in rows]
    aEgo = [float(r["aEgo"]) for r in rows]
    brake = [r.get("brakePressed", "False") == "True" for r in rows]

    debounced_speed, release_seq = debounce_only(raw_idx, raw_dist, raw_speed, args.confirm_frames)
    armed_raw = old_gate(raw_speed)
    armed_debounced = old_gate(debounced_speed)

    print(f"구간: t={args.t_start}~{args.t_end} ({len(rows)} rows), confirm_frames={args.confirm_frames}")
    print(f"  OLD 게이트(raw, 199차 그대로) armed 프레임 수 = {sum(armed_raw)}")
    print(f"  OLD 게이트(debounce-only 적용 후) armed 프레임 수 = {sum(armed_debounced)}")
    print(f"  raw apex_speed 프레임간 최대낙차 = {max((raw_speed[i-1]-raw_speed[i]) for i in range(1,len(raw_speed))):.2f}kph")
    print(f"  debounced apex_speed 프레임간 최대낙차 = {max((debounced_speed[i-1]-debounced_speed[i]) for i in range(1,len(debounced_speed))):.2f}kph")

    n_brake = sum(brake)
    min_aego = min(aEgo)
    hard_brake_frames = sum(1 for a in aEgo if a < HARD_BRAKE_AEGO_MSS)
    print(f"  실차 결과 대조: brakePressed=True 프레임 수={n_brake}, "
          f"aEgo 최소값={min_aego:.2f}m/s^2, "
          f"aEgo<{HARD_BRAKE_AEGO_MSS}m/s^2 프레임 수={hard_brake_frames}")
    if n_brake == 0 and hard_brake_frames == 0:
        print("  -> 이 구간은 실제 급제동/운전자개입 신호가 없음. "
              "게이트 미작동(armed=0)이 실제 문제였는지 별도 확인 필요.")
    else:
        print("  -> 이 구간에서 급제동/개입 신호가 감지됨 -- 게이트 미작동이 "
              "실제 문제였을 가능성이 높은 후보 구간.")


if __name__ == "__main__":
    main()
