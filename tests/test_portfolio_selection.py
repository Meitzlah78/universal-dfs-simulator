import unittest
import numpy as np
import pandas as pd
from simmah_portfolio_selection import select_portfolio,put_portfolio_first


def fixture():
    rng=np.random.default_rng(9)
    names=np.array([f'P{i}' for i in range(35)])
    score=rng.random((2000,35));score[:,0:5]*=.2
    picks=np.argsort(score,axis=1)[:,:9]
    d=pd.DataFrame(names[picks],columns=[f'S{i}' for i in range(9)])
    d['Top1']=1-np.arange(len(d))/len(d)
    return d,list(d.columns[:9])


class PortfolioSelectionTests(unittest.TestCase):
    def test_caps_unique_legal_candidates_and_ranking_retained(self):
        d,slots=fixture();p=select_portfolio(d,slots,20,'Top1')
        self.assertEqual(len(p),20)
        counts=p[slots].stack().value_counts()
        self.assertLessEqual(counts.max(),16)
        originals={tuple(row) for row in d[slots].itertuples(index=False,name=None)}
        self.assertTrue(all(tuple(row) in originals for row in p[slots].itertuples(index=False,name=None)))
        self.assertEqual(p[slots].apply(lambda r:tuple(sorted(r)),axis=1).nunique(),20)
        q=put_portfolio_first(d,p,slots)
        pd.testing.assert_frame_equal(q.head(20),p,check_flags=False)

    def test_lock_manual_max_and_minimum(self):
        d,slots=fixture()
        # Lock means every selected lineup must contain the player.
        p=select_portfolio(d,slots,20,'Top1',controls={'P0':{'Lock':True},'P1':{'Max Exposure %':30},'P34':{'Min Exposure %':35}})
        c=p[slots].stack().value_counts()
        self.assertEqual(c['P0'],20)
        self.assertLessEqual(c.get('P1',0),6)
        self.assertGreaterEqual(c['P34'],7)

    def test_higher_explicit_minimum_can_exceed_auto_cap(self):
        d,slots=fixture();p=select_portfolio(d,slots,20,'Top1',controls={'P0':{'Min Exposure %':90}})
        self.assertGreaterEqual(p[slots].stack().value_counts()['P0'],18)

    def test_impossible_pool_stops_instead_of_repeating_lineups(self):
        d,slots=fixture();d.loc[:,'S0']='Always'
        with self.assertRaisesRegex(ValueError,'only .* of .* portfolio'):
            select_portfolio(d,slots,20,'Top1')

    def test_interchangeable_slot_permutations_not_unique(self):
        d,slots=fixture();d=d.iloc[:1].copy();other=d.copy();other.loc[0,slots[0]],other.loc[0,slots[1]]=d.loc[0,slots[1]],d.loc[0,slots[0]]
        with self.assertRaisesRegex(ValueError,'Only 1 unique'):
            select_portfolio(pd.concat([d,other]),slots,2,'Top1')

    def test_deterministic_and_zero_exposure(self):
        d,slots=fixture();controls={'P0':{'Max Exposure %':0}}
        a=select_portfolio(d,slots,20,'Top1',controls);b=select_portfolio(d,slots,20,'Top1',controls)
        pd.testing.assert_frame_equal(a,b)
        self.assertFalse((a[slots]=='P0').any().any())

if __name__=='__main__':unittest.main()
