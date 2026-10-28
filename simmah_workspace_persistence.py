"""Browser-confirmed autosaves; large backups bypass Streamlit's WebSocket."""
import base64
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from simmah_workspace_backup import pack, unpack, unpack_file, digest, write_backup, load_backup, path_for, stage_backup, unstage_backup, MAX_BYTES, RECOVERY_CHUNK_BYTES

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='workspace-backup')
KEY = '_slate_backup_browser'


def component():
    import streamlit.components.v1 as components
    return components.declare_component('simmah_workspace_backup_v1',
        path=str(Path(__file__).parent / 'components' / 'workspace_backup'))


def apply_payload(state, payload):
    row = payload['record']
    if not all(k in row for k in ('id', 'name', 'data')):
        raise ValueError('Backup is missing the original slate upload')
    row['_session_checkpoint'] = payload['checkpoint']
    state.setdefault('_slate_records', {})[row['id']] = row
    state['_slate_pending'] = row


def receive_backup_part(state, part):
    """Decode only one bounded frame; spool a verified archive to disk before restore."""
    if state.get('_slate_backup_restored') and part.get('id') == state['_slate_backup_restored']:
        return
    ref = state.get('_slate_backup_restore')
    if not ref or type(ref.get('bytes')) is not int or not 0 < ref['bytes'] <= MAX_BYTES:
        raise ValueError('Invalid backup recovery reference')
    ident, index, total, data = (part.get(k) for k in ('id', 'index', 'total', 'data'))
    expected = (ref['bytes'] + RECOVERY_CHUNK_BYTES - 1) // RECOVERY_CHUNK_BYTES
    if (not isinstance(ident, str) or not 1 <= len(ident) <= 128
            or type(index) is not int or type(total) is not int or total != expected
            or not 0 <= index < total or not isinstance(data, str)
            or len(data) > 4 * ((RECOVERY_CHUNK_BYTES + 2) // 3)):
        raise ValueError('Invalid backup recovery part')
    decoded = base64.b64decode(data, validate=True)
    size = min(RECOVERY_CHUNK_BYTES, ref['bytes'] - index * RECOVERY_CHUNK_BYTES)
    if len(decoded) != size:
        raise ValueError('Incomplete backup recovery part')
    path = path_for(state['_slate_backup_owner'], ref['token'])
    temporary = path.with_suffix('.restore')
    transfer = state.get('_slate_backup_transfer')
    if not transfer or transfer['id'] != ident or transfer['token'] != ref['token']:
        if index != 0:
            raise ValueError('Backup recovery interrupted; retry from the first part')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(b'')
        transfer = dict(id=ident, token=ref['token'], index=0)
        state['_slate_backup_transfer'] = transfer
    if index > transfer['index']:
        raise ValueError('Backup recovery parts arrived out of order')
    if index == transfer['index']:
        with temporary.open('r+b') as stream:
            stream.seek(index * RECOVERY_CHUNK_BYTES)
            stream.write(decoded)
        if index == total - 1:
            payload = unpack_file(temporary, expected_digest=ref['digest'],
                                  expected_bytes=ref['bytes'])
            if not all(k in payload['record'] for k in ('id', 'name', 'data')):
                raise ValueError('Backup is missing the original slate upload')
            if payload['record']['id'] != ref['id']:
                raise ValueError('Restored slate does not match the requested backup')
            os.replace(temporary, path)
            apply_payload(state, payload)
            state.pop('_slate_backup_restore', None)
            state.pop('_slate_backup_transfer', None)
            state['_slate_backup_restored'] = ident
        else:
            transfer['index'] += 1
    state['_slate_backup_ack'] = dict(id=ident, index=index)


def consume(st):
    state = st.session_state
    event = state.get(KEY) or {}
    if not isinstance(event, dict) or event.get('event') == state.get('_slate_backup_event'):
        return
    state['_slate_backup_event'] = event.get('event')
    if event.get('error'):
        state['_slate_backup_error'] = event['error']
    if event.get('boot') and not state.get('_slate_backup_booted'):
        boot = event['boot']
        owner = boot['owner']
        path_for(owner, '0'*32)  # Validate capability identity before using paths.
        state['_slate_backup_owner'] = owner
        state['_slate_backup_booted'] = True
        records = state.setdefault('_slate_records', {})
        for row in boot.get('records', []):
            if row.get('open') and row['id'] not in records:
                records[row['id']] = {**row, '_backup_reference': row}
                state.setdefault('_slate_backup_refs', {})[row['id']] = row
        active = boot.get('active')
        if not state.get('_slate_active') and records:
            state['_slate_pending'] = records.get(active, next(reversed(records.values())))
    for sid, ref in event.get('saved', {}).items():
        expected = state.get('_slate_backup_refs', {}).get(sid)
        if expected and ref.get('digest') == expected['digest'] and ref.get('revision') == expected['revision']:
            previous = state.setdefault('_slate_backup_confirmed', {}).get(sid)
            state['_slate_backup_confirmed'][sid] = ref
            unstage_backup(state['_slate_backup_owner'], ref['token'])
            state.pop('_slate_backup_error', None)
            obsolete = state.setdefault('_slate_backup_obsolete', {}).pop(sid, [])
            if previous: obsolete.append(previous)
            for old in obsolete:
                if old['token'] != ref['token']:
                    path_for(state['_slate_backup_owner'], old['token']).unlink(missing_ok=True)
                    unstage_backup(state['_slate_backup_owner'], old['token'])
    if event.get('backup_part'):
        receive_backup_part(state, event['backup_part'])
    part = event.get('upload_part')
    if part:
        from simmah_slate_transport import receive_upload
        ack = receive_upload(state, part)
        state['_slate_backup_ack'] = ack
        incoming = state.pop('_slate_upload_event', None)
        if incoming:
            selected = incoming['selected']
            raw = base64.b64decode(selected['data'], validate=True)
            requested = state.get('_slate_backup_restore')
            if not requested or selected['id'] != requested['id'] or digest(raw) != requested['digest']:
                raise ValueError('Restored backup failed verification')
            payload = unpack(raw)
            if payload['record']['id'] != selected['id']:
                raise ValueError('Restored slate does not match the requested backup')
            write_backup(state['_slate_backup_owner'], raw, token=requested['token'])
            apply_payload(state, payload)
            state.pop('_slate_backup_restore', None)
            state['_slate_backup_restored'] = part['id']


def args_for(state):
    records = state.get('_slate_records', {})
    active = state.get('_slate_active') or {}
    refs = state.get('_slate_backup_refs', {})
    return dict(max_backup_bytes=MAX_BYTES, recovery_chunk_bytes=RECOVERY_CHUNK_BYTES,
        generation=state['_slate_generation'], ready=bool(state.get('_slate_backup_booted')),
        owner=state.get('_slate_backup_owner'), active=active.get('id'),
        records=[dict(id=r['id'],name=r['name'],title=r.get('title',r['name'])) for r in records.values()],
        backups=[{**ref, 'id':sid, 'name':records[sid]['name'], 'title':records[sid].get('title',records[sid]['name']),
                  'url':'app/static/workspace_backups/'+state['_slate_backup_owner']+'/'+ref['token']+'.zip'}
                 for sid,ref in refs.items() if sid in records],
        busy=bool(state.get('_slate_backup_future') or state.get('_slate_backup_queue') or state.get('_slate_export_jobs')),
        error=state.get('_slate_backup_error'), restore=state.get('_slate_backup_restore'),
        upload_ack=state.get('_slate_backup_ack'), restored=state.get('_slate_backup_restored'))


def begin(st):
    state = st.session_state
    state['_slate_fresh_mode'] = True
    state.setdefault('_slate_generation', uuid.uuid4().hex)
    try:
        consume(st)
        pending = state.get('_slate_pending')
        if pending and pending.get('_backup_reference') and '_session_checkpoint' not in pending:
            ref = pending['_backup_reference']
            try:
                payload = load_backup(state['_slate_backup_owner'], ref)
                apply_payload(state, payload)
            except (FileNotFoundError, ValueError):
                state['_slate_backup_restore'] = ref
                state.pop('_slate_pending', None)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        state['_slate_backup_error'] = 'Recovery needs attention: '+str(exc)
    if not state.get('_slate_backup_booted') or state.get('_slate_backup_restore'):
        component()(**args_for(state), key=KEY, default=None)
        if state.get('_slate_backup_error'):
            st.error(state['_slate_backup_error'])
            if st.button('Continue without restoring', key='_slate_backup_continue'):
                state['_slate_backup_booted'] = True
                state.pop('_slate_backup_restore', None)
                state.pop('_slate_pending', None)
                state['_slate_records'] = {}
                st.rerun()
        st.stop()


def save_job(owner, payload, previous, revision):
    raw = pack(payload)
    if previous and digest(raw) == previous['digest']:
        reference = {**previous, 'revision':revision}
    else:
        reference = {**write_backup(owner, raw), 'revision':revision}
    stage_backup(owner, reference)
    return reference


def advance(state):
    future = state.get('_slate_backup_future')
    if future and future.done():
        sid = state.pop('_slate_backup_saving')
        state.pop('_slate_backup_future', None)
        try:
            refs = state.setdefault('_slate_backup_refs', {})
            if sid in refs:
                state.setdefault('_slate_backup_obsolete', {}).setdefault(sid, []).append(refs[sid])
            refs[sid] = future.result()
            state.pop('_slate_backup_error', None)
        except Exception as exc:
            state['_slate_backup_error'] = 'Changes are not saved: '+str(exc)
    queue = state.setdefault('_slate_backup_queue', {})
    if not state.get('_slate_backup_future') and queue:
        sid = next(iter(queue))
        payload, revision = queue.pop(sid)
        state['_slate_backup_saving'] = sid
        state['_slate_backup_future'] = _POOL.submit(save_job, state['_slate_backup_owner'], payload,
            state.get('_slate_backup_refs', {}).get(sid), revision)


def schedule(st):
    from simmah_session_workspaces import checkpoint, fingerprint
    state = st.session_state
    if not state.get('_slate_backup_owner'):
        return
    current = state.get('_slate_active')
    if current:
        try:
            view = checkpoint(st, copy=False)
            signature = fingerprint(view)
            signatures = state.setdefault('_slate_backup_signatures', {})
            if current['id'] not in signatures and current.get('_session_checkpoint') is not None:
                signatures[current['id']] = fingerprint(current['_session_checkpoint'])
                if (signatures[current['id']] == signature
                        and current['id'] in state.get('_slate_backup_refs', {})):
                    state.setdefault('_slate_backup_captured', {})[current['id']] = current['_session_checkpoint']
            if signatures.get(current['id']) != signature:
                current['_session_checkpoint'] = checkpoint(st)
                signatures[current['id']] = signature
        except Exception as exc:
            state['_slate_backup_error'] = 'Changes are not saved: '+str(exc)
            return
    for sid, row in state.get('_slate_records', {}).items():
        cp = row.get('_session_checkpoint')
        if cp is None or state.setdefault('_slate_backup_captured', {}).get(sid) is cp:
            continue
        state['_slate_backup_captured'][sid] = cp
        revision = state.get('_slate_backup_revision', 0)+1
        state['_slate_backup_revision'] = revision
        clean = {k:v for k,v in row.items() if not k.startswith('_') and k != 'snapshot'}
        state.setdefault('_slate_backup_queue', {})[sid] = (dict(record=clean, checkpoint=cp),revision)
    advance(state)


def render(st, host):
    # Fragment reruns poll disk work and acknowledgements without rerunning models
    # or deleting the main page's widgets during a multi-part save.
    @st.fragment(run_every=1)
    def status():
        state = st.session_state
        event = state.get(KEY) or {}
        if isinstance(event,dict) and (event.get('boot') or event.get('upload_part') or event.get('backup_part')) and event.get('event') != state.get('_slate_backup_event'):
            st.rerun(scope='app')
        consume(st)
        from simmah_export_history import finish_exports
        if finish_exports(st):
            schedule(st)
        advance(state)
        component()(**args_for(state), key=KEY, default=None)
        if state.get('_slate_backup_error'):
            for sid, ref in state.get('_slate_backup_refs', {}).items():
                path = path_for(state['_slate_backup_owner'], ref['token'])
                if path.exists():
                    st.download_button('Download last recovery backup', path.read_bytes(), on_click='ignore',
                        file_name='simmah-workspace-'+sid+'.zip', mime='application/zip',
                        key='_slate_backup_download_'+sid)
        if not state.get('_slate_records') or state.get('_slate_backup_error'):
            with st.expander('Restore a recovery backup'):
                uploaded = st.file_uploader('Simmah workspace backup', type=['zip'], key='_slate_backup_import')
                if uploaded is not None:
                    raw = uploaded.getvalue()
                    fingerprint = digest(raw)
                    if state.get('_slate_backup_imported') != fingerprint:
                        try:
                            payload = unpack(raw)
                            apply_payload(state, payload)
                            state['_slate_backup_imported'] = fingerprint
                            st.rerun(scope='app')
                        except (ValueError, KeyError, TypeError, OSError) as exc:
                            st.error('Backup could not restore: '+str(exc))
    with host:
        status()
