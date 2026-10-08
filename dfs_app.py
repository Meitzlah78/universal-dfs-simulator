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
st.subheader("DraftKings Showdown")

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

if "control_values" not in st.session_state:

    control_values = players_df[
        ["Name", "Position", "Team", "Opponent"]
    ].copy()

    control_values["Lock"] = False
    control_values["Fade"] = False
    control_values["Min Exposure %"] = 0
    control_values["Max Exposure %"] = 100
    control_values["Captain Min %"] = 0
    control_values["Captain Max %"] = 100

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
        values = simulation_df[player]

        player_sim[player] = {
            "Mean": values.mean(),
            "P95": values.quantile(0.95),
            "P99": values.quantile(0.99)
        }

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

    available_players = [
        p for p in players_df["Name"]
        if not control_map[p]["Fade"]
    ]

    rng = np.random.default_rng(123)

    if "simulation_df" in st.session_state:
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
# PLAYER CONTROLS
# ============================================

control_map = edited_controls.set_index(
    "Name"
).to_dict("index")

if build_clicked:
    with st.spinner("Running 10,000 game simulations..."):
        simulation_df = run_game_simulations(players_df)

    st.session_state["simulation_df"] = simulation_df
    st.session_state["simulations_ready"] = True

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
