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
                pd.to_numeric(uploaded_df[projection_col], errors="coerce").fillna(0.01)
                if projection_col is not None else 0.01
            )
            if id_col is not None:
                loaded_players["DK_ID"] = uploaded_df[id_col].astype(str).str.strip()
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
                st.success(f"Loaded {len(players_df)} players from the salary file.")
                if projection_col is None:
                    st.warning("No projection column was found. Projections are set to 0.01 until projections are added.")
                if is_showdown_template:
                    st.info("DraftKings Showdown template detected. FLEX rows are used for player salaries; CPT rows are ignored to avoid duplicate players.")
                elif is_lineup_template:
                    st.info("Lineup template detected. Player rows were kept without applying Showdown-only filtering.")
                st.caption("Check the player names, teams, salaries, and projections before building lineups.")
    except Exception as exc:
        st.error(f"Could not read that CSV: {exc}. The sample player pool is still being used.")

# Infer the opposing team from the teams present in the uploaded slate.
teams_in_slate = [
    team for team in players_df["Team"].dropna().astype(str).unique()
    if team.strip()
]
opponent_map = {}
if len(teams_in_slate) == 2:
    opponent_map = {
        teams_in_slate[0]: teams_in_slate[1],
        teams_in_slate[1]: teams_in_slate[0],
    }
players_df["Opponent"] = players_df["Team"].map(opponent_map)

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

player_display = player_display[
    [
        "Name",
        "Position",
        "Team",
        "Opponent",
        "Salary",
        "CaptainSalary",
        "Projection",
        "SimMean",
        "SimP10",
        "SimP25",
        "SimP50",
        "SimP75",
        "SimP90",
        "SimP95",
        "SimP99"
    ]
]

st.dataframe(
    player_display,
    use_container_width=True,
    hide_index=True
)

# ================================
# SETTINGS DISPLAY
# ================================


st.divider()


st.markdown("""
<style>
div.stButton > button {
    min-height: 16px !important;
    height: 16px !important;
    width: 18px !important;
    min-width: 18px !important;
    padding: 0px !important;
    margin: 0px !important;
    font-size: 9px !important;
    line-height: 16px !important;
}
</style>
""", unsafe_allow_html=True)

st.write("### Player Controls")
st.caption("− / + changes exposure by 1%.")

# Keep settings for players that remain, and add new uploaded players.
default_control_columns = [
    "Name", "Position", "Team", "Opponent",
    "Lock", "Fade", "Min Exposure %", "Max Exposure %",
    "Captain Min %", "Captain Max %"
]
if "control_values" not in st.session_state:
    control_values = players_df[["Name", "Position", "Team", "Opponent"]].copy()
    control_values["Lock"] = False
    control_values["Fade"] = False
    control_values["Min Exposure %"] = 0
    control_values["Max Exposure %"] = 100
    control_values["Captain Min %"] = 0
    control_values["Captain Max %"] = 100
else:
    previous_controls = st.session_state["control_values"].copy()
    current_controls = players_df[["Name", "Position", "Team", "Opponent"]].copy()
    setting_columns = [
        "Lock", "Fade", "Min Exposure %", "Max Exposure %",
        "Captain Min %", "Captain Max %"
    ]
    previous_by_name = previous_controls.drop_duplicates("Name").set_index("Name")
    for setting in setting_columns:
        current_controls[setting] = current_controls["Name"].map(
            previous_by_name[setting] if setting in previous_by_name.columns
            else pd.Series(dtype=object)
        )
    current_controls["Lock"] = current_controls["Lock"].fillna(False).astype(bool)
    current_controls["Fade"] = current_controls["Fade"].fillna(False).astype(bool)
    for setting, default in [
        ("Min Exposure %", 0), ("Max Exposure %", 100),
        ("Captain Min %", 0), ("Captain Max %", 100)
    ]:
        current_controls[setting] = current_controls[setting].fillna(default).astype(int)
    control_values = current_controls

st.session_state["control_values"] = control_values
control_values = st.session_state["control_values"]

headers = st.columns(
    [2.4, 0.45, 0.45, 0.55, 0.55, 0.55, 1.0, 1.0, 1.0, 1.0]
)

headers[0].write("Player")
headers[1].write("Pos")
headers[2].write("Team")
headers[3].write("Opp")
headers[4].write("Lock")
headers[5].write("Fade")
headers[6].write("Min")
headers[7].write("Max")
headers[8].write("CPT Min")
headers[9].write("CPT Max")

for idx in control_values.index:

    row = st.columns(
        [2.4, 0.45, 0.45, 0.55, 0.55, 0.55, 1.0, 1.0, 1.0, 1.0]
    )

    row[0].write(control_values.loc[idx, "Name"])
    row[1].write(control_values.loc[idx, "Position"])
    row[2].write(control_values.loc[idx, "Team"])
    row[3].write(control_values.loc[idx, "Opponent"])

    control_values.loc[idx, "Lock"] = row[4].checkbox(
        "Lock",
        value=bool(control_values.loc[idx, "Lock"]),
        key=f"lock_{idx}",
        label_visibility="collapsed"
    )

    control_values.loc[idx, "Fade"] = row[5].checkbox(
        "Fade",
        value=bool(control_values.loc[idx, "Fade"]),
        key=f"fade_{idx}",
        label_visibility="collapsed"
    )

    settings = [
        ("Min Exposure %", "min"),
        ("Max Exposure %", "max"),
        ("Captain Min %", "cmin"),
        ("Captain Max %", "cmax")
    ]

    for col, (setting, short) in enumerate(settings, start=6):

        value = int(control_values.loc[idx, setting])

        small = row[col].columns([0.5, 1.0, 0.5])

        if small[0].button(
            "−",
            key=f"minus_{idx}_{short}",
            width="content"
        ):
            value = max(0, value - 1)

        small[1].write(f"{value}%")

        if small[2].button(
            "+",
            key=f"plus_{idx}_{short}",
            width="content"
        ):
            value = min(100, value + 1)

        control_values.loc[idx, setting] = value

st.session_state["control_values"] = control_values
edited_controls = control_values.copy()

# Build control lookup before any button handlers use it.
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

        st.success(
            f"Contest field created: {len(contest_field_df):,} lineups."
        )
    else:
        st.warning("Run SIM or BUILD first.")

# ============================================
# BUILD ACTION
# ============================================

if build_clicked:
    with st.spinner("Running 10,000 game simulations..."):
        simulation_df = run_game_simulations(players_df)

    st.session_state["simulation_df"] = simulation_df
    st.session_state["simulations_ready"] = True

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
