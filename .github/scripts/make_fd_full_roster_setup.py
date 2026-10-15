from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings behavior is intentionally untouched.
old_salary = '''        fd_salary_range = st.slider(
            "Allowed lineup salary range",
            min_value=0,
            max_value=60000,
            value=(54000, 60000),
            step=100,
            format="$%d",
            key="fd_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),
            help="Only build lineups whose total salary falls inside this range."
        )'''
new_salary = '''        fd_salary_range = st.slider(
            "Allowed lineup salary range",
            min_value=0,
            max_value=60000,
            value=(57000, 60000) if lineup_mode == "Full Roster" else (54000, 60000),
            step=100,
            format="$%d",
            key="fd_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),
            help="Only build lineups whose total salary falls inside this range."
        )'''
if old_salary in text:
    text = text.replace(old_salary, new_salary, 1)
elif new_salary not in text:
    raise SystemExit("FanDuel salary slider block not found")

old_stack = '''            default=["QB + 2 teammates + bring-back"],
            key="fd_full_roster_stack_rules",'''
new_stack = '''            default=["No stack rule"],
            key="fd_full_roster_stack_rules",'''
if old_stack in text:
    text = text.replace(old_stack, new_stack, 1)
elif new_stack not in text:
    raise SystemExit("FanDuel Full Roster stack default block not found")

path.write_text(text, encoding="utf-8")
