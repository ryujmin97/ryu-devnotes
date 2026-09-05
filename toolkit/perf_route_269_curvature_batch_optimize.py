#!/usr/bin/env python3
"""
perf_route_269_curvature_batch_optimize.py (269차 신규)

목적: carrot_man.py::carrot_navi_route()의 macro(sample=4)/fine
(ROUTE_CURVATURE_FINE_SAMPLE=1) 곡률 계산 이중루프를 대상으로,
269차가 코드 추적으로 확정한 3개 CPU 최적화 후보를 실제로 적용하기
전에 (1) 출력 동일성(§28/§29 -- 시뮬레이션 선행 원칙)과 (2) 실제
시간 절감폭을 합성 데이터로 먼저 검증한다.

269차가 확정한 3개 후보:
  A. fine 루프가 macro보다 sample_fine*2(=2) < sample*2(=8)만큼 더
     계산하는데, 뒷단 병합 루프(`for j in range(len(distances))`)는
     macro 길이(len(distances))만 소비 -- fine 후반 초과분은 완전히
     낭비. 게다가 macro/fine 두 거리그리드가 둘 다 -10.0에서 시작해
     10.0씩 증가하는 lock-step 구조라 fine_points[j][0] ==
     distances[j]가 항상 정확히 성립 -- 즉 "가장 가까운 fine 포인트
     탐색"(fine_idx 순차탐색, while 루프) 자체가 불필요한 간접참조이며
     매 프레임 정확히 fine_points[j]가 선택되는 것과 결과가 100%
     동일하다(아래 self_test가 이를 실증).
  B. np.interp가 매 루프 반복마다 스칼라 1개씩 호출됨(macro 53회 +
     fine 59회 = 112회/프레임, 61-point/600m/10m 기준). 배열로 모아
     macro 1회 + fine 1회, 총 2회 배치 호출로 대체 가능 -- np.interp는
     원소별 독립 선형보간이므로 배치화해도 각 원소의 결과값은 스칼라
     호출과 완전히 동일(연산 재배열로 인한 부동소수점 오차조차 없음 --
     동일 함수를 동일 x값에 대해 그대로 호출).
  C. fine_points를 (distance, curvature, speed) 튜플 리스트로 만드는
     대신, A의 인덱스 정렬 확정으로 탐색 자체가 사라지므로 튜플도
     불필요 -- curvature만 리스트로 유지하면 충분.

**중요**: 이 스크립트는 `carrot_man.py`의 실제 함수를 import하지
않는다(carrot_man.py는 openpilot 런타임 의존성이 많아 이 컨테이너에서
단독 실행 불가 -- cereal/msgq 등). 대신 아래 baseline_curvature_calc()가
carrot_man.py L919-977(HEAD 8964413=266차, 269차가 코드로 확인한 부분,
223차 이후 이 구간은 구조 변경 없음)을 **1:1 그대로 재현**한다.
patch 적용 전 diff로 원본과 다시 한번 라인 대조할 것(§28 -- 추측 금지).

**한계(명시)**:
- 합성 폴리라인만 사용 -- 실 corpus(naviPaths) 검증 아님. 실 corpus
  A/B는 apex_idx/apex_dist/apex_speed/apex_mode/apex_streak/out_speed
  까지 `replay_route_237_vs_baseline.py` 방식으로 별도 수행 필요
  (corpus CSV 필요, 이번 세션엔 컨테이너에 route CSV 없음).
- 타이밍 벤치마크는 이 컨테이너(클라우드 서버 CPU)에서 측정한 것으로,
  실제 C3 디바이스(임베디드 ARM) 절대시간과는 다르다 -- **상대적
  호출횟수/알고리즘 복잡도 절감 비율**로만 해석할 것.
- 실차 검증: 미실시.

사용:
    python3 perf_route_269_curvature_batch_optimize.py --self-test
    python3 perf_route_269_curvature_batch_optimize.py --benchmark --iters 3000
    (인자 없이 실행하면 둘 다 수행)
"""
import argparse
import math
import random
import time

import numpy as np

# carrot_man.py L44-45 (HEAD 8964413) 그대로
V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265., 1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]
ROUTE_CURVE_NEGLIGIBLE_THRESHOLD = 0.001
ROUTE_CURVATURE_FINE_SAMPLE = 1


def calculate_curvature(p1, p2, p3):
    """carrot_man.py L373-391 (HEAD 8964413) 그대로."""
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        curvature = 0
    else:
        curvature = cross_product / (len_v1 * len_v2 * len_v1)
    return curvature


def baseline_curvature_calc(resampled_points, distance_interval, road_limit_speed,
                             sample=4, sample_fine=ROUTE_CURVATURE_FINE_SAMPLE):
    """carrot_man.py L919-977 (HEAD 8964413) 1:1 재현. 최적화 없음."""
    curvatures = []
    distances = []
    distance = -10.0
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
        fine_distance = -10.0
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


def optimized_curvature_calc(resampled_points, distance_interval, road_limit_speed,
                              sample=4, sample_fine=ROUTE_CURVATURE_FINE_SAMPLE):
    """269차 Phase1 최적화안: A(fine 범위 제한 + 탐색 제거) + B(np.interp
    배치화) + C(fine tuple 제거)."""
    curvatures = []
    distances = []
    distance = -10.0
    if len(resampled_points) < sample * 2 + 1:
        return distances, curvatures, []

    macro_abs_curv = []
    for i in range(len(resampled_points) - sample * 2):
        distance += distance_interval
        p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
        curvature = calculate_curvature(p1, p2, p3)
        curvatures.append(curvature)
        macro_abs_curv.append(abs(curvature))
        distances.append(distance)

    # [B] macro 배치 np.interp 1회
    macro_speeds_arr = np.interp(macro_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
    speeds = []
    for i in range(len(curvatures)):
        speed = macro_speeds_arr[i]
        if macro_abs_curv[i] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
            speed = max(speed, road_limit_speed)
        speeds.append(speed)

    if sample_fine and sample_fine < sample and len(resampled_points) >= sample_fine * 2 + 1:
        # [A] macro/fine 그리드는 둘 다 distance=-10.0에서 시작해
        # distance_interval씩 lock-step 증가하므로 fine_points[j]는
        # distances[j]와 항상 정확히 같은 지점 -- 탐색 불필요, 딱
        # len(distances)개만 계산하면 원본과 100% 동일한 소비량.
        n_fine_available = len(resampled_points) - sample_fine * 2
        n_fine = min(len(distances), n_fine_available)
        if n_fine > 0:
            fine_curvatures = []
            fine_abs_curv = []
            for i in range(n_fine):
                p1, p2, p3 = resampled_points[i], resampled_points[i + sample_fine], resampled_points[i + sample_fine * 2]
                f_curvature = calculate_curvature(p1, p2, p3)
                fine_curvatures.append(f_curvature)
                fine_abs_curv.append(abs(f_curvature))
            # [B] fine 배치 np.interp 1회
            fine_speeds_arr = np.interp(fine_abs_curv, V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS)
            for j in range(n_fine):
                f_curv = fine_curvatures[j]
                f_speed = fine_speeds_arr[j]
                if fine_abs_curv[j] < ROUTE_CURVE_NEGLIGIBLE_THRESHOLD:
                    f_speed = max(f_speed, road_limit_speed)
                if f_speed < speeds[j]:
                    speeds[j] = f_speed
                    curvatures[j] = f_curv
    return distances, curvatures, speeds


# ---------------------------------------------------------------------------
# 합성 폴리라인 생성 (실 naviPaths 형태 근사 -- 이미 10m 리샘플된 상태로 가정,
# resample_10m_np()는 이 최적화 대상 범위 밖이라 여기서 재현하지 않음)
# ---------------------------------------------------------------------------
def make_straight(n_points, step=10.0):
    return [(i * step, 0.0) for i in range(n_points)]


def make_single_turn(n_points, step=10.0, turn_at=30, radius=27.0, arc_points=8):
    """직선 -> 원호(반경 radius) -> 직선. 147차/269차가 실측 기준으로
    쓴 R약27m 급코너류 재현."""
    pts = [(i * step, 0.0) for i in range(turn_at)]
    cx, cy = pts[-1][0], pts[-1][1] + radius
    start_angle = -math.pi / 2
    dtheta = step / radius
    x0, y0 = pts[-1]
    heading = 0.0
    x, y = x0, y0
    for _ in range(arc_points):
        heading += dtheta
        x += step * math.cos(heading)
        y += step * math.sin(heading)
        pts.append((x, y))
    last_heading = heading
    for k in range(1, n_points - len(pts) + 1):
        x2 = pts[-1][0] + step * math.cos(last_heading)
        y2 = pts[-1][1] + step * math.sin(last_heading)
        pts.append((x2, y2))
    return pts[:n_points]


def make_s_curve(n_points, step=10.0):
    pts = []
    heading = 0.0
    x, y = 0.0, 0.0
    for i in range(n_points):
        pts.append((x, y))
        heading += 0.05 * math.sin(i / 6.0)
        x += step * math.cos(heading)
        y += step * math.sin(heading)
    return pts


def make_random_jitter(n_points, step=10.0, seed=0):
    rnd = random.Random(seed)
    pts = []
    heading = 0.0
    x, y = 0.0, 0.0
    for i in range(n_points):
        pts.append((x, y))
        heading += rnd.uniform(-0.15, 0.15)
        x += step * math.cos(heading)
        y += step * math.sin(heading)
    return pts


SCENARIOS = {
    "straight_61": lambda: make_straight(61),
    "single_turn_61": lambda: make_single_turn(61),
    "s_curve_61": lambda: make_s_curve(61),
    "random_jitter_61": lambda: make_random_jitter(61, seed=1),
    "random_jitter_61_seed2": lambda: make_random_jitter(61, seed=2),
    # 경계값: sample_fine*2+1(=3)~sample*2+1(=9) 사이 -- fine은 돌지만
    # macro는 건너뛰는 구간
    "boundary_below_macro_5": lambda: make_straight(5),
    "boundary_exact_macro_9": lambda: make_single_turn(9, turn_at=3, arc_points=4),
    "boundary_exact_fine_3": lambda: make_straight(3),
    "boundary_below_fine_2": lambda: make_straight(2),
    "long_route_121": lambda: make_random_jitter(121, seed=3),
}


def self_test():
    print("=== self-test: baseline vs optimized 출력 동일성 ===")
    road_limit_speed = 80.0
    all_pass = True
    for name, gen in SCENARIOS.items():
        pts = gen()
        d0, c0, s0 = baseline_curvature_calc(pts, 10.0, road_limit_speed)
        d1, c1, s1 = optimized_curvature_calc(pts, 10.0, road_limit_speed)

        ok = True
        reason = ""
        if d0 != d1:
            ok = False
            reason = f"distances 불일치 (len {len(d0)} vs {len(d1)})"
        elif len(c0) != len(c1) or len(s0) != len(s1):
            ok = False
            reason = f"길이 불일치 curv({len(c0)},{len(c1)}) speed({len(s0)},{len(s1)})"
        else:
            for i, (a, b) in enumerate(zip(c0, c1)):
                if a != b and not math.isclose(a, b, rel_tol=0, abs_tol=1e-15):
                    ok = False
                    reason = f"curvature[{i}] {a!r} != {b!r}"
                    break
            if ok:
                for i, (a, b) in enumerate(zip(s0, s1)):
                    fa, fb = float(a), float(b)
                    if fa != fb and not math.isclose(fa, fb, rel_tol=0, abs_tol=1e-12):
                        ok = False
                        reason = f"speed[{i}] {fa!r} != {fb!r}"
                        break

        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {name:24s} n_points={len(pts):3d} "
              f"macro_n={len(d0):3d} {reason}")

    print()
    if all_pass:
        print(f"결과: 전체 {len(SCENARIOS)}개 시나리오 PASS -- baseline과 "
              "optimized의 distances/curvatures/speeds가 완전히 동일함.")
    else:
        print("결과: FAIL 발견 -- 최적화 코드에 원본과의 차이가 있음. "
              "패치 적용 보류.")
    return all_pass


def benchmark(iters=2000):
    print(f"=== 타이밍 벤치마크 (iters={iters}, 이 컨테이너 CPU 기준"
          " -- 상대비교 전용, C3 디바이스 절대시간 아님) ===")
    road_limit_speed = 80.0
    for name in ("straight_61", "single_turn_61", "s_curve_61", "long_route_121"):
        pts = SCENARIOS[name]()

        t0 = time.perf_counter()
        for _ in range(iters):
            baseline_curvature_calc(pts, 10.0, road_limit_speed)
        t_base = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(iters):
            optimized_curvature_calc(pts, 10.0, road_limit_speed)
        t_opt = time.perf_counter() - t0

        base_ms = (t_base / iters) * 1000
        opt_ms = (t_opt / iters) * 1000
        speedup = t_base / t_opt if t_opt > 0 else float("inf")
        print(f"  {name:16s} n_points={len(pts):3d}  "
              f"baseline={base_ms:.4f}ms/frame  optimized={opt_ms:.4f}ms/frame  "
              f"speedup={speedup:.2f}x")
    print()
    print("주의: 이 수치는 CPython 함수호출/리스트조작 오버헤드 절감폭을")
    print("보여줄 뿐, 임베디드 C3 디바이스의 실제 절감 초 단위 값이 아님.")
    print("실차 CPU 부하 검증은 미실시 -- 다음 작업으로 남김.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--iters", type=int, default=2000)
    args = ap.parse_args()

    run_test = args.self_test or not (args.self_test or args.benchmark)
    run_bench = args.benchmark or not (args.self_test or args.benchmark)

    ok = True
    if run_test:
        ok = self_test()
        print()
    if run_bench:
        benchmark(args.iters)

    if run_test and not ok:
        raise SystemExit(1)
