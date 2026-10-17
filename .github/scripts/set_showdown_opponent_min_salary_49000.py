from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''        picked = rng.choice(len(names), size=6, replace=False, p=weights)
        # Captain selection uses Captain ownership when available; otherwise it
        # falls back to the same ownership-first overall field weights.
        captain_weights = np.clip(captain_base_weights[picked], 0.01, None)
        captain_weights = captain_weights / captain_weights.sum()
        captain_idx = int(rng.choice(picked, p=captain_weights))
        flex_idx = picked[picked != captain_idx]
        salary = int(captain_salaries[captain_idx] + salaries[flex_idx].sum())
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

new = '''        # Build the public field the same way we learned from the completed
        # Showdown study: choose Captain from Captain ownership first, then choose
        # five FLEX players from overall field ownership. Choosing six players first
        # and only then assigning Captain distorts both Captain ownership and lineup
        # construction.
        captain_weights = np.clip(captain_base_weights, 0.01, None)
        captain_weights = captain_weights / captain_weights.sum()
        captain_idx = int(rng.choice(len(names), p=captain_weights))

        flex_weights = weights.copy()
        flex_weights[captain_idx] = 0.0
        if flex_weights.sum() <= 0:
            continue
        flex_weights /= flex_weights.sum()
        flex_idx = rng.choice(len(names), size=5, replace=False, p=flex_weights)
        picked = np.concatenate(([captain_idx], flex_idx))

        salary = int(captain_salaries[captain_idx] + salaries[flex_idx].sum())
        if salary > salary_cap:
            continue

        # Diagnostic based on the real completed field: salary was concentrated
        # close to the cap, with a median near $49.7K. Require $49K+ opponents.
        # This affects only the simulated opponent field, never the user's BUILD.
        if salary < 49000:
            continue

        if len(set(teams[picked])) < 2:
            continue
'''

if old not in text:
    raise SystemExit("Could not find current Showdown opponent construction block")

path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Applied Captain-first ownership construction and $49K opponent salary floor.")
