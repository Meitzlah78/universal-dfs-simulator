"""Bounded batched NBA candidate search over shared game outcomes."""
import numpy as np
from simmah_nba_rules import rules_for


def build_candidates(pool,outcomes,target=5000,seed=83,salary_min=0,salary_cap=None,
                     max_attempts=200000,batch_size=512):
    """Return original pool-row indices in uploaded slot order, never filler duplicates.

    Candidates use individual shared-slate outcomes plus modest search noise.
    This is bounded heuristic search, not an exhaustive optimizer or portfolio
    selector. Evaluation must use separately simulated outcomes.
    """
    rules=rules_for(pool);eligibility=rules['eligibility'];size=len(rules['slots'])
    salary_cap=rules['salary_cap'] if salary_cap is None else salary_cap
    values=np.asarray(outcomes,float)
    if values.ndim!=2 or values.shape[1]!=len(pool) or not len(values) or not np.isfinite(values).all():
        raise ValueError('Finite simulation rows aligned to the full NBA pool required')
    if any(not isinstance(v,int) or v<1 for v in (target,max_attempts,batch_size)):
        raise ValueError('Positive integer search limits required')
    if not 0<=salary_min<=salary_cap:raise ValueError('Invalid salary range')
    if pool['Player ID'].duplicated().any():raise ValueError('Duplicate NBA player IDs')
    projection=np.asarray(pool['Projection'],float)
    injury=pool['Injury Status'].astype(str).str.upper().isin(['O','OUT','IR','SUSPENDED']).to_numpy()
    keep=np.isfinite(projection)&(projection>0)&~injury
    original=np.flatnonzero(keep)
    if len(original)<size:raise ValueError('At least nine eligible NBA players required')
    players=pool.iloc[original];values=values[:,original]
    salary=np.asarray(players['Salary'],float)
    if not np.isfinite(salary).all() or (salary<=0).any():raise ValueError('Positive salaries required')
    positions=[set(str(p).split('/')) for p in players['Position']]
    eligible=np.array([[bool(p & allowed) for p in positions] for allowed in eligibility])
    if not eligible.any(axis=1).all():raise ValueError('A roster slot has no eligible NBA players')
    _,teams=np.unique(players['Team'].astype(str),return_inverse=True)
    if len(set(teams))<rules['min_teams']:raise ValueError('NBA roster requires at least three teams')
    # Restrictive positions first, flexible slots last. Safe lower bounds may
    # reuse cheap players; this prunes impossible budgets without removing a
    # feasible partial lineup.
    order=sorted(range(5),key=lambda j:eligible[j].sum())+list(range(5,size))
    minimum=np.array([salary[eligible[j]].min() for j in order])
    rng=np.random.default_rng(seed);seen=set();answer=[];attempted=0;incomplete=0;duplicates=0
    while attempted<max_attempts and len(answer)<target:
        n=min(batch_size,max_attempts-attempted);attempted+=n
        score=values[rng.integers(len(values),size=n)].copy()
        scale=np.maximum(np.std(score,axis=1),1)
        score+=rng.gumbel(size=score.shape)*scale[:,None]*.15
        chosen=np.full((n,size),-1,dtype=int);used=np.zeros((n,len(players)),bool)
        spent=np.zeros(n);counts=np.zeros((n,teams.max()+1),int);alive=np.ones(n,bool)
        for k,slot in enumerate(order):
            allowed=eligible[slot][None,:]&~used&(counts[:,teams]<rules['max_from_team'])
            allowed &= spent[:,None]+salary[None,:]+minimum[k+1:].sum()<=salary_cap
            possible=allowed.any(axis=1);alive &= possible
            pick=np.argmax(np.where(allowed,score,-np.inf),axis=1)
            ids=np.flatnonzero(alive);chosen[ids,slot]=pick[ids]
            used[ids,pick[ids]]=True;spent[ids]+=salary[pick[ids]]
            counts[ids,teams[pick[ids]]]+=1
        valid=alive&(spent>=salary_min)&(spent<=salary_cap)
        valid &= (counts>0).sum(axis=1)>=rules['min_teams']
        if rules['min_games']>1:
            games=np.array([str(tuple(sorted((str(r.Team),str(r.Opponent))))) for r in players.itertuples()])
            for row_index in np.flatnonzero(valid):
                valid[row_index]=len(set(games[chosen[row_index]]))>=rules['min_games']
        incomplete+=int((~valid).sum())
        for row in chosen[valid]:
            canonical=tuple(sorted(row))
            if canonical in seen:duplicates+=1;continue
            seen.add(canonical);answer.append(original[row])
            if len(answer)==target:break
    return {'indices':np.asarray(answer,dtype=int).reshape(-1,size),
            'requested':target,'attempted':attempted,'unique':len(answer),
            'rejected_incomplete_or_salary':incomplete,'duplicates':duplicates,
            'complete':len(answer)==target,'status':'experimental bounded heuristic; not live NBA build'}
