"""Experimental ownership-shaped NBA field on a finite legal roster support."""
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from scipy.sparse import csr_matrix


def _draw_copies(entries, probability, seed):
    """Preserve ordinary seeded draws; repair only roundoff at the last bin."""
    try:
        return np.random.default_rng(seed).multinomial(entries, probability)
    except ValueError:
        p = np.asarray(probability, dtype=np.float64)
        if (p.ndim != 1 or not len(p) or not np.isfinite(p).all()
                or (p < 0).any() or abs(p.sum() - 1) > 1e-10):
            raise
        # NumPy takes the last probability as the remainder. Give it the
        # largest mass, so a tiny final bin cannot vanish into rounding.
        order = np.arange(len(p))
        largest = int(p.argmax())
        order[largest], order[-1] = order[-1], order[largest]
        counts = np.empty(len(p), dtype=np.int64)
        counts[order] = np.random.default_rng(seed).multinomial(entries, p[order] / p.sum())
        return counts


def build_field(lineups,ownership,entries,seed=83,source=None,max_iterations=100,max_error_pct=5):
    """Fit candidate probabilities to full nine-slot ownership targets.

    ownership is a complete percent vector (sum 900), aligned to outcome player
    columns. Caller supplies legal rosters and verified source metadata. This
    models marginal ownership only, not learned NBA stacking or lineup habits.
    Integer copies represent actual duplicate entries without expanding memory.
    """
    ids=np.asarray(lineups);target=np.asarray(ownership,float)
    if ids.ndim!=2 or ids.shape[1] not in {8,9} or not len(ids) or ids.dtype.kind not in 'iu':
        raise ValueError('Nonempty nine-player integer field support required')
    if target.ndim!=1 or not np.isfinite(target).all() or (target<0).any() or (target>100).any() or abs(target.sum()-ids.shape[1]*100)>.5:
        raise ValueError('Complete NBA ownership percentages must sum to 900')
    if (ids<0).any() or (ids>=len(target)).any() or (np.diff(np.sort(ids,axis=1),axis=1)==0).any():
        raise ValueError('Invalid or repeated player in opponent lineup')
    if not isinstance(entries,int) or entries<1 or not source or max_iterations<1:
        raise ValueError('Positive field size, fitting budget and ownership source required')
    if not np.isfinite(max_error_pct) or not 0<max_error_pct<=100:
        raise ValueError('Ownership fitting tolerance must be positive and at most 100 percentage points')
    # Flexible-slot permutations are one roster support point, not additional
    # independent probabilities for the same lineup.
    _,unique=np.unique(np.sort(ids,axis=1),axis=0,return_index=True)
    ids=ids[np.sort(unique)]
    incidence=csr_matrix((np.ones(ids.size),(np.repeat(np.arange(len(ids)),ids.shape[1]),ids.ravel())),
                         shape=(len(ids),len(target)))
    if ((target>0)&~(np.asarray(incidence.sum(axis=0)).ravel()>0)).any():
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
    initial_error=float(abs(expected-target).max())
    fit_method='exact-target entropy fit'
    if initial_error>max_error_pct:
        # Finite support can admit a close fit without admitting exact marginals.
        # The split dual solves maximum entropy inside a band around each target.
        # Keep the best measured residual if a recovery solve exhausts its budget.
        players=len(target)
        for band_pct in (max_error_pct/2,max_error_pct*.99):
            band=band_pct/100
            def band_loss(parameters):
                theta=parameters[:players]-parameters[players:]
                logits=incidence@theta
                normalizer=logsumexp(logits)
                weights=np.exp(logits-normalizer)
                gradient=weights@incidence-desired
                return (normalizer-desired@theta+band*parameters.sum(),
                        np.r_[gradient+band,-gradient+band])
            recovery=minimize(band_loss,np.zeros(2*players),method='L-BFGS-B',jac=True,
                bounds=[(0,None)]*(2*players),
                options={'maxiter':max_iterations,'maxls':40,'ftol':1e-12,'gtol':1e-7})
            theta=recovery.x[:players]-recovery.x[players:]
            logits=incidence@theta
            weights=np.exp(logits-logsumexp(logits))
            recovered_expected=100*(weights@incidence)
            error=float(abs(recovered_expected-target).max())
            if np.isfinite(error) and error<float(abs(expected-target).max()):
                probability=weights
                expected=recovered_expected
                recovery.x=theta
                fit=recovery
                fit_method='ownership-band entropy recovery'
            if float(abs(expected-target).max())<=max_error_pct:
                break
    copies=_draw_copies(entries,probability,seed)
    actual=100*(copies@incidence)/entries
    selected=copies>0
    return {'indices':ids[selected],'copies':copies[selected],
            'ownership_target':target,'ownership_expected':expected,'ownership_sampled':actual,
            'max_expected_error_pct':float(abs(expected-target).max()),
            'optimizer_converged':bool(fit.success),'optimizer_message':str(fit.message),
            'fit_method':fit_method,'initial_max_expected_error_pct':initial_error,
            'fit_tolerance_pct':float(max_error_pct),
            'fit_state':{'indices':ids,'probabilities':probability,'theta':fit.x},
            'entries':entries,'unique_rosters':int(selected.sum()),'ownership_source':source,
            'status':'experimental marginal ownership fit on supplied legal support; inspect residuals'}


def sample_popularity_field(lineups,popularity,entries,seed=83,source=None,strength=.5):
    """Estimate a field from relative popularity scores, not ownership targets.

    A lineup's log weight is strength times summed log player popularity.
    Legal-support conditioning produces coherent roster frequencies totaling
    900%. This does not validate the original scores or claim external projected
    ownership; callers must display the estimate label and source assumption.
    """
    ids=np.asarray(lineups);raw=np.asarray(popularity,float)
    if ids.ndim!=2 or ids.shape[1] not in {8,9} or not len(ids) or ids.dtype.kind not in 'iu':
        raise ValueError('Nine-player integer legal support required')
    if raw.ndim!=1 or not np.isfinite(raw).all() or (raw<0).any() or not (raw>0).any():
        raise ValueError('Finite nonnegative relative popularity scores required')
    if (ids<0).any() or (ids>=len(raw)).any() or (np.diff(np.sort(ids,axis=1),axis=1)==0).any():
        raise ValueError('Invalid opponent roster indices')
    if not isinstance(entries,int) or entries<1 or not source or not np.isfinite(strength) or not 0<=strength<=2:
        raise ValueError('Explicit source, field size and bounded popularity strength required')
    _,unique=np.unique(np.sort(ids,axis=1),axis=0,return_index=True)
    ids=ids[np.sort(unique)]
    # A documented 0.1 floor preserves possible low-popularity combinations.
    logits=strength*np.log(np.maximum(raw,.1))[ids].sum(axis=1)
    probability=np.exp(logits-logsumexp(logits))
    incidence=csr_matrix((np.ones(ids.size),(np.repeat(np.arange(len(ids)),ids.shape[1]),ids.ravel())),
                         shape=(len(ids),len(raw)))
    copies=_draw_copies(entries,probability,seed)
    keep=copies>0
    return {'indices':ids[keep],'copies':copies[keep],
            'ownership_expected':100*(probability@incidence),
            'ownership_sampled':100*(copies@incidence)/entries,
            'ownership_source':'Estimated field; relative popularity assumption: '+source,
            'entries':entries,'unique_rosters':int(keep.sum()),
            'fit_state':{'indices':ids,'probabilities':probability},
            'effective_support':float(1/(probability@probability)),
            'largest_roster_probability':float(probability.max()),
            'popularity_strength':strength,
            'status':'estimated ownership from legal support; not verified projected ownership'}


def ownership_support_diagnostic(lineups,ownership,tolerance=5):
    """Bound the best possible maximum ownership error on this support.

    This is a diagnostic only: its sparse LP weights never replace the field.
    A failed/time-limited solve is inconclusive, not proof of infeasibility.
    """
    from scipy.optimize import linprog
    from scipy.sparse import coo_matrix,hstack,vstack
    ids=np.asarray(lineups);target=np.asarray(ownership,float)
    rows=ids.ravel();columns=np.repeat(np.arange(len(ids)),ids.shape[1])
    incidence=coo_matrix((np.full(len(rows),100.),(rows,columns)),
                         shape=(len(target),len(ids))).tocsr()
    slack=-np.ones((len(target),1))
    constraints=vstack([hstack([incidence,slack]),hstack([-incidence,slack])]).tocsr()
    objective=np.r_[np.zeros(len(ids)),1.]
    fit=linprog(objective,A_ub=constraints,b_ub=np.r_[target,-target],
        A_eq=coo_matrix((np.ones(len(ids)),(np.zeros(len(ids),dtype=int),np.arange(len(ids)))),
                       shape=(1,len(ids)+1)).tocsr(),b_eq=[1.],
        bounds=(0,None),method='highs',options={'time_limit':5.})
    result={'status':'inconclusive','solver_message':str(fit.message)}
    if fit.success:
        error=float(fit.x[-1])
        result.update(status='feasible' if error<=tolerance+1e-6 else 'support-limited',
                      minimum_max_error_pct=error)
    return result
