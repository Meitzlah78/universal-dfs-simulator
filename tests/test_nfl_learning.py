import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import simmah_nfl_learning as L
from simmah_nfl_engine import simulate_stat_lines,STAT_KEYS


def pool():
    return pd.DataFrame([dict(Name=t+p,Team=t,Opponent=o,Position=p,Projection=15.)
        for t,o in [('A','B'),('B','A')] for p in ['QB','RB','WR','TE','K','DST']])


def cases():
    return [dict(game_id='future',kickoff='2026-11-09T18:00:00Z',frozen_at='2026-11-09T17:00:00Z',
        pool=pool().to_dict('records'),roles={},weather={},projection_inputs={},market_gain={},market_targets={},
        fit_settings={'pilot_n':16,'iterations':0},platform=site,
        actual_stats={n:dict.fromkeys(STAT_KEYS,0.) for n in pool().Name}) for site in ['DraftKings','FanDuel']]


class LearningTests(unittest.TestCase):
    def test_real_archives_do_not_activate(self):
        frame,sources=L.load_archives(Path('data/pbp').glob('*.gz'));candidate=L.fit_candidate(frame,sources)
        self.assertGreaterEqual(candidate['training_games'],20);self.assertGreaterEqual(candidate['validation_games'],10)
        self.assertLess(candidate['training_through'],candidate['validation_from'])
        self.assertIn('status',candidate['event_diagnostics']['extra_point_rate'])
        self.assertIn('rushing_sd',candidate['event_diagnostics']);self.assertIn('receiving_shape',candidate['event_diagnostics'])
        with tempfile.TemporaryDirectory() as root:
            L.atomic_json(Path(root)/'trials'/'trial.json',candidate)
            self.assertIsNone(L.model_for_date('2026-11-01',root))

    def test_duplicate_archive_rejected(self):
        p=next(Path('data/pbp').glob('*.gz'))
        with self.assertRaisesRegex(ValueError,'Overlapping'):L.load_archives([p,p])

    def test_parameters_fail_closed(self):
        for value in [float('nan'),float('inf'),-1.,True,1.1]:
            with self.assertRaises(ValueError):L.validate_parameters({'sack_rate':value})
        with self.assertRaises(ValueError):L.validate_parameters({'unknown':1.})

    def test_default_seeded_identity(self):
        a=simulate_stat_lines(pool(),{},np.random.default_rng(53),256)
        b=simulate_stat_lines(pool(),{},np.random.default_rng(53),256,learned_parameters=L.DEFAULTS)
        for name in a:
            for key in STAT_KEYS:np.testing.assert_array_equal(a[name][key],b[name][key])

    def test_variance_input_and_shared_accounting(self):
        a=simulate_stat_lines(pool(),{},np.random.default_rng(8),512,learned_parameters={'rushing_sd':3.})
        b=simulate_stat_lines(pool(),{},np.random.default_rng(8),512,learned_parameters={'rushing_sd':9.})
        self.assertFalse(np.array_equal(a['ARB']['rushing_yards'],b['ARB']['rushing_yards']))
        for stats in [a,b]:
            np.testing.assert_allclose(stats['AQB']['passing_yards'],sum(stats['A'+p]['receiving_yards'] for p in ['RB','WR','TE']),atol=.001)
            np.testing.assert_array_equal(stats['AQB']['interceptions'],stats['BDST']['def_interceptions'])
            self.assertTrue((stats['AQB']['passing_attempts']>=stats['AQB']['completions']).all())
            np.testing.assert_array_equal(stats['AQB']['completions'],sum(stats['A'+p]['receptions'] for p in ['RB','WR','TE']))
            self.assertTrue((stats['ARB']['targets']>=stats['ARB']['receptions']).all())
            self.assertGreater(stats['ARB']['rushing_attempts'].sum(),0)

    def test_capture_only_pregame(self):
        with tempfile.TemporaryDirectory() as root:
            now=pd.Timestamp('2026-11-08T16:00:00Z')
            for clocks in [{},{'A':'2026-10-01 13:00','B':'2026-10-01 13:00'}]:
                self.assertEqual(L.capture_pregame_inputs(pool(),{},'FanDuel',{}, {},{},clocks,root,now=now),[])
            paths=L.capture_pregame_inputs(pool(),{},'DraftKings',{}, {},{},
                {'A':'2026-11-08 13:00','B':'2026-11-08 13:00'},root,now=now)
            self.assertEqual(len(paths),1);record=json.loads(Path(paths[0]).read_text())
            self.assertLess(pd.Timestamp(record['frozen_at']),pd.Timestamp(record['kickoff']))
            self.assertNotIn('actual_stats',record)

    def test_stable_identity_and_trade_guard(self):
        profiles={'p|A':dict(games=5,**dict.fromkeys(L.ROLE_FIELDS,10.))}
        roles={'OK':dict(player_id='p',team='A',targets=2.),'Traded':dict(player_id='p',team='B',targets=2.)}
        result=L.apply_player_profiles(roles,profiles)
        self.assertEqual(result['OK']['targets'],4.);self.assertEqual(result['Traded']['targets'],2.)
        self.assertEqual(roles['OK']['targets'],2.)

    def test_replay_rejects_postgame_or_missing_actuals(self):
        c=cases()[0];c['frozen_at']=c['kickoff']
        with self.assertRaisesRegex(ValueError,'precede'):L.replay_losses([c],{}, {},draws=256)
        c=cases()[0];c['actual_stats']['AQB'].pop('fumbles_lost')
        with self.assertRaisesRegex(ValueError,'Complete explicit'):L.replay_losses([c],{}, {},draws=256)

    def test_full_replay_finite_marginal_and_joint_scores(self):
        scores,_=L.replay_losses(cases(),{}, {},draws=256)
        self.assertIn('correlations',scores['joint'])
        self.assertTrue(all(np.isfinite(v) for g in scores.values() for v in g.values()))
        with self.assertRaisesRegex(ValueError,'Duplicate'):L.replay_losses([cases()[0]]*2,{}, {},draws=256)

    def test_temporal_leak_blocks_promotion(self):
        c=dict(parameters={},players={},validation_through='2026-11-10',source_game_ids=[])
        with self.assertRaisesRegex(ValueError,'follow ALL'):L.validate_and_promote(c,cases(),draws=256,min_games=1)

    def test_single_regression_blocks_other_gains(self):
        c=dict(parameters={},players={},validation_through='2026-10-26',source_game_ids=[])
        base={'QB/passing_yards':{'mean':1.},'RB/rushing_yards':{'mean':1.},'joint':{'correlations':1.}}
        worse={'QB/passing_yards':{'mean':.5},'RB/rushing_yards':{'mean':1.1},'joint':{'correlations':.8}}
        dates=[pd.Timestamp('2026-11-09',tz='UTC')]
        with tempfile.TemporaryDirectory() as root,patch.object(L,'replay_losses',side_effect=[(base,dates),(worse,dates)]):
            self.assertEqual(L.validate_and_promote(c,cases(),root,min_games=1)['status'],'rejected full-engine replay')
            self.assertFalse((Path(root)/'index.json').exists())

    def test_promotion_date_guard_checksums_and_code_version(self):
        c=dict(parameters={'rushing_sd':6.},players={},validation_through='2026-10-26',source_game_ids=[])
        base={'RB/rushing_yards':{'mean':1.},'joint':{'correlations':1.}}
        good={'RB/rushing_yards':{'mean':.9},'joint':{'correlations':.9}}
        dates=[pd.Timestamp('2026-11-09',tz='UTC')]
        with tempfile.TemporaryDirectory() as root,patch.object(L,'replay_losses',side_effect=[(base,dates),(good,dates)]):
            result=L.validate_and_promote(c,cases(),root,min_games=1)
            self.assertEqual(result['status'],'accepted');self.assertIsNone(L.model_for_date('2026-11-09',root))
            self.assertEqual(L.model_for_date('2026-11-10',root)['version'],result['version'])
            with patch.object(L,'engine_digest',return_value='changed'):
                with self.assertRaisesRegex(ValueError,'revalidation'):L.model_for_date('2026-11-10',root)
            path=next((Path(root)/'versions').glob('*.json'));obj=json.loads(path.read_text());obj['parameters']['rushing_sd']=8.;path.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,'Invalid'):L.model_for_date('2026-11-10',root)

if __name__=='__main__':unittest.main()

class IntegrationTests(unittest.TestCase):
    def test_active_model_invalidates_fitter_and_outcome_cache(self):
        from simmah_simulation_store import prepare_simulations,construction_for_build
        from test_nfl_engine import fixture
        p,roles=fixture()
        with tempfile.TemporaryDirectory() as root:
            old=prepare_simulations(p,roles,'FanDuel',root,count=32,pilot_n=16,iterations=0,slate_date='2026-11-10')
            model=dict(version='test-approved',parameters={'rushing_sd':8.},players={})
            with patch.object(L,'model_for_date',return_value=model):
                new=prepare_simulations(p,roles,'FanDuel',root,count=32,pilot_n=16,iterations=0,slate_date='2026-11-10')
                self.assertEqual(new['metadata']['learning']['version'],'test-approved')
                self.assertNotEqual(old['metadata']['fit_key'],new['metadata']['fit_key'])
                self.assertNotEqual(old['metadata']['key'],new['metadata']['key'])
                old['evaluation'].attrs['preparation_key']=old['metadata']['key']
                with self.assertRaisesRegex(ValueError,'learned model changed'):
                    construction_for_build(old['evaluation'],p,'FanDuel',root,count=32)

    def test_joint_latent_opportunities_keep_event_conservation(self):
        p=pool()
        # Multiple receivers exercise latent game-level ownership of touches.
        extra=p[p.Position.eq('WR')].copy();extra.Name=extra.Name+'2';p=pd.concat([p,extra],ignore_index=True)
        stats=simulate_stat_lines(p,{},np.random.default_rng(88),256,
            learned_parameters={'opportunity_concentration':20.,'pace_sd':.15,'environment_sd':.18})
        for t in ['A','B']:
            receivers=p.loc[p.Team.eq(t)&p.Position.isin(['RB','WR','TE']),'Name']
            np.testing.assert_allclose(stats[t+'QB']['passing_yards'],sum(stats[name]['receiving_yards'] for name in receivers),atol=.001)

    def test_confirmed_weather_clock_routes_learning(self):
        p=pool();p['Weather Kickoff']='2026-11-08T18:00:00Z'
        day,clocks=L.slate_clock_inputs(p);self.assertEqual(day,'2026-11-08');self.assertEqual(set(clocks),{'A','B'})
        p.loc[0,'Weather Kickoff']='';self.assertEqual(L.slate_clock_inputs(p),(None,{}))

    def test_partial_new_optional_flags_do_not_turn_unknowns_into_zero(self):
        frame,_=L.load_archives(Path('data/pbp').glob('*.gz'))
        frame['fumble_lost']=np.nan
        touches=(frame.play_type.eq('run')|frame.sack.eq(1)|frame.complete_pass.eq(1))&frame.qtr.between(1,4)&frame.two_point_attempt.eq(0)&frame.extra_point_attempt.eq(0)
        known=frame.index[touches][:80];frame.loc[known,'fumble_lost']=0.;frame.loc[known[:4],'fumble_lost']=1.
        samples,missing=L.event_samples(frame)
        self.assertEqual(len(samples['fumble_loss_rate']),80)
        self.assertEqual(samples['fumble_loss_rate'].sum(),4.)
        self.assertIn('unknown',missing['fumble_loss_rate'])

class ReplayAssemblyTests(unittest.TestCase):
    def actuals(self):
        return pd.DataFrame([dict({'Game ID':'official-game','Kickoff':'2026-11-09T18:00:00Z',
            'Team':r.Team,'Opponent':r.Opponent,'Name':r.Name,'Status':'FINAL'},**dict.fromkeys(STAT_KEYS,0.))
            for r in pool().itertuples()])

    def test_complete_exact_cases_pair_both_sites(self):
        from simmah_nfl_replay_inputs import assemble_replays
        result,report=assemble_replays(cases(),self.actuals(),source_sha256='a'*64)
        self.assertEqual(len(result),2)
        self.assertTrue(all(c['game_id']=='official-game' for c in result))
        self.assertTrue(all(r['status']=='ready' for r in report))

    def test_missing_players_not_inferred_as_zero(self):
        from simmah_nfl_replay_inputs import assemble_replays
        result,report=assemble_replays(cases(),self.actuals().iloc[1:],source_sha256='a'*64)
        self.assertEqual(result,[]);self.assertIn('AQB',report[0]['missing_players'])

    def test_missing_stats_or_nonfinal_rows_block_pairing(self):
        from simmah_nfl_replay_inputs import assemble_replays
        frame=self.actuals();frame.loc[0,'fumbles_lost']=np.nan
        with self.assertRaisesRegex(ValueError,'Missing'):assemble_replays(cases(),frame,source_sha256='a'*64)
        frame=self.actuals();frame.loc[0,'Status']='IN PROGRESS'
        with self.assertRaisesRegex(ValueError,'FINAL'):assemble_replays(cases(),frame,source_sha256='a'*64)

    def test_identity_conflict_not_fuzzy_matched(self):
        from simmah_nfl_replay_inputs import assemble_replays
        snapshots=cases();snapshots[0]['roles']['AQB']={'player_id':'correct-id'}
        frame=self.actuals();frame['Player ID']='wrong-id'
        result,report=assemble_replays(snapshots,frame,source_sha256='a'*64)
        self.assertEqual(len(result),1);self.assertEqual(report[0]['missing_players'],['AQB'])
