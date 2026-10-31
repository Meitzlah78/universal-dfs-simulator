import unittest
import numpy as np
import pandas as pd
from simmah_nba_ownership import field_ownership_inputs,COLUMN

class PopularityFallbackTests(unittest.TestCase):
    def pool(self,values):
        return pd.DataFrame({'Projection':[20]*len(values),'Injury Status':['Active']*len(values),
            'Eligible':[True]*len(values),'Projected Minutes':[24]*len(values),COLUMN:values})
    def test_inconsistent_total_keeps_raw_relative_values(self):
        p=self.pool([10,20,30]);r=field_ownership_inputs(p)
        self.assertEqual(r['mode'],'relative popularity')
        np.testing.assert_array_equal(r['weights'],[10,20,30])
        self.assertIn('60.0%',r['status'])
        self.assertIn('900%',r['status'])
    def test_missing_or_invalid_values_remain_unknown(self):
        for values in [[10,np.nan,30],[10,101,30]]:
            r=field_ownership_inputs(self.pool(values))
            np.testing.assert_array_equal(r['weights'],np.ones(3))
    def test_valid_targets_still_use_fit_and_exclusions_stay_zero(self):
        p=self.pool([90]*10+[50]);p.loc[10,'Eligible']=False
        r=field_ownership_inputs(p)
        self.assertEqual(r['mode'],'projected');self.assertEqual(r['weights'][10],0)
        self.assertAlmostEqual(r['weights'].sum(),900)
