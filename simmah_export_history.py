"""Every export click is a distinct, browser-owned audit checkpoint.

Raw CSV and serializable workspace/build state are retained; omitted state is
listed explicitly. This is export provenance, not proof of a site upload.
"""
import hashlib,io,json,uuid,zipfile,os,tempfile
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

HISTORY='simmah_export_history_v1'


def make_checkpoint(data,filename,context,state):
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
    # Never nest earlier archives inside the next archive.
    values={k:state[k] for k in list(state) if k!=HISTORY and not str(k).startswith('export_history_')}
    files={'export.csv':payload,'workspace_snapshot.txt':snapshot(values).encode('ascii')}
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
            persist_checkpoint(record,Path(__file__).resolve().parent/'data'/'export_archives')
        except Exception as exc:
            st.error('Export retained in this workspace, but the server archive copy FAILED: '+str(exc))
        st.toast('Export saved: '+record['exported_utc']+' ('+record['kind']+').')
    except Exception as exc:
        st.error('Export download is available, but its audit archive FAILED: '+str(exc))
    if callable(original_callback):original_callback(*callback_args,**(callback_kwargs or {}))


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
    records=[r for r in st.session_state.get(HISTORY,[]) if r.get('format')==context.get('format') and str(r.get('contest_id',''))==str(context.get('contest_id',''))]
    if not records:return
    with st.expander('Saved exports — latest first',expanded=False):
        ordered=list(reversed(records))
        chosen=st.selectbox('Saved export',range(len(ordered)),format_func=lambda i:ordered[i]['exported_utc']+' · '+ordered[i]['kind']+' · '+ordered[i]['export_filename'],key='export_history_select_'+key)
        record=ordered[chosen]
        st.download_button('DOWNLOAD SAVED EXPORT ARCHIVE',record['archive'],file_name='Simmah_Export_'+record['export_id']+'.zip',mime='application/zip',key='export_history_backup_'+key,on_click='ignore')
        with zipfile.ZipFile(io.BytesIO(record['archive'])) as archive:csv=archive.read('export.csv')
        st.download_button('DOWNLOAD THIS EXACT CSV',csv,file_name=record['export_filename'],mime='text/csv',key='export_history_csv_'+key,on_click='ignore')
        st.caption('Latest matching entries or late-swap export is used for review. Reports do not replace it. Keep an archive download as an independent backup; exports do not confirm site submission.')
