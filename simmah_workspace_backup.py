"""Safe, lossless ZIP workspaces, independent of Streamlit session memory."""
import hashlib
import io
import json
import math
import os
import re
import shutil
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent / 'data' / 'workspace_recovery'
STAGING = Path(__file__).parent / 'static' / 'workspace_backups'
MAX_BYTES = 512 * 1024 * 1024
RECOVERY_CHUNK_BYTES = 750000
MAX_EXPANDED = 1024 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pack(payload):
    """No pickle, no 16 MiB omissions, and identical payloads have identical bytes."""
    files = {}
    def file(raw, suffix):
        name = digest(raw) + suffix
        files.setdefault(name, raw)
        return name
    def enc(value):
        if value is pd.NA: return {'t':'na'}
        if value is pd.NaT: return {'t':'nat'}
        if value is None or isinstance(value, (str, bool, int)): return value
        if isinstance(value, (float, np.floating)):
            return float(value) if math.isfinite(value) else {'t':'float','v':str(float(value))}
        if isinstance(value, np.integer): return int(value)
        if isinstance(value, np.bool_): return bool(value)
        if isinstance(value, pd.DataFrame):
            homogeneous = bool(len(value.columns)) and all(isinstance(d, np.dtype) and d == value.dtypes.iloc[0] and not d.hasobject for d in value.dtypes)
            data = enc(value.to_numpy()) if homogeneous else [enc(value.iloc[:, i].to_numpy()) for i in range(len(value.columns))]
            categories = {str(i):enc((value.iloc[:,i].cat.categories.tolist(),value.iloc[:,i].cat.ordered)) for i,d in enumerate(value.dtypes) if str(d)=='category'}
            return dict(t='frame', data=data, matrix=homogeneous, columns=enc(value.columns), index=enc(value.index), dtypes=list(map(str,value.dtypes)), categories=categories, attrs=enc(value.attrs))
        if isinstance(value, pd.Series): return dict(t='series', frame=enc(value.to_frame()), name=enc(value.name))
        if isinstance(value, pd.MultiIndex): return dict(t='multiindex', values=enc(value.tolist()), names=enc(value.names))
        if isinstance(value, pd.RangeIndex): return dict(t='rangeindex', start=value.start, stop=value.stop, step=value.step, name=enc(value.name))
        if isinstance(value, pd.Index): return dict(t='index', values=enc(value.to_numpy()), name=enc(value.name))
        if isinstance(value, np.ndarray):
            if value.dtype.hasobject: return dict(t='objects', shape=list(value.shape), values=[enc(v) for v in value.flat])
            stream=io.BytesIO();np.save(stream,value,allow_pickle=False)
            return dict(t='array', file=file(stream.getvalue(),'.npy'))
        if isinstance(value, pd.Timestamp): return dict(t='timestamp',v=value.isoformat(),zone=str(value.tz) if value.tz else None)
        if isinstance(value, datetime): return dict(t='datetime',v=value.isoformat(),zone=getattr(value.tzinfo,'key',None))
        if isinstance(value, date): return dict(t='date',v=value.isoformat())
        if isinstance(value, bytes): return dict(t='bytes',file=file(value,'.bin'))
        if hasattr(value,'getvalue') and hasattr(value,'name'): return dict(t='upload', name=value.name, data=enc(bytes(value.getvalue())))
        if isinstance(value, dict):
            from simmah_slate_workspaces import private_key
            return dict(t='dict',v=[[enc(k),enc(v)] for k,v in value.items() if not (isinstance(k,str) and private_key(k))])
        if isinstance(value,(list,tuple,set)):
            items=[enc(v) for v in value]
            if isinstance(value,set): items.sort(key=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')))
            return dict(t=type(value).__name__,v=items)
        raise TypeError('Unsupported workspace value: '+type(value).__name__)
    tree=enc(payload)
    manifest=json.dumps(dict(schema=1,payload=tree),separators=(',',':'),allow_nan=False).encode()
    if len(manifest) + sum(map(len, files.values())) > MAX_EXPANDED:
        raise ValueError('Workspace expands beyond the supported limit')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as bundle:
        for name,raw in [('manifest.json',manifest),*sorted(files.items())]:
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            bundle.writestr(info,raw,compresslevel=1)
    raw=out.getvalue()
    if len(raw)>MAX_BYTES: raise ValueError(f'Workspace exceeds the {MAX_BYTES // (1024 * 1024)} MiB backup limit')
    return raw


def _unpack(raw):
    if len(raw)>MAX_BYTES: raise ValueError('Workspace exceeds the backup limit')
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        if len(bundle.infolist())>20000 or sum(i.file_size for i in bundle.infolist())>MAX_EXPANDED:
            raise ValueError('Workspace expands beyond the supported limit')
        manifest=json.loads(bundle.read('manifest.json'))
        if manifest.get('schema')!=1: raise ValueError('Unknown workspace version')
        checked={}
        def attachment(name):
            if not re.fullmatch(r'[a-f0-9]{64}\.(npy|bin)',name): raise ValueError('Invalid workspace attachment')
            if name not in checked:
                content=bundle.read(name)
                if digest(content)!=name.split('.')[0]: raise ValueError('Workspace attachment failed verification')
                checked[name]=content
            return checked[name]
        def dec(node):
            if not isinstance(node,dict): return node
            kind=node['t']
            if kind=='na': return pd.NA
            if kind=='nat': return pd.NaT
            if kind=='float': return float(node['v'])
            if kind=='array':
                content=attachment(node['file']);stream=io.BytesIO(content)
                version=np.lib.format.read_magic(stream)
                if version==(1,0): shape,order,dtype=np.lib.format.read_array_header_1_0(stream)
                elif version==(2,0): shape,order,dtype=np.lib.format.read_array_header_2_0(stream)
                else: raise ValueError('Unsupported workspace array version')
                size=math.prod(shape)*dtype.itemsize
                if dtype.hasobject or size>MAX_EXPANDED or size!=len(content)-stream.tell():
                    raise ValueError('Invalid workspace array dimensions')
                return np.load(io.BytesIO(content),allow_pickle=False)
            if kind=='bytes': return attachment(node['file'])
            if kind=='objects':
                shape=node['shape']
                if not isinstance(shape,list) or any(type(n) is not int or n<0 for n in shape) or math.prod(shape)!=len(node['values']) or math.prod(shape)*8>MAX_EXPANDED:
                    raise ValueError('Invalid object array dimensions')
                result=np.empty(tuple(shape),object)
                for i,v in enumerate(node['values']): result.flat[i]=dec(v)
                return result
            if kind=='dict': return {dec(k):dec(v) for k,v in node['v']}
            if kind in ('list','tuple','set'): return {'list':list,'tuple':tuple,'set':set}[kind](dec(v) for v in node['v'])
            if kind=='date': return date.fromisoformat(node['v'])
            if kind in ('datetime','timestamp'):
                result=pd.Timestamp(node['v']) if kind=='timestamp' else datetime.fromisoformat(node['v'])
                if node.get('zone'): result=result.tz_convert(node['zone']) if kind=='timestamp' else result.astimezone(ZoneInfo(node['zone']))
                return result
            if kind=='rangeindex': return pd.RangeIndex(node['start'],node['stop'],node['step'],name=dec(node['name']))
            if kind=='index': return pd.Index(dec(node['values']),name=dec(node['name']))
            if kind=='multiindex': return pd.MultiIndex.from_tuples(dec(node['values']),names=dec(node['names']))
            if kind=='frame':
                columns=dec(node['columns']);index=dec(node['index'])
                if node['matrix']: result=pd.DataFrame(dec(node['data']),index=index,columns=columns)
                else:
                    arrays=[]
                    for i,(data,dtype) in enumerate(zip(node['data'],node['dtypes'])):
                        values=dec(data)
                        if str(i) in node.get('categories',{}):
                            categories,ordered=dec(node['categories'][str(i)]);values=pd.Categorical(values,categories=categories,ordered=ordered)
                        else: values=pd.array(values,dtype=dtype)
                        arrays.append(pd.Series(values,index=index))
                    result=pd.concat(arrays,axis=1) if arrays else pd.DataFrame(index=index)
                    result.columns=columns
                result.attrs=dec(node['attrs']);return result
            if kind=='series':
                result=dec(node['frame']).iloc[:,0];result.name=dec(node['name']);return result
            if kind=='upload':
                from simmah_slate_workspaces import StoredUpload
                return StoredUpload(dec(node['data']),node['name'])
            raise ValueError('Unknown workspace value type')
        result=dec(manifest['payload'])
    if not isinstance(result,dict) or not isinstance(result.get('record'),dict) or not isinstance(result.get('checkpoint'),dict):
        raise ValueError('Incomplete workspace backup')
    return result


def unpack(raw):
    try:
        return _unpack(raw)
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError, EOFError) as exc:
        raise ValueError('Invalid or damaged workspace backup') from exc


def path_for(owner, token, root=None):
    if not re.fullmatch('[a-f0-9]{32}',str(owner)) or not re.fullmatch('[a-f0-9]{32}',str(token)):
        raise ValueError('Invalid private workspace reference')
    return Path(root or ROOT)/owner/(token+'.zip')


def write_backup(owner, raw, root=None, token=None):
    token=token or uuid.uuid4().hex
    path=path_for(owner,token,root);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_bytes(raw);os.replace(temporary,path)
    return dict(token=token,digest=digest(raw),bytes=len(raw))


def load_backup(owner, reference, root=None):
    raw=path_for(owner,reference['token'],root).read_bytes()
    if digest(raw)!=reference['digest']: raise ValueError('Workspace backup failed verification')
    return unpack(raw)


def stage_backup(owner, reference):
    """Expose a temporary capability download; keep the durable host copy private.

    Confirmed downloads leave the static folder, keeping Streamlit's startup
    static-folder size check independent of accumulated workspace history.
    """
    source=path_for(owner,reference['token'])
    target=path_for(owner,reference['token'],STAGING)
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            try: os.link(source,temporary)
            except OSError: shutil.copyfile(source,temporary)
            os.replace(temporary,target)
        finally: temporary.unlink(missing_ok=True)


def unstage_backup(owner, token):
    path_for(owner,token,STAGING).unlink(missing_ok=True)
