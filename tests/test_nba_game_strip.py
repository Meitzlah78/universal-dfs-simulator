import unittest
import pandas as pd
from simmah_nba_game_strip import team_lineup,game_records

class GameStripTests(unittest.TestCase):
    def pool(self):
        return pd.DataFrame([{'Player ID':str(i),'Name':'Player '+str(i),'Team':'NY' if i<5 else 'PHI',
            'Opponent':'PHI' if i<5 else 'NY','Game':'PHI@NY','Expected Starter':'Yes',
            'Starter Confirmed':True,'Injury Status':'Active'} for i in range(10)])
    def test_confirmed_five_and_correct_market_team_order(self):
        p=self.pool();records=game_records(p,[{'teams':('NY','PHI'),'implied_points':(118.5,114)}])
        self.assertEqual(records[0]['label'],'PHI @ NY')
        self.assertEqual([t['score'] for t in records[0]['teams']],[114,118.5])
        self.assertEqual([t['status'] for t in records[0]['teams']],['Confirmed','Confirmed'])
    def test_expected_partial_missing_and_false_strings_never_confirm(self):
        p=self.pool();p['Starter Confirmed']='False'
        self.assertEqual(team_lineup(p,'NY')['status'],'Expected')
        p.loc[0,'Expected Starter']='No'
        self.assertEqual(team_lineup(p,'NY')['status'],'Pending')
        self.assertEqual(team_lineup(p.drop(columns=['Starter Confirmed']),'NY')['status'],'Unavailable')
        self.assertIsNone(game_records(p,[])[0]['teams'][0]['score'])
    def test_out_starter_blocks_confirmation(self):
        p=self.pool();p.loc[0,'Injury Status']='Out'
        self.assertEqual(team_lineup(p,'NY')['status'],'Expected')

    def test_source_false_is_not_truthy_and_date_guard(self):
        from simmah_nba_lineups import parse_lineup_status
        source=[{'firstName':'A','lastName':'B','team':{'abbr':'NYK'},'opponent':{'team':'PHI'},
                 'game':{'dateTime':'2026-10-20 19:00:00'},
                 'lineup':{'slot':'Yes','isConfirmed':'false'}}]
        d=parse_lineup_status(source,'2026-10-20',(('NY','PHI'),('PHI','NY')))
        self.assertFalse(d[('a b','NY')]['Starter Confirmed'])
        with self.assertRaises(ValueError):parse_lineup_status(source,'2026-10-21',(('NY','PHI'),))

    def test_change_alert_is_sticky_until_refresh_and_slate_scoped(self):
        from simmah_nba_lineups import observe_lineup_change,acknowledge_lineup_refresh,refresh_button_style
        state={};expected=(('NY','Expected',('a','b','c','d','e')),)
        confirmed=(('NY','Confirmed',('a','b','c','d','e')),)
        self.assertFalse(observe_lineup_change(state,'slate1',expected))
        self.assertTrue(observe_lineup_change(state,'slate1',confirmed))
        self.assertTrue(observe_lineup_change(state,'slate1',expected))
        self.assertIn('#d62828',refresh_button_style(True))
        acknowledge_lineup_refresh(state)
        self.assertFalse(observe_lineup_change(state,'slate1',confirmed))
        self.assertFalse(observe_lineup_change(state,'slate2',expected))
        changed=(('NY','Confirmed',('a','b','c','d','replacement')),)
        self.assertTrue(observe_lineup_change(state,'slate2',changed))
