import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import re
import unittest
import pandas as pd


class DraftKingsContestExportTest(unittest.TestCase):
    def setUp(self):
        self.source = Path('dfs_app.py').read_text()
        tree = ast.parse(self.source)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'build_dk_contest_entry_export')
        self.st = SimpleNamespace(session_state={}, error=Mock(), success=Mock(), info=Mock())
        scope = {'st': self.st, 'pd': pd, 're': re, 'is_full_game_contest_name': lambda name: True}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'app', 'exec'), scope)
        self.export = scope['build_dk_contest_entry_export']
        self.slots = ['QB','RB','RB','WR','WR','WR','TE','FLEX','DST']
        columns = ['Entry ID','Contest ID','Contest Name','Entry Fee','QB','RB','RB.1','WR','WR.1','WR.2','TE','FLEX','DST']
        rows = [['1','100','Free contest',0] + ['old']*9]
        rows += [[str(100+i),'200','20-entry contest',.1] + ['old']*9 for i in range(20)]
        self.entries = pd.DataFrame(rows, columns=columns)
        self.lineups = pd.DataFrame([[str(10000+r*10+s) for s in range(9)] for r in range(20)], columns=self.slots)

    def test_paid_contest_export_replaces_all_twenty_entry_ids(self):
        result = self.export(self.entries, '200', self.lineups, self.slots, 'Classic')
        self.assertEqual(len(result), 20)
        self.assertEqual(result['Entry ID'].tolist(), [str(100+i) for i in range(20)])
        self.assertEqual(set(result['Contest ID']), {'200'})
        self.assertFalse(result.iloc[:,4:].eq('old').any().any())
        self.assertIn('other 1 entries', self.st.info.call_args[0][0])

    def test_free_contest_export_explicitly_reports_twenty_excluded_entries(self):
        result = self.export(self.entries, '100', self.lineups, self.slots, 'Classic')
        self.assertEqual(result['Entry ID'].tolist(), ['1'])
        self.assertIn('other 20 entries', self.st.info.call_args[0][0])

    def test_one_lineup_cannot_partially_replace_twenty_reserved_entries(self):
        result = self.export(self.entries, '200', self.lineups.head(1), self.slots, 'Classic')
        self.assertIsNone(result)
        self.assertIn('20 reserved entries', self.st.error.call_args[0][0])

    def test_contest_selector_requires_explicit_choice_and_download_names_show_scope(self):
        tree = ast.parse(self.source)
        selectors = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == 'selectbox'
                     and n.args and isinstance(n.args[0], ast.Constant)
                     and n.args[0].value == 'Contest to build and export']
        self.assertEqual(len(selectors), 1)
        index = next(k.value for k in selectors[0].keywords if k.arg == 'index')
        self.assertIsNone(index.value)
        self.assertIn('DraftKings_Classic_{selected_contest_id}_{len(export_df)}_ENTRIES.csv', self.source)
        self.assertIn('DraftKings_Showdown_{selected_contest_id}_{len(export_df)}_ENTRIES.csv', self.source)


if __name__ == '__main__':
    unittest.main()
