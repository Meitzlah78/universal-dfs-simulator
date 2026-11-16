import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

APP='''
import streamlit as st
from simmah_diagnostic_packages import render_nfl_package,CAPTURE_VERSION
site=st.session_state.get('fixture_site','FanDuel')
mode='Single Game' if site=='FanDuel' else 'Showdown'
st.session_state['dfs_format']=site+' '+mode
st.session_state['selected_fd_contest' if site=='FanDuel' else 'selected_dk_contest']={'id':'test'}
st.session_state['diagnostic_package_current']={'format':site+' '+mode,'contest_id':'test','filename':'audit.zip','captured_at':'saved','digest':'a'*64}
st.session_state['diagnostic_package_error_version']=CAPTURE_VERSION
st.session_state['diagnostic_package_error']='Diagnostic save needs attention'
render_nfl_package(st)
st.download_button('Download assigned entries',b'entry csv',file_name='entries.csv')
'''

class DiagnosticsPlacementTests(unittest.TestCase):
    def test_both_nfl_sites_collapse_reports_but_leave_warning_and_entries_visible(self):
        for site in ('FanDuel','DraftKings'):
            with patch('simmah_package_download.package_download_data',return_value=b'audit zip'):
                app=AppTest.from_string(APP);app.session_state['fixture_site']=site;app.run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.expander),1);section=app.expander[0]
            self.assertFalse(section.proto.expanded)
            self.assertEqual(len(section.get('download_button')),1)
            self.assertFalse(section.warning)
            self.assertEqual(len(app.warning),1)
            self.assertEqual(len(app.get('download_button')),2)

if __name__=='__main__':unittest.main()
