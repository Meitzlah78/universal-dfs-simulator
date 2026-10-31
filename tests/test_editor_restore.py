import ast,base64,gzip,json,unittest
from pathlib import Path
from simmah_slate_workspaces import restore,snapshot,encode

class EditorRestoreTests(unittest.TestCase):
    def test_readonly_keys_never_assigned_while_manual_deltas_migrate(self):
        class ReadonlyState(dict):
            def __setitem__(self,key,value):
                if key.startswith(('game_lines_','fd_player_pool_editor_')) or key=='player_controls_editor':raise RuntimeError('read-only')
                super().__setitem__(key,value)
            def update(self,items):
                for key,value in items.items():self[key]=value
        values={'game_lines_abc':encode({'edited_rows':{'0':{'Game total':45.5}}}),
                'fd_player_pool_editor_full_roster':encode({'edited_rows':{}}),
                'player_controls_editor':encode({'edited_rows':{}}),'salary':48000}
        blob=base64.b64encode(gzip.compress(json.dumps({'schema':1,'values':values,'uploads':{}}).encode())).decode()
        state=ReadonlyState();restore(state,blob)
        self.assertEqual(state['salary'],48000)
        self.assertEqual(state['legacy_game_line_edits_abc']['edited_rows']['0']['Game total'],45.5)
        self.assertNotIn('game_lines_abc',state)
        self.assertNotIn('fd_player_pool_editor_full_roster',state)
    def test_saved_manual_values_survive_without_internal_editor_state(self):
        state={};restore(state,snapshot({'game_lines_abc':{'edited_rows':{}},'manual_game_lines_abc':{'DAL @ GB':{'Game total':45.5}}}))
        self.assertNotIn('game_lines_abc',state)
        self.assertEqual(state['manual_game_lines_abc']['DAL @ GB']['Game total'],45.5)
    def test_legacy_editor_opens_and_reruns_with_manual_values(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('editor_restore_fixture.py'))).run()
        self.assertFalse(app.exception)
        frame=app.session_state['_slate_editor_result']
        self.assertEqual(frame.iloc[0]['Game total'],45.5)
        self.assertEqual(frame.iloc[0]['Home spread'],-3.5)
        app.run();self.assertFalse(app.exception)
        self.assertEqual(app.session_state['_slate_editor_result'].iloc[0]['Game total'],45.5)
        restored={};restore(restored,app.session_state['_slate_editor_snapshot'])
        self.assertEqual(restored['salary'],48000)
        self.assertNotIn('game_lines_529f8237066490d6',restored)
    def test_main_app_editors_use_safe_boundary(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'dfs_app.py').read_text())
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='st' and n.func.attr=='data_editor' for n in ast.walk(tree)))
