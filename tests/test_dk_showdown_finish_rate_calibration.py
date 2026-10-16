import unittest

import numpy as np

from dk_showdown_engine import opponent_quality_acceptance


class DKShowdownFinishRateCalibrationTests(unittest.TestCase):
    """Guard against the historical unrealistically soft opponent-field failure."""

    def test_quality_calibration_reduces_candidate_top_one_rate(self):
        rng = np.random.default_rng(20261018)
        n_sims = 20_000
        field_size = 10_000

        # Approximate scenario-to-scenario lineup outcomes while keeping this test
        # cheap enough for CI. Candidate and field share the same game environment;
        # the only comparison is raw ownership sampling vs quality-calibrated field.
        game = rng.normal(0.0, 7.0, size=n_sims)
        candidate = 79.0 + game + rng.normal(0.0, 8.0, size=n_sims)

        raw_means = rng.normal(72.0, 8.5, size=120_000)
        acceptance = opponent_quality_acceptance(raw_means)
        calibrated_means = raw_means[rng.random(len(raw_means)) <= acceptance]

        # Top-1% threshold for a 10k-entry field is the 99th percentile of
        # opponent outcomes. Estimate it across the same correlated game states.
        raw_noise = rng.normal(0.0, 8.0, size=250_000)
        calibrated_noise = rng.normal(0.0, 8.0, size=250_000)
        raw_threshold = float(np.quantile(rng.choice(raw_means, 250_000) + raw_noise, 0.99))
        calibrated_threshold = float(
            np.quantile(rng.choice(calibrated_means, 250_000) + calibrated_noise, 0.99)
        )

        raw_top1 = float(np.mean(candidate - game >= raw_threshold))
        calibrated_top1 = float(np.mean(candidate - game >= calibrated_threshold))

        self.assertGreater(calibrated_threshold, raw_threshold + 1.0)
        self.assertLess(calibrated_top1, raw_top1)
        # The old app portfolio averaged roughly 7-8% Top-1%. A representative
        # optimized lineup should not clear a 10k-field Top-1% threshold that often.
        self.assertLess(calibrated_top1, 0.05)

    def test_calibrated_field_keeps_nonzero_upside_for_good_lineup(self):
        rng = np.random.default_rng(20261019)
        field = rng.normal(72.0, 8.5, size=150_000)
        acceptance = opponent_quality_acceptance(field)
        calibrated = field[rng.random(len(field)) <= acceptance]
        threshold = float(np.quantile(calibrated + rng.normal(0.0, 8.0, len(calibrated)), 0.99))
        candidate = rng.normal(79.0, 8.0, size=100_000)
        top1 = float(np.mean(candidate >= threshold))
        self.assertGreater(top1, 0.001)
        self.assertLess(top1, 0.05)


if __name__ == "__main__":
    unittest.main()
