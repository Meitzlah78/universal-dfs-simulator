"""Legal tournament baseline and batched full-roster opponent proposals.

A QB plus one WR/TE is an explicit modeling assumption, not a learned stack
frequency. It is independent of the user's selected candidate stack rules.
"""
import numpy as np


def classic_tournament_mask(picks, teams, positions, max_from_team=8, require_stack=True):
    picks=np.asarray(picks,dtype=int)
    teams=np.asarray(teams,dtype=str)
    positions=np.asarray(positions,dtype=str)
    if picks.ndim!=2 or picks.shape[1]!=9:
        raise ValueError('Classic fields require nine roster slots')
    unique=np.all(np.diff(np.sort(picks,axis=1),axis=1)!=0,axis=1)
    roster_teams=teams[picks]
    # Site-specific team cap (DK eight; FD four).
    team_counts=(roster_teams[:,:,None]==roster_teams[:,None,:]).sum(axis=2)
    legal_teams=team_counts.max(axis=1)<=max_from_team
    skills=picks[:,1:8]
    pass_catcher=np.array([bool(set(p.split('/')) & {'WR','TE'}) for p in positions],dtype=bool)
    stacked=((teams[skills]==teams[picks[:,0],None]) & pass_catcher[skills]).any(axis=1)
    return unique & legal_teams & (stacked if require_stack else True)


def build_full_roster_field(pool, weights, slots, target, rng=None, progress=None, max_proposals=None, platform="FanDuel", salary_counts=None, construction_distribution=None):
    """Shared batched full-roster opponent sampler with site-specific rules.

    Keeps the existing salary acceptance curve, ownership/mean blend, QB stack,
    team limit and natural duplicate rosters. Never samples evaluation outcomes.
    """
    import pandas as pd
    rng=np.random.default_rng() if rng is None else rng
    target=int(target)
    draftkings=str(platform).casefold() in {"draftkings", "dk"}
    cap,floor,team_limit=(50000,48500,8) if draftkings else (60000,59000,4)
    from simmah_field_construction import construction_labels, allocate_counts
    learned_construction = None
    if construction_distribution is not None:
        learned_construction=np.asarray(construction_distribution,float)
        if learned_construction.shape!=(6,):raise ValueError("Expected six construction frequencies")
        construction_remaining=allocate_counts(learned_construction,target)
    names=pool.Name.astype(str).to_numpy()
    salaries=pd.to_numeric(pool.Salary,errors='raise').to_numpy(float)
    means=pd.to_numeric(pool.get('MeanPoints',pool.Projection),errors='coerce').fillna(pool.Projection).to_numpy(float)
    positions=pool.Position.astype(str).str.upper().to_numpy()
    teams=pool.Team.astype(str).to_numpy()
    opponents=pool.get("Opponent",pd.Series("",index=pool.index)).fillna("").astype(str).to_numpy()
    if learned_construction is not None and (opponents=="").any():
        raise ValueError("Learned bring-backs require verified opponents")
    weights=np.asarray(weights,float)
    if weights.shape!=(len(pool),) or not np.isfinite(weights).all():raise ValueError('Invalid field weights')
    if not np.isfinite(salaries).all() or (salaries<=0).any():raise ValueError('Invalid field salaries')
    if not np.isfinite(means).all():raise ValueError('Invalid field means')
    allowed=[{'RB','WR','TE'} if s=='FLEX' else {'D','DST','DEF'} if s in {'D','DST'} else {s.rstrip('123')} for s in slots]
    eligible=[np.array([i for i,p in enumerate(positions) if set(p.split('/'))&a],int) for a in allowed]
    if len(slots)!=9 or any(not len(c) for c in eligible):raise ValueError('Incomplete full-roster player pool')
    minimum=np.array([salaries[c].min() for c in eligible]);maximum=np.array([salaries[c].max() for c in eligible])
    # Dividing each row's means by their mean is a scalar factor and cancels
    # when weights normalize, so precompute the exact relative weights once.
    # Probabilities may already sum to one. An absolute floor such as .01
    # flattens a 267-player normalized vector into almost uniform sampling.
    # Use a relative floor so raw and normalized weights are equivalent.
    nonnegative=np.maximum(weights,0)
    relative_floor=float(nonnegative.max())*1e-8 if nonnegative.max()>0 else 1.
    base=np.maximum(nonnegative,relative_floor)*(1 if draftkings else np.maximum(means,.01)**.20)
    acceptance={60000:1.,59900:.90,59800:.72,59700:.58,59600:.46,59500:.36,59400:.24,59300:.18,59200:.13,59100:.09,59000:.06}
    learned_salary = None
    if salary_counts is not None:
        learned_salary = {int(k):float(v) for k,v in salary_counts.items()
                          if floor <= int(k) <= cap and float(v)>0}
        if not learned_salary or not all(np.isfinite(v) for v in learned_salary.values()):
            raise ValueError("Invalid historical salary distribution")
    limit=max(300000,target*150) if max_proposals is None else int(max_proposals)
    chunks=[];accepted=0;attempted=0
    while accepted<target and attempted<limit:
        n=min(4096,limit-attempted);attempted+=n
        picks=np.full((n,9),-1,int);total=np.zeros(n);alive=np.ones(n,bool)
        if learned_construction is not None:
            requested=rng.choice(6,n,p=construction_remaining/construction_remaining.sum())
            stack_goal=requested//2;back_goal=requested%2
            # Seed required pass catchers; choose the bring-back slot separately
            # so RB/TE bring-backs remain possible, not just opposing WRs.
            back_choices=np.broadcast_to(np.arange(1,8),(n,7))
            permitted=~(((back_choices==3)&(stack_goal[:,None]>=1)) | ((back_choices==4)&(stack_goal[:,None]>=2)))
            draw=rng.random((n,7));draw[~permitted]=-1
            back_slot=1+draw.argmax(axis=1)

        for slot,choices in enumerate(eligible):
            used=(picks[:,:slot,None]==choices[None,None,:]).any(axis=1)
            next_total=total[:,None]+salaries[choices]
            feasible=(~used)&(next_total+minimum[slot+1:].sum()<=cap)&(next_total+maximum[slot+1:].sum()>=floor)
            if learned_construction is not None and slot:
                qb_team=teams[picks[:,0]];qb_opp=opponents[picks[:,0]]
                candidate_teams=teams[choices][None,:]
                catcher=np.array([bool(set(p.split('/'))&{'WR','TE'}) for p in positions[choices]])[None,:]
                offensive=np.array([bool(set(p.split('/'))&{'RB','WR','TE'}) for p in positions[choices]])[None,:]
                same=candidate_teams==qb_team[:,None];opposing=candidate_teams==qb_opp[:,None]
                required=((stack_goal>=1)&(slot==3)) | ((stack_goal>=2)&(slot==4))
                feasible &= (~required[:,None]) | (same & catcher)
                forbidden=((stack_goal==0) | ((stack_goal==1)&(slot!=3)))[:,None]
                feasible &= ~(forbidden & same & catcher)
                feasible &= ~((back_goal==0)[:,None] & opposing & offensive)
                required_back=(back_goal==1)&(back_slot==slot)
                feasible &= (~required_back[:,None]) | (opposing & offensive)
            cumulative=np.cumsum(np.where(feasible,base[choices],0),axis=1)
            mass=cumulative[:,-1];alive &= mass>0
            draw=rng.random(n)*mass
            index=(cumulative<=draw[:,None]).sum(axis=1).clip(max=len(choices)-1)
            picks[:,slot]=choices[index];total+=salaries[picks[:,slot]]
        valid=alive&(total>=floor)&(total<=cap)&classic_tournament_mask(picks,teams,positions,max_from_team=team_limit,require_stack=learned_construction is None)
        if draftkings:
            viable=np.flatnonzero(valid)
            if len(viable):
                points=means[picks[viable]].sum(axis=1)
                z=np.clip((points-np.median(points))/max(float(points.std()),1),-3,3)
                spend=np.clip((total[viable]-48500)/1200,-3,1.25)
                skills=picks[viable,1:8]
                catcher=np.array([bool(set(p.split('/'))&{'WR','TE'}) for p in positions])
                stacks=((teams[skills]==teams[picks[viable,0],None])&catcher[skills]).sum(axis=1)
                human=np.exp(.85*z+.55*spend)*np.where(stacks>=2,2.,1.45)
                # Accept each independent proposal at most once. Duplicate
                # rosters may still arise naturally across proposals.
                keep=rng.random(len(viable)) < human/human.max()
                selected=viable[keep]
                rng.shuffle(selected)
                selected=selected if learned_construction is not None else selected[:target-accepted]
            else:selected=viable
            chosen=picks[selected];cost=total[selected]
        elif learned_salary:
            viable=np.flatnonzero(valid)
            if len(viable):
                costs=total[viable].astype(int)
                values,counts=np.unique(costs,return_counts=True)
                source=dict(zip(values,counts))
                # Correct for proposal frequency: an acceptance curve alone
                # cannot reproduce a historical salary distribution.
                mass=np.array([learned_salary.get(int(v),0)/source[v] for v in costs])
                if mass.sum()>0:
                    # Independent rejection keeps each generated proposal at
                    # most once. Resampling a small batch with replacement
                    # manufactured many copies of otherwise rare rosters.
                    keep=rng.random(len(viable)) < mass/mass.max()
                    selected=viable[keep]
                    rng.shuffle(selected)
                    selected=selected if learned_construction is not None else selected[:target-accepted]
                else:selected=np.array([],int)
            else:selected=viable
            chosen=picks[selected];cost=total[selected]
        else:
            probability=np.array([acceptance.get(int(s),.01 if s>=58000 else .002) for s in total])
            valid &= rng.random(n)<=probability
            chosen=picks[valid];cost=total[valid]
            if learned_construction is None:
                chosen=chosen[:target-accepted];cost=cost[:target-accepted]
        if len(chosen) and learned_construction is not None:
            labels=construction_labels(chosen,teams,positions,opponents)
            selected=[]
            for group in range(6):
                rows=np.flatnonzero(labels==group);rng.shuffle(rows)
                keep=rows[:construction_remaining[group]]
                selected.extend(keep.tolist());construction_remaining[group]-=len(keep)
            selected=np.asarray(selected,int);chosen=chosen[selected];cost=cost[selected]
        if len(chosen):
            data={slot:names[chosen[:,i]] for i,slot in enumerate(slots)}
            data.update(Salary=cost.astype(int),ProjectedPoints=np.round(means[chosen].sum(axis=1),2))
            if learned_construction is not None:
                data["Construction Group"]=construction_labels(chosen,teams,positions,opponents)
            chunks.append(pd.DataFrame(data));accepted+=len(chosen)
        if progress:progress(min(1,accepted/max(target,1)),f'Building {platform} opponent field: {accepted:,} / {target:,}')
    if accepted<target:raise ValueError(f'Built {accepted:,} of {target:,} {platform} opponents after {attempted:,} proposals; check player availability and salary feasibility')
    result=pd.concat(chunks,ignore_index=True) if chunks else pd.DataFrame(columns=list(slots)+['Salary','ProjectedPoints'])
    result.attrs.update(proposals=attempted,target=target,engine='batched-full-roster-field-v7',platform=platform, salary_model='historical distribution within supported salary range' if learned_salary else 'baseline')
    if learned_construction is not None:
        result.attrs['construction_distribution']=(learned_construction/learned_construction.sum()).tolist()
    return result


# Existing callers retain their FanDuel defaults.
def build_fanduel_full_field(pool, weights, slots, target, rng=None, progress=None, max_proposals=None):
    return build_full_roster_field(pool, weights, slots, target, rng, progress, max_proposals, platform="FanDuel")
