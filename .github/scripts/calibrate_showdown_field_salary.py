from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''        # Require simulated Showdown opponents to use at least $45,000 of salary.
        # This applies only to the opponent field, not the user's candidate builder.
        if salary < 45000:
            continue
'''

new = '''        # Calibrate opponent salary usage to the completed 59,453-entry DK Showdown
        # field we studied. After removing bad salary parses, the real field had:
        # mean $49,459; P5 $48,200; P10 $48,700; P25 $49,300; median $49,700;
        # P75 $49,900; P90/P95 $50,000. Keep the user's requested $45K hard floor,
        # then acceptance-sample legal lineups so the 10K representative field has
        # the same strong concentration near the salary cap instead of treating all
        # $45K-$50K constructions equally.
        if salary < 45000:
            continue
        salary_left = int(salary_cap - salary)
        if salary_left <= 100:
            salary_acceptance = 1.00
        elif salary_left <= 300:
            salary_acceptance = 0.92
        elif salary_left <= 700:
            salary_acceptance = 0.72
        elif salary_left <= 1300:
            salary_acceptance = 0.42
        elif salary_left <= 1800:
            salary_acceptance = 0.20
        else:
            salary_acceptance = 0.06
        if rng.random() > salary_acceptance:
            continue
'''

if old not in text:
    raise SystemExit("Could not find the $45,000 Showdown opponent salary filter")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("Calibrated Showdown opponent salary usage to real DK field behavior.")
