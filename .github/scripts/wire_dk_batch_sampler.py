from pathlib import Path
p=Path('dfs_app.py'); s=p.read_text()
old='    duplicate_expansion_weights as dk_duplicate_expansion_weights,\n)'
new='    duplicate_expansion_weights as dk_duplicate_expansion_weights,\n    sample_opponent_batch as dk_sample_opponent_batch,\n)'
if s.count(old)!=1: raise SystemExit('SAFE_ABORT import')
s=s.replace(old,new,1)
start=s.index('    while len(rows) < target and attempts < max_attempts:')
end=s.index('\n    return pd.DataFrame.from_records(rows, columns=columns)',start)
oldblock=s[start:end]
if 'rng.choice(len(names), size=5, replace=False, p=flex_weights)' not in oldblock: raise SystemExit('SAFE_ABORT loop')
newblock='''    captain_weights = np.clip(captain_base_weights, 0.01, None)\n    captain_weights /= captain_weights.sum()\n    batch_size = min(4096, max(512, int(target)))\n    while len(rows) < target and attempts < max_attempts:\n        n = min(batch_size, max_attempts - attempts)\n        captain_batch, flex_batch = dk_sample_opponent_batch(rng, captain_weights, weights, n)\n        attempts += n\n        salary_batch = captain_salaries[captain_batch] + salaries[flex_batch].sum(axis=1)\n        picked_teams = teams[flex_batch]\n        multi_team = np.any(picked_teams != teams[captain_batch][:, None], axis=1)\n        valid = np.flatnonzero((salary_batch <= salary_cap) & (salary_batch >= 49000) & multi_team)\n        for i in valid:\n            f = flex_batch[i]\n            rows.append((names[captain_batch[i]], names[f[0]], names[f[1]], names[f[2]], names[f[3]], names[f[4]], int(salary_batch[i])))\n            if len(rows) >= target: break\n        if progress_bar is not None:\n            progress_bar.progress(min(0.99, attempts / max_attempts), text=f"Building opponent lineups: {len(rows):,} of {target:,} accepted (attempt {attempts:,})")\n'''
s=s[:start]+newblock+s[end:]
p.write_text(s)
