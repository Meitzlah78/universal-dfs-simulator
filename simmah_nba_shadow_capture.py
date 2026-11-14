"""Opt-in NBA receipts and pre-simulation freeze. No live forecast mutations."""
from collections import OrderedDict,Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

_LOCK=threading.Lock()
_RECEIPTS=OrderedDict()
_HEALTH=Counter()
_EXECUTOR=None
_PENDING=threading.BoundedSemaphore(2)
_MAX_RAW=16*1024*1024
_MAX_STORE=128*1024*1024


def enabled():
    return os.environ.get('SIMMAH_NBA_SHADOW_CAPTURE','').strip()=='1'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _event(kind):
    with _LOCK:_HEALTH[kind]+=1


def remember_response(source,raw):
    """Best-effort bounded receipt, at actual existing fetch completion."""
    if not enabled():return
    try:
        raw=raw.encode() if isinstance(raw,str) else bytes(raw)
        if len(raw)>_MAX_RAW:
            _event('source_too_large');return
        receipt={'source':str(source),'observed_at':_now(),'sha256':hashlib.sha256(raw).hexdigest(),'raw':raw}
        with _LOCK:
            _RECEIPTS.pop(str(source),None);_RECEIPTS[str(source)]=receipt
            while len(_RECEIPTS)>64 or sum(len(r['raw']) for r in _RECEIPTS.values())>_MAX_RAW:
                _RECEIPTS.popitem(last=False)
            _HEALTH['source_receipts']+=1
    except Exception:_event('source_capture_failed')


def read_json_response(response,source):
    if not enabled():return json.load(response)
    raw=response.read()
    remember_response(source,raw)
    return json.loads(raw)


def read_text_response(response,source):
    raw=response.read()
    remember_response(source,raw)
    return raw.decode('utf-8')


def health():
    with _LOCK:
        result=dict(_HEALTH,enabled=enabled(),receipt_sources=len(_RECEIPTS))
    attempts=result.get('capture_attempts',0)
    result['persisted_per_attempt']=result.get('captures_persisted',0)/attempts if attempts else None
    result['certified_pools']=0  # No certified eligibility/role adapter is connected.
    return result


def _directory():
    return Path(os.environ.get('SIMMAH_NBA_SHADOW_DIRECTORY',str(Path(__file__).parent/'data'/'nba_shadow')))


def _freeze(source_pool,prepared_pool,settings,model):
    # Freeze at the real build boundary, before asynchronous persistence.
    with _LOCK:
        at=_now();receipts=[dict(r) for r in _RECEIPTS.values()]
    version={}
    for name in ('simmah_nba_pipeline.py','simmah_nba_pregame.py','simmah_nba_engine.py','simmah_nba_shadow_worker.py'):
        version[name]=hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
    capture={'schema_version':1,'mode':'shadow','capture_id':uuid.uuid4().hex,'frozen_at':at,
        'source_pool':json.loads(source_pool.to_json(orient='split',date_format='iso',double_precision=15)),
        'prepared_pool':json.loads(prepared_pool.to_json(orient='split',date_format='iso',double_precision=15)),
        'settings':settings,'model':model,'model_source_hashes':version,
        'baseline_forecasts':json.loads(prepared_pool[[c for c in ('Player ID','Name','Team','Opponent','Projection','Projected Minutes','Game Start','Injury Status','Eligible') if c in prepared_pool]].to_json(orient='records',date_format='iso',double_precision=15)),
        'role_priors':None,'bounds':None,
        'input_status':'uncertified_pool',
        'warnings':['DFS pool is not certified full team/game membership','Independent point-in-time role priors and bounds are not connected','Observed source cache is not yet a certified per-player transformation lineage'],
        'receipts':[{**{k:v for k,v in r.items() if k!='raw'},'raw_file':r['sha256']+'.response.gz'} for r in receipts]}
    if not receipts:capture['warnings'].append('No upstream raw receipts were observed in this process')
    # Serialization here detaches all mutable caller references before queueing.
    frozen=json.dumps(capture,sort_keys=True,allow_nan=False).encode()
    return frozen,receipts,capture['capture_id']


def _persist_and_run(frozen,receipts,capture_id):
    root=_directory();root.mkdir(parents=True,exist_ok=True)
    incoming=len(frozen)+sum(len(r['raw']) for r in receipts)
    if sum(p.stat().st_size for p in root.iterdir() if p.is_file())+incoming>_MAX_STORE:
        raise ValueError('shadow_storage_limit')
    for receipt in receipts:
        path=root/(receipt['sha256']+'.response.gz')
        try:
            with path.open('xb') as f:f.write(gzip.compress(receipt['raw'],mtime=0))
        except FileExistsError:
            if hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()!=receipt['sha256']:
                raise ValueError('shadow_receipt_corrupt')
    path=root/(capture_id+'.capture.json')
    with path.open('xb') as f:f.write(frozen)
    _event('captures_persisted')
    # Separate process; no Streamlit state, shared engine, RNG or live arrays.
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('simmah_nba_shadow_worker.py')),str(path)],
        timeout=20,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    if result.returncode:raise ValueError('shadow_worker_failed')
    _event('uncertified_pool')


def _failure(capture_id,reason):
    _event(reason)
    try:
        root=_directory();root.mkdir(parents=True,exist_ok=True)
        event={'capture_id':capture_id,'at':_now(),'event':'shadow_failure','reason':reason,'production_modified':False}
        with (root/(capture_id+'.failure.json')).open('x') as f:json.dump(event,f)
    except Exception:_event('failure_log_unavailable')


def _background(frozen,receipts,capture_id):
    try:_persist_and_run(frozen,receipts,capture_id)
    except subprocess.TimeoutExpired:_failure(capture_id,'worker_timeout')
    except Exception:_failure(capture_id,'capture_or_worker_failed')
    finally:_PENDING.release()


def begin_build_capture(source_pool,prepared_pool,*,settings,model):
    """Fail-open, no network, bounded queue. Returns capture ID or None."""
    global _EXECUTOR
    if not enabled():return None
    _event('capture_attempts')
    if not _PENDING.acquire(blocking=False):
        _event('queue_full');return None
    try:
        frozen,receipts,capture_id=_freeze(source_pool,prepared_pool,settings,model)
        with _LOCK:
            if _EXECUTOR is None:_EXECUTOR=ThreadPoolExecutor(max_workers=1,thread_name_prefix='nba-shadow')
            executor=_EXECUTOR
        executor.submit(_background,frozen,receipts,capture_id)
        _event('captures_queued')
        return capture_id
    except Exception:
        _PENDING.release();_event('freeze_or_submit_failed');return None
