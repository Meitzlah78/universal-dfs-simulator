"""Offline structural diagnostics for aligned single-game lineup distributions.

Joint probabilities and covariances are separate outputs. Reference rows must
represent the same slate/player universe, or an explicitly mapped universe.
No fixed salary curve or universal KL threshold is assumed.
"""
import numpy as np
from scipy.sparse import csr_matrix
from scipy.stats import wasserstein_distance


def _weights(values,size):
    w=np.asarray(values,dtype=float)
    if w.shape!=(size,) or not np.isfinite(w).all() or (w<0).any() or not w.any():
        raise ValueError('Finite nonnegative row weights with positive total required')
    # Scale first to avoid overflow when normalizing large counts.
    w=w/w.max()
    return w/w.sum()


def _picks(values,player_count):
    p=np.asarray(values)
    if type(player_count) is not int or player_count<6:raise ValueError('At least six players required')
    if p.ndim!=2 or p.shape[1]!=6 or not len(p) or not np.issubdtype(p.dtype,np.integer):
        raise ValueError('Nonempty integer J x 6 lineup indices required')
    if (p<0).any() or (p>=player_count).any():raise ValueError('Player index out of range')
    if (np.diff(np.sort(p,axis=1),axis=1)==0).any():raise ValueError('Repeated player within roster')
    return p


def joint_probabilities(picks,weights,player_count,*,roles=True):
    """Compute E[XX.T] using six sparse indicators per lineup.

    Role columns: special players 0..P-1, FLEX players P..2P-1.
    With roles=False, columns instead represent any-role player inclusion.
    """
    p=_picks(picks,player_count);w=_weights(weights,len(p))
    columns=p.copy()
    if roles:columns[:,1:]+=player_count
    width=player_count*(2 if roles else 1)
    x=csr_matrix((np.ones(p.size),(np.repeat(np.arange(len(p)),6),columns.ravel())),shape=(len(p),width))
    joint=(x.T@x.multiply(w[:,None])).toarray()
    marginal=np.asarray(x.T@w).ravel()
    covariance=joint-np.outer(marginal,marginal)
    return {'marginal':marginal,'joint':joint,'covariance':covariance}


def salary_distribution(salaries,weights,quantiles=(0,.1,.25,.5,.75,.9,1)):
    salary=np.asarray(salaries,float)
    if salary.ndim!=1 or not len(salary) or not np.isfinite(salary).all() or (salary<0).any():
        raise ValueError('Finite nonnegative salary per lineup required')
    w=_weights(weights,len(salary));keep=w>0;salary=salary[keep];w=w[keep]
    unique,inverse=np.unique(salary,return_inverse=True)
    mass=np.bincount(inverse,weights=w,minlength=len(unique));cdf=np.cumsum(mass);cdf[-1]=1.
    qs=np.asarray(quantiles,float)
    if qs.ndim!=1 or not np.isfinite(qs).all() or (qs<0).any() or (qs>1).any():raise ValueError('Quantiles must be in [0,1]')
    # Discrete inverse CDF; no fictitious interpolated salaries.
    values=unique[np.minimum(np.searchsorted(cdf,qs,side='left'),len(unique)-1)]
    return {'salary':unique,'mass':mass,'cdf':cdf,'mean':float(np.dot(unique,mass)),
            'quantiles':dict(zip(map(str,qs.tolist()),values.tolist()))}


def kl_divergence(weights,prior):
    w=np.asarray(weights,float);q=np.asarray(prior,float)
    if w.ndim!=1 or q.shape!=w.shape or not len(w):raise ValueError('Matching nonempty weights and priors required')
    w=_weights(w,len(w));q=_weights(q,len(q));positive=w>0
    if (q[positive]==0).any():return float('inf')
    return float(np.sum(w[positive]*(np.log(w[positive])-np.log(q[positive]))))


def compare_fields(sim_picks,sim_weights,sim_salaries,sim_player_ids,
                   reference_picks,reference_weights,reference_salaries,reference_player_ids,*,slate_id,reference_slate_id,site,reference_site,prior=None):
    """Align IDs, then compare normalized distributions; never align by row order.

    Caller verifies source slate identity and reference provenance. We reject
    missing/extra IDs rather than silently dropping unmatched players.
    """
    if not isinstance(slate_id,str) or not slate_id or slate_id!=reference_slate_id:
        raise ValueError('Identical explicit slate identities required')
    if site not in {'dk','fd'} or site!=reference_site:raise ValueError('Identical site identities required')
    ids=list(sim_player_ids);refids=list(reference_player_ids)
    if not all(isinstance(i,str) and i for i in ids+refids) or len(set(ids))!=len(ids) or len(set(refids))!=len(refids) or set(ids)!=set(refids):
        raise ValueError('Unique, identical player-ID sets required for pair comparison')
    n=len(ids);sp=_picks(sim_picks,n);rp=_picks(reference_picks,n)
    lookup={key:i for i,key in enumerate(ids)};mapping=np.array([lookup[key] for key in refids]);rp=mapping[rp]
    sw=_weights(sim_weights,len(sp));rw=_weights(reference_weights,len(rp))
    sd=salary_distribution(sim_salaries,sw);rd=salary_distribution(reference_salaries,rw)
    if len(sim_salaries)!=len(sp) or len(reference_salaries)!=len(rp):raise ValueError('Salary and lineup counts differ')
    report={'player_ids':ids,'slate_id':slate_id,'site':site,'roles':{},'all_slot':{},
        'column_mapping':[{'column':i+offset,'player_id':key,'role':role}
            for role,offset in [('CPT' if site=='dk' else 'MVP',0),('FLEX',n)] for i,key in enumerate(ids)]}
    for name,roles in [('roles',True),('all_slot',False)]:
        a=joint_probabilities(sp,sw,n,roles=roles);b=joint_probabilities(rp,rw,n,roles=roles)
        delta=a['joint']-b['joint'];covdelta=a['covariance']-b['covariance']
        upper=np.triu(np.ones(delta.shape,bool),k=1)
        if roles:
            # Special-special and same-player special/FLEX pairs are impossible;
            # exclude them from aggregate errors to avoid diluting diagnostics.
            upper[:n,:n]=False
            upper[np.arange(n),n+np.arange(n)]=False
        report[name]={'simulated':a,'reference':b,'joint_residual':delta,'covariance_residual':covdelta,
            'summary':{'marginal_mae_pp':float(np.mean(np.abs(a['marginal']-b['marginal']))*100),
                'pair_mae_pp':float(np.mean(np.abs(delta[upper]))*100),
                'pair_max_abs_pp':float(np.max(np.abs(delta[upper]))*100),
                'max_over_pairing_pp':float(max(0,np.max(delta[upper]))*100),
                'max_under_pairing_pp':float(min(0,np.min(delta[upper]))*100),
                'covariance_max_abs_pp':float(np.max(np.abs(covdelta[upper]))*100),
                'covariance_mae_pp':float(np.mean(np.abs(covdelta[upper]))*100)}}
    axis=np.union1d(sd['salary'],rd['salary'])
    def evaluate_cdf(d):
        loc=np.searchsorted(d['salary'],axis,side='right')-1
        return np.where(loc>=0,d['cdf'][np.maximum(loc,0)],0.)
    report['salary']={'simulated':sd,'reference':rd,'cdf_max_abs_difference':float(np.max(np.abs(evaluate_cdf(sd)-evaluate_cdf(rd)))),
        'wasserstein_dollars':float(wasserstein_distance(sd['salary'],rd['salary'],u_weights=sd['mass'],v_weights=rd['mass']))}
    report['kl_from_prior']=kl_divergence(sw,prior) if prior is not None else None
    report['offline_only']=True
    return report
