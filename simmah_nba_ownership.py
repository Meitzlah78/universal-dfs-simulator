"""Validate external NBA ownership before using marginal field targets."""
import numpy as np
import pandas as pd
from simmah_nba_rules import rules_for

COLUMN='RotoWire Projected Own %'


def field_ownership_inputs(pool):
    expected=100*len(rules_for(pool)['slots'])
    projection=pd.to_numeric(pool['Projection'],errors='coerce').to_numpy(float)
    active=np.isfinite(projection)&(projection>0)&~pool['Injury Status'].astype(str).str.upper().isin(['O','OUT','IR','SUSPENDED']).to_numpy()
    if 'Eligible' in pool:active &= pool['Eligible'].astype(str).str.casefold().isin(['true','1']).to_numpy()
    if 'Projected Minutes' in pool:
        minutes=pd.to_numeric(pool['Projected Minutes'],errors='coerce').to_numpy(float)
        active &= np.isfinite(minutes)&(minutes>0)&(minutes<=48)
    raw=pd.to_numeric(pool.get(COLUMN,pd.Series(np.nan,index=pool.index)),errors='coerce').to_numpy(float)
    reason=None
    if not active.any():reason='no eligible players'
    elif not np.isfinite(raw[active]).all():reason='missing dedicated ownership values'
    elif ((raw[active]<0)|(raw[active]>100)).any():reason='ownership outside 0–100%'
    target=np.where(active,raw,0.)
    total=float(target.sum()) if np.isfinite(target).all() else None
    if reason is None and abs(total-expected)>expected*.01:
        reason=f'eligible RST total {total:.1f}% differs from {expected}% for this roster'
    if reason is None:
        target=target*(expected/total)
        if (target>100).any():reason='rounding adjustment would exceed 100%'
    if reason is None:
        return {'weights':target,'mode':'projected','source':f'RotoWire dedicated slate ownership; total {total:.1f}% rounded to {expected}%',
                'raw_total':total,'expected_total':expected,'status':'External ownership targets; field fit still requires residual checks.'}
    return {'weights':np.ones(len(pool)), 'mode':'relative popularity',
        'source':'Scenario-derived estimate; external ownership not used: '+reason,
        'raw_total':total,'expected_total':expected,
        'status':'External ownership unavailable or inconsistent. Field uses equal weights on independent scenario-built legal rosters; not calibrated contest ownership.'}
