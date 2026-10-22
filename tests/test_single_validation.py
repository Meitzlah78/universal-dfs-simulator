import unittest,itertools
import numpy as np
from simmah_single_validation import joint_probabilities,compare_fields as compare_raw,salary_distribution,kl_divergence

def compare_fields(*args,**kwargs):
    return compare_raw(*args,slate_id="test",reference_slate_id="test",site="dk",reference_site="dk",**kwargs)

class ValidationTests(unittest.TestCase):
    def inputs(self):
        p=np.array([[0,1,2,3,4,5],[1,0,2,3,4,6],[6,0,1,2,3,4]])
        return p,np.array([2.,3.,5.]),np.array([48000.,49000.,50000.]),[str(i) for i in range(7)]
    def test_joint_against_explicit_outer_products(self):
        p,w,_,ids=self.inputs();w=w/w.sum()
        for roles in [True,False]:
            x=np.zeros((len(p),len(ids)*(2 if roles else 1)))
            for row,picks in enumerate(p):
                x[row,picks[0]]=1
                x[row,picks[1:]+(len(ids) if roles else 0)]=1
            result=joint_probabilities(p,w,len(ids),roles=roles)
            expected=sum(weight*np.outer(row,row) for weight,row in zip(w,x))
            np.testing.assert_allclose(result['joint'],expected)
            np.testing.assert_allclose(result['covariance'],expected-np.outer(w@x,w@x))
    def test_reference_id_reorder_aligns_exactly(self):
        p,w,s,ids=self.inputs();rev=np.arange(6,-1,-1)
        r=compare_fields(p,w,s,ids,rev[p],w,s,ids[::-1],prior=w)
        self.assertAlmostEqual(r['roles']['summary']['pair_mae_pp'],0)
        self.assertAlmostEqual(r['salary']['wasserstein_dollars'],0)
        self.assertAlmostEqual(r['kl_from_prior'],0)
    def test_signed_residual_and_impossible_pairs(self):
        p,w,s,ids=self.inputs();r=compare_fields(p,[1,0,0],s,ids,p,[0,1,0],s,ids)
        self.assertAlmostEqual(r['roles']['joint_residual'][0,7+1],1)
        self.assertAlmostEqual(r['roles']['joint_residual'][1,7+0],-1)
        np.testing.assert_array_equal(np.diag(r['roles']['simulated']['joint'][:7,7:]),0)
    def test_weighted_salary_cdf(self):
        p,w,s,ids=self.inputs();d=salary_distribution(s,w)
        self.assertEqual(d['quantiles']['0.5'],49000)
        r=compare_fields(p,[1,0,0],s,ids,p,[0,0,1],s,ids)
        self.assertAlmostEqual(r['salary']['wasserstein_dollars'],2000)
        self.assertAlmostEqual(r['salary']['cdf_max_abs_difference'],1)
    def test_kl_zero_support_is_infinite(self):
        self.assertTrue(np.isinf(kl_divergence([.5,.5],[1,0])))
    def test_mismatched_players_and_bad_weights_rejected(self):
        p,w,s,ids=self.inputs()
        with self.assertRaises(ValueError):compare_fields(p,w,s,ids,p,w,s,ids[:-1]+['other'])
        for bad in ([0,0,0],[1,np.nan,1],[-1,1,1]):
            with self.assertRaises(ValueError):joint_probabilities(p,bad,7)

    def test_cross_slate_and_cross_site_rejected(self):
        args=self.inputs();p,w,s,ids=args
        for reference_slate,reference_site in [('other','dk'),('test','fd')]:
            with self.assertRaises(ValueError):
                compare_raw(p,w,s,ids,p,w,s,ids,slate_id='test',reference_slate_id=reference_slate,site='dk',reference_site=reference_site)
