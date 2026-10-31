"""Offline exhaustive support for NFL DK Showdown and FD Single Game.

One row per distinct special-role player and unordered five-player FLEX set.
This enumerates legal support, not opponent probabilities or a realistic field.
No live application module imports this file.
"""
from itertools import combinations,islice
from math import comb
import numpy as np
import pandas as pd


def prepare(pool,site,*,min_salary=0):
    if site not in {'dk','fd'}:raise ValueError('Site must be dk or fd')
    if not {'Player ID','Salary','Team'}<=set(pool):raise ValueError('Player ID, Salary and Team required')
    ids=pool['Player ID'].astype(str)
    if pool['Player ID'].isna().any() or ids.str.strip().eq('').any() or ids.duplicated().any():raise ValueError('Unique nonempty player IDs required')
    salary=pd.to_numeric(pool['Salary'],errors='raise').to_numpy(float)
    special=(pd.to_numeric(pool['CaptainSalary'],errors='raise').to_numpy(float)
             if site=='dk' and 'CaptainSalary' in pool else salary*1.5)
    if not np.isfinite(salary).all() or not np.isfinite(special).all() or (salary<=0).any() or (special<=0).any():raise ValueError('Positive finite salaries required')
    # Work in half-dollar units to preserve exact 1.5x salary arithmetic.
    if not np.equal(salary*2,np.rint(salary*2)).all() or not np.equal(special*2,np.rint(special*2)).all():raise ValueError('Salaries must be representable in half-dollar units')
    teams=pool['Team'].astype(str).str.strip()
    if pool['Team'].isna().any() or teams.eq('').any() or teams.nunique()!=2:raise ValueError('Exactly two known teams required')
    cap=50000 if site=='dk' else 60000
    if isinstance(min_salary,bool) or not np.isfinite(min_salary) or not 0<=min_salary<=cap:raise ValueError('Invalid minimum salary')
    keep=np.ones(len(pool),bool)
    if 'Projection' in pool:
        projection=pd.to_numeric(pool['Projection'],errors='coerce').to_numpy(float)
        keep &= np.isfinite(projection)&(projection>0)
    if 'Injury Status' in pool:keep &= ~pool['Injury Status'].astype(str).str.upper().isin(['OUT','O','IR','SUSPENDED']).to_numpy()
    if 'Eligible' in pool:keep &= pool['Eligible'].astype(str).str.casefold().isin(['true','1']).to_numpy()
    original=np.flatnonzero(keep)
    return dict(indices=original,salary_ticks=np.rint(salary*2).astype(np.int64),
                special_ticks=np.rint(special*2).astype(np.int64),teams=pd.factorize(teams,sort=True)[0],
                cap_ticks=cap*2,min_ticks=float(min_salary)*2,
                eligible_players=len(original),six_player_sets=comb(len(original),6) if len(original)>=6 else 0,
                special_role_assignments=6*comb(len(original),6) if len(original)>=6 else 0)


def enumerate_lineups(pool,site,*,min_salary=0,batch_sets=8192,special_player_ids=None):
    """Yield (original-row index matrix, exact salaries) in bounded batches.

    Projection/injury/Eligible filters are applied when provided. Questionable
    stays eligible. An optional special-player whitelist restricts Captain/MVP only; all eligible
    players remain available in FLEX. No sampling is performed.
    A complete traversal is exhaustive; consumers must not label partial runs
    complete. FLEX permutation duplicates are never generated.
    """
    if type(batch_sets) is not int or batch_sets<1:raise ValueError('Positive integer batch size required')
    state=prepare(pool,site,min_salary=min_salary)
    allowed=np.ones(len(pool),dtype=bool)
    if special_player_ids is not None:
        requested=list(map(str,special_player_ids))
        known=pool['Player ID'].astype(str).to_numpy()
        if not requested or not np.isin(requested,known[state['indices']]).all():
            raise ValueError('Special-role IDs must be a nonempty subset of eligible player IDs')
        allowed=np.isin(known,requested)
    # Enumerate C(n,5) FLEX sets once, rather than C(n,6) sets with six
    # assignments each. Captain restrictions reduce work immediately.
    captains=state['indices'][allowed[state['indices']]]
    source=combinations(state['indices'].tolist(),5)
    while True:
        flat=np.fromiter((v for row in islice(source,batch_sets) for v in row),dtype=np.int32)
        if not len(flat):return
        flex=flat.reshape(-1,5)
        base=state['salary_ticks'][flex].sum(axis=1)
        teams=state['teams'][flex]
        mixed=(teams!=teams[:,0,None]).any(axis=1)
        for captain in captains:
            cost=base+state['special_ticks'][captain]
            valid=((cost>=state['min_ticks'])&(cost<=state['cap_ticks'])
                   &~(flex==captain).any(axis=1)
                   &(mixed|(teams[:,0]!=state['teams'][captain])))
            if not valid.any():continue
            selected=flex[valid]
            rows=np.empty((len(selected),6),dtype=np.int32)
            rows[:,0]=captain
            rows[:,1:]=selected
            yield rows,cost[valid]/2
