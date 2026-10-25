"""Run the app's column discovery before its actual assignment loop."""
import ast
from pathlib import Path
import unittest

import pandas as pd

APP = Path(__file__).resolve().parents[1] / 'dfs_app.py'


class FanDuelEntryColumnsTest(unittest.TestCase):
    def test_player_columns_do_not_overwrite_entry_metadata(self):
        tree = ast.parse(APP.read_text())
        finder = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == 'fd_find_column')
        discovery = sorted((n for n in ast.walk(tree)
                            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                            and isinstance(n.value.func, ast.Name)
                            and n.value.func.id == 'fd_find_column'), key=lambda n: n.lineno)
        assignment = next(n for n in ast.walk(tree)
                          if isinstance(n, ast.For) and isinstance(n.target, ast.Tuple)
                          and [getattr(t, 'id', None) for t in n.target.elts]
                          == ['_source_column', '_output_column'])
        for count in (1, 53):
            for name_header, id_header in [('Nickname', 'Id'), ('Name', 'Player ID')]:
                with self.subTest(count=count, name_header=name_header, id_header=id_header):
                    entries = pd.DataFrame({
                        'entry_id': [str(1000 + i) for i in range(count)],
                        'contest_id': ['111-222' if i < 51 else '111-333' for i in range(count)],
                        'contest_name': ['Paid' if i < 51 else 'Free' for i in range(count)],
                    })
                    env = dict(fd_entries_col='entry_id', fd_id_col='contest_id',
                               fd_name_col='contest_name', fd_assignment_entries=entries,
                               fd_export_portfolio=pd.DataFrame({'QB': ['Player'] * count}),
                               fd_raw=pd.DataFrame(columns=[name_header, id_header, 'Salary', 'Team', 'Position']))
                    code = ast.Module(body=[finder, *discovery, assignment], type_ignores=[])
                    exec(compile(code, str(APP), 'exec'), env)
                    report = env['fd_export_portfolio']
                    for source, output in [('entry_id', 'Entry ID'), ('contest_id', 'Contest ID'), ('contest_name', 'Contest Name')]:
                        self.assertEqual(report[output].tolist(), entries[source].tolist())


if __name__ == '__main__':
    unittest.main()
