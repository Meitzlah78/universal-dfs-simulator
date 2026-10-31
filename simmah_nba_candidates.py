"""Bounded batched NBA candidate search over shared game outcomes."""
import numpy as np
from simmah_nba_rules import rules_for


def build_candidates(pool,outcomes,target=5000,seed=83,salary_min=0,salary_cap=None,
                     max_attempts=200000,batch_size=512,correlation=0,fixed_slots=None,excluded_indices=None):
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
    if not np.isfinite(correlation) or not 0<=correlation<=100:raise ValueError('Build correlation must be between 0 and 100')
    if pool['Player ID'].duplicated().any():raise ValueError('Duplicate NBA player IDs')
    projection=np.asarray(pool['Projection'],float)
    injury=pool['Injury Status'].astype(str).str.upper().isin(['O','OUT','IR','SUSPENDED']).to_numpy()
    keep=np.isfinite(projection)&(projection>0)&~injury
    if 'Eligible' in pool:
        keep &= pool['Eligible'].astype(str).str.casefold().isin(['true','1']).to_numpy()
    if 'Projected Minutes' in pool:
        minutes=np.asarray(pool['Projected Minutes'],float)
        keep &= np.isfinite(minutes)&(minutes>0)&(minutes<=48)
    fixed_slots={} if fixed_slots is None else dict(fixed_slots)
    if len(set(fixed_slots.values()))!=len(fixed_slots):raise ValueError('Repeated fixed NBA player')
    for slot,index in fixed_slots.items():
        if not isinstance(slot,(int,np.integer)) or not 0<=slot<size or not isinstance(index,(int,np.integer)) or not 0<=index<len(pool):
            raise ValueError('Invalid fixed NBA slot or player')
    if excluded_indices is not None:keep[np.asarray(excluded_indices,dtype=int)]=False
    for index in fixed_slots.values():keep[index]=True
    original=np.flatnonzero(keep)
    if len(original)<size:raise ValueError('At least nine eligible NBA players required')
    players=pool.iloc[original];values=values[:,original]
    positive_correlation=np.zeros((len(players),len(players)))
    if correlation>0:
        centered=values-values.mean(axis=0)
        norm=np.sqrt((centered*centered).sum(axis=0))
        denominator=norm[:,None]*norm[None,:]
        positive_correlation=np.divide(centered.T@centered,denominator,
                                       out=positive_correlation,where=denominator>0)
        games=[tuple(sorted((str(r.Team),str(r.Opponent)))) for r in players.itertuples()]
        same_game=np.array([[a==b for b in games] for a in games])
        # Ignore weak sample noise and independent games. This affects search
        # preference only; the simulated stat ledger is never modified.
        positive_correlation=np.where(same_game & (positive_correlation>=.05),
                                      np.clip(positive_correlation,0,1),0)
        np.fill_diagonal(positive_correlation,0)
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
    local={int(index):j for j,index in enumerate(original)}
    fixed={slot:local[index] for slot,index in fixed_slots.items()}
    if any(not eligible[slot,index] for slot,index in fixed.items()):raise ValueError('Fixed NBA player is ineligible for slot')
    order=[slot for slot in order if slot not in fixed]
    minimum=np.array([salary[eligible[j]].min() for j in order])
    remaining_minimum=np.array([minimum[k+1:].sum() for k in range(len(order))])
    if rules['min_games']>1:
        game_keys=[str(tuple(sorted((str(r.Team),str(r.Opponent))))) for r in players.itertuples()]
        _,game_ids=np.unique(game_keys,return_inverse=True)
    rng=np.random.default_rng(seed);seen=set();answer=[];attempted=0;incomplete=0;duplicates=0
    while attempted<max_attempts and len(answer)<target:
        n=min(batch_size,max_attempts-attempted);attempted+=n
        score=values[rng.integers(len(values),size=n)].copy()
        scale=np.maximum(np.std(score,axis=1),1)
        score+=rng.gumbel(size=score.shape)*scale[:,None]*.15
        chosen=np.full((n,size),-1,dtype=int);used=np.zeros((n,len(players)),bool)
        pair_bonus=np.zeros_like(score)
        spent=np.zeros(n);counts=np.zeros((n,teams.max()+1),int);alive=np.ones(n,bool)
        for slot,index in fixed.items():
            chosen[:,slot]=index;used[:,index]=True;spent+=salary[index];counts[:,teams[index]]+=1
        alive &= (counts<=rules['max_from_team']).all(axis=1)
        for k,slot in enumerate(order):
            allowed=eligible[slot][None,:]&~used&(counts[:,teams]<rules['max_from_team'])
            allowed &= spent[:,None]+salary[None,:]+remaining_minimum[k]<=salary_cap
            possible=allowed.any(axis=1);alive &= possible
            utility=score if correlation==0 else score+(correlation/100)*.5*scale[:,None]*pair_bonus/max(k,1)
            pick=np.argmax(np.where(allowed,utility,-np.inf),axis=1)
            ids=np.flatnonzero(alive);chosen[ids,slot]=pick[ids]
            used[ids,pick[ids]]=True;spent[ids]+=salary[pick[ids]]
            if correlation>0:pair_bonus[ids]+=positive_correlation[pick[ids]]
            counts[ids,teams[pick[ids]]]+=1
        valid=alive&(spent>=salary_min)&(spent<=salary_cap)
        valid &= (counts>0).sum(axis=1)>=rules['min_teams']
        if rules['min_games']>1:
            valid_ids=np.flatnonzero(valid)
            sorted_games=np.sort(game_ids[chosen[valid_ids]],axis=1)
            valid[valid_ids]=1+np.count_nonzero(np.diff(sorted_games,axis=1),axis=1)>=rules['min_games']
        incomplete+=int((~valid).sum())
        for row in chosen[valid]:
            canonical=tuple(sorted(row))
            if canonical in seen:duplicates+=1;continue
            seen.add(canonical);answer.append(original[row])
            if len(answer)==target:break
    return {'indices':np.asarray(answer,dtype=int).reshape(-1,size),
            'build_correlation':float(correlation),'requested':target,'attempted':attempted,'unique':len(answer),
            'rejected_incomplete_or_salary':incomplete,'duplicates':duplicates,
            'complete':len(answer)==target,'status':'experimental bounded heuristic; not live NBA build'}




def build_opponent_support(pool,outcomes,ownership,*,target=10000,seed=83):
    """Mix scenario rosters with broad ownership proposals before marginal fit.

    Proposal scores only determine which legal rosters are available. They do
    not alter game outcomes or become field probabilities; build_field fits
    those probabilities against the original validated ownership targets.
    """
    weights=np.asarray(ownership,float)
    if weights.shape!=(len(pool),) or not np.isfinite(weights).all() or (weights<0).any():
        raise ValueError('Finite ownership proposal weights aligned to pool required')
    scenario_target=max(1,target//2)
    scenario=build_candidates(pool,outcomes,target=scenario_target,seed=seed)
    rng=np.random.default_rng(seed+37)
    proposal=np.log(np.maximum(weights,.1))[None,:]+2*rng.gumbel(size=(1024,len(pool)))
    broad=build_candidates(pool,proposal,target=max(1,target-scenario_target),seed=seed+38)
    rows=np.concatenate([scenario['indices'],broad['indices']],axis=0)
    _,unique=np.unique(np.sort(rows,axis=1),axis=0,return_index=True)
    return {'indices':rows[np.sort(unique)][:target],
            'scenario_unique':scenario['unique'],'ownership_proposal_unique':broad['unique']}
