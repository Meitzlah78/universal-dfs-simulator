import contextlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from simmah_slate_workspaces import render_session_tabs, restore, snapshot


class SessionTabsTest(unittest.TestCase):
    def test_switch_saves_each_build_without_transferring_snapshots(self):
        first={'id':'dk','name':'DKEntries.csv','data':'original-dk','snapshot':''}
        second={'id':'fd','name':'FanDuel.csv','data':'original-fd','snapshot':snapshot({'build':['fd lineup']})}
        state={'_slate_fresh_mode':True,'_slate_records':{'dk':first,'fd':second},
               '_slate_active':first,'build':['dk lineup'],'dfs_format':'DraftKings Classic'}
        st=SimpleNamespace(session_state=state,rerun=lambda:(_ for _ in ()).throw(RuntimeError('rerun')))
        calls=[]
        def component(**kwargs):
            calls.append(kwargs)
            return {'event':'choose-fd','selected_id':'fd'}
        with patch('streamlit.components.v1.declare_component', return_value=component):
            with self.assertRaisesRegex(RuntimeError, 'rerun'):
                render_session_tabs(st,contextlib.nullcontext())
        self.assertEqual(state['_slate_pending']['id'],'fd')
        self.assertTrue(state['_slate_records']['dk']['snapshot'])
        self.assertNotIn('snapshot',str(calls[0]['records']))
        self.assertNotIn('original-dk',str(calls))
        restore(state,state.pop('_slate_pending')['snapshot'])
        self.assertEqual(state['build'],['fd lineup'])
        restore(state,state['_slate_records']['dk']['snapshot'])
        self.assertEqual(state['build'],['dk lineup'])
        self.assertTrue(state['_slate_fresh_mode'])
