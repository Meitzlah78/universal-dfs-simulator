"""Every export click is a distinct, browser-owned audit checkpoint.

Raw CSV and serializable workspace/build state are retained; omitted state is
listed explicitly. This is export provenance, not proof of a site upload.
"""
import hashlib,io,json,uuid,zipfile,os,tempfile
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="export-audit")

HISTORY='simmah_export_history_v1'


def make_checkpoint(data,filename,context,state, metadata=None):
    from simmah_slate_workspaces import snapshot,encode
    payload=data.encode('utf-8') if isinstance(data,str) else bytes(data)
    export_id=uuid.uuid4().hex
    meta={k:v for k,v in context.items() if k not in {'player_pool','build','portfolio','late_swap','original_entries'}}
    parent=latest_record(state,context.get('format'),context.get('contest_id',''))
    meta['parent_export_id']=parent.get('export_id') if parent else None
    meta['capture_scope']='Exact downloaded CSV plus available serializable state; see workspace omitted list. Not proof of site submission or original build-time feed provenance.'
    meta.update(export_id=export_id,exported_utc=datetime.now(timezone.utc).isoformat(),
                export_filename=filename,export_sha256=hashlib.sha256(payload).hexdigest(),
                submission_verified=False,kind=context.get('kind','entries'))
    if metadata is not None:
        meta.update(metadata)
    # Never nest earlier archives inside the next archive.
    # Let the widget-safe codec filter before reading values. A retired editor
    # may remain in iteration even though its Streamlit value no longer exists.
    excluded={HISTORY}|{k for k in list(state) if str(k).startswith('export_history_')}
    files={'export.csv':payload,'workspace_snapshot.txt':snapshot(state,excluded).encode('ascii')}
    # The existing workspace codec preserves arrays, frames, attrs and controls.
    # Its explicit omitted list is retained instead of claiming a complete build.
    for key in ('build','portfolio','late_swap'):
        if key in context:files[key+'.json']=json.dumps(encode(context[key]),allow_nan=False).encode()
    if 'original_entries' in context:
        files['original_entries.csv']=bytes(context['original_entries'])
    pool=context.get('player_pool')
    if isinstance(pool,pd.DataFrame):
        files['player_pool.csv']=pool.to_csv(index=False).encode()
        files['player_pool_attrs.json']=json.dumps(encode(pool.attrs),allow_nan=False).encode()
    files['meta.json']=json.dumps(meta,indent=2,allow_nan=False).encode()
    files['hashes.json']=json.dumps({n:hashlib.sha256(v).hexdigest() for n,v in files.items()},sort_keys=True).encode()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,value in files.items():archive.writestr(name,value)
    return {**meta,'archive':buffer.getvalue()}


def persist_checkpoint(record,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    final=folder/(record['export_id']+'.zip')
    descriptor,temp=tempfile.mkstemp(prefix='.export_',dir=folder)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(record['archive']);stream.flush();os.fsync(stream.fileno())
        os.link(temp,final)  # Atomic, same filesystem, refuses overwrite.
    finally:
        Path(temp).unlink(missing_ok=True)
    return final


def capture_export(st,data,filename,context,original_callback=None,callback_args=(),callback_kwargs=None):
    try:
        record=make_checkpoint(data,filename,context,st.session_state)
        st.session_state[HISTORY]=[*st.session_state.get(HISTORY,[]),record]
        try:
            from simmah_diagnostic_updates import attach_latest_export
            attach_latest_export(st,record,context)
        except Exception as exc:
            st.warning('Export saved, but attaching it to the calibration/solver package failed: '+str(exc))
        try:
            persist_checkpoint(record,Path(__file__).resolve().parent/'data'/'export_archives')
        except Exception as exc:
            st.error('Export retained in this workspace, but the server archive copy FAILED: '+str(exc))
        st.toast('Export saved: '+record['exported_utc']+' ('+record['kind']+').')
    except Exception as exc:
        st.error('Export download is available, but its audit archive FAILED: '+str(exc))
    if callable(original_callback):original_callback(*callback_args,**(callback_kwargs or {}))



def _archive_job(data, filename, context, state, metadata):
    record = make_checkpoint(data, filename, context, state, metadata)
    try:
        persist_checkpoint(record, Path(__file__).resolve().parent/'data'/'export_archives')
        error = None
    except Exception as exc:
        error = 'Export retained in this workspace, but the server archive copy FAILED: '+str(exc)
    return record, error


def queue_export(st, data, filename, context, original_callback=None,
                 callback_args=(), callback_kwargs=None):
    """Freeze click-time values; archive encoding/compression runs off the UI thread."""
    from simmah_session_workspaces import checkpoint
    state = st.session_state
    try:
        sid = (state.get('_slate_active') or {}).get('id')
        jobs = state.setdefault('_slate_export_jobs', [])
        parent = latest_record(state, context.get('format'), context.get('contest_id',''))
        for job in jobs:
            if (job['sid'] == sid and job['format'] == context.get('format')
                    and str(job['contest_id']) == str(context.get('contest_id',''))
                    and job['kind'] in {'entries','late_swap'}):
                parent = job['metadata']
        metadata = dict(export_id=uuid.uuid4().hex,
                        exported_utc=datetime.now(timezone.utc).isoformat(),
                        parent_export_id=parent.get('export_id') if parent else None)
        # Prior audit ZIPs are excluded before copying, just as in make_checkpoint.
        view = checkpoint(st, copy=False)
        view['values'] = {k:v for k,v in view['values'].items()
                          if k != HISTORY and not str(k).startswith('export_history_')}
        frozen, frozen_context = deepcopy((view, context))
        frozen_state = frozen['values']
        frozen_state['_slate_restored_uploads'] = frozen.get('uploads', {})
        future = _POOL.submit(_archive_job, data, filename, frozen_context, frozen_state, metadata)
        jobs.append(dict(sid=sid, format=context.get('format'), contest_id=context.get('contest_id',''),
                         kind=context.get('kind','entries'), metadata=metadata,
                         context={k:v for k,v in context.items() if k in {'format','contest_id','kind'}},
                         future=future))
        st.toast('Download ready · Saving export history…')
    except Exception as exc:
        st.error('Export download is available, but its audit archive FAILED: '+str(exc))
    if callable(original_callback):
        original_callback(*callback_args, **(callback_kwargs or {}))


def finish_exports(st):
    """Publish completed jobs on the session thread, including inactive slates."""
    state = st.session_state
    jobs = state.get('_slate_export_jobs', [])
    remaining = []
    changed = False
    for job in jobs:
        if not job['future'].done():
            remaining.append(job)
            continue
        sid = job['sid']
        target = st
        row = None
        if sid != (state.get('_slate_active') or {}).get('id'):
            row = state.get('_slate_records', {}).get(sid)
            if row is None:
                # The disk archive remains available if its slate was closed.
                continue
            saved = row.get('_session_checkpoint')
            if saved is None:
                remaining.append(job)
                continue
            saved = dict(saved, values=dict(saved['values']), artifacts=dict(saved.get('artifacts', {})))
            row['_session_checkpoint'] = saved
            target = SimpleNamespace(session_state=saved['values'], warning=st.warning,
                                     error=st.error, toast=st.toast)
            target.session_state['_slate_archive_pending'] = saved['artifacts']
        try:
            record, error = job['future'].result()
            target.session_state[HISTORY] = [*target.session_state.get(HISTORY, []), record]
            try:
                from simmah_diagnostic_updates import attach_latest_export
                attach_latest_export(target, record, job['context'])
            except Exception as exc:
                st.warning('Export saved, but attaching it to the calibration/solver package failed: '+str(exc))
            if error:
                st.error(error)
            changed = True
        except Exception as exc:
            st.error('Export download is available, but its audit archive FAILED: '+str(exc))
        finally:
            if row is not None:
                target.session_state.pop('_slate_archive_pending', None)
    state['_slate_export_jobs'] = remaining
    return changed

def latest_record(state,format_label,contest_id):
    # Never substitute a report, another format, or another contest.
    matches=[r for r in state.get(HISTORY,[]) if r.get('format')==format_label
             and str(r.get('contest_id',''))==str(contest_id) and r.get('kind') in {'entries','late_swap'}]
    return matches[-1] if matches else None


def latest_player_snapshot(state,format_label,contest_id):
    record=latest_record(state,format_label,contest_id)
    if record is None:return pd.DataFrame(),{}
    with zipfile.ZipFile(io.BytesIO(record['archive'])) as archive:
        if 'player_pool.csv' not in archive.namelist():return pd.DataFrame(),record
        return pd.read_csv(archive.open('player_pool.csv')),{**record.get('snapshot_metadata',{}),**{k:v for k,v in record.items() if k!='archive'}}


def render_history(st,context,key):
    @st.fragment(run_every=1)
    def history():
        if finish_exports(st):
            from simmah_workspace_persistence import schedule
            schedule(st)
        if st.session_state.get('_slate_export_jobs'):
            st.caption('Saving export history…')
        _render_history(st, context, key)
    history()


def _render_history(st,context,key):
    from simmah_slate_workspaces import workspace_download_button
    records=[r for r in st.session_state.get(HISTORY,[]) if r.get('format')==context.get('format') and str(r.get('contest_id',''))==str(context.get('contest_id',''))]
    if not records:return
    from simmah_diagnostic_updates import matching_reference
    from simmah_nba_diagnostics import package_bytes
    diagnostic=matching_reference(st,context)
    if diagnostic and diagnostic.get('latest_export_utc'):
        raw=package_bytes(st,diagnostic)
        if raw is not None:
            workspace_download_button(st,'DOWNLOAD CALIBRATION & SOLVER PACKAGE',raw,
                file_name=diagnostic['filename'],mime='application/zip',
                key='export_history_diagnostics_'+key,on_click='ignore')
            st.caption('Includes original build and latest exported entries/late swap: '+diagnostic['latest_export_utc'])
    with st.expander('Saved exports — latest first',expanded=False):
        ordered=list(reversed(records))
        chosen=st.selectbox('Saved export',range(len(ordered)),format_func=lambda i:ordered[i]['exported_utc']+' · '+ordered[i]['kind']+' · '+ordered[i]['export_filename'],key='export_history_select_'+key)
        record=ordered[chosen]
        workspace_download_button(st,'DOWNLOAD SAVED EXPORT ARCHIVE',record['archive'],file_name='Simmah_Export_'+record['export_id']+'.zip',mime='application/zip',key='export_history_backup_'+key,on_click='ignore')
        with zipfile.ZipFile(io.BytesIO(record['archive'])) as archive:csv=archive.read('export.csv')
        workspace_download_button(st,'DOWNLOAD THIS EXACT CSV',csv,file_name=record['export_filename'],mime='text/csv',key='export_history_csv_'+key,on_click='ignore')
        st.caption('Latest matching entries or late-swap export is used for review. Reports do not replace it. Keep an archive download as an independent backup; exports do not confirm site submission.')

