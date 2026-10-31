import unittest
import numpy as np
import pandas as pd
from test_nba_late_swap import LateSwapTests
from simmah_nba_sim_late_swap import simulate_swap_entries,final_scores
from simmah_nba_late_swap import locked_players,export_swaps


class SimLateSwapTests(unittest.TestCase):
    def test_independent_remaining_draws_locked_slots_and_export(self):
        fixture=LateSwapTests();fixture.setUp();pool=fixture.pool
        pool.loc[0,'Projection']=0;pool.loc[0,'Injury Status']='Out'
        field={'indices':np.array([list(range(9))]),'copies':np.array([9])}
        actuals=pd.DataFrame({'Player ID':pool['Player ID'],'Actual Points':np.arange(len(pool)),'Status':'FINAL'})
        seeds=[]
        def factory(n,seed,ids):
            self.assertFalse(locked_players(pool,fixture.now)[ids].any())
            seeds.append(seed)
            return np.random.default_rng(seed).gamma(4,8,(n,len(ids)))
        result=simulate_swap_entries(fixture.template,'42-99',pool,factory,field,
            np.r_[1.,np.zeros(9)],.05,actuals,now=fixture.now,simulations=30,candidate_target=10)
        self.assertEqual(len(set(seeds)),2)
        for slot in [0,3,6]:self.assertEqual(result['lineups'][0][slot],fixture.ids[slot])
        export_swaps(fixture.template,'42-99',pool,result,now=fixture.now)
        required=locked_players(pool,fixture.now)
        with self.assertRaises(ValueError):final_scores(None,pool,required)
        actuals.loc[0,'Status']='IN_PROGRESS'
        with self.assertRaises(ValueError):final_scores(actuals,pool,required)
        actuals.loc[0,'Status']='FINAL';actuals.loc[0,'Actual Points']=0
        self.assertEqual(final_scores(actuals,pool,required)[0],0)

    def test_fixed_dk_slots_exclude_new_started_players(self):
        from test_nba_candidates import CandidateTests
        from simmah_nba_candidates import build_candidates
        pool,outcomes=CandidateTests().fixture()
        pool.attrs['platform']='DraftKings';pool['Opponent']='X'
        built=build_candidates(pool,outcomes,target=30,salary_min=0,
            fixed_slots={0:0},excluded_indices=np.array([0,1,2]),max_attempts=10000)
        self.assertGreater(built['unique'],0)
        self.assertTrue((built['indices'][:,0]==0).all())
        self.assertFalse(np.isin(built['indices'],[1,2]).any())
