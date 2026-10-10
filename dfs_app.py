import itertools

import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Universal DFS Simulator",
    page_icon="🏈",
    layout="wide"
)

st.title("Universal DFS Simulator")

def build_opponent_map(source_df, team_values):
    """Map each NFL team to its opponent using matchup data when available."""
    import re

    teams = {
        str(team).strip().upper()
        for team in team_values
        if str(team).strip() and str(team).strip().lower() != "nan"
    }
    opponents = {}

    if source_df is not None:
        lookup = {str(col).strip().casefold(): col for col in source_df.columns}
        game_info_col = lookup.get("game info") or lookup.get("gameinfo")
        if game_info_col is not None:
            for game_info in source_df[game_info_col].dropna().astype(str):
                match = re.search(r"([A-Z]{2,3})\\s*@\\s*([A-Z]{2,3})", game_info.upper())
                if match:
                    away, home = match.groups()
                    opponents[away] = home
                    opponents[home] = away

    # For single-game files without a Game Info column, use the two teams present.
    if not opponents and len(teams) == 2:
        first, second = sorted(teams)
        opponents[first] = second
        opponents[second] = first

    return opponents


platform = st.selectbox(
    "DFS Site",
    ["DraftKings", "FanDuel"],
    key="dfs_platform"
)
mode_options = {
    "DraftKings": ["Showdown", "Classic"],
    "FanDuel": ["Single Game", "Full Roster"],
}
lineup_mode = st.selectbox(
    "Contest Type",
    mode_options[platform],
    key="lineup_mode_" + platform
)
st.subheader(platform + " " + lineup_mode)

if platform == "FanDuel":
    # FanDuel uses its own player upload and lineup rules. This separate path
    # keeps DraftKings controls and saved builds unchanged.
    st.write("### Upload FanDuel Salary File")
    st.caption(
        "Upload a FanDuel NFL player CSV. Player names, positions, salaries, "
        "and IDs are read from the file. If projections are missing, add a "
        "Projection or FPPG column for useful lineup rankings."
    )
    fd_file = st.file_uploader(
        "Upload a FanDuel player CSV",
        type=["csv"],
        key="fd_salary_file"
    )

    if fd_file is None:
        st.info("Upload your FanDuel salary CSV to build FanDuel lineups.")
        st.stop()

    try:
        # FanDuel exports may include preamble rows or inconsistent rows before
        # the actual player table. Find the real header row before parsing.
        import csv
        import io

        fd_text = fd_file.getvalue().decode("utf-8-sig", errors="replace")
        fd_lines = fd_text.splitlines()
        fd_header_line = None
        for line_index, line in enumerate(fd_lines[:60]):
            try:
                cells = next(csv.reader([line]))
            except Exception:
                continue
            normalized = {str(cell).strip().lower() for cell in cells}
            has_name = bool(normalized & {"nickname", "name", "name + id", "player", "player name"})
            has_salary = "salary" in normalized
            has_team = bool(normalized & {"team", "teamabbrev", "team abbrev", "team abbreviation"})
            has_position = bool(normalized & {"position", "roster position", "rosterposition"})
            if has_name and has_salary and has_team and has_position:
                fd_header_line = line_index
                break

        if fd_header_line is None:
            fd_raw = pd.read_csv(io.StringIO(fd_text), engine="python", on_bad_lines="skip")
        else:
            fd_raw = pd.read_csv(
                io.StringIO(fd_text),
                skiprows=fd_header_line,
                engine="python",
                on_bad_lines="skip"
            )
        fd_raw.columns = [str(c).strip() for c in fd_raw.columns]

        def fd_find_column(frame, choices):
            lookup = {str(c).strip().lower(): c for c in frame.columns}
            for choice in choices:
                if choice.lower() in lookup:
                    return lookup[choice.lower()]
            return None

        fd_name_col = fd_find_column(
            fd_raw, ["Nickname", "Name", "Name + ID", "Player", "Player Name"]
        )
        fd_salary_col = fd_find_column(fd_raw, ["Salary"])
        fd_team_col = fd_find_column(
            fd_raw, ["Team", "TeamAbbrev", "Team Abbrev", "Team Abbreviation"]
        )
        fd_pos_col = fd_find_column(
            fd_raw, ["Position", "Roster Position", "RosterPosition"]
        )
        fd_proj_col = fd_find_column(
            fd_raw, ["Projection", "Projected Points", "FPPG", "Fpts",
                     "AvgPointsPerGame", "Avg Points Per Game"]
        )
        fd_id_col = fd_find_column(
            fd_raw, ["Id", "ID", "Player ID", "FDP_ID", "PlayerId"]
        )

        missing_cols = []
        if fd_name_col is None:
            missing_cols.append("player name (Nickname or Name)")
        if fd_salary_col is None:
            missing_cols.append("Salary")
        if fd_team_col is None:
            missing_cols.append("Team")
        if fd_pos_col is None:
            missing_cols.append("Position")

        if missing_cols:
            st.error("Missing required columns: " + ", ".join(missing_cols))
            st.stop()

        fd_players = pd.DataFrame()
        fd_players["Name"] = fd_raw[fd_name_col].astype(str).str.strip()
        fd_players["Name"] = fd_players["Name"].str.replace(
            r"\s*\(\d+\)\s*$", "", regex=True
        )
        fd_players["Salary"] = pd.to_numeric(
            fd_raw[fd_salary_col].astype(str).str.replace(r"[$,]", "", regex=True),
            errors="coerce"
        )
        fd_players["Team"] = fd_raw[fd_team_col].astype(str).str.strip().str.upper()
        fd_opponents = build_opponent_map(fd_raw, fd_players["Team"])
        fd_players["Opponent"] = fd_players["Team"].map(fd_opponents).fillna("—")
        fd_players["Position"] = fd_raw[fd_pos_col].astype(str).str.strip().str.upper()
        fd_players["Projection"] = (
            pd.to_numeric(fd_raw[fd_proj_col], errors="coerce").fillna(0.01)
            if fd_proj_col is not None else 0.01
        )
        if fd_id_col is not None:
            fd_players["FD_ID"] = fd_raw[fd_id_col].astype(str).str.strip()

        fd_players = fd_players.dropna(subset=["Salary"])
        fd_players = fd_players[
            (fd_players["Name"] != "") &
            (fd_players["Name"].str.lower() != "nan") &
            (fd_players["Salary"] > 0)
        ].drop_duplicates(subset=["Name"], keep="first").reset_index(drop=True)

        if fd_players.empty:
            st.error("No usable players were found in that CSV.")
            st.stop()

    except Exception as exc:
        st.error(f"Could not read that FanDuel CSV: {exc}")
        st.stop()

    st.success(f"Loaded {len(fd_players)} FanDuel players.")
    if fd_proj_col is None:
        st.warning("No projection column found. All players currently have a placeholder projection of 0.01.")
    st.dataframe(
        fd_players.drop(columns=["FD_ID"], errors="ignore"),
        use_container_width=True,
        hide_index=True
    )

    fd_signature = (
        "FanDuel",
        lineup_mode,
        tuple(fd_players[["Name", "Position", "Team", "Salary", "Projection"]]
              .astype(str).itertuples(index=False, name=None))
    )
    if "fd_saved_builds" not in st.session_state:
        st.session_state["fd_saved_builds"] = {}
    fd_build_key = "fd_lineups_" + lineup_mode.replace(" ", "_").lower()
    fd_active_key = "fd_active_signature_" + lineup_mode.replace(" ", "_").lower()
    previous_fd_signature = st.session_state.get(fd_active_key)
    if previous_fd_signature != fd_signature:
        if previous_fd_signature is not None and fd_build_key in st.session_state:
            st.session_state["fd_saved_builds"][previous_fd_signature] = {
                "lineups": st.session_state[fd_build_key]
            }
        st.session_state.pop(fd_build_key, None)
        fd_saved = st.session_state["fd_saved_builds"].get(fd_signature, {})
        if "lineups" in fd_saved:
            st.session_state[fd_build_key] = fd_saved["lineups"]
        st.session_state[fd_active_key] = fd_signature

    if lineup_mode == "Single Game":
        st.caption(
            "FanDuel Single Game: 1 MVP (1.5x points and salary) plus 4 FLEX players. "
            "Salary cap: $60,000."
        )
        fd_slots = ["MVP", "FLEX1", "FLEX2", "FLEX3", "FLEX4"]
    else:
        st.caption(
            "FanDuel NFL Full Roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), D. "
            "Salary cap: $60,000."
        )
        fd_slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "D"]

    if st.button("BUILD FANDUEL LINEUPS", type="primary", key="fd_build_" + lineup_mode):
        rng = np.random.default_rng()
        pool = fd_players.copy()
        pool["Eligible"] = pool["Position"].apply(
            lambda value: set(str(value).upper().replace(" ", "").split("/"))
        )
        results = []
        seen = set()
        max_attempts = 30000

        for _ in range(max_attempts):
            chosen = {}
            used = set()
            salary = 0
            total_points = 0.0

            if lineup_mode == "Single Game":
                mvp_candidates = pool[pool["Salary"] * 1.5 <= 60000]
                if mvp_candidates.empty:
                    continue
                mvp_weights = np.maximum(mvp_candidates["Projection"].to_numpy(float), 0.01)
                mvp_weights /= mvp_weights.sum()
                mvp_row = mvp_candidates.iloc[int(rng.choice(len(mvp_candidates), p=mvp_weights))]
                mvp_name = mvp_row["Name"]
                chosen["MVP"] = mvp_name
                used.add(mvp_name)
                salary = int(float(mvp_row["Salary"]) * 1.5)
                total_points = float(mvp_row["Projection"]) * 1.5

                flex_pool = pool[~pool["Name"].isin(used)]
                for slot in ["FLEX1", "FLEX2", "FLEX3", "FLEX4"]:
                    choices = flex_pool[
                        (~flex_pool["Name"].isin(used)) &
                        ((salary + flex_pool["Salary"]) <= 60000)
                    ]
                    if choices.empty:
                        break
                    weights = np.maximum(choices["Projection"].to_numpy(float), 0.01)
                    weights /= weights.sum()
                    picked = choices.iloc[int(rng.choice(len(choices), p=weights))]
                    chosen[slot] = picked["Name"]
                    used.add(picked["Name"])
                    salary += int(picked["Salary"])
                    total_points += float(picked["Projection"])
            else:
                roster = [
                    ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
                    ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
                    ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}),
                    ("D", {"D", "DST", "DEF"})
                ]
                for slot, eligible in roster:
                    choices = pool[
                        (~pool["Name"].isin(used)) &
                        pool["Eligible"].apply(lambda positions: bool(positions & eligible)) &
                        ((pool["Salary"] + salary) <= 60000)
                    ]
                    if choices.empty:
                        break
                    weights = np.maximum(choices["Projection"].to_numpy(float), 0.01)
                    weights /= weights.sum()
                    picked = choices.iloc[int(rng.choice(len(choices), p=weights))]
                    chosen[slot] = picked["Name"]
                    used.add(picked["Name"])
                    salary += int(picked["Salary"])
                    total_points += float(picked["Projection"])

            if len(chosen) != len(fd_slots) or salary > 60000:
                continue
            lineup_key = tuple(chosen[slot] for slot in fd_slots)
            if lineup_key in seen:
                continue
            seen.add(lineup_key)
            results.append({
                **chosen,
                "Salary": salary,
                "ProjectedPoints": round(total_points, 2)
            })
            if len(results) >= 20:
                break

        if results:
            fd_results = pd.DataFrame(results).sort_values(
                "ProjectedPoints", ascending=False
            ).reset_index(drop=True)
            st.session_state[fd_build_key] = fd_results
            st.session_state["fd_saved_builds"][fd_signature] = {"lineups": fd_results}
        else:
            st.error(
                "No valid lineups found. Check player positions, salary values, "
                "and make sure the uploaded slate has enough players for this contest type."
            )

    fd_results = st.session_state.get(fd_build_key)
    if fd_results is not None:
        st.write(f"Built {len(fd_results)} FanDuel lineups.")
        st.dataframe(fd_results, use_container_width=True, hide_index=True)

        if "FD_ID" in fd_players.columns:
            fd_ids = dict(zip(fd_players["Name"], fd_players["FD_ID"].astype(str)))
            export_slots = (
                ["MVP", "FLEX", "FLEX", "FLEX", "FLEX"]
                if lineup_mode == "Single Game"
                else ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "D"]
            )
            export_data = []
            missing_ids = []
            for _, lineup in fd_results.iterrows():
                row_ids = []
                for slot in fd_slots:
                    name = lineup[slot]
                    player_id = fd_ids.get(name, "")
                    if not player_id or player_id.lower() == "nan":
                        missing_ids.append(name)
                    row_ids.append(player_id)
                export_data.append(row_ids)
            if missing_ids:
                st.warning("Some player IDs are missing, so export is unavailable.")
            else:
                export_df = pd.DataFrame(export_data, columns=export_slots)
                st.download_button(
                    "EXPORT FANDUEL CSV",
                    export_df.to_csv(index=False).encode("utf-8"),
                    file_name=("FanDuel_Single_Game_Lineups.csv" if lineup_mode == "Single Game"
                               else "FanDuel_Full_Roster_Lineups.csv"),
                    mime="text/csv",
                    key="fd_export_" + lineup_mode.replace(" ", "_").lower()
                )
        else:
            st.info("This CSV has no player ID column, so lineup export is unavailable.")

    st.stop()

# ================================
# SETTINGS
# ================================

SIMULATIONS = 10000
DISPERSION = 8.0
SALARY_CAP = 50000

# ================================
# PLAYER POOL
# ================================

players_df = pd.DataFrame([
    ["Dak Prescott", "QB", "DAL", 10400, 21.3],
    ["CeeDee Lamb", "WR", "DAL", 11800, 19.9],
    ["Javonte Williams", "RB", "DAL", 10800, 18.9],
    ["Jalon Daniels", "QB", "TB", 8600, 15.8],
    ["George Pickens", "WR", "DAL", 9400, 14.2],
    ["Bucky Irving", "RB", "TB", 8400, 12.3],
    ["Emeka Egbuka", "WR", "TB", 8200, 9.0],
    ["Ryan Flournoy", "WR", "DAL", 3800, 8.3],
    ["Jake Ferguson", "TE", "DAL", 7600, 8.0],
    ["Chris Godwin Jr.", "WR", "TB", 7200, 7.8],
    ["Cowboys", "DST", "DAL", 4800, 7.1],
    ["Cade Otton", "TE", "TB", 4400, 7.1],
    ["Kenny Gainwell", "RB", "TB", 4000, 6.6],
    ["Ted Hurst III", "WR", "TB", 2800, 5.4],
    ["Buccaneers", "DST", "TB", 3600, 4.4],
    ["Tyler Goodson", "RB", "DAL", 2600, 4.1],
    ["Tez Johnson", "WR", "TB", 2400, 3.5],
    ["KaVontae Turpin", "WR", "DAL", 1200, 1.5],
    ["Sean Tucker", "RB", "TB", 2000, 1.5],
    ["Brevyn Spann-Ford", "TE", "DAL", 1600, 1.4],
    ["Luke Schoonmaker", "TE", "DAL", 1400, 1.3],
    ["Hunter Luepke", "RB", "DAL", 1000, 0.9],
    ["Jonathan Mingo", "WR", "DAL", 1000, 0.9],
    ["Bauer Sharp", "TE", "TB", 800, 0.4],
    ["Kameron Johnson", "WR", "TB", 600, 0.4],
    ["Payne Durham", "TE", "TB", 200, 0.2],
    ["Brandon Aubrey", "K", "DAL", 5400, 8.0],
    ["Chase McLaughlin", "K", "TB", 5000, 7.0],
], columns=[
    "Name",
    "Position",
    "Team",
    "Salary",
    "Projection"
])

# ================================
# DRAFTKINGS SALARY FILE UPLOAD
# ================================

st.divider()
st.write("### Upload DraftKings Salary File")
salary_file = st.file_uploader(
    "Upload a DraftKings player CSV",
    type=["csv"],
    help="Upload the salary CSV for the slate. If you do not upload one, the sample player pool below is used."
)

entry_file = st.file_uploader(
    "Upload DraftKings Contest Entry File",
    type=["csv"],
    key="dk_contest_entry_file",
    help="Upload the CSV downloaded from DraftKings My Contests. The app will identify the contests included in the file."
)

selected_contest_id = None
selected_contest_name = None
selected_contest_entry_count = 0
selected_contest_entry_fee = None

if entry_file is not None:
    try:
        entry_file.seek(0)
        entry_df = pd.read_csv(entry_file)
        entry_df.columns = [str(c).strip() for c in entry_df.columns]
        required_entry_columns = {"Contest Name", "Contest ID"}
        if required_entry_columns.issubset(entry_df.columns):
            entry_df["Contest ID"] = entry_df["Contest ID"].astype(str).str.replace(r"\.0$", "", regex=True)
            contest_summary = (
                entry_df.groupby(["Contest ID", "Contest Name"], dropna=False)
                .agg(
                    Entries=("Entry ID", "count") if "Entry ID" in entry_df.columns else ("Contest ID", "size"),
                    EntryFee=("Entry Fee", "first") if "Entry Fee" in entry_df.columns else ("Contest ID", "size")
                )
                .reset_index()
            )
            contest_summary["Contest Label"] = contest_summary.apply(
                lambda row: f"{row['Contest Name']} | ID {row['Contest ID']} | {int(row['Entries'])} of your entries",
                axis=1
            )
            selected_label = st.selectbox(
                "Select the contest to simulate against",
                contest_summary["Contest Label"].tolist(),
                key="dk_selected_contest"
            )
            selected_row = contest_summary.loc[
                contest_summary["Contest Label"].eq(selected_label)
            ].iloc[0]
            selected_contest_id = str(selected_row["Contest ID"])
            selected_contest_name = str(selected_row["Contest Name"])
            selected_contest_entry_count = int(selected_row["Entries"])
            selected_contest_entry_fee = pd.to_numeric(
                str(selected_row["EntryFee"]).replace("$", "").replace(",", ""),
                errors="coerce"
            )
            st.session_state["selected_dk_contest"] = {
                "id": selected_contest_id,
                "name": selected_contest_name,
                "your_entries": selected_contest_entry_count,
                "entry_fee": (
                    float(selected_contest_entry_fee)
                    if pd.notna(selected_contest_entry_fee) else None
                ),
            }
            fee_text = (
                f"${float(selected_contest_entry_fee):.2f}"
                if pd.notna(selected_contest_entry_fee) else "not listed"
            )
            st.success(
                f"Selected: {selected_contest_name} | Contest ID: {selected_contest_id} | "
                f"Your entries in this file: {selected_contest_entry_count} | Entry fee: {fee_text}"
            )
            st.caption(
                "This file identifies your contest and your entries. It does not provide the full opponent field or payout table, "
                "so those details are not assumed by the simulator yet."
            )
        else:
            st.error("This CSV does not appear to be a DraftKings contest entry file. It needs Contest Name and Contest ID columns.")
    except Exception as exc:
        st.error(f"Could not read the DraftKings contest entry file: {exc}")
dff_file = st.file_uploader(
    "Upload Daily Fantasy Fuel (DFF) projections CSV",
    type=["csv"],
    key="dff_projection_file",
    help="Download projections from Daily Fantasy Fuel and upload that CSV here. DFF projections take priority over DraftEdge."
)

st.write("### Projection Controls")
st.caption("Use this button to pull the latest projections for the uploaded slate.")
refresh_clicked = st.button("🔄 REFRESH DRAFTEDGE PROJECTIONS NOW", key="refresh_draftedge", type="primary", use_container_width=True)
if "draftedge_last_updated" in st.session_state:
    st.caption("Last successful DraftEdge update: " + st.session_state["draftedge_last_updated"])
else:
    st.caption("DraftEdge projections have not been successfully refreshed in this session.")

if salary_file is not None:
    try:
        # DraftKings lineup templates have instructions before the player table.
        # Detect that format and skip those rows; ordinary salary CSVs load normally.
        salary_file.seek(0)
        first_lines = salary_file.getvalue().decode("utf-8-sig", errors="replace").splitlines()
        header_line = next(
            (i for i, line in enumerate(first_lines)
             if "Roster Position" in line and "AvgPointsPerGame" in line),
            None
        )
        is_lineup_template = header_line is not None
        is_showdown_template = False

        salary_file.seek(0)
        if is_lineup_template:
            uploaded_df = pd.read_csv(salary_file, skiprows=header_line)
            uploaded_df.columns = [str(c).strip() for c in uploaded_df.columns]
            roster_col = "Roster Position" if "Roster Position" in uploaded_df.columns else None
            # Showdown templates repeat each player as CPT and FLEX. Keep FLEX
            # only for that format; Classic templates must keep all player rows.
            if roster_col:
                roster_values = set(
                    uploaded_df[roster_col].astype(str).str.upper().str.strip()
                )
                is_showdown_template = "CPT" in roster_values
                if is_showdown_template:
                    uploaded_df = uploaded_df[
                        uploaded_df[roster_col].astype(str).str.upper().str.strip().eq("FLEX")
                    ].copy()
        else:
            uploaded_df = pd.read_csv(salary_file)
            uploaded_df.columns = [str(c).strip() for c in uploaded_df.columns]

        def find_column(frame, choices):
            lookup = {str(c).strip().lower(): c for c in frame.columns}
            for choice in choices:
                if choice.lower() in lookup:
                    return lookup[choice.lower()]
            return None

        name_col = find_column(uploaded_df, ["Name", "Name + ID", "Player", "Player Name"])
        salary_col = find_column(uploaded_df, ["Salary"])
        team_col = find_column(uploaded_df, ["TeamAbbrev", "Team", "Team Abbrev", "Team Abbreviation"])
        position_col = find_column(uploaded_df, ["Position", "Roster Position", "RosterPosition"])
        projection_col = find_column(uploaded_df, ["Projection", "Projected Points", "Fpts", "FPPG", "AvgPointsPerGame", "Avg Points Per Game"])
        id_col = find_column(uploaded_df, ["ID", "Player ID", "DK ID"])

        missing = []
        if name_col is None:
            missing.append("player name (Name or Name + ID)")
        if salary_col is None:
            missing.append("Salary")
        if team_col is None:
            missing.append("team (TeamAbbrev or Team)")

        if missing:
            st.error("Could not load the salary file. Missing columns: " + ", ".join(missing) + ". The sample player pool is still being used.")
        else:
            loaded_players = pd.DataFrame()
            loaded_players["Name"] = uploaded_df[name_col].astype(str).str.strip()
            loaded_players["Name"] = loaded_players["Name"].str.replace(r"\s*\(\d+\)\s*$", "", regex=True)
            loaded_players["Salary"] = pd.to_numeric(
                uploaded_df[salary_col].astype(str).str.replace(r"[$,]", "", regex=True),
                errors="coerce"
            )
            loaded_players["Team"] = uploaded_df[team_col].astype(str).str.strip().str.upper()
            loaded_players["Position"] = (
                uploaded_df[position_col].astype(str).str.strip()
                if position_col is not None else "FLEX"
            )
            loaded_players["Projection"] = (
                pd.to_numeric(uploaded_df[projection_col], errors="coerce")
                if projection_col is not None else np.nan
            )
            if id_col is not None:
                loaded_players["DK_ID"] = uploaded_df[id_col].astype(str).str.strip()
            # Keep missing projections blank until the DFF refresh below has a chance to fill them.
            loaded_players["Projection"] = pd.to_numeric(
                loaded_players["Projection"], errors="coerce"
            )
            loaded_players = loaded_players.dropna(subset=["Name", "Salary"])
            loaded_players = loaded_players[
                (loaded_players["Name"] != "") &
                (loaded_players["Name"].str.lower() != "nan") &
                (loaded_players["Salary"] > 0)
            ].drop_duplicates(subset=["Name"], keep="first")

            if loaded_players.empty:
                st.error("No usable players were found in that file. The sample player pool is still being used.")
            else:
                players_df = loaded_players.reset_index(drop=True)

                # Projection priority: DFF first, DraftEdge fills gaps, salary CSV last.
                import hashlib
                import re
                import requests
                from io import StringIO
                from html import unescape
                from datetime import datetime

                def normalize_projection_name(name):
                    value = str(name).casefold().strip()
                    value = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", value)
                    return re.sub(r"[^a-z0-9]", "", value)

                dff_projections = {}
                dff_error = None
                dff_source_label = "automatic DFF download"

                # An uploaded DFF CSV overrides the automatic download.
                dff_df = None
                if dff_file is not None:
                    try:
                        dff_file.seek(0)
                        dff_df = pd.read_csv(dff_file)
                        dff_source_label = "uploaded DFF CSV"
                    except Exception as exc:
                        dff_error = "Could not read uploaded DFF CSV: " + str(exc)

                # Otherwise, download the public DraftKings NFL projections CSV from DFF.
                if dff_df is None and dff_file is None:
                    try:
                        from html.parser import HTMLParser
                        from urllib.parse import urljoin

                        dff_page_url = "https://www.dailyfantasyfuel.com/nfl/projections/"
                        dff_page_response = requests.get(
                            dff_page_url,
                            timeout=20,
                            headers={"User-Agent": "Mozilla/5.0 UniversalDFS-Simulator"}
                        )
                        dff_page_response.raise_for_status()

                        class DFFDownloadLinkParser(HTMLParser):
                            def __init__(self):
                                super().__init__()
                                self.links = []
                                self._href = None
                                self._text = []

                            def handle_starttag(self, tag, attrs):
                                if tag.lower() == "a":
                                    attrs_map = dict(attrs)
                                    self._href = attrs_map.get("href")
                                    self._text = []

                            def handle_data(self, data):
                                if self._href is not None:
                                    self._text.append(data)

                            def handle_endtag(self, tag):
                                if tag.lower() == "a" and self._href is not None:
                                    label = " ".join(self._text).strip().lower()
                                    href = self._href
                                    if (
                                        "csv" in href.lower()
                                        or "download" in href.lower()
                                        or "download projections" in label
                                        or ("projection" in label and "csv" in label)
                                    ):
                                        self.links.append(urljoin(dff_page_url, href))
                                    self._href = None
                                    self._text = []

                        dff_link_parser = DFFDownloadLinkParser()
                        dff_link_parser.feed(dff_page_response.text)
                        dff_csv_url = next(
                            (url for url in dff_link_parser.links if "csv" in url.lower()),
                            dff_link_parser.links[0] if dff_link_parser.links else None
                        )
                        if not dff_csv_url:
                            raise ValueError(
                                "DFF's CSV download link was not found on its projections page."
                            )

                        dff_csv_response = requests.get(
                            dff_csv_url,
                            timeout=20,
                            headers={"User-Agent": "Mozilla/5.0 UniversalDFS-Simulator"}
                        )
                        dff_csv_response.raise_for_status()
                        if not dff_csv_response.text.strip() or "<html" in dff_csv_response.text[:500].lower():
                            raise ValueError(
                                "DFF returned a webpage instead of a projections CSV."
                            )
                        dff_df = pd.read_csv(StringIO(dff_csv_response.text))
                    except Exception as exc:
                        dff_error = "Automatic DFF download failed: " + str(exc)

                if dff_df is not None:
                    try:
                        dff_df.columns = [str(c).strip() for c in dff_df.columns]
                        dff_name_col = find_column(
                            dff_df, ["Name", "Player", "Player Name", "Nickname", "Player Name + ID"]
                        )
                        dff_proj_col = find_column(
                            dff_df, [
                                "Projection", "Projected Points", "Proj", "FPTS",
                                "Fantasy Points", "DK Points", "Points", "Fpts",
                                "FPTS Proj", "FP Projection", "Proj. FPTS"
                            ]
                        )
                        if dff_name_col is None or dff_proj_col is None:
                            raise ValueError(
                                "The downloaded DFF CSV did not contain recognizable player-name and projection columns. "
                                "Columns found: " + ", ".join(map(str, dff_df.columns))
                            )
                        dff_df["_projection"] = pd.to_numeric(
                            dff_df[dff_proj_col].astype(str).str.replace(",", "", regex=False),
                            errors="coerce"
                        )
                        for _, dff_row in dff_df.iterrows():
                            dff_name = str(dff_row[dff_name_col]).strip()
                            dff_value = dff_row["_projection"]
                            if dff_name and dff_name.lower() != "nan" and pd.notna(dff_value):
                                dff_projections[normalize_projection_name(dff_name)] = float(dff_value)
                        if not dff_projections:
                            raise ValueError("No usable player projections were found in the DFF data.")
                    except Exception as exc:
                        dff_error = "Could not read DFF projections: " + str(exc)
                        dff_projections = {}

                slate_signature = hashlib.sha256(salary_file.getvalue()).hexdigest()
                cache_key = "draftedge_cache_" + slate_signature
                refresh_needed = (
                    refresh_clicked
                    or st.session_state.get("draftedge_active_slate") != slate_signature
                    or cache_key not in st.session_state
                )
                draftedge_error = None
                if refresh_needed:
                    fresh_cache = {"projections": {}, "updated_at": None, "error": None, "draftedge_names": [], "parsed_rows": 0}
                    try:
                        game_info_col = find_column(uploaded_df, ["Game Info", "GameInfo"])
                        game_info_values = (
                            uploaded_df[game_info_col].dropna().astype(str).tolist()
                            if game_info_col is not None else []
                        )
                        game_match = None
                        for game_info in game_info_values:
                            game_match = re.search(
                                r"([A-Z]{2,3})\s*@\s*([A-Z]{2,3}).*?(\d{1,2}/\d{1,2}/\d{4})",
                                game_info.upper()
                            )
                            if game_match:
                                break

                        team_slug = {
                            "ARI": "ari", "ATL": "atl", "BAL": "bal", "BUF": "buf",
                            "CAR": "car", "CHI": "chi", "CIN": "cin", "CLE": "cle",
                            "DAL": "dal", "DEN": "den", "DET": "det", "GB": "gb",
                            "HOU": "hou", "IND": "ind", "JAX": "jax", "KC": "kc",
                            "LV": "lv", "LAC": "lac", "LAR": "la", "MIA": "mia",
                            "MIN": "min", "NE": "ne", "NO": "no", "NYG": "nyg",
                            "NYJ": "nyj", "PHI": "phi", "PIT": "pit", "SEA": "sea",
                            "SF": "sf", "TB": "tb", "TEN": "ten", "WAS": "was",
                            "WSH": "was"
                        }
                        if not game_match:
                            raise ValueError("Could not find matchup/date in the salary CSV's Game Info column.")
                        away, home, date_text = game_match.groups()
                        if away not in team_slug or home not in team_slug:
                            raise ValueError(f"DraftEdge URL mapping is missing for {away} or {home}.")
                        game_date = pd.to_datetime(date_text, format="%m/%d/%Y")
                        draftedge_url = (
                            f"https://draftedge.com/nfl/game/"
                            f"{team_slug[away]}-{team_slug[home]}-{game_date:%Y-%m-%d}/"
                        )
                        de_response = requests.get(
                            draftedge_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20
                        )
                        de_response.raise_for_status()
                        # Parse HTML with Python's built-in parser; lxml is not required.
                        from html.parser import HTMLParser

                        class DraftEdgeTableParser(HTMLParser):
                            def __init__(self):
                                super().__init__()
                                self.tables = []
                                self.table_depth = 0
                                self.in_row = False
                                self.in_cell = False
                                self.current_table = []
                                self.current_row = []
                                self.current_cell = []

                            def handle_starttag(self, tag, attrs):
                                if tag == "table":
                                    self.table_depth += 1
                                    if self.table_depth == 1:
                                        self.current_table = []
                                elif self.table_depth == 1 and tag == "tr":
                                    self.in_row = True
                                    self.current_row = []
                                elif self.table_depth == 1 and self.in_row and tag in ("td", "th"):
                                    self.in_cell = True
                                    self.current_cell = []

                            def handle_data(self, data):
                                if self.table_depth == 1 and self.in_cell:
                                    self.current_cell.append(data)

                            def handle_endtag(self, tag):
                                if self.table_depth == 1 and self.in_cell and tag in ("td", "th"):
                                    self.current_row.append(re.sub(r"\\s+", " ", "".join(self.current_cell)).strip())
                                    self.in_cell = False
                                elif self.table_depth == 1 and self.in_row and tag == "tr":
                                    if self.current_row:
                                        self.current_table.append(self.current_row)
                                    self.in_row = False
                                elif tag == "table" and self.table_depth > 0:
                                    if self.table_depth == 1 and self.current_table:
                                        self.tables.append(self.current_table)
                                    self.table_depth -= 1

                        table_parser = DraftEdgeTableParser()
                        table_parser.feed(de_response.text)
                        de_records = []
                        for raw_table in table_parser.tables:
                            header_index = next(
                                (i for i, row in enumerate(raw_table)
                                 if {"team", "player", "proj"}.issubset(
                                     {cell.strip().casefold() for cell in row}
                                 )),
                                None
                            )
                            if header_index is None:
                                continue
                            headers = [cell.strip() for cell in raw_table[header_index]]
                            header_lookup = {name.casefold(): i for i, name in enumerate(headers)}
                            required_index = max(
                                header_lookup["team"], header_lookup["player"], header_lookup["proj"]
                            )
                            for row in raw_table[header_index + 1:]:
                                if len(row) <= required_index:
                                    continue
                                de_records.append({
                                    "Team": row[header_lookup["team"]],
                                    "Player": row[header_lookup["player"]],
                                    "Proj": row[header_lookup["proj"]]
                                })
                        if not de_records:
                            raise ValueError("DraftEdge page did not contain the expected Team/Player/Proj table.")
                        de_table = pd.DataFrame(de_records)
                        fresh_cache["parsed_rows"] = int(len(de_table))

                        de_table["Player"] = de_table["Player"].astype(str).map(
                            lambda name: re.sub(r"\s+", " ", unescape(name)).strip()
                        )
                        de_table["Proj"] = pd.to_numeric(
                            de_table["Proj"].astype(str).str.replace(",", "", regex=False),
                            errors="coerce"
                        )

                        def normalize_player_name(name):
                            value = unescape(str(name)).casefold().strip()
                            value = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", value)
                            return re.sub(r"[^a-z0-9]", "", value)

                        for _, row in de_table.iterrows():
                            player_name = str(row["Player"]).strip()
                            projection_value = row["Proj"]
                            if player_name and pd.notna(projection_value) and projection_value >= 0:
                                fresh_cache["projections"][normalize_player_name(player_name)] = float(projection_value)

                        fresh_cache["draftedge_names"] = sorted(
                            str(name) for name in de_table.loc[de_table["Proj"].notna(), "Player"].tolist()
                        )
                        matched_count = sum(
                            normalize_player_name(name) in fresh_cache["projections"]
                            for name in players_df["Name"]
                        )
                        if matched_count == 0:
                            raise ValueError(f"No player names matched. URL checked: {draftedge_url}")

                        fresh_cache["updated_at"] = datetime.now(__import__("zoneinfo").ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M:%S %p ET")
                    except Exception as exc:
                        fresh_cache["error"] = str(exc)

                    st.session_state[cache_key] = fresh_cache
                    st.session_state["draftedge_active_slate"] = slate_signature

                active_cache = st.session_state.get(cache_key, {"projections": {}, "updated_at": None, "error": None})
                draftedge_projections = active_cache.get("projections", {})
                dff_matched = players_df["Name"].map(
                    lambda name: dff_projections.get(normalize_projection_name(name))
                )
                dff_found = dff_matched.notna()
                if dff_found.any():
                    players_df.loc[dff_found, "Projection"] = dff_matched.loc[dff_found].astype(float)

                draftedge_matched = players_df["Name"].map(
                    lambda name: draftedge_projections.get(normalize_projection_name(name))
                )
                draftedge_found = draftedge_matched.notna() & ~dff_found
                if draftedge_found.any():
                    players_df.loc[draftedge_found, "Projection"] = draftedge_matched.loc[draftedge_found].astype(float)

                players_df["ProjectionSource"] = "Salary CSV"
                players_df.loc[draftedge_found, "ProjectionSource"] = "DraftEdge"
                players_df.loc[dff_found, "ProjectionSource"] = "DFF"
                found = dff_found | draftedge_found
                draftedge_count = int(draftedge_found.sum())
                dff_count = int(dff_found.sum())
                draftedge_error = active_cache.get("error")

                if dff_file is not None:
                    if dff_error:
                        st.error("Could not read the DFF projections file: " + dff_error)
                    else:
                        st.success(f"DFF projections matched for {dff_count} players (first choice).")
                if active_cache.get("updated_at"):
                    st.session_state["draftedge_last_updated"] = active_cache["updated_at"]
                    st.success(f"DraftEdge projections filled gaps for {draftedge_count} players.")
                elif draftedge_error:
                    st.error("DraftEdge refresh failed. Last successful update time has not changed.")
                    st.caption("Refresh detail: " + str(draftedge_error))
                else:
                    st.warning("DraftEdge projections are not available yet. Click REFRESH PROJECTIONS to try again.")


                st.success(f"Loaded {len(players_df)} players from the salary file.")
                if dff_count + draftedge_count:
                    st.success(f"Applied projections to {dff_count + draftedge_count} players: DFF first, then DraftEdge.")
                else:
                    st.warning("No DFF or DraftEdge projections matched. Check the uploaded files and matchup/date before building lineups.")
                    if draftedge_error:
                        st.caption(f"DraftEdge refresh detail: {draftedge_error}")
                if is_showdown_template:
                    st.info("DraftKings Showdown template detected. FLEX rows are used for player salaries; CPT rows are ignored to avoid duplicate players.")
                elif is_lineup_template:
                    st.info("Lineup template detected. Player rows were kept without applying Showdown-only filtering.")
                st.caption("Check the player names, teams, salaries, and projections before building lineups.")
                with st.expander("DraftEdge matching details"):
                    st.write(f"DFF projections loaded: {len(dff_projections)}")
                    st.write(f"DFF players matched: {dff_count}")
                    st.write(f"DraftEdge player rows parsed: {active_cache.get('parsed_rows', 'unknown')}")
                    st.write(f"Usable DraftEdge projections: {len(draftedge_projections)}")
                    st.write(f"DraftEdge players used after DFF priority: {draftedge_count}")
                    unmatched_names = players_df.loc[~found, "Name"].astype(str).tolist()
                    st.write("Salary-file players not matched:")
                    st.write(", ".join(unmatched_names) if unmatched_names else "All players matched.")
                    st.write("Names found on DraftEdge:")
                    draftedge_names = active_cache.get("draftedge_names", [])
                    st.write(", ".join(draftedge_names) if draftedge_names else "No diagnostic names saved. Click Refresh DraftEdge Projections.")
    except Exception as exc:
        st.error(f"Could not read that CSV: {exc}. The sample player pool is still being used.")

# Infer the opposing team from the teams present in the uploaded slate.
# Never run the simulator with fake 0.01 projections. If a source did not provide
# projections, stop and tell the user instead of generating misleading lineups.
if "ProjectionSource" not in players_df.columns:
    players_df["ProjectionSource"] = "Salary CSV"
players_df["Projection"] = pd.to_numeric(players_df["Projection"], errors="coerce")
missing_projection_count = int(players_df["Projection"].isna().sum())
if missing_projection_count:
    st.warning(
        f"{missing_projection_count} players still have no valid projection. "
        "Upload a CSV with projections or wait until DraftEdge projections are available for this slate before building lineups."
    )
    players_df["Projection"] = players_df["Projection"].fillna(0.0)

st.caption("Projection source counts: " + str(players_df["ProjectionSource"].value_counts().to_dict()))

opponent_source = uploaded_df if "uploaded_df" in locals() else None
opponent_map = build_opponent_map(opponent_source, players_df["Team"])
players_df["Opponent"] = players_df["Team"].map(opponent_map).fillna("—")

players_df["CaptainSalary"] = (
    players_df["Salary"] * 1.5
).astype(int)

# Save results by player pool instead of deleting them when the slate changes.
# This lets a user return to a previously loaded slate and recover its last build.
slate_signature = tuple(
    players_df[["Name", "Team", "Salary", "Projection"]]
    .astype(str)
    .itertuples(index=False, name=None)
)
BUILD_STATE_KEYS = [
    "simulation_df", "simulations_ready", "contest_field_df",
    "contest_field_count", "contest_field_ready", "candidates_df",
    "candidates_ready", "contest_results_df", "portfolio_df",
    "portfolio_count_used", "portfolio_metric_used",
    "final_lineups", "dk_player_ids",
    "classic_lineups", "classic_pool_signature"
]
if "saved_builds_by_slate" not in st.session_state:
    st.session_state["saved_builds_by_slate"] = {}

previous_signature = st.session_state.get("active_slate_signature")
if previous_signature is not None and previous_signature != slate_signature:
    st.session_state["saved_builds_by_slate"][previous_signature] = {
        key: st.session_state[key]
        for key in BUILD_STATE_KEYS
        if key in st.session_state
    }
    for key in BUILD_STATE_KEYS:
        st.session_state.pop(key, None)

if previous_signature != slate_signature:
    previous_build = st.session_state["saved_builds_by_slate"].get(slate_signature, {})
    for key, value in previous_build.items():
        st.session_state[key] = value
    st.session_state["active_slate_signature"] = slate_signature

# ================================
# SIMULATION
# ================================

def run_game_simulations(players_df):
    rng = np.random.default_rng(42)

    means = np.maximum(
        players_df["Projection"].to_numpy(dtype=float),
        0.01
    )

    n = float(DISPERSION)
    p = n / (n + means)

    sims = rng.negative_binomial(
        n=n,
        p=p,
        size=(SIMULATIONS, len(players_df))
    ).astype(float)

    sim_means = sims.mean(axis=0)

    for i in range(len(means)):
        if sim_means[i] > 0:
            sims[:, i] *= means[i] / sim_means[i]

    return pd.DataFrame(
        sims,
        columns=players_df["Name"].tolist()
    )

# ================================
# PLAYER DISPLAY
# ================================

st.divider()
st.write("### Player Pool")

player_display = players_df.copy()

if "simulation_df" in st.session_state:
    simulation_df = st.session_state["simulation_df"]

    player_display["SimMean"] = simulation_df.mean(axis=0).values
    player_display["SimP10"] = simulation_df.quantile(0.10, axis=0).values
    player_display["SimP25"] = simulation_df.quantile(0.25, axis=0).values
    player_display["SimP50"] = simulation_df.quantile(0.50, axis=0).values
    player_display["SimP75"] = simulation_df.quantile(0.75, axis=0).values
    player_display["SimP90"] = simulation_df.quantile(0.90, axis=0).values
    player_display["SimP95"] = simulation_df.quantile(0.95, axis=0).values
    player_display["SimP99"] = simulation_df.quantile(0.99, axis=0).values
else:
    for column in [
        "SimMean",
        "SimP10",
        "SimP25",
        "SimP50",
        "SimP75",
        "SimP90",
        "SimP95",
        "SimP99"
    ]:
        player_display[column] = np.nan

# Show editable player settings in their own block, separate from player stats.
existing_control_values = st.session_state.get("control_values")
if existing_control_values is not None:
    existing_control_values = existing_control_values.drop_duplicates("Name").set_index("Name")

control_display = players_df[["Name", "Position", "Team", "Opponent"]].copy()
for setting, default in [
    ("Lock", False), ("Fade", False),
    ("Min Exposure %", 0), ("Max Exposure %", 100),
    ("Captain Min %", 0), ("Captain Max %", 100)
]:
    if existing_control_values is not None and setting in existing_control_values.columns:
        control_display[setting] = control_display["Name"].map(existing_control_values[setting]).fillna(default)
    else:
        control_display[setting] = default

st.write("### Player Controls")
st.caption("Change these settings directly for each player. Lock includes a player, Fade excludes a player, and exposure values set lineup percentages.")
edited_player_controls = st.data_editor(
    control_display,
    use_container_width=True,
    hide_index=True,
    disabled=["Name", "Position", "Team", "Opponent"],
    column_config={
        "Lock": st.column_config.CheckboxColumn("Lock", help="Force this player into lineup builds."),
        "Fade": st.column_config.CheckboxColumn("Fade", help="Keep this player out of lineup builds."),
        "Min Exposure %": st.column_config.NumberColumn("Min Exp %", min_value=0, max_value=100, step=5, format="%d%%"),
        "Max Exposure %": st.column_config.NumberColumn("Max Exp %", min_value=0, max_value=100, step=5, format="%d%%"),
        "Captain Min %": st.column_config.NumberColumn("CPT Min %", min_value=0, max_value=100, step=5, format="%d%%"),
        "Captain Max %": st.column_config.NumberColumn("CPT Max %", min_value=0, max_value=100, step=5, format="%d%%"),
    },
    key="player_controls_editor"
)

# Keep the player stats table read-only; settings are changed in the block above.
player_display = player_display[
    [c for c in player_display.columns if c not in [
        "Lock", "Fade", "Min Exposure %", "Max Exposure %",
        "Captain Min %", "Captain Max %"
    ]]
]
st.write("### Player Pool")
st.dataframe(player_display, use_container_width=True, hide_index=True)

# Keep the Lock/Fade selections from the Player Pool editor and preserve
# the existing exposure controls internally at their saved/default values.
existing_controls = st.session_state.get("control_values")
if existing_controls is not None:
    previous_by_name = existing_controls.drop_duplicates("Name").set_index("Name")
    control_values = players_df[["Name", "Position", "Team", "Opponent"]].copy()
    for setting, default in [
        ("Lock", False), ("Fade", False),
        ("Min Exposure %", 0), ("Max Exposure %", 100),
        ("Captain Min %", 0), ("Captain Max %", 100)
    ]:
        if setting in previous_by_name.columns:
            control_values[setting] = control_values["Name"].map(previous_by_name[setting]).fillna(default)
        else:
            control_values[setting] = default
else:
    control_values = players_df[["Name", "Position", "Team", "Opponent"]].copy()
    control_values["Lock"] = False
    control_values["Fade"] = False
    control_values["Min Exposure %"] = 0
    control_values["Max Exposure %"] = 100
    control_values["Captain Min %"] = 0
    control_values["Captain Max %"] = 100

editor_controls = edited_player_controls.set_index("Name")
for setting in [
    "Lock", "Fade", "Min Exposure %", "Max Exposure %",
    "Captain Min %", "Captain Max %"
]:
    control_values[setting] = control_values["Name"].map(
        editor_controls[setting]
    ).fillna(control_values[setting])
control_values["Lock"] = control_values["Lock"].astype(bool)
control_values["Fade"] = control_values["Fade"].astype(bool)
for setting in ["Min Exposure %", "Max Exposure %", "Captain Min %", "Captain Max %"]:
    control_values[setting] = pd.to_numeric(control_values[setting], errors="coerce").fillna(
        0 if "Min" in setting else 100
    ).clip(0, 100)
st.session_state["control_values"] = control_values
edited_controls = control_values.copy()
control_map = edited_controls.set_index("Name").to_dict("index")
available_players = [
    p for p in players_df["Name"]
    if p in control_map and not control_map[p]["Fade"]
]

# ============================================
# SALARY MAPS
# ============================================

salary_map = dict(zip(
    players_df["Name"],
    players_df["Salary"]
))

captain_salary_map = dict(zip(
    players_df["Name"],
    players_df["CaptainSalary"]
))

# SIMULATION VALUES
# ============================================

player_sim = {}

if "simulation_df" in st.session_state:
    simulation_df = st.session_state["simulation_df"]

    for player in players_df["Name"]:
        if player in simulation_df.columns:
            values = simulation_df[player]
            player_sim[player] = {
                "Mean": values.mean(),
                "P95": values.quantile(0.95),
                "P99": values.quantile(0.99)
            }

# Safe fallback so the page can render before the first simulation.
for _, player_row in players_df.iterrows():
    player = player_row["Name"]
    if player not in player_sim:
        projection = max(float(player_row["Projection"]), 0.01)
        player_sim[player] = {
            "Mean": projection,
            "P95": projection * 1.8,
            "P99": projection * 2.3
        }

# ============================================
# DRAFTKINGS CLASSIC BUILDER
# ============================================

if platform == "DraftKings" and lineup_mode == "Classic":
    st.write("### DraftKings Classic Lineups")
    st.caption(
        "Classic roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), DST. "
        "Salary cap: $50,000."
    )

    def classic_positions(value):
        raw = str(value).upper().replace(" ", "")
        return set(raw.split("/"))

    classic_pool = players_df.copy()
    classic_pool["Eligible"] = classic_pool["Position"].apply(classic_positions)
    classic_pool = classic_pool[
        classic_pool["Name"].isin(available_players)
        & (classic_pool["Salary"] > 0)
    ].copy()

    roster_slots = [
        ("QB", {"QB"}), ("RB1", {"RB"}), ("RB2", {"RB"}),
        ("WR1", {"WR"}), ("WR2", {"WR"}), ("WR3", {"WR"}),
        ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}), ("DST", {"DST"})
    ]

    if st.button("BUILD CLASSIC LINEUPS", type="primary"):
        rng = np.random.default_rng()
        rankings = {}
        for _, row in classic_pool.iterrows():
            player = row["Name"]
            rankings[player] = (
                player_sim.get(player, {}).get("P95", row["Projection"]) * 0.50
                + player_sim.get(player, {}).get("P99", row["Projection"] * 2.3) * 0.25
                + player_sim.get(player, {}).get("Mean", row["Projection"]) * 0.25
            )

        # Use the best projected players while keeping enough depth for each slot.
        classic_locked_players = [
            name for name in available_players
            if control_map.get(name, {}).get("Lock", False)
        ]
        ranked_names = list(dict.fromkeys(
            sorted(rankings, key=rankings.get, reverse=True)[:60]
            + classic_locked_players
        ))
        classic_pool = classic_pool[classic_pool["Name"].isin(ranked_names)].copy()
        player_rows = classic_pool.set_index("Name").to_dict("index")
        candidate_lineups = []
        seen = set()
        max_attempts = 50000

        for attempt in range(max_attempts):
            chosen = {}
            used = set()
            salary = 0
            slots = list(roster_slots)
            # Fill the most restrictive positions first; FLEX is last.
            for slot, eligible in slots:
                choices = [
                    name for name in ranked_names
                    if name in player_rows
                    and name not in used
                    and player_rows[name]["Eligible"] & eligible
                    and salary + float(player_rows[name]["Salary"]) <= 50000
                ]
                if not choices:
                    break
                weights = np.array([
                    max(rankings.get(name, 0.01), 0.01) for name in choices
                ], dtype=float)
                weights /= weights.sum()
                # Mix projection-weighted choices with random choices for lineup variety.
                if rng.random() < 0.25:
                    picked = str(rng.choice(choices))
                else:
                    picked = str(rng.choice(choices, p=weights))
                chosen[slot] = picked
                used.add(picked)
                salary += int(player_rows[picked]["Salary"])

            if len(chosen) != len(roster_slots) or salary > 50000:
                continue
            if not all(name in chosen.values() for name in classic_locked_players):
                continue

            key = tuple(chosen[slot] for slot, _ in roster_slots)
            if key in seen:
                continue
            seen.add(key)
            projected_points = sum(
                float(player_sim.get(name, {}).get("Mean", player_rows[name]["Projection"]))
                for name in chosen.values()
            )
            candidate_lineups.append({
                **chosen,
                "Salary": salary,
                "ProjectedPoints": projected_points,
                "Score": sum(rankings.get(name, 0.01) for name in chosen.values())
            })
            if len(candidate_lineups) >= 20:
                break

        if not candidate_lineups:
            st.error(
                "No valid Classic lineups found. Check player positions, salaries, "
                "locks, fades, and the uploaded salary file."
            )
        else:
            classic_results = pd.DataFrame(candidate_lineups).sort_values(
                "Score", ascending=False
            ).reset_index(drop=True)
            st.session_state["classic_lineups"] = classic_results
            st.session_state["classic_pool_signature"] = slate_signature

    classic_results = st.session_state.get("classic_lineups")
    if classic_results is not None:
        st.write(f"Built {len(classic_results)} valid Classic lineups.")
        st.dataframe(
            classic_results.drop(columns=["Score"], errors="ignore"),
            use_container_width=True,
            hide_index=True
        )

        id_column = "DK_ID" if "DK_ID" in classic_pool.columns else None
        if id_column:
            ids = dict(zip(classic_pool["Name"], classic_pool[id_column].astype(str)))
            export_slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
            export_data = []
            missing = []
            for _, lineup in classic_results.iterrows():
                row_ids = []
                for slot in export_slots:
                    player_name = lineup[slot]
                    player_id = ids.get(player_name, "")
                    if not player_id or player_id.lower() == "nan":
                        missing.append(player_name)
                    row_ids.append(player_id)
                export_data.append(row_ids)
            if missing:
                st.warning("Some player IDs are missing. Upload the DraftKings lineup template to enable export.")
            else:
                # DraftKings upload templates use repeated roster-slot names.
                dk_upload_columns = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
                export_df = pd.DataFrame(export_data, columns=dk_upload_columns)
                st.download_button(
                    "EXPORT DRAFTKINGS CLASSIC CSV",
                    export_df.to_csv(index=False).encode("utf-8"),
                    file_name="DraftKings_Classic_Lineups.csv",
                    mime="text/csv"
                )
        else:
            st.info("Upload a DraftKings salary/template CSV containing player IDs to enable lineup export.")

    st.stop()


# ============================================
# BUILD LINEUPS
# ============================================

simulate_clicked = st.button(
    "SIM",
    type="primary",
    use_container_width=False
)

if simulate_clicked:
    with st.spinner("Running 10,000 game simulations..."):
        simulation_df = run_game_simulations(players_df)

    st.session_state["simulation_df"] = simulation_df
    st.session_state["simulations_ready"] = True

    st.success("10,000 game simulations completed.")

build_clicked = st.button(
    "BUILD",
    type="primary",
    use_container_width=False
)

contest_sim_clicked = st.button(
    "CONTEST SIM",
    type="primary",
    use_container_width=False
)

if contest_sim_clicked:
    contest_field = []
    rng = np.random.default_rng(123)

    if len(available_players) < 6:
        st.error("At least 6 non-faded players are required for Contest Sim.")
    elif "simulation_df" in st.session_state:
        simulation_df = st.session_state["simulation_df"]

        player_weights = simulation_df.mean(axis=0).reindex(
            available_players
        ).clip(lower=0.01)

        player_weights = player_weights / player_weights.sum()

        attempts = 0

        while len(contest_field) < 10000 and attempts < 200000:
            attempts += 1

            selected = rng.choice(
                available_players,
                size=6,
                replace=False,
                p=player_weights.to_numpy()
            )

            captain = selected[
                np.argmax([
                    simulation_df[p].mean()
                    for p in selected
                ])
            ]

            flex = [p for p in selected if p != captain]

            total_salary = (
                captain_salary_map[captain]
                + sum(salary_map[p] for p in flex)
            )

            if total_salary > SALARY_CAP:
                continue

            lineup_teams = set(
                players_df.loc[
                    players_df["Name"].isin(selected),
                    "Team"
                ]
            )

            if len(lineup_teams) < 2:
                continue

            contest_field.append({
                "Captain": captain,
                "Flex1": flex[0],
                "Flex2": flex[1],
                "Flex3": flex[2],
                "Flex4": flex[3],
                "Flex5": flex[4],
                "Salary": total_salary
            })

        contest_field_df = pd.DataFrame(contest_field)

        st.session_state["contest_field_df"] = contest_field_df
        st.session_state["contest_field_count"] = len(contest_field_df)
        st.session_state["contest_field_ready"] = (
            len(contest_field_df) == 10000
        )

        contest_details = st.session_state.get("selected_dk_contest")
        if contest_details:
            st.success(
                f"Simulated contest field created for {contest_details['name']} "
                f"(ID {contest_details['id']}): {len(contest_field_df):,} simulated opponent lineups."
            )
        else:
            st.success(
                f"Contest field created: {len(contest_field_df):,} simulated opponent lineups."
            )
    else:
        st.warning("Run SIM or BUILD first.")

# ============================================
# BUILD ACTION
# ============================================

if build_clicked:
    # One-click workflow: simulate players, build a contest field, then
    # continue below to create and score candidate lineups.
    with st.spinner("Running 10,000 game simulations..."):
        simulation_df = run_game_simulations(players_df)

    st.session_state["simulation_df"] = simulation_df
    st.session_state["simulations_ready"] = True

    # Build the 10,000-lineup contest field automatically for this run.
    with st.spinner("Building the simulated contest field..."):
        contest_field = []
        rng = np.random.default_rng(123)
        if len(available_players) >= 6:
            player_weights = simulation_df.mean(axis=0).reindex(
                available_players
            ).clip(lower=0.01)
            player_weights = player_weights / player_weights.sum()
            attempts = 0
            while len(contest_field) < 10000 and attempts < 200000:
                attempts += 1
                selected = rng.choice(
                    available_players, size=6, replace=False,
                    p=player_weights.to_numpy()
                )
                captain = selected[
                    np.argmax([simulation_df[p].mean() for p in selected])
                ]
                flex = [p for p in selected if p != captain]
                total_salary = (
                    captain_salary_map[captain]
                    + sum(salary_map[p] for p in flex)
                )
                if total_salary > SALARY_CAP:
                    continue
                lineup_teams = set(
                    players_df.loc[players_df["Name"].isin(selected), "Team"]
                )
                if len(lineup_teams) < 2:
                    continue
                contest_field.append({
                    "Captain": captain, "Flex1": flex[0], "Flex2": flex[1],
                    "Flex3": flex[2], "Flex4": flex[3], "Flex5": flex[4],
                    "Salary": total_salary
                })
        contest_field_df = pd.DataFrame(contest_field)
        st.session_state["contest_field_df"] = contest_field_df
        st.session_state["contest_field_count"] = len(contest_field_df)
        st.session_state["contest_field_ready"] = len(contest_field_df) == 10000

    selected_contest = st.session_state.get("selected_dk_contest")
    if selected_contest:
        st.info(
            f"Contest selected from your entry CSV: {selected_contest['name']} "
            f"(ID {selected_contest['id']}). Your uploaded file has "
            f"{selected_contest['your_entries']} of your entries in this contest. "
            "The 10,000 opponents are simulated; the entry CSV does not contain "
            "the actual opponent field or payout table."
        )

    # Refresh rankings with the simulations created by this BUILD click.
    player_sim = {}
    for player in players_df["Name"]:
        values = simulation_df[player]
        player_sim[player] = {
            "Mean": values.mean(),
            "P95": values.quantile(0.95),
            "P99": values.quantile(0.99)
        }

locked_players = [
    p for p in available_players
    if control_map[p]["Lock"]
]

# ============================================
# RANK PLAYERS
# ============================================

player_rank = sorted(
    available_players,
    key=lambda p: (
        player_sim[p]["P95"] * 0.50
        + player_sim[p]["P99"] * 0.25
        + player_sim[p]["Mean"] * 0.25
    ),
    reverse=True
)

# Use top players plus all locked players.
search_pool = list(dict.fromkeys(
    player_rank[:20] + locked_players
))

# ============================================
# ============================================
# CANDIDATE SETTINGS
# ============================================

LINEUP_COUNT = 20
CANDIDATE_COUNT = 5000

# BUILD CANDIDATES
# ============================================

candidates = []

for captain in search_pool:

    if control_map[captain]["Captain Max %"] <= 0:
        continue

    flex_pool = [
        p for p in search_pool
        if p != captain
    ]

    for flex_players in itertools.combinations(
        flex_pool,
        5
    ):

        lineup_players = [
            captain
        ] + list(flex_players)

        # LOCK CHECK
        if not all(
            p in lineup_players
            for p in locked_players
        ):
            continue

        # SALARY CHECK
        total_salary = (
            captain_salary_map[captain]
            + sum(
                salary_map[p]
                for p in flex_players
            )
        )

        if total_salary > SALARY_CAP:
            continue

        # DraftKings Showdown requires players
        # from both teams
        lineup_teams = set(
            players_df.loc[
                players_df["Name"].isin(lineup_players),
                "Team"
            ]
        )

        if len(lineup_teams) < 2:
            continue

        # ========================================
        # SIMULATION SCORE
        # ========================================

        total_mean = (
            player_sim[captain]["Mean"] * 1.5
            + sum(
                player_sim[p]["Mean"]
                for p in flex_players
            )
        )

        total_p95 = (
            player_sim[captain]["P95"] * 1.5
            + sum(
                player_sim[p]["P95"]
                for p in flex_players
            )
        )

        total_p99 = (
            player_sim[captain]["P99"] * 1.5
            + sum(
                player_sim[p]["P99"]
                for p in flex_players
            )
        )

        score = (
            total_p95 * 0.50
            + total_p99 * 0.25
            + total_mean * 0.25
        )

        candidates.append({
            "Captain": captain,
            "Flex1": flex_players[0],
            "Flex2": flex_players[1],
            "Flex3": flex_players[2],
            "Flex4": flex_players[3],
            "Flex5": flex_players[4],
            "Salary": total_salary,
            "SimMean": total_mean,
            "SimP95": total_p95,
            "SimP99": total_p99,
            "Score": score
        })

        # Stop once we have 10,000 candidates
        if len(candidates) >= CANDIDATE_COUNT:
            break

    if len(candidates) >= CANDIDATE_COUNT:
        break

candidates_df = pd.DataFrame(candidates)

st.session_state["candidates_df"] = candidates_df
st.session_state["candidates_ready"] = True

st.write(
    f"Candidate lineups tested: {len(candidates_df):,}"
)


# ============================================
# CONTEST SCORING
# ============================================

if (
    "contest_field_df" in st.session_state
    and "candidates_df" in st.session_state
    and "simulation_df" in st.session_state
):

    contest_field_df = st.session_state["contest_field_df"]
    candidates_df = st.session_state["candidates_df"]
    simulation_df = st.session_state["simulation_df"]

    lineup_cols = [
        "Captain",
        "Flex1",
        "Flex2",
        "Flex3",
        "Flex4",
        "Flex5"
    ]

    player_index = {
        player: i
        for i, player in enumerate(simulation_df.columns)
    }

    candidate_idx = np.array([
        [player_index[row[col]] for col in lineup_cols]
        for _, row in candidates_df.iterrows()
    ], dtype=np.int16)

    contest_idx = np.array([
        [player_index[row[col]] for col in lineup_cols]
        for _, row in contest_field_df.iterrows()
    ], dtype=np.int16)

    n_candidates = len(candidate_idx)
    n_sims = len(simulation_df)
    total_field = len(contest_idx)

    win_rates = np.zeros(n_candidates)
    top1_rates = np.zeros(n_candidates)
    top5_rates = np.zeros(n_candidates)
    top10_rates = np.zeros(n_candidates)
    cash_rates = np.zeros(n_candidates)
    avg_percentiles = np.zeros(n_candidates)

    progress = st.progress(0)

    for sim_idx in range(n_sims):

        values = simulation_df.iloc[sim_idx].to_numpy(
            dtype=np.float32
        )

        cand_scores = (
            values[candidate_idx[:, 0]] * 1.5
            + values[candidate_idx[:, 1:]].sum(axis=1)
        )

        field_scores = (
            values[contest_idx[:, 0]] * 1.5
            + values[contest_idx[:, 1:]].sum(axis=1)
        )

        sorted_field = np.sort(field_scores)

        count_greater = (
            total_field
            - np.searchsorted(
                sorted_field,
                cand_scores,
                side="right"
            )
        )

        percentile = 1.0 - (
            count_greater / total_field
        )

        win_rates += (count_greater == 0)
        top1_rates += (percentile >= 0.99)
        top5_rates += (percentile >= 0.95)
        top10_rates += (percentile >= 0.90)
        cash_rates += (percentile >= 0.50)
        avg_percentiles += percentile

        if (sim_idx + 1) % 500 == 0:
            progress.progress(
                (sim_idx + 1) / n_sims
            )

    progress.empty()

    results_df = candidates_df.copy()

    results_df["WinRate"] = win_rates / n_sims
    results_df["Top1"] = top1_rates / n_sims
    results_df["Top5"] = top5_rates / n_sims
    results_df["Top10"] = top10_rates / n_sims
    results_df["CashRate"] = cash_rates / n_sims
    results_df["AvgPercentile"] = avg_percentiles / n_sims

    results_df["ContestScore"] = (
        results_df["Top1"] * 0.40
        + results_df["Top5"] * 0.25
        + results_df["Top10"] * 0.20
        + results_df["CashRate"] * 0.10
        + results_df["WinRate"] * 0.05
    )

    results_df = (
        results_df
        .sort_values("ContestScore", ascending=False)
        .reset_index(drop=True)
    )

    st.session_state["contest_results_df"] = results_df

# ============================================

# ============================================
# PORTFOLIO FUNCTIONS
# ============================================

PORTFOLIO_METRICS = {
    "Contest Score": "ContestScore",
    "Win %": "WinRate",
    "Top 1%": "Top1",
    "Top 5%": "Top5",
    "Top 10%": "Top10",
    "Cash %": "CashRate",
    "Average Percentile": "AvgPercentile"
}


def build_portfolio(results_df, lineup_count, metric):
    """Build a portfolio using the selected ranking metric."""

    if lineup_count < 1:
        raise ValueError("Lineup count must be at least 1.")

    if lineup_count > len(results_df):
        raise ValueError(
            f"Only {len(results_df)} lineups are available."
        )

    if metric not in results_df.columns:
        raise ValueError(
            f"Ranking metric not found: {metric}"
        )

    portfolio = (
        results_df
        .sort_values(metric, ascending=False)
        .head(lineup_count)
        .copy()
        .reset_index(drop=True)
    )

    portfolio["Locked"] = False

    return portfolio


def lock_portfolio_lineup(portfolio_df, lineup_index):
    """Lock one lineup so it cannot be replaced."""

    portfolio_df = portfolio_df.copy()

    if 0 <= lineup_index < len(portfolio_df):
        portfolio_df.loc[lineup_index, "Locked"] = True

    return portfolio_df


def delete_and_replace_portfolio_lineup(
    portfolio_df,
    results_df,
    lineup_index,
    metric
):
    """Delete one unlocked lineup and replace it with the next ranked lineup."""

    portfolio_df = portfolio_df.copy()

    if not 0 <= lineup_index < len(portfolio_df):
        return portfolio_df

    if bool(portfolio_df.loc[lineup_index, "Locked"]):
        return portfolio_df

    lineup_columns = [
        "Captain",
        "Flex1",
        "Flex2",
        "Flex3",
        "Flex4",
        "Flex5"
    ]

    deleted_key = tuple(
        portfolio_df.loc[
            lineup_index,
            lineup_columns
        ]
    )

    remaining = portfolio_df.drop(
        portfolio_df.index[lineup_index]
    ).copy()

    used_keys = set(
        tuple(row)
        for row in remaining[lineup_columns].to_numpy()
    )

    ranked = results_df.sort_values(
        metric,
        ascending=False
    )

    replacement = None

    for _, row in ranked.iterrows():

        key = tuple(
            row[lineup_columns]
        )

        if key not in used_keys and key != deleted_key:
            replacement = row.copy()
            break

    if replacement is not None:
        replacement["Locked"] = False

        remaining = pd.concat(
            [
                remaining,
                replacement.to_frame().T
            ],
            ignore_index=True
        )

    return remaining.reset_index(drop=True)


# ============================================
# ============================================
# PORTFOLIO
# ============================================

st.divider()
st.write("## Portfolio")

if "contest_results_df" in st.session_state:

    results_df = st.session_state["contest_results_df"]

    portfolio_count = st.number_input(
        "Number of lineups",
        min_value=1,
        max_value=min(150, len(results_df)),
        value=20,
        step=1,
        key="portfolio_count"
    )

    portfolio_metric_label = st.selectbox(
        "Rank lineups by",
        list(PORTFOLIO_METRICS.keys()),
        key="portfolio_metric"
    )

    portfolio_metric = PORTFOLIO_METRICS[
        portfolio_metric_label
    ]

    if (
        "portfolio_df" not in st.session_state
        or st.session_state.get("portfolio_count_used") != portfolio_count
        or st.session_state.get("portfolio_metric_used") != portfolio_metric
    ):

        old_portfolio = st.session_state.get("portfolio_df")

        if old_portfolio is not None and "Locked" in old_portfolio.columns:
            locked_df = old_portfolio[
                old_portfolio["Locked"] == True
            ].copy()

            available_count = max(
                0,
                int(portfolio_count) - len(locked_df)
            )

            ranked_df = (
                results_df
                .sort_values(
                    portfolio_metric,
                    ascending=False
                )
                .copy()
            )

            lineup_columns = [
                "Captain",
                "Flex1",
                "Flex2",
                "Flex3",
                "Flex4",
                "Flex5"
            ]

            locked_keys = set(
                tuple(row)
                for row in locked_df[lineup_columns].to_numpy()
            )

            selected_rows = []

            for _, row in ranked_df.iterrows():

                key = tuple(
                    row[lineup_columns]
                )

                if key not in locked_keys:
                    selected_rows.append(row)

                if len(selected_rows) >= available_count:
                    break

            new_rows = pd.DataFrame(
                selected_rows
            )

            if len(new_rows) > 0:
                new_rows["Locked"] = False

            portfolio_df = pd.concat(
                [
                    locked_df,
                    new_rows
                ],
                ignore_index=True
            ).head(int(portfolio_count))

        else:

            portfolio_df = build_portfolio(
                results_df,
                int(portfolio_count),
                portfolio_metric
            )

        st.session_state["portfolio_df"] = portfolio_df
        st.session_state["portfolio_count_used"] = portfolio_count
        st.session_state["portfolio_metric_used"] = portfolio_metric

    portfolio_df = st.session_state["portfolio_df"].copy()

    # Add each lineup's total salary to the portfolio display and export.
    portfolio_df["Salary"] = portfolio_df.apply(
        lambda row: int(
            captain_salary_map.get(str(row["Captain"]), 0)
            + sum(
                salary_map.get(str(row[col]), 0)
                for col in ["Flex1", "Flex2", "Flex3", "Flex4", "Flex5"]
            )
        ),
        axis=1
    )
    st.session_state["portfolio_df"] = portfolio_df

    st.write(
        f"Portfolio: {len(portfolio_df)} lineups"
    )

    display_columns = [
        "Captain",
        "Flex1",
        "Flex2",
        "Flex3",
        "Flex4",
        "Flex5",
        "Salary",
        "ContestScore",
        "WinRate",
        "Top1",
        "Top5",
        "Top10",
        "CashRate",
        "Locked"
    ]

    display_df = portfolio_df[
        [c for c in display_columns if c in portfolio_df.columns]
    ].copy()

    for col in [
        "ContestScore",
        "WinRate",
        "Top1",
        "Top5",
        "Top10",
        "CashRate"
    ]:
        if col in display_df.columns:
            display_df[col] = display_df[col] * 100

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    export_columns = [
        "Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5",
        "Salary", "ContestScore", "WinRate", "Top1", "Top5",
        "Top10", "CashRate"
    ]
    portfolio_export_df = portfolio_df[
        [col for col in export_columns if col in portfolio_df.columns]
    ].copy()
    for col in ["WinRate", "Top1", "Top5", "Top10", "CashRate"]:
        if col in portfolio_export_df.columns:
            portfolio_export_df[col] = portfolio_export_df[col] * 100

    st.download_button(
        label="EXPORT PORTFOLIO CSV",
        data=portfolio_export_df.to_csv(index=False).encode("utf-8"),
        file_name="DFS_Portfolio.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.write("### Portfolio Controls")

    for idx in portfolio_df.index:

        cols = st.columns([0.7, 1.0, 1.0])

        cols[0].write(f"Lineup {idx + 1}")

        if bool(portfolio_df.loc[idx, "Locked"]):
            cols[1].success("LOCKED")
        else:
            if cols[1].button(
                "LOCK",
                key=f"portfolio_lock_{idx}"
            ):
                portfolio_df = lock_portfolio_lineup(
                    portfolio_df,
                    idx
                )

                st.session_state["portfolio_df"] = portfolio_df
                st.rerun()

        if bool(portfolio_df.loc[idx, "Locked"]):
            cols[2].write("Protected")
        else:
            if cols[2].button(
                "DELETE",
                key=f"portfolio_delete_{idx}"
            ):
                portfolio_df = delete_and_replace_portfolio_lineup(
                    portfolio_df,
                    results_df,
                    idx,
                    portfolio_metric
                )

                st.session_state["portfolio_df"] = portfolio_df
                st.rerun()

else:

    st.info(
        "Run CONTEST SIM before building a portfolio."
    )


# ============================================
# ============================================
# DRAFTKINGS EXPORT BUTTONS
# ============================================

if (
    "final_lineups" in st.session_state
    and "dk_player_ids" in st.session_state
):

    final_lineups = st.session_state["final_lineups"]
    dk_player_ids = st.session_state["dk_player_ids"]

    export_rows = []
    missing_ids = []

    for _, row in final_lineups.iterrows():

        captain = str(row["Captain"]).strip()

        flex_players = [
            str(row["Flex1"]).strip(),
            str(row["Flex2"]).strip(),
            str(row["Flex3"]).strip(),
            str(row["Flex4"]).strip(),
            str(row["Flex5"]).strip()
        ]

        captain_id = dk_player_ids.get(
            captain, {}
        ).get("CPT")

        flex_ids = [
            dk_player_ids.get(
                player, {}
            ).get("FLEX")
            for player in flex_players
        ]

        if not captain_id:
            missing_ids.append(
                f"{captain} - CPT"
            )

        for player, player_id in zip(
            flex_players,
            flex_ids
        ):

            if not player_id:
                missing_ids.append(
                    f"{player} - FLEX"
                )

        export_rows.append(
            [captain_id] + flex_ids
        )

    if missing_ids:

        st.error("Missing DraftKings IDs:")
        st.write(missing_ids)

    else:

        export_df = pd.DataFrame(
            export_rows,
            columns=[
                "CPT",
                "FLEX",
                "FLEX",
                "FLEX",
                "FLEX",
                "FLEX"
            ]
        )

        csv_data = export_df.to_csv(
            index=False
        ).encode("utf-8")

        st.success(
            "DraftKings IDs ready for export."
        )

        st.download_button(
            label="EXPORT CSV",
            data=csv_data,
            file_name="NFL_DraftKings_20_Lineups_Upload.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.link_button(
            "UPLOAD TO DRAFTKINGS",
            "https://www.draftkings.com/lineup/upload",
            use_container_width=True
        )

elif "final_lineups" in st.session_state:

    st.warning(
        "Upload the DraftKings contest CSV template first."
    )

else:

    st.info(
        "Click BUILD LINEUPS first."
    )
