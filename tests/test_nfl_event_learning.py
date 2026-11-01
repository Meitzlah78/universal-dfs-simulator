import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from urllib.error import URLError
import simmah_nfl_event_learning as E
from simmah_nfl_learning import load_archives,model_for_date


class ComponentLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame,cls.sources=load_archives(Path('data/pbp').glob('*.gz'))

    def test_existing_games_produce_a_dated_usable_component(self):
        with tempfile.TemporaryDirectory() as root:
            report=E.learn_components(self.frame,self.sources,root)
            self.assertGreaterEqual(report['training_games'],10)
            self.assertGreaterEqual(report['selection_games'],10)
            self.assertGreaterEqual(report['validation_games'],10)
            self.assertTrue(set(report['accepted_components'])<=set(E.DEFAULTS))
            if report['status']=='accepted':
                self.assertLess(report['training_through'],report['selection_through'])
                self.assertLess(report['selection_through'],report['validation_from'])
                self.assertIsNone(model_for_date(report['validation_through'],root))
                active=model_for_date((pd.Timestamp(report['validation_through'])+pd.Timedelta(days=1)).date().isoformat(),root)
                self.assertEqual(active['version'],report['active_version'])
                for key,row in report['component_validation'].items():
                    if row['accepted']:
                        self.assertLess(row['familywise_95pct_upper_loss_change'],0)
                        if key in {'rushing_distribution','receiving_shape'}:self.assertTrue(row['tail_validation']['accepted'])
            self.assertIn('extra_point_rate',report['component_validation'])

    def test_one_heldout_week_cannot_be_retested_as_a_new_update(self):
        with tempfile.TemporaryDirectory() as root:
            first=E.learn_components(self.frame,self.sources,root)
            second=E.learn_components(self.frame,self.sources,root)
            self.assertIn(second['status'],{'already evaluated; waiting for new independent week','no component passed'})
            self.assertEqual(second['accepted_components'],[])
            if first['status']=='accepted':
                index=json.loads((Path(root)/'index.json').read_text())
                self.assertEqual(len(index['versions']),1)

    def test_fitted_candidate_is_independent_of_test_outcomes(self):
        # Fixed early means/candidates cannot incorporate holdout results.
        train=E.block_samples(self.frame[self.frame.week.eq(5)])
        means=E.means_from_training(train,'rushing_distribution')
        first=E.fit_value(train,'rushing_distribution',{'sd':5.5,'df':0.},means)
        changed=self.frame.copy();changed.loc[changed.week.eq(7),'yards_gained']=500.
        again=E.block_samples(changed[changed.week.eq(5)])
        self.assertEqual(first,E.fit_value(again,'rushing_distribution',{'sd':5.5,'df':0.},means))

    def test_noisy_and_regressing_changes_are_rejected(self):
        before={str(i):1. for i in range(14)}
        self.assertFalse(E.independent_gate(before,{str(i):1.1 for i in range(14)})['accepted'])
        self.assertFalse(E.independent_gate(before,{str(i):1+(-.2 if i<8 else .2) for i in range(14)})['accepted'])
        self.assertFalse(E.independent_gate({'one':1.},{'one':.1})['accepted'])
        self.assertTrue(E.independent_gate(before,{str(i):.9 for i in range(14)})['accepted'])

    def test_negative_completed_gains_remain_in_distribution_score(self):
        obs={'receiving_shape':[('g',pd.DataFrame({'player_id':['p'],'yards_gained':[-8.]}))]}
        negative=E.losses(obs,'receiving_shape',1.5,{})['g']
        obs['receiving_shape'][0][1].loc[0,'yards_gained']=0.
        zero=E.losses(obs,'receiving_shape',1.5,{})['g']
        self.assertGreater(negative,zero)


class FeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('archive_nfl_learning_games','scripts/archive_nfl_learning_games.py')
        cls.feed=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.feed)

    def test_partial_week_and_nonfinal_game_are_excluded(self):
        pbp=pd.DataFrame({'game_id':['g1','g2'],'qtr':[4,4],'game_seconds_remaining':[0,0]})
        schedule=pd.DataFrame([dict(season=2026,week=1,game_id='g1',gameday='2026-10-01',home_score=14,away_score=7,game_type='REG'),
                               dict(season=2026,week=1,game_id='g2',gameday='2026-10-02',home_score=np.nan,away_score=np.nan,game_type='REG')])
        self.assertEqual(self.feed.complete_weeks(pbp,schedule,2026,pd.Timestamp('2026-10-03',tz='UTC')), {})
        schedule.loc[1,['home_score','away_score']]=[10,20]
        self.assertEqual(set(self.feed.complete_weeks(pbp,schedule,2026,pd.Timestamp('2026-10-03',tz='UTC'))),{1})
        pbp.loc[1,'game_seconds_remaining']=60
        self.assertEqual(self.feed.complete_weeks(pbp,schedule,2026,pd.Timestamp('2026-10-03',tz='UTC')), {})

    def test_feed_failure_uses_existing_saved_games_without_inventing_new_games(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(3):(Path(root)/f'week{i}.csv.gz').write_bytes(b'existing')
            def unavailable(*a,**k):raise URLError('offline')
            status=self.feed.refresh(root,Path(root)/'status.json',now=pd.Timestamp('2026-11-01',tz='UTC'),get=unavailable)
            self.assertIn('using existing saved games',status['status'])
            self.assertEqual(len(list(Path(root).glob('*.csv.gz'))),3)


class RuntimeTests(unittest.TestCase):
    def test_dated_salary_fields_load_without_fabricating_clocks(self):
        from simmah_nfl_learning import slate_clock_inputs
        from test_nfl_engine import fixture
        pool,_=fixture();pool['Game Info']='A@B 11/01/2026 01:00PM ET'
        self.assertEqual(slate_clock_inputs(pool),('2026-11-01',{}))

    def test_corrupt_optional_model_uses_visible_baseline(self):
        from simmah_simulation_store import prepare_simulations
        from test_nfl_engine import fixture
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root,patch('simmah_nfl_learning.model_for_date',side_effect=ValueError('checksum')):
            result=prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=0,slate_date='2026-11-01')
            self.assertIn('learned model unavailable',result['metadata']['learning']['status'])
            self.assertIsNone(result['metadata']['learning']['version'])

class AcceptedEngineTests(unittest.TestCase):
    def test_student_tail_branch_preserves_shared_stats_and_scoreboard(self):
        from test_nfl_engine import fixture
        from simmah_nfl_engine import simulate_stat_lines
        pool,roles=fixture()
        stats,games=simulate_stat_lines(pool,roles,np.random.default_rng(84),1024,
            learned_parameters={'rushing_df':3.,'rushing_sd':6.},return_diagnostics=True)
        for team,other in [('A','B'),('B','A')]:
            np.testing.assert_allclose(stats[team+'QB']['passing_yards'],sum(stats[team+p]['receiving_yards'] for p in ['RB','WR','TE']),atol=.001)
            np.testing.assert_array_equal(stats[team+'QB']['interceptions'],stats[other+'DST']['def_interceptions'])
            g=games[team]
            np.testing.assert_array_equal(g['points'],6*(g['offensive_tds']+g['defensive_tds'])+2*g['safeties']+3*g['fg_made']+g['pat_made']+2*g['two_made'])
            self.assertTrue((g['clock_remaining']<=0).all())

class ShippedModelTests(unittest.TestCase):
    def test_checked_in_version_is_usable_by_runtime(self):
        registry=json.loads(Path('data/nfl_models/index.json').read_text())
        newest=max(registry['versions'],key=lambda item:item['validation_through'])
        day=(pd.Timestamp(newest['validation_through'])+pd.Timedelta(days=1)).date().isoformat()
        model=model_for_date(day)
        self.assertIsNotNone(model)
        self.assertEqual(model['status'],'accepted')
        self.assertTrue(model['parameters'])
