import unittest

import pandas as pd

from dk_showdown_build import build_showdown_candidates


class ShowdownBuildAdapterTests(unittest.TestCase):
    def setUp(self):
        self.players = pd.DataFrame({
            "Name": list("ABCDEFGH"),
            "Salary": [10000, 9000, 8000, 7000, 6000, 5000, 4000, 3000],
            "Team": ["X", "Y", "X", "Y", "X", "Y", "X", "Y"],
        })
        self.sim = {
            name: {"Mean": 20-i, "P95": (20-i)*1.5, "P99": (20-i)*1.8, "StdDev": 4.0}
            for i, name in enumerate(self.players["Name"])
        }
        self.own = {name: 10.0 + i for i, name in enumerate(self.players["Name"])}

    def test_build_returns_requested_competitive_pool(self):
        result = build_showdown_candidates(self.players, self.sim, self.own, candidate_count=12, salary_cap=100000)
        self.assertEqual(len(result), 12)
        self.assertTrue(result["CandidateScore"].is_monotonic_decreasing)

    def test_fade_is_hard_eligibility_constraint(self):
        controls = pd.DataFrame({"Name": list("ABCDEFGH"), "Fade": [True, False, False, False, False, False, False, False]})
        result = build_showdown_candidates(self.players, self.sim, self.own, controls=controls, candidate_count=100, salary_cap=100000)
        roster_cols = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        self.assertFalse(result[roster_cols].eq("A").any().any())

    def test_lock_is_in_every_candidate(self):
        controls = pd.DataFrame({"Name": list("ABCDEFGH"), "Lock": [True, False, False, False, False, False, False, False]})
        result = build_showdown_candidates(self.players, self.sim, self.own, controls=controls, candidate_count=100, salary_cap=100000)
        roster_cols = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        self.assertTrue(result[roster_cols].eq("A").any(axis=1).all())

    def test_zero_captain_max_blocks_only_captain_slot(self):
        controls = pd.DataFrame({"Name": list("ABCDEFGH"), "Captain Max %": [0, 100, 100, 100, 100, 100, 100, 100]})
        result = build_showdown_candidates(self.players, self.sim, self.own, controls=controls, candidate_count=100, salary_cap=100000)
        self.assertFalse(result["Captain"].eq("A").any())
        self.assertTrue(result[["Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]].eq("A").any().any())

    def test_salary_floor_and_cap_are_hard_constraints(self):
        result = build_showdown_candidates(self.players, self.sim, self.own, candidate_count=100, salary_floor=39000, salary_cap=45000)
        self.assertTrue(result["Salary"].between(39000, 45000).all())

    def test_build_does_not_force_portfolio_uniqueness(self):
        result = build_showdown_candidates(self.players, self.sim, self.own, candidate_count=30, salary_cap=100000)
        roster_cols = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        sets = [set(row) for row in result[roster_cols].itertuples(index=False, name=None)]
        # Competitive candidate generation may retain highly overlapping lineups.
        self.assertTrue(any(len(a & b) >= 5 for i, a in enumerate(sets) for b in sets[i+1:]))


if __name__ == "__main__":
    unittest.main()
