#!/usr/bin/env python3
"""
[365차 신규] "고립 fine curvature spike" 원인을 heading(진행방향) 기하 레벨에서
직접 진단하고, 크기(RATIO)/지속성(PERSIST, 362~364차) 대신 "heading 변화의
국소 집중도"로 오탐/정탐을 구분하는 게이트 후보(ISOLATION)를 검증한다.

배경 (§28 순서: 증상 -> 재현조건 -> 원인 -> 검증):
- 362차가 확정한 오탐 메커니즘: route_curvature_macro_fine()의 fine 루프
  (carrot_man.py L567-575)가 macro보다 낮은(=더 급한) speed면 인접
  지점과의 정합성 확인 없이 무조건 채택한다.
- 363차/364차는 "곡률 크기 비율(RATIO)"과 "저곡률 지속 프레임 수(PERSIST)"로
  게이트를 시도했으나 둘 다 실제 급커브(R≈20~35m) 정탐을 광범위하게
  파괴해 기각됐다(FINDINGS.md 363차/364차).
- 365차는 곡률값이 아니라 naviPaths 원시좌표의 heading(진행방향) 변화
  패턴 자체를 직접 분석했다. 362차 오탐 corpus(`d1cd25bdf1` seg10/11/13)의
  두 신고 지점(t=4426.417, t=4572.215) 모두 다음 패턴을 보인다:
    - 오탐 지점 앞뒤로 여러 개(6~9개)의 10m 세그먼트가 heading 변화
      거의 0(<0.3도)으로 "완전히 평평"
    - 오탐 지점 정확히 그 위치(±1 세그먼트)에서만 heading이 6.2~6.5도
      "한 번에" 꺾인다
  -> 실제 도로는 완만하게(총 20도 안팎) continuously 휘어지는데, raw
  navi waypoint 간격이 국소적으로 불균일해(한 구간만 유독 성기게 샘플링됨)
  resample_10m_np()의 선형보간 결과 그 한 구간(vertex)에 커브 전체의
  각도변화가 통째로 집중된다. fine의 3점 윈도우(sample_fine=1, 20m 폭)가
  이 국소 집중을 "R=88~92m급 급커브"로 오인한다(calculate_curvature는
  세 점의 기하만 보고 "그 앞뒤가 얼마나 평평했는지"는 모름).

가설(ISOLATION 게이트): 오탐은 "국소 1개 세그먼트에 heading 변화가 집중"
되어 있고, 진짜 급커브(363차 corpus)는 "여러 연속 세그먼트에 heading
변화가 분산"되어 있을 것이다. 이를 다음 지표로 정량화:

    isolation_score(j) = 이 지점 순간 heading 꺾임 각도(피크) /
                          (진입 꺾임 각도 + 진출 꺾임 각도)

    여기서 j는 fine apex 지점(routeApexDist/10), h_before/h_mid/h_after는
    (j-1,j)/(j,j+1)/(j+1,j+2) 세그먼트의 heading. "진입 꺾임" = h_mid-h_before
    (j에서의 방향 전환), "진출 꺾임" = h_after-h_mid(j+1에서의 방향 전환).
    피크가 둘 중 하나에 쏠려 있으면(=반대쪽은 거의 0) isolation_score->1.0
    (전형적 vertex 아티팩트), 두 전환이 비슷한 크기로 나뉘어 있으면(=커브가
    이 구간에서도 계속 진행 중) isolation_score는 0.5에 가까워진다.

실측 결과 (본 스크립트로 산출, 세부 수치는 FINDINGS.md 365차 참고):
- 362차 오탐 corpus(new+fineTriggered 29건, 인접 윈도우 확보 가능한 것만):
  isolation_score median=0.99, th=0.90 기준 억제율 86.2%(25/29)
- 363차 급커브 corpus(routeApexSpeed<=45kph 대리 필터, 1233프레임):
  th=0.90 기준 정탐 생존율 86.6%(1068/1233)
- th=0.885~0.92 구간에서 오탐 억제율(86.2% 고정)과 정탐 생존율(84~90%)이
  "동시에" 높은 안정적 평탄부(plateau) 확인 -- RATIO/PERSIST가 보였던
  "억제 개선 없이 정탐만 붕괴하는 절벽" 구조가 이번엔 나타나지 않았다.

한계 (코드 패치 판단 전 반드시 확인 필요, §28 -- 성급한 결론 금지):
1. 오탐 표본이 29건(그나마 인접 윈도우 확보 가능한 건 얼마 안 됨)으로 작다.
   두 corpus 모두 이번 세션에서 처음 이 지표로 본 것이라 다른 corpus에서
   일반화되는지 미검증(과적합 가능성 배제 못함).
2. 정탐 필터(routeApexSpeed<=45)는 363차의 "R<30m" 기준과 정확히 같지
   않은 대리(proxy) 필터 -- routeApexSpeed는 map_turn_speed_factor 등이
   곱해진 값이라 R<30m과 1:1 대응이 아니다. 363차 원 스크립트
   (`sim_route_363_gate_sharp_curve_regression.py`)의 R 계산과 교차검증
   필요.
3. 362차 오탐 29건 중 4건(apexDist가 10m 격자에 정확히 걸치지 않는
   167.5/147.5/87.5/20.0 -- 최초 트리거 이후 접근 중 보간된 위치로 추정)은
   `apexDist/10` 반올림 인덱싱이 원래 vertex 위치와 어긋났을 가능성이 있어
   낮은 isolation_score로 나왔다 -- 최초 "new" 트리거 프레임(정수 격자에
   정확히 걸리는 시점)만 별도로 재확인 필요.
4. 실차 검증 없음, 코드 패치 없음(설계 검증 단계).

입력: extract_log.py --with-navi-paths로 뽑은 route CSV(naviPaths/
routeApexDist/routeApexSpeed/routeApexMode/routeApexFineTriggered 컬럼 필요).

사용:
    python3 sim_route_365_heading_isolation_gate.py \
        --false-positive-csv corpus362_seg10.csv corpus362_seg11.csv corpus362_seg13.csv \
        --true-positive-csv corpus363_seg12-16.csv \
        [--tp-speed-max 45.0] [--thresholds 0.80,0.85,0.90,0.95]
"""
import argparse
import csv
import math


# carrot_man.py L494-512 calculate_curvature() verbatim 포팅(§27) --
# 이 스크립트는 곡률값 자체보다 heading을 더 많이 쓰지만, 363차/364차
# 스크립트와 동일 기준으로 R(반경)도 함께 낼 수 있도록 유지.
def calculate_curvature(p1, p2, p3):
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cross_product = v1[0] * v2[1] - v1[1] * v2[0]
    len_v1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len_v2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if len_v1 * len_v2 == 0:
        return 0.0
    return cross_product / (len_v1 * len_v2 * len_v1)


def parse_navipaths(s):
    """extract_log.py --with-navi-paths가 기록하는 'x,y,d;x,y,d;...' 포맷 파싱.
    x,y는 gps_to_relative_xy() 이후의 국소 상대좌표(resample_10m_np 10m 격자),
    d는 경로 시작점 기준 누적거리(m, 10m 배수)."""
    pts = []
    for chunk in s.strip().rstrip(';').split(';'):
        if not chunk:
            continue
        x, y, d = chunk.split(',')
        pts.append((float(x), float(y), float(d)))
    return pts


def heading(p1, p2):
    return math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))


def isolation_score(pts, j):
    """j: fine 인덱스(예상 apex 지점, routeApexDist/10). j-1,j,j+1,j+2
    네 점(=3개 세그먼트)의 heading 전환을 본다. 반환값 1.0에 가까울수록
    "국소 1세그먼트 집중형 꺾임"(오탐 의심), 0.5에 가까울수록 "인접
    세그먼트로 고르게 분산된 꺾임"(진짜 커브 의심)."""
    if j - 1 < 0 or j + 2 >= len(pts):
        return None
    h_before = heading(pts[j - 1], pts[j])
    h_mid = heading(pts[j], pts[j + 1])
    h_after = heading(pts[j + 1], pts[j + 2])
    d_prev = h_mid - h_before
    d_next = h_after - h_mid
    peak = max(abs(d_prev), abs(d_next))
    total = abs(d_prev) + abs(d_next)
    if total <= 1e-9:
        return 0.0
    return peak / total


def load_rows(paths):
    rows = []
    for p in paths:
        with open(p, newline='') as f:
            rows.extend(list(csv.DictReader(f)))
    return rows


def collect_false_positive_scores(rows):
    """362차형 오탐 corpus: routeApexMode=='new' and routeApexFineTriggered=='True'
    인 프레임에서 apexDist/10을 fine 인덱스로 사용."""
    scores = []
    for r in rows:
        if r.get('routeApexMode') != 'new' or r.get('routeApexFineTriggered') != 'True':
            continue
        navi = r.get('naviPaths', '')
        if len(navi) < 20:
            continue
        try:
            d = float(r['routeApexDist'])
        except (KeyError, ValueError):
            continue
        pts = parse_navipaths(navi)
        j = round(d / 10.0)
        s = isolation_score(pts, j)
        if s is not None:
            scores.append((s, r.get('t'), d, r.get('routeApexSpeed')))
    return scores


def collect_true_positive_scores(rows, speed_max):
    """363차형 급커브 corpus: routeApexSpeed<=speed_max(대리 필터, 한계 2번
    참고)인 저속 프레임에서 apexDist/10을 fine 인덱스로 사용."""
    scores = []
    for r in rows:
        navi = r.get('naviPaths', '')
        if len(navi) < 20:
            continue
        try:
            d = float(r['routeApexDist'])
            spd = float(r['routeApexSpeed'])
        except (KeyError, ValueError):
            continue
        if spd <= 0 or spd > speed_max:
            continue
        pts = parse_navipaths(navi)
        j = round(d / 10.0)
        s = isolation_score(pts, j)
        if s is not None:
            scores.append((s, r.get('t'), d, spd))
    return scores


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--false-positive-csv', nargs='+', required=True,
                     help='362차형 오탐 corpus CSV(들)')
    ap.add_argument('--true-positive-csv', nargs='+', required=True,
                     help='363차형 급커브(정탐) corpus CSV(들)')
    ap.add_argument('--tp-speed-max', type=float, default=45.0,
                     help='정탐 필터: routeApexSpeed<=이 값(kph)인 프레임만 사용 (기본 45.0, 한계 2번 참고)')
    ap.add_argument('--thresholds', type=str, default='0.80,0.85,0.885,0.90,0.905,0.92,0.95,0.98',
                     help='콤마구분 isolation_score 임계값 목록')
    args = ap.parse_args()

    fp_rows = load_rows(args.false_positive_csv)
    tp_rows = load_rows(args.true_positive_csv)

    fp_scores = collect_false_positive_scores(fp_rows)
    tp_scores = collect_true_positive_scores(tp_rows, args.tp_speed_max)

    print(f"오탐(false-positive) 후보: {len(fp_scores)}건")
    print(f"정탐(true-positive) 후보: {len(tp_scores)}건 (routeApexSpeed<={args.tp_speed_max})")
    print()

    fp_vals = [s[0] for s in fp_scores]
    tp_vals = [s[0] for s in tp_scores]
    if fp_vals:
        print(f"오탐 isolation_score: min={min(fp_vals):.3f} "
              f"median={sorted(fp_vals)[len(fp_vals)//2]:.3f} max={max(fp_vals):.3f}")
    if tp_vals:
        print(f"정탐 isolation_score: min={min(tp_vals):.3f} "
              f"median={sorted(tp_vals)[len(tp_vals)//2]:.3f} max={max(tp_vals):.3f}")
    print()

    thresholds = [float(x) for x in args.thresholds.split(',')]
    print(f"{'threshold':>10} {'오탐 억제율':>12} {'정탐 생존율':>12}")
    for th in thresholds:
        supp = sum(1 for v in fp_vals if v >= th) / len(fp_vals) if fp_vals else float('nan')
        surv = sum(1 for v in tp_vals if v < th) / len(tp_vals) if tp_vals else float('nan')
        print(f"{th:>10.3f} {supp*100:>11.1f}% {surv*100:>11.1f}%")

    print()
    print("오탐 중 낮은 isolation_score(<0.90, 억제 실패) 상세:")
    for s, t, d, spd in fp_scores:
        if s < 0.90:
            print(f"  t={t} apexDist={d} apexSpeed={spd} iso={s:.3f}")


if __name__ == '__main__':
    main()
