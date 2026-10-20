import unittest
import numpy as np
import pandas as pd
import test_nba_roles
from simmah_nba_role_priors import fit_position_priors,apply_position_priors
from simmah_nba_pregame import ROLE_COLUMNS

class PriorTests(unittest.TestCase):
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
