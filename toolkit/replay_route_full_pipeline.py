"""
148차 신규 (route898 898edd0f96 seg10 실측 로그로 147차 패치 검증 계기).

목적: carrot_man.py::carrot_navi_route()의 전체 out_speed 계산 파이프라인
(매크로 sample=4 곡률 -> 147차 sample_fine=1 병합 -> 91차 margin_kph 역방향DP
-> 132차 프레임간 램프 리미터)을 extract_log.py --with-navi-paths로 뽑은
CSV의 naviPaths(=carrot_navi_route()가 실제로 쓰는 리샘플 폴리라인 그 자체,
GPS 재구성/근사 불필요)로 프레임 단위 그대로 재현한다.

기존 recompute_route_curvature_speed()(analysis_helpers.py)는 "이 지점
곡률이 얼마나 급한가"만 계산하고 역방향DP/램프리미터는 포함하지 않아,
147차가 발견한 실측 근접(10~30m) 오탐 후보(GPS 리샘플 시작점 부근 노이즈성
곡률 스파이크)가 최종 발행 desiredSpeed에 실제로 전파되는지는 답하지 못했다.
이 스크립트가 그 공백을 메운다.

의존성: numpy.
사용:
    python3 replay_route_full_pipeline.py <route.csv> [--accel 0.70]
"""
import csv
import math
import sys
import numpy as np

V_CURVE_LOOKUP_BP = [0., 1./800., 1./670., 1./560., 1./440., 1./360., 1./265.,
                      1./190., 1./135., 1./85., 1./55., 1./30., 1./25.]
V_CRUVE_LOOKUP_VALS = [300, 150, 120, 110, 100, 90, 80, 70, 60, 50, 40, 15, 5]

ROUTE_ENTRY_MARGIN_KPH = 25.0
ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_CURVATURE_FINE_SAMPLE = 1


def parse_navi_paths(navi_paths_str):
    if not navi_paths_str:
        return [], []
    points, distances = [], []
    for chunk in navi_paths_str.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(",")
        if len(parts) != 3:
            continue
        try:
            x, y, d = float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            continue
        points.append((x, y))
        distances.append(d)
    return points, distances


def calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


class RouteFullPipelineReplay:
    """carrot_man.py carrot_navi_route()의 out_speed 계산부(리샘플 폴리라인
    입력 이후 전체) 리터럴 이식. patched=True/False로 147차
    (sample_fine merge) 유무를 토글해 before/after 비교 가능."""

    def __init__(self, accel_limit=0.70, road_limit_speed=200.0, patched=True,
                 vturn_safe_time=2.0, apply_ramp_limiter=True):
        self.accel_limit = accel_limit
        self.road_limit_speed = road_limit_speed
        self.patched = patched
        self.vturn_safe_time = vturn_safe_time
        self.apply_ramp_limiter = apply_ramp_limiter
        self._route_speed_prev = None

    def step(self, resampled_points, v_ego_kph):
        """한 프레임(=한 row의 naviPaths) 처리, out_speed(km/h) 리턴."""
        distance_interval = 10.0
        sample = 4
        n = len(resampled_points)
        if n < sample * 2 + 1:
            self._route_speed_prev = None
            return 300.0

        curvatures, speeds, distances = [], [], []
        distance = 10.0
        for i in range(n - sample * 2):
            distance += distance_interval
            p1, p2, p3 = resampled_points[i], resampled_points[i + sample], resampled_points[i + sample * 2]
            curvature = calculate_curvature(p1, p2, p3)
            speed = float(np.interp(abs(curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS))
            if abs(curvature) < 0.02:
                speed = max(speed, self.road_limit_speed)
            curvatures.append(curvature)
            speeds.append(speed)
            distances.append(distance)

        if self.patched:
            sample_fine = ROUTE_CURVATURE_FINE_SAMPLE
            if sample_fine and sample_fine < sample and n >= sample_fine * 2 + 1:
                fine_distance = 10.0
                fine_points = []
                for i in range(n - sample_fine * 2):
                    fine_distance += distance_interval
                    p1, p2, p3 = resampled_points[i], resampled_points[i + sample_fine], resampled_points[i + sample_fine * 2]
                    f_curvature = calculate_curvature(p1, p2, p3)
                    f_speed = float(np.interp(abs(f_curvature), V_CURVE_LOOKUP_BP, V_CRUVE_LOOKUP_VALS))
                    if abs(f_curvature) < 0.02:
                        f_speed = max(f_speed, self.road_limit_speed)
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

        accel_limit_kmh = self.accel_limit * 3.6
        out_speeds = [0.0] * len(speeds)
        out_speeds[-1] = speeds[-1]

        time_delay = 0
        time_wait = 0
        route_prev_state = None
        for i in range(len(speeds) - 2, -1, -1):
            target_speed = speeds[i]
            next_out_speed = out_speeds[i + 1]

            if target_speed < next_out_speed:
                margin_target_speed = max(0.0, target_speed - ROUTE_ENTRY_MARGIN_KPH)
                time_delay = max(0, ((v_ego_kph - margin_target_speed) / accel_limit_kmh))
                time_wait = -time_delay
                route_prev_state = 'decel'
            elif target_speed > next_out_speed and route_prev_state == 'decel':
                time_wait += self.vturn_safe_time
                route_prev_state = 'accel'

            time_interval = distance_interval / (next_out_speed / 3.6) if next_out_speed > 0 else 0
            time_apply = min(time_interval, max(0, time_interval + time_wait))
            max_allowed_speed = next_out_speed + (accel_limit_kmh * time_apply)
            adjusted_speed = min(target_speed, max_allowed_speed)
            time_wait += min(2.0, time_interval)
            out_speeds[i] = adjusted_speed

        out_speed = out_speeds[0]

        if self.apply_ramp_limiter and self._route_speed_prev is not None:
            max_step_kmh = accel_limit_kmh * ROUTE_SPEED_LOOP_DT
            lo = self._route_speed_prev - max_step_kmh
            hi = self._route_speed_prev + max_step_kmh
            out_speed = min(max(out_speed, lo), hi)
        self._route_speed_prev = out_speed
        return out_speed


def load_route_rows(csv_path):
    with open(csv_path, newline='') as f:
        return list(csv.DictReader(f))


def run_replay(csv_path, accel=0.70):
    rows = load_route_rows(csv_path)
    if not any(r.get('naviPaths') for r in rows):
        print("naviPaths가 채워진 행이 없습니다 (--with-navi-paths로 재추출 필요).")
        return

    # carrot_navi_route()는 src(route/vturn/gas 등)와 무관하게 매 20Hz 사이클
    # 항상 호출되어 _route_speed_prev가 계속 갱신된다 -- route가 아닌 프레임을
    # 건너뛰면 램프리미터 상태 연속성이 깨져 재현이 어긋난다. 따라서 전체
    # 행을 순서대로 통과시키되, published와의 비교는 src=='route' 행에서만 한다.
    patched_sim = RouteFullPipelineReplay(accel_limit=accel, patched=True)
    unpatched_sim = RouteFullPipelineReplay(accel_limit=accel, patched=False)

    results = []
    for r in rows:
        naq = r.get('naviPaths', '')
        if not naq:
            # naviPaths가 비어있는 프레임(플래그 off였거나 route 미가용) --
            # 상태 유지 관점에서 스킵하지 않고 이전 프레임 상태를 그대로
            # carry(실제 코드는 매 사이클 재계산하지만 이 로그에선 항상 채워짐)
            continue
        points, distances = parse_navi_paths(naq)
        v_ego_kph = float(r['vEgo']) * 3.6
        p_out = patched_sim.step(points, v_ego_kph)
        u_out = unpatched_sim.step(points, v_ego_kph)
        if r.get('src') != 'route':
            continue
        published = float(r['desiredSpeed'])
        results.append({
            't': float(r['t']), 'published': published,
            'patched_sim': p_out, 'unpatched_sim': u_out,
            'vEgo_kph': v_ego_kph,
        })

    print(f"검증 대상 route 행: {len(results)}건 (accel_limit={accel} m/s^2)")

    # 1) patched_sim vs published 정합성 (재현 신뢰도 체크)
    diffs = [abs(x['patched_sim'] - x['published']) for x in results]
    print(f"\n[재현 신뢰도] patched_sim vs 실제 published desiredSpeed 오차: "
          f"mean={np.mean(diffs):.2f}kph max={np.max(diffs):.2f}kph "
          f"(median={np.median(diffs):.2f}kph)")

    # 2) patched vs unpatched 최저점 비교 (147차 패치가 실제로 무엇을 바꿨는지)
    min_patched = min(results, key=lambda x: x['patched_sim'])
    min_unpatched = min(results, key=lambda x: x['unpatched_sim'])
    print(f"\n[패치 효과] patched_sim 최저값: {min_patched['patched_sim']:.1f}kph @t={min_patched['t']:.2f}")
    print(f"            unpatched_sim 최저값: {min_unpatched['unpatched_sim']:.1f}kph @t={min_unpatched['t']:.2f}")

    # 3) 프레임간 낙차(오탐 시 급브레이크 여부) 체크 -- patched_sim 시퀀스
    max_drop = 0.0
    max_drop_t = None
    for i in range(1, len(results)):
        drop = results[i-1]['patched_sim'] - results[i]['patched_sim']
        if drop > max_drop:
            max_drop = drop
            max_drop_t = results[i]['t']
    print(f"\n[급락 체크] patched_sim 프레임간 최대 낙차: {max_drop:.2f}kph @t={max_drop_t}")

    # 4) unpatched 대비 patched가 실제로 더 낮게(=더 일찍 감속) 잡은 구간 요약
    big_diff = [x for x in results if x['unpatched_sim'] - x['patched_sim'] > 10.0]
    print(f"\n[패치 개입 구간] unpatched보다 10kph 이상 낮게 잡힌 행: {len(big_diff)}건"
          f" / 전체 {len(results)}건")
    if big_diff:
        t_lo = min(x['t'] for x in big_diff)
        t_hi = max(x['t'] for x in big_diff)
        print(f"  시간범위: t={t_lo:.2f} ~ {t_hi:.2f}")

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 replay_route_full_pipeline.py <route.csv> [--accel 0.70]")
        sys.exit(1)
    csv_path = sys.argv[1]
    accel = 0.70
    if "--accel" in sys.argv:
        accel = float(sys.argv[sys.argv.index("--accel") + 1])
    run_replay(csv_path, accel=accel)
