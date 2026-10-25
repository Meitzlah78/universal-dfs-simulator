"""Archive all original salary/entries/contest uploads independently of tabs."""
import base64
import hashlib
import json
import os
import uuid
from pathlib import Path

from simmah_input_archive import Archive, S3Backup, inspect_input, sha256

PREFIX = '_slate_archive_'


def capture_upload(st, upload, key='upload'):
    if upload is None:
        return
    values = upload if isinstance(upload,(list,tuple)) else [upload]
    pending = st.session_state.setdefault(PREFIX+'pending',{})
    known = st.session_state.setdefault(PREFIX+'seen',set())
    for value in values:
        if not hasattr(value,'getvalue'):
            continue
        raw = value.getvalue()
        digest = sha256(raw)
        if digest in known:
            continue
        # Preserve original bytes before parsing. Even a malformed source is
        # recoverable for diagnosis instead of disappearing on the error path.
        pending[digest] = dict(digest=digest,filename=value.name,raw=raw,upload_key=str(key))
        known.add(digest)


def archive_for(st):
    owner = st.session_state.get(PREFIX+'owner')
    if not owner:
        return None
    root = os.environ.get('SIMMAH_ARCHIVE_DIR',str(Path(__file__).resolve().parent/'data'/'input_archive'))
    config = {}
    try:
        config = dict(st.secrets.get('input_archive',{}))
    except (FileNotFoundError,KeyError):
        pass
    backup = S3Backup(config) if config.get('bucket') else None
    return Archive(root,owner,backup)


def process_event(st, event):
    if not event or event.get('event') == st.session_state.get(PREFIX+'last_event'):
        return False
    state = st.session_state
    state[PREFIX+'last_event'] = event.get('event')
    if event.get('error'):
        state[PREFIX+'browser_error'] = str(event['error'])
    owner = event.get('owner')
    if not isinstance(owner,str) or len(owner) != 32 or any(c not in '0123456789abcdef' for c in owner):
        return False
    state.pop(PREFIX+'browser_error',None)
    # The browser identity persists separately from active/closed slate tabs.
    changed = state.get(PREFIX+'owner') != owner or state.get(PREFIX+'browser_hashes',[]) != list(event.get('hashes',[]))
    state[PREFIX+'owner'] = owner
    state[PREFIX+'browser_hashes'] = list(event.get('hashes',[]))
    state[PREFIX+'persistent_storage'] = bool(event.get('persistent'))
    ack = state.setdefault(PREFIX+'browser_acked',set())
    ack.update(event.get('hashes',[]))
    for record in event.get('restored',[]):
        raw = base64.b64decode(record['data'],validate=True)
        if sha256(raw) != record.get('digest'):
            state[PREFIX+'browser_error'] = 'Saved file failed its SHA-256 verification'
            continue
        state.setdefault(PREFIX+'pending',{})[record['digest']] = dict(
            digest=record['digest'],filename=record['filename'],raw=raw,upload_key='browser_recovery')
        changed = True
    return changed


def flush_pending(st, archive):
    pending = st.session_state.setdefault(PREFIX+'pending',{})
    for digest, record in list(pending.items()):
        st.session_state.setdefault(PREFIX+'browser_outbox',{})[digest] = dict(
            digest=digest,filename=record['filename'],data=base64.b64encode(record['raw']).decode())
        try:
            saved = archive.put(record['raw'],record['filename'],metadata=record.get('metadata'))
            st.session_state.setdefault(PREFIX+'browser_outbox',{})[digest] = dict(
                digest=digest,filename=saved['filename'],data=base64.b64encode(record['raw']).decode(),
                saved_at=saved['saved_at'],metadata=saved['metadata'])
            pending.pop(digest)
            st.session_state.pop(PREFIX+'server_error',None)
        except Exception as error:
            # A failed durable mirror never becomes a successful cloud save.
            st.session_state[PREFIX+'server_error'] = 'Archive save failed: '+str(error)


def render_archive(st):
    import streamlit.components.v1 as components
    from simmah_archive_jobs import queue_jobs
    state = st.session_state
    component = components.declare_component('simmah_input_archive',path=str(Path(__file__).parent/'components'/'input_archive'))
    archive = None
    try:
        archive = archive_for(st)
        if archive:
            if archive.backup and not state.get(PREFIX+'remote_checked'):
                archive.recover_remote_index()
                state[PREFIX+'remote_checked'] = True
            flush_pending(st,archive)
            # Existing workspace salary originals are backfilled automatically.
            for record in state.get('_slate_records',{}).values():
                capture_upload(st,_Upload(base64.b64decode(record['data']),record['name']),'loaded_slate_backfill')
            flush_pending(st,archive)
            queue_jobs(archive)
    except Exception as error:
        state[PREFIX+'server_error'] = 'Archive unavailable: '+str(error)
    files = archive.files() if archive else []
    hashes = {r['digest'] for r in files}
    ack = state.get(PREFIX+'browser_acked',set())
    outbox = state.setdefault(PREFIX+'browser_outbox',{})
    # Include newly finished reports and existing server originals after a
    # browser reconnect. Four at a time bounds Streamlit message size.
    for record in files:
        if len([h for h in outbox if h not in ack]) >= 4:
            break
        digest = record['digest']
        if digest not in ack and digest not in outbox:
            outbox[digest] = dict(digest=digest,filename=record['filename'],
                                  data=base64.b64encode(archive.get(digest)).decode(),
                                  metadata=record['metadata'],saved_at=record['saved_at'])
    outgoing = [r for digest,r in outbox.items() if digest not in ack][:4]
    need = [h for h in state.get(PREFIX+'browser_hashes',[]) if h not in hashes][:4]
    with st.expander('Saved files & automatic calibration',expanded=False):
        event = component(records=outgoing,restore=need,key=PREFIX+'browser',default=None)
        if process_event(st,event):
            st.rerun()
        for digest in list(outbox):
            if digest in state.get(PREFIX+'browser_acked',set()):
                outbox.pop(digest,None)
        if state.get(PREFIX+'browser_error'):
            st.error(state[PREFIX+'browser_error'])
        if state.get(PREFIX+'server_error'):
            st.error(state[PREFIX+'server_error'])
        if not archive:
            st.caption('Preparing your private file archive. Uploaded originals are waiting to be saved.')
            return
        cloud = sum(bool(r['remote_ok']) for r in files)
        st.caption(f'{len(files)} files and reports saved on this server · {len(hashes & ack)} confirmed in this browser · {cloud} backed up to durable storage.')
        if not archive.backup:
            st.warning('Durable cloud backup is not configured. Originals are retained in this browser and on this server; clearing browser data or rebuilding the host can remove those copies. Download a backup below or configure a private archive bucket.')
        st.caption('Closing a slate tab does not delete this archive. Calibration is retrospective and does not change live projections or opponent-field settings.')
        jobs = archive.jobs()
        # Heavy diagnostics are cached once per immutable hash.
        for record in files:
            meta = record['metadata']
            label = record['filename']+' — '+str(meta.get('kind','saved'))
            st.write(label)
            if meta.get('kind') == 'contest':
                audited = archive.audit(record)
                if audited['status'] == 'audited':
                    st.caption(f"{audited['complete_entries']:,} complete entries · {audited['unique_rosters']:,} unique rosters · {audited['observed_equal_roster_pairs']:,} identical pairs")
                else:
                    st.caption(audited['detail'])
                matching = [j for j in jobs if j['contest_digest']==record['digest']]
                if not matching:
                    st.caption('Waiting for a matching original entries/salary file with a verified contest ID. No current-slate salary substitution is used.')
                    options=[r for r in files if r['metadata'].get('embedded_salary') and r['metadata'].get('platform')==meta.get('platform') and r['metadata'].get('mode')==meta.get('mode')]
                    if options:
                        chosen=st.selectbox('Historical salary file',options,format_func=lambda r:r['filename']+' · '+', '.join(r['metadata'].get('teams',[])),key=PREFIX+'pair_'+record['digest'])
                        confirmed=st.checkbox('I verified these files belong to the same historical slate',key=PREFIX+'confirm_'+record['digest'])
                        if st.button('Link files and queue calibration',disabled=not confirmed,key=PREFIX+'link_'+record['digest']):
                            try:
                                archive.bind_salary(record['digest'],chosen['digest'])
                                st.rerun()
                            except Exception as error:
                                st.error(str(error))
            st.download_button('Download original',archive.get(record['digest']),file_name=record['filename'],
                               key=PREFIX+'original_'+record['digest'])
        if jobs:
            display=[]
            for job in jobs:
                detail=job['detail'];residual='—'
                try:
                    parsed=json.loads(detail)
                    residual=format(parsed['final_float64']['original_residual_max'],'.3g')
                    detail='Historical targets verified' if job['state']=='verified_convergence' else 'Target gates not met'
                except (ValueError,KeyError,TypeError):pass
                display.append({'Calibration':job['state'].replace('_',' '),'Maximum target error':residual,'Details':detail})
            st.dataframe(display,hide_index=True,use_container_width=True)
            for job in jobs:
                result = archive.root/'jobs'/job['id']/'result.zip'
                if result.exists():
                    st.download_button('Download calibration report',result.read_bytes(),
                        file_name='calibration-'+job['id'][:12]+'.zip',key=PREFIX+'result_'+job['id'])
                if job['state'] in ('failed','stopped_without_verified_convergence','blocked_runtime'):
                    if st.button('Retry calibration with current settings',key=PREFIX+'retry_'+job['id']):
                        archive.set_job(job['id'],'queued','Explicit retry requested; earlier attempt files retained.')
                        st.rerun()
        # Refresh only this status area while a subprocess is active.
        if any(j['state'] in ('queued','running','paused_for_build') for j in jobs):
            @st.fragment(run_every='5s')
            def running_status():
                for j in archive.jobs():
                    st.caption('Calibration: '+j['state'])
            running_status()
        if st.button('Prepare complete archive backup',key=PREFIX+'prepare_backup'):
            state[PREFIX+'backup'] = archive.backup_zip()
        if state.get(PREFIX+'backup'):
            st.download_button('Download all originals and calibration reports',state[PREFIX+'backup'],
                               file_name='simmah-input-archive.zip',mime='application/zip',key=PREFIX+'backup_download')
        restored = st.file_uploader('Restore a complete archive backup',type=['zip'],key=PREFIX+'restore_upload')
        if restored is not None:
            digest = sha256(restored.getvalue())
            if digest != state.get(PREFIX+'restored_backup'):
                try:
                    count = archive.restore_zip(restored.getvalue())
                    state[PREFIX+'restored_backup'] = digest
                    st.success(f'Restored {count} original files. Matching historical fits will be queued automatically.')
                    st.rerun()
                except Exception as error:
                    st.error('Backup restoration failed: '+str(error))


class _Upload:
    def __init__(self, raw, name):
        self.raw, self.name = raw, name

    def getvalue(self):
        return self.raw

