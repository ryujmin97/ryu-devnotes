import sys, csv, os
from collections import deque
sys.path.insert(0, '/home/claude/devnotes/toolkit')
from analysis_helpers import load_csv

# --- 26차 패치 설계값 (WIP.md 기술 내용 그대로 재현) ---
# 28차: GATE_CAUTION/GATE_DANGER는 환경변수로 override 가능하게 함
# (문턱 재설계 스윕을 파일 수정 없이 반복 실행하기 위함, 29차)
VISION_CLOSING_RATE_TAU            = 1.0   # s, 기존 저역통과 시정수
VISION_CLOSING_RATE_MIN_TIME       = 0.5   # s
LEAD_ACQ_LOSS_GRACE_TIME           = 0.5   # s
VISION_CLOSING_RATE_MAX_PLAUSIBLE  = 30.0  # m/s, 클램프 상한(접근 방향만)
VISION_CLOSING_RATE_MEDIAN_WINDOW  = 3     # frames
VISION_CLOSING_RATE_GATE_CAUTION   = float(os.environ.get('SIM_GATE_CAUTION', -5.5))  # m/s
VISION_CLOSING_RATE_GATE_DANGER    = float(os.environ.get('SIM_GATE_DANGER', -10.0))  # m/s


def _f(row, key, default=None):
    v = row.get(key, '')
    if v in (None, ''):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _b(row, key, default=False):
    v = row.get(key, '')
    if v in (None, ''):
        return default
    return str(v).strip().lower() in ('1', 'true', 't', 'yes')


def frac_rate_of(filtered_rate):
    """CAUTION(-5.5)에서 0, DANGER(-10.0)에서 1로 선형 정규화, [0,1] 클립."""
    if filtered_rate is None:
        return 0.0
    if filtered_rate >= VISION_CLOSING_RATE_GATE_CAUTION:
        return 0.0
    if filtered_rate <= VISION_CLOSING_RATE_GATE_DANGER:
        return 1.0
    span = VISION_CLOSING_RATE_GATE_CAUTION - VISION_CLOSING_RATE_GATE_DANGER
    return (VISION_CLOSING_RATE_GATE_CAUTION - filtered_rate) / span


def simulate_route(route_csv):
    rows = load_csv(route_csv)
    by_seg = {}
    for r in rows:
        by_seg.setdefault(r.get('seg'), []).append(r)
    for seg in by_seg:
        by_seg[seg].sort(key=lambda r: _f(r, 't'))

    out = []
    for seg, lst in by_seg.items():
        vision_dRel_prev = None
        filt_rate = 0.0
        lead_absent_timer = 0.0
        lead_acq_timer = 0.0
        prev_t = None
        window = deque(maxlen=VISION_CLOSING_RATE_MEDIAN_WINDOW)

        # raw(클램프 전)도 같이 기록해서 비교
        raw_rate_lp = 0.0  # 참고용: 클램프/중앙값 없이 raw만 저역통과한 값(27차 정성분석에서 쓴 것과 동일 기준)

        for r in lst:
            t = _f(r, 't')
            if t is None:
                continue
            dt = (t - prev_t) if prev_t is not None else 0.05
            dt = max(dt, 1e-3)
            prev_t = t

            status = _b(r, 'leadStatus')
            radar = _b(r, 'leadRadar')
            dRel = _f(r, 'leadDRel')
            vRel_raw = _f(r, 'leadVRel')  # 참고: 레이더/모델이 보고하는 원시 vRel (raw 정성분석에 쓰인 값)

            if status:
                lead_absent_timer = 0.0
            else:
                lead_absent_timer += dt

            reset = False
            if status and radar:
                reset = True
            elif not status and lead_absent_timer > LEAD_ACQ_LOSS_GRACE_TIME:
                reset = True

            if reset:
                vision_dRel_prev = None
                filt_rate = 0.0
                raw_rate_lp = 0.0
                window.clear()
                lead_acq_timer = 0.0
            elif status and not radar:
                lead_acq_timer += dt
                if vision_dRel_prev is not None and dRel is not None:
                    raw_rate = (dRel - vision_dRel_prev) / dt
                    # 클램프: 접근 방향(음수)만, 비현실적으로 큰 접근율 억제
                    clamped = max(raw_rate, -VISION_CLOSING_RATE_MAX_PLAUSIBLE)
                    window.append(clamped)
                    med = sorted(window)[len(window) // 2]
                    alpha = min(max(dt / VISION_CLOSING_RATE_TAU, 0.0), 1.0)
                    filt_rate = filt_rate * (1 - alpha) + med * alpha

                    # 참고용 raw(클램프/중앙값 없는) 저역통과
                    raw_clamped_only = max(raw_rate, -VISION_CLOSING_RATE_MAX_PLAUSIBLE)
                    raw_rate_lp = raw_rate_lp * (1 - alpha) + raw_clamped_only * alpha
                if dRel is not None:
                    vision_dRel_prev = dRel
            # blip(grace 이내 유실)은 freeze -- 아무것도 갱신 안 함

            active = status and not radar and lead_acq_timer >= VISION_CLOSING_RATE_MIN_TIME
            fr = frac_rate_of(filt_rate) if active else 0.0

            out.append({
                't': t, 'seg': seg, 'leadStatus': status, 'leadRadar': radar,
                'leadDRel': dRel, 'leadVRel_raw': vRel_raw,
                'lead_acq_timer': round(lead_acq_timer, 3),
                'filt_rate': round(filt_rate, 3),
                'raw_rate_lp_noclamp_nomedian': round(raw_rate_lp, 3),
                'frac_rate': round(fr, 3),
                'gate_active': active,
            })
    return out


if __name__ == '__main__':
    route_csv = sys.argv[1] if len(sys.argv) > 1 else '/home/claude/work/route.csv'
    t_lo = float(sys.argv[2]) if len(sys.argv) > 2 else None
    t_hi = float(sys.argv[3]) if len(sys.argv) > 3 else None

    out = simulate_route(route_csv)
    by_seg = {}
    for r in out:
        by_seg.setdefault(r['seg'], []).append(r)

    for seg, lst in by_seg.items():
        max_fr = max(r['frac_rate'] for r in lst)
        min_filt = min(r['filt_rate'] for r in lst)
        print(f"=== seg={seg} rows={len(lst)} max_frac_rate={max_fr:.3f} min_filt_rate={min_filt:.3f} ===")

    print()
    print(f"{'t':>10} {'seg':>4} {'status':>6} {'radar':>5} {'dRel':>7} {'vRel_raw':>9} "
          f"{'acq_t':>6} {'filt_rate':>9} {'raw_lp':>8} {'frac':>6} {'active':>6}")
    for r in out:
        if t_lo is not None and not (t_lo <= r['t'] <= t_hi):
            continue
        print(f"{r['t']:>10.3f} {r['seg'][-2:]:>4} {str(r['leadStatus']):>6} {str(r['leadRadar']):>5} "
              f"{str(r['leadDRel']):>7} {str(r['leadVRel_raw']):>9} {r['lead_acq_timer']:>6.2f} "
              f"{r['filt_rate']:>9.3f} {r['raw_rate_lp_noclamp_nomedian']:>8.3f} {r['frac_rate']:>6.3f} "
              f"{str(r['gate_active']):>6}")
