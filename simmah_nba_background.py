"""Process-local, bounded jobs. Workers never access Streamlit or session state."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock
from time import time
from uuid import uuid4

_lock = Lock()
_jobs = {}
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='nba-build')


def peek(key):
    with _lock:
        job = _jobs.get(key)
        return dict(job) if job else None


def release(key, job_id):
    with _lock:
        job = _jobs.get(key)
        if job and job['id'] == job_id and job['status'] != 'running':
            del _jobs[key]


def start(key, snapshot, compute):
    # No unbounded queue of large frozen pools; one heavy build per process.
    with _lock:
        if any(j['status'] == 'running' for j in _jobs.values()):
            raise RuntimeError('Another NBA build is running. Previous lineups remain available; retry when it finishes.')
        if key in _jobs:
            raise RuntimeError('Review the completed replacement before starting another build.')
        if len(_jobs) >= 8:
            raise RuntimeError('Completed builds await review in other workspaces. Review them before starting another build.')
        frozen = deepcopy(snapshot)
        job = {'id': uuid4().hex, 'status': 'running', 'stage': 'Starting',
               'started': time(), 'result': None, 'error': None}
        _jobs[key] = job

    def progress(stage):
        with _lock:
            job['stage'] = str(stage)

    def worker():
        try:
            result = compute(frozen, progress)
            with _lock:
                job.update(result=result, status='ready', finished=time())
        except Exception as exc:
            with _lock:
                job.update(error=str(exc), failure=exc, status='failed', finished=time())
    try:
        _executor.submit(worker)
    except Exception:
        with _lock:
            _jobs.pop(key, None)
        raise
    return peek(key)


def compute_nba(snapshot, progress):
    from simmah_nba_pregame import PregameEngine
    from simmah_nba_engine import EventRates
    from simmah_nba_simulation_cache import CachedNBAOutcomes
    from simmah_nba_pipeline import run_pipeline, export_portfolio
    from time import perf_counter
    started = perf_counter()
    pool = snapshot['pool']
    engine = CachedNBAOutcomes(PregameEngine(pool, snapshot['markets'],
        EventRates(**snapshot['rates']), platform=snapshot['platform']))
    built = run_pipeline(pool, engine, snapshot['weights'], snapshot['source'],
        snapshot['payouts'], snapshot['entry_fee'], snapshot['count'],
        progress=progress, **snapshot['kwargs'])
    progress('Validating replacement export')
    export_portfolio(snapshot['entries'], snapshot['cid'], pool, built,
                     salary_min=snapshot['kwargs']['salary_min'])
    built['build_total_seconds'] = perf_counter() - started
    return {'identity': snapshot['identity'], 'result': built, 'pool': pool,
            'contest_id': snapshot['cid'], 'engine_reports': engine.last_report,
            'rotation_reconciliation': engine.rotation_reconciliation,
            'started_at': snapshot['started_at'],
            'engine_metadata': {'rates': vars(engine.rates), 'max_overtimes': engine.max_overtimes,
                'rotation_reconciliation': engine.rotation_reconciliation,
                'simulation_identity': engine.identity}}
