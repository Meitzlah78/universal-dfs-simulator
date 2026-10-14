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

replace_once('''        for line_index, line in enumerate(fd_lines[:60]):
''','''        for line_index, line in enumerate(fd_lines[:500]):
''',"FD player-header scan")

replace_once('''        fd_players["Team"] = fd_raw[fd_team_col].astype(str).str.strip().str.upper()
        fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
''','''        fd_players["Team"] = fd_raw[fd_team_col].astype(str).str.strip().str.upper()
        show_detected_slate_games(fd_raw)
        fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
''',"FD games display")

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
                        lambda row: (f"{row['Contest Name']} | {int(row['Entries'])} entries | ID {row['Contest ID']}"), axis=1,
                    )
                    selected_label = st.selectbox(
                        "Contest", contest_summary["Contest Label"].tolist(),
                        key=f"dk_one_upload_contest_{lineup_mode.lower().replace(' ', '_')}",
                    )
                    selected_row = contest_summary.loc[contest_summary["Contest Label"].eq(selected_label)].iloc[0]
''',
"DK contest selector",
)

replace_once('''                loaded_players["Team"] = uploaded_df[team_col].astype(str).str.strip().str.upper()
                loaded_players["Position"] = (
''','''                loaded_players["Team"] = uploaded_df[team_col].astype(str).str.strip().str.upper()
                show_detected_slate_games(uploaded_df)
                loaded_players["Position"] = (
''',"DK games display")

replace_once('''        st.info("Upload your FanDuel salary CSV to build FanDuel lineups.")
''','''        st.info("Upload your FanDuel slate/entries CSV to load the slate and build lineups.")
''',"FD missing upload message")

replace_once(
'''    fd_players = apply_external_projection_sources(fd_players, fd_dff_projection_file, fd_draftedge_projection_file, platform_name=("FanDuel Single Game" if lineup_mode == "Single Game" else "FanDuel Full Roster"))
    fd_players = exclude_zero_projection_players(fd_players, "FanDuel " + lineup_mode)
''',
'''    fd_players = apply_external_projection_sources(fd_players, fd_dff_projection_file, fd_draftedge_projection_file, platform_name=("FanDuel Single Game" if lineup_mode == "Single Game" else "FanDuel Full Roster"))
    fd_valid_projection_count = int(pd.to_numeric(fd_players.get("Projection"), errors="coerce").gt(0).sum())
    if fd_valid_projection_count == 0 and not fd_players.empty:
        st.warning("Players loaded successfully, but DFF/DraftEdge projections are not available for this slate yet. Click REFRESH PROJECTIONS + INJURY NEWS later after projections are posted.")
    elif fd_valid_projection_count < len(fd_players):
        st.info(f"Players loaded successfully. Projections are available for {fd_valid_projection_count} of {len(fd_players)} players; players without a posted external projection will stay out of builds until a refresh finds one.")
    fd_players = exclude_zero_projection_players(fd_players, "FanDuel " + lineup_mode)
''',"FD projection availability message")

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
        st.warning("Players loaded successfully, but DFF/DraftEdge projections are not available for this slate yet. Click REFRESH PROJECTIONS + INJURY NEWS later after projections are posted.")
    elif dk_valid_projection_count < len(players_df):
        st.info(f"Players loaded successfully. Projections are available for {dk_valid_projection_count} of {len(players_df)} players; players without a posted external projection will stay out of builds until a refresh finds one.")

    def internal_slate_key(frame):
''',"DK projection availability message")

# Match the visible workflow controls across paired formats. The existing pipelines
# remain intact; these buttons feed the same tested all-in-one execution path.
replace_once(
'''    with build_cols[2]:
        st.write("### Run")
        fd_run_all_clicked = st.button(
            "RUN SIM → BUILD → CONTEST SIM",
            type="primary",
            use_container_width=True,
            key="fd_run_all_" + lineup_mode.replace(" ", "_").lower(),
            help="Run all three FanDuel steps in order, with a progress bar."
        )
        fd_sim_clicked = fd_run_all_clicked
        fd_build_clicked = fd_run_all_clicked
        fd_contest_clicked = fd_run_all_clicked
''',
'''    with build_cols[2]:
        st.write("### Run")
        _fd_run_cols = st.columns(3)
        with _fd_run_cols[0]:
            fd_sim_button = st.button("SIM", type="primary", use_container_width=True, key="fd_sim_" + lineup_mode.replace(" ", "_").lower())
        with _fd_run_cols[1]:
            fd_build_button = st.button("BUILD", use_container_width=True, key="fd_build_" + lineup_mode.replace(" ", "_").lower())
        with _fd_run_cols[2]:
            fd_contest_button = st.button("CONTEST SIM", use_container_width=True, key="fd_contest_" + lineup_mode.replace(" ", "_").lower())
        fd_run_all_clicked = fd_sim_button or fd_build_button or fd_contest_button
        fd_sim_clicked = fd_run_all_clicked
        fd_build_clicked = fd_run_all_clicked
        fd_contest_clicked = fd_run_all_clicked
''',"FD paired workflow buttons")

replace_once(
'''        with build_cols[2]:
            st.write("### Run")
            classic_run_all = st.button("SIM", type="primary", use_container_width=True, key="dk_classic_run_all")
''',
'''        with build_cols[2]:
            st.write("### Run")
            _classic_run_cols = st.columns(3)
            with _classic_run_cols[0]:
                _classic_sim_button = st.button("SIM", type="primary", use_container_width=True, key="dk_classic_sim")
            with _classic_run_cols[1]:
                _classic_build_button = st.button("BUILD", use_container_width=True, key="dk_classic_build")
            with _classic_run_cols[2]:
                _classic_contest_button = st.button("CONTEST SIM", use_container_width=True, key="dk_classic_contest")
            classic_run_all = _classic_sim_button or _classic_build_button or _classic_contest_button
''',"DK Classic paired workflow buttons")

# Add the same field-sanity summary to full-roster contest comparisons without
# changing opponent construction strength.
replace_once(
'''                    st.metric("Simulated opponent lineups", f"{len(contest_field_df):,}")
                    # Field ownership is already shown in the Player Pool.
''',
'''                    st.metric("Simulated opponent lineups", f"{len(contest_field_df):,}")
                    if all(c in user_lineups.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                        _classic_sanity = pd.DataFrame([{
                            "Top 1%": round(100 * float(user_lineups["Top1"].mean()), 2),
                            "Top 5%": round(100 * float(user_lineups["Top5"].mean()), 2),
                            "Top 10%": round(100 * float(user_lineups["Top10"].mean()), 2),
                            "Cash %": round(100 * float(user_lineups["CashRate"].mean()), 2),
                        }])
                        st.write("### Field Sanity Check")
                        st.dataframe(_classic_sanity, use_container_width=True, hide_index=True)
                    # Field ownership is already shown in the Player Pool.
''',"DK Classic field sanity")

replace_once(
'''                        st.dataframe(compared, use_container_width=True, hide_index=True)
                        # Keep the contest results area consistent with DraftKings Classic and Showdown.
''',
'''                        st.dataframe(compared, use_container_width=True, hide_index=True)
                        if all(c in compared.columns for c in ["Top1", "Top5", "Top10", "CashRate"]):
                            _fd_sanity = pd.DataFrame([{
                                "Top 1%": round(100 * float(compared["Top1"].mean()), 2),
                                "Top 5%": round(100 * float(compared["Top5"].mean()), 2),
                                "Top 10%": round(100 * float(compared["Top10"].mean()), 2),
                                "Cash %": round(100 * float(compared["CashRate"].mean()), 2),
                            }])
                            st.write("### Field Sanity Check")
                            st.dataframe(_fd_sanity, use_container_width=True, hide_index=True)
                        # Keep the contest results area consistent with DraftKings Classic and Showdown.
''',"FD field sanity")

APP.write_text(text, encoding="utf-8")
print("Patched one-upload slate setup and paired workflow controls")