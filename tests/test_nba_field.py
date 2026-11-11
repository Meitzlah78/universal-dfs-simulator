import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from simmah_nba_field import build_field

class NBAFieldTests(unittest.TestCase):
    def test_failed_exact_fit_recovers_within_tolerance_on_both_sites(self):
        import simmah_nba_field as field
        optimize=field.minimize
        for size in (8,9):
            ids=np.array([list(range(size)),list(range(size-1))+[size]])
            target=np.r_[np.full(size-1,99.6),[50+.2*(size-1)]*2]
            stalled=SimpleNamespace(x=np.r_[np.zeros(size),100.],success=False,
                                    message='Iteration limit reached')
            def solve(*args,**kwargs):
                return stalled if 'bounds' not in kwargs else optimize(*args,**kwargs)
            with patch.object(field,'minimize',side_effect=solve):
                result=build_field(ids,target,50000,source='fixture',max_error_pct=5)
            self.assertGreater(result['initial_max_expected_error_pct'],40)
            self.assertLess(result['max_expected_error_pct'],2.51)
            self.assertEqual(result['fit_method'],'ownership-band entropy recovery')
            self.assertTrue(result['optimizer_converged'])
            self.assertEqual(result['copies'].sum(),50000)
            np.testing.assert_array_equal(result['ownership_target'],target)
            self.assertTrue(all(tuple(row) in set(map(tuple,ids)) for row in result['indices']))
            probabilities=result['fit_state']['probabilities']
            self.assertAlmostEqual(probabilities.sum(),1)
            self.assertTrue(np.isfinite(probabilities).all())

    def test_infeasible_support_still_reports_error_after_recovery(self):
        ids=np.array([list(range(8)),list(range(1,9))])
        result=build_field(ids,np.full(9,800/9),1000,source='infeasible')
        self.assertGreater(result['max_expected_error_pct'],5)
        self.assertEqual(result['copies'].sum(),1000)

    def support(self):
        rng=np.random.default_rng(7)
        return np.array([rng.choice(20,9,replace=False) for _ in range(100)])
    def test_fit_counts_and_duplicate_compression(self):
        ids=self.support();target=100*np.bincount(ids.ravel(),minlength=20)/len(ids)
        r=build_field(np.vstack([ids,ids]),target,50000,source='synthetic test targets')
        self.assertEqual(r['copies'].sum(),50000)
        self.assertLessEqual(r['unique_rosters'],100)
        self.assertLess(r['max_expected_error_pct'],.1)
        np.testing.assert_allclose(r['ownership_sampled'].sum(),900)
        again=build_field(ids,target,50000,source='synthetic test targets')
        np.testing.assert_array_equal(r['copies'],again['copies'])
    def test_unsupported_or_incomplete_ownership_rejected(self):
        ids=self.support()
        with self.assertRaises(ValueError):build_field(ids,np.ones(20),100,source='test')
        target=np.r_[np.full(20,44.5),10]
        with self.assertRaises(ValueError):build_field(ids,target,100,source='test')
        with self.assertRaises(ValueError):build_field(ids,np.full(20,45),100)

    def test_relative_popularity_is_labeled_estimate_not_normalized_ownership(self):
        from simmah_nba_field import sample_popularity_field
        ids=self.support();raw=np.linspace(1,90,20)
        self.assertNotAlmostEqual(raw.sum(),900)
        r=sample_popularity_field(ids,raw,10000,source='synthetic relative scores')
        self.assertEqual(r['copies'].sum(),10000)
        self.assertAlmostEqual(r['ownership_expected'].sum(),900)
        self.assertAlmostEqual(r['ownership_sampled'].sum(),900)
        self.assertIn('Estimated',r['ownership_source'])
        self.assertNotIn('ownership_target',r)
        self.assertTrue(0<r['largest_roster_probability']<=1)

    def test_roundoff_at_tiny_final_bin(self):
        from simmah_nba_field import _draw_copies
        p = np.array([0., .8, .2 + 1e-11, 1e-25])
        with self.assertRaises(ValueError):
            np.random.default_rng(83).multinomial(20000, p)
        counts = _draw_copies(20000, p, 83)
        self.assertEqual(counts.sum(), 20000)
        np.testing.assert_allclose(counts / 20000, p, atol=.012)
        np.testing.assert_array_equal(counts, _draw_copies(20000, p, 83))
        with self.assertRaises(ValueError):
            _draw_copies(100, np.array([.8, .3, 0.]), 83)
