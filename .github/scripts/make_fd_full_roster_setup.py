from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# FanDuel lists defenses as full team names while projection sources can use
# nickname or abbreviation. Recover those real external projections before the
# zero/missing-projection filter removes every defense.
needle = '''    fd_players = apply_external_projection_sources(fd_players, fd_dff_projection_file, fd_draftedge_projection_file, platform_name=("FanDuel Single Game" if lineup_mode == "Single Game" else "FanDuel Full Roster"))
    fd_valid_projection_count = int(pd.to_numeric(fd_players.get("Projection"), errors="coerce").gt(0).sum())
'''
replacement = '''    fd_projection_platform = "FanDuel Single Game" if lineup_mode == "Single Game" else "FanDuel Full Roster"
    fd_players = apply_external_projection_sources(
        fd_players, fd_dff_projection_file, fd_draftedge_projection_file,
        platform_name=fd_projection_platform
    )
    if lineup_mode == "Full Roster":
        fd_defense_aliases = {
            "ARI": ["Arizona Cardinals", "Cardinals", "Arizona"],
            "ATL": ["Atlanta Falcons", "Falcons", "Atlanta"],
            "BAL": ["Baltimore Ravens", "Ravens", "Baltimore"],
            "BUF": ["Buffalo Bills", "Bills", "Buffalo"],
            "CAR": ["Carolina Panthers", "Panthers", "Carolina"],
            "CHI": ["Chicago Bears", "Bears", "Chicago"],
            "CIN": ["Cincinnati Bengals", "Bengals", "Cincinnati"],
            "CLE": ["Cleveland Browns", "Browns", "Cleveland"],
            "DAL": ["Dallas Cowboys", "Cowboys", "Dallas"],
            "DEN": ["Denver Broncos", "Broncos", "Denver"],
            "DET": ["Detroit Lions", "Lions", "Detroit"],
            "GB": ["Green Bay Packers", "Packers", "Green Bay"],
            "HOU": ["Houston Texans", "Texans", "Houston"],
            "IND": ["Indianapolis Colts", "Colts", "Indianapolis"],
            "JAX": ["Jacksonville Jaguars", "Jaguars", "Jacksonville"],
            "KC": ["Kansas City Chiefs", "Chiefs", "Kansas City"],
            "LV": ["Las Vegas Raiders", "Raiders", "Las Vegas"],
            "LAC": ["Los Angeles Chargers", "Chargers", "LA Chargers"],
            "LAR": ["Los Angeles Rams", "Rams", "LA Rams"],
            "MIA": ["Miami Dolphins", "Dolphins", "Miami"],
            "MIN": ["Minnesota Vikings", "Vikings", "Minnesota"],
            "NE": ["New England Patriots", "Patriots", "New England"],
            "NO": ["New Orleans Saints", "Saints", "New Orleans"],
            "NYG": ["New York Giants", "Giants", "NY Giants"],
            "NYJ": ["New York Jets", "Jets", "NY Jets"],
            "PHI": ["Philadelphia Eagles", "Eagles", "Philadelphia"],
            "PIT": ["Pittsburgh Steelers", "Steelers", "Pittsburgh"],
            "SEA": ["Seattle Seahawks", "Seahawks", "Seattle"],
            "SF": ["San Francisco 49ers", "49ers", "San Francisco"],
            "TB": ["Tampa Bay Buccaneers", "Buccaneers", "Tampa Bay", "Bucs"],
            "TEN": ["Tennessee Titans", "Titans", "Tennessee"],
            "WAS": ["Washington Commanders", "Commanders", "Washington"],
        }
        fd_dff_all, _ = get_projection_source_data(
            fd_dff_projection_file, "DFF", fd_projection_platform,
            target_names=fd_players["Name"].astype(str).tolist()
        )
        fd_edge_all, _ = get_projection_source_data(
            fd_draftedge_projection_file, "DraftEdge", fd_projection_platform,
            target_names=fd_players["Name"].astype(str).tolist()
        )
        fd_def_mask = fd_players["Position"].astype(str).str.upper().isin(["D", "DST", "DEF"])
        for fd_idx in fd_players.index[fd_def_mask]:
            if pd.notna(pd.to_numeric(fd_players.at[fd_idx, "Projection"], errors="coerce")) and float(fd_players.at[fd_idx, "Projection"]) > 0:
                continue
            fd_team = str(fd_players.at[fd_idx, "Team"]).strip().upper()
            aliases = [str(fd_players.at[fd_idx, "Name"]), fd_team] + fd_defense_aliases.get(fd_team, [])
            alias_keys = [normalize_projection_player_name(alias) for alias in aliases]
            dff_value = next((fd_dff_all.get(key) for key in alias_keys if fd_dff_all.get(key) is not None), None)
            edge_value = next((fd_edge_all.get(key) for key in alias_keys if fd_edge_all.get(key) is not None), None)
            if dff_value is not None and edge_value is not None:
                fd_players.at[fd_idx, "Projection"] = (float(dff_value) + float(edge_value)) / 2.0
                fd_players.at[fd_idx, "ProjectionSource"] = "DFF + DraftEdge average"
            elif dff_value is not None:
                fd_players.at[fd_idx, "Projection"] = float(dff_value)
                fd_players.at[fd_idx, "ProjectionSource"] = "DFF"
            elif edge_value is not None:
                fd_players.at[fd_idx, "Projection"] = float(edge_value)
                fd_players.at[fd_idx, "ProjectionSource"] = "DraftEdge"
    fd_valid_projection_count = int(pd.to_numeric(fd_players.get("Projection"), errors="coerce").gt(0).sum())
'''
if needle not in text:
    raise SystemExit("FanDuel projection block not found")
text = text.replace(needle, replacement, 1)

path.write_text(text, encoding="utf-8")
