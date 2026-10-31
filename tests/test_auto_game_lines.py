import unittest
from datetime import datetime, timezone
from simmah_auto_game_lines import parse_scoreboard, download_lines
NOW=datetime(2026,10,19,20,tzinfo=timezone.utc)
def event(details='SF -7.5',state='pre',date='2026-10-20T00:15Z'):
    return {'date':date,'competitions':[{'status':{'type':{'state':state}},'competitors':[{'homeAway':'away','team':{'abbreviation':'WSH'}},{'homeAway':'home','team':{'abbreviation':'SF'}}], 'odds':[{'details':details,'spread':-7.5,'overUnder':52.5,'provider':{'name':'DraftKings'}}]}]}
class GameLinesTests(unittest.TestCase):
    def parse(self,e,games=('WAS @ SF',),dates=('2026-10-19',)):
        return parse_scoreboard({'events':[e]},games,dates,NOW)
    def test_home_sign_and_eastern_date(self):
        r=self.parse(event())['WAS @ SF'];self.assertEqual(r['home_spread'],-7.5);self.assertEqual(r['total'],52.5)
        self.assertEqual(r['source'],'ESPN / DraftKings')
    def test_away_favorite_sign(self):
        self.assertEqual(self.parse(event('WSH -3.5'))['WAS @ SF']['home_spread'],3.5)
    def test_reject_live_final_past_wrong_date_and_matchup(self):
        for e in [event(state='in'),event(state='post'),event(date='2026-10-19T19:00Z')]:self.assertEqual(self.parse(e),{})
        self.assertEqual(self.parse(event(),dates=('2026-10-18',)),{})
        self.assertEqual(self.parse(event(),games=('DAL @ GB',)),{})
    def test_bad_values_and_pickem(self):
        e=event();o=e['competitions'][0]['odds'][0];o['overUnder']=float('nan');self.assertEqual(self.parse(e),{})
        e=event('PK');e['competitions'][0]['odds'][0]['spread']=0
        self.assertEqual(self.parse(e)['WAS @ SF']['home_spread'],0)
    def test_duplicate_ambiguous_games_rejected(self):
        self.assertEqual(parse_scoreboard({'events':[event(),event()]},['WAS @ SF'],['2026-10-19'],NOW),{})
    def test_download_exact_date(self):
        calls=[]
        def fetch(day):calls.append(day);return {'events':[event()]}
        self.assertIn('WAS @ SF',download_lines(['WAS @ SF'],['2026-10-19'],fetch,NOW));self.assertEqual(calls,['2026-10-19'])
