from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Do not merely reject low-salary lineups after they are built. During each
# roster pick, remove choices that make the requested salary floor impossible.
old_loop = '''                else:
                    for slot, _ in roster:
                        choices = np.asarray([
                            i for i in eligible_indices[slot]
                            if i not in used and salary + salaries[i] <= salary_max
                        ], dtype=int)
                        if not len(choices):
                            break
                        weights = lineup_scores[choices].copy()'''
new_loop = '''                else:
                    for roster_pos, (slot, _) in enumerate(roster):
                        choices = np.asarray([
                            i for i in eligible_indices[slot]
                            if i not in used and salary + salaries[i] <= salary_max
                        ], dtype=int)
                        if not len(choices):
                            break

                        # Salary-floor feasibility. Keep only picks that leave a path
                        # to at least the requested minimum salary with the remaining
                        # FanDuel roster slots. This prevents 0-lineup builds at $57K+.
                        if salary_min > 0 and roster_pos < len(roster) - 1:
                            feasible_choices = []
                            remaining_roster = roster[roster_pos + 1:]
                            for candidate_i in choices:
                                reserved = used | {int(candidate_i)}
                                max_remaining_salary = 0
                                possible = True
                                temp_reserved = set(reserved)
                                for remaining_slot, _remaining_positions in remaining_roster:
                                    remaining_choices = [
                                        j for j in eligible_indices[remaining_slot]
                                        if j not in temp_reserved
                                    ]
                                    if not remaining_choices:
                                        possible = False
                                        break
                                    best_j = max(remaining_choices, key=lambda j: int(salaries[j]))
                                    max_remaining_salary += int(salaries[best_j])
                                    temp_reserved.add(int(best_j))
                                if possible and salary + int(salaries[candidate_i]) + max_remaining_salary >= salary_min:
                                    feasible_choices.append(int(candidate_i))
                            if feasible_choices:
                                choices = np.asarray(feasible_choices, dtype=int)
                            else:
                                break
                        elif salary_min > 0 and roster_pos == len(roster) - 1:
                            choices = np.asarray([
                                i for i in choices
                                if salary + int(salaries[i]) >= salary_min
                            ], dtype=int)
                            if not len(choices):
                                break

                        weights = lineup_scores[choices].copy()'''
if old_loop in text:
    text = text.replace(old_loop, new_loop, 1)
elif "Salary-floor feasibility. Keep only picks" not in text:
    raise SystemExit("FanDuel Full Roster build loop not found")

path.write_text(text, encoding="utf-8")
