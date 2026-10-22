import base64,gzip,json,unittest
from pathlib import Path
import pandas as pd
from simmah_slate_workspaces import restore,snapshot,encode

class SwapFormRestoreTests(unittest.TestCase):
    def test_old_auto_submit_and_explicit_submit_not_restored_but_lineups_are(self):
        values={'FormSubmitter:old_form-Apply player swap':False,'FormSubmitter:other_form-Submit':True,
            'manual_lineups_abc_apply_swap':True,'manual_lineups_abc':encode(pd.DataFrame({'Flex1':['Player']})),'salary':48000}
        blob=base64.b64encode(gzip.compress(json.dumps({'schema':1,'values':values,'uploads':{}}).encode())).decode()
        state={};restore(state,blob)
        self.assertEqual(state['manual_lineups_abc'].iloc[0]['Flex1'],'Player')
        self.assertEqual(state['salary'],48000)
        for key in values.keys()-{'manual_lineups_abc','salary'}:self.assertNotIn(key,state)
    def test_submit_states_are_never_saved_again(self):
        state={};restore(state,snapshot({'FormSubmitter:old_form-Apply player swap':False,'manual_lineups_abc_apply_swap':True,'salary':48000}))
        self.assertEqual(state['salary'],48000)
        self.assertNotIn('FormSubmitter:old_form-Apply player swap',state)
        self.assertNotIn('manual_lineups_abc_apply_swap',state)
    def test_restored_editor_waits_for_click_and_applies_valid_swap(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('swap_form_restore_fixture.py'))).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['_slate_swap_result'].iloc[0]['Flex1'],'A1')
        app.selectbox[1].select('Flex1');app.selectbox[2].select('A6')
        app.button(key=app.session_state['_slate_swap_submit_key']).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['_slate_swap_result'].iloc[0]['Flex1'],'A6')
        app.run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['_slate_swap_result'].iloc[0]['Flex1'],'A6')
        state={};restore(state,app.session_state['_slate_swap_blob'])
        self.assertEqual(state['salary'],48000)
        self.assertNotIn(app.session_state['_slate_swap_submit_key'],state)
