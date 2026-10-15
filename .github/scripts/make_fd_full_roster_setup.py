from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
old_buttons = '''        _fd_run_cols = st.columns(3)
        with _fd_run_cols[0]:
            fd_sim_button = st.button("SIM", type="primary", use_container_width=True, key="fd_sim_" + lineup_mode.replace(" ", "_").lower())
        with _fd_run_cols[1]:
            fd_build_button = st.button("BUILD", use_container_width=True, key="fd_build_" + lineup_mode.replace(" ", "_").lower())
        with _fd_run_cols[2]:
            fd_contest_button = st.button("CONTEST SIM", use_container_width=True, key="fd_contest_" + lineup_mode.replace(" ", "_").lower())
        fd_run_all_clicked = fd_sim_button or fd_build_button or fd_contest_button
        fd_sim_clicked = fd_run_all_clicked
        fd_build_clicked = fd_run_all_clicked
        fd_contest_clicked = fd_run_all_clicked'''
new_buttons = '''        fd_sim_button = st.button(
            "SIM",
            type="primary",
            use_container_width=True,
            key="fd_sim_" + lineup_mode.replace(" ", "_").lower(),
            help="Runs player simulations, builds your lineups, builds the opponent field, and runs the contest comparison."
        )
        fd_run_all_clicked = fd_sim_button
        fd_sim_clicked = fd_sim_button
        fd_build_clicked = fd_sim_button
        fd_contest_clicked = fd_sim_button'''
if old_buttons in text:
    text = text.replace(old_buttons, new_buttons, 1)
elif new_buttons not in text:
    raise SystemExit("FanDuel three-button run block not found")

path.write_text(text, encoding="utf-8")
