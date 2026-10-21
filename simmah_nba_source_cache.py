"""Fetch independent NBA providers concurrently; briefly cache failures too."""
from concurrent.futures import ThreadPoolExecutor
import time


def load_sources(state, identity, loaders, *, force=False, now=None):
    now=time.time() if now is None else float(now)
    result={};pending={}
    for key,loader in loaders.items():
        old=state.get(key,{})
        same=old.get('identity')==identity
        retry_wait=same and old.get('error') and 0<=now-old.get('error_time',0)<60
        fresh=same and not old.get('error') and 0<=now-old.get('time',0)<900
        if not force and (retry_wait or fresh):result[key]=old
        else:pending[key]=(loader,old if same else {})
    if pending:
        # Workers only perform provider IO. Session state and Streamlit calls
        # stay on the calling thread.
        with ThreadPoolExecutor(max_workers=len(pending)) as executor:
            jobs={key:executor.submit(loader) for key,(loader,_) in pending.items()}
            for key,job in jobs.items():
                old=pending[key][1]
                try:
                    result[key]={**job.result(),'identity':identity,'time':now}
                except Exception as exc:
                    result[key]={**old,'identity':identity,'error':str(exc),'error_time':now}
                state[key]=result[key]
    return result
