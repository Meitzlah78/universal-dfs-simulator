from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''    weights = opponent_field_selection_weights(ownership_pool, means)\n    weights = np.clip(weights, 0.01, None)\n    weights /= weights.sum()\n'''
new = '''    # DK Showdown needs a stronger public-field fallback than the shared full-roster\n    # helper. Real large-field Showdown contests concentrate heavily around the best\n    # projected/chalk constructions; a soft rank-squared fallback makes opponents too\n    # random and inflates our portfolio's Top-1% and ROI. Keep true external ownership\n    # first, but when it is absent use a DK-only projection-rank curve.\n    _own_lookup = {str(c).strip().casefold(): c for c in ownership_pool.columns}\n    _own_col = next((_own_lookup[k] for k in (\n        "projected own %", "ownership %", "projected ownership",\n        "projected own", "ownership", "own%", "own"\n    ) if k in _own_lookup), None)\n    if _own_col is not None:\n        _external_ownership = pd.to_numeric(\n            ownership_pool[_own_col], errors="coerce"\n        ).fillna(0.0).to_numpy(dtype=float)\n    else:\n        _external_ownership = np.zeros(len(ownership_pool), dtype=float)\n    if np.clip(_external_ownership, 0.0, None).sum() > 0:\n        weights = np.clip(_external_ownership, 0.01, None)\n    else:\n        _ranks = pd.Series(means).rank(pct=True).to_numpy(dtype=float)\n        # Sharper than the shared 0.10 + rank^2 fallback, but retains a nonzero\n        # contrarian tail. This is intentionally scoped to DK Showdown only.\n        weights = np.clip(0.02 + _ranks ** 3.25, 0.01, None)\n    weights /= weights.sum()\n'''
if new in text:
    print("DK Showdown field fallback already isolated.")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Installed DK-only Showdown field fallback weighting.")
else:
    raise SystemExit("Could not find Showdown opponent weighting block")
