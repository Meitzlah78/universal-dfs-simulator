import unittest
import test_nba_history
from simmah_nba_historical_markets import parse_closing_market

class HistoricalMarketTests(unittest.TestCase):
    def sample(self):
        p=test_nba_history.NBAHistoryTests().sample()
        for team in p['header']['competitions'][0]['competitors']:
            team['id']='9' if team['homeAway']=='home' else '13'
        p['pickcenter']=[{'provider':{'id':'100'},'pointSpread':{
            'home':{'close':{'line':'-5.5'}},'away':{'close':{'line':'+5.5'}}},
            'total':{'over':{'close':{'line':'o225.5'}},'under':{'close':{'line':'u225.5'}}}}]
        return p
    def test_team_identity_and_closing_fields(self):
        r=parse_closing_market(self.sample(),'123','2026-10-20')
        self.assertEqual(r['team_implied_points'],{'9':115.5,'13':110})
    def test_open_only_and_conflicting_sides_rejected(self):
        p=self.sample();p['pickcenter'][0]['pointSpread']['home']={'open':{'line':'-5.5'}}
        with self.assertRaises(KeyError):parse_closing_market(p,'123','2026-10-20')
        p=self.sample();p['pickcenter'][0]['pointSpread']['away']['close']['line']='+6.5'
        with self.assertRaises(ValueError):parse_closing_market(p,'123','2026-10-20')
