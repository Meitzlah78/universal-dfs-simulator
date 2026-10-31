"""Candidate-relative simulation leverage, not a claim of global optimality."""
import numpy as np
import pandas as pd

SLOTS=['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','D','DST','Captain','MVP','Flex1','Flex2','Flex3','Flex4','Flex5','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']


def candidate_opportunities(outcomes, candidates):
    """Share of independent evaluation outcomes won by each player's rosters.

    Use every supplied evaluation outcome and unique generated candidate. Split
    tied best rosters equally. This is relative to that candidate set, not an
    optimal-lineup probability over all legal combinations.
    """
    empty=pd.DataFrame(columns=['Name','Candidate Best %'])
    if not isinstance(outcomes,pd.DataFrame) or outcomes.empty or not isinstance(candidates,pd.DataFrame) or candidates.empty:
        empty.attrs['status']='Pending SIM and candidate build';return empty
    slots=[s for s in SLOTS if s in candidates]
    special=next((s for s in ['Captain','MVP'] if s in slots),None)
    if len(slots) not in {6,9} or (len(slots)==6 and not special):
        empty.attrs['status']='Unsupported candidate roster columns';return empty
    values=candidates[slots].astype(str).apply(lambda col:col.str.strip())
    keys=values.apply(lambda row:((row[special],) if special else ())+tuple(sorted(row[s] for s in slots if s!=special)),axis=1)
    values=values.loc[~keys.duplicated()]
    names=[str(c).strip() for c in outcomes.columns]
    if len(names)!=len(set(names)):
        empty.attrs['status']='Ambiguous simulation player names';return empty
    index={name:i for i,name in enumerate(names)}
    if not set(values.to_numpy().ravel())<=set(names):
        empty.attrs['status']='Pending: candidates and simulations have different players';return empty
    picks=np.array([[index[name] for name in row] for row in values.itertuples(index=False,name=None)],int)
    if (np.diff(np.sort(picks,axis=1),axis=1)==0).any():
        empty.attrs['status']='Invalid candidate with repeated player';return empty
    data=outcomes.to_numpy(float)
    if not np.isfinite(data[:,np.unique(picks)]).all():
        empty.attrs['status']='Pending: nonfinite simulation outcomes';return empty
    weights=np.zeros(len(picks),float)
    special_index=slots.index(special) if special else None
    for start in range(0,len(data),64):
        batch=data[start:start+64]
        scores=batch[:,picks].sum(axis=2)
        if special:scores+=.5*batch[:,picks[:,special_index]]
        best=scores==scores.max(axis=1,keepdims=True)
        weights+=(best/best.sum(axis=1,keepdims=True)).sum(axis=0)
    weights/=len(data)
    result=pd.DataFrame({'Name':names,'Candidate Best %':100*np.bincount(picks.ravel(),weights=np.repeat(weights,len(slots)),minlength=len(names))})
    if special:
        role='CPT' if special=='Captain' else 'MVP'
        role_best=100*np.bincount(picks[:,special_index],weights=weights,minlength=len(names))
        result[role+' Candidate Best %']=role_best
        result['FLEX Candidate Best %']=result['Candidate Best %']-role_best
    result.attrs.update(status='Ready',candidates=len(picks),simulations=len(data),basis='Best among unique generated candidates; ties split equally')
    return result


def attach_leverage(players, opportunities):
    result=players.copy();names=result.Name.astype(str).str.strip()
    for column in ['Candidate Best %','Leverage (pp)']:
        result[column]=np.nan
    result['Leverage Signal']='Pending'
    result['Leverage Status']=opportunities.attrs.get('status','Pending')
    result['Leverage Ownership Source']='Unavailable'
    if opportunities.empty:return result
    lookup=opportunities.set_index('Name')
    for col in lookup:result[col]=names.map(lookup[col])
    def ownership(col):
        raw=result[col] if col in result else pd.Series(np.nan,index=result.index)
        vals=pd.to_numeric(raw.astype(str).str.replace('%','',regex=False),errors='coerce')
        return vals.where(vals.between(0,100))
    projected=ownership('Projected Own %');field=ownership('Field Own %')
    baseline=projected.combine_first(field)
    result['Leverage (pp)']=result['Candidate Best %']-baseline
    result['Leverage Ownership Source']=np.where(projected.notna(),'Projected ownership',np.where(field.notna(),'Simulated field estimate','Unavailable'))
    for role in ['CPT','MVP','FLEX']:
        col=role+' Candidate Best %'
        if col in result:result[role+' Leverage (pp)']=result[col]-ownership('Field '+role+' Own %')
    result['Leverage Signal']=np.select([result['Leverage (pp)'].gt(0),result['Leverage (pp)'].lt(0),result['Leverage (pp)'].eq(0)],['Positive','Negative','Neutral'],default='Pending')
    result.loc[baseline.isna(),'Leverage Status']='Pending ownership'
    return result


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

