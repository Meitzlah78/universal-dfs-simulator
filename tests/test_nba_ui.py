import importlib.util
from pathlib import Path
import unittest

@unittest.skipUnless(importlib.util.find_spec('streamlit'),'Streamlit not installed')
class NBAWorkspaceTests(unittest.TestCase):
    def test_build_diversity_and_stale_export_without_rebuilding(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py'))).run(timeout=20)
        self.assertFalse(at.exception)
        html=' '.join(x.value for x in at.markdown)
        self.assertIn('simmah-game-strip',html)
        self.assertIn('○ Expected',html)
        at.button(key='test_source_change').click().run(timeout=20)
        self.assertTrue(at.session_state['nba_lineup_updates_found'])
        html=' '.join(x.value for x in at.markdown)
        self.assertIn('● Confirmed',html)
        self.assertIn('#d62828',html)
        at.button(key='test_refresh').click().run(timeout=20)
        self.assertFalse(at.session_state['nba_lineup_updates_found'])
        self.assertEqual(at.session_state['test_build_calls'],0)
        at.button(key='nba_build').click().run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        self.assertEqual(len(at.session_state['nba_build_result']['result']['portfolio']),5)
        at.slider(key='nba_exposure_diversity').set_value(100).run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        at.number_input(key='nba_min_salary').set_value(500).run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        exports=[x for x in at.get('download_button') if x.proto.id.endswith('-nba_entries_download')]
        self.assertEqual(len(exports),1)
        self.assertTrue(exports[0].proto.disabled)
