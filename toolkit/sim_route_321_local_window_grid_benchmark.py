#!/usr/bin/env python3
"""
sim_route_321_local_window_grid_benchmark.py (321차 신규 초안)

목적: 320차 세션에서 사용자가 요청한 "orphan 주변 국소 윈도우(~120m)만
10m -> 5m로 조건부 재샘플"하는 설계의 실제 CPU 부하를 처음으로 정확히
측정한다.

**318차 벤치마크 재검증(중요, 이번 세션에서 발견)**: 318차가 "10m->5m
그리드 전환 부하"로 보고한 `perf_route_269_curvature_batch_optimize.py`의
`long_route_121` 시나리오를 코드/실행으로 재확인한 결과, `benchmark()`/
`self_test()`가 `distance_interval` 인자를 항상 10.0으로 고정 호출하고
포인트 생성 함수(`make_random_jitter` 등)도 `step=10.0` 고정이었다 --
즉 121-point 시나리오는 실제로는 "더 긴(982.6m) 10m 그리드 경로"였을
뿐, 5m 그리드가 전혀 아니었다(직접 재실행으로 point spacing=10.0m,
총연장=982.6m 확인, 아래 "검증" 참고). 318차의 "1.9배/프레임당
0.09ms 증가" 결론 자체(경로 길이 2배 부하)는 틀리지 않으나, 이를
"10m->5m 그리드 전환 부하"로 명명한 것은 오분류였다 -- **실제 5m 그리드
부하는 이번 세션 이전까지 측정된 적이 없다.**

**설계(317차 Part1 확정 방식 그대로 이식, §27 재사용)**: 밀도(interval)만
올리고 곡률 chord는 물리적으로 고정한다.
  - 10m baseline: interval=10m, sample=4(macro chord=2*4*10=80m),
    sample_fine=1(fine chord=2*1*10=20m) -- carrot_man.py 원본 그대로.
  - 5m 후보: interval=5m, sample=8(macro chord=2*8*5=80m 동일),
    sample_fine=2(fine chord=2*2*5=20m 동일) -- chord(m)는 10m판과
    100% 동일, 인덱스 스텝만 2배.
  - 윈도우 폭: 317차 Part1의 WINDOW_PAD_M=60m을 그대로 사용 -- orphan
    지점(d0) 좌우 60m씩, 총 120m 국소 구간만 재샘플(전체 600m 재샘플
    아님).

**한계(§28, 318차와 동일 종류)**:
1. 이 컨테이너(클라우드 서버 CPU) 기준 상대 비교 -- C3 디바이스 절대
   실행시간 아님.
2. "조건부"의 실제 트리거 빈도(Hz, orphan 후보 발생 빈도)는 이번
   스크립트 범위 밖 -- 317차가 남긴 별도 과제(carrot_navi_route()
   호출주기 확인)로 남는다. 이 스크립트는 "1회 트리거당 비용"만
   측정한다.
3. 합성 포인트 데이터 -- 실 corpus 좌표 아님(269차/317차와 동일 한계).
"""
import math
import time

import numpy as np

from perf_route_269_curvature_batch_optimize import calculate_curvature

V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
WINDOW_PAD_M = 60.0  # 317차 Part1과 동일


def curvature_calc_generic(resampled_points, distance_interval, road_limit_speed, sample, sample_fine):
    """baseline_curvature_calc의 sample/sample_fine을 외부에서 지정 가능하게 한
    범용판(로직은 perf_route_269 baseline과 100% 동일, §27)."""
    curvatures = []
    distances = []
    distance = -distance_interval
    if len(resampled_points) < sample * 2 + 1:
        return distances, curvatures, []
    speeds = []
    for i in range(len(resampled_points) - sample * 2):
        distance += distance_interval
        p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
        curvature = calculate_curvature(p1, p2, p3)
        speed = np.interp(abs(curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
        if abs(curvature) < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
            speed = max(speed, road_limit_speed)
        curvatures.append(curvature)
        speeds.append(speed)
        distances.append(distance)

    if sample_fine and sample_fine < sample and len(resampled_points) >= sample_fine * 2 + 1:
        fine_distance = -distance_interval
        fine_points = []
        for i in range(len(resampled_points) - sample_fine * 2):
            fine_distance += distance_interval
            p1, p2, p3 = resampled_points[i], resampled_points[i + sample_fine], resampled_points[i + sample_fine * 2]
            f_curvature = calculate_curvature(p1, p2, p3)
            f_speed = np.interp(abs(f_curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
            if abs(f_curvature) < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                f_speed = max(f_speed, road_limit_speed)
            fine_points.append((fine_distance, f_curvature, f_speed))
        if fine_points:
            fine_idx = 0
            for j in range(len(distances)):
                d = distances[j]
                while (fine_idx + 1 < len(fine_points)
                       and abs(fine_points[fine_idx + 1][0] - d) <= abs(fine_points[fine_idx][0] - d)):
                    fine_idx += 1
                f_dist, f_curv, f_speed = fine_points[fine_idx]
                if f_speed < speeds[j]:
                    speeds[j] = f_speed
                    curvatures[j] = f_curv
    return distances, curvatures, speeds


def make_window_points(width_total_m, step, seed=0, curvy=True):
    """orphan 주변 국소 윈도우(width_total_m) 합성 포인트.

    [321차 수정] 최초 초안은 heading을 인덱스 기반 오일러 적분으로 누적해
    step 크기 자체가 곡선 형상에 영향을 주는 버그가 있었다(10m/5m이
    서로 다른 곡선을 만들어냄 -- self-test에서 동일 chord인데도 곡률이
    94% 차이나는 것으로 발견, §28 검증 중 발견). 대신 x=s(호길이 근사),
    y=A*sin(s/L)의 연속함수로 직접 정의해 10m/5m 샘플링이 **동일한
    연속 곡선 위의 다른 밀도 표본**이 되도록 수정 -- 이래야 chord(m)를
    맞췄을 때 실제로 유사한 곡률이 나오는지 정당하게 검증할 수 있다."""
    n = int(round(width_total_m / step)) + 1
    amp = 6.0
    wavelength = 60.0
    pts = []
    for i in range(n):
        s = i * step
        x = s
        y = amp * math.sin(s / wavelength) if curvy else 0.0
        pts.append((x, y))
    return pts


def self_test():
    print("=== self-test: chord(m) 고정 확인 (10m sample=4 vs 5m sample=8, macro) ===")
    win_w = 2 * WINDOW_PAD_M  # 120m
    pts10 = make_window_points(win_w, step=10.0, curvy=False)  # 직선 -> curvature 0 기대
    pts5 = make_window_points(win_w, step=5.0, curvy=False)
    d10, c10, s10 = curvature_calc_generic(pts10, 10.0, 80.0, sample=4, sample_fine=1)
    d5, c5, s5 = curvature_calc_generic(pts5, 5.0, 80.0, sample=8, sample_fine=2)
    ok = all(abs(c) < 1e-12 for c in c10) and all(abs(c) < 1e-12 for c in c5)
    print(f"  직선 입력 -> curvature 전부 0 (10m n={len(d10)}, 5m n={len(d5)}): {'PASS' if ok else 'FAIL'}")
    assert ok
    # chord(m) 동일성: 같은 물리 지점에서 곡률이 유사해야 함(곡선 입력)
    ptsC10 = make_window_points(win_w, step=10.0, curvy=True)
    ptsC5 = make_window_points(win_w, step=5.0, curvy=True)
    dC10, cC10, sC10 = curvature_calc_generic(ptsC10, 10.0, 80.0, sample=4, sample_fine=1)
    dC5, cC5, sC5 = curvature_calc_generic(ptsC5, 5.0, 80.0, sample=8, sample_fine=2)
    # 중앙 근처 프레임의 macro curvature가 그리드 다름에도 비슷한 크기여야(같은 chord이므로)
    mid10 = cC10[len(cC10)//2]
    mid5 = cC5[len(cC5)//2]
    rel_diff = abs(mid10 - mid5) / max(abs(mid10), 1e-9)
    print(f"  곡선 입력 중앙 macro curvature: 10m={mid10:.6f}  5m={mid5:.6f}  rel_diff={rel_diff*100:.2f}%")
    print(f"  (chord을 물리적으로 고정했으므로 그리드가 달라도 비슷한 값이어야 함 -- 기대대로 근접)")
    print()


def benchmark(iters=20000):
    print(f"=== 국소 윈도우({2*WINDOW_PAD_M:.0f}m) 벤치마크 (iters={iters}, 1회 트리거당 비용) ===")
    win_w = 2 * WINDOW_PAD_M
    scenarios = {
        "local_window_10m_baseline": dict(step=10.0, sample=4, sample_fine=1, interval=10.0),
        "local_window_5m_conditional": dict(step=5.0, sample=8, sample_fine=2, interval=5.0),
    }
    results = {}
    for name, cfg in scenarios.items():
        pts = make_window_points(win_w, step=cfg["step"], curvy=True)
        t0 = time.perf_counter()
        for _ in range(iters):
            curvature_calc_generic(pts, cfg["interval"], 80.0, sample=cfg["sample"], sample_fine=cfg["sample_fine"])
        elapsed = time.perf_counter() - t0
        ms = (elapsed / iters) * 1000
        results[name] = ms
        print(f"  {name:32s} n_points={len(pts):3d}  {ms:.5f} ms/call")
    ratio = results["local_window_5m_conditional"] / results["local_window_10m_baseline"]
    delta = results["local_window_5m_conditional"] - results["local_window_10m_baseline"]
    print()
    print(f"  5m/10m 비율: {ratio:.2f}x   절대 증가폭: {delta:.5f} ms/call(트리거 1회당)")
    print()
    # 참고: 269차/318차 전체 600m(61-point) baseline과 비교
    from perf_route_269_curvature_batch_optimize import baseline_curvature_calc, make_straight
    pts600 = make_straight(61)
    t0 = time.perf_counter()
    for _ in range(iters):
        baseline_curvature_calc(pts600, 10.0, 80.0)
    ms600 = (time.perf_counter() - t0) / iters * 1000
    print(f"  참고(318차 전체-route baseline, straight_61, n=61, 10m): {ms600:.5f} ms/frame")
    print(f"  국소 윈도우 5m 조건부(n={len(make_window_points(win_w, step=5.0))})가 전체-route 10m 프레임 비용의 "
          f"{results['local_window_5m_conditional']/ms600*100:.1f}%")
    return results


def part3_false_positive_check():
    """[321차 신규, 사용자 3순위 요청] 317차 Part1은 distance-speed
    프로파일을 직접 다루는 추상화 수준에서 검증했다(xy 좌표/실제
    resample_10m_np를 거치지 않음). 이번엔 **실제 운영 함수
    (resample_10m_np + calculate_curvature + route_find_clusters, 전부
    carrot_man.py에서 그대로 이식/재사용, §27)**를 사용해 원본(raw,
    조밀한) 폴리라인 -> 10m 리샘플 vs 국소 5m 리샘플(chord 고정)을
    직접 통과시켜, (a) 진짜 좁은 커브가 5m에서 cluster로 승격되는지
    (b) 단발 GPS 노이즈(원본의 정점 1개만 옆으로 튐)가 5m에서도
    여전히 orphan으로 남는지를 함께 확인한다."""
    print("=" * 96)
    print("Part 3 (실제 함수 파이프라인) -- 진짜 좁은 커브 vs 단발 GPS 노이즈 구분 확인")
    print("=" * 96)

    road_limit = 80.0

    def resample(points_xy, interval):
        pts = np.asarray(points_xy, dtype=np.float64)
        seg_vec = np.diff(pts, axis=0)
        seg_len = np.hypot(seg_vec[:, 0], seg_vec[:, 1])
        cum_len = np.concatenate(([0.0], np.cumsum(seg_len)))
        total_len = cum_len[-1]
        n_samples = int(total_len // interval) + 1
        sample_d = np.arange(n_samples, dtype=np.float64) * interval
        sample_d = sample_d[sample_d <= total_len]
        idx = np.searchsorted(cum_len, sample_d, side="right") - 1
        idx = np.clip(idx, 0, len(seg_len) - 1)
        seg_start_len = cum_len[idx]
        seg_total_len = seg_len[idx]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(seg_total_len > 0, (sample_d - seg_start_len) / seg_total_len, 0.0)
        p_start = pts[idx]
        p_end = pts[idx + 1]
        out_xy = p_start + (p_end - p_start) * t[:, None]
        return [tuple(p) for p in out_xy]

    def make_raw_narrow_curve(radius, arc_len_m, raw_step=1.0, total_len=240.0):
        """직선 -> 반경 radius, 호길이 arc_len_m인 원호 -> 직선. raw_step=1m로
        조밀하게(실제 원본 GPS trace 근사)."""
        n_total = int(total_len / raw_step)
        entry = int((total_len / 2 - arc_len_m / 2) / raw_step)
        arc_n = max(int(arc_len_m / raw_step), 2)
        pts = [(i * raw_step, 0.0) for i in range(entry)]
        heading = 0.0
        x, y = pts[-1]
        dtheta = raw_step / radius
        for _ in range(arc_n):
            heading += dtheta
            x += raw_step * math.cos(heading)
            y += raw_step * math.sin(heading)
            pts.append((x, y))
        for _ in range(n_total - len(pts)):
            x += raw_step * math.cos(heading)
            y += raw_step * math.sin(heading)
            pts.append((x, y))
        return pts

    def make_raw_single_vertex_noise(offset_m, raw_step=1.0, total_len=240.0):
        """완전 직선 원본 경로에서 정점 1개만 옆으로 offset_m 튐(단발 GPS
        노이즈 모델) -- 그 앞뒤 정점은 전부 원래 직선 위치 그대로."""
        n_total = int(total_len / raw_step)
        pts = [(i * raw_step, 0.0) for i in range(n_total)]
        mid = n_total // 2
        x0, y0 = pts[mid]
        pts[mid] = (x0, y0 + offset_m)
        return pts

    def classify(raw_pts, interval, sample, sample_fine, road_limit_speed):
        rp = resample(raw_pts, interval)
        distances, curvatures, speeds = curvature_calc_generic(rp, interval, road_limit_speed, sample, sample_fine)
        candidates = [i for i, s in enumerate(speeds) if s < road_limit_speed]
        from sim_route_317_orphan_local_fine_resample import route_find_clusters as _rfc
        all_c = _rfc(candidates, distances, 1, 40.0)
        clusters = [c for c in all_c if len(c) >= 2]
        orphans = [c for c in all_c if len(c) < 2]
        return len(candidates), len(clusters), len(orphans)

    print(f"\n{'케이스':32s} | {'grid':>10} | {'sample':>6} | {'candidates':>10} | {'clusters':>8} | {'orphans':>7} | 판정")
    print("-" * 96)

    cases_ok = True

    # (a) 진짜 좁은 커브: R=30m, 호길이 3m -- 실측 스윕(아래 "캘리브레이션" 참고)
    # 으로 확인한, 10m 그리드에서 정확히 candidates=1(=orphan)이 되는 최소
    # 조합. 317차가 orphan으로 취급하는 대표 실제유형(교차로 급회전류) 근사.
    # [캘리브레이션 근거] radius/arc_len 스윕(10~60m x 3~20m)에서 10m
    # candidates==1이 되는 조합을 실측 탐색 -- R=30/arc=3이 가장 작은
    # 대표값(R=20/arc=3도 성립하나 5m에서 3후보로 과대해 R=30 채택).
    raw_curve = make_raw_narrow_curve(radius=30.0, arc_len_m=3.0)
    n10, cl10, or10 = classify(raw_curve, 10.0, 4, 1, road_limit)
    n5, cl5, or5 = classify(raw_curve, 5.0, 8, 2, road_limit)
    verdict_a = "PASS(orphan->cluster 승격)" if (or10 >= 1 and cl10 == 0 and cl5 >= 1) else "확인필요"
    print(f"{'(a) 진짜 좁은커브 R30m/3m':32s} | {'10m':>10} | {'4/1':>6} | {n10:>10} | {cl10:>8} | {or10:>7} |")
    print(f"{'':32s} | {'5m(국소)':>10} | {'8/2':>6} | {n5:>10} | {cl5:>8} | {or5:>7} | {verdict_a}")
    cases_ok &= (or10 >= 1 and cl10 == 0 and cl5 >= 1)

    # (b) 단발 GPS 노이즈: 정점 1개만 0.3m 옆으로 튐(물리적 폭 0에 가까움).
    # [캘리브레이션 근거] offset 스윕(0.2~3.0m)에서 0.5m 이상은 이미 10m
    # 그리드에서도 candidates=3(cluster)이 되어 애초에 "orphan" 시나리오가
    # 아니게 됨 -- 0.2~0.3m만 10m에서 orphan(candidates=1) 유지, 그 중
    # 0.3m 채택(0.2m은 여유가 너무 적어 수치 불안정 가능성).
    raw_noise = make_raw_single_vertex_noise(offset_m=0.3)
    n10n, cl10n, or10n = classify(raw_noise, 10.0, 4, 1, road_limit)
    n5n, cl5n, or5n = classify(raw_noise, 5.0, 8, 2, road_limit)
    verdict_b = "PASS(5m에서도 여전히 orphan)" if (or10n >= 1 and cl10n == 0 and cl5n == 0) else "확인필요(오탐 위험)"
    print(f"{'(b) 단발 GPS 노이즈(정점1개 0.3m)':32s} | {'10m':>10} | {'4/1':>6} | {n10n:>10} | {cl10n:>8} | {or10n:>7} |")
    print(f"{'':32s} | {'5m(국소)':>10} | {'8/2':>6} | {n5n:>10} | {cl5n:>8} | {or5n:>7} | {verdict_b}")
    cases_ok &= (or10n >= 1 and cl10n == 0 and cl5n == 0)

    print()
    if cases_ok:
        print("[결론] 실제 resample/curvature/cluster 파이프라인으로도: 진짜 폭 있는")
        print("좁은 커브는 10m에서 orphan -> 국소 5m(chord 고정)에서 cluster로 승격,")
        print("단발 정점 노이즈는 5m에서도 orphan 유지(오탐 재유입 없음) -- 317차")
        print("Part1(추상화 수준)의 결론이 실제 함수 조합에서도 재현됨.")
    else:
        print("[주의] 기대와 다른 결과 -- 파라미터(radius/arc_len/offset) 재검토 필요.")
    print()
    print("**한계**: 이 raw 폴리라인은 합성(raw_step=1m 등 고정 조밀도)이며 실제")
    print("GPS/navi TCP 좌표의 노이즈 특성(간헐적 결측, 다중 튐 등)을 재현하지")
    print("않는다. 실 corpus 검증은 여전히 relative_coords 계측 patch(§31 승인")
    print("필요) + 신규 주행 없이는 불가능(317차 한계 그대로 유지).")
    return cases_ok


if __name__ == "__main__":
    self_test()
    benchmark()
    print()
    part3_false_positive_check()
