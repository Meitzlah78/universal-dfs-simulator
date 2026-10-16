from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''    captain_weights = np.clip(captain_base_weights, 0.01, None)
    # Completed large-field DK Showdown data is materially more concentrated at
    # Captain than a straight ownership draw. BUF@LAR put about 59.7% of entries
    # on its top four Captains. Sharpen Captain only; FLEX remains ownership-first.
    captain_weights = np.power(captain_weights, 1.45)
    captain_weights /= captain_weights.sum()
'''
new = '''    captain_weights = np.clip(captain_base_weights, 0.01, None)
    # A real Field CPT Own % column is already role-specific public ownership.
    # Do not sharpen it a second time. Only sharpen the fallback curve derived
    # from FLEX/projection ownership; completed BUF@LAR data put about 59.7% of
    # entries on its top four Captains, which is the fallback calibration target.
    has_external_captain_ownership = cpt_col is not None and float(np.clip(captain_base_weights, 0.0, None).sum()) > 0
    if not has_external_captain_ownership:
        captain_weights = np.power(captain_weights, 1.45)
    captain_weights /= captain_weights.sum()
'''

if new in text:
    print("DK captain ownership source fix already applied.")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Applied DK captain ownership source fix.")
else:
    raise SystemExit("Could not find DK captain weighting block")
