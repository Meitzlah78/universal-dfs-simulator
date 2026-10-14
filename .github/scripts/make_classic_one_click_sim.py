from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

# Keep prior Classic one-click/no-stack changes idempotent.
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

old_drop = '''    control_display = control_display.drop(
        columns=["ProjectionSource", "Injury Status", "Fade"], errors="ignore"
    )
'''
new_drop = '''    # Keep source, injury status, and Fade visible as shown in the requested Player Pool layout.
    control_display = control_display.drop(columns=["CaptainSalary"], errors="ignore")
'''
if old_drop in text:
    text = text.replace(old_drop, new_drop, 1)

old_order = '''    _preferred_player_pool_order = [
        "Name", "Position", "Team", "Opponent", "Salary", "CaptainSalary",
        "Projection", "Sim Pts",
        "Captain Exp %", "MVP Exp %", "Exposure %", "Flex Exp %",
        "Projected Own %", "Mine Own %",
        "Field CPT Own %", "Field MVP Own %", "Field FLEX Own %", "Field Own %",
        "Sim P10", "Sim P25", "Sim P50", "Sim P75", "Sim P90", "Sim P95", "Sim P99",
        "Cap Hit %",
        "Lock", "Min Exposure %", "Max Exposure %", "Captain Min %", "Captain Max %",
    ]
'''
new_order = '''    _preferred_player_pool_order = [
        "Name", "Position", "Team", "Opponent", "Salary",
        "Projection", "Sim Pts", "ProjectionSource", "Injury Status",
        "Captain Exp %", "MVP Exp %", "Exposure %", "Flex Exp %",
        "Projected Own %", "Mine Own %",
        "Field CPT Own %", "Field MVP Own %", "Field FLEX Own %", "Field Own %",
        "Sim P10", "Sim P25", "Sim P50", "Sim P75", "Sim P90", "Sim P95", "Sim P99",
        "Cap Hit %", "Lock", "Fade",
        "Min Exposure %", "Max Exposure %", "Captain Min %", "Captain Max %",
    ]
'''
if old_order in text:
    text = text.replace(old_order, new_order, 1)

# Do not immediately rerun after the one-click Classic workflow. The rerun was
# wiping the just-rendered Contest Sim ROI and Field Sanity Check from the screen.
old_rerun = '''        # Player Pool is rendered before the SIM button handler. After a fresh
        # simulation/build, rerun once so its Sim Pts and percentile columns read the
        # newly saved simulation_df instead of the previous run.
        if _classic_sim_button or _classic_build_button:
            st.rerun()
        st.stop()
'''
new_rerun = '''        # Keep the one-click Contest Sim results on screen. A later normal Streamlit
        # interaction will refresh the Player Pool from the saved simulation state.
        st.stop()
'''
if old_rerun in text:
    text = text.replace(old_rerun, new_rerun, 1)

# DraftKings Classic defaults requested by the user.
text = text.replace('''                value=(45000, 50000),
                step=100,
                format="$%d",
                key="dk_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),''', '''                value=(47000, 50000),
                step=100,
                format="$%d",
                key="dk_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),''', 1)
text = text.replace('''            default=["QB + 2 teammates + bring-back"],
            key="dk_classic_stack_rules",''', '''            default=["No stack rule"],
            key="dk_classic_stack_rules",''', 1)

# Show 20 Classic portfolio lineups by default, while still allowing the user to raise it.
text = text.replace('''                value=min(2500, max(1, len(classic_portfolio_source))),
                step=100 if len(classic_portfolio_source) >= 100 else 1,
                key="dk_classic_portfolio_count"''', '''                value=min(20, max(1, len(classic_portfolio_source))),
                step=1,
                key="dk_classic_portfolio_count"''', 1)

path.write_text(text, encoding='utf-8')
print('Classic defaults updated: No stack, $47K minimum salary, 20 portfolio lineups.')
