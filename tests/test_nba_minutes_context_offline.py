import unittest
import numpy as np
from scripts.slice_independent_minutes_context_offline import context_features,previous_rows,ridge_fit,normalized_blends
from simmah_nba_independent_minutes_offline import forecast_team
import pandas as pd
class Context(unittest.TestCase):
 def test_default_baseline_unchanged(self):
  r=[{'name':str(i),'team':'BOS','status':'Active'} for i in range(6)];h=[{'key':(str(i),'BOS'),'minutes':30+i,'date':'2026-10-20','completed_at':'2026-10-21T00:00Z','game_id':'1'} for i in range(6)]
  a=forecast_team(r,h,'2026-10-30','2026-10-30T22:00Z');b=forecast_team(r,h,'2026-10-30','2026-10-30T22:00Z',window=5,half_life=3.)
  self.assertEqual(a,b)
 def test_weighting_options_conserve_budget(self):
  r=[{'name':str(i),'team':'BOS','status':'Active'} for i in range(6)];h=[{'key':(str(i),'BOS'),'minutes':30+i+j,'date':f'2026-10-{20+j}','completed_at':f'2026-10-{21+j}T00:00Z','game_id':str(j)} for i in range(6) for j in range(3)]
  for window,half in [(1,3),(3,1),(5,1e12)]:
   p=forecast_team(r,h,'2026-10-30','2026-10-30T22:00Z',window=window,half_life=half);self.assertAlmostEqual(sum(x['predicted_minutes'] for x in p),240)
 def test_positive_role_history_is_strictly_earlier(self):
  h=[{'key':['test','BOS'],'minutes':30,'date':'2026-10-20','completed_at':'2026-10-21T00:00Z','game_id':'1'},{'key':['test','BOS'],'minutes':48,'date':'2026-10-30','completed_at':'2026-10-30T00:00Z','game_id':'2'},{'key':['test','BOS'],'minutes':0,'date':'2026-10-22','completed_at':'2026-10-23T00:00Z','game_id':'3'}]
  x=previous_rows(h,('test','BOS'),'2026-10-30',pd.Timestamp('2026-10-30T22:00Z'),True);self.assertEqual(len(x),1);self.assertEqual(x[0]['minutes'],30)
 def test_context_design_no_provider_input(self):
  x=context_features([12,36],1,10,30,[0,12]);self.assertEqual(x.shape,(2,6));self.assertAlmostEqual(x[1,5],.4);beta=ridge_fit(x,[1,-1]);self.assertTrue(np.isfinite(beta).all())
 def test_invalid_history_options_rejected(self):
  with self.assertRaises(ValueError):forecast_team([],[],'2026-10-30','2026-10-30T22:00Z',window=0)
  with self.assertRaises(ValueError):forecast_team([],[],'2026-10-30','2026-10-30T22:00Z',half_life=0)

 def test_normalized_ensemble_keeps240(self):
  arms,supported=normalized_blends(np.array([40.]*6),np.array([32.]*6));self.assertTrue(supported)
  for v in arms.values():self.assertAlmostEqual(v.sum(),240);self.assertTrue(np.all((v>=0)&(v<=48)))
 def test_missing_provider_not_zero_filled_in_ensemble(self):
  arms,supported=normalized_blends(np.array([40.]*6),np.array([32.]*5+[np.nan]));self.assertFalse(supported);self.assertTrue(all(np.isnan(v).all() for v in arms.values()))
