from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

# Add a clear shared layout marker/caption so all formats present the same workflow order.
anchor = 'st.subheader(selected_format)\n'
insert = '''st.subheader(selected_format)\nst.caption("Workflow: Slate Setup → Contest → Player Pool → Build Settings → SIM → BUILD → CONTEST SIM → Results / Export")\n'''
if anchor in text and 'Workflow: Slate Setup → Contest → Player Pool' not in text:
    text = text.replace(anchor, insert, 1)

# Rename FanDuel player pool area with the same heading used by DraftKings.
fd_anchor = '        fd_player_display = fd_players.drop(columns=["FD_ID"], errors="ignore").copy()\n'
fd_insert = '''        st.divider()\n        st.write("### Player Pool — Stats, Simulation, Exposure & Controls")\n        fd_player_display = fd_players.drop(columns=["FD_ID"], errors="ignore").copy()\n'''
if fd_anchor in text and '### Player Pool — Stats, Simulation, Exposure & Controls' in text:
    # Only replace the FanDuel occurrence; DK already has this heading elsewhere.
    text = text.replace(fd_anchor, fd_insert, 1)

# Label FanDuel settings consistently; do not duplicate if already immediately present.
text = text.replace(
    '    st.caption("The 5,000-lineup build automatically spreads player exposure while still favoring stronger simulated scores.")\n    build_cols = st.columns([1, 1, 0.65])\n',
    '    st.caption("The 5,000-lineup build automatically spreads player exposure while still favoring stronger simulated scores.")\n    st.write("### Build Settings")\n    build_cols = st.columns([1, 1, 0.65])\n',
    1,
)
# Remove nested duplicate heading in first FanDuel build column if present.
text = text.replace('    with build_cols[0]:\n        st.write("### Build Settings")\n        fd_salary_range = st.slider(', '    with build_cols[0]:\n        fd_salary_range = st.slider(', 1)

path.write_text(text, encoding='utf-8')
print('Standardized shared layout labels and Player Pool-first workflow markers.')
