from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''        # Completed large-field Showdown contests show that the public field is not
        # six random legal players. Most entries use a meaningful amount of the cap,
        # while low-salary constructions still exist as a smaller contrarian tail.
        # Keep those low-salary lineups possible, but make them progressively rarer.
        # This strengthens the simulated public field without making it use the same
        # ceiling/leverage optimizer as SIMMAH's candidate builder.
        if salary < 40000:
            low_salary_acceptance = float(np.exp((salary - 40000) / 4000.0))
            if rng.random() > low_salary_acceptance:
                continue
'''

new = '''        # Require simulated Showdown opponents to use at least $45,000 of salary.
        # This applies only to the opponent field, not the user's candidate builder.
        if salary < 45000:
            continue
'''

if old not in text:
    raise SystemExit("Could not find current Showdown opponent salary filter")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("Set Showdown opponent minimum salary to $45,000.")
