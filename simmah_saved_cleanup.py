"""User-triggered, date-scoped cleanup before automatic restoration starts."""
from datetime import datetime
from pathlib import Path
import re
import shutil
from zoneinfo import ZoneInfo

KEY = '_slate_cleanup_browser'


def today():
    return datetime.now(ZoneInfo('America/New_York')).date().isoformat()


def matches(record, day):
    name = record.get('filename', record.get('name', ''))
    match = re.search(r'(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)', name)
    stamp = record.get('saved_at') or (record.get('updated', 0) / 1000)
    date = '-'.join(match.groups()) if match else (
        datetime.fromtimestamp(stamp, ZoneInfo('America/New_York')).date().isoformat() if stamp else '')
    platform = (record.get('metadata') or {}).get('platform', '') or ''
    return date == day and bool(re.search(
        r'DraftKings|FanDuel|DKEntries|\bDK\b|\bFD\b',
        platform + ' ' + name + ' ' + record.get('title', ''), re.I))


def clear_archive(archive, day):
    """Delete only matching originals and their dependent calibration reports."""
    rows = [r for r in archive.files() if matches(r, day)]
    targets = {r['digest'] for r in rows}
    jobs = [j for j in archive.jobs() if j['salary_digest'] in targets or j['contest_digest'] in targets]
    job_ids = {j['id'] for j in jobs}
    targets.update(r['digest'] for r in archive.files() if r['metadata'].get('job_id') in job_ids)
    from simmah_archive_jobs import _LOCK, _SCHEDULED
    with _LOCK:
        scheduled = any((str(archive.root), jid) in _SCHEDULED for jid in job_ids)
    if scheduled or any(j['state'] in ('running', 'paused_for_build') for j in jobs):
        raise ValueError('A calibration is still running. Cleanup can be retried when it finishes.')
    # Remove the remote index first so originals cannot be resurrected on reboot.
    if archive.backup:
        for digest in targets:
            for key in (f'metadata/{digest}.json', f'inputs/{digest}'):
                archive.backup.client.delete_object(Bucket=archive.backup.bucket,
                    Key=f'{archive.backup.prefix}/{archive.owner}/{key}')
        for jid in job_ids:
            archive.backup.client.delete_object(Bucket=archive.backup.bucket,
                Key=f'{archive.backup.prefix}/{archive.owner}/calibrations/{jid}.zip')
    with archive.connect() as db:
        for job in jobs:
            db.execute('DELETE FROM jobs WHERE id=?', (job['id'],))
        for digest in targets:
            db.execute('DELETE FROM files WHERE digest=?', (digest,))
    for digest in targets:
        (archive.root / 'objects' / digest).unlink(missing_ok=True)
        (archive.root / 'audits' / (digest + '.json')).unlink(missing_ok=True)
    for job in jobs:
        shutil.rmtree(archive.root / 'jobs' / job['id'], ignore_errors=True)
    return targets


def reset_state(state, day, slates=(), hashes=()):
    from simmah_slate_workspaces import restore
    records = state.get('_slate_records', {})
    removed = set(slates) | {sid for sid, row in records.items() if matches(row, day)}
    retained = {sid: row for sid, row in records.items() if sid not in removed}
    owner = state.get('_slate_archive_owner')
    event = state.get(KEY)
    # Clear active calculations, uploader widgets, pending transfers and mirrors.
    restore(state, '')
    for key in list(state):
        if str(key).startswith('_slate_'):
            state.pop(key, None)
    state['_slate_records'] = retained
    state['_slate_fresh_mode'] = True
    state['_slate_cleanup_last'] = event.get('event') if isinstance(event, dict) else None
    state[KEY] = event
    if owner:
        state['_slate_archive_owner'] = owner
    state['_slate_upload_epoch'] = int(datetime.now().timestamp() * 1000)


def render_cleanup(st):
    import streamlit.components.v1 as components
    state = st.session_state
    day = today()
    component = components.declare_component('simmah_saved_cleanup_v1',
        path=str(Path(__file__).parent / 'components' / 'saved_cleanup'))
    event = state.get(KEY) or {}
    error = state.get('_slate_cleanup_error')
    if isinstance(event, dict) and event.get('event') != state.get('_slate_cleanup_last') and event.get('day') == day:
        if event.get('clear'):
            state.pop('_slate_cleanup_error', None)
            # Pause restore immediately, including if deletion needs a retry.
            state['_slate_fresh_mode'] = True
            try:
                from simmah_archive_ui import archive_for
                owner = event.get('owner', '')
                if isinstance(owner, str) and re.fullmatch('[a-f0-9]{32}', owner):
                    state['_slate_archive_owner'] = owner
                archive = archive_for(st)
                if archive:
                    clear_archive(archive, day)
                reset_state(state, day, event.get('slates', []), event.get('hashes', []))
                st.rerun()
            except Exception as exc:
                error = 'Server cleanup incomplete: ' + str(exc)
                state['_slate_cleanup_error'] = error
                state['_slate_cleanup_last'] = event.get('event')
        elif event.get('fresh'):
            state['_slate_fresh_mode'] = True
            state['_slate_cleanup_last'] = event.get('event')
    component(day=day, fresh=bool(state.get('_slate_fresh_mode')), error=error, key=KEY, default=None)
