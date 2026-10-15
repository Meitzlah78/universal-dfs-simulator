from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Split the difference between the prior field and the 0.20 strength test.
needle = '''                                    # Mild 0.20 power keeps ownership/diversity dominant while
                                    # removing a little of the weak-lineup bias seen in sanity checks.
                                    weights = weights * np.power(_fd_mean_scale, 0.20)
'''
replacement = '''                                    # 0.10 splits the difference between the original field and
                                    # the 0.20 test that made the FanDuel field slightly too strong.
                                    weights = weights * np.power(_fd_mean_scale, 0.10)
'''
if needle not in text:
    raise SystemExit("FanDuel Full Roster field-strength adjustment not found")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
