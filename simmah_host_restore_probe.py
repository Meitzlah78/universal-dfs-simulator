"""Guarded synthetic restore for a private QA deployment, never a public app route."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

MIB=1024*1024


def memory_snapshot(root=Path('/sys/fs/cgroup')):
    result={'limit_bytes':None,'current_bytes':None,'oom':None,'oom_kill':None}
    try:
        limit=(root/'memory.max').read_text().strip()
        result['limit_bytes']=int(limit) if limit!='max' else None
        result['current_bytes']=int((root/'memory.current').read_text())
        events=dict(line.split() for line in (root/'memory.events').read_text().splitlines())
        result.update(oom=int(events.get('oom',0)),oom_kill=int(events.get('oom_kill',0)))
    except (OSError,ValueError):
        return result
    return result


def preflight(snapshot, mib, disk_free):
    source=mib*MIB
    required=8*source+512*MIB  # Conservative allowance for serialization/decoding copies.
    limit,current=snapshot.get('limit_bytes'),snapshot.get('current_bytes')
    available=limit-current if limit is not None and current is not None else None
    reason=None
    if available is None:reason='A finite cgroup memory budget could not be established'
    elif available<required:reason='Insufficient memory headroom for the full test; no large payload allocated'
    elif disk_free<3*source:reason='Insufficient temporary disk space'
    return dict(passed=reason is None,reason=reason,available_memory_bytes=available,
                required_memory_headroom_bytes=required,temporary_disk_free_bytes=disk_free)


def _rss(pid):
    try:
        return next(int(line.split()[1])*1024 for line in Path(f'/proc/{pid}/status').read_text().splitlines() if line.startswith('VmRSS:'))
    except (OSError,StopIteration):
        return 0


def run_guarded(*, enabled=False, mib=511, timeout=180):
    if not enabled:
        return dict(status='disabled',reason='Enable only in a private QA deployment; no payload allocated')
    if type(mib) is not int or not 1<=mib<=511:
        raise ValueError('Source payload must be 1–511 MiB')
    if timeout<=0:raise ValueError('Positive timeout required')
    before=memory_snapshot()
    check=preflight(before,mib,shutil.disk_usage(tempfile.gettempdir()).free)
    report=dict(schema=1,source_mib=mib,preflight=check,memory_before=before,status='blocked')
    if not check['passed']:
        return report
    # A container-wide lease prevents simultaneous diagnostic subprocesses.
    with open(Path(tempfile.gettempdir())/'simmah-host-restore-probe.lock','a') as lease:
        try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            report['reason']='Another host restore probe is running';return report
        with tempfile.TemporaryDirectory(prefix='simmah-restore-qa-') as folder:
            output=Path(folder)/'report.json';log_path=Path(folder)/'worker.log'
            budget=check['available_memory_bytes']-512*MIB
            script=Path(__file__).parent/'scripts'/'benchmark_workspace_restore.py'
            env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
            start=time.monotonic();peak=0;process=None;aborted=None
            try:
                with log_path.open('w') as log:
                    process=subprocess.Popen([sys.executable,str(script),'--mib',str(mib),
                        '--additional-address-space-bytes',str(budget),'--environment','guarded host QA',
                        '--output',str(output)],stdout=log,stderr=log,env=env,start_new_session=True)
                    while process.poll() is None:
                        peak=max(peak,_rss(process.pid))
                        current=memory_snapshot()
                        remaining=(current['limit_bytes']-current['current_bytes']
                            if current['limit_bytes'] is not None and current['current_bytes'] is not None else None)
                        if time.monotonic()-start>timeout:aborted='Timeout'
                        elif remaining is None or remaining<256*MIB:aborted='Memory guard stopped the worker'
                        if aborted:
                            os.killpg(process.pid,signal.SIGTERM);break
                        time.sleep(.05)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait()
                report.update(exit_code=process.returncode,elapsed_seconds=time.monotonic()-start,
                    peak_sampled_worker_rss_bytes=peak,additional_address_space_budget=budget)
                if not aborted and process.returncode==0 and output.exists():
                    worker=json.loads(output.read_text())
                    peak_reported=worker.get('peak_process_rss_bytes',0)
                    telemetry_ok=peak>0 and peak>=.25*peak_reported
                    report.update(status='passed' if telemetry_ok else 'completed_with_telemetry_warning',
                        worker_report=worker,rss_telemetry_consistent=telemetry_ok)
                    if not telemetry_ok:
                        report['telemetry_warning']='Sampled parent-side worker RSS is much smaller than child-reported peak; memory monitoring is not verified in this environment'
                else:
                    report.update(status='failed',reason=aborted or 'Worker exited without a verified restore',
                        worker_log_tail=log_path.read_text()[-1500:])
            finally:
                if process and process.poll() is None:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
    after=memory_snapshot();report['memory_after']=after
    for key in ('oom','oom_kill'):
        if before[key] is not None and after[key] is not None:
            report[key+'_event_delta']=after[key]-before[key]
    return report
