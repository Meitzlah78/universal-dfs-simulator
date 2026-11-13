import unittest
import numpy as np
from simmah_nba_clock_offline import sample_duration
from scripts.replay_nba_clock_audit import fit_clock

class ClockSamplerTests(unittest.TestCase):
 def test_gamma_tail_is_not_automatically_an_expiration(self):
  raw=np.array([3.,15.,30.,80.]);budget=np.full(4,14.)
  result=sample_duration(raw,3.14,np.ones(4,int),budget,{'mode':'truncated','profiles':{}})
  self.assertTrue((result<14).all());self.assertTrue((result>=0).all())
 def test_only_supported_empirical_intervals_selected(self):
  raw=np.array([1.,6.,12.,24.]);budget=np.array([14.,14.,5.,2.])
  r=sample_duration(raw,3.,np.ones(4,int),budget,{'mode':'empirical','profiles':{'after_oreb':[1.,3.,6.,20.]}})
  self.assertTrue(set(r)<=set([1.,3.,6.]));self.assertTrue((r<budget).all())
 def test_current_date_and_future_events_do_not_enter_clock_fit(self):
  records=[{'date':d,'counts':{'violation':v,'make':100},'profiles':{'after_oreb':[x]}} for d,v,x in [('2026-11-01',1,5),('2026-11-02',80,30),('2026-11-03',90,40)]]
  m=fit_clock(records,'2026-11-02','empirical')
  self.assertEqual(m['training_games'],1);self.assertEqual(m['profiles']['after_oreb'],[5]);self.assertAlmostEqual(m['violation_probability'],1/101)
 def test_invalid_clock_support_rejected(self):
  with self.assertRaises(ValueError):sample_duration(np.array([1]),3,np.array([1]),np.array([-1]),{'mode':'truncated','profiles':{}})
  with self.assertRaises(ValueError):sample_duration(np.array([1]),3,np.array([1]),np.array([14]),{'mode':'unknown','profiles':{}})

class IntegratedClockTests(unittest.TestCase):
 def test_legal_clock_zero_violation_model_and_conserved_regulation(self):
  from simmah_nba_engine import EventRates
  from simmah_nba_full_game_offline import simulate_game
  from simmah_nba_rotation_schedule import build_rotation
  n=8;size=8;means=np.full((2,size),30.);profiles=np.ones((2,size,5))
  reg=np.stack([build_rotation(np.tile(means[t],(n,1)),9+t,t*size) for t in (0,1)],axis=1)
  ot=np.stack([np.stack([build_rotation(np.tile(means[t]*5/48,(n,1)),30+t+k,t*size,period_minutes=5) for k in range(2)],axis=1) for t in (0,1)],axis=1)
  saved=reg.copy();weights=profiles.copy();rates=EventRates(.12,.10,.4,.55,.37,.78,.64,.25,.59,.10,12.5)
  result=simulate_game(reg,profiles,[rates]*2,31,ot,shooting=np.tile([.4,.55,.37,.78],(2*size,1)),target_minutes=means,foul_rates=np.full(2*size,.1),clock_model={'mode':'truncated','profiles':{},'violation_probability':0.})
  self.assertEqual(int(result['mechanics_counters']['shot_clock_violations'].sum()),0)
  np.testing.assert_allclose(result['clock_audit']['regulation_seconds'].sum(axis=1),2880)
  np.testing.assert_allclose(result['clock_audit']['seconds'].sum(axis=1),result['elapsed_seconds'])
  np.testing.assert_array_equal(reg,saved);np.testing.assert_array_equal(profiles,weights)
