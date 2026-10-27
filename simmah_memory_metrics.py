"""Comparable process snapshots; not Python-heap or leak measurements."""
import os
from pathlib import Path
import time

try:
    import psutil
except ImportError:
    psutil=None


def process_memory(pid=None, *, include_uss=True):
    pid=os.getpid() if pid is None else int(pid)
    result=dict(pid=pid,sampled_at_monotonic=time.monotonic(),source='psutil',
                rss_bytes=None,vms_bytes=None,uss_bytes=None,rss_mib=None,vms_mib=None,uss_mib=None,uss_status='not_requested',
                process_created_at=None,proc_status_rss_bytes=None,proc_status_hwm_bytes=None)
    if psutil is None:
        result.update(error='psutil unavailable',uss_status='unavailable')
        return result
    try:
        process=psutil.Process(pid)
        info=process.memory_info()
        result.update(rss_bytes=int(info.rss),vms_bytes=int(info.vms),process_created_at=process.create_time())
        if include_uss:
            try:
                uss=getattr(process.memory_full_info(),'uss',None)
                result.update(uss_bytes=int(uss) if uss is not None else None,
                              uss_status='available' if uss is not None else 'unsupported')
            except (psutil.Error,OSError) as exc:
                result['uss_status']='unavailable: '+type(exc).__name__
    except (psutil.Error,OSError) as exc:
        result.update(error=type(exc).__name__,uss_status='unavailable')
    try:
        rows=dict((line.split(':',1)[0],line.split(':',1)[1].strip())
                  for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
        for key,field in [('VmRSS','proc_status_rss_bytes'),('VmHWM','proc_status_hwm_bytes')]:
            if key in rows:result[field]=int(rows[key].split()[0])*1024
    except (OSError,ValueError):
        pass
    if pid==os.getpid():
        try:
            own_rows=Path('/proc/self/status').read_text().splitlines()
            proc_pid=next(int(line.split()[1]) for line in own_rows if line.startswith('Pid:'))
            result['proc_self_pid']=proc_pid
            if proc_pid!=pid:
                result.update(rss_bytes=None,vms_bytes=None,uss_bytes=None,
                              error='ProcessIdentityMismatch',uss_status='unavailable')
        except (OSError,ValueError,StopIteration):
            pass
    for field in ('rss','vms','uss'):
        value=result[field+'_bytes']
        result[field+'_mib']=value/(1024**2) if value is not None else None
    return result
