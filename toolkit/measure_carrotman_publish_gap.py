#!/usr/bin/env python3
"""358차 계속: carrotMan 실제 발행 간격(Δt) 분포 실측.

배경(§21/§27):
358차/이번 세션이 확정한 E'(cereal/services.py의 carrotMan frequency=0
등록은 그대로 두고, 각 소비처(controlsd.py/lateral_planner.py/cruise.py/
selfdrived.py/carrot_functions.py)에서 SubMaster.recv_time['carrotMan']
기반 로컬 staleness 체크를 추가) 설계에서 마지막으로 남은 것은
CARROT_MAN_STALE_S 임계값 하나다. carrot_man.py의 20Hz Ratekeeper 루프는
이론상 50ms 주기지만, 예외 발생 시 outer try/except의 time.sleep(1)
경로(broadcast_version_info(), 40ed6d9 기준 라인 1036-1039)가 존재해
"정상 지연"과 "예외 recovery"를 구분하는 실측 분포가 필요하다.

이 스크립트는 새로운 rlog 필드나 실차 재수집 없이, extract_log.py가
이미 만드는 CSV로 바로 계산 가능하다 -- extract_log.py는 carrotMan
이벤트가 올 때만 행을 append하고(`w == "carrotMan"` 분기), 그 행의
`t` 컬럼이 곧 `evt.logMonoTime / 1e9`이므로(과거 어떤 세션의 corpus든
재사용 가능, §21) **CSV의 연속된 행 간 t 차이 자체가 carrotMan
발행/수신 간격이다.** 새 계측 필드 추가나 실차 재수집이 필요 없다.

그룹화 기준(319차 group_orphan_episodes_319.py의 groupby('seg')['t'].diff()
패턴 재사용, §21):
- 동일 seg(route segment) 경계를 넘는 diff는 실제 gap이 아니므로
  seg별로 diff를 계산하고 세그먼트 첫 행(diff=NaN)은 제외한다.

출력:
- 전체 Δt 분포: count/mean/p50/p90/p95/p99/max
- 후보 임계값(기본 0.5/1.0/1.5/2.0초)별 초과 빈도
- 상위 N개 최대 gap의 seg/시각(다음 세션 qcamera 대조용)
- "예외 recovery 서명" 근사 분류: gap을 3구간(정상<0.5s / 애매 0.5~1.5s /
  sleep(1)-suspect 1.5~2.5s / 그 이상 unknown)으로 나눠 카운트.
  주의: sleep(1)이 정확히 1.0초 고정이므로 실제 관측 gap은
  "예외 발생 프레임의 나머지 처리시간 + 1.0s + 다음 프레임 처리시간"이
  되어 1.0초보다 다소 크게 나타날 수 있다(§28 -- 이 스크립트는 분류
  기준만 제공, 원인 확정은 아님).

사용:
  python3 measure_carrotman_publish_gap.py <extract_log.py 출력 CSV> \\
      [--thresholds 0.5,1.0,1.5,2.0] [--top 20]

CSV는 extract_log.py로 생성한 것이면 --with-navi-paths 여부 무관하게
사용 가능(t/seg 컬럼만 필요).
"""
import argparse
import sys

import pandas as pd


def compute_gaps(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(['seg', 't']).reset_index(drop=True)
    dt = df.groupby('seg')['t'].diff()
    out = df.copy()
    out['dt'] = dt
    return out.dropna(subset=['dt'])


def percentile(vals, p):
    if len(vals) == 0:
        return float('nan')
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def classify(dt):
    if dt < 0.5:
        return 'normal(<0.5s)'
    elif dt < 1.5:
        return 'ambiguous(0.5~1.5s)'
    elif dt < 2.5:
        return 'sleep1_suspect(1.5~2.5s)'
    else:
        return 'unknown(>=2.5s)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('--thresholds', default='0.5,1.0,1.5,2.0')
    ap.add_argument('--top', type=int, default=20)
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    if 't' not in df.columns or 'seg' not in df.columns:
        print("ERROR: CSV에 't'/'seg' 컬럼이 없습니다. extract_log.py 출력인지 확인하세요.", file=sys.stderr)
        sys.exit(1)

    gapped = compute_gaps(df)
    dts = gapped['dt'].tolist()

    print(f"=== carrotMan 발행 간격(Δt) 실측 -- {args.csv} ===")
    print(f"총 carrotMan 행: {len(df)}, 세그먼트 수: {df['seg'].nunique()}, "
          f"유효 gap 샘플: {len(dts)} (세그먼트 첫 행 제외)")
    if not dts:
        print("gap 샘플 없음 -- 세그먼트당 carrotMan 행이 1개 이하인지 확인.")
        return

    print(f"\nmean={sum(dts)/len(dts):.4f}s  "
          f"p50={percentile(dts,50):.4f}s  p90={percentile(dts,90):.4f}s  "
          f"p95={percentile(dts,95):.4f}s  p99={percentile(dts,99):.4f}s  "
          f"max={max(dts):.4f}s")

    print("\n-- 임계값별 초과 빈도 --")
    thresholds = [float(x) for x in args.thresholds.split(',')]
    for th in thresholds:
        n = sum(1 for d in dts if d >= th)
        pct = 100.0 * n / len(dts)
        print(f"  dt >= {th:.2f}s : {n}건 ({pct:.4f}%)")

    print("\n-- 구간별 분류(예외 recovery 서명 근사) --")
    from collections import Counter
    buckets = Counter(classify(d) for d in dts)
    for k in ['normal(<0.5s)', 'ambiguous(0.5~1.5s)', 'sleep1_suspect(1.5~2.5s)', 'unknown(>=2.5s)']:
        print(f"  {k}: {buckets.get(k, 0)}건")

    print(f"\n-- 상위 {args.top}개 최대 gap (seg/t/dt, qcamera 대조용) --")
    top = gapped.sort_values('dt', ascending=False).head(args.top)
    for _, row in top.iterrows():
        print(f"  seg={row['seg']}  t={row['t']:.3f}  dt={row['dt']:.4f}s")


if __name__ == '__main__':
    main()
