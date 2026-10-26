"""One automatic NFL build package across Classic, Showdown, Full and Single."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import base64
import io
import json
import re
import zipfile
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from simmah_nba_diagnostics import _json, retain_package, package_reference, package_bytes


def make_nfl_package(state, format_label, pool, field, candidates, results, cache_root,
                     *, extras=None, source_root=None, captured_at=None):
    """Capture explicit scored data, relevant controls and matching immutable cache files."""
    from simmah_slate_workspaces import encode, private_key, transient_key
    site='FanDuel' if str(format_label).startswith('FanDuel') else 'DraftKings'
    contest=dict(state.get('selected_fd_contest' if site=='FanDuel' else 'selected_dk_contest') or {})
    stamp=captured_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:raise ValueError('Timezone-aware capture time required')
    stamp=stamp.astimezone(timezone.utc)
    cid=str(contest.get('id') or 'unselected')
    root=Path(source_root) if source_root is not None else Path(__file__).parent
    files={};omitted=[]
    def csv(name,frame):
        files[name]=frame.to_csv(index=False).encode('utf-8-sig')
        files[name+'.attrs.json']=_json(frame.attrs)
    for name,frame in [('player_pool',pool),('opponent_field',field),('candidates',candidates),('scored_lineups',results)]:
        if isinstance(frame,pd.DataFrame):csv(name+'.csv',frame)
        else:omitted.append(name+' unavailable')
    files['inputs/contest.json']=_json(contest)
    context=dict(extras or {})
    evaluation=context.pop('evaluation_outcomes',None)
    if isinstance(evaluation,pd.DataFrame):
        raw=io.BytesIO();np.savez_compressed(raw,values=evaluation.to_numpy(),names=evaluation.columns.to_numpy(dtype=str))
        files['solver/evaluation_outcomes.npz']=raw.getvalue()
        files['solver/evaluation_outcomes.attrs.json']=_json(evaluation.attrs)
    encoded_context=[]
    for key,value in context.items():
        try:encoded=encode(value)
        except (TypeError,ValueError,RecursionError):
            if isinstance(value,pd.DataFrame):
                path='solver/context_'+str(key)+'.csv';csv(path,value)
                encoded='See '+path+' and its attrs JSON'
            elif isinstance(value,np.ndarray) and not value.dtype.hasobject:
                path='solver/context_'+str(key)+'.npz';raw=io.BytesIO()
                np.savez_compressed(raw,values=value);files[path]=raw.getvalue();encoded='See '+path
            else:
                omitted.append('Explicit context not serializable: '+str(key));continue
        encoded_context.append([key,encoded])
    files['solver/explicit_context.json']=json.dumps({'@':'dict','value':encoded_context},allow_nan=False).encode()
    # Only scientific/build controls, never archive payloads, other slates or credentials.
    tokens=('simulation','candidate','contest_','ownership','projection_event_fit','field_learning',
            'active_game','stack','salary','aggressiveness','correlation','player_control','exposure',
            'latest_auto_pregame','engine','payout','diversity','portfolio_metric','portfolio_count','control_values')
    values={}
    for key in list(state):
        text=str(key)
        if text.startswith(('_','nba_','export_history_','diagnostic_')) or private_key(text) or transient_key(text):continue
        if text=='simmah_export_history_v1' or 'saved_build' in text:continue
        if not any(token in text.lower() for token in tokens):continue
        if site=='FanDuel' and text.startswith(('dk_','classic_')):continue
        if site=='DraftKings' and text.startswith('fd_'):continue
        try:value=state[key]
        except KeyError:
            omitted.append('State unavailable during capture: '+text)
            continue
        if hasattr(value,'getvalue'):continue
        if isinstance(value,pd.DataFrame) and 'simulation' in text and 'df' in text:
            # Exact active evaluation outcomes are stored as binary arrays above.
            # Other mode's large outcome tables must not leak into this package.
            continue
        try:values[text]=encode(value)
        except (TypeError,ValueError,RecursionError):omitted.append('State not serializable: '+text)
    files['solver/runtime_state.json']=json.dumps({'@':'dict','value':list(values.items())},allow_nan=False).encode()
    # Original uploaded salary/entries bytes from the ACTIVE slate, not a recent-file guess.
    active=state.get('_slate_active') or {}
    if active.get('data'):
        files['inputs/original_active_slate.csv']=base64.b64decode(active['data'],validate=True)
    else:omitted.append('Original active slate upload unavailable')
    upload_names={}
    for key,value in state.get('_slate_restored_uploads',{}).items():
        if not hasattr(value,'getvalue'):continue
        if not any(word in str(key).lower() for word in ('salary','entries','projection','ownership','payout','slate')):continue
        name='inputs/upload_'+str(len(upload_names))+'.csv'
        files[name]=bytes(value.getvalue());upload_names[name]={'widget_key':str(key),'original_filename':value.name}
    files['inputs/uploads.json']=_json(upload_names)
    # Copy only the exact prepared/fit keys used by this simulation, without rerunning it.
    preparation=state.get('simulation_preparation_'+site) or {}
    active_key=evaluation.attrs.get('preparation_key') if isinstance(evaluation,pd.DataFrame) else None
    if active_key and active_key!=preparation.get('key'):
        omitted.append('Prepared cache metadata differs from active evaluation key; unrelated cache excluded')
        preparation={}
    copied_prepared=False
    for kind,key,folder in [('prepared',preparation.get('key'),'prepared'),('fit',preparation.get('fit_key'),'fits')]:
        if not key or not re.fullmatch(r'[a-f0-9]{64}',str(key)):
            omitted.append('Matching '+kind+' cache key unavailable');continue
        directory=Path(cache_root)/folder
        paths=[directory/(key+'.json')] if kind=='fit' else [directory/key/n for n in ('manifest.json','outcomes.npz','fit_report.json')]
        if kind=='prepared' and all(path.is_file() for path in paths):
            stored=json.loads(paths[0].read_bytes())
            outcome_bytes=paths[1].read_bytes()
            valid=(stored.get('key')==key and sha256(outcome_bytes).hexdigest()==stored.get('outcomes_sha256')
                and sha256(paths[2].read_bytes()).hexdigest()==stored.get('fit_report_sha256'))
            if valid and isinstance(evaluation,pd.DataFrame):
                with np.load(io.BytesIO(outcome_bytes),allow_pickle=False) as arrays:
                    valid=(arrays['names'].tolist()==list(evaluation.columns)
                        and np.array_equal(arrays['evaluation'],evaluation.to_numpy()))
            if not valid:
                omitted.append('Prepared cache failed checksum or active-outcome alignment; excluded')
                continue
        for path in paths:
            if path.is_file():
                files['solver/cache/'+kind+'/'+path.name]=path.read_bytes()
                if path.name=='outcomes.npz':copied_prepared=True
            else:omitted.append('Matching cache artifact unavailable: '+kind+'/'+path.name)
    paths=set(root.glob('simmah_*.py'))|set(root.glob('dfs_app.py'))|set(root.glob('requirements.txt'))
    for pattern in ('calibration/*.py','calibration/*.c','calibration/*.h','data/*history*.json','data/*profile*.json'):
        paths.update(root.glob(pattern))
    for path in sorted(paths):
        if path.is_file():files['implementation/'+path.relative_to(root).as_posix()]=path.read_bytes()
    manifest={'schema':1,'kind':'nfl_calibration_solver_package','sport':'NFL','platform':site,
        'format':str(format_label),'contest_id':cid,'slate_identity':state.get('active_slate_identity'),
        'captured_at_utc':stamp.astimezone(timezone.utc).isoformat(),
        'captured_at_eastern':stamp.astimezone(ZoneInfo('America/New_York')).isoformat(),
        'pre_tip_status':'unverified; compare capture time with game starts',
        'prepared_outcomes_included':copied_prepared,'missing_evidence':omitted,
        'field_rows':len(field) if isinstance(field,pd.DataFrame) else None,
        'field_size_policy':'Original scored field retained without resampling; copy weights remain in original columns/attrs',
        'files':{name:{'sha256':sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}}
    files['manifest.json']=_json(manifest)
    files['README.txt']=(
        'SIMMAH NFL CALIBRATION & SOLVER PACKAGE\nSend this entire ZIP.\n'
        'Frozen at contest-scoring completion; later lineup edits are not included.\n'
        'Contains original active slate upload, scored opponent field, candidates, player pool,\n'
        'controls, ownership, payouts, weather/market context and exact matching prepared caches when available.\n'
        'solver/cache/prepared/outcomes.npz contains evaluation and construction outcomes with player names.\n'
        'runtime_state.json and explicit_context.json use simmah_slate_workspaces.decode; no pickle.\n'
        'Player pool rows and original uploads supply platform IDs for name-based NFL rosters.\n'
        'Source files preserve model/solver versions. Historical solver execution logs are separate archived reports.\n'
        'This is build evidence, not proof of pre-tip timing, site submission or predictive improvement.\n'
        'Completed standings must be uploaded after the contest for actual-field comparison.\n'
        'See manifest.json for hashes and any missing evidence.\n').encode()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as bundle:
        for name,raw in files.items():bundle.writestr(name,raw)
    label=re.sub(r'[^A-Za-z0-9_-]','_',str(format_label))
    safe_cid=re.sub(r'[^A-Za-z0-9_-]','_',cid)
    tag=sha256(files['manifest.json']).hexdigest()[:10]
    return f'Simmah_NFL_{label}_{safe_cid}_{stamp.strftime("%Y%m%dT%H%M%SZ")}_{tag}_Calibration_Solver.zip',buffer.getvalue(),manifest


def capture_nfl_build(st, format_label, pool, field, candidates, results, cache_root, *, extras=None):
    """A save failure is visible and cannot erase successful lineup results."""
    try:
        package=make_nfl_package(st.session_state,format_label,pool,field,candidates,results,cache_root,extras=extras)
        st.session_state['diagnostic_package_current']={**package_reference(package),
            'format':str(format_label),'contest_id':package[2]['contest_id'],'captured_at':package[2]['captured_at_eastern']}
        retain_package(st,package)
        st.session_state.pop('diagnostic_package_error',None)
    except Exception as exc:
        st.session_state['diagnostic_package_error']='Calibration/solver package capture failed: '+str(exc)
        st.warning(st.session_state['diagnostic_package_error'])


def render_nfl_package(st):
    from simmah_slate_workspaces import workspace_download_button
    saved=st.session_state.get('diagnostic_package_current')
    if st.session_state.get('diagnostic_package_error'):st.warning(st.session_state['diagnostic_package_error'])
    if not saved:return
    current=str(st.session_state.get('dfs_format',''))
    if current!=saved['format']:return
    site='FanDuel' if current.startswith('FanDuel') else 'DraftKings'
    contest=st.session_state.get('selected_fd_contest' if site=='FanDuel' else 'selected_dk_contest') or {}
    if str(contest.get('id') or 'unselected')!=saved['contest_id']:return
    data=package_bytes(st,saved)
    if data is None:
        st.caption('Diagnostic package is awaiting archive recovery. Check Saved files below.')
        return
    workspace_download_button(st,'DOWNLOAD CALIBRATION & SOLVER PACKAGE',data,
        saved['filename'],'application/zip',key='nfl_diagnostic_download',on_click='ignore')
    st.caption('Saved '+saved['format']+' · contest '+saved['contest_id']+' · '+saved['captured_at']+
        '. Send this one ZIP for opponent calibration and solver review. Older builds remain in Saved files.')
