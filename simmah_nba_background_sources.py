"""Session-isolated provider IO; no worker reads or writes Streamlit state."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic,time
from uuid import uuid4
import math

_EXECUTOR=ThreadPoolExecutor(max_workers=4,thread_name_prefix='nba-provider')
_JOBS={}
_LOCK=Lock()
_TOKEN='_slate_nba_provider_session'


def load_background_sources(state,identity,loaders,*,force=False,timeout=12):
    if not math.isfinite(timeout) or timeout<=0:raise ValueError('Positive finite refresh wait required')
    now=time();token=state.setdefault(_TOKEN,uuid4().hex);result={}
    with _LOCK:
        for key,loader in loaders.items():
            jobkey=(token,key);job=_JOBS.get(jobkey);old=state.get(key,{})
            old=old if old.get('identity')==identity else {}
            # A different slate never consumes this worker's result.
            if job and job['identity']!=identity:
                job['future'].cancel();_JOBS.pop(jobkey);job=None
            if job:
                future=job['future']
                if future.done():
                    try:
                        value=future.result()
                        if not isinstance(value,dict):raise ValueError('Invalid NBA provider response')
                        if value.get('error'):raise ValueError(value['error'])
                        record={**value,'identity':identity,'time':now}
                    except Exception as exc:record={**old,'identity':identity,'error':str(exc),'error_time':now}
                    state[key]=record;_JOBS.pop(jobkey);result[key]=record
                    continue
                if monotonic()-job['started']>=timeout:
                    future.cancel();_JOBS.pop(jobkey)
                    record={**old,'identity':identity,'error':f'Provider refresh exceeded the {timeout:g}-second wait budget','error_time':now}
                    state[key]=record;result[key]=record
                    continue
                result[key]={**old,'identity':identity,'pending':True};continue
            retry_wait=old.get('error') and 0<=now-old.get('error_time',0)<60
            fresh=not old.get('error') and 'time' in old and 0<=now-old['time']<900
            if not force and (retry_wait or fresh):result[key]=old;continue
            # Bound abandoned-session bookkeeping as well as the executor size.
            for stale_key,stale_job in list(_JOBS.items()):
                if monotonic()-stale_job['started']>60:
                    stale_job['future'].cancel();_JOBS.pop(stale_key)
            if len(_JOBS)>=64:
                result[key]={**old,'identity':identity,'error':'NBA provider refresh is busy; retry shortly','error_time':now};continue
            _JOBS[jobkey]={'identity':identity,'started':monotonic(),'future':_EXECUTOR.submit(loader)}
            result[key]={**old,'identity':identity,'pending':True}
    return result


def refresh_ready(state,timeout=12,keys=None):
    """Poll only; caller performs exactly one full rerun to apply ready results."""
    token=state.get(_TOKEN)
    with _LOCK:
        return any(k[0]==token and (keys is None or k[1] in keys) and (j['future'].done() or monotonic()-j['started']>=timeout) for k,j in _JOBS.items())


def render_refresh_status(st,pending):
    if not pending:return
    @st.fragment(run_every=1)
    def poll():
        if refresh_ready(st.session_state,keys=None if pending is True else set(pending)):st.rerun(scope='app')
        st.caption('Refreshing NBA sources in the background. Last successful data stays available until the refresh finishes.')
    poll()
