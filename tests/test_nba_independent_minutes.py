import io,json,unittest
from unittest.mock import patch
import pandas as pd
from simmah_nba_projections import download_rotowire

class IndependentMinutesTests(unittest.TestCase):
    def test_fd_minutes_survive_optional_projection_outage_without_retry(self):
        pool=pd.DataFrame([{'Team':'ATL','Opponent':'ORL'}])
        listing={'slates':[{'slateID':9,'contestType':'Full Roster','startDateOnly':'2026-10-21','games':[1]}],
            'games':{'1':{'homeTeamCode':'ORL','visitTeamCode':'ATL','gameDate':'2026-10-21'}}}
        player={'slateID':7,'firstName':'Jalen','lastName':'Johnson','team':{'abbr':'ATL'},
            'opponent':{'team':'ORL'},'game':{'dateTime':'2026-10-21 19:00:00'},'minutes':35}
        calls=[]
        def get(url,timeout):
            calls.append(url)
            if 'projections.php' in url:raise TimeoutError('temporary outage')
            if 'players.php' in url:
                payload=[player]
            elif 'slate-list.php' in url:payload=listing
            else:payload={'access':True,'source':'RotoWire','rostership':[{'slateID':7,'rst':10}]}
            return io.BytesIO(json.dumps(payload).encode())
        with patch('simmah_nba_projections.urlopen',side_effect=get):
            values,details,sid=download_rotowire('2026-10-21',pool,platform='FanDuel')
        self.assertEqual(values,{})
        self.assertEqual(details[('jalen johnson','ATL')]['Projected Minutes'],35)
        self.assertEqual(details[('jalen johnson','ATL')]['RotoWire Projected Own %'],10)
        self.assertEqual(sid,'9')
        self.assertEqual(sum('projections.php' in c for c in calls),1)
        self.assertEqual(sum('players.php' in c for c in calls),1)

