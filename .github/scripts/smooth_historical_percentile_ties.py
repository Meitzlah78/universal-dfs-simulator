from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''                    # Preserve the historical/sample mean instead of forcing
                    # simulated outcomes to average the supplied projection.
                    scores = projection + standardized
'''

new = '''                    # Center the rescaled historical shape on the blended target mean.
                    scores = projection + standardized
                    # Historical weekly scores are discrete, so repeated sampled values can
                    # make P90/P95/P99 collapse to the exact same number. Add a very small
                    # mean-zero smoothing term only to historical samples. This separates
                    # percentile ties without materially changing the player's mean or spread.
                    if has_player_history:
                        _tie_smoothing_std = max(0.05, target_std * 0.04)
                        _tie_noise = rng.normal(0.0, _tie_smoothing_std, size=n)
                        _tie_noise = _tie_noise - float(np.mean(_tie_noise))
                        scores = scores + _tie_noise
'''

if new in text:
    print("Historical percentile tie smoothing already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Added small mean-zero smoothing to historical samples to separate percentile ties.")
else:
    raise SystemExit("Could not find historical re-centering block")
