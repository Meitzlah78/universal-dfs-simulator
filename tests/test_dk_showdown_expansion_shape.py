import unittest

import numpy as np
from dk_showdown_engine import duplicate_expansion_counts, duplicate_expansion_weights


class DKShowdownExpansionShapeTests(unittest.TestCase):
    def test_duplicate_weights_preserve_long_tail_without_collapsing_field(self):
        rng = np.random.default_rng(20261016)
        log_popularity = rng.normal(-14.0, 2.0, size=10_000)
        weights = duplicate_expansion_weights(log_popularity)

        self.assertAlmostEqual(float(weights.sum()), 1.0, places=10)
        self.assertTrue(np.all(weights > 0))

        ordered = np.sort(weights)
        top_1pct_mass = float(ordered[-100:].sum())
        top_10pct_mass = float(ordered[-1000:].sum())
        median = float(np.median(weights))
        maximum = float(weights.max())

        self.assertLess(top_1pct_mass, 0.40)
        self.assertGreater(top_10pct_mass, 0.20)
        self.assertGreater(maximum / median, 8.0)

    def test_expanded_entry_mass_matches_real_showdown_shape(self):
        # Latest completed 47,271-lineup DK field: 11.22% singleton entry mass,
        # 55.72% in constructions duplicated 10+ times, and 38.69% in 20+.
        # Entry-mass realism belongs to the full-field multiplicity allocator,
        # not to a raw multinomial draw from the popularity weights alone.
        log_popularity = np.random.default_rng(20261016).normal(-14.0, 2.0, size=10_000)
        counts = duplicate_expansion_counts(log_popularity, 47_271, seed=7)
        positive = counts[counts > 0]

        singleton_mass = float(positive[positive == 1].sum() / counts.sum())
        ten_plus_mass = float(positive[positive >= 10].sum() / counts.sum())
        twenty_plus_mass = float(positive[positive >= 20].sum() / counts.sum())
        unique_rate = float(len(positive) / counts.sum())

        self.assertEqual(int(counts.sum()), 47_271)
        self.assertGreater(singleton_mass, 0.09)
        self.assertLess(singleton_mass, 0.13)
        self.assertGreater(ten_plus_mass, 0.48)
        self.assertLess(ten_plus_mass, 0.66)
        self.assertGreater(twenty_plus_mass, 0.32)
        self.assertLess(twenty_plus_mass, 0.50)
        self.assertGreater(unique_rate, 0.18)
        self.assertLess(unique_rate, 0.25)
        self.assertGreater(int(positive.max()), 300)

    def test_chalk_order_is_monotonic(self):
        log_popularity = np.linspace(-20.0, -5.0, 2000)
        weights = duplicate_expansion_weights(log_popularity)
        self.assertTrue(np.all(np.diff(weights) >= -1e-15))


if __name__ == "__main__":
    unittest.main()
