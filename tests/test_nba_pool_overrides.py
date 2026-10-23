import unittest
import pandas as pd
from simmah_nba_pool_overrides import requested_pool_exclusions


class RequestedExclusionTests(unittest.TestCase):
    def setUp(self):
        self.pool=pd.DataFrame([
            {'Player ID':'fd-sergio','Name':'Sergio De Larrea','Team':'DAL','Projected Minutes':None},
            {'Player ID':'fd-other','Name':'Another Player','Team':'DAL','Projected Minutes':33},
            {'Player ID':'other-team','Name':'Sergio De Larrea','Team':'IND','Projected Minutes':12}])

    def test_explicit_player_drop_preserves_other_players_and_original(self):
        old=self.pool.copy(deep=True)
        result,names=requested_pool_exclusions(self.pool,'2026-10-23','FanDuel')
        self.assertEqual(result['Player ID'].tolist(),['fd-other','other-team'])
        self.assertEqual(names,['Sergio De Larrea'])
        pd.testing.assert_frame_equal(self.pool,old)
        self.assertEqual(result['Projected Minutes'].tolist(),[33,12])

    def test_exclusion_is_limited_to_requested_date_and_platform(self):
        for day,platform in [('2026-10-24','FanDuel'),('2026-10-23','DraftKings')]:
            result,names=requested_pool_exclusions(self.pool,day,platform)
            self.assertEqual(names,[])
            pd.testing.assert_frame_equal(self.pool,result)
