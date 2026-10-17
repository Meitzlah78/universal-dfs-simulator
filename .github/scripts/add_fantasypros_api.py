from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text(encoding="utf-8")

# Add FantasyPros handling immediately after the current target-key block.
anchor = '''    target_keys = {
        normalize_projection_player_name(name)
        for name in (target_names or [])
        if normalize_projection_player_name(name)
    }
'''
block = anchor + '''
    # FantasyPros official API. The API key lives only in Streamlit Secrets.
    if source_name == "FantasyPros":
        try:
            api_key = str(st.secrets.get("FANTASYPROS_API_KEY", "")).strip()
        except Exception:
            api_key = ""
        if not api_key:
            return {}
        try:
            from datetime import datetime
            season = datetime.now(ZoneInfo("America/New_York")).year
            response = requests.get(
                f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections",
                headers={"x-api-key": api_key, "Accept": "application/json"},
                params={"positions": "QB:RB:WR:TE:K:DST", "scoring": "PPR"},
                timeout=(5, 30),
            )
            response.raise_for_status()
            payload = response.json()
            players = payload.get("players", []) if isinstance(payload, dict) else []
            result = {}
            is_fd = "fanduel" in str(platform_name).casefold()
            for player in players:
                if not isinstance(player, dict):
                    continue
                name = player.get("name") or player.get("player_name")
                key = normalize_projection_player_name(name)
                if not key or (target_keys and key not in target_keys):
                    continue
                stats = player.get("stats") or {}
                if not isinstance(stats, dict):
                    stats = {}
                candidates = (
                    ("points_half", "fpts_half", "fantasy_points_half")
                    if is_fd else
                    ("points_ppr", "fpts_ppr", "fantasy_points_ppr")
                )
                value = next((stats.get(k) for k in candidates if stats.get(k) is not None), None)
                if value is None:
                    value = stats.get("points")
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(value) and value >= 0:
                    result[key] = value
            return result
        except Exception as exc:
            st.warning(f"FantasyPros API unavailable: {type(exc).__name__}: {exc}")
            return {}
'''
if 'if source_name == "FantasyPros":' not in s:
    if anchor not in s:
        raise SystemExit("projection target anchor not found")
    s = s.replace(anchor, block, 1)

s = s.replace(
    'for source_name in ("DFF", "DraftEdge"):',
    'for source_name in ("DFF", "DraftEdge", "FantasyPros"): ',
    1,
)

old = '''def apply_external_projection_sources(players_frame, dff_file, draftedge_file, platform_name='DraftKings'):
    """Use only DFF/DraftEdge projections; never substitute internal estimates."""
    result = players_frame.copy()
    target_names = result["Name"].astype(str).tolist() if "Name" in result.columns else []
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    projections, sources = [], []
    dff_matches = draftedge_matches = averages = missing_external = 0

    for _, row in result.iterrows():
        key = normalize_projection_player_name(row.get("Name", ""))
        dff_value, edge_value = dff.get(key), draftedge.get(key)

        if dff_value is not None and edge_value is not None:
            value, source = (dff_value + edge_value) / 2.0, "DFF + DraftEdge average"
            averages += 1
        elif dff_value is not None:
            value, source = dff_value, "DFF"
        elif edge_value is not None:
            value, source = edge_value, "DraftEdge"
        else:
            value, source = np.nan, "No external projection"
            missing_external += 1

        projections.append(value)
        sources.append(source)
        dff_matches += int(dff_value is not None)
        draftedge_matches += int(edge_value is not None)

    result["Projection"] = pd.to_numeric(
        pd.Series(projections, index=result.index), errors="coerce"
    )
    result["ProjectionSource"] = sources
    st.caption(
        f"External projection matches: DFF {dff_matches}; DraftEdge {draftedge_matches}; "
        f"averaged {averages}; missing from both external sources {missing_external}. "
        f"DFF source: {dff_status}; DraftEdge source: {draftedge_status}. "
        "Internal estimates are disabled. Players without a valid external projection, including zero projections, "
        "are removed from the lineup pool."
    )
    return result
'''
new = '''def apply_external_projection_sources(players_frame, dff_file, draftedge_file, platform_name='DraftKings'):
    """Average every available external projection; never substitute internal estimates."""
    result = players_frame.copy()
    target_names = result["Name"].astype(str).tolist() if "Name" in result.columns else []
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    fantasypros, fantasypros_status = get_projection_source_data(None, "FantasyPros", platform_name, target_names)
    source_maps = (("DFF", dff), ("DraftEdge", draftedge), ("FantasyPros", fantasypros))
    match_counts = {name: 0 for name, _ in source_maps}
    projections, sources = [], []
    averaged = missing_external = 0

    for _, row in result.iterrows():
        key = normalize_projection_player_name(row.get("Name", ""))
        available = []
        for source_name, values in source_maps:
            value = values.get(key)
            if value is not None:
                available.append((source_name, float(value)))
                match_counts[source_name] += 1
        if available:
            value = float(np.mean([v for _, v in available]))
            source = " + ".join(name for name, _ in available)
            if len(available) > 1:
                source += " average"
                averaged += 1
        else:
            value, source = np.nan, "No external projection"
            missing_external += 1
        projections.append(value)
        sources.append(source)

    result["Projection"] = pd.to_numeric(pd.Series(projections, index=result.index), errors="coerce")
    result["ProjectionSource"] = sources
    st.caption(
        f"External projection matches: DFF {match_counts['DFF']}; DraftEdge {match_counts['DraftEdge']}; "
        f"FantasyPros {match_counts['FantasyPros']}; averaged {averaged}; missing {missing_external}. "
        f"DFF: {dff_status}; DraftEdge: {draftedge_status}; FantasyPros: {fantasypros_status}. "
        "Internal estimates are disabled. Players without a valid external projection, including zero projections, "
        "are removed from the lineup pool."
    )
    return result
'''
if old in s:
    s = s.replace(old, new, 1)
elif "FantasyPros {match_counts['FantasyPros']}" not in s:
    raise SystemExit("projection averaging function anchor not found")

p.write_text(s, encoding="utf-8")
print("FantasyPros API integration applied")
