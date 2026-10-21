"""Offline bounded-weight field experiment. No live builder imports this module.

Caps are sensitivity assumptions, not learned contest duplication frequencies.
Callers supply already validated legal rosters and explicit normalized targets.
"""
import numpy as np
from scipy import sparse
from scipy.optimize import linprog


def fit_bounded_field(indices, targets, player_salaries, entries, *,
                      max_roster_weight, mean_salary_min, tail_salary,
                      tail_fraction_max, timeout=20):
    ids=np.asarray(indices); y=np.asarray(targets,float); salaries=np.asarray(player_salaries,float)
    if ids.ndim!=2 or not ids.size or ids.dtype.kind not in 'iu':
        raise ValueError('Nonempty integer roster matrix required')
    if y.ndim!=1 or salaries.shape!=y.shape or not np.isfinite(y).all() or not np.isfinite(salaries).all():
        raise ValueError('Aligned finite ownership and salary vectors required')
    if (y<0).any() or (y>100).any() or (salaries<=0).any() or abs(y.sum()-100*ids.shape[1])>1e-6:
        raise ValueError('Valid normalized ownership and positive salaries required')
    if (ids<0).any() or (ids>=len(y)).any() or (np.diff(np.sort(ids,axis=1),axis=1)==0).any():
        raise ValueError('Distinct in-range players required per roster')
    if len(np.unique(np.sort(ids,axis=1),axis=0))!=len(ids):
        raise ValueError('Canonical duplicate support rosters are not allowed')
    if not isinstance(entries,int) or isinstance(entries,bool) or not 1<=entries<=10000000:
        raise ValueError('Positive bounded integer field size required')
    if not np.isfinite([max_roster_weight,mean_salary_min,tail_salary,tail_fraction_max,timeout]).all():
        raise ValueError('Finite explicit constraints required')
    n=len(ids)
    if not 0<max_roster_weight<=1 or n*max_roster_weight<1-1e-10:
        raise ValueError('Weight cap cannot cover the supplied support')
    if mean_salary_min<0 or tail_salary<0 or not 0<=tail_fraction_max<=1 or timeout<=0:
        raise ValueError('Invalid salary or solver constraints')
    incidence=sparse.coo_matrix((np.full(ids.size,100.),
        (ids.ravel(),np.repeat(np.arange(n),ids.shape[1]))),shape=(len(y),n)).tocsr()
    salary=salaries[ids].sum(axis=1); scale=max(1.,float(salary.max()))
    tail=(salary<tail_salary).astype(float)
    inequality=sparse.vstack([
        sparse.hstack([incidence,-np.ones((len(y),1))]),
        sparse.hstack([-incidence,-np.ones((len(y),1))]),
        sparse.csr_matrix(np.r_[-salary/scale,0][None,:]),
        sparse.csr_matrix(np.r_[tail,0][None,:])]).tocsr()
    result=linprog(np.r_[np.zeros(n),1.],A_ub=inequality,
        b_ub=np.r_[y,-y,-mean_salary_min/scale,tail_fraction_max],
        A_eq=sparse.csr_matrix(np.r_[np.ones(n),0][None,:]),b_eq=[1.],
        bounds=[(0,max_roster_weight)]*n+[(0,None)],method='highs',
        options={'time_limit':float(timeout)})
    if not result.success:
        raise ValueError('Bounded field fit unavailable: '+result.message)
    weights=np.clip(result.x[:n],0,max_roster_weight)
    if abs(weights.sum()-1)>1e-7:
        raise ValueError('Solver returned invalid field mass')
    weights/=weights.sum()
    if weights.max()>max_roster_weight+1e-7 or weights@salary<mean_salary_min-1e-4 or weights@tail>tail_fraction_max+1e-7:
        raise ValueError('Solver returned constraint violation')
    # Largest remainders preserve exact contest size and keep every count
    # within one entry of its fitted mass; multinomial noise can break caps.
    counts=np.floor(weights*entries).astype(np.int64)
    remaining=entries-int(counts.sum())
    if not 0<=remaining<=n:raise ValueError('Integer allocation failed')
    order=np.argsort(-(weights*entries-counts),kind='stable')
    counts[order[:remaining]]+=1
    integer_cap=int(np.ceil(max_roster_weight*entries))
    if counts.sum()!=entries or counts.max()>integer_cap:
        raise ValueError('Integer concentration bound failed')
    expected=incidence@weights; sampled=incidence@(counts/entries);keep=counts>0
    return {'indices':ids[keep], 'copies':counts[keep], 'weights':weights,
        'ownership_expected':expected,'ownership_sampled':sampled,
        'max_expected_error_pct':float(abs(expected-y).max()),
        'max_sampled_error_pct':float(abs(sampled-y).max()),
        'expected_mean_salary':float(weights@salary),
        'integer_mean_salary':float(counts@salary/entries),
        'integer_tail_fraction':float(counts@tail/entries),
        'unique_rosters':int(keep.sum()),'maximum_copies':int(counts.max()),
        'effective_rosters':float(1/(weights@weights)),
        'max_roster_weight':float(max_roster_weight),
        'live_enabled':False,'status':'Offline sensitivity test; duplication cap is not empirically calibrated'}
