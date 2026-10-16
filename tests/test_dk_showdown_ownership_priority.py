import unittest

import numpy as np
import pandas as pd


FLEX_ALIASES = (
    "field flex own %", "field own %", "projected own %", "ownership %",
    "projected ownership", "projected own", "ownership", "own%", "own",
)
CPT_ALIASES = (
    "field cpt own %", "field captain own %", "captain ownership %", "cpt ownership %",
)


def pick_column(frame, aliases):
    lookup = {str(c).strip().casefold(): c for c in frame.columns}
    return next((lookup[k] for k in aliases if k in lookup), None)


class DKShowdownOwnershipPriorityTests(unittest.TestCase):
    def test_field_flex_ownership_beats_generic_and_projected_ownership(self):
        pool = pd.DataFrame({
            "Name": ["A", "B", "C"],
            "Field FLEX Own %": [60.0, 25.0, 15.0],
            "Field Own %": [40.0, 35.0, 25.0],
            "Projected Own %": [10.0, 20.0, 70.0],
        })
        col = pick_column(pool, FLEX_ALIASES)
        self.assertEqual(col, "Field FLEX Own %")
        # pandas 3 can expose a read-only NumPy view.  The production builder
        # does not normalize this array in place, so make the test copy explicit.
        weights = pd.to_numeric(pool[col]).to_numpy(dtype=float, copy=True)
        weights /= weights.sum()
        np.testing.assert_allclose(weights, [0.60, 0.25, 0.15])

    def test_field_overall_ownership_is_second_choice(self):
        pool = pd.DataFrame({
            "Field Own %": [55.0, 45.0],
            "Projected Own %": [20.0, 80.0],
        })
        self.assertEqual(pick_column(pool, FLEX_ALIASES), "Field Own %")

    def test_captain_ownership_is_separate_from_flex_ownership(self):
        pool = pd.DataFrame({
            "Field FLEX Own %": [70.0, 30.0],
            "Field CPT Own %": [20.0, 80.0],
        })
        self.assertEqual(pick_column(pool, FLEX_ALIASES), "Field FLEX Own %")
        self.assertEqual(pick_column(pool, CPT_ALIASES), "Field CPT Own %")


if __name__ == "__main__":
    unittest.main()
