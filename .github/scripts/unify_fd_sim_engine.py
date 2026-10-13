from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

SHARED_MARKER = "# SHARED HISTORICAL/PBP PLAYER SIMULATION ENGINE"


def dedent_one_level(block):
    lines = []
    for line in block.splitlines(True):
        lines.append(line[4:] if line.startswith("    ") else line)
    return "".join(lines)


# DraftKings currently contains two pieces that FanDuel needs:
# 1) scoring + the actual player-outcome simulation function near SETTINGS
# 2) historical/PBP loader/helper functions farther down the DK branch.
# Lift both existing blocks unchanged into shared scope before the site split.
if SHARED_MARKER not in text:
    fd_branch = '\nif platform == "FanDuel":\n'
    else_marker = '\nelse:\n\n    # ================================\n    # SETTINGS\n'
    player_pool_marker = '\n    # ================================\n    # PLAYER POOL\n'
    history_start_marker = (
        '    @st.cache_data(show_spinner=False, ttl=86400)\n'
        '    @st.cache_data(show_spinner=False, ttl=86400)\n'
        '    def _download_nfl_historical_player_stats():\n'
    )
    history_end_marker = '\n\n    players_df = apply_injury_statuses('

    fd_pos = text.find(fd_branch)
    if fd_pos < 0:
        raise SystemExit("FanDuel branch anchor not found")
    else_pos = text.find(else_marker, fd_pos)
    if else_pos < 0:
        raise SystemExit("DraftKings else/settings anchor not found")
    pool_pos = text.find(player_pool_marker, else_pos)
    if pool_pos < 0:
        raise SystemExit("DraftKings player-pool anchor not found")

    engine_block = text[else_pos + len("\nelse:\n"):pool_pos]
    for name in ["def score_nfl_stat_line", "def _simulate_scored_player_outcomes"]:
        if name not in engine_block:
            raise SystemExit(f"Engine block is missing {name}")

    history_start = text.find(history_start_marker, pool_pos)
    if history_start < 0:
        raise SystemExit("Historical/PBP helper block start not found")
    history_end = text.find(history_end_marker, history_start)
    if history_end < 0:
        raise SystemExit("Historical/PBP helper block end not found")
    history_block = text[history_start:history_end]
    for name in [
        "def load_nfl_historical_player_stats",
        "def load_nfl_pbp_game_history",
        "def _historical_player_average",
        "def _build_historical_name_index",
    ]:
        if name not in history_block:
            raise SystemExit(f"Historical/PBP helper block is missing {name}")

    # Remove the later helper block first so earlier indexes remain valid.
    text = text[:history_start] + text[history_end:]

    # Re-find the DK settings block after the first removal, then remove it from
    # the DraftKings-only branch while keeping the DK Player Pool inside else:.
    fd_pos = text.find(fd_branch)
    else_pos = text.find(else_marker, fd_pos)
    pool_pos = text.find(player_pool_marker, else_pos)
    engine_block = text[else_pos + len("\nelse:\n"):pool_pos]
    text = text[:else_pos] + "\nelse:\n" + text[pool_pos:]

    shared_block = (
        "\n" + SHARED_MARKER + "\n"
        + dedent_one_level(engine_block).lstrip("\n")
        + "\n"
        + dedent_one_level(history_block).lstrip("\n")
        + "\n"
    )

    # Both helper groups are now defined before either site branch executes.
    fd_pos = text.find(fd_branch)
    text = text[:fd_pos] + shared_block + text[fd_pos:]

# Replace the old FanDuel-only generic simulator with the exact shared engine.
fd_sim_start = '        if fd_sim_clicked:\n            with st.spinner(f"Running {SIMULATION_COUNT:,} FanDuel scoring simulations..."):\n'
fd_signature = '\n        fd_signature = (\n'
start = text.find(fd_sim_start)
if start < 0:
    if 'simulated_scores = _simulate_scored_player_outcomes(fd_players, "FanDuel", rng)' not in text:
        raise SystemExit("FanDuel simulation block anchor not found")
else:
    end = text.find(fd_signature, start)
    if end < 0:
        raise SystemExit("FanDuel simulation end anchor not found")

    replacement = '''        if fd_sim_clicked:\n            with st.spinner(f"Running {SIMULATION_COUNT:,} shared historical/PBP simulations for FanDuel..."):\n                rng = np.random.default_rng()\n                simulated_scores = _simulate_scored_player_outcomes(fd_players, "FanDuel", rng)\n                player_sim = {}\n                for sim_name in fd_players["Name"].astype(str):\n                    if sim_name not in simulated_scores.columns:\n                        continue\n                    values = pd.to_numeric(simulated_scores[sim_name], errors="coerce").dropna().to_numpy(dtype=float)\n                    if not len(values):\n                        continue\n                    player_sim[sim_name] = {\n                        "Mean": float(np.mean(values)),\n                        "P10": float(np.quantile(values, 0.10)),\n                        "P25": float(np.quantile(values, 0.25)),\n                        "P50": float(np.quantile(values, 0.50)),\n                        "P75": float(np.quantile(values, 0.75)),\n                        "P90": float(np.quantile(values, 0.90)),\n                        "P95": float(np.quantile(values, 0.95)),\n                        "P99": float(np.quantile(values, 0.99)),\n                        "StdDev": float(np.std(values)),\n                    }\n                st.session_state["fd_player_sim_" + lineup_mode.replace(" ", "_").lower()] = player_sim\n                st.session_state["fd_simulation_ready_" + lineup_mode.replace(" ", "_").lower()] = True\n            if fd_run_all_clicked:\n                fd_progress_bar.progress(30, text="Shared historical/PBP simulation complete. Building FanDuel lineups...")\n'''
    text = text[:start] + replacement + text[end:]

# Make the shared-engine intent obvious for future edits.
text = text.replace(
    'def _simulate_scored_player_outcomes(players_df, platform, rng):\n    """Simulate player outcomes from historical distributions and shared game scripts.',
    'def _simulate_scored_player_outcomes(players_df, platform, rng):\n    """Shared DK/FD engine: simulate player outcomes from historical distributions and shared game scripts.',
    1,
)

APP.write_text(text, encoding="utf-8")
print("FanDuel now uses the exact DraftKings historical/PBP player simulation engine.")
