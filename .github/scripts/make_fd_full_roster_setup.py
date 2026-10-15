from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Match the useful DK Classic player-pool information while retaining FD rules.
needle = '''    fd_player_display = fd_players.drop(columns=["FD_ID"], errors="ignore").copy()
    # Show exposure from the active FanDuel slate only.
'''
replacement = '''    fd_player_display = fd_players.drop(columns=["FD_ID"], errors="ignore").copy()
    # FanDuel Full Roster uses the same useful player-pool information as DK Classic.
    # Simulation columns are restored immediately from the saved/current simulation.
    for sim_key, sim_label in [
        ("Mean", "Sim Pts"), ("P10", "Sim P10"), ("P25", "Sim P25"),
        ("P50", "Sim P50"), ("P75", "Sim P75"), ("P90", "Sim P90"),
        ("P95", "Sim P95"), ("P99", "Sim P99"),
    ]:
        fd_player_display[sim_label] = fd_player_display["Name"].astype(str).map(
            lambda name, key=sim_key: pd.to_numeric(player_sim.get(str(name), {}).get(key), errors="coerce")
        )
    _fd_cap_hits = st.session_state.get("simulation_cap_hit_pct", {})
    fd_player_display["Cap Hit %"] = fd_player_display["Name"].astype(str).map(
        lambda name: pd.to_numeric(_fd_cap_hits.get(str(name)), errors="coerce")
    )
    if "Lock" not in fd_player_display.columns:
        fd_player_display["Lock"] = False
    if "Fade" not in fd_player_display.columns:
        fd_player_display["Fade"] = False
    if "Min Exposure %" not in fd_player_display.columns:
        fd_player_display["Min Exposure %"] = 0
    if "Max Exposure %" not in fd_player_display.columns:
        fd_player_display["Max Exposure %"] = 100
    # Full Roster has no captain/MVP exposure controls.
    if lineup_mode == "Full Roster":
        fd_player_display = fd_player_display.drop(
            columns=["Captain Min %", "Captain Max %", "MVP Min %", "MVP Max %"],
            errors="ignore"
        )
    # Show exposure from the active FanDuel slate only.
'''
if needle not in text:
    raise SystemExit("FanDuel player display block not found")
text = text.replace(needle, replacement, 1)

# Keep the most useful Classic-style columns together in Full Roster.
needle2 = '''    st.dataframe(
        fd_player_display,
        use_container_width=True,
        hide_index=True,
        column_config={"Name": st.column_config.TextColumn("Name", pinned=True)},
    )
'''
replacement2 = '''    if lineup_mode == "Full Roster":
        _fd_classic_order = [
            "Name", "Team", "Opponent", "Position", "Salary", "Projection", "ProjectionSource",
            "Injury Status", "Sim Pts", "Sim P10", "Sim P25", "Sim P50", "Sim P75",
            "Sim P90", "Sim P95", "Sim P99", "Cap Hit %", "Field Own %", "Exposure %",
            "Lock", "Fade", "Min Exposure %", "Max Exposure %"
        ]
        fd_player_display = fd_player_display[
            [c for c in _fd_classic_order if c in fd_player_display.columns]
            + [c for c in fd_player_display.columns if c not in _fd_classic_order]
        ]
    st.dataframe(
        fd_player_display,
        use_container_width=True,
        hide_index=True,
        column_config={"Name": st.column_config.TextColumn("Name", pinned=True)},
    )
'''
if needle2 not in text:
    raise SystemExit("FanDuel player dataframe block not found")
text = text.replace(needle2, replacement2, 1)

path.write_text(text, encoding="utf-8")
