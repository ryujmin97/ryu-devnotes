#!/usr/bin/env python3
"""
sim_route_308_orphan_real_corpus_scan.py (308차 신규)

목적: 306차가 코드+합성 재현으로 확정한 가설("route_find_clusters()의
min_points=2 게이트가 고립된 1포인트 좁은 커브를 노이즈로 오인해 제거할
수 있음", ep108)을, 사용자가 재업로드한 실차 corpus(route1~4 원본,
293/294차와 동일 zip -- a3b3373495/01742d6c1c/bf794c0073/c8d2619479)로
**최초로 실측 검증**한다.

**§21/22 기존 도구 재사용**: 에피소드 판별 로직(passed/dist_reached_
during_hold/lost_with_candidates_present/lost_no_candidate 4분류, predicted
kinematic 역산 공식)은 292차 `sim_route_292_continuity_root_cause.py::
classify_continuity_episode()`와 완전히 동일한 산식을 그대로 재사용한다
(재구현이 아니라 "에피소드를 289차 산출물에서 받는 대신 이 스크립트가
CSV를 직접 스캔해서 찾는다"는 입력 방식만 다름 -- 289차가 아직 이번 4개
route CSV로 재실행되지 않았기 때문에 독립적으로 cutoff를 탐지해야 함).
`route_find_clusters()`는 296차/306차 이식본과 동일 상수/로직.

**이 스크립트가 추가로 하는 일(306/307차에는 없던 것)**: `lost_with_
candidates_present`로 분류된 각 cutoff 프레임에 대해, CSV에 이미 존재하는
`routeCandidate0/1/2Idx/Dist/Speed`(최대 3개, 거리 오름차순)만으로
"그 프레임의 raw candidate 집합이 min_points=2 클러스터링을 통과했을지"를
근사 판정한다 -- candidate가 1개뿐이거나(candidate1Idx==-1), 2개 이상
있어도 서로 `ROUTE_CLUSTER_MAX_GAP_M`(40m) 밖에 있으면(모두 고립) "orphan
패턴"(306차 가설과 부합), 그렇지 않으면(2개 이상이 40m 이내로 뭉쳐 있음)
"non-orphan"(다른 원인 -- tolerance 불일치, 후보 자체가 실제로 사라짐 등)
으로 표시한다.

**한계**:
- CSV의 `routeCandidate0~2`는 stage0 raw 후보 중 거리 기준 최근접 3개
  까지만 기록한다(코드: `carrot_man.py` candidates 배열 앞 3개). raw
  후보가 4개 이상이면 뒤쪽 후보는 CSV에서 보이지 않아 orphan 판정이
  실제보다 낙관적일 수 있다(과소평가 방향 -- 실제로는 클러스터를 이뤘을
  후보가 CSV엔 안 보여 "orphan"으로 오분류될 가능성은 없음, 반대로 실제
  orphan인데 4번째 이후 후보가 있어서 non-orphan으로 오분류될 가능성은
  있음 -- 이 한계는 보수적 방향).
- 289차가 아직 이번 4개 real route로 재실행되지 않았으므로, 이 스크립트는
  289차의 "continuity 에피소드" 판별(자체적으로 raw apex_speed가
  ROUTE_APEX_MISS_TOLERANCE_FRAMES 넘게 끊기는지 여부)까지 포함하지
  않고, **단순화된 cutoff 탐지**(valid->invalid 전이)만 사용한다 -- 289차
  전체 파이프라인 재실행은 범위 밖(다음 세션 후보).
- qcamera 육안 대조는 이 스크립트 범위 밖 -- orphan/non-orphan 분류까지만.

사용:
    python3 sim_route_308_orphan_real_corpus_scan.py route1.csv route2.csv ...
        [--dt 0.05] [--dist-m 10.0] [--min-gap-frames 3]
"""
import argparse
import sys

import numpy as np
import pandas as pd

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_RELEASE_DIST_M = 10.0
ROUTE_CLUSTER_MIN_POINTS = 2
ROUTE_CLUSTER_MAX_GAP_M = 40.0


def load_route(path):
    df = pd.read_csv(path, low_memory=False)
    df["__src_file"] = path
    df = df.sort_values("t").reset_index(drop=True)
    return df


def find_cutoff_events(df, min_gap_frames=3):
    """raw routeApexSpeed가 유효(>0)하다가 처음으로 0/NaN이 되는 전이를
    전부 찾는다(289차의 '6프레임 이상 지속' 조건과 달리, 이 스크립트는
    간단히 valid->invalid 전이 자체를 전부 훑는다 -- 289차 파이프라인
    재실행 없이도 독립적으로 실행 가능하게 하기 위한 의도적 단순화, 위
    한계 항목 참고). min_gap_frames: 같은 cutoff를 중복 카운트하지 않기
    위해 직전 이벤트로부터 이 프레임 수 이상 떨어진 것만 신규로 취급."""
    apexSpeed = df["routeApexSpeed"].values
    valid = (~np.isnan(apexSpeed)) & (apexSpeed > 0.0)
    events = []
    last_event_idx = -10**9
    for idx in range(1, len(df)):
        if valid[idx - 1] and not valid[idx]:
            if idx - last_event_idx >= min_gap_frames:
                events.append(idx)
                last_event_idx = idx
    return events


def classify_cutoff(df, cutoff_idx, dt, dist_m):
    """292차 classify_continuity_episode()와 동일 산식(predicted kinematic
    역산)을 cutoff_idx 하나에 대해 직접 적용 -- 289차 에피소드 경계 대신
    cutoff_idx 자체에서 거꾸로 마지막 유효 프레임을 찾는다."""
    t = df["t"].values
    vEgo = df["vEgo"].values
    apexDist = df["routeApexDist"].values
    apexSpeed = df["routeApexSpeed"].values
    candCount = df["routeCandidateCount"].values if "routeCandidateCount" in df.columns else None

    last_valid_idx = None
    for idx in range(cutoff_idx - 1, max(cutoff_idx - 400, -1), -1):
        sp = apexSpeed[idx]
        if sp and sp > 0.0 and not np.isnan(sp):
            last_valid_idx = idx
            break
    if last_valid_idx is None:
        return None

    last_valid_t = t[last_valid_idx]
    last_valid_dist = apexDist[last_valid_idx]
    elapsed_s = t[cutoff_idx] - last_valid_t
    v_ego_at_cutoff = vEgo[cutoff_idx]
    predicted_at_cutoff = last_valid_dist - v_ego_at_cutoff * elapsed_s

    cand_at_cutoff = None
    if candCount is not None and not np.isnan(candCount[cutoff_idx]):
        cand_at_cutoff = int(candCount[cutoff_idx])

    if predicted_at_cutoff <= 0:
        sub_cause = "passed"
    elif predicted_at_cutoff <= dist_m:
        sub_cause = "dist_reached_during_hold"
    elif cand_at_cutoff is not None and cand_at_cutoff > 0:
        sub_cause = "lost_with_candidates_present"
    else:
        sub_cause = "lost_no_candidate"

    result = {
        "cutoff_idx": int(cutoff_idx),
        "cutoff_t": float(t[cutoff_idx]),
        "last_valid_idx": int(last_valid_idx),
        "last_valid_t": float(last_valid_t),
        "elapsed_s": float(elapsed_s),
        "last_valid_dist_m": float(last_valid_dist),
        "predicted_at_cutoff_m": float(predicted_at_cutoff),
        "candidate_count_at_cutoff": cand_at_cutoff,
        "sub_cause": sub_cause,
        "src_file": df["__src_file"].iloc[cutoff_idx],
        "seg": df["seg"].iloc[cutoff_idx] if "seg" in df.columns else None,
    }

    if sub_cause == "lost_with_candidates_present":
        result.update(_orphan_check(df, cutoff_idx))
    return result


def _orphan_check(df, idx):
    """CSV의 routeCandidate0~2 필드(거리 오름차순, 최대 3개)만으로
    306차 가설(고립 singleton이 min_points=2에 걸려 제거됨)에 부합하는지
    근사 판정한다."""
    cols = {}
    for i in range(3):
        for suffix in ("Idx", "Dist", "Speed"):
            col = f"routeCandidate{i}{suffix}"
            cols[col] = df[col].iloc[idx] if col in df.columns else None

    present = []
    for i in range(3):
        cidx = cols.get(f"routeCandidate{i}Idx")
        cdist = cols.get(f"routeCandidate{i}Dist")
        if cidx is not None and not (isinstance(cidx, float) and np.isnan(cidx)) and int(cidx) != -1:
            present.append(float(cdist))

    present.sort()
    if len(present) == 0:
        return {"orphan_pattern": None, "candidates_seen": 0, "candidate_dists": []}

    if len(present) == 1:
        orphan = True
    else:
        # 인접 거리끼리 gap이 전부 40m 넘으면(=서로 뭉치지 못함) 전부 고립
        gaps = [present[k + 1] - present[k] for k in range(len(present) - 1)]
        orphan = all(g > ROUTE_CLUSTER_MAX_GAP_M for g in gaps)

    return {
        "orphan_pattern": bool(orphan),
        "candidates_seen": len(present),
        "candidate_dists": present,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("route_csvs", nargs="+")
    ap.add_argument("--dt", type=float, default=ROUTE_SPEED_LOOP_DT)
    ap.add_argument("--dist-m", type=float, default=ROUTE_RELEASE_DIST_M)
    ap.add_argument("--min-gap-frames", type=int, default=3)
    ap.add_argument("--out-csv", default=None)
    args = ap.parse_args()

    all_rows = []
    for path in args.route_csvs:
        df = load_route(path)
        events = find_cutoff_events(df, args.min_gap_frames)
        print(f"{path}: {len(df)} rows, cutoff 이벤트 {len(events)}건 탐지")
        for cutoff_idx in events:
            r = classify_cutoff(df, cutoff_idx, args.dt, args.dist_m)
            if r is not None:
                all_rows.append(r)

    if not all_rows:
        print("cutoff 이벤트를 하나도 못 찾음 -- CSV 컬럼/데이터 확인 필요")
        sys.exit(1)

    rdf = pd.DataFrame(all_rows)
    print(f"\n=== 전체 cutoff {len(rdf)}건 sub_cause 분포 ===")
    print(rdf["sub_cause"].value_counts().to_string())

    lwcp = rdf[rdf["sub_cause"] == "lost_with_candidates_present"]
    print(f"\n=== lost_with_candidates_present {len(lwcp)}건 중 orphan 패턴 분포 ===")
    if len(lwcp) > 0:
        print(lwcp["orphan_pattern"].value_counts(dropna=False).to_string())
        print("\n상세:")
        for _, row in lwcp.iterrows():
            print(f"  {row['src_file']} seg={row['seg']} cutoff_t={row['cutoff_t']:.2f}s "
                  f"cand={row['candidate_count_at_cutoff']} orphan={row['orphan_pattern']} "
                  f"dists={row['candidate_dists']}")
    else:
        print("(해당 없음)")

    if args.out_csv:
        rdf.to_csv(args.out_csv, index=False)
        print(f"\n전체 결과 저장: {args.out_csv}")


if __name__ == "__main__":
    main()
