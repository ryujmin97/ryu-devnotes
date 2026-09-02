#!/usr/bin/env python3
"""
214차 -- 213차가 특정한 "연속커브 저속유지" 근본원인(carrot_man.py L994,
sharpest_candidate_speed가 candidate의 거리를 무시하고 speed(raw target)만
반영)에 대한 두 수정안(A: 명시적 required_decel_dist 판정식 / B: 기존
calculate_current_speed() 재사용) 중, 사용자가 채택한 B안을 프로덕션 코드
수정 전에 시나리오 기반으로 검증한다.

전제 검증(코드 확인 완료, 이 스크립트 밖에서 수행):
carrot_man.py L748 "distance = -10.0"(213차 A안) 이후에도 distances[]와
speeds[]는 동일 루프에서 동일 인덱스로 append되므로(L753-762),
distances[k]는 항상 candidate k의 실제 거리와 정확히 대응한다. fine 보정
루프(L772-796)는 speeds[j]/curvatures[j]만 조건부로 덮어쓰고 distances[]는
건드리지 않는다. 따라서 distances[k]를 그대로 calculate_current_speed()에
넘기는 B안은 213차 거리축 수정과 어긋나지 않는다.

OLD = 현재 프로덕션 코드(207차, carrot_man.py L994-996):
    sharpest_candidate_speed = min(speeds[k] for k in candidates, default=apex_speed)
    ceiling = max(vEgo_kph, sharpest_candidate_speed)

NEW(B) = 이번에 검증하는 안:
    sharpest_candidate_speed_B = min(
        calculate_current_speed(distances[k], speeds[k], safe_time, safe_decel_rate)
        for k in candidates
    , default=apex_speed)
    ceiling = max(vEgo_kph, sharpest_candidate_speed_B)

out_speed = min(raw, ceiling, ROUTE_MAX_SPEED_KPH)  (raw/apex_dist/apex_speed는
B안과 무관하게 기존 그대로 -- candidates[0] 기준 계산, 전혀 변경 없음)

이 스크립트는 사용자가 요청한 4개 시나리오 세트 + 205~207차가 검증했던
기존 대조군(diff-0 확인용)을 함께 돌린다. PASS/FAIL 판정 기준은 각 시나리오
설명에 있는 정성적 조건(스파이크 재발 여부, 조기고정 여부, 단조수렴 여부,
원복 가능 여부)을 코드로 assert 가능한 형태로 옮긴 것이며, 최종 판단은
사용자(+ChatGPT)가 출력된 실제 수치를 보고 함께 내린다는 전제로 작성한다.

실차 검증: 미실시. 이 스크립트는 순수 함수 레벨 시나리오 검증만 수행한다.
"""
import math

AUTO_NAVI_SPEED_DECEL_RATE = 0.70  # 83차 실측
AUTO_NAVI_SPEED_CTRL_END = 7.0     # params_keys.h 기본값(AutoNaviSpeedCtrlEnd)
ROUTE_MAX_SPEED_KPH = 150.0        # 211차, 300->150


def calculate_current_speed(left_dist, safe_speed_kph, safe_time, safe_decel_rate):
    """carrot_serv.py::calculate_current_speed 그대로 재현(213차 이후 미변경)."""
    safe_speed = safe_speed_kph / 3.6
    safe_dist = safe_speed * safe_time
    decel_dist = left_dist - safe_dist
    if decel_dist <= 0:
        return safe_speed_kph
    temp = safe_speed ** 2 + 2 * safe_decel_rate * decel_dist
    speed_mps = math.sqrt(temp) if temp >= 0 else safe_speed
    return max(safe_speed_kph, min(250, speed_mps * 3.6))


def sharpest_old_207(apex_speed, candidates):
    """현재 프로덕션(207차): candidate의 raw target speed 자체의 min. 거리 무시."""
    if not candidates:
        return apex_speed
    return min(spd for (dist, spd) in candidates)


def sharpest_new_B(apex_speed, candidates, safe_time, safe_decel_rate):
    """214차 B안: candidate마다 calculate_current_speed()를 그대로 재사용한 min."""
    if not candidates:
        return apex_speed
    return min(
        calculate_current_speed(dist, spd, safe_time, safe_decel_rate)
        for (dist, spd) in candidates
    )


def compute(apex_dist, apex_speed, candidates, v_ego_kph,
            safe_time=AUTO_NAVI_SPEED_CTRL_END, safe_decel_rate=AUTO_NAVI_SPEED_DECEL_RATE):
    """candidates: list of (dist, speed) tuples, candidates[0]는 apex(=가장 가까운 후보)와
    동일 지점이어야 정합(현재 프로덕션 구조와 동일하게 candidates[0]가 apex_idx)."""
    raw = calculate_current_speed(apex_dist, apex_speed, safe_time, safe_decel_rate)

    old_sharpest = sharpest_old_207(apex_speed, candidates)
    old_ceiling = max(v_ego_kph, old_sharpest)
    old_out = min(raw, old_ceiling, ROUTE_MAX_SPEED_KPH)

    new_sharpest = sharpest_new_B(apex_speed, candidates, safe_time, safe_decel_rate)
    new_ceiling = max(v_ego_kph, new_sharpest)
    new_out = min(raw, new_ceiling, ROUTE_MAX_SPEED_KPH)

    return {
        "raw": raw,
        "old_sharpest": old_sharpest, "old_ceiling": old_ceiling, "old_out": old_out,
        "new_sharpest": new_sharpest, "new_ceiling": new_ceiling, "new_out": new_out,
    }


def fmt(r):
    return (f"raw={r['raw']:.2f}  "
            f"OLD(207차) sharpest={r['old_sharpest']:.2f} ceiling={r['old_ceiling']:.2f} out={r['old_out']:.2f}  |  "
            f"NEW(B안) sharpest={r['new_sharpest']:.2f} ceiling={r['new_ceiling']:.2f} out={r['new_out']:.2f}")


def main():
    results = []

    # ------------------------------------------------------------------
    # 시나리오 1 -- 207차 회귀 방어
    # apex(=candidates[0])=70m/297.5kph(road_limit 바로 아래 trivial 근접 후보),
    # 같은 윈도우에 sharpest 실제 후보 230m/50kph(북대전IC류 실제 급커브)
    # 공존. vEgo=55.
    # PASS 조건: NEW가 206차가 겪었던 "298 근처 고원"(=거의 무제한 통과)을
    # 재현하지 않아야 한다. B안은 거리(230m)로 감쇠된 raw를 쓰므로 완전한
    # 50 고정은 아니지만, road_limit급 스파이크(150 또는 298)와는 확실히
    # 구분되는 수준(수 배 이상 낮음)이어야 한다.
    # ------------------------------------------------------------------
    print("=" * 78)
    print("시나리오 1: 207차 회귀 방어 (apex=70m/297.5kph trivial, sharpest candidate=230m/50kph, vEgo=55)")
    r1 = compute(apex_dist=70.0, apex_speed=297.5,
                 candidates=[(70.0, 297.5), (230.0, 50.0)], v_ego_kph=55.0)
    print("  " + fmt(r1))
    spike_avoided = r1["new_out"] < 100.0  # 150/298 스파이크와는 확실히 구분되는 임계선
    old_correct = abs(r1["old_out"] - 55.0) < 0.5  # 기존 207차 동작 재확인(diff 기준선)
    ok1 = spike_avoided and old_correct
    print(f"  [{'PASS' if ok1 else 'FAIL'}] NEW out={r1['new_out']:.2f} < 100(스파이크 아님) "
          f"and OLD out={r1['old_out']:.2f}~=55(207차 기존 동작 재확인)")
    print(f"  참고: NEW out({r1['new_out']:.2f})이 OLD out(55.00)보다 다소 높은 이유는, B안이 "
          f"230m 거리를 반영해 '아직 완전히 감속할 필요는 없는' 값을 계산하기 때문 -- "
          f"거리를 무시하고 target speed(50)를 그대로 쓰는 OLD보다 물리적으로 더 정확한 값.")
    results.append(("1. 207차 회귀 방어", ok1))

    # ------------------------------------------------------------------
    # 시나리오 2 -- 멀리 있는 2차 커브
    # 실질적으로 유효 후보가 하나뿐이고(=apex==sharpest candidate) 그것이
    # 300m 앞의 40kph 커브. vEgo=70(설정속도권, 비구속 주행 중 가정).
    # PASS 조건: route가 40으로 미리 떨어지지 않고(=out이 40 근처로 눌리지
    # 않고) 사실상 vEgo/설정속도 부근(비구속)을 유지해야 한다.
    # ------------------------------------------------------------------
    print("=" * 78)
    print("시나리오 2: 멀리 있는 2차 커브 (candidate=300m/40kph 단독, vEgo=70)")
    r2 = compute(apex_dist=300.0, apex_speed=40.0,
                 candidates=[(300.0, 40.0)], v_ego_kph=70.0)
    print("  " + fmt(r2))
    not_pinned_old = r2["old_out"] > 60.0
    not_pinned_new = r2["new_out"] > 60.0
    ok2 = not_pinned_old and not_pinned_new
    print(f"  [{'PASS' if ok2 else 'FAIL'}] OLD out={r2['old_out']:.2f}, NEW out={r2['new_out']:.2f} "
          f"둘 다 > 60(=40으로 조기고정 안 됨, 사실상 비구속 유지)")
    results.append(("2. 멀리 있는 2차 커브(조기고정 없음)", ok2))

    # ------------------------------------------------------------------
    # 시나리오 3 -- 필요 감속거리 진입(단조수렴 sweep)
    # candidate=40kph 고정, apex_dist(=거리)만 300 -> 0으로 스윕.
    # PASS 조건: NEW(B) out이 거리 감소에 따라 "올라갔다 내려가는" 진동 없이
    # 단조 비증가로 40에 수렴해야 한다.
    # ------------------------------------------------------------------
    print("=" * 78)
    print("시나리오 3: 필요 감속거리 진입 (candidate speed=40 고정, 거리 300m -> 0m 스윕, vEgo=40 고정)")
    sweep_dists = [300, 250, 200, 150, 100, 77.8, 50, 20, 0]
    prev_new_out = None
    monotonic_ok = True
    converged_ok = False
    for d in sweep_dists:
        r = compute(apex_dist=d, apex_speed=40.0, candidates=[(d, 40.0)], v_ego_kph=40.0)
        note = ""
        if prev_new_out is not None and r["new_out"] > prev_new_out + 1e-6:
            monotonic_ok = False
            note = "  <== 상승(진동 의심)"
        print(f"  dist={d:6.1f}m  " + fmt(r) + note)
        prev_new_out = r["new_out"]
        if d <= 20 and abs(r["new_out"] - 40.0) < 0.5:
            converged_ok = True
    ok3 = monotonic_ok and converged_ok
    print(f"  [{'PASS' if ok3 else 'FAIL'}] 단조비증가(진동 없음)={monotonic_ok}, "
          f"근접시 40으로 수렴={converged_ok}")
    results.append(("3. 필요감속거리 진입(단조수렴)", ok3))

    # ------------------------------------------------------------------
    # 시나리오 3b -- 1차 통과 후 원복 가능 여부(213차가 지적한 핵심 버그 재현)
    # 1차 커브를 이미 통과해 vEgo가 낮아진 상태(예 30)에서, 남은 후보가
    # 2차(300m/40kph)뿐인 상황. OLD는 거리 무시하고 target(40)을 그대로
    # ceiling에 써서 vEgo(30)보다 높지만 40에 즉시 눌린다(=213차가 지적한
    # "1차->2차 사이 저속유지" 그 자체). NEW(B)는 거리로 감쇠된 값을 써서
    # 40보다 훨씬 높은 원복을 허용해야 한다.
    # ------------------------------------------------------------------
    print("=" * 78)
    print("시나리오 3b: 1차 통과 후 원복 가능 여부 (vEgo=30, 남은 후보=2차 300m/40kph뿐)")
    r3b = compute(apex_dist=300.0, apex_speed=40.0,
                  candidates=[(300.0, 40.0)], v_ego_kph=30.0)
    print("  " + fmt(r3b))
    old_bug_reproduced = r3b["old_out"] < 45.0  # 213차가 지적한 버그: 40 근처에 조기고정
    new_bug_fixed = r3b["new_out"] > 60.0        # B안: 원복 허용(설정속도 방향)
    ok3b = old_bug_reproduced and new_bug_fixed
    print(f"  [{'PASS' if ok3b else 'FAIL'}] OLD out={r3b['old_out']:.2f} < 45(213차 버그 재현), "
          f"NEW out={r3b['new_out']:.2f} > 60(원복 허용, 버그 해소)")
    results.append(("3b. 1차 통과 후 원복(213차 버그 재현/해소 확인)", ok3b))

    # ------------------------------------------------------------------
    # 시나리오 4 -- 연속 S자 전체 타임라인 (1차 30 통과 -> 원복/가속 -> 2차 40 진입)
    # 절대위치가 아닌 "2차 커브까지 남은 거리"를 프레임 진행에 따라 감소시키는
    # 형태로 근사(1차는 이미 통과했다고 가정, apex_idx가 2차로 전환된 이후
    # 구간만 시뮬레이션 -- apex_idx 전환 자체는 179/196차 로직으로 이 B안과
    # 무관하므로 대상에서 제외). vEgo는 매 프레임 out_speed에 근접하도록
    # 단순 근사(실제 accel_limit 램프리미터는 132차 로직, 이 스크립트 범위 밖).
    # PASS 조건: 2차가 멀 때는 40으로 눌리지 않고(=가속 허용), 가까워지면서
    # 40으로 서서히(스파이크/진동 없이) 수렴해야 한다.
    # ------------------------------------------------------------------
    print("=" * 78)
    print("시나리오 4: 연속 S자 전체 타임라인 (1차 통과 후 vEgo=30에서 2차 300m/40kph까지 접근)")
    v_ego = 30.0
    prev_out = None
    osc = False
    for d in [300, 260, 220, 180, 140, 100, 77.8, 60, 30, 0]:
        r = compute(apex_dist=d, apex_speed=40.0, candidates=[(d, 40.0)], v_ego_kph=v_ego)
        flag = ""
        if prev_out is not None and r["new_out"] > prev_out + 1e-6 and d < 250:
            # 250m 이내(=이미 감속영역 진입 이후)에서 상승은 진동으로 간주.
            # 300->260 구간은 vEgo가 아직 out을 못 따라잡아 raw/ceiling이
            # 같이 완화되는 초기 구간이라 예외로 둔다.
            osc = True
            flag = "  <== 진동 의심"
        print(f"  2차까지 {d:6.1f}m  vEgo={v_ego:5.1f}  " + fmt(r) + flag)
        # vEgo가 out_speed를 향해 점진적으로 따라간다고 근사(실제 accel_limit 램프와는
        # 다르지만, 이 스크립트는 ceiling 값 자체의 형태 검증이 목적).
        v_ego = v_ego + min(5.0, max(-5.0, r["new_out"] - v_ego) * 0.5)
        prev_out = r["new_out"]
    ok4 = not osc
    print(f"  [{'PASS' if ok4 else 'FAIL'}] 진동(비단조 상승) 없음={not osc}")
    results.append(("4. 연속 S자 전체 타임라인(진동 없음)", ok4))

    # ------------------------------------------------------------------
    # 대조군 -- 205~207차가 이미 검증한 기존 시나리오를 B안으로도 재확인
    # (diff-0 요구는 아니지만, 최소한 회귀가 없어야 함).
    # ------------------------------------------------------------------
    print("=" * 78)
    print("대조군: 기존 205~207차 검증 시나리오 재확인 (B안 적용 후 회귀 없는지)")

    print("  대조군-1) 정상 직선 복귀(원거리 급커브 없음)")
    rc1 = compute(apex_dist=50.0, apex_speed=90.0, candidates=[(50.0, 90.0)], v_ego_kph=40.0)
    print("    " + fmt(rc1))
    okc1 = abs(rc1["old_out"] - rc1["new_out"]) < 0.5
    print(f"    [{'PASS' if okc1 else 'FAIL'}] OLD/NEW 거의 동일(diff<0.5) -- 단일후보라 B안 영향 미미해야 함")
    results.append(("대조군-1. 정상 직선 복귀", okc1))

    print("  대조군-2) 연속 S자(2차가 더 급함, vEgo가 이미 ceiling 지배)")
    rc2 = compute(apex_dist=30.0, apex_speed=45.0, candidates=[(30.0, 45.0), (80.0, 30.0)], v_ego_kph=50.0)
    print("    " + fmt(rc2))
    okc2 = rc2["old_out"] <= 50.5 and rc2["new_out"] <= 50.5
    print(f"    [{'PASS' if okc2 else 'FAIL'}] OLD/NEW 둘 다 vEgo(50) 이하로 정상 감속 유지")
    results.append(("대조군-2. 연속 S자(vEgo 지배 구간)", okc2))

    print("  대조군-3) candidates=[] 완전 직선 폴백")
    rc3 = compute(apex_dist=300.0, apex_speed=300.0, candidates=[], v_ego_kph=40.0)
    print("    " + fmt(rc3))
    okc3 = abs(rc3["old_out"] - rc3["new_out"]) < 0.5
    print(f"    [{'PASS' if okc3 else 'FAIL'}] OLD/NEW 완전 동일해야 함(폴백 경로는 B안과 무관)")
    results.append(("대조군-3. candidates=[] 폴백", okc3))

    # ------------------------------------------------------------------
    print("=" * 78)
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
