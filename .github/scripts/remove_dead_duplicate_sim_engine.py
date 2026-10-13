from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

start = text.find("\n    # ================================\n    # SETTINGS\n    # ================================\n\n    SIMULATIONS = SIMULATION_COUNT\n", text.find("        st.stop()"))
if start == -1:
    if text.count("def _simulate_scored_player_outcomes(") == 1:
        print("Dead duplicate simulation engine already removed")
        raise SystemExit(0)
    raise SystemExit("Could not find dead duplicate simulation engine start")

end_marker = "\nelse:\n\n    # ================================\n    # PLAYER POOL\n"
end = text.find(end_marker, start)
if end == -1:
    raise SystemExit("Could not find DraftKings branch after duplicate simulation engine")

block = text[start:end]
required = [
    "DFS_SCORING_RULES = {",
    "def score_nfl_stat_line(stats, platform):",
    "def _simulate_scored_player_outcomes(players_df, platform, rng):",
]
if not all(item in block for item in required):
    raise SystemExit("Refusing cleanup because the targeted block does not match the expected duplicate engine")

text = text[:start] + text[end:]

if text.count("def _simulate_scored_player_outcomes(") != 1:
    raise SystemExit("Cleanup did not leave exactly one shared simulation engine definition")
if text.count("def score_nfl_stat_line(") != 1:
    raise SystemExit("Cleanup did not leave exactly one scoring function definition")

APP.write_text(text, encoding="utf-8")
print("Removed dead duplicate simulation/scoring engine; one shared engine remains")
