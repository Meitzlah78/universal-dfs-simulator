import math
import unittest

import pandas as pd

from dk_showdown_exhaustive import exhaustive_showdown_candidates, fast_exhaustive_showdown_candidates
from dk_showdown_engine import candidate_score


class ExhaustiveShowdownBuilderTests(unittest.TestCase):
    def setUp(self):
        self.players = pd.DataFrame({
            "Name": ["A", "B", "C", "D", "E", "F", "G"],
            "Salary": [10000, 9000, 8000, 7000, 6000, 5000, 4000],
            "Team": ["X", "Y", "X", "Y", "X", "Y", "X"],
            "Projection": [20, 18, 16, 14, 12, 10, 8],
        })
        self.proj = self.players["Projection"].tolist()
        self.sim = {
            name: {"Mean": p, "P95": p * 1.5, "P99": p * 1.8, "StdDev": p * 0.35}
            for name, p in zip(self.players["Name"], self.proj)
        }
        self.own = {name: 8.0 + i * 7.0 for i, name in enumerate(self.players["Name"])}

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

    def test_fast_prescreen_matches_production_candidate_score_ranking(self):
        weights = dict(p95_weight=.30, p99_weight=.55, mean_weight=.15, stddev_weight=.10)
        names = self.players["Name"].tolist()

        def production_score(captain, flex):
            return candidate_score(names[captain], [names[i] for i in flex], self.sim, self.own, **weights)["Score"]

        scalar = exhaustive_showdown_candidates(self.players, production_score, keep=10, salary_cap=100000)
        fast = fast_exhaustive_showdown_candidates(
            self.players, self.sim, self.own, keep=10, salary_cap=100000, **weights
        )
        lineup_columns = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        scalar_scores = {
            tuple(row[column] for column in lineup_columns): float(row["CandidateScore"])
            for _, row in scalar.iterrows()
        }
        fast_scores = {
            tuple(row[column] for column in lineup_columns): float(row["CandidateScore"])
            for _, row in fast.iterrows()
        }
        self.assertEqual(set(fast_scores), set(scalar_scores))
        for key in scalar_scores:
            self.assertAlmostEqual(fast_scores[key], scalar_scores[key], places=10)
        self.assertEqual(fast.attrs["examined_lineups"], scalar.attrs["examined_lineups"])
        self.assertEqual(fast.attrs["legal_lineups"], scalar.attrs["legal_lineups"])


if __name__ == "__main__":
    unittest.main()
