"""Experimental one-minute rotation schedules with exact court occupancy.

Minute totals are preserved after integer apportionment. This is a feasibility
bridge, not a learned substitution/coaching model.
"""
import numpy as np


def build_rotation(minutes, seed, player_offset=0, period_minutes=48):
    """Map batch x player minutes to batch x period_minutes x 5 player indices.

    Caller must include every reserve receiving minutes; latent unmodeled bench
    minutes cannot silently disappear. Sub-minute resolution is rounded while
    retaining 240 total minutes and a maximum of 48 per player.
    """
    if not isinstance(period_minutes,int) or not 1<=period_minutes<=48:
        raise ValueError("Period length must be an integer from 1 to 48")
    budget=5*period_minutes
    values=np.asarray(minutes,float)
    if (values.ndim!=2 or values.shape[1]<5 or not len(values)
            or not np.isfinite(values).all() or (values<0).any()
            or (values>period_minutes).any()):
        raise ValueError('Finite complete team minutes within period length required')
    if not np.allclose(values.sum(axis=1),budget,rtol=0,atol=1e-6):
        raise ValueError('Complete rotation must supply five times the period length')
    if not isinstance(player_offset,(int,np.integer)) or player_offset<0:
        raise ValueError('Nonnegative integer player offset required')
    rng=np.random.default_rng(seed)
    counts=np.floor(values).astype(int)
    # Largest remainder apportionment; random ties keep player order neutral.
    priority=values-counts+rng.random(values.shape)*1e-10
    order=np.argsort(-priority,axis=1)
    extra=budget-counts.sum(axis=1)
    for rank in range(values.shape[1]):
        ids=np.flatnonzero(extra>rank)
        counts[ids,order[ids,rank]]+=1
    result=np.full((len(values),period_minutes,5),-1,dtype=np.int32)
    capacity=np.full((len(values),period_minutes),5,dtype=int)
    # Bipartite degree construction: place highest-degree players in the
    # minutes with greatest remaining capacity. No player repeats in a minute.
    player_order=np.argsort(-counts,axis=1,kind='stable')
    batch=np.arange(len(values))
    for rank in range(values.shape[1]):
        players=player_order[:,rank]
        degree=counts[batch,players]
        court_order=np.argsort(-(capacity+rng.random(capacity.shape)*.01),axis=1)
        for k in range(period_minutes):
            ids=np.flatnonzero(degree>k)
            if not len(ids):continue
            minute=court_order[ids,k]
            slot=5-capacity[ids,minute]
            if (slot>=5).any():raise ValueError('Infeasible rotation degree sequence')
            result[ids,minute,slot]=players[ids]+player_offset
            capacity[ids,minute]-=1
    if (capacity!=0).any() or (result<0).any():
        raise ValueError('Incomplete on-court rotation')
    return result
