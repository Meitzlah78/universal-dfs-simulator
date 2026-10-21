import unittest
import numpy as np
import pandas as pd
from simmah_nba_candidates import build_candidates,build_opponent_support
from simmah_nba_ownership import field_ownership_inputs
from simmah_nba_field import build_field

class FieldEligibilityTests(unittest.TestCase):
    def test_both_sites_exclude_disabled_and_zero_minute_players(self):
        for platform,size in [('DraftKings',8),('FanDuel',9)]:
            n=102
            p=pd.DataFrame({'Player ID':[str(i) for i in range(n)],
                'Position':(['PG','SG','SF','PF','C']*21)[:n],
                'Team':['T'+str(i//10) for i in range(n)],
                'Opponent':['T'+str((i//10)^1) for i in range(n)],
                'Salary':4000,'Projection':25.,'Injury Status':'Active',
                'Eligible':True,'Projected Minutes':24.,'RotoWire Projected Own %':size})
            p.attrs['platform']=platform
            p.loc[100,'Eligible']=False;p.loc[101,'Projected Minutes']=0
            inputs=field_ownership_inputs(p)
            self.assertEqual(inputs['mode'],'projected')
            self.assertTrue((inputs['weights'][100:]==0).all())
            x=np.random.default_rng(7).gamma(4,6,(512,n));x[:,100:]=10000
            candidates=build_candidates(p,x,target=100)
            self.assertFalse(np.isin(candidates['indices'],[100,101]).any())
            support=build_opponent_support(p,x,inputs['weights'],target=2000)
            self.assertFalse(np.isin(support['indices'],[100,101]).any())
            fit=build_field(support['indices'],inputs['weights'],1000,source='fixture')
            self.assertLess(fit['max_expected_error_pct'],.1)
            self.assertEqual(fit['copies'].sum(),1000)
