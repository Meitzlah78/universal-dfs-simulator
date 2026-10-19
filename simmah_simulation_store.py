"""Persistent, content-addressed simulation preparation, independent of Streamlit.

Prepare two separate seeded PBP samples once. Reuse only validated, exact-input
matches. Fitting is cached separately so changing simulation seeds/counts does
not rerun the projection fitter. No pickle, network, outcome scaling or UI calls.
"""
import hashlib
import io
import json
import os
from pathlib import Path
from contextlib import contextmanager
import time
import uuid

import numpy as np
import pandas as pd
from simmah_nfl_engine import simulate_stat_lines
from simmah_nfl_scoring import score_nfl_stat_line
from simmah_projection_inputs import fit_projection_inputs
from simmah_qb_roles import quarterback_conflicts

SCHEMA=1


class CacheIntegrityError(ValueError):
    pass


def _json(value):
    def default(item):
        if isinstance(item,np.generic):return item.item()
        raise TypeError('Unsupported simulation input type: '+type(item).__name__)
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=default).encode()


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _model_digest():
    root=Path(__file__).parent
    names=['simmah_simulation_store.py','simmah_nfl_engine.py','simmah_projection_inputs.py',
           'simmah_nfl_scoring.py','simmah_weather.py','simmah_qb_roles.py']
    return _hash(_json({name:_hash((root/name).read_bytes()) for name in names}))


def _atomic_write(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_bytes(raw)
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def _cache_lock(path):
    # Deployment workers share a filesystem; only one may prepare a key at a time.
    # Use a process lock, released by the OS if a worker exits unexpectedly.
    import fcntl
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def _fit(pool,roles,platform,root,key,pilot_n,iterations,progress):
    path=root/'fits'/(key+'.json')
    with _cache_lock(root/'locks'/('fit-'+key+'.lock')):
        if path.exists():
            try:
                envelope=json.loads(path.read_bytes());payload=envelope['payload']
                if payload['key']!=key or _hash(_json(payload))!=envelope['sha256']:
                    raise CacheIntegrityError('Projection-fit cache checksum mismatch')
                report=pd.DataFrame(**payload['report'])
                return payload['parameters'],report,True
            except (KeyError,TypeError,json.JSONDecodeError) as exc:
                raise CacheIntegrityError('Unreadable projection-fit cache') from exc
        parameters,report=fit_projection_inputs(pool,roles,platform,score_nfl_stat_line,
            pilot_n=pilot_n,iterations=iterations,progress=progress)
        payload={'key':key,'parameters':parameters,
                 'report':report.astype(object).where(pd.notna(report),None).to_dict(orient='split')}
        _atomic_write(path,_json({'payload':payload,'sha256':_hash(_json(payload))}))
        return parameters,report,False


def _read_prepared(directory,key,names,count):
    manifest_path=directory/'manifest.json'
    if not manifest_path.exists():return None
    try:
        manifest=json.loads(manifest_path.read_bytes())
        if manifest['key']!=key or manifest['schema']!=SCHEMA:
            raise CacheIntegrityError('Simulation manifest key mismatch')
        raw=(directory/'outcomes.npz').read_bytes()
        if _hash(raw)!=manifest['outcomes_sha256']:
            raise CacheIntegrityError('Simulation outcomes checksum mismatch')
        with np.load(io.BytesIO(raw),allow_pickle=False) as archive:
            if archive['names'].tolist()!=names:raise CacheIntegrityError('Cached player names differ')
            result={}
            for kind in ['evaluation','construction']:
                matrix=archive[kind]
                if matrix.shape!=(count,len(names)) or not np.isfinite(matrix).all():
                    raise CacheIntegrityError('Invalid cached '+kind+' matrix')
                result[kind]=pd.DataFrame(matrix,columns=names)
        report_raw=(directory/'fit_report.json').read_bytes()
        if _hash(report_raw)!=manifest['fit_report_sha256']:
            raise CacheIntegrityError('Fit-report checksum mismatch')
        result['fit_report']=pd.DataFrame(**json.loads(report_raw))
        return result
    except CacheIntegrityError:
        raise
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise CacheIntegrityError('Incomplete or unreadable prepared simulation bundle') from exc


def prepare_simulations(pool,roles,platform,cache_root,count=10000,correlation_strength=1.,
                        weather_by_team=None,evaluation_seed=530001,construction_seed=530002,
                        pilot_n=1024,iterations=8,progress=None):
    """Return two DataFrames, fit report and timings. No candidate/field work here.

    Confirm QB roles before this call. Input row order is part of the key because
    it affects RNG consumption. History and weather must be supplied snapshots;
    this layer never fetches today's data during a replay.
    """
    started=time.perf_counter();count=int(count)
    if count<1 or int(pilot_n)<1 or int(iterations)<0:raise ValueError('Invalid simulation counts')
    if evaluation_seed==construction_seed:raise ValueError('Construction and evaluation require distinct seeds')
    if not np.isfinite(correlation_strength) or not 0<=correlation_strength<=1:
        raise ValueError('Invalid correlation strength')
    if platform not in {'DraftKings','FanDuel'}:raise ValueError('Unknown scoring platform')
    if not isinstance(roles,dict) or any(not isinstance(value,dict) for value in roles.values()):
        raise ValueError('Historical roles must be a player-to-metrics mapping')
    columns=['Name','Team','Opponent','Position','Projection']
    if not set(columns)<=set(pool):raise ValueError('Missing simulation input columns')
    inputs=pool[columns].copy()
    if inputs.Name.isna().any() or inputs.Name.duplicated().any():raise ValueError('Player names must be unique')
    for column in ['Name','Team','Opponent','Position']:
        if inputs[column].isna().any() or inputs[column].astype(str).str.strip().eq('').any():
            raise ValueError('Missing '+column)
        inputs[column]=inputs[column].astype(str)
    inputs['Projection']=pd.to_numeric(inputs.Projection,errors='coerce')
    if not len(inputs) or not np.isfinite(inputs.Projection).all() or inputs.Projection.le(0).any():
        raise ValueError('Positive external projections are required')
    conflicts=quarterback_conflicts(inputs)
    if conflicts:raise ValueError('Confirm starting quarterbacks before preparing simulations: '+str(conflicts))
    root=Path(cache_root);names=inputs.Name.tolist();weather_by_team=weather_by_team or {}
    fit_spec={'schema':SCHEMA,'model_digest':_model_digest(),'players':inputs.to_dict('records'),
              'roles':roles,'platform':platform,'pilot_n':pilot_n,'iterations':iterations}
    fit_key=_hash(_json(fit_spec))
    spec={'schema':SCHEMA,'fit_key':fit_key,'count':count,'correlation_strength':correlation_strength,
          'weather':weather_by_team,'evaluation_seed':int(evaluation_seed),'construction_seed':int(construction_seed)}
    key=_hash(_json(spec));directory=root/'prepared'/key
    with _cache_lock(root/'locks'/('outcomes-'+key+'.lock')):
        cached=_read_prepared(directory,key,names,count)
        if cached is not None:
            cached['metadata']={'key':key,'fit_key':fit_key,'cache_hit':True,'count':count,
                'timings':{'load_seconds':time.perf_counter()-started}}
            return cached
        timings={};mark=time.perf_counter()
        parameters,report,fit_hit=_fit(inputs,roles,platform,root,fit_key,pilot_n,iterations,
            (lambda f,t:progress(.3*f,t)) if progress else None)
        timings['fit_seconds']=time.perf_counter()-mark
        result={}
        for index,(kind,seed) in enumerate([('evaluation',evaluation_seed),('construction',construction_seed)]):
            mark=time.perf_counter()
            if progress:progress(.3+.35*index,'Preparing '+kind+' outcomes')
            stats=simulate_stat_lines(inputs,roles,np.random.default_rng(seed),count,correlation_strength,
                weather_by_team=weather_by_team,projection_inputs=parameters,scoring_platform=platform,
                progress=(lambda fraction,text:progress(.3+.35*index+.35*fraction,text)) if progress else None)
            values={}
            for row in inputs.itertuples():
                line=dict(stats[row.Name],is_defense=int(row.Position.upper().split('/')[0] in {'D','DEF','DST'}))
                scores=np.asarray(score_nfl_stat_line(line,platform),float)
                if scores.shape!=(count,) or not np.isfinite(scores).all():raise ValueError('Invalid scored outcomes')
                values[row.Name]=scores
            result[kind]=pd.DataFrame(values)
            timings[kind+'_seconds']=time.perf_counter()-mark
        mark=time.perf_counter();directory.mkdir(parents=True,exist_ok=True)
        buffer=io.BytesIO()
        np.savez(buffer,names=np.array(names,dtype=str),evaluation=result['evaluation'].to_numpy(),
                 construction=result['construction'].to_numpy())
        raw=buffer.getvalue();report_raw=_json(report.astype(object).where(pd.notna(report),None).to_dict(orient='split'))
        _atomic_write(directory/'outcomes.npz',raw);_atomic_write(directory/'fit_report.json',report_raw)
        # Manifest is the commit marker; readers never accept a partial write.
        manifest={'schema':SCHEMA,'key':key,'spec':spec,'names':names,'model_digest':_model_digest(),
                  'outcomes_sha256':_hash(raw),'fit_report_sha256':_hash(report_raw)}
        _atomic_write(directory/'manifest.json',_json(manifest))
        timings['persist_seconds']=time.perf_counter()-mark;timings['total_seconds']=time.perf_counter()-started
        result['fit_report']=report
        result['metadata']={'key':key,'fit_key':fit_key,'cache_hit':False,'fit_cache_hit':fit_hit,
                            'count':count,'timings':timings}
        if progress:progress(1.,'Prepared simulation bundle ready')
        return result


def load_prepared(cache_root,key):
    """Load ready outcomes by preparation key, without fitting or simulation.

    The caller retains the preparation key for its frozen slate inputs; changing
    the slate requires preparing that new snapshot, not reusing an old key.
    """
    if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Invalid preparation key')
    started=time.perf_counter();directory=Path(cache_root)/'prepared'/key
    try:
        manifest=json.loads((directory/'manifest.json').read_bytes())
        if _hash(_json(manifest['spec']))!=key or manifest['model_digest']!=_model_digest():
            raise CacheIntegrityError('Prepared simulations belong to different inputs or model code')
        result=_read_prepared(directory,key,manifest['names'],int(manifest['spec']['count']))
        if result is None:raise CacheIntegrityError('Preparation is incomplete')
        result['metadata']={'key':key,'cache_hit':True,'count':manifest['spec']['count'],
            'timings':{'load_seconds':time.perf_counter()-started}}
        return result
    except CacheIntegrityError:raise
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise CacheIntegrityError('Prepared simulation bundle is unavailable') from exc


def main():
    import argparse
    from simmah_qb_roles import resolve_quarterbacks
    parser=argparse.ArgumentParser(description='Prepare reusable construction/evaluation outcomes offline')
    parser.add_argument('--players',required=True)
    parser.add_argument('--roles',required=True,help='Frozen historical-role JSON; {} explicitly selects model defaults')
    parser.add_argument('--weather',required=True,help='Frozen weather JSON; {} explicitly selects neutral/default weather')
    parser.add_argument('--starters',help='Confirmed team-to-starting-QB JSON when projections are ambiguous')
    parser.add_argument('--platform',required=True,choices=['DraftKings','FanDuel'])
    parser.add_argument('--cache-root',required=True)
    parser.add_argument('--output',required=True,help='Metadata report JSON')
    args=parser.parse_args()
    pool=pd.read_csv(args.players)
    choices=json.loads(Path(args.starters).read_text()) if args.starters else {}
    pool=resolve_quarterbacks(pool,choices)
    result=prepare_simulations(pool,json.loads(Path(args.roles).read_text()),args.platform,args.cache_root,
        weather_by_team=json.loads(Path(args.weather).read_text()),
        progress=lambda fraction,text:print(f'{fraction:.0%} {text}',flush=True))
    Path(args.output).write_text(json.dumps(result['metadata'],indent=2)+'\n')
    print(json.dumps(result['metadata'],indent=2))


if __name__=='__main__':main()
