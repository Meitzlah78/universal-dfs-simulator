from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old_import = """    sample_opponent_batch as dk_sample_opponent_batch,\n    score_lineup_matrix as dk_score_lineup_matrix,\n)"""
new_import = """    sample_opponent_batch as dk_sample_opponent_batch,\n    score_lineup_matrix as dk_score_lineup_matrix,\n    weighted_score_bounds as dk_weighted_score_bounds,\n)"""
if old_import not in text:
    raise SystemExit("DK engine import target not found")
text = text.replace(old_import, new_import, 1)

start_marker = """        # Score the user's portfolio as entries in the SAME contest. Each candidate\n"""
end_marker = """        # Convert sampled opponent results to a smoothed full-field rank estimate.\n"""
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("DK rank hotpath target not found")

new = """        # Score the user's portfolio in the same contest. For DK Showdown, use\n        # exact multiplicity-aware opponent bounds instead of physically sorting\n        # every duplicated opponent score. Portfolio entries still count once.\n        comparison_field_size = total_field + max(0, n_candidates - 1)\n        if is_dk_showdown:\n            field_left, field_right = dk_weighted_score_bounds(\n                batch_field_scores, contest_multiplicity, batch_candidate_scores\n            )\n            portfolio_left = np.sum(\n                batch_candidate_scores[:, :, None] < batch_candidate_scores[:, None, :],\n                axis=1,\n            )\n            portfolio_right = np.sum(\n                batch_candidate_scores[:, :, None] <= batch_candidate_scores[:, None, :],\n                axis=1,\n            )\n            left_low = field_left + portfolio_left\n            low = field_right + portfolio_right\n            search_field_size = total_field + n_candidates\n        else:\n            if n_candidates > 1:\n                combined_scores = np.concatenate((batch_field_scores, batch_candidate_scores), axis=1)\n                sorted_field = np.sort(combined_scores, axis=1)\n            else:\n                sorted_field = np.sort(batch_field_scores, axis=1)\n\n            batch_count = batch_end - batch_start\n            search_field_size = sorted_field.shape[1]\n            low = np.zeros((batch_count, n_candidates), dtype=np.int32)\n            high = np.full((batch_count, n_candidates), search_field_size, dtype=np.int32)\n            sim_rows = np.arange(batch_count)[:, None]\n            while np.any(low < high):\n                active = low < high\n                mid = np.minimum((low + high) // 2, search_field_size - 1)\n                mid_values = sorted_field[sim_rows, mid]\n                move_right = (mid_values <= batch_candidate_scores) & active\n                move_left = (mid_values > batch_candidate_scores) & active\n                low = np.where(move_right, mid + 1, low)\n                high = np.where(move_left, mid, high)\n\n            left_low = np.zeros((batch_count, n_candidates), dtype=np.int32)\n            left_high = np.full((batch_count, n_candidates), search_field_size, dtype=np.int32)\n            while np.any(left_low < left_high):\n                active_left = left_low < left_high\n                mid_left = np.minimum((left_low + left_high) // 2, search_field_size - 1)\n                mid_left_values = sorted_field[sim_rows, mid_left]\n                move_right_left = (mid_left_values < batch_candidate_scores) & active_left\n                move_left_left = (mid_left_values >= batch_candidate_scores) & active_left\n                left_low = np.where(move_right_left, mid_left + 1, left_low)\n                left_high = np.where(move_left_left, mid_left, left_high)\n\n        count_greater = search_field_size - low\n        percentiles = 1.0 - (count_greater / max(1, comparison_field_size))\n\n"""
text = text[:start] + new + text[end:]
path.write_text(text)
print("wired DK weighted rank hotpath")
