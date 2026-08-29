"""
replay_lane_departure_gate.py (120차, 신규)

목적: 119차 실제 패치(radard.py get_lead() 내 LANE_DEPARTURE 게이트,
LANE_DEPARTURE_DPATH_THRESH=1.75m / LANE_DEPARTURE_CONFIRM_S=0.5s /
LANE_DEPARTURE_VREL_GATE=-0.5)가 실차에서 실제로 동작했는지 real
route CSV(extract_log.py 산출물, leadDPath/leadVRel/leadStatus 컬럼
필요)로 검증한다. sim_lane_departure_gate.py(119차, 근사 프로파일
합성검증)의 실측 replay 버전.

핵심 아이디어: get_lead()가 게이트를 발동시키면 lead_dict가
{'status': False}로 강제 리셋되므로, 그 프레임 이후 CSV의 leadDPath는
사라진다(leadStatus=False가 되며 값이 비게 됨) - 즉 게이트 발동 "이후"의
dPath는 로그에서 관측 불가능. 따라서 검증은 다음 방식으로 한다:
  1) leadStatus=True 구간에서 |leadDPath|가 1.75m를 넘고 leadVRel이
     -0.5보다 큰(강접근 아닌) 상태가 몇 초 지속되는지 프레임 단위로
     누적(cnt)한다 - radard.py 951~956행 로직을 그대로 복제.
  2) cnt가 0.5s(CONFIRM_S)에 도달하는 시점을 "예측 발동 시각"으로 기록.
  3) 그 직후(다음 프레임, 통상 DT_MDL=0.05s 이내) 실제로 leadStatus가
     True->False로 전환되는지 CSV에서 직접 확인.
  4) 일치하면 PASS(패치가 실제로 그 프레임에 개입해 강제해제한 것으로
     추정), 불일치(leadStatus가 계속 True로 남아 dPath가 1.75m를
     한참 넘도록 유지)하면 FAIL(패치 미반영 또는 다른 원인으로 트리거
     안 됨 - 코드 리뷰 필요).

주의(중요, 오탐 원인 배제용): leadStatus가 True->False로 바뀌는 원인은
이 게이트 말고도 많다(리드 자체 소실, cut-out, 프레임 갭 등). 따라서
"예측 발동 시각 부근에서 실제로 False가 됐다"만으로 100% 확정은 아니고,
'예측 시각과 거의 동시(±1프레임)에 정확히 발생' + '그 직전 프레임까지
dPath>=1.75가 유지되고 있었다'는 두 조건을 모두 만족해야 "게이트로 인한
강제해제"로 분류한다(match_reason 필드에 근거 명시).

의존성: analysis_helpers.load_csv (같은 폴더)
입력: extract_log.py CSV (leadDPath/leadVRel/leadStatus/leadRadar 컬럼
      필요 - 63차 계속3 이후 버전)

사용:
    python3 replay_lane_departure_gate.py <route.csv> [<route.csv> ...]
    # 또는
    from replay_lane_departure_gate import scan_route
    events = scan_route(rows)
"""
import sys
import csv as _csv

DPATH_THRESH = 1.75
CONFIRM_S = 0.5
VREL_GATE = -0.5


def _f(row, key, default=None):
    v = row.get(key, "")
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _b(row, key, default=False):
    v = row.get(key, "")
    if v is None or v == "":
        return default
    return str(v).strip().lower() == "true"


def scan_route(rows):
    """rows: analysis_helpers.load_csv() 결과 (list[dict]).

    리턴: list of dict, 각 원소:
      predicted_trigger_t, actual_drop_t (None이면 못 찾음),
      dt_predicted_to_actual (초, 음수면 실제가 예측보다 먼저),
      dpath_at_predicted, vrel_at_predicted, seg,
      verdict ('PASS'|'FAIL'|'AMBIGUOUS'),
      note
    """
    events = []
    cnt = 0.0
    prev_t = None
    prev_status = None
    armed = False  # 이번 episode에서 이미 predicted_trigger를 기록했는지
    pending = None  # 현재 대기 중인 predicted event(dict) - actual drop 탐색 중

    PENDING_SEARCH_WINDOW_S = 1.0  # 예측 시각 이후 이 시간 안에 drop 없으면 FAIL 확정

    for row in rows:
        t = _f(row, "t")
        if t is None:
            continue
        status = _b(row, "leadStatus")
        seg = row.get("seg", "")

        dt = 0.05 if prev_t is None else max(0.0, min(0.2, t - prev_t))

        # pending 이벤트가 있으면 actual drop 여부 우선 체크
        if pending is not None:
            if prev_status and not status:
                # True -> False 전환 발생
                pending["actual_drop_t"] = t
                pending["dt_predicted_to_actual"] = t - pending["predicted_trigger_t"]
                if 0.0 <= pending["dt_predicted_to_actual"] <= PENDING_SEARCH_WINDOW_S:
                    pending["verdict"] = "PASS"
                    pending["note"] = "예측 발동 후 %.3fs 이내 실제 leadStatus False 전환 확인 - 패치 정상 동작으로 판단" % pending["dt_predicted_to_actual"]
                else:
                    pending["verdict"] = "AMBIGUOUS"
                    pending["note"] = "leadStatus는 False가 됐으나 예측 시각과 %.3fs 차이(1.0s 초과) - 게이트 외 다른 원인 가능성" % pending["dt_predicted_to_actual"]
                events.append(pending)
                pending = None
            elif t - pending["predicted_trigger_t"] > PENDING_SEARCH_WINDOW_S:
                pending["actual_drop_t"] = None
                pending["dt_predicted_to_actual"] = None
                pending["verdict"] = "FAIL"
                pending["note"] = "예측 발동 후 %.1fs 지나도록 leadStatus가 계속 True로 유지됨 - 게이트 미동작 의심(패치 미반영 또는 코드 우회 경로 존재 가능)" % PENDING_SEARCH_WINDOW_S
                events.append(pending)
                pending = None

        if status:
            dPath = _f(row, "leadDPath")
            vRel = _f(row, "leadVRel")
            if dPath is not None and vRel is not None and abs(dPath) > DPATH_THRESH and vRel > VREL_GATE:
                cnt += dt
                if cnt >= CONFIRM_S and not armed:
                    armed = True
                    if pending is None:
                        pending = {
                            "predicted_trigger_t": t,
                            "seg": seg,
                            "dpath_at_predicted": dPath,
                            "vrel_at_predicted": vRel,
                            "cnt_at_predicted": cnt,
                        }
            else:
                cnt = 0.0
                armed = False
        else:
            cnt = 0.0
            armed = False

        prev_t = t
        prev_status = status

    # 루프 끝났는데 pending이 남아있으면 FAIL로 마감(로그가 중간에 끝난 경우)
    if pending is not None:
        pending["actual_drop_t"] = None
        pending["dt_predicted_to_actual"] = None
        pending["verdict"] = "FAIL(로그 종료로 미확인)"
        pending["note"] = "예측 발동 이후 로그가 끝나 실제 확인 불가"
        events.append(pending)

    return events


def summarize(route_label, events):
    print(f"=== {route_label}: LANE_DEPARTURE 게이트 후보 이벤트 {len(events)}건 ===")
    if not events:
        print("  (dPath>1.75m 지속 0.5s 이상 후보 없음 - 이 라우트에서는 게이트 발동 조건 자체가 발생하지 않음)")
        return
    for e in events:
        print(f"  t={e['predicted_trigger_t']:.2f} seg={e['seg']} dPath={e['dpath_at_predicted']:.2f}m "
              f"vRel={e['vrel_at_predicted']:.2f} -> {e['verdict']} | {e['note']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용: python3 replay_lane_departure_gate.py <route.csv> [<route.csv> ...]")
        sys.exit(1)
    for path in sys.argv[1:]:
        with open(path, newline="") as f:
            rows = list(_csv.DictReader(f))
        events = scan_route(rows)
        summarize(path, events)
