from pathlib import Path

path = Path("dfs_app.py")
s = path.read_text()

old = '''    own_col = next((lookup[k] for k in (
        "field own %", "projected own %", "ownership %", "projected ownership",
        "projected own", "ownership", "own%", "own"
    ) if k in lookup), None)
'''
new = '''    # Never feed ownership measured from a previous simulated field back into
    # the next FanDuel opponent build. That creates a self-reinforcing field and
    # can make the representative opponents much weaker than the user's lineups.
    # Prefer true/pregame projected ownership; fall back to the projection-rank
    # proxy below when no external ownership is available.
    own_col = next((lookup[k] for k in (
        "projected own %", "ownership %", "projected ownership",
        "projected own", "ownership", "own%", "own"
    ) if k in lookup), None)
'''
if old not in s:
    raise SystemExit("ownership marker not found")
s = s.replace(old, new, 1)

old2 = '''                                # 0.10 splits the difference between the original field and
                                # the 0.20 test that made the FanDuel field slightly too strong.
                                weights = weights * np.power(_fd_mean_scale, 0.10)
'''
new2 = '''                                # Full-roster GPP opponents should be competitive rather
                                # than near-random within each position. Blend ownership with
                                # simulated mean strength while leaving Single Game untouched.
                                weights = weights * np.power(_fd_mean_scale, 0.20)
'''
if old2 not in s:
    raise SystemExit("field-strength marker not found")
s = s.replace(old2, new2, 1)

path.write_text(s)
print("Patched FanDuel Full Roster opponent field strength; DraftKings/Single Game unchanged")
