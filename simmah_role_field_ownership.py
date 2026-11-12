"""Fit single-game opponent role marginals over legal saved roster support.

Only pregame ownership and roster identities enter this fit. Duplicate opponent
entries are allowed; no outcomes, candidate scores or portfolio caps are used.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.sparse import csr_matrix
from scipy.special import logsumexp

ENGINE = 'role-marginals-v4'


def impossible_salary_roles(pool, slots, salary_cap):
    """Check every positive imported role against the cheapest legal roster.

    This runs before simulation and diagnoses structural pool loss without
    changing ownership, projections, or the salary cap.
    """
    special = 'Projected CPT Own %' if slots[0] == 'Captain' else 'Projected MVP Ownership'
    records = pool.reset_index(drop=True).to_dict('records')
    flex = [i for i,r in enumerate(records) if float(r['Projected Flex Ownership']) > 0]
    captains = [i for i,r in enumerate(records) if float(r[special]) > 0]
    def cheapest(captain, forced=None):
        selected=[] if forced is None else [forced]
        options=sorted((i for i in flex if i!=captain and i!=forced),key=lambda i:float(records[i]['Salary']))
        selected += options[:5-len(selected)]
        if len(selected)<5:return float('inf')
        if all(records[i]['Team']==records[captain]['Team'] for i in selected):
            other=[i for i in options if records[i]['Team']!=records[captain]['Team']]
            replaceable=[i for i in selected if i!=forced]
            if not other or not replaceable:return float('inf')
            selected.remove(max(replaceable,key=lambda i:float(records[i]['Salary'])))
            selected.append(other[0])
        return float(records[captain]['CaptainSalary'])+sum(float(records[i]['Salary']) for i in selected)
    failures=[]
    for i,r in enumerate(records):
        for role,minimum in ([('CPT' if slots[0]=='Captain' else 'MVP',cheapest(i))] if i in captains else []) + ([('FLEX',min((cheapest(c,i) for c in captains if c!=i),default=float('inf')))] if i in flex else []):
            if minimum>salary_cap:
                failures.append({'Name':r['Name'],'Role':role,'Cheapest legal salary':minimum,'Salary cap':salary_cap})
    return pd.DataFrame(failures,columns=['Name','Role','Cheapest legal salary','Salary cap'])


def calibrate_role_ownership(field, pool, slots, target=None, seed=20261105, tolerance_pp=.5, support_salary_cap=None):
    if field is None or field.empty:
        raise ValueError('Role ownership calibration requires legal opponent proposals')
    count = len(field) if target is None else int(target)
    if count <= 0 or len(slots) != 6 or pool.Name.duplicated().any():
        raise ValueError('Invalid role ownership calibration inputs')
    special = 'Projected CPT Own %' if slots[0] == 'Captain' else 'Projected MVP Ownership'
    raw = pool[[special, 'Projected Flex Ownership']].apply(pd.to_numeric, errors='coerce').to_numpy(float).T
    if not np.isfinite(raw).all() or (raw < 0).any() or (raw > 100).any() or (raw.sum(axis=1) <= 0).any():
        raise ValueError('Complete valid role ownership required; no fallback ownership used')
    # Removed/ineligible players and display rounding change role totals. Keep
    # raw inputs intact and explicitly report this eligible-pool normalization.
    totals = raw.sum(axis=1)
    desired = raw * np.array([1., 5.])[:, None] / totals[:, None]
    independent = desired.copy()
    if (desired.sum(axis=0) > 1 + 1e-9).any():
        # Exclusions can make separate role normalization impossible. Project
        # onto legal per-player marginals, preserving posted zero role shares.
        n_players = raw.shape[1]
        bounds = [(0., 1. if value > 0 else 0.) for value in raw.ravel()]
        constraints = [
            {'type':'eq', 'fun':lambda x: x.reshape(2,-1).sum(axis=1)-[1.,5.],
             'jac':lambda x: np.kron(np.eye(2),np.ones((1,n_players)))},
            {'type':'ineq', 'fun':lambda x: 1.-x.reshape(2,-1).sum(axis=0),
             'jac':lambda x: -np.tile(np.eye(n_players),(1,2))}]
        projected = minimize(lambda x: (.5*np.square(x-independent.ravel()).sum(),
                             x-independent.ravel()), independent.ravel(), jac=True,
                             bounds=bounds, constraints=constraints, method='SLSQP',
                             options={'ftol':1e-12,'maxiter':500})
        desired = projected.x.reshape(2,-1)
        if (not projected.success or not np.isfinite(desired).all()
                or np.max(np.abs(desired.sum(axis=1)-[1.,5.])) > 1e-7
                or (desired.sum(axis=0)>1+1e-7).any()):
            raise ValueError('Eligible role targets have no feasible six-player allocation; check the eligible pool')
    # SLSQP may leave numerical dust on a binding zero boundary.
    desired[np.abs(desired) < 1e-10] = 0.
    names = pool.Name.astype(str).tolist(); index = {name:i for i,name in enumerate(names)}
    n = len(names)
    picks = field[slots].apply(lambda col:col.astype(str).map(index)).to_numpy()
    if pd.isna(picks).any():
        raise ValueError('Unknown opponent player in role ownership calibration')
    picks = picks.astype(int)
    if any(len(set(row)) != 6 for row in picks):
        raise ValueError('Duplicate player in opponent roster')
    repaired_support = 0
    if support_salary_cap is not None:
        # Earlier representatives can become forbidden after the eligible-target
        # projection zeros another player's role. Repair against FINAL targets.
        role_indices=picks.copy();role_indices[:,1:]+=n
        legal=(desired.ravel()[role_indices]>0).all(axis=1)
        present=np.zeros(2*n,dtype=bool);present[role_indices[legal].ravel()]=True
        if ((desired.ravel()>0)&~present).any():
            from simmah_showdown_field import build_unique_field, SLOTS
            if not {'Salary','CaptainSalary','Team'}<=set(pool):
                raise ValueError('Verified role salaries required to repair legal proposal support')
            extra=build_unique_field(pool,desired[1],desired[0],max(10000,2*n),
                salary_cap=support_salary_cap,min_salary=0,
                rng=np.random.default_rng(seed),ensure_role_support=True)
            extra=extra.rename(columns=dict(zip(SLOTS,slots)))
            repaired_support=len(extra)
            field=pd.concat([field,extra],ignore_index=True)
            picks=field[slots].apply(lambda col:col.astype(str).map(index)).to_numpy(int)
    keys = pd.MultiIndex.from_arrays([picks[:,0], *np.sort(picks[:,1:],axis=1).T])
    codes, _ = pd.factorize(keys, sort=False)
    first = np.flatnonzero(~pd.Series(codes).duplicated().to_numpy())
    prior = np.bincount(codes).astype(float)
    rows = field.iloc[first].copy().reset_index(drop=True)
    picks = picks[first]
    role_picks = picks.copy();role_picks[:,1:] += n
    allowed = (desired.ravel()[role_picks] > 0).all(axis=1)
    rows = rows.loc[allowed].reset_index(drop=True);picks=picks[allowed];role_picks=role_picks[allowed];prior=prior[allowed]
    if not len(rows):raise ValueError('No legal support for nonzero role ownership targets')
    matrix = csr_matrix((np.ones(role_picks.size),
        (np.repeat(np.arange(len(rows)),6),role_picks.ravel())),shape=(len(rows),2*n))
    support = np.asarray(matrix.sum(axis=0)).ravel() > 0
    if ((desired.ravel() > 0) & ~support).any():
        missing = [names[i % n]+' ('+('CPT/MVP' if i<n else 'FLEX')+')'
                   for i in np.flatnonzero((desired.ravel()>0)&~support)]
        eligible = ', '.join(names)
        raise ValueError('Missing legal proposal support for role targets: '+', '.join(missing)
                         +f'. Build {ENGINE}; eligible players ({n}): '+eligible
                         +f'; repair proposals: {repaired_support}; salary cap: {support_salary_cap}')
    logprior = np.log(prior / prior.sum())
    wanted = desired.ravel()
    def objective(theta):
        logits=logprior + matrix @ theta
        normalizer=logsumexp(logits)
        probability=np.exp(logits-normalizer)
        return float(normalizer-wanted@theta), np.asarray(matrix.T@probability).ravel()-wanted
    fit=minimize(objective,np.zeros(2*n),jac=True,method='L-BFGS-B',
        options={'maxiter':700,'ftol':1e-13,'gtol':1e-8,'maxls':30})
    logits=logprior+matrix@fit.x;probability=np.exp(logits-logsumexp(logits))
    fitted=np.asarray(matrix.T@probability).ravel()
    if not np.isfinite(probability).all() or not np.isfinite(fitted).all():
        raise ValueError('Role ownership fit returned invalid probabilities; contest estimates stopped')
    fit_error=float(np.max(np.abs(fitted-wanted))*100)
    if fit_error > tolerance_pp:
        raise ValueError(f'Role ownership targets could not be matched within legal proposal support (largest fitted difference {fit_error:.2f} pp). Contest estimates were stopped; targets were not replaced.')
    # Randomized systematic resampling preserves fitted mass without forcing
    # every rare representative into the contest. Multiplicities are modeled,
    # not inferred from a mandatory unique-lineup quota.
    rng=np.random.default_rng(seed);order=rng.permutation(len(rows))
    cumulative=np.cumsum(probability[order]);cumulative[-1]=1.
    selected=order[np.searchsorted(cumulative,(rng.random()+np.arange(count))/count,side='right')]
    result=rows.iloc[selected].reset_index(drop=True)
    actual=np.bincount(role_picks[selected].ravel(),minlength=2*n)/count
    error=float(np.max(np.abs(actual-wanted))*100)
    # Small fields have coarser ownership steps. Never hide large residuals.
    rounding_limit=max(tolerance_pp,600/count)
    allocation_attempts = 1
    # A valid fitted distribution can miss tolerance in one randomized integer
    # draw. Retry only that draw, retaining the closest legal allocation.
    while error > rounding_limit and allocation_attempts < 32:
        allocation_attempts += 1
        trial_order=rng.permutation(len(rows))
        trial_cumulative=np.cumsum(probability[trial_order]);trial_cumulative[-1]=1.
        trial_selected=trial_order[np.searchsorted(trial_cumulative,
            (rng.random()+np.arange(count))/count,side='right')]
        trial_actual=np.bincount(role_picks[trial_selected].ravel(),minlength=2*n)/count
        trial_error=float(np.max(np.abs(trial_actual-wanted))*100)
        if trial_error < error:
            selected=trial_selected;actual=trial_actual;error=trial_error
    if error > rounding_limit:
        raise ValueError(f'Final role ownership differs by {error:.2f} pp after integer allocation; increase opponent count')
    result=rows.iloc[selected].reset_index(drop=True)
    report=pd.DataFrame({'Name':names,'Raw special own %':raw[0],'Raw FLEX own %':raw[1],
        'Independent special target %':independent[0]*100,'Independent FLEX target %':independent[1]*100,
        'Eligible special target %':desired[0]*100,'Eligible FLEX target %':desired[1]*100,
        'Final special own %':actual[:n]*100,'Final FLEX own %':actual[n:]*100,
        'Special difference pp':(actual[:n]-desired[0])*100,'FLEX difference pp':(actual[n:]-desired[1])*100})
    result.attrs.update(field.attrs)
    result.attrs['role_ownership_calibration']={'engine':ENGINE,'raw_eligible_role_totals':totals.tolist(),
        'normalized_role_totals':[100.,500.],
        'eligibility_adjustment_max_pp':float(np.max(np.abs(desired-independent))*100),'fitted_max_error_pp':fit_error,'final_max_error_pp':error,
        'final_mean_error_pp':float(np.abs(actual-wanted).mean()*100),'support_rosters':len(rows),
        'field_entries':count,'repair_proposal_rosters':repaired_support,'allocation_attempts':allocation_attempts,'unique_rosters':int(np.unique(selected).size),
        'construction_policy':'learned roster frequencies used as prior; ownership fitted last',
        'duplication_policy':'fitted roster resampling; real duplicate frequencies not independently validated'}
    return result, report


def restore_role_support(selected, proposals, pool, slots):
    """Retain at least one legal representative of each positive target role.

    This is support only: final resampling does not impose a minimum exposure.
    """
    special='Projected CPT Own %' if slots[0]=='Captain' else 'Projected MVP Ownership'
    rows=[]
    for role,columns in [(special,slots[:1]),('Projected Flex Ownership',slots[1:])]:
        present=set(selected[columns].astype(str).to_numpy().ravel())
        for name in pool.loc[pd.to_numeric(pool[role],errors='coerce')>0,'Name'].astype(str):
            if name in present:continue
            support=proposals.loc[proposals[columns].eq(name).any(axis=1)]
            if not support.empty:rows.append(support.iloc[:1]);present.add(name)
    if not rows:return selected
    result=pd.concat([selected,*rows],ignore_index=True)
    result.attrs.update(selected.attrs)
    return result
