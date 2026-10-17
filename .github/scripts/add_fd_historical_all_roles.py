from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

anchor = '''    stats = {name: {} for name in names}
'''
insert = '''    # Historical opportunity/efficiency profiles for every offensive position.
    # These feed the play generator itself; they do not add fantasy points after simulation.
    _fd_hist_roles = {}
    if not _fd_hist.empty:
        for _, _row in pool.iterrows():
            _name = str(_row.get("Name", ""))
            _pos = str(_row.get("Position", "")).upper().split("/")[0].strip()
            if _pos not in {"QB", "RB", "WR", "TE", "K"}:
                continue
            try:
                _matches = _fd_hist_index.get(normalize_projection_player_name(_name), [])
                if not _matches or not all(isinstance(x, (int, np.integer)) for x in _matches):
                    continue
                _rows = _fd_hist.loc[_matches].copy()
                if _rows.empty:
                    continue
                if "season" in _rows.columns and "week" in _rows.columns:
                    _rows = _rows.sort_values(["season", "week"]).tail(24)
                def _avg(*cols):
                    c = next((x for x in cols if x in _rows.columns), None)
                    return float(pd.to_numeric(_rows[c], errors="coerce").fillna(0).clip(lower=0).mean()) if c else 0.0
                _fd_hist_roles[_name] = {
                    "carries": _avg("carries", "rushing_attempts", "rush_attempts"),
                    "targets": _avg("targets"),
                    "receptions": _avg("receptions"),
                    "rush_yards": _avg("rushing_yards", "rush_yards"),
                    "rec_yards": _avg("receiving_yards", "rec_yards"),
                    "rush_tds": _avg("rushing_tds", "rushing_touchdowns", "rush_tds"),
                    "rec_tds": _avg("receiving_tds", "receiving_touchdowns", "rec_tds"),
                    "pass_attempts": _avg("attempts", "passing_attempts"),
                }
            except Exception:
                continue

    stats = {name: {} for name in names}
'''
if "_fd_hist_roles = {}" not in s:
    if anchor not in s: raise SystemExit("historical role insertion anchor missing")
    s = s.replace(anchor, insert, 1)

old = '''            rec_w = np.clip(recs["Projection"].to_numpy(dtype=float), 0.05, None) if len(recs) else np.array([])
            rb_w = np.clip(rbs["Projection"].to_numpy(dtype=float), 0.05, None) if len(rbs) else np.array([])
            if len(rec_w): rec_w = rec_w / rec_w.sum()
            if len(rb_w): rb_w = rb_w / rb_w.sum()
'''
new = '''            # Blend current projection with each player's historical opportunity.
            # Targets determine receiver selection; carries determine RB rush selection.
            if len(recs):
                _rec_proj = np.clip(recs["Projection"].to_numpy(dtype=float), 0.05, None)
                _rec_hist = np.asarray([max(_fd_hist_roles.get(str(x), {}).get("targets", 0.0), 0.0) for x in rec_names], dtype=float)
                if _rec_hist.sum() > 0:
                    _rec_hist = _rec_hist / _rec_hist.sum()
                    _rec_proj = _rec_proj / _rec_proj.sum()
                    rec_w = 0.70 * _rec_hist + 0.30 * _rec_proj
                else:
                    rec_w = _rec_proj / _rec_proj.sum()
            else: rec_w = np.array([])
            if len(rbs):
                _rb_proj = np.clip(rbs["Projection"].to_numpy(dtype=float), 0.05, None)
                _rb_hist = np.asarray([max(_fd_hist_roles.get(str(x), {}).get("carries", 0.0), 0.0) for x in rb_names], dtype=float)
                if _rb_hist.sum() > 0:
                    _rb_hist = _rb_hist / _rb_hist.sum()
                    _rb_proj = _rb_proj / _rb_proj.sum()
                    rb_w = 0.75 * _rb_hist + 0.25 * _rb_proj
                else:
                    rb_w = _rb_proj / _rb_proj.sum()
            else: rb_w = np.array([])
'''
if old in s:
    s = s.replace(old, new, 1)
elif "_rec_hist = np.asarray" not in s:
    raise SystemExit("receiver/rusher weight anchor missing")

old2 = '''                        catch_prob = float(np.clip(0.64 + 0.025 * (rec_w[target_i] - np.mean(rec_w)), 0.50, 0.78))
                        if rng.random() < catch_prob:
                            yards = float(np.clip(rng.gamma(2.0, 5.6) * score_env, 0.0, 75.0))
'''
new2 = '''                        _role = _fd_hist_roles.get(receiver, {})
                        _hist_targets = float(_role.get("targets", 0.0))
                        _hist_recs = float(_role.get("receptions", 0.0))
                        _hist_catch = (_hist_recs / _hist_targets) if _hist_targets > 0 else 0.64
                        catch_prob = float(np.clip(0.70 * _hist_catch + 0.30 * 0.64, 0.42, 0.88))
                        if rng.random() < catch_prob:
                            _hist_ypr = float(_role.get("rec_yards", 0.0)) / max(_hist_recs, 1.0) if _hist_recs > 0 else 11.2
                            _yard_mean = float(np.clip(_hist_ypr, 5.0, 20.0))
                            yards = float(np.clip(rng.gamma(2.0, _yard_mean / 2.0) * score_env, 0.0, 75.0))
'''
if old2 in s:
    s = s.replace(old2, new2, 1)
elif "_hist_catch" not in s:
    raise SystemExit("catch efficiency anchor missing")

old3 = '''                        yards = float(np.clip(rng.normal(4.35 * np.sqrt(score_env), 4.2), -4.0, 45.0))
'''
new3 = '''                        _rb_role = _fd_hist_roles.get(runner, {})
                        _rb_carries = float(_rb_role.get("carries", 0.0))
                        _rb_ypc = float(_rb_role.get("rush_yards", 0.0)) / max(_rb_carries, 1.0) if _rb_carries > 0 else 4.35
                        _rb_ypc = float(np.clip(_rb_ypc, 2.5, 7.0))
                        yards = float(np.clip(rng.normal(_rb_ypc * np.sqrt(score_env), max(3.2, _rb_ypc)), -4.0, 45.0))
'''
if old3 in s:
    s = s.replace(old3, new3, 1)
elif "_rb_ypc" not in s:
    raise SystemExit("RB efficiency anchor missing")

p.write_text(s)
print("Added historical roles for QB/RB/WR/TE to FanDuel PBP")
