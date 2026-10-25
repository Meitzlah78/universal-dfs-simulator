import contextlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from simmah_slate_workspaces import render_session_tabs


class CloseTabsTest(unittest.TestCase):
    def close(self, state, ident):
        api=ModuleType('streamlit.components.v1')
        api.declare_component=lambda *a,**k: lambda **kw: {'event':'close-'+ident,'closed_id':ident}
        root=ModuleType('streamlit');components=ModuleType('streamlit.components')
        root.components=components;components.v1=api
        st=SimpleNamespace(session_state=state,rerun=lambda:(_ for _ in ()).throw(RuntimeError('rerun')))
        with patch.dict(sys.modules, {'streamlit':root,'streamlit.components':components,'streamlit.components.v1':api}):
            with self.assertRaisesRegex(RuntimeError,'rerun'):
                render_session_tabs(st,contextlib.nullcontext())

    def fixture(self):
        a={'id':'dk','name':'DK.csv'};b={'id':'fd','name':'FD.csv','_session_checkpoint':{'values':{'build':'keep'}}}
        return {'_slate_records':{'dk':a,'fd':b},'_slate_active':a,'build':'current'}

    def test_close_inactive_keeps_current_build(self):
        state=self.fixture();self.close(state,'fd')
        self.assertEqual(list(state['_slate_records']),['dk'])
        self.assertEqual(state['build'],'current')
        self.assertNotIn('_slate_pending',state)
        self.assertNotIn('_slate_clear_active',state)

    def test_close_active_selects_remaining_workspace(self):
        state=self.fixture();self.close(state,'dk')
        self.assertEqual(list(state['_slate_records']),['fd'])
        self.assertEqual(state['_slate_pending']['id'],'fd')
        self.assertEqual(state['_slate_pending']['_session_checkpoint']['values']['build'],'keep')

    def test_close_last_returns_to_empty_workspace(self):
        state=self.fixture();state['_slate_records'].pop('fd');self.close(state,'dk')
        self.assertFalse(state['_slate_records'])
        self.assertTrue(state['_slate_clear_active'])
