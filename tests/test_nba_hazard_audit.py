import unittest
import numpy as np
from scripts.audit_nba_hazards import observe_hazards,fit_hazards
from simmah_nba_engine import EventRates

class HazardExposureTests(unittest.TestCase):
 def event(self,k,clock='9:00',actor='1',text='',shot=False,points=0,made=False):
  return {'id':str(id(text)+points),'type':{'text':k},'period':{'number':1},'clock':{'displayValue':clock},'participants':[{'athlete':{'id':actor}}] if actor else [],'text':text,'shootingPlay':shot,'pointsAttempted':points,'scoringPlay':made}
 def test_and_one_is_verified_not_every_one_shot_trip(self):
  events=[self.event('Jump Shot',shot=True,points=2,made=True),self.event('Shooting Foul',actor='2'),self.event('Free Throw',text='makes free throw 1 of 1',points=1,made=True)]
  result=observe_hazards({'event_id':'1','date':'2026-11-01','events':events})['counts']
  self.assertEqual(result['verified_and_one_fouls'],1)
  events[-1]['participants']=[{'athlete':{'id':'3'}}]
  self.assertNotIn('verified_and_one_fouls',observe_hazards({'event_id':'1','date':'2026-11-01','events':events})['counts'])
 def test_nonfinal_free_throw_miss_is_not_a_live_rebound_exposure(self):
  events=[self.event('Free Throw',text='misses free throw 1 of 2',points=1),self.event('Offensive Rebound',actor=''),self.event('Free Throw',text='misses free throw 2 of 2',points=1),self.event('Defensive Rebound')]
  c=observe_hazards({'event_id':'1','date':'2026-11-01','events':events})['counts']
  self.assertEqual(c['final_ft_misses'],1);self.assertEqual(c['ft_dreb'],1);self.assertNotIn('ft_team_oreb',c)
 def test_fitting_is_prior_date_only_and_probabilities_sum_to_one(self):
  rates=EventRates(.12,.1,.4,.55,.37,.78,.64,.25,.59,.1,12.5)
  a={'game_id':'1','date':'2026-11-01','counts':{'fga':100,'fgm':50,'shooting_fouls':10,'verified_and_one_fouls':2,'fg_oreb':10,'fg_dreb':30,'fg_team_oreb':5,'fg_team_dreb':5}}
  b={'game_id':'2','date':'2026-11-02','counts':{'fga':10000,'shooting_fouls':9999}}
  x=fit_hazards([a,b],'2026-11-02',rates);y=fit_hazards([a],'2026-11-02',rates)
  self.assertEqual(x,y);self.assertEqual(x['training_games'],1)
  self.assertAlmostEqual(sum(x['fg_rebound_outcomes']),1)
  self.assertAlmostEqual(sum(x['ft_rebound_outcomes']),1)
  self.assertGreater(x['fg_rebound_outcomes'][2],0)

class IntegratedReboundTests(unittest.TestCase):
 def test_team_rebounds_do_not_create_player_fantasy_rebounds(self):
  from simmah_nba_full_game_offline import simulate_game
  from simmah_nba_rotation_schedule import build_rotation
  n=8;size=8;means=np.full((2,size),30.);reg=np.stack([build_rotation(np.tile(means[t],(n,1)),8+t,t*size) for t in (0,1)],axis=1)
  rates=EventRates(.12,.10,.4,.55,.37,.78,.64,.25,.59,.10,12.5)
  hazards={'and_one_probability_per_make':.03,'fg_rebound_outcomes':[0.,1.,0.,0.],'ft_rebound_outcomes':[0.,0.,1.,0.]}
  r=simulate_game(reg,np.ones((2,size,5)),[rates]*2,61,shooting=np.tile([.4,.55,.37,0.],(size*2,1)),target_minutes=means,foul_rates=np.full(size*2,.1),shot_hazards=hazards)
  e=r['mechanics_counters']
  np.testing.assert_array_equal(e['fg_player_dreb'],e['fg_miss_rebound_opportunities'])
  np.testing.assert_array_equal(e['ft_team_oreb'],e['ft_miss_rebound_opportunities'])
  self.assertGreater(e['ft_team_oreb'].sum(),0);self.assertEqual(e['ft_player_oreb'].sum(),0)
  np.testing.assert_array_equal(r['stats'][:,:,3].sum(axis=1),e['fg_player_dreb'])
  np.testing.assert_allclose(r['clock_audit']['regulation_seconds'].sum(axis=1),2880)

class ReplayResumeTests(unittest.TestCase):
 def test_finished_arms_are_preserved_without_resimulation(self):
  import tempfile,json,io,contextlib
  from pathlib import Path
  from unittest.mock import patch
  from scripts import replay_nba_hazard_audit as runner
  rates=EventRates(.12,.10,.4,.55,.37,.78,.64,.25,.59,.10,12.5)
  names=['clock_reference','shooting_fouls','rebound_outcomes','shooting_fouls_and_rebounds']
  keys=['points','fga','fta','shooting_fouls','non_andone_shooting_fouls','and_one_fouls','player_oreb','player_dreb','team_oreb','team_dreb','shot_clock_violations']
  rows=[{'game_id':'1','date':'2026-11-01','arm':a,'fitted_hazards':{'before':'2026-11-01'},'max_regulation_error':0.,'rebound_context_counts':{'fg_miss_rebound_opportunities':1.},**dict.fromkeys(keys,1.)} for a in names]
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);model=root/'data/nba_models';model.mkdir(parents=True);(model/'event-rates-before-2026-04-09.json').write_text(json.dumps({'rates':vars(rates)}))
   out=root/'result';out.mkdir();(out/'hazard-replays.json').write_text(json.dumps({'results':rows,'failures':[]}))
   game={'event_id':'1','date':'2026-11-01'}
   with patch.object(runner,'load',return_value=([game],{'1'})),patch.object(runner,'observed',return_value={}),patch.object(runner,'observe_hazards',return_value={}),patch.object(runner,'simulate_game',side_effect=AssertionError('finished replay rerun')),contextlib.redirect_stdout(io.StringIO()):
    runner.run(root,'unused',out)
   result=json.loads((out/'hazard-summary.json').read_text())
   self.assertEqual(result['checkpoint_records_carried'],4);self.assertEqual(result['arms']['clock_reference']['completed'],1)
   self.assertEqual(json.loads((out/'hazard-replays.json').read_text())['results'],rows)
