import unittest
import numpy as np
import pandas as pd
import test_nba_roles
from simmah_nba_role_priors import fit_position_priors,apply_position_priors
from simmah_nba_pregame import ROLE_COLUMNS

class PriorTests(unittest.TestCase):
    def test_zero_history_uses_prior_but_keeps_inputs_and_individual_roles(self):
        model={'before':'2026-04-09','latest_game':'2026-04-08',
               'positions':{'G':{'rates':[.4,.2,.1,.02,.01]}}}
        p=pd.DataFrame([{'Player ID':str(i),'Position':'PG','Projection':12.,
                         'Projected Minutes':minutes,'Injury Status':status,
                         **dict(zip(ROLE_COLUMNS,roles))}
                        for i,(minutes,status,roles) in enumerate([
                            (12,'Active',[0]*5),(12,'Active',[.1,0,0,0,0]),
                            (0,'Active',[0]*5),(np.nan,'Active',[0]*5),
                            (12,'Out',[0]*5)])])
        before=p.copy(deep=True)
        out=apply_position_priors(p,model,'2026-10-23')
        np.testing.assert_array_equal(out.loc[0,ROLE_COLUMNS].to_numpy(float),model['positions']['G']['rates'])
        np.testing.assert_array_equal(out.loc[1,ROLE_COLUMNS].to_numpy(float),[.1,0,0,0,0])
        self.assertIn('Position prior',out.loc[0,'Role Rate Source'])
        np.testing.assert_array_equal(out.loc[2:,ROLE_COLUMNS].to_numpy(float),np.zeros((3,5)))
        pd.testing.assert_frame_equal(p,before)
        for c in ['Projection','Projected Minutes','Injury Status']:
            pd.testing.assert_series_equal(out[c],p[c])
        again=apply_position_priors(out,model,'2026-10-23')
        pd.testing.assert_frame_equal(out,again)

    def test_empty_prior_rejected(self):
        p=pd.DataFrame([{'Player ID':'1','Position':'PG','Projection':12.,
                         'Projected Minutes':12,'Injury Status':'Active',
                         **{c:0. for c in ROLE_COLUMNS}}])
        model={'before':'2026-04-09','latest_game':'2026-04-08','positions':{'G':{'rates':[0]*5}}}
        with self.assertRaisesRegex(ValueError,'Invalid historical position prior'):
            apply_position_priors(p,model,'2026-10-23')

    def test_fanduel_zero_history_player_completes_game_simulation(self):
        from simmah_nba_pregame import PregameEngine
        from simmah_nba_engine import EventRates
        p=pd.DataFrame([{'Player ID':str(i),'Position':'PG','Team':'A' if i<5 else 'B',
            'Opponent':'B' if i<5 else 'A','Projection':30.,'Injury Status':'Active',
            'Projected Minutes':48,**{c:(0. if i==0 else .1) for c in ROLE_COLUMNS}} for i in range(10)])
        model={'before':'2026-04-09','latest_game':'2026-04-08','positions':{'G':{'rates':[.4,.2,.1,.02,.01]}}}
        rates=EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)
        # Reproduce the exact former failure before testing the repaired path.
        with self.assertRaisesRegex(ValueError,'Positive targets require supported player roles'):
            PregameEngine(p,[],rates,platform='FanDuel',parallel=False)(20,7)
        fixed=apply_position_priors(p,model,'2026-10-23')
        for markets in [[],[{'teams':('A','B'),'implied_points':(100,110)}]]:
            engine=PregameEngine(fixed,markets,rates,platform='FanDuel',parallel=False)
            scores=engine(30,7)
            self.assertEqual(scores.shape,(30,10))
            self.assertTrue(np.isfinite(scores).all())
            self.assertGreater(scores[:,0].sum(),0)

    def test_sourced_prior_does_not_create_or_replace_projection(self):
        g=test_nba_roles.game()
        for r in g['boxscore']['players'][0]['statistics'][0]['athletes']:
            r['athlete']['position']={'abbreviation':'G'}
        model=fit_position_priors([g],'2026-04-02',minimum_minutes=1)
        p=pd.DataFrame([{'Player ID':str(i),'Position':'PG','Projection':value,
                         'Projected Minutes':10,'Injury Status':'Active'} for i,value in enumerate([12,0,np.nan])])
        r=apply_position_priors(p,model,'2026-10-20')
        self.assertTrue(r.loc[0,ROLE_COLUMNS].notna().all())
        self.assertIn('Position prior',r.loc[0,'Role Rate Source'])
        self.assertTrue(r.loc[1,ROLE_COLUMNS].isna().all())
        pd.testing.assert_series_equal(p['Projection'],r['Projection'])
        with self.assertRaises(ValueError):apply_position_priors(p,model,'2026-04-01')
    def test_future_training_rejected(self):
        with self.assertRaises(ValueError):fit_position_priors([test_nba_roles.game()],'2026-04-01',1)
