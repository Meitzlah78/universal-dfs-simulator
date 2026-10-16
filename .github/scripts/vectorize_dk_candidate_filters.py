from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text()

anchor = '''                sampled_indices = np.argpartition(gumbels + flex_log_weights[None, :], -5, axis=1)[:, -5:]\n                captain_attempts += batch_n\n                for sampled_idx in sampled_indices:\n'''
replacement = '''                sampled_indices = np.argpartition(gumbels + flex_log_weights[None, :], -5, axis=1)[:, -5:]\n                captain_attempts += batch_n\n\n                # Reject invalid DK Showdown candidates in one NumPy batch before\n                # entering the remaining duplicate/scoring Python loop.\n                sampled_names = flex_names[sampled_indices]\n                sampled_salaries = np.asarray(\n                    [[int(salary_map.get(str(name), 0)) for name in row] for row in sampled_names],\n                    dtype=np.int32,\n                )\n                batch_salary = int(captain_salary_map.get(captain, 0)) + sampled_salaries.sum(axis=1, dtype=np.int32)\n                batch_valid = (batch_salary >= int(min_salary)) & (batch_salary <= int(max_salary)) & (batch_salary <= int(SALARY_CAP))\n\n                if locked_players:\n                    locked_names = np.asarray([str(name) for name in locked_players], dtype=object)\n                    captain_locked = locked_names == str(captain)\n                    flex_has_locked = (sampled_names[:, :, None] == locked_names[None, None, :]).any(axis=1)\n                    batch_valid &= np.all(flex_has_locked | captain_locked[None, :], axis=1)\n\n                captain_team = str(team_map.get(captain, ''))\n                sampled_teams = np.asarray(\n                    [[str(team_map.get(str(name), '')) for name in row] for row in sampled_names],\n                    dtype=object,\n                )\n                batch_valid &= np.any(sampled_teams != captain_team, axis=1)\n                sampled_indices = sampled_indices[batch_valid]\n\n                for sampled_idx in sampled_indices:\n'''

if s.count(anchor) != 1:
    raise SystemExit('SAFE_ABORT DK candidate batch anchor')
s = s.replace(anchor, replacement, 1)
p.write_text(s)
