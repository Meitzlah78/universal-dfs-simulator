from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''        captain_weights = np.clip(captain_base_weights[picked], 0.01, None)
        captain_weights = captain_weights / captain_weights.sum()
        captain_idx = int(rng.choice(picked, p=captain_weights))
'''

new = '''        captain_weights = np.clip(captain_base_weights[picked], 0.01, None)
        # Real large-field DK Showdown entries concentrate Captain choices more
        # heavily than FLEX choices. In the completed 59,453-entry BUF@LAR Dime
        # Package, the top four Captains accounted for about 59.7% of entries,
        # versus about 45% in our representative field before this calibration.
        # Sharpen only the Captain probabilities; FLEX/player selection stays
        # ownership-first and otherwise unchanged.
        captain_weights = np.power(captain_weights, 1.45)
        captain_weights = captain_weights / captain_weights.sum()
        captain_idx = int(rng.choice(picked, p=captain_weights))
'''

if new in text:
    print("Showdown Captain concentration calibration already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Calibrated Showdown Captain concentration.")
else:
    raise SystemExit("Could not find Showdown Captain weighting block")
