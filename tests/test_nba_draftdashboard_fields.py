import unittest
import pandas as pd,numpy as np
import test_nba_ownership_upload as old_fixture
from simmah_nba_ownership_upload import apply_snapshot
from simmah_nba_player_score import player_scores
class DraftDashboardFieldsTests(unittest.TestCase):
 def fixture(self):
  pool,frame=old_fixture.NBAOwnershipUploadTests().fixture();frame['Source']='DraftDashboard';return pool,frame
 def apply(self,p,f):return apply_snapshot(p,f.to_csv(index=False).encode(),'DraftKings','2026-11-06')
 def test_projected_fields_ratings_and_historical_fields_never_cross(self):
  p,f=self.fixture();f=f.drop(columns=['Projected Ownership %']);f['OWN']=[48.03]+[(800-48.03)/9]*9
  f['PRO']=47.89;f['MIN']=34;f['USE']='25%';f['DashRank']=100;f['Opponent Rank']=30;f['Position Rank']=30;f['FPPG']=41.8;f['PPM']=1.28;f['HIT']='56%';f['VAL']='5.3x'
  r,m=self.apply(p,f);self.assertAlmostEqual(r.loc[0,'Projection'],47.89);self.assertEqual(r.loc[0,'Projected Minutes'],34);self.assertAlmostEqual(r.loc[0,'DraftDashboard Projected Own %'],48.03)
  self.assertEqual(r.loc[0,'DraftDashboard Historical FPPG'],41.8);self.assertEqual(r.loc[0,'DraftDashboard DashRank'],100);self.assertEqual(r.loc[0,'DraftDashboard Position Defensive Rank'],30)
  self.assertEqual(r.loc[0,'DraftDashboard Usage %'],25);self.assertEqual(m['ownership_scope'],'main slate');self.assertIn('user-confirmed',m['draftdashboard_fields']['Projected Minutes']['meaning']);self.assertEqual(p.loc[0,'Projection'],30)
 def test_ratings_or_fppg_do_not_replace_projections(self):
  p,f=self.fixture();f['FPPG']=100;f['DashRank']=100;r,m=self.apply(p,f)
  pd.testing.assert_series_equal(r.Projection,p.Projection);pd.testing.assert_series_equal(r['Projected Minutes'],p['Projected Minutes']);self.assertFalse(r.attrs['draftdashboard_fields']['ratings_applied_as_projection_boost'])
 def test_bad_units_bad_rank_wrong_site_and_conflicts_fail_atomically(self):
  for col,val in [('MIN','34%'),('MIN',49),('PRO','47.89x'),('Position Rank',30.5),('Opponent Rank',31),('DashRank',101),('USE',101),('HIT',-1),('Site','FanDuel')]:
   p,f=self.fixture();before=p.copy(deep=True);f[col]=val
   with self.subTest(field=col),self.assertRaises(ValueError):self.apply(p,f)
   pd.testing.assert_frame_equal(p,before)
  p,f=self.fixture();f['PRO']=47;f['Projected Points']=48
  with self.assertRaises(ValueError):self.apply(p,f)
 def test_projection_zero_is_explicit_not_missing_fallback(self):
  p,f=self.fixture();f['PRO']=0;f['MIN']=0;r,m=self.apply(p,f);self.assertTrue(r.Projection.eq(0).all());self.assertTrue(r['Projected Minutes'].eq(0).all())

class SimmahPlayerScoreTests(unittest.TestCase):
 def fixture(self):
  return pd.DataFrame({'Player ID':['a','b','c'],'Name':['A','B','C'],'Salary':[5000,5000,5000],'Projection':[20.,30.,10.],'Projected Minutes':[30.,30.,0.],'Injury Status':['Active','Active','Out']})
 def test_score_is_relative_and_does_not_mutate_or_score_inactive_players(self):
  p=self.fixture();saved=p.copy(deep=True);x=np.array([[10.,20.,0.],[20.,30.,0.],[30.,40.,0.]])
  r=player_scores(p,x);self.assertGreater(r.loc[1,'Simmah Score'],r.loc[0,'Simmah Score']);self.assertTrue(pd.isna(r.loc[2,'Simmah Score']));self.assertTrue(pd.isna(r.loc[2,'Simulated Hit 5x %']));self.assertFalse(r.attrs['used_by_selector']);pd.testing.assert_frame_equal(p,saved)
 def test_provider_ranks_do_not_change_simmah_score(self):
  p=self.fixture();x=np.tile([20.,30.,0.],(10,1));a=player_scores(p,x);p['DraftDashboard DashRank']=[100,1,100];p['DraftDashboard Position Defensive Rank']=[30,1,30]
  b=player_scores(p,x);pd.testing.assert_series_equal(a['Simmah Score'],b['Simmah Score']);self.assertIn('DraftDashboard DashRank',b)
 def test_ties_and_one_player_do_not_imply_certainty(self):
  p=self.fixture();p.loc[1,'Projected Minutes']=0;r=player_scores(p,np.tile([20.,20.,0.],(5,1)));self.assertEqual(r.loc[0,'Simmah Score'],50.)
 def test_bad_outcome_alignment_rejected(self):
  with self.assertRaises(ValueError):player_scores(self.fixture(),np.ones((10,2)))
