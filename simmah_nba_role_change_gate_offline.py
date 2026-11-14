"""Offline role-change gate. No provider, position, news or outcome features."""
import numpy as np
from simmah_nba_minutes import allocate_minutes


def gated_minutes(base_raw,long_raw,fast_raw,threshold=3.,mode='baseline5'):
    base=np.asarray(base_raw,float);long=np.asarray(long_raw,float);fast=np.asarray(fast_raw,float)
    if base.ndim!=1 or base.shape!=long.shape or base.shape!=fast.shape or not all(np.isfinite(a).all() for a in [base,long,fast]) or any(np.any((a<0)|(a>48)) for a in [base,long,fast]):raise ValueError('Matched bounded historical weights required')
    if not np.isfinite(threshold) or threshold<0 or mode not in ['baseline5','fast3']:raise ValueError('Invalid frozen gate')
    core=base>=28;bench=base<18;rise=core&((base-long)>threshold)
    weights=np.where(core,long,np.where(bench,fast,base));weights=np.where(rise,base if mode=='baseline5' else fast,weights)
    return allocate_minutes(weights[None,:])[0],rise


def starter_transition(expected,prior_started,prior_played):
    """Diagnostic only: saved expected starter vs verified previous-game role."""
    if expected is None or prior_started is None or prior_played is not True:return 'unknown'
    if expected and not prior_started:return 'expected_promotion'
    if not expected and prior_started:return 'expected_bench_change'
    return 'stable_expected_starter' if expected else 'stable_expected_bench'
