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
        a=engine(30,7);b=engine(30,7)
        self.assertEqual(a.shape,(30,10));self.assertTrue(np.isfinite(a).all())
        np.testing.assert_array_equal(a,b)
        self.assertEqual(engine.last_report[0]['calibration']['targets'],[100,110])
        self.assertEqual(engine.last_report[0]['max_overtimes_supplied'],4)
        self.assertEqual(engine.last_report[0]['unresolved_tie_fraction'],0)
    def test_incomplete_rotations_roles_or_markets_rejected(self):
        p,m,r=self.fixture();p.loc[0,'Projected Minutes']=40
        with self.assertRaises(ValueError):PregameEngine(p,m,r)
        p,m,r=self.fixture();p.loc[0,ROLE_COLUMNS[0]]=np.nan
        with self.assertRaises(ValueError):PregameEngine(p,m,r)
        p,m,r=self.fixture()
        with self.assertRaises(ValueError):PregameEngine(p,[],r)
        p.loc[0,'Injury Status']='Out'
        with self.assertRaises(ValueError):PregameEngine(p,m,r)
