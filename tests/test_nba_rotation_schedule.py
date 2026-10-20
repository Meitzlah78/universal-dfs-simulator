import unittest
import numpy as np
from simmah_nba_rotation_schedule import build_rotation

class ScheduleTests(unittest.TestCase):
    def test_occupancy_exact_minutes_offset_and_seed(self):
        m=np.array([[48,40,36,32,28,24,20,12],[48,48,48,48,48,0,0,0]])
        r=build_rotation(m,42,8)
        self.assertEqual(r.shape,(2,48,5))
        self.assertTrue((np.diff(np.sort(r,axis=2),axis=2)>0).all())
        for b in range(2):
            np.testing.assert_array_equal(np.bincount(r[b].ravel()-8,minlength=8),m[b])
        np.testing.assert_array_equal(r,build_rotation(m,42,8))
    def test_fractional_rounding_preserves_budget(self):
        m=np.full((100,10),24.)
        m[:,0]+=.7;m[:,1]-=.7
        r=build_rotation(m,9)
        for b in range(100):
            count=np.bincount(r[b].ravel(),minlength=10)
            self.assertLessEqual(abs(count-m[b]).max(),1)
    def test_incomplete_minutes_rejected(self):
        for m in ([[28]*8],[[48]*4],[[49,48,48,48,47]],[[float('nan')]*5]):
            with self.assertRaises(ValueError):build_rotation(m,1)

    def test_generated_rotations_feed_shared_event_engine(self):
        from simmah_nba_engine import simulate_game,EventRates
        m=np.tile([40,40,40,40,40,40],(10,1))
        rotations=np.stack([build_rotation(m,1),build_rotation(m,2,6)],axis=1)
        rates=[EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)]*2
        result=simulate_game(rotations,np.ones((2,6,5)),rates,7)
        self.assertEqual(result['scores'].shape,(10,12))
        self.assertTrue(np.isfinite(result['scores']).all())
