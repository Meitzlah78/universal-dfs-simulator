import unittest
import numpy as np
from simmah_nba_concentrated_minutes_offline import concentrated_transfer,redistribute_concentrated
class Concentrated(unittest.TestCase):
 def setUp(self):
  self.m=np.array([36,34,32,30,28,26,24,16,10,3,1.]);self.names=[f'Player {i}' for i in range(11)]
  self.pattern=[{'team':'BOS','donor':'Player 0','recipients':[{'name':f'Player {i}','probability':p} for i,p in [(5,.4),(7,.3),(8,.2),(10,.1)]]}]
 def test_two_and_rotation_recipient(self):
  x,l=concentrated_transfer(self.m,self.m,self.names,'BOS',{0:12},self.pattern,5)
  self.assertLessEqual(np.sum(x>self.m+1e-8),2);self.assertEqual(x[10],1);self.assertAlmostEqual(x.sum(),240);self.assertTrue(np.all((x>=0)&(x<=48)))
  self.assertEqual(l['unallocated'],0)
 def test_missing_support_not_uniform_fallback(self):
  x,l=concentrated_transfer(self.m,self.m,self.names,'BOS',{1:12},self.pattern,5)
  np.testing.assert_array_equal(x,self.m);self.assertEqual(l['unallocated'],12)
 def test_explicit_depth_permission(self):
  patterns=[{'team':'BOS','donor':'Player 0','recipients':[{'name':'Player 10','probability':1.}]}]
  a,l=concentrated_transfer(self.m,self.m,self.names,'BOS',{0:12},patterns,5);self.assertEqual(l['transferred'],0)
  b,l=concentrated_transfer(self.m,self.m,self.names,'BOS',{0:12},patterns,5,allow_deep=True);self.assertEqual(b[10],13)
 def test_zero_cut_not_recipient_exclusion(self):
  a,l=concentrated_transfer(self.m,self.m,self.names,'BOS',{0:12,5:0},self.pattern,5);self.assertIn(5,l['recipients'])
 def test_foul_then_script_schedules(self):
  from simmah_nba_rotation_schedule import build_rotation
  for seed in range(40):
   x,_=redistribute_concentrated(self.m,self.m,self.names,'BOS',self.pattern,seed,state='blowout',transfer_budget=12,foul_cuts={0:8})
   build_rotation(x[None,:],seed);self.assertAlmostEqual(x.sum(),240)
 def test_input_not_mutated(self):
  old=self.m.copy();concentrated_transfer(self.m,self.m,self.names,'BOS',{0:12},self.pattern,5);np.testing.assert_array_equal(self.m,old)
