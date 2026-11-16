"""Bounded threads for deterministic NumPy/SciPy scoring, never random draws."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import psutil


def scoring_workers(requested=None):
    """Respect CPU affinity/quota and memory; small hosts keep one worker."""
    if requested is not None and (isinstance(requested,bool) or not isinstance(requested,int) or not 1<=requested<=4):
        raise ValueError('Scoring workers must be an integer from 1 to 4')
    count=getattr(os,'process_cpu_count',os.cpu_count)() or 1
    try:count=min(count,len(os.sched_getaffinity(0)))
    except (AttributeError,OSError):pass
    try:
        quota,period=Path('/sys/fs/cgroup/cpu.max').read_text().split()
        if quota!='max':count=min(count,max(1,int(quota)//int(period)))
    except (OSError,ValueError,ZeroDivisionError):
        try:
            root=Path('/sys/fs/cgroup/cpu')
            quota=int((root/'cpu.cfs_quota_us').read_text())
            period=int((root/'cpu.cfs_period_us').read_text())
            if quota>0:count=min(count,max(1,quota//period))
        except (OSError,ValueError,ZeroDivisionError):pass
    # Each scoring task owns only one bounded batch, but leave headroom for
    # the simulations, solver, and Streamlit session already resident in RAM.
    try:available=psutil.virtual_memory().available
    except Exception:return 1
    try:
        limit=Path('/sys/fs/cgroup/memory.max').read_text().strip()
        if limit!='max':
            used=int(Path('/sys/fs/cgroup/memory.current').read_text())
            available=min(available,max(0,int(limit)-used))
    except (OSError,ValueError):
        try:
            root=Path('/sys/fs/cgroup/memory')
            limit=int((root/'memory.limit_in_bytes').read_text())
            used=int((root/'memory.usage_in_bytes').read_text())
            available=min(available,max(0,limit-used))
        except (OSError,ValueError):pass
    ceiling=4 if available>=1024**3 else 2 if available>=512*1024**2 else 1
    return max(1,min(count,ceiling,requested or 4))


def ordered_scoring_map(function,items,workers):
    """At most workers batches in flight; yield in original reduction order."""
    if workers==1:
        yield from map(function,items)
        return
    items=iter(items)
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='nfl-scoring') as executor:
        pending=deque()
        for _ in range(workers):
            try:pending.append(executor.submit(function,next(items)))
            except StopIteration:break
        while pending:
            yield pending.popleft().result()
            try:pending.append(executor.submit(function,next(items)))
            except StopIteration:pass
