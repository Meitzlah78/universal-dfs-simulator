import unittest

import numpy as np
from dk_showdown_engine import duplicate_expansion_weights


class DKShowdownExpansionShapeTests(unittest.TestCase):
    def test_duplicate_weights_preserve_long_tail_without_collapsing_field(self):
        # Representative 10k public-field popularity scores. The exact slate
        # changes, but completed DK fields show both thousands of singletons and
        # a small extreme chalk tail with hundreds of copies.
        rng = np.random.default_rng(20261016)
        log_popularity = rng.normal(-14.0, 2.0, size=10_000)
        weights = duplicate_expansion_weights(log_popularity)

        self.assertAlmostEqual(float(weights.sum()), 1.0, places=10)
        self.assertTrue(np.all(weights > 0))

        # A realistic expansion cannot collapse almost all probability into a
        # handful of constructions, but the chalk tail must remain meaningfully
        # more likely than the median lineup.
        ordered = np.sort(weights)
        top_1pct_mass = float(ordered[-100:].sum())
        top_10pct_mass = float(ordered[-1000:].sum())
        median = float(np.median(weights))
        maximum = float(weights.max())

        self.assertLess(top_1pct_mass, 0.40)
        self.assertGreater(top_10pct_mass, 0.20)
        self.assertGreater(maximum / median, 8.0)

    def test_chalk_order_is_monotonic(self):
        log_popularity = np.linspace(-20.0, -5.0, 2000)
        weights = duplicate_expansion_weights(log_popularity)
        self.assertTrue(np.all(np.diff(weights) >= -1e-15))


if __name__ == "__main__":
    unittest.main()
