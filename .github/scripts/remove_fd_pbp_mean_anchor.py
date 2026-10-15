from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''        mean = float(np.mean(vals)) if len(vals) else 0.0
        # Calibrate only the marginal mean; shared play outcomes/correlation stay intact.
        # Do not clip this ratio: clipping can leave a player's simulated mean
        # several points away from the FanDuel target even after calibration.
        if mean > 0 and target > 0:
            vals *= float(target / mean)
        elif target > 0:
            vals = np.maximum(0.0, rng.normal(target, max(0.75, target * 0.35), n))
        out[name] = np.maximum(vals, 0.0)
'''
new = '''        # Keep the football/PBP result as the simulated outcome. Projection is an
        # input for usage/game setup, not a target that every player's final mean
        # must be forced back to. Only use a projection-shaped fallback if the
        # event engine produced no usable scoring at all for a projected player.
        if (not len(vals) or not np.isfinite(vals).any()) and target > 0:
            vals = np.maximum(0.0, rng.normal(target, max(0.75, target * 0.35), n))
        out[name] = np.maximum(np.nan_to_num(vals, nan=0.0), 0.0)
'''
if old not in s:
    raise SystemExit("Remaining FanDuel PBP mean-anchor block not found")
s = s.replace(old, new, 1)
p.write_text(s)
print("Removed remaining FanDuel PBP projection mean anchor")
