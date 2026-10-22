import unittest,itertools
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from simmah_single_calibration import (RoleDual,calibrate_role_weights,InfeasibleTargets,
    FeasibilityUnknown,CalibrationNotConverged,CalibrationError)

class CalibrationTests(unittest.TestCase):
    def support(self):
        return np.array([[c,*f] for c in range(7) for f in itertools.combinations([p for p in range(7) if p!=c],5)])
    def problem(self):
        picks=self.support();q=np.linspace(1,2,len(picks))
        base=RoleDual(picks,q,np.full(7,1/7),np.full(7,5/7))
        theta=np.random.default_rng(4).normal(0,.3,14)
        truth,_=base.probabilities(theta);target=base.marginals(truth)
        return picks,q,truth,target
    def test_gradient_sign_matches_finite_difference(self):
        picks,q,_,target=self.problem();dual=RoleDual(picks,q,target[:7],target[7:])
        theta=np.linspace(-.5,.5,14);_,gradient=dual.objective_gradient(theta)
        numerical=[]
        for k in range(14):
            step=np.zeros(14);step[k]=1e-6
            numerical.append((dual.objective_gradient(theta+step)[0]-dual.objective_gradient(theta-step)[0])/2e-6)
        np.testing.assert_allclose(gradient,numerical,atol=1e-8)
    def test_recovers_known_kl_projection(self):
        picks,q,truth,target=self.problem();result=calibrate_role_weights(picks,q,target[:7],target[7:])
        np.testing.assert_allclose(result.weights,truth,atol=1e-6)
        self.assertLess(result.diagnostics['max_ownership_error'],1e-6)
    def test_prior_already_matches_stays_unchanged(self):
        picks,q,_,_=self.problem();d=RoleDual(picks,q,np.full(7,1/7),np.full(7,5/7));w,_=d.probabilities(np.zeros(14));t=d.marginals(w)
        r=calibrate_role_weights(picks,q,t[:7],t[7:]);np.testing.assert_allclose(r.weights,w,atol=1e-10)
    def test_support_infeasibility_separate_from_bad_totals(self):
        picks=self.support();picks=picks[picks[:,0]!=0]
        with self.assertRaises(InfeasibleTargets):calibrate_role_weights(picks,np.ones(len(picks)),np.full(7,1/7),np.full(7,5/7))
        with self.assertRaises(InfeasibleTargets):RoleDual(self.support(),np.ones(42),np.zeros(7),np.full(7,5/7))
    def test_zero_prior_support_not_revived(self):
        picks,q,_,_=self.problem();q[0]=0
        d=RoleDual(picks,q,np.full(7,1/7),np.full(7,5/7));w,_=d.probabilities(np.zeros(14));t=d.marginals(w)
        r=calibrate_role_weights(picks,q,t[:7],t[7:]);self.assertEqual(r.weights[0],0)
    def test_timeout_is_unknown_not_infeasible(self):
        picks,q,_,target=self.problem();d=RoleDual(picks,q,target[:7],target[7:])
        with patch('simmah_single_calibration.linprog',return_value=SimpleNamespace(status=1,message='Time limit')):
            with self.assertRaises(FeasibilityUnknown):d.feasibility()
    def test_feasible_optimizer_failure_does_not_mean_infeasible(self):
        picks,q,_,target=self.problem()
        with self.assertRaises(CalibrationNotConverged):calibrate_role_weights(picks,q,target[:7],target[7:],max_iterations=1,tolerance=1e-12)
    def test_bad_roster_and_percentage_inputs_rejected(self):
        picks,q,_,target=self.problem();picks[0,1]=picks[0,0]
        with self.assertRaises(CalibrationError):RoleDual(picks,q,target[:7],target[7:])
        with self.assertRaises(CalibrationError):RoleDual(self.support(),q,target[:7]*100,target[7:]*100)

    def test_rare_role_targets_converge_with_scaling(self):
        picks,q,_,_=self.problem()
        d=RoleDual(picks,q,np.full(7,1/7),np.full(7,5/7))
        theta=np.zeros(14);theta[0]=-10;theta[8]=-5
        w,_=d.probabilities(theta);target=d.marginals(w)
        r=calibrate_role_weights(picks,q,target[:7],target[7:])
        self.assertLess(r.diagnostics['max_ownership_error'],1e-6)
