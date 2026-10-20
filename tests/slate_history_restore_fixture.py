import base64
import gzip
import json
import streamlit as st
from simmah_slate_workspaces import restore, workspace_file_uploader, snapshot

if not st.session_state.get('_slate_fixture_ready'):
    payload = {'schema': 1, 'values': {'contest_history_uploads_v2': None,
                'future_upload_key': {'@': 'list', 'value': []}}, 'uploads': {}}
    restore(st.session_state, base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode())
    st.session_state['_slate_fixture_ready'] = True
workspace_file_uploader(st, 'History', accept_multiple_files=True, key='contest_history_uploads_v2')
workspace_file_uploader(st, 'Future uploader', accept_multiple_files=True, key='future_upload_key')
st.session_state['_slate_test_blob'] = snapshot(st.session_state)
st.success('Uploaders available')
