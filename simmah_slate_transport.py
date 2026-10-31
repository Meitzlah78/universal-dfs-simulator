"""Bounded, acknowledged transfers for browser-owned saved slate state."""
import hashlib
import json

CHUNK_CHARS = 1000000
MAX_PARTS = 256


def packet(transfer):
    index = transfer['index']
    return dict(id=transfer['id'], index=index, total=transfer['total'],
                data=transfer['raw'][index*CHUNK_CHARS:(index+1)*CHUNK_CHARS])


def outgoing(state, args, skip=False):
    """Bound server-to-browser frames too; never duplicate snapshots in metadata."""
    if skip:
        return {**args, 'current': None, 'snapshot': ''}
    raw = json.dumps(dict(current=args['current'], snapshot=args['snapshot']), separators=(',', ':'))
    if len(raw) <= CHUNK_CHARS:
        return args
    digest = hashlib.sha256(raw.encode()).hexdigest()
    base = {**args, 'current': None, 'snapshot': ''}
    if digest == state.get('_slate_download_saved'):
        return base
    total = (len(raw)+CHUNK_CHARS-1)//CHUNK_CHARS
    if total > MAX_PARTS:
        raise ValueError('Saved slate exceeds the supported transfer size; original browser data is unchanged.')
    transfer = dict(id=digest, raw=raw, total=total, index=0)
    state['_slate_download_transfer'] = transfer
    return {**base, 'download': packet(transfer)}


def receive_upload(state, part):
    """Accept one small browser message; restore nothing until every part arrives."""
    ident, index, total, data = (part.get(k) for k in ('id', 'index', 'total', 'data'))
    if (not isinstance(ident, str) or not 1 <= len(ident) <= 128
            or type(index) is not int or type(total) is not int
            or not 1 <= total <= MAX_PARTS or not 0 <= index < total
            or not isinstance(data, str) or len(data) > CHUNK_CHARS):
        raise ValueError('Invalid saved-slate transfer part.')
    ack = dict(id=ident, index=index)
    if state.get('_slate_upload_finished') == ident:
        return ack
    transfer = state.get('_slate_upload_transfer')
    if not transfer or transfer['id'] != ident:
        if index != 0:
            raise ValueError('Saved-slate transfer interrupted; select the tab again to retry.')
        transfer = dict(id=ident, total=total, parts=[])
        state['_slate_upload_transfer'] = transfer
    if transfer['total'] != total or index > len(transfer['parts']):
        raise ValueError('Saved-slate transfer parts arrived out of order.')
    if index == len(transfer['parts']):
        transfer['parts'].append(data)
    if len(transfer['parts']) == total:
        event = json.loads(''.join(transfer['parts']))
        if not isinstance(event, dict) or not isinstance(event.get('selected'), dict):
            raise ValueError('Saved-slate selection is incomplete.')
        state['_slate_upload_event'] = event
        state['_slate_upload_finished'] = ident
        state.pop('_slate_upload_transfer', None)
    return ack


def advance_download(state, ack):
    transfer = state.get('_slate_download_transfer')
    if not transfer or transfer['id'] != ack.get('id'):
        if state.get('_slate_download_saved') == ack.get('id'):
            return {'download_done': ack['id']}
        raise ValueError('Saved-slate download acknowledgement is stale.')
    index = ack.get('index')
    if type(index) is not int or index < 0 or index > transfer['index']:
        raise ValueError('Invalid saved-slate download acknowledgement.')
    if index == transfer['index']:
        transfer['index'] += 1
    if transfer['index'] == transfer['total']:
        state['_slate_download_saved'] = transfer['id']
        state.pop('_slate_download_transfer', None)
        return {'download_done': transfer['id']}
    return {'download': packet(transfer)}


def finish_upload(state, ident):
    if state.get('_slate_upload_finished') != ident or state.get('_slate_upload_applied') == ident:
        return
    event = state.pop('_slate_upload_event')
    selected = event['selected']
    if not all(k in selected for k in ('id', 'data', 'name', 'snapshot')):
        raise ValueError('Saved slate is missing its original input or snapshot.')
    records = state.setdefault('_slate_records', {})
    if event.get('closed'):
        records.pop(event['closed'], None)
    records[selected['id']] = selected
    state['_slate_pending'] = selected
    state['_slate_last_event'] = event['event']
    state['_slate_upload_applied'] = ident
    state['_slate_skip_transport_capture'] = True


def restart_download(state, ident):
    """A full page refresh can lose the browser's incomplete chunk buffer."""
    transfer = state.get('_slate_download_transfer')
    if transfer and transfer['id'] == ident:
        transfer['index'] = 0
        return {'download': packet(transfer)}
    if state.get('_slate_download_saved') == ident:
        return {'download_done': ident}
    raise ValueError('Saved-file transfer expired; reload the app to retry from the retained original.')


def restart_upload(state, ident):
    """Retry from the retained original, or consume an already complete upload."""
    if state.get('_slate_upload_finished') == ident:
        return True
    transfer = state.get('_slate_upload_transfer')
    if transfer and transfer['id'] == ident:
        state.pop('_slate_upload_transfer', None)
    return False


def handle_browser_transfer(st):
    """Run before expensive app work. Partial transfers render only an ack."""
    event = st.session_state.get('loaded_slates_browser') or {}
    if not isinstance(event, dict):
        return
    response = None
    try:
        if event.get('upload_part'):
            response = {'upload_ack': receive_upload(st.session_state, event['upload_part'])}
        elif event.get('download_ack'):
            response = advance_download(st.session_state, event['download_ack'])
        elif event.get('download_restart'):
            response = restart_download(st.session_state, event['download_restart'])
        elif event.get('upload_restart'):
            if restart_upload(st.session_state, event['upload_restart']):
                finish_upload(st.session_state, event['upload_restart'])
            st.session_state['_slate_skip_transport_capture'] = True
        elif event.get('upload_done'):
            finish_upload(st.session_state, event['upload_done'])
        elif event.get('download_received'):
            if st.session_state.get('_slate_download_received') != event['download_received']:
                st.session_state['_slate_download_received'] = event['download_received']
                st.session_state['_slate_skip_transport_capture'] = True
    except (ValueError, TypeError, KeyError) as exc:
        response = {'transport_error': str(exc)}
    if response is not None:
        from simmah_slate_workspaces import slate_component
        slate_component()(transport_only=True, **response, key='loaded_slates_browser', default=None)
        st.stop()
