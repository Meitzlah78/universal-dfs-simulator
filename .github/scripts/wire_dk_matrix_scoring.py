from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old_import = '''    sample_opponent_batch as dk_sample_opponent_batch,\n)'''
new_import = '''    sample_opponent_batch as dk_sample_opponent_batch,\n    score_lineup_matrix as dk_score_lineup_matrix,\n)'''
if old_import not in text:
    raise SystemExit("DK engine import anchor not found")
text = text.replace(old_import, new_import, 1)

old_batch = '''        batch_candidate_scores = batch_values[:, candidate_idx].sum(axis=2)\n        batch_field_scores = batch_values[:, contest_idx].sum(axis=2)\n\n        if scoring_multiplier != 1.0:\n            batch_candidate_scores += batch_values[:, candidate_idx[:, 0]] * (scoring_multiplier - 1.0)\n            batch_field_scores += batch_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)'''
new_batch = '''        if scoring_multiplier == 1.5 and candidate_idx.shape[1] == 6:\n            batch_candidate_scores = dk_score_lineup_matrix(\n                batch_values, candidate_idx[:, 0], candidate_idx[:, 1:]\n            )\n            batch_field_scores = dk_score_lineup_matrix(\n                batch_values, contest_idx[:, 0], contest_idx[:, 1:]\n            )\n        else:\n            # Preserve the existing generic full-roster scoring path.\n            batch_candidate_scores = batch_values[:, candidate_idx].sum(axis=2)\n            batch_field_scores = batch_values[:, contest_idx].sum(axis=2)'''
if old_batch not in text:
    raise SystemExit("contest scoring anchor not found")
text = text.replace(old_batch, new_batch, 1)

old_diag = '''            _diag_scores = _diag_values[:, _diag_candidate_idx].sum(axis=2)\n            _diag_field_scores = _diag_values[:, contest_idx].sum(axis=2)\n            if scoring_multiplier != 1.0:\n                _diag_scores[:, :] += _diag_values[:, _diag_candidate_idx[:, 0]] * (scoring_multiplier - 1.0)\n                _diag_field_scores[:, :] += _diag_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)'''
new_diag = '''            if scoring_multiplier == 1.5 and _diag_candidate_idx.shape[1] == 6:\n                _diag_scores = dk_score_lineup_matrix(\n                    _diag_values, _diag_candidate_idx[:, 0], _diag_candidate_idx[:, 1:]\n                )\n                _diag_field_scores = dk_score_lineup_matrix(\n                    _diag_values, contest_idx[:, 0], contest_idx[:, 1:]\n                )\n            else:\n                _diag_scores = _diag_values[:, _diag_candidate_idx].sum(axis=2)\n                _diag_field_scores = _diag_values[:, contest_idx].sum(axis=2)'''
if old_diag not in text:
    raise SystemExit("holdout scoring anchor not found")
text = text.replace(old_diag, new_diag, 1)

path.write_text(text)
print("Wired DK Showdown contest and holdout scoring to dk_score_lineup_matrix")
