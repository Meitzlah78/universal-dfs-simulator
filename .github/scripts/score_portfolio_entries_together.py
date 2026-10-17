from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''        batch_candidate_scores = batch_values[:, candidate_idx].sum(axis=2)\n        batch_field_scores = batch_values[:, contest_idx].sum(axis=2)\n\n        if scoring_multiplier != 1.0:\n            batch_candidate_scores += batch_values[:, candidate_idx[:, 0]] * (scoring_multiplier - 1.0)\n            batch_field_scores += batch_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)\n\n        # Sort every simulation's opponent scores together along the opponent axis.\n        sorted_field = np.sort(batch_field_scores, axis=1)\n'''

new = '''        batch_candidate_scores = batch_values[:, candidate_idx].sum(axis=2)\n        batch_field_scores = batch_values[:, contest_idx].sum(axis=2)\n\n        if scoring_multiplier != 1.0:\n            batch_candidate_scores += batch_values[:, candidate_idx[:, 0]] * (scoring_multiplier - 1.0)\n            batch_field_scores += batch_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)\n\n        # Score the user's portfolio as entries in the SAME contest. Each candidate\n        # must compete with the other submitted portfolio entries, not only with\n        # simulated opponents. Exclude the candidate itself from its comparison\n        # field so the field size remains opponents + the other user entries.\n        if n_candidates > 1:\n            portfolio_scores = batch_candidate_scores\n            combined_scores = np.concatenate((batch_field_scores, portfolio_scores), axis=1)\n            sorted_combined = np.sort(combined_scores, axis=1)\n        else:\n            portfolio_scores = None\n            sorted_combined = np.sort(batch_field_scores, axis=1)\n\n        # Sort every simulation's opponent scores together along the opponent axis.\n        # Candidate-specific searches below correct for the candidate's own score\n        # when the full portfolio was appended to the comparison field.\n        sorted_field = sorted_combined\n'''

old2 = '''        batch_count = batch_end - batch_start\n        low = np.zeros((batch_count, n_candidates), dtype=np.int32)\n        high = np.full((batch_count, n_candidates), total_field, dtype=np.int32)\n        sim_rows = np.arange(batch_count)[:, None]\n'''
new2 = '''        batch_count = batch_end - batch_start\n        comparison_field_size = total_field + max(0, n_candidates - 1)\n        search_field_size = sorted_field.shape[1]\n        low = np.zeros((batch_count, n_candidates), dtype=np.int32)\n        high = np.full((batch_count, n_candidates), search_field_size, dtype=np.int32)\n        sim_rows = np.arange(batch_count)[:, None]\n'''

old3 = '''            mid = np.minimum((low + high) // 2, total_field - 1)\n'''
new3 = '''            mid = np.minimum((low + high) // 2, search_field_size - 1)\n'''

old4 = '''        count_greater = total_field - low\n        percentiles = 1.0 - (count_greater / total_field)\n'''
new4 = '''        count_greater = search_field_size - low\n        # The candidate itself is never greater than its own score, so no removal\n        # is needed from count_greater. Percentiles use opponents + other entries.\n        percentiles = 1.0 - (count_greater / max(1, comparison_field_size))\n'''

old5 = '''        left_low = np.zeros((batch_count, n_candidates), dtype=np.int32)\n        left_high = np.full((batch_count, n_candidates), total_field, dtype=np.int32)\n'''
new5 = '''        left_low = np.zeros((batch_count, n_candidates), dtype=np.int32)\n        left_high = np.full((batch_count, n_candidates), search_field_size, dtype=np.int32)\n'''

old6 = '''            mid_left = np.minimum((left_low + left_high) // 2, total_field - 1)\n'''
new6 = '''            mid_left = np.minimum((left_low + left_high) // 2, search_field_size - 1)\n'''

old7 = '''        sampled_equal_opponents = low - left_low\n        sampled_rank_equivalent = count_greater + (0.5 * sampled_equal_opponents)\n'''
new7 = '''        # Remove the candidate itself from the equal-score count. Other portfolio\n        # entries with the same score remain in the tie and therefore split prizes.\n        sampled_equal_opponents = np.maximum(0, (low - left_low) - 1)\n        sampled_rank_equivalent = count_greater + (0.5 * sampled_equal_opponents)\n'''

old8 = '''        rank_fraction = (sampled_rank_equivalent + 1.0) / (total_field + 1.0)\n'''
new8 = '''        rank_fraction = (sampled_rank_equivalent + 1.0) / (comparison_field_size + 1.0)\n'''

old9 = '''            (count_greater + 1.0) / (total_field + 1.0), 0.0, 1.0\n'''
new9 = '''            (count_greater + 1.0) / (comparison_field_size + 1.0), 0.0, 1.0\n'''

old10 = '''                    / (total_field + 1.0)\n                    * estimated_full_field_size\n'''
new10 = '''                    / (comparison_field_size + 1.0)\n                    * estimated_full_field_size\n'''

pairs = [(old,new),(old2,new2),(old3,new3),(old4,new4),(old5,new5),(old6,new6),(old7,new7),(old8,new8),(old9,new9),(old10,new10)]
for before, after in pairs:
    if after in text:
        continue
    if before not in text:
        raise SystemExit("Could not find expected Contest Sim scoring block")
    text = text.replace(before, after, 1)

path.write_text(text, encoding="utf-8")
print("Contest Sim now scores portfolio entries together.")
