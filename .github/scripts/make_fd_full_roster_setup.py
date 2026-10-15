from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''    # A full slate at 10,000 x ~64 literal plays is millions of Python iterations.
    # Build 1,000 complete correlated game scripts, then resample COMPLETE scripts.
    # This keeps Step 1 fast without breaking within-game/player correlation.
    n = min(requested_n, 1000)
'''
new = '''    # Streamlit cannot afford thousands of literal full-slate play loops.
    # Build 150 complete correlated game scripts, then bootstrap COMPLETE rows.
    # Whole-row resampling keeps QB/receiver/team/opponent outcomes tied together.
    n = min(requested_n, 150)
'''
if old not in s:
    raise SystemExit("1000-scenario block not found")
s = s.replace(old, new, 1)

p.write_text(s)
print("FanDuel play-by-play scenario bank reduced to 150 complete games for fast Step 1")
