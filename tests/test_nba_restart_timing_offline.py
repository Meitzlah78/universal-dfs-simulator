import unittest
from copy import deepcopy
import numpy as np
from simmah_nba_restart_timing_offline import fit_restarts,restart_observations
from simmah_nba_clock_offline import sample_duration
from test_nba_possession_trace_offline import event,game

class RestartTimingTests(unittest.TestCase):
 def clock(self):return {'mode':'empirical','profiles':{'after_make':[10.,20.],'after_dreb':[5.,12.,22.],'after_turnover':[3.,11.,19.]},'violation_probability':.01}
 def test_cutoff_and_input_immutability(self):
  c=self.clock();saved=deepcopy(c)
  records=[{'date':'2026-11-01','profiles':{'period_start':[18.],'dead_ball_inbound':[16.],'after_make':[17.]}},{'date':'2026-11-02','profiles':{'period_start':[1.]}},{'date':'2026-11-03','profiles':{'period_start':[2.]}}]
  r=fit_restarts(c,records,'2026-11-02');self.assertEqual(r['profiles']['period_start'],[18.]);self.assertEqual(r['restart_training']['games'],1);self.assertEqual(c,saved)
  self.assertEqual(r['profiles']['after_dreb'],c['profiles']['after_dreb']);self.assertEqual(r['profiles']['after_turnover'],c['profiles']['after_turnover']);self.assertEqual(r['violation_probability'],.01)
 def test_unmodified_transition_timers_and_new_codes(self):
  c=self.clock();r=fit_restarts(c,[{'date':'2026-11-01','profiles':{'period_start':[18.],'dead_ball_inbound':[16.]}}],'2026-11-02')
  raw=np.array([2.,8.,12.,22.]);budget=np.full(4,24.)
  for origin in [5,6]:np.testing.assert_array_equal(sample_duration(raw,3.,np.full(4,origin),budget,c),sample_duration(raw,3.,np.full(4,origin),budget,r))
  np.testing.assert_array_equal(sample_duration(raw,3.,np.full(4,7),budget,r),np.full(4,18.))
  np.testing.assert_array_equal(sample_duration(raw,3.,np.full(4,8),budget,r),np.full(4,16.))
 def test_first_action_not_full_possession_duration(self):
  ev=[event(1,'11:45','Jump Shot',shootingPlay=True,pointsAttempted=2),event(2,'11:43','Offensive Rebound'),event(3,'11:30','Jump Shot',shootingPlay=True,scoringPlay=True,pointsAttempted=2),event(4,'0:00','End Period')]
  g=game(ev,2);g['date']='2026-11-01';r=restart_observations(g)
  self.assertEqual(r['profiles']['period_start'],[15.])
 def test_no_future_fallback(self):
  r=fit_restarts(self.clock(),[], '2026-11-01');self.assertEqual(r['profiles']['period_start'],[10.,20.]);self.assertEqual(r['restart_training']['counts']['period_start'],0)

 def test_completed_restart_checkpoint_is_preserved(self):
  import tempfile,json,io,contextlib
  from pathlib import Path
  from unittest.mock import patch
  from scripts import replay_nba_possession_reconciliation as runner
  from simmah_nba_engine import EventRates
  rates=EventRates(.12,.10,.4,.55,.37,.78,.64,.25,.59,.10,12.5)
  row={'game_id':'1','date':'2026-11-01','arm':'restart_timing','points':1.}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);model=root/'data/nba_models';model.mkdir(parents=True);(model/'event-rates-before-2026-04-09.json').write_text(json.dumps({'rates':vars(rates)}))
   source=root/'nba-possession-results';source.mkdir();(source/'reconciliation-summary.json').write_text(json.dumps({'clean_game_ids':['1']}))
   out=root/'replay';out.mkdir();checkpoint=out/'possession-replays.json';checkpoint.write_text(json.dumps({'results':[row],'failures':[]}))
   g={'event_id':'1','date':'2026-11-01'}
   with patch.object(runner,'load',return_value=([g],{'1'})),patch.object(runner,'observed',return_value={}),patch.object(runner,'observe_hazards',return_value={}),patch('simmah_nba_restart_timing_offline.restart_observations',return_value={}),patch.object(runner,'simulate_game',side_effect=AssertionError('Finished replay rerun')),contextlib.redirect_stdout(io.StringIO()):
    runner.run(root,'unused',out,restarts='yes')
   self.assertEqual(json.loads(checkpoint.read_text())['results'],[row])
