from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# Keep the settings compact, but move the SIM workflow/progress/results out of
# the narrow right-hand column so status bars and result windows use full width.
fd_start = text.find('if platform == "FanDuel":')
if fd_start == -1:
    raise SystemExit("FanDuel branch not found")

old_cols = '    build_cols = st.columns([0.75, 0.75, 2.5])'
if old_cols in text[fd_start:]:
    text = text[:fd_start] + text[fd_start:].replace(old_cols, '    build_cols = st.columns([1, 1])', 1)

run_start = text.find('    with build_cols[2]:\n', fd_start)
if run_start == -1:
    raise SystemExit("FanDuel Run column not found")

# The FanDuel branch ends at the top-level else after its st.stop().
branch_end = text.find('\n        st.stop()\n\nelse:\n', run_start)
if branch_end == -1:
    raise SystemExit("End of FanDuel branch not found")
branch_end += len('\n        st.stop()\n')

prefix = text[:run_start]
block = text[run_start + len('    with build_cols[2]:\n'):branch_end]
suffix = text[branch_end:]

# Everything formerly nested under the Run column loses one indentation level.
lines = block.splitlines(True)
dedented = []
for line in lines:
    if line.startswith('        '):
        dedented.append(line[4:])
    else:
        dedented.append(line)
block = ''.join(dedented)

# Give the SIM button a centered, readable row while all progress/results below
# it remain full-width.
run_header = '''    st.write("### Run")\n    _fd_run_left, _fd_run_center, _fd_run_right = st.columns([1, 2, 1])\n    with _fd_run_center:\n'''
# The old block starts with st.write("### Run") and the button definition.
old_header = '    st.write("### Run")\n    fd_sim_button = st.button(\n'
if old_header not in block:
    raise SystemExit("FanDuel Run header not found")
block = block.replace(old_header, run_header + '        fd_sim_button = st.button(\n', 1)
# Indent only the remaining button arguments through its closing line.
button_start = block.find('        fd_sim_button = st.button(\n')
button_end = block.find('    )\n', button_start)
if button_end == -1:
    raise SystemExit("FanDuel SIM button end not found")
button_end += len('    )\n')
button_chunk = block[button_start:button_end]
button_lines = button_chunk.splitlines(True)
fixed_button = [button_lines[0]]
for line in button_lines[1:]:
    fixed_button.append('    ' + line)
block = block[:button_start] + ''.join(fixed_button) + block[button_end:]

text = prefix + block + suffix
path.write_text(text, encoding="utf-8")
