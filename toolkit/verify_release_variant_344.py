#!/usr/bin/env python3
"""
verify_release_variant_344.py (344차 신규)

목적: extract_log.py 실측 CSV의 routeApexMode/Dist/Speed(코드가 이미
계산해 발행한 continuity 상태 그대로 -- 재도출 아님, §27)와 vEgo를
그대로 재생해, ACTIVE 릴리즈 OR-조건을 speed_reached 포함/제거 두
가설로 각각 판정하고 실측 src=='route' 프록시(283차가 이미 문서화한
한계 있는 프록시, verify_route_release_hold_283_real_log.py 참고)와
대조한다.

344차가 이 스크립트로 실제 확인한 것: 사용자가 재업로드한
000003d4--59a8ae5773(x20seg, 20260910 재촬영본) 로그는
check_device_build.py 기준 device gitCommit=7b3dfec4(336차)+
dirty=True였고, 이 replay로도 3프레임(150ms) 이상 지속된 src=='route'
run 118개 중 19건이 dist_reached/apex_passed_or_lost가 아닌
speed_reached 단독 조건으로 정확히 그 프레임에 종료됨을 확인 --
343차(speed_reached 삭제) 패치가 이 로그 기록 시점에는 실제
반영되지 않았음을 시사한다(WIP.md 344차 참고 -- git 메타데이터만으로
판단하지 않고 텔레메트리 재생으로 교차검증한 사례).

한계(283차와 동일): src=='route'는 self.route_active 내부 상태와
100% 동일하지 않다(다른 소스에 arbitration으로 밀리는 경우도 섞임).
이 스크립트는 "release 사유 판별"에 한정해 사용하며, ACTIVE 재진입
게이트(INERT->ACTIVE)는 별도로 근사하지 않고 실측 src 전이를 그대로
따른다(release 판정과 무관한 재진입 로직까지 재구현할 필요가 없어
§27 최소변경).

사용:
    python3 verify_release_variant_344.py <extract_log.py 출력 CSV>

출력: WITH/WITHOUT speed_reached 두 가설 각각의 mismatch 건수 비율,
그리고 3프레임 이상 지속된 route-run의 종료 사유 분류(speed_reached
단독 vs dist_reached/apex_passed_or_lost).
"""
import csv
import sys

ROUTE_ACTIVE_RELEASE_MARGIN_RATIO = 1.05
ROUTE_RELEASE_DIST_M = 10.0
ROUTE_SPEED_LOOP_DT = 0.05


def replay(rows, use_speed_reached):
    route_active = False
    out = []
    for r in rows:
        apex_mode = r['routeApexMode']
        apex_dist = r['routeApexDist']
        apex_speed = r['routeApexSpeed']
        vEgo_kph = r['vEgo_kph']
        if apex_mode in ('', 'none') or apex_speed is None:
            if route_active:
                route_active = False
            out.append(route_active)
            continue
        if route_active:
            apex_passed_or_lost = apex_mode in ('passed', 'lost', 'new')
            dist_reached = apex_dist is not None and apex_dist <= ROUTE_RELEASE_DIST_M
            speed_reached = (use_speed_reached and apex_speed is not None
                              and vEgo_kph <= apex_speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO)
            if apex_passed_or_lost or dist_reached or speed_reached:
                route_active = False
        out.append(route_active)
        # ACTIVE 재진입은 근사하지 않고, 실측 src=='route' 전이를 그대로 따라간다
        # (release 판정 재현이 목적이므로 재진입 게이트 재구현 불필요, §27).
        if r['src_route'] and not route_active:
            route_active = True
            out[-1] = True
    return out


def classify_release_causes(rows):
    """3프레임 이상 지속된 src=='route' run 각각의 종료 사유를 분류한다."""
    is_route = [r['src_route'] for r in rows]
    n = len(is_route)
    total_runs = 0
    speed_reached_only = 0
    other = 0
    i = 0
    while i < n:
        if is_route[i]:
            j = i
            while j < n and is_route[j]:
                j += 1
            if j < n and (j - i) >= 3:
                total_runs += 1
                last = rows[j - 1]
                mode = last['routeApexMode']
                dist = last['routeApexDist']
                speed = last['routeApexSpeed']
                v = last['vEgo_kph']
                sr = speed is not None and v <= speed * ROUTE_ACTIVE_RELEASE_MARGIN_RATIO
                dr = dist is not None and dist <= ROUTE_RELEASE_DIST_M
                plost = mode in ('passed', 'lost', 'new')
                if sr and not dr and not plost:
                    speed_reached_only += 1
                else:
                    other += 1
            i = j
        else:
            i += 1
    return total_runs, speed_reached_only, other


def load(path):
    with open(path, newline='', encoding='utf-8') as f:
        rows_raw = list(csv.DictReader(f))
    rows = []
    for r in rows_raw:
        try:
            vEgo_kph = float(r['vEgo']) * 3.6
        except (ValueError, KeyError):
            vEgo_kph = None
        try:
            apex_dist = float(r['routeApexDist']) if r.get('routeApexDist') not in ('', 'None', None) else None
        except ValueError:
            apex_dist = None
        try:
            apex_speed = float(r['routeApexSpeed']) if r.get('routeApexSpeed') not in ('', 'None', None) else None
        except ValueError:
            apex_speed = None
        rows.append({
            't': float(r['t']),
            'routeApexMode': r['routeApexMode'],
            'routeApexDist': apex_dist,
            'routeApexSpeed': apex_speed,
            'vEgo_kph': vEgo_kph,
            'src_route': (r['src'] == 'route'),
        })
    return rows


def main(path):
    rows = load(path)

    for label, use_sr in [('WITH speed_reached (구코드 가정)', True),
                           ('WITHOUT speed_reached (343차 가정)', False)]:
        active = replay(rows, use_sr)
        mismatch = sum(1 for a, r in zip(active, rows) if a != r['src_route'])
        print(f"{label}: mismatch={mismatch} ({mismatch / len(rows) * 100:.2f}%)")

    total, sr_only, other = classify_release_causes(rows)
    print(f"\n3프레임+ 지속 src=='route' run: {total}건")
    print(f"  speed_reached 단독 종료(dist_reached/apex_passed_or_lost 아님): {sr_only}건")
    print(f"  그 외(dist_reached 또는 apex_passed_or_lost 등): {other}건")
    if sr_only > 0:
        print("  -> speed_reached 경로가 실제로 발동 중 -- 이 로그는 343차(speed_reached 삭제) 이전 코드로 기록됐을 가능성이 높음.")
    else:
        print("  -> speed_reached 단독 종료 0건 -- 343차 패치가 반영된 코드로 기록됐을 가능성과 부합.")


if __name__ == '__main__':
    main(sys.argv[1])
