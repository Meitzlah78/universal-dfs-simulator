import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from simmah_host_restore_probe import MIB, memory_snapshot, preflight, run_guarded


class HostProbeTest(unittest.TestCase):
    def test_cgroup_snapshot_and_unknown_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'memory.max').write_text(str(1024*MIB))
            (root/'memory.current').write_text(str(100*MIB))
            (root/'memory.events').write_text('oom 2\noom_kill 1\n')
            self.assertEqual(memory_snapshot(root)['oom_kill'],1)
            (root/'memory.max').write_text('max')
            self.assertFalse(preflight(memory_snapshot(root),511,10**12)['passed'])

    def test_low_memory_low_disk_and_unknown_budget_block(self):
        snapshot=dict(limit_bytes=1024*MIB,current_bytes=100*MIB)
        self.assertFalse(preflight(snapshot,511,10**12)['passed'])
        self.assertFalse(preflight(dict(limit_bytes=8*1024*MIB,current_bytes=0),511,1)['passed'])
        self.assertFalse(preflight(dict(limit_bytes=None,current_bytes=None),511,10**12)['passed'])
        self.assertTrue(preflight(dict(limit_bytes=8*1024*MIB,current_bytes=0),511,10**12)['passed'])

    def test_disabled_or_blocked_run_never_spawns(self):
        with patch('simmah_host_restore_probe.subprocess.Popen') as spawn:
            self.assertEqual(run_guarded()['status'],'disabled')
            with patch('simmah_host_restore_probe.memory_snapshot',return_value=dict(limit_bytes=1024*MIB,current_bytes=100*MIB)):
                self.assertEqual(run_guarded(enabled=True)['status'],'blocked')
            spawn.assert_not_called()

    def test_real_small_worker_round_trip_reports_memory_and_exact_equality(self):
        report=run_guarded(enabled=True,mib=1,timeout=30)
        if report['status']=='blocked':self.skipTest('Executor has insufficient bounded cgroup resources')
        self.assertIn(report['status'],('passed','completed_with_telemetry_warning'),report)
        self.assertTrue(report['worker_report']['exact_full_array_equal'])
        self.assertGreater(report['worker_report']['peak_process_rss_bytes'],0)
        self.assertEqual(report['oom_kill_event_delta'],0)
