"""Serial background historical fits with durable input hashes and exit gates."""
import json
import math
import io
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from simmah_input_archive import Archive, atomic_write, csv_tables, sha256

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='simmah-calibration')
_LOCK = threading.Lock()
_SCHEDULED = set()
_LIVE_BUILDS = {}
_CHILDREN = {}
_ROOT = Path(__file__).resolve().parent


def queue_jobs(archive):
    """Reruns do not duplicate jobs; heavyweight work never blocks Streamlit."""
    if builds_active():return
    for job in archive.plan():
        if job['state'] not in ('queued','running','paused_for_build'):
            continue
        identity = (str(archive.root),job['id'])
        with _LOCK:
            if identity in _SCHEDULED:
                continue
            _SCHEDULED.add(identity)
        # A stale running status after process restart is replayed into a new
        # attempt directory, preserving the previous partial logs.
        _POOL.submit(_run_guarded, archive, job, identity)


def builds_active():
    with _LOCK:
        now=time.monotonic()
        for token,started in list(_LIVE_BUILDS.items()):
            if now-started>1800:_LIVE_BUILDS.pop(token,None)
        return bool(_LIVE_BUILDS)


def _signal_children(paused):
    if not hasattr(signal,'SIGSTOP'):return
    with _LOCK:
        for pid,was_paused in list(_CHILDREN.items()):
            if paused==was_paused:continue
            try:os.killpg(pid,signal.SIGSTOP if paused else signal.SIGCONT)
            except ProcessLookupError:continue
            _CHILDREN[pid]=paused


def begin_live_build(token):
    with _LOCK:_LIVE_BUILDS[token]=time.monotonic()
    _signal_children(True)


def end_live_build(token):
    with _LOCK:_LIVE_BUILDS.pop(token,None)
    if not builds_active():_signal_children(False)


def _run_calibration_process(argv,stdout,stderr,env,timeout,archive,job):
    """Pause solver/GCC process groups while live builds own CPU on Linux.

    Paused time does not consume the timeout; allocated memory is retained.
    Other hosts only defer new jobs. A stale build lease expires in 30 minutes.
    """
    process=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,cwd=_ROOT,start_new_session=True)
    with _LOCK:_CHILDREN[process.pid]=False
    active_seconds=0.;last=time.monotonic();previous_paused=False
    try:
        while process.poll() is None:
            paused=builds_active() and hasattr(signal,'SIGSTOP')
            _signal_children(paused)
            now=time.monotonic()
            if not previous_paused:active_seconds+=now-last
            last=now
            if paused!=previous_paused:
                archive.set_job(job['id'],'paused_for_build' if paused else 'running',
                    'Calibration paused while SIM/BUILD runs; solver memory remains allocated.' if paused else 'Historical calibration resumed.')
            previous_paused=paused
            if active_seconds>timeout:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
                raise subprocess.TimeoutExpired(argv,timeout)
            threading.Event().wait(.2)
        return process
    finally:
        with _LOCK:_CHILDREN.pop(process.pid,None)
        if process.poll() is None:
            # A callback/storage error must not leave an orphaned paused
            # compiler or solver process behind.
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait()


def _run_guarded(archive, job, identity):
    try:
        run_job(archive, job)
    except Exception as error:
        archive.set_job(job['id'],'failed',f'{type(error).__name__}: {error}')
    finally:
        with _LOCK:
            _SCHEDULED.discard(identity)


def run_job(archive, job, timeout_seconds=1800):
    records = {r['digest']:r for r in archive.files()}
    salary = records[job['salary_digest']]
    contest = records[job['contest_digest']]
    # Final/live gating precedes all expensive fitting.
    audit = archive.audit(contest)
    if audit['status'] != 'audited':
        archive.set_job(job['id'],'waiting_for_final_standings',audit['detail'])
        return
    if not shutil.which('gcc'):
        archive.set_job(job['id'],'blocked_runtime','GCC/libquadmath are required; original files and standings audit are saved.')
        return
    archive.set_job(job['id'],'running','Historical KL fit in progress; live player projections are unchanged.')
    attempt = archive.root/'jobs'/job['id']/('attempt-'+str(time.time_ns()))
    sources = attempt/'sources'
    sources.mkdir(parents=True)
    raw = archive.get(salary['digest'])
    upload = sources/salary['filename']
    atomic_write(upload,raw)
    members = list(csv_tables(archive.get(contest['digest']),contest['filename']))
    if len(members) != 1:
        raise ValueError('Exactly one contest CSV required')
    member, raw_contest = members[0]
    contest_path = sources/member
    if contest_path == upload:
        raise ValueError('Salary and contest source paths collide')
    atomic_write(contest_path,raw_contest)
    meta = salary['metadata']
    nba = meta.get('mode')=='nba'
    script = 'nba_pipeline.py' if nba else ('dk_showdown_pipeline.py' if meta['platform']=='DraftKings' else 'single_game_pipeline.py')
    cap = 50000 if meta['platform']=='DraftKings' else 60000
    out = attempt/'fit'
    engine=attempt/'engine'
    shutil.copytree(_ROOT/'calibration',engine,ignore=shutil.ignore_patterns('__pycache__'))
    argv = [sys.executable,str(engine/script),'--upload',str(upload),
            '--contest',str(contest_path),'--output',str(out)]
    if not nba:argv+=['--team-a',meta['teams'][0],'--salary-cap',str(cap)]
    else:
        max_states=int(os.environ.get('SIMMAH_NBA_MAX_STATES','4000000'))
        if not 1000<=max_states<=20000000:raise ValueError('SIMMAH_NBA_MAX_STATES must be between 1000 and 20000000')
        argv+=['--max-states',str(max_states)]
    env = {**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    atomic_write(attempt/'provenance.json',json.dumps(dict(
        salary_sha256=salary['digest'],contest_sha256=contest['digest'],
        classification='RETROSPECTIVE_DIAGNOSTIC',salary_cap=cap,
        engine_sha256={p.name:sha256(p.read_bytes()) for p in engine.iterdir() if p.is_file()},
        salary_cap_source='NFL platform format rule configured in the dispatcher',
        argv=argv),indent=2).encode())
    with (attempt/'stdout.jsonl').open('w') as stdout, (attempt/'stderr.log').open('w') as stderr:
        completed = _run_calibration_process(argv,stdout,stderr,env,timeout_seconds,archive,job)
    if completed.returncode:
        budget_file=out/'budget_status.json'
        if budget_file.exists():
            status=json.loads(budget_file.read_text())
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as bundle:
                for path in attempt.rglob('*'):
                    if path.is_file() and path.suffix not in ('.bin','.pyc') and path.name!='quad_optimizer':
                        bundle.write(path,path.relative_to(attempt))
            packed=buf.getvalue();atomic_write(archive.root/'jobs'/job['id']/'result.zip',packed)
            archive.put(packed,'calibration-'+job['id'][:12]+'.zip',metadata=dict(kind='calibration_report',job_id=job['id'],status=status['status']))
            archive.set_job(job['id'],status['status'],status['reason'])
            return
        raise RuntimeError('Calibration process failed; separate attempt logs retained. Exit '+str(completed.returncode))
    result = json.loads((out/'results.json').read_text())
    # Independent acceptance is based on original units, not SciPy success.
    final = result.get('final_float64',{})
    def gates(metrics):
        bounds={'raw_gradient_max':1e-9,'original_residual_max':1e-8,'normalization_error':1e-12}
        return all(k in metrics and math.isfinite(float(metrics[k])) and 0<=float(metrics[k])<=limit
                   for k,limit in bounds.items())
    accepted = (result.get('status') == 'verified_convergence' and gates(final)
                and gates(result.get('quad',{}).get('fresh_binary128',{})))
    summary = dict(status='verified_convergence' if accepted else 'stopped_without_verified_convergence',
                   final_float64=final,scope=result.get('scope'),
                   roster_concentration=result.get('roster_concentration'))
    atomic_write(archive.root/'jobs'/job['id']/'summary.json',json.dumps(summary,indent=2).encode())
    packed = out.with_suffix('.zip').read_bytes()
    target = archive.root/'jobs'/job['id']/'result.zip'
    atomic_write(target,packed)
    # Reports receive the same browser/cloud retention as original inputs.
    try:
        archive.put(packed,'calibration-'+job['id'][:12]+'.zip',
                    metadata=dict(kind='calibration_report',job_id=job['id'],status=summary['status']))
        if archive.backup:
            archive.backup.put(archive.owner,'calibrations/'+job['id']+'.zip',packed)
    except Exception as error:
        # Numerical acceptance and backup health are separate facts.
        summary['backup_warning'] = str(error)
        atomic_write(archive.root/'jobs'/job['id']/'summary.json',json.dumps(summary,indent=2).encode())
    assert sha256(archive.get(salary['digest'])) == salary['digest']
    assert sha256(archive.get(contest['digest'])) == contest['digest']
    archive.set_job(job['id'],summary['status'],json.dumps(summary))
