from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''        salary = int(captain_salaries[captain_idx] + salaries[flex_idx].sum())
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

new = '''        salary = int(captain_salaries[captain_idx] + salaries[flex_idx].sum())
        if salary > salary_cap:
            continue

        # Public Showdown fields are ownership-driven, but they are not six fully
        # independent ownership draws. Better players tend to construct lineups that
        # use the salary cap efficiently. Keep contrarian salary left on the table,
        # but make weak constructions progressively less common.
        salary_left = max(0, int(salary_cap - salary))
        if salary_left > 500:
            salary_acceptance = float(np.exp(-(salary_left - 500) / 7000.0))
            if rng.random() > salary_acceptance:
                continue

        # Add a mild lineup-strength filter using the same simulation means that are
        # already available to the opponent generator. This is deliberately much
        # softer than the user's candidate optimizer: it only removes a portion of
        # obviously weak public constructions while ownership remains the main draw.
        lineup_mean = float(means[picked].sum() + means[captain_idx] * 0.5)
        pool_mean = float(np.mean(means)) if len(means) else 0.0
        baseline_mean = max(0.01, pool_mean * 6.5)
        strength_ratio = lineup_mean / baseline_mean
        if strength_ratio < 1.0:
            strength_acceptance = float(np.clip(0.35 + 0.65 * strength_ratio, 0.35, 1.0))
            if rng.random() > strength_acceptance:
                continue

        if len(set(teams[picked])) < 2:
            continue
'''

if new in text:
    print("Showdown opponent strength calibration already applied.")
elif old not in text:
    raise SystemExit("Could not find current Showdown opponent acceptance block")
else:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Strengthened Showdown opponent construction.")
