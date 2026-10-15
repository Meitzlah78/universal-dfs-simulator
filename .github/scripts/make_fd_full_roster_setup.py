from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

anchor = "def apply_fd_nws_weather(fd_players):\n"
helper = r'''def simulate_fd_play_by_play(players_df, rng, n=SIMULATION_COUNT, correlation_strength=1.0):
    """FanDuel-only play-by-play NFL engine: simulate shared plays, then score player stat lines."""
    if not isinstance(players_df, pd.DataFrame) or players_df.empty:
        return pd.DataFrame()
    pool = players_df.drop_duplicates("Name", keep="first").copy().reset_index(drop=True)
    for col in ("Name", "Team", "Opponent", "Position"):
        if col not in pool.columns:
            pool[col] = ""
    pool["Projection"] = pd.to_numeric(pool.get("Projection", 0.0), errors="coerce").fillna(0.01).clip(lower=0.01)
    strength = float(np.clip(correlation_strength, 0.0, 1.0))
    names = pool["Name"].astype(str).tolist()
    stats = {name: {} for name in names}
    stat_keys = ("passing_yards","passing_tds","interceptions","rushing_yards","rushing_tds","receiving_yards","receiving_tds","receptions","fumbles_lost","sacks","def_interceptions","fumble_recoveries","defensive_tds","safeties","blocked_kicks","points_allowed","yards_allowed","fg_under_40","fg_40_49","fg_50_plus","extra_points_made")
    for name in names:
        for key in stat_keys:
            stats[name][key] = np.zeros(n, dtype=float)

    def pos_mask(frame, token):
        return frame["Position"].astype(str).str.upper().str.contains(token, regex=True)

    teams = [t for t in pool["Team"].astype(str).str.upper().str.strip().unique() if t and t != "NAN"]
    team_rows = {t: pool[pool["Team"].astype(str).str.upper().str.strip().eq(t)].copy() for t in teams}
    opponents = {}
    for team, rows in team_rows.items():
        vals = rows["Opponent"].astype(str).str.upper().str.strip()
        vals = vals[~vals.isin(["", "—", "-", "NAN", "NONE"])]
        opponents[team] = vals.iloc[0] if len(vals) else ""

    handled_games = set()
    for team in teams:
        opp = opponents.get(team, "")
        game_key = tuple(sorted([team, opp])) if opp in team_rows and opp != team else (team,)
        if game_key in handled_games:
            continue
        handled_games.add(game_key)
        sides = [team] + ([opp] if opp in team_rows and opp != team else [])
        game_pace = np.clip(rng.normal(1.0, 0.09, n), 0.80, 1.22)
        game_scoring = np.clip(rng.normal(1.0, 0.13, n), 0.70, 1.35)
        game_edge = rng.normal(0.0, 1.0, n)

        for side_i, side in enumerate(sides):
            rows = team_rows[side]
            other = sides[1-side_i] if len(sides) == 2 else ""
            qbs = rows[pos_mask(rows, "QB")].sort_values("Projection", ascending=False)
            rbs = rows[pos_mask(rows, "RB")].sort_values("Projection", ascending=False)
            recs = rows[pos_mask(rows, "WR|TE|RB")].sort_values("Projection", ascending=False)
            ks = rows[pos_mask(rows, r"(^|/)K($|/)")]
            defs = rows[pos_mask(rows, r"DST|DEF|^D$")]
            qb_name = str(qbs.iloc[0]["Name"]) if not qbs.empty else None
            rec_names = recs["Name"].astype(str).tolist()
            rb_names = rbs["Name"].astype(str).tolist()
            rec_w = np.clip(recs["Projection"].to_numpy(dtype=float), 0.05, None) if len(recs) else np.array([])
            rb_w = np.clip(rbs["Projection"].to_numpy(dtype=float), 0.05, None) if len(rbs) else np.array([])
            if len(rec_w): rec_w = rec_w / rec_w.sum()
            if len(rb_w): rb_w = rb_w / rb_w.sum()
            plays_by_sim = np.clip(np.rint(rng.normal(64.0, 6.5, n) * game_pace), 48, 82).astype(int)
            side_sign = 1.0 if side_i == 0 else -1.0

            team_points = np.zeros(n, dtype=float)
            team_yards = np.zeros(n, dtype=float)
            giveaways = np.zeros(n, dtype=float)
            sacks_allowed = np.zeros(n, dtype=float)
            for sim_i in range(n):
                score_env = 1.0 + strength * (game_scoring[sim_i] - 1.0)
                pace_env = 1.0 + strength * (game_pace[sim_i] - 1.0)
                edge = side_sign * game_edge[sim_i] * strength
                pass_rate = float(np.clip(0.58 - 0.025 * edge, 0.43, 0.72))
                for _ in range(int(plays_by_sim[sim_i])):
                    is_pass = rng.random() < pass_rate
                    if is_pass and qb_name:
                        if rng.random() < 0.065:
                            sacks_allowed[sim_i] += 1
                            continue
                        if rng.random() < 0.021:
                            stats[qb_name]["interceptions"][sim_i] += 1
                            giveaways[sim_i] += 1
                            continue
                        if not rec_names:
                            continue
                        target_i = int(rng.choice(len(rec_names), p=rec_w))
                        receiver = rec_names[target_i]
                        catch_prob = float(np.clip(0.64 + 0.025 * (rec_w[target_i] - np.mean(rec_w)), 0.50, 0.78))
                        if rng.random() < catch_prob:
                            yards = float(np.clip(rng.gamma(2.0, 5.6) * score_env, 0.0, 75.0))
                            stats[qb_name]["passing_yards"][sim_i] += yards
                            stats[receiver]["receiving_yards"][sim_i] += yards
                            stats[receiver]["receptions"][sim_i] += 1
                            team_yards[sim_i] += yards
                            td_prob = float(np.clip(0.035 * score_env + max(yards - 20.0, 0.0) * 0.0015, 0.015, 0.18))
                            if rng.random() < td_prob:
                                stats[qb_name]["passing_tds"][sim_i] += 1
                                stats[receiver]["receiving_tds"][sim_i] += 1
                                team_points[sim_i] += 7
                    elif rb_names:
                        runner_i = int(rng.choice(len(rb_names), p=rb_w))
                        runner = rb_names[runner_i]
                        yards = float(np.clip(rng.normal(4.35 * np.sqrt(score_env), 4.2), -4.0, 45.0))
                        yards = max(yards, -4.0)
                        stats[runner]["rushing_yards"][sim_i] += yards
                        team_yards[sim_i] += max(yards, 0.0)
                        if rng.random() < float(np.clip(0.026 * score_env + max(yards - 15.0, 0.0) * 0.002, 0.01, 0.14)):
                            stats[runner]["rushing_tds"][sim_i] += 1
                            team_points[sim_i] += 7
                    if rng.random() < 0.006:
                        carrier_pool = rec_names if rec_names else rb_names
                        if carrier_pool:
                            carrier = str(rng.choice(carrier_pool))
                            stats[carrier]["fumbles_lost"][sim_i] += 1
                            giveaways[sim_i] += 1
                # Kicking comes from possessions that did not become touchdowns.
                for _, kr in ks.iterrows():
                    kn = str(kr["Name"])
                    fg_att = int(np.clip(rng.poisson(1.7 * pace_env), 0, 5))
                    for _ in range(fg_att):
                        bucket = rng.random()
                        if bucket < 0.55: stats[kn]["fg_under_40"][sim_i] += 1
                        elif bucket < 0.82: stats[kn]["fg_40_49"][sim_i] += 1
                        else: stats[kn]["fg_50_plus"][sim_i] += 1
                    stats[kn]["extra_points_made"][sim_i] += max(0, round(team_points[sim_i] / 7.0))
                    team_points[sim_i] += 3 * fg_att

            # Defense for the opponent receives events generated by this offense.
            if other and other in team_rows:
                other_defs = team_rows[other][pos_mask(team_rows[other], r"DST|DEF|^D$")]
                for _, dr in other_defs.iterrows():
                    dn = str(dr["Name"])
                    stats[dn]["sacks"] += sacks_allowed
                    stats[dn]["def_interceptions"] += np.array([stats[qb_name]["interceptions"][i] if qb_name else 0 for i in range(n)])
                    stats[dn]["fumble_recoveries"] += np.maximum(giveaways - (stats[qb_name]["interceptions"] if qb_name else 0), 0)
                    stats[dn]["points_allowed"] = team_points.copy()
                    stats[dn]["yards_allowed"] = team_yards.copy()
                    stats[dn]["defensive_tds"] += rng.binomial(1, np.clip(0.025 + 0.025 * giveaways, 0.025, 0.16))

    out = {}
    for _, row in pool.iterrows():
        name = str(row["Name"]); pos = str(row["Position"]).upper(); target = float(row["Projection"])
        line = stats[name].copy()
        if any(x in pos for x in ("DST", "DEF")) or pos.strip() == "D": line["is_defense"] = 1
        vals = np.asarray(score_nfl_stat_line(line, "FanDuel"), dtype=float)
        mean = float(np.mean(vals)) if len(vals) else 0.0
        # Calibrate only the marginal mean; shared play outcomes/correlation stay intact.
        if mean > 0 and target > 0:
            vals *= float(np.clip(target / mean, 0.65, 1.55))
        elif target > 0:
            vals = np.maximum(0.0, rng.normal(target, max(0.75, target * 0.35), n))
        out[name] = np.maximum(vals, 0.0)
    return pd.DataFrame(out)


'''
# Replace the earlier FanDuel bottom-up helper with the play-by-play engine.
start = s.find("def simulate_fd_bottom_up_stats(")
end = s.find(anchor, start) if start >= 0 else -1
if start >= 0 and end > start:
    s = s[:start] + helper + s[end:]
elif "def simulate_fd_play_by_play(" not in s:
    if anchor not in s:
        raise SystemExit("FanDuel helper anchor not found")
    s = s.replace(anchor, helper + anchor, 1)

old = 'simulated_scores = simulate_fd_bottom_up_stats(fd_players, rng, SIMULATION_COUNT, correlation_strength)'
new = 'simulated_scores = simulate_fd_play_by_play(fd_players, rng, SIMULATION_COUNT, correlation_strength)'
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit("FanDuel simulation call not found")

p.write_text(s)
print("FanDuel now uses shared play-by-play simulation before FanDuel scoring")
