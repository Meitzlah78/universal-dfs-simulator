import importlib.util
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
                for key in ['nba_entries_download','nba_portfolio_report_lineups']:
                    matching=[b for b in buttons if b.proto.id.endswith('-'+key)]
                    self.assertEqual(len(matching),1,key)
                    self.assertFalse(matching[0].proto.disabled,key)
                for key in ['nba_entries_download_build','nba_portfolio_report_build']:
                    self.assertFalse(any(b.proto.id.endswith('-'+key) for b in buttons),key)
                entry_buttons=[b for b in app.tabs[3].get('download_button') if 'EDIT ENTRIES CSV' in b.proto.label]
                self.assertEqual(len(entry_buttons),1)
                self.assertFalse(any('EDIT ENTRIES CSV' in b.proto.label for b in app.tabs[2].get('download_button')))
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
