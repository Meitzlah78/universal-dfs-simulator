import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_simulation_store import prepare_simulations,construction_for_build,weather_snapshot
from test_nfl_engine import fixture


class PreparedBuildBoundaryTest(unittest.TestCase):
    def prepared(self,root):
        pool,roles=fixture()
        result=prepare_simulations(pool,roles,'DraftKings',root,count=32,pilot_n=16,iterations=0,
            weather_by_team=weather_snapshot(pool))
        evaluation=result['evaluation'].copy();evaluation.attrs['preparation_key']=result['metadata']['key']
        return pool,evaluation,result

    def test_build_loads_without_simulation_or_fit_and_allows_pool_subset(self):
        with tempfile.TemporaryDirectory() as root:
            pool,evaluation,result=self.prepared(root)
            with patch('simmah_simulation_store.prepare_simulations',side_effect=AssertionError('prepare on BUILD')), \
                 patch('simmah_simulation_store.simulate_stat_lines',side_effect=AssertionError('simulate on BUILD')), \
                 patch('simmah_simulation_store.fit_projection_inputs',side_effect=AssertionError('fit on BUILD')):
                construction=construction_for_build(evaluation,pool.iloc[:6],'DraftKings',root,count=32,correlation_strength=1.)
            pd.testing.assert_frame_equal(construction,result['construction'])
            self.assertFalse(construction.equals(evaluation))

    def test_changed_inputs_weather_or_evaluation_require_preparation(self):
        with tempfile.TemporaryDirectory() as root:
            pool,evaluation,_=self.prepared(root)
            changed=pool.copy();changed.loc[0,'Projection']+=1
            with self.assertRaisesRegex(ValueError,'Player inputs changed'):
                construction_for_build(evaluation,changed,'DraftKings',root,count=32)
            changed=pool.copy();changed['Wind MPH']=20
            with self.assertRaisesRegex(ValueError,'Weather inputs changed'):
                construction_for_build(evaluation,changed,'DraftKings',root,count=32)
            corrupted=evaluation.copy();corrupted.iloc[0,0]+=1
            with self.assertRaisesRegex(ValueError,'do not match'):
                construction_for_build(corrupted,pool,'DraftKings',root,count=32)
            with self.assertRaisesRegex(ValueError,'correlation changed'):
                construction_for_build(evaluation,pool,'DraftKings',root,count=32,correlation_strength=.5)
            with self.assertRaisesRegex(ValueError,'scoring platform'):
                construction_for_build(evaluation,pool,'FanDuel',root,count=32)

    def test_app_sim_reuses_preparation_without_any_ui_cache_callback(self):
        from test_nfl_engine import app_functions
        ns=app_functions();pool,_=fixture()
        first=ns['simulate_fd_play_by_play'](pool,np.random.default_rng(1),n=32)
        with patch('simmah_simulation_store.simulate_stat_lines',side_effect=AssertionError('warm SIM reran engine')), \
             patch('simmah_simulation_store.fit_projection_inputs',side_effect=AssertionError('warm SIM refitted')):
            again=ns['simulate_fd_play_by_play'](pool,np.random.default_rng(2),n=32)
        pd.testing.assert_frame_equal(first,again)
        self.assertIn('preparation_key',again.attrs)
        self.assertTrue(ns['st'].session_state['simulation_preparation_FanDuel']['cache_hit'])

    def test_old_sessions_without_preparation_are_rejected(self):
        pool,_=fixture()
        with self.assertRaisesRegex(ValueError,'Run SIM'):
            construction_for_build(pd.DataFrame(),pool,'DraftKings','/unused')

    def test_all_app_formats_share_the_load_only_build_boundary(self):
        root=ast.parse(Path('dfs_app.py').read_text())
        build=next(n for n in root.body if isinstance(n,ast.FunctionDef) and n.name=='build_joint_candidate_pool')
        calls=[n.func.id for n in ast.walk(build) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        self.assertIn('construction_for_build',calls)
        self.assertNotIn('simulate_fd_play_by_play',calls)
        self.assertNotIn('prepare_simulations',calls)
