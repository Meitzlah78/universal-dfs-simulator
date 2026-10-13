from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch anchor not found: {label}")
    text = text.replace(old, new, 1)


# Helper to show the matchups detected from the uploaded player table.
replace_once(
'''def get_contest_opponent_target(platform_key, default=MAX_SIMULATED_OPPONENTS):
''',
'''def extract_slate_games(source_df):
    """Return compact matchup labels detected from a DK/FD player table."""
    import re
    if not isinstance(source_df, pd.DataFrame) or source_df.empty:
        return []
    lookup = {str(col).strip().casefold(): col for col in source_df.columns}
    game_col = lookup.get("game info") or lookup.get("gameinfo") or lookup.get("game")
    if game_col is None:
        return []
    games = []
    for raw_value in source_df[game_col].dropna().astype(str):
        value = raw_value.strip().upper()
        match = re.search(r"\\b([A-Z]{2,3})\\s*@\\s*([A-Z]{2,3})\\b", value)
        if not match:
            continue
        label = f"{match.group(1)} @ {match.group(2)}"
        if label not in games:
            games.append(label)
    return games


def show_detected_slate_games(source_df):
    games = extract_slate_games(source_df)
    if not games:
        return
    st.write("#### Games on this slate")
    if len(games) == 1:
        st.info(games[0])
    else:
        st.caption(" • ".join(games))


def get_contest_opponent_target(platform_key, default=MAX_SIMULATED_OPPONENTS):
''',
"slate-game helpers",
)

# FanDuel: one upload provides both entry rows and the player-reference section.
replace_once(
'''    # FanDuel uses its own player upload and lineup rules. This separate path
    # keeps DraftKings controls and saved builds unchanged.
    st.write("### Upload FanDuel Salary File")
    st.caption(
        "Upload a FanDuel NFL player CSV. Player names, positions, salaries, "
        "and IDs are read from the file. FanDuel salary-file averages are ignored; "
        "the app uses matching DFF/DraftEdge projections and excludes players "
        "without a valid positive external projection."
    )
    fd_file = st.file_uploader(
        "Upload a FanDuel player CSV",
        type=["csv"],
        key="fd_salary_file"
    )

    st.write("### Contest Selector")
    fd_entry_file = st.file_uploader(
        "Upload FanDuel Contest Entry File",
        type=["csv"],
        key="fd_contest_entry_file",
        help="Upload your FanDuel contest entries CSV. It must include contest name and contest ID columns."
    )
''',
'''    # One-upload FanDuel slate setup. FanDuel entry templates include both the
    # user's contest rows and a player-reference section later in the same CSV.
    st.write("### Slate Setup")
    st.caption(
        "Upload the FanDuel entries/slate CSV once. SIMMAH reads your contests, entries, "
        "players, salaries, IDs, teams, and games from that same file."
    )
    fd_slate_file = st.file_uploader(
        "Upload FanDuel Slate / Entries CSV",
        type=["csv"],
        key="fd_slate_setup_file",
        help="Use the FanDuel CSV that contains your contest entries and player reference table."
    )
    fd_file = fd_slate_file
    fd_entry_file = fd_slate_file

    st.write("### Contest Selector")
''',
"FD one uploader",
)

# FanDuel player table may be farther down when many entries are present.
replace_once(
'''        for line_index, line in enumerate(fd_lines[:60]):
''',
'''        for line_index, line in enumerate(fd_lines[:500]):
''',
"FD player-header scan",
)

# Show FanDuel games as soon as its player table is parsed.
replace_once(
'''        fd_players["Team"] = fd_raw[fd_team_col].astype(str).str.strip().str.upper()
        fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
''',
'''        fd_players["Team"] = fd_raw[fd_team_col].astype(str).str.strip().str.upper()
        show_detected_slate_games(fd_raw)
        fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
''',
"FD games display",
)

# DraftKings: the My Contests CSV includes the salary/player table below the entries.
replace_once(
'''    st.divider()
    st.write("### DraftKings Salary CSV")
    st.caption("Upload the salary CSV downloaded from DraftKings. The player pool and salaries will be loaded from this file.")
    salary_file = st.file_uploader(
        "Upload DraftKings Salary CSV",
        type=["csv"],
        help="Upload the DraftKings salary CSV for the single game you want to build lineups for.",
        key="dk_optional_salary_file",
    )

    entry_file = st.file_uploader(
        "Upload DraftKings Contest Entry File",
        type=["csv"],
        key="dk_contest_entry_file",
        help="Upload the CSV downloaded from DraftKings My Contests. The app will identify the contests included in the file."
    )
''',
'''    st.divider()
    st.write("### Slate Setup")
    st.caption(
        "Upload the DraftKings My Contests CSV once. SIMMAH reads your contests and entries from the top "
        "and the player/salary table from the same file automatically."
    )
    dk_slate_file = st.file_uploader(
        "Upload DraftKings Slate / Entries CSV",
        type=["csv"],
        key="dk_slate_setup_file",
        help="Use the original DraftKings My Contests CSV for this slate. No separate salary upload is needed."
    )
    salary_file = dk_slate_file
    entry_file = dk_slate_file
''',
"DK one uploader",
)

# DraftKings: let one uploaded slate file contain several entered contests.
replace_once(
'''                # No contest dropdown: use the first unique contest in the uploaded entry CSV.
                # Users can upload a file containing only the contest they want to target.
                if contest_summary.empty:
                    st.warning("No usable contest rows were found in this entry CSV. Please upload the original DraftKings My Contests CSV.")
                    selected_row = pd.Series({"Contest ID": "", "Contest Name": "", "Entries": len(entry_df), "EntryFee": None})
                else:
                    selected_row = contest_summary.iloc[0]
''',
'''                if contest_summary.empty:
                    st.warning("No usable contest rows were found in this entry CSV. Please upload the original DraftKings My Contests CSV.")
                    selected_row = pd.Series({"Contest ID": "", "Contest Name": "", "Entries": len(entry_df), "EntryFee": None})
                else:
                    contest_summary["Contest Label"] = contest_summary.apply(
                        lambda row: (
                            f"{row['Contest Name']} | {int(row['Entries'])} entries | "
                            f"ID {row['Contest ID']}"
                        ),
                        axis=1,
                    )
                    selected_label = st.selectbox(
                        "Contest",
                        contest_summary["Contest Label"].tolist(),
                        key=f"dk_one_upload_contest_{lineup_mode.lower().replace(' ', '_')}",
                    )
                    selected_row = contest_summary.loc[
                        contest_summary["Contest Label"].eq(selected_label)
                    ].iloc[0]
''',
"DK contest selector",
)

# Show DK games after the salary/player table from the same file is parsed.
replace_once(
'''                loaded_players["Team"] = uploaded_df[team_col].astype(str).str.strip().str.upper()
                loaded_players["Position"] = (
''',
'''                loaded_players["Team"] = uploaded_df[team_col].astype(str).str.strip().str.upper()
                show_detected_slate_games(uploaded_df)
                loaded_players["Position"] = (
''',
"DK games display",
)

# Update the missing-file message to match the new single-upload flow.
replace_once(
'''        st.info("Upload your FanDuel salary CSV to build FanDuel lineups.")
''',
'''        st.info("Upload your FanDuel slate/entries CSV to load the slate and build lineups.")
''',
"FD missing upload message",
)

# Clearly explain when the slate loaded before DFF/DraftEdge have posted projections.
replace_once(
'''    fd_players = apply_external_projection_sources(fd_players, fd_dff_projection_file, fd_draftedge_projection_file, platform_name=("FanDuel Single Game" if lineup_mode == "Single Game" else "FanDuel Full Roster"))
    fd_players = exclude_zero_projection_players(fd_players, "FanDuel " + lineup_mode)
''',
'''    fd_players = apply_external_projection_sources(fd_players, fd_dff_projection_file, fd_draftedge_projection_file, platform_name=("FanDuel Single Game" if lineup_mode == "Single Game" else "FanDuel Full Roster"))
    fd_valid_projection_count = int(pd.to_numeric(fd_players.get("Projection"), errors="coerce").gt(0).sum())
    if fd_valid_projection_count == 0 and not fd_players.empty:
        st.warning(
            "Players loaded successfully, but DFF/DraftEdge projections are not available for this slate yet. "
            "Click REFRESH PROJECTIONS + INJURY NEWS later after projections are posted."
        )
    elif fd_valid_projection_count < len(fd_players):
        st.info(
            f"Players loaded successfully. Projections are available for {fd_valid_projection_count} of {len(fd_players)} players; "
            "players without a posted external projection will stay out of builds until a refresh finds one."
        )
    fd_players = exclude_zero_projection_players(fd_players, "FanDuel " + lineup_mode)
''',
"FD projection availability message",
)

replace_once(
'''    players_df = apply_external_projection_sources(
        players_df,
        dff_projection_file,
        draftedge_projection_file,
        platform_name=("DraftKings Showdown" if lineup_mode == "Showdown" else "DraftKings Classic"),
    )

    def internal_slate_key(frame):
''',
'''    players_df = apply_external_projection_sources(
        players_df,
        dff_projection_file,
        draftedge_projection_file,
        platform_name=("DraftKings Showdown" if lineup_mode == "Showdown" else "DraftKings Classic"),
    )
    dk_valid_projection_count = int(pd.to_numeric(players_df.get("Projection"), errors="coerce").gt(0).sum())
    if dk_valid_projection_count == 0 and not players_df.empty:
        st.warning(
            "Players loaded successfully, but DFF/DraftEdge projections are not available for this slate yet. "
            "Click REFRESH PROJECTIONS + INJURY NEWS later after projections are posted."
        )
    elif dk_valid_projection_count < len(players_df):
        st.info(
            f"Players loaded successfully. Projections are available for {dk_valid_projection_count} of {len(players_df)} players; "
            "players without a posted external projection will stay out of builds until a refresh finds one."
        )

    def internal_slate_key(frame):
''',
"DK projection availability message",
)

APP.write_text(text, encoding="utf-8")
print("Patched one-upload slate setup")