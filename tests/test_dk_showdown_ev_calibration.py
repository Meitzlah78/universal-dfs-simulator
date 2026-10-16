import math
import unittest

from dk_showdown_history import ev_calibration_features, ev_ranking_features, multi_contest_ev_features


class DKShowdownEVCalibrationTests(unittest.TestCase):
    def test_positive_ev_bucket_is_measured_by_real_money(self):
        features = ev_calibration_features([40.0, 15.0, -10.0, -20.0], [1.0, -0.2, -0.5, -0.5], [1.0] * 4)
        self.assertEqual(features["predicted_positive_ev_rate"], 0.5)
        self.assertAlmostEqual(features["positive_ev_realized_roi"], 40.0)
        self.assertAlmostEqual(features["nonpositive_ev_realized_roi"], -50.0)
        self.assertAlmostEqual(features["realized_roi"], -5.0)

    def test_no_positive_ev_predictions_are_explicit(self):
        features = ev_calibration_features([-1.0, 0.0], [-1.0, 1.0], [1.0, 1.0])
        self.assertTrue(math.isnan(features["positive_ev_realized_roi"]))
        self.assertAlmostEqual(features["nonpositive_ev_realized_roi"], 0.0)

    def test_top_predicted_ev_must_show_realized_roi_lift(self):
        features = ev_ranking_features([50,40,30,20,10,0,-10,-20,-30,-40], [1,.5,0,0,0,-.5,-.5,-.5,-.5,-.5], [1.0]*10, .20)
        self.assertEqual(features["top_count"], 2.0)
        self.assertAlmostEqual(features["top_predicted_ev_realized_roi"], 75.0)
        self.assertAlmostEqual(features["remaining_realized_roi"], -31.25)
        self.assertGreater(features["top_ev_roi_lift"], 0.0)

    def test_multi_contest_validation_requires_repeatable_ev_lift(self):
        contests = [
            {"predicted_roi": [30,20,10,0,-10], "realized_net": [1,.5,0,-.5,-.5], "entry_fees": [1]*5},
            {"predicted_roi": [25,15,5,-5,-15], "realized_net": [.5,.25,0,-.5,-.5], "entry_fees": [1]*5},
            {"predicted_roi": [40,20,0,-20,-40], "realized_net": [.75,0,0,-.25,-.5], "entry_fees": [1]*5},
        ]
        f = multi_contest_ev_features(contests, top_fraction=.20)
        self.assertEqual(f["contests"], 3.0)
        self.assertEqual(f["positive_lift_contest_rate"], 1.0)
        self.assertGreater(f["median_contest_roi_lift"], 0.0)
        self.assertGreater(f["aggregate_top_ev_realized_roi"], f["aggregate_remaining_realized_roi"])

    def test_one_jackpot_cannot_hide_inconsistent_ranking(self):
        contests = [
            {"predicted_roi": [100,0,-10,-20,-30], "realized_net": [20,-1,-1,-1,-1], "entry_fees": [1]*5},
            {"predicted_roi": [100,0,-10,-20,-30], "realized_net": [-1,1,0,0,0], "entry_fees": [1]*5},
            {"predicted_roi": [100,0,-10,-20,-30], "realized_net": [-1,1,0,0,0], "entry_fees": [1]*5},
        ]
        f = multi_contest_ev_features(contests, top_fraction=.20)
        self.assertLess(f["positive_lift_contest_rate"], .5)
        self.assertLess(f["median_contest_roi_lift"], 0.0)
        self.assertGreater(f["aggregate_top_ev_realized_roi"], 0.0)

    def test_invalid_calibration_inputs_are_rejected(self):
        with self.assertRaises(ValueError): ev_calibration_features([], [], [])
        with self.assertRaises(ValueError): ev_calibration_features([1.0], [1.0, 2.0], [1.0])
        with self.assertRaises(ValueError): ev_calibration_features([1.0], [1.0], [0.0])
        with self.assertRaises(ValueError): ev_ranking_features([1.0], [1.0], [1.0], top_fraction=1.0)
        with self.assertRaises(ValueError): multi_contest_ev_features([])


if __name__ == "__main__":
    unittest.main()
