#!/usr/bin/env python3
"""
334차: `route_local_curve_merge()`의 오프라인 재현(offline replay) 예측이
x18seg 실측 corpus 전체(orphan-raw-path 존재 3645/3645 프레임)에서
production 텔레메트리와 정반대로 갈리는 구조적 불일치를 formalize한
diagnostic 스크립트.

배경(333차/334차 WIP 참고):
  - 333차: t=640.216295606(x18seg) 단일 프레임에서 offline replay가
    "local merge 성공"(local_used=True, orphan 클러스터 승격)을 예측했지만
    실측 routeOrphanSingletonCount/routeClusterCount는 "병합 실패"
    (local_used=False)와 일치하는 값을 보임 -- 재현 불일치 발견.
  - 334차: 이 불일치가 ws=0 경계 특이 케이스가 아니라 corpus 전체
    (orphan-raw-path 존재 3645프레임, offline 도달가능 3635프레임)에서
    구조적으로 반복됨을 확인:
      * 실측: 3645/3645건 전부 routeOrphanSingletonDist가 정확히
        10m 그리드 배수 -> 병합 성공 흔적이 단 한 건도 없음(로컬
        재계산은 2.5m 간격이므로, 병합이 실제로 발동했다면 orphan
        singleton dist가 10m 그리드에서 벗어나는 경우가 나와야 정상)
      * offline replay(동일 verbatim 함수 + CSV 복원 orphans/distances/
        relative_coords): 3635/3635건 전부 local_used=True 예측

  코드(carrot_man.py 609~725행, `route_local_curve_merge()`) 자체는
  toolkit 사본과 바이트 단위로 diff해 로직 100% 동일함을 확인했고
  (주석/331차 A-B 비교용 patch_ws_clamp 파라미터만 차이),
  입력(orphans/distances/relative_coords)도 CSV 복원값과 naviPaths
  1차pass 재현값이 완전히 일치함을 확인했다(§28 -- 코드/입력 양쪽 다
  재현 오류 후보에서 배제). 남은 유력 후보는 (a) production 런타임에만
  존재하는 값(레이스 컨디션 등) 또는 (b) 로그로 관측 불가능한 조건이며,
  현재로선 __둘 다 로그만으로는 확정 불가__(원인 미확정, §28).

이 스크립트는 그 자체로 새로운 결론을 내지 않는다 -- 지금까지 ad-hoc
bash로 확인한 parity 대조를 재사용 가능한 형태로 만들어, (a) 다른
route/corpus에서도 동일 불일치가 재현되는지, (b) 향후 계측 패치가
승인되어 `routeLocalResampleUsed`(가칭) 필드가 실측에 추가된 뒤
"코드 예측 vs 새 계측값" 자체를 직접 대조하는 데 재사용하기 위함이다
(§21 -- 신규 toolkit 작성 전 기존 도구 확인 완료, 동일 목적 도구 없음).

사용:
    python3 sim_route_334_local_merge_parity_trace.py <route.csv> [--limit N]

<route.csv>는 extract_log.py --with-navi-paths 로 뽑은 CSV
(naviPaths, routeOrphanRawPath, nRoadLimitSpeed, routeOrphanSingletonDist,
routeClusterCount, routeOrphanSingletonCount 컬럼 필요).

주의: 이 스크립트가 산출하는 "실측 local_used 추정"은 직접 계측된 값이
아니라 __10m 그리드 휴리스틱 대리(proxy)__ 다(로컬 재계산 grid=2.5m이므로
singleton dist가 10m 배수에서 벗어나면 병합 발동으로 간주). 확정적 판정이
아니므로 이 스크립트의 출력을 FINDINGS.md에 그대로 인용하지 않는다(§28) --
`self._route_local_resample_used` 직접 계측 패치(승인 대기, WIP 334차 참고)
전까지는 "정황 근거"로만 취급한다.
"""
import argparse
import csv
import math
import sys

import sim_route_322d_stateful_replay as m322
import sim_route_331_ws_negative_downstream as m331
import sim_route_332_ws_negative_real_corpus as m332

MAP_TURN_SPEED_FACTOR_DEFAULT = 1.10  # 333/334차에서 t=640.216 프레임 역산으로 확인(§28, 정확값 아님 -- factor는
                                       # 프레임마다 mapTurnSpeedFactor로 달라질 수 있어 근사치임을 각 결과에 명시).


def to_float(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def is_10m_grid(dist_m, tol=0.001):
    if dist_m is None:
        return None
    q = dist_m / 10.0
    return abs(q - round(q)) <= tol / 10.0


def trace_row(r, factor):
    """단일 CSV row에 대해 offline replay를 실행하고 실측과 비교한다.
    반환: dict(status, offline_local_used, telemetry_grid_aligned, ...)
    """
    raw = r.get("routeOrphanRawPath", "")
    if not raw:
        return None

    navi_paths = r.get("naviPaths", "")
    pts, _dists = m322.parse_navi_paths(navi_paths)
    if len(pts) < 9:
        return {"status": "skip_navipoints_lt9"}

    road_limit_speed = to_float(r.get("nRoadLimitSpeed"), 300.0) or 300.0
    candidates, clusters, orphans, distances, speeds, fine_triggered = (
        m322.recompute_full(pts, road_limit_speed, map_turn_speed_factor=factor)
    )
    if not orphans:
        return {"status": "no_orphans_offline"}

    relative_coords = m332.parse_raw_path(raw)
    curvatures_dummy = [0.0] * len(distances)
    merged_d, merged_s, merged_c, merged_ft, local_used = m331.route_local_curve_merge(
        orphans, distances, speeds, curvatures_dummy, fine_triggered,
        relative_coords, factor, road_limit_speed,
    )

    orphan_dist = to_float(r.get("routeOrphanSingletonDist"))
    telemetry_grid_aligned = is_10m_grid(orphan_dist)

    return {
        "status": "traced",
        "t": r.get("t"),
        "offline_local_used": local_used,
        "telemetry_orphan_dist": orphan_dist,
        "telemetry_grid_aligned": telemetry_grid_aligned,
        # mismatch: offline은 병합 성공(local_used=True)을 예측했는데
        # 실측 orphan dist는 여전히 10m 그리드 위(=병합 미발동 정황)
        "mismatch": bool(local_used) and bool(telemetry_grid_aligned),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_csv")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--factor", type=float, default=MAP_TURN_SPEED_FACTOR_DEFAULT)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.route_csv, newline="")))
    if args.limit:
        rows = rows[: args.limit]

    n_orphan_rows = 0
    n_traced = 0
    n_mismatch = 0
    n_offline_local_used_true = 0
    n_telemetry_grid_aligned = 0
    first_examples = []

    for r in rows:
        result = trace_row(r, args.factor)
        if result is None:
            continue
        n_orphan_rows += 1
        if result["status"] != "traced":
            continue
        n_traced += 1
        if result["offline_local_used"]:
            n_offline_local_used_true += 1
        if result["telemetry_grid_aligned"]:
            n_telemetry_grid_aligned += 1
        if result["mismatch"]:
            n_mismatch += 1
            if len(first_examples) < 10:
                first_examples.append(result)

    print(f"orphan-raw-path 존재 row: {n_orphan_rows}")
    print(f"offline replay 도달(traced): {n_traced}")
    print(f"offline local_used=True 예측: {n_offline_local_used_true}")
    print(f"실측 orphan dist가 10m 그리드 위(=병합 미발동 정황): {n_telemetry_grid_aligned}")
    print(f"불일치(offline 성공예측 & 실측은 미발동 정황) 건수: {n_mismatch} "
          f"({(n_mismatch/n_traced*100):.1f}%)" if n_traced else "")
    print()
    print("첫 10건 예시(t, offline_local_used, telemetry_orphan_dist):")
    for ex in first_examples:
        print(f"  t={ex['t']}  offline_local_used={ex['offline_local_used']}  "
              f"telemetry_orphan_dist={ex['telemetry_orphan_dist']}")

    print()
    print("주의: telemetry_grid_aligned는 10m-grid 휴리스틱 proxy이며 직접 계측이 "
          "아니다(§28, 스크립트 상단 docstring 참고). 이 출력만으로 FINDINGS.md를 "
          "갱신하지 말 것 -- self._route_local_resample_used 계측 패치(승인 대기) "
          "적용 후 재검증 필요.")


if __name__ == "__main__":
    main()
