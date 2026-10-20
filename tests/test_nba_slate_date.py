import unittest
import pandas as pd
from simmah_nba_slate_date import resolve_slate_date

class SlateDateTests(unittest.TestCase):
    def test_renamed_fanduel_uses_exact_saved_contest(self):
        slate={'players':pd.DataFrame(),'contests':[{'id':'135251-281018991','entry_fee':.05}]}
        self.assertEqual(resolve_slate_date(slate,'my-entries.csv'),'2026-10-20')
    def test_embedded_game_times_take_eastern_date(self):
        slate={'players':pd.DataFrame({'Game Start':['2026-10-21T01:30:00Z']}),'contests':[]}
        self.assertEqual(resolve_slate_date(slate,'renamed.csv'),'2026-10-20')
    def test_unknown_has_no_today_fallback_and_conflicts_rejected(self):
        slate={'players':pd.DataFrame(),'contests':[{'id':'999999','entry_fee':.05}]}
        self.assertIsNone(resolve_slate_date(slate,'my-entries.csv'))
        slate['date']='2026-10-20'
        with self.assertRaises(ValueError):resolve_slate_date(slate,'FanDuel-NBA-2026-10-21-entries.csv')
    def test_mismatched_fee_does_not_resolve_from_saved_contest(self):
        slate={'players':pd.DataFrame(),'contests':[{'id':'135251-281018991','entry_fee':1}]}
        self.assertIsNone(resolve_slate_date(slate,'renamed.csv'))

    def test_undated_unknown_file_renders_date_prompt_without_network(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        testdir=str(Path(__file__).parent)
        source="""
import sys
sys.path.insert(0,TESTDIR)
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
from test_nba_import import NBAImportTests
from simmah_nba_import import render_setup
upload=SimpleNamespace(name='entries.csv',getvalue=NBAImportTests().template)
tabs=st.tabs(['Contests','Roster','Build','Lineups'])
with patch('simmah_nba_projections.download_dff',side_effect=AssertionError('No network before date')):
    render_setup(st,upload,tabs,st.container())
""".replace('TESTDIR',repr(testdir))
        app=AppTest.from_string(source).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.date_input),1)
        self.assertIsNone(app.date_input[0].value)
