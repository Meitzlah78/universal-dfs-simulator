import unittest
from unittest.mock import patch
import pandas as pd
from simmah_nba_learning import ROLE_COLUMNS
from simmah_nba_role_policy_offline import blend_stale_provider_roles

class RolePolicyTests(unittest.TestCase):
 def pool(self):return pd.DataFrame([{'Name':'Player','Projection':20,'Projected Minutes':30,'Role Rate Source':'Individual historical rates',**dict.fromkeys(ROLE_COLUMNS,2.)}])
 def test_unknown_fresh_and_stale_precedence(self):
  p=self.pool();model={'version':'v','players_by_name':{'player':{'minutes':100,'rates':[6]*5,'enabled_roles':['shot']}}}
  with patch('simmah_nba_role_policy_offline.load_approved',return_value=model):
   r=blend_stale_provider_roles(p,'2026-11-11');self.assertEqual(r.iloc[0][ROLE_COLUMNS[0]],2)
   self.assertEqual(r.attrs['offline_role_policy']['reasons'],{'provider_freshness_unknown_kept':1})
   p['Role Rates As Of']='2026-11-10';self.assertEqual(blend_stale_provider_roles(p,'2026-11-11').iloc[0][ROLE_COLUMNS[0]],2)
   p['Role Rates As Of']='2026-10-01';r=blend_stale_provider_roles(p,'2026-11-11')
   self.assertEqual(r.iloc[0][ROLE_COLUMNS[0]],3);self.assertEqual(r.iloc[0][ROLE_COLUMNS[1]],2)
   self.assertEqual(r.Projection.tolist(),p.Projection.tolist());self.assertEqual(r['Projected Minutes'].tolist(),p['Projected Minutes'].tolist())
 def test_future_provider_timestamp_rejected(self):
  p=self.pool();p['Role Rates As Of']='2026-11-12'
  with patch('simmah_nba_role_policy_offline.load_approved',return_value=None),self.assertRaises(ValueError):blend_stale_provider_roles(p,'2026-11-11')
