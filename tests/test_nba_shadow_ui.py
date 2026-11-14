from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

class ShadowUITests(unittest.TestCase):
    def test_shadow_exception_does_not_stop_build_or_replace_saved_on_export_failure(self):
        sys.path.insert(0,str(Path(__file__).parent))
        with patch('simmah_nba_shadow_capture.begin_build_capture',side_effect=OSError('shadow unavailable')) as hook, patch('simmah_nba_shadow_capture.health',side_effect=OSError('health unavailable')):
            app=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py'))).run(timeout=30)
            app.button(key='nba_build').click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertGreaterEqual(hook.call_count,1)
            self.assertEqual(len(app.session_state['nba_build_result']['result']['portfolio']),5)
            app.session_state['nba_build_result']['shadow_sentinel']='preserve'
            app.session_state['fixture_reject_export']=True
            app.button(key='nba_build').click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['nba_build_result']['shadow_sentinel'],'preserve')
            self.assertTrue(any('Fixture export validation failed' in x.value for x in app.error))

if __name__=='__main__':unittest.main()
