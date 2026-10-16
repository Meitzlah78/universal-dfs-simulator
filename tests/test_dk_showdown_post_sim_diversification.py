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

    def test_changing_diversification_only_reselects_scored_lineups(self):
        original = self.pool.copy(deep=True)
        no_forced_uniques = select_post_sim_portfolio(self.pool, 2, min_uniques=0)
        two_uniques = select_post_sim_portfolio(self.pool, 2, min_uniques=2)
        lineup_columns = ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
        scored_keys = set(map(tuple, self.pool[lineup_columns].astype(str).to_numpy()))
        for portfolio in (no_forced_uniques, two_uniques):
            selected_keys = set(map(tuple, portfolio[lineup_columns].astype(str).to_numpy()))
            self.assertTrue(selected_keys.issubset(scored_keys))
        self.assertNotEqual(
            no_forced_uniques.iloc[1][lineup_columns].astype(str).tolist(),
            two_uniques.iloc[1][lineup_columns].astype(str).tolist(),
        )
        pd.testing.assert_frame_equal(self.pool, original)

    def test_no_hidden_exposure_cap(self):
        result = select_post_sim_portfolio(self.pool, 4, min_uniques=0)
        self.assertEqual(len(result), 4)
        self.assertTrue((result["Captain"] == "A").all())

    def test_manual_player_max_exposure_is_authoritative(self):
        result = select_post_sim_portfolio(self.pool, 4, min_uniques=0, max_exposure={"F": 0.0, "E": 25.0})
        self.assertFalse(result[["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]].eq("F").any().any())
        exposure_e = int(result[["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]].eq("E").sum().sum())
        self.assertLessEqual(exposure_e, 1)

    def test_manual_captain_max_exposure_is_authoritative(self):
        pool = pd.concat([self.pool, pd.DataFrame([
            {"Captain": "M", "Flex1": "B", "Flex2": "C", "Flex3": "D", "Flex4": "E", "Flex5": "F", "Expected ROI (%)": 10.0},
            {"Captain": "N", "Flex1": "B", "Flex2": "C", "Flex3": "D", "Flex4": "E", "Flex5": "G", "Expected ROI (%)": 9.0},
        ])], ignore_index=True)
        result = select_post_sim_portfolio(pool, 4, min_uniques=0, captain_max_exposure={"A": 50.0})
        self.assertEqual(int((result["Captain"] == "A").sum()), 2)
        self.assertEqual(len(result), 4)

    def test_exposure_constraints_are_post_sim_only(self):
        original = self.pool.copy(deep=True)
        select_post_sim_portfolio(self.pool, 3, max_exposure={"A": 0.0}, captain_max_exposure={"A": 0.0})
        pd.testing.assert_frame_equal(self.pool, original)

    def test_locked_lineup_is_retained_even_when_current_limits_conflict(self):
        locked = self.pool.iloc[[0]].copy()
        result = select_post_sim_portfolio(
            self.pool,
            2,
            max_exposure={"F": 0.0},
            captain_max_exposure={"A": 0.0},
            locked_df=locked,
        )
        self.assertEqual(result.iloc[0]["Flex5"], "F")
        self.assertTrue(bool(result.iloc[0]["Locked"]))

    def test_new_lineup_must_satisfy_uniques_relative_to_lock(self):
        locked = self.pool.iloc[[0]].copy()
        result = select_post_sim_portfolio(self.pool, 2, min_uniques=2, locked_df=locked)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[1]["Expected ROI (%)"], 30.0)
        self.assertGreaterEqual(min_unique_players(result.iloc[0][0:6], result.iloc[1][0:6]), 2)

    def test_locked_lineup_counts_toward_exposure(self):
        locked = self.pool.iloc[[0]].copy()
        # 33% of a 3-lineup portfolio rounds up to one allowed lineup.
        result = select_post_sim_portfolio(self.pool, 3, max_exposure={"E": 33.0}, locked_df=locked)
        exposure_e = int(result[["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]].eq("E").sum().sum())
        self.assertEqual(exposure_e, 1)

    def test_locked_duplicates_are_not_readded(self):
        locked = self.pool.iloc[[0]].copy()
        result = select_post_sim_portfolio(self.pool, 2, locked_df=locked)
        keys = result[["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]].astype(str).agg("|".join, axis=1)
        self.assertEqual(keys.nunique(), len(result))
        self.assertEqual(int(result["Locked"].sum()), 1)

    def test_conflicting_locked_lineups_are_kept(self):
        locked = self.pool.iloc[[0, 1]].copy()
        result = select_post_sim_portfolio(self.pool, 2, min_uniques=2, locked_df=locked)
        self.assertEqual(len(result), 2)
        self.assertTrue(result["Locked"].all())

    def test_invalid_uniques_rejected(self):
        with self.assertRaises(ValueError):
            select_post_sim_portfolio(self.pool, 2, min_uniques=-1)
        with self.assertRaises(ValueError):
            select_post_sim_portfolio(self.pool, 2, min_uniques=7)


if __name__ == "__main__":
    unittest.main()
