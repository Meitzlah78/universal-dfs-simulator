"""Grouped late-swap selection and an independent export exposure audit."""
import math
import time
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, vstack
from simmah_nba_portfolio_limits import portfolio_limits

VERSION='nba-grouped-late-swap-v1'


def exposure_bounds(pool, originals, locked, controls=None):
    limits=portfolio_limits(pool,controls);count=len(originals)
    inherited=np.bincount(originals.ravel(),minlength=len(pool))*locked
    lower=[];upper=[];warnings=[]
    for index,row in pool.iterrows():
        pid=str(row['Player ID']);cfg=limits[pid]
        cap=0 if cfg.get('Fade') else float(cfg['Max Exposure %'])
        maximum=0 if cap<=0 else max(1,math.floor(count*cap/100+1e-9))
        # Explicit user ceilings never gain a one-entry rounding exception.
        manual=(controls or {}).get(pid,{})
        if 'Max Exposure %' in manual:
            value=pd.to_numeric(manual['Max Exposure %'],errors='coerce')
            if pd.notna(value):maximum=min(maximum,math.floor(count*float(np.clip(value,0,100))/100+1e-9))
        minimum=math.ceil(count*float(cfg.get('Min Exposure %',0))/100-1e-9)
        if inherited[index]>maximum:
            warnings.append({'Player ID':pid,'Player':str(row['Name']),
                'Configured maximum entries':maximum,'Locked entries':int(inherited[index]),
                'Reason':'Already locked above cap; cannot remove or add started players'})
        lower.append(minimum);upper.append(max(maximum,int(inherited[index])))
    return np.asarray(lower),np.asarray(upper),limits,warnings


def audit_swap_portfolio(pool,originals,selected,locked,controls=None):
    """Only immutable inherited exposure can exceed a configured maximum."""
    lower,upper,limits,warnings=exposure_bounds(pool,originals,locked,controls)
    counts=np.bincount(np.asarray(selected).ravel(),minlength=len(pool))
    bad=np.flatnonzero((counts<lower)|(counts>upper))
    if len(bad):
        detail='; '.join(f"{pool.iloc[i]['Name']}: {counts[i]} entries, allowed {lower[i]}–{upper[i]}" for i in bad[:8])
        raise ValueError('Late-swap portfolio exposure check failed: '+detail+'. Run late swap again; caps were not relaxed')
    from collections import Counter
    actual=Counter(tuple(sorted(row)) for row in selected)
    frozen=Counter(tuple(sorted(row)) for row in originals if locked[row].all())
    if any(n>max(1,frozen.get(key,0)) for key,n in actual.items()):
        raise ValueError('Late-swap portfolio contains duplicate rosters; run late swap again')
    return warnings


def select_swap_portfolio(pool,originals,locked,candidates,group_candidates,group_entries,metric,
                          diversity=50,controls=None,seconds=10):
    """Choose group quotas jointly; then improve normalized quality/concentration.

    Each binary variable is a complete legal roster in one exact locked-slot
    group. Canonical uniqueness couples groups. Locked duplicate rosters already
    entered are preserved, explicitly, rather than moved after tipoff.
    """
    candidates=np.asarray(candidates,int);metric=np.asarray(metric,float)
    count=len(originals);m=len(candidates)
    if not m or metric.shape!=(m,):raise ValueError('Late-swap candidate scores are misaligned')
    lower,upper,limits,warnings=exposure_bounds(pool,originals,locked,controls)
    groups=list(group_entries);membership=np.zeros(m,int)
    for g in groups:membership[np.asarray(group_candidates[g],int)]+=1
    if not (membership==1).all():raise ValueError('Each swap candidate must belong to one locked-slot group')
    keys=[tuple(sorted(row)) for row in candidates]
    key_lookup={key:i for i,key in enumerate(dict.fromkeys(keys))}
    incidence=coo_matrix((np.ones(candidates.size),
        (candidates.ravel(),np.repeat(np.arange(m),candidates.shape[1]))),shape=(len(pool),m)).tocsc()
    rr=[];cc=[]
    for gno,g in enumerate(groups):
        ids=group_candidates[g];rr.extend([gno]*len(ids));cc.extend(ids)
    quotas=coo_matrix((np.ones(len(cc)),(rr,cc)),shape=(len(groups),m)).tocsc()
    unique=coo_matrix((np.ones(m),([key_lookup[k] for k in keys],np.arange(m))),shape=(len(key_lookup),m)).tocsc()
    unique_upper=np.ones(len(key_lookup))
    # Fully locked duplicates cannot be repaired. Only their exact existing
    # multiplicity is exempt; open duplicate entries still require uniqueness.
    fixed_counts={}
    for row in originals:
        if locked[row].all():
            key=tuple(sorted(row));fixed_counts[key]=fixed_counts.get(key,0)+1
    for key,n in fixed_counts.items():
        if key in key_lookup:unique_upper[key_lookup[key]]=n
    matrix=vstack([quotas,incidence,unique],format='csc')
    sizes=np.asarray([len(group_entries[g]) for g in groups])
    lo=np.r_[sizes,lower,np.zeros(len(key_lookup))];hi=np.r_[sizes,upper,unique_upper]
    finite=np.isfinite(metric)
    if not finite.any():raise ValueError('No finite late-swap ranking values')
    quality=np.zeros(m);quality[finite]=(metric[finite]-metric[finite].min())/max(np.ptp(metric[finite]),1e-9)
    strength=float(np.clip(diversity,0,100))/100
    started=time.monotonic()
    solution=milp(-quality+np.arange(m)*1e-10,integrality=np.ones(m),
        bounds=Bounds(np.zeros(m),finite.astype(float)),constraints=LinearConstraint(matrix,lo,hi),
        options={'time_limit':float(seconds),'mip_rel_gap':.01})
    if solution.x is None:
        reason='No full portfolio satisfies the late-swap caps in this candidate pool' if solution.status==2 else 'Late-swap portfolio search reached its time limit'
        raise ValueError(reason+'; original entries remain unchanged. No caps were relaxed')
    chosen=np.flatnonzero(solution.x>.5).tolist()
    totals=np.asarray(matrix[:,chosen].sum(axis=1)).ravel()
    if len(chosen)!=count or (totals<lo-1e-7).any() or (totals>hi+1e-7).any():
        raise ValueError('Late-swap solver did not return a valid integer portfolio')
    # Same normalized marginal concentration and max-overlap scale as the
    # initial selector, with same-group swaps preserving all hard constraints.
    deadline=time.monotonic()+min(1.,max(0.,seconds-(time.monotonic()-started)))
    for _ in range(2):
        changed=False
        for position,outgoing in enumerate(chosen):
            if not strength or time.monotonic()>=deadline:break
            g=next(g for g in groups if outgoing in group_candidates[g])
            options=np.asarray(group_candidates[g],int)
            others=chosen[:position]+chosen[position+1:]
            counts=np.asarray(incidence[:,others].sum(axis=1)).ravel()
            used_keys={keys[i] for i in others}
            def score(i):
                overlap=max((len(set(candidates[i])&set(candidates[j]))/candidates.shape[1] for j in others),default=0.)
                concentration=(2*counts[candidates[i]].sum()+candidates.shape[1])/count
                return quality[i]-strength*concentration-.7*strength*overlap
            best=outgoing;best_score=score(outgoing)
            for incoming in options:
                if time.monotonic()>=deadline:break
                if incoming==outgoing or not finite[incoming] or keys[incoming] in used_keys:continue
                total=counts.copy();total[candidates[incoming]]+=1
                if (total<lower).any() or (total>upper).any():continue
                value=score(incoming)
                if value>best_score+1e-9:best=int(incoming);best_score=value
            if best!=outgoing:chosen[position]=best;changed=True
        if not changed:break
    assignment=np.full(count,-1,int)
    for g in groups:
        picked=[i for i in chosen if i in group_candidates[g]]
        for entry,i in zip(group_entries[g],picked):assignment[entry]=i
    if (assignment<0).any():raise ValueError('Incomplete late-swap entry assignment')
    audit_swap_portfolio(pool,originals,candidates[assignment],locked,controls)
    return assignment,{'version':VERSION,'hard_limits':limits,'locked_overages':warnings,
        'solver_status':int(solution.status),'diversity':float(diversity),
        'objective':'normalized quality with bounded same-group concentration/overlap improvement'}
