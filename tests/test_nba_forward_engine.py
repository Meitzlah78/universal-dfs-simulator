import unittest
import numpy as np
from simmah_nba_engine import simulate_game,EventRates

class NBAForwardTests(unittest.TestCase):
    def fixture(self,n=200):
        rotations=np.broadcast_to(np.arange(10).reshape(1,2,1,5),(n,2,48,5)).copy()
        profiles=np.ones((2,5,5))
        rates=[EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)]*2
        return rotations,profiles,rates
    def test_shared_events_conserve_scoring_and_credits(self):
        inputs=self.fixture();result=simulate_game(*inputs,seed=37);s=result['stats'];c=result['counters']
        points=2*s[:,:,0]+s[:,:,1]+s[:,:,2]
        np.testing.assert_array_equal(points[:,:5].sum(axis=1),result['team_points'][:,0])
        np.testing.assert_array_equal(points[:,5:].sum(axis=1),result['team_points'][:,1])
        self.assertTrue((s[:,:,1]<=s[:,:,0]).all())
        self.assertTrue((c['credited_assists']<=c['field_goal_makes']).all())
        self.assertTrue((c['steals']<=c['turnovers']).all())
        self.assertTrue((c['blocks']<=c['field_goal_misses']).all())
        self.assertTrue((c['credited_rebounds']<=c['field_goal_misses']+c['free_throw_misses']).all())
        np.testing.assert_array_equal(result['scores'],simulate_game(*inputs,seed=37)['scores'])
    def test_assister_cannot_be_shooter(self):
        rot,w,rates=self.fixture(30);w[:,:,:2]=0;w[:,0,:2]=1
        result=simulate_game(rot,w,rates,7)
        self.assertTrue((result['stats'][:,[0,5],4]==0).all())
    def test_bad_rotations_rejected(self):
        rot,w,rates=self.fixture(1);rot[0,0,0,0]=1
        with self.assertRaises(ValueError):simulate_game(rot,w,rates,1)

    def test_explicit_overtime_and_unresolved_tie(self):
        rot,w,rates=self.fixture(5)
        # Every action is a turnover: force ties to test bounded overtime without
        # forcing a winner or adding invented fantasy points.
        zero=[EventRates(1,0,0,0,0,0,0,0,0,0,13)]*2
        overtime=np.broadcast_to(np.arange(10).reshape(1,2,1,1,5),(5,2,2,5,5)).copy()
        result=simulate_game(rot,w,zero,7,overtime_rotations=overtime)
        self.assertTrue((result['overtime_periods']==2).all())
        self.assertTrue(result['requires_overtime'].all())
        np.testing.assert_allclose(result['elapsed_seconds'],3480)
        self.assertTrue((result['team_points']==0).all())
