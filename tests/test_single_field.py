import unittest
import numpy as np
import pandas as pd
from simmah_single_field import build_fanduel_single_field

class SingleFieldTests(unittest.TestCase):
    def test_legal_field_and_mvp_arithmetic(self):
        pool=pd.DataFrame({'Name':[str(i) for i in range(12)],'Salary':[8000]*12,'Projection':np.arange(12)+1,'Team':['A']*6+['B']*6})
        d=build_fanduel_single_field(pool,np.ones(12),np.ones(12),2000,(50000,60000),rng=np.random.default_rng(42))
        self.assertEqual(len(d),2000)
        for r in d.itertuples(index=False):
            ids=[int(x) for x in r[:6]]
            self.assertEqual(len(set(ids)),6)
            self.assertEqual(r.Salary,52000)
            self.assertAlmostEqual(r.ProjectedPoints,(ids[0]+1)*1.5+sum(i+1 for i in ids[1:]))
            self.assertEqual(len(set(pool.Team.iloc[ids])),2)
    def test_natural_duplicates_retained(self):
        p=pd.DataFrame({'Name':list('abcdef'),'Salary':[8000]*6,'Projection':[10]*6,'Team':['A']*3+['B']*3})
        d=build_fanduel_single_field(p,np.ones(6),np.ones(6),100,(50000,60000),rng=np.random.default_rng(1))
        self.assertEqual(len(d),100)
        self.assertLessEqual(d.MVP.nunique(),6)
    def test_impossible_range_does_not_return_partial_field(self):
        p=pd.DataFrame({'Name':list('abcdef'),'Salary':[8000]*6,'Projection':[10]*6,'Team':['A']*3+['B']*3})
        with self.assertRaises(ValueError):
            build_fanduel_single_field(p,np.ones(6),np.ones(6),10,(59000,60000),max_proposals=100)
