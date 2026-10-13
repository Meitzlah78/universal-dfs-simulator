from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

# Add a clear shared layout marker/caption so all formats present the same workflow order.
anchor = 'st.subheader(selected_format)\n'
insert = '''st.subheader(selected_format)\nst.caption("Workflow: Slate Setup → Contest → Player Pool → Build Settings → SIM → BUILD → CONTEST SIM → Results / Export")\n'''
if anchor in text and 'Workflow: Slate Setup → Contest → Player Pool' not in text:
    text = text.replace(anchor, insert, 1)

# Move the existing FanDuel Player Pool block ahead of Build Settings so all formats
# put the same main work area in the same place. This keeps the existing columns,
# exposure, ownership, snapshot, and copy-to-ChatGPT behavior intact.
player_start = '        st.success(f"Loaded {len(fd_players)} FanDuel players after injury-status filtering.")\n'
player_end = '        fd_signature = (\n'
settings_anchor = '    st.caption("The 5,000-lineup build automatically spreads player exposure while still favoring stronger simulated scores.")\n'

if player_start in text and player_end in text and settings_anchor in text:
    start = text.index(player_start)
    end = text.index(player_end, start)
    block = text[start:end]
    # The block originally lived one indentation level deeper. De-indent it so it
    # can live at the same FanDuel-page level as Build Settings.
    moved_lines = []
    for line in block.splitlines(True):
        moved_lines.append(line[4:] if line.startswith('    ') else line)
    moved_block = ''.join(moved_lines)

    text = text[:start] + text[end:]
    insert_at = text.index(settings_anchor)
    heading = '    st.divider()\n    st.write("### Player Pool — Stats, Simulation, Exposure & Controls")\n'
    if heading.strip() not in moved_block:
        moved_block = heading + moved_block
    text = text[:insert_at] + moved_block + '\n' + text[insert_at:]

# Label FanDuel settings consistently and avoid a duplicate nested heading.
text = text.replace(
    '    st.caption("The 5,000-lineup build automatically spreads player exposure while still favoring stronger simulated scores.")\n    build_cols = st.columns([1, 1, 0.65])\n',
    '    st.write("### Build Settings")\n    st.caption("The 5,000-lineup build automatically spreads player exposure while still favoring stronger simulated scores.")\n    build_cols = st.columns([1, 1, 0.65])\n',
    1,
)
text = text.replace(
    '    with build_cols[0]:\n        st.write("### Build Settings")\n        fd_salary_range = st.slider(',
    '    with build_cols[0]:\n        fd_salary_range = st.slider(',
    1,
)

path.write_text(text, encoding='utf-8')
print('Standardized SIM layout with FanDuel Player Pool before Build Settings.')
