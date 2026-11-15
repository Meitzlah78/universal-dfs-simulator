import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from simmah_simulation_store import prepare_simulations, pre_market_iterations, FIT_POLICY
from simmah_projection_inputs import fit_projection_inputs
from simmah_nfl_learning import replay_losses
from test_nfl_engine import fixture
from test_nfl_learning import cases


class ColdFitBudgetTest(unittest.TestCase):
    def test_only_preliminary_market_fit_is_shortened(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root, \
             patch('simmah_market_calibration.calibrate_market_inputs',return_value=({'A':1.1},[])), \
             patch('simmah_simulation_store.fit_projection_inputs',wraps=fit_projection_inputs) as fitter:
            result=prepare_simulations(pool,roles,'DraftKings',root,count=16,pilot_n=16,iterations=8,
                                       market_targets={'A':(23.,)},correlation_strength=.4)
            self.assertEqual([c.kwargs['iterations'] for c in fitter.call_args_list],[2,8])
            self.assertEqual(fitter.call_args.kwargs['market_gain'],{'A':1.1})
            self.assertEqual(fitter.call_args.kwargs['correlation_strength'],.4)
            manifest=json.loads(next((Path(root)/'prepared').glob('*/manifest.json')).read_text())
            self.assertEqual(manifest['fit_spec']['fit_policy'],FIT_POLICY)
            self.assertEqual(manifest['fit_spec']['pre_market_iterations'],2)
            with patch('simmah_simulation_store.fit_projection_inputs',side_effect=AssertionError('refit')):
                warm=prepare_simulations(pool,roles,'DraftKings',root,count=16,pilot_n=16,iterations=8,
                                         market_targets={'A':(23.,)},correlation_strength=.4)
            self.assertTrue(warm['metadata']['cache_hit'])

    def test_without_market_the_complete_projection_fit_remains(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root, \
             patch('simmah_simulation_store.fit_projection_inputs',wraps=fit_projection_inputs) as fitter:
            prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=8)
            self.assertEqual([c.kwargs['iterations'] for c in fitter.call_args_list],[8])
        for n in [0,1,2]:self.assertEqual(pre_market_iterations(n,{'A':23}),n)

    def test_pregame_capture_records_both_fit_budgets(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root, \
             patch('simmah_market_calibration.calibrate_market_inputs',return_value=({'A':1.1},[])), \
             patch('simmah_nfl_learning.capture_pregame_inputs',return_value=[]) as capture:
            prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=4,market_targets={'A':(23.,)})
        self.assertEqual(capture.call_args.kwargs['fit_settings'],
                         dict(pilot_n=16,iterations=4,policy=FIT_POLICY,pre_market_iterations=2))

    def test_replay_uses_captured_budget_and_final_context(self):
        case=cases()[0];case['market_targets']={'A':23.};case['weather']={'A':{'wind_mph':18}}
        case['correlation_strength']=.4
        case['fit_settings']=dict(pilot_n=16,iterations=4,policy=FIT_POLICY,pre_market_iterations=2)
        with patch('simmah_market_calibration.calibrate_market_inputs',return_value=({'A':1.1},[])), \
             patch('simmah_projection_inputs.fit_projection_inputs',wraps=fit_projection_inputs) as fitter:
            replay_losses([case],{},{},draws=256)
        self.assertEqual([c.kwargs['iterations'] for c in fitter.call_args_list],[2,4])
        for call in fitter.call_args_list:
            self.assertEqual(call.kwargs['weather_by_team'],case['weather'])
            self.assertEqual(call.kwargs['correlation_strength'],.4)
        self.assertEqual(fitter.call_args.kwargs['market_gain'],{'A':1.1})

    def test_legacy_replay_budget_is_not_reinterpreted(self):
        case=cases()[0]
        with patch('simmah_projection_inputs.fit_projection_inputs',wraps=fit_projection_inputs) as fitter:
            replay_losses([case],{},{},draws=256)
        self.assertEqual(len(fitter.call_args_list),1)
        self.assertEqual(fitter.call_args.kwargs['iterations'],0)
        self.assertNotIn('weather_by_team',fitter.call_args.kwargs)


if __name__=='__main__':unittest.main()
