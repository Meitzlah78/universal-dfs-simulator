from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old = '''    if str(platform).lower().startswith("fanduel"):
        stats_map = {
            "passing_yards": "passing_yards", "passing_tds": "passing_tds",
            "interceptions": "interceptions", "rushing_yards": "rushing_yards",
            "rushing_tds": "rushing_tds", "receiving_yards": "receiving_yards",
            "receiving_tds": "receiving_tds", "receptions": "receptions",
            "fumbles_lost": "sack_fumbles_lost",
        }
        scores = []
        for _, game in rows.iterrows():
            stat_line = {}
            for output_col, source_col in stats_map.items():
                if source_col in rows.columns:
                    stat_line[output_col] = pd.to_numeric(pd.Series([game[source_col]]), errors="coerce").fillna(0).iloc[0]
            # Normalize all offensive 2PT roles into the shared scoring field.
            stat_line["two_point_conversions"] = historical_two_point_conversions(game)
            scores.append(float(score_nfl_stat_line(stat_line, platform)))
        points = np.asarray(scores, dtype=float)
    else:
        points_col = next((col for col in ["fantasy_points_ppr", "fantasy_points"] if col in rows.columns), None)
        if points_col is None:
            return None
        points = pd.to_numeric(rows[points_col], errors="coerce").fillna(0).to_numpy(dtype=float)
'''
new = '''    # Rebuild offensive historical fantasy scores from raw stats for BOTH sites.
    # This is especially important for the optimized DraftKings Showdown engine:
    # nflverse fantasy_points_ppr is not a guaranteed exact DK scoring column and
    # can omit/handle site-specific details differently. Keep site differences in
    # score_nfl_stat_line() and keep raw-stat normalization site-neutral here.
    primary_position = str(position or "").upper().strip().split("/")[0]
    rebuild_positions = {"QB", "RB", "WR", "TE"}
    raw_required = {
        "QB": {"passing_yards", "passing_tds", "interceptions", "rushing_yards", "rushing_tds"},
        "RB": {"rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds", "receptions"},
        "WR": {"receiving_yards", "receiving_tds", "receptions"},
        "TE": {"receiving_yards", "receiving_tds", "receptions"},
    }
    can_rebuild = primary_position in rebuild_positions and raw_required.get(primary_position, set()).issubset(rows.columns)

    if can_rebuild:
        stats_map = {
            "passing_yards": "passing_yards", "passing_tds": "passing_tds",
            "interceptions": "interceptions", "rushing_yards": "rushing_yards",
            "rushing_tds": "rushing_tds", "receiving_yards": "receiving_yards",
            "receiving_tds": "receiving_tds", "receptions": "receptions",
        }
        # nflverse exposes several fumble columns across releases. Prefer an
        # explicit lost-fumble field; sack_fumbles_lost is only a QB fallback.
        fumble_source = next(
            (col for col in ("fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost", "sack_fumbles_lost") if col in rows.columns),
            None,
        )
        scores = []
        for _, game in rows.iterrows():
            stat_line = {}
            for output_col, source_col in stats_map.items():
                if source_col in rows.columns:
                    stat_line[output_col] = pd.to_numeric(pd.Series([game[source_col]]), errors="coerce").fillna(0).iloc[0]
            if fumble_source is not None:
                stat_line["fumbles_lost"] = pd.to_numeric(pd.Series([game[fumble_source]]), errors="coerce").fillna(0).iloc[0]
            stat_line["two_point_conversions"] = historical_two_point_conversions(game)
            scores.append(float(score_nfl_stat_line(stat_line, platform)))
        points = np.asarray(scores, dtype=float)
    else:
        # K/DST and incomplete legacy rows stay on the provider fallback until
        # their complete raw-stat mappings are available; never fabricate stats.
        points_col = next((col for col in ["fantasy_points_ppr", "fantasy_points"] if col in rows.columns), None)
        if points_col is None:
            return None
        points = pd.to_numeric(rows[points_col], errors="coerce").fillna(0).to_numpy(dtype=float)
'''

if new not in text:
    if old not in text:
        raise SystemExit("historical scoring block anchor not found")
    text = text.replace(old, new, 1)

path.write_text(text)
