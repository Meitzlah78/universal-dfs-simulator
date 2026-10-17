from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''                st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True
                fd_workflow_status.success("FanDuel SIM complete: contest results and ROI are shown below.")
'''
new = '''                st.session_state["fd_last_completed_workflow_" + lineup_mode.replace(" ", "_").lower()] = True
                fd_workflow_status.success("FanDuel SIM complete. Refreshing the Player Pool with the new PBP results...")
                # The Player Pool and export were rendered before this SIM click.
                # Rerun once so they are rebuilt from the fd_player_sim_* values
                # saved above instead of the pre-SIM projection placeholders.
                st.rerun()
'''

if old not in s:
    if new in s:
        print("FanDuel Player Pool refresh patch already applied")
    else:
        raise SystemExit("FanDuel completed-workflow refresh marker not found")
else:
    s = s.replace(old, new, 1)
    p.write_text(s)
    print("Applied FanDuel Player Pool/export refresh after completed SIM")
