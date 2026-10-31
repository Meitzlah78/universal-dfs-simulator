import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_nba_cash import flat_payouts,select_flat_primary
from simmah_nba_pipeline import run_pipeline
import test_nba_candidates

class CashTests(unittest.TestCase):
    def test_exact_paid_places_and_ticket_value(self):
        np.testing.assert_array_equal(flat_payouts(5,2,100,5),[100,100,0,0,0])
        for args in [(1,1,2,1),(5,5,2,1),(5,0,2,1),(5,2,1,1),(5,2,np.nan,1),(5,2,2,0)]:
            with self.assertRaises(ValueError):flat_payouts(*args)
    def test_cash_objective_is_not_top_one_or_roi_and_has_no_ownership_cap(self):
        for platform,size in [('DraftKings',8),('FanDuel',9)]:
            pool=pd.DataFrame({'Player ID':[str(i) for i in range(3*size)]})
            pool.attrs['platform']=platform
            candidates=np.arange(3*size).reshape(3,size)
            report=pd.DataFrame({'Cash %':[80.,65.,80.],'Evaluation Mean Points':[200.,250.,210.],
                'Top 1%':[1.,10.,2.],'Expected ROI (%)':[10.,30.,5.]})
            result=select_flat_primary(pool,candidates,report)
            self.assertEqual(result.iloc[0]['PG'],str(2*size))
            self.assertEqual(len(result),1)
    def test_flat_build_does_not_replace_tournament_or_apply_its_caps(self):
        for platform in ['DraftKings','FanDuel']:
            pool,_=test_nba_candidates.CandidateTests().fixture();pool.attrs['platform']=platform
            pool['Name']=pool['Player ID'];pool['Opponent']='E'
            before=pool.copy(deep=True)
            def engine(n,seed):return np.random.default_rng(seed).gamma(4,8,(n,len(pool)))
            with patch('simmah_nba_pipeline.select_entries',side_effect=AssertionError('Tournament selection called')):
                result=run_pipeline(pool,engine,np.ones(len(pool)),'synthetic',flat_payouts(51,20,2,1),1,1,
                    simulations=32,candidate_target=100,field_support_target=100,ownership_mode='relative popularity',
                    selection_mode='flat_payout',excluded_indices=np.array([0]))
            self.assertEqual(result['selection_mode'],'flat_payout')
            self.assertEqual(len(result['portfolio']),1)
            self.assertFalse(np.isin(result['candidates']['indices'],[0]).any())
            pd.testing.assert_frame_equal(pool,before)
    def test_nonflat_payout_or_multiple_primary_rejected_before_simulating(self):
        pool,_=test_nba_candidates.CandidateTests().fixture()
        for prizes,count in [([3,2,0],1),([2,2],1),([2,0,0],2)]:
            with patch('simmah_nba_pipeline.build_candidates') as build:
                with self.assertRaises(ValueError):run_pipeline(pool,None,np.ones(len(pool)),'test',prizes,1,count,selection_mode='flat_payout')
                build.assert_not_called()
