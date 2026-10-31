import unittest
import numpy as np
from simmah_nba_engine import EventRates,simulate_game
from simmah_nba_projection_anchor import fit_player_means

class AnchorTests(unittest.TestCase):
    def test_allocation_fit_improves_external_target_alignment(self):
        rot=np.broadcast_to(np.arange(10).reshape(1,2,1,5),(1000,2,48,5)).copy()
        profiles=np.ones((2,5,5));rates=[EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)]*2
        base=simulate_game(rot,profiles,rates,7)['scores'].mean(axis=0).reshape(2,5)
        targets=base.copy();targets[:,0]+=15;targets[:,1:]-=15/4
        w,r,report=fit_player_means(rot,profiles,rates,targets,7)
        self.assertLess(report['validation_mae'],report['initial_fit_mae'])
        self.assertTrue(np.isfinite(w).all());self.assertTrue((w>=0).all())
        self.assertEqual(rates[0].assisted,.6)
        np.testing.assert_array_equal(profiles,np.ones((2,5,5)))
        self.assertTrue(all(.05<=x.assisted<=.95 for x in r))
    def test_invalid_targets_rejected(self):
        with self.assertRaises(ValueError):fit_player_means(None,np.ones((2,5,5)),[],np.ones((1,5)),1)
