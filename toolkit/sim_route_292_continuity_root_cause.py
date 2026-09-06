#!/usr/bin/env python3
"""
sim_route_292_continuity_root_cause.py (292차 신규)

목적: 289차가 "RELEASE margin 1.1->1.05 what-if"에서 연장 30건 중 28건을
뭉뚱그려 분류한 `apex_lost_or_new(continuity)` 원인을, production
`carrot_man.py::_route_cluster_continuity_step()` (735~808행)의 실제
분기(matched/held/passed/lost/none)에 최대한 가깝게 재구성해 세분화한다.

**289차 방법과의 차이(§28 -- 추측만으로 원인 확정하지 않는다)**:

289차 `simulate_new_release()`는 "raw apex_speed가 6프레임 넘게 연속으로
0/NaN이면 continuity 원인"이라는 단일 규칙만 썼다. 그러나 실제 production
코드를 읽어보면 이 하나의 라벨 안에 서로 매우 다른 의미의 4가지 경로가
섞여 있다(carrot_man.py 781~808행):

1. **"passed"** (predicted_dist=locked_dist-vEgo*dt <= 0): apex를 이미
   물리적으로 통과했다고 예측되는 경우 -- miss_frames 카운트와 무관하게
   그 프레임에서 즉시 lock 해제. 새 후보(cluster)가 있으면 그걸로 재탐색
   (mode="passed"이지만 apex_speed는 새 값으로 계속 로깅됨), 없으면
   apex_speed=None -> 그 즉시 route_active=False(1177~1193행, margin/dist
   조건과 완전히 무관하게 그 프레임에 바로 RELEASE). **이건 버그가
   아니라 정상적인 "커브를 다 지나갔다" 완료 이벤트다.**
2. **"lost" + 새 후보 발견**: miss_frames가 ROUTE_APEX_MISS_TOLERANCE_FRAMES(6)를
   초과해 lock은 풀리지만, 같은 프레임에 새 cluster가 있으면 그걸로 즉시
   재탐색(apex_speed는 새 값). RELEASE 여부는 그 새 후보 기준 margin/dist로
   다시 판정된다 -- **거의 새로운 에피소드가 시작되는 것과 같음.**
3. **"lost" + 후보 없음(apex_speed=None)**: miss_frames 초과 + 대체 후보도
   없음 -> 그 즉시 route_active=False. **이것만이 289차가 의도한
   "진짜 continuity 소실"에 해당** -- qcamera 대조가 필요한 케이스.
4. **"held" 중 raw 값 자체는 0이 아니다**: `_route_apex_dist`는 held
   프레임에도 predicted(=locked_dist-vEgo*dt, 감쇠된 예측값)로 매 프레임
   갱신되어 CSV에 로깅된다(1196~1198행) -- 즉 289차의 "raw_speed>0이면
   유효" 판정 자체는 held 프레임을 올바르게 잡아낸다. 문제는 위 1/3이
   갈리는 지점, 즉 raw 값이 **정확히 0/None으로 찍히는 바로 그 프레임**을
   "continuity 소실"으로 뭉뚱그리면서 1(passed, 정상)과 3(진짜 소실)을
   구분하지 못한다는 것.

**이 스크립트가 하는 일**: 289차가 "continuity"로 분류한 각 에피소드에
대해, 원본 df의 raw apex_dist/apex_speed 시계열이 0/None으로 찍히기
**직전 마지막 유효 프레임**의 apex_dist와 그 시점 vEgo로
`predicted = last_valid_apex_dist - vEgo*dt`를 역산해, 0 이하로
떨어졌는지(=passed, 정상 완료) 여부를 우선 판별한다. predicted>0인데도
raw 값이 0으로 끊겼다면 그건 진짜 "lost"(위 2/3 중 하나)이고,
`routeCandidateCount`(234차부터 CSV에 존재)가 0인프레임인지 아닌지로
2(재탐색 성공, 정상)와 3(진짜 소실, qcamera 대조 필요)을 추가로 나눈다.

**한계(정직하게 명시)**:
- ROUTE_SPEED_LOOP_DT(=0.05s, carrot_man.py 50행)를 그대로 사용하지만
  CSV의 실제 프레임 간격(`t` diff)이 이와 정확히 일치하지 않을 수 있어
  ±1프레임 오차 가능.
- `routeCandidateCount`는 클러스터링(stage2) *이전* 원시 후보 개수라
  stage2 클러스터가 실제로 몇 개였는지와 정확히 같지 않을 수 있다(근사).
- 이 스크립트 단독으로는 "왜 후보가 사라졌는지"(맵 데이터 자체의 공백인지,
  클러스터링 임계값 문제인지, 실제 도로에 커브가 없어졌는지)까지는 알 수
  없다 -- 그건 qcamera 육안 대조가 필요한 영역이다(아래
  `select_qcamera_candidates()` 참고).

사용:
    python3 sim_route_292_continuity_root_cause.py \\
        sim289_margin_per_episode.csv route1.csv route2.csv ... \\
        [--dt 0.05] [--dist-m 10.0] [--top-n 8]

    (sim289_margin_per_episode.csv는 sim_route_289_margin_ab_real_log.py의
    출력 -- cause_new=="apex_lost_or_new(continuity)"인 행만 골라
    원본 df에서 재조사한다.)
"""
import argparse
import numpy as np
import pandas as pd

ROUTE_SPEED_LOOP_DT = 0.05
ROUTE_RELEASE_DIST_M = 10.0


def load_concat(paths):
    dfs = []
    for p in paths:
        df = pd.read_csv(p, low_memory=False)
        df["__src_file"] = p
        dfs.append(df)
    full = pd.concat(dfs, ignore_index=True)
    full = full.sort_values("t").reset_index(drop=True)
    return full


def classify_continuity_episode(df, t_start, t_end_old, dt, dist_m,
                                 lookahead_frames=40):
    """289차가 'apex_lost_or_new(continuity)'로 분류한 에피소드 하나를
    받아, raw 값이 끊기기 직전 마지막 유효 프레임을 찾고 predicted
    kinematic 거리로 passed/lost 여부를 재판별한다.

    반환: dict(sub_cause, last_valid_idx, last_valid_t, last_valid_dist,
                predicted_at_cutoff, candidate_count_at_cutoff,
                frames_to_zero)
    """
    t = df["t"].values
    vEgo = df["vEgo"].values
    apexDist = df["routeApexDist"].values
    apexSpeed = df["routeApexSpeed"].values
    hasCand = "routeCandidateCount" in df.columns
    candCount = df["routeCandidateCount"].values if hasCand else None

    # t_end_old 근방(에피소드가 원래 289차 기준으로 끝난 시각)부터
    # 시작해서, raw apex_speed가 처음으로 0/NaN이 되는 프레임(cutoff)과
    # 그 직전 마지막 유효 프레임을 찾는다.
    idx0 = int(np.searchsorted(t, t_start))
    idx_end_old = int(np.searchsorted(t, t_end_old))
    n = len(df)

    last_valid_idx = None
    cutoff_idx = None
    for idx in range(idx0, min(idx_end_old + lookahead_frames, n)):
        sp = apexSpeed[idx]
        if sp and sp > 0.0 and not np.isnan(sp):
            last_valid_idx = idx
        else:
            if last_valid_idx is not None:
                cutoff_idx = idx
                break
    if cutoff_idx is None or last_valid_idx is None:
        return {"sub_cause": "UNRESOLVED(no clean cutoff found in window)",
                "last_valid_idx": last_valid_idx, "cutoff_idx": cutoff_idx}

    last_valid_t = t[last_valid_idx]
    last_valid_dist = apexDist[last_valid_idx]
    # cutoff까지 흐른 실제 시간(프레임 간격이 정확히 dt가 아닐 수 있으므로
    # t 배열의 실측 시간차를 우선 사용, dt*frame_count는 sanity-check용).
    elapsed_s = t[cutoff_idx] - last_valid_t
    v_ego_at_cutoff = vEgo[cutoff_idx]
    predicted_at_cutoff = last_valid_dist - v_ego_at_cutoff * elapsed_s
    frames_to_zero = cutoff_idx - last_valid_idx

    cand_at_cutoff = int(candCount[cutoff_idx]) if hasCand and not np.isnan(candCount[cutoff_idx]) else None

    if predicted_at_cutoff <= 0:
        sub_cause = "passed(정상 완료 -- apex 물리적 통과, continuity 결함 아님)"
    elif predicted_at_cutoff <= dist_m:
        sub_cause = "dist_reached_during_hold(정상 -- 감쇠된 예측거리가 RELEASE_DIST_M 이내로 진입)"
    elif cand_at_cutoff is not None and cand_at_cutoff > 0:
        sub_cause = "lost_with_candidates_present(요주의 -- 후보는 있었는데 매칭 실패, 클러스터링/tolerance 재검토 필요)"
    else:
        sub_cause = "lost_no_candidate(진짜 소실 -- qcamera 대조 권장)"

    return {
        "sub_cause": sub_cause,
        "last_valid_idx": int(last_valid_idx),
        "last_valid_t": float(last_valid_t),
        "cutoff_idx": int(cutoff_idx),
        "cutoff_t": float(t[cutoff_idx]),
        "last_valid_dist_m": float(last_valid_dist),
        "predicted_at_cutoff_m": float(predicted_at_cutoff),
        "frames_to_zero": int(frames_to_zero),
        "candidate_count_at_cutoff": cand_at_cutoff,
    }


def select_qcamera_candidates(results_df, top_n):
    """'lost_no_candidate' 또는 'lost_with_candidates_present'로 분류된
    에피소드 중, qcamera 육안 대조 우선순위가 높은 것부터 top_n개를
    고른다. 우선순위: (1) lost_with_candidates_present가 lost_no_candidate
    보다 우선(클러스터링 버그 가능성이 더 구체적) (2) 같은 sub_cause 내에서는
    last_valid_dist_m이 클수록(=아직 멀리 있는 커브인데 소실됨 -> 더
    비정상적) 우선."""
    mask = results_df["sub_cause"].str.startswith("lost_")
    cand = results_df.loc[mask].copy()
    if cand.empty:
        return cand
    cand["priority"] = cand["sub_cause"].map(
        lambda s: 0 if s.startswith("lost_with_candidates_present") else 1)
    cand = cand.sort_values(["priority", "last_valid_dist_m"], ascending=[True, False])
    return cand.head(top_n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sim289_per_episode_csv")
    ap.add_argument("route_csvs", nargs="+")
    ap.add_argument("--dt", type=float, default=ROUTE_SPEED_LOOP_DT)
    ap.add_argument("--dist-m", type=float, default=ROUTE_RELEASE_DIST_M)
    ap.add_argument("--top-n", type=int, default=8)
    ap.add_argument("--out-prefix", default="sim292_continuity_breakdown")
    args = ap.parse_args()

    sim289 = pd.read_csv(args.sim289_per_episode_csv)
    cont_eps = sim289[sim289["cause_new"] == "apex_lost_or_new(continuity)"].copy()
    print(f"289차 기준 'continuity' 분류 에피소드: {len(cont_eps)}건 -- 재분류 시작")

    df = load_concat(args.route_csvs)

    rows = []
    for _, ep in cont_eps.iterrows():
        r = classify_continuity_episode(df, ep["t_start"], ep["t_end_old"],
                                         args.dt, args.dist_m)
        r["ep"] = ep["ep"]
        r["t_start"] = ep["t_start"]
        r["t_end_old"] = ep["t_end_old"]
        rows.append(r)
    rdf = pd.DataFrame(rows)
    rdf.to_csv(f"{args.out_prefix}.csv", index=False)

    print("\n세부원인 분포:")
    print(rdf["sub_cause"].value_counts().to_string())

    qc = select_qcamera_candidates(rdf, args.top_n)
    if not qc.empty:
        qc.to_csv(f"{args.out_prefix}_qcamera_candidates.csv", index=False)
        print(f"\nqcamera 육안 대조 우선순위 상위 {len(qc)}건 "
              f"({args.out_prefix}_qcamera_candidates.csv):")
        for _, row in qc.iterrows():
            print(f"  ep={row['ep']}  cutoff_t={row['cutoff_t']:.2f}s  "
                  f"sub_cause={row['sub_cause']}  "
                  f"last_valid_dist={row['last_valid_dist_m']:.1f}m")
        print("\n다음 단계: 위 cutoff_t 시각대를 extract_dashcam_frames.py로 "
              "qcamera.ts에서 전후 프레임 추출 -> 실제로 커브가 사라졌는지, "
              "candidate가 다른 커브로 전환된 것인지 육안 확인.")
    else:
        print("\nqcamera 대조가 필요한 'lost_*' 에피소드 없음 -- 전부 "
              "passed/dist_reached_during_hold로 재분류(정상 동작).")


# ---------------------------------------------------------------------------
# self-test (§27/§28 관례 -- 실제 corpus 없이도 로직 자체를 검증)
# ---------------------------------------------------------------------------
def _self_test():
    import io

    rows = []
    t = 0.0
    dt = 0.05

    def add(vEgo, apexDist, apexSpeed, candCount):
        nonlocal t
        rows.append({"t": t, "vEgo": vEgo, "routeApexDist": apexDist,
                      "routeApexSpeed": apexSpeed, "routeCandidateCount": candCount,
                      "src": "route"})
        t += dt

    # 시나리오 A: "passed" -- apex_dist가 자연 감쇠하다 0 근처에서 신호가
    # 끊김(마지막 유효 dist=1.0m, vEgo=20m/s, elapsed 1프레임=0.05s ->
    # predicted=1.0-20*0.05=0.0 -> passed 판정 기대).
    for d in [3.0, 2.0, 1.0]:
        add(20.0, d, 40.0, 1)
    add(20.0, 0.0, 0.0, 0)  # cutoff frame

    # 시나리오 B: "lost_no_candidate" -- 멀리(80m) 있는데 갑자기 후보 소실,
    # candidate count도 0.
    for d in [90.0, 85.0, 80.0]:
        add(15.0, d, 60.0, 2)
    add(15.0, 0.0, 0.0, 0)  # cutoff, candCount=0 -> lost_no_candidate 기대

    # 시나리오 C: "lost_with_candidates_present" -- 멀리 있는데 소실,
    # 그러나 candidate count>0(클러스터링/매칭 실패 의심).
    for d in [70.0, 65.0, 60.0]:
        add(15.0, d, 55.0, 3)
    add(15.0, 0.0, 0.0, 3)  # cutoff, candCount=3 -> lost_with_candidates_present 기대

    # 시나리오 D: "dist_reached_during_hold" -- 마지막 유효 dist=12m,
    # vEgo=25m/s, 1프레임 경과 -> predicted=12-25*0.05=10.75 (0보다 크고
    # dist_m=10.0보다 큼 -> 이 경우는 아직 dist_reached 아님, 여러 프레임
    # 필요) -- dist_m 이내로 확실히 넣기 위해 마지막 유효 dist=11.0으로 조정.
    for d in [15.0, 13.0, 11.0]:
        add(25.0, d, 45.0, 1)
    add(25.0, 0.0, 0.0, 1)  # cutoff: predicted=11-25*0.05=9.75<=10.0 -> dist_reached 기대

    df = pd.DataFrame(rows)

    episodes = [
        (0.00, 0.15, "passed"),
        (0.20, 0.35, "lost_no_candidate"),
        (0.40, 0.55, "lost_with_candidates_present"),
        (0.60, 0.75, "dist_reached_during_hold"),
    ]

    all_pass = True
    for t_start, t_end_old, expected_prefix in episodes:
        r = classify_continuity_episode(df, t_start, t_end_old, dt, 10.0)
        ok = r["sub_cause"].startswith(expected_prefix)
        all_pass &= ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] t_start={t_start:.2f} expected~'{expected_prefix}' "
              f"got='{r['sub_cause']}' predicted={r.get('predicted_at_cutoff_m')}")

    print(f"\nself-test {'ALL PASS' if all_pass else 'SOME FAILED'}")
    return all_pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        ok = _self_test()
        sys.exit(0 if ok else 1)
    main()
