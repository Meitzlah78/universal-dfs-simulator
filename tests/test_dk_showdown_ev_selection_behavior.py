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


class DKShowdownEVSelectionBehaviorTests(unittest.TestCase):
    def setUp(self):
        common = {
            "Flex1": ["B", "H", "N"],
            "Flex2": ["C", "I", "O"],
            "Flex3": ["D", "J", "P"],
            "Flex4": ["E", "K", "Q"],
            "Flex5": ["F", "L", "R"],
        }
        self.pool = pd.DataFrame(
            {
                "Captain": ["A", "G", "M"],
                **common,
                # Lineup A looks best by the old/top-percentile view but has worse payout EV.
                "Top1": [0.080, 0.050, 0.030],
                "ContestScore": [0.090, 0.070, 0.040],
                "Expected ROI (%)": [15.0, 42.0, 5.0],
            }
        )

    def test_verified_payout_prefers_higher_ev_over_prettier_top1(self):
        ranked = rank_for_portfolio(self.pool, "Top1", verified_payout=True)
        self.assertEqual(ranked.iloc[0]["Captain"], "G")
        self.assertGreater(ranked.iloc[0]["Expected ROI (%)"], ranked.iloc[1]["Expected ROI (%)"])

    def test_display_metric_change_does_not_change_ev_membership_order(self):
        by_top1 = rank_for_portfolio(self.pool, "Top1", verified_payout=True)
        by_contest = rank_for_portfolio(self.pool, "ContestScore", verified_payout=True)
        self.assertListEqual(by_top1["Captain"].tolist(), by_contest["Captain"].tolist())

    def test_without_verified_payout_selected_metric_still_controls_ranking(self):
        ranked = rank_for_portfolio(self.pool, "Top1", verified_payout=False)
        self.assertEqual(ranked.iloc[0]["Captain"], "A")


if __name__ == "__main__":
    unittest.main()
