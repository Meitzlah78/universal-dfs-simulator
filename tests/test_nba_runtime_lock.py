"""Isolate real imports/reloads so stress tests cannot disturb other test modules."""
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

class RuntimeLockTests(unittest.TestCase):
    def run_python(self,code):
        result=subprocess.run([sys.executable,'-c',textwrap.dedent(code)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result.stdout

    def test_held_lock_and_activation_state_survive_reload(self):
        self.run_python('''
            import importlib,threading
            from concurrent.futures import ThreadPoolExecutor
            import simmah_runtime_release as release
            anchor=release._lock
            release._active_release='preserved'
            release._active_role_ownership_release='roles'
            release._active_role_ownership_fingerprint=('fingerprint',)
            entered=threading.Event();acquired=threading.Event()
            def contender():
                entered.set()
                with release._lock:acquired.set()
            with ThreadPoolExecutor(max_workers=1) as pool:
                with anchor:
                    pending=pool.submit(contender)
                    assert entered.wait(2)
                    importlib.reload(release)
                    assert release._lock is anchor
                    assert release._active_release=='preserved'
                    assert release._active_role_ownership_release=='roles'
                    assert release._active_role_ownership_fingerprint==('fingerprint',)
                    assert not acquired.wait(.02),'contender bypassed lock during reload'
                pending.result(timeout=2)
                assert acquired.is_set()
        ''')

    def test_module_eviction_rebinds_same_process_anchor(self):
        self.run_python('''
            import importlib,sys
            import simmah_runtime_release as first
            lock=first._lock
            with lock:
                sys.modules.pop('simmah_runtime_release')
                second=importlib.import_module('simmah_runtime_release')
                assert second is not first
                assert second._lock is lock
                assert second._active_release is None
        ''')

    def test_first_upgrade_adopts_legacy_lock_before_reload(self):
        self.run_python('''
            import importlib,sys,threading,types
            from pathlib import Path
            from concurrent.futures import ThreadPoolExecutor
            legacy=types.ModuleType('simmah_runtime_release')
            legacy._lock=threading.RLock()
            sys.modules['simmah_runtime_release']=legacy
            sys.__dict__.pop('_simmah_runtime_release_lock',None)
            original=legacy._lock
            source=Path('dfs_app.py').read_text()
            start=source.index('import importlib\\nimport sys\\nimport threading\\n')
            end=source.index("\\nif st.query_params.get('simmah_qa')",start)
            code=compile(source[start:end],'upgrade_entrypoint','exec')
            started=threading.Event();reloading=threading.Event()
            real_reload=importlib.reload
            def tracked(module):
                reloading.set();return real_reload(module)
            importlib.reload=tracked
            def worker():
                started.set();namespace={};exec(code,namespace)
                assert namespace['_release_lock'] is original
                assert namespace['runtime_release']._lock is original
            with ThreadPoolExecutor(max_workers=1) as pool:
                with original:
                    pending=pool.submit(worker)
                    assert started.wait(2)
                    assert not reloading.wait(.02),'upgrade bypassed a held legacy lock'
                pending.result(timeout=5)
            assert reloading.is_set()
        ''')

    def test_eight_threads_serialize_240_real_entrypoint_reloads(self):
        output=self.run_python('''
            import importlib,threading,time
            from pathlib import Path
            from concurrent.futures import ThreadPoolExecutor
            text=Path('dfs_app.py').read_text()
            start=text.index('import importlib\\nimport sys\\nimport threading\\n')
            end=text.index("\\nif st.query_params.get('simmah_qa')",start)
            block=text[start:end].replace('if (getattr','if (True or getattr',1)
            code=compile(block,'release_entrypoint','exec')
            real_reload=importlib.reload
            counter_lock=threading.Lock();barrier=threading.Barrier(8)
            active=peak=calls=0;locks=set()
            def tracked(module):
                global active,peak,calls
                if module.__name__!='simmah_runtime_release':return real_reload(module)
                with counter_lock:
                    active+=1;peak=max(peak,active);calls+=1
                try:
                    time.sleep(.001)
                    return real_reload(module)
                finally:
                    with counter_lock:active-=1
            importlib.reload=tracked
            def worker():
                barrier.wait(timeout=5)
                for _ in range(30):
                    namespace={};exec(code,namespace)
                    release=namespace['runtime_release']
                    assert namespace['_release_lock'] is release._lock
                    with counter_lock:locks.add(id(release._lock))
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures=[pool.submit(worker) for _ in range(8)]
                for future in futures:future.result(timeout=20)
            assert calls==240,calls
            assert peak==1,peak
            assert len(locks)==1,locks
            print('240 reloads; 8 threads; 1 lock; peak simultaneous reloads=1')
        ''')
        self.assertIn('peak simultaneous reloads=1',output)
