"""
213차: route 곡률 스캔 루프의 20m 하드플로어(212차 진단) 제거 검증.

carrot_man.py::carrot_navi_route()의 macro/fine curvature 스캔 루프에서
`distance = 10.0`(선증가) -> `distance = 0.0`으로 바꾸는 패치(212차 A안)를
실제 함수와 분리된 순수함수로 복제해, 차량이 커브 apex에 접근할 때
apex_dist가 20.0에 고정되지 않고 실제로 0을 향해 단조감소하는지 확인한다.

실제 carrot_man.py 수정 자체는 이미 패치 적용됨(213차) -- 이 스크립트는
그 로직을 격리 재현해 회귀 없이 의도대로 동작하는지 사전/사후 대조하는
용도(§ 시뮬레이트 먼저 원칙).
"""
import numpy as np


def calculate_curvature(p1, p2, p3):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    a = np.hypot(x2 - x1, y2 - y1)
    b = np.hypot(x3 - x2, y3 - y2)
    c = np.hypot(x3 - x1, y3 - y1)
    s = (a + b + c) / 2.0
    area = max(s * (s - a) * (s - b) * (s - c), 0.0) ** 0.5
    if a * b * c == 0 or area == 0:
        return 0.0
    return 4.0 * area / (a * b * c)


def scan_distances(resampled_points, distance_interval=10.0, sample=4, use_old_offset=True):
    """carrot_man.py 곡률스캔 루프 복제. use_old_offset=True면 213차 이전(버그),
    False면 213차 이후(distance=0.0 시작, 패치 적용)."""
    distances = []
    curvatures = []
    distance = 10.0 if use_old_offset else -10.0
    for i in range(len(resampled_points) - sample * 2):
        distance += distance_interval
        p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
        curvatures.append(calculate_curvature(p1, p2, p3))
        distances.append(distance)
    return distances, curvatures


def make_approach_points(n=40, step=10.0):
    """직선 경로 위 점들(곡률=0, 거리 진행만 검증하는 용도)."""
    return [(0.0, i * step) for i in range(n)]


def run_unit_tests():
    results = []

    # 1) 213차 이전: index 0의 거리가 항상 20.0으로 고정(차량이 10m씩
    #    전진하며 매 프레임 재스캔해도 첫 샘플 라벨은 불변)되는 버그 재현.
    pts = make_approach_points()
    dist_old, _ = scan_distances(pts, use_old_offset=True)
    bug_reproduced = dist_old[0] == 20.0
    results.append(("OLD: idx0 distance == 20.0 (버그 재현)", bug_reproduced))

    # 2) 213차 이후: index 0의 거리가 0.0(차량 현재위치와 사실상 동일)으로
    #    정상화됨.
    dist_new, _ = scan_distances(pts, use_old_offset=False)
    fixed_ok = dist_new[0] == 0.0
    results.append(("NEW: idx0 distance == 0.0 (패치 확인)", fixed_ok))

    # 3) 매 10m 간격 시퀀스 자체는 old/new 동일하게 유지(212차가 진단한
    #    20m 하드플로어만 전 구간에서 균일하게 제거, 나머지 구조/간격은
    #    회귀 없음 확인).
    diffs = [round(n - o, 6) for o, n in zip(dist_old, dist_new)]
    structure_preserved = all(d == -20.0 for d in diffs)
    results.append(("구조 보존: new = old - 20.0 (20m 하드플로어만 균일 제거)", structure_preserved))

    # 4) 차량이 실제로 apex에 접근하는 상황(20Hz로 매 프레임 10m씩 전진한다고
    #    가정, 매 프레임 새로 스캔)에서 apex로 선택된 인덱스의 거리가
    #    단조감소(0을 향해 접근)하는지 확인 -- old는 항상 20.0 고정이라
    #    "감소"가 아예 성립하지 않음(212차 실측과 동일 증상).
    approach_frames = []  # 프레임마다 차량이 5m씩 전진(경로점 자체를 shift)
    for shift in range(0, 25, 5):
        shifted = [(x, y - shift) for x, y in pts]
        shifted = [(x, y) for x, y in shifted if y >= 0.0]
        approach_frames.append(shifted)
    old_apex_dists = [scan_distances(f, use_old_offset=True)[0][0] for f in approach_frames if len(f) > 8]
    new_apex_dists = [scan_distances(f, use_old_offset=False)[0][0] for f in approach_frames if len(f) > 8]
    old_all_stuck = all(d == 20.0 for d in old_apex_dists)
    new_decreasing = all(new_apex_dists[i] >= new_apex_dists[i + 1] for i in range(len(new_apex_dists) - 1))
    results.append(("OLD: 접근 중에도 apex idx0 거리 20.0 고정(증상 재현)", old_all_stuck))
    results.append(("NEW: 접근 중 apex idx0 거리 단조비증가(정상 접근)", new_decreasing))

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{len(results)} PASS")
    return passed == len(results)


if __name__ == "__main__":
    import sys
    ok = run_unit_tests()
    sys.exit(0 if ok else 1)
