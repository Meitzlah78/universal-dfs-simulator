"""Fresh uploads must reach detection/parsing in the selecting run."""
import ast
import csv
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from simmah_slate_workspaces import StoredUpload, select_upload

ROOT = Path(__file__).resolve().parents[1]


class FreshUploadTest(unittest.TestCase):
    def test_dk_and_fd_uploads_are_immediately_available_and_survive_rerun(self):
        tree = ast.parse((ROOT / 'dfs_app.py').read_text())
        detector = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'detect_uploaded_dfs_format')
        env = {}
        exec(compile(ast.Module(body=[detector],type_ignores=[]), 'detector', 'exec'), env)
        cases = [
            ('DKEntries.csv', b'Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n123,Dime Package,456,.10,,,,,,,,,\n', 'DraftKings Classic'),
            ('FanDuel.csv', b'entry_id,contest_id,contest_name,entry_fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DEF\n123,111-222,Pooch Punt,.05,,,,,,,,,\n\nId,Nickname\n111-1,Player\n', 'FanDuel Full Roster'),
        ]
        for name, raw, expected in cases:
            with self.subTest(name=name):
                state={'_slate_fresh_mode':True}
                st=SimpleNamespace(session_state=state)
                with patch('simmah_archive_ui.capture_upload'):
                    selected=select_upload(st,StoredUpload(raw,name))
                    self.assertIsNotNone(selected, 'CSV must be available immediately after selection')
                    self.assertEqual(selected.getvalue(), raw)
                    self.assertEqual(env['detect_uploaded_dfs_format'](selected), expected)
                    self.assertNotIn('_slate_incoming',state)
                    self.assertNotIn('_slate_pending',state)
                    after_rerun=select_upload(st,None)
                    self.assertEqual(after_rerun.getvalue(), raw)
                    rows=list(csv.reader(io.StringIO(after_rerun.getvalue().decode())))
                    self.assertEqual(rows[1][0], '123')


if __name__ == '__main__': unittest.main()
