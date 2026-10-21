"""Nonblocking shared public lineup-page IO; workers never touch Streamlit."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time


class LineupPageCache:
    def __init__(self,fetch,ttl=60):
        self.fetch=fetch;self.ttl=ttl;self.records={};self.lock=Lock()
        self.executor=ThreadPoolExecutor(max_workers=2)

    def get(self,day,*,force=False):
        with self.lock:
            record=self.records.setdefault(day,{})
            future=record.get('future')
            if future is not None and future.done():
                try:record['result']=future.result()
                except Exception as exc:record['result']={'error':str(exc),'checked_at':time.time()}
                if record['result'].get('html') and not record['result'].get('error'):
                    record['last_success']=record['result']
                record['completed_at']=time.monotonic();record.pop('future',None)
                future=None
            result=record.get('result')
            expired=time.monotonic()-record.get('completed_at',-float('inf'))>=self.ttl
            if future is None and (force or result is None or expired):
                record['future']=self.executor.submit(self.fetch,day)
                future=record['future']
            pending=future is not None
            if result is None:return {'pending':pending}
            if result.get('error') and record.get('last_success'):
                return {**record['last_success'],'pending':pending,'stale':True,'issue':result['error']}
            return {**result,'pending':pending}
