from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
old = '''                            _fd_scenario_count = min(250, len(_fd_holdout_pool))
                            _fd_scenario_idx = _fd_holdout_pool[
                                np.linspace(0, len(_fd_holdout_pool) - 1, _fd_scenario_count, dtype=int)
                            ]
'''
new = '''                            # Top-heavy 200K+ entry GPP ROI is dominated by rare first-place
                            # outcomes. Use the entire untouched holdout pool for the final joint
                            # portfolio evaluation instead of only 250 scenarios; otherwise a
                            # handful of wins can move expected ROI by thousands of percent.
                            _fd_scenario_count = len(_fd_holdout_pool)
                            _fd_scenario_idx = _fd_holdout_pool
'''
if old not in text:
    raise SystemExit("target holdout sampling block not found")
text = text.replace(old, new, 1)
path.write_text(text)
print("Updated FanDuel Full Roster final ROI to use the full holdout sample.")
