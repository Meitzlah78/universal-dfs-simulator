from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings behavior is intentionally untouched.
old = '''    dk_salary_range = st.slider(
        "Allowed lineup salary range",
        min_value=0,
        max_value=50000,
        value=(40000, 50000) if lineup_mode in ("Showdown", "Single Game") else (45000, 50000),
        step=100,
        format="$%d",
        key="dk_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),
        help="Only build lineups whose total salary falls inside this range."
    )'''
new = '''    _fd_full = platform == "FanDuel" and lineup_mode == "Full Roster"
    _salary_cap = 60000 if _fd_full else 50000
    _salary_default = (57000, 60000) if _fd_full else ((40000, 50000) if lineup_mode in ("Showdown", "Single Game") else (45000, 50000))
    dk_salary_range = st.slider(
        "Allowed lineup salary range",
        min_value=0,
        max_value=_salary_cap,
        value=_salary_default,
        step=100,
        format="$%d",
        key="dk_build_salary_range_" + platform.lower() + "_" + lineup_mode.replace(" ", "_").lower(),
        help="Only build lineups whose total salary falls inside this range."
    )'''
if old not in text:
    raise SystemExit("salary slider block not found")
text = text.replace(old, new, 1)

# If the full-roster stack selector uses the shared default, make FanDuel Full Roster
# start with no stack rule without changing DraftKings defaults.
old_stack = '''default=["No stack rule"] if platform == "DraftKings" and lineup_mode == "Classic" else None,'''
if old_stack in text:
    new_stack = '''default=["No stack rule"] if ((platform == "DraftKings" and lineup_mode == "Classic") or (platform == "FanDuel" and lineup_mode == "Full Roster")) else None,'''
    text = text.replace(old_stack, new_stack, 1)

path.write_text(text, encoding="utf-8")
