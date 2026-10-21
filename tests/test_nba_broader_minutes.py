import io,json,unittest
from unittest.mock import patch
import pandas as pd
from simmah_nba_projections import download_rotowire,select_rotowire_minutes_slate

class BroaderSlateMinutesTests(unittest.TestCase):
    def fixture(self):
        pool=pd.DataFrame([{'Team':'ATL','Opponent':'ORL'},{'Team':'ORL','Opponent':'ATL'}])
        listing={'slates':[{'slateID':9,'contestType':'Full Roster','startDateOnly':'2026-10-21','games':[1,2]}],
          'games':{'1':{'homeTeamCode':'ORL','visitTeamCode':'ATL','gameDate':'2026-10-21'},
                   '2':{'homeTeamCode':'BOS','visitTeamCode':'NYK','gameDate':'2026-10-21'}}}
        players=[{'slateID':1,'firstName':'Jalen','lastName':'Johnson','team':{'abbr':'ATL'},
          'opponent':{'team':'ORL'},'game':{'dateTime':'2026-10-21 19:00:00'},'minutes':35,'rostership':50},
          {'slateID':2,'firstName':'Other','lastName':'Player','team':{'abbr':'BOS'},
          'opponent':{'team':'NYK'},'game':{'dateTime':'2026-10-21 19:00:00'},'minutes':35}]
        return pool,listing,players
    def test_minutes_only_filters_games_and_does_not_borrow_ownership_or_points(self):
        pool,listing,players=self.fixture();calls=[]
        def get(url,timeout):
            calls.append(url)
            self.assertFalse('projections.php' in url or 'rostership.php' in url)
            return io.BytesIO(json.dumps(listing if 'slate-list' in url else players).encode())
        with patch('simmah_nba_projections.urlopen',side_effect=get):
            values,details,sid=download_rotowire('2026-10-21',pool)
        self.assertEqual(values,{})
        self.assertEqual(set(details),{('jalen johnson','ATL')})
        row=details[('jalen johnson','ATL')]
        self.assertEqual(row['Projected Minutes'],35)
        self.assertIsNone(row['RotoWire Projected Own %'])
        self.assertIsNone(row['RotoWire RST % (unverified)'])
        self.assertIn('broader slate 9',row['Minutes Source'])
    def test_wrong_date_or_missing_game_rejected(self):
        pool,listing,_=self.fixture()
        with self.assertRaises(ValueError):select_rotowire_minutes_slate(listing,'2026-10-22',pool)
        pool.loc[0,'Opponent']='HOU'
        with self.assertRaises(ValueError):select_rotowire_minutes_slate(listing,'2026-10-21',pool)
