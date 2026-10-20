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
        self.assertIn('7:00 PM ET',html)
        self.assertIn('9:30 PM ET',html)
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
        at.slider(key='nba_build_correlation').set_value(100).run(timeout=20)
        self.assertEqual(at.session_state['test_build_calls'],1)
        self.assertFalse(at.exception)
        at.number_input(key='nba_min_salary').set_value(500).run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        exports=[x for x in at.get('download_button') if x.proto.id.endswith('-nba_entries_download')]
        self.assertEqual(len(exports),1)
        self.assertTrue(exports[0].proto.disabled)

    def test_draftkings_uses_same_workspace_with_eight_slots(self):
        import sys
        from streamlit.testing.v1 import AppTest
        sys.path.insert(0,str(Path(__file__).parent))
        at=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py')))
        at.session_state['fixture_platform']='DraftKings'
        at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.number_input(key='nba_min_salary_DraftKings').max,50000)
        self.assertEqual(at.slider(key='nba_build_correlation').value,0)
        at.button(key='nba_build').click().run(timeout=20)
        self.assertFalse(at.exception)
        built=at.session_state['nba_build_result']['result']
        self.assertEqual(built['candidates']['indices'].shape[1],8)
        self.assertEqual(len(built['portfolio']),3)
        at.slider(key='nba_exposure_diversity').set_value(100).run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        self.assertTrue(any('UPLOAD TO DRAFTKINGS' in button.proto.label for button in at.get('download_button')))
