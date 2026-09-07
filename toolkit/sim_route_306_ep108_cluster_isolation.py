#!/usr/bin/env python3
"""
sim_route_306_ep108_cluster_isolation.py (306차 신규)

목적: 293차/294차가 발견한 신규 하위유형 중 유일한 "lost_with_candidates_present"
사례(ep108, route4 t=4017.4, 주택가 좁은 도로/교차로 인접)의 원인을,
production 코드(`carrot_man.py`) 구조 분석만으로 확정한 메커니즘을
합성 시나리오로 직접 재현/검증한다(§28: 코드 읽기로 얻은 "구조적으로
반드시 참인 결론"과, "실측 없이는 확정 못하는 가설"을 구분).

**§21/22 기존 도구 재사용**: `route_find_clusters()`/`ContinuityState`는
296차(`sim_route_296_active_reacquire_gap.py`)가 이미 production
코드(carrot_man.py HEAD 8d481ec=305차 기준, 로직은 251차 이후 무변경)
그대로 이식해둔 것을 그대로 import해서 쓴다 -- 재구현하지 않음(§27).

**구조적으로 코드만으로 이미 확정되는 사실(실측 불필요, 수학적으로 증명됨)**:
`_route_cluster_continuity_step()`(carrot_man.py 749~822행)을 끝까지
읽으면, 반환값 `apex_speed`가 `None`이 되는 경로는 정확히 하나뿐이다 --
그 프레임의 `clusters`(=`route_find_clusters()` 결과, 즉 min_points=2
필터를 통과한 클러스터 목록)가 **완전히 비어 있는 경우**뿐이다.
`clusters`가 하나라도 있으면(`if clusters:` 812행) reset_reason이
"passed"든 "lost"든 무조건 그 클러스터의 대표점으로 즉시 재탐색에
성공해 유효한 apex_speed를 반환한다. 즉:

    293차 분류 스크립트(`sim_route_292_continuity_root_cause.py`)가
    "lost_with_candidates_present"(=cutoff 프레임에 stage0 raw
    routeCandidateCount>0인데 apex_speed가 0/None으로 찍힘)로 잡아낸
    이벤트는, 반드시 "raw candidates(len(candidates)>=1)는 있었지만
    route_find_clusters()가 그 후보(들)를 전부 min_points=2 미만이라고
    걸러내 최종 clusters=[]가 된 경우"로만 설명 가능하다 -- 이것 말고는
    수학적으로 다른 경로가 없다.

**이 스크립트가 추가로 검증하는 가설(§28 -- 아직 실측 미확정, 정황증거임)**:
그렇다면 "raw candidate는 있는데 clusters가 전부 필터링되는" 구체적인
공간 패턴은 무엇인가? 147차가 넣은 fine 곡률 서브샘플(carrot_man.py
1094~1139행, `ROUTE_CURVATURE_FINE_SAMPLE=1`, 즉 10m 그리드에서 chord
20m로 좁은 커브를 잡기 위한 보조 계산)은 "교차로 우회전처럼 좁은
코너"를 명시적으로 겨냥한 기능이다. 그런데 그런 좁은 코너는 물리적
곡선 구간 자체가 짧아(반경이 작을수록 곡률>임계치 구간의 호 길이도
짧다), distance_interval=10m 그리드로 리샘플링하면 "도로제한속도보다
느린 지점"이 **정확히 1개 그리드 포인트에만** 찍힐 수 있다 -- 그리고
route_find_clusters()의 min_points=2 게이트는 정확히 이런 "고립된
단일 포인트"를 노이즈로 간주해 제거하도록 설계돼 있다(247차 design
doc 의도 자체가 "단발성 노이즈 후보 하나만으로 apex가 성립하지
않도록"). 즉 147차가 잡으려던 신호와 251차가 걸러내려던 노이즈가
그리드 해상도 관점에서 구분 불가능한 동일한 모양(고립된 1개 포인트)을
가질 수 있다는 것이 이 가설의 핵심.

**입력**: 없음(순수 합성 시나리오, ep108 실제 corpus 데이터는 이번
세션 컨테이너에 없음 -- 293/294차가 쓴 route4 zip은 §23에 따라
devnotes에 커밋되지 않았고 재업로드되지 않으면 재현 불가).

**한계(§28, 반드시 명시)**: 이 스크립트는 "그런 메커니즘이 코드
구조상 존재하며 트리거 가능하다"는 것만 증명한다. ep108 그 프레임의
실제 raw candidates 배열(간격/거리)이 정말로 이 "고립된 1포인트"
모양이었는지는 **원본 route4 CSV 재확인 없이는 확정 불가**(다음
작업 참고).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim_route_296_active_reacquire_gap import route_find_clusters, ContinuityState, ROUTE_CLUSTER_MAX_GAP_M


def make_scenario(dip_len, dip_start_idx=20, n_points=60, grid_m=10.0,
                   above_speed=300.0, dip_speed=15.0, road_limit=50.0):
    """distance_interval=10m 그리드(production carrot_man.py 1050행
    distance=-10.0; distance_interval씩 증가 구조와 동일)를 흉내낸
    합성 speeds/distances 배열. dip_start_idx부터 dip_len개 연속
    그리드 포인트만 road_limit보다 느리게(dip_speed) 찍고, 나머지는
    전부 road_limit보다 빠르게(above_speed, "감속 불필요" 상태) 채운다
    -- 즉 "고립된 짧은 커브 하나만 있고 그 앞뒤로는 전부 직선"인
    가장 단순한 형태(ep108처럼 좁은 교차로 코너 하나만 존재하는 경우를
    최소 재현).
    """
    distances = [i * grid_m for i in range(n_points)]
    speeds = [above_speed] * n_points
    for i in range(dip_start_idx, min(dip_start_idx + dip_len, n_points)):
        speeds[i] = dip_speed
    return distances, speeds, road_limit


def run_one_frame(distances, speeds, road_limit, v_ego_ms=8.0):
    """production carrot_man.py 1206행 stage0 candidate 필터 +
    1237~1240행 stage2/stage3 호출을 그대로 재현. ContinuityState는
    매 시나리오 새로 생성(=locked apex 없는 "첫 진입" 프레임 하나만
    본다 -- ep108처럼 '이 커브에 처음 접근하는 순간'을 최소 재현).
    """
    candidates = [k for k in range(len(speeds)) if speeds[k] < road_limit]
    cand_count = len(candidates)
    clusters = route_find_clusters(candidates, distances, 2, ROUTE_CLUSTER_MAX_GAP_M)
    cs = ContinuityState()
    idx, dist, speed, mode, streak = cs.step(clusters, distances, speeds, v_ego_ms)
    return {
        "cand_count_raw": cand_count,
        "n_clusters_after_min_points_filter": len(clusters),
        "apex_mode": mode,
        "apex_speed": speed,
        "apex_lost_despite_raw_candidates": (cand_count > 0 and speed is None),
    }


def main():
    print("=" * 78)
    print("306차: '고립된 짧은 커브'(ep108류) -- min_points=2 클러스터링 게이트 재현")
    print("=" * 78)
    print(f"{'dip_len(그리드포인트)':>22} | {'물리적 길이(m)':>14} | {'raw_cand':>8} | "
          f"{'클러스터수':>8} | {'apex_mode':>10} | {'apex_speed':>10} | 손실여부")
    print("-" * 100)

    results = []
    for dip_len in range(1, 6):
        distances, speeds, road_limit = make_scenario(dip_len=dip_len)
        r = run_one_frame(distances, speeds, road_limit)
        results.append((dip_len, r))
        phys_len_m = (dip_len - 1) * 10.0  # 연속 그리드포인트 dip_len개가 덮는 거리 스팬
        lost_marker = "**LOST**" if r["apex_lost_despite_raw_candidates"] else "정상 유지"
        print(f"{dip_len:>22} | {phys_len_m:>14.0f} | {r['cand_count_raw']:>8} | "
              f"{r['n_clusters_after_min_points_filter']:>8} | {r['apex_mode']:>10} | "
              f"{str(r['apex_speed']):>10} | {lost_marker}")

    print("-" * 100)
    n_lost = sum(1 for _, r in results if r["apex_lost_despite_raw_candidates"])
    print(f"\n결과 요약: dip_len=1(그리드 포인트 1개, 즉 물리적으로 ~10m 미만짜리 "
          f"고립된 커브)일 때만 raw candidate(1개)가 있음에도 apex_speed=None "
          f"({n_lost}/{len(results)}개 시나리오에서 손실 재현).")
    print("dip_len>=2(20m+ 폭)부터는 즉시 min_points=2를 통과해 정상적으로 apex가 잡힘.")
    print()
    print("=> route_find_clusters()의 min_points=2 게이트가 '노이즈 후보 1개'와")
    print("   '실제로 존재하지만 그리드 해상도(10m)상 1개 포인트로만 찍히는 좁은")
    print("   커브(ep108류: 주택가 교차로 코너)'를 구조적으로 구분하지 못함을 확인.")

    assert results[0][1]["apex_lost_despite_raw_candidates"] is True, "self-test FAIL: dip_len=1은 손실이 재현돼야 함"
    for dip_len, r in results[1:]:
        assert r["apex_lost_despite_raw_candidates"] is False, f"self-test FAIL: dip_len={dip_len}은 손실이 없어야 함"
    print("\nself-test(실험1): 5/5 PASS (dip_len=1 손실 재현 1건 + dip_len=2~5 정상유지 4건)")

    print()
    print("=" * 78)
    print("실험2: 293/294차가 실제로 검출한 상황(이미 locked apex가 있다가 손실)까지")
    print("       재현 -- mode가 'none'이 아니라 'lost'/'passed'로 찍히는지 확인")
    print("=" * 78)
    # 293차 분류 스크립트가 "lost_with_candidates_present"로 잡으려면
    # cutoff 직전에 raw apex_speed가 유효했어야 한다(= 이미 locked apex
    # 존재). 여기서는 ContinuityState를 먼저 앞쪽의 넓은 커브(2포인트
    # 이상, 정상적으로 lock되는 커브)로 lock시킨 뒤, 그 apex가 다
    # 지나가고(predicted<=0, "passed" 경로) 다음으로 접근하는 게
    # ep108류 고립된 1포인트 커브인 시나리오를 2프레임으로 구성한다.
    distances2 = [i * 10.0 for i in range(60)]
    speeds2 = [300.0] * 60
    # 앞쪽 넓은 커브(정상, 2포인트 이상) -- 이미 지나간 것으로 취급
    speeds2[2] = 15.0
    speeds2[3] = 15.0
    # 훨씬 뒤쪽에 ep108류 고립된 1포인트 커브
    speeds2[40] = 15.0
    road_limit2 = 50.0
    cs2 = ContinuityState()
    # 프레임 A: 앞쪽 넓은 커브를 lock (idx=2, dist=20.0)
    candidates_a = [k for k in range(len(speeds2)) if speeds2[k] < road_limit2]
    clusters_a = route_find_clusters(candidates_a, distances2, 2, ROUTE_CLUSTER_MAX_GAP_M)
    idxA, distA, speedA, modeA, streakA = cs2.step(clusters_a, distances2, speeds2, v_ego_ms=8.0)
    print(f"프레임 A(초기 lock): mode={modeA}, locked_dist={distA}, locked_speed={speedA}")
    # 프레임 B: v_ego*dt를 크게 줘서 predicted<=0(=이미 통과)으로 강제 --
    # 동시에 이번 프레임 raw candidates는 뒤쪽 고립된 1포인트뿐(앞쪽
    # 커브는 지나쳐서 speeds에서 제외됐다고 가정-- 실제로는 매 프레임
    # get_path_after_distance()가 새로 자르므로 뒤로 빠진 지점은 자연히
    # 사라짐, 여기서는 그 효과를 speeds2[2],[3]을 300으로 되돌려 흉내냄).
    speeds2[2] = 300.0
    speeds2[3] = 300.0
    candidates_b = [k for k in range(len(speeds2)) if speeds2[k] < road_limit2]
    clusters_b = route_find_clusters(candidates_b, distances2, 2, ROUTE_CLUSTER_MAX_GAP_M)
    idxB, distB, speedB, modeB, streakB = cs2.step(clusters_b, distances2, speeds2, v_ego_ms=500.0)  # v_ego*dt=25.0 > locked_dist(20.0) -> predicted<=0 강제("passed" 전이)
    cand_count_b = len(candidates_b)
    print(f"프레임 B(고립 커브 접근, raw_cand={cand_count_b}): mode={modeB}, apex_speed={speedB}")
    lost_b = (cand_count_b > 0 and speedB is None)
    print(f"  -> raw candidate 존재(={cand_count_b}>0)함에도 apex_speed=None: {lost_b}")
    print("  -> 293차 분류기준(routeCandidateCount>0 + apexSpeed 0/None) 그대로 재현됨" if lost_b else "  -> 재현 실패, 시나리오 조정 필요")

    assert modeB in ("passed", "lost"), f"self-test FAIL: 프레임B mode는 passed/lost여야 함 (실제: {modeB})"
    assert lost_b is True, "self-test FAIL: 프레임B는 raw candidate 존재하는데도 손실돼야 함"
    print(f"\nself-test(실험2): PASS (mode='{modeB}' + raw_cand={cand_count_b}>0 + apex_speed=None 동시 재현 확인)")


if __name__ == "__main__":
    main()
