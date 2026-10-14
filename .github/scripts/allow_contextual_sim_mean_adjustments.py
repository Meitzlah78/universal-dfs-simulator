from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

marker = '''        # Position-specific volatility targets. Historical data still informs
        # each player's spread, but blending it with a position baseline helps
        # prevent noisy samples from creating extreme tails.
'''

insert = '''        # Allow a small, explainable move away from the source projection.
        # DFF/DraftEdge remain the baseline, while slate context can nudge the
        # simulated mean. Historical/PBP outcomes still determine the shape.
        if np.isfinite(projection) and projection > 0:
            try:
                _team = str(row.get("Team", "")).strip().upper()
                _opp = str(row.get("Opponent", "")).strip().upper()
                _pos = str(row.get("Position", "")).strip().upper().replace(" ", "")
                _injury = str(row.get("Injury Status", row.get("Status", ""))).strip().casefold()

                _pool_context = players_df.copy()
                _pool_context["_ctx_projection"] = pd.to_numeric(
                    _pool_context.get("Projection", 0), errors="coerce"
                ).fillna(0.0)
                _pool_context["_ctx_team"] = _pool_context.get("Team", "").astype(str).str.strip().str.upper()
                _team_totals = _pool_context.groupby("_ctx_team")["_ctx_projection"].sum()
                _positive_team_totals = _team_totals[_team_totals > 0]
                _median_team_total = float(_positive_team_totals.median()) if len(_positive_team_totals) else 0.0
                _team_total = float(_team_totals.get(_team, 0.0))
                _opp_total = float(_team_totals.get(_opp, 0.0)) if _opp else 0.0

                # Game environment: stronger projected games get a modest lift,
                # lower-total environments a modest reduction. Cap at +/-4%.
                _environment_adjustment = 0.0
                if _median_team_total > 0 and (_team_total > 0 or _opp_total > 0):
                    _game_team_average = np.mean([v for v in (_team_total, _opp_total) if v > 0])
                    _environment_adjustment = float(np.clip(
                        (_game_team_average / _median_team_total - 1.0) * 0.12,
                        -0.04,
                        0.04,
                    ))

                # Role concentration: high-share skill players can move slightly
                # above baseline, while thin roles can move slightly below it.
                _role_adjustment = 0.0
                if _team_total > 0 and _pos.split("/")[0] in {"RB", "WR", "TE"}:
                    _share = projection / _team_total
                    if _share >= 0.28:
                        _role_adjustment = 0.025
                    elif _share >= 0.20:
                        _role_adjustment = 0.0125
                    elif _share <= 0.06:
                        _role_adjustment = -0.02
                    elif _share <= 0.10:
                        _role_adjustment = -0.01

                # Questionable tags get only a very small discount; OUT players
                # are already removed elsewhere in the app.
                _injury_adjustment = -0.015 if "question" in _injury else 0.0

                _total_mean_adjustment = float(np.clip(
                    _environment_adjustment + _role_adjustment + _injury_adjustment,
                    -0.08,
                    0.08,
                ))
                projection = max(0.01, projection * (1.0 + _total_mean_adjustment))
            except Exception:
                # Never break a slate because one row is missing context fields.
                pass

'''

if insert in text:
    print("Contextual sim-mean adjustment already applied.")
elif marker in text:
    text = text.replace(marker, insert + marker, 1)
    path.write_text(text, encoding="utf-8")
    print("Added controlled contextual sim-mean adjustments.")
else:
    raise SystemExit("Could not find volatility marker in dfs_app.py")
