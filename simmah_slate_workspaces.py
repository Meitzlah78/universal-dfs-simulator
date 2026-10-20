"""Browser-owned loaded slates. JSON only; no entries sent to a shared database."""
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
    return (key.endswith('_remove_restored') or key.startswith('nba_projection_upload_')
            or key in {'nba_build','nba_field_download','nba_entries_download',
                       'nba_fast_late_swap','nba_late_swap_upload','nba_late_swap_download',
                       'loaded_slates_browser','sticky_refresh_projections'})


def snapshot(state, transient_keys=()):
    values={};omitted=[]
    for key in list(state):
        if str(key).startswith(('_slate_','$$','universal_slate_setup_file')) or private_key(key):continue
        if key in transient_keys or transient_key(key):continue
        if key in {'loaded_slates_browser','sticky_refresh_projections','refresh_projections_requested','projection_updates_found','injury_updates_found'}:continue
        value=state[key]
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
    pending=st.session_state.pop('_slate_pending',None)
    records=st.session_state.setdefault('_slate_records',{})
    if pending:
        pending=records.get(pending['id'],pending)
        try:
            restore(st.session_state,pending.get('snapshot',''))
            st.session_state['_slate_active']=pending
            records[pending['id']]=pending
        except (ValueError,TypeError,KeyError,OSError) as exc:st.warning('Saved slate could not restore: '+str(exc))
    st.session_state.setdefault('_slate_generation',uuid.uuid4().hex)
    return st.container()


def select_upload(st,upload):
    if upload is not None:
        digest=hashlib.sha256(upload.getvalue()).hexdigest()
        if digest!=st.session_state.get('_slate_seen_upload'):
            st.session_state['_slate_seen_upload']=digest
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
    value=st.file_uploader(label,*args,**kwargs)
    if kwargs.get('accept_multiple_files'):return value  # History imports remain explicit actions.
    key=str(kwargs.get('key',label));saved=st.session_state.setdefault('_slate_restored_uploads',{})
    seen=st.session_state.setdefault('_slate_widget_seen',{})
    if value is not None:saved[key]=value
    elif seen.get(key):saved.pop(key,None)
    seen[key]=value is not None
    if value is None and key in saved:
        st.caption('Restored file: '+saved[key].name)
        if st.button('Remove restored file',key=key+'_remove_restored'):
            saved.pop(key,None)
    return value if value is not None else saved.get(key)


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
        st.session_state['_slate_pending']=incoming
        st.rerun()
    component=components.declare_component('simmah_loaded_slates',path=str(Path(__file__).parent/'components/slate_workspaces'))
    with host:
        event=component(active=current['id'] if current else None,current=current,snapshot=blob,
                        incoming=None,records=list(records.values()),generation=st.session_state['_slate_generation'],
                        key='loaded_slates_browser',default=None)
        if event and event.get('error'):st.warning(event['error'])
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
