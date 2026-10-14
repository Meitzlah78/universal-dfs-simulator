from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# 1) Remove Fade from the editable Player Pool controls. Keep the internal Fade
# field available for compatibility, but force it off later so hidden stale fades
# cannot exclude players.
text = text.replace(
'''    display_settings = [
        ("Lock", False), ("Fade", False),
        ("Min Exposure %", 0), ("Max Exposure %", 100)
    ]
''',
'''    display_settings = [
        ("Lock", False),
        ("Min Exposure %", 0), ("Max Exposure %", 100)
    ]
''',
1,
)

text = text.replace(
'''            "Fade": st.column_config.CheckboxColumn("Fade", help="Keep this player out of lineup builds."),
''',
'',
1,
)

# 2) Reorder the visible Player Pool to match the requested layout and remove
# ProjectionSource / Injury Status from the visible table only.
marker = '''    st.caption("Player stats, simulation results, exposure, and editable controls are all in this one table. Lock includes a player; Fade excludes a player.")
'''
insert = '''    # Keep the visible Player Pool compact and in a consistent left-to-right order.
    # ProjectionSource and Injury Status still remain in the underlying data for app logic.
    control_display = control_display.drop(
        columns=["ProjectionSource", "Injury Status", "Fade"], errors="ignore"
    )
    _preferred_player_pool_order = [
        "Name", "Position", "Team", "Opponent", "Salary", "CaptainSalary",
        "Projection", "Sim Pts",
        "Captain Exp %", "MVP Exp %", "Exposure %", "Flex Exp %",
        "Projected Own %", "Mine Own %",
        "Field CPT Own %", "Field MVP Own %", "Field FLEX Own %", "Field Own %",
        "Sim P10", "Sim P25", "Sim P50", "Sim P75", "Sim P90", "Sim P95", "Sim P99",
        "Cap Hit %",
        "Lock", "Min Exposure %", "Max Exposure %", "Captain Min %", "Captain Max %",
    ]
    _ordered_player_pool_columns = [
        column for column in _preferred_player_pool_order if column in control_display.columns
    ]
    _remaining_player_pool_columns = [
        column for column in control_display.columns
        if column not in _ordered_player_pool_columns
    ]
    control_display = control_display[_ordered_player_pool_columns + _remaining_player_pool_columns]

    st.caption("Player stats, simulation results, exposure, and editable controls are all in this one table. Lock includes a player.")
'''
if insert not in text:
    if marker not in text:
        raise SystemExit("Could not find Player Pool caption insertion point")
    text = text.replace(marker, insert, 1)

# 3) Fade is no longer editable in the visible table. Do not try to read a
# missing Fade column back from the editor.
text = text.replace(
'''    for setting in [
        "Lock", "Fade", "Min Exposure %", "Max Exposure %"
    ] + (
''',
'''    for setting in [
        "Lock", "Min Exposure %", "Max Exposure %"
    ] + (
''',
1,
)

# 4) Force hidden Fade state off so an old saved fade cannot silently remove a player.
needle = '''    control_values["Lock"] = control_values["Lock"].astype(bool)
    control_values["Fade"] = control_values["Fade"].astype(bool)
'''
replacement = '''    control_values["Lock"] = control_values["Lock"].astype(bool)
    control_values["Fade"] = False
'''
if needle in text:
    text = text.replace(needle, replacement, 1)
elif replacement not in text:
    raise SystemExit("Could not find Fade normalization block")

path.write_text(text, encoding="utf-8")
print("Removed Fade/ProjectionSource/Injury Status from Player Pool and reordered visible columns.")
