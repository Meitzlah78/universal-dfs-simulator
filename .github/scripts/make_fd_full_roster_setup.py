from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

changes = 0

# FanDuel PBP: do not leave a player several points away from the intended
# simulation mean just because the raw event engine started outside an arbitrary
# 0.65-1.55 multiplier range. Scale the marginal mean to the current FanDuel
# target while preserving every shared play/script relationship.
old_calibration = '''        # Calibrate only the marginal mean; shared play outcomes/correlation stay intact.\n        if mean > 0 and target > 0:\n            vals *= float(np.clip(target / mean, 0.65, 1.55))\n        elif target > 0:\n'''
new_calibration = '''        # Calibrate only the marginal mean; shared play outcomes/correlation stay intact.\n        # Do not clip this ratio: clipping can leave a player's simulated mean\n        # several points away from the FanDuel target even after calibration.\n        if mean > 0 and target > 0:\n            vals *= float(target / mean)\n        elif target > 0:\n'''
if old_calibration in s:
    s = s.replace(old_calibration, new_calibration, 1)
    changes += 1
elif new_calibration not in s:
    raise SystemExit("FanDuel PBP calibration block not found")

# Save the actual FanDuel play-by-play score matrix under a FanDuel/mode-specific
# key. Never let FanDuel contest construction read DraftKings simulation_df.
old_save = '''            st.session_state["fd_player_sim_" + lineup_mode.replace(" ", "_").lower()] = player_sim\n            st.session_state["fd_simulation_ready_" + lineup_mode.replace(" ", "_").lower()] = True\n'''
new_save = '''            _fd_mode_key = lineup_mode.replace(" ", "_").lower()\n            st.session_state["fd_player_sim_" + _fd_mode_key] = player_sim\n            st.session_state["fd_simulation_df_" + _fd_mode_key] = simulated_scores.copy()\n            st.session_state["fd_simulation_ready_" + _fd_mode_key] = True\n'''
if old_save in s:
    s = s.replace(old_save, new_save, 1)
    changes += 1
elif new_save not in s:
    raise SystemExit("FanDuel simulation save block not found")

old_field = '''        fd_sim_df = st.session_state.get("simulation_df")\n        if isinstance(fd_sim_df, pd.DataFrame) and not fd_sim_df.empty:\n            fd_mean_scores = fd_sim_df.mean(axis=0).to_dict()\n        else:\n            fd_mean_scores = {}\n'''
new_field = '''        # Use this FanDuel mode's own PBP outcomes. The shared simulation_df key\n        # belongs to the DraftKings workflow and must never drive FanDuel opponents.\n        _fd_mode_key = lineup_mode.replace(" ", "_").lower()\n        fd_sim_df = st.session_state.get("fd_simulation_df_" + _fd_mode_key)\n        if isinstance(fd_sim_df, pd.DataFrame) and not fd_sim_df.empty:\n            fd_mean_scores = fd_sim_df.mean(axis=0).to_dict()\n        else:\n            fd_mean_scores = {\n                str(name): float(values.get("Mean", 0.0))\n                for name, values in player_sim.items()\n                if isinstance(values, dict)\n            }\n'''
if old_field in s:
    s = s.replace(old_field, new_field, 1)
    changes += 1
elif new_field not in s:
    raise SystemExit("FanDuel opponent simulation source block not found")

# The Player Pool/export is rendered before the SIM button handler. After all four
# steps finish, rerun once so it is rebuilt from the just-saved PBP results.
old_complete = '''        if fd_run_all_clicked:\n            _fd_step4_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()\n            _fd_step4_result = st.session_state.get(_fd_step4_key)\n            if isinstance(_fd_step4_result, pd.DataFrame) and not _fd_step4_result.empty:\n                fd_workflow_status.success("FanDuel SIM complete: all 4 steps finished.")\n            else:\n                fd_workflow_status.error("FanDuel SIM stopped before Step 4 produced a contest comparison.")\n'''
new_complete = '''        if fd_run_all_clicked:\n            _fd_step4_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()\n            _fd_step4_result = st.session_state.get(_fd_step4_key)\n            if isinstance(_fd_step4_result, pd.DataFrame) and not _fd_step4_result.empty:\n                st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True\n                st.rerun()\n            else:\n                fd_workflow_status.error("FanDuel SIM stopped before Step 4 produced a contest comparison.")\n'''
if old_complete in s:
    s = s.replace(old_complete, new_complete, 1)
    changes += 1
elif new_complete not in s:
    # The rerun fix may already be baked into dfs_app.py from the previous workflow.
    expected_rerun = 'st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True\n                st.rerun()'
    if expected_rerun not in s:
        raise SystemExit("FanDuel workflow completion block not found")

p.write_text(s)
print(f"Applied {changes} FanDuel-only PBP/state fixes")
