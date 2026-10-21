import copy
import unittest
import pandas as pd
from simmah_nba_live import parse_boxscore,match_pool,save_live_snapshot


class LiveScoreTests(unittest.TestCase):
    def fixture(self):
        game={'date':'2026-10-20T23:00Z','competitors':[{'team':{'abbreviation':'NY'}},{'team':{'abbreviation':'PHI'}}],
              'status':{'period':2,'displayClock':'0.0','type':{'state':'in','completed':False}}}
        payload={'header':{'id':'123','competitions':[game]},'boxscore':{'players':[{'team':{'abbreviation':'PHI'},
            'statistics':[{'labels':['PTS','3PT','REB','AST','STL','BLK','TO'],'athletes':[
                {'athlete':{'id':'1','displayName':'Example Player'},'stats':['5','0-2','4','4','0','0','1']}]}]}]}}
        pool=pd.DataFrame([{'Player ID':'site-1','Name':'Example Player','Team':'PHI','Opponent':'NYK'},
                           {'Player ID':'site-2','Name':'Unknown Player','Team':'PHI','Opponent':'NYK'}])
        return payload,pool

    def test_site_scoring_and_date_guard(self):
        payload,pool=self.fixture()
        for site,expected in [('FanDuel',14.8),('DraftKings',15.5)]:
            rows=parse_boxscore(payload,'123','2026-10-20',('NY','PHI'),site)
            self.assertAlmostEqual(rows[0]['Fantasy Points'],expected)
            matched=match_pool(pool,rows)
            self.assertEqual(matched.iloc[0]['Player ID'],'site-1')
            self.assertTrue(pd.isna(matched.iloc[1]['Fantasy Points']))
        with self.assertRaises(ValueError):parse_boxscore(payload,'123','2026-10-19',('NY','PHI'),'FanDuel')

    def test_missing_stats_and_ambiguous_names_never_become_zero(self):
        payload,pool=self.fixture();payload['boxscore']['players'][0]['statistics'][0]['athletes'][0]['stats'][0]='--'
        rows=parse_boxscore(payload,'123','2026-10-20',('NY','PHI'),'FanDuel')
        self.assertIsNone(rows[0]['Fantasy Points'])
        self.assertEqual(match_pool(pool,rows+rows).iloc[0]['Game Status'],'UNMATCHED')

    def test_archive_live_final_and_correction_are_separate(self):
        payload,pool=self.fixture();rows=parse_boxscore(payload,'123','2026-10-20',('NY','PHI'),'FanDuel')
        state={};result={'rows':rows,'issues':[],'fetched_at':'2026-10-20T20:00:00-04:00'}
        self.assertTrue(save_live_snapshot(state,pool,'2026-10-20','FanDuel',result))
        self.assertFalse(save_live_snapshot(state,pool,'2026-10-20','FanDuel',result))
        self.assertFalse(state['nba_final_score_history'])
        result=copy.deepcopy(result);result['rows'][0]['Game Status']='FINAL'
        save_live_snapshot(state,pool,'2026-10-20','FanDuel',result)
        result['rows'][0]['Fantasy Points']=16.;save_live_snapshot(state,pool,'2026-10-20','FanDuel',result)
        self.assertEqual(len(state['nba_live_score_history']),3)
        self.assertEqual(len(state['nba_final_score_history']),1)
        self.assertEqual(next(iter(state['nba_final_score_history'].values()))['Fantasy Points'],16)
