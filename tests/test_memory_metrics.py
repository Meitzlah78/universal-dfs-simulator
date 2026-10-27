from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import os

import psutil
import simmah_memory_metrics as metrics


class MemoryMetricsTest(unittest.TestCase):
    def process(self):
        return SimpleNamespace(memory_info=lambda:SimpleNamespace(rss=20*1024**2,vms=100*1024**2),
            create_time=lambda:123.,memory_full_info=lambda:SimpleNamespace(uss=12*1024**2))

    def test_metrics_are_distinct_bytes_and_mib(self):
        with patch.object(metrics.psutil,'Process',return_value=self.process()):
            r=metrics.process_memory(999999)
        self.assertEqual(r['rss_mib'],20)
        self.assertEqual(r['vms_mib'],100)
        self.assertEqual(r['uss_mib'],12)
        self.assertEqual(r['uss_status'],'available')

    def test_permission_denied_uss_is_not_zero(self):
        p=self.process();p.memory_full_info=Mock(side_effect=psutil.AccessDenied(999999))
        with patch.object(metrics.psutil,'Process',return_value=p):
            r=metrics.process_memory(999999)
        self.assertEqual(r['rss_mib'],20)
        self.assertIsNone(r['uss_bytes'])
        self.assertIn('AccessDenied',r['uss_status'])

    def test_missing_process_preserves_unavailable_measurement(self):
        with patch.object(metrics.psutil,'Process',side_effect=psutil.NoSuchProcess(999999)):
            r=metrics.process_memory(999999)
        self.assertIsNone(r['rss_bytes'])
        self.assertEqual(r['error'],'NoSuchProcess')

    def test_hot_sampling_skips_expensive_uss_lookup(self):
        p=self.process();p.memory_full_info=Mock(side_effect=AssertionError('should not read USS'))
        with patch.object(metrics.psutil,'Process',return_value=p):
            r=metrics.process_memory(999999,include_uss=False)
        self.assertEqual(r['uss_status'],'not_requested')
        self.assertIsNone(r['uss_mib'])

    def test_self_pid_mapping_mismatch_invalidates_memory_readings(self):
        with patch.object(metrics.psutil,'Process',return_value=self.process()), \
             patch.object(metrics.Path,'read_text',return_value=f'Pid:\t{os.getpid()+1}\nVmRSS:\t20000 kB\n'):
            r=metrics.process_memory()
        self.assertIsNone(r['rss_bytes'])
        self.assertEqual(r['error'],'ProcessIdentityMismatch')
