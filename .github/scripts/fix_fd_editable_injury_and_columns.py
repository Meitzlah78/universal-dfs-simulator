from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old_order = '''        _fd_classic_order = [
            "Name", "Team", "Opponent", "Position", "Salary", "Projection", "ProjectionSource",
            "Injury Status", "Sim Pts", "Sim P10", "Sim P25", "Sim P50", "Sim P75",
            "Sim P90", "Sim P95", "Sim P99", "Cap Hit %", "Field Own %", "Exposure %",
            "Lock", "Fade", "Min Exposure %", "Max Exposure %"
        ]'''
new_order = '''        _fd_classic_order = [
            "Fade", "Lock", "Name", "Team", "Opponent", "Position", "Salary", "Injury Status",
            "Projection", "Sim Pts", "Exposure %", "Field Own %", "Min Exposure %", "Max Exposure %",
            "ProjectionSource", "Sim P10", "Sim P25", "Sim P50", "Sim P75", "Sim P90", "Sim P95",
            "Sim P99", "Cap Hit %"
        ]'''
if old_order not in s:
    raise SystemExit("FanDuel Full Roster column-order block not found")
s = s.replace(old_order, new_order, 1)

old_table = '''    st.dataframe(
        fd_player_display,
        use_container_width=True,
        hide_index=True,
        column_config={"Name": st.column_config.TextColumn("Name", pinned=True)},
    )'''
new_table = '''    # Let the user override injury status directly in the FanDuel Player Pool.
    # Manual overrides win over automatic injury refreshes until the user changes them again.
    _fd_manual_injury_key = "fd_manual_injury_status_" + lineup_mode.replace(" ", "_").lower()
    _fd_manual_injuries = st.session_state.get(_fd_manual_injury_key, {})
    if not isinstance(_fd_manual_injuries, dict):
        _fd_manual_injuries = {}
    if "Injury Status" in fd_player_display.columns:
        fd_player_display["Injury Status"] = fd_player_display.apply(
            lambda row: _fd_manual_injuries.get(str(row.get("Name", "")), row.get("Injury Status", "Active")),
            axis=1,
        )
    _fd_edited_pool = st.data_editor(
        fd_player_display,
        use_container_width=True,
        hide_index=True,
        disabled=[c for c in fd_player_display.columns if c not in {"Fade", "Lock", "Injury Status", "Min Exposure %", "Max Exposure %"}],
        column_config={
            "Name": st.column_config.TextColumn("Name", pinned=True),
            "Injury Status": st.column_config.SelectboxColumn(
                "Injury Status", options=["Active", "Questionable", "Doubtful", "Out"], required=True
            ),
        },
        key="fd_player_pool_editor_" + lineup_mode.replace(" ", "_").lower(),
    )
    if isinstance(_fd_edited_pool, pd.DataFrame) and "Injury Status" in _fd_edited_pool.columns:
        _fd_new_manual = dict(zip(_fd_edited_pool["Name"].astype(str), _fd_edited_pool["Injury Status"].astype(str)))
        if _fd_new_manual != _fd_manual_injuries:
            st.session_state[_fd_manual_injury_key] = _fd_new_manual
            fd_players["Injury Status"] = fd_players["Name"].astype(str).map(_fd_new_manual).fillna(fd_players.get("Injury Status", "Active"))
            _fd_out_names = set(fd_players.loc[fd_players["Injury Status"].astype(str).str.casefold().eq("out"), "Name"].astype(str))
            if _fd_out_names:
                fd_players = fd_players[~fd_players["Name"].astype(str).isin(_fd_out_names)].copy()
            st.rerun()
    fd_player_display = _fd_edited_pool.copy() if isinstance(_fd_edited_pool, pd.DataFrame) else fd_player_display'''
if old_table not in s:
    raise SystemExit("FanDuel Player Pool dataframe block not found")
s = s.replace(old_table, new_table, 1)

p.write_text(s)
print("FanDuel Player Pool now has editable injury status and requested Full Roster column order")
# updater trigger 2026-10-15
