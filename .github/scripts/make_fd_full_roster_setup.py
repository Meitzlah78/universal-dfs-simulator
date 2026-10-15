from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()
changes = 0

# The completed FanDuel workflow used to call st.rerun(), which immediately erased
# the just-rendered Contest Results and ROI sections from the screen. Keep the
# completed run on screen instead. The results are already saved in session state.
old_complete = '''        if fd_run_all_clicked:\n            _fd_step4_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()\n            _fd_step4_result = st.session_state.get(_fd_step4_key)\n            if isinstance(_fd_step4_result, pd.DataFrame) and not _fd_step4_result.empty:\n                st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True\n                st.rerun()\n            else:\n                fd_workflow_status.error("FanDuel SIM stopped before Step 4 produced a contest comparison.")\n'''
new_complete = '''        if fd_run_all_clicked:\n            _fd_step4_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()\n            _fd_step4_result = st.session_state.get(_fd_step4_key)\n            if isinstance(_fd_step4_result, pd.DataFrame) and not _fd_step4_result.empty:\n                st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True\n                fd_workflow_status.success("FanDuel SIM complete: contest results and ROI are shown below.")\n            else:\n                fd_workflow_status.error("FanDuel SIM stopped before Step 4 produced a contest comparison.")\n'''
if old_complete in s:
    s = s.replace(old_complete, new_complete, 1)
    changes += 1
elif new_complete not in s:
    raise SystemExit("FanDuel completion/rerun block not found")

p.write_text(s)
print(f"Applied {changes} FanDuel result-persistence fix")
