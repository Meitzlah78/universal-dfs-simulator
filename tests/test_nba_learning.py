import hashlib,json,tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from simmah_nba_learning import train_and_validate,load_approved,apply_learned_roles,ROLE_COLUMNS,identities


def game(day,eid,shots=10):
    return {'event_id':str(eid),'date':day,'boxscore':{'players':[{'statistics':[{
        'names':['MIN','FG','AST','REB','STL','BLK'],
        'athletes':[{'athlete':{'id':str(i),'displayName':'Player '+str(i),'position':{'abbreviation':'PG'}},
                     'stats':['20',f'2-{shots}','2','4','1','1']} for i in range(60)]}]}]}}

class LearningTests(unittest.TestCase):
    def baseline(self):
        return {'before':'2026-04-09','positions':{'G':{'rates':[1.,.2,.3,.1,.1]}}}
    def fit(self):
        games=[game('2026-10-0'+str(i),i) for i in range(1,7)]
        return train_and_validate(games,'2026-10-07',self.baseline(),minimum_training=1,minimum_validation=3)
    def install(self,root,model):
        p=Path(root)/'learned_roles';p.mkdir()
        data=json.dumps(model).encode();file='learned_roles/test.json'
        (Path(root)/file).write_bytes(data)
        (Path(root)/'learned_roles_index.json').write_text(json.dumps({'versions':[{
            'file':file,'activation_date':model['activation_date'],'version':model['version'],
            'sha256':hashlib.sha256(data).hexdigest()}]}))
    def test_training_and_later_validation_are_disjoint(self):
        report=self.fit();self.assertEqual(report['status'],'approved')
        self.assertFalse(set(report['training_ids'])&set(report['validation_ids']))
        self.assertEqual(report['model']['latest_game'],'2026-10-03')
        self.assertEqual(report['observations'],180)
    def test_worse_candidate_rejected(self):
        baseline=self.baseline();baseline['positions']['G']['rates']=[.5,.1,.2,.05,.05]
        games=[game('2026-10-0'+str(i),i,shots=100 if i<=3 else 10) for i in range(1,7)]
        report=train_and_validate(games,'2026-10-07',baseline,minimum_training=1,minimum_validation=3)
        self.assertEqual(report['status'],'rejected');self.assertNotIn('model',report)
    def test_duplicate_future_and_small_sample_guards(self):
        g=game('2026-10-01',1)
        for games in [[g,g],[game('2026-10-05',1)]]:
            with self.assertRaises(ValueError):train_and_validate(games,'2026-10-05',self.baseline())
        self.assertEqual(train_and_validate([g],'2026-10-05',self.baseline())['status'],'pending')
    def test_live_application_dated_and_preserves_provider_inputs(self):
        for platform in ['DraftKings','FanDuel']:
            with tempfile.TemporaryDirectory() as root:
                model=self.fit()['model'];self.install(root,model)
                self.assertIsNone(load_approved('2026-10-06',root))
                pool=pd.DataFrame({'Name':['Player 0','Player 1','Unknown'],'Projection':[30.,40.,20.],
                    'Projected Minutes':[30.,35.,20.],'RotoWire Projected Own %':[10.,20.,5.],
                    'Role Rate Source':['Position prior (G); 2026-04-09','Individual historical rates','Position prior (G); 2026-04-09'],
                    **{c:[1.,2.,3.] for c in ROLE_COLUMNS}})
                pool.attrs['platform']=platform;original=pool.copy(deep=True)
                result=apply_learned_roles(pool,'2026-10-07',root)
                self.assertNotEqual(result.loc[0,ROLE_COLUMNS[0]],1.)
                self.assertEqual(result.loc[1,ROLE_COLUMNS[0]],2.)
                self.assertEqual(result.loc[2,ROLE_COLUMNS[0]],3.)
                for c in ['Projection','Projected Minutes','RotoWire Projected Own %']:
                    pd.testing.assert_series_equal(pool[c],result[c])
                pd.testing.assert_frame_equal(pool,original)
                self.assertEqual(result.attrs['nba_learning']['matched_players'],1)
    def test_corrupt_model_and_colliding_names_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            model=self.fit()['model'];self.install(root,model)
            (Path(root)/'learned_roles/test.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'checksum'):load_approved('2026-10-07',root)
        g=game('2026-10-01',1)
        athletes=g['boxscore']['players'][0]['statistics'][0]['athletes']
        athletes[1]['athlete']['displayName']=athletes[0]['athlete']['displayName']
        self.assertNotIn('player0',identities([g])[0])

    def test_shared_build_and_swap_prior_path_uses_approved_version(self):
        from unittest.mock import patch
        from simmah_nba_role_priors import apply_position_priors
        with tempfile.TemporaryDirectory() as root:
            model=self.fit()['model'];self.install(root,model)
            pool=pd.DataFrame({'Name':['Player 0'],'Player ID':['dk-player-id'],'Position':['PG'],
                'Projection':[30.],'Projected Minutes':[30.],'Injury Status':['Active'],
                'Role Rate Source':['Position prior (G); 2026-04-09'],
                **{c:[1.] for c in ROLE_COLUMNS}})
            with patch('simmah_nba_learning.MODEL_ROOT',Path(root)):
                output=apply_position_priors(pool,dict(self.baseline(),latest_game='2026-04-08'),'2026-10-07')
                refreshed=apply_position_priors(output,dict(self.baseline(),latest_game='2026-04-08'),'2026-10-07')
                historical=apply_position_priors(output,dict(self.baseline(),latest_game='2026-04-08'),'2026-10-06')
            self.assertTrue(output['Role Rate Source'].iloc[0].startswith('Learned historical roles '))
            self.assertEqual(refreshed.attrs['nba_learning']['version'],model['version'])
            self.assertEqual(output.Projection.iloc[0],30.)
            self.assertNotIn('nba_learning',historical.attrs)
            self.assertTrue(historical['Role Rate Source'].iloc[0].startswith('Position prior ('))

    def test_runner_publishes_only_approved_and_preserves_previous_on_rejection(self):
        from unittest.mock import patch
        import gzip,contextlib,io
        from scripts.learn_nba_roles import run
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);models=root/'models';archive=root/'archive'
            models.mkdir();archive.mkdir()
            (models/'position-roles-before-2026-04-09.json').write_text(json.dumps(self.baseline()))
            day=archive/'2026-10-01';day.mkdir()
            g=game('2026-10-01',1);g.update(home_score=100,away_score=90)
            g['events']=[{'homeScore':100,'awayScore':90}]
            (day/'1.json.gz').write_bytes(gzip.compress(json.dumps(g).encode()))
            report=self.fit();expected=report['model']['version']
            with patch('scripts.learn_nba_roles.train_and_validate',return_value=report),contextlib.redirect_stdout(io.StringIO()):
                run(archive,models,'2026-10-07')
            active=load_approved('2026-10-07',models)
            self.assertEqual(active['version'],expected)
            with patch('scripts.learn_nba_roles.train_and_validate',return_value={'status':'rejected'}),contextlib.redirect_stdout(io.StringIO()):
                run(archive,models,'2026-10-08')
            self.assertEqual(load_approved('2026-10-08',models)['version'],active['version'])
