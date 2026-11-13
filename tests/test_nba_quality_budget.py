import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import pandas as pd
from simmah_nba_contest import select_entries,reselect_saved_entries
from simmah_selector_budget import QualityNotCertified

class NBAQualityBudgetTests(unittest.TestCase):
 def fixture(self):
  p=pd.DataFrame({'Player ID':[str(i) for i in range(24)],'Name':['P'+str(i) for i in range(24)],'Projected Minutes':[30.]*24,'Projection':[20.]*24})
  p.attrs.update(platform='DraftKings',nba_uncapped=True)
  c=np.arange(24).reshape(3,8);r=pd.DataFrame({'Top 1%':[10.,9.,8.],'Expected ROI (%)':[-10.,-20.,-30.],'Expected Prize ($)':[.9,.8,.7],'Entry Fee ($)':[1.]*3})
  return p,c,r
 def test_budget_and_hard_manual_cap(self):
  p,c,r=self.fixture();v=select_entries(p,c,r,2,controls={'0':{'Max Exposure %':50}})
  self.assertEqual(len(v),2);self.assertGreaterEqual(v['Top 1%'].sum(),19*.95);self.assertLessEqual(v.attrs['actual_quality_loss'],.05)
  self.assertEqual(v.attrs['nba_hard_exposure_limits']['0']['Max Exposure %'],50)
 def test_negative_roi_uses_expected_payout(self):
  p,c,r=self.fixture();v=select_entries(p,c,r,2,metric='Expected ROI (%)')
  self.assertEqual(v.attrs['budget_metric'],'Expected Prize ($)');self.assertAlmostEqual(v.attrs['quality_optimum'],1.7)
 def test_disabled_diversity_skips_second_solver_and_preserves_hard_caps(self):
  from simmah_selector_budget import milp
  p,c,r=self.fixture()
  with patch('simmah_selector_budget.milp',wraps=milp) as solve:
   v=select_entries(p,c,r,2,diversity=0,controls={'0':{'Max Exposure %':0}})
  self.assertEqual(solve.call_count,1)
  self.assertAlmostEqual(v['Top 1%'].sum(),17.)
  self.assertEqual(v.attrs['actual_quality_loss'],0.)
  self.assertFalse(v.attrs['diversity_requested'])
  self.assertNotIn('0',v[list(['PG','SG','SF','PF','C','G','F','UTIL'])].values)
  self.assertIn('disabled',v.attrs['diversity_status'])
 def test_quality_timeout_preserves_saved_lineups_and_key(self):
  p,c,r=self.fixture();old=pd.DataFrame({'saved':[1,2]});built={'portfolio':old,'selection_key':'previous','candidates':{'indices':c},'report':r}
  with patch('simmah_selector_budget.milp',return_value=SimpleNamespace(status=1,x=np.array([1.,1.,0.]))):
   with self.assertRaises(QualityNotCertified):reselect_saved_entries(p,built,100,'Top 1%')
  self.assertIs(built['portfolio'],old);self.assertEqual(built['selection_key'],'previous')
 def test_diversity_timeout_retains_certified_quality_optimum(self):
  p,c,r=self.fixture()
  with patch('simmah_selector_budget.milp',side_effect=[SimpleNamespace(status=0,x=np.array([1.,1.,0.])),SimpleNamespace(status=1,x=None)]):
   v=select_entries(p,c,r,2)
  self.assertAlmostEqual(v['Top 1%'].sum(),19);self.assertFalse(v.attrs['diversity_optimal']);self.assertIn('retained certified',v.attrs['diversity_status'])
 def test_saved_selection_cache_and_score_change(self):
  p,c,r=self.fixture();v=select_entries(p,c,r,2);built={'portfolio':v,'candidates':{'indices':c},'report':r}
  with patch('simmah_nba_contest.select_entries',return_value=v) as f:
   reselect_saved_entries(p,built,100,'Top 1%');reselect_saved_entries(p,built,100,'Top 1%');self.assertEqual(f.call_count,1)
   built['report']=r.copy();built['report'].loc[0,'Top 1%']=11
   reselect_saved_entries(p,built,100,'Top 1%');self.assertEqual(f.call_count,2)

 def test_unexpected_solver_failure_preserves_saved_portfolio(self):
  p,c,r=self.fixture();old=pd.DataFrame({'saved':[1,2]});built={'portfolio':old,'candidates':{'indices':c},'report':r}
  with patch('simmah_nba_contest.select_entries',side_effect=RuntimeError('Solver failure')):
   with self.assertRaises(RuntimeError):reselect_saved_entries(p,built,100,'Top 1%')
  self.assertIs(built['portfolio'],old);self.assertNotIn('selection_key',built)
