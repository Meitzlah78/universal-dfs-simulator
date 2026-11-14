import unittest
import numpy as np
from simmah_nba_independent_minutes_offline import forecast_team
class IndependentForecast(unittest.TestCase):
 def roster(self):return [{'name':f'Player {i}','team':'BOS','status':'Active'} for i in range(8)]
 def history(self):return [{'key':('player '+str(i),'BOS'),'minutes':m,'date':'2026-10-20','completed_at':'2026-10-21T02:00:00+00:00','game_id':'1'} for i,m in enumerate([36,34,32,30,28,26,24,30])]
 def predict(self,r=None,h=None,**kw):return forecast_team(self.roster() if r is None else r,self.history() if h is None else h,'2026-10-30','2026-10-30T22:00:00+00:00',**kw)
 def test_no_provider_dependence(self):
  a=self.predict();r=self.roster()
  for p in r:p.update({'Projected Minutes':48,'Projection':1000,'Salary':1,'Expected Starter':True})
  self.assertEqual(a,self.predict(r=r))
 def test_future_and_same_day_labels_excluded(self):
  h=self.history();extra=[dict(row,date='2026-10-30',minutes=0) for row in h]+[dict(row,date='2026-10-29',completed_at='2026-10-31T00:00:00+00:00',minutes=0) for row in h]
  self.assertEqual(self.predict(),self.predict(h=h+extra))
 def test_out_and_exact_budget(self):
  r=self.roster();r[0]['status']='Out';a=self.predict(r=r);self.assertEqual(len(a),7);self.assertAlmostEqual(sum(p['predicted_minutes'] for p in a),240);self.assertTrue(all(0<=p['predicted_minutes']<=48 for p in a))
 def test_missing_history_tag_not_missing_as_zero(self):
  a=self.predict(h=self.history()[:-1]);self.assertTrue(a[-1]['cold_start']);self.assertGreater(a[-1]['predicted_minutes'],0);self.assertEqual(a[-1]['history_n'],0)
 def test_no_history_or_naive_capture_rejected(self):
  with self.assertRaises(ValueError):self.predict(h=[])
  with self.assertRaises(ValueError):forecast_team(self.roster(),self.history(),'2026-10-30','2026-10-30T22:00:00')
 def test_history_ceiling(self):
  h=self.history()+[dict(row,date='2026-10-29',minutes=0) for row in self.history()]
  self.assertEqual(self.predict(),self.predict(h=h,history_ceiling='2026-10-29'))
