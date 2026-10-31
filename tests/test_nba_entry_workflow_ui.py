import importlib.util
from pathlib import Path
import unittest


@unittest.skipUnless(importlib.util.find_spec('streamlit'),'Streamlit not installed')
class NBAEntryWorkflowUITests(unittest.TestCase):
    def test_status_transition_restore_and_download_remain_usable(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('nba_entry_workflow_fixture.py'))).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value,'3')
        for status in ('In Progress','Final'):
            app.selectbox(key='download_status').set_value(status).run(timeout=20)
            self.assertFalse(app.exception)
            app.button[0].click().run(timeout=20)
            app.checkbox(key='clock_missing').set_value(True).run(timeout=20)
            self.assertFalse(app.exception)
            app.button[1].click().run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value,'3')
            self.assertEqual(app.metric[1].value,'3')
            self.assertIn('verified_export',app.session_state)
            self.assertEqual(len(app.get('download_button')),1)
            self.assertFalse(app.get('download_button')[0].proto.disabled)
