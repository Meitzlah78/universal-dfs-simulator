"""Read shared session mappings without failing on removed widget values."""


def safe_state_items(state, key_filter=None):
    """Snapshot keys, then skip values Streamlit removed during widget cleanup.

    Filter keys before reading values so unrelated large caches and widget
    payloads need not be fetched. Other errors still propagate.
    """
    for key in list(state):
        if key_filter is not None and not key_filter(key):
            continue
        try:
            value = state[key]
        except KeyError:
            continue
        yield key, value
