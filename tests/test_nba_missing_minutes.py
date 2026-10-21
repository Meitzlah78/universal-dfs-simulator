import unittest
import numpy as np
import pandas as pd
from simmah_nba_role_priors import apply_position_priors
from simmah_nba_pregame import ROLE_COLUMNS

MODEL={'before':'2026-04-09','latest_game':'2026-04-08','positions':{'G':{'rates':[.4,.2,.1,.02,.01]}}}

class MissingMinutesTests(unittest.TestCase):
    def pool(self):
        return pd.DataFrame([{'Player ID':'1','Name':'Player','Position':'PG',
                             'Projection':25.,'Injury Status':'Active'}])
    def test_missing_column_does_not_crash_or_invent_minutes(self):
        p=self.pool();out=apply_position_priors(p,MODEL,'2026-10-21')
        self.assertTrue(out['Projected Minutes'].isna().all())
        self.assertEqual(out.loc[0,'Minutes Source'],'Missing')
        self.assertEqual(out.loc[0,'Role Rate Source'],'Missing')
        self.assertTrue(out[ROLE_COLUMNS].isna().all().all())
        self.assertNotIn('Projected Minutes',p)
        pd.testing.assert_series_equal(p.Projection,out.Projection)
    def test_invalid_minutes_do_not_receive_prior(self):
        for value in [None,np.nan,float('inf'),-1,0,49,'bad',pd.NA]:
            p=self.pool();p['Projected Minutes']=[value]
            out=apply_position_priors(p,MODEL,'2026-10-21')
            self.assertEqual(out.loc[0,'Role Rate Source'],'Missing')
    def test_valid_minutes_apply_prior(self):
        p=self.pool();p['Projected Minutes']=30
        out=apply_position_priors(p,MODEL,'2026-10-21')
        self.assertTrue(out[ROLE_COLUMNS].notna().all().all())
        self.assertEqual(out.loc[0,'Projected Minutes'],30)
    def test_individual_roles_survive_provider_outage(self):
        p=self.pool()
        for c in ROLE_COLUMNS:p[c]=.1
        out=apply_position_priors(p,MODEL,'2026-10-21')
        self.assertEqual(out.loc[0,'Role Rate Source'],'Individual historical rates')
        self.assertTrue(out['Projected Minutes'].isna().all())

if __name__=='__main__':unittest.main()
