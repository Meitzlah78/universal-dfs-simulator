import importlib.util
import json
from pathlib import Path
import sys
import unittest

@unittest.skipUnless(importlib.util.find_spec('streamlit'),'Streamlit not installed')
class NBAExportPlacementTests(unittest.TestCase):
    def test_both_sites_offer_one_entry_export_and_report_in_lineups(self):
        from streamlit.testing.v1 import AppTest
        sys.path.insert(0,str(Path(__file__).parent))
        for platform in ['FanDuel','DraftKings']:
            with self.subTest(platform=platform):
                app=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py')))
                app.session_state['fixture_platform']=platform
                app.run(timeout=20).button(key='nba_build').click().run(timeout=20)
                self.assertFalse(app.exception)
                buttons=app.get('download_button')
                components = app.get('component_instance')
                entries = [x for x in components if x.proto.id.endswith('_nba_entries_download')]
                self.assertEqual(len(entries), 1)
                self.assertFalse(json.loads(entries[0].proto.json_args)['disabled'])
                self.assertFalse(any(x.proto.id.endswith('_nba_entries_download_build') for x in components))
                self.assertEqual(sum(b.proto.id.endswith('-nba_portfolio_report_lineups') for b in buttons), 1)
                self.assertFalse(any(b.proto.id.endswith('-nba_portfolio_report_build') for b in buttons))
                for tab_index, count in ((2, 0), (3, 1)):
                    tab_components = app.tabs[tab_index].get('component_instance')
                    self.assertEqual(sum(
                        'EDIT ENTRIES CSV' in json.loads(x.proto.json_args).get('label', '')
                        for x in tab_components
                    ), count)
                reports=[e for e in app.expander if e.label=='Advanced — diagnostics and reports']
                self.assertEqual(len(reports),1)
                for section in reports:
                    self.assertFalse(section.proto.expanded)
                    labels=[b.proto.label for b in section.get('download_button')]
                    self.assertIn('DOWNLOAD PORTFOLIO REPORT',labels)
                    self.assertFalse(any('EDIT ENTRIES CSV' in label for label in labels))
                if platform=='FanDuel':
                    self.assertEqual(len([b for b in app.get('link_button') if 'OPEN FANDUEL' in b.proto.label]),1)

    def test_opponent_report_is_deferred_without_rebuilding_selected_lineups(self):
        from streamlit.testing.v1 import AppTest
        sys.path.insert(0,str(Path(__file__).parent))
        for platform in ['FanDuel','DraftKings']:
            with self.subTest(platform=platform):
                app=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py')))
                app.session_state['fixture_platform']=platform
                app.run(timeout=20).button(key='nba_build').click().run(timeout=20)
                self.assertFalse(app.exception)
                saved=app.session_state['nba_build_result']['result']['portfolio'].copy(deep=True)
                calls=app.session_state['test_build_calls']
                self.assertTrue(any(h.value=='My lineups' for h in app.subheader))
                self.assertFalse(any(b.proto.id.endswith('-nba_field_download') for b in app.get('download_button')))
                app.checkbox(key='nba_load_engine_details').check().run(timeout=20)
                self.assertFalse(app.exception)
                self.assertTrue(any(b.proto.id.endswith('-nba_field_download') for b in app.get('download_button')))
                self.assertEqual(app.session_state['test_build_calls'],calls)
                import pandas as pd
                pd.testing.assert_frame_equal(saved,app.session_state['nba_build_result']['result']['portfolio'])

    def test_minutes_toggle_does_not_build_or_prepare_candidate_download(self):
        from streamlit.testing.v1 import AppTest
        sys.path.insert(0,str(Path(__file__).parent))
        for platform in ['FanDuel','DraftKings']:
            with self.subTest(platform=platform):
                app=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py')))
                app.session_state['fixture_platform']=platform
                app.run(timeout=20).button(key='nba_build').click().run(timeout=20)
                self.assertFalse(app.exception)
                calls=app.session_state['test_build_calls']
                saved=app.session_state['nba_build_result']['result']['portfolio'].copy(deep=True)
                key='nba_variable_minutes_'+platform
                app.checkbox(key=key).uncheck().run(timeout=20)
                app.checkbox(key=key).check().run(timeout=20)
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['test_build_calls'],calls)
                self.assertFalse(any(b.proto.id.endswith('-nba_all_candidates_download') for b in app.get('download_button')))
                app.checkbox(key='nba_load_candidate_details').check().run(timeout=20)
                self.assertFalse(app.exception)
                self.assertTrue(any(b.proto.id.endswith('-nba_all_candidates_download') for b in app.get('download_button')))
                self.assertEqual(app.session_state['test_build_calls'],calls)
                import pandas as pd
                pd.testing.assert_frame_equal(saved,app.session_state['nba_build_result']['result']['portfolio'])
