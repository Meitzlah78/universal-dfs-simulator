from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
old_start = '''        fd_progress_bar = None
        if fd_run_all_clicked:
            fd_progress_bar = st.progress(2, text="Starting FanDuel simulation...")
        if fd_sim_clicked:
            with st.spinner(f"Running {SIMULATION_COUNT:,} shared historical/PBP simulations for FanDuel..."):'''
new_start = '''        fd_progress_bar = None
        fd_workflow_status = None
        if fd_run_all_clicked:
            fd_progress_bar = st.progress(2, text="Step 1 of 4: Running player simulations...")
            fd_workflow_status = st.empty()
            fd_workflow_status.info(f"Step 1 of 4: Running {SIMULATION_COUNT:,} player simulations...")
        if fd_sim_clicked:
            with st.spinner(f"Running {SIMULATION_COUNT:,} shared historical/PBP simulations for FanDuel..."):'''
if old_start in text:
    text = text.replace(old_start, new_start, 1)
elif new_start not in text:
    raise SystemExit("FanDuel progress start block not found")

old_sim_done = '''            if fd_run_all_clicked:
                fd_progress_bar.progress(30, text="Shared historical/PBP simulation complete. Building FanDuel lineups...")'''
new_sim_done = '''            if fd_run_all_clicked:
                fd_progress_bar.progress(25, text="Step 2 of 4: Building your candidate lineups...")
                fd_workflow_status.info("Step 2 of 4: Preparing rankings and building your candidate lineups...")'''
if old_sim_done in text:
    text = text.replace(old_sim_done, new_sim_done, 1)
elif new_sim_done not in text:
    raise SystemExit("FanDuel simulation-complete progress block not found")

old_build_progress = '''                    build_progress = min(
                        59,
                        30 + int(29 * max(
                            len(results) / max(target_lineups, 1),
                            build_attempt / max_attempts
                        ))
                    )
                    fd_progress_bar.progress(
                        build_progress,
                        text=f"Building FanDuel lineups: {len(results):,} of {target_lineups:,} accepted (attempt {build_attempt:,} of {max_attempts:,})..."
                    )'''
new_build_progress = '''                    build_progress = min(
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
if old_build_progress in text:
    text = text.replace(old_build_progress, new_build_progress, 1)
elif new_build_progress not in text:
    raise SystemExit("FanDuel lineup progress block not found")

old_build_done = '''            if fd_run_all_clicked:
                fd_progress_bar.progress(
                    60,
                    text="Lineup build complete. Simulating the contest field..."
                    if results else "Lineup build did not produce valid lineups."
                )'''
new_build_done = '''            if fd_run_all_clicked:
                fd_progress_bar.progress(
                    50,
                    text="Step 3 of 4: Building the simulated opponent field..."
                    if results else "Step 2 of 4: Lineup build did not produce valid lineups."
                )
                if results:
                    fd_workflow_status.info("Step 3 of 4: Building the simulated opponent field...")'''
if old_build_done in text:
    text = text.replace(old_build_done, new_build_done, 1)
elif new_build_done not in text:
    raise SystemExit("FanDuel build-complete progress block not found")

old_field_pct = '''                            progress_pct = 60 + int(35 * min(field_progress, 1.0))
                            fd_progress_bar.progress(
                                min(progress_pct, 95),
                                text=(
                                    f"Simulating contest field: {len(opponent_rows):,} of "
                                    f"{fd_opponent_target:,} opponents (attempt {attempts:,})..."
                                )
                            )'''
new_field_pct = '''                            progress_pct = 50 + int(25 * min(field_progress, 1.0))
                            fd_progress_bar.progress(
                                min(progress_pct, 75),
                                text=(
                                    f"Step 3 of 4: Building opponent field — {len(opponent_rows):,} of "
                                    f"{fd_opponent_target:,} lineups..."
                                )
                            )'''
if old_field_pct in text:
    text = text.replace(old_field_pct, new_field_pct, 1)
elif new_field_pct not in text:
    raise SystemExit("FanDuel field progress block not found")

old_compare = '''                    user_lineups = st.session_state.get(fd_build_key)
                    if user_lineups is None or user_lineups.empty:'''
new_compare = '''                    if fd_run_all_clicked:
                        fd_progress_bar.progress(78, text="Step 4 of 4: Scoring your lineups against the contest field...")
                        fd_workflow_status.info("Step 4 of 4: Scoring your lineups against the contest field...")
                    user_lineups = st.session_state.get(fd_build_key)
                    if user_lineups is None or user_lineups.empty:'''
if old_compare in text:
    text = text.replace(old_compare, new_compare, 1)
elif new_compare not in text:
    raise SystemExit("FanDuel contest comparison block not found")

old_finish = '''            if fd_run_all_clicked:
                fd_progress_bar.progress(
                    100,
                    text="FanDuel SIM → BUILD → CONTEST SIM finished."
                )'''
new_finish = '''            if fd_run_all_clicked:
                fd_progress_bar.progress(100, text="FanDuel SIM complete.")
                fd_workflow_status.success("FanDuel SIM complete: player simulations, lineup build, opponent field, and contest comparison finished.")'''
if old_finish in text:
    text = text.replace(old_finish, new_finish, 1)
elif new_finish not in text:
    raise SystemExit("FanDuel finish progress block not found")

path.write_text(text, encoding="utf-8")
