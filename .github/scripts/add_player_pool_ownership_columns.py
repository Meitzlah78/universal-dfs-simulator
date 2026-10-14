from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

marker = '''    # Add simulated opponent-field ownership beside the user's own exposure columns.\n'''
insert = '''    # Easy-to-read overall ownership columns.\n    # Ownership % = exposure in the user's current selected portfolio/build.\n    # Proj Own % = ownership observed in the simulated opponent field.\n    if platform == "DraftKings" and lineup_mode == "Showdown":\n        own_captain = pd.to_numeric(player_display.get("Captain Exp %"), errors="coerce")\n        own_flex = pd.to_numeric(player_display.get("Flex Exp %"), errors="coerce")\n        if own_captain is not None and own_flex is not None:\n            player_display["Ownership %"] = (own_captain.fillna(0.0) + own_flex.fillna(0.0)).clip(upper=100.0).round(1)\n            no_own_data = own_captain.isna() & own_flex.isna()\n            player_display.loc[no_own_data, "Ownership %"] = np.nan\n        else:\n            player_display["Ownership %"] = np.nan\n    elif "Exposure %" in player_display.columns:\n        player_display["Ownership %"] = pd.to_numeric(\n            player_display["Exposure %"], errors="coerce"\n        ).round(1)\n    else:\n        player_display["Ownership %"] = np.nan\n\n'''
if insert not in text:
    if marker not in text:
        raise SystemExit("Could not find player ownership insertion point")
    text = text.replace(marker, insert + marker, 1)

old = '''        names_for_field = player_display["Name"].astype(str).str.strip()\n        overall_field = names_for_field.map(field_own_map)\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n'''
new = '''        names_for_field = player_display["Name"].astype(str).str.strip()\n        overall_field = names_for_field.map(field_own_map)\n        player_display["Proj Own %"] = overall_field.round(1)\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n'''
if new not in text:
    if old not in text:
        raise SystemExit("Could not find simulated field ownership block")
    text = text.replace(old, new, 1)

old_else = '''    else:\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n            player_display["Field CPT Own %"] = np.nan\n'''
new_else = '''    else:\n        player_display["Proj Own %"] = np.nan\n        if platform == "DraftKings" and lineup_mode == "Showdown":\n            player_display["Field CPT Own %"] = np.nan\n'''
if new_else not in text:
    if old_else not in text:
        raise SystemExit("Could not find missing field ownership block")
    text = text.replace(old_else, new_else, 1)

path.write_text(text, encoding="utf-8")
print("Added Ownership % and Proj Own % to the DraftKings Player Pool.")
