from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

# FanDuel-only correlation helper. DraftKings is intentionally untouched.
helper_anchor = "def apply_fd_nws_weather(fd_players):\n"
helper = '''def apply_fd_correlated_simulations(sim_df, player_pool, seed=20261015):\n    """Add conservative game/team correlation to FanDuel outcomes only."""\n    if not isinstance(sim_df, pd.DataFrame) or sim_df.empty or not isinstance(player_pool, pd.DataFrame) or player_pool.empty:\n        return sim_df\n    needed = {"Name", "Team", "Opponent", "Position"}\n    if not needed.issubset(player_pool.columns):\n        return sim_df\n    meta = player_pool.drop_duplicates("Name", keep="first").set_index("Name")\n    cols = [c for c in sim_df.columns if c in meta.index]\n    if len(cols) < 2:\n        return sim_df\n    out = sim_df.copy()\n    n = len(out)\n    rng = np.random.default_rng(seed)\n    game_z, team_z = {}, {}\n    for name in cols:\n        row = meta.loc[name]\n        team = str(row.get("Team", "")).strip().upper()\n        opp = str(row.get("Opponent", "")).strip().upper()\n        if not team:\n            continue\n        g = tuple(sorted([team, opp])) if opp else (team,)\n        game_z.setdefault(g, rng.standard_normal(n))\n        team_z.setdefault(team, rng.standard_normal(n))\n    for name in cols:\n        row = meta.loc[name]\n        team = str(row.get("Team", "")).strip().upper()\n        opp = str(row.get("Opponent", "")).strip().upper()\n        pos = str(row.get("Position", "")).strip().upper().replace("DST", "D")\n        if not team:\n            continue\n        g = tuple(sorted([team, opp])) if opp else (team,)\n        gz, tz, oz = game_z.get(g), team_z.get(team), team_z.get(opp) if opp else None\n        if gz is None or tz is None:\n            continue\n        if pos == "QB": shock = 0.16 * gz + 0.22 * tz\n        elif pos in {"WR", "TE"}: shock = 0.18 * gz + 0.24 * tz\n        elif pos == "RB": shock = 0.12 * gz + 0.18 * tz - (0.06 * oz if oz is not None else 0.0)\n        elif pos in {"D", "DEF"}: shock = -0.10 * gz + 0.16 * tz - (0.18 * oz if oz is not None else 0.0)\n        elif pos == "K": shock = 0.10 * gz + 0.12 * tz\n        else: shock = 0.12 * gz + 0.15 * tz\n        vals = pd.to_numeric(out[name], errors="coerce").fillna(0.0).to_numpy(dtype=float)\n        old_mean, old_sd = float(np.mean(vals)), float(np.std(vals))\n        if old_sd <= 0:\n            continue\n        vals2 = vals + shock * old_sd\n        new_sd = float(np.std(vals2))\n        if new_sd > 0:\n            vals2 = old_mean + (vals2 - float(np.mean(vals2))) * (old_sd / new_sd)\n        out[name] = np.maximum(vals2, 0.0)\n    return out\n\n\n'''
if "def apply_fd_correlated_simulations(" not in s:
    if helper_anchor not in s:
        raise SystemExit("FanDuel weather helper not found")
    s = s.replace(helper_anchor, helper + helper_anchor, 1)

# Locate the FanDuel section only, then insert correlation immediately before its
# simulation dataframe is stored. This protects every DraftKings path.
fd_start = s.find('if platform == "FanDuel":')
if fd_start < 0:
    raise SystemExit("FanDuel section not found")
fd = s[fd_start:]
call = "fd_sim_df = apply_fd_correlated_simulations(fd_sim_df, fd_players)"
if call not in fd:
    candidates = [
        'st.session_state["fd_simulation_df"] = fd_sim_df',
        "st.session_state['fd_simulation_df'] = fd_sim_df",
        'st.session_state["simulation_df"] = fd_sim_df',
        "st.session_state['simulation_df'] = fd_sim_df",
    ]
    hit = next((x for x in candidates if x in fd), None)
    if hit is None:
        raise SystemExit("FanDuel simulation dataframe assignment not found")
    fd = fd.replace(hit, call + "\n" + hit, 1)
    s = s[:fd_start] + fd

p.write_text(s)
print("Applied FanDuel-only correlated simulation outcomes")
