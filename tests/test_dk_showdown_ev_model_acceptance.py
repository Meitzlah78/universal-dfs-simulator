import unittest

from dk_showdown_history import multi_contest_ev_features


def ev_model_is_credible(features, min_positive_lift_rate=.60, min_median_lift=0.0):
    """A model must rank well repeatedly, not merely win aggregate dollars once."""
    return (
        features["positive_lift_contest_rate"] >= min_positive_lift_rate
        and features["median_contest_roi_lift"] > min_median_lift
        and features["aggregate_top_ev_realized_roi"] > features["aggregate_remaining_realized_roi"]
    )


class DKShowdownEVModelAcceptanceTests(unittest.TestCase):
    def test_consistently_better_ev_ranking_can_pass(self):
        contests = [
            {"predicted_roi": [30, 20, 10, 0, -10], "realized_net": [1, .5, 0, -.5, -.5], "entry_fees": [1] * 5},
            {"predicted_roi": [25, 15, 5, -5, -15], "realized_net": [.5, .25, 0, -.5, -.5], "entry_fees": [1] * 5},
            {"predicted_roi": [40, 20, 0, -20, -40], "realized_net": [.75, 0, 0, -.25, -.5], "entry_fees": [1] * 5},
        ]
        self.assertTrue(ev_model_is_credible(multi_contest_ev_features(contests)))

    def test_jackpot_model_fails_despite_positive_aggregate_roi(self):
        contests = [
            {"predicted_roi": [100, 0, -10, -20, -30], "realized_net": [20, -1, -1, -1, -1], "entry_fees": [1] * 5},
            {"predicted_roi": [100, 0, -10, -20, -30], "realized_net": [-1, 1, 0, 0, 0], "entry_fees": [1] * 5},
            {"predicted_roi": [100, 0, -10, -20, -30], "realized_net": [-1, 1, 0, 0, 0], "entry_fees": [1] * 5},
        ]
        f = multi_contest_ev_features(contests)
        self.assertGreater(f["aggregate_top_ev_realized_roi"], 0.0)
        self.assertFalse(ev_model_is_credible(f))

    def test_flat_ranking_skill_does_not_pass(self):
        contests = [
            {"predicted_roi": [20, 10, 0, -10, -20], "realized_net": [0, 0, 0, 0, 0], "entry_fees": [1] * 5},
            {"predicted_roi": [20, 10, 0, -10, -20], "realized_net": [0, 0, 0, 0, 0], "entry_fees": [1] * 5},
        ]
        self.assertFalse(ev_model_is_credible(multi_contest_ev_features(contests)))


if __name__ == "__main__":
    unittest.main()
