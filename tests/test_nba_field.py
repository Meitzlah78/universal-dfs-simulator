import unittest
import numpy as np
from simmah_nba_field import build_field

class NBAFieldTests(unittest.TestCase):
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
