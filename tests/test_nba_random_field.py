import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_nba_random_field import build_randomized_field

class RandomFieldTests(unittest.TestCase):
    def setUp(self):
        self.pool=pd.DataFrame({'Player ID':[str(i) for i in range(10)],'Salary':[6000]*10})
        self.values=np.arange(200,dtype=float).reshape(20,10);self.weights=np.ones(10)
        self.support=np.array([list(range(9)),list(range(1,10))])
    def build(self,pct=0,count=499):
        with patch('simmah_nba_random_field.build_opponent_support',return_value={'indices':self.support}) as mock:
            result=build_randomized_field(self.pool,self.values,self.weights,contest_entries=500,opponent_entries=count,randomness_pct=pct)
            used=mock.call_args.args[1].copy()
        return result,used
    def test_zero_preserves_construction_inputs(self):
        original=self.values.copy();result,used=self.build()
        np.testing.assert_array_equal(used,original);np.testing.assert_array_equal(self.values,original)
        self.assertEqual(int(result['copies'].sum()),499)
    def test_randomness_reproducible_and_inputs_unchanged(self):
        original=self.values.copy();first,used=self.build(30);second,again=self.build(30)
        self.assertFalse(np.array_equal(used,original));np.testing.assert_array_equal(used,again)
        np.testing.assert_array_equal(first['copies'],second['copies']);np.testing.assert_array_equal(self.values,original)
    def test_complete_support_kept_with_zero_copies(self):
        result,_=self.build(count=1)
        self.assertEqual(len(result['support_probabilities']),2)
        self.assertEqual(int(result['support_copies'].sum()),1)
        self.assertAlmostEqual(float(result['support_probabilities'].sum()),1)
        self.assertFalse(result['settings']['live_enabled'])
    def test_invalid_settings(self):
        for changes in ({'randomness_pct':31},{'randomness_pct':-1},{'opponent_entries':500},{'opponent_entries':True}):
            args=dict(contest_entries=500,opponent_entries=499);args.update(changes)
            with self.assertRaises(ValueError):build_randomized_field(self.pool,self.values,self.weights,**args)

class IntegrationTests(unittest.TestCase):
    def test_real_builder_both_sites(self):
        from simmah_nba_rosters import validate_lineup
        pool=pd.DataFrame([{'Player ID':str(i),'Position':['PG','SG','SF','PF','C'][i%5],
            'Team':['A','B','C','D'][i%4],'Opponent':['B','A','D','C'][i%4],
            'Salary':4000+i*80,'Projection':20+i/4,'Injury Status':'Active'} for i in range(40)])
        values=np.random.default_rng(7).gamma(4,8,(100,40));original=values.copy()
        for site in ['DraftKings','FanDuel']:
            pool.attrs['platform']=site
            result=build_randomized_field(pool,values,np.ones(40),contest_entries=750,opponent_entries=749,randomness_pct=15,support_target=40)
            self.assertEqual(result['copies'].sum(),749)
            for row in result['support_indices']:
                validate_lineup(pool,pool.iloc[row]['Player ID'].tolist(),salary_cap=50000 if site=='DraftKings' else 60000,max_from_team=8 if site=='DraftKings' else 4)
        np.testing.assert_array_equal(values,original)
