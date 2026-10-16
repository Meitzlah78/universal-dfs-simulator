import unittest

import numpy as np


def captain_weights(base, has_external_cpt):
    values = np.clip(np.asarray(base, dtype=float), 0.01, None)
    # A real Field CPT Own % column is already role-specific public ownership.
    # Sharpen only a fallback curve derived from FLEX/projection ownership.
    if not has_external_cpt:
        values = np.power(values, 1.45)
    return values / values.sum()


class DKShowdownCaptainSourceBehaviorTests(unittest.TestCase):
    def test_real_captain_ownership_is_not_double_sharpened(self):
        base = np.array([0.30, 0.24, 0.18, 0.12, 0.08, 0.05, 0.03])
        actual = captain_weights(base, has_external_cpt=True)
        expected = np.clip(base, 0.01, None)
        expected /= expected.sum()
        np.testing.assert_allclose(actual, expected)

    def test_fallback_captain_curve_is_sharpened(self):
        base = np.array([0.18, 0.145, 0.115, 0.09, 0.075, 0.065, 0.055, 0.05])
        plain = captain_weights(base, has_external_cpt=True)
        fallback = captain_weights(base, has_external_cpt=False)
        self.assertGreater(fallback[:4].sum(), plain[:4].sum())


if __name__ == "__main__":
    unittest.main()
