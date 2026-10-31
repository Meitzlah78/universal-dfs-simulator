import unittest
import numpy as np
import test_single_exhaustive as reference
from simmah_special_role_history import likely_special_players

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.pool=reference.ExhaustiveTests().pool()
        self.pool['Ownership']=np.arange(8,0,-1,dtype=float)
        self.history={'profiles':[{'site':'dk','available_date':'2026-10-16','source_sha256':'abc','entries':100,'special_mass_by_rank':[.8,.15,.04,.01]}]}
    def select(self,**kw):
        return likely_special_players(self.pool,'dk',self.history,slate_date='2026-10-22',**kw)
    def test_coverage_transfers_ranks_not_names(self):
        self.assertEqual(self.select()['player_ids'],['0','1','2'])
    def test_current_ownership_ties_remain(self):
        self.pool.loc[3,'Ownership']=self.pool.loc[2,'Ownership']
        self.assertEqual(self.select()['player_ids'],['0','1','2','3'])
    def test_future_history_rejected(self):
        self.history['profiles'][0]['available_date']='2026-10-22'
        with self.assertRaises(ValueError):self.select()
    def test_missing_ownership_does_not_invent_signal(self):
        self.pool.loc[0,'Ownership']=np.nan
        with self.assertRaises(ValueError):self.select()
    def test_wrong_site_rejected(self):
        self.history['profiles'][0]['site']='fd'
        with self.assertRaises(ValueError):self.select()
