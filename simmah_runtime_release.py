"""Activate a coordinated NBA code release in a long-lived Streamlit process."""
import importlib
import sys
import threading

_lock=threading.RLock()
_active_release=None
# Reload dependency order, including modules that bind functions with `from`.
_NBA_MODULES=(
    'simmah_nba_projections','simmah_nba_dk_import','simmah_nba_import',
    'simmah_nba_rosters','simmah_nba_pipeline','simmah_nba_late_swap',
    'simmah_nba_sim_late_swap','simmah_nba_auto_swap','simmah_nba_ui',
)


def activate_nba_release(release):
    """Refresh already imported NBA modules once per explicit entrypoint release.

    No session state, uploads, cached outcomes or portfolios are cleared. Fresh
    processes import normally. This also refreshes function aliases when Cloud
    reruns the entrypoint while retaining imported Python modules.
    """
    global _active_release
    with _lock:
        if _active_release==release:return
        for name in _NBA_MODULES:
            module=sys.modules.get(name)
            if module is not None:importlib.reload(module)
        _active_release=release
