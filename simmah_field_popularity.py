"""Explicit fallback preferences when pregame ownership is unavailable.

These are sampling weights, not projected ownership percentages. No contest
results, settled ownership, ranks or player identity enter the calculation.
"""
import numpy as np
import pandas as pd


def estimated_field_weights(pool, fallback_scores):
    points=np.asarray(fallback_scores,float)
    if points.shape!=(len(pool),):raise ValueError('Field score inputs do not match player pool')
    if 'Projection' in pool:
        # Posted external projections anchor public preferences independently of
        # the simulator's fitted means. Only missing values use supplied scores.
        posted=pd.to_numeric(pool['Projection'],errors='coerce').to_numpy(float)
        points=np.where(np.isfinite(posted),posted,points)
    points=np.where(np.isfinite(points)&(points>0),points,0.)
    if not points.any():raise ValueError('No positive projection inputs for opponent preferences')
    quality=points/points.max()
    value=np.ones(len(pool))
    if 'Salary' in pool:
        salary=pd.to_numeric(pool['Salary'],errors='coerce').to_numpy(float)
        good=np.isfinite(salary)&(salary>0)
        efficiency=np.divide(points,salary,out=np.zeros(len(pool)),where=good)
        if (efficiency>0).any():value=efficiency/efficiency.max()
    # Magnitude matters: rank-percentile floors gave near-zero backup players
    # substantial weight. Quadratic quality plus linear salary efficiency favors
    # competitive projected rosters while retaining stochastic construction.
    weights=quality**2*value
    return weights/weights.max()
