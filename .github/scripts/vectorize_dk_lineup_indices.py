from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old = '''    candidate_idx = np.array([\n        [player_index[row[col]] for col in lineup_cols]\n        for _, row in candidates_df.iterrows()\n    ], dtype=np.int16)\n\n    contest_idx = np.array([\n        [player_index[row[col]] for col in lineup_cols]\n        for _, row in contest_field_df.iterrows()\n    ], dtype=np.int16)'''
new = '''    # Build compact lineup index matrices with vectorized pandas mapping.\n    # This avoids Python iterrows() across thousands of candidate/field rows.\n    _candidate_names = candidates_df.loc[:, lineup_cols]\n    _contest_names = contest_field_df.loc[:, lineup_cols]\n    _candidate_mapped = _candidate_names.apply(lambda col: col.map(player_index))\n    _contest_mapped = _contest_names.apply(lambda col: col.map(player_index))\n\n    if _candidate_mapped.isna().any().any() or _contest_mapped.isna().any().any():\n        _known_players = set(player_index)\n        _missing = sorted(\n            {str(v) for v in _candidate_names.to_numpy().ravel() if v not in _known_players}\n            | {str(v) for v in _contest_names.to_numpy().ravel() if v not in _known_players}\n        )\n        raise ValueError(\n            "Contest scoring contains players missing from simulation_df: "\n            + ", ".join(_missing[:10])\n        )\n\n    candidate_idx = _candidate_mapped.to_numpy(dtype=np.int16, copy=False)\n    contest_idx = _contest_mapped.to_numpy(dtype=np.int16, copy=False)'''

if old not in text:
    raise SystemExit("lineup index construction anchor not found")
text = text.replace(old, new, 1)
path.write_text(text)
print("Vectorized candidate and contest lineup index construction")
