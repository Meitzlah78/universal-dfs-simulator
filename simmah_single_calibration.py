"""Offline KL projection of legal single-game support onto role ownership.

Input picks are J x 6 integer player indices (special role first). No dense
J x 2P indicator matrix is created. Targets are probabilities, not percentages.
Enumeration is responsible for salary, eligibility, and team legality.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import linprog, minimize
from scipy.special import logsumexp
from scipy.sparse import coo_matrix


class CalibrationError(ValueError):
    pass


class InfeasibleTargets(CalibrationError):
    """A necessary constraint failed or HiGHS certified infeasibility."""


class FeasibilityUnknown(CalibrationError):
    """The feasibility solver stopped without a certificate."""


class CalibrationNotConverged(CalibrationError):
    """No calibrated distribution meeting the requested tolerance was found."""


@dataclass
class CalibrationResult:
    weights: np.ndarray
    special_ownership: np.ndarray
    flex_ownership: np.ndarray
    diagnostics: dict


class RoleDual:
    """Positive-exponent dual: log Z(theta) - theta @ target.

    Gradient = achieved - target. For a negative exponent, the gradient sign
    must also reverse. Normalization is analytic; no multiplier is needed for
    the sum-to-one constraint. Redundant role totals create harmless gauge
    freedom; L-BFGS does not require an invertible Hessian.
    """
    def __init__(self, picks, prior, special_targets, flex_targets):
        special=np.asarray(special_targets,dtype=float)
        flex=np.asarray(flex_targets,dtype=float)
        if special.ndim!=1 or flex.shape!=special.shape or len(special)<6:
            raise CalibrationError('Matching role vectors for at least six players required')
        self.n=len(special)
        raw=np.asarray(picks)
        if raw.ndim!=2 or raw.shape[1]!=6 or not len(raw) or not np.issubdtype(raw.dtype,np.integer):
            raise CalibrationError('Nonempty integer J x 6 lineup indices required')
        if (raw<0).any() or (raw>=self.n).any():raise CalibrationError('Player index out of range')
        if (np.diff(np.sort(raw,axis=1),axis=1)==0).any():raise CalibrationError('Player repeated within lineup')
        q=np.asarray(prior,dtype=float)
        if q.shape!=(len(raw),) or not np.isfinite(q).all() or (q<0).any() or not q.any():
            raise CalibrationError('Finite nonnegative prior with positive mass required')
        self.target=np.r_[special,flex]
        if not np.isfinite(self.target).all() or (self.target<0).any() or (self.target>1).any():
            raise CalibrationError('Ownership targets must be finite probabilities in [0,1]')
        if not np.isclose(special.sum(),1,atol=1e-10,rtol=0) or not np.isclose(flex.sum(),5,atol=1e-10,rtol=0):
            raise InfeasibleTargets('Special targets must sum to 1 and FLEX targets to 5')
        if (special+flex>1+1e-10).any():raise InfeasibleTargets('A player cannot occupy both roles')
        self.active=np.flatnonzero(q>0)
        self.original_count=len(raw)
        self.picks=raw[self.active].astype(np.intp,copy=False)
        self.logq=np.log(q[self.active]);self.logq-=logsumexp(self.logq)

    def probabilities(self,theta):
        theta=np.asarray(theta,float)
        if theta.shape!=(2*self.n,) or not np.isfinite(theta).all():raise CalibrationError('Invalid dual vector')
        logits=self.logq+theta[self.picks[:,0]]
        for slot in range(1,6):logits=logits+theta[self.n+self.picks[:,slot]]
        logz=logsumexp(logits)
        return np.exp(logits-logz),logz

    def marginals(self,w):
        special=np.bincount(self.picks[:,0],weights=w,minlength=self.n)
        flex=np.zeros(self.n)
        for slot in range(1,6):flex+=np.bincount(self.picks[:,slot],weights=w,minlength=self.n)
        return np.r_[special,flex]

    def objective_gradient(self,theta):
        w,logz=self.probabilities(theta)
        return float(logz-np.dot(theta,self.target)),self.marginals(w)-self.target

    def feasibility(self,time_limit=5):
        if not np.isfinite(time_limit) or time_limit<=0:raise CalibrationError('Positive feasibility time limit required')
        count=len(self.picks);columns=np.arange(count)
        # Seven nonzeros per lineup: normalization, special role, five FLEX.
        rows=np.concatenate([np.full(count,2*self.n),self.picks[:,0],
                             *[self.n+self.picks[:,s] for s in range(1,6)]])
        cols=np.tile(columns,7)
        a=coo_matrix((np.ones(7*count),(rows,cols)),shape=(2*self.n+1,count)).tocsc()
        result=linprog(np.zeros(count),A_eq=a,b_eq=np.r_[self.target,1.],bounds=(0,None),
            method='highs',options={'time_limit':float(time_limit),'primal_feasibility_tolerance':1e-9})
        if result.status==2:raise InfeasibleTargets('HiGHS certified targets infeasible on positive-prior support')
        if result.status!=0:raise FeasibilityUnknown(str(result.message))
        residual=float(np.max(np.abs(a@result.x-np.r_[self.target,1.])))
        if residual>1e-8:raise FeasibilityUnknown(f'Feasibility witness residual {residual:g}')
        return {'status':'feasible','witness_max_residual':residual}


def calibrate_role_weights(picks,prior,special_targets,flex_targets,*,tolerance=1e-6,
                           max_iterations=500,feasibility_seconds=5):
    """Return accepted weights or raise; never silently relax ownership targets.

    Zero-prior rows remain zero. Feasibility is checked on that same support.
    Boundary targets may require divergent dual parameters; numerical failure
    after a feasible LP is reported as nonconvergence, not infeasibility.
    Tolerance is in probability units (1e-6 = 0.0001 percentage points).
    """
    if not np.isfinite(tolerance) or tolerance<=0:raise CalibrationError('Positive tolerance required')
    if type(max_iterations) is not int or max_iterations<1:raise CalibrationError('Positive iteration count required')
    dual=RoleDual(picks,prior,special_targets,flex_targets)
    feasible=dual.feasibility(feasibility_seconds)
    solved=minimize(dual.objective_gradient,np.zeros(2*dual.n),jac=True,method='L-BFGS-B',
        options={'maxiter':max_iterations,'gtol':min(1e-10,tolerance*.01),'ftol':1e-15,'maxls':50})
    w,_=dual.probabilities(solved.x);achieved=dual.marginals(w)
    error=float(np.max(np.abs(achieved-dual.target)))
    if not np.isfinite(w).all() or error>tolerance or abs(w.sum()-1)>1e-10:
        raise CalibrationNotConverged(f'Feasible targets; dual residual {error:g}, optimizer: {solved.message}')
    weights=np.zeros(dual.original_count);weights[dual.active]=w
    positive=w>0
    kl=float(np.sum(w[positive]*(np.log(w[positive])-dual.logq[positive])))
    diagnostics={'feasibility':feasible,'optimizer_success':bool(solved.success),'optimizer_message':str(solved.message),
        'iterations':int(solved.nit),'max_ownership_error':error,'kl_from_prior':kl,
        'effective_support':float(1/np.dot(w,w)),'positive_prior_support':len(w),
        'tolerance':tolerance,'offline_only':True}
    return CalibrationResult(weights,achieved[:dual.n],achieved[dual.n:],diagnostics)
