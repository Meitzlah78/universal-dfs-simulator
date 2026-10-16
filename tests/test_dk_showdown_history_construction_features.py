import unittest

from dk_showdown_history import captain_behavior_features, salary_behavior_features


class DKShowdownConstructionFeatureTests(unittest.TestCase):
    def test_salary_features_capture_field_spend_shape(self):
        features = salary_behavior_features([45000, 48000, 49000, 49500, 50000])
        self.assertEqual(features["salary_mean"], 48300.0)
        self.assertEqual(features["salary_median"], 49000.0)
        self.assertLessEqual(features["salary_p05"], features["salary_p25"])
        self.assertLessEqual(features["salary_p75"], features["salary_p95"])

    def test_captain_top_four_is_entry_weighted(self):
        captains = ["A"] * 40 + ["B"] * 25 + ["C"] * 15 + ["D"] * 10 + ["E"] * 10
        features = captain_behavior_features(captains)
        self.assertEqual(features["captain_unique_count"], 5.0)
        self.assertAlmostEqual(features["captain_top1_mass"], 0.40)
        self.assertAlmostEqual(features["captain_top4_mass"], 0.90)

    def test_bad_salary_values_are_rejected(self):
        with self.assertRaises(ValueError):
            salary_behavior_features([49000, float("nan")])
        with self.assertRaises(ValueError):
            salary_behavior_features([-1])

    def test_empty_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            salary_behavior_features([])
        with self.assertRaises(ValueError):
            captain_behavior_features([])


if __name__ == "__main__":
    unittest.main()
