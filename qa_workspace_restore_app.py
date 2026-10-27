"""Deploy privately for a guarded host-memory test; not a production app page."""
import os
import streamlit as st
from simmah_host_restore_probe import memory_snapshot, preflight, run_guarded
from simmah_memory_metrics import process_memory
import shutil
import tempfile

st.set_page_config(page_title='Simmah private host restore QA')
st.title('Private host restore QA')
st.caption('Synthetic data only. This tests this container, not another deployment with different resource limits.')
source_mib=st.selectbox('Synthetic source size (MiB)',[32,64,128,256,511],index=0)
st.caption('Measures the full generation, packing, and recovery pipeline; not extraction alone.')
snapshot=memory_snapshot()
check=preflight(snapshot,source_mib,shutil.disk_usage(tempfile.gettempdir()).free)
process_snapshot=process_memory()
if process_snapshot['rss_bytes'] is None:
    check.update(passed=False,reason='Process RSS unavailable; test blocked')
st.json(dict(container_memory=snapshot,process_memory=process_snapshot,preflight=check))
enabled=os.environ.get('SIMMAH_ENABLE_HOST_RESTORE_PROBE')=='1'
if not enabled:
    st.info('Disabled. In a private QA deployment only, set SIMMAH_ENABLE_HOST_RESTORE_PROBE to the string 1.')
if st.button(f'Run guarded {source_mib} MiB ZIP restore',disabled=not enabled or not check['passed']):
    with st.spinner('Monitoring isolated synthetic restore worker…'):
        st.session_state['host_restore_report']=run_guarded(enabled=enabled,mib=source_mib)
if 'host_restore_report' in st.session_state:
    st.json(st.session_state['host_restore_report'])
