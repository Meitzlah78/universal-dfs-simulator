import unittest
import pandas as pd
from simmah_nba_minutes_validation import freeze_minutes

class SnapshotClockTests(unittest.TestCase):
    def test_real_pool_column_and_eastern_naive_kickoff(self):
        pool=pd.DataFrame({'Player ID':['1'],'Game Start':['2026-10-20 19:00:00'],
            'Projected Minutes':[30.],'RotoWire Projected Own %':[20.]})
        snap=freeze_minutes(pool,'FanDuel','2026-10-20T22:00:00Z')
        self.assertIsNotNone(snap)
        self.assertEqual(snap['players'][0]['GameStart'],'2026-10-20T23:00:00+00:00')
        self.assertEqual(snap['players'][0]['RotoWire Projected Own %'],20.)
        self.assertIsNone(freeze_minutes(pool,'FanDuel','2026-10-20T23:00:00Z'))
    def test_date_only_does_not_prove_future_kickoff(self):
        pool=pd.DataFrame({'Player ID':['1'],'Game Start':['2026-10-20'],'Projected Minutes':[30.]})
        self.assertIsNone(freeze_minutes(pool,'FanDuel','2026-10-20T12:00:00Z'))
