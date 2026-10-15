from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

# FanDuel-only correlation layer. It is deliberately inserted immediately after
# FanDuel weather adjustment so DraftKings code and calibration remain untouched.
needle = '''# Automatic NWS weather for FanDuel Full Roster and Single Game only.\nfd_players = apply_fd_nws_weather(fd_players)\n'''
insert = '''# Automatic NWS weather for FanDuel Full Roster and Single Game only.\nfd_players = apply_fd_nws_weather(fd_players)\n\n# FanDuel correlated game outcomes. Shared game/team shocks make player results\n# move together instead of sampling every player independently. The marginal\n# player distributions stay intact; this only changes their joint outcomes.\ndef apply_fd_correlated_simulations(sim_df, player_pool, seed=20261015):\n    if not isinstance(sim_df, pd.DataFrame) or sim_df.empty:\n        return sim_df\n    if not isinstance(player_pool, pd.DataFrame) or player_pool.empty:\n        return sim_df\n    needed = {"Name", "Team", "Opponent", "Position"}\n    if not needed.issubset(player_pool.columns):\n        return sim_df\n\n    meta = player_pool.drop_duplicates("Name", keep="first").set_index("Name")\n    cols = [c for c in sim_df.columns if c in meta.index]\n    if len(cols) < 2:\n        return sim_df\n\n    out = sim_df.copy()\n    n = len(out)\n    rng = np.random.default_rng(seed)\n\n    # One shock per game and per team. Coefficients are conservative so the\n    # existing FanDuel projections/percentiles remain the main signal.\n    game_z = {}\n    team_z = {}\n    for name in cols:\n        row = meta.loc[name]\n        team = str(row.get("Team", "")).strip().upper()\n        opp = str(row.get("Opponent", "")).strip().upper()\n        if not team:\n            continue\n        game_key = tuple(sorted([team, opp])) if opp else (team,)\n        if game_key not in game_z:\n            game_z[game_key] = rng.standard_normal(n)\n        if team not in team_z:\n            team_z[team] = rng.standard_normal(n)\n\n    for name in cols:\n        row = meta.loc[name]\n        team = str(row.get("Team", "")).strip().upper()\n        opp = str(row.get("Opponent", "")).strip().upper()\n        pos = str(row.get("Position", "")).strip().upper().replace("DST", "D")\n        if not team:\n            continue\n        game_key = tuple(sorted([team, opp])) if opp else (team,)\n        gz = game_z.get(game_key)\n        tz = team_z.get(team)\n        oz = team_z.get(opp) if opp else None\n        if gz is None or tz is None:\n            continue\n\n        # Positive same-game correlation plus position/game-script effects.\n        if pos == "QB":\n            shock = 0.16 * gz + 0.22 * tz\n        elif pos in {"WR", "TE"}:\n            shock = 0.18 * gz + 0.24 * tz\n        elif pos == "RB":\n            shock = 0.12 * gz + 0.18 * tz - (0.06 * oz if oz is not None else 0.0)\n        elif pos in {"D", "DEF"}:\n            shock = -0.10 * gz + 0.16 * tz - (0.18 * oz if oz is not None else 0.0)\n        elif pos == "K":\n            shock = 0.10 * gz + 0.12 * tz\n        else:\n            shock = 0.12 * gz + 0.15 * tz\n\n        vals = pd.to_numeric(out[name], errors="coerce").fillna(0.0).to_numpy(dtype=float)\n        sd = float(np.std(vals))\n        if sd <= 0:\n            continue\n        # Add correlation, then restore the original player's mean and standard\n        # deviation so correlation does not inflate projections or volatility.\n        old_mean = float(np.mean(vals))\n        old_sd = max(sd, 1e-9)\n        vals2 = vals + shock * old_sd\n        new_sd = float(np.std(vals2))\n        if new_sd > 0:\n            vals2 = old_mean + (vals2 - float(np.mean(vals2))) * (old_sd / new_sd)\n        out[name] = np.maximum(vals2, 0.0)\n\n    return out\n'''

if "def apply_fd_correlated_simulations(" not in s:
    if needle not in s:
        raise SystemExit("FanDuel weather insertion point not found")
    s = s.replace(needle, insert, 1)

# Apply the correlation layer to FanDuel's simulation dataframe after it is built.
# Match several known assignment forms without touching DraftKings simulation_df.
patterns = [
    'st.session_state["fd_simulation_df"] = fd_sim_df\n',
    "st.session_state['fd_simulation_df'] = fd_sim_df\n",
]
replacement = '''fd_sim_df = apply_fd_correlated_simulations(fd_sim_df, fd_players)\nst.session_state["fd_simulation_df"] = fd_sim_df\n'''
if "fd_sim_df = apply_fd_correlated_simulations(fd_sim_df, fd_players)" not in s:
    for pat in patterns:
        if pat in s:
            s = s.replace(pat, replacement, 1)
            break
    else:
        # Current app may store the FanDuel frame under the generic simulation key
        # inside the FanDuel block. Anchor on the FanDuel SIM completion marker.
        marker = 'st.session_state["simulation_df"] = fd_sim_df\n'
        if marker in s:
            s = s.replace(marker, 'fd_sim_df = apply_fd_correlated_simulations(fd_sim_df, fd_players)\n' + marker, 1)
        else:
            raise SystemExit("FanDuel simulation dataframe assignment not found")

p.write_text(s)
print("Applied FanDuel-only correlated simulation outcomes")
