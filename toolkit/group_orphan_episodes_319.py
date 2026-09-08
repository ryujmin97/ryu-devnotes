#!/usr/bin/env python3
"""319차 신규: orphan singleton 프레임을 에피소드로 그룹화 + 계층화(stratify).

배경(§21/§22 재발방지):
317/318차 세션에서 x17seg corpus(020ea86, 20171행)의
routeOrphanSingletonCount>0 프레임(3433개)을 "232건 persistent /
84건 phase-resolved" 로 나누고, 다시 "73건 근접+이동+활성 후보"로
계층화하는 작업을 진행했으나, 그 그룹화/계층화 로직 자체를 toolkit에
저장하지 않은 채 컨테이너가 리셋되어 전부 소실됨(319차에서 재현
시도했으나 원래 수치와 불일치 확인, 재현 불가 확정).

이 스크립트는 그 재발을 막기 위해 **그룹화/계층화 기준을 코드로
명시적으로 고정**한다. 317/318차의 정확한 수치(232/84/73/316)와는
다를 수 있음 -- 이 스크립트가 새로운 기준선(baseline)이다.

그룹화 기준(episode):
- 동일 seg(route segment) 내에서
- 연속 orphan 프레임 간 시간 간격(dt) <= EPISODE_GAP_S(기본 1.0s)
  이면 같은 에피소드로 묶는다. 초과하면 새 에피소드 시작.
- (참고) 219/220차 그리드 재앵커링으로 인해 물리적으로 동일한 지점이
  아주 짧게 orphan 상태를 벗어났다 복귀하는 경우가 있을 수 있으나,
  이 스크립트는 "시간 연속성"만으로 단순화한다 -- 위상 재앵커링까지
  고려한 정교한 매칭(317차가 시도했던 방식)은 범위 밖.

계층화 기준(strata), 에피소드 단위 평균값 기준:
- near_moving_active : dist_mean <= NEAR_M(200) AND vEgo_mean > MOVING_MPS(0.5)
                        AND cruise_frac >= 0.5
- far_moving_active  : dist_mean >= FAR_M(400) AND vEgo_mean > MOVING_MPS(0.5)
                        AND cruise_frac >= 0.5
- moving_inactive    : vEgo_mean > MOVING_MPS(0.5) AND cruise_frac < 0.5
- stopped_inactive   : vEgo_mean <= MOVING_MPS(0.5) AND cruise_frac < 0.5
- other              : 위 어디에도 안 걸리는 나머지(stopped+active 등)

사용:
  python3 group_orphan_episodes_319.py --csv <x17seg_full.csv> \
      --out-episodes episodes.csv --out-summary summary.txt

CSV는 extract_log.py --with-navi-paths 로 생성된 것을 기대한다
(routeOrphanSingletonDist, vEgo, cruiseEnabled, seg, t 컬럼 필요).
"""
import argparse
import pandas as pd

EPISODE_GAP_S = 1.0
NEAR_M = 200.0
FAR_M = 400.0
MOVING_MPS = 0.5


def group_episodes(df: pd.DataFrame) -> pd.DataFrame:
    orphan = df[df['routeOrphanSingletonCount'] > 0].copy()
    orphan = orphan.sort_values(['seg', 't']).reset_index(drop=True)

    dt = orphan.groupby('seg')['t'].diff()
    new_ep = (orphan['seg'] != orphan['seg'].shift()) | dt.isna() | (dt > EPISODE_GAP_S)
    orphan['ep_id'] = new_ep.cumsum()

    agg = orphan.groupby('ep_id').agg(
        seg=('seg', 'first'),
        t0=('t', 'min'),
        t1=('t', 'max'),
        n_frames=('t', 'count'),
        dist_mean=('routeOrphanSingletonDist', 'mean'),
        dist_min=('routeOrphanSingletonDist', 'min'),
        dist_max=('routeOrphanSingletonDist', 'max'),
        vEgo_mean=('vEgo', 'mean'),
        cruise_frac=('cruiseEnabled', 'mean'),
    ).reset_index()
    agg['duration_s'] = agg['t1'] - agg['t0']

    def strat(row):
        near = row['dist_mean'] <= NEAR_M
        far = row['dist_mean'] >= FAR_M
        moving = row['vEgo_mean'] > MOVING_MPS
        active = row['cruise_frac'] >= 0.5
        if near and moving and active:
            return 'near_moving_active'
        if far and moving and active:
            return 'far_moving_active'
        if moving and not active:
            return 'moving_inactive'
        if not moving and not active:
            return 'stopped_inactive'
        return 'other'

    agg['stratum'] = agg.apply(strat, axis=1)
    return agg, orphan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True)
    ap.add_argument('--out-episodes', required=True)
    ap.add_argument('--out-summary', default=None)
    args = ap.parse_args()

    df = pd.read_csv(args.csv, low_memory=False)
    agg, orphan = group_episodes(df)
    agg.to_csv(args.out_episodes, index=False)

    lines = []
    lines.append(f"orphan frames: {len(orphan)}")
    lines.append(f"episodes: {len(agg)}")
    for s, cnt in agg['stratum'].value_counts().items():
        lines.append(f"  {s}: {cnt}")
    summary = "\n".join(lines)
    print(summary)
    if args.out_summary:
        with open(args.out_summary, 'w') as f:
            f.write(summary + "\n")


if __name__ == '__main__':
    main()
