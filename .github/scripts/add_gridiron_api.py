from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text(encoding='utf-8')

anchor = '''    def matches_target(projections):
        return not target_keys or bool(target_keys.intersection(projections))
'''
block = '''    # GridIron Data official API. One cached request returns the full weekly pool.
    if source_name == "GridIron":
        try:
            api_key = str(st.secrets.get("GRIDIRON_API_KEY", "")).strip()
        except Exception:
            api_key = ""
        if not api_key:
            return {}
        try:
            from datetime import datetime
            season = datetime.now(ZoneInfo("America/New_York")).year
            now_et = datetime.now(ZoneInfo("America/New_York"))
            sep1 = datetime(season, 9, 1, tzinfo=ZoneInfo("America/New_York"))
            labor_day = sep1 + pd.Timedelta(days=(7 - sep1.weekday()) % 7)
            kickoff = labor_day + pd.Timedelta(days=3)
            projection_week = max(1, min(18, ((now_et.date() - kickoff.date()).days // 7) + 1))
            scoring = "half" if "fanduel" in str(platform_name).casefold() else "ppr"
            response = requests.get(
                f"https://api.gridirondata.com/api/v1/projections/{projection_week}",
                headers={"x-api-key": api_key, "Accept": "application/json"},
                params={"season": season, "source": "weekly", "scoring": scoring},
                timeout=(5, 30),
            )
            if response.status_code == 429:
                st.info("GridIron rate limit reached; using the other projection sources for this refresh.")
                return {}
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("projections", []) if isinstance(payload, dict) else []
            result = {}
            for player in rows:
                if not isinstance(player, dict):
                    continue
                # Never accept GridIron's season-prorated fallback as a weekly projection.
                if str(player.get("projection_source", "weekly")).casefold() != "weekly":
                    continue
                key = normalize_projection_player_name(player.get("player_name") or player.get("name"))
                if not key or (target_keys and key not in target_keys):
                    continue
                try:
                    value = float(player.get("projected_points"))
                except (TypeError, ValueError):
                    continue
                if np.isfinite(value) and value >= 0:
                    result[key] = value
            st.caption(
                f"GridIron diagnostic — week {projection_week}; weekly rows {len(rows)}; slate matches {len(result)}."
            )
            return result
        except Exception as exc:
            st.warning(f"GridIron API unavailable: {type(exc).__name__}: {exc}")
            return {}

'''
if 'if source_name == "GridIron":' not in s:
    if anchor not in s:
        raise SystemExit('GridIron insertion anchor not found')
    s = s.replace(anchor, block + anchor, 1)

old = '''    fantasypros, fantasypros_status = get_projection_source_data(None, "FantasyPros", platform_name, target_names)
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    source_maps = (("FantasyPros", fantasypros), ("DFF", dff), ("DraftEdge", draftedge))
'''
new = '''    gridiron, gridiron_status = get_projection_source_data(None, "GridIron", platform_name, target_names)
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    source_maps = (("GridIron", gridiron), ("DFF", dff), ("DraftEdge", draftedge))
'''
if old in s:
    s = s.replace(old, new, 1)
elif 'source_maps = (("GridIron", gridiron)' not in s:
    raise SystemExit('projection source-map anchor not found')

old_caption = '''        f"External projection matches: FantasyPros {match_counts['FantasyPros']}; DFF {match_counts['DFF']}; "
        f"DraftEdge {match_counts['DraftEdge']}; averaged {averaged}; missing {missing_external}. "
        f"FantasyPros: {fantasypros_status}; DFF: {dff_status}; DraftEdge: {draftedge_status}. "
'''
new_caption = '''        f"External projection matches: GridIron {match_counts['GridIron']}; DFF {match_counts['DFF']}; "
        f"DraftEdge {match_counts['DraftEdge']}; averaged {averaged}; missing {missing_external}. "
        f"GridIron: {gridiron_status}; DFF: {dff_status}; DraftEdge: {draftedge_status}. "
'''
if old_caption in s:
    s = s.replace(old_caption, new_caption, 1)
elif "External projection matches: GridIron" not in s:
    raise SystemExit('projection caption anchor not found')

p.write_text(s, encoding='utf-8')
print('GridIron weekly projection API integrated')
