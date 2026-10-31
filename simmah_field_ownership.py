"""Fit final full-roster field marginals without changing individual lineups.

Select each independently generated proposal at most once. Salary bucket quotas
are retained, and no realized or simulated contest outcomes enter the fit.
"""
import numpy as np


def has_ownership_targets(pool):
    import pandas as pd
    if 'Projected Ownership' not in pool:
        return False
    own = pd.to_numeric(pool['Projected Ownership'], errors='coerce')
    return bool((own.notna() & own.between(0,100)).sum() >= 10 and own.fillna(0).sum() > 0)


def quota_probabilities(weights,quota):
    """Capped proportional inclusion probabilities with an exact feasible quota.

    Solve the saturated portion directly rather than stopping an iterative
    normalization while concentrated probabilities still have missing mass.
    """
    weights=np.asarray(weights,float);quota=int(quota)
    if not np.isfinite(weights).all() or (weights<0).any():raise ValueError('Invalid inclusion weights')
    result=np.zeros(len(weights));positive=weights>0
    if quota<0 or quota>positive.sum():raise ValueError('Insufficient inclusion capacity')
    if quota==0:return result
    if quota==positive.sum():result[positive]=1.;return result
    w=weights[positive]/weights[positive].max()
    ordered=np.sort(w)[::-1]
    suffix=np.cumsum(ordered[::-1])[::-1]
    saturated=np.arange(quota+1)
    scale=(quota-saturated)/suffix[saturated]
    index=np.flatnonzero(scale*ordered[saturated]<=1)[0]
    result[positive]=np.minimum(1,w*scale[index])
    return result


def calibrate_field_ownership(field, pool, slots, target, rng=None, iterations=160):
    import pandas as pd
    target = int(target)
    if not has_ownership_targets(pool) or target <= 0:
        return field.iloc[:max(0,target)].copy(), pd.DataFrame()
    if target > len(field):
        raise ValueError('Ownership calibration needs at least the requested field size')
    rng = np.random.default_rng() if rng is None else rng
    if pool.Name.duplicated().any():
        raise ValueError('Ambiguous player names in ownership calibration')
    names = pool.Name.astype(str).tolist()
    index = {n:i for i,n in enumerate(names)}
    picks = field[slots].astype(str).apply(lambda c:c.map(index)).to_numpy()
    if pd.isna(picks).any():
        raise ValueError('Unknown field player in ownership calibration')
    picks = picks.astype(int)
    own = pd.to_numeric(pool['Projected Ownership'],errors='coerce').to_numpy(float)
    known = np.isfinite(own) & (own >= 0) & (own <= 100)
    desired = np.where(known,own/100,0)
    # Retain learned joint stack/bring-back mix and conditional salary counts.
    from simmah_field_construction import construction_quotas
    groups, quotas = construction_quotas(field,target)
    sizes = np.bincount(groups)
    supported = np.bincount(picks.ravel(),minlength=len(pool)) > 0
    fit = known & supported
    # A posted zero is exact, not an invitation to invent exposure.
    forbidden = ((desired[picks] == 0) & known[picks]).any(axis=1)
    available = np.bincount(groups[~forbidden],minlength=len(sizes))
    # Salary buckets with insufficient zero-free support cannot honor both
    # constraints. Keep the valid proposals and report the remaining residual.
    zero_enforced = bool(np.all(available >= quotas))
    allowed = ~forbidden if zero_enforced else np.ones(len(field),bool)
    logweight = np.zeros(len(field),float)

    def inclusion(logw):
        w = np.exp(np.clip(logw,-35,35)) * allowed
        scale = quotas / np.maximum(np.bincount(groups,weights=w,minlength=len(sizes)),1e-300)
        for _ in range(25):
            prob = np.minimum(1,w*scale[groups])
            mass = np.bincount(groups,weights=prob,minlength=len(sizes))
            if np.max(np.abs(mass-quotas)) < 1e-7:
                break
            scale *= quotas / np.maximum(mass,1e-300)
        return np.minimum(1,w*scale[groups])

    best = None
    best_loss = float('inf')
    for _ in range(iterations):
        probability = inclusion(logweight)
        actual = np.bincount(picks.ravel(),weights=np.repeat(probability,len(slots)),minlength=len(pool))/target
        loss = float(np.mean((actual[known]-desired[known])**2))
        if loss < best_loss:
            best_loss, best = loss, probability.copy()
        if np.max(np.abs(actual[known]-desired[known])) < .003:
            break
        correction = np.zeros(len(pool))
        correction[fit] = .25 * np.clip(np.log(np.maximum(desired[fit],1e-5)/np.maximum(actual[fit],1e-5)),-2,2)
        logweight += correction[picks].sum(axis=1)
        logweight -= np.mean(logweight)
        np.clip(logweight,-35,35,out=logweight)
    # Randomized systematic sampling within each salary bucket. This preserves
    # each proposal's fitted inclusion probability and chooses exactly its quota
    # without replacement. Identical independently proposed rosters may remain.
    selected = []
    for group, quota in enumerate(quotas):
        if not quota:
            continue
        rows = np.flatnonzero(groups == group)
        rng.shuffle(rows)
        p = quota_probabilities(best[rows],quota)
        cumulative = np.cumsum(p)
        cumulative[-1] = quota
        chosen = rows[np.searchsorted(cumulative,rng.random()+np.arange(quota),side='right')]
        if len(np.unique(chosen)) != quota:
            raise ValueError('Ownership selection capacity failed')
        selected.extend(chosen.tolist())
    result = field.iloc[selected].copy().reset_index(drop=True)
    final = np.bincount(picks[np.asarray(selected)].ravel(),minlength=len(pool))/target
    report = pd.DataFrame({'Name':names,'Projected Ownership':own,
                           'Final Field Own %':100*final,
                           'Difference (pp)':100*final-own,
                           'Proposal Supported':supported})
    report = report.loc[known].sort_values('Difference (pp)',key=lambda c:c.abs(),ascending=False).reset_index(drop=True)
    result.attrs.update(field.attrs)
    result.attrs['target'] = target
    result.attrs['ownership_calibration'] = {'mean_absolute_error_pp':float(report['Difference (pp)'].abs().mean()),
        'max_error_pp':float(report['Difference (pp)'].abs().max()),'zero_enforced':zero_enforced,
        'proposal_count':len(field),'target':target}
    return result, report
