import unittest
import numpy as np,pandas as pd
from simmah_nba_guided_search_offline import environment_weights,build_candidates
from simmah_nba_candidates import build_candidates as baseline
import test_nba_candidates as candidate_fixtures
class GuidedSearchTests(unittest.TestCase):
 def test_market_weight_direction_and_invalid_inputs(self):
  p=pd.DataFrame({'Team':['A','B','C','D'],'Opponent':['B','A','D','C'],'Game Total':[220.,220.,240.,240.],'Team Implied Points':[110.,110.,120.,120.]})
  g,w=environment_weights(p);self.assertGreater(w[1],w[0]);self.assertAlmostEqual(sum(w),1.)
  p.loc[0,'Team Implied Points']=100
  with self.assertRaises(ValueError):environment_weights(p)
 def test_disabled_challenger_reproduces_live_and_does_not_mutate_inputs(self):
  p,x=candidate_fixtures.CandidateTests().fixture();saved=x.copy()
  a=baseline(p,x,target=100,seed=84);b=build_candidates(p,x,target=100,seed=84)
  np.testing.assert_array_equal(a['indices'],b['indices']);np.testing.assert_array_equal(saved,x)
 def test_soft_guidance_preserves_legality_and_original_row_ids(self):
  from simmah_nba_rules import rules_for
  from simmah_nba_rosters import validate_lineup
  p,x=candidate_fixtures.CandidateTests().fixture();p['Game Total']=220.;p['Team Implied Points']=110.
  # Fixture has several opponents, fill two-sided markets in its own four teams.
  p['Opponent']=p['Team'].map({'A':'B','B':'A','C':'D','D':'C'})
  r=build_candidates(p,x,target=100,seed=84,environment_guidance={'focus_probability':.35,'utility_bonus_scale':.25})
  rules=rules_for(p)
  for row in r['indices']:validate_lineup(p,p.iloc[row]['Player ID'].astype(str).tolist(),salary_cap=rules['salary_cap'],max_from_team=rules['max_from_team'])
  self.assertEqual(len({tuple(sorted(row)) for row in r['indices']}),100);self.assertFalse(r['live_enabled'])

 def test_unbounded_guidance_is_rejected(self):
  p,x=candidate_fixtures.CandidateTests().fixture()
  for policy in [{'focus_probability':1.1,'utility_bonus_scale':.25},{'focus_probability':.35,'utility_bonus_scale':-1}]:
   with self.assertRaises(ValueError):build_candidates(p,x,target=10,environment_guidance=policy)
