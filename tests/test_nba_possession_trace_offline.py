import unittest
import numpy as np
from simmah_nba_possession_trace_offline import reconstruct_trace,kind
from simmah_nba_full_game_offline import simulate_game
from simmah_nba_engine import EventRates
from simmah_nba_rotation_schedule import build_rotation


def event(i,clock,typ,team='1',**kw):
 return {'id':str(i),'clock':{'displayValue':clock},'period':{'number':1},'type':{'text':typ},'team':{'id':team},'text':'','participants':[{'athlete':{'id':team}}],**kw}
def game(events,points=0):
 return {'event_id':'test','home_score':points,'away_score':0,'boxscore':{'players':[{'team':{'id':t},'statistics':[{'athletes':[{'athlete':{'id':t}}]}]} for t in ['1','2']]},'events':events}

class SourcePossessionTests(unittest.TestCase):
 def test_oreb_continues_and_next_starts_at_prior_end(self):
  events=[event(1,'11:45','Jump Shot',shootingPlay=True,pointsAttempted=2),event(2,'11:43','Offensive Rebound'),event(3,'11:30','Jump Shot',shootingPlay=True,scoringPlay=True,pointsAttempted=2),event(4,'11:10','Traveling',team='2',text='Player turnover'),event(5,'0:00','End Period')]
  r=reconstruct_trace(game(events,2));p=r['possessions']
  self.assertEqual(len(p),3);self.assertEqual(p[0]['seconds'],30);self.assertEqual(p[0]['oreb_tail_seconds'],[13]);self.assertEqual(p[1]['seconds'],20)
  self.assertEqual(sum(x['seconds'] for x in p),720);self.assertFalse(r['flags']);self.assertEqual(r['official_points'],r['reconciled_points'])
 def test_nonfinal_ft_team_rebound_is_not_new_control(self):
  ev=[event(1,'11:40','Shooting Foul',team='2'),event(2,'11:40','Free Throw',pointsAttempted=1,text='Player misses free throw 1 of 2'),event(3,'11:40','Defensive Rebound',team='2',participants=[]),event(4,'11:40','Free Throw',pointsAttempted=1,text='Player makes free throw 2 of 2',scoringPlay=True),event(5,'0:00','End Period')]
  r=reconstruct_trace(game(ev,1));self.assertEqual(r['possessions'][0]['end_reason'],'final_ft');self.assertFalse(r['flags']);self.assertEqual(r['reconciled_points'],1)
 def test_andone_missed_ft_oreb_is_new_control(self):
  ev=[event(1,'11:40','Jump Shot',shootingPlay=True,scoringPlay=True,pointsAttempted=2),event(2,'11:40','Shooting Foul',team='2'),event(3,'11:40','Free Throw',pointsAttempted=1,text='Player misses free throw 1 of 1'),event(4,'11:40','Offensive Rebound'),event(5,'11:30','Traveling',text='Player turnover'),event(6,'0:00','End Period')]
  r=reconstruct_trace(game(ev,2));self.assertEqual(r['possessions'][0]['end_reason'],'and_one_basket');self.assertEqual(r['possessions'][1]['origin'],'after_andone_oreb');self.assertEqual(r['possessions'][0]['oreb_tail_seconds'],[])
 def test_administrative_duplicate_team_rebound_ignored(self):
  ev=[event(1,'11:40','Jump Shot',shootingPlay=True,pointsAttempted=2),event(2,'11:40','Defensive Rebound',team='2'),event(3,'11:40','Defensive Rebound',team='2',participants=[]),event(4,'11:30','Traveling',team='2',text='Player turnover'),event(5,'0:00','End Period')]
  r=reconstruct_trace(game(ev));self.assertFalse(r['flags']);self.assertEqual(r['ignored_administrative_team_rebounds'],1)

class SimulatedTraceTests(unittest.TestCase):
 def test_counter_preserves_draws_and_partitions_clock(self):
  n=24;size=8;means=np.full((2,size),30.)
  rotations=np.stack([build_rotation(np.tile(means[t],(n,1)),31+t,t*size) for t in [0,1]],axis=1)
  rates=EventRates(.12,.10,.40,.55,.37,.78,.64,.25,.59,.10,12.5)
  kwargs=dict(shooting=np.tile([.4,.55,.37,.78],(16,1)),target_minutes=means,foul_rates=np.full(16,.1))
  plain=simulate_game(rotations,np.ones((2,size,5)),[rates]*2,57,**kwargs)
  traced=simulate_game(rotations,np.ones((2,size,5)),[rates]*2,57,possession_audit=True,**kwargs)
  for key in ['scores','stats','team_points','attempts','elapsed_seconds','player_minutes','personal_fouls']:np.testing.assert_array_equal(plain[key],traced[key])
  t=traced['possession_trace'];np.testing.assert_allclose(t['completed_seconds_by_origin'].sum(axis=1)+t['terminal_seconds_by_origin'].sum(axis=1),traced['elapsed_seconds'],atol=1e-8)
  np.testing.assert_array_equal(t['counts_by_team'].sum(axis=1),t['completed_by_origin'].sum(axis=1)+t['terminal_by_origin'].sum(axis=1))
  last=0
  for row in t['scenario_zero']:
   self.assertAlmostEqual(row['start_elapsed'],last);last=row['end_elapsed']
  self.assertAlmostEqual(last,traced['elapsed_seconds'][0])
