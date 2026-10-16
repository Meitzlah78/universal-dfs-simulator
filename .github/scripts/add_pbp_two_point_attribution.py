from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old_keys = '''    stat_keys = ("passing_yards","passing_tds","interceptions","rushing_yards","rushing_tds","receiving_yards","receiving_tds","receptions","fumbles_lost","sacks","def_interceptions","fumble_recoveries","defensive_tds","safeties","blocked_kicks","points_allowed","yards_allowed","fg_under_40","fg_40_49","fg_50_plus","extra_points_made")
'''
new_keys = '''    stat_keys = ("passing_yards","passing_tds","interceptions","rushing_yards","rushing_tds","receiving_yards","receiving_tds","receptions","fumbles_lost","two_point_conversions","sacks","def_interceptions","fumble_recoveries","defensive_tds","safeties","blocked_kicks","points_allowed","yards_allowed","fg_under_40","fg_40_49","fg_50_plus","extra_points_made")
'''
if new_keys not in text:
    if old_keys not in text:
        raise SystemExit("stat_keys anchor not found")
    text = text.replace(old_keys, new_keys, 1)

old_arrays = '''            team_points = np.zeros(n, dtype=float)
            team_yards = np.zeros(n, dtype=float)
            giveaways = np.zeros(n, dtype=float)
            sacks_allowed = np.zeros(n, dtype=float)
'''
new_arrays = '''            team_points = np.zeros(n, dtype=float)
            team_yards = np.zeros(n, dtype=float)
            giveaways = np.zeros(n, dtype=float)
            sacks_allowed = np.zeros(n, dtype=float)
            team_touchdowns = np.zeros(n, dtype=float)
            team_two_point_attempts = np.zeros(n, dtype=float)
'''
if new_arrays not in text:
    if old_arrays not in text:
        raise SystemExit("team arrays anchor not found")
    text = text.replace(old_arrays, new_arrays, 1)

old_pass_td = '''                            if rng.random() < td_prob:
                                stats[qb_name]["passing_tds"][sim_i] += 1
                                stats[receiver]["receiving_tds"][sim_i] += 1
                                team_points[sim_i] += 7
'''
new_pass_td = '''                            if rng.random() < td_prob:
                                stats[qb_name]["passing_tds"][sim_i] += 1
                                stats[receiver]["receiving_tds"][sim_i] += 1
                                team_touchdowns[sim_i] += 1
                                # Model the try as a separate event. A successful pass
                                # conversion credits BOTH passer and receiver; the existing
                                # site scorer then awards each player +2. Do not apply CPT/MVP
                                # multipliers here -- those belong at lineup scoring time.
                                if rng.random() < 0.12:
                                    team_two_point_attempts[sim_i] += 1
                                    if rng.random() < 0.48 and rec_names:
                                        conv_receiver = rec_names[int(rng.choice(len(rec_names), p=rec_w))]
                                        stats[qb_name]["two_point_conversions"][sim_i] += 1
                                        stats[conv_receiver]["two_point_conversions"][sim_i] += 1
                                        team_points[sim_i] += 8
                                    else:
                                        team_points[sim_i] += 6
                                else:
                                    team_points[sim_i] += 7
'''
if new_pass_td not in text:
    if old_pass_td not in text:
        raise SystemExit("pass TD anchor not found")
    text = text.replace(old_pass_td, new_pass_td, 1)

old_rush_td = '''                        if rng.random() < _rush_td_prob:
                            stats[runner]["rushing_tds"][sim_i] += 1
                            team_points[sim_i] += 7
'''
new_rush_td = '''                        if rng.random() < _rush_td_prob:
                            stats[runner]["rushing_tds"][sim_i] += 1
                            team_touchdowns[sim_i] += 1
                            # Rushing conversions credit only the rusher. The try can also
                            # be a pass even when the touchdown itself was a rush, so choose
                            # the conversion play independently from the scoring play.
                            if rng.random() < 0.12:
                                team_two_point_attempts[sim_i] += 1
                                conv_is_pass = bool(qb_name and rec_names and rng.random() < 0.62)
                                if rng.random() < 0.48:
                                    if conv_is_pass:
                                        conv_receiver = rec_names[int(rng.choice(len(rec_names), p=rec_w))]
                                        stats[qb_name]["two_point_conversions"][sim_i] += 1
                                        stats[conv_receiver]["two_point_conversions"][sim_i] += 1
                                    else:
                                        stats[runner]["two_point_conversions"][sim_i] += 1
                                    team_points[sim_i] += 8
                                else:
                                    team_points[sim_i] += 6
                            else:
                                team_points[sim_i] += 7
'''
if new_rush_td not in text:
    if old_rush_td not in text:
        raise SystemExit("rush TD anchor not found")
    text = text.replace(old_rush_td, new_rush_td, 1)

old_xp = '''                    stats[kn]["extra_points_made"][sim_i] += max(0, round(team_points[sim_i] / 7.0))
'''
new_xp = '''                    # Only touchdowns that did NOT choose a two-point try create an XP.
                    stats[kn]["extra_points_made"][sim_i] += max(0, team_touchdowns[sim_i] - team_two_point_attempts[sim_i])
'''
if new_xp not in text:
    if old_xp not in text:
        raise SystemExit("XP anchor not found")
    text = text.replace(old_xp, new_xp, 1)

path.write_text(text)
