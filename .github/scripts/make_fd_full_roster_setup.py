from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.

old = '''        fd_progress_bar = None
        fd_workflow_status = None
        if fd_run_all_clicked:
            fd_progress_bar = st.progress(2, text="Step 1 of 4: Running player simulations...")
            fd_workflow_status = st.empty()
            fd_workflow_status.info(f"Step 1 of 4: Running {SIMULATION_COUNT:,} player simulations...")'''
new = '''        fd_workflow_status = None
        if fd_run_all_clicked:
            fd_workflow_status = st.empty()
            fd_workflow_status.info(
                f"Step 1 of 4: Running {SIMULATION_COUNT:,} player simulations for FanDuel {lineup_mode}..."
            )'''
if old in text:
    text = text.replace(old, new, 1)

old = '''            if fd_run_all_clicked:
                fd_progress_bar.progress(25, text="Step 2 of 4: Building your candidate lineups...")
                fd_workflow_status.info("Step 2 of 4: Preparing rankings and building your candidate lineups...")'''
new = '''            if fd_run_all_clicked:
                fd_workflow_status.info(
                    "Step 2 of 4: Preparing rankings and building your candidate lineups..."
                )'''
if old in text:
    text = text.replace(old, new, 1)

old = '''            max_attempts = 150000 if lineup_mode == "Full Roster" else 500000
            player_build_counts = {str(name): 0 for name in names}'''
new = '''            max_attempts = 150000 if lineup_mode == "Full Roster" else 500000
            player_build_counts = {str(name): 0 for name in names}
            fd_build_progress = st.progress(
                0,
                text=f"Building FanDuel {lineup_mode} lineups: 0 / {target_lineups:,}"
            )'''
if old in text:
    text = text.replace(old, new, 1)

old = '''                if fd_run_all_clicked and (build_attempt % 1000 == 0):
                    build_progress = min(
                        49,
                        25 + int(24 * max(
                            len(results) / max(target_lineups, 1),
                            build_attempt / max_attempts
                        ))
                    )
                    fd_progress_bar.progress(
                        build_progress,
                        text=f"Step 2 of 4: Building lineups — {len(results):,} of {target_lineups:,} accepted..."
                    )'''
new = '''                if build_attempt % 250 == 0:
                    fd_build_progress.progress(
                        min(0.99, build_attempt / max_attempts),
                        text=f"Building FanDuel {lineup_mode} lineups: {len(results):,} / {target_lineups:,} (checking valid rosters)"
                    )'''
if old in text:
    text = text.replace(old, new, 1)

old = '''                                max_remaining_salary = 0
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
                                    feasible_choices.append(int(candidate_i))'''
new = '''                                max_remaining_salary = 0
                                min_remaining_salary = 0
                                possible = True
                                temp_reserved_max = set(reserved)
                                temp_reserved_min = set(reserved)
                                for remaining_slot, _remaining_positions in remaining_roster:
                                    remaining_choices_max = [
                                        j for j in eligible_indices[remaining_slot]
                                        if j not in temp_reserved_max
                                    ]
                                    remaining_choices_min = [
                                        j for j in eligible_indices[remaining_slot]
                                        if j not in temp_reserved_min
                                    ]
                                    if not remaining_choices_max or not remaining_choices_min:
                                        possible = False
                                        break
                                    best_j = max(remaining_choices_max, key=lambda j: int(salaries[j]))
                                    cheap_j = min(remaining_choices_min, key=lambda j: int(salaries[j]))
                                    max_remaining_salary += int(salaries[best_j])
                                    min_remaining_salary += int(salaries[cheap_j])
                                    temp_reserved_max.add(int(best_j))
                                    temp_reserved_min.add(int(cheap_j))
                                candidate_total = salary + int(salaries[candidate_i])
                                if (
                                    possible
                                    and candidate_total + max_remaining_salary >= salary_min
                                    and candidate_total + min_remaining_salary <= salary_max
                                ):
                                    feasible_choices.append(int(candidate_i))'''
if old in text:
    text = text.replace(old, new, 1)
elif "min_remaining_salary = 0" not in text:
    raise SystemExit("FanDuel salary feasibility block not found")

marker = "# Salary-floor feasibility. Keep only picks"
pos = text.find(marker)
old_pick = '''                        weights /= exposure_penalty
                        weights /= weights.sum()
                        picked = int(rng.choice(choices, p=weights))'''
new_pick = '''                        weights /= exposure_penalty
                        weight_total = weights.sum()
                        if not np.isfinite(weight_total) or weight_total <= 0:
                            weights = np.full(len(choices), 1.0 / len(choices), dtype=float)
                        else:
                            weights /= weight_total
                        if lineup_mode == "Full Roster" and rng.random() < 0.25:
                            picked = int(rng.choice(choices))
                        else:
                            picked = int(rng.choice(choices, p=weights))'''
if pos >= 0:
    pick_pos = text.find(old_pick, pos)
    if pick_pos >= 0:
        text = text[:pick_pos] + text[pick_pos:].replace(old_pick, new_pick, 1)

old = '''                results.append({**chosen, "Salary": salary, "ProjectedPoints": round(total_points, 2), "Score": round(total_score, 2)})
                if len(results) >= target_lineups:
                    break

            if results:'''
new = '''                results.append({**chosen, "Salary": salary, "ProjectedPoints": round(total_points, 2), "Score": round(total_score, 2)})
                if len(results) % 100 == 0 or len(results) >= target_lineups:
                    fd_build_progress.progress(
                        min(1.0, len(results) / target_lineups),
                        text=f"Building FanDuel {lineup_mode} lineups: {len(results):,} / {target_lineups:,}"
                    )
                if len(results) >= target_lineups:
                    break
            fd_build_progress.empty()

            if results:'''
if old in text:
    text = text.replace(old, new, 1)

text = text.replace('''            if fd_run_all_clicked:
                fd_progress_bar.progress(
                    50,
                    text="Step 3 of 4: Building the simulated opponent field..."
                    if results else "Step 2 of 4: Lineup build did not produce valid lineups."
                )
                if results:
                    fd_workflow_status.info("Step 3 of 4: Building the simulated opponent field...")''', '''            if fd_run_all_clicked and results:
                fd_workflow_status.info("Step 3 of 4: Building the simulated opponent field...")''')
text = text.replace('''                fd_progress_bar.progress(78, text="Step 4 of 4: Scoring your lineups against the contest field...")
                fd_workflow_status.info("Step 4 of 4: Scoring your lineups against the contest field...")''', '''                fd_workflow_status.info("Step 4 of 4: Scoring your lineups against the contest field...")''')
text = text.replace('''            fd_progress_bar.progress(100, text="FanDuel SIM complete.")
            fd_workflow_status.success("FanDuel SIM complete: player simulations, lineup build, opponent field, and contest comparison finished.")''', '''            fd_workflow_status.success("FanDuel SIM complete: player simulations, lineup build, opponent field, and contest comparison finished.")''')

path.write_text(text, encoding="utf-8")
