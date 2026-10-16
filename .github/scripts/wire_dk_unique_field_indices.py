from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
old = '''    candidate_idx = _candidate_mapped.to_numpy(dtype=np.int16, copy=False)\n    contest_idx = _contest_mapped.to_numpy(dtype=np.int16, copy=False)\n\n    n_candidates = len(candidate_idx)\n'''
new = '''    candidate_idx = _candidate_mapped.to_numpy(dtype=np.int16, copy=False)\n    contest_idx = _contest_mapped.to_numpy(dtype=np.int16, copy=False)\n\n    # DK Showdown fields contain heavy duplication. Canonicalize FLEX order,\n    # collapse identical opponent lineups once, and retain exact multiplicities.\n    # This prepares the hot scoring path to score unique opponents only.\n    is_dk_showdown = platform == "DraftKings" and lineup_mode != "Classic"\n    if is_dk_showdown and len(contest_idx):\n        _contest_canonical = contest_idx.copy()\n        _contest_canonical[:, 1:] = np.sort(_contest_canonical[:, 1:], axis=1)\n        contest_unique_idx, contest_multiplicity = np.unique(\n            _contest_canonical, axis=0, return_counts=True\n        )\n        contest_unique_idx = contest_unique_idx.astype(np.int16, copy=False)\n        contest_multiplicity = contest_multiplicity.astype(np.int32, copy=False)\n    else:\n        contest_unique_idx = contest_idx\n        contest_multiplicity = np.ones(len(contest_idx), dtype=np.int32)\n\n    n_candidates = len(candidate_idx)\n'''
if old not in text:
    raise SystemExit("target block not found; refusing unsafe patch")
text = text.replace(old, new, 1)
path.write_text(text)
