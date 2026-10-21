import unittest
import pandas as pd
from simmah_nba_game_context import parse_game_context,apply_game_context

class ContextTests(unittest.TestCase):
    def payload(self):return {'games':{'1':{'gameDate':'2026-10-21 19:00:00','homeTeamCode':'WAS','visitTeamCode':'MIL','overUnder':'239','homeTeam':{'expectedScore':121.75},'visitTeam':{'expectedScore':117.25}}}}
    def pool(self):return pd.DataFrame({'Name':['A','B'],'Team':['MIL','WAS'],'Opponent':['WAS','MIL'],'Projection':[20,30]})
    def test_fd_times_scores_without_projection_metadata(self):
        p=self.pool();r=apply_game_context(p,parse_game_context(self.payload(),'2026-10-21',[('MIL','WAS')]))
        self.assertEqual(r['Team Implied Points'].tolist(),[117.25,121.75])
        self.assertTrue(r['Game Start'].str.contains('19:00:00-04:00').all())
        self.assertNotIn('Projected Minutes',r)
        pd.testing.assert_series_equal(p.Projection,r.Projection)
        self.assertNotIn('Game Start',p)
    def test_date_and_pair_guards(self):
        self.assertEqual(parse_game_context(self.payload(),'2026-10-20',[('MIL','WAS')]),{})
        self.assertEqual(parse_game_context(self.payload(),'2026-10-21',[('NY','PHI')]),{})
    def test_unknown_odds_still_preserve_schedule(self):
        d=self.payload();d['games']['1']['overUnder']=None
        r=apply_game_context(self.pool(),parse_game_context(d,'2026-10-21',[('MIL','WAS')]))
        self.assertIn('Game Start',r);self.assertNotIn('Team Implied Points',r)
    def test_salary_time_is_preserved(self):
        p=self.pool();p['Game Start']='2026-10-21T19:00:00-04:00'
        r=apply_game_context(p,parse_game_context(self.payload(),'2026-10-21',[('MIL','WAS')]))
        pd.testing.assert_series_equal(p['Game Start'],r['Game Start'])
    def test_duplicate_game_rejected(self):
        d=self.payload();d['games']['2']=dict(d['games']['1'])
        with self.assertRaises(ValueError):parse_game_context(d,'2026-10-21',[('MIL','WAS')])

if __name__=='__main__':unittest.main()
