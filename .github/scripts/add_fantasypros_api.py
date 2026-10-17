from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text(encoding="utf-8")

old_params = 'params={"position": position, "week": "current", "scoring": scoring},'
new_params = 'params={"position": position, "scoring": scoring},'
if old_params in s:
    s = s.replace(old_params, new_params, 1)

old_stats = '''                    stats = player.get("stats") or {}
                    if not isinstance(stats, dict):
                        stats = {}
'''
new_stats = '''                    stats = player.get("stats") or {}
                    # FantasyPros currently returns stats as a one-item list for
                    # NFL projections. Older responses used a dict, so support both.
                    if isinstance(stats, list):
                        stats = next((item for item in stats if isinstance(item, dict)), {})
                    if not isinstance(stats, dict):
                        stats = {}
'''
if old_stats in s:
    s = s.replace(old_stats, new_stats, 1)
elif 'if isinstance(stats, list):' not in s:
    raise SystemExit("FantasyPros stats parser block not found")

# FantasyPros is the preferred source attempt/order, while the app still averages
# every available external source equally for the final projection.
s = s.replace(
'''    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    fantasypros, fantasypros_status = get_projection_source_data(None, "FantasyPros", platform_name, target_names)
    source_maps = (("DFF", dff), ("DraftEdge", draftedge), ("FantasyPros", fantasypros))
''',
'''    fantasypros, fantasypros_status = get_projection_source_data(None, "FantasyPros", platform_name, target_names)
    dff, dff_status = get_projection_source_data(dff_file, "DFF", platform_name, target_names)
    draftedge, draftedge_status = get_projection_source_data(draftedge_file, "DraftEdge", platform_name, target_names)
    source_maps = (("FantasyPros", fantasypros), ("DFF", dff), ("DraftEdge", draftedge))
''', 1)
s = s.replace(
'''        f"External projection matches: DFF {match_counts['DFF']}; DraftEdge {match_counts['DraftEdge']}; "
        f"FantasyPros {match_counts['FantasyPros']}; averaged {averaged}; missing {missing_external}. "
        f"DFF: {dff_status}; DraftEdge: {draftedge_status}; FantasyPros: {fantasypros_status}. "
''',
'''        f"External projection matches: FantasyPros {match_counts['FantasyPros']}; DFF {match_counts['DFF']}; "
        f"DraftEdge {match_counts['DraftEdge']}; averaged {averaged}; missing {missing_external}. "
        f"FantasyPros: {fantasypros_status}; DFF: {dff_status}; DraftEdge: {draftedge_status}. "
''', 1)

p.write_text(s, encoding="utf-8")
print("FantasyPros stats parsing and preferred-source ordering applied")
