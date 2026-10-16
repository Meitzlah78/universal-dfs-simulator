import math
import unittest

from dk_showdown_history import ev_calibration_features, ev_ranking_features


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
        features = ev_ranking_features(
            predicted_roi=[50, 40, 30, 20, 10, 0, -10, -20, -30, -40],
            realized_net=[1.0, 0.5, 0, 0, 0, -0.5, -0.5, -0.5, -0.5, -0.5],
            entry_fees=[1.0] * 10,
            top_fraction=0.20,
        )
        self.assertEqual(features["top_count"], 2.0)
        self.assertAlmostEqual(features["top_predicted_ev_realized_roi"], 75.0)
        self.assertAlmostEqual(features["remaining_realized_roi"], -31.25)
        self.assertGreater(features["top_ev_roi_lift"], 0.0)

    def test_invalid_calibration_inputs_are_rejected(self):
        with self.assertRaises(ValueError): ev_calibration_features([], [], [])
        with self.assertRaises(ValueError): ev_calibration_features([1.0], [1.0, 2.0], [1.0])
        with self.assertRaises(ValueError): ev_calibration_features([1.0], [1.0], [0.0])
        with self.assertRaises(ValueError): ev_ranking_features([1.0], [1.0], [1.0], top_fraction=1.0)


if __name__ == "__main__":
    unittest.main()
