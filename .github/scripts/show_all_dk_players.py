from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

anchor = '''    def internal_slate_key(frame):\n        \"\"\"Stable identity for an uploaded slate, independent of external projections.\"\"\"\n'''
if 'all_dk_players_df = players_df.copy()' not in text:
    text = text.replace(anchor, '    # Keep the full DraftKings salary-file pool visible even when some players do not yet have projections.\n    all_dk_players_df = players_df.copy()\n\n' + anchor, 1)

old_block = '''    players_df = exclude_zero_projection_players(players_df, \"DraftKings \" + lineup_mode)\n    internal_key = internal_slate_key(players_df)\n    st.caption(\"Projection values use the DFF/DraftEdge average when both are available, otherwise the single available source. Players without an external projection or with a zero projection are excluded.\")\n'''
new_block = '''    internal_key = internal_slate_key(all_dk_players_df)\n    st.caption(\"Projection values use the DFF/DraftEdge average when both are available, otherwise the single available source. All salary-file players remain visible; players without a positive external projection stay out of SIM/BUILD until a refresh finds one.\")\n'''
if old_block in text:
    text = text.replace(old_block, new_block, 1)

old_opp = '''    opponent_source = uploaded_df if \"uploaded_df\" in locals() else None\n    opponent_map = build_opponent_map(opponent_source, players_df[\"Team\"])\n    players_df[\"Opponent\"] = players_df[\"Team\"].map(opponent_map).fillna(\"—\")\n\n    players_df[\"CaptainSalary\"] = (\n        players_df[\"Salary\"] * 1.5\n    ).astype(int)\n'''
new_opp = '''    opponent_source = uploaded_df if \"uploaded_df\" in locals() else None\n    opponent_map = build_opponent_map(opponent_source, all_dk_players_df[\"Team\"])\n    all_dk_players_df[\"Opponent\"] = all_dk_players_df[\"Team\"].map(opponent_map).fillna(\"—\")\n    all_dk_players_df[\"CaptainSalary\"] = (all_dk_players_df[\"Salary\"] * 1.5).astype(int)\n\n    # Build/simulate only players with a positive external projection.\n    players_df = exclude_zero_projection_players(all_dk_players_df, \"DraftKings \" + lineup_mode)\n    players_df[\"Opponent\"] = players_df[\"Team\"].map(opponent_map).fillna(\"—\")\n    players_df[\"CaptainSalary\"] = (players_df[\"Salary\"] * 1.5).astype(int)\n'''
if old_opp in text:
    text = text.replace(old_opp, new_opp, 1)

text = text.replace('    player_display = players_df.copy()\n', '    player_display = all_dk_players_df.copy()\n', 1)

path.write_text(text, encoding="utf-8")
print("Full DraftKings player pool display checked.")
