from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

old = '''    strength = float(np.clip(correlation_strength, 0.0, 1.0))
    names = pool["Name"].astype(str).tolist()
    stats = {name: {} for name in names}
'''
new = '''    strength = float(np.clip(correlation_strength, 0.0, 1.0))
    names = pool["Name"].astype(str).tolist()

    # FanDuel PBP role inputs: use the same historical player-week data already
    # cached by the simulator. In particular, QB rushing must come from each QB's
    # own history rather than being treated as an RB-only team rushing play.
    _fd_hist = load_nfl_historical_player_stats()
    _fd_hist_index = _build_historical_name_index(_fd_hist) if not _fd_hist.empty else {}
    _fd_qb_rush = {}
    for _, _row in pool.iterrows():
        _name = str(_row.get("Name", ""))
        _pos = str(_row.get("Position", "")).upper().split("/")[0].strip()
        if _pos != "QB" or _fd_hist.empty:
            continue
        try:
            _key = normalize_projection_player_name(_name)
            _matches = _fd_hist_index.get(_key, [])
            if not _matches:
                continue
            _rows = _fd_hist.loc[_matches].copy() if all(isinstance(x, (int, np.integer)) for x in _matches) else pd.DataFrame()
            if _rows.empty:
                continue
            if "season" in _rows.columns and "week" in _rows.columns:
                _rows = _rows.sort_values(["season", "week"]).tail(24)
            _carries_col = next((c for c in ("carries", "rushing_attempts", "rush_attempts") if c in _rows.columns), None)
            _yards_col = next((c for c in ("rushing_yards", "rush_yards") if c in _rows.columns), None)
            _td_col = next((c for c in ("rushing_tds", "rushing_touchdowns", "rush_tds") if c in _rows.columns), None)
            if _carries_col:
                _carries = pd.to_numeric(_rows[_carries_col], errors="coerce").fillna(0).clip(lower=0)
                _avg_carries = float(_carries.mean())
            else:
                _avg_carries = 0.0
            if _yards_col:
                _yards = pd.to_numeric(_rows[_yards_col], errors="coerce").fillna(0)
                _ypc = float(_yards.sum() / max(pd.to_numeric(_rows[_carries_col], errors="coerce").fillna(0).sum(), 1.0)) if _carries_col else 4.5
            else:
                _ypc = 4.5
            if _td_col:
                _rush_tds = pd.to_numeric(_rows[_td_col], errors="coerce").fillna(0).clip(lower=0)
                _td_per_carry = float(_rush_tds.sum() / max(pd.to_numeric(_rows[_carries_col], errors="coerce").fillna(0).sum(), 1.0)) if _carries_col else 0.0
            else:
                _td_per_carry = 0.0
            if _avg_carries > 0:
                _fd_qb_rush[_name] = {
                    "carries": float(np.clip(_avg_carries, 0.0, 14.0)),
                    "ypc": float(np.clip(_ypc, 2.0, 8.5)),
                    "td_per_carry": float(np.clip(_td_per_carry, 0.0, 0.12)),
                }
        except Exception:
            continue

    stats = {name: {} for name in names}
'''
if old not in s:
    if "_fd_qb_rush = {}" in s:
        print("Historical QB rushing setup already applied")
        raise SystemExit(0)
    raise SystemExit("FanDuel PBP setup anchor not found")
s = s.replace(old, new, 1)

old2 = '''            team_points = np.zeros(n, dtype=float)
            team_yards = np.zeros(n, dtype=float)
            giveaways = np.zeros(n, dtype=float)
            sacks_allowed = np.zeros(n, dtype=float)
            for sim_i in range(n):
'''
new2 = '''            team_points = np.zeros(n, dtype=float)
            team_yards = np.zeros(n, dtype=float)
            giveaways = np.zeros(n, dtype=float)
            sacks_allowed = np.zeros(n, dtype=float)
            _qb_rush_role = _fd_qb_rush.get(qb_name, {}) if qb_name else {}
            for sim_i in range(n):
'''
if old2 not in s:
    raise SystemExit("FanDuel team simulation anchor not found")
s = s.replace(old2, new2, 1)

old3 = '''                # Kicking comes from possessions that did not become touchdowns.
                for _, kr in ks.iterrows():
'''
new3 = '''                # Add this QB's historical rushing role as real stat-line events.
                # These are carries/scrambles, rushing yards and rushing TDs before
                # FanDuel scoring; no fantasy points are added after the fact.
                if qb_name and _qb_rush_role:
                    _mean_qb_carries = float(_qb_rush_role.get("carries", 0.0))
                    _qb_carries = int(np.clip(rng.poisson(max(_mean_qb_carries * pace_env, 0.0)), 0, 18))
                    _qb_ypc = float(_qb_rush_role.get("ypc", 4.5))
                    _qb_td_rate = float(_qb_rush_role.get("td_per_carry", 0.0))
                    for _ in range(_qb_carries):
                        _rush_yards = float(np.clip(rng.normal(_qb_ypc, max(2.0, abs(_qb_ypc) * 0.75)), -3.0, 35.0))
                        stats[qb_name]["rushing_yards"][sim_i] += _rush_yards
                        team_yards[sim_i] += max(_rush_yards, 0.0)
                        if rng.random() < _qb_td_rate * score_env:
                            stats[qb_name]["rushing_tds"][sim_i] += 1
                            team_points[sim_i] += 7

                # Kicking comes from possessions that did not become touchdowns.
                for _, kr in ks.iterrows():
'''
if old3 not in s:
    raise SystemExit("FanDuel kicking anchor not found")
s = s.replace(old3, new3, 1)

p.write_text(s)
print("Added historical QB rushing roles to FanDuel PBP")
