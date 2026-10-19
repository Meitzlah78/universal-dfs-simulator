"""Real Streamlit layout smoke tests with public network calls disabled."""
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import requests

class DashboardSmokeTests(unittest.TestCase):
    def test_new_layout_renders_without_entry_file(self):
        for format_name in ['DraftKings Classic','DraftKings Showdown','FanDuel Full Roster','FanDuel Single Game']:
            with self.subTest(format=format_name):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'dfs_app.py'),default_timeout=30)
                app.session_state['dfs_format']=format_name
                with patch('requests.sessions.Session.request',side_effect=requests.ConnectionError('offline layout check')),patch('urllib.request.urlopen',side_effect=OSError('offline layout check')):
                    app.run()
                self.assertFalse(app.exception, '\n'.join(str(e.message) for e in app.exception))
                self.assertEqual([tab.label for tab in app.tabs],['Contests','Roster & Projections','Build'])
                self.assertTrue(any('SIMMAH' in str(item.value) for item in app.markdown))
                self.assertTrue(any(widget.label=='Format' for widget in app.selectbox))
    def test_compact_editor_retains_hidden_data(self):
        app=AppTest.from_string('''
import streamlit as st
import pandas as pd
from simmah_ui import render_brand,player_columns,player_column_config
st.set_page_config(layout="wide")
render_brand(st)
p=pd.DataFrame({'Name':['Player'],'Salary':[5000],'Projection':[10.],'Lock':[False],'Internal diagnostic':[123]})
edited=st.data_editor(p,column_order=player_columns(p),column_config=player_column_config(st),row_height=32,height=660,key='pool')
st.session_state['returned_columns']=list(edited.columns)
''',default_timeout=10).run()
        self.assertFalse(app.exception)
        self.assertIn('Internal diagnostic',app.session_state['returned_columns'])

class DiversityControlTests(unittest.TestCase):
    def test_exposure_slider_does_not_change_scenario_construction(self):
        app=AppTest.from_string("""
import streamlit as st
from simmah_ui import render_diversity_controls
exposure,construction=render_diversity_controls(st,'FanDuel','Single Game',10000)
st.session_state['observed']=(exposure,construction)
""",default_timeout=10).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['observed'],(50,1.))
        app.slider(key='portfolio_exposure_diversity_FanDuel_Single Game_v1').set_value(100).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['observed'],(100,1.))
        self.assertEqual(app.slider(key='lineup_build_aggressiveness_FanDuel_Single Game').value,100)

if __name__=='__main__':unittest.main()
