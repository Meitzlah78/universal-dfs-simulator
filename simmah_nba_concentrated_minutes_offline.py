"""Training-only empirical recipient routing. Offline, no production imports."""
import numpy as np
from scripts.expand_minutes_evidence_offline import player_key


def compile_patterns(patterns):
    result={}
    for row in patterns:
        key=(row['team'],player_key(row['donor'],row['team'])[0])
        if key in result:raise ValueError('Duplicate donor model')
        result[key]=[(player_key(p['name'],row['team'])[0],float(p['probability'])) for p in row['recipients']]
    return result

def concentrated_transfer(minutes,means,names,team,cuts,patterns,seed,*,allowed=None,allow_deep=False):
    """Route a cut pool to at most two empirically supported eligible players.

    No support => explicit unallocated pool, with donor minutes preserved.
    Deep bench means pregame minute rank >10. It needs explicit depth permission.
    Recipient roles come from observed replacements, not a positional guess.
    """
    v=np.array(minutes,float,copy=True);means=np.asarray(means,float)
    if v.ndim!=1 or v.shape!=means.shape or len(names)!=len(v) or not np.isfinite(v).all() or not np.isfinite(means).all():raise ValueError('Invalid rotation')
    if np.any((v<0)|(v>48)) or np.any(means<0) or not np.isclose(v.sum(),240):raise ValueError('Require bounded240-minute rotation')
    if np.any(v[means==0]>0):raise ValueError('Inactive-player minutes')
    keys=[player_key(n,team)[0] for n in names];rank=np.flatnonzero(means>0)[np.argsort(-means[means>0],kind='stable')]
    if len(set(keys[i] for i in rank))!=len(rank):raise ValueError('Ambiguous player identity')
    support=set(rank if allow_deep else rank[:10]);support-={i for i,c in cuts.items() if c>0}
    if allowed is not None:support&=set(allowed)
    request={}
    for i,c in cuts.items():
        if not isinstance(i,(int,np.integer)) or i not in rank or not np.isfinite(c) or c<0:raise ValueError('Invalid donor cut')
        request[i]=min(float(c),float(v[i]))
    weights=np.zeros(len(v));wanted=sum(request.values())
    for i,cut in request.items():
        model=patterns if isinstance(patterns,dict) else compile_patterns(patterns)
        for key,probability in model.get((team,keys[i]),[]):
            for j in support:
                if keys[j]==key:weights[j]+=cut*probability
    eligible=np.flatnonzero((weights>0)&(v<48))
    if len(eligible):
        rng=np.random.default_rng(seed);chosen=rng.choice(eligible,size=min(2,len(eligible)),replace=False,p=weights[eligible]/weights[eligible].sum())
    else:chosen=np.array([],int)
    room=(48-v[chosen]).sum();amount=min(wanted,room)
    if amount>0:
        for i,cut in request.items():v[i]-=amount*cut/wanted
        remaining=amount
        # Weighted water filling within the chosen pair; headroom remains hard.
        for _ in range(3):
            active=chosen[v[chosen]<48-1e-12]
            if not len(active) or remaining<1e-12:break
            allocations=np.minimum(48-v[active],remaining*weights[active]/weights[active].sum());v[active]+=allocations;remaining-=allocations.sum()
        if remaining>1e-8:raise AssertionError('Unassigned recipient transfer')
    v=np.clip(v,0.,48.);residual=240-v.sum()
    if abs(residual)>1e-8:raise AssertionError('Budget mismatch')
    if residual:
        repair=np.flatnonzero((means>0)&((48-v>abs(residual)) if residual>0 else (v>abs(residual))))
        v[repair[0]]+=residual
    return v,{'requested':wanted,'transferred':float(amount),'unallocated':float(wanted-amount),'recipients':[int(i) for i in chosen]}


def redistribute_concentrated(minutes,means,names,team,patterns,seed,*,state='neutral',transfer_budget=0.,foul_cuts=None,allow_deep=False):
    if state not in ['neutral','blowout','tight'] or not np.isfinite(transfer_budget) or transfer_budget<0:raise ValueError('Invalid script')
    means=np.asarray(means,float);v=np.array(minutes,float,copy=True);rank=np.flatnonzero(means>0)[np.argsort(-means[means>0],kind='stable')];rng=np.random.default_rng(seed);ledgers=[]
    foul_cuts={i:c for i,c in (foul_cuts or {}).items() if c>0}
    if foul_cuts:
        v,l=concentrated_transfer(v,means,names,team,foul_cuts,patterns,int(rng.integers(2**32)),allow_deep=allow_deep);ledgers.append(l)
    donors=rank[means[rank]>=28] if state=='blowout' else rank[7:] if state=='tight' else np.array([],int)
    # Blowout replacements may include other regular rotation players; no blanket <18 restriction.
    allowed=set(rank)-set(foul_cuts or {})
    if state=='tight':allowed&=set(rank[:7])
    if len(donors) and transfer_budget:
        total=v[donors].sum();cuts={int(i):float(transfer_budget*v[i]/total) for i in donors} if total else {}
        v,l=concentrated_transfer(v,means,names,team,cuts,patterns,int(rng.integers(2**32)),allowed=allowed,allow_deep=allow_deep);ledgers.append(l)
    return v,ledgers
