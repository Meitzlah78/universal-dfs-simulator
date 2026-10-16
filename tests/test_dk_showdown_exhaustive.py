import math
import unittest

import pandas as pd

from dk_showdown_exhaustive import exhaustive_showdown_candidates


class ExhaustiveShowdownBuilderTests(unittest.TestCase):
    def setUp(self):
        self.players = pd.DataFrame({
            "Name": ["A", "B", "C", "D", "E", "F", "G"],
            "Salary": [10000, 9000, 8000, 7000, 6000, 5000, 4000],
            "Team": ["X", "Y", "X", "Y", "X", "Y", "X"],
            "Projection": [20, 18, 16, 14, 12, 10, 8],
        })
        self.proj = self.players["Projection"].tolist()

    def score(self, captain, flex):
        return self.proj[captain] * 1.5 + sum(self.proj[i] for i in flex)

    def test_examines_entire_combinatorial_space(self):
        result = exhaustive_showdown_candidates(self.players, self.score, keep=5, salary_cap=100000)
        expected = len(self.players) * math.comb(len(self.players) - 1, 5)
        self.assertEqual(result.attrs["examined_lineups"], expected)
        self.assertEqual(len(result), 5)

    def test_retains_only_best_k_without_materializing_every_lineup(self):
        result = exhaustive_showdown_candidates(self.players, self.score, keep=3, salary_cap=100000)
        self.assertEqual(len(result), 3)
        self.assertEqual(result["CandidateScore"].tolist(), sorted(result["CandidateScore"], reverse=True))

    def test_salary_rules_are_applied_before_retention(self):
        result = exhaustive_showdown_candidates(self.players, self.score, keep=100, salary_cap=50000)
        self.assertTrue((result["Salary"] <= 50000).all())
        self.assertEqual(result.attrs["legal_lineups"], len(result))

    def test_captain_and_flex_never_repeat_same_player(self):
        result = exhaustive_showdown_candidates(self.players, self.score, keep=100, salary_cap=100000)
        for _, row in result.iterrows():
            roster = [row["Captain"], row["Flex1"], row["Flex2"], row["Flex3"], row["Flex4"], row["Flex5"]]
            self.assertEqual(len(set(roster)), 6)


if __name__ == "__main__":
    unittest.main()
