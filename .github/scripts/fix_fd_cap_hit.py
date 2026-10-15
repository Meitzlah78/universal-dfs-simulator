from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''            st.session_state["fd_player_sim_" + _fd_mode_key] = player_sim
            st.session_state["fd_simulation_df_" + _fd_mode_key] = simulated_scores.copy()
            st.session_state["fd_simulation_ready_" + _fd_mode_key] = True
'''
new = '''            st.session_state["fd_player_sim_" + _fd_mode_key] = player_sim
            st.session_state["fd_simulation_df_" + _fd_mode_key] = simulated_scores.copy()
            # Cap Hit % = share of simulated game outcomes in which the player
            # finishes tied for the highest raw FanDuel score on the slate.
            # Split tied top outcomes evenly so the percentages remain meaningful.
            _fd_scores = simulated_scores.apply(pd.to_numeric, errors="coerce").fillna(0.0)
            _fd_row_max = _fd_scores.max(axis=1)
            _fd_top_mask = _fd_scores.eq(_fd_row_max, axis=0)
            _fd_tie_count = _fd_top_mask.sum(axis=1).clip(lower=1)
            _fd_cap_hits = {
                str(_fd_name): float(100.0 * (_fd_top_mask[_fd_name] / _fd_tie_count).mean())
                for _fd_name in _fd_scores.columns
            }
            st.session_state["fd_simulation_cap_hit_pct_" + _fd_mode_key] = _fd_cap_hits
            st.session_state["fd_simulation_ready_" + _fd_mode_key] = True
'''
if old in s:
    s = s.replace(old, new, 1)
elif 'fd_simulation_cap_hit_pct_' not in s:
    raise SystemExit("FanDuel SIM state block not found")

old_display = '''    _fd_cap_hits = st.session_state.get("simulation_cap_hit_pct", {})
    fd_player_display["Cap Hit %"] = fd_player_display["Name"].astype(str).map(
        lambda name: pd.to_numeric(_fd_cap_hits.get(str(name)), errors="coerce")
    )
'''
new_display = '''    _fd_cap_hit_key = "fd_simulation_cap_hit_pct_" + lineup_mode.replace(" ", "_").lower()
    _fd_cap_hits = st.session_state.get(_fd_cap_hit_key, {})
    fd_player_display["Cap Hit %"] = fd_player_display["Name"].astype(str).map(
        lambda name: pd.to_numeric(_fd_cap_hits.get(str(name)), errors="coerce")
    )
'''
if old_display in s:
    s = s.replace(old_display, new_display, 1)
elif '_fd_cap_hit_key = "fd_simulation_cap_hit_pct_"' not in s:
    raise SystemExit("FanDuel Cap Hit display block not found")

p.write_text(s)
print("FanDuel Cap Hit % now comes from this mode's PBP simulations")
