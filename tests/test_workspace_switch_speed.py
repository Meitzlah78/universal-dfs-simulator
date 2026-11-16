import contextlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_session_workspaces import checkpoint,restore_checkpoint
from simmah_slate_workspaces import render_session_tabs
from simmah_workspace_persistence import schedule


class SwitchSpeedTests(unittest.TestCase):
    def test_nfl_and_nba_dk_fd_round_trip_reuses_detached_capture(self):
        for sport in ('NFL','NBA'):
            first={'id':'dk','name':'DK.csv','data':'dk'}
            second={'id':'fd','name':'FD.csv','data':'fd'}
            state={'_slate_active':first,'_slate_records':{'dk':first,'fd':second},
                '_slate_backup_owner':'a'*32,'dfs_format':'DraftKings '+sport,
                'portfolio':pd.DataFrame({'Player':['DK player']}),'outcomes':np.arange(10000).reshape(100,100),
                'export_bytes':b'DK complete CSV'}
            st=SimpleNamespace(session_state=state,rerun=lambda:(_ for _ in ()).throw(RuntimeError('rerun')))
            def select(site,prepared):
                with patch('streamlit.components.v1.declare_component',return_value=lambda **kw:{'event':'select-'+site,'selected_id':site}):
                    with self.assertRaisesRegex(RuntimeError,'rerun'):
                        render_session_tabs(st,contextlib.nullcontext(),prepared_checkpoint=prepared)
            with patch('simmah_workspace_persistence.advance'),patch('simmah_session_workspaces.checkpoint',wraps=checkpoint) as capture:
                prepared=schedule(st)
                select('fd',prepared)
                self.assertEqual(capture.call_count,2) # One view, one detached copy; no second tab-switch copy.
            saved=state['_slate_records']['dk']['_session_checkpoint']
            self.assertIs(saved,prepared[1])
            state['outcomes'][0,0]=-1
            self.assertEqual(saved['values']['outcomes'][0,0],0)
            state['_slate_active']=second
            state['dfs_format']='FanDuel '+sport
            state['portfolio']=pd.DataFrame({'Player':['FD player']})
            state['export_bytes']=b'FD complete CSV'
            with patch('simmah_workspace_persistence.advance'):
                prepared=schedule(st)
                select('dk',prepared)
            fd_saved=state['_slate_records']['fd']['_session_checkpoint']
            restore_checkpoint(st,state['_slate_pending']['_session_checkpoint'])
            self.assertEqual(state['portfolio'].Player.tolist(),['DK player'])
            self.assertEqual(state['export_bytes'],b'DK complete CSV')
            self.assertEqual(state['outcomes'][0,0],0)
            restore_checkpoint(st,fd_saved)
            self.assertEqual(state['portfolio'].Player.tolist(),['FD player'])
            self.assertEqual(state['export_bytes'],b'FD complete CSV')

    def test_without_current_capture_switch_still_saves_current_edits(self):
        state={'_slate_active':{'id':'dk','name':'DK.csv'},'_slate_records':{'fd':{'id':'fd'}},'build':['new edit']}
        st=SimpleNamespace(session_state=state,rerun=lambda:(_ for _ in ()).throw(RuntimeError('rerun')))
        self.assertIsNone(schedule(st)) # No backup owner: no captured checkpoint.
        for prepared in (None,('other-slate',{'values':{}})):
            with patch('streamlit.components.v1.declare_component',return_value=lambda **kw:{'event':str(prepared),'selected_id':'fd'}):
                with self.assertRaisesRegex(RuntimeError,'rerun'):
                    render_session_tabs(st,contextlib.nullcontext(),prepared_checkpoint=prepared)
            self.assertEqual(state['_slate_records']['dk']['_session_checkpoint']['values']['build'],['new edit'])

if __name__=='__main__':unittest.main()
