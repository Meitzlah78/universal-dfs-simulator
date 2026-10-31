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

    def test_legacy_history_download_keys_are_not_restored(self):
        from simmah_slate_workspaces import snapshot
        keys=['export_history_backup_nba_entries_download_build',
              'export_history_csv_nba_entries_download_build',
              'export_history_backup_nba_entries_download',
              'export_history_csv_nba_entries_download']
        values={key:False for key in keys}
        values['simmah_export_history_v1']=[]
        values['export_history_select_nba_entries_download_build']=0
        blob=base64.b64encode(gzip.compress(json.dumps({'schema':1,'values':values,'uploads':{}}).encode())).decode()
        state={};restore(state,blob)
        for key in keys:self.assertNotIn(key,state)
        self.assertIn('simmah_export_history_v1',state)
        self.assertIn('export_history_select_nba_entries_download_build',state)
        saved=json.loads(gzip.decompress(base64.b64decode(snapshot(values))))
        for key in keys:self.assertNotIn(key,saved['values'])

    def test_saved_history_downloads_clear_assigned_state_and_keep_archive(self):
        from streamlit.testing.v1 import AppTest
        source='''
import streamlit as st
from simmah_export_history import make_checkpoint,HISTORY
from simmah_slate_workspaces import workspace_download_button,snapshot,restore
context={'format':'DraftKings NBA','contest_id':'fixture','kind':'entries'}
key='nba_entries_download_build'
if not st.session_state.get('_slate_test_ready'):
    st.session_state[HISTORY]=[make_checkpoint(b'Entry ID,PG\\n1,2\\n','entries.csv',context,{})]
    st.session_state['export_history_backup_'+key]=False
    st.session_state['export_history_csv_'+key]=True
    st.session_state['_slate_test_ready']=True
original_archive=st.session_state[HISTORY][0]['archive']
workspace_download_button(st,'EXPORT',b'csv','entries.csv',key=key,export_checkpoint=context)
state={};restore(state,snapshot(st.session_state))
assert state[HISTORY][0]['archive']==original_archive
assert 'export_history_backup_'+key not in state
assert 'export_history_csv_'+key not in state
assert {'export_history_backup_'+key,'export_history_csv_'+key} <= st.session_state['_slate_action_keys']
'''
        app=AppTest.from_string(source).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('download_button')),3)
        app.run(timeout=20)
        self.assertFalse(app.exception)
