import unittest

import numpy as np

from dk_showdown_engine import sample_opponent_batch


class DKShowdownCaptainCalibrationTests(unittest.TestCase):
    """Guard the public-field captain concentration seen in completed DK fields."""

    def test_sharpened_captain_curve_reaches_real_field_concentration(self):
        # BUF@LAR's completed 59,453-entry field put about 59.7% of entries on
        # its top four Captains.  Use a representative ownership curve and make
        # sure the DK-specific captain transform lands in that neighborhood
        # without collapsing the field onto only a few players.
        base = np.array([
            0.18, 0.145, 0.115, 0.09, 0.075, 0.065, 0.055, 0.05,
            0.045, 0.04, 0.035, 0.03, 0.025, 0.02, 0.015, 0.01,
        ], dtype=float)
        base /= base.sum()
        captain = np.power(base, 1.45)
        captain /= captain.sum()

        rng = np.random.default_rng(20261016)
        captains, _ = sample_opponent_batch(rng, captain, base, 100_000)
        shares = np.bincount(captains, minlength=len(base)) / len(captains)
        top_four = float(np.sort(shares)[-4:].sum())

        self.assertGreater(top_four, 0.55)
        self.assertLess(top_four, 0.70)
        self.assertGreater(int(np.count_nonzero(shares > 0.005)), 8)


if __name__ == "__main__":
    unittest.main()
