"""Experimental verified-input minutes model. No live imports or defaults.

Unknown membership/participation is never converted to absence. Bounds are
forecast constraints learned from earlier observations, not playing-time rules.
"""
import numpy as np
import pandas as pd


def _utc(value):
    t = pd.Timestamp(value)
    if t.tzinfo is None or pd.isna(t):
        raise ValueError('Timezone-aware evidence timestamp required')
    return t


def eligibility_at(evidence, capture, team):
    """Return eligible/ineligible/unknown; require historical publication proof."""
    capture = _utc(capture)
    if not evidence or not evidence.get('source'):
        return 'unknown'
    required = ('published_at', 'valid_from', 'valid_until')
    if any(not evidence.get(k) for k in required):
        return 'unknown'
    published, start, end = (_utc(evidence[k]) for k in required)
    if published > capture or not start <= capture < end or evidence.get('team') != team:
        return 'unknown'
    state = evidence.get('eligibility')
    return state if state in {'eligible', 'ineligible'} else 'unknown'


def verified_history(rows, capture, game_date, season_type='regular'):
    """Season labels must be source-verified, never inferred from calendar month."""
    capture = _utc(capture)
    accepted, rejected = [], []
    for row in rows:
        reason = None
        if row.get('date', '') >= game_date or _utc(row['completed_at']) >= capture:
            reason = 'not_prior'
        elif not row.get('season_verified') or not row.get('season_source') or not row.get('season_id'):
            reason = 'unverified_season'
        elif row.get('season_type') != season_type:
            reason = 'other_season_type'
        elif row.get('participation') not in {'played', 'confirmed_dnp'}:
            reason = 'unknown_participation'
        elif not np.isfinite(row['minutes']) or not 0 <= row['minutes'] <= 48:
            raise ValueError('Invalid regulation minutes')
        elif row['participation'] == 'confirmed_dnp' and row['minutes'] != 0:
            raise ValueError('Contradictory DNP minutes')
        elif row['participation'] == 'played' and row['minutes'] <= 0:
            raise ValueError('Played observation requires positive minutes')
        (rejected if reason else accepted).append(dict(row, rejection=reason) if reason else row)
    return accepted, rejected


def age_shrink(rows, prior_minutes, capture, *, half_life_days=14., prior_strength=3.):
    """Absolute evidence mass decays; normalized historical mean alone cannot expire."""
    if not (0 <= prior_minutes <= 48 and half_life_days > 0 and prior_strength > 0):
        raise ValueError('Invalid shrinkage parameters')
    capture = _utc(capture)
    ages = np.array([(capture - _utc(r['completed_at'])).total_seconds()/86400 for r in rows])
    if np.any(ages < 0):
        raise ValueError('Future history')
    mass = np.exp2(-ages/half_life_days)
    total = float(mass.sum())
    historical = float(np.average([r['minutes'] for r in rows], weights=mass)) if total else prior_minutes
    trust = total/(total + prior_strength)
    return {'raw_minutes': trust*historical + (1-trust)*prior_minutes,
            'history_weight': trust, 'evidence_mass': total, 'history_mean': historical}


def _role_label_verified(row):
    # A boolean alone is not a provenance record.
    if row.get('role_verified_pregame') is not True or not row.get('role_source'):
        return False
    try:
        return _utc(row['role_published_at']) <= _utc(row['game_started_at'])
    except (KeyError, ValueError, TypeError):
        return False


def learn_role_bounds(rows, role, *, minimum_samples=20, context='normal'):
    """Earlier verified role-labelled records only; callers cannot fit test outcomes.

    Deliberately reports insufficient support instead of inventing a generic cap.
    Role labels must have been available before the corresponding game.
    """
    if context not in {'normal', 'injury_promoted'}:
        raise ValueError('Unsupported pregame role context')
    selected = [r for r in rows if r.get('role') == role and _role_label_verified(r) and r.get('role_context', 'normal') == context]
    values = [r['minutes'] for r in selected]
    if len(values) < minimum_samples:
        raise ValueError('Insufficient earlier verified role observations for '+context+'; normal-rotation bounds not substituted')
    low, high = np.quantile(values, [.05, .95])
    return {'lower': float(low), 'upper': float(high), 'sample_n': len(values),
            'role': role, 'context': context, 'latest_date': max(r['date'] for r in selected)}


class AllocationConflict(ValueError):
    """Machine-readable conflict for offline diagnostics; never relaxes bounds."""
    def __init__(self, lower_sum, upper_sum):
        self.details = {'target':240., 'lower_sum':float(lower_sum), 'upper_sum':float(upper_sum),
                        'upper_shortfall':max(0.,240.-float(upper_sum)),
                        'lower_excess':max(0.,float(lower_sum)-240.)}
        super().__init__('Learned role bounds cannot allocate 240 minutes; no bounds relaxed')


def bounded_redistribution(means, lower, upper, uncertainty):
    """Weighted constrained projection: uncertain roles absorb more adjustment."""
    m, lo, hi, u = (np.asarray(x, dtype=float) for x in (means, lower, upper, uncertainty))
    if not (m.ndim == 1 and len(m) >= 5 and m.shape == lo.shape == hi.shape == u.shape):
        raise ValueError('Invalid rotation shape')
    if not all(np.all(np.isfinite(x)) for x in (m, lo, hi, u)) or np.any(lo < 0) or np.any(hi > 48) or np.any(lo > hi) or np.any(u <= 0):
        raise ValueError('Invalid learned bounds')
    if lo.sum() > 240 + 1e-9 or hi.sum() < 240 - 1e-9:
        raise AllocationConflict(lo.sum(), hi.sum())
    a = float(np.min((lo-m)/u))-1
    b = float(np.max((hi-m)/u))+1
    for _ in range(100):
        mid = (a+b)/2
        if np.clip(m+mid*u, lo, hi).sum() < 240:
            a = mid
        else:
            b = mid
    return np.clip(m+(a+b)/2*u, lo, hi)


def forecast_verified_team(roster, history, game_date, captured_at):
    """Require dated eligibility + current role priors and verified learned bounds.

    Unsupported inputs stop this experimental arm; baseline remains separate.
    No provider projections, retrospective availability, or test-game outcomes.
    """
    capture = _utc(captured_at)
    prior, rejected = verified_history(history, capture, game_date)
    players = []
    for p in roster:
        state = eligibility_at(p.get('eligibility_evidence'), capture, p['team'])
        if state == 'unknown':
            raise ValueError('Unverified roster eligibility: '+p['name'])
        if state == 'ineligible':
            continue
        role = p.get('role_prior', {})
        if not role.get('source') or _utc(role['published_at']) > capture or not _utc(role['valid_from']) <= capture < _utc(role['valid_until']):
            raise ValueError('Unverified current role prior: '+p['name'])
        own = [r for r in prior if tuple(r['key']) == tuple(p['key'])]
        estimate = age_shrink(own, role['minutes'], capture)
        bounds = learn_role_bounds(prior, role['role'], context=role.get('context', 'normal'))
        players.append(dict(p, **estimate, bounds=bounds))
    if len({tuple(p['key']) for p in players}) != len(players):
        raise ValueError('Duplicate player identity')
    result = bounded_redistribution([p['raw_minutes'] for p in players],
        [p['bounds']['lower'] for p in players], [p['bounds']['upper'] for p in players],
        [p['role_prior']['uncertainty'] for p in players])
    for p, value in zip(players, result):
        p['predicted_minutes'] = float(value)
    return {'players': players, 'rejected_history': rejected}
