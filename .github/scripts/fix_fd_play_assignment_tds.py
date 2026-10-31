from pathlib import Path
p=Path('dfs_app.py'); s=p.read_text()
old='''                    elif rb_names:
                        runner_i = int(rng.choice(len(rb_names), p=rb_w))
                        runner = rb_names[runner_i]
                        _rb_role = _fd_hist_roles.get(runner, {})
                        _rb_carries = float(_rb_role.get("carries", 0.0))
                        _rb_ypc = float(_rb_role.get("rush_yards", 0.0)) / max(_rb_carries, 1.0) if _rb_carries > 0 else 4.35
                        _rb_ypc = float(np.clip(_rb_ypc, 2.5, 7.0))
                        yards = float(np.clip(rng.normal(_rb_ypc * np.sqrt(score_env), max(3.2, _rb_ypc)), -4.0, 45.0))
                        yards = max(yards, -4.0)
                        stats[runner]["rushing_yards"][sim_i] += yards
                        team_yards[sim_i] += max(yards, 0.0)
                        if rng.random() < float(np.clip(0.026 * score_env + max(yards - 15.0, 0.0) * 0.002, 0.01, 0.14)):
                            stats[runner]["rushing_tds"][sim_i] += 1
                            team_points[sim_i] += 7
'''
new='''                    elif rb_names or qb_name:
                        # Allocate QB rushing INSIDE the existing run-play pool so it
                        # replaces an RB carry rather than creating an extra team play.
                        _qb_carries_hist = float(_fd_hist_roles.get(qb_name, {}).get("carries", 0.0)) if qb_name else 0.0
                        _rb_carries_hist = float(sum(max(_fd_hist_roles.get(x, {}).get("carries", 0.0), 0.0) for x in rb_names))
                        _qb_rush_share = float(np.clip(_qb_carries_hist / max(_qb_carries_hist + _rb_carries_hist, 1.0), 0.0, 0.35))
                        _use_qb = bool(qb_name and rng.random() < _qb_rush_share)
                        if _use_qb:
                            runner = qb_name
                            _run_role = _fd_hist_roles.get(runner, {})
                            _carries = float(_run_role.get("carries", 0.0))
                            _ypc = float(_run_role.get("rush_yards", 0.0)) / max(_carries, 1.0) if _carries > 0 else 4.5
                            _ypc = float(np.clip(_ypc, 2.0, 8.5))
                        elif rb_names:
                            runner_i = int(rng.choice(len(rb_names), p=rb_w))
                            runner = rb_names[runner_i]
                            _run_role = _fd_hist_roles.get(runner, {})
                            _carries = float(_run_role.get("carries", 0.0))
                            _ypc = float(_run_role.get("rush_yards", 0.0)) / max(_carries, 1.0) if _carries > 0 else 4.35
                            _ypc = float(np.clip(_ypc, 2.5, 7.0))
                        else:
                            continue
                        yards = float(np.clip(rng.normal(_ypc * np.sqrt(score_env), max(3.2, abs(_ypc))), -4.0, 45.0))
                        stats[runner]["rushing_yards"][sim_i] += yards
                        team_yards[sim_i] += max(yards, 0.0)
                        _hist_rush_td_rate = float(_run_role.get("rush_tds", 0.0)) / max(_carries, 1.0) if _carries > 0 else 0.026
                        _rush_td_prob = float(np.clip((0.80 * _hist_rush_td_rate + 0.20 * 0.026) * score_env + max(yards - 15.0, 0.0) * 0.001, 0.004, 0.16))
                        if rng.random() < _rush_td_prob:
                            stats[runner]["rushing_tds"][sim_i] += 1
                            team_points[sim_i] += 7
'''
if old not in s:
    if '_qb_rush_share' not in s: raise SystemExit('run assignment anchor missing')
else: s=s.replace(old,new,1)
old2='''                            td_prob = float(np.clip(0.035 * score_env + max(yards - 20.0, 0.0) * 0.0015, 0.015, 0.18))
'''
new2='''                            _hist_rec_td_rate = float(_role.get("rec_tds", 0.0)) / max(_hist_targets, 1.0) if _hist_targets > 0 else 0.035
                            td_prob = float(np.clip((0.80 * _hist_rec_td_rate + 0.20 * 0.035) * score_env + max(yards - 20.0, 0.0) * 0.001, 0.006, 0.18))
'''
if old2 in s: s=s.replace(old2,new2,1)
elif '_hist_rec_td_rate' not in s: raise SystemExit('receiving TD anchor missing')
start='''                # Add this QB's historical rushing role as real stat-line events.
'''
end='''                # Kicking comes from possessions that did not become touchdowns.
'''
if start in s:
    a=s.index(start); b=s.index(end,a); s=s[:a]+end+s[b+len(end):]
p.write_text(s)
print('Fixed FanDuel run-play assignment and historical TD rates')
