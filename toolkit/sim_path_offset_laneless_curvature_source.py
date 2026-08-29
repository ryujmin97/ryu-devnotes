#!/usr/bin/env python3
"""
140차: controlsd.py state_control()의 curvature 소스 선택 분기
("use_mpc_curvature = lanefull_mode_enabled or self._path_offset_active")
가 (a) PathOffset==0일 때 기존 동작과 100% 동일하고 (b) PathOffset!=0일 때만
레인리스에서 MPC 곡률(lat_plan.curvatures, PathOffset 반영됨)로 전환되며
(c) lat_plan.curvatures가 비어있을 때 안전하게 폴백하는지를 로직단위로
검증하는 합성 시뮬레이션.

141차: 140차 패치 리뷰에서 "len(curvatures)==0 폴백만으로는 배열은
채워졌지만 아직 유효하지 않은 MPC 해(mpcSolutionValid=False)를 걸러내지
못한다"는 지적이 있어, lateralPlan.mpcSolutionValid 체크를 레인/레인리스
공통 안전장치로 추가 -- 이 스크립트에도 mpcSolutionValid 케이스 반영.

배경: 137/138/139차에서 PathOffset이 path_xyz/MPC 레벨에는 레인리스에서도
반영되지만 controlsd.py가 레인리스에서 model_v2.action.desiredCurvature
(offset 무관, 신경망 직접출력)를 쓰기 때문에 실제 조향에는 미반영이던
문제를 발견 -- 140차에서 self._path_offset_active(Params "PathOffset"!=0)
플래그로 레인리스에서도 MPC 곡률을 쓰도록 패치. 아래 함수는
controlsd.py의 해당 분기를 리터럴 이식한 것 -- 실제 파일과 분기 구조가
달라지면 이 스크립트도 함께 갱신 필요.

의존성: 없음(표준 라이브러리만).
"""


def select_new_desired_curvature(
    lat_active: bool,
    lanefull_mode_enabled: bool,
    path_offset_active: bool,
    lat_plan_curvatures: list,
    mpc_solution_valid: bool,
    prev_curvature: float,
    mpc_curvature_value: float,
    model_action_curvature_value: float,
):
    """controlsd.py state_control()의 140/141차 패치 분기를 그대로 재현.

    실제 코드의 get_lag_adjusted_curvature/smooth_value는 값 자체가
    본 검증의 관심사가 아니므로(로직 분기 검증이 목적), MPC 경로를
    타면 mpc_curvature_value, 모델 액션 경로를 타면
    model_action_curvature_value, 폴백이면 prev_curvature를 그대로
    반환하도록 단순화했다.

    Returns: (new_desired_curvature, branch_taken: str)
    """
    use_mpc_curvature = lanefull_mode_enabled or path_offset_active

    if not lat_active:
        return prev_curvature, "latInactive"
    elif use_mpc_curvature:
        if len(lat_plan_curvatures) == 0 or not mpc_solution_valid:
            return prev_curvature, "mpcBranch_invalidFallback"
        else:
            return mpc_curvature_value, "mpcBranch_used"
    else:
        return model_action_curvature_value, "modelActionBranch"


def run_matrix():
    cases = [
        # (설명, lat_active, lanefull, offset_active, curvatures_len, mpc_valid, 기대_branch)
        ("latActive=False -> 무조건 유지 (offset/lanefull 무관)",
         False, False, True, 5, True, "latInactive"),
        ("레인모드, curvatures 있음, valid=True -> 기존과 동일(MPC)",
         True, True, False, 5, True, "mpcBranch_used"),
        ("레인모드, curvatures 없음 -> 기존과 동일(폴백)",
         True, True, False, 0, True, "mpcBranch_invalidFallback"),
        ("레인모드, curvatures 있음, valid=False -> 141차 신규: 폴백(기존엔 못 걸렀음)",
         True, True, False, 5, False, "mpcBranch_invalidFallback"),
        ("레인리스 + offset=0(기본값) -> 기존과 100% 동일(모델액션)",
         True, False, False, 5, True, "modelActionBranch"),
        ("레인리스 + offset!=0, curvatures 있음, valid=True -> 신규: MPC(offset반영) 사용",
         True, False, True, 5, True, "mpcBranch_used"),
        ("레인리스 + offset!=0, curvatures 없음(초기화 등) -> 안전 폴백",
         True, False, True, 0, True, "mpcBranch_invalidFallback"),
        ("레인리스 + offset!=0, curvatures 있음, valid=False -> 141차 신규: 폴백(무효 MPC해 차단)",
         True, False, True, 5, False, "mpcBranch_invalidFallback"),
    ]

    passed = 0
    for desc, lat_active, lanefull, offset_active, n_curv, mpc_valid, expected in cases:
        _, branch = select_new_desired_curvature(
            lat_active=lat_active,
            lanefull_mode_enabled=lanefull,
            path_offset_active=offset_active,
            lat_plan_curvatures=list(range(n_curv)),
            mpc_solution_valid=mpc_valid,
            prev_curvature=0.01,
            mpc_curvature_value=0.02,
            model_action_curvature_value=0.03,
        )
        ok = branch == expected
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}")
        print(f"       expected={expected} actual={branch}")

    print(f"\n{passed}/{len(cases)} PASS")
    return passed == len(cases)


if __name__ == "__main__":
    ok = run_matrix()
    raise SystemExit(0 if ok else 1)
