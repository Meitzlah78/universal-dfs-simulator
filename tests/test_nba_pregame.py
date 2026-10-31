import unittest
import numpy as np
import pandas as pd
from simmah_nba_pregame import PregameEngine,ROLE_COLUMNS
from simmah_nba_engine import EventRates

class PregameTests(unittest.TestCase):
    def fixture(self):
        p=pd.DataFrame([{'Player ID':str(i),'Team':'A' if i<5 else 'B',
            'Opponent':'B' if i<5 else 'A','Projection':30,'Injury Status':'Active',
            'Projected Minutes':48,**{c:1 for c in ROLE_COLUMNS}} for i in range(10)])
        markets=[{'teams':('A','B'),'implied_points':(100,110)}]
        rates=EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)
        return p,markets,rates
    def test_provider_inputs_reach_shared_engine(self):
        p,m,r=self.fixture();engine=PregameEngine(p,m,r)
        a=engine(30,7);prepared=engine.prepared[0];b=engine(30,7)
        self.assertIs(engine.prepared[0],prepared)
        self.assertEqual(a.shape,(30,10));self.assertTrue(np.isfinite(a).all())
        np.testing.assert_array_equal(a,b)
        self.assertEqual(engine.last_report[0]['calibration']['targets'],[100,110])
        self.assertEqual(engine.last_report[0]['max_overtimes_supplied'],10)
        self.assertEqual(engine.last_report[0]['unresolved_tie_fraction'],0)
    def test_incomplete_rotations_roles_or_markets_rejected(self):
        p,m,r=self.fixture();p.loc[0,'Projected Minutes']=40
        with self.assertRaises(ValueError):PregameEngine(p,m,r)
        p,m,r=self.fixture();p.loc[0,ROLE_COLUMNS[0]]=np.nan
        with self.assertRaises(ValueError):PregameEngine(p,m,r)
        p,m,r=self.fixture()
        with self.assertRaises(ValueError):PregameEngine(p,[],r,require_markets=True)
        p.loc[0,'Injury Status']='Out'
        with self.assertRaises(ValueError):PregameEngine(p,m,r)

    def test_missing_markets_keep_external_targets_and_report_no_calibration(self):
        for platform in ('DraftKings','FanDuel'):
            with self.subTest(platform=platform):
                p,_,r=self.fixture();before=p.copy(deep=True)
                engine=PregameEngine(p,[],r,platform=platform)
                output=engine(20,7)
                self.assertEqual(output.shape,(20,10))
                self.assertTrue(np.isfinite(output).all())
                self.assertEqual(engine.missing_markets,[('A','B')])
                calibration=engine.last_report[0]['calibration']
                self.assertFalse(calibration['applied'])
                self.assertIsNone(calibration['targets'])
                self.assertIsNone(calibration['within_four_points'])
                pd.testing.assert_frame_equal(p,before)

    def test_partial_markets_preserve_verified_game_and_cover_remaining_game(self):
        p,m,r=self.fixture();other=p.copy();other['Player ID']='x'+other['Player ID'];other['Team']=other['Team'].map({'A':'C','B':'D'});other['Opponent']=other['Opponent'].map({'A':'C','B':'D'})
        engine=PregameEngine(pd.concat([p,other],ignore_index=True),m,r)
        self.assertEqual(engine.missing_markets,[('C','D')])
        self.assertEqual(engine.games[0][0]['implied_points'],(100,110))
        self.assertIsNone(engine.games[1][0]['implied_points'])
        p.loc[0,'Projected Minutes']=None
        with self.assertRaisesRegex(ValueError,'rotation'):
            PregameEngine(p,[],r)



class ExtendedOvertimeTests(unittest.TestCase):
    def test_more_than_four_overtimes_continue_with_real_events(self):
        from simmah_nba_engine import simulate_game
        n=256
        regulation=np.stack([np.tile(np.arange(5),(n,48,1)),np.tile(np.arange(5,10),(n,48,1))],axis=1)
        overtime=np.repeat(regulation[:,:,:5,:][:,:,None,:,:],10,axis=2)
        rates=EventRates(0,0,0,.005,0,0,0,0,0,0,13)
        short=simulate_game(regulation,np.ones((2,5,5)),[rates]*2,83,overtime_rotations=overtime[:,:,:4])
        extended=simulate_game(regulation,np.ones((2,5,5)),[rates]*2,83,overtime_rotations=overtime)
        finished=(~extended['requires_overtime'])&(extended['overtime_periods']>4)
        self.assertTrue(finished.any())
        self.assertGreater(short['requires_overtime'].sum(),extended['requires_overtime'].sum())
        points=2*extended['stats'][:,:,0]+extended['stats'][:,:,1]+extended['stats'][:,:,2]
        np.testing.assert_array_equal(points[:,:5].sum(axis=1),extended['team_points'][:,0])
        np.testing.assert_array_equal(points[:,5:].sum(axis=1),extended['team_points'][:,1])
        np.testing.assert_allclose(extended['elapsed_seconds'][finished],2880+300*extended['overtime_periods'][finished],rtol=0,atol=1e-8)
        # Degenerate zero scoring stays unresolved and must still block downstream.
        from dataclasses import replace
        zero=simulate_game(regulation[:1],np.ones((2,5,5)),[replace(rates,make_two=0)]*2,83,overtime_rotations=overtime[:1])
        self.assertTrue(zero['requires_overtime'][0])
        from simmah_nba_pregame import validate_game_reports
        with self.assertRaisesRegex(ValueError,'unresolved overtime'):
            validate_game_reports([dict(teams=['A','B'],calibration={'applied':False},unresolved_tie_fraction=1)])
