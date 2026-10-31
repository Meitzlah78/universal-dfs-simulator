import ast
import base64
import gzip
import json
from pathlib import Path
import unittest
from simmah_slate_workspaces import restore,snapshot

class DownloadRestoreTests(unittest.TestCase):
    def test_legacy_accuracy_action_is_not_restored(self):
        blob=base64.b64encode(gzip.compress(json.dumps({'schema':1,'values':{
            'projection_accuracy_template_download':False,'salary':48000},'uploads':{}}).encode())).decode()
        state={};restore(state,blob)
        self.assertEqual(state['salary'],48000)
        self.assertNotIn('projection_accuracy_template_download',state)
    def test_accuracy_action_is_not_saved(self):
        state={};restore(state,snapshot({'projection_accuracy_template_download':True,'salary':48000}))
        self.assertEqual(state['salary'],48000)
        self.assertNotIn('projection_accuracy_template_download',state)
    def test_main_app_downloads_use_guarded_helper(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'dfs_app.py').read_text())
        direct=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and isinstance(n.func.value,ast.Name) and n.func.value.id=='st' and n.func.attr=='download_button']
        self.assertEqual(direct,[])
    def test_programmatic_action_values_can_render_and_rerun(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('download_restore_fixture.py'))).run()
        self.assertFalse(app.exception)
        state=app.session_state['_slate_restored_test']
        self.assertEqual(state['kept_salary'],48000)
        self.assertNotIn('projection_accuracy_template_download',state)
        self.assertNotIn('future_report_download',state)
        app.run();self.assertFalse(app.exception)
