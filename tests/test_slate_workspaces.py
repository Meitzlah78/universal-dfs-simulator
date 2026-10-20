import unittest
import numpy as np
import pandas as pd
from simmah_slate_workspaces import StoredUpload,snapshot,restore,slate_record,encode,decode
from test_nba_draftkings import template

class SlateWorkspaceTests(unittest.TestCase):
    def test_safe_roundtrip_survives_new_session_and_keeps_platform(self):
        pool=pd.DataFrame({'Player ID':['1000'],'Projection':[35.]});pool.attrs['platform']='DraftKings'
        state={'nba_build_result':{'pool':pool,'result':{'indices':np.array([[1,2,3]]),'portfolio':pd.DataFrame({'PG':['1000']})}},
               'nba_min_salary_DraftKings':45000,'dfs_format':'DraftKings NBA','test_api_key':'never save',
               'loaded_slates_browser':{'selected':{'snapshot':'recursive'}},'_slate_restored_uploads':{'projection':StoredUpload(b'Player ID,Projection\n1000,35','projection.csv')}}
        blob=snapshot(state);fresh={'old_slate':'remove','_slate_generation':'keep'};restore(fresh,blob)
        self.assertNotIn('old_slate',fresh);self.assertNotIn('test_api_key',fresh);self.assertNotIn('loaded_slates_browser',fresh)
        self.assertEqual(fresh['nba_build_result']['pool'].attrs['platform'],'DraftKings')
        np.testing.assert_array_equal(fresh['nba_build_result']['result']['indices'],[[1,2,3]])
        self.assertEqual(fresh['_slate_restored_uploads']['projection'].getvalue(),b'Player ID,Projection\n1000,35')
    def test_one_tab_per_salary_slate_despite_entry_changes(self):
        first=StoredUpload(template(),'DKEntries.csv');second=StoredUpload(template().replace(b'NBA fixture',b'NBA different contest'),'renamed.csv')
        self.assertEqual(slate_record(first)['id'],slate_record(second)['id'])
        third=StoredUpload(template().replace(b'1000',b'9999'),'other.csv')
        self.assertNotEqual(slate_record(first)['id'],slate_record(third)['id'])
    def test_typed_keys_missing_values_and_no_pickle(self):
        value={(1,'NY'):[np.nan,np.int64(3),{1,2}]};restored=decode(encode(value))
        self.assertTrue(np.isnan(restored[(1,'NY')][0]));self.assertEqual(restored[(1,'NY')][2],{1,2})
        with self.assertRaises(ValueError):decode({'@':'pickle','value':'no'})
        with self.assertRaises(ValueError):encode(np.array([object()]))

class SlateWidgetRestoreTests(unittest.TestCase):
    def test_widget_settings_restore_without_replaying_buttons(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('slate_workspace_fixture.py'))).run()
        app.number_input(key='test_salary').set_value(45000).run()
        app.button(key='test_button').click().run()
        app.number_input(key='test_salary').set_value(1000).run()
        app.button(key='test_restore').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key='test_salary').value,45000)

class MultipleLoadedSlateTests(unittest.TestCase):
    def test_load_fd_after_dk_keeps_both_and_restores_each_setting(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('slate_switch_fixture.py'))).run()
        app.button(key='load_DK').click().run()
        self.assertFalse(app.exception)
        app.number_input(key='slate_salary').set_value(45000).run()
        app.button(key='load_FD').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['_slate_records']),2)
        self.assertEqual(app.session_state['_slate_active']['name'],'FD.csv')
        self.assertEqual(app.number_input(key='slate_salary').value,0)
        app.number_input(key='slate_salary').set_value(55000).run()
        app.button(key='switch_DK.csv').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key='slate_salary').value,45000)
        app.button(key='switch_FD.csv').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key='slate_salary').value,55000)
