from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

# Keep the play-by-play engine, but simulate a representative bank of complete
# shared game scripts and bootstrap those complete rows to the requested count.
# Resampling whole rows preserves every QB/receiver/team/opponent correlation.
old_start = '''def simulate_fd_play_by_play(players_df, rng, n=SIMULATION_COUNT, correlation_strength=1.0):
    """FanDuel-only play-by-play NFL engine: simulate shared plays, then score player stat lines."""
    if not isinstance(players_df, pd.DataFrame) or players_df.empty:
        return pd.DataFrame()
    pool = players_df.drop_duplicates("Name", keep="first").copy().reset_index(drop=True)
'''
new_start = '''def simulate_fd_play_by_play(players_df, rng, n=SIMULATION_COUNT, correlation_strength=1.0):
    """FanDuel-only play-by-play NFL engine: simulate shared plays, then score player stat lines."""
    if not isinstance(players_df, pd.DataFrame) or players_df.empty:
        return pd.DataFrame()
    requested_n = max(1, int(n))
    # A full slate at 10,000 x ~64 literal plays is millions of Python iterations.
    # Build 1,000 complete correlated game scripts, then resample COMPLETE scripts.
    # This keeps Step 1 fast without breaking within-game/player correlation.
    n = min(requested_n, 1000)
    pool = players_df.drop_duplicates("Name", keep="first").copy().reset_index(drop=True)
'''
if old_start not in s:
    raise SystemExit("play-by-play helper start not found")
s = s.replace(old_start, new_start, 1)
old_end = '''        out[name] = np.maximum(vals, 0.0)
    return pd.DataFrame(out)
'''
new_end = '''        out[name] = np.maximum(vals, 0.0)
    result = pd.DataFrame(out)
    if requested_n > n and not result.empty:
        # Resample row indices once for the entire slate so every player's score
        # comes from the same underlying simulated game script.
        take = rng.integers(0, n, size=requested_n)
        result = result.iloc[take].reset_index(drop=True)
    return result
'''
if old_end not in s:
    raise SystemExit("play-by-play helper return not found")
s = s.replace(old_end, new_end, 1)

p.write_text(s)
print("FanDuel play-by-play Step 1 optimized with correlated scenario-bank resampling")
