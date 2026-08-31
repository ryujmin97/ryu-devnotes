#!/usr/bin/env python3
"""
182차: navi_points_active 드롭아웃("route 사전감속이 N초간 전혀 없었음")
진단 스크립트.

배경: carrotMan.naviPaths(route 폴리라인)가 좌회전 접근 구간(61초) 동안
완전히 비어있어 carrot_navi_route()가 곡률계산 자체를 스킵한 사례
(FINDINGS.md 182차, route=390.0 "제약없음" 기본값 노출)를 조사하며,
navi_points_active 상태전이가 cereal 미발행이라 rlog 재분석만으로는
"패킷단절/앱 재요청 실패/네트워크" 등 근본원인을 특정할 수 없음이
확인됐다. 이를 위해 `0001-navi-route-activity-instrumentation.patch`
(182차)로 carrotMan에 naviPointsActive/navdActive/dtRouteInactive/
routeSource 4개 필드를 신규 추가했고, 이 스크립트는 그 필드들을 CSV에서
읽어 드롭아웃 구간을 자동으로 찾아낸다.

**주의**: 이 계측은 패치 적용 이후 새로 뽑은 로그에만 유효하다. 패치
적용 전 로그(naviPointsActive/navdActive/dtRouteInactive/routeSource가
전부 capnp 기본값 False/False/0.0/"")로는 정상적으로 계속 활성 상태였던
것과 구분이 안 되므로, 이 경우 --with-navi-paths로 뽑은 CSV가 있으면
naviPaths 텍스트 비어있음 + liveRouteSpeed==390.0 조합으로 근사 추정하는
폴백 모드로 동작한다 (182차 최초 분석이 실제로 썼던 수동 방법과 동일 —
정확도는 계측 모드보다 낮음, "왜" 끊겼는지는 폴백 모드로 절대 알 수 없음).

사용:
    # 계측 패치 적용 후 로그 (권장, 정확)
    python3 check_navi_route_activity.py <route.csv> [--min-duration 5.0]

    # 계측 패치 적용 전 로그 (근사 폴백, --with-navi-paths로 뽑은 CSV 필요)
    python3 check_navi_route_activity.py <route.csv> --fallback-naviPaths

의존성: analysis_helpers.load_csv
"""
import argparse
import sys

from analysis_helpers import load_csv


def _to_bool(s):
    return str(s).strip().lower() in ("true", "1")


def _to_float(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _has_instrumentation(rows):
    """182차 계측 컬럼이 CSV에 존재하고, 실제로 True 값이 한 번이라도
    찍혔는지 확인한다. 컬럼 자체는 있어도 전부 기본값(False/0.0/"")이면
    패치 적용 전 로그일 가능성이 높다 (또는 온로드 내내 route가 단 한
    번도 활성화된 적이 없는 극단적 케이스 -- 후자는 report에서 별도 안내).
    """
    if not rows or "naviPointsActive" not in rows[0]:
        return False
    return any(_to_bool(r.get("naviPointsActive", "")) for r in rows)


def find_dropouts_instrumented(rows, min_duration):
    """naviPointsActive=False 연속 구간을 dtRouteInactive로 직접 확정."""
    dropouts = []
    cur = None
    for r in rows:
        active = _to_bool(r.get("naviPointsActive", ""))
        t = _to_float(r.get("t", ""))
        if not active:
            if cur is None:
                cur = {
                    "t_start": t,
                    "source_before": r.get("routeSource", ""),
                    "route_speeds": [],
                    "v_egos": [],
                }
            cur["t_end"] = t
            cur["dt_route_inactive_last"] = _to_float(r.get("dtRouteInactive", ""))
            rs = r.get("liveRouteSpeed", "")
            if rs != "":
                cur["route_speeds"].append(_to_float(rs))
            ve = r.get("vEgo", "")
            if ve != "":
                cur["v_egos"].append(_to_float(ve) * 3.6)
        else:
            if cur is not None:
                dropouts.append(cur)
                cur = None
    if cur is not None:
        dropouts.append(cur)

    out = []
    for d in dropouts:
        dur = d["dt_route_inactive_last"] if d["dt_route_inactive_last"] > 0 else (d["t_end"] - d["t_start"])
        if dur < min_duration:
            continue
        out.append({
            "t_start": d["t_start"],
            "t_end": d["t_end"],
            "duration_s": round(dur, 2),
            "route_source_before_dropout": d["source_before"] or "(없음 -- 온로드 내내 한 번도 활성화 안 됨)",
            "route_speed_all_390": (len(d["route_speeds"]) > 0 and all(abs(v - 390.0) < 0.5 for v in d["route_speeds"])),
            "v_ego_kph_range": (round(min(d["v_egos"]), 1), round(max(d["v_egos"]), 1)) if d["v_egos"] else None,
        })
    return out


def find_dropouts_fallback(rows, min_duration):
    """계측 패치 적용 전 로그용 근사 폴백. naviPaths 텍스트가 비어있고
    liveRouteSpeed==390.0(제약없음 기본값)인 연속 구간을 드롭아웃으로
    추정한다. --with-navi-paths로 뽑지 않은 CSV는 naviPaths 컬럼 자체가
    없어 사용 불가.
    """
    if not rows or "naviPaths" not in rows[0]:
        print("경고: naviPaths 컬럼이 없습니다. extract_log.py --with-navi-paths로 재추출하세요.",
              file=sys.stderr)
        return []

    dropouts = []
    cur = None
    for r in rows:
        empty_paths = (r.get("naviPaths", "") == "")
        rs = r.get("liveRouteSpeed", "")
        is_default = (rs != "" and abs(_to_float(rs) - 390.0) < 0.5)
        t = _to_float(r.get("t", ""))
        suspect = empty_paths and is_default
        if suspect:
            if cur is None:
                cur = {"t_start": t}
            cur["t_end"] = t
        else:
            if cur is not None:
                dropouts.append(cur)
                cur = None
    if cur is not None:
        dropouts.append(cur)

    out = []
    for d in dropouts:
        dur = d["t_end"] - d["t_start"]
        if dur < min_duration:
            continue
        out.append({
            "t_start": d["t_start"],
            "t_end": d["t_end"],
            "duration_s": round(dur, 2),
            "route_source_before_dropout": "(폴백 모드 -- 알 수 없음, 계측 패치 적용 후 재확인 필요)",
            "route_speed_all_390": True,
            "v_ego_kph_range": None,
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path")
    ap.add_argument("--min-duration", type=float, default=3.0,
                     help="이 초 미만 드롭아웃은 노이즈로 간주해 무시 (기본 3.0s)")
    ap.add_argument("--fallback-naviPaths", action="store_true",
                     help="182차 계측 패치 적용 전 로그용 근사 모드 강제 사용 (--with-navi-paths CSV 필요)")
    args = ap.parse_args()

    rows = load_csv(args.csv_path)
    if not rows:
        print("CSV가 비어있습니다.")
        return

    instrumented = (not args.fallback_naviPaths) and _has_instrumentation(rows)

    if instrumented:
        print("[모드] 182차 계측 필드(naviPointsActive 등) 사용 -- 정확한 드롭아웃 확정")
        dropouts = find_dropouts_instrumented(rows, args.min_duration)
    else:
        if args.fallback_naviPaths:
            print("[모드] 강제 폴백(naviPaths 휴리스틱) -- 근사치, 원인규명 불가")
        else:
            print("[모드] 계측 필드 없음/전부 기본값 -- 패치 적용 전 로그로 판단, naviPaths 휴리스틱 폴백 시도")
        dropouts = find_dropouts_fallback(rows, args.min_duration)

    if not dropouts:
        print(f"\n{args.min_duration}s 이상 지속된 route 드롭아웃 없음.")
        return

    print(f"\n총 {len(dropouts)}건의 드롭아웃 (>= {args.min_duration}s):\n")
    for i, d in enumerate(dropouts, 1):
        print(f"  [{i}] t={d['t_start']:.2f}~{d['t_end']:.2f} (지속 {d['duration_s']}초)")
        print(f"      드롭아웃 직전 마지막 route 소스: {d['route_source_before_dropout']}")
        print(f"      전 구간 route=390.0(제약없음) 고정: {d['route_speed_all_390']}")
        if d["v_ego_kph_range"]:
            print(f"      이 구간 vEgo 범위: {d['v_ego_kph_range'][0]}~{d['v_ego_kph_range'][1]} km/h")
        print()


if __name__ == "__main__":
    main()
