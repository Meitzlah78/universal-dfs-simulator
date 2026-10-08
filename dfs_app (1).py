
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
    ["Chase McLaughlin", "K", "TB", 5000, 7.0, "DAL"],
], columns=[
    "Name",
    "Position",
    "Team",
    "Salary",
    "Projection",
    "Opponent"
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
            step=5
        ),
        "Max Exposure %": st.column_config.NumberColumn(
            "Max Exposure %",
            min_value=0,
            max_value=100,
            step=5
        ),
        "Captain Min %": st.column_config.NumberColumn(
            "Captain Min %",
            min_value=0,
            max_value=100,
            step=5
        ),
        "Captain Max %": st.column_config.NumberColumn(
            "Captain Max %",
            min_value=0,
            max_value=100,
            step=5
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
    st.success("Lineup builder is ready.")
