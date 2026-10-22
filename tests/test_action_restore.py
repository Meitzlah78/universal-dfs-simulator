import base64,gzip,json,unittest,ast
from pathlib import Path
from simmah_slate_workspaces import restore,encode

class ActionRestoreTests(unittest.TestCase):
    def test_exact_saved_contest_panel_restores_actions_and_selects_metadata(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('saved_contest_action_fixture.py'))).run()
        self.assertFalse(app.exception)
        app.button(key='saved_contest_choice_DraftKings Classic_use').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['_slate_panel_result']['field_size'],100)
    def test_legacy_contest_buttons_removed_but_selection_retained(self):
        prefix='saved_contest_choice_DraftKings Classic'
        values={prefix:'123',prefix+'_active':encode({'id':'123'}),'salary':48000}
        for suffix in ('_use','_save','_restore_button','_backup','_restore'):values[prefix+suffix]=False
        blob=base64.b64encode(gzip.compress(json.dumps({'schema':1,'values':values,'uploads':{}}).encode())).decode()
        state={};restore(state,blob)
        self.assertEqual(state, {prefix:'123',prefix+'_active':{'id':'123'},'salary':48000,'_slate_restored_uploads':{},'_slate_widget_seen':{}})
    def test_restored_action_renders_and_native_click_is_preserved(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('action_restore_fixture.py'))).run()
        self.assertFalse(app.exception)
        self.assertNotIn('uses',app.session_state)
        key='saved_contest_choice_DraftKings Classic_use'
        app.button(key=key).click().run()
        self.assertFalse(app.exception);self.assertEqual(app.session_state['uses'],1)
        state={};restore(state,app.session_state['_slate_test_blob'])
        self.assertEqual(state['salary'],48000)
        self.assertNotIn(key,state);self.assertNotIn('future_action',state)
        app.run();self.assertFalse(app.exception);self.assertEqual(app.session_state['uses'],1)
    def test_primary_action_surfaces_use_guard(self):
        for name in ('dfs_app.py','simmah_saved_contests.py','simmah_nba_ui.py','simmah_nba_late_swap.py'):
            tree=ast.parse((Path(__file__).resolve().parents[1]/name).read_text())
            self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='st' and n.func.attr=='button' for n in ast.walk(tree)),name)
