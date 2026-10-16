from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old_import = """    sample_opponent_batch as dk_sample_opponent_batch,\n    score_lineup_matrix as dk_score_lineup_matrix,\n)"""
new_import = """    sample_opponent_batch as dk_sample_opponent_batch,\n    score_lineup_matrix as dk_score_lineup_matrix,\n    weighted_score_bounds as dk_weighted_score_bounds,\n)"""
if old_import not in text:
    raise SystemExit("DK engine import target not found")
text = text.replace(old_import, new_import, 1)

old = """        combined_scores = np.concatenate([batch_field_scores, batch_portfolio_scores], axis=1)\n        sorted_scores = np.sort(combined_scores, axis=1)\n        right_idx = np.sum(sorted_scores[:, :, None] <= batch_portfolio_scores[:, None, :], axis=1)\n        left_idx = np.sum(sorted_scores[:, :, None] < batch_portfolio_scores[:, None, :], axis=1)\n"""
new = """        if is_dk_showdown:\n            # Exact expanded-field rank boundaries without physically scoring/sorting\n            # every duplicated opponent lineup. Portfolio entries still count once.\n            field_left, field_right = dk_weighted_score_bounds(\n                batch_field_scores, contest_multiplicity, batch_portfolio_scores\n            )\n            portfolio_left = np.sum(\n                batch_portfolio_scores[:, :, None] < batch_portfolio_scores[:, None, :],\n                axis=1,\n            )\n            portfolio_right = np.sum(\n                batch_portfolio_scores[:, :, None] <= batch_portfolio_scores[:, None, :],\n                axis=1,\n            )\n            left_idx = field_left + portfolio_left\n            right_idx = field_right + portfolio_right\n        else:\n            combined_scores = np.concatenate([batch_field_scores, batch_portfolio_scores], axis=1)\n            sorted_scores = np.sort(combined_scores, axis=1)\n            right_idx = np.sum(sorted_scores[:, :, None] <= batch_portfolio_scores[:, None, :], axis=1)\n            left_idx = np.sum(sorted_scores[:, :, None] < batch_portfolio_scores[:, None, :], axis=1)\n"""
if old not in text:
    raise SystemExit("DK rank hotpath target not found")
text = text.replace(old, new, 1)
path.write_text(text)
print("wired DK weighted rank hotpath")
