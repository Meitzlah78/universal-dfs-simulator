import importlib.util
from pathlib import Path
import sys
import unittest

@unittest.skipUnless(importlib.util.find_spec('streamlit'),'Streamlit not installed')
class NBAExportPlacementTests(unittest.TestCase):
    def test_both_sites_offer_entries_and_report_in_build_and_lineups(self):
        from streamlit.testing.v1 import AppTest
        sys.path.insert(0,str(Path(__file__).parent))
        for platform in ['FanDuel','DraftKings']:
            with self.subTest(platform=platform):
                app=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py')))
                app.session_state['fixture_platform']=platform
                app.run(timeout=20).button(key='nba_build').click().run(timeout=20)
                self.assertFalse(app.exception)
                buttons=app.get('download_button')
                for key in ['nba_entries_download_build','nba_entries_download',
                            'nba_portfolio_report_build','nba_portfolio_report_lineups']:
                    matching=[b for b in buttons if b.proto.id.endswith('-'+key)]
                    self.assertEqual(len(matching),1,key)
                    self.assertFalse(matching[0].proto.disabled,key)
                if platform=='FanDuel':
                    self.assertEqual(len([b for b in app.get('link_button') if 'OPEN FANDUEL' in b.proto.label]),2)
