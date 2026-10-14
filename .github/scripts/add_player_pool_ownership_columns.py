from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

marker = '''    # Add simulated opponent-field ownership beside the user's own exposure columns.\n'''

old_insert = '''    # Easy-to-read overall ownership columns.\n    # Ownership % = exposure in the user's current selected portfolio/build.\n    # Proj Own % = ownership observed in the simulated opponent field.\n    if platform == "DraftKings" and lineup_mode == "Showdown":\n        own_captain = pd.to_numeric(player_display.get("Captain Exp %"), errors="coerce")\n        own_flex = pd.to_numeric(player_display.get("Flex Exp %"), errors="coerce")\n        if own_captain is not None and own_flex is not None:\n            player_display["Ownership %"] = (own_captain.fillna(0.0) + own_flex.fillna(0.0)).clip(upper=100.0).round(1)\n            no_own_data = own_captain.isna() & own_flex.isna()\n            player_display.loc[no_own_data, "Ownership %"] = np.nan\n        else:\n            player_display["Ownership %"] = np.nan\n    elif "Exposure %" in player_display.columns:\n        player_display["Ownership %"] = pd.to_numeric(\n            player_display["Exposure %"], errors="coerce"\n        ).round(1)\n    else:\n        player_display["Ownership %"] = np.nan\n\n'''

new_insert = '''    # Keep three overall ownership views side by side. Showdown also keeps the\n    # existing Captain Exp % and Flex Exp % columns for the user's portfolio.\n    # Projected Own % = pre-contest ownership estimate.\n    # Mine Own % = exposure in the user's current selected portfolio/build.\n    # Field Own % = ownership observed in the simulated opponent field.\n    ownership_lookup = {str(c).strip().casefold(): c for c in player_display.columns}\n    projected_own_col = next((ownership_lookup[k] for k in (\n        "projected ownership", "projected own", "ownership %", "ownership", "own%", "own"\n    ) if k in ownership_lookup), None)\n    if projected_own_col is not None:\n        player_display["Projected Own %"] = pd.to_numeric(\n            player_display[projected_own_col].astype(str).str.replace("%", "", regex=False),\n            errors="coerce",\n        ).clip(lower=0.0, upper=100.0).round(1)\n    else:\n        # Match the ownership proxy already used by lineup ranking when no\n        # external ownership column is available.\n        projection_values = pd.to_numeric(player_display.get("Projection"), errors="coerce")\n        if projection_values is not None and projection_values.notna().any():\n            projection_ranks = projection_values.rank(pct=True, method="average")\n            player_display["Projected Own %"] = (5.0 + 30.0 * projection_ranks).clip(0.0, 100.0).round(1)\n            player_display.loc[projection_values.isna() | projection_values.le(0), "Projected Own %"] = np.nan\n        else:\n            player_display["Projected Own %"] = np.nan\n\n    if platform == "DraftKings" and lineup_mode == "Showdown":\n        own_captain = pd.to_numeric(player_display.get("Captain Exp %"), errors="coerce")\n        own_flex = pd.to_numeric(player_display.get("Flex Exp %"), errors="coerce")\n        if own_captain is not None and own_flex is not None:\n            player_display["Mine Own %"] = (own_captain.fillna(0.0) + own_flex.fillna(0.0)).clip(upper=100.0).round(1)\n            no_own_data = own_captain.isna() & own_flex.isna()\n            player_display.loc[no_own_data, "Mine Own %"] = np.nan\n        else:\n            player_display["Mine Own %"] = np.nan\n    elif "Exposure %" in player_display.columns:\n        player_display["Mine Own %"] = pd.to_numeric(\n            player_display["Exposure %"], errors="coerce"\n        ).round(1)\n    else:\n        player_display["Mine Own %"] = np.nan\n\n'''

if old_insert in text:
    text = text.replace(old_insert, new_insert, 1)
elif new_insert not in text:
    if marker not in text:
        raise SystemExit("Could not find player ownership insertion point")
    text = text.replace(marker, new_insert + marker, 1)

old_field = '''        names_for_field = player_display["Name"].astype(str).str.strip()\n        overall_field = names_for_field.map(field_own_map)\n        player_display["Proj Own %"] = overall_field.round(1)\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n'''
base_field = '''        names_for_field = player_display["Name"].astype(str).str.strip()\n        overall_field = names_for_field.map(field_own_map)\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n'''
new_field = '''        names_for_field = player_display["Name"].astype(str).str.strip()\n        overall_field = names_for_field.map(field_own_map)\n        player_display["Field Own %"] = overall_field.round(1)\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n'''
if old_field in text:
    text = text.replace(old_field, new_field, 1)
elif base_field in text:
    text = text.replace(base_field, new_field, 1)
elif new_field not in text:
    raise SystemExit("Could not find simulated field ownership block")

old_else = '''    else:\n        player_display["Proj Own %"] = np.nan\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n'''
base_else = '''    else:\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n'''
new_else = '''    else:\n        player_display["Field Own %"] = np.nan\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n'''
if old_else in text:
    text = text.replace(old_else, new_else, 1)
elif base_else in text:
    text = text.replace(base_else, new_else, 1)
elif new_else not in text:
    raise SystemExit("Could not find missing field ownership block")

# Do not drop overall Field Own % in Showdown; keep it beside the role-specific\n# field columns and the user's Captain/Flex exposure columns.\ntext = text.replace(\n    '''            player_display = player_display.drop(columns=["Field Own %"], errors="ignore")\n        else:\n            player_display["Field Own %"] = overall_field.round(1)\n''',\n    '''        else:\n            player_display["Field Own %"] = overall_field.round(1)\n''',\n    1,\n)\ntext = text.replace(\n    '''            player_display = player_display.drop(columns=["Field Own %"], errors="ignore")\n        else:\n            player_display["Field Own %"] = np.nan\n''',\n    '''        else:\n            player_display["Field Own %"] = np.nan\n''',\n    1,\n)\n
path.write_text(text, encoding="utf-8")
print("Player Pool now shows Projected Own %, Mine Own %, Field Own %, Captain Exp %, and Flex Exp %.")
