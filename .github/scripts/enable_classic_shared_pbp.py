from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''def simulate_fd_play_by_play(players_df, rng, n=SIMULATION_COUNT, correlation_strength=1.0):
    """FanDuel-only play-by-play NFL engine: simulate shared plays, then score player stat lines."""'''
new = '''def simulate_fd_play_by_play(players_df, rng, n=SIMULATION_COUNT, correlation_strength=1.0, platform="FanDuel"):
    """Shared NFL play-by-play engine for FanDuel and DraftKings Classic.

    The engine creates complete correlated game scripts first, then applies the
    selected site's scoring rules. Keeping one football engine prevents DK and
    FD player outcomes from drifting apart while preserving site-specific scoring.
    """'''
if old not in text:
    raise SystemExit("PBP function signature anchor not found")
text = text.replace(old, new, 1)

old = '''        vals = np.asarray(score_nfl_stat_line(line, "FanDuel"), dtype=float)'''
new = '''        vals = np.asarray(score_nfl_stat_line(line, platform), dtype=float)'''
if old not in text:
    raise SystemExit("PBP scoring anchor not found")
text = text.replace(old, new, 1)

old = '''        # Simulate stat lines first, then calculate fantasy points with site scoring.
        rng = np.random.default_rng()
        outcomes = _simulate_scored_player_outcomes(eligible_players, platform, rng)'''
new = '''        # Simulate stat lines first, then calculate fantasy points with site scoring.
        rng = np.random.default_rng()
        # DraftKings Classic now consumes the same literal shared-play football
        # engine used by FanDuel. One complete slate script is generated per row,
        # so QB/receiver, rushing, turnover, DST and game-environment outcomes stay
        # correlated before the 5,000 candidate and 10,000 field lineup matrices
        # score those rows. Showdown keeps its existing configurable correlation path.
        if platform == "DraftKings" and lineup_mode == "Classic":
            if workflow_status is not None:
                workflow_status.info(
                    f"Step 1 of 4: Running {SIMULATION_COUNT:,} shared PBP slate outcomes for DraftKings Classic..."
                )
            outcomes = simulate_fd_play_by_play(
                eligible_players,
                rng,
                n=SIMULATION_COUNT,
                correlation_strength=1.0,
                platform="DraftKings",
            )
            if isinstance(outcomes, pd.DataFrame) and not outcomes.empty:
                st.session_state["dk_classic_sim_engine"] = "Shared NFL PBP"
        else:
            outcomes = _simulate_scored_player_outcomes(eligible_players, platform, rng)'''
if old not in text:
    raise SystemExit("run_game_simulations anchor not found")
text = text.replace(old, new, 1)

old = '''        st.caption(
            "Classic roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), DST. "
            "Salary cap: $50,000. The 5,000-lineup build automatically spreads exposure instead of repeatedly selecting the same top players."
        )'''
new = '''        st.caption(
            "Classic roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), DST. "
            "Salary cap: $50,000. SIM uses the shared NFL play-by-play engine so every lineup is scored against the same correlated game outcomes. "
            "The 5,000-lineup build automatically spreads exposure instead of repeatedly selecting the same top players."
        )'''
if old not in text:
    raise SystemExit("Classic caption anchor not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Enabled shared NFL PBP engine for DraftKings Classic")
