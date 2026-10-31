import unittest
import pandas as pd
from simmah_nba_projections import select_rotowire_slate,parse_rotowire,team_key

class FanDuelPhoenixTests(unittest.TestCase):
    def test_fanduel_pho_matches_rotowire_phx_for_slate_and_minutes(self):
        pool=pd.DataFrame([{'Team':'PHO','Opponent':'POR'},{'Team':'POR','Opponent':'PHO'},
                           {'Team':'ATL','Opponent':'ORL'},{'Team':'ORL','Opponent':'ATL'}])
        listing={'slates':[{'slateID':29816,'contestType':'Full Roster','startDateOnly':'2026-10-21','games':[1,2]}],
            'games':{'1':{'homeTeamCode':'POR','visitTeamCode':'PHX','gameDate':'2026-10-21'},
                     '2':{'homeTeamCode':'ORL','visitTeamCode':'ATL','gameDate':'2026-10-21'}}}
        self.assertEqual(select_rotowire_slate(listing,'2026-10-21',pool)['slateID'],29816)
        player={'firstName':'Devin','lastName':'Booker','slateID':1,'team':{'abbr':'PHX'},
            'opponent':{'team':'POR'},'game':{'dateTime':'2026-10-21 22:00:00'},'minutes':35}
        _,details=parse_rotowire([player],None,'2026-10-21',pool)
        self.assertEqual(details[('devin booker','PHX')]['Projected Minutes'],35)
        self.assertEqual(team_key('PHO'),team_key('PHX'))
        self.assertNotEqual(team_key('PHO'),team_key('PHI'))
