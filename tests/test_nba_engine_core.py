import unittest
import numpy as np
import pandas as pd
from simmah_nba_scoring import score_fanduel
from simmah_nba_minutes import allocate_minutes,simulate_minutes

class NBACoreTests(unittest.TestCase):
    def test_scoring_and_no_double_counted_threes(self):
        self.assertEqual(score_fanduel(fgm=1,threes=1),3)
        self.assertEqual(score_fanduel(points=3,threes=1),3)
        line=dict(rebounds=10,assists=7,steals=2,blocks=3,turnovers=4)
        self.assertAlmostEqual(score_fanduel(fgm=8,threes=3,ftm=4,**line),56.5)
        self.assertEqual(score_fanduel(turnovers=3),-3)
    def test_minutes_conservation_injuries_and_reproducibility(self):
        rotation=pd.DataFrame({'Projected Minutes':[34,32,30,28,26,20,15,10],
            'Minutes SD':[3]*8,'Active':[True]*7+[False], 'Starter':[True]*5+[False]*3})
        m,b=simulate_minutes(rotation,1000,37)
        np.testing.assert_allclose(m.sum(axis=1)+b,240,atol=1e-7)
        self.assertTrue((m>=0).all() and (m<=48).all())
        self.assertTrue((m[:,-1]==0).all())
        np.testing.assert_array_equal(m,simulate_minutes(rotation,1000,37)[0])
        blow=simulate_minutes(rotation,1000,37,blowout=np.ones(1000,bool))[0]
        self.assertLess(blow[:,:5].sum(),m[:,:5].sum())
    def test_impossible_and_missing_rotations_rejected(self):
        with self.assertRaises(ValueError):allocate_minutes(np.ones((2,4)))
        with self.assertRaises(ValueError):simulate_minutes(pd.DataFrame({'Projected Minutes':[float('nan')],'Minutes SD':[2],'Active':[True]}),10,1)
