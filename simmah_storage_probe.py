"""Explicit browser-only diagnostic, isolated from slate session restoration."""
from pathlib import Path


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
    st.markdown('[Open Simmah in a separate tab](https://universal-dfs-simulator-7bhlq8fvkrzkvfdfsokhan.streamlit.app/)')
