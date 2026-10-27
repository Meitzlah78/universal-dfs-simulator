"""Explicit browser-only diagnostic, isolated from slate session restoration."""
from pathlib import Path


def read_only_host_preflight():
    """Inspect only this app's resource budget; never spawn or allocate a payload."""
    from datetime import datetime, timezone
    import shutil
    import tempfile
    from simmah_memory_metrics import process_memory
    from simmah_host_restore_probe import memory_snapshot, preflight
    container=memory_snapshot()
    process=process_memory()
    check=preflight(container,511,shutil.disk_usage(tempfile.gettempdir()).free)
    monitor_available=process['rss_bytes'] is not None
    check['process_monitor_available']=monitor_available
    if not monitor_available:
        check.update(passed=False,reason='Process RSS unavailable; host test is blocked')
    return dict(schema=1,captured_at_utc=datetime.now(timezone.utc).isoformat(),
        execution_context='host of this Streamlit app',container_memory=container,
        process_memory=process,preflight=check,heavy_test_executed=False,
        worker_visibility_verified=False)


def render(st):
    import streamlit.components.v1 as components
    st.title('Workspace storage verification')
    st.caption('Probe version: storage-probe-v3-random')
    st.caption('This tests this browser and origin only. It does not prove every browser has 512 MiB available, or test the full ZIP/server restore pipeline.')
    probe=components.declare_component('simmah_storage_capacity_probe_v1',
        path=str(Path(__file__).parent/'components'/'storage_probe'))
    result=probe(key='_simmah_storage_probe',default=None)
    if result:
        if result.get('passed') and result.get('test_data_removed'):
            if result.get('event_loop_stall_over_3s'):
                st.warning('Byte parity passed, but an event-loop stall over three seconds was observed. Synthetic data removed.')
            else:
                st.success('512 MiB browser storage round trip passed; synthetic data removed.')
        else:
            st.error('Storage test failed or cleanup needs attention. See the exact result below.')
        st.json(result)
    with st.expander('Cloud host preflight — read only'):
        st.caption('Reads memory visibility and resource limits only. It does not start the private restore worker or allocate the archive.')
        if st.button('Check Cloud host memory',key='_simmah_host_preflight_check'):
            st.session_state['_simmah_host_preflight_report']=read_only_host_preflight()
        if st.session_state.get('_simmah_host_preflight_report'):
            st.json(st.session_state['_simmah_host_preflight_report'])
    st.markdown('[Open Simmah in a separate tab](https://universal-dfs-simulator-7bhlq8fvkrzkvfdfsokhan.streamlit.app/)')
