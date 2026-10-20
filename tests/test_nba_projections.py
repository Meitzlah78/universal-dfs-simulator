import unittest
import pandas as pd
from simmah_nba_projections import parse_dff, apply_projections, slate_date

class NBAProjectionTests(unittest.TestCase):
    def setUp(self):
        self.pool=pd.DataFrame([{'Player ID':'1-1','Name':'A','Team':'NY','Opponent':'PHI','Injury Status':'Active'},
            {'Player ID':'1-2','Name':'B','Team':'PHI','Opponent':'NY','Injury Status':'Out'}])
    def test_date_and_matchup_guards(self):
        html='<tr data-start_date="2026-10-20" data-name="A" data-team="NY" data-opp="PHI" data-ppg_proj="40">'
        self.assertEqual(parse_dff(html,'2026-10-20',self.pool),{('a','NY'):40})
        for bad in [html.replace('2026-10-20','2026-10-21'),html.replace('PHI','BOS'),html.replace('40','nan')]:
            with self.assertRaises(ValueError):parse_dff(bad,'2026-10-20',self.pool)
        self.assertEqual(slate_date('FanDuel-NBA-2026-10-20-135251-entries.csv'),'2026-10-20')
    def test_uploaded_zero_has_priority_and_out_is_ineligible(self):
        result=apply_projections(self.pool,{('a','NY'):40,('b','PHI'):25},pd.DataFrame({'Player ID':['1-1'],'Projection':[0]}))
        self.assertTrue(result.Projection.isna().iloc[0])
        self.assertFalse(result.Eligible.any())
        self.assertEqual(result['Projection Source'].iloc[0],'Uploaded CSV')
    def test_cross_slate_upload_rejected(self):
        with self.assertRaises(ValueError):apply_projections(self.pool,{},pd.DataFrame({'Player ID':['9-9'],'Projection':[40]}))
