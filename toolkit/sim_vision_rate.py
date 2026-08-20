import sys, csv
sys.path.insert(0, '/home/claude/devnotes/toolkit')
from analysis_helpers import load_csv

VISION_CLOSING_RATE_TAU = 1.0
VISION_CLOSING_RATE_MIN_TIME = 0.5
LEAD_ACQ_LOSS_GRACE_TIME = 0.5
LEAD_ACQ_TTC_DANGER = 2.5
LEAD_ACQ_TTC_CAUTION = 6.0

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

def simulate_route(route_csv, blip_reset_only=False):
    """
    blip_reset_only=True  -> OLD (pre-patch) buggy behavior: reset on any
                              leadStatus==False frame, ignore grace.
    blip_reset_only=False -> NEW (patched) behavior: grace-aware.
    Returns per-row dict with computed _vision_dRel_rate (both variants can be
    run and compared), plus event log of "blip preserved" cases.
    """
    rows = load_csv(route_csv)
    by_seg = {}
    for r in rows:
        by_seg.setdefault(r.get('seg'), []).append(r)
    for seg in by_seg:
        by_seg[seg].sort(key=lambda r: _f(r, 't'))

    out = []
    blip_events = []  # cases where a blip happened and rate was preserved (new) vs reset (old)

    for seg, lst in by_seg.items():
        vision_dRel_prev = None
        vision_dRel_rate = 0.0
        lead_absent_timer = 0.0
        prev_t = None
        # track a shadow "old" (buggy) rate too, for direct comparison
        old_rate = 0.0
        old_prev = None

        pending_blip_start_rate = None
        blip_len = 0.0

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

            # -- lead_absent_timer bookkeeping (mirrors ramp bookkeeping block) --
            if status:
                lead_absent_timer = 0.0
            else:
                lead_absent_timer += dt

            # -- NEW (patched) logic --
            if status and not radar:
                if vision_dRel_prev is not None and dRel is not None:
                    raw_rate = (dRel - vision_dRel_prev) / dt
                    alpha = min(max(dt / VISION_CLOSING_RATE_TAU, 0.0), 1.0)
                    vision_dRel_rate = vision_dRel_rate * (1 - alpha) + raw_rate * alpha
                if dRel is not None:
                    vision_dRel_prev = dRel
                if blip_len > 0:
                    blip_events.append({
                        'seg': seg, 't_resume': round(t, 3), 'blip_len_s': round(blip_len, 3),
                        'rate_before_blip': round(pending_blip_start_rate, 3) if pending_blip_start_rate is not None else None,
                        'rate_after_resume': round(vision_dRel_rate, 3),
                        'preserved': True,
                    })
                blip_len = 0.0
                pending_blip_start_rate = None
            elif status and radar:
                vision_dRel_prev = None
                vision_dRel_rate = 0.0
                blip_len = 0.0
                pending_blip_start_rate = None
            elif lead_absent_timer > LEAD_ACQ_LOSS_GRACE_TIME:
                vision_dRel_prev = None
                vision_dRel_rate = 0.0
                blip_len = 0.0
                pending_blip_start_rate = None
            else:
                # blip within grace -- freeze
                if blip_len == 0.0:
                    pending_blip_start_rate = vision_dRel_rate
                blip_len += dt

            # -- OLD (pre-patch, buggy) logic for comparison --
            if status and not radar:
                if old_prev is not None and dRel is not None:
                    raw_rate = (dRel - old_prev) / dt
                    alpha = min(max(dt / VISION_CLOSING_RATE_TAU, 0.0), 1.0)
                    old_rate = old_rate * (1 - alpha) + raw_rate * alpha
                if dRel is not None:
                    old_prev = dRel
            else:
                old_prev = None
                old_rate = 0.0

            out.append({
                't': t, 'seg': seg, 'vEgo': _f(r, 'vEgo'), 'aEgo': _f(r, 'aEgo'),
                'leadStatus': status, 'leadRadar': radar, 'leadDRel': dRel,
                'leadVRel': _f(r, 'leadVRel'),
                'vision_dRel_rate_new': round(vision_dRel_rate, 3),
                'vision_dRel_rate_old': round(old_rate, 3),
                'src': r.get('src'),
            })

    return out, blip_events

if __name__ == '__main__':
    route = sys.argv[1]
    out, blips = simulate_route(f'/home/claude/work/{route}.csv')
    print(f"=== {route}: {len(out)} rows, blip-preserved 이벤트 {len(blips)}건 ===")
    for b in blips[:40]:
        print(f"  seg={b['seg'][-2:]:>2} t_resume={b['t_resume']:.2f} blip={b['blip_len_s']:.2f}s "
              f"rate_before={b['rate_before_blip']} -> rate_after_resume={b['rate_after_resume']}")
    if len(blips) > 40:
        print(f"  ... 총 {len(blips)}건 중 40건만 표시")

    import pickle
    with open(f'/home/claude/work/{route}_sim.pkl', 'wb') as f:
        pickle.dump({'rows': out, 'blips': blips}, f)
