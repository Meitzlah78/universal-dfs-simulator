from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
old = '''            batch_field_scores = dk_score_lineup_matrix(\n                batch_values, contest_idx[:, 0], contest_idx[:, 1:]\n            )\n'''
new = '''            _dk_field_idx = contest_unique_idx if is_dk_showdown else contest_idx\n            batch_field_scores = dk_score_lineup_matrix(\n                batch_values, _dk_field_idx[:, 0], _dk_field_idx[:, 1:]\n            )\n'''
if old not in text:
    raise SystemExit("DK field scoring target not found; refusing unsafe patch")
text = text.replace(old, new, 1)
# Do not yet replace rank/tie logic: compressed scores require weighted bounds.
path.write_text(text)
