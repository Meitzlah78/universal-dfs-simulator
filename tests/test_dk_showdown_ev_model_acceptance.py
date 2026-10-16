import unittest

from dk_showdown_history import ev_model_is_credible, multi_contest_ev_features


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

    def test_incomplete_or_nonfinite_validation_cannot_be_credible(self):
        with self.assertRaises(KeyError):
            ev_model_is_credible({"positive_lift_contest_rate": 1.0})
        self.assertFalse(ev_model_is_credible({
            "positive_lift_contest_rate": float("nan"),
            "median_contest_roi_lift": 10.0,
            "aggregate_top_ev_realized_roi": 20.0,
            "aggregate_remaining_realized_roi": 0.0,
        }))


if __name__ == "__main__":
    unittest.main()
