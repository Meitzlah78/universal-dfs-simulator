import unittest

from dk_showdown_history import field_behavior_features


class DKShowdownHistoryFeatureTests(unittest.TestCase):
    def test_duplicate_mass_is_entry_weighted(self):
        keys = ["A"] * 20 + ["B"] * 10 + ["C"] * 3 + ["D"]
        features = field_behavior_features(keys)
        self.assertEqual(features["entries"], 34.0)
        self.assertEqual(features["unique_lineups"], 4.0)
        self.assertAlmostEqual(features["unique_rate"], 4 / 34)
        self.assertAlmostEqual(features["singleton_entry_mass"], 1 / 34)
        self.assertAlmostEqual(features["ten_plus_duplicate_entry_mass"], 30 / 34)
        self.assertAlmostEqual(features["twenty_plus_duplicate_entry_mass"], 20 / 34)
        self.assertEqual(features["max_duplicates"], 20.0)

    def test_all_singletons(self):
        features = field_behavior_features(["A", "B", "C"])
        self.assertEqual(features["unique_rate"], 1.0)
        self.assertEqual(features["singleton_entry_mass"], 1.0)
        self.assertEqual(features["ten_plus_duplicate_entry_mass"], 0.0)
        self.assertEqual(features["twenty_plus_duplicate_entry_mass"], 0.0)
        self.assertEqual(features["max_duplicates"], 1.0)

    def test_empty_field_is_rejected(self):
        with self.assertRaises(ValueError):
            field_behavior_features([])


if __name__ == "__main__":
    unittest.main()
