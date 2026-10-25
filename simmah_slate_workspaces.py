"""Browser-owned slate tabs, with a separate private original-input archive."""
import base64,csv,gzip,hashlib,io,json,math,uuid
from pathlib import Path
from datetime import date,datetime
import numpy as np
import pandas as pd

MAX_ARRAY_BYTES=16*1024*1024
class StoredUpload(io.BytesIO):
    def __init__(self,data,name):super().__init__(data);self.name=name;self.size=len(data)


def encode(value):
    if value is None or isinstance(value,(str,bool,int)):return value
    if isinstance(value,(float,np.floating)):return float(value) if math.isfinite(value) else {'@':'float','value':str(float(value))}
    if isinstance(value,np.integer):return int(value)
    if isinstance(value,np.bool_):return bool(value)
    if isinstance(value,pd.DataFrame):
        if value.memory_usage(deep=True).sum()>MAX_ARRAY_BYTES:raise ValueError('Large calculation cache')
        return {'@':'frame','value':value.to_json(orient='table',date_format='iso'),'attrs':encode(value.attrs)}
    if isinstance(value,pd.Series):return {'@':'series','value':encode(value.to_frame()),'name':encode(value.name)}
    if isinstance(value,np.ndarray):
        if value.nbytes>MAX_ARRAY_BYTES or value.dtype.hasobject:raise ValueError('Large or object calculation cache')
        buf=io.BytesIO();np.save(buf,value,allow_pickle=False)
        return {'@':'array','value':base64.b64encode(buf.getvalue()).decode()}
    if isinstance(value,(datetime,date,pd.Timestamp)):return {'@':'date','value':value.isoformat()}
    if isinstance(value,bytes):return {'@':'bytes','value':base64.b64encode(value).decode()}
    if isinstance(value,dict):
        result=[]
        for k,v in value.items():
            if isinstance(k,str) and private_key(k):continue
            try:result.append([encode(k),encode(v)])
            except (ValueError,TypeError,RecursionError):continue
        return {'@':'dict','value':result}
    if isinstance(value,(tuple,list,set)):return {'@':type(value).__name__,'value':[encode(v) for v in value]}
    raise TypeError('Not a saved slate value')


def decode(value):
    if not isinstance(value,dict):return value
    kind=value.get('@');raw=value.get('value')
    if kind=='dict':return {decode(k):decode(v) for k,v in raw}
    if kind in {'tuple','list','set'}:return {'tuple':tuple,'list':list,'set':set}[kind](decode(v) for v in raw)
    if kind=='frame':
        frame=pd.read_json(io.StringIO(raw),orient='table');frame.attrs=decode(value['attrs']);return frame
    if kind=='series':
        series=decode(raw).iloc[:,0];series.name=decode(value['name']);return series
    if kind=='array':return np.load(io.BytesIO(base64.b64decode(raw)),allow_pickle=False)
    if kind=='bytes':return base64.b64decode(raw)
    if kind=='date':return datetime.fromisoformat(raw)
    if kind=='float':return float(raw)
    raise ValueError('Unknown saved-state type')


def private_key(key):
    lowered=str(key).lower()
    return any(word in lowered for word in ('secret','password','token','api_key','credential','authorization'))


def transient_key(key):
    key=str(key)
    # Legacy snapshots saved these download triggers as ordinary booleans.
    # Keep actual export archives and the history selector; discard only actions.
    if key.startswith(('export_history_backup_','export_history_csv_','export_history_diagnostics_')):return True
    return (key.startswith('FormSubmitter:') or (key.startswith('manual_lineups_') and key.endswith('_apply_swap')) or key.startswith(('game_lines_','fd_player_pool_editor_')) or key=='player_controls_editor' or key.endswith('_remove_restored') or key=='projection_accuracy_template_download' or (key.startswith('saved_contest_choice_') and key.endswith(('_use','_save','_restore_button','_backup','_restore'))) or key.startswith(('nba_projection_upload_','nba_minutes_snapshot_download','nba_entries_download','nba_portfolio_report_','nba_open_fanduel_','nba_open_draftkings_'))
            or key in {'nba_build','nba_field_download','nba_entries_download',
                       'nba_fast_late_swap','nba_late_swap_upload','nba_late_swap_download',
                       'loaded_slates_browser','nba_underdog_x_feed','sticky_refresh_projections',
                       'contest_history_uploads_v2'})


def snapshot(state, transient_keys=()):
    transient_keys=set(transient_keys) | set(state.get('_slate_uploader_keys',())) | set(state.get('_slate_action_keys',())) | set(state.get('_slate_readonly_keys',()))
    values={};omitted=[]
    for key in list(state):
        if str(key).startswith(('_slate_','$$','universal_slate_setup_file')) or private_key(key):continue
        if key in transient_keys or transient_key(key):continue
        if key in {'loaded_slates_browser','sticky_refresh_projections','refresh_projections_requested','projection_updates_found','injury_updates_found'}:continue
        try:value=state[key]
        except KeyError:
            # Streamlit can expose a stale widget mapping during cleanup.
            # An unreadable value is absent, not a reason to lose the slate.
            omitted.append(str(key))
            continue
        if hasattr(value,'getvalue') and hasattr(value,'name'):continue
        try:values[key]=encode(value)
        except (TypeError,ValueError,RecursionError):omitted.append(str(key))
    uploads={k:{'name':v.name,'data':base64.b64encode(v.getvalue()).decode()} for k,v in state.get('_slate_restored_uploads',{}).items() if hasattr(v,'getvalue')}
    content=json.dumps({'schema':1,'values':values,'uploads':uploads,'omitted':omitted,'transient_keys':list(transient_keys)},separators=(',',':'),allow_nan=False).encode()
    return base64.b64encode(gzip.compress(content,compresslevel=1)).decode()


def restore(state,content):
    payload=json.loads(gzip.decompress(base64.b64decode(content))) if content else {'values':{},'uploads':{}}
    if payload.get('schema',1)!=1:raise ValueError('Unknown slate backup version')
    values={k:decode(v) for k,v in payload['values'].items() if not private_key(k) and not transient_key(k) and k not in payload.get('transient_keys',[])}
    # Migrate old game-line deltas into application data before touching session
    # state: recent Streamlit versions reject assignment to known editor keys.
    for key,value in payload['values'].items():
        if str(key).startswith('game_lines_'):
            migrated='legacy_game_line_edits_'+str(key)[len('game_lines_'):]
            values.setdefault(migrated,decode(value))
    for k in list(state):
        if not str(k).startswith(('_slate_','$$')):del state[k]
    state.update(values)
    state['_slate_restored_uploads']={k:StoredUpload(base64.b64decode(v['data']),v['name']) for k,v in payload.get('uploads',{}).items()}
    state['_slate_widget_seen']={}


def slate_record(upload):
    data=upload.getvalue();rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
    if not rows:raise ValueError('Empty entries file')
    # Stable salary IDs identify one site/format/slate even if its entries change.
    ids=[]
    for i,row in enumerate(rows):
        column=next((row.index(k) for k in ('Id','ID') if k in row and any(n in row for n in ('Nickname','Name'))),None)
        if column is not None:
            ids=[r[column].strip() for r in rows[i+1:] if len(r)>column and r[column].strip()];break
    identity=json.dumps([rows[0][:13],sorted(ids) if ids else hashlib.sha256(data).hexdigest()],sort_keys=True)
    sid=hashlib.sha256(identity.encode()).hexdigest()[:24]
    return {'id':sid,'name':upload.name,'title':upload.name.replace('.csv',''),'data':base64.b64encode(data).decode(),'snapshot':''}


def begin_workspaces(st):
    from simmah_archive_jobs import end_live_build
    if st.session_state.pop('_slate_archive_live_build',False):
        end_live_build(st.session_state.get('_slate_archive_build_token',''))
    if st.session_state.pop('_slate_clear_active',False):
        restore(st.session_state,'')
        st.session_state.pop('_slate_active',None)
        st.session_state['_slate_upload_epoch']=st.session_state.get('_slate_upload_epoch',0)+1
    pending=st.session_state.pop('_slate_pending',None)
    records=st.session_state.setdefault('_slate_records',{})
    if pending:
        pending=records.get(pending['id'],pending)
        try:
            restore(st.session_state,pending.get('snapshot',''))
            st.session_state['_slate_active']=pending
            st.session_state['_slate_upload_epoch']=st.session_state.get('_slate_upload_epoch',0)+1
            records[pending['id']]=pending
        except (ValueError,TypeError,KeyError,OSError) as exc:st.warning('Saved slate could not restore: '+str(exc))
    st.session_state.setdefault('_slate_generation',uuid.uuid4().hex)
    return st.container()


def select_upload(st,upload):
    if upload is not None:
        from simmah_archive_ui import capture_upload
        capture_upload(st,upload,'primary_slate_upload')
        digest=hashlib.sha256(upload.getvalue()).hexdigest()
        scope=(st.session_state.get('_slate_active',{}).get('id','new'),st.session_state.get('_slate_upload_epoch',0))
        seen=st.session_state.setdefault('_slate_seen_uploads',{})
        if digest!=seen.get(scope):
            seen[scope]=digest
            incoming=slate_record(upload)
            current=st.session_state.get('_slate_active')
            if current and current['id']==incoming['id']:
                current.update({k:incoming[k] for k in ('data','name')})
            else:
                st.session_state['_slate_incoming']=incoming
                return None
    current=st.session_state.get('_slate_active')
    return StoredUpload(base64.b64decode(current['data']),current['name']) if current else None


def workspace_file_uploader(st,label,*args,**kwargs):
    key=str(kwargs.get('key',label))
    st.session_state.setdefault('_slate_uploader_keys',set()).add(key)
    # Older browser snapshots may contain None or [] for ANY uploader. Streamlit
    # forbids assigning those values just as it forbids assigning real files.
    # Clear only programmatic assignments, never native uploaded widget state.
    from streamlit.runtime.state import get_session_state
    if get_session_state().is_new_state_value(key):
        del st.session_state[key]
    value=st.file_uploader(label,*args,**kwargs)
    from simmah_archive_ui import capture_upload
    capture_upload(st,value,key)
    if kwargs.get('accept_multiple_files'):return value  # History imports remain explicit actions.
    key=str(kwargs.get('key',label));saved=st.session_state.setdefault('_slate_restored_uploads',{})
    seen=st.session_state.setdefault('_slate_widget_seen',{})
    if value is not None:saved[key]=value
    elif seen.get(key):saved.pop(key,None)
    seen[key]=value is not None
    if value is None and key in saved:
        st.caption('Restored file: '+saved[key].name)
        if workspace_button(st,'Remove restored file',key=key+'_remove_restored'):
            saved.pop(key,None)
    return value if value is not None else saved.get(key)





def workspace_button(st,*args,**kwargs):
    """Action triggers are transient; never assign a restored value to a button."""
    key=kwargs.get('key')
    if key is not None:
        key=str(key)
        st.session_state.setdefault('_slate_action_keys',set()).add(key)
        from streamlit.runtime.state import get_session_state
        if get_session_state().is_new_state_value(key):
            del st.session_state[key]
    result=st.button(*args,**kwargs)
    _prioritize_build(st,result,args,kwargs)
    return result


def _prioritize_build(st,pressed,args,kwargs):
    label=str(args[0] if args else kwargs.get('label','')).upper()
    if pressed and any(word in label for word in ('BUILD','SIMULAT','RUN SIM')):
        from simmah_archive_jobs import begin_live_build
        token=st.session_state.setdefault('_slate_archive_build_token',uuid.uuid4().hex)
        st.session_state['_slate_archive_live_build']=True
        begin_live_build(token)



def workspace_form_submit_button(st,*args,**kwargs):
    """Render explicit form actions without replaying a saved submit value."""
    key=kwargs.get('key')
    if key is None:
        raise ValueError('Saved-workspace form actions require an explicit key')
    key=str(key)
    st.session_state.setdefault('_slate_action_keys',set()).add(key)
    from streamlit.runtime.state import get_session_state
    if get_session_state().is_new_state_value(key):
        del st.session_state[key]
    result=st.form_submit_button(*args,**kwargs)
    _prioritize_build(st,result,args,kwargs)
    return result


def workspace_download_button(st,*args,**kwargs):
    """Never replay a saved download-button value; preserve the actual data separately."""
    key=kwargs.get('key')
    if key is not None:
        st.session_state.setdefault('_slate_action_keys',set()).add(str(key))
        from streamlit.runtime.state import get_session_state
        if get_session_state().is_new_state_value(str(key)):
            del st.session_state[str(key)]
    checkpoint=kwargs.pop('export_checkpoint',None)
    if checkpoint is not None:
        from simmah_export_history import capture_export,render_history
        data=kwargs.get('data',args[1] if len(args)>1 else None)
        filename=kwargs.get('file_name',args[2] if len(args)>2 else 'export.csv')
        original=kwargs.get('on_click');callback_args=kwargs.get('args',());callback_kwargs=kwargs.get('kwargs',{})
        kwargs['on_click']=capture_export
        kwargs['args']=(st,data,filename,checkpoint,original,callback_args,callback_kwargs)
        kwargs.pop('kwargs',None)
        clicked=st.download_button(*args,**kwargs)
        render_history(st,checkpoint,str(key or filename))
        return clicked
    return st.download_button(*args,**kwargs)


def workspace_data_editor(st,data,*args,**kwargs):
    """Do not replay editor widget state; retain game-line values separately."""
    key=kwargs.get('key')
    if key is None:return st.data_editor(data,*args,**kwargs)
    key=str(key)
    st.session_state.setdefault('_slate_readonly_keys',set()).add(key)
    from streamlit.runtime.state import get_session_state
    assigned=get_session_state().is_new_state_value(key)
    legacy=st.session_state.get(key) if assigned else None
    if assigned:del st.session_state[key]
    game_lines=key.startswith('game_lines_') and isinstance(data,pd.DataFrame) and 'Game' in data
    if game_lines:
        # This application value is safe to restore. Only manual line columns
        # are retained, never automatic odds or the read-only widget payload.
        saved_key='manual_game_lines_'+key[len('game_lines_'):]
        migrated=st.session_state.pop('legacy_game_line_edits_'+key[len('game_lines_'):],None)
        if legacy is None:legacy=migrated
        saved=st.session_state.get(saved_key,{})
        base=data.copy()
        columns=('Game total','Home spread')
        for index,row in base.iterrows():
            values=saved.get(str(row['Game']),{})
            for column in columns:
                if column in base and column in values:base.at[index,column]=values[column]
        # Migrate old snapshots' edited_rows once before dropping the forbidden
        # widget assignment. Never allow edits to game identity or other fields.
        if isinstance(legacy,dict):
            for row_number,edits in legacy.get('edited_rows',{}).items():
                try:position=int(row_number)
                except (TypeError,ValueError):continue
                if not 0<=position<len(base) or not isinstance(edits,dict):continue
                for column in columns:
                    if column in base and column in edits:base.at[base.index[position],column]=edits[column]
        data=base
    result=st.data_editor(data,*args,**kwargs)
    if game_lines:
        st.session_state[saved_key]={str(row['Game']):{column:row[column] for column in columns if column in result}
                                    for _,row in result.iterrows()}
    return result


def capture(st):
    # Button triggers and uploader widget internals must never be replayed.
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    transient=set()
    context=get_script_run_ctx()
    if context:
        for widget in context.session_state.get_widget_states():
            if widget.WhichOneof('value') in {'trigger_value','string_trigger_value','json_trigger_value','chat_input_value','file_uploader_state_value'}:
                transient.update(k for k in st.session_state if widget.id.endswith('-'+str(k)))
    return snapshot(st.session_state,transient)


def finish_workspaces(st,host):
    import streamlit.components.v1 as components
    from simmah_archive_jobs import end_live_build
    if st.session_state.pop('_slate_archive_live_build',False):
        end_live_build(st.session_state.get('_slate_archive_build_token',''))
    from simmah_archive_ui import render_archive
    with host:
        from simmah_diagnostic_packages import render_nfl_package
        render_nfl_package(st)
        render_archive(st)
    current=st.session_state.get('_slate_active')
    blob=capture(st) if current else ''
    if current and st.session_state.get('dfs_format'):current['title']=st.session_state['dfs_format']+' · '+current['name'].replace('.csv','')
    records=st.session_state.setdefault('_slate_records',{})
    if current:
        current={**current,'snapshot':blob}
        records[current['id']]=current
        st.session_state['_slate_active']=current
    incoming=st.session_state.pop('_slate_incoming',None)
    if incoming:
        existing=records.get(incoming['id'],{})
        incoming={**incoming,'snapshot':existing.get('snapshot','')}
        records[incoming['id']]=incoming
        st.session_state['_slate_reopen']=incoming['id']
        st.session_state['_slate_pending']=incoming
        st.rerun()
    component=components.declare_component('simmah_loaded_slates',path=str(Path(__file__).parent/'components/slate_workspaces'))
    with host:
        event=component(active=current['id'] if current else None,current=current,snapshot=blob,
                        incoming=None,reopen=st.session_state.get('_slate_reopen'),records=list(records.values()),generation=st.session_state['_slate_generation'],
                        key='loaded_slates_browser',default=None)
        if event and event.get('error'):st.warning(event['error'])
        if event and event.get('event')!=st.session_state.get('_slate_last_event') and event.get('closed'):
            closed=str(event['closed'])
            records.pop(closed,None)
            st.session_state.pop('_slate_reopen',None)
            st.session_state['_slate_last_event']=event['event']
            if current and current['id']==closed:
                selected=event.get('selected')
                if selected and selected.get('id') in records:
                    st.session_state['_slate_pending']=records[selected['id']]
                else:
                    st.session_state['_slate_clear_active']=True
            st.rerun()

        if event and event.get('event')!=st.session_state.get('_slate_last_event') and event.get('selected'):
            for record in event.get('records',[]):
                if isinstance(record,dict) and all(k in record for k in ('id','data','name','snapshot')):
                    records.setdefault(record['id'],record)
            st.session_state['_slate_last_event']=event['event']
            st.session_state['_slate_pending']=records.get(event['selected']['id'],event['selected'])
            st.rerun()


def workspace_stop(st,host):
    finish_workspaces(st,host)
    st.stop()


def workspace_rerun(st,host):
    finish_workspaces(st,host)
    st.rerun()





