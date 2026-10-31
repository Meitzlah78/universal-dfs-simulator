import unittest,itertools
import numpy as np
from scipy.special import logsumexp
from simmah_single_partition import SalaryPartition
class PartitionTests(unittest.TestCase):
    def problem(self):
        s=np.array([1000,1200,1800,2400,3000,3400,4000]);teams=np.array(['A']*3+['B']*4)
        e=SalaryPartition(s,s*3//2,teams,15000)
        rows=np.array([[c,*f] for c in range(7) for f in itertools.combinations([i for i in range(7) if i!=c],5) if s[c]*1.5+s[list(f)].sum()<=15000 and len(set(teams[[c,*f]]))==2])
        return e,s,rows
    def test_partition_marginals_salary_against_enumeration(self):
        e,s,rows=self.problem();theta=np.linspace(-.3,.4,14)
        logits=theta[rows[:,0]]+theta[7+rows[:,1:]].sum(axis=1);w=np.exp(logits-logsumexp(logits))
        logz,m,d=e.evaluate(theta);t=np.r_[np.bincount(rows[:,0],weights=w,minlength=7),sum(np.bincount(rows[:,i],weights=w,minlength=7) for i in range(1,6))]
        self.assertAlmostEqual(logz,logsumexp(logits));np.testing.assert_allclose(m,t,atol=1e-12)
        cost=(s[rows[:,0]]*1.5+s[rows[:,1:]].sum(axis=1)).astype(int)
        np.testing.assert_allclose(d,np.bincount(cost//e.unit,weights=w,minlength=len(d)),atol=1e-12)
    def test_log_partition_gradient(self):
        e,_,_=self.problem();theta=np.linspace(-.3,.4,14);_,g,_=e.evaluate(theta)
        for i in range(14):
            d=np.zeros(14);d[i]=1e-6
            self.assertAlmostEqual(g[i],(e.evaluate(theta+d,gradient=False)[0]-e.evaluate(theta-d,gradient=False)[0])/2e-6,places=7)
    def test_calibration_recovers_targets(self):
        e,_,_=self.problem();_,t,_=e.evaluate(np.linspace(-1,1,14));r=e.calibrate(t[:7],t[7:]);np.testing.assert_allclose(r['marginal'],t,atol=1e-6)

    def test_exact_pair_moments_against_explicit_joint(self):
        e,_,rows=self.problem();theta=np.linspace(-.3,.4,14)
        logits=theta[rows[:,0]]+theta[7+rows[:,1:]].sum(axis=1);w=np.exp(logits-logsumexp(logits))
        x=np.zeros((len(rows),14))
        for r,p in enumerate(rows):x[r,p[0]]=1;x[r,7+p[1:]]=1
        target=w@x
        marginal,joint,cov=e.role_moments(theta,target[:7],target[7:])
        expected=x.T@(x*w[:,None])
        np.testing.assert_allclose(joint,expected,atol=1e-12)
        np.testing.assert_allclose(cov,expected-np.outer(target,target),atol=1e-12)

    def test_integer_salary_and_cap_contract(self):
        for salaries,cap in [([1000.5]*6,15000),([1000]*6,15000.5)]:
            with self.assertRaises(ValueError):SalaryPartition(salaries,[1500]*6,['A']*3+['B']*3,cap)
    def test_zero_target_face_preserves_full_prior_kl(self):
        e,s,rows=self.problem();mask=rows[:,0]!=0
        logits=np.zeros(mask.sum());w=np.ones(mask.sum())/mask.sum();r=rows[mask]
        t=np.r_[np.bincount(r[:,0],weights=w,minlength=7),sum(np.bincount(r[:,i],weights=w,minlength=7) for i in range(1,6))]
        fit=e.calibrate(t[:7],t[7:]);self.assertAlmostEqual(fit['marginal'][0],0)
        self.assertAlmostEqual(fit['diagnostics']['kl_from_full_uniform_prior'],np.log(len(rows)/len(r)),places=6)
