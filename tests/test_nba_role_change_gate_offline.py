import unittest
import numpy as np
from simmah_nba_role_change_gate_offline import gated_minutes,starter_transition
class RoleGate(unittest.TestCase):
 def setUp(self):
  self.base=np.array([36,34,32,30,28,26,24,16,10,4.]);self.long=self.base.copy();self.long[0]=30;self.fast=self.base.copy();self.fast[7]=20
 def test_rising_core_keeps_recent_weight(self):
  v,mask=gated_minutes(self.base,self.long,self.fast,3,'baseline5');self.assertTrue(mask[0]);self.assertEqual(mask.sum(),1);self.assertAlmostEqual(v.sum(),240);self.assertTrue(np.all((v>=0)&(v<=48)))
 def test_threshold_is_strict_and_stable_core_not_triggered(self):
  long=self.base.copy();long[0]-=3;_,mask=gated_minutes(self.base,long,self.fast,3);self.assertFalse(mask.any())
 def test_recency_fallback_modes_are_distinct(self):
  fast=self.fast.copy();fast[0]=42;a,_=gated_minutes(self.base,self.long,fast,3,'baseline5');b,_=gated_minutes(self.base,self.long,fast,3,'fast3');self.assertGreater(b[0],a[0])
 def test_unknown_starter_history_is_not_a_promotion(self):
  self.assertEqual(starter_transition(True,None,None),'unknown');self.assertEqual(starter_transition(True,False,None),'unknown');self.assertEqual(starter_transition(None,False,True),'unknown')
 def test_expected_changes_are_distinct(self):
  self.assertEqual(starter_transition(True,False,True),'expected_promotion');self.assertEqual(starter_transition(False,True,True),'expected_bench_change');self.assertEqual(starter_transition(True,True,True),'stable_expected_starter')
 def test_invalid_input_rejected(self):
  with self.assertRaises(ValueError):gated_minutes(self.base,self.long[:-1],self.fast)
  with self.assertRaises(ValueError):gated_minutes(self.base,self.long,self.fast,-1)
  with self.assertRaises(ValueError):gated_minutes(self.base,self.long,self.fast,3,'unrecognized')
 def test_input_arrays_are_not_mutated(self):
  old=[a.copy() for a in [self.base,self.long,self.fast]];gated_minutes(self.base,self.long,self.fast)
  for a,b in zip(old,[self.base,self.long,self.fast]):np.testing.assert_array_equal(a,b)
 def test_insufficient_support_never_invents_players(self):
  with self.assertRaises(ValueError):gated_minutes([36]*4,[30]*4,[40]*4)
