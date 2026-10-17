"""Bounded joint-outcome roster search shared by all NFL DFS formats.

Each proposal optimizes ONE complete simulated slate outcome. Batched greedy
seeds plus coordinate ascent are a heuristic, not a claim of global optimality.
Evaluation/contest outcomes must be generated independently by the caller.
"""
import numpy as np
import pandas as pd


def build_candidates(pool,outcomes,roster,target=5000,salary_min=0,salary_max=50000,
                     multipliers=None,salary_costs=None,locks=(),special_allowed=None,
                     max_from_team=None,require_both_teams=False,validator=None,
                     rng=None,progress=None,max_proposals=100000,noise=.08,penalties=None):
    rng=np.random.default_rng() if rng is None else rng
    pool=pool.drop_duplicates('Name').reset_index(drop=True)
    names=pool['Name'].astype(str).to_numpy(object)
    if len(names)<len(roster):raise ValueError('Not enough eligible players for this roster')
    missing=set(names)-set(outcomes.columns)
    if missing:raise ValueError('Candidate outcomes are missing players: '+', '.join(sorted(missing)[:5]))
    values=outcomes.reindex(columns=names).to_numpy(dtype=np.float32)
    if not len(values) or not np.isfinite(values).all():raise ValueError('Candidate outcomes must be finite and nonempty')
    slots=[slot for slot,_ in roster];count=len(slots)
    mult=np.ones(count) if multipliers is None else np.asarray(multipliers,float)
    salary=pd.to_numeric(pool['Salary'],errors='raise').to_numpy(float)
    costs=np.asarray(salary_costs,float) if salary_costs is not None else mult[:,None]*salary[None,:]
    if len(mult)!=count or costs.shape!=(count,len(names)) or not np.isfinite(costs).all() or (costs<=0).any():
        raise ValueError('Invalid slot multiplier or salary-cost matrix')
    positions=[set(str(p).upper().replace(' ','').split('/')) for p in pool['Position']]
    eligible=[np.array([i for i,p in enumerate(positions) if not allowed or p & allowed],dtype=int) for _,allowed in roster]
    if special_allowed is not None:eligible[0]=np.array([i for i in eligible[0] if names[i] in special_allowed])
    if any(not len(x) for x in eligible):raise ValueError('A roster slot has no eligible players')
    lookup={name:i for i,name in enumerate(names)}
    if any(name not in lookup for name in locks):raise ValueError('A locked player is unavailable')
    locked=np.array([lookup[name] for name in locks],int)
    if len(locked)>count:raise ValueError('More locks than roster slots')
    teams=pool.get('Team',pd.Series('',index=pool.index)).astype(str).str.upper().to_numpy(object)
    min_cost=np.array([costs[s,choices].min() for s,choices in enumerate(eligible)])
    max_cost=np.array([costs[s,choices].max() for s,choices in enumerate(eligible)])
    penalty=np.zeros(len(names)) if penalties is None else np.asarray(penalties,float)
    if penalty.shape!=(len(names),):raise ValueError('Ownership penalties do not align with player names')
    records=[];seen=set();proposed=0
    while len(records)<target and proposed<max_proposals:
        batch=min(256,max_proposals-proposed);proposed+=batch
        scenario=rng.integers(0,len(values),batch)
        joint=values[scenario]
        picks=np.full((batch,count),-1,dtype=int);fixed=np.zeros((batch,count),bool)
        total=np.zeros(batch);alive=np.ones(batch,bool)
        # Allocate all locked players first, with randomized eligible-slot choices.
        for player in locked:
            possible=np.array([player in choices for choices in eligible])
            options=(picks<0)&possible[None,:]
            valid=options.any(axis=1);alive &= valid
            draw=rng.random((batch,count));draw[~options]=-1
            col=draw.argmax(axis=1);row=np.flatnonzero(valid)
            picks[row,col[row]]=player;fixed[row,col[row]]=True
            total[row]+=costs[col[row],player]
        scale=np.maximum(joint.std(axis=1),1)
        # Vary the salary opportunity cost between proposals, not player outcomes.
        price=rng.uniform(0,.004,batch)
        for slot,choices in enumerate(eligible):
            row=np.flatnonzero(alive & (picks[:,slot]<0))
            if not len(row):continue
            used=(picks[row,:,None]==choices[None,None,:]).any(axis=1)
            free=picks[row]<0;free[:,slot]=False
            low=(free*min_cost).sum(axis=1);high=(free*max_cost).sum(axis=1)
            next_total=total[row,None]+costs[slot,choices][None,:]
            feasible=(~used)&(next_total+low[:,None]<=salary_max)&(next_total+high[:,None]>=salary_min)
            objective=(joint[row[:,None],choices]-penalty[choices])*mult[slot]-price[row,None]*costs[slot,choices]
            objective+=rng.gumbel(size=objective.shape)*scale[row,None]*noise
            objective[~feasible]=-np.inf
            valid=feasible.any(axis=1);alive[row[~valid]]=False
            best=objective.argmax(axis=1);row=row[valid];best=best[valid]
            picks[row,slot]=choices[best];total[row]+=costs[slot,choices[best]]
        alive &= (picks>=0).all(axis=1)&(total>=salary_min)&(total<=salary_max)
        # Coordinate ascent improves each complete legal seed on its own scenario.
        for _ in range(2):
            for slot,choices in enumerate(eligible):
                row=np.flatnonzero(alive & ~fixed[:,slot])
                if not len(row):continue
                current=picks[row,slot].copy()
                picks[row,slot]=-1
                used=(picks[row,:,None]==choices[None,None,:]).any(axis=1)
                adjusted=total[row,None]-costs[slot,current][:,None]+costs[slot,choices][None,:]
                feasible=(~used)&(adjusted>=salary_min)&(adjusted<=salary_max)
                objective=(joint[row[:,None],choices]-penalty[choices])*mult[slot]
                objective[~feasible]=-np.inf
                best=objective.argmax(axis=1)
                picks[row,slot]=choices[best];total[row]=adjusted[np.arange(len(row)),best]
        for row in np.flatnonzero(alive):
            pick=picks[row]
            unique_teams,counts=np.unique(teams[pick],return_counts=True)
            if max_from_team is not None and len(counts) and counts.max()>max_from_team:continue
            if require_both_teams and len(unique_teams)<2:continue
            chosen={slot:str(names[pick[i]]) for i,slot in enumerate(slots)}
            if validator is not None and not validator(chosen):continue
            special=count==6 and mult[0]!=1
            key=(int(pick[0]),tuple(sorted(map(int,pick[1:])))) if special else tuple(sorted(map(int,pick)))
            if key in seen:continue
            seen.add(key)
            records.append({**chosen,'Salary':int(round(total[row])),
                'Build Scenario':int(scenario[row]),
                'Scenario Score':float((joint[row,pick]*mult).sum())})
            if len(records)>=target:break
        if progress:progress(min(1,len(records)/target),f'Building from joint outcomes: {len(records):,} / {target:,}')
    result=pd.DataFrame(records)
    result.attrs.update(engine='joint-outcome-search-v1',proposals=proposed,target=target)
    return result


def summarize_candidates(frame,outcomes,slots,multipliers=None):
    """Score joint lineup distributions in chunks; never sum marginal percentiles."""
    if frame.empty:return frame
    names=list(map(str,outcomes.columns));index={name:i for i,name in enumerate(names)}
    values=outcomes.to_numpy(np.float32)
    mult=np.ones(len(slots)) if multipliers is None else np.asarray(multipliers,np.float32)
    result=frame.copy();means=[];p95=[];p99=[]
    for start in range(0,len(frame),128):
        chunk=frame.iloc[start:start+128]
        picks=np.array([[index[str(name)] for name in row] for row in chunk[slots].itertuples(index=False,name=None)])
        scores=np.zeros((len(values),len(chunk)),np.float32)
        for s in range(len(slots)):scores+=values[:,picks[:,s]]*mult[s]
        means.extend(scores.mean(axis=0));p95.extend(np.quantile(scores,.95,axis=0));p99.extend(np.quantile(scores,.99,axis=0))
    result['SimMean']=means;result['ProjectedPoints']=means
    result['SimP95']=p95;result['SimP99']=p99
    result['Score']=means  # scenario scores across different stories aren't comparable
    return result
