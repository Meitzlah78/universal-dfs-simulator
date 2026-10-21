import io,json,unittest
from unittest.mock import patch
import pandas as pd
from simmah_nba_projections import download_rotowire
class MissingReserveTests(unittest.TestCase):
    def test_cross_site_metadata_preserves_zero_without_borrowing_scores(self):
        pool=pd.DataFrame([{'Name':'Sergio De Larrea','Team':'DAL','Opponent':'HOU'}])
        def get(url,timeout):
            if 'slate-list' in url:
                dk='siteID=1' in url
                data={'slates':[{'slateID':1 if dk else 2,'contestType':'Classic' if dk else 'Full Roster','startDateOnly':'2026-10-21','games':[1]}],
                    'games':{'1':{'homeTeamCode':'HOU','visitTeamCode':'DAL','gameDate':'2026-10-21'}}}
            elif 'players.php?slateID=1' in url:
                data=[{'slateID':3,'firstName':'Sergio','lastName':'de Larrea','team':{'abbr':'DAL'},
                    'opponent':{'team':'HOU'},'game':{'dateTime':'2026-10-21 20:30:00'},'minutes':0,'rostership':50}]
            elif 'players.php' in url:data=[]
            else:data={'access':True,'source':'RotoWire','projections':[],'rostership':[]}
            return io.BytesIO(json.dumps(data).encode())
        with patch('simmah_nba_projections.urlopen',side_effect=get):
            values,details,sid=download_rotowire('2026-10-21',pool)
        self.assertEqual(values,{})
        self.assertEqual(sid,'2')
        row=details[('sergio de larrea','DAL')]
        self.assertEqual(row['Projected Minutes'],0)
        self.assertIsNone(row['RotoWire Projected Own %'])
        self.assertIn('DraftKings',row['Minutes Source'])
