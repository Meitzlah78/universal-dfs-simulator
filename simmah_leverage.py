"""Transparent value metrics and candidate-dependent simulated leverage signals."""
import numpy as np
import pandas as pd


def add_value_columns(pool):
    result = pool.copy()
    salary = pd.to_numeric(result.get('Salary', pd.Series(index=result.index, dtype=float)), errors='coerce')
    projection = pd.to_numeric(result.get('Projection', pd.Series(index=result.index, dtype=float)), errors='coerce')
    result['Projected Pts / $1k'] = (1000 * projection / salary.where(salary > 0)).replace([np.inf, -np.inf], np.nan).round(2)
    if 'Sim P95' in result:
        result['P95 Pts / $1k'] = (1000 * pd.to_numeric(result['Sim P95'], errors='coerce') / salary.where(salary > 0)).replace([np.inf, -np.inf], np.nan).round(2)
    if 'Position' in result:
        result['Position Value Percentile'] = (100 * result.groupby('Position')['Projected Pts / $1k'].rank(pct=True)).round(1)
    return result


def leverage_report(pool, candidates, field, slots, special_slot=None):
    """Top1-weighted candidate presence minus observed simulated field presence.

    This is NOT optimal-lineup frequency or a causal player edge. Equal-quality
    duplicate rosters count once in the candidate sample; field duplicates count
    as entries. Unknown players and unevaluated/nonpositive weights are excluded.
    """
    result = add_value_columns(pool.drop_duplicates('Name')).reset_index(drop=True)
    result['Top1-weighted Presence %'] = np.nan
    result['Field Own %'] = np.nan
    result['Sim Leverage (pp)'] = np.nan
    if not slots or not isinstance(candidates, pd.DataFrame) or not isinstance(field, pd.DataFrame):
        return result
    if candidates.empty or field.empty or 'Top1' not in candidates or not all(s in candidates and s in field for s in slots):
        return result
    known = set(result.Name.astype(str))
    sample = candidates.copy()
    sample = sample.loc[sample[slots].notna().all(axis=1)]
    sample = sample.loc[sample[slots].astype(str).isin(known).all(axis=1)]
    # FLEX order never creates a new roster; special-role assignment does.
    ordinary = [s for s in slots if s != special_slot]
    sample['_roster'] = [((str(row[special_slot]),) if special_slot else ()) + tuple(sorted(str(row[s]) for s in ordinary)) for _, row in sample.iterrows()]
    sample['_weight'] = pd.to_numeric(sample.Top1, errors='coerce').replace([np.inf, -np.inf], np.nan)
    sample = sample.loc[sample['_weight'].gt(0)]
    if sample.empty:
        return result
    # Average repeated roster estimates so duplicate ordering cannot change results.
    group = sample.groupby('_roster')['_weight'].mean()
    rosters = list(group.index)
    weights = group.to_numpy(float)
    denominator = weights.sum()
    field_rows = field[slots].dropna().astype(str).to_numpy()
    if not len(field_rows):
        return result
    def presence(names, weighted_rosters, field_sets):
        rates, owns = [], []
        for name in names:
            rates.append(100 * sum(w for roster, w in zip(weighted_rosters, weights) if name in roster) / denominator)
            owns.append(100 * sum(name in row for row in field_sets) / len(field_sets))
        return np.array(rates), np.array(owns)
    rates, owns = presence(result.Name.astype(str), [set(r) for r in rosters], [set(r) for r in field_rows])
    result['Top1-weighted Presence %'] = rates.round(2)
    result['Field Own %'] = owns.round(2)
    result['Sim Leverage (pp)'] = (rates - owns).round(2)
    if special_slot:
        special_index = slots.index(special_slot)
        rates, owns = presence(result.Name.astype(str), [{r[0]} for r in rosters], [{r[special_index]} for r in field_rows])
        result['CPT/MVP Weighted Presence %'] = rates.round(2)
        result['Field CPT/MVP Own %'] = owns.round(2)
        result['CPT/MVP Leverage (pp)'] = (rates - owns).round(2)
    result.attrs['evaluated_unique_candidates'] = len(group)
    result.attrs['field_entries'] = len(field_rows)
    return result
