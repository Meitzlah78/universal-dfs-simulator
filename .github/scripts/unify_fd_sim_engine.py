from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

SHARED_MARKER = "# SHARED HISTORICAL/PBP PLAYER SIMULATION ENGINE"

# Lift the DraftKings historical/PBP simulation engine out of the DraftKings-only
# branch so both DraftKings and FanDuel call the exact same function.
if SHARED_MARKER not in text:
    fd_branch = '\nif platform == "FanDuel":\n'
    else_marker = '\nelse:\n\n    # ================================\n    # SETTINGS\n'
    player_pool_marker = '\n    # ================================\n    # PLAYER POOL\n'

    fd_pos = text.find(fd_branch)
    if fd_pos < 0:
        raise SystemExit("FanDuel branch anchor not found")
    else_pos = text.find(else_marker, fd_pos)
    if else_pos < 0:
        raise SystemExit("DraftKings else/settings anchor not found")
    pool_pos = text.find(player_pool_marker, else_pos)
    if pool_pos < 0:
        raise SystemExit("DraftKings player-pool anchor not found")

    # Everything between the outer else and PLAYER POOL is the shared scoring,
    # history-loading, PBP calibration, and player-outcome engine.
    indented_block = text[else_pos + len("\nelse:\n"):pool_pos]
    required = [
        "def score_nfl_stat_line",
        "def _simulate_scored_player_outcomes",
        "def load_nfl_pbp_game_history",
        "def load_nfl_historical_player_stats",
        "def _historical_player_average",
    ]
    missing = [name for name in required if name not in indented_block]
    if missing:
        raise SystemExit("Shared engine block is missing: " + ", ".join(missing))

    shared_lines = []
    for line in indented_block.splitlines(True):
        shared_lines.append(line[4:] if line.startswith("    ") else line)
    shared_block = "\n" + SHARED_MARKER + "\n" + "".join(shared_lines).lstrip("\n") + "\n"

    # Remove the engine from the DraftKings-only else, leaving the DK Player Pool
    # as the first code in that branch.
    text = text[:else_pos] + "\nelse:\n" + text[pool_pos:]

    # Insert the shared engine immediately before the platform split.
    fd_pos = text.find(fd_branch)
    text = text[:fd_pos] + shared_block + text[fd_pos:]

# Replace the old FanDuel-only generic simulator with the shared historical/PBP engine.
fd_sim_start = '        if fd_sim_clicked:\n            with st.spinner(f"Running {SIMULATION_COUNT:,} FanDuel scoring simulations..."):\n'
fd_signature = '\n        fd_signature = (\n'
start = text.find(fd_sim_start)
if start < 0:
    # Already patched is okay.
    if "simulated_scores = _simulate_scored_player_outcomes(fd_players, \"FanDuel\", rng)" not in text:
        raise SystemExit("FanDuel simulation block anchor not found")
else:
    end = text.find(fd_signature, start)
    if end < 0:
        raise SystemExit("FanDuel simulation end anchor not found")

    replacement = '''        if fd_sim_clicked:\n            with st.spinner(f"Running {SIMULATION_COUNT:,} shared historical/PBP simulations for FanDuel..."):\n                rng = np.random.default_rng()\n                simulated_scores = _simulate_scored_player_outcomes(fd_players, "FanDuel", rng)\n                player_sim = {}\n                for sim_name in fd_players["Name"].astype(str):\n                    if sim_name not in simulated_scores.columns:\n                        continue\n                    values = pd.to_numeric(simulated_scores[sim_name], errors="coerce").dropna().to_numpy(dtype=float)\n                    if not len(values):\n                        continue\n                    player_sim[sim_name] = {\n                        "Mean": float(np.mean(values)),\n                        "P10": float(np.quantile(values, 0.10)),\n                        "P25": float(np.quantile(values, 0.25)),\n                        "P50": float(np.quantile(values, 0.50)),\n                        "P75": float(np.quantile(values, 0.75)),\n                        "P90": float(np.quantile(values, 0.90)),\n                        "P95": float(np.quantile(values, 0.95)),\n                        "P99": float(np.quantile(values, 0.99)),\n                        "StdDev": float(np.std(values)),\n                    }\n                st.session_state["fd_player_sim_" + lineup_mode.replace(" ", "_").lower()] = player_sim\n                st.session_state["fd_simulation_ready_" + lineup_mode.replace(" ", "_").lower()] = True\n            if fd_run_all_clicked:\n                fd_progress_bar.progress(30, text="Shared historical/PBP simulation complete. Building FanDuel lineups...")\n'''
    text = text[:start] + replacement + text[end:]

# Make the shared-engine intent explicit for future edits.
text = text.replace(
    'def _simulate_scored_player_outcomes(players_df, platform, rng):\n    """Simulate player outcomes from historical distributions and shared game scripts.',
    'def _simulate_scored_player_outcomes(players_df, platform, rng):\n    """Shared DK/FD engine: simulate player outcomes from historical distributions and shared game scripts.',
    1,
)

APP.write_text(text, encoding="utf-8")
print("FanDuel now uses the same historical/PBP player simulation engine as DraftKings.")
