"""Offline NBA field-size/randomness experiment; never imported by the live UI.

Randomness is the standard deviation of a mean-one lognormal player multiplier
applied only to field-construction outcomes. It is not forecast uncertainty and
is not applied to evaluation outcomes or the user's candidate pool.
"""
import numpy as np
from simmah_nba_candidates import build_opponent_support
from simmah_nba_rules import rules_for


def build_randomized_field(pool, field_outcomes, popularity, *, contest_entries,
                           opponent_entries, randomness_pct=0, seed=83,
                           support_target=10000):
    for name,value,minimum in [('contest_entries',contest_entries,2),
                               ('opponent_entries',opponent_entries,1),
                               ('support_target',support_target,1),('seed',seed,0)]:
        if type(value) is not int or value<minimum:
            raise ValueError(name+' must be an integer at least '+str(minimum))
    if opponent_entries>=contest_entries:
        raise ValueError('Opponent entries must be smaller than total contest entries')
    if isinstance(randomness_pct,bool) or not np.isfinite(randomness_pct) or not 0<=randomness_pct<=30:
        raise ValueError('Field randomness must be between 0 and 30 percent')
    values=np.asarray(field_outcomes)
    weights=np.asarray(popularity,float)
    if values.ndim!=2 or values.shape[1]!=len(pool) or not len(values) or not np.isfinite(values).all():
        raise ValueError('Finite field-construction outcomes aligned to pool required')
    if weights.shape!=(len(pool),) or not np.isfinite(weights).all() or (weights<0).any() or not (weights>0).any():
        raise ValueError('Finite nonnegative popularity aligned to pool required')
    # Separate streams: randomness does not change the support/sampling seeds.
    randomized=values.copy()
    if randomness_pct:
        sigma=np.sqrt(np.log1p((float(randomness_pct)/100)**2))
        multiplier=np.random.default_rng(seed+7001).lognormal(-sigma*sigma/2,sigma,size=values.shape)
        randomized=values*multiplier
    support=build_opponent_support(pool,randomized,weights,target=support_target,seed=seed+1010)
    ids=np.asarray(support['indices'])
    if not len(ids):raise ValueError('No legal opponent support generated')
    _,unique=np.unique(np.sort(ids,axis=1),axis=0,return_index=True)
    ids=ids[np.sort(unique)]
    # Explicit relative-popularity assumption, not fitted ownership percentages.
    logits=.5*np.log(np.maximum(weights,.1))[ids].sum(axis=1)
    probability=np.exp(logits-logits.max());probability/=probability.sum()
    copies=np.random.default_rng(seed+1011).multinomial(opponent_entries,probability)
    keep=copies>0
    salary=np.asarray(pool['Salary'],float)[ids].sum(axis=1)
    sampled=np.bincount(ids.ravel(),weights=np.repeat(copies,ids.shape[1]),minlength=len(pool))*100/opponent_entries
    return {'indices':ids[keep],'copies':copies[keep],
            'support_indices':ids,'support_probabilities':probability,'support_copies':copies,
            'ownership_sampled':sampled,
            'settings':{'experiment':'randomized-relative-popularity-field-v1',
                'live_enabled':False,'contest_entries':contest_entries,
                'opponent_entries':opponent_entries,'randomness_pct':float(randomness_pct),
                'randomness_definition':'mean-one lognormal multiplier; percentage is multiplier standard deviation',
                'seed':seed,'randomness_seed':seed+7001,'support_seed':seed+1010,
                'sampling_seed':seed+1011,'support_target':support_target,
                'popularity_strength':.5,'popularity_floor':.1,
                'platform':rules_for(pool)['platform']},
            'diagnostics':{'generated_support':len(ids),'unique_sampled_rosters':int(keep.sum()),
                'represented_opponents':int(copies.sum()),
                'mean_salary':float(copies@salary/opponent_entries),
                'exact_cap_fraction':float(copies@(salary==rules_for(pool)['salary_cap'])/opponent_entries)}}
