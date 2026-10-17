from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''        vals = np.asarray(score_nfl_stat_line(line, "FanDuel"), dtype=float)
        # Keep the football/PBP result as the simulated outcome. Projection is an
        # input for usage/game setup, not a target that every player's final mean
        # must be forced back to. Only use a projection-shaped fallback if the
        # event engine produced no usable scoring at all for a projected player.
        if (not len(vals) or not np.isfinite(vals).any()) and target > 0:
            vals = np.maximum(0.0, rng.normal(target, max(0.75, target * 0.35), n))
        out[name] = np.maximum(np.nan_to_num(vals, nan=0.0), 0.0)
'''
new = '''        vals = np.asarray(score_nfl_stat_line(line, "FanDuel"), dtype=float)
        # Projection-informed ROLE calibration. The literal PBP engine intentionally
        # remains the source of each outcome and its correlations, but a generic
        # 64-play offense can materially understate the workload of elite players.
        # Softly scale the generated stat-line scores toward the player's current
        # expectation without forcing the finished simulation mean to equal it.
        # An 0.80 exponent leaves roughly 20% of the raw PBP disagreement intact;
        # the bounded factor also prevents tiny/raw samples from exploding.
        raw_mean = float(np.mean(vals)) if len(vals) and np.isfinite(vals).any() else 0.0
        if raw_mean > 0 and target > 0:
            role_factor = float(np.clip((target / raw_mean) ** 0.80, 0.60, 1.80))
            vals = vals * role_factor
        elif target > 0:
            vals = np.maximum(0.0, rng.normal(target, max(0.75, target * 0.35), n))
        out[name] = np.maximum(np.nan_to_num(vals, nan=0.0), 0.0)
'''

if old in s:
    s = s.replace(old, new, 1)
elif "Projection-informed ROLE calibration" in s:
    print("FanDuel PBP role calibration already applied")
    raise SystemExit(0)
else:
    raise SystemExit("FanDuel PBP output block not found")

p.write_text(s)
print("Applied soft FanDuel PBP role calibration")
