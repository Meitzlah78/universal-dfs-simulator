"""Offline guided proposal challenger. Never imported by production."""
import numpy as np
from simmah_nba_rules import rules_for


def environment_weights(pool):
    required={'Team','Opponent','Game Total','Team Implied Points'}
    if not required<=set(pool):raise ValueError('Verified saved game/side totals required')
    games=sorted({tuple(sorted((str(r.Team),str(r.Opponent)))) for r in pool.itertuples()})
    totals=[];margins=[]
    for pair in games:
        group=pool.loc[pool['Team'].astype(str).isin(pair)]
        total=group['Game Total'].dropna().astype(float).unique()
        sides=[group.loc[group['Team'].astype(str)==t,'Team Implied Points'].dropna().astype(float).unique() for t in pair]
        if len(total)!=1 or any(len(v)!=1 for v in sides):raise ValueError('Unambiguous two-sided saved market required')
        pts=np.array([v[0] for v in sides]);game_total=float(total[0])
        if not np.isfinite(pts).all() or (pts<=0).any() or not np.isfinite(game_total) or game_total<=0 or abs(pts.sum()-game_total)>.1:raise ValueError('Inconsistent saved game totals')
        totals.append(game_total);margins.append(abs(pts[0]-pts[1]))
    logits=(np.array(totals)-np.mean(totals))/15-np.array(margins)/10
    weights=np.exp(logits-logits.max());weights/=weights.sum()
    return games,weights


def build_candidates(pool,outcomes,target=5000,seed=83,salary_min=0,salary_cap=None,
                     max_attempts=200000,batch_size=512,correlation=0,fixed_slots=None,excluded_indices=None,search_noise=.15,proposal_weights=None,salary_aware=False,environment_guidance=None):
    """Return original pool-row indices in uploaded slot order, never filler duplicates.

    Candidates use individual shared-slate outcomes plus modest search noise.
    This is bounded heuristic search, not an exhaustive optimizer or portfolio
    selector. Evaluation must use separately simulated outcomes.
    """
    if proposal_weights is not None:
        proposal_weights=np.asarray(proposal_weights,float)
        if proposal_weights.shape!=(len(pool),) or not np.isfinite(proposal_weights).all() or (proposal_weights<0).any():
            raise ValueError('Finite nonnegative proposal weights aligned to pool required')
    rules=rules_for(pool);eligibility=rules['eligibility'];size=len(rules['slots'])
    salary_cap=rules['salary_cap'] if salary_cap is None else salary_cap
    values=np.asarray(outcomes,float)
    if values.ndim!=2 or values.shape[1]!=len(pool) or not len(values) or not np.isfinite(values).all():
        raise ValueError('Finite simulation rows aligned to the full NBA pool required')
    if any(not isinstance(v,int) or v<1 for v in (target,max_attempts,batch_size)):
        raise ValueError('Positive integer search limits required')
    if not 0<=salary_min<=salary_cap:raise ValueError('Invalid salary range')
    if not np.isfinite(search_noise) or not 0<=search_noise<=2:raise ValueError('Candidate search noise must be between 0 and 2')
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
    if salary_aware and np.ptp(salary)>0:
        # Estimate the price of one more salary dollar on this slate.
        # Discount it only in search utilities; evaluation uses raw game scores.
        centered_salary=salary-salary.mean()
        points=projection[original]
        valid=np.isfinite(points)&(points>0)
        x=salary[valid]-salary[valid].mean() if valid.any() else np.array([])
        if x@x>0:
            slope=max(0.,float(x@(points[valid]-points[valid].mean())/(x@x)))
            values=values-slope*centered_salary
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
    # Per-slot maxima can reuse a player, so this is an optimistic bound.
    # It only removes picks that cannot possibly reach the floor.
    maximum = [salary[eligible[slot]].max() for slot in order]
    remaining_maximum = [sum(maximum[k + 1:]) for k in range(len(order))]
    if rules['min_games']>1:
        game_keys=[str(tuple(sorted((str(r.Team),str(r.Opponent))))) for r in players.itertuples()]
        _,game_ids=np.unique(game_keys,return_inverse=True)
    env_rng=None;game_probabilities=None
    if environment_guidance is not None:
        focus=float(environment_guidance['focus_probability']);strength=float(environment_guidance['utility_bonus_scale'])
        if not np.isfinite([focus,strength]).all() or not 0<=focus<=1 or not 0<=strength<=1:raise ValueError('Invalid bounded environment policy')
        env_games,game_probabilities=environment_weights(pool)
        env_ids=np.array([env_games.index(tuple(sorted((str(r.Team),str(r.Opponent))))) for r in players.itertuples()])
        env_rng=np.random.default_rng(np.random.SeedSequence([seed,9017]))
    rng=np.random.default_rng(seed);seen=set();answer=[];attempted=0;incomplete=0;duplicates=0
    while attempted<max_attempts and len(answer)<target:
        n=min(batch_size,max_attempts-attempted);attempted+=n
        if proposal_weights is None:
            score=values[rng.integers(len(values),size=n)].copy()
        else:
            # Fresh proposals each batch: reusing a finite bank creates an
            # artificial ceiling on distinct full-contest opponent rosters.
            score=np.log(np.maximum(proposal_weights[original],.001))[None,:]+rng.gumbel(size=(n,len(players)))
        scale=np.maximum(np.std(score,axis=1),1)
        score+=rng.gumbel(size=score.shape)*scale[:,None]*search_noise
        if env_rng is not None:
            focus_game=env_rng.choice(len(env_games),size=n,p=game_probabilities)
            active=env_rng.random(n)<focus
            score+=strength*scale[:,None]*active[:,None]*(focus_game[:,None]==env_ids[None,:])
        chosen=np.full((n,size),-1,dtype=int);used=np.zeros((n,len(players)),bool)
        pair_bonus=np.zeros_like(score)
        spent=np.zeros(n);counts=np.zeros((n,teams.max()+1),int);alive=np.ones(n,bool)
        for slot,index in fixed.items():
            chosen[:,slot]=index;used[:,index]=True;spent+=salary[index];counts[:,teams[index]]+=1
        alive &= (counts<=rules['max_from_team']).all(axis=1)
        for k,slot in enumerate(order):
            allowed=eligible[slot][None,:]&~used&(counts[:,teams]<rules['max_from_team'])
            allowed &= spent[:,None]+salary[None,:]+remaining_minimum[k]<=salary_cap
            if salary_min > 0:
                allowed &= spent[:, None] + salary[None, :] + remaining_maximum[k] >= salary_min
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
            'complete':len(answer)==target,'environment_guidance':environment_guidance,'environment_game_weights':None if game_probabilities is None else dict(zip(map(str,env_games),game_probabilities.tolist())),'live_enabled':False,'status':'experimental bounded heuristic; not live NBA build'}



