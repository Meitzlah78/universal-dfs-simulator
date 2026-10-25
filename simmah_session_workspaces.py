"""Full session-only checkpoints without JSON/gzip or browser transfers."""
from copy import deepcopy


def checkpoint(st):
    from simmah_slate_workspaces import private_key, transient_key, transient_widget_keys
    state = st.session_state
    forbidden = transient_widget_keys(st) | set(state.get('_slate_uploader_keys', ())) | set(state.get('_slate_action_keys', ())) | set(state.get('_slate_readonly_keys', ()))
    values = {}
    for key in list(state):
        if str(key).startswith(('_slate_', '$$', 'universal_slate_setup_file')) or private_key(key) or transient_key(key) or key in forbidden:
            continue
        try:
            value = state[key]
        except KeyError:
            continue
        if hasattr(value, 'getvalue') and hasattr(value, 'name'):
            continue
        values[key] = value
    return deepcopy(dict(values=values, uploads=state.get('_slate_restored_uploads', {})))


def restore_checkpoint(st, saved):
    from simmah_slate_workspaces import restore
    # Reuse widget-safe clearing, but preserve large outcomes and candidate pools.
    restore(st.session_state, '')
    copied = deepcopy(saved)
    st.session_state.update(copied['values'])
    st.session_state['_slate_restored_uploads'] = copied.get('uploads', {})
