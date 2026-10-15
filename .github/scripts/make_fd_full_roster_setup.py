from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# The FanDuel workflow/results are still nested inside the narrow Run column.
# Match DK layout: keep only the SIM button in the small third column and render
# all workflow status, field results, contest summary, sanity check and portfolio
# at full page width.
needle = '''    with build_cols[2]:
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
replacement = '''    with build_cols[2]:
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
if needle not in text:
    raise SystemExit("FanDuel narrow Run-column block not found")
text = text.replace(needle, replacement, 1)

# The remainder of the FanDuel branch was one indentation level too deep because
# it lived inside build_cols[2]. Dedent it through the start of the DK branch.
start = text.index('    if fd_run_all_clicked:\n', text.index(replacement))
end = text.find('\nif platform == "DraftKings":', start)
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

# Rename the FanDuel ROI area to the same clear Contest Summary wording used for
# the overall contest information. Keep the existing metrics and payout logic.
text = text.replace(
    'st.write("### FanDuel Contest Sim + ROI")',
    'st.write("### FanDuel Contest Summary")',
    1,
)

path.write_text(text, encoding="utf-8")
