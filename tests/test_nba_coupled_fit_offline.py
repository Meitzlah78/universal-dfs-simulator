import unittest
import numpy as np,pandas as pd
from scripts.fit_coupled_minutes_offline import fit,sampler
from simmah_nba_rotation_schedule import build_rotation
class Fit(unittest.TestCase):
 def rows(self):
  return pd.DataFrame([dict(game_id=str(game),team_key=team,date='2026-10-30',projected_minutes=m,name_key=str(i),delta=(-2 if i<7 else 5),blowout_proxy=True,competitive_proxy=False,foul_ledger_verified=True,foul_threshold_proxy=False) for game in range(2) for team in ['A','B'] for i,m in enumerate([36,34,32,30,28,26,24,16,10,4])])
 def test_game_not_site_or_team_probability_denominator(self):
  model=fit(self.rows());self.assertEqual(model['train_games'],2);self.assertAlmostEqual(model['probabilities']['blowout'],2.5/3.5);self.assertAlmostEqual(sum(model['probabilities'].values()),1)
 def test_all_rows_not_only_misses(self):
  f=self.rows();self.assertTrue((f.delta.abs()<=5).all());self.assertEqual(fit(f)['foul']['core']['n'],20)
 def test_no_truth_in_sampler_and_conservation(self):
  m=np.array([36,34,32,30,28,26,24,16,10,4.]);model=fit(self.rows());draw=sampler(model,'coupled');a=draw(m,100,11);b=draw(m,100,11);np.testing.assert_array_equal(a,b);np.testing.assert_allclose(a.sum(1),240);self.assertTrue(np.all((a>=0)&(a<=48)))
 def test_scheduler_accepts_boundary_repairs(self):
  m=np.array([48,48,48,48,47,1,0,0.]);model=fit(self.rows());v=sampler(model,'coupled')(m,1024,np.random.SeedSequence([83,0,1,731]));build_rotation(v,7)
 def test_heldout_labels_cannot_change_training_fit(self):
  f=self.rows();held=f.copy();held['date']='2026-11-06';held['delta']=1000
  a=fit(f);b=fit(pd.concat([f,held]).query("date < '2026-11-06'"));self.assertEqual(a,b)
 def test_empty_training_rejected(self):
  with self.assertRaises(ValueError):fit(self.rows().iloc[:0])
