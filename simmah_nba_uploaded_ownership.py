"""Apply uploaded ownership with explicit provenance and field-only normalization."""
import re
import hashlib
import numpy as np
import pandas as pd


def normalize_targets(values, active, expected):
    values = np.asarray(values, dtype=float)
    active = np.asarray(active, dtype=bool)
    if not np.isfinite(values[active]).all() or ((values[active] < 0) | (values[active] > 100)).any():
        raise ValueError('Uploaded ownership needs finite values from 0 to 100 for every eligible player')
    target = np.where(active, values, 0.)
    total = float(target.sum())
    if total < expected * .5:
        raise ValueError('Uploaded ownership total is below half the roster total; check missing players or percentage units')
    target *= expected / total
    if (target > 100 + 1e-9).any():
        raise ValueError('Ownership normalization would exceed 100% for a player; check slate coverage')
    return target, total


def apply_displayed_ownership(pool, frame, keys, pool_keys, platform, day):
    from simmah_nba_ownership import active_players, ownership_values
    from simmah_nba_rules import rules_for
    aliases = [c for c in ('Projected Ownership %', 'OWN', 'DraftDashboard Displayed OWN') if c in frame]
    if not aliases:
        return pool, None
    # Prefer explicit numeric ownership over the display-only copy when both exist.
    column = aliases[0]
    parsed = []
    exact_keys = set()
    censored = []
    for key, value in zip(keys, frame[column]):
        text = str(value).strip().rstrip('%').strip()
        if text in ('', '...', '…', 'NA', 'N/A', 'nan'):
            parsed.append(np.nan)
        elif re.fullmatch(r'<\s*(?:\d+(?:\.\d*)?|\.\d+)', text):
            limit = float(text[1:])
            if not 0 < limit <= 100:
                raise ValueError('Invalid censored DraftDashboard ownership')
            parsed.append(limit / 2)
            censored.append(key)
        else:
            try:
                number = float(text)
            except ValueError as exc:
                raise ValueError('Invalid DraftDashboard ownership: '+str(value)) from exc
            if not np.isfinite(number) or not 0 <= number <= 100:
                raise ValueError('DraftDashboard ownership must be between 0 and 100')
            parsed.append(number)
            exact_keys.add(key)
    source = dict(zip(keys, parsed))
    raw = pd.Series([source.get(k, np.nan) for k in pool_keys], index=pool.index)
    active = active_players(pool)
    if not any(k in exact_keys for k,a in zip(pool_keys,active) if a):
        return pool, None
    missing = active & raw.isna().to_numpy()
    combined = raw.copy()
    fallback_source = None
    if missing.any():
        from simmah_nba_ownership import ownership_column
        fallback_source = ownership_column(pool)
        fallback = ownership_values(pool)
        combined.loc[missing] = fallback.loc[missing]
    expected = 100 * len(rules_for(platform=platform)['slots'])
    _, total = normalize_targets(combined, active, expected)
    names = pool.get('Name', pool['Player ID']).astype(str)
    warnings = []
    if total > expected + 50:
        warnings.append(f'Raw eligible ownership totals {total:.2f}% (above {expected+50}%); check source slate. Field targets normalized to {expected}%.')
    if missing.any():
        warnings.append(f'{int(missing.sum())} unreported ownership values use {fallback_source} as estimates: '+', '.join(names.loc[missing]))
    censored_active=[k for k,a in zip(pool_keys,active) if a and k in censored]
    if censored_active:
        warnings.append(f'{len(censored_active)} eligible censored ownership values use interval midpoints as estimates.')
    result = pool.copy(deep=True)
    result['DraftDashboard Raw Own %'] = raw
    result['DraftDashboard Projected Own %'] = combined
    meta = {'sha256':hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),'source':'DraftDashboard', 'site':platform, 'date':str(day),
            'raw_total':total, 'reported_total':float(raw[active].sum()),
            'expected_total':expected, 'normalize_field_targets':True,
            'normalization_factor':expected/total, 'normalization_total':total, 'source_column':column,
            'estimated_players':names.loc[missing].tolist(),
            'fallback_source':fallback_source, 'censored_player_keys':censored_active,
            'missing_eligible_players':[], 'warnings':warnings}
    result.attrs['fantasylabs_nba_ownership'] = meta
    return result, meta
