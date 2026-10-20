import unittest
from simmah_nba_history import parse_game

class NBAHistoryTests(unittest.TestCase):
    def sample(self):
        return {'header':{'id':'123','date':'2025-10-21T23:00:00Z','competitions':[{
            'status':{'type':{'completed':True}},'competitors':[{'homeAway':'home','score':'100'},{'homeAway':'away','score':'90'}]}]},
            'plays':[{'id':'1','homeScore':100,'awayScore':90}], 'boxscore':{'players':[{'team':{}}]}}
    def test_completed_prior_game(self):
        game=parse_game(self.sample(),'123','2026-10-20')
        self.assertEqual(game['home_score'],100)
        self.assertEqual(game['date'],'2025-10-21')
    def test_lookahead_incomplete_and_wrong_identity_rejected(self):
        for cutoff in ['2025-10-21','2025-10-20']:
            with self.assertRaises(ValueError):parse_game(self.sample(),'123',cutoff)
        with self.assertRaises(ValueError):parse_game(self.sample(),'999','2026-10-20')
        p=self.sample();p['plays'][0]['homeScore']=99
        with self.assertRaises(ValueError):parse_game(p,'123','2026-10-20')
        p=self.sample();p['header']['competitions'][0]['status']['type']['completed']=False
        with self.assertRaises(ValueError):parse_game(p,'123','2026-10-20')
