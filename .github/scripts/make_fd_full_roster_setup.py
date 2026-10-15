from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Fix the KeyError from a missing salary-bound entry. More importantly, if a
# required FD roster slot has no eligible players, stop cleanly and show which
# slot is missing instead of crashing.
old = '''                            min_remaining_salary = sum(
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
'''
new = '''                            missing_remaining_slots = [
                                remaining_slot
                                for remaining_slot, _remaining_positions in remaining_roster
                                if remaining_slot not in fd_slot_salary_bounds
                            ]
                            if missing_remaining_slots:
                                choices = np.asarray([], dtype=int)
                            else:
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
'''
if old not in text:
    raise SystemExit("Expected FanDuel salary-bound block not found")
text = text.replace(old, new, 1)

# Give a useful error when the filtered FanDuel simulation pool is missing a
# required position (most commonly DEF/D). This keeps the app from hiding the
# actual cause behind a generic zero-lineup message.
old_error = '''            else:
                st.error(
                    "No valid lineups found. Check player positions, salary values, "
                    "and make sure the uploaded slate has enough players for this contest type."
                )
'''
new_error = '''            else:
                if lineup_mode == "Full Roster":
                    missing_slots = [slot for slot, _eligible in roster if not len(eligible_indices.get(slot, []))]
                    if missing_slots:
                        st.error(
                            "No valid FanDuel Full Roster lineups found because the filtered player pool "
                            f"has no eligible players for: {', '.join(missing_slots)}."
                        )
                    else:
                        st.error(
                            "No valid lineups found. Check player positions, salary values, "
                            "and make sure the uploaded slate has enough players for this contest type."
                        )
                else:
                    st.error(
                        "No valid lineups found. Check player positions, salary values, "
                        "and make sure the uploaded slate has enough players for this contest type."
                    )
'''
if old_error in text:
    text = text.replace(old_error, new_error, 1)

path.write_text(text, encoding="utf-8")
