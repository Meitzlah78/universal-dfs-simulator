"""Bounded joint-outcome roster search shared by all NFL DFS formats.

Each proposal optimizes a complete simulated slate outcome or the average of
a uniform sample of outcomes. Batched greedy seeds plus coordinate ascent
are a heuristic, not a claim of global optimality.
Evaluation/contest outcomes must be generated independently by the caller.
"""
import numpy as np
import pandas as pd


def offense_vs_defense_allowed(chosen, lookup):
    """Reject an offensive player facing a defense in the same roster."""
    aliases = {"LA":"LAR", "JAC":"JAX", "WSH":"WAS"}
    def team(value):
        key = str(value or "").strip().upper()
        return aliases.get(key,key) if key not in {"NAN","NONE","—","-"} else ""
    defense, offense = [], []
    for slot,name in chosen.items():
        row = lookup.get(str(name).strip(),{})
        positions = set(str(row.get("Position","")).upper().replace(" ","").split("/"))
        item = (team(row.get("Team")),team(row.get("Opponent")))
        if positions & {"D","DST","DEF"} or slot in {"D","DST","DEF"}:
            defense.append(item)
        elif positions & {"QB","RB","WR","TE","K"}:
            offense.append(item)
    return not any((dopp and oteam == dopp) or (dteam and oopp == dteam)
                   for dteam,dopp in defense for oteam,oopp in offense)


def construction_sample_size(diversity, outcome_count):
    """Map 0 to every construction sim and 1 to one, using log interpolation.

    The endpoints follow SaberSim's documented approach. Intermediate sample
    counts are Simmah's mapping, not a claim about SaberSim's private settings.
    """
    diversity = float(diversity)
    if not np.isfinite(diversity) or not 0 <= diversity <= 1:
        raise ValueError('Scenario diversity must be between zero and one')
    if outcome_count < 1:
        raise ValueError('Construction outcomes must be nonempty')
    return max(1, min(outcome_count, int(round(outcome_count ** (1.0 - diversity)))))


def sample_construction_targets(values, sample_size, batch, rng, full_mean=None):
    """Average uniformly sampled complete rows, never individual player draws.

    Random windows of a shuffled cycle are uniform subsets without replacement.
    Sharing that shuffle within a batch bounds memory even near 10,000 sims per
    candidate. Windows can overlap, so candidate samples are not independent;
    contest evaluation is generated separately by the app.
    """
    values = np.asarray(values)
    if not 1 <= sample_size <= len(values):
        raise ValueError('Invalid construction sample size')
    if sample_size == len(values) and sample_size > 1:
        return np.broadcast_to(values.mean(axis=0, dtype=np.float64) if full_mean is None else full_mean, (batch, values.shape[1])), np.full(batch, -1)
    if sample_size == 1:
        indices = rng.integers(0, len(values), batch)
        return values[indices], indices
    permutation = rng.permutation(len(values))
    cumulative = np.empty((len(values) + 1, values.shape[1]), dtype=np.float64)
    cumulative[0] = 0
    np.cumsum(values[permutation], axis=0, dtype=np.float64, out=cumulative[1:])
    start = rng.integers(0, len(values), batch)
    end = start + sample_size
    totals = cumulative[np.minimum(end, len(values))] - cumulative[start]
    totals += cumulative[np.maximum(end - len(values), 0)]
    return totals / sample_size, np.full(batch, -1)


def build_candidates(pool,outcomes,roster,target=5000,salary_min=0,salary_max=50000,
                     multipliers=None,salary_costs=None,locks=(),special_allowed=None,
                     max_from_team=None,require_both_teams=False,validator=None,
                     rng=None,progress=None,max_proposals=100000,noise=.08,penalties=None,primary_stacks=None,avoid_opposing_defense=False,
                     scenario_diversity=1.0):
    rng=np.random.default_rng() if rng is None else rng
    pool=pool.drop_duplicates('Name').reset_index(drop=True)
    names=pool['Name'].astype(str).to_numpy(object)
    if len(names)<len(roster):raise ValueError('Not enough eligible players for this roster')
    missing=set(names)-set(outcomes.columns)
    if missing:raise ValueError('Candidate outcomes are missing players: '+', '.join(sorted(missing)[:5]))
    values=outcomes.reindex(columns=names).to_numpy(dtype=np.float32)
    if not len(values) or not np.isfinite(values).all():raise ValueError('Candidate outcomes must be finite and nonempty')
    sample_size = construction_sample_size(scenario_diversity, len(values))
    full_mean = values.mean(axis=0, dtype=np.float64) if sample_size == len(values) else None
    scenario_draws = np.zeros(len(values), dtype=np.int64)
    slots=[slot for slot,_ in roster];count=len(slots)
    mult=np.ones(count) if multipliers is None else np.asarray(multipliers,float)
    salary=pd.to_numeric(pool['Salary'],errors='raise').to_numpy(float)
    costs=np.asarray(salary_costs,float) if salary_costs is not None else mult[:,None]*salary[None,:]
    if len(mult)!=count or costs.shape!=(count,len(names)) or not np.isfinite(costs).all() or (costs<=0).any():
        raise ValueError('Invalid slot multiplier or salary-cost matrix')
    positions=[set(str(p).upper().replace(' ','').split('/')) for p in pool['Position']]
    # Salary sources use D, DEF and DST for the same NFL roster position.
    for position in positions:
        if position & {'D','DEF','DST'}:position.update({'D','DEF','DST'})
    eligible=[np.array([i for i,p in enumerate(positions) if not allowed or p & allowed],dtype=int) for _,allowed in roster]
    if special_allowed is not None:eligible[0]=np.array([i for i in eligible[0] if names[i] in special_allowed])
    missing_slots=[slot for (slot,_),choices in zip(roster,eligible) if not len(choices)]
    if missing_slots:
        counts=pd.Series(pool['Position'].astype(str)).value_counts().to_dict()
        raise ValueError('No eligible players for roster slot(s): '+', '.join(missing_slots)+
                         '. Available pool positions: '+str(counts)+
                         '. Check positive projections, injury/exclusion filters and the uploaded format.')
    lookup={name:i for i,name in enumerate(names)}
    if any(name not in lookup for name in locks):raise ValueError('A locked player is unavailable')
    locked=np.array([lookup[name] for name in locks],int)
    if len(locked)>count:raise ValueError('More locks than roster slots')
    teams=pool.get('Team',pd.Series('',index=pool.index)).astype(str).str.upper().to_numpy(object)
    min_cost=np.array([costs[s,choices].min() for s,choices in enumerate(eligible)])
    max_cost=np.array([costs[s,choices].max() for s,choices in enumerate(eligible)])
    penalty=np.zeros(len(names)) if penalties is None else np.asarray(penalties,float)
    if penalty.shape!=(len(names),):raise ValueError('Ownership penalties do not align with player names')
    opponents=pool.get('Opponent',pd.Series('',index=pool.index)).astype(str).str.upper().to_numpy(object)
    conflicts = None
    if avoid_opposing_defense:
        aliases={"LA":"LAR","JAC":"JAX","WSH":"WAS"}
        normalized_teams=np.array([aliases.get(str(t).strip(),str(t).strip()) for t in teams])
        normalized_opponents=np.array([aliases.get(str(t).strip(),str(t).strip()) for t in opponents])
        defense=np.array([bool(p & {"D","DST","DEF"}) for p in positions])
        offense=np.array([bool(p & {"QB","RB","WR","TE","K"}) for p in positions])
        valid_teams=~np.isin(normalized_teams,["","NAN","NONE","—","-"])
        valid_opps=~np.isin(normalized_opponents,["","NAN","NONE","—","-"])
        facing=((normalized_teams[:,None]==normalized_opponents[None,:]) & valid_teams[:,None] & valid_opps[None,:])
        relation=facing | facing.T
        conflicts=relation & ((defense[:,None]&offense[None,:]) | (offense[:,None]&defense[None,:]))
    records=[];seen=set();proposed=0
    rejected={'incomplete_or_salary':0,'team_limit':0,'stack_rules':0,'duplicate':0}
    while len(records)<target and proposed<max_proposals:
        batch=min(256,max_proposals-proposed);proposed+=batch
        joint, scenario = sample_construction_targets(values, sample_size, batch, rng, full_mean)
        if sample_size == 1:
            scenario_draws += np.bincount(scenario, minlength=len(values))
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
        # Seed the primary stack before filling other slots. Previously stack
        # rules were checked only after unconstrained optimization, discarding
        # almost every proposal for double stacks with bring-backs.
        if primary_stacks:
            if 'QB' not in slots:raise ValueError('Primary stacks require a QB slot')
            qb_slot=slots.index('QB')
            for row in range(batch):
                if not alive[row]:continue
                desired,bringback=primary_stacks[int(rng.integers(len(primary_stacks)))]
                assigned=set(picks[row][picks[row]>=0].tolist())
                def place(player,slot):
                    picks[row,slot]=player;fixed[row,slot]=True
                    total[row]+=costs[slot,player]
                    assigned.add(player)
                if picks[row,qb_slot]<0:
                    available=[i for i in eligible[qb_slot] if i not in assigned]
                    if not available:alive[row]=False;continue
                    # Weighted by this proposal's joint QB outcome, with a
                    # probability floor so quieter scenarios remain searchable.
                    q=np.asarray(available);v=joint[row,q]
                    w=np.exp(np.clip((v-v.max())/max(float(v.std()),3),-8,0))
                    place(int(rng.choice(q,p=w/w.sum())),qb_slot)
                qb=picks[row,qb_slot];team=teams[qb];opp=opponents[qb]
                def assign_matching(allowed):
                    options=[]
                    for slot,choices in enumerate(eligible):
                        if picks[row,slot]>=0:continue
                        available=[int(i) for i in choices if i not in assigned and allowed(int(i))]
                        if available:options.append((slot,available))
                    if not options:return False
                    # Preserve FLEX for the remaining roster when possible.
                    slot,available=min(options,key=lambda pair:(len(roster[pair[0]][1]) or 99,pair[0]))
                    player=int(rng.choice(available))
                    place(player,slot)
                    return True
                stacked=sum(i>=0 and i!=qb and teams[i]==team and bool(positions[i]&{'WR','TE'}) for i in picks[row])
                if stacked>desired:alive[row]=False;continue
                for _ in range(desired-stacked):
                    if not assign_matching(lambda i:teams[i]==team and bool(positions[i]&{'WR','TE'})):
                        alive[row]=False;break
                if alive[row] and bringback and not any(i>=0 and teams[i]==opp and bool(positions[i]&{'RB','WR','TE'}) for i in picks[row]):
                    if not opp or not assign_matching(lambda i:teams[i]==opp and bool(positions[i]&{'RB','WR','TE'})):
                        alive[row]=False
        scale=np.maximum(joint.std(axis=1),1)
        # Vary the salary opportunity cost between proposals, not player outcomes.
        price=rng.uniform(0,.004,batch)
        # Keep the same search perturbation and salary opportunity cost through
        # refinement. Removing them after seeding collapses independent starts
        # onto a few identical local optima, especially at low sim diversity.
        exploration=rng.gumbel(size=joint.shape)*scale[:,None]*noise
        for slot,choices in enumerate(eligible):
            row=np.flatnonzero(alive & (picks[:,slot]<0))
            if not len(row):continue
            used=(picks[row,:,None]==choices[None,None,:]).any(axis=1)
            free=picks[row]<0;free[:,slot]=False
            low=(free*min_cost).sum(axis=1);high=(free*max_cost).sum(axis=1)
            next_total=total[row,None]+costs[slot,choices][None,:]
            feasible=(~used)&(next_total+low[:,None]<=salary_max)&(next_total+high[:,None]>=salary_min)
            if conflicts is not None:
                selected=picks[row]
                blocked=(conflicts[np.maximum(selected,0)[:,:,None],choices[None,None,:]] & (selected>=0)[:,:,None]).any(axis=1)
                feasible &= ~blocked
            objective=(joint[row[:,None],choices]-penalty[choices])*mult[slot]-price[row,None]*costs[slot,choices]
            objective+=exploration[row[:,None],choices]
            objective[~feasible]=-np.inf
            valid=feasible.any(axis=1);alive[row[~valid]]=False
            best=objective.argmax(axis=1);row=row[valid];best=best[valid]
            picks[row,slot]=choices[best];total[row]+=costs[slot,choices[best]]
        alive &= (picks>=0).all(axis=1)&(total>=salary_min)&(total<=salary_max)
        rejected['incomplete_or_salary']+=int((~alive).sum())
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
                if conflicts is not None:
                    selected=picks[row]
                    blocked=(conflicts[np.maximum(selected,0)[:,:,None],choices[None,None,:]] & (selected>=0)[:,:,None]).any(axis=1)
                    feasible &= ~blocked
                objective=(joint[row[:,None],choices]-penalty[choices])*mult[slot]-price[row,None]*costs[slot,choices]
                objective+=exploration[row[:,None],choices]
                objective[~feasible]=-np.inf
                best=objective.argmax(axis=1)
                picks[row,slot]=choices[best];total[row]=adjusted[np.arange(len(row)),best]
        for row in np.flatnonzero(alive):
            pick=picks[row]
            unique_teams,counts=np.unique(teams[pick],return_counts=True)
            if max_from_team is not None and len(counts) and counts.max()>max_from_team:
                rejected['team_limit']+=1;continue
            if require_both_teams and len(unique_teams)<2:continue
            chosen={slot:str(names[pick[i]]) for i,slot in enumerate(slots)}
            if validator is not None and not validator(chosen):
                rejected['stack_rules']+=1;continue
            special=count==6 and mult[0]!=1
            key=(int(pick[0]),tuple(sorted(map(int,pick[1:])))) if special else tuple(sorted(map(int,pick)))
            if key in seen:
                rejected['duplicate']+=1;continue
            seen.add(key)
            records.append({**chosen,'Salary':int(round(total[row])),
                'Build Scenario':int(scenario[row]) if sample_size == 1 else None,
                'Build Simulations':sample_size,
                'Scenario Score':float((joint[row,pick]*mult).sum())})
            if len(records)>=target:break
        if progress:progress(min(1,len(records)/target),f'Building from joint outcomes: {len(records):,} / {target:,}')
    result=pd.DataFrame(records)
    result.attrs.update(engine='joint-outcome-search-v5',proposals=proposed,target=target,rejected=rejected,stack_seeded=bool(primary_stacks),
                        scenario_diversity=float(scenario_diversity),
                        construction_simulations_per_candidate=sample_size,
                        scenario_unique_draws=int(np.count_nonzero(scenario_draws)) if sample_size == 1 else None)
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
