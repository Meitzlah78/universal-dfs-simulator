from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old_alias = '''    own_col = next((lookup[k] for k in (
        "field own %", "ownership %", "projected ownership", "ownership", "own%", "own"
    ) if k in lookup), None)
'''
new_alias = '''    own_col = next((lookup[k] for k in (
        "field own %", "projected own %", "ownership %", "projected ownership",
        "projected own", "ownership", "own%", "own"
    ) if k in lookup), None)
'''

old_salary = '''        salary = int(captain_salaries[captain_idx] + salaries[flex_idx].sum())
        if salary > salary_cap:
            continue
        if len(set(teams[picked])) < 2:
            continue
'''
new_salary = '''        salary = int(captain_salaries[captain_idx] + salaries[flex_idx].sum())
        if salary > salary_cap:
            continue

        # Completed large-field Showdown contests show that the public field is not
        # six random legal players. Most entries use a meaningful amount of the cap,
        # while low-salary constructions still exist as a smaller contrarian tail.
        # Keep those low-salary lineups possible, but make them progressively rarer.
        # This strengthens the simulated public field without making it use the same
        # ceiling/leverage optimizer as SIMMAH's candidate builder.
        if salary < 40000:
            low_salary_acceptance = float(np.exp((salary - 40000) / 4000.0))
            if rng.random() > low_salary_acceptance:
                continue

        if len(set(teams[picked])) < 2:
            continue
'''

changed = False
if new_alias not in text:
    if old_alias not in text:
        raise SystemExit("Could not find opponent ownership alias block")
    text = text.replace(old_alias, new_alias, 1)
    changed = True

if new_salary not in text:
    if old_salary not in text:
        raise SystemExit("Could not find Showdown opponent salary block")
    text = text.replace(old_salary, new_salary, 1)
    changed = True

if changed:
    path.write_text(text, encoding="utf-8")
    print("Calibrated Showdown opponent field strength.")
else:
    print("Showdown opponent field strength calibration already applied.")
