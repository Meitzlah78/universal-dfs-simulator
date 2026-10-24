"""Experimental external-mean anchoring through event allocation parameters."""
from dataclasses import replace
import numpy as np
from simmah_nba_engine import simulate_game


def fit_player_means(rotations,profiles,rates,targets,seed,overtime_rotations=None,iterations=5,platform='FanDuel'):
    """Fit allocation weights and bounded team assist rates, never scale scores.

    Team point probabilities remain fixed from market calibration. Assist rates
    adjust the aggregate fantasy-point budget; this is an explicit modeling
    assumption, not a provider-projected assist forecast. Return residuals rather
    than claiming arbitrary projection vectors are simultaneously attainable.
    """
    desired=np.asarray(targets,float);weights=np.asarray(profiles,float).copy();models=list(rates)
    if desired.shape!=weights.shape[:2] or not np.isfinite(desired).all() or (desired<0).any():
        raise ValueError('Finite nonnegative player targets aligned to both teams required')
    if not isinstance(iterations,int) or iterations<1:raise ValueError('Positive fitting budget required')
    if ((desired>0)&(weights.sum(axis=2)<=0)).any():raise ValueError('Positive targets require supported player roles')
    size=weights.shape[1];active=desired>0
    if not active.any():raise ValueError('Positive external player projections required')
    def run(run_seed):
        return simulate_game(rotations,weights,models,run_seed,overtime_rotations=overtime_rotations,platform=platform)
    initial=None
    for _ in range(iterations):
        result=run(seed)
        means=result['scores'].mean(axis=0,dtype=np.float64).reshape(2,size)
        if initial is None:initial=float(abs(means-desired)[active].mean())
        factor=np.clip(desired/np.maximum(means,.1),.5,2.)**.7
        # Untargeted rotation-only reserves retain their historical event
        # roles. Padding already has zero weights; missing projections are
        # not hard zero-point targets.
        factor=np.where(active,factor,1.)
        weights*=factor[:,:,None]
        # Per-role normalization only removes irrelevant common scale.
        sums=weights.sum(axis=1,keepdims=True)
        weights=np.divide(weights,sums,out=np.zeros_like(weights),where=sums>0)
        for team in range(2):
            fg=result['stats'][:,team*size:(team+1)*size,0].sum(axis=1).mean()
            difference=desired[team,active[team]].sum()-means[team,active[team]].sum()
            assisted=np.clip(models[team].assisted+difference/max(1.5*fg,1),.05,.95)
            models[team]=replace(models[team],assisted=float(assisted))
    # Separate diagnostic seed: fitted observations are not their own validation.
    result=run(seed+65537)
    means=result['scores'].mean(axis=0,dtype=np.float64).reshape(2,size)
    residual=means-desired
    report={'initial_fit_mae':initial,'validation_mae':float(abs(residual)[active].mean()),
            'validation_max_error':float(abs(residual)[active].max()),
            'validation_means':means.tolist(),'targets':desired.tolist(),
            'team_assist_probabilities':[m.assisted for m in models],
            'status':'experimental event allocation fit; bounded assist-budget assumption; inspect residuals'}
    return weights,models,report
