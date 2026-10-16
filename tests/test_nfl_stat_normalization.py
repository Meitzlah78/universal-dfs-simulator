import unittest
from nfl_stat_normalization import historical_two_point_conversions
class T(unittest.TestCase):
    def test_2pt(self):
        self.assertEqual(historical_two_point_conversions({'passing_2pt_conversions':1,'receiving_2pt_conversions':1}),2.0)
