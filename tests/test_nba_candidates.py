import unittest
import numpy as np
import pandas as pd
from simmah_nba_candidates import build_candidates
from simmah_nba_rosters import validate_lineup

class CandidateTests(unittest.TestCase):
    def fixture(self):
        p=pd.DataFrame([{'Player ID':str(i),'Position':['PG','SG','SF','PF','C'][i%5],
            'Team':['A','B','C','D'][i%4],'Salary':4000+i*80,'Projection':20+i/4,
            'Injury Status':'Active'} for i in range(40)])
        return p,np.random.default_rng(7).gamma(4,8,(100,40))
    def test_valid_unique_and_reproducible(self):
        p,x=self.fixture();p.loc[0,'Projection']=0;p.loc[1,'Injury Status']='Out'
        r=build_candidates(p,x,target=100,seed=3,salary_min=45000,max_attempts=10000)
        self.assertTrue(r['complete'],r)
        self.assertEqual(len({tuple(sorted(row)) for row in r['indices']}),100)
        self.assertFalse(np.isin(r['indices'],[0,1]).any())
        for row in r['indices']:
            validate_lineup(p,p.iloc[row]['Player ID'].tolist(),salary_cap=60000,max_from_team=4,salary_min=45000)
        np.testing.assert_array_equal(r['indices'],build_candidates(p,x,target=100,seed=3,salary_min=45000,max_attempts=10000)['indices'])
    def test_bounded_failure_no_duplicate_fill(self):
        p,x=self.fixture();r=build_candidates(p,x,target=100,max_attempts=5)
        self.assertLessEqual(r['unique'],5);self.assertFalse(r['complete'])
        with self.assertRaises(ValueError):build_candidates(p,x[:,:5])
