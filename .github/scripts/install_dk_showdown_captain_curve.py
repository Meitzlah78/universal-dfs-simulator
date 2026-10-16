from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''    captain_weights = np.clip(captain_base_weights, 0.01, None)\n    captain_weights /= captain_weights.sum()\n'''
new = '''    captain_weights = np.clip(captain_base_weights, 0.01, None)\n    # Completed large-field DK Showdown data is materially more concentrated at\n    # Captain than a straight ownership draw. BUF@LAR put about 59.7% of entries\n    # on its top four Captains. Sharpen Captain only; FLEX remains ownership-first.\n    captain_weights = np.power(captain_weights, 1.45)\n    captain_weights /= captain_weights.sum()\n'''
if new in text:
    print("DK Showdown Captain curve already installed.")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Installed calibrated DK Showdown Captain curve.")
else:
    raise SystemExit("Could not find DK Showdown Captain weighting block")
