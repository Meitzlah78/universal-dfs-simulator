import unittest
import pandas as pd
from simmah_nba_confirmed import parse_confirmed_page,apply_confirmed_status
from simmah_nba_player_display import player_labels


class SharedConfirmationTests(unittest.TestCase):
    def page(self,day='2026-10-20',count=5):
        sides=[]
        for side in ('visit','home'):
            names=''.join(f'<li class="lineup__player"><a title="{side} Player {i}" href="/basketball/player/{i}">Player</a></li>' for i in range(count))
            sides.append(f'<ul class="lineup__list is-{side}"><li class="lineup__status is-confirmed">Confirmed</li>{names}</ul>')
        return f'<main data-gamedate="{day}"><div class="lineup is-nba" data-lnum="1"><div class="lineup__abbr">OKC</div><div class="lineup__abbr">SAS</div>'+''.join(sides)+'</div></main>'

    def test_two_sites_share_confirmation_and_keep_saved_inputs(self):
        values=parse_confirmed_page(self.page(),'2026-10-20',[('SA','OKC')])
        for site in ('DK','FD'):
            pool=pd.DataFrame([{'Player ID':site+str(i),'Name':name,'Team':team,'Injury Status':'Active',
                'Expected Starter':False,'Starter Confirmed':False} for i,((name,team),_) in enumerate(values.items())])
            current=apply_confirmed_status(pool,values)
            self.assertEqual(sum('✅' in n for n in player_labels(pool,current).values()),10)
            self.assertFalse(pool['Starter Confirmed'].any())

    def test_wrong_date_missing_matchup_and_incomplete_five_rejected(self):
        for html,day,pairs in [(self.page(),'2026-10-21',[('SA','OKC')]),
                               (self.page(count=4),'2026-10-20',[('SA','OKC')]),
                               (self.page(),'2026-10-20',[('PHI','NY')])]:
            with self.assertRaises(ValueError):parse_confirmed_page(html,day,pairs)
