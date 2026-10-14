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

# Do not immediately rerun after the one-click Classic workflow.
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

# Show 20 Classic portfolio lineups by default.
text = text.replace('''                value=min(2500, max(1, len(classic_portfolio_source))),
                step=100 if len(classic_portfolio_source) >= 100 else 1,
                key="dk_classic_portfolio_count"''', '''                value=min(20, max(1, len(classic_portfolio_source))),
                step=1,
                key="dk_classic_portfolio_count"''', 1)

# Persist Classic Contest Sim output across normal Streamlit widget reruns.
anchor = '''        classic_results = st.session_state.get("classic_lineups")
'''
persist = '''        # Redisplay the last completed Classic Contest Sim after widget changes
        # such as changing the Portfolio count or ranking method.
        if not _classic_contest_button:
            _saved_classic_comparison = st.session_state.get("classic_contest_comparison_df")
            _saved_classic_entries = st.session_state.get("classic_contest_entries_df")
            _saved_classic_field = st.session_state.get("classic_contest_field_df")
            if isinstance(_saved_classic_comparison, pd.DataFrame) and not _saved_classic_comparison.empty:
                st.write("### Your Lineups vs. Contest Field")
                st.dataframe(_saved_classic_comparison, use_container_width=True, hide_index=True)
                if isinstance(_saved_classic_field, pd.DataFrame) and not _saved_classic_field.empty:
                    st.metric("Simulated opponent lineups", f"{len(_saved_classic_field):,}")
                if isinstance(_saved_classic_entries, pd.DataFrame) and not _saved_classic_entries.empty:
                    _saved_entry_fee = float(classic_contest["entry"])
                    _saved_total_fees = _saved_entry_fee * len(_saved_classic_entries)
                    _saved_expected_winnings = float(_saved_classic_entries["Expected Prize ($)"].sum())
                    _saved_expected_profit = _saved_expected_winnings - _saved_total_fees
                    _saved_expected_roi = (100.0 * _saved_expected_profit / _saved_total_fees) if _saved_total_fees > 0 else 0.0
                    st.write("### Classic Contest Sim + ROI")
                    st.caption(f"{classic_contest_name} · full field {classic_contest['field']:,} · {len(_saved_classic_entries)} of your entries")
                    _saved_roi_cols = st.columns(5)
                    _saved_roi_cols[0].metric("Entries", f"{len(_saved_classic_entries)}")
                    _saved_roi_cols[1].metric("Entry Fees", f"${_saved_total_fees:,.2f}")
                    _saved_roi_cols[2].metric("Expected Winnings", f"${_saved_expected_winnings:,.2f}")
                    _saved_roi_cols[3].metric("Expected Profit", f"${_saved_expected_profit:,.2f}")
                    _saved_roi_cols[4].metric("Expected ROI", f"{_saved_expected_roi:,.1f}%")
                if all(c in _saved_classic_comparison.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                    _saved_classic_sanity = pd.DataFrame([{
                        "Top 1%": round(100 * float(_saved_classic_comparison["Top1"].mean()), 2),
                        "Top 5%": round(100 * float(_saved_classic_comparison["Top5"].mean()), 2),
                        "Top 10%": round(100 * float(_saved_classic_comparison["Top10"].mean()), 2),
                        "Cash %": round(100 * float(_saved_classic_comparison["CashRate"].mean()), 2),
                    }])
                    st.write("### Field Sanity Check")
                    st.dataframe(_saved_classic_sanity, use_container_width=True, hide_index=True)

        classic_results = st.session_state.get("classic_lineups")
'''
if persist not in text:
    if anchor not in text:
        raise SystemExit('Classic results anchor not found')
    text = text.replace(anchor, persist, 1)

path.write_text(text, encoding='utf-8')
print('Classic ROI and Field Sanity now persist across Portfolio and ranking widget reruns.')
