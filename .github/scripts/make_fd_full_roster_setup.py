from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

# 1) FanDuel templates already contain an explicit Opponent column. Prefer it.
old = '''        fd_players["Team"] = fd_raw[fd_team_col].astype(str).str.strip().str.upper()
        show_detected_slate_games(fd_raw)
        fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
        fd_players["Opponent"] = fd_players["Team"].map(fd_opponents).fillna("—")
        fd_players["Position"] = fd_raw[fd_pos_col].astype(str).str.strip().str.upper()
'''
new = '''        fd_players["Team"] = fd_raw[fd_team_col].astype(str).str.strip().str.upper()
        show_detected_slate_games(fd_raw)
        fd_opponent_col = fd_find_column(fd_raw, ["Opponent", "Opp"])
        if fd_opponent_col is not None:
            fd_players["Opponent"] = (
                fd_raw[fd_opponent_col].astype(str).str.strip().str.upper()
                .replace({"": np.nan, "NAN": np.nan, "NONE": np.nan, "-": np.nan, "—": np.nan})
            )
            # Only use the Game-column fallback for rows where FanDuel did not supply Opponent.
            fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
            fd_players["Opponent"] = fd_players["Opponent"].fillna(fd_players["Team"].map(fd_opponents)).fillna("—")
        else:
            fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
            fd_players["Opponent"] = fd_players["Team"].map(fd_opponents).fillna("—")
        fd_players["Position"] = fd_raw[fd_pos_col].astype(str).str.strip().str.upper()
'''
if old not in s:
    raise SystemExit("FanDuel opponent parsing block not found")
s = s.replace(old, new, 1)

# 2) The Player Pool is rendered before SIM. After Step 1, replace the in-memory
# display values with the actual play-by-play percentiles so downloads/snapshots
# from the completed run cannot retain the projection-multiplier placeholders.
needle = '''            st.session_state["fd_player_sim_" + lineup_mode.replace(" ", "_").lower()] = player_sim
            st.session_state["fd_simulation_ready_" + lineup_mode.replace(" ", "_").lower()] = True
'''
replacement = '''            st.session_state["fd_player_sim_" + lineup_mode.replace(" ", "_").lower()] = player_sim
            st.session_state["fd_simulation_ready_" + lineup_mode.replace(" ", "_").lower()] = True
            # Keep the already-created Player Pool dataframe wired to THIS run's
            # play-by-play output. On the next normal rerun the same values are
            # restored from session state before the table is drawn.
            if "fd_player_display" in locals() and isinstance(fd_player_display, pd.DataFrame):
                for _sim_key, _sim_label in [
                    ("Mean", "Sim Pts"), ("P10", "Sim P10"), ("P25", "Sim P25"),
                    ("P50", "Sim P50"), ("P75", "Sim P75"), ("P90", "Sim P90"),
                    ("P95", "Sim P95"), ("P99", "Sim P99"),
                ]:
                    fd_player_display[_sim_label] = fd_player_display["Name"].astype(str).map(
                        lambda _name, _key=_sim_key: pd.to_numeric(player_sim.get(str(_name), {}).get(_key), errors="coerce")
                    )
'''
if needle not in s:
    raise SystemExit("FanDuel simulation session-state block not found")
s = s.replace(needle, replacement, 1)

# 3) The old post-hoc correlation helper must not be used on top of play-by-play.
# Remove any call if an older patch left one behind; event correlation is already inherent.
s = s.replace('simulated_scores = apply_fd_correlated_simulations(simulated_scores, fd_players, correlation_strength)\n', '')

p.write_text(s)
print("FanDuel opponent parsing and play-by-play Player Pool wiring fixed")
