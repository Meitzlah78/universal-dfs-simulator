import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from simmah_nba_individual_learning import frozen_snapshot, validate_individual, apply_individual
from simmah_nba_learning import ROLE_COLUMNS
from tests.test_nba_learning import game


class IndividualLearningTests(unittest.TestCase):
    def corpus(self, baseline=.9):
        games=[game('2026-10-'+str(i).zfill(2),i) for i in range(1,9)]
        snapshots=[]
        for i in range(5,9):
            day='2026-10-'+str(i).zfill(2)
            snapshots.append({'schema':1,'captured_at':day+'T15:00:00+00:00','players':{
                'player0':{'rates':[baseline,.1,.2,.05,.05],
                           'source':'Individual historical rates','game_start':day+'T20:00:00+00:00'}}})
        return games,snapshots

    def test_exact_provider_beats_candidate_despite_weak_position_prior(self):
        games,snapshots=self.corpus(.5)
        report=validate_individual(games,snapshots,'2026-10-09')
        self.assertEqual(report['status'],'rejected')
        self.assertNotIn('model',report)

    def test_per_player_confirmation_and_disjoint_dates(self):
        games,snapshots=self.corpus()
        report=validate_individual(games,snapshots,'2026-10-09')
        self.assertEqual(report['status'],'approved')
        player=report['players']['player0']
        self.assertEqual(player['accepted_roles'],['shot'])
        self.assertFalse(set(report['training_ids']) & set(player['selection_ids']+player['confirmation_ids']))
        for g in games[-2:]:
            for row in g['boxscore']['players'][0]['statistics'][0]['athletes']:
                row['stats'][1]='2-18'
        self.assertEqual(validate_individual(games,snapshots,'2026-10-09')['status'],'rejected')

    def test_missing_stale_and_postgame_snapshots_cannot_approve(self):
        games,snapshots=self.corpus()
        self.assertEqual(validate_individual(games,[],'2026-10-09')['status'],'pending')
        self.assertEqual(validate_individual(games,snapshots[:3],'2026-10-09')['status'],'pending')
        snapshots[0]['captured_at']='2026-10-05T21:00:00+00:00'
        with self.assertRaises(ValueError):
            validate_individual(games,snapshots,'2026-10-09')
        with self.assertRaises(ValueError):
            validate_individual(games,[],'2026-10-08')

    def test_snapshot_excludes_started_players_and_learning_preserves_inputs(self):
        pool=pd.DataFrame({'Name':['Player 0','Player 1'],
            'Game Start':['2026-10-09T20:00:00+00:00','2026-10-09T14:00:00+00:00'],
            'Role Rate Source':['Individual historical rates']*2,
            'Projection':[30.,20.],'Projected Minutes':[30.,20.],'Ownership':[40.,10.],
            **{c:[v,v] for c,v in zip(ROLE_COLUMNS,[.9,.1,.2,.05,.05])}})
        snapshot=frozen_snapshot(pool,'2026-10-09T15:00:00+00:00')
        self.assertEqual(set(snapshot['players']),{'player0'})
        games,snapshots=self.corpus();model=validate_individual(games,snapshots,'2026-10-09')['model']
        with tempfile.TemporaryDirectory() as root:
            digest=hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest()
            Path(root,'individual_role_challenger.json').write_text(json.dumps({'sha256':digest,'model':model}))
            old=apply_individual(pool,'2026-10-08',root)
            self.assertEqual(old.iloc[0][ROLE_COLUMNS[0]],.9)
            for platform in ['DraftKings','FanDuel']:
                pool.attrs['platform']=platform
                result=apply_individual(pool,'2026-10-09',root)
                self.assertEqual(result.attrs['nba_individual_learning']['matched_players'],1)
                self.assertEqual(result.loc[0,ROLE_COLUMNS[0]],.5)
                for c in ROLE_COLUMNS[1:]+['Projection','Projected Minutes','Ownership']:
                    pd.testing.assert_series_equal(result[c],pool[c])
                self.assertEqual(result.loc[1,ROLE_COLUMNS[0]],.9)

    def test_build_and_refresh_restore_source_before_challenger(self):
        from unittest.mock import patch
        from simmah_nba_role_priors import apply_position_priors
        from simmah_nba_learning import name_key
        pool=pd.DataFrame({'Name':['Player 0'],'Position':['PG'],'Projection':[30.],
            'Game Start':['2099-10-09T20:00:00+00:00'],'Projected Minutes':[30.],
            'Injury Status':['Active'],'Role Rate Source':['Individual historical rates'],
            **{c:[v] for c,v in zip(ROLE_COLUMNS,[.9,.1,.2,.05,.05])}})
        games,snapshots=self.corpus();model=validate_individual(games,snapshots,'2026-10-09')['model']
        baseline={'before':'2026-04-09','latest_game':'2026-04-08','positions':{'G':{'rates':[1.,.2,.3,.1,.1]}}}
        with tempfile.TemporaryDirectory() as root:
            digest=hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest()
            Path(root,'individual_role_challenger.json').write_text(json.dumps({'sha256':digest,'model':model}))
            with patch('simmah_nba_learning.MODEL_ROOT',Path(root)):
                result=apply_position_priors(pool,baseline,'2026-10-09')
                again=apply_position_priors(result,baseline,'2026-10-09')
                before=apply_position_priors(result,baseline,'2026-10-08')
            self.assertEqual(again.loc[0,ROLE_COLUMNS[0]],.5)
            self.assertEqual(before.loc[0,ROLE_COLUMNS[0]],.9)
            self.assertEqual(again.attrs['nba_individual_rate_snapshot']['players']['player0']['rates'][0],.9)
