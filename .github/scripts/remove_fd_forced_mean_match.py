from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''    # projection several points. Multiplying a player's whole final distribution
    # by one positive constant preserves its event shape and shared-script links.
    if not result.empty:
        target_map = dict(zip(pool["Name"].astype(str), pool["Projection"].astype(float)))
        for player_name in result.columns:
            target = float(target_map.get(str(player_name), 0.0) or 0.0)
            final_vals = pd.to_numeric(result[player_name], errors="coerce").fillna(0.0).to_numpy(dtype=float)
            final_mean = float(np.mean(final_vals)) if len(final_vals) else 0.0
            if target > 0 and final_mean > 0:
                result[player_name] = np.maximum(final_vals * (target / final_mean), 0.0)
            elif target > 0 and final_mean <= 0:
                result[player_name] = np.maximum(
                    rng.normal(target, max(0.25, target * 0.35), len(result)), 0.0
                )
'''
new = '''    # Keep the PBP engine's simulated means. Projection is an input expectation,
    # not a hard target that the finished simulation must equal. This lets game
    # scripts, usage, touchdowns, turnovers, and shared play outcomes move a
    # player's Sim Pts above or below Projection while preserving the P10-P99 shape.
'''

if old not in s:
    raise SystemExit("FanDuel forced mean-match block not found")
s = s.replace(old, new, 1)
p.write_text(s)
print("Removed FanDuel final projection mean-match")
