"""Offline legal-action clock proposal; PBP profiles must predate target day."""
import numpy as np
from scipy.special import gammainc,gammaincinv
BUCKETS=['other','after_oreb','after_foul','after_ft','after_make','after_dreb','after_turnover']

def sample_duration(raw,scale,origin,budget,model):
    """Condition legal event times on clock support, not a turnover from a tail.

    Actual shot-clock violations are separate events. CDF mapping preserves a
    draw's quantile while selecting legal historical intervals or a truncated
    gamma fallback. This is a research proposal, not validated game-state timing.
    """
    raw=np.asarray(raw,float);budget=np.asarray(budget,float)
    if model.get('mode') not in ['truncated','empirical']:raise ValueError('Unknown offline clock mode')
    if raw.shape!=budget.shape or raw.shape!=np.shape(origin) or not np.isfinite(raw).all() or not np.isfinite(budget).all() or (raw<0).any() or (budget<0).any() or not np.isfinite(scale) or scale<=0:
        raise ValueError('Finite aligned durations and nonnegative clock support required')
    u=np.clip(gammainc(4,raw/scale),0,np.nextafter(1.,0.))
    bound=np.maximum(0,np.nextafter(budget,0.))
    result=scale*gammaincinv(4,u*gammainc(4,bound/scale))
    if model['mode']=='empirical':
        for code,key in enumerate(BUCKETS):
            use=origin==code;history=np.asarray(model['profiles'].get(key,[]),float)
            if not use.any() or not len(history):continue
            history=np.sort(history[(history>0)&np.isfinite(history)])
            if not len(history):continue
            counts=np.searchsorted(history,bound[use],side='right');good=counts>0
            locations=np.flatnonzero(use)[good]
            result[locations]=history[np.floor(u[locations]*counts[good]).astype(int)]
    return np.minimum(result,bound)
