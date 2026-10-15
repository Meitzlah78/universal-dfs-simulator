from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# The FanDuel controls were all being rendered inside build_cols[1], which
# squeezed the rest of the page into the small right-side column. Match the
# DK Classic layout by closing that column after the build-style controls.
needle = '''        else:
            correlation_strength = 1.0
        st.session_state["active_game_correlation_strength"] = correlation_strength
    if lineup_mode == "Full Roster":
'''
replacement = '''        else:
            correlation_strength = 1.0
        st.session_state["active_game_correlation_strength"] = correlation_strength

    # Everything below this point renders at normal page width, matching DK Classic.
    if lineup_mode == "Full Roster":
'''
if needle not in text:
    raise SystemExit("FanDuel display layout boundary not found")
text = text.replace(needle, replacement, 1)

# Move Run into the third build column exactly like DK Classic, then leave that
# context before workflow status/results so all displays use full page width.
needle2 = '''    with build_cols[2]:
        st.write("### Run")
        fd_sim_button = st.button(
            "SIM",
            type="primary",
            use_container_width=True,
            key="fd_sim_" + lineup_mode.replace(" ", "_").lower(),
            help="Runs player simulations, builds your lineups, builds the opponent field, and runs the contest comparison."
        )
        fd_run_all_clicked = fd_sim_button
        fd_sim_clicked = fd_sim_button
        fd_build_clicked = fd_sim_button
        fd_contest_clicked = fd_sim_button
        fd_workflow_status = None
        if fd_run_all_clicked:
'''
replacement2 = '''    with build_cols[2]:
        st.write("### Run")
        fd_sim_button = st.button(
            "SIM",
            type="primary",
            use_container_width=True,
            key="fd_sim_" + lineup_mode.replace(" ", "_").lower(),
            help="Runs player simulations, builds your lineups, builds the opponent field, and runs the contest comparison."
        )
    fd_run_all_clicked = fd_sim_button
    fd_sim_clicked = fd_sim_button
    fd_build_clicked = fd_sim_button
    fd_contest_clicked = fd_sim_button
    fd_workflow_status = None
    if fd_run_all_clicked:
'''
if needle2 not in text:
    raise SystemExit("FanDuel Run/display block not found")
text = text.replace(needle2, replacement2, 1)

# The existing workflow body was indented under the old build_cols[2] context.
# Dedent that body until the FanDuel branch exits, so status, progress bars,
# results, sanity checks, portfolio and exports render full-width.
start_marker = '    if fd_run_all_clicked:\n'
start = text.index(start_marker, text.index(replacement2))
end_marker = '\nif platform == "DraftKings":'
end = text.find(end_marker, start)
if end == -1:
    raise SystemExit("End of FanDuel branch not found")
block = text[start:end]
lines = block.splitlines(True)
fixed = []
for i, line in enumerate(lines):
    if i == 0:
        fixed.append(line)
    elif line.startswith('        '):
        fixed.append(line[4:])
    else:
        fixed.append(line)
text = text[:start] + ''.join(fixed) + text[end:]

path.write_text(text, encoding="utf-8")
