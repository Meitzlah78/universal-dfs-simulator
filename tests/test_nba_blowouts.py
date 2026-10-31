import unittest
import numpy as np
from simmah_nba_blowouts import garbage_time_court
from simmah_nba_rotation_schedule import build_rotation
from simmah_nba_engine import simulate_game,EventRates

class BlowoutTests(unittest.TestCase):
    def test_thresholds_and_legality_both_sides(self):
        court=np.tile(np.arange(5),(6,1));minutes=np.tile([40,38,36,34,32,24,20,16,0],(6,1))
        out,changed=garbage_time_court(court,minutes,[2500,2530,2710,2710,2890,2710],[40,20,-15,14,50,0])
        np.testing.assert_array_equal(changed,[False,True,True,False,False,False])
        self.assertTrue((np.diff(np.sort(out,axis=1),axis=1)>0).all())
        self.assertFalse((out==8).any())
        self.assertLess((out[changed]<5).sum(),(court[changed]<5).sum())
        np.testing.assert_array_equal(garbage_time_court(court,minutes,np.full(6,2750),np.full(6,40),enabled=False)[0],court)
    def test_no_bench_and_zero_minutes_not_invented(self):
        c=np.arange(5)[None,:];m=np.array([[48,48,48,48,48,0]])
        out,changed=garbage_time_court(c,m,[2750],[30]);np.testing.assert_array_equal(out,c);self.assertFalse(changed.any())
    def test_live_engine_both_scoring_sites(self):
        minutes=np.array([[40,38,36,34,32,24,20,16]])
        rot=np.stack([build_rotation(np.repeat(minutes,30,axis=0),12,t*8) for t in range(2)],axis=1)
        good=EventRates(0,0,0,1,1,1,0,0,0,0,12)
        bad=EventRates(0,0,0,0,0,0,0,0,0,0,12)
        weights=np.ones((2,8,5))
        for site in ['FanDuel','DraftKings']:
            neutral=simulate_game(rot,weights,[good,bad],41,platform=site,blowouts=False)
            result=simulate_game(rot,weights,[good,bad],41,platform=site)
            self.assertTrue(result['blowout_rotation_applied'].all())
            self.assertGreater(result['stats'][:,5:8].sum(),neutral['stats'][:,5:8].sum())
            self.assertEqual(result['stats'][:,:8,0].sum()*2,result['team_points'][:,0].sum())
            again=simulate_game(rot,weights,[good,bad],41,platform=site)
            np.testing.assert_array_equal(result['scores'],again['scores'])
