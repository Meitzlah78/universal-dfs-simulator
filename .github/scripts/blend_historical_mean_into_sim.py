from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old_hist = '''        has_player_history = historical_result is not None
        if historical_result is not None:
            historical_points, recency_weights = historical_result
            probabilities = recency_weights / recency_weights.sum()
            scores = rng.choice(
                historical_points, size=n, replace=True, p=probabilities
            ).astype(float)
'''

new_hist = '''        has_player_history = historical_result is not None
        historical_anchor_mean = np.nan
        historical_games_used = 0
        if historical_result is not None:
            historical_points, recency_weights = historical_result
            probabilities = recency_weights / recency_weights.sum()
            historical_games_used = int(len(historical_points))
            try:
                historical_anchor_mean = float(np.average(historical_points, weights=probabilities))
            except Exception:
                historical_anchor_mean = float(np.mean(historical_points)) if len(historical_points) else np.nan
            scores = rng.choice(
                historical_points, size=n, replace=True, p=probabilities
            ).astype(float)
'''

history_blend_marker = '''        # Let the simulation mean move away from DFF/DraftEdge when slate context
'''

history_blend = '''        # Blend the player's recency-weighted historical fantasy mean directly
        # into the simulation target. This is the missing link that lets core
        # players move away from DFF/DraftEdge when their own NFL history supports it.
        # Keep the source projection as the stronger anchor so old/sparse history
        # cannot overwhelm current role, matchup, or injury information.
        if (
            has_player_history
            and historical_games_used >= 4
            and np.isfinite(historical_anchor_mean)
            and historical_anchor_mean >= 0
            and np.isfinite(projection)
            and projection > 0
        ):
            _historical_gap = historical_anchor_mean - projection
            # More history earns slightly more influence. Typical weight is 18-28%.
            _history_weight = float(np.clip(0.14 + 0.012 * historical_games_used, 0.18, 0.28))
            _history_points = _historical_gap * _history_weight
            # Core players may move more than fringe players, but no historical
            # signal alone can create an unsupported multi-point jump.
            _history_cap = float(np.clip(0.30 + projection * 0.065, 0.45, 1.35))
            _history_points = float(np.clip(_history_points, -_history_cap, _history_cap))
            projection = max(0.01, projection + _history_points)

'''

old_center = '''                    # Preserve the historical/sample mean instead of forcing
                    # simulated outcomes to average the supplied projection.
                    scores = projection + standardized
'''

new_center = '''                    # Center on the blended target mean. The target already
                    # includes recency-weighted player history plus slate context,
                    # so we keep the historical shape without snapping back to raw DFF.
                    scores = projection + standardized
'''

changed = False
if new_hist not in text:
    if old_hist not in text:
        raise SystemExit("Could not find historical sampling block")
    text = text.replace(old_hist, new_hist, 1)
    changed = True

if history_blend not in text:
    if history_blend_marker not in text:
        raise SystemExit("Could not find contextual mean marker")
    text = text.replace(history_blend_marker, history_blend + history_blend_marker, 1)
    changed = True

if old_center in text:
    text = text.replace(old_center, new_center, 1)
    changed = True

if changed:
    path.write_text(text, encoding="utf-8")
    print("Blended recency-weighted historical player means into simulation targets.")
else:
    print("Historical mean blend already applied.")
