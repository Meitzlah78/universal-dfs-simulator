import unittest
from nfl_stat_normalization import historical_two_point_conversions


class TestHistoricalTwoPointConversions(unittest.TestCase):
    def test_passing_conversion(self):
        self.assertEqual(historical_two_point_conversions({'passing_2pt_conversions': 1}), 1.0)

    def test_rushing_conversion(self):
        self.assertEqual(historical_two_point_conversions({'rushing_2pt_conversions': 1}), 1.0)

    def test_receiving_conversion(self):
        self.assertEqual(historical_two_point_conversions({'receiving_2pt_conversions': 1}), 1.0)

    def test_roles_sum_for_player_row(self):
        self.assertEqual(historical_two_point_conversions({'passing_2pt_conversions': 1, 'receiving_2pt_conversions': 1}), 2.0)

    def test_missing_fields_are_zero(self):
        self.assertEqual(historical_two_point_conversions({}), 0.0)


if __name__ == '__main__':
    unittest.main()
