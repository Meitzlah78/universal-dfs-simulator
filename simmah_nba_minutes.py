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
