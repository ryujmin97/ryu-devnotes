#!/usr/bin/env python3
"""
sim_route_254_release_dist20_6state.py (254차 신규, NEEDS_VALIDATION)

배경: 지선생(ChatGPT)이 252차 INERT/ACTIVE 래치 설계 위에 두 가지 변경을
지시함(devnotes ROUTE_REDESIGN_GUIDE.md/247cha 설계와의 차이):

  ① Continuity 상태를 4종(matched/held/new/none)에서 6종
     (MATCHED/HELD/PASSED/LOST/NEW/NONE)으로 분리 -- 현재 252차 코드의
     `apex_passed_or_lost = apex_mode == "new"` 가 "진짜 통과(predicted<=0)"와
     "신호 소실(miss_frames 초과)"을 구분하지 못하는 문제(사용자 지적,
     247차 설계 §10에서도 동일 지점을 다른 각도로 언급) 해결.

  ② ACTIVE release 조건을 "Apex 통과(predicted_dist<=0)"에서
     "apex_dist<=ROUTE_RELEASE_DIST_M(20.0)"로 변경. 사용자 확정 근거(원문):
     "20m 전이면 vturn이 관여한 시점일테고, apex까지 20m가 중요한게
     아니고, 그 지점까지 충분히 감속을 했느냐가 중요한 것" -- 즉 route는
     근거리 vturn(비전 기반 커브 제어)에게 20m 지점에서 넘겨주면 되고,
     그 시점까지 target_speed 부근으로 감속을 마쳤는지가 안전성의 핵심이라는
     설계 판단. 이 스크립트는 그 판단을 검증하기 위한 도구다(§10 검증우선
     원칙 -- carrot_man.py를 바로 고치지 않고 먼저 시뮬레이션).

이 스크립트는 sim_route_252_active_state_full.py의 build_candidates/
route_find_clusters/load_csv/scan_freeze를 그대로 import해 재사용하고
(§21/§27, 동일 로직 재작성 금지), Sim252를 상속하지 않고 별도
Sim254(6-state + release-mode 선택)로 새로 작성한다 -- 252차 클래스는
release 조건이 하드코딩돼 있어 상속보다 별도 클래스가 §27(최소 변경/
관련없는 리팩터링 금지) 원칙에 더 맞는다고 판단.

**한계(§28 명시, sim_route_252와 동일)**:
1~4번 전부 동일(naviPaths 재구성 근사, safe_time/decel_rate 고정가정,
open-loop 재생, 실차검증 아님). 추가로:
5. **이번 세션은 실측 dashcam CSV가 컨테이너에 없다**(253차가 쓰던
   corpus는 컨테이너 초기화로 유실, §23에 따라 devnotes git에도 원본
   CSV는 커밋되지 않음). 따라서 이 스크립트의 자체 검증은 아래
   synthetic 케이스(--self-test)로 "6-state 전이 로직 자체의 정확성"과
   "release 조건 두 가지가 설계 의도대로 동작하는가"만 확인한 것이고,
   **실측 로그 A/B는 아직 미실시** -- 158/159차 원칙(synthetic 단독으로
   결론 내리지 않음)에 따라 실측 corpus 확보 전까지 이 설계 변경을
   "검증 완료"로 보고하지 않는다.

사용:
  # synthetic 케이스로 상태 전이/release 로직만 우선 검증
  python3 sim_route_254_release_dist20_6state.py --self-test

  # 실측 CSV 확보 후 A/B (기존 apex_passed 모드 vs 신규 dist20 모드)
  python3 sim_route_254_release_dist20_6state.py route.csv --release-mode apex_passed
  python3 sim_route_254_release_dist20_6state.py route.csv --release-mode dist20
"""
import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sim_route_252_active_state_full import (
    build_candidates, load_csv, route_find_clusters, scan_freeze,
    ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M,
    ROUTE_APEX_MISS_TOLERANCE_FRAMES, ROUTE_SPEED_LOOP_DT,
)

ROUTE_RELEASE_DIST_M = 20.0  # [254차, 사용자 확정] apex_dist<=20m이면 release, vturn에 인계.


class Sim254:
    """252차 상태머신 + 6-state continuity(MATCHED/HELD/PASSED/LOST/NEW/NONE)
    + release_mode 선택("apex_passed"=기존 동작 재현 / "dist20"=신규 지시)."""

    def __init__(self, safe_time, decel_rate, release_margin, continuity_tolerance_m,
                 release_mode="dist20", release_dist_m=ROUTE_RELEASE_DIST_M):
        self.route_active = False
        self._locked_dist = None
        self._locked_speed = None
        self._miss_frames = 0
        self.safe_time = safe_time
        self.decel_rate = decel_rate
        self.release_margin = release_margin
        self.continuity_tolerance_m = continuity_tolerance_m
        self.release_mode = release_mode
        self.release_dist_m = release_dist_m
        self.route_release_t = None
        self.t = 0.0
        self.ROUTE_RELEASE_HOLD_S = 2.0

    def _continuity_step(self, clusters, distances, speeds, v_ego_ms):
        # [254차, ①] sim_route_252의 _continuity_step과 동일한 매칭/hold
        # 규칙이되, lock이 리셋되는 시점의 "원인"(predicted<=0=PASSED vs
        # miss_frames 초과=LOST vs 최초진입=NEW)을 구분해 반환한다.
        dt = ROUTE_SPEED_LOOP_DT
        had_lock = self._locked_dist is not None
        predicted = (self._locked_dist - v_ego_ms * dt) if had_lock else None

        matched = None
        if predicted is not None and predicted > 0 and clusters:
            best, best_err = None, None
            for c in clusters:
                idx = c[0]
                err = abs(distances[idx] - predicted)
                if best_err is None or err < best_err:
                    best, best_err = idx, err
            if best_err is not None and best_err <= self.continuity_tolerance_m:
                matched = best

        if matched is not None:
            self._locked_dist = distances[matched]
            self._locked_speed = speeds[matched]
            self._miss_frames = 0
            return matched, self._locked_dist, self._locked_speed, "MATCHED"

        reset_reason = None
        if had_lock:
            if predicted is not None and predicted <= 0:
                reset_reason = "PASSED"
            else:
                self._miss_frames += 1
                if (self._miss_frames < ROUTE_APEX_MISS_TOLERANCE_FRAMES
                        and predicted is not None and predicted > 0):
                    self._locked_dist = predicted
                    return -1, predicted, self._locked_speed, "HELD"
                reset_reason = "LOST"
            self._locked_dist = None
            self._locked_speed = None
            self._miss_frames = 0

        if clusters:
            idx = clusters[0][0]
            self._locked_dist = distances[idx]
            self._locked_speed = speeds[idx]
            self._miss_frames = 0
            return idx, distances[idx], speeds[idx], (reset_reason or "NEW")

        return -1, None, None, (reset_reason or "NONE")

    def _decel_step(self, v_ego_ms, apex_dist, apex_speed):
        target_ms = apex_speed / 3.6
        eff_dist = max(0.0, apex_dist - target_ms * self.safe_time)
        if eff_dist <= 0 or v_ego_ms <= target_ms:
            out_speed_ms = v_ego_ms
        else:
            required_decel_mss = (v_ego_ms ** 2 - target_ms ** 2) / (2.0 * eff_dist)
            applied_decel_mss = min(max(required_decel_mss, 0.0), self.decel_rate)
            out_speed_ms = max(target_ms, v_ego_ms - applied_decel_mss * ROUTE_SPEED_LOOP_DT)
        return out_speed_ms * 3.6

    def step(self, v_ego_ms, road_limit_speed_kph, distances, speeds, t_abs=None):
        self.t = t_abs if t_abs is not None else (self.t + ROUTE_SPEED_LOOP_DT)
        if self.route_release_t is not None:
            if (self.t - self.route_release_t) < self.ROUTE_RELEASE_HOLD_S:
                return None, -1, 0.0, 0.0, "GATE"
            self.route_release_t = None

        v_ego_kph = v_ego_ms * 3.6
        candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit_speed_kph]
        clusters = route_find_clusters(candidates, distances,
                                        ROUTE_CLUSTER_MIN_POINTS, ROUTE_CLUSTER_MAX_GAP_M)
        apex_idx, apex_dist, apex_speed, apex_mode = self._continuity_step(
            clusters, distances, speeds, v_ego_ms)

        if apex_mode == "NONE" or apex_speed is None:
            if self.route_active:
                self.route_active = False
                self.route_release_t = self.t
            return None, -1, 0.0, 0.0, apex_mode

        if self.route_active:
            # [254차, ②] release 판정 -- 두 모드 공통으로 "이전 apex의
            # continuity 추적을 잃었다"(PASSED/LOST/NEW, §5 원 설계의
            # apex_passed_or_lost와 동치)면 무조건 release. 여기에 더해
            # release_mode="dist20"이면, 추적을 잃지 않았어도(MATCHED/HELD)
            # apex_dist<=20m이면 추가로 release(vturn 인계, 사용자 확정
            # 근거 -- 20m 지점까지 감속 완료 여부가 중요, apex 자체 도달
            # 여부가 아님).
            # [254차] tracking_lost(PASSED/LOST/NEW)이면 이번 프레임의
            # apex_speed/apex_dist가 None이거나(추적 대상 완전소실) 아예
            # 다른 apex의 값(재탐색 성공)일 수 있으므로, 그 값들로
            # speed_reached/dist_reached를 계산하지 않고 무조건 즉시
            # release한다(원 설계 `apex_passed_or_lost or speed_reached`와
            # 동일한 단락평가 의도, apex_speed=None으로 인한 TypeError
            # 방지 -- self-test 케이스3에서 실제로 이 경로가 발견됨).
            tracking_lost = apex_mode in ("PASSED", "LOST", "NEW")
            if tracking_lost:
                self.route_active = False
                self.route_release_t = self.t
                out_speed = None
                release_reason = "tracking_lost:" + apex_mode
            else:
                speed_reached = v_ego_kph <= apex_speed * self.release_margin
                dist_reached = (self.release_mode == "dist20"
                                and apex_dist is not None
                                and apex_dist <= self.release_dist_m)
                if speed_reached or dist_reached:
                    self.route_active = False
                    self.route_release_t = self.t
                    out_speed = None
                    release_reason = "speed_reached" if speed_reached else "dist20"
                else:
                    out_speed = self._decel_step(v_ego_ms, apex_dist, apex_speed)
                    release_reason = ""
            return out_speed, apex_idx, apex_dist, apex_speed, (apex_mode + ("|" + release_reason if release_reason else ""))

        target_ms = apex_speed / 3.6
        eff_dist = max(0.0, apex_dist - target_ms * self.safe_time)
        if eff_dist <= 0:
            out_speed = v_ego_kph
        elif v_ego_ms > target_ms:
            self.route_active = True
            out_speed = self._decel_step(v_ego_ms, apex_dist, apex_speed)
        else:
            out_speed = apex_speed
        return out_speed, apex_idx, apex_dist, apex_speed, apex_mode

    def on_missing_navi_data(self, t_abs):
        self.t = t_abs
        if self.route_active:
            self.route_active = False
        self._locked_dist = None
        self._locked_speed = None
        self._miss_frames = 0


def replay(rows, safe_time, decel_rate, release_margin, continuity_tolerance_m, release_mode):
    sim = Sim254(safe_time, decel_rate, release_margin, continuity_tolerance_m, release_mode)
    out = []
    for row in rows:
        try:
            v_ego_ms = float(row["vEgo"])
            road_limit = float(row.get("nRoadLimitSpeed") or 50.0)
        except (TypeError, ValueError):
            out.append(dict(row, sim_out_speed="", sim_src="", sim_mode=""))
            continue
        dists, speeds = build_candidates(row.get("naviPaths", ""), road_limit)
        if not dists:
            sim.on_missing_navi_data(float(row["t"]))
            out.append(dict(row, sim_out_speed="", sim_src="", sim_mode=""))
            continue
        out_speed, apex_idx, apex_dist, apex_speed, mode = sim.step(
            v_ego_ms, road_limit, dists, speeds, t_abs=float(row["t"]))
        newrow = dict(row)
        newrow["sim_out_speed"] = "" if out_speed is None else f"{out_speed:.2f}"
        newrow["sim_src"] = "route" if out_speed is not None else ""
        newrow["sim_apex_dist"] = f"{apex_dist:.1f}" if apex_idx != -1 or out_speed is not None else ""
        newrow["sim_mode"] = mode
        out.append(newrow)
    return out


# ---------------------------------------------------------------------------
# self-test: 실측 CSV 없이도 6-state 전이 로직과 release 두 모드의 차이를
# 합성 궤적으로 검증한다(§28 -- 이것만으로 "실측 검증 완료"라고 주장하지
# 않음, docstring 한계 5번 참고).
# ---------------------------------------------------------------------------

def _make_synthetic_approach(apex_speed_kph=40.0, apex_true_dist_m=300.0,
                              v0_kph=100.0, dt=ROUTE_SPEED_LOOP_DT, decel=0.70,
                              safe_time=2.2, drop_frames=None, disappear_after_m=None):
    """v0에서 등감속(decel)으로 접근하는 1개 apex 합성 궤적을 생성.
    drop_frames: 이 프레임 인덱스 집합에서는 clusters를 빈 리스트로(순간 미스,
    HELD 유발용). disappear_after_m: apex까지 남은 거리가 이 값 이하가 되면
    그 이후 프레임은 candidate 자체가 아예 없는 것으로 처리(LOST 유발용,
    predicted>0인데 계속 미매칭 -> miss_frames 초과)."""
    v = v0_kph / 3.6
    remaining = apex_true_dist_m
    frames = []
    i = 0
    while remaining > -50.0 and i < 4000:
        # [254차] ROUTE_CLUSTER_MIN_POINTS=2 요구 -- 실측 naviPaths처럼 apex
        # 지점 부근에 최소 2개 점(gap<=ROUTE_CLUSTER_MAX_GAP_M)이 있어야
        # 클러스터가 성립한다. 단일점만 주면 항상 클러스터가 필터링돼
        # apex_mode가 "NONE"으로만 나오는 버그를 self-test 작성 중 발견함
        # (§28 -- self-test 자체도 검증 대상).
        speeds = [apex_speed_kph, apex_speed_kph]
        distances = [remaining, remaining + 5.0]
        if drop_frames and i in drop_frames:
            speeds, distances = [], []
        if disappear_after_m is not None and remaining <= disappear_after_m:
            speeds, distances = [], []
        frames.append((v, distances, speeds))
        # 등속에 가깝게(감속식 자체는 Sim254 내부가 계산하므로 여기서는 단순
        # 접근 궤적만 필요 -- 실측 vEgo 대입과 동일한 역할).
        v = max(apex_speed_kph / 3.6 * 0.98, v - decel * dt)
        remaining -= v * dt
        i += 1
    return frames


def _run_synthetic(frames, release_mode, road_limit_kph=80.0):
    sim = Sim254(safe_time=2.2, decel_rate=0.70, release_margin=1.10,
                 continuity_tolerance_m=10.0, release_mode=release_mode)
    log = []
    t = 0.0
    for v_ego_ms, distances, speeds in frames:
        out_speed, apex_idx, apex_dist, apex_speed, mode = sim.step(
            v_ego_ms, road_limit_kph, distances, speeds, t_abs=t)
        log.append((t, v_ego_ms * 3.6, out_speed, apex_dist, mode, sim.route_active))
        t += ROUTE_SPEED_LOOP_DT
    return log


def self_test():
    ok = True

    # 케이스 1: 노이즈 없는 정상 접근 -- ENGAGE 후 계속 MATCHED, 두 release
    # 모드 각각 기대한 조건에서 release 되는지 확인.
    for mode in ("apex_passed", "dist20"):
        frames = _make_synthetic_approach()
        log = _run_synthetic(frames, mode)
        active_frames = [r for r in log if r[5]]
        assert active_frames, f"[{mode}] ACTIVE 진입 자체가 없음"
        release_idx = next((i for i, r in enumerate(log) if not r[5] and i > 0 and log[i - 1][5]), None)
        assert release_idx is not None, f"[{mode}] release 전이를 못 찾음"
        # release_idx 프레임 자체가 release 판정이 내려진 프레임(이 프레임의
        # apex_dist/속도가 판정 기준값). apex_dist가 None(추적 완전소실)이면
        # 직전 활성 프레임 값으로 대체(마지막으로 유효했던 apex_dist).
        rel_apex_dist = log[release_idx][3] if log[release_idx][3] is not None else log[release_idx - 1][3]
        rel_speed_kph = log[release_idx][1]
        rel_apex_speed_kph = 40.0
        if mode == "dist20":
            cond = (rel_apex_dist is not None and rel_apex_dist <= 20.0 + 1e-6) or \
                   (rel_speed_kph <= rel_apex_speed_kph * 1.10 + 1e-6)
            assert cond, f"[dist20] release 시점이 20m/110% 조건을 만족 안 함: dist={rel_apex_dist}, v={rel_speed_kph}"
        else:
            # apex_passed 모드는 predicted<=0(=apex_dist가 0 근방 이하) 근처거나
            # 110% 속도 조건에서 release되어야 한다(20m에서 조기 release되면 안 됨).
            cond = (rel_apex_dist is not None and rel_apex_dist <= 1.0) or \
                   (rel_speed_kph <= rel_apex_speed_kph * 1.10 + 1e-6)
            assert cond, f"[apex_passed] release가 20m 근방에서 조기발생(회귀): dist={rel_apex_dist}, v={rel_speed_kph}"
        print(f"[OK] 케이스1 mode={mode}: release at apex_dist={rel_apex_dist}, v={rel_speed_kph:.1f}kph")

    # 케이스 2: 짧은 candidate 소실(HELD 경로) -- ROUTE_APEX_MISS_TOLERANCE_FRAMES
    # (3) 미만이면 HELD로 흡수되고 lock 유지, ACTIVE가 끊기지 않아야 한다.
    frames = _make_synthetic_approach(drop_frames=set(range(50, 52)))  # 2프레임만 소실
    log = _run_synthetic(frames, "dist20")
    modes_in_window = [r[4] for r in log if 48 <= (r[0] / ROUTE_SPEED_LOOP_DT) <= 54]
    assert any(m.startswith("HELD") for m in modes_in_window), f"HELD 전이가 없음: {modes_in_window}"
    assert all(r[5] for r in log if 40 <= (r[0] / ROUTE_SPEED_LOOP_DT) <= 60), \
        "2프레임 순간미스로 ACTIVE가 끊김(HELD가 흡수 못함)"
    print("[OK] 케이스2: 2프레임 순간미스 -> HELD로 흡수, ACTIVE 유지")

    # 케이스 3: candidate가 예측 위치보다 훨씬 전에 완전히 사라짐(LOST 경로) --
    # miss_frames가 3프레임 이상 지속되면 LOST로 전이하고 release되어야 한다.
    frames = _make_synthetic_approach(disappear_after_m=150.0)
    log = _run_synthetic(frames, "dist20")
    lost_frames = [r for r in log if r[4].startswith("LOST")]
    assert lost_frames, f"LOST 전이가 한 번도 발생하지 않음(150m 지점 이후 후보가 계속 없어야 함): {[r[4] for r in log[:400]]}"
    print(f"[OK] 케이스3: LOST 전이 발생 at t={lost_frames[0][0]:.2f}s")

    # 케이스 4: PASSED -- disappear 없이 끝까지 진행하면 predicted<=0 시점에서
    # PASSED로 전이해야 한다(apex_passed 모드에서 이게 곧 release 트리거).
    frames = _make_synthetic_approach()
    log = _run_synthetic(frames, "apex_passed")
    passed_frames = [r for r in log if r[4].startswith("PASSED")]
    assert passed_frames, f"PASSED 전이가 없음: {[r[4] for r in log if r[5]][-5:]}"
    print(f"[OK] 케이스4: PASSED 전이 발생 at t={passed_frames[0][0]:.2f}s")

    print("\n전체 self-test 통과(synthetic 한정 -- §28: 실측 로그 A/B는 별도 필요, 위 docstring 한계 5번 참고).")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", nargs="?")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--release-mode", choices=["apex_passed", "dist20"], default="dist20")
    ap.add_argument("--safe-time", type=float, default=2.2)
    ap.add_argument("--decel-rate", type=float, default=0.70)
    ap.add_argument("--release-margin", type=float, default=1.1)
    ap.add_argument("--continuity-tolerance", type=float, default=10.0)
    ap.add_argument("--far-dist-m", type=float, default=150.0)
    ap.add_argument("--cruise-gap-kph", type=float, default=15.0)
    ap.add_argument("--ceiling-track-kph", type=float, default=2.0)
    ap.add_argument("--min-duration-s", type=float, default=2.0)
    args = ap.parse_args()

    if args.self_test or not args.csv_path:
        self_test()
        return

    rows = load_csv(args.csv_path)
    print(f"loaded {len(rows)} rows from {args.csv_path} (release_mode={args.release_mode})")

    sim_rows = replay(rows, args.safe_time, args.decel_rate, args.release_margin,
                       args.continuity_tolerance, args.release_mode)

    real_ep = scan_freeze(rows, "src", "routeOutSpeed", args.far_dist_m, args.cruise_gap_kph,
                           args.ceiling_track_kph, args.min_duration_s, apex_dist_key="routeApexDist")
    sim_ep = scan_freeze(sim_rows, "sim_src", "sim_out_speed", args.far_dist_m, args.cruise_gap_kph,
                          args.ceiling_track_kph, args.min_duration_s, apex_dist_key="sim_apex_dist")

    mode_counts = {}
    for r in sim_rows:
        m = r.get("sim_mode", "")
        base = m.split("|")[0] if m else ""
        if base:
            mode_counts[base] = mode_counts.get(base, 0) + 1

    print(f"\n=== 실측(CSV routeOutSpeed/src 기준) far-apex-freeze episodes: {len(real_ep)} ===")
    for e in real_ep:
        print(f"  t={e['start']:.1f}-{e['end']:.1f} (dur={e['end']-e['start']:.2f}s)")

    print(f"\n=== 시뮬레이션(254차, release_mode={args.release_mode}) far-apex-freeze episodes: {len(sim_ep)} ===")
    for e in sim_ep:
        print(f"  t={e['start']:.1f}-{e['end']:.1f} (dur={e['end']-e['start']:.2f}s)")

    print(f"\n6-state continuity 분포: {mode_counts}")
    print(f"\n요약: 실측 {len(real_ep)}건 -> 시뮬레이션(254차, {args.release_mode}) {len(sim_ep)}건")
    print("주의: open-loop 재생(§28) -- 실측 궤적 대입 결과이지 피드백 루프 재현 아님.")


if __name__ == "__main__":
    main()
