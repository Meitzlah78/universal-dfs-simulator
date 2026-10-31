import unittest
import numpy as np
from test_nba_late_swap import LateSwapTests
from simmah_nba_sim_late_swap import simulate_swap_entries
from simmah_nba_late_swap import export_swaps

class OngoingPregameSwapTests(unittest.TestCase):
    def test_explicit_pregame_mode_needs_no_final_actuals_and_keeps_locks(self):
        fixture=LateSwapTests();fixture.setUp();pool=fixture.pool
        field={'indices':np.array([list(range(9))]),'copies':np.array([9])}
        def factory(n,seed,open_ids):
            return np.random.default_rng(seed).gamma(4,8,(n,len(pool)))
        result=simulate_swap_entries(fixture.template,'42-99',pool,factory,field,
            np.r_[1.,np.zeros(9)],.05,now=fixture.now,simulations=30,candidate_target=10,pregame_locked=True)
        for slot in [0,3,6]:self.assertEqual(result['lineups'][0][slot],fixture.ids[slot])
        self.assertIn('NOT used',result['status'])
        export_swaps(fixture.template,'42-99',pool,result,now=fixture.now)
