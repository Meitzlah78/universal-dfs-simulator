"""Bounded quality/overlap selection with explicit player exposure limits.

This is a deterministic roster-overlap heuristic, not a contest-payout portfolio
optimizer or a claim to reproduce SaberSim's proprietary selection method.
"""
import math
import numpy as np
import pandas as pd


def select_portfolio(candidates, slots, count, metric, controls=None, default_max=80):
    count=int(count);controls=controls or {}
    if count<1:raise ValueError('Portfolio size must be positive')
    if candidates.empty or metric not in candidates:raise ValueError('Ranked candidates are unavailable')
    ranked=candidates.sort_values(metric,ascending=False,kind='stable').copy()
    # Interchangeable RB/WR/FLEX slots are part of one roster, not extra unique
    # entries. Special-role identity remains in the canonical key if supplied.
    special=next((s for s in slots if s in {'Captain','MVP'}),None)
    def canonical(row):
        return ((str(row[special]),) if special else ()) + tuple(sorted(str(row[s]) for s in slots if s!=special))
    keys=ranked.apply(canonical,axis=1)
    ranked=ranked.loc[~keys.duplicated()].reset_index(drop=True)
    if len(ranked)<count:raise ValueError(f'Only {len(ranked)} unique candidates are available for {count} entries')
    values=ranked[slots].astype(str).to_numpy()
    names=np.unique(values);lookup={n:i for i,n in enumerate(names)}
    picks=np.array([[lookup[n] for n in row] for row in values],int)
    incidence=np.zeros((len(ranked),len(names)),np.int8)
    incidence[np.arange(len(ranked))[:,None],picks]=1
    lower=np.zeros(len(names),int);upper=np.zeros(len(names),int)
    hard_upper=np.zeros(len(names),int);automatic=np.ones(len(names),bool)
    for i,name in enumerate(names):
        cfg=controls.get(name,{})
        def pct(key,default):
            value=pd.to_numeric(cfg.get(key,default),errors='coerce')
            return float(np.clip(value if pd.notna(value) else default,0,100))
        manual_min=pct('Min Exposure %',0);manual_max=pct('Max Exposure %',100)
        locked=bool(cfg.get('Lock',False));faded=bool(cfg.get('Fade',False))
        minimum=100 if locked else manual_min
        maximum=manual_max if locked or manual_min>default_max else min(manual_max,default_max)
        if faded:maximum=0;manual_max=0
        automatic[i]=not locked and manual_min<=default_max
        hard_upper[i]=0 if manual_max<=0 else max(1,math.floor(count*manual_max/100+1e-9))
        lower[i]=math.ceil(count*minimum/100-1e-9)
        upper[i]=0 if maximum<=0 else max(1,math.floor(count*maximum/100+1e-9))
        if lower[i]>upper[i]:raise ValueError(f'Conflicting portfolio exposure limits for {name}')
    quality=pd.to_numeric(ranked[metric],errors='coerce').fillna(-np.inf).to_numpy(float)
    finite=np.isfinite(quality)
    if not finite.any():raise ValueError('No finite lineup ranking values')
    lo,hi=quality[finite].min(),quality[finite].max()
    utility=np.where(finite,(quality-lo)/max(hi-lo,1e-9),-np.inf)
    chosen=[];used=np.zeros(len(ranked),bool);counts=np.zeros(len(names),int)
    overlap=np.zeros(len(ranked),float)
    selection_method="greedy";effective_auto_cap=default_max
    for turn in range(count):
        remaining=count-turn
        valid=(~used)&np.all(counts[picks]<upper[picks],axis=1)
        # Players whose minimum must occur in every remaining roster are hard
        # requirements. Other deficits get priority to make progress early.
        deficit=np.maximum(0,lower-counts)
        mandatory=deficit>=remaining
        if mandatory.any():valid &= incidence[:,mandatory].sum(axis=1)==mandatory.sum()
        urgency=(incidence@deficit.astype(float))/max(remaining,1)
        score=utility-.35*overlap+2*urgency
        score[~valid]=-np.inf
        best=int(np.argmax(score))
        if not np.isfinite(score[best]):
            chosen,effective_auto_cap=_repair_portfolio(incidence,lower,upper,hard_upper,automatic,
                count,utility,finite,default_max)
            selection_method="integer repair"
            counts=incidence[chosen].sum(axis=0)
            break
        chosen.append(best);used[best]=True;counts[picks[best]]+=1
        shared=incidence[:,picks[best]].sum(axis=1)/len(slots)
        overlap=np.maximum(overlap,shared)
    if (counts<lower).any():
        chosen,effective_auto_cap=_repair_portfolio(incidence,lower,upper,hard_upper,automatic,
            count,utility,finite,default_max)
        selection_method="integer repair"
    result=ranked.iloc[chosen].copy().reset_index(drop=True)
    result.attrs['portfolio_selection']='quality-overlap-exposure-v1'
    result.attrs['default_max_exposure_pct']=default_max
    result.attrs['effective_auto_cap_pct']=effective_auto_cap
    result.attrs['selection_method']=selection_method
    return result


def _repair_portfolio(incidence,lower,upper,hard_upper,automatic,count,utility,finite,default_max):
    """Reconsider all early choices with a sparse integer feasibility solve.

    Automatic diversification is a preference. Only after proven infeasibility
    may it relax in five-point steps. Manual maximums, minimums and locks never
    relax. A timed-out search is not evidence that constraints are infeasible.
    """
    from scipy.optimize import milp,Bounds,LinearConstraint
    from scipy.sparse import csc_matrix,vstack
    matrix=vstack([csc_matrix(np.ones((1,len(incidence)))),csc_matrix(incidence.T)],format='csc')
    objective=-np.where(finite,utility,0)+np.arange(len(incidence))*1e-10
    bounds=Bounds(np.zeros(len(incidence)),finite.astype(float))
    cap_levels=list(range(int(default_max),101,5))
    if 100 not in cap_levels:cap_levels.append(100)
    for cap in cap_levels:
        current=upper.copy()
        current[automatic]=np.minimum(hard_upper[automatic],max(1,math.floor(count*cap/100+1e-9)))
        solution=milp(objective,integrality=np.ones(len(incidence)),bounds=bounds,
            constraints=LinearConstraint(matrix,np.r_[count,lower],np.r_[count,current]),
            options={'time_limit':5.,'mip_rel_gap':.05})
        if solution.x is not None:
            chosen=np.flatnonzero(solution.x>.5)
            counts=incidence[chosen].sum(axis=0)
            if len(chosen)==count and (counts>=lower).all() and (counts<=current).all():
                return chosen.tolist(),cap
        if solution.status!=2:
            raise ValueError('Portfolio repair reached its search limit without a valid full portfolio. Manual exposure limits were kept; no duplicates were added.')
    raise ValueError('No full unique portfolio satisfies the manual exposure limits. Adjust those limits or expand the candidate pool; no duplicates were added.')


def put_portfolio_first(candidates,selected,slots):
    """Keep every alternative, placing assigned rosters first for display."""
    selected_keys={tuple(row) for row in selected[slots].astype(str).itertuples(index=False,name=None)}
    rest=candidates.loc[[tuple(row) not in selected_keys for row in candidates[slots].astype(str).itertuples(index=False,name=None)]]
    return pd.concat([selected,rest],ignore_index=True)
