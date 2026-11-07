"""Experimental regulation minutes: capped players and conserved team minutes.

This is not a calibrated injury or blowout probability model. Callers supply the
active rotation, minute uncertainty and (optional) explicit game-script flags.
"""
import numpy as np


def allocate_minutes(weights, total=240., cap=48.):
    """Proportional water filling, capped per player, for a batch of rotations."""
    weights=np.asarray(weights,dtype=float)
    if weights.ndim!=2 or not np.isfinite(weights).all() or (weights<0).any():
        raise ValueError('Minute weights must be a finite nonnegative matrix')
    support=weights>0
    if np.any(support.sum(axis=1)*cap < total-1e-8):
        raise ValueError('Active rotation cannot supply the required team minutes')
    low=np.zeros(len(weights));high=np.ones(len(weights))
    for _ in range(60):
        short=np.minimum(weights*high[:,None],cap).sum(axis=1)<total
        if not short.any():break
        high[short]*=2
    for _ in range(60):
        mid=(low+high)/2
        short=np.minimum(weights*mid[:,None],cap).sum(axis=1)<total
        low=np.where(short,mid,low);high=np.where(short,high,mid)
    return np.minimum(weights*high[:,None],cap)


def simulate_minutes(rotation, n, seed, blowout=None):
    """Return active-player minutes and unmodeled bench minutes for one team.

    Required columns: Projected Minutes, Minutes SD, Active. Optional Starter.
    Five latent bench slots absorb minutes without inventing player projections.
    Missing minutes are rejected rather than inferred from fantasy projections.
    A supplied blowout flag reduces starter weights; it does not forecast flags.
    """
    mean=np.asarray(rotation['Projected Minutes'],float)
    sd=np.asarray(rotation['Minutes SD'],float)
    active=np.asarray(rotation['Active'],bool)
    if n<1 or not np.isfinite(mean).all() or not np.isfinite(sd).all():
        raise ValueError('Finite projected minutes and uncertainty are required')
    if (mean<0).any() or (mean>48).any() or (sd<0).any():
        raise ValueError('Invalid projected minutes or uncertainty')
    mean=np.where(active,mean,0)
    if mean.sum()>240+1e-6:
        raise ValueError('Projected team minutes exceed 240; review the rotation')
    rng=np.random.default_rng(seed)
    # Shared regulation budget creates competition for playing time. No player
    # draws a full independent game of minutes on top of the team total.
    weights=np.maximum(mean+rng.normal(size=(n,len(mean)))*sd,1e-8)
    weights[:,~active | (mean==0)]=0
    if blowout is not None:
        flags=np.asarray(blowout,bool)
        if flags.shape!=(n,):raise ValueError('One blowout flag is required per scenario')
        starters=np.asarray(rotation.get('Starter',mean>=28),bool)
        weights *= np.where(flags[:,None] & starters[None,:],.8,1.)
    residual=max(0.,240-mean.sum())
    # Explicit reserve volume, including unprojected roster members; no fantasy
    # score is assigned to these latent reserves.
    bench=np.full((n,5),max(residual/5,1e-8))
    minutes=allocate_minutes(np.column_stack([weights,bench]))
    return minutes[:,:len(mean)],minutes[:,len(mean):].sum(axis=1)


def draw_regulation_minutes(means, trials, seed):
    """Exchange minutes between teammates, preserving each projection in expectation.

    Four rounds of random pairs; each bounded transfer has zero conditional
    mean. Variance scales are trial assumptions, not fitted coaching effects.
    """
    means=np.asarray(means,float)
    if (means.ndim!=1 or not np.isfinite(means).all() or (means<0).any()
            or (means>48).any() or abs(means.sum()-240)>1e-6 or trials<1):
        raise ValueError('Complete 240-minute regulation team and positive trials required')
    v=np.tile(means,(trials,1))
    active=np.flatnonzero((means>0)&(means<48))
    width=len(active)//2
    if not width:return v
    # High-minute players have smaller swings. A partner with a tight
    # role limits the transfer. No multiplication of bench mean minutes.
    sd=np.interp(means,[0,10,24,36,48],[0,5,5,3,0])
    rng=np.random.default_rng(seed)
    row=np.arange(trials)[:,None]
    for _ in range(4):
        order=active[np.argsort(rng.random((trials,len(active))),axis=1)]
        a,b=order[:,:width],order[:,width:2*width]
        step=np.minimum(sd[a],sd[b])/2
        plus=np.minimum(np.minimum(48-v[row,a],v[row,b]),step)
        minus=np.minimum(np.minimum(v[row,a],48-v[row,b]),step)
        prob=np.divide(minus,plus+minus,out=np.zeros_like(minus),where=plus+minus>0)
        transfer=np.where(rng.random(prob.shape)<prob,plus,-minus)
        v[row,a]+=transfer
        v[row,b]-=transfer
    return np.clip(v,0,48)


def draw_wider_minutes(means,trials,seed):
    """One extra mean-neutral reserve/donor exchange after normal variability."""
    means=np.asarray(means,float)
    seq=seed if isinstance(seed,np.random.SeedSequence) else np.random.SeedSequence(seed)
    v=draw_regulation_minutes(means,trials,seq)
    rng=np.random.default_rng(np.random.SeedSequence(seq.entropy,spawn_key=(*seq.spawn_key,0),pool_size=seq.pool_size))
    reserve=np.flatnonzero((means>0)&(means<18))
    donor=np.flatnonzero((means>=18)&(means<48))
    ranks=min(len(reserve),len(donor))
    if not ranks:return v
    rows=np.arange(trials)
    r=reserve[np.argsort(rng.random((trials,len(reserve))),axis=1)]
    d=donor[np.argsort(rng.random((trials,len(donor))),axis=1)]
    for k in range(ranks):
        i,j=r[:,k],d[:,k]
        swing=np.minimum.reduce([np.full(trials,12.),48-v[rows,i],v[rows,j],4*v[rows,i],4*(48-v[rows,j])])
        transfer=swing*np.where(rng.random(trials)<.2,1.,-.25)
        v[rows,i]+=transfer
        v[rows,j]-=transfer
    return v
