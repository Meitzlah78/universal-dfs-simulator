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
