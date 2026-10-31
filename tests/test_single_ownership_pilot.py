import unittest
import numpy as np
import pandas as pd
from scripts.test_single_ownership_learning import marginals,features

class OwnershipPilotTests(unittest.TestCase):
    def test_role_totals_and_no_double_selection(self):
        m,f=marginals(np.arange(1,30.)**2,np.arange(1,30.)**3)
        self.assertAlmostEqual(m.sum(),1);self.assertAlmostEqual(f.sum(),5)
        self.assertTrue((m+f<=1+1e-8).all())
    def test_exact_six_player_support(self):
        m,f=marginals(np.arange(1,7.),np.arange(1,7.))
        np.testing.assert_allclose(m+f,1,atol=1e-8)
    def test_invalid_weights_rejected(self):
        for w in [np.ones(5),np.array([1,1,1,1,1,np.nan]),np.array([1,1,1,1,1,0])]:
            with self.assertRaises(ValueError):marginals(w,w)
    def test_actual_scores_and_names_cannot_affect_features(self):
        p=pd.DataFrame({'salary':[1000,5000,10000],'position':['WR','RB','QB'],'Name':['A','B','C'],'FPTS':[0,0,0]})
        before=features(p);p['FPTS']=[90,70,80];p['Name']=['X','Y','Z']
        np.testing.assert_array_equal(before,features(p))

if __name__=='__main__':unittest.main()
