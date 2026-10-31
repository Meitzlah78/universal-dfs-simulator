"""Unique legal Showdown proposals and expansion without ownership feedback."""
from itertools import combinations
from math import comb
import numpy as np
import pandas as pd

SLOTS=['Captain','Flex1','Flex2','Flex3','Flex4','Flex5']


def build_unique_field(pool,flex_weights,captain_weights,target,salary_cap=50000,min_salary=48000,rng=None,progress=None):
    rng=rng if rng is not None else np.random.default_rng(123)
    p=pool.reset_index(drop=True);n=len(p);target=max(0,int(target))
    empty=pd.DataFrame(columns=SLOTS+['Salary'])
    if n<6 or not target:return empty
    if p.Name.duplicated().any():raise ValueError('Unique player names required')
    salary=pd.to_numeric(p.Salary,errors='raise').to_numpy(float)
    captain_salary=pd.to_numeric(p.CaptainSalary,errors='raise').to_numpy(float)
    teams=p.Team.astype(str).to_numpy();names=p.Name.astype(str).to_numpy()
    fw=np.asarray(flex_weights,float);cw=np.asarray(captain_weights,float)
    for w in (fw,cw):
        if w.shape!=(n,) or not np.isfinite(w).all() or (w<0).any() or not w.any():raise ValueError('Invalid opponent preferences')
    fw=fw/fw.sum();cw=cw/cw.sum()
    if n*comb(n-1,5)>8000000:raise ValueError('Too many Showdown combinations; narrow the positive-projection pool')
    picks=[];costs=[];mass=[]
    for captain in range(n):
        if progress:progress(captain/n,f'Enumerating legal Showdown rosters: {captain+1}/{n} Captains')
        if cw[captain]<=0:continue
        other=[i for i in range(n) if i!=captain]
        combos=np.asarray(list(combinations(other,5)),dtype=np.int32)
        sums=captain_salary[captain]+salary[combos].sum(axis=1)
        valid=(sums>=min_salary)&(sums<=salary_cap)&(teams[combos]!=teams[captain]).any(axis=1)
        combos=combos[valid];sums=sums[valid]
        if not len(combos):continue
        # Normalize FLEX preferences within each legal Captain group. Salary
        # rejection must not turn a cheap Captain into the most popular Captain.
        logs=np.log(np.maximum(fw[combos],1e-300)).sum(axis=1)
        w=np.exp(logs-logs.max());w/=w.sum()
        mass.append(cw[captain]*w)
        picks.append(np.column_stack([np.full(len(combos),captain,dtype=np.int32),combos]));costs.append(sums)
    if not picks:return empty
    picks=np.concatenate(picks);costs=np.concatenate(costs);mass=np.concatenate(mass);mass/=mass.sum()
    size=min(target,len(picks))
    chosen=rng.choice(len(picks),size=size,replace=False,p=mass)
    result=pd.DataFrame(names[picks[chosen]],columns=SLOTS);result['Salary']=costs[chosen].astype(int)
    result.attrs.update(legal_combinations=len(picks),requested_unique=target,unique_sample=len(result))
    if progress:progress(1.,f'{len(result):,} unique legal Showdown opponents ready')
    return result


def expand_field(sample_field,full_field_size,seed=20261012):
    """Uniform bootstrap of the selected sample, no second ownership weighting.

    This is an estimated expansion, not a calibrated real-world duplication model.
    Player preferences and learned profiles have already shaped the sample.
    """
    if sample_field is None or sample_field.empty:return sample_field
    count=int(full_field_size)
    if count<1:raise ValueError('Positive field size required')
    rng=np.random.default_rng(seed)
    sample=sample_field.copy().reset_index(drop=True)
    # Defend against callers providing FLEX permutations of the same roster.
    keys=[(r[0],tuple(sorted(r[1:]))) for r in sample[SLOTS].itertuples(index=False,name=None)]
    sample=sample.loc[~pd.Series(keys).duplicated()].reset_index(drop=True)
    if count<=len(sample):return sample.iloc[rng.choice(len(sample),count,replace=False)].reset_index(drop=True)
    # Keep every sampled representative; only additional contest entries repeat.
    indices=np.concatenate([np.arange(len(sample)),rng.integers(0,len(sample),count-len(sample))])
    rng.shuffle(indices)
    return sample.iloc[indices].reset_index(drop=True)
