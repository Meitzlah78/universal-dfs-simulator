from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text(encoding='utf-8')

old = '''            response = requests.get(
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
'''
new = '''            result = {}
            diagnostic = []
            for position in ("QB", "RB", "WR", "TE"):
                response = requests.get(
                    f"https://api.gridirondata.com/api/v1/projections/{projection_week}",
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    params={"season": season, "position": position, "source": "weekly", "scoring": scoring},
                    timeout=(5, 30),
                )
                if response.status_code == 429:
                    st.info("GridIron rate limit reached; using the other projection sources for this refresh.")
                    break
                response.raise_for_status()
                payload = response.json()
                rows = payload.get("projections", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
                matched = 0
                for player in rows:
                    if not isinstance(player, dict):
                        continue
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
                        matched += 1
                diagnostic.append(f"{position} {matched}/{len(rows)}")
            st.caption(f"GridIron diagnostic — week {projection_week}; " + ", ".join(diagnostic) + f"; slate matches {len(result)}.")
            return result
'''
if old not in s:
    raise SystemExit('GridIron request block not found')
s = s.replace(old, new, 1)

old_sources = '''    fantasypros, fantasypros_status = get_projection_source_data(None, "FantasyPros", platform_name, target_names)
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    source_maps = (("FantasyPros", fantasypros), ("DFF", dff), ("DraftEdge", draftedge))
'''
new_sources = '''    gridiron, gridiron_status = get_projection_source_data(None, "GridIron", platform_name, target_names)
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    source_maps = (("GridIron", gridiron), ("DFF", dff), ("DraftEdge", draftedge))
'''
if old_sources in s:
    s = s.replace(old_sources, new_sources, 1)

s = s.replace("External projection matches: FantasyPros {match_counts['FantasyPros']}", "External projection matches: GridIron {match_counts['GridIron']}")
s = s.replace("FantasyPros: {fantasypros_status}; DFF: {dff_status}", "GridIron: {gridiron_status}; DFF: {dff_status}")

p.write_text(s, encoding='utf-8')
print('GridIron integration updated for QB/RB/WR/TE weekly calls')
