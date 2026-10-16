import unittest

import numpy as np

from dk_showdown_engine import opponent_lineup_means, opponent_quality_acceptance


class DKShowdownOpponentQualityTests(unittest.TestCase):
    def test_lineup_mean_uses_captain_multiplier(self):
        means = np.array([20.0, 16.0, 12.0, 10.0, 8.0, 6.0, 4.0])
        captains = np.array([0, 1])
        flex = np.array([[1, 2, 3, 4, 5], [0, 2, 3, 4, 6]])
        actual = opponent_lineup_means(captains, flex, means)
        expected = np.array([
            1.5 * 20.0 + 16.0 + 12.0 + 10.0 + 8.0 + 6.0,
            1.5 * 16.0 + 20.0 + 12.0 + 10.0 + 8.0 + 4.0,
        ])
        np.testing.assert_allclose(actual, expected)

    def test_quality_curve_keeps_tail_but_prefers_stronger_lineups(self):
        lineup_means = np.linspace(45.0, 90.0, 1001)
        acceptance = opponent_quality_acceptance(lineup_means)
        self.assertGreaterEqual(float(acceptance.min()), 0.18)
        self.assertLessEqual(float(acceptance.max()), 1.0)
        self.assertTrue(np.all(np.diff(acceptance) >= 0.0))
        self.assertGreater(float(acceptance[-100:].mean()), float(acceptance[:100].mean()) * 2.0)

    def test_acceptance_lifts_sampled_field_without_collapsing_diversity(self):
        rng = np.random.default_rng(20261016)
        lineup_means = rng.normal(68.0, 8.0, 100000)
        acceptance = opponent_quality_acceptance(lineup_means)
        kept = lineup_means[rng.random(len(lineup_means)) <= acceptance]
        self.assertGreater(float(kept.mean()), float(lineup_means.mean()) + 1.0)
        self.assertGreater(len(kept), 35000)
        self.assertGreater(float(np.std(kept)), 5.0)


if __name__ == "__main__":
    unittest.main()
