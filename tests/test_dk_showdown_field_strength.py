import unittest

import numpy as np

from dk_showdown_engine import opponent_quality_acceptance


class DKShowdownFieldStrengthTests(unittest.TestCase):
    def test_quality_acceptance_strengthens_field_without_erasing_tail(self):
        rng = np.random.default_rng(20261016)
        # Representative legal ownership-weighted Showdown constructions.
        raw = rng.normal(72.0, 8.5, size=100_000)
        acceptance = opponent_quality_acceptance(raw)
        kept = raw[rng.random(len(raw)) <= acceptance]

        self.assertGreater(len(kept), 30_000)
        self.assertGreater(float(kept.mean() - raw.mean()), 1.5)
        self.assertGreater(float(kept.std()), 6.0)
        self.assertLess(float(np.percentile(kept, 10)), float(kept.mean() - 5.0))

    def test_quality_acceptance_reduces_optimized_candidate_edge(self):
        rng = np.random.default_rng(20261017)
        raw = rng.normal(72.0, 8.5, size=150_000)
        acceptance = opponent_quality_acceptance(raw)
        kept = raw[rng.random(len(raw)) <= acceptance]

        # A candidate optimized from the same projection environment should have
        # a smaller apparent edge versus a realistic field than versus raw
        # independent ownership draws. This guards the ROI inflation failure.
        candidate_mean = 79.0
        raw_edge = candidate_mean - float(raw.mean())
        calibrated_edge = candidate_mean - float(kept.mean())

        self.assertGreater(raw_edge, 5.0)
        self.assertLess(calibrated_edge, raw_edge - 1.5)
        self.assertGreater(calibrated_edge, 1.0)

    def test_acceptance_is_bounded_and_monotonic(self):
        means = np.linspace(45.0, 100.0, 500)
        acceptance = opponent_quality_acceptance(means, reference_mean=72.0)
        self.assertTrue(np.all(acceptance >= 0.18))
        self.assertTrue(np.all(acceptance <= 1.0))
        self.assertTrue(np.all(np.diff(acceptance) >= -1e-12))


if __name__ == '__main__':
    unittest.main()
