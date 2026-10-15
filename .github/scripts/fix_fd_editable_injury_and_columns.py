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
if old_order in s:
    s = s.replace(old_order, new_order, 1)
elif new_order not in s:
    raise SystemExit("FanDuel Full Roster column-order block not found")

old_table = '''    st.dataframe(
        fd_player_display,
        use_container_width=True,
        hide_index=True,
        column_config={"Name": st.column_config.TextColumn("Name", pinned=True)},
    )'''
new_table = '''    # Let the user override injury status directly in the FanDuel Player Pool.
    _fd_manual_injury_key = "fd_manual_injury_status_" + lineup_mode.replace(" ", "_").lower()
    _fd_manual_injuries = st.session_state.get(_fd_manual_injury_key, {})
    if not isinstance(_fd_manual_injuries, dict):
        _fd_manual_injuries = {}
    if "Injury Status" in fd_player_display.columns:
        fd_player_display["Injury Status"] = fd_player_display.apply(
            lambda row: _fd_manual_injuries.get(str(row.get("Name", "")), row.get("Injury Status", "Active")), axis=1
        )
    _fd_edited_pool = st.data_editor(
        fd_player_display,
        use_container_width=True,
        hide_index=True,
        disabled=[c for c in fd_player_display.columns if c not in {"Fade", "Lock", "Injury Status", "Min Exposure %", "Max Exposure %"}],
        column_config={
            "Name": st.column_config.TextColumn("Name", pinned=True),
            "Injury Status": st.column_config.SelectboxColumn("Injury Status", options=["Active", "Questionable", "Doubtful", "Out"], required=True),
        },
        key="fd_player_pool_editor_" + lineup_mode.replace(" ", "_").lower(),
    )
    if isinstance(_fd_edited_pool, pd.DataFrame) and "Injury Status" in _fd_edited_pool.columns:
        _fd_auto_status = dict(zip(fd_player_display["Name"].astype(str), fd_player_display["Injury Status"].astype(str)))
        _fd_new_manual = dict(_fd_manual_injuries)
        for _fd_name, _fd_status in zip(_fd_edited_pool["Name"].astype(str), _fd_edited_pool["Injury Status"].astype(str)):
            if _fd_status != _fd_auto_status.get(_fd_name):
                _fd_new_manual[_fd_name] = _fd_status
        if _fd_new_manual != _fd_manual_injuries:
            st.session_state[_fd_manual_injury_key] = _fd_new_manual
            st.rerun()
        fd_players["Injury Status"] = fd_players.apply(
            lambda row: _fd_new_manual.get(str(row.get("Name", "")), row.get("Injury Status", "Active")), axis=1
        )
        fd_players = fd_players[~fd_players["Injury Status"].astype(str).str.casefold().eq("out")].copy()
    fd_player_display = _fd_edited_pool.copy() if isinstance(_fd_edited_pool, pd.DataFrame) else fd_player_display'''
if old_table in s:
    s = s.replace(old_table, new_table, 1)
elif '_fd_manual_injury_key = "fd_manual_injury_status_"' not in s:
    raise SystemExit("FanDuel Player Pool dataframe block not found")

p.write_text(s)
print("FanDuel Player Pool editable injury status and requested column order are installed")
