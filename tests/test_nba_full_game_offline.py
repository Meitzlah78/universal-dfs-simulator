import unittest
import numpy as np
from simmah_nba_engine import EventRates
from simmah_nba_full_game_offline import simulate_game
from simmah_nba_rotation_schedule import build_rotation

class IntegratedGameTests(unittest.TestCase):
 def test_game_ledgers_and_no_seventh_foul(self):
  n=32;size=8;means=np.full((2,size),30.)
  rotations=np.stack([build_rotation(np.tile(means[t],(n,1)),31+t,t*size) for t in (0,1)],axis=1)
  overtime=np.stack([np.stack([build_rotation(np.tile(means[t]*5/48,(n,1)),100+t+k,t*size,period_minutes=5) for k in range(4)],axis=1) for t in (0,1)],axis=1)
  rates=EventRates(.12,.10,.40,.55,.37,.78,.64,.25,.59,.10,12.5)
  from simmah_nba_engine import simulate_game as original
  from simmah_nba_baseline_audit_offline import simulate_game as instrumented
  old=original(rotations,np.ones((2,size,5)),[rates]*2,57,overtime)
  counted=instrumented(rotations,np.ones((2,size,5)),[rates]*2,57,overtime)
  for key in ['scores','stats','team_points','elapsed_seconds']:np.testing.assert_array_equal(old[key],counted[key])
  result=simulate_game(rotations,np.ones((2,size,5)),[rates]*2,57,overtime,shooting=np.tile([.4,.55,.37,.78],(2*size,1)),target_minutes=means,foul_rates=np.full(2*size,.1))
  stats=result['stats'];pts=2*stats[:,:,0]+stats[:,:,1]+stats[:,:,2]
  np.testing.assert_array_equal(pts.reshape(n,2,size).sum(axis=2),result['team_points'])
  expected=240+25*result['overtime_periods']
  np.testing.assert_allclose(result['player_minutes'].reshape(n,2,size).sum(axis=2),np.tile(expected[:,None],(1,2)),atol=1e-7)
  self.assertTrue((result['personal_fouls']<=6).all())
  self.assertTrue((stats[:,:,1]<=stats[:,:,0]).all())
  self.assertTrue((stats[:,:,0]<=result['attempts'][:,:,0]).all())
  self.assertTrue((stats[:,:,2]<=result['attempts'][:,:,2]).all())
  self.assertGreater(sum(result['mechanics_counters']['shot_clock_violations']),0)
  self.assertFalse(result['live_enabled'])

class ReplayCutoffTests(unittest.TestCase):
 def test_same_day_and_future_boxscores_cannot_change_prior(self):
  from scripts.replay_nba_full_game_offline import Priors
  from copy import deepcopy
  def game(day,goals):
   stats={'MIN':'30','FG':f'{goals}-10','3PT':'1-3','FT':'2-3','AST':'4','REB':'5','STL':'1','BLK':'1','PF':'2','TO':'2','PTS':str(goals*2+3)}
   return {'date':day,'event_id':day,'boxscore':{'players':[{'team':{'abbreviation':'BOS'},'statistics':[{'names':list(stats),'athletes':[{'athlete':{'id':'1','displayName':'Player'},'stats':list(stats.values())}]}]}]}}
  rates=EventRates(.12,.1,.4,.55,.37,.78,.64,.25,.59,.1,12.5)
  games=[game('2026-11-01',3),game('2026-11-02',4),game('2026-11-03',5)]
  first=Priors(games,'2026-11-02',rates).for_names(['player'])
  games[1]=game('2026-11-02',9);games[2]=game('2026-11-03',10)
  second=Priors(games,'2026-11-02',rates).for_names(['player'])
  for a,b in zip(first,second):np.testing.assert_array_equal(a,b)
