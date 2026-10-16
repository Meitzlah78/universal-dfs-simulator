import unittest

# Completed 47,271-entry DK Showdown contest 196689724 (SEA-DEN).
# These are entry-mass score thresholds from the actual contest, not model output.
ENTRIES = 47_271
UNIQUE_LINEUPS = 10_547
WINNING_SCORE = 106.62
TOP_1_SCORE = 98.00
TOP_5_SCORE = 90.619995
TOP_10_SCORE = 86.33
TOP_20_SCORE = 82.22
FIELD_MEAN_SCORE = 70.932656
FIELD_MEDIAN_SCORE = 72.88
FIELD_SCORE_STD = 13.498677


class DKShowdownRealContestScoreTargetTests(unittest.TestCase):
    def test_real_contest_score_order_is_sensible(self):
        self.assertGreater(WINNING_SCORE, TOP_1_SCORE)
        self.assertGreater(TOP_1_SCORE, TOP_5_SCORE)
        self.assertGreater(TOP_5_SCORE, TOP_10_SCORE)
        self.assertGreater(TOP_10_SCORE, TOP_20_SCORE)
        self.assertGreater(TOP_20_SCORE, FIELD_MEDIAN_SCORE)

    def test_real_contest_has_large_score_separation(self):
        # Competitive selection has to care about the upper tail: the top 1%
        # finished more than 25 DK points above the median in this real field.
        self.assertGreater(TOP_1_SCORE - FIELD_MEDIAN_SCORE, 25.0)
        self.assertGreater(WINNING_SCORE - FIELD_MEAN_SCORE, 35.0)
        self.assertGreater(FIELD_SCORE_STD, 13.0)

    def test_real_contest_unique_rate_matches_calibration_target(self):
        self.assertAlmostEqual(UNIQUE_LINEUPS / ENTRIES, 0.22308, places=4)


if __name__ == "__main__":
    unittest.main()
