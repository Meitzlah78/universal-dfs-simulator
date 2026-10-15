from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

anchor = "def apply_fd_nws_weather(fd_players):\n"
helper = r'''def simulate_fd_bottom_up_stats(players_df, rng, n=SIMULATION_COUNT, correlation_strength=1.0):
    """FanDuel-only bottom-up NFL simulation: game/team stats first, FD points second."""
    if not isinstance(players_df, pd.DataFrame) or players_df.empty:
        return pd.DataFrame()
    pool = players_df.drop_duplicates("Name", keep="first").copy().reset_index(drop=True)
    for col in ("Name", "Team", "Opponent", "Position"):
        if col not in pool.columns:
            pool[col] = ""
    pool["Projection"] = pd.to_numeric(pool.get("Projection", 0.0), errors="coerce").fillna(0.01).clip(lower=0.01)
    strength = float(np.clip(correlation_strength, 0.0, 1.0))
    out = {str(name): np.zeros(n, dtype=float) for name in pool["Name"].astype(str)}

    teams = [t for t in pool["Team"].astype(str).str.upper().str.strip().unique() if t and t != "NAN"]
    team_rows = {t: pool[pool["Team"].astype(str).str.upper().str.strip().eq(t)].copy() for t in teams}
    handled = set()

    def allocate(total, weights):
        weights = np.asarray(weights, dtype=float)
        weights = np.clip(weights, 0.001, None)
        weights /= weights.sum()
        # Dirichlet shares vary role from simulation to simulation while preserving hierarchy.
        alpha = np.clip(weights * 35.0, 0.35, None)
        shares = rng.dirichlet(alpha, size=n)
        return shares * np.asarray(total, dtype=float)[:, None]

    for team in teams:
        if team in handled:
            continue
        rows = team_rows[team]
        opp_values = rows["Opponent"].astype(str).str.upper().str.strip()
        opp_values = opp_values[~opp_values.isin(["", "—", "-", "NAN", "NONE"])]
        opp = opp_values.iloc[0] if len(opp_values) else ""
        pair = [team] + ([opp] if opp in team_rows and opp != team else [])
        game_env = np.clip(rng.normal(1.0, 0.13, n), 0.70, 1.35)
        # Shared pace and scoring environment creates natural cross-team correlation.
        pace = np.clip(rng.normal(1.0, 0.09, n), 0.78, 1.24)
        team_edge = rng.normal(0.0, 0.10, n)

        for side_i, side in enumerate(pair):
            side_rows = team_rows[side]
            side_factor = np.clip(game_env * pace * (1.0 + (team_edge if side_i == 0 else -team_edge)), 0.62, 1.48)
            plays = np.clip(np.rint(rng.normal(64.0, 7.0, n) * pace), 48, 82).astype(int)
            pass_rate = np.clip(rng.normal(0.58, 0.055, n) - (0.035 * team_edge if side_i == 0 else -0.035 * team_edge), 0.43, 0.72)
            pass_att = np.clip(np.rint(plays * pass_rate), 18, 58).astype(int)
            rush_att = np.maximum(plays - pass_att, 12)
            completions = rng.binomial(pass_att, np.clip(rng.normal(0.65, 0.025, n), 0.54, 0.75))
            pass_yards = np.maximum(0.0, completions * np.clip(rng.normal(11.0, 1.5, n), 7.0, 15.5) * side_factor)
            rush_yards = np.maximum(0.0, rush_att * np.clip(rng.normal(4.35, 0.55, n), 2.8, 6.2) * np.sqrt(side_factor))
            offensive_tds = np.clip(rng.poisson(np.clip(2.45 * side_factor, 0.5, 5.0)), 0, 7)
            pass_td_share = np.clip(rng.normal(0.68, 0.10, n), 0.35, 0.90)
            pass_tds = rng.binomial(offensive_tds.astype(int), pass_td_share)
            rush_tds = offensive_tds - pass_tds
            interceptions = np.clip(rng.poisson(0.75 / np.clip(side_factor, 0.75, 1.3)), 0, 4)
            fumbles = rng.binomial(1, 0.10, n)

            qbs = side_rows[side_rows["Position"].astype(str).str.upper().str.contains("QB")]
            if not qbs.empty:
                qb = qbs.sort_values("Projection", ascending=False).iloc[0]
                qn = str(qb["Name"])
                qb_rush_share = np.clip(0.08 + float(qb["Projection"]) / 180.0, 0.08, 0.25)
                qb_stats = {
                    "passing_yards": pass_yards,
                    "passing_tds": pass_tds,
                    "interceptions": interceptions,
                    "rushing_yards": rush_yards * qb_rush_share,
                    "rushing_tds": rng.binomial(rush_tds.astype(int), np.clip(qb_rush_share * 1.35, 0.08, 0.38)),
                    "fumbles_lost": fumbles,
                }
                out[qn] = np.asarray(score_nfl_stat_line(qb_stats, "FanDuel"), dtype=float)

            receivers = side_rows[side_rows["Position"].astype(str).str.upper().str.contains("WR|TE|RB", regex=True)].copy()
            if not receivers.empty:
                rec_weights = receivers["Projection"].to_numpy(dtype=float)
                rec_yard_alloc = allocate(pass_yards, rec_weights)
                reception_alloc = allocate(completions, rec_weights)
                td_alloc = allocate(pass_tds, np.power(np.clip(rec_weights, 0.01, None), 1.15))
                td_winners = np.argmax(td_alloc, axis=1)
                rec_tds_matrix = np.zeros((n, len(receivers)), dtype=int)
                for sim_i in range(n):
                    if pass_tds[sim_i] > 0:
                        probs = np.clip(td_alloc[sim_i], 0.001, None); probs /= probs.sum()
                        winners = rng.choice(len(receivers), size=int(pass_tds[sim_i]), replace=True, p=probs)
                        for w in winners: rec_tds_matrix[sim_i, w] += 1
                for j, (_, pr) in enumerate(receivers.iterrows()):
                    name = str(pr["Name"]); pos = str(pr["Position"]).upper()
                    stats = {
                        "receiving_yards": rec_yard_alloc[:, j],
                        "receiving_tds": rec_tds_matrix[:, j],
                        "receptions": np.rint(reception_alloc[:, j]).astype(int),
                        "fumbles_lost": rng.binomial(1, 0.02, n),
                    }
                    if "RB" in pos:
                        rb_pool = side_rows[side_rows["Position"].astype(str).str.upper().str.contains("RB")]
                        rb_weights = rb_pool["Projection"].to_numpy(dtype=float)
                        rb_names = rb_pool["Name"].astype(str).tolist()
                        if name in rb_names:
                            rush_alloc = allocate(rush_yards * (1.0 - qb_rush_share if not qbs.empty else 0.94), rb_weights)
                            att_alloc = allocate(rush_att * (1.0 - qb_rush_share if not qbs.empty else 0.94), rb_weights)
                            rj = rb_names.index(name)
                            stats["rushing_yards"] = rush_alloc[:, rj]
                            stats["rushing_tds"] = np.rint(allocate(rush_tds, rb_weights)[:, rj]).astype(int)
                    out[name] = np.asarray(score_nfl_stat_line(stats, "FanDuel"), dtype=float)

            # Defenses are linked directly to opponent turnovers/scoring environment.
            defenses = side_rows[side_rows["Position"].astype(str).str.upper().str.contains("D|DST|DEF", regex=True)]
            for _, dr in defenses.iterrows():
                dn = str(dr["Name"])
                points_allowed = np.clip(np.rint(20.5 * side_factor + rng.normal(0, 6, n)), 0, 50)
                dst_stats = {
                    "sacks": rng.poisson(2.4, n), "def_interceptions": interceptions,
                    "fumble_recoveries": fumbles, "defensive_tds": rng.binomial(1, 0.07, n),
                    "safeties": rng.binomial(1, 0.02, n), "blocked_kicks": rng.binomial(1, 0.03, n),
                    "points_allowed": points_allowed, "yards_allowed": np.clip(pass_yards + rush_yards, 150, 600), "is_defense": 1,
                }
                out[dn] = np.asarray(score_nfl_stat_line(dst_stats, "FanDuel"), dtype=float)

            # Projection calibration changes player baselines, not correlation: each player's
            # stat-derived FD distribution is shifted/scaled toward the current slate projection.
            for _, pr in side_rows.iterrows():
                name = str(pr["Name"]); target = float(pr["Projection"])
                vals = out.get(name)
                if vals is None or not np.any(vals):
                    # Kicker/unsupported positions retain a stat-line fallback.
                    if "K" in str(pr["Position"]).upper():
                        stats = {"fg_under_40": rng.poisson(1.0 * side_factor), "fg_40_49": rng.poisson(0.45 * side_factor), "fg_50_plus": rng.poisson(0.22 * side_factor), "extra_points_made": rng.poisson(2.0 * side_factor)}
                        vals = np.asarray(score_nfl_stat_line(stats, "FanDuel"), dtype=float)
                    else:
                        vals = np.maximum(0.0, rng.normal(target, max(0.75, target * 0.35), n))
                mean = float(np.mean(vals))
                if mean > 0:
                    scale = float(np.clip(target / mean, 0.65, 1.55))
                    vals = vals * scale
                out[name] = np.maximum(vals, 0.0)
            handled.add(side)
        handled.update(pair)

    return pd.DataFrame(out)


'''
if "def simulate_fd_bottom_up_stats(" not in s:
    if anchor not in s:
        raise SystemExit("FanDuel helper anchor not found")
    s = s.replace(anchor, helper + anchor, 1)

old = 'simulated_scores = _simulate_scored_player_outcomes(fd_players, "FanDuel", rng)\n            simulated_scores = apply_fd_correlated_simulations(simulated_scores, fd_players, correlation_strength)'
old2 = 'simulated_scores = _simulate_scored_player_outcomes(fd_players, "FanDuel", rng)'
new = 'simulated_scores = simulate_fd_bottom_up_stats(fd_players, rng, SIMULATION_COUNT, correlation_strength)'
if old in s:
    s = s.replace(old, new, 1)
elif old2 in s:
    s = s.replace(old2, new, 1)
elif new not in s:
    raise SystemExit("FanDuel simulation call not found")

p.write_text(s)
print("FanDuel now simulates football stats first, then FanDuel fantasy points")
