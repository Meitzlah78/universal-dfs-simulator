import base64
import gzip
import json
import unittest
from simmah_slate_workspaces import restore

class DownloadRestoreTests(unittest.TestCase):
    def test_old_snapshots_scrub_all_nba_download_actions(self):
        keys=['nba_minutes_snapshot_download','nba_entries_download_build',
              'nba_portfolio_report_build','nba_portfolio_report_lineups','nba_field_download',
              'nba_late_swap_download','nba_open_fanduel_build']
        values={key:False for key in keys};values['nba_min_salary']=58000
        blob=base64.b64encode(gzip.compress(json.dumps({'schema':1,'values':values,'uploads':{}}).encode())).decode()
        state={};restore(state,blob)
        self.assertEqual(state['nba_min_salary'],58000)
        for key in keys:self.assertNotIn(key,state)

    def test_generic_download_guard_handles_old_unknown_key_and_keeps_history(self):
        from streamlit.testing.v1 import AppTest
        source='''
import streamlit as st
from simmah_slate_workspaces import workspace_download_button,snapshot,restore
if not st.session_state.get('_slate_test_ready'):
    st.session_state['future_download_key']=False
    st.session_state['nba_minutes_snapshots']=[{'captured_at':'2026-10-20T12:00:00Z'}]
    st.session_state['_slate_test_ready']=True
workspace_download_button(st,'Download',b'data','test.csv',key='future_download_key',on_click='ignore')
state={};restore(state,snapshot(st.session_state))
assert 'future_download_key' not in state
assert len(state['nba_minutes_snapshots'])==1
'''
        app=AppTest.from_string(source).run(timeout=20)
        self.assertFalse(app.exception)
        app.run(timeout=20)
        self.assertFalse(app.exception)
