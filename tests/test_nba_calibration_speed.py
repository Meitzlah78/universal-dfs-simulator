"""Remove discarded pilot draws while preserving physical outcomes exactly."""
import unittest
from unittest.mock import patch
import numpy as np
from simmah_nba_pregame import PregameEngine
from simmah_nba_markets import simulate_market_game
import test_nba_pregame


class CalibrationSpeedTests(unittest.TestCase):
    def test_parameter_only_fit_skips_exactly_one_discarded_draw(self):
        from simmah_nba_engine import simulate_game
        pool, markets, rates = test_nba_pregame.PregameTests().fixture()
        rotations = np.broadcast_to(np.arange(10).reshape(1,2,1,5),(60,2,48,5)).copy()
        with patch('simmah_nba_markets.simulate_game',wraps=simulate_game) as run:
            full = simulate_market_game(rotations,np.ones((2,5,5)),[rates]*2,[100,110],83)
            self.assertEqual(run.call_count,5)
            run.reset_mock()
            fit = simulate_market_game(rotations,np.ones((2,5,5)),[rates]*2,[100,110],83,calibration_only=True)
            self.assertEqual(run.call_count,4)
        self.assertEqual(fit['calibrated_rates'],full['calibrated_rates'])
        self.assertEqual(fit['market_calibration']['baseline_pilot_means'],full['market_calibration']['baseline_pilot_means'])

    def test_all_three_draws_and_reports_are_identical_to_legacy_preparation(self):
        def legacy(*args,**kwargs):
            kwargs.pop('calibration_only',None)
            return simulate_market_game(*args,**kwargs)
        for platform in ('FanDuel','DraftKings'):
            with self.subTest(platform=platform):
                pool,markets,rates=test_nba_pregame.PregameTests().fixture()
                before=PregameEngine(pool,markets,rates,parallel=False,platform=platform)
                after=PregameEngine(pool,markets,rates,parallel=False,platform=platform)
                for seed in (83,1092,2100):
                    with patch('simmah_nba_pregame.simulate_market_game',side_effect=legacy):
                        expected=before(160,seed)
                    actual=after(160,seed)
                    np.testing.assert_array_equal(actual,expected)
                    self.assertEqual(after.last_report,before.last_report)
