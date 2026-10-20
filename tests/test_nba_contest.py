import unittest
import numpy as np
from simmah_nba_contest import evaluate_candidates

class NBAContestTests(unittest.TestCase):
    def test_compressed_duplicate_tie_prizes_and_top_one(self):
        x=np.ones((5,10));c=np.array([list(range(9))]);f=c.copy()
        r=evaluate_candidates(x,c,f,[10,6,0,0],1,construction_seed=1,evaluation_seed=2,field_copies=np.array([3]),batch_size=2)
        self.assertEqual(r.iloc[0]['Expected Prize ($)'],4)
        self.assertEqual(r.iloc[0]['Win %'],25)
        self.assertEqual(r.iloc[0]['Cash %'],50)
        self.assertEqual(r.iloc[0]['Expected ROI (%)'],300)
    def test_unique_winner_and_independent_seed_guard(self):
        x=np.ones((3,10));x[:,0]=10
        c=np.array([list(range(9))]);f=np.array([list(range(1,10))])
        r=evaluate_candidates(x,c,f,[10,0],1,construction_seed=1,evaluation_seed=2)
        self.assertEqual(r.iloc[0]['Expected Prize ($)'],10)
        with self.assertRaises(ValueError):evaluate_candidates(x,c,f,[10,0],1,construction_seed=1,evaluation_seed=1)
        with self.assertRaises(ValueError):evaluate_candidates(x,c,f,[10],1,construction_seed=1,evaluation_seed=2)

    def test_portfolio_reselects_scored_candidates_with_exposure_caps(self):
        import pandas as pd
        import test_nba_candidates
        from simmah_nba_candidates import build_candidates
        from simmah_nba_contest import select_entries
        from simmah_nba_rosters import SLOT_COLUMNS
        pool,x=test_nba_candidates.CandidateTests().fixture()
        candidates=build_candidates(pool,x,target=200)['indices']
        report=pd.DataFrame({'Top 1%':np.linspace(1,10,len(candidates))})
        portfolio=select_entries(pool,candidates,report,20,diversity=100)
        ids=portfolio[list(SLOT_COLUMNS)].to_numpy().ravel()
        _,counts=np.unique(ids,return_counts=True)
        self.assertLessEqual(counts.max(),12)
        self.assertEqual(len(portfolio),20)
        self.assertEqual(len(report),200)
