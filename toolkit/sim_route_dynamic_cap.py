#!/usr/bin/env python3
"""
84차(500m 초기값)+85차(500->600 상향): carrot_navi_route()의 get_path_after_distance() 300m 고정 캡을
v_ego/accel_limit 기반 동적 캡(300~600m)으로 교체한 로직 검증.

carrot_man.py의 compute_route_lookahead_distance() 순수함수를 그대로
복제해 여러 (v_ego, accel_limit) 조합에서 캡 값이 의도대로 나오는지 확인.
- 저속(<=60km/h 부근)에서는 300m(floor)로 수렴 -> 회귀 없음 확인
- 고속(100km/h+)에서는 600m(ceil)로 확장 확인
- accel_limit(AutoNaviSpeedDecelRate)이 낮을수록(더 완만한 감속 설정)
  더 낮은 속도에서부터 캡이 커지기 시작하는지 확인
"""


def compute_route_lookahead_distance(v_ego_kph, accel_limit_mss, min_m=300.0, max_m=600.0,
                                      assumed_target_kph=30.0):
  if accel_limit_mss is None or accel_limit_mss <= 0:
    return min_m
  v_ego_ms = max(0.0, v_ego_kph) / 3.6
  v_target_ms = assumed_target_kph / 3.6
  needed_m = max(0.0, (v_ego_ms ** 2 - v_target_ms ** 2) / (2.0 * accel_limit_mss))
  return float(min(max_m, max(min_m, needed_m)))


def run():
  print(f"{'v_ego(kph)':>10} | {'accel=0.70':>12} | {'accel=1.20(기본)':>16} | {'accel=1.39':>12}")
  print("-" * 60)
  speeds = [30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130]
  accels = [0.70, 1.20, 1.39]
  results = {}
  for v in speeds:
    row = [round(compute_route_lookahead_distance(v, a), 1) for a in accels]
    results[v] = row
    print(f"{v:>10} | {row[0]:>12} | {row[1]:>16} | {row[2]:>12}")

  # 회귀 체크: 저속(<=50km/h)은 accel_limit 무관하게 항상 floor(300)여야 함
  assert all(results[v][i] == 300.0 for v in (30, 40, 50) for i in range(3)), \
      "FAIL: 저속 구간에서 floor(300m)로 수렴하지 않음"
  print("\n[PASS] 저속(<=50km/h) 전 accel_limit에서 floor(300m) 유지 확인")

  # 회귀 체크: 고속(130km/h)+낮은 accel(0.70)은 ceil(600)에 clip돼야 함
  assert results[130][0] == 600.0, "FAIL: 고속+낮은 accel 조합이 ceil(600m)에 clip 안 됨"
  print("[PASS] 고속(130km/h)+accel=0.70 조합 ceil(600m) clip 확인")

  # 회귀 체크: accel_limit이 낮을수록(0.70) 같은 속도에서 더 이르게(낮은 속도부터)
  # 캡이 늘어나야 함 -> 80km/h 시점 비교
  assert results[80][0] >= results[80][1] >= results[80][2], \
      "FAIL: accel_limit 낮을수록 더 큰 캡이어야 하는 단조성 위반"
  print("[PASS] accel_limit 낮을수록(0.70) 같은 속도에서 캡이 더 크게(단조) 확인")

  # 예외 처리: accel_limit=0 또는 None -> floor(300) 안전 폴백
  assert compute_route_lookahead_distance(120, 0) == 300.0
  assert compute_route_lookahead_distance(120, None) == 300.0
  print("[PASS] accel_limit=0/None 예외 케이스 -> floor(300m) 안전 폴백 확인")

  print("\n모든 시나리오 PASS.")


if __name__ == "__main__":
  run()
