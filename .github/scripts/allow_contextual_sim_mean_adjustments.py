from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''        # Allow a controlled, explainable move away from the source projection.
        # DFF/DraftEdge remain the baseline, while slate context can meaningfully
        # nudge the simulated mean. Historical/PBP outcomes still determine shape.
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

                # Game environment now carries enough weight to matter, while
                # remaining bounded so the source projection is still the anchor.
                _environment_adjustment = 0.0
                if _median_team_total > 0 and (_team_total > 0 or _opp_total > 0):
                    _game_team_average = np.mean([v for v in (_team_total, _opp_total) if v > 0])
                    _environment_adjustment = float(np.clip(
                        (_game_team_average / _median_team_total - 1.0) * 0.24,
                        -0.06,
                        0.06,
                    ))

                # Role concentration can now create roughly half-point to one-plus
                # point moves for meaningful skill-player roles on typical projections.
                _role_adjustment = 0.0
                if _team_total > 0 and _pos.split("/")[0] in {"RB", "WR", "TE"}:
                    _share = projection / _team_total
                    if _share >= 0.28:
                        _role_adjustment = 0.04
                    elif _share >= 0.20:
                        _role_adjustment = 0.02
                    elif _share <= 0.06:
                        _role_adjustment = -0.03
                    elif _share <= 0.10:
                        _role_adjustment = -0.015

                # Questionable players receive a modest risk discount. OUT players
                # continue to be removed elsewhere in the app.
                _injury_adjustment = -0.025 if "question" in _injury else 0.0

                # Hard cap at +/-10% prevents unsupported projection swings.
                _total_mean_adjustment = float(np.clip(
                    _environment_adjustment + _role_adjustment + _injury_adjustment,
                    -0.10,
                    0.10,
                ))
                projection = max(0.01, projection * (1.0 + _total_mean_adjustment))
            except Exception:
                # Never break a slate because one row is missing context fields.
                pass

'''

new = '''        # Let the simulation mean move away from DFF/DraftEdge when slate context
        # gives us a real reason. The source projection remains the anchor, while
        # historical/PBP outcomes still determine the shape and volatility.
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

                # Environment signal: scale projected game strength into a direct
                # point adjustment instead of only a tiny percentage change.
                _environment_points = 0.0
                if _median_team_total > 0 and (_team_total > 0 or _opp_total > 0):
                    _game_team_average = np.mean([v for v in (_team_total, _opp_total) if v > 0])
                    _environment_points = float(np.clip(
                        (_game_team_average / _median_team_total - 1.0) * 3.0,
                        -0.75,
                        0.75,
                    ))

                # Role signal: concentrated skill-player roles get a direct bump,
                # while thin roles get a small reduction. This creates meaningful
                # movement even for mid-range projections.
                _role_points = 0.0
                if _team_total > 0 and _pos.split("/")[0] in {"RB", "WR", "TE"}:
                    _share = projection / _team_total
                    if _share >= 0.30:
                        _role_points = 0.90
                    elif _share >= 0.24:
                        _role_points = 0.60
                    elif _share >= 0.18:
                        _role_points = 0.30
                    elif _share <= 0.05:
                        _role_points = -0.45
                    elif _share <= 0.09:
                        _role_points = -0.25

                _injury_points = -0.35 if "question" in _injury else 0.0

                # Scale the allowed movement with player importance. Cheap fringe
                # players should not move as much as core plays. Hard cap remains.
                _importance_cap = float(np.clip(0.35 + projection * 0.055, 0.50, 1.50))
                _context_points = float(np.clip(
                    _environment_points + _role_points + _injury_points,
                    -_importance_cap,
                    _importance_cap,
                ))
                projection = max(0.01, projection + _context_points)
            except Exception:
                # Never break a slate because one row is missing context fields.
                pass

'''

if new in text:
    print("Direct-point contextual mean adjustment already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Changed contextual sim-mean adjustments from tiny percentages to controlled point moves.")
else:
    raise SystemExit("Could not find existing contextual sim-mean adjustment block")
