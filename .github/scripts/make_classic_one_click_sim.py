from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

old_buttons = '''        with build_cols[2]:
            st.write("### Run")
            _classic_run_cols = st.columns(3)
            with _classic_run_cols[0]:
                _classic_sim_button = st.button("SIM", type="primary", use_container_width=True, key="dk_classic_sim")
            with _classic_run_cols[1]:
                _classic_build_button = st.button("BUILD", use_container_width=True, key="dk_classic_build")
            with _classic_run_cols[2]:
                _classic_contest_button = st.button("CONTEST SIM", use_container_width=True, key="dk_classic_contest")
            classic_run_all = _classic_sim_button or _classic_build_button or _classic_contest_button
'''
new_buttons = '''        with build_cols[2]:
            st.write("### Run")
            _classic_sim_button = st.button(
                "SIM", type="primary", use_container_width=True, key="dk_classic_sim"
            )
            # One-click Classic workflow: SIM -> BUILD -> CONTEST SIM -> ROI.
            _classic_build_button = _classic_sim_button
            _classic_contest_button = _classic_sim_button
            classic_run_all = _classic_sim_button
'''
if old_buttons in text:
    text = text.replace(old_buttons, new_buttons, 1)
elif new_buttons not in text:
    raise SystemExit('Classic run-button block not found')

old_loop = '''            target_lineups = 5000
            # The old 500,000-attempt loop could look frozen after player simulation
            # completed. Unique Classic lineups are normally found much sooner; keep
            # the full 5,000-lineup target while bounding wasted duplicate/invalid tries.
            max_attempts = 100000
            build_progress = st.progress(0, text="Building DraftKings Classic lineups: 0 / 2,000")
            expected_exposure = max(1.0, target_lineups * len(roster_slots) / max(1, len(classic_names)))
            for attempt in range(max_attempts):
'''
new_loop = '''            target_lineups = 5000
            no_stack_rules = (not dk_classic_stack_rules) or ("No stack rule" in dk_classic_stack_rules)
            # No-stack builds should be the fast path. Stack builds can need more
            # attempts because they must satisfy the selected QB correlation rule.
            max_attempts = 30000 if no_stack_rules else 100000
            build_progress = st.progress(0, text=f"Building DraftKings Classic lineups: 0 / {target_lineups:,}")
            expected_exposure = max(1.0, target_lineups * len(roster_slots) / max(1, len(classic_names)))
            for attempt in range(max_attempts):
'''
if old_loop in text:
    text = text.replace(old_loop, new_loop, 1)
elif new_loop not in text:
    raise SystemExit('Classic build-loop settings not found')

old_penalty = '''                    exposure_penalty = np.asarray([
                        (1.0 + classic_build_counts.get(str(classic_names[i]), 0) / expected_exposure) ** 1.5
                        for i in choices
                    ], dtype=float)
                    weights /= exposure_penalty
'''
new_penalty = '''                    if no_stack_rules:
                        # Avoid the expensive Python exposure loop for every roster slot
                        # when the user intentionally selected no stacking rules.
                        exposure_penalty = np.fromiter(
                            ((1.0 + classic_build_counts.get(str(classic_names[i]), 0) / expected_exposure) ** 1.5 for i in choices),
                            dtype=float,
                            count=len(choices),
                        )
                    else:
                        exposure_penalty = np.asarray([
                            (1.0 + classic_build_counts.get(str(classic_names[i]), 0) / expected_exposure) ** 1.5
                            for i in choices
                        ], dtype=float)
                    weights /= exposure_penalty
'''
if old_penalty in text:
    text = text.replace(old_penalty, new_penalty, 1)
elif new_penalty not in text:
    raise SystemExit('Classic exposure block not found')

old_stack_check = '''                if not full_roster_stack_matches(chosen, classic_pool, dk_classic_stack_rules):
                    continue
'''
new_stack_check = '''                if not no_stack_rules and not full_roster_stack_matches(chosen, classic_pool, dk_classic_stack_rules):
                    continue
'''
if old_stack_check in text:
    text = text.replace(old_stack_check, new_stack_check, 1)
elif new_stack_check not in text:
    raise SystemExit('Classic stack validation not found')

path.write_text(text, encoding='utf-8')
print('Classic one-click SIM retained; no-stack build path sped up.')
