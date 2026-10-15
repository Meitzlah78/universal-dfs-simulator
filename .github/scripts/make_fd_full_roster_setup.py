from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''        if fd_run_all_clicked:
            _fd_step4_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()
            _fd_step4_result = st.session_state.get(_fd_step4_key)
            if isinstance(_fd_step4_result, pd.DataFrame) and not _fd_step4_result.empty:
                fd_workflow_status.success("FanDuel SIM complete: all 4 steps finished.")
            else:
                fd_workflow_status.error("FanDuel SIM stopped before Step 4 produced a contest comparison.")
'''
new = '''        if fd_run_all_clicked:
            _fd_step4_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()
            _fd_step4_result = st.session_state.get(_fd_step4_key)
            if isinstance(_fd_step4_result, pd.DataFrame) and not _fd_step4_result.empty:
                # The Player Pool and its download widgets were created earlier in
                # this Streamlit run, before Step 1 replaced the projection fallback
                # with real PBP outcomes. Rerun once now so the visible/exported
                # P10-P99 values are rebuilt from fd_player_sim_* session state.
                st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True
                st.rerun()
            else:
                fd_workflow_status.error("FanDuel SIM stopped before Step 4 produced a contest comparison.")
'''
if old not in s:
    raise SystemExit("FanDuel workflow completion block not found")
s = s.replace(old, new, 1)

p.write_text(s)
print("FanDuel completed SIM now reruns once so Player Pool exports use real PBP percentiles")
