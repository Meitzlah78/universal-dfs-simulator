"""Experimental ownership-shaped NBA field on a finite legal roster support."""
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


def build_field(lineups,ownership,entries,seed=83,source=None,max_iterations=100):
    """Fit candidate probabilities to full nine-slot ownership targets.

    ownership is a complete percent vector (sum 900), aligned to outcome player
    columns. Caller supplies legal rosters and verified source metadata. This
    models marginal ownership only, not learned NBA stacking or lineup habits.
    Integer copies represent actual duplicate entries without expanding memory.
    """
    ids=np.asarray(lineups);target=np.asarray(ownership,float)
    if ids.ndim!=2 or ids.shape[1]!=9 or not len(ids) or ids.dtype.kind not in 'iu':
        raise ValueError('Nonempty nine-player integer field support required')
    if target.ndim!=1 or not np.isfinite(target).all() or (target<0).any() or (target>100).any() or abs(target.sum()-900)>.5:
        raise ValueError('Complete NBA ownership percentages must sum to 900')
    if (ids<0).any() or (ids>=len(target)).any() or (np.diff(np.sort(ids,axis=1),axis=1)==0).any():
        raise ValueError('Invalid or repeated player in opponent lineup')
    if not isinstance(entries,int) or entries<1 or not source or max_iterations<1:
        raise ValueError('Positive field size, fitting budget and ownership source required')
    # Flexible-slot permutations are one roster support point, not additional
    # independent probabilities for the same lineup.
    _,unique=np.unique(np.sort(ids,axis=1),axis=0,return_index=True)
    ids=ids[np.sort(unique)]
    incidence=np.zeros((len(ids),len(target)))
    incidence[np.arange(len(ids))[:,None],ids]=1
    if ((target>0)&~incidence.any(axis=0)).any():
        raise ValueError('Ownership targets include players absent from legal field support')
    desired=target/100
    def loss(theta):
        logits=incidence@theta;normalizer=logsumexp(logits)
        p=np.exp(logits-normalizer)
        return normalizer-desired@theta+1e-6*(theta@theta)/2, p@incidence-desired+1e-6*theta
    fit=minimize(loss,np.zeros(len(target)),method='L-BFGS-B',jac=True,
                 options={'maxiter':max_iterations,'ftol':1e-12,'gtol':1e-7})
    logits=incidence@fit.x;probability=np.exp(logits-logsumexp(logits))
    expected=100*(probability@incidence)
    copies=np.random.default_rng(seed).multinomial(entries,probability)
    actual=100*(copies@incidence)/entries
    selected=copies>0
    return {'indices':ids[selected],'copies':copies[selected],
            'ownership_target':target,'ownership_expected':expected,'ownership_sampled':actual,
            'max_expected_error_pct':float(abs(expected-target).max()),
            'optimizer_converged':bool(fit.success),'optimizer_message':str(fit.message),
            'entries':entries,'unique_rosters':int(selected.sum()),'ownership_source':source,
            'status':'experimental marginal ownership fit on supplied legal support; inspect residuals'}
