import io
import json
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_nba_projections import download_rotowire
from simmah_nba_pregame import PregameEngine, ROLE_COLUMNS
from simmah_nba_engine import EventRates
from simmah_nba_role_priors import apply_position_priors


class GameScopedMinutesTests(unittest.TestCase):
    def recover(self, primary_minutes=None):
        pool=pd.DataFrame([{'Name':'Sergio De Larrea','Team':'DAL','Opponent':'SA'},
                           {'Name':'Known Player','Team':'GS','Opponent':'PHX'}])
        def player(name,team,opp,minutes,pid):
            first,last=name.split(' ',1)
            return {'firstName':first,'lastName':last,'slateID':pid,'minutes':minutes,
                    'team':{'abbr':team},'opponent':{'team':opp},'game':{'dateTime':'2026-10-24 19:30:00'}}
        def get(url,timeout):
            if 'slate-list' in url:
                dk='siteID=1' in url
                data={'slates':[{'slateID':1 if dk else 2,'contestType':'Classic' if dk else 'Full Roster',
                    'startDateOnly':'2026-10-24','games':[1] if dk else [1,2]}],
                    'games':{'1':{'homeTeamCode':'DAL','visitTeamCode':'SA','gameDate':'2026-10-24'},
                             '2':{'homeTeamCode':'PHX','visitTeamCode':'GS','gameDate':'2026-10-24'}}}
            elif 'players.php?slateID=1' in url:
                data=[player('Sergio de Larrea','DAL','SA',15,3)]
            elif 'players.php' in url:
                data=[player('Known Player','GS','PHX',30,4)]
                if primary_minutes is not None:data.append(player('Sergio De Larrea','DAL','SA',primary_minutes,5))
            elif 'rostership' in url:
                data={'access':True,'source':'RotoWire','rostership':[{'slateID':5,'rst':3.5}]}
            else:data={'access':True,'source':'RotoWire','projections':[{'slateID':4,'pts':25},{'slateID':5,'pts':7}]}
            return io.BytesIO(json.dumps(data).encode())
        with patch('simmah_nba_projections.urlopen',side_effect=get):
            return download_rotowire('2026-10-24',pool)

    def test_missing_player_recovered_without_full_slate_overlap(self):
        values,details,sid=self.recover()
        row=details[('sergio de larrea','DAL')]
        self.assertEqual(row['Projected Minutes'],15)
        self.assertIn('DraftKings',row['Minutes Source'])
        self.assertNotIn(('sergio de larrea','DAL'),values)
        self.assertIsNone(row['RotoWire Projected Own %'])
        self.assertEqual(sid,'2')

    def test_existing_invalid_minutes_recovered_without_erasing_site_ownership(self):
        values,details,_=self.recover('bad')
        row=details[('sergio de larrea','DAL')]
        self.assertEqual(row['Projected Minutes'],15)
        self.assertEqual(row['RotoWire Projected Own %'],3.5)
        self.assertEqual(values[('sergio de larrea','DAL')],7)

    def test_explicit_provider_zero_is_not_overridden(self):
        _,details,_=self.recover(0)
        row=details[('sergio de larrea','DAL')]
        self.assertEqual(row['Projected Minutes'],0)
        self.assertEqual(row['Minutes Source'],'RotoWire')


class RotationBudgetTests(unittest.TestCase):
    def fixture(self,total=230):
        pool=pd.DataFrame([{'Player ID':str(i),'Name':'Player '+str(i),'Team':'GS' if i<10 else 'PHX',
            'Opponent':'PHX' if i<10 else 'GS','Projection':25.,'Injury Status':'Active',
            'Projected Minutes':total/10 if i<10 else 24.,**{col:.2 for col in ROLE_COLUMNS}}
            for i in range(20)])
        rates=EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)
        return pool,rates

    def test_small_budget_difference_reconciles_without_changing_forecasts(self):
        pool,rates=self.fixture();before=pool.copy(deep=True)
        engine=PregameEngine(pool,[],rates,parallel=False)
        pd.testing.assert_frame_equal(pool,before)
        pd.testing.assert_series_equal(engine.pool['Projected Minutes'],pool['Projected Minutes'])
        pd.testing.assert_series_equal(engine.pool['Projection'],pool['Projection'])
        change=engine.rotation_reconciliation[0]
        self.assertEqual(change['team'],'GS');self.assertEqual(change['provider_total'],230)
        self.assertAlmostEqual(change['simulation_total'],240)
        np.testing.assert_allclose(engine.games[0][1][0][1],24)
        scores=engine(8,83)
        self.assertEqual(scores.shape,(8,20));self.assertTrue(np.isfinite(scores).all())

    def test_missing_minutes_and_large_shortfalls_still_block(self):
        pool,rates=self.fixture();pool.loc[0,'Projected Minutes']=np.nan
        with self.assertRaisesRegex(ValueError,'Complete positive projected rotation'):
            PregameEngine(pool,[],rates)
        pool,rates=self.fixture(220)
        with self.assertRaisesRegex(ValueError,'240 required'):PregameEngine(pool,[],rates)

    def test_complete_budgets_unchanged_and_zero_reserve_stays_out(self):
        pool,rates=self.fixture(240)
        reserve=dict(pool.iloc[0],**{'Player ID':'reserve','Projected Minutes':0.})
        pool=pd.concat([pool,pd.DataFrame([reserve])],ignore_index=True)
        engine=PregameEngine(pool,[],rates)
        self.assertEqual(engine.rotation_reconciliation,[])
        self.assertFalse(any(20 in group[0] for _,groups in engine.games for group in groups))

    def test_unprojected_reserve_keeps_physical_minutes_but_not_lineup_eligibility(self):
        pool,rates=self.fixture(240)
        pool['Position']='PG';pool['Projection Source']='RotoWire';pool['Eligible']=True
        pool.loc[0,'Projection']=np.nan;pool.loc[0,'Projection Source']='Missing';pool.loc[0,'Eligible']=False
        pool.loc[0,ROLE_COLUMNS]=np.nan
        model={'before':'2026-04-09','latest_game':'2026-04-08','positions':{'G':{'rates':[.4,.2,.1,.02,.01]}}}
        recovered=apply_position_priors(pool,model,'2026-10-24')
        self.assertTrue(recovered.loc[0,'Rotation Only'])
        self.assertFalse(recovered.loc[0,'Eligible'])
        self.assertTrue(pd.isna(recovered.loc[0,'Projection']))
        self.assertTrue(recovered.loc[0,ROLE_COLUMNS].notna().all())
        engine=PregameEngine(recovered,[],rates,parallel=False)
        self.assertEqual(len(engine.games[0][1][0][0]),10)
        self.assertEqual(engine.rotation_reconciliation,[])
        scores=engine(16,83)
        self.assertGreater(scores[:,0].sum(),0)
        self.assertTrue(pd.isna(engine.pool.loc[0,'Projection']))


if __name__=='__main__':unittest.main()
