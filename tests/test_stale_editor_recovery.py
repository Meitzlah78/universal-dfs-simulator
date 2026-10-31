"""Reproduce the missing player_controls_editor failures in restore and capture."""
from collections.abc import MutableMapping
from types import SimpleNamespace
import io
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd

from simmah_diagnostic_packages import make_nfl_package
from simmah_session_workspaces import checkpoint, restore_checkpoint
from simmah_slate_workspaces import decode, restore, snapshot


class RetiredEditorState(MutableMapping):
    """Streamlit can retain a widget's name after removing its stored value."""
    def __init__(self, values=None, missing=()):
        self.data=dict(values or {})
        self.missing={'player_controls_editor',*missing}
    def __iter__(self):return iter([*self.data,*sorted(self.missing-self.data.keys())])
    def __len__(self):return len(set(self.data)|self.missing)
    def __getitem__(self,key):
        if key in self.missing:raise KeyError('st.session_state has no key "'+key+'"')
        return self.data[key]
    def __setitem__(self,key,value):
        if key=='player_controls_editor':raise AssertionError('Native editor state must not be replayed')
        self.data[key]=value
    def __delitem__(self,key):
        if key in self.missing:raise KeyError('st.session_state has no key "'+key+'"')
        del self.data[key]


class StaleEditorRecoveryTest(unittest.TestCase):
    def test_saved_slate_restore_keeps_settings_and_large_build_without_editor(self):
        outcomes=np.arange(2200000,dtype=float).reshape(10000,220)
        state=RetiredEditorState({'minimum_salary':48000,'player_control_values':{'A':{'Fade':True}},
            'outcomes':outcomes,'portfolio_df':pd.DataFrame({'QB':['A'],'Points':[123.45]}),
            '_slate_active':{'id':'dk'}})
        app=SimpleNamespace(session_state=state)
        with patch('simmah_slate_workspaces.transient_widget_keys',return_value=set()):
            saved=checkpoint(app)
        self.assertNotIn('player_controls_editor',saved['values'])
        state['minimum_salary']=0
        restore_checkpoint(app,saved)
        self.assertEqual(state['minimum_salary'],48000)
        self.assertTrue(state['player_control_values']['A']['Fade'])
        np.testing.assert_array_equal(state['outcomes'],outcomes)
        self.assertEqual(state['portfolio_df'].iloc[0]['QB'],'A')
        self.assertEqual(state['_slate_active']['id'],'dk')

    def test_legacy_snapshot_restore_tolerates_retired_editor(self):
        state=RetiredEditorState({'salary_min':0})
        restore(state,snapshot({'salary_min':48500}))
        self.assertEqual(state['salary_min'],48500)

    def package(self,state):
        pool=pd.DataFrame({'Name':['A','B'],'Salary':[5000,6000]})
        lineups=pd.DataFrame({'Captain':['A'],'Flex1':['B']})
        with tempfile.TemporaryDirectory() as directory:
            return make_nfl_package(state,'DraftKings Showdown',pool,lineups,lineups,lineups,
                directory,source_root=directory)

    def test_package_capture_skips_editor_and_reports_other_disappearing_controls(self):
        state=RetiredEditorState({'selected_dk_contest':{'id':'123'},
            'player_control_values':{'A':{'Fade':True}},'salary_min':48500},missing=['field_learning_expired'])
        _,raw,manifest=self.package(state)
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            values=decode(json.loads(bundle.read('solver/runtime_state.json')))
        self.assertNotIn('player_controls_editor',values)
        self.assertTrue(values['player_control_values']['A']['Fade'])
        self.assertEqual(values['salary_min'],48500)
        self.assertTrue(any('field_learning_expired' in item for item in manifest['missing_evidence']))

    def test_present_editor_deltas_are_excluded_too(self):
        _,raw,_=self.package({'selected_dk_contest':{'id':'123'},
            'player_controls_editor':{'edited_rows':{0:{'Fade':True}}},
            'player_control_values':{'A':{'Fade':True}}})
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            values=decode(json.loads(bundle.read('solver/runtime_state.json')))
        self.assertNotIn('player_controls_editor',values)
        self.assertTrue(values['player_control_values']['A']['Fade'])

    def test_restore_does_not_hide_unrelated_failures(self):
        class BrokenState(dict):
            def __delitem__(self,key):raise RuntimeError('real failure')
        with self.assertRaisesRegex(RuntimeError,'real failure'):
            restore(BrokenState(salary_min=48000),'')

    def test_export_checkpoint_skips_retired_editor_and_earlier_archives(self):
        from simmah_export_history import make_checkpoint,HISTORY
        state=RetiredEditorState({'salary_min':48500,HISTORY:[{'archive':b'old archive'}],
            'export_history_download':True,'player_control_values':{'A':{'Fade':True}}})
        record=make_checkpoint(b'Entry ID,QB\n1,A\n','entries.csv',{'format':'DraftKings Classic','contest_id':'123'},state)
        with zipfile.ZipFile(io.BytesIO(record['archive'])) as bundle:
            restored={};restore(restored,bundle.read('workspace_snapshot.txt').decode())
        self.assertEqual(restored['salary_min'],48500)
        self.assertTrue(restored['player_control_values']['A']['Fade'])
        self.assertNotIn('player_controls_editor',restored)
        self.assertNotIn(HISTORY,restored)
        self.assertNotIn('export_history_download',restored)

    def test_old_error_is_not_redrawn_as_a_new_failure_after_slate_restore(self):
        from simmah_diagnostic_packages import render_nfl_package
        message='Calibration/solver package capture failed: st.session_state has no key "player_controls_editor"'
        state={};restore(state,snapshot({'diagnostic_package_error':message}))
        warnings=[];information=[]
        app=SimpleNamespace(session_state=state,warning=warnings.append,info=information.append)
        render_nfl_package(app);render_nfl_package(app)
        self.assertFalse(warnings)
        self.assertTrue(all('previous' in text and 'Run a new build' in text for text in information))
        self.assertEqual(state['diagnostic_package_previous_error'],message)
        self.assertNotIn('diagnostic_package_current',state)

    def test_current_failures_stay_visible_and_success_clears_old_status(self):
        from simmah_diagnostic_packages import CAPTURE_VERSION,capture_nfl_build,render_nfl_package
        warnings=[];state={'diagnostic_package_previous_error':'old failure','portfolio_df':'keep'}
        app=SimpleNamespace(session_state=state,warning=warnings.append,info=lambda message:None)
        with patch('simmah_diagnostic_packages.make_nfl_package',side_effect=KeyError('st.session_state has no key "player_controls_editor"')):
            capture_nfl_build(app,'DraftKings Classic',None,None,None,None,'.')
        self.assertEqual(state['diagnostic_package_error_version'],CAPTURE_VERSION)
        render_nfl_package(app)
        self.assertIn(CAPTURE_VERSION,warnings[-1])
        package=('evidence.zip',b'zip bytes',{'contest_id':'123','captured_at_eastern':'now'})
        with patch('simmah_diagnostic_packages.make_nfl_package',return_value=package),patch('simmah_diagnostic_packages.retain_package'):
            capture_nfl_build(app,'DraftKings Classic',None,None,None,None,'.')
        self.assertNotIn('diagnostic_package_error',state)
        self.assertNotIn('diagnostic_package_previous_error',state)
        self.assertEqual(state['portfolio_df'],'keep')
