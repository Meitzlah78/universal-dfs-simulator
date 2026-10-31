import gzip
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from scripts.archive_nba_pbp import archive, run_nightly

class ArchiveTests(unittest.TestCase):
    def test_rollover_retry_idempotence_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            seen=[]
            def schedule(day,before):
                seen.append((day,before))
                return ['123','124'] if day=='2026-10-30' else []
            def download(eid,before):
                if eid=='124':raise OSError('temporarily unavailable')
                return {'event_id':eid,'date':'2026-10-30','events':[{'id':'1'}]}
            report=archive(directory,date(2026,10,31),schedule=schedule,download=download)
            self.assertEqual(len(seen),7)
            self.assertEqual(report['downloaded'],1)
            self.assertEqual(len(report['failures']),1)
            target=Path(directory)/'2026-10-30/123.json.gz'
            with gzip.open(target,'rt') as stream:self.assertEqual(json.load(stream)['event_id'],'123')
            def recovered(eid,before):
                self.assertEqual(eid,'124')
                return {'event_id':eid,'date':'2026-10-30','events':[{'id':'1'}]}
            report=archive(directory,date(2026,10,31),schedule=schedule,download=recovered)
            self.assertEqual(report['already_archived'],1)
            self.assertEqual(report['downloaded'],1)
            self.assertFalse(report['failures'])
    def test_wrong_date_is_not_saved_and_failed_schedule_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            def schedule(day,before):
                if day=='2026-10-30':raise OSError('scoreboard unavailable')
                return ['123']
            report=archive(directory,date(2026,10,31),lookback=2,schedule=schedule,
                download=lambda *args:{'date':'2026-10-01'})
            self.assertEqual(len(report['failures']),2)
            self.assertFalse(list(Path(directory).rglob('*.gz')))

    def test_first_run_backfills_season_and_retries_until_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            days=[]
            def schedule(day,before):
                days.append(day)
                if day=='2026-10-02':raise OSError('not ready')
                return []
            report=run_nightly(directory,date(2026,10,31),schedule=schedule)
            self.assertEqual(days[0],'2026-10-01')
            self.assertEqual(days[-1],'2026-10-30')
            self.assertFalse(list(Path(directory).glob('backfill_*.json')))
            days.clear()
            report=run_nightly(directory,date(2026,11,1),schedule=lambda d,b:days.append(d) or [])
            self.assertEqual(days[0],'2026-10-01')
            self.assertTrue(list(Path(directory).glob('backfill_*.json')))
            days.clear()
            run_nightly(directory,date(2026,11,2),schedule=lambda d,b:days.append(d) or [])
            self.assertEqual(len(days),7)

    def test_january_uses_previous_october(self):
        with tempfile.TemporaryDirectory() as directory:
            days=[]
            run_nightly(directory,date(2027,1,2),schedule=lambda d,b:days.append(d) or [])
            self.assertEqual(days[0],'2026-10-01')
            self.assertEqual(days[-1],'2027-01-01')
