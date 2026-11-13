import unittest
import numpy as np
from simmah_nba_mechanics_offline import RotationState,PossessionClock,sample_minutes,sample_shot,free_throws

class OfflineMechanicsTests(unittest.TestCase):
 def test_disqualification_immediate_and_minutes_conserved(self):
  s=RotationState(np.full(8,30.))
  court=s.choose(2880);s.advance(court,120)
  for _ in range(6):s.personal_foul(0)
  self.assertNotIn(0,s.choose(2760))
  with self.assertRaises(ValueError):s.advance([0,1,2,3,4],1)
  self.assertEqual(s.seconds.sum(),600)
  self.assertEqual(s.fouls[0],6)
 def test_exhausted_roster_is_explicit(self):
  s=RotationState(np.full(5,48.))
  for _ in range(6):s.personal_foul(0)
  with self.assertRaises(ValueError):s.choose(2000)
 def test_240_named_minutes_and_reproducibility(self):
  a=sample_minutes([36,36,36,36,36,20,20,20],[4]*8,500,14)
  np.testing.assert_allclose(a.sum(axis=1),240)
  self.assertTrue(((a>=0)&(a<=48)).all())
  np.testing.assert_array_equal(a,sample_minutes([36]*5+[20]*3,[4]*8,500,14))
 def test_shot_clock_and_offensive_reset(self):
  c=PossessionClock();self.assertEqual(c.elapse(30),(24.,'shot_clock_violation'))
  c.change_possession();self.assertEqual(c.shot,24)
  c.offensive_rebound();self.assertEqual(c.elapse(20),(14.,'shot_clock_violation'))
  c=PossessionClock(game=5,period=5);self.assertEqual(c.elapse(10),(5,'period_end'))
 def test_technical_miss_is_dead_and_retains_ball(self):
  r=free_throws('technical',0,np.random.default_rng(1))
  self.assertEqual(r['attempts'],1);self.assertFalse(r['live_rebound']);self.assertTrue(r['retains_possession'])
  for k,n in [('and_one',1),('two_shot',2),('three_shot',3)]:
   r=free_throws(k,0,np.random.default_rng(1));self.assertEqual(r['attempts'],n);self.assertTrue(r['live_rebound'])
 def test_shooter_specific_extremes(self):
  rng=np.random.default_rng(4)
  self.assertEqual(sample_shot([0,1,0],rng)['points'],2)
  self.assertEqual(sample_shot([1,0,1],rng)['points'],3)
 def test_foul_trouble_and_blowout_affect_choices_only_when_enabled(self):
  a=RotationState(np.array([36.]*5+[20.]*3),foul_trouble=False)
  b=RotationState(a.targets,foul_trouble=True)
  for _ in range(2):a.personal_foul(0);b.personal_foul(0)
  self.assertIn(0,a.choose(2700));self.assertNotIn(0,b.choose(2700))
  b=RotationState(a.targets,blowout=True)
  self.assertIn(0,b.choose(400,25));self.assertEqual(b.choose(300,25)[:3].tolist(),[5,6,7])

class IntegratedFoulMinutesTests(unittest.TestCase):
 def test_high_foul_rate_removes_player_and_redistributes_time(self):
  from simmah_nba_mechanics_offline import simulate_minutes_fouls
  r=simulate_minutes_fouls([36]*5+[20]*3,[0]*8,[100]+[0]*7,4,17)
  np.testing.assert_allclose(r['minutes'].sum(axis=1),240)
  self.assertTrue((r['fouls'][:,0]==6).all())
  self.assertTrue((r['minutes'][:,0]<2).all())
  self.assertFalse(r['live_enabled'])
