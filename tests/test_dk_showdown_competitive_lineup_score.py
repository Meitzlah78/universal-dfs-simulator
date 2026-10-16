import unittest

from dk_showdown_engine import candidate_score


class DKShowdownCompetitiveLineupScoreTests(unittest.TestCase):
    def _stats(self, mean, p95, p99, stddev):
        return {"Mean": mean, "P95": p95, "P99": p99, "StdDev": stddev}

    def test_ceiling_lineup_beats_same_mean_low_upside_lineup(self):
        players = {
            "CPT": self._stats(20, 30, 40, 8),
            "A": self._stats(10, 16, 24, 6),
            "B": self._stats(10, 16, 24, 6),
            "C": self._stats(10, 16, 24, 6),
            "D": self._stats(10, 16, 24, 6),
            "UP": self._stats(10, 22, 34, 10),
            "FLAT": self._stats(10, 12, 14, 2),
        }
        ownership = {name: 10.0 for name in players}
        common = ["A", "B", "C", "D"]
        upside = candidate_score("CPT", common + ["UP"], players, ownership, 0.45, 0.25, 0.20, 0.10)
        flat = candidate_score("CPT", common + ["FLAT"], players, ownership, 0.45, 0.25, 0.20, 0.10)
        self.assertAlmostEqual(upside["SimMean"], flat["SimMean"])
        self.assertGreater(upside["Score"], flat["Score"])

    def test_lower_owned_lineup_wins_when_fantasy_profile_is_identical(self):
        players = {name: self._stats(10, 18, 26, 7) for name in ["CPT", "A", "B", "C", "D", "LOW", "CHALK"]}
        ownership = {name: 12.0 for name in players}
        ownership["LOW"] = 5.0
        ownership["CHALK"] = 70.0
        common = ["A", "B", "C", "D"]
        low = candidate_score("CPT", common + ["LOW"], players, ownership, 0.45, 0.25, 0.20, 0.10)
        chalk = candidate_score("CPT", common + ["CHALK"], players, ownership, 0.45, 0.25, 0.20, 0.10)
        self.assertGreater(low["Score"], chalk["Score"])

    def test_projection_edge_is_not_sacrificed_for_leverage_alone(self):
        players = {name: self._stats(10, 18, 26, 7) for name in ["CPT", "A", "B", "C", "D"]}
        players["GOOD"] = self._stats(16, 27, 38, 9)
        players["PUNT"] = self._stats(4, 8, 12, 4)
        ownership = {name: 12.0 for name in players}
        ownership["GOOD"] = 55.0
        ownership["PUNT"] = 1.0
        common = ["A", "B", "C", "D"]
        good = candidate_score("CPT", common + ["GOOD"], players, ownership, 0.45, 0.25, 0.20, 0.10)
        punt = candidate_score("CPT", common + ["PUNT"], players, ownership, 0.45, 0.25, 0.20, 0.10)
        self.assertGreater(good["Score"], punt["Score"])

    def test_bad_uniqueness_cannot_beat_competitive_chalk(self):
        """A nearly unowned lineup still needs a credible fantasy ceiling.

        Completed-contest backtests showed that uniqueness by itself is not
        leverage: some old optimizer constructions were unique because they
        combined too many weak pieces.  Keep enough ownership benefit to reward
        a true leverage play, but never let an implausible low-owned lineup beat
        a materially stronger six-player construction.
        """
        names = ["CPT", "A", "B", "C", "D", "STRONG", "WEIRD"]
        players = {name: self._stats(11, 19, 28, 7) for name in names}
        players["STRONG"] = self._stats(18, 30, 43, 10)
        players["WEIRD"] = self._stats(2, 5, 9, 3)
        ownership = {name: 14.0 for name in names}
        ownership["STRONG"] = 65.0
        ownership["WEIRD"] = 0.2
        common = ["A", "B", "C", "D"]
        strong = candidate_score("CPT", common + ["STRONG"], players, ownership, 0.45, 0.25, 0.20, 0.10)
        weird = candidate_score("CPT", common + ["WEIRD"], players, ownership, 0.45, 0.25, 0.20, 0.10)
        self.assertGreater(strong["SimMean"], weird["SimMean"])
        self.assertGreater(strong["SimP95"], weird["SimP95"])
        self.assertGreater(strong["Score"], weird["Score"])


if __name__ == "__main__":
    unittest.main()
