from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''    dk_salary_range = st.slider(\n        "Allowed lineup salary range",\n        min_value=0,\n        max_value=50000,\n        value=(45000, 50000),\n        step=100,\n        format="$%d",\n        key="dk_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),\n        help="Only build lineups whose total salary falls inside this range."\n    )\n'''

new = '''    dk_salary_range = st.slider(\n        "Allowed lineup salary range",\n        min_value=0,\n        max_value=50000,\n        value=(40000, 50000) if lineup_mode in ("Showdown", "Single Game") else (45000, 50000),\n        step=100,\n        format="$%d",\n        key="dk_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),\n        help="Only build lineups whose total salary falls inside this range."\n    )\n'''

if new in text:
    print("Single-game salary minimum default already set to $40,000.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Set Showdown and Single Game default minimum lineup salary to $40,000.")
else:
    raise SystemExit("Could not find single-game salary range slider block")
