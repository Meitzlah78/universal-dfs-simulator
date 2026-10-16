import unittest

import pandas as pd

from dk_portfolio_selection import min_unique_players, select_post_sim_portfolio


class DKShowdownPostSimDiversificationTests(unittest.TestCase):
    def setUp(self):
        self.pool = pd.DataFrame([
            {"Captain": "A", "Flex1": "B", "Flex2": "C", "Flex3": "D", "Flex4": "E", "Flex5": "F", "Expected ROI (%)": 50.0},
            {"Captain": "A", "Flex1": "B", "Flex2": "C", "Flex3": "D", "Flex4": "E", "Flex5": "G", "Expected ROI (%)": 40.0},
            {"Captain": "A", "Flex1": "B", "Flex2": "C", "Flex3": "D", "Flex4": "H", "Flex5": "I", "Expected ROI (%)": 30.0},
            {"Captain": "A", "Flex1": "B", "Flex2": "C", "Flex3": "J", "Flex4": "K", "Flex5": "L", "Expected ROI (%)": 20.0},
        ])

    def test_zero_uniques_keeps_best_ev_even_when_lineups_overlap(self):
        result = select_post_sim_portfolio(self.pool, 2, min_uniques=0)
        self.assertEqual(result["Expected ROI (%)"].tolist(), [50.0, 40.0])

    def test_one_unique_allows_five_shared_players(self):
        result = select_post_sim_portfolio(self.pool, 2, min_uniques=1)
        self.assertEqual(result["Expected ROI (%)"].tolist(), [50.0, 40.0])
        self.assertEqual(min_unique_players(result.iloc[0][0:6], result.iloc[1][0:6]), 1)

    def test_two_uniques_skips_one_unique_lineup(self):
        result = select_post_sim_portfolio(self.pool, 2, min_uniques=2)
        self.assertEqual(result["Expected ROI (%)"].tolist(), [50.0, 30.0])

    def test_three_uniques_selects_three_player_difference(self):
        result = select_post_sim_portfolio(self.pool, 2, min_uniques=3)
        self.assertEqual(result["Expected ROI (%)"].tolist(), [50.0, 20.0])

    def test_diversification_never_changes_candidate_pool(self):
        original = self.pool.copy(deep=True)
        select_post_sim_portfolio(self.pool, 3, min_uniques=2)
        pd.testing.assert_frame_equal(self.pool, original)

    def test_no_hidden_exposure_cap(self):
        result = select_post_sim_portfolio(self.pool, 4, min_uniques=0)
        self.assertEqual(len(result), 4)
        self.assertTrue((result["Captain"] == "A").all())

    def test_invalid_uniques_rejected(self):
        with self.assertRaises(ValueError):
            select_post_sim_portfolio(self.pool, 2, min_uniques=-1)
        with self.assertRaises(ValueError):
            select_post_sim_portfolio(self.pool, 2, min_uniques=7)


if __name__ == "__main__":
    unittest.main()
