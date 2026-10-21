import unittest
import pandas as pd
from simmah_nba_game_strip import game_records

class GameOrderTests(unittest.TestCase):
    def test_chronological_timezone_ties_and_unknown(self):
        p=pd.DataFrame([{'Name':a,'Team':a,'Opponent':b,'Game':a+'@'+b,
            'Game Start':time,'Injury Status':'Active'} for a,b,time in [
                ('AAA','BBB','2026-10-21T22:00:00-04:00'),
                ('MIL','WAS','2026-10-21 19:00:00'),
                ('ATL','ORL','2026-10-21T23:00:00Z'),
                ('CCC','DDD',None)]])
        r=game_records(p,[])
        self.assertEqual([x['label'] for x in r],['ATL @ ORL','MIL @ WAS','AAA @ BBB','CCC @ DDD'])
        self.assertEqual(r[-1]['start_time'],'Time TBD')

if __name__=='__main__':unittest.main()
