"""Bounded process workers for independent games; no Streamlit in workers."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from multiprocessing import get_context
from pathlib import Path
from threading import Lock
import math
import os
import numpy as np

_executor=None
_executor_lock=Lock()


def worker_count():
    count=(getattr(os,'process_cpu_count',os.cpu_count)() or 1)
    try:
        quota,period=Path('/sys/fs/cgroup/cpu.max').read_text().split()
        if quota!='max':count=min(count,max(1,math.ceil(int(quota)/int(period))))
    except (OSError,ValueError,ZeroDivisionError):pass
    return min(2,count)


def _pool():
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor=ProcessPoolExecutor(max_workers=worker_count(),mp_context=get_context('spawn'))
        return _executor


def shutdown_workers():
    global _executor
    with _executor_lock:
        if _executor is not None:_executor.shutdown(wait=True,cancel_futures=True)
        _executor=None


def simulate_one_game(payload):
    from simmah_nba_pregame import PregameEngine
    pool,market,rates,max_overtimes,platform,index,n,seed,prepared=payload
    engine=PregameEngine(pool,[market],rates,max_overtimes=max_overtimes,
                         platform=platform,parallel=False,game_index_offset=index)
    if prepared is not None:engine.prepared[index]=prepared
    scores=engine(n,seed)
    return scores,engine.prepared[index],engine.last_report[0]


def simulate_parallel(engine,n,seed):
    from simmah_nba_projections import team_key
    output=np.zeros((n,len(engine.pool)),np.float32);reports=[None]*len(engine.games)
    jobs={}
    for local_index,(market,_) in enumerate(engine.games):
        index=local_index+engine.game_index_offset
        teams=set(map(team_key,market['teams']))
        ids=np.flatnonzero(engine.pool['Team'].map(team_key).isin(teams).to_numpy())
        pool=engine.pool.iloc[ids].reset_index(drop=True)
        payload=(pool,market,engine.rates,engine.max_overtimes,engine.platform,index,n,seed,engine.prepared.get(index))
        jobs[_pool().submit(simulate_one_game,payload)]=(local_index,index,ids)
    completed=0
    try:
        for future in as_completed(jobs):
            local_index,index,ids=jobs[future]
            scores,prepared,report=future.result()
            output[:,ids]=scores;engine.prepared[index]=prepared;reports[local_index]=report
            completed+=1
            if engine.progress:engine.progress(f'Simulating NBA games {completed}/{len(jobs)} complete')
    except Exception:
        for future in jobs:future.cancel()
        raise
    engine.last_report=reports
    return output
