import ast
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
from simmah_snapshot_archive import archive_snapshot


def test_archive_preserves_versions_and_separates_slates():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        frame = pd.DataFrame({'Name': ['A'], 'Projection': [20.], 'Snapshot Saved ET': ['one']})
        meta = {'format': 'DraftKings Classic', 'slate_id': 'slate1', 'game_lines': [{'total': 48}], 'saved_at_et': 'one'}
        first = archive_snapshot(root, frame, meta, 'dk', 'slate1')
        original = first.read_bytes()
        frame['Snapshot Saved ET'] = 'two'
        assert archive_snapshot(root, frame, dict(meta, saved_at_et='two'), 'dk', 'slate1') == first
        frame['Projection'] = 22.
        second = archive_snapshot(root, frame, meta, 'dk', 'slate1')
        assert first != second and first.read_bytes() == original
        assert archive_snapshot(root, frame, meta, 'dk', 'slate2').parent != first.parent
        assert json.loads(first.with_suffix('.json').read_text())['game_lines'][0]['total'] == 48


def test_export_callback_copies_exact_payload():
    with tempfile.TemporaryDirectory() as tmp:
        tree = ast.parse(Path('dfs_app.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'save_export_checkpoint')
        errors = []
        st = SimpleNamespace(session_state={}, error=errors.append, toast=lambda message: None)
        ns = {'pd': pd, 'st': st, '_pregame_snapshot_dir': lambda: Path(tmp), '_safe_snapshot_slug': lambda v: 'dk'}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'dfs_app.py', 'exec'), ns)
        payload = b'Entry ID,QB\r\n123,456\r\n'
        ns[fn.name](pd.DataFrame({'Name':['A']}), {'format':'DraftKings Classic','slate_id':'slate1'}, payload, 'upload.csv')
        assert not errors
        path = Path(st.session_state['last_export_snapshot_path'])
        assert path.with_name(path.stem + '_lineups.csv').read_bytes() == payload
        assert json.loads(path.with_suffix('.json').read_text())['export_filename'] == 'upload.csv'
