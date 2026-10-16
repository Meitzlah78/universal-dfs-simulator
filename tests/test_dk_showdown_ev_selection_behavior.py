import unittest

import pandas as pd


def rank_for_portfolio(frame, display_metric, verified_payout):
    """Mirror production membership authority without Streamlit state."""
    selection_metric = "Expected ROI (%)" if verified_payout else display_metric
    ranked = (
        frame.drop_duplicates(subset=["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"], keep="first")
        .sort_values(selection_metric, ascending=False, kind="stable")
        .reset_index(drop=True)
    )
    return ranked


def positive_ev_candidates(frame, verified_payout):
    """A verified contest may filter on payout EV, never on vanity metrics."""
    if not verified_payout:
        return frame.copy()
    return frame.loc[frame["Expected ROI (%)"] > 0].copy()


class DKShowdownEVSelectionBehaviorTests(unittest.TestCase):
    def setUp(self):
        common = {"Flex1": ["B", "H", "N"], "Flex2": ["C", "I", "O"], "Flex3": ["D", "J", "P"], "Flex4": ["E", "K", "Q"], "Flex5": ["F", "L", "R"]}
        self.pool = pd.DataFrame({
            "Captain": ["A", "G", "M"], **common,
            "Top1": [0.080, 0.050, 0.030], "Top5": [0.280, 0.240, 0.120],
            "ContestScore": [0.090, 0.070, 0.040], "Lineup Ownership Score (%)": [128.0, 151.0, 92.0],
            "Salary": [50000, 49300, 46800], "Expected ROI (%)": [15.0, 42.0, 5.0],
        })

    def test_verified_payout_prefers_higher_ev_over_prettier_top1(self):
        ranked = rank_for_portfolio(self.pool, "Top1", verified_payout=True)
        self.assertEqual(ranked.iloc[0]["Captain"], "G")
        self.assertGreater(ranked.iloc[0]["Expected ROI (%)"], ranked.iloc[1]["Expected ROI (%)"])

    def test_display_metric_change_does_not_change_ev_membership_order(self):
        by_top1 = rank_for_portfolio(self.pool, "Top1", verified_payout=True)
        by_contest = rank_for_portfolio(self.pool, "ContestScore", verified_payout=True)
        self.assertListEqual(by_top1["Captain"].tolist(), by_contest["Captain"].tolist())

    def test_vanity_metrics_cannot_override_verified_ev_membership(self):
        expected = rank_for_portfolio(self.pool, "Top1", verified_payout=True)["Captain"].tolist()
        for metric in ["Top5", "ContestScore", "Lineup Ownership Score (%)", "Salary"]:
            self.assertListEqual(rank_for_portfolio(self.pool, metric, True)["Captain"].tolist(), expected)

    def test_lower_owned_lineup_is_not_automatically_selected_over_higher_ev(self):
        ranked = rank_for_portfolio(self.pool, "Lineup Ownership Score (%)", True)
        self.assertEqual(ranked.iloc[0]["Captain"], "G")
        self.assertNotEqual(ranked.iloc[0]["Captain"], "M")

    def test_positive_ev_lineup_survives_bad_vanity_metrics(self):
        pool = self.pool.copy()
        pool.loc[1, ["Top1", "Top5", "ContestScore"]] = [0.001, 0.002, 0.001]
        pool.loc[1, "Lineup Ownership Score (%)"] = 250.0
        pool.loc[1, "Salary"] = 45000
        kept = positive_ev_candidates(pool, verified_payout=True)
        self.assertIn("G", kept["Captain"].tolist())
        self.assertEqual(rank_for_portfolio(kept, "Top1", True).iloc[0]["Captain"], "G")

    def test_negative_ev_lineup_is_not_rescued_by_elite_top1(self):
        pool = self.pool.copy()
        pool.loc[0, "Expected ROI (%)"] = -5.0
        pool.loc[0, ["Top1", "Top5", "ContestScore"]] = [0.50, 0.80, 0.90]
        kept = positive_ev_candidates(pool, verified_payout=True)
        self.assertNotIn("A", kept["Captain"].tolist())

    def test_without_verified_payout_selected_metric_still_controls_ranking(self):
        ranked = rank_for_portfolio(self.pool, "Top1", False)
        self.assertEqual(ranked.iloc[0]["Captain"], "A")


if __name__ == "__main__":
    unittest.main()
