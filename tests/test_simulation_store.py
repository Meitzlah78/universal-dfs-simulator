import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_simulation_store import prepare_simulations,load_prepared,CacheIntegrityError
from simmah_nfl_scoring import score_nfl_stat_line
from simmah_nfl_engine import simulate_stat_lines
from test_nfl_engine import fixture,app_functions


class SimulationStoreTest(unittest.TestCase):
    def test_cold_and_warm_results_match_without_rerunning_engine(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root:
            cold=prepare_simulations(pool,roles,'DraftKings',root,count=128,pilot_n=32,iterations=1)
            self.assertFalse(cold['metadata']['cache_hit'])
            self.assertFalse(cold['evaluation'].equals(cold['construction']))
            with patch('simmah_simulation_store.simulate_stat_lines',side_effect=AssertionError('engine rerun')), \
                 patch('simmah_simulation_store.fit_projection_inputs',side_effect=AssertionError('refit')):
                warm=prepare_simulations(pool,roles,'DraftKings',root,count=128,pilot_n=32,iterations=1)
            with patch('simmah_simulation_store.simulate_stat_lines',side_effect=AssertionError('engine rerun')):
                direct=load_prepared(root,cold['metadata']['key'])
            pd.testing.assert_frame_equal(direct['construction'],cold['construction'])
            self.assertTrue(warm['metadata']['cache_hit'])
            for kind in ['evaluation','construction']:pd.testing.assert_frame_equal(cold[kind],warm[kind])
            payload=json.loads(next((Path(root)/'fits').glob('*.json')).read_text())['payload']
            raw=simulate_stat_lines(pool,roles,np.random.default_rng(530001),128,
                projection_inputs=payload['parameters'],scoring_platform='DraftKings')
            for row in pool.itertuples():
                expected=score_nfl_stat_line(dict(raw[row.Name],is_defense=int(row.Position=='DST')),'DraftKings')
                np.testing.assert_array_equal(cold['evaluation'][row.Name],expected)

    def test_new_seeds_reuse_fit_but_generate_new_outcomes(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root:
            a=prepare_simulations(pool,roles,'FanDuel',root,count=32,pilot_n=16,iterations=0)
            with patch('simmah_simulation_store.fit_projection_inputs',side_effect=AssertionError('refit')):
                b=prepare_simulations(pool,roles,'FanDuel',root,count=32,pilot_n=16,iterations=0,
                    evaluation_seed=41,construction_seed=42)
            self.assertTrue(b['metadata']['fit_cache_hit'])
            self.assertNotEqual(a['metadata']['key'],b['metadata']['key'])
            self.assertFalse(a['evaluation'].equals(b['evaluation']))

    def test_changed_inputs_and_code_do_not_reuse_stale_bundle(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root:
            a=prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=0)
            variants=[{'roles':dict(roles,AQB=dict(roles['AQB'],pass_attempts=40))},{'platform':'DraftKings'},{'weather_by_team':{'A':{'wind_mph':20}}},
                {'correlation_strength':.2},{'count':17}]
            for change in variants:
                kwargs=dict(pool=pool,roles=roles,platform='FanDuel',cache_root=root,count=16,pilot_n=16,iterations=0)
                kwargs.update(change);b=prepare_simulations(**kwargs)
                self.assertNotEqual(a['metadata']['key'],b['metadata']['key'])
            changed=pool.copy();changed.loc[0,'Projection']+=1
            b=prepare_simulations(changed,roles,'FanDuel',root,count=16,pilot_n=16,iterations=0)
            self.assertNotEqual(a['metadata']['fit_key'],b['metadata']['fit_key'])
            with patch('simmah_simulation_store._model_digest',return_value='changed-code'):
                b=prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=0)
            self.assertNotEqual(a['metadata']['fit_key'],b['metadata']['fit_key'])

    def test_corrupt_cache_fails_explicitly(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root:
            a=prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=0)
            path=Path(root)/'prepared'/a['metadata']['key']/'outcomes.npz'
            path.write_bytes(b'corrupted')
            with self.assertRaises(CacheIntegrityError):
                prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=0)

    def test_distinct_samples_and_confirmed_qb_roles_are_required(self):
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'distinct seeds'):
                prepare_simulations(pool,roles,'FanDuel',root,evaluation_seed=1,construction_seed=1)
            extra=pool[pool.Name.eq('AQB')].copy();extra['Name']='backup'
            with self.assertRaisesRegex(ValueError,'Confirm starting'):
                prepare_simulations(pd.concat([pool,extra]),roles,'FanDuel',root)

    def test_pure_scoring_matches_existing_app_for_both_sites(self):
        app_score=app_functions()['score_nfl_stat_line']
        stats={'passing_yards':np.array([0,299,300,400]),'passing_tds':np.array([0,1,2,3]),
            'interceptions':1,'rushing_yards':np.array([0,99,100,200]),'receptions':4,
            'receiving_yards':100,'receiving_tds':1,'fumbles_lost':1,'two_point_conversions':1,
            'points_allowed':np.array([0,7,21,35]),'is_defense':1,'sacks':2}
        for platform in ['DraftKings','FanDuel']:
            np.testing.assert_array_equal(app_score(stats,platform),score_nfl_stat_line(stats,platform))
