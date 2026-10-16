import math
import unittest

import pandas as pd

from dk_showdown_build import build_showdown_candidates


class ShowdownBuildAdapterTests(unittest.TestCase):
    def setUp(self):
        self.players = pd.DataFrame({
            "Name": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "Salary": [10000, 9000, 8000, 7000, 6000, 5000, 4000, 3000],
            "Team": ["X", "Y", "X", "Y", "X", "Y", "X", "Y"],
        })
        self.sim = {
            name: {"Mean": 20-i, "P95": (20-i)*1.5, "P99": (20-i)*1.8, "StdDev": (20-i)*0.35}
            for i, name in enumerate(self.players["Name"])
        }
        self.own = {name: 10.0 + i for i, name in enumerate(self.players["Name"])}

    def test_adapter_returns_contest_sim_schema(self):
        result = build_showdown_candidates(
            self.players, self.sim, self.own, candidate_count=25, salary_cap=100000
        )
        for column in [
            "Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5",
            "Salary", "SimMean", "SimP95", "SimP99", "Score"
        ]:
            self.assertIn(column, result.columns)
        self.assertLessEqual(len(result), 25)
        self.assertEqual(result.attrs["retained_lineups"], len(result))

    def test_adapter_applies_only_hard_build_controls(self):
        controls = pd.DataFrame({
            "Name": self.players["Name"],
            "Fade": [False, False, False, False, False, False, False, True],
            "Lock": [False, True, False, False, False, False, False, False],
            "Captain Max %": [0, 100, 100, 100, 100, 100, 100, 100],
            # These exposure settings deliberately conflict with a competitive pool.
            # Candidate generation must ignore them; they belong after Contest Sim.
            "Max Exposure %": [5] * 8,
            "Min Exposure %": [95] * 8,
        })
        result = build_showdown_candidates(
            self.players, self.sim, self.own, controls=controls,
            candidate_count=100, salary_cap=100000
        )
        self.assertFalse(result.empty)
        self.assertTrue((result["Captain"] != "A").all())
        self.assertFalse(result[["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]].eq("H").any().any())
        self.assertTrue(result[["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]].eq("B").any(axis=1).all())

    def test_adapter_is_exhaustive_over_eligible_captains(self):
        result = build_showdown_candidates(
            self.players, self.sim, self.own, candidate_count=10, salary_cap=100000
        )
        expected = len(self.players) * math.comb(len(self.players) - 1, 5)
        self.assertEqual(result.attrs["examined_lineups"], expected)


if __name__ == "__main__":
    unittest.main()
