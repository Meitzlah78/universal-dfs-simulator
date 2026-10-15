from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()
marker = 'st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True'
pos = s.find(marker)
if pos < 0:
    raise SystemExit("FanDuel completed-workflow marker not found")
window_end = min(len(s), pos + 700)
window = s[pos:window_end]
if "st.rerun()" in window:
    window = window.replace(
        "st.rerun()",
        'fd_workflow_status.success("FanDuel SIM complete: contest results and ROI are shown below.")',
        1,
    )
    s = s[:pos] + window + s[window_end:]
    p.write_text(s)
    print("Removed FanDuel post-SIM rerun so contest results and ROI remain visible")
else:
    print("FanDuel post-SIM rerun already removed")