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

class BuildCorrelationTests(unittest.TestCase):
    def test_slider_favors_positive_pairs_without_changing_simulated_scores(self):
        p=pd.DataFrame([{'Player ID':str(i),'Position':['PG','SG','SF','PF','C'][i%5],
            'Salary':5000,'Team':['A','B','C','D'][i%4],'Opponent':['B','A','D','C'][i%4],
            'Projection':30,'Injury Status':'Active'} for i in range(40)])
        rng=np.random.default_rng(5);groups=np.arange(40)//10
        outcomes=30+rng.normal(0,3,(2000,40))+rng.normal(0,5,(2000,4))[:,groups]
        original=outcomes.copy();matrix=np.corrcoef(outcomes,rowvar=False)
        for site in ['FanDuel','DraftKings']:
            p.attrs['platform']=site;means=[]
            for setting in [0,100]:
                built=build_candidates(p,outcomes,target=300,seed=17,correlation=setting)
                ids=built['indices'];pairs=np.triu_indices(ids.shape[1],1)
                means.append(matrix[ids[:,:,None],ids[:,None,:]][:,pairs[0],pairs[1]].mean())
                for row in ids:
                    validate_lineup(p,p.iloc[row]['Player ID'].tolist(),salary_cap=50000 if site=='DraftKings' else 60000,max_from_team=8 if site=='DraftKings' else 4)
            self.assertGreater(means[1],means[0])
        np.testing.assert_array_equal(outcomes,original)
        for setting in [-1,101,float('nan')]:
            with self.assertRaises(ValueError):build_candidates(p,outcomes,target=10,correlation=setting)

class OwnershipProposalTests(unittest.TestCase):
    def test_fresh_proposals_expand_support_without_changing_outcomes(self):
        from simmah_nba_candidates import build_opponent_support
        pool,outcomes=CandidateTests().fixture()
        original=outcomes.copy()
        weights=np.full(len(pool),900/len(pool))
        result=build_opponent_support(pool,outcomes,weights,target=100,entries=1000)
        self.assertEqual(result['expanded_support_target'],2000)
        ids=result['indices']
        self.assertGreater(len(ids),1000)
        self.assertEqual(len(ids),len(np.unique(np.sort(ids,axis=1),axis=0)))
        for row in ids:
            validate_lineup(pool,pool.iloc[row]['Player ID'].tolist(),salary_cap=60000,max_from_team=4)
        np.testing.assert_array_equal(outcomes,original)

class SalarySearchTests(unittest.TestCase):
    def test_search_discounts_slate_price_without_mutating_scenarios(self):
        pool,outcomes=CandidateTests().fixture()
        original=outcomes.copy()
        # Fixture projections increase .25 points for every $80.
        adjusted=outcomes-(.25/80)*(pool.Salary.to_numpy()-pool.Salary.mean())
        trial=build_candidates(pool,outcomes,target=100,seed=3,salary_aware=True)
        reference=build_candidates(pool,adjusted,target=100,seed=3)
        np.testing.assert_array_equal(trial['indices'],reference['indices'])
        np.testing.assert_array_equal(outcomes,original)
