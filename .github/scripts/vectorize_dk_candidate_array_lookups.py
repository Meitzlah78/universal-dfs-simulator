from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

old_setup = '''            flex_names = np.asarray(flex_pool, dtype=object)\n            flex_log_weights = np.log(np.clip(flex_rank_weights, 1e-300, None))\n'''
new_setup = '''            flex_names = np.asarray(flex_pool, dtype=object)\n            # Precompute numeric FLEX metadata once per captain. Candidate batches can\n            # then index NumPy arrays directly instead of rebuilding Python dict rows.\n            flex_salary_values = np.asarray(\n                [int(salary_map.get(str(name), 0)) for name in flex_names],\n                dtype=np.int32,\n            )\n            flex_team_values = np.asarray(\n                [str(team_map.get(str(name), '')) for name in flex_names],\n                dtype=object,\n            )\n            flex_log_weights = np.log(np.clip(flex_rank_weights, 1e-300, None))\n'''

old_hot = '''                sampled_names = flex_names[sampled_indices]\n                sampled_salaries = np.asarray(\n                    [[int(salary_map.get(str(name), 0)) for name in row] for row in sampled_names],\n                    dtype=np.int32,\n                )\n                batch_salary = int(captain_salary_map.get(captain, 0)) + sampled_salaries.sum(axis=1, dtype=np.int32)\n'''
new_hot = '''                sampled_names = flex_names[sampled_indices]\n                batch_salary = (\n                    int(captain_salary_map.get(captain, 0))\n                    + flex_salary_values[sampled_indices].sum(axis=1, dtype=np.int32)\n                )\n'''

old_team = '''                captain_team = str(team_map.get(captain, ''))\n                sampled_teams = np.asarray(\n                    [[str(team_map.get(str(name), '')) for name in row] for row in sampled_names],\n                    dtype=object,\n                )\n                batch_valid &= np.any(sampled_teams != captain_team, axis=1)\n'''
new_team = '''                captain_team = str(team_map.get(captain, ''))\n                batch_valid &= np.any(\n                    flex_team_values[sampled_indices] != captain_team,\n                    axis=1,\n                )\n'''

for old, new, label in [
    (old_setup, new_setup, 'setup'),
    (old_hot, new_hot, 'salary hotpath'),
    (old_team, new_team, 'team hotpath'),
]:
    if text.count(old) != 1:
        raise SystemExit(f'SAFE_ABORT {label}: expected 1 anchor, found {text.count(old)}')
    text = text.replace(old, new, 1)

path.write_text(text)
