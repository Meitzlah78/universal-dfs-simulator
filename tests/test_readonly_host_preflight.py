import unittest
from unittest.mock import patch
from simmah_storage_probe import read_only_host_preflight


class ReadOnlyPreflightTest(unittest.TestCase):
    def test_probe_reports_visibility_and_never_spawns_worker(self):
        with patch('simmah_host_restore_probe.subprocess.Popen') as spawn, \
             patch('simmah_host_restore_probe.memory_snapshot',return_value=dict(limit_bytes=8*1024**3,current_bytes=0)), \
             patch('simmah_memory_metrics.process_memory',return_value={'rss_bytes':10000000,'uss_bytes':None}):
            report=read_only_host_preflight()
        self.assertTrue(report['preflight']['process_monitor_available'])
        self.assertFalse(report['heavy_test_executed'])
        self.assertFalse(report['worker_visibility_verified'])
        spawn.assert_not_called()

    def test_unavailable_rss_blocks_without_fabricating_zero(self):
        with patch('simmah_host_restore_probe.memory_snapshot',return_value=dict(limit_bytes=8*1024**3,current_bytes=0)), \
             patch('simmah_memory_metrics.process_memory',return_value={'rss_bytes':None,'error':'NoSuchProcess'}):
            report=read_only_host_preflight()
        self.assertFalse(report['preflight']['passed'])
        self.assertIsNone(report['process_memory']['rss_bytes'])
