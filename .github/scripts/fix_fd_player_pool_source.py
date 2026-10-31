from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''    if "simulation_df" in st.session_state:
        simulation_df = st.session_state["simulation_df"]

        # IMPORTANT: simulation_df can be retained in Streamlit session state while
'''
new = '''    # Use the active format's saved FanDuel PBP outcomes. The generic simulation_df
    # belongs to the DraftKings/shared path and can be stale or absent on FanDuel.
    _active_simulation_df = None
    if platform == "FanDuel":
        _fd_pool_sim_key = "fd_simulation_df_" + lineup_mode.replace(" ", "_").lower()
        _fd_saved_sim = st.session_state.get(_fd_pool_sim_key)
        if isinstance(_fd_saved_sim, pd.DataFrame) and not _fd_saved_sim.empty:
            _active_simulation_df = _fd_saved_sim
    elif isinstance(st.session_state.get("simulation_df"), pd.DataFrame):
        _active_simulation_df = st.session_state.get("simulation_df")

    if isinstance(_active_simulation_df, pd.DataFrame):
        simulation_df = _active_simulation_df

        # IMPORTANT: simulation_df can be retained in Streamlit session state while
'''
if old not in s:
    raise SystemExit("Player Pool simulation source block not found")
s = s.replace(old, new, 1)

old_snapshot = '''    if isinstance(st.session_state.get("simulation_df"), pd.DataFrame) and not st.session_state["simulation_df"].empty:
        save_automatic_pregame_snapshot(
'''
new_snapshot = '''    if isinstance(_active_simulation_df, pd.DataFrame) and not _active_simulation_df.empty:
        save_automatic_pregame_snapshot(
'''
if old_snapshot not in s:
    raise SystemExit("Player Pool snapshot source block not found")
s = s.replace(old_snapshot, new_snapshot, 1)

# The lineup builder below the Player Pool must use the same active format source.
old_builder = '''    if "simulation_df" in st.session_state:
        simulation_df = st.session_state["simulation_df"]

        for player in players_df["Name"]:
'''
new_builder = '''    if isinstance(_active_simulation_df, pd.DataFrame) and not _active_simulation_df.empty:
        simulation_df = _active_simulation_df

        for player in players_df["Name"]:
'''
if old_builder not in s:
    raise SystemExit("Builder simulation source block not found")
s = s.replace(old_builder, new_builder, 1)

p.write_text(s)
print("FanDuel Player Pool and builder now read the active mode-specific PBP simulation dataframe")
