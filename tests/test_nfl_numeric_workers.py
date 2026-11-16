"""Parallel scoring must preserve every value, tie and reduction order."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_candidates import summarize_candidates
from simmah_contests import evaluate_contest
from simmah_numeric_workers import ordered_scoring_map,scoring_workers


class NumericWorkerTests(unittest.TestCase):
    def test_exact_summary_and_contest_parity_for_all_formats(self):
        rng=np.random.default_rng(875)
        outcomes=pd.DataFrame(rng.integers(-50,100,(65,40)).astype(np.float32)/10,columns=[str(i) for i in range(40)])
        for width,mult in [(6,[1.5,1,1,1,1,1]),(6,None),(9,None)]:
            slots=[str(i) for i in range(width)]
            frame=pd.DataFrame([rng.choice(outcomes.columns,width,False) for _ in range(600)],columns=slots)
            field=frame.iloc[:350].copy();before=outcomes.copy()
            summary=summarize_candidates(frame,outcomes,slots,mult,workers=1)
            for joint in (False,True):
                expected=evaluate_contest(outcomes,summary,field,slots,2000,[(1,1,100),(2,20,10),(21,800,.1)],.05,mult,joint,workers=1)
                for workers in (2,4):
                    # Force the requested worker path independent of test-host quotas.
                    with patch('simmah_numeric_workers.scoring_workers',return_value=workers):
                        actual_summary=summarize_candidates(frame,outcomes,slots,mult,workers=workers)
                        updates=[]
                        actual=evaluate_contest(outcomes,actual_summary,field,slots,2000,[(1,1,100),(2,20,10),(21,800,.1)],.05,mult,joint,
                            progress=lambda fraction,message:updates.append((fraction,threading.current_thread())),workers=workers)
                    pd.testing.assert_frame_equal(summary,actual_summary,check_exact=True)
                    pd.testing.assert_frame_equal(expected,actual,check_exact=True)
                    self.assertEqual([x[0] for x in updates],sorted(x[0] for x in updates))
                    self.assertEqual(updates[-1][0],1)
                    self.assertTrue(all(t is threading.current_thread() for _,t in updates))
            pd.testing.assert_frame_equal(outcomes,before,check_exact=True)

    def test_quota_affinity_and_memory_bound_workers(self):
        for quota,memory,expected in [('100000 100000',2*1024**3,1),('250000 100000',2*1024**3,2),('max 100000',100*1024**2,1),('max 100000',700*1024**2,2),('max 100000',2*1024**3,4)]:
            def read(path):
                return {'cpu.max':quota,'memory.max':str(memory),'memory.current':'0'}[path.name]
            with patch('simmah_numeric_workers.os.cpu_count',return_value=8),patch('simmah_numeric_workers.os.sched_getaffinity',return_value=set(range(8))),patch('simmah_numeric_workers.Path.read_text',read),patch('simmah_numeric_workers.psutil.virtual_memory',return_value=SimpleNamespace(available=8*1024**3)):
                self.assertEqual(scoring_workers(),expected)
                self.assertEqual(scoring_workers(1),1)
        for invalid in (0,5,1.5,True):
            with self.assertRaises(ValueError):scoring_workers(invalid)

    def test_legacy_cgroup_limits_and_cpu_affinity(self):
        values={'cpu.cfs_quota_us':'200000','cpu.cfs_period_us':'100000',
            'memory.limit_in_bytes':str(1024**3),'memory.usage_in_bytes':str(800*1024**2)}
        def read(path):
            if path.name not in values:raise FileNotFoundError(path)
            return values[path.name]
        with patch('simmah_numeric_workers.Path.read_text',read),patch('simmah_numeric_workers.os.cpu_count',return_value=8),patch('simmah_numeric_workers.os.sched_getaffinity',return_value=set(range(8))),patch('simmah_numeric_workers.psutil.virtual_memory',return_value=SimpleNamespace(available=8*1024**3)):
            self.assertEqual(scoring_workers(),1)
            values['memory.usage_in_bytes']='0'
            self.assertEqual(scoring_workers(),2)
            with patch('simmah_numeric_workers.os.sched_getaffinity',return_value={0}):
                self.assertEqual(scoring_workers(),1)

    def test_ordered_map_bounds_submission_and_surfaces_errors(self):
        started=threading.Event();release=threading.Event();pulled=[]
        def work(i):
            if i==0:
                started.set();release.wait(2)
            return i
        def items():
            for i in range(10):pulled.append(i);yield i
        iterator=ordered_scoring_map(work,items(),2)
        output=[]
        thread=threading.Thread(target=lambda:output.extend(iterator));thread.start()
        self.assertTrue(started.wait(2))
        # The first result is held, so later completions cannot grow the queue.
        self.assertLessEqual(len(pulled),2)
        release.set();thread.join(2)
        self.assertFalse(thread.is_alive());self.assertEqual(output,list(range(10)))
        def bad(i):raise RuntimeError('scoring failed')
        with self.assertRaisesRegex(RuntimeError,'scoring failed'):
            list(ordered_scoring_map(bad,range(4),2))

if __name__=='__main__':unittest.main()
