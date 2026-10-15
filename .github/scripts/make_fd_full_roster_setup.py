from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings behavior is intentionally untouched.
# Existing salary/stack/contest-detail patches are already present in dfs_app.py.

old_reset = '''        fd_stack_rules = []
        if fd_build_clicked:'''
new_reset = '''        # Preserve the Full Roster stack selection made above. Single Game has no stack rules.
        if lineup_mode != "Full Roster":
            fd_stack_rules = []
        if fd_build_clicked:'''
if old_reset in text:
    text = text.replace(old_reset, new_reset, 1)
elif new_reset not in text:
    raise SystemExit("FanDuel stack-rule reset block not found")

old_weights = '''                        weights = lineup_scores[choices].copy()
                        # Build the requested QB stack during generation instead of
                        # relying only on post-build rejection.'''
new_weights = '''                        weights = lineup_scores[choices].copy()
                        # Full Roster lineups must spend at least $57K by default. Bias
                        # the random construction toward salary-efficient higher-priced
                        # players so the builder does not create hundreds of thousands
                        # of otherwise-valid lineups that finish below the salary floor.
                        if lineup_mode == "Full Roster":
                            salary_bias = np.clip(salaries[choices].astype(float) / 5000.0, 0.35, 2.5) ** 2.0
                            weights *= salary_bias
                        # Build the requested QB stack during generation instead of
                        # relying only on post-build rejection.'''
if old_weights in text:
    text = text.replace(old_weights, new_weights, 1)
elif "salary_bias = np.clip(salaries[choices].astype(float) / 5000.0" not in text:
    raise SystemExit("FanDuel Full Roster choice-weight block not found")

old_attempts = '''            max_attempts = 500000
            salary_min, salary_max = int(fd_salary_range[0]), min(int(fd_salary_range[1]), 60000)'''
new_attempts = '''            max_attempts = 150000 if lineup_mode == "Full Roster" else 500000
            salary_min, salary_max = int(fd_salary_range[0]), min(int(fd_salary_range[1]), 60000)'''
if old_attempts in text:
    text = text.replace(old_attempts, new_attempts, 1)
elif new_attempts not in text:
    raise SystemExit("FanDuel max-attempt block not found")

path.write_text(text, encoding="utf-8")
