"""Deploy privately for a guarded host-memory test; not a production app page."""
import os
import streamlit as st
from simmah_host_restore_probe import memory_snapshot, preflight, run_guarded
import shutil
import tempfile

st.set_page_config(page_title='Simmah private host restore QA')
st.title('Private host restore QA')
st.caption('Synthetic data only. This tests this container, not another deployment with different resource limits.')
snapshot=memory_snapshot()
check=preflight(snapshot,511,shutil.disk_usage(tempfile.gettempdir()).free)
st.json(dict(memory=snapshot,preflight=check))
enabled=os.environ.get('SIMMAH_ENABLE_HOST_RESTORE_PROBE')=='1'
if not enabled:
    st.info('Disabled. In a private QA deployment only, set SIMMAH_ENABLE_HOST_RESTORE_PROBE to the string 1.')
if st.button('Run guarded 511 MiB ZIP restore',disabled=not enabled or not check['passed']):
    with st.spinner('Monitoring isolated synthetic restore worker…'):
        st.session_state['host_restore_report']=run_guarded(enabled=enabled)
if 'host_restore_report' in st.session_state:
    st.json(st.session_state['host_restore_report'])
