"""Controlled background IO tests, included in the standard unittest CI runner."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from threading import Event
from time import monotonic,time
from unittest.mock import patch
import unittest
import simmah_nba_background_sources as bg


def fail(message):raise AssertionError(message)


def finish(state,key):
    job=bg._JOBS[(state[bg._TOKEN],key)]
    job['future'].result(timeout=2)
    return bg.load_background_sources(state,'FD',{key:lambda:pytest.fail('Duplicate request')})[key]


class BackgroundSourcesTests(unittest.TestCase):
    def setUp(self):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(bg,'_JOBS',{}))
        executor=stack.enter_context(ThreadPoolExecutor(max_workers=2))
        stack.enter_context(patch.object(bg,'_EXECUTOR',executor))

    def test_slow_provider_never_blocks_page_or_duplicates_requests(self):
        gate=Event();state={};calls=[]
        def load():calls.append(1);gate.wait(2);return {'values':{'a':30}}
        try:
            started=monotonic();result=bg.load_background_sources(state,'FD',{'rw':load})
            assert monotonic()-started<.2 and result['rw']['pending']
            bg.load_background_sources(state,'FD',{'rw':load},force=True)
            assert len(bg._JOBS)==1
        finally:gate.set()
        assert finish(state,'rw')['values']=={'a':30}
        assert len(calls)==1 and not bg.refresh_ready(state)


    def test_same_slate_success_retained_while_refreshing_and_fresh_cache_skips_io(self):
        state={'rw':{'identity':'FD','time':time(),'values':{'old':22}}};gate=Event()
        assert bg.load_background_sources(state,'FD',{'rw':lambda:fail('Unexpected fetch')})['rw']['values']=={'old':22}
        try:
            record=bg.load_background_sources(state,'FD',{'rw':lambda:(gate.wait(2) or True) and {'values':{'new':31}}},force=True)['rw']
            assert record['values']=={'old':22} and record['pending']
        finally:gate.set()
        assert finish(state,'rw')['values']=={'new':31}


    def test_failed_refresh_keeps_last_good_and_backs_off(self):
        state={'rw':{'identity':'FD','time':1,'values':{'old':22}}}
        bg.load_background_sources(state,'FD',{'rw':lambda:{'error':'provider down'}})
        job=bg._JOBS[(state[bg._TOKEN],'rw')];job['future'].result(2)
        r=bg.load_background_sources(state,'FD',{'rw':lambda:fail('No retry yet')})['rw']
        assert r['error']=='provider down' and r['values']=={'old':22}
        bg.load_background_sources(state,'FD',{'rw':lambda:fail('No retry yet')})
        assert not bg._JOBS


    def test_slate_and_session_isolation_and_old_job_never_overwrites_new_pool(self):
        a={'rw':{'identity':'FD','time':1,'values':{'fd':22}}};b={};gate=Event()
        try:
            bg.load_background_sources(a,'FD',{'rw':lambda:(gate.wait(2) or True) and {'values':{'late_fd':99}}})
            result=bg.load_background_sources(a,'DK',{'rw':lambda:{'values':{'dk':30}}})
            assert 'values' not in result['rw']
            bg.load_background_sources(b,'FD',{'rw':lambda:{'values':{'other_session':3}}})
        finally:gate.set()
        job=bg._JOBS[(a[bg._TOKEN],'rw')];job['future'].result(2)
        record=bg.load_background_sources(a,'DK',{'rw':lambda:fail('Duplicate')})['rw']
        assert record['values']=={'dk':30}
        assert bg._TOKEN not in a['rw'] and a[bg._TOKEN]!=b[bg._TOKEN]


    def test_deadline_discards_late_result_and_does_not_loop(self):
        gate=Event();state={}
        try:
            bg.load_background_sources(state,'FD',{'rw':lambda:(gate.wait(2) or True) and {'values':{'late':99}}})
            job=bg._JOBS[(state[bg._TOKEN],'rw')];job['started']-=13
            assert bg.refresh_ready(state)
            r=bg.load_background_sources(state,'FD',{'rw':lambda:fail('No retry')})['rw']
            assert 'wait budget' in r['error'] and not bg.refresh_ready(state)
        finally:gate.set()
        job['future'].result(2)
        assert 'values' not in state['rw']


    def test_only_completed_jobs_trigger_poll(self):
        gate=Event();state={}
        try:
            bg.load_background_sources(state,'FD',{'rw':lambda:(gate.wait(2) or True) and {'values':{}}})
            assert not bg.refresh_ready(state)
            gate.set();bg._JOBS[(state[bg._TOKEN],'rw')]['future'].result(2)
            assert bg.refresh_ready(state)
        finally:gate.set()


    def test_poll_reruns_only_when_ready_and_stops_when_pending_clears(self):
        from types import SimpleNamespace
        reruns=[];captions=[];decorated=[];state={}
        st=SimpleNamespace(session_state=state,caption=captions.append,rerun=lambda **kw:reruns.append(kw),fragment=lambda **kw:(lambda fn:(decorated.append(fn) or fn)))
        with patch.object(bg,'refresh_ready',return_value=False):bg.render_refresh_status(st,True)
        assert not reruns and len(captions)==1
        with patch.object(bg,'refresh_ready',return_value=True):bg.render_refresh_status(st,True)
        assert reruns==[{'scope':'app'}]
        before=len(decorated);bg.render_refresh_status(st,False)
        assert len(decorated)==before


    def test_completed_obsolete_source_does_not_rerun_active_refresh(self):
        state={};gate=Event()
        try:
            bg.load_background_sources(state,'FD',{'old':lambda:{'values':{}},'active':lambda:(gate.wait(2) or True) and {'values':{}}})
            bg._JOBS[(state[bg._TOKEN],'old')]['future'].result(2)
            assert not bg.refresh_ready(state,keys={'active'})
            assert bg.refresh_ready(state,keys={'old'})
        finally:gate.set()
