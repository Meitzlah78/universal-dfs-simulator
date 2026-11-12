"""Activate a coordinated NBA code release in a long-lived Streamlit process."""
import importlib
import hashlib
from pathlib import Path
import sys
import threading

_lock=threading.RLock()
_active_release=None
# Reload dependency order, including modules that bind functions with `from`.
_NBA_MODULES=(
    'simmah_workspace_backup','simmah_workspace_cloud','simmah_session_workspaces','simmah_export_history',
    'simmah_workspace_persistence','simmah_slate_workspaces',
    'simmah_nba_official_lineups','simmah_nba_confirmed','simmah_nba_lineups',
    'simmah_nba_projections','simmah_nba_ownership_upload','simmah_nba_ownership',
    'simmah_nba_portfolio_limits','simmah_nba_dk_import','simmah_nba_import',
    'simmah_nba_rosters','simmah_nba_candidates','simmah_nba_field','simmah_nba_markets','simmah_nba_minutes','simmah_nba_pregame','simmah_nba_simulation_cache',
    'simmah_portfolio_selection','simmah_nba_contest','simmah_nba_diagnostics','simmah_nba_pipeline',
    'simmah_nba_swap_portfolio','simmah_nba_swap_archive','simmah_nba_late_swap',
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
        parallel = sys.modules.get('simmah_nba_parallel')
        if parallel is not None:
            parallel.shutdown_workers()
        for name in _NBA_MODULES:
            module=sys.modules.get(name)
            if module is not None:importlib.reload(module)
        _active_release=release


NFL_PROJECTION_RELEASE = 'public-json-headers-v1'
_active_role_ownership_release = None
_active_role_ownership_fingerprint = None

def activate_role_ownership_release(release):
    """Refresh the NFL role fit helpers once, without changing saved inputs."""
    global _active_role_ownership_release, _active_role_ownership_fingerprint
    modules=('simmah_showdown_field', 'simmah_role_field_ownership', 'simmah_fantasylabs_ownership', 'simmah_rotowire')
    # Cloud may rerun the entrypoint without restarting imported modules. A
    # source digest also covers fixes that accidentally reuse a release marker.
    root=Path(__file__).resolve().parent
    fingerprint=tuple(hashlib.sha256((root/(name+'.py')).read_bytes()).hexdigest() for name in modules)
    with _lock:
        if (_active_role_ownership_release == release
                and _active_role_ownership_fingerprint == fingerprint):
            return
        importlib.invalidate_caches()
        for name in modules:
            module = sys.modules.get(name)
            if module is not None:
                importlib.reload(module)
        _active_role_ownership_release = release
        _active_role_ownership_fingerprint = fingerprint

