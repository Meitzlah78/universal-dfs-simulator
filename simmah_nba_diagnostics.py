"""Frozen, self-describing NBA calibration/solver evidence. No network or pickle."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from zoneinfo import ZoneInfo
import io
import json
import platform
import re
import zipfile

import numpy as np
import pandas as pd
from simmah_nba_rules import rules_for


def _plain(value):
    if isinstance(value, dict):return {str(k):_plain(v) for k,v in value.items()}
    if isinstance(value, (tuple,list,set)):return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):return _plain(value.tolist())
    if isinstance(value, np.generic):return _plain(value.item())
    if isinstance(value, float) and not np.isfinite(value):return None
    if value is pd.NA or value is pd.NaT:return None
    if isinstance(value, (datetime,pd.Timestamp)):return value.isoformat()
    if isinstance(value, Path):return str(value)
    return value


def _json(value):
    return (json.dumps(_plain(value),sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def _rosters(pool, indices, slots):
    ids=np.asarray(indices)
    if ids.ndim!=2 or ids.shape[1]!=len(slots) or ids.dtype.kind not in 'iu':
        raise ValueError('Diagnostic roster indices must match site slots')
    if (ids<0).any() or (ids>=len(pool)).any():raise ValueError('Diagnostic player index outside frozen pool')
    return pd.DataFrame(pool['Player ID'].astype(str).to_numpy()[ids],columns=slots)


def make_package(pool, built, template, contest, markets, settings, *, started_at,
                 engine_metadata=None, source_root=None, captured_at=None):
    """Freeze one successful build, including exact shared outcomes and unsampled support.

    The package is captured once, before any later UI edits or portfolio re-sort.
    Timestamps are evidence, not a claim that capture preceded tipoff.
    """
    stamp=captured_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:raise ValueError('Timezone-aware capture time required')
    stamp=stamp.astimezone(timezone.utc)
    rules=rules_for(pool);slots=rules['slots'];field=built['field']
    frame=_rosters(pool,field['indices'],slots)
    copies=np.asarray(field['copies'])
    if copies.shape!=(len(frame),) or not np.isfinite(copies).all() or (copies<1).any() or (copies!=np.floor(copies)).any():
        raise ValueError('Positive integer opponent copies required')
    entries=int(copies.sum())
    if entries!=field['entries']:raise ValueError('Diagnostic opponent count differs from scored field')
    physical=Counter()
    for row,count in zip(frame.itertuples(index=False,name=None),copies):physical[tuple(sorted(row))]+=int(count)
    frame['Copies']=copies.astype(np.int64)
    indices=np.asarray(field['indices'])
    salary=pool['Salary'].to_numpy()[indices].sum(axis=1)
    frame['Salary']=salary;frame['Salary Left']=rules['salary_cap']-salary
    frame['Max Team']=[max(Counter(pool.iloc[row]['Team']).values()) for row in indices]
    games=[tuple(sorted((str(r.Team),str(r.Opponent)))) for r in pool.itertuples()]
    frame['Max Game']=[max(Counter(games[i] for i in row).values()) for row in indices]
    diagnostic=built.get('diagnostics',{})
    files={}
    def add(name,raw):files[name]=raw
    def csv(name,data):add(name,data.to_csv(index=False).encode('utf-8-sig'))
    add('inputs/original_entries_salary.csv',bytes(template))
    csv('inputs/player_pool.csv',pool)
    add('inputs/player_pool.json',_json({'columns':list(pool.columns),'dtypes':dict(zip(pool.columns,map(str,pool.dtypes))),
        'rows':pool.to_dict(orient='records'),'attrs':pool.attrs}))
    add('inputs/contest.json',_json(contest))
    add('inputs/markets.json',_json(markets))
    add('inputs/rules.json',_json(rules))
    add('inputs/settings.json',_json({**diagnostic.get('settings',{}),**settings}))
    add('inputs/engine.json',_json(engine_metadata or {}))
    csv('opponent_field.csv',frame)
    candidates=_rosters(pool,built['candidates']['indices'],slots)
    csv('candidate_lineups.csv',candidates)
    csv('candidate_scores.csv',built['report'])
    csv('portfolio_at_build.csv',built['portfolio'])
    support=diagnostic.get('support',{})
    if 'indices' in support:csv('solver/opponent_support.csv',_rosters(pool,support['indices'],slots))
    fit=field.get('fit_state',{})
    if 'indices' in fit:
        fit_frame=_rosters(pool,fit['indices'],slots)
        fit_frame['Probability']=fit['probabilities']
        csv('solver/fitted_support.csv',fit_frame)
    arrays={}
    for seed,values in diagnostic.get('outcomes',{}).items():arrays['outcomes_seed_'+seed]=values
    for key in ('ownership_input','payouts'):
        if key in diagnostic:arrays[key]=diagnostic[key]
    if 'theta' in fit:arrays['ownership_fit_theta']=fit['theta']
    if arrays:
        buffer=io.BytesIO();np.savez_compressed(buffer,**arrays);add('solver/arrays.npz',buffer.getvalue())
    add('solver/diagnostics.json',_json({
        'field':{k:v for k,v in field.items() if k not in ('indices','copies','fit_state')},
        'support':{k:v for k,v in support.items() if k!='indices'},
        'candidates':{k:v for k,v in built['candidates'].items() if k!='indices'},
        'engine_reports':diagnostic.get('engine_reports',{}),
        'simulation_seeds':built.get('simulation_seeds',{}),'search_seeds':diagnostic.get('seeds',{}),
        'simulations_per_set':built.get('simulations_per_set'),
        'timings_seconds':built.get('timings_seconds',{}),
        'excluded_player_ids':built.get('excluded_player_ids',[])}))
    # Preserve the actual installed implementation and model/profile files.
    # Never capture secrets, environment variables, other users' files or archives.
    root=Path(source_root) if source_root is not None else Path(__file__).parent
    source_paths=set(root.glob('simmah_nba_*.py'))
    source_paths.update(root.glob('simmah_portfolio.py'))
    source_paths.update(root.glob('simmah_diagnostic*.py'))
    source_paths.update(root.glob('simmah_slate_workspaces.py'))
    source_paths.update(root.glob('simmah_export_history.py'))
    source_paths.update(root.glob('calibration/*.py'))
    source_paths.update(root.glob('calibration/*.c'))
    source_paths.update(root.glob('calibration/*.h'))
    for folder in ('nba_models','nba_field_history'):
        source_paths.update(root.glob('data/'+folder+'/*.json'))
    for path in sorted(source_paths):
        if path.is_file():add('implementation/'+path.relative_to(root).as_posix(),path.read_bytes())
    missing=[]
    if len(diagnostic.get('outcomes',{}))!=3:missing.append('Three exact construction/field/evaluation outcome sets unavailable')
    if 'indices' not in support:missing.append('Unsampled opponent support unavailable')
    if 'indices' not in fit:missing.append('Fitted support probabilities unavailable')
    if not diagnostic.get('settings'):missing.append('Pipeline settings unavailable')
    versions={'python':platform.python_version()}
    for dependency in ('numpy','pandas','scipy','streamlit'):
        try:versions[dependency]=version(dependency)
        except PackageNotFoundError:versions[dependency]=None
    cid=str(contest['id'])
    manifest={'schema':1,'kind':'nba_calibration_solver_package','sport':'NBA','contest_id':cid,
        'platform':rules['platform'],'slate_date':contest.get('date'),
        'build_started_at_utc':started_at,'captured_at_utc':stamp.astimezone(timezone.utc).isoformat(),
        'captured_at_eastern':stamp.astimezone(ZoneInfo('America/New_York')).isoformat(),
        'pre_tip_status':'unverified; compare capture time with frozen game start times',
        'salary_template_sha256':sha256(bytes(template)).hexdigest(),
        'field_dimensions':{'entries':entries,'distinct_lineups':len(physical),
            'duplicate_entry_fraction':1-len(physical)/entries,'largest_roster_copies':max(physical.values()),
            'contest_capacity':contest.get('capacity'),'portfolio_entries':len(built['portfolio']),
            'field_size_policy':'Exact scored opponent count; no post-hoc rescaling'},
        'runtime_versions':versions,'missing_evidence':missing,
        'retention':'Saved through the private file archive; durable backup depends on archive configuration',
        'files':{name:{'sha256':sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}}
    add('manifest.json',_json(manifest))
    add('README.txt',(
        'SIMMAH NBA CALIBRATION & SOLVER PACKAGE\n'
        'Send this entire ZIP. File names and manifest identify its contest and build.\n'
        'Contains your original entries/salary upload and frozen inputs, including player IDs.\n'
        'The opponent field is the field actually scored, with weighted Copies.\n'
        'solver/arrays.npz contains exact shared outcomes keyed by seed (player columns follow player_pool.csv),\n'
        'plus ownership input, payout vector and fitted parameters when available. Load with allow_pickle=False.\n'
        'The full unsampled support and fitted probabilities support replaying the solver.\n'
        'implementation/ preserves installed code and model/profile JSON; bundled profiles are not proof of use.\n'
        'Capture time does not prove this was a pre-tip forecast. This package contains no future standings.\n'
        'For postgame evaluation, also upload the completed contest standings; preserve this original package.\n'
        'Portfolio and settings reflect build completion, before later sorting or edits.\n'
        +'Missing evidence: '+('; '.join(missing) if missing else 'none')+'\n').encode())
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        for name,raw in files.items():archive.writestr(name,raw)
    safe_cid=re.sub(r'[^A-Za-z0-9_-]','_',cid)
    tag=sha256(files['manifest.json']).hexdigest()[:10]
    name=f'Simmah_NBA_{rules["platform"]}_{safe_cid}_{stamp.strftime("%Y%m%dT%H%M%SZ")}_{tag}_Calibration_Solver.zip'
    return name,buf.getvalue(),manifest


def retain_package(st, package):
    """Queue once for the existing private server/browser/optional-cloud archive."""
    name,raw,manifest=package
    digest=sha256(raw).hexdigest()
    seen=st.session_state.setdefault('_slate_archive_seen',set())
    if digest in seen:return
    pending=st.session_state.setdefault('_slate_archive_pending',{})
    pending[digest]={'digest':digest,'filename':name,'raw':raw,'upload_key':'nba_diagnostic_package',
        'metadata':{'kind':manifest.get('kind','calibration_solver_package'),'contest_ids':[manifest['contest_id']],
            'platform':manifest['platform'],'sport':manifest.get('sport','NBA'),
            'mode':'nba' if manifest.get('sport','NBA')=='NBA' else 'nfl',
            'captured_at':manifest['captured_at_utc']}}
    seen.add(digest)


def package_reference(package):
    return {'filename':package[0],'digest':sha256(package[1]).hexdigest()}


def package_bytes(st, reference):
    """Keep large ZIPs out of slate snapshots; recover by their immutable hash."""
    pending=st.session_state.get('_slate_archive_pending',{}).get(reference['digest'])
    if pending:return pending['raw']
    from simmah_archive_ui import archive_for
    archive=archive_for(st)
    if archive is None:return None
    try:return archive.get(reference['digest'])
    except (OSError,KeyError):return None


def rotation_audit(pool):
    """Explain the exact pregame rotation filter, including excluded minutes."""
    rows=pool.copy()
    projection=pd.to_numeric(rows['Projection'],errors='coerce')
    minutes=pd.to_numeric(rows.get('Projected Minutes',pd.Series(np.nan,index=rows.index)),errors='coerce')
    injured=rows['Injury Status'].astype(str).str.upper().isin(['OUT','O','IR','SUSPENDED'])
    rotation_only=rows['Rotation Only'].eq(True) if 'Rotation Only' in rows else pd.Series(False,index=rows.index)
    projected=(np.isfinite(projection)&projection.gt(0))|rotation_only
    included=projected&~injured&~minutes.eq(0)
    reason=np.select([injured,minutes.eq(0),~projected],
        ['OUT / inactive','Provider minutes explicitly zero','No positive projection or rotation-only status'],
        default='Included')
    valid=np.isfinite(minutes)&minutes.gt(0)&minutes.le(48)
    detail=rows[[c for c in ('Player ID','Name','Team','Opponent','Injury Status','Projection','Projection Source',
        'Projected Minutes','Minutes Source','Eligible','Rotation Only') if c in rows]].copy()
    detail['In Simulated Rotation']=included
    detail['Rotation Reason']=reason
    detail['Minutes Valid']=valid
    summary=[]
    for team,group in rows.groupby('Team',sort=True):
        idx=group.index;used=included.loc[idx]
        total=float(minutes.loc[idx][used&valid.loc[idx]].sum())
        summary.append({'Team':team,'Rotation Players':int(used.sum()),'Known Rotation Minutes':total,
            'Minutes Short of 240':240-total,'Invalid Rotation Minutes':int((used&~valid.loc[idx]).sum()),
            'Excluded Known Minutes':float(minutes.loc[idx][~used&valid.loc[idx]].sum())})
    return pd.DataFrame(summary),detail


def make_setup_package(pool,template,contest,markets,error,*,source_root=None):
    """Evidence for a blocked setup; never substitute a previous successful field."""
    summary,detail=rotation_audit(pool)
    stamp=datetime.now(timezone.utc);rules=rules_for(pool)
    files={'inputs/original_entries_salary.csv':bytes(template),
        'inputs/player_pool.csv':pool.to_csv(index=False).encode('utf-8-sig'),
        'inputs/player_pool.json':_json({'rows':pool.to_dict('records'),'attrs':pool.attrs}),
        'inputs/contest.json':_json(contest),'inputs/markets.json':_json(markets),
        'inputs/rules.json':_json(rules),
        'rotation_summary.csv':summary.to_csv(index=False).encode('utf-8-sig'),
        'rotation_players.csv':detail.to_csv(index=False).encode('utf-8-sig'),
        'setup_error.txt':str(error).encode()}
    root=Path(source_root) if source_root is not None else Path(__file__).parent
    for name in ('simmah_nba_pregame.py','simmah_nba_role_priors.py','simmah_nba_projections.py','simmah_nba_diagnostics.py'):
        path=root/name
        if path.is_file():files['implementation/'+name]=path.read_bytes()
    manifest={'schema':1,'kind':'nba_setup_diagnostic_package','sport':'NBA','platform':rules['platform'],
        'contest_id':str(contest['id']),'slate_date':contest.get('date'),
        'captured_at_utc':stamp.isoformat(),'captured_at_eastern':stamp.astimezone(ZoneInfo('America/New_York')).isoformat(),
        'build_status':'blocked_before_simulation','error':str(error),
        'salary_template_sha256':sha256(bytes(template)).hexdigest(),
        'missing_evidence':['No new opponent field or solver outcomes: setup validation blocked the build'],
        'files':{name:{'sha256':sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}}
    files['manifest.json']=_json(manifest)
    files['README.txt']=(
        'SIMMAH BLOCKED NBA SETUP\nSend this entire ZIP to diagnose the current input failure.\n'
        'rotation_summary.csv shows minutes reaching the simulator; rotation_players.csv explains every included/excluded player.\n'
        'Projected minutes and point projections have not been adjusted. No previous build is substituted.\n').encode()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as bundle:
        for name,raw in files.items():bundle.writestr(name,raw)
    cid=re.sub(r'[^A-Za-z0-9_-]','_',str(contest['id']))
    return f'Simmah_NBA_{rules["platform"]}_{cid}_{stamp.strftime("%Y%m%dT%H%M%SZ")}_SETUP_DIAGNOSTIC.zip',buffer.getvalue(),manifest
