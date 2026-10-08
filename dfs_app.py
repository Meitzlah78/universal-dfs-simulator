
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Universal DFS Simulator",
    page_icon="🏈",
    layout="wide"
)

st.title("Universal DFS Simulator")
st.subheader("DraftKings Showdown")

# ================================
# SETTINGS
# ================================

SIMULATIONS = 50000
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

players_df["Opponent"] = players_df["Team"].map({
    "DAL": "TB",
    "TB": "DAL"
})

players_df["CaptainSalary"] = (
    players_df["Salary"] * 1.5
).astype(int)

# ================================
# SIMULATION
# ================================

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

simulation_df = pd.DataFrame(
    sims,
    columns=players_df["Name"].tolist()
)

# ================================
# PLAYER DISPLAY
# ================================

st.divider()
st.write("### Player Pool")

player_display = players_df.copy()

player_display["SimMean"] = simulation_df.mean(axis=0).values
player_display["SimP10"] = simulation_df.quantile(0.10, axis=0).values
player_display["SimP25"] = simulation_df.quantile(0.25, axis=0).values
player_display["SimP50"] = simulation_df.quantile(0.50, axis=0).values
player_display["SimP75"] = simulation_df.quantile(0.75, axis=0).values
player_display["SimP90"] = simulation_df.quantile(0.90, axis=0).values
player_display["SimP95"] = simulation_df.quantile(0.95, axis=0).values
player_display["SimP99"] = simulation_df.quantile(0.99, axis=0).values

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

st.write("### Player Controls")

controls_df = players_df[
    ["Name", "Position", "Team", "Opponent"]
].copy()

controls_df["Lock"] = False
controls_df["Fade"] = False
controls_df["Min Exposure %"] = 0
controls_df["Max Exposure %"] = 100
controls_df["Captain Min %"] = 0
controls_df["Captain Max %"] = 100

edited_controls = st.data_editor(
    controls_df,
    use_container_width=True,
    hide_index=True,
    disabled=["Name", "Position", "Team", "Opponent"],
    column_config={
        "Lock": st.column_config.CheckboxColumn("Lock"),
        "Fade": st.column_config.CheckboxColumn("Fade"),
        "Min Exposure %": st.column_config.NumberColumn(
            "Min Exposure %",
            min_value=0,
            max_value=100,
            step=1
        ),
        "Max Exposure %": st.column_config.NumberColumn(
            "Max Exposure %",
            min_value=0,
            max_value=100,
            step=1
        ),
        "Captain Min %": st.column_config.NumberColumn(
            "Captain Min %",
            min_value=0,
            max_value=100,
            step=1
        ),
        "Captain Max %": st.column_config.NumberColumn(
            "Captain Max %",
            min_value=0,
            max_value=100,
            step=1
        )
    }
)

st.divider()

st.write("### Current Settings")


col1, col2, col3, col4 = st.columns(4)

col1.metric("Sport", "NFL")
col2.metric("Site", "DraftKings")
col3.metric("Format", "Showdown")
col4.metric("Simulations", f"{SIMULATIONS:,}")

st.write("")

if st.button(
    "BUILD LINEUPS",
    type="primary",
    use_container_width=True
):
    import itertools

    LINEUP_COUNT = 20
    CANDIDATE_COUNT = 10000

    salary_map = dict(zip(
        players_df["Name"],
        players_df["Salary"]
    ))

    captain_salary_map = dict(zip(
        players_df["Name"],
        players_df["CaptainSalary"]
    ))

    # ============================================
    # SIMULATION VALUES
    # ============================================

    player_sim = {}

    for player in players_df["Name"]:
        values = simulation_df[player]

        player_sim[player] = {
            "Mean": values.mean(),
            "P95": values.quantile(0.95),
            "P99": values.quantile(0.99)
        }

    # ============================================
    # PLAYER CONTROLS
    # ============================================

    control_map = edited_controls.set_index(
        "Name"
    ).to_dict("index")

    available_players = [
        p for p in players_df["Name"]
        if not control_map[p]["Fade"]
    ]

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

    st.write(
        f"Candidate lineups tested: {len(candidates_df):,}"
    )

    # ============================================
    # SELECT BEST 20
    # ============================================

    if candidates_df.empty:

        st.error("No valid lineups found.")

    else:

        candidates_df = candidates_df.sort_values(
            "Score",
            ascending=False
        ).reset_index(drop=True)

        selected = []
        used_sets = []
        player_counts = {}
        captain_counts = {}

        for _, row in candidates_df.iterrows():

            lineup_set = {
                row["Captain"],
                row["Flex1"],
                row["Flex2"],
                row["Flex3"],
                row["Flex4"],
                row["Flex5"]
            }

            too_similar = False

            for previous_set in used_sets:

                overlap = len(
                    lineup_set & previous_set
                )

                if overlap >= 5:
                    too_similar = True
                    break

            if too_similar:
                continue

            # Check player maximum exposure
            exposure_ok = True

            for player in lineup_set:

                max_exposure = float(
                    control_map[player]["Max Exposure %"]
                )

                current_count = player_counts.get(
                    player,
                    0
                )

                if current_count >= (
                    LINEUP_COUNT
                    * max_exposure
                    / 100
                ):
                    exposure_ok = False
                    break

            if not exposure_ok:
                continue

            # Check captain maximum exposure
            captain = row["Captain"]

            captain_max = float(
                control_map[captain]["Captain Max %"]
            )

            current_captain_count = captain_counts.get(
                captain,
                0
            )

            if current_captain_count >= (
                LINEUP_COUNT
                * captain_max
                / 100
            ):
                continue

            selected.append(row)
            used_sets.append(lineup_set)

            # Update player exposure counts
            for player in lineup_set:
                player_counts[player] = (
                    player_counts.get(player, 0) + 1
                )

            # Update captain exposure count
            captain_counts[captain] = (
                captain_counts.get(captain, 0) + 1
            )

            if len(selected) >= LINEUP_COUNT:
                break

        final_lineups = pd.DataFrame(selected)
        st.session_state["final_lineups"] = final_lineups

        st.success(
            f"Built {len(final_lineups)} valid lineups."
        )

        st.write("### 20-Lineup Portfolio")

        st.dataframe(
            final_lineups[
                [
                    "Captain",
                    "Flex1",
                    "Flex2",
                    "Flex3",
                    "Flex4",
                    "Flex5",
                    "Salary",
                    "SimMean",
                    "SimP95",
                    "SimP99"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )


        st.write("### Portfolio Summary")

        st.write(
            f"Lineups: {len(final_lineups)}"
        )

        st.write(
            f"Salary range: "
            f"${final_lineups['Salary'].min():,.0f}"
            f" - "
            f"${final_lineups['Salary'].max():,.0f}"
        )

        st.write(
            f"Average salary: "
            f"${final_lineups['Salary'].mean():,.0f}"
        )


# ============================================
# DRAFTKINGS CONTEST TEMPLATE
# ============================================

st.write("### DraftKings Contest Template")

dk_template = st.file_uploader(
    "Drag and drop your DraftKings CSV template here",
    type=["csv"],
    help="Upload the CSV template downloaded from DraftKings for this contest."
)

if dk_template is not None:

    try:
        template_df = pd.read_csv(
        dk_template,
        engine="python",
        on_bad_lines="skip",
        header=None
    )
    except Exception as e:
        st.error("Could not read the DraftKings template.")
        st.code(str(e))
        template_df = None

    if template_df is not None:
        st.success("DraftKings template loaded.")

    st.write("Template columns:")
    st.write(template_df.columns.tolist())

    st.write("Template preview:")
    st.dataframe(
        template_df.head(5),
        use_container_width=True,
        hide_index=True
    )

    st.write("Template rows:")
    st.code(
        template_df.head(10).to_string(index=False)
    )

    st.write("Template shape:")
    st.write(
        f"Rows: {len(template_df):,} | Columns: {len(template_df.columns)}"
    )

    st.write("Last 20 rows of template:")
    st.code(
        template_df.tail(20).to_string(index=False)
    )

    st.write("ALL TEMPLATE COLUMN NAMES:")
    st.code(
        "\n".join(
            f"{i}: {col}"
            for i, col in enumerate(template_df.columns)
        )
    )

    st.session_state["dk_template"] = template_df


# ============================================
# DRAFTKINGS ID PARSER
# ============================================

import csv
import io

if dk_template is not None:

    try:
        raw_text = dk_template.getvalue().decode(
            "utf-8-sig",
            errors="replace"
        )

        rows = list(
            csv.reader(
                io.StringIO(raw_text)
            )
        )

        header_index = None

        for i, row in enumerate(rows):
            if (
                "ID" in row
                and "Name" in row
                and "Roster Position" in row
            ):
                header_index = i
                break

        if header_index is None:
            st.error(
                "Could not find DraftKings player IDs."
            )

        else:

            header = rows[header_index]

            name_index = header.index("Name")
            id_index = header.index("ID")
            roster_index = header.index(
                "Roster Position"
            )

            dk_player_ids = {}

            for row in rows[header_index + 1:]:

                if len(row) <= max(
                    name_index,
                    id_index,
                    roster_index
                ):
                    continue

                name = row[name_index].strip()
                player_id = row[id_index].strip()
                roster_position = row[
                    roster_index
                ].strip()

                if (
                    name
                    and player_id
                    and roster_position in [
                        "CPT",
                        "FLEX"
                    ]
                ):

                    if name not in dk_player_ids:
                        dk_player_ids[name] = {}

                    dk_player_ids[name][
                        roster_position
                    ] = player_id

            st.session_state[
                "dk_player_ids"
            ] = dk_player_ids

            cpt_count = sum(
                1
                for ids in dk_player_ids.values()
                if "CPT" in ids
            )

            flex_count = sum(
                1
                for ids in dk_player_ids.values()
                if "FLEX" in ids
            )

            st.success(
                "DraftKings player IDs loaded."
            )

            st.write(
                f"CPT IDs: {cpt_count}"
            )

            st.write(
                f"FLEX IDs: {flex_count}"
            )

    except Exception as e:

        st.error(
            "Could not read DraftKings player IDs."
        )

        st.code(str(e))

# ============================================
# DRAFTKINGS EXPORT BUTTONS
# ============================================

if "final_lineups" in st.session_state and "dk_player_ids" in st.session_state:

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

        st.error(
            "Missing DraftKings IDs:"
        )

        st.write(
            missing_ids
        )

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

