import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from test_nfl_engine import fixture
from simmah_nfl_engine import simulate_stat_lines
from simmah_market_calibration import canonical_targets, calibrate_market_inputs
from simmah_simulation_store import prepare_simulations, construction_for_build

class MarketCalibrationTests(unittest.TestCase):
    def test_missing_and_invalid_markets(self):
        self.assertEqual(canonical_targets({}),{})
        self.assertEqual(canonical_targets({'WSH':(22.5,30)}),{'WAS':22.5})
        for value in [float('nan'),-1,100]:
            with self.assertRaises(ValueError):canonical_targets({'SF':(value,20)})
    def test_event_calibration_moves_toward_targets_and_preserves_shared_yards(self):
        pool,roles=fixture();targets={'A':30.,'B':17.}
        gains,report=calibrate_market_inputs(pool,roles,{}, {},'FanDuel',targets,1024)
        self.assertLess(sum(abs(r['Pilot mean']-r['Market target']) for r in report),sum(abs(r['Before market calibration']-r['Market target']) for r in report))
        baseline,base_diag=simulate_stat_lines(pool,roles,np.random.default_rng(99811),2048,return_diagnostics=True)
        scored,diag=simulate_stat_lines(pool,roles,np.random.default_rng(99811),2048,market_gain=gains,return_diagnostics=True)
        self.assertLess(sum(abs(diag[t]['points'].mean()-targets[t]) for t in targets),sum(abs(base_diag[t]['points'].mean()-targets[t]) for t in targets))
        for team in ['A','B']:
            receivers=[name for name in scored if name.startswith(team) and name.endswith(('WR','TE','RB'))]
            np.testing.assert_allclose(scored[team+'QB']['passing_yards'],sum(scored[n]['receiving_yards'] for n in receivers),atol=.001)
    def test_market_snapshot_in_cache_key_and_warm_reuse(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root:
            a=prepare_simulations(pool,roles,'FanDuel',root,count=64,pilot_n=32,iterations=0,market_targets={'A':(30,17),'B':(17,30)})
            with patch('simmah_simulation_store.calibrate_market_inputs',create=True):
                # The calibrator is imported inside prepare; patch its source.
                with patch('simmah_market_calibration.calibrate_market_inputs',side_effect=AssertionError('refit')):
                    b=prepare_simulations(pool,roles,'FanDuel',root,count=64,pilot_n=32,iterations=0,market_targets={'A':(30,17),'B':(17,30)})
            self.assertTrue(b['metadata']['cache_hit'])
            self.assertEqual(a['metadata']['market_report'],b['metadata']['market_report'])
            c=prepare_simulations(pool,roles,'FanDuel',root,count=64,pilot_n=32,iterations=0)
            self.assertNotEqual(a['metadata']['key'],c['metadata']['key'])
            self.assertFalse(a['evaluation'].equals(a['construction']))
            a['evaluation'].attrs['preparation_key']=a['metadata']['key']
            with self.assertRaisesRegex(ValueError,'Spreads or totals changed'):
                construction_for_build(a['evaluation'],pool,'FanDuel',root,count=64,market_targets={'A':(29,18),'B':(18,29)})
