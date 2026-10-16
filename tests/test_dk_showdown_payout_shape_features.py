import unittest

from dk_showdown_history import payout_shape_features


class DKShowdownPayoutShapeFeatureTests(unittest.TestCase):
    def test_payout_shape_is_based_only_on_pregame_contest_economics(self):
        payouts = [100.0, 50.0, 25.0, 10.0, 5.0] + [0.0] * 95
        f = payout_shape_features(field_size=100, entry_fee=2.0, payouts=payouts)
        self.assertEqual(f["field_size"], 100.0)
        self.assertEqual(f["paid_places"], 5.0)
        self.assertAlmostEqual(f["paid_rate"], 0.05)
        self.assertEqual(f["first_prize_multiple"], 50.0)
        self.assertAlmostEqual(f["first_prize_pool_share"], 100.0 / 190.0)
        self.assertAlmostEqual(f["listed_return_rate"], 190.0 / 200.0)

    def test_top_heavy_and_flat_contests_have_different_ev_context(self):
        top_heavy = payout_shape_features(100, 1.0, [60.0, 10.0, 10.0, 10.0, 10.0] + [0.0] * 95)
        flatter = payout_shape_features(100, 1.0, [20.0] * 5 + [0.0] * 95)
        self.assertGreater(top_heavy["first_prize_pool_share"], flatter["first_prize_pool_share"])
        self.assertGreater(top_heavy["first_prize_multiple"], flatter["first_prize_multiple"])
        self.assertEqual(top_heavy["listed_prize_pool"], flatter["listed_prize_pool"])

    def test_invalid_contest_economics_are_rejected(self):
        with self.assertRaises(ValueError): payout_shape_features(0, 1.0, [1.0])
        with self.assertRaises(ValueError): payout_shape_features(10, 0.0, [1.0])
        with self.assertRaises(ValueError): payout_shape_features(2, 1.0, [1.0, 1.0, 1.0])
        with self.assertRaises(ValueError): payout_shape_features(10, 1.0, [1.0, -1.0])


if __name__ == "__main__":
    unittest.main()
