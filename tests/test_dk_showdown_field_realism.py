import unittest

import numpy as np

from dk_showdown_engine import duplicate_expansion_weights, sample_opponent_batch


class DKShowdownFieldRealismTests(unittest.TestCase):
    def test_duplicate_weights_are_normalized_and_chalk_sensitive(self):
        log_weights = np.linspace(-6.0, 0.0, 1000)
        weights = duplicate_expansion_weights(log_weights)
        self.assertAlmostEqual(float(weights.sum()), 1.0, places=12)
        self.assertTrue(np.all(weights >= 0.0))
        self.assertGreater(float(weights[-1]), float(weights[0]))
        # The calibrated mixture should preserve a broad field while still
        # assigning materially more mass to the chalkiest constructions.
        self.assertGreater(float(weights[-100:].sum()), float(weights[:100].sum()) * 2.0)

    def test_opponent_sampler_respects_captain_and_flex_weights(self):
        rng = np.random.default_rng(20261016)
        captain_weights = np.array([0.70, 0.20, 0.07, 0.02, 0.01, 0.001, 0.001])
        flex_weights = np.array([0.45, 0.25, 0.12, 0.08, 0.05, 0.03, 0.02])
        captains, flex = sample_opponent_batch(rng, captain_weights, flex_weights, 20000)
        self.assertEqual(flex.shape, (20000, 5))
        # Captain can never also occupy FLEX.
        self.assertFalse(np.any(flex == captains[:, None]))
        # Sampling should retain a strong public-field preference rather than
        # collapsing toward uniform player selection.
        captain_share = np.bincount(captains, minlength=len(captain_weights)) / len(captains)
        self.assertGreater(float(captain_share[0]), 0.60)
        self.assertGreater(float(captain_share[0]), float(captain_share[-1]) * 100.0)

    def test_flex_sampler_never_duplicates_a_player(self):
        rng = np.random.default_rng(7)
        weights = np.arange(1.0, 13.0)
        captains, flex = sample_opponent_batch(rng, weights, weights, 5000)
        for row, captain in zip(flex, captains):
            self.assertEqual(len(set(map(int, row))), 5)
            self.assertNotIn(int(captain), set(map(int, row)))


if __name__ == "__main__":
    unittest.main()
