from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
old = '''    if cpt_col is not None:
        captain_base_weights = pd.to_numeric(ownership_pool[cpt_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        if captain_base_weights.sum() <= 0:
            captain_base_weights = weights.copy()
    else:
        captain_base_weights = weights.copy()
'''
new = '''    has_external_captain_ownership = False
    if cpt_col is not None:
        captain_base_weights = pd.to_numeric(ownership_pool[cpt_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        has_external_captain_ownership = bool(np.clip(captain_base_weights, 0.0, None).sum() > 0)
        if not has_external_captain_ownership:
            captain_base_weights = weights.copy()
    else:
        captain_base_weights = weights.copy()
'''
if old not in text:
    raise SystemExit("captain source block not found")
text = text.replace(old, new, 1)
old2 = '''    captain_weights = np.clip(captain_base_weights, 0.01, None)
    # Completed large-field DK Showdown data is materially more concentrated at
    # Captain than a straight ownership draw. BUF@LAR put about 59.7% of entries
    # on its top four Captains. Sharpen Captain only; FLEX remains ownership-first.
    captain_weights = np.power(captain_weights, 1.45)
    captain_weights /= captain_weights.sum()
'''
new2 = '''    captain_weights = np.clip(captain_base_weights, 0.01, None)
    # Role-specific Field CPT ownership is already calibrated for Captain and must
    # not be sharpened a second time. Only sharpen the fallback curve derived from
    # FLEX/overall ownership; completed BUF@LAR data had ~59.7% on the top four CPTs.
    if not has_external_captain_ownership:
        captain_weights = np.power(captain_weights, 1.45)
    captain_weights /= captain_weights.sum()
'''
if old2 not in text:
    raise SystemExit("captain sharpening block not found")
path.write_text(text)
