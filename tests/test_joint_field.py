from itertools import combinations
import unittest
import numpy as np
from scipy import sparse
from simmah_joint_field import (single_game_features, expected_duplicate_curve,
    observed_duplicate_curve, fit_joint_field, JointFitNotConverged)


class JointFieldTest(unittest.TestCase):
    def support(self):
        return np.array([[captain,*flex] for captain in range(8)
            for flex in combinations([i for i in range(8) if i!=captain],5)],dtype=int)

    def test_sparse_roles_pairs_and_canonical_duplicate_rejection(self):
        picks=self.support()
        x=single_game_features(picks,8,[(0,1),(2,3)])
        self.assertEqual(x.shape,(18,len(picks)))
        np.testing.assert_array_equal(np.asarray(x[:8].sum(axis=0)).ravel(),1)
        np.testing.assert_array_equal(np.asarray(x[8:16].sum(axis=0)).ravel(),5)
        np.testing.assert_array_equal(x[16].toarray().ravel(),(picks==0).any(axis=1)&(picks==1).any(axis=1))
        with self.assertRaisesRegex(ValueError,'duplicate'):
            single_game_features(np.vstack([picks[0],picks[0,[0,5,4,3,2,1]]]),8)
        with self.assertRaises(ValueError):single_game_features(picks,8,[(1,0)])

    def test_duplicate_curve_matches_independent_tagged_entry_monte_carlo(self):
        w=np.array([.55,.25,.15,.05]);entries=40
        expected=expected_duplicate_curve(w,entries)
        rng=np.random.default_rng(83)
        counts=rng.multinomial(entries,w,size=20000)
        actual=np.mean([observed_duplicate_curve(row,entries) for row in counts],axis=0)
        np.testing.assert_allclose(expected,actual,atol=.003)
        self.assertAlmostEqual(expected.sum(),1)
        np.testing.assert_allclose(expected_duplicate_curve(np.array([1.]),1),[1,0,0,0,0,0])
        np.testing.assert_allclose(expected_duplicate_curve(np.array([1.]),100),[0,0,0,0,0,1])

    def test_duplicate_gradient_matches_finite_difference_on_simplex(self):
        w=np.array([.4,.3,.2,.1]);direction=np.array([.3,-.2,-.3,.2])
        curve,gradient=expected_duplicate_curve(w,120,gradient=True)
        h=1e-6
        numeric=(expected_duplicate_curve(w+h*direction,120)-expected_duplicate_curve(w-h*direction,120))/(2*h)
        np.testing.assert_allclose(gradient@direction,numeric,atol=1e-8,rtol=1e-6)

    def test_joint_fit_meets_roles_pairs_and_duplicate_bands_without_mutating_inputs(self):
        picks=self.support();x=single_game_features(picks,8,[(0,1),(2,3),(4,5)])
        # Known distribution supplies consistent targets; this is not historical evidence.
        logits=np.zeros(len(picks));logits[:15]=2.0;logits[30:70]=1.0
        truth=np.exp(logits);truth/=truth.sum()
        target=np.asarray(x@truth).ravel();duplicate=expected_duplicate_curve(truth,1000)
        prior=np.ones(len(picks))/len(picks);copy=picks.copy()
        args=dict(feature_tolerance=.002,duplicate_tolerance=.005,max_iterations=600,seed=83)
        result=fit_joint_field(x,target,prior,1000,duplicate,**args)
        self.assertTrue(result.diagnostics['accepted'])
        self.assertTrue(result.diagnostics['offline_only'])
        self.assertLessEqual(result.diagnostics['max_feature_error'],.002)
        self.assertLessEqual(result.diagnostics['max_duplicate_band_error'],.005)
        self.assertEqual(result.counts.sum(),1000)
        np.testing.assert_array_equal(picks,copy)
        np.testing.assert_array_equal(prior,np.ones(len(picks))/len(picks))
        repeated=fit_joint_field(x,target,prior,1000,duplicate,**args)
        np.testing.assert_array_equal(repeated.counts,result.counts)

    def test_stopping_never_accepts_one_matching_statistic_or_impossible_support(self):
        # One support row can only populate the last duplication band at N=100.
        x=sparse.csr_matrix([[1.]])
        with self.assertRaises(JointFitNotConverged) as context:
            fit_joint_field(x,[1.],[1.],100,[1,0,0,0,0,0],
                feature_tolerance=.001,duplicate_tolerance=.001)
        self.assertEqual(context.exception.diagnostics['max_feature_error'],0)
        self.assertEqual(context.exception.diagnostics['max_duplicate_band_error'],1)
        with self.assertRaisesRegex(ValueError,'support coverage'):
            fit_joint_field(sparse.csr_matrix([[0.,0.]]),[.5],[.5,.5],10,[1,0,0,0,0,0],
                feature_tolerance=.001,duplicate_tolerance=.01)

    def test_equal_field_size_and_count_validation(self):
        np.testing.assert_array_equal(observed_duplicate_curve(np.array([1,3,0]),4),[.25,.75,0,0,0,0])
        with self.assertRaises(ValueError):observed_duplicate_curve(np.array([1,3]),5)
        with self.assertRaises(ValueError):observed_duplicate_curve(np.array([1.,3.]),4)
        with self.assertRaises(ValueError):expected_duplicate_curve([.2,.2],10)


if __name__=='__main__':unittest.main()
