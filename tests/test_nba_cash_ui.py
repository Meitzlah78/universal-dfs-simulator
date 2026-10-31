from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

class CashUITests(unittest.TestCase):
    def test_separate_section_both_sites_and_satellite(self):
        for platform,site in [('DraftKings','DK'),('FanDuel','FD')]:
            app=AppTest.from_file(str(Path(__file__).with_name('nba_cash_ui_fixture.py')))
            app.session_state['site']=platform
            app.run().checkbox(key='nba_cash_enable_'+site).check().run()
            self.assertFalse(app.exception)
            app.button(key='nba_cash_build_'+site).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['nba_build_result'],{'sentinel':'tournament unchanged'})
            self.assertEqual(app.session_state['cash_calls'],1)
            self.assertEqual(len(app.dataframe),1)
            app.selectbox(key='nba_cash_kind_'+site).select('Satellite (equal tickets)').run()
            self.assertEqual(len(app.dataframe),0)  # Hide stale cash results.
            app.number_input(key='nba_cash_prize_'+site).set_value(100.).run()
            app.button(key='nba_cash_build_'+site).click().run()
            self.assertFalse(app.exception)
            labels=[d.proto.label for d in app.get('download_button')]
            self.assertIn('DOWNLOAD '+site+' SATELLITE LINEUP REPORT',labels)
            app.number_input(key='nba_cash_fee_'+site).set_value(100.).run()
            self.assertTrue(app.button(key='nba_cash_build_'+site).disabled)
            self.assertEqual(len(app.dataframe),0)
