"""Load diagnostic archives on click, without reading session state in workers."""
from collections.abc import Callable
from functools import lru_cache,partial
import inspect
from typing import get_args,get_origin,get_type_hints


@lru_cache(maxsize=1)
def supports_deferred_download():
    # Check the installed public API, retaining the existing byte-based path on
    # Streamlit versions without callable download data. No framework upgrade.
    try:
        import streamlit as st
        data=get_type_hints(inspect.unwrap(st.download_button))['data']
        return any(get_origin(item) is Callable for item in get_args(data))
    except (KeyError,NameError,TypeError,ValueError):return False


def package_download_data(st,reference):
    from simmah_nba_diagnostics import package_bytes
    if not supports_deferred_download():return package_bytes(st,reference)
    digest=reference['digest']
    pending=st.session_state.get('_slate_archive_pending',{}).get(digest)
    if pending:return pending['raw']
    from simmah_archive_ui import archive_for
    archive=archive_for(st)
    if archive is None:return None
    # Freeze the archive/owner and immutable digest now. The deferred callable
    # must not inspect a different slate's mutable session state after a switch.
    return partial(archive.get,digest)
