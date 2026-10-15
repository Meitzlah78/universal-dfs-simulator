from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Apply a small field-strength adjustment: keep the same DK-style ownership weights,
# but lean Full Roster opponent selections slightly toward stronger simulated means.
needle = '''                                weights = np.clip(fd_weights[choices].astype(float), 0.0001, None)
                                weights /= weights.sum()
                                picked_idx = int(rng.choice(choices, p=weights))
'''
replacement = '''                                weights = np.clip(fd_weights[choices].astype(float), 0.0001, None)
                                if lineup_mode == "Full Roster":
                                    _fd_choice_means = np.clip(fd_field_projections[choices].astype(float), 0.01, None)
                                    _fd_mean_scale = _fd_choice_means / max(float(np.mean(_fd_choice_means)), 0.01)
                                    # Mild 0.20 power keeps ownership/diversity dominant while
                                    # removing a little of the weak-lineup bias seen in sanity checks.
                                    weights = weights * np.power(_fd_mean_scale, 0.20)
                                weights /= weights.sum()
                                picked_idx = int(rng.choice(choices, p=weights))
'''
if needle not in text:
    raise SystemExit("FanDuel Full Roster field-weight block not found")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
