import unittest
import pandas as pd
from scripts.audit_shared_bench_offline import verify_pregame_forecasts,summarize_interval
from scripts.expand_minutes_evidence_offline import player_key

class MinutesEvidenceTests(unittest.TestCase):
    def test_verified_source_team_aliases_keep_player_identity(self):
        self.assertEqual(player_key('Alexandre Sarr','WSH'),player_key('Alex Sarr','WAS'))
        self.assertEqual(player_key('Lauri Markkanen','UTAH'),player_key('Lauri Markkanen','UTA'))
    def frame(self):
        return pd.DataFrame({'package':['a','b'],'player_id':['1','1'],
            'captured_at':['2026-11-01T22:00:00Z']*2,
            'observed_opening_utc':['2026-11-01T23:00:00Z']*2})
    def test_distinct_snapshots_allowed_and_equal_or_late_capture_rejected(self):
        verify_pregame_forecasts(self.frame())
        for t in ['2026-11-01T23:00:00Z','2026-11-01T23:00:01Z']:
            f=self.frame();f.loc[0,'captured_at']=t
            with self.assertRaises(ValueError):verify_pregame_forecasts(f)
    def test_duplicate_forecast_and_naive_timestamp_rejected(self):
        f=self.frame();f['package']='a'
        with self.assertRaises(ValueError):verify_pregame_forecasts(f)
        f=self.frame();f.loc[0,'captured_at']='2026-11-01T22:00:00'
        with self.assertRaises(ValueError):verify_pregame_forecasts(f)
    def test_discrete_interval_endpoints_and_missing_slice_count(self):
        self.assertEqual(summarize_interval(pd.DataFrame()),{'n':0})
        f=pd.DataFrame({'game_id':['1','1','2'],'actual':[1,9,12],'p10':[1]*3,'p90':[9]*3,'p99':[11]*3})
        s=summarize_interval(f)
        self.assertEqual(s['n'],3);self.assertEqual(s['games'],2)
        self.assertAlmostEqual(s['coverage80'],2/3);self.assertAlmostEqual(s['above_p99'],1/3)
