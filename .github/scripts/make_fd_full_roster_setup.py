from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.

# Precompute cheap salary bounds once per roster slot. The prior constructive
# check rescanned hundreds of players for every candidate on every pick, which
# made Step 2 appear stuck at 0 accepted lineups.
needle = '''                eligible_indices = {
                    slot: np.asarray([i for i, positions in enumerate(eligible_sets) if positions & eligible], dtype=int)
                    for slot, eligible in roster
                }
'''
replacement = '''                eligible_indices = {
                    slot: np.asarray([i for i, positions in enumerate(eligible_sets) if positions & eligible], dtype=int)
                    for slot, eligible in roster
                }
                fd_slot_salary_bounds = {
                    slot: (
                        int(salaries[eligible_indices[slot]].min()),
                        int(salaries[eligible_indices[slot]].max()),
                    )
                    for slot, _eligible in roster
                    if len(eligible_indices[slot])
                }
'''
if needle in text and "fd_slot_salary_bounds" not in text:
    text = text.replace(needle, replacement, 1)

start = text.find('''                        # Salary-floor feasibility. Keep only picks that leave a path''')
end_marker = '''
                        weights = lineup_scores[choices].copy()'''
end = text.find(end_marker, start) if start >= 0 else -1
if start >= 0 and end >= 0:
    fast_block = '''                        # Fast salary feasibility: use precomputed slot salary bounds
                        # instead of rescanning the entire player pool for every choice.
                        remaining_roster = roster[roster_pos + 1:]
                        if remaining_roster:
                            min_remaining_salary = sum(
                                fd_slot_salary_bounds[remaining_slot][0]
                                for remaining_slot, _remaining_positions in remaining_roster
                            )
                            max_remaining_salary = sum(
                                fd_slot_salary_bounds[remaining_slot][1]
                                for remaining_slot, _remaining_positions in remaining_roster
                            )
                            choices = np.asarray([
                                i for i in choices
                                if (
                                    salary + int(salaries[i]) + max_remaining_salary >= salary_min
                                    and salary + int(salaries[i]) + min_remaining_salary <= salary_max
                                )
                            ], dtype=int)
                        else:
                            choices = np.asarray([
                                i for i in choices
                                if salary_min <= salary + int(salaries[i]) <= salary_max
                            ], dtype=int)
                        if not len(choices):
                            break
'''
    text = text[:start] + fast_block + text[end:]
elif "Fast salary feasibility" not in text:
    raise SystemExit("FanDuel salary feasibility block not found")

# Remove the old overall progress-bar references left in the contest phase.
# Keep the DraftKings-style status box and the dedicated lineup build progress bar.
text = text.replace('''                            progress_pct = 50 + int(25 * min(field_progress, 1.0))
                            fd_progress_bar.progress(
                                min(progress_pct, 75),
                                text=(
                                    f"Step 3 of 4: Building opponent field — {len(opponent_rows):,} of "
                                    f"{fd_opponent_target:,} lineups..."
                                )
                            )''', '''                            fd_workflow_status.info(
                                f"Step 3 of 4: Building opponent field — {len(opponent_rows):,} of "
                                f"{fd_opponent_target:,} lineups..."
                            )''')
text = text.replace('''                        fd_progress_bar.progress(78, text="Step 4 of 4: Scoring your lineups against the contest field...")
                        fd_workflow_status.info("Step 4 of 4: Scoring your lineups against the contest field...")''', '''                        fd_workflow_status.info("Step 4 of 4: Scoring your lineups against the contest field...")''')
text = text.replace('''            if fd_run_all_clicked:
                fd_progress_bar.progress(100, text="FanDuel SIM complete.")
                fd_workflow_status.success("FanDuel SIM complete: player simulations, lineup build, opponent field, and contest comparison finished.")''', '''            if fd_run_all_clicked:
                fd_workflow_status.success("FanDuel SIM complete: player simulations, lineup build, opponent field, and contest comparison finished.")''')

path.write_text(text, encoding="utf-8")
