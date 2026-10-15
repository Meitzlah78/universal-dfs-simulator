from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''                if fd_run_all_clicked:
                    fd_workflow_status.info("Step 4 of 4: Scoring your lineups against the contest field...")
                user_lineups = st.session_state.get(fd_build_key)
'''
new = '''                if fd_run_all_clicked:
                    fd_workflow_status.info("Step 4 of 4: Scoring your lineups against the contest field...")
                fd_step4_status = st.empty()
                fd_step4_status.info("Step 4 of 4: Scoring your lineups against the contest field...")
                fd_step4_progress = st.progress(0, text="Step 4 of 4: Preparing FanDuel contest comparison...")
                user_lineups = st.session_state.get(fd_build_key)
'''
if old not in s:
    raise SystemExit("FanDuel Step 4 start block not found")
s = s.replace(old, new, 1)

old2 = '''                    st.session_state["fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()] = compared
                    st.write("### FanDuel Lineups vs. Simulated Contest Field")
'''
new2 = '''                    st.session_state["fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()] = compared
                    fd_step4_progress.progress(1.0, text="Step 4 of 4 complete: FanDuel contest comparison finished.")
                    fd_step4_status.success("Step 4 of 4 complete: contest comparison finished.")
                    st.write("### FanDuel Lineups vs. Simulated Contest Field")
'''
if old2 not in s:
    raise SystemExit("FanDuel Step 4 completion block not found")
s = s.replace(old2, new2, 1)

old3 = '''                if user_lineups is None or user_lineups.empty:
                    st.warning("SIM is running the lineup build and contest comparison together.")
'''
new3 = '''                if user_lineups is None or user_lineups.empty:
                    fd_step4_status.error("Step 4 could not run because the current SIM did not produce user lineups.")
                    fd_step4_progress.empty()
                    st.warning("SIM is running the lineup build and contest comparison together.")
'''
if old3 not in s:
    raise SystemExit("FanDuel missing-lineups Step 4 block not found")
s = s.replace(old3, new3, 1)

old4 = '''        if fd_run_all_clicked:
            fd_workflow_status.success("FanDuel SIM complete: player simulations, lineup build, opponent field, and contest comparison finished.")
'''
new4 = '''        if fd_run_all_clicked:
            _fd_step4_key = "fd_contest_comparison_" + lineup_mode.replace(" ", "_").lower()
            _fd_step4_result = st.session_state.get(_fd_step4_key)
            if isinstance(_fd_step4_result, pd.DataFrame) and not _fd_step4_result.empty:
                fd_workflow_status.success("FanDuel SIM complete: all 4 steps finished.")
            else:
                fd_workflow_status.error("FanDuel SIM stopped before Step 4 produced a contest comparison.")
'''
if old4 not in s:
    raise SystemExit("FanDuel workflow completion block not found")
s = s.replace(old4, new4, 1)

p.write_text(s)
print("FanDuel Step 4 is explicit, visible, and required before SIM reports complete")
